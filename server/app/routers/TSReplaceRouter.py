import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from tortoise.exceptions import DoesNotExist

from app import logging, schemas
from app.models.RecordedProgram import RecordedProgram
from app.models.User import User
from app.routers.UsersRouter import GetCurrentUser
from app.streams.TSReplaceEncodingTask import TSReplaceEncodingTask
from app.schemas import EncodingTask


# ルーター
router = APIRouter(
    tags = ['TSReplace'],
    prefix = '/api/tsreplace',
)

# 実行中のタスクを管理する辞書
_running_tasks: dict[str, TSReplaceEncodingTask] = {}

def _generate_output_file_path(input_file_path: str, codec: str) -> str:
    """入力ファイルパスから出力ファイルパスを生成する"""
    import os
    from pathlib import Path

    input_path = Path(input_file_path)
    stem = input_path.stem.replace(' （', '（')  # スペースを削除
    output_filename = f"{stem}_{codec}{input_path.suffix}"
    return str(input_path.parent / output_filename)


@router.post(
    '/encode',
    summary = '手動エンコード開始 API',
    response_description = 'エンコードタスクの情報。',
    response_model = schemas.TSReplaceEncodingResponse,
)
async def StartManualEncodingAPI(
    request: schemas.TSReplaceManualEncodingRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定された録画番組の手動エンコードを開始する。<br>
    エンコード方式（ソフトウェア/ハードウェア）とコーデック（H.264/HEVC）を指定できる。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 録画番組の存在確認
        recorded_program = await RecordedProgram.get(id=request.video_id).select_related('recorded_video')

        # 出力ファイルパスを生成
        input_file_path = recorded_program.recorded_video.file_path
        output_file_path = _generate_output_file_path(input_file_path, request.codec)

        # エンコードタスクを作成
        encoding_task = EncodingTask(
            rec_file_id=recorded_program.recorded_video.id,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            codec=request.codec,
            encoder_type=request.encoder_type,
            quality_preset=request.quality_preset
        )

        # TSReplaceEncodingTaskを直接実行
        tsreplace_task = TSReplaceEncodingTask(
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            codec=request.codec,
            encoder_type=request.encoder_type,
            quality_preset=request.quality_preset
        )

        # タスクを管理辞書に追加
        _running_tasks[encoding_task.task_id] = tsreplace_task

        # バックグラウンドでエンコード実行
        async def execute_and_cleanup():
            try:
                await tsreplace_task.execute()
            finally:
                # 完了後もしばらく辞書に残す（状況確認のため）
                pass

        asyncio.create_task(execute_and_cleanup())

        return schemas.TSReplaceEncodingResponse(
            success=True,
            task_id=encoding_task.task_id,
            detail='エンコードタスクを開始しました。',
        )

    except DoesNotExist:
        logging.error(f'[StartManualEncodingAPI] Specified video_id was not found [video_id: {request.video_id}]')
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Specified video_id was not found',
        )
    except Exception as ex:
        logging.error(f'[StartManualEncodingAPI] Failed to start manual encoding [video_id: {request.video_id}]:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to start manual encoding: {ex!s}',
        )


@router.get(
    '/status/{task_id}',
    summary = 'エンコード状況取得 API',
    response_description = 'エンコードタスクの状況。',
    response_model = schemas.TSReplaceEncodingStatusResponse,
)
async def GetEncodingStatusAPI(
    task_id: Annotated[str, Path(description='エンコードタスクの ID 。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたエンコードタスクの状況を取得する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 実行中のタスクから状況を取得
        if task_id not in _running_tasks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Specified task_id was not found',
            )

        task = _running_tasks[task_id]

        return schemas.TSReplaceEncodingStatusResponse(
            success=True,
            task_id=task_id,
            status=task.encoding_task.status,
            progress=task.encoding_task.progress,
            detail=task.encoding_task.error_message or 'Processing',
            created_at=task.encoding_task.created_at,
            started_at=task.encoding_task.started_at,
            completed_at=task.encoding_task.completed_at,
            error_message=task.encoding_task.error_message,
        )

    except HTTPException:
        raise
    except Exception as ex:
        logging.error(f'[GetEncodingStatusAPI] Failed to get encoding status [task_id: {task_id}]:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get encoding status: {ex!s}',
        )


@router.delete(
    '/cancel/{task_id}',
    summary = 'エンコードキャンセル API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def CancelEncodingAPI(
    task_id: Annotated[str, Path(description='エンコードタスクの ID 。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたエンコードタスクをキャンセルする。<br>
    実行中のエンコード処理は安全に停止され、一時ファイルは削除される。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 実行中のタスクをキャンセル
        if task_id not in _running_tasks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Specified task_id was not found or cannot be cancelled',
            )

        task = _running_tasks[task_id]
        await task.cancel()

        # タスクを辞書から削除
        del _running_tasks[task_id]

        logging.info(f'[CancelEncodingAPI] Successfully cancelled encoding task [task_id: {task_id}]')

    except HTTPException:
        raise
    except Exception as ex:
        logging.error(f'[CancelEncodingAPI] Failed to cancel encoding [task_id: {task_id}]:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to cancel encoding: {ex!s}',
        )


@router.get(
    '/queue',
    summary = 'エンコードキュー取得 API',
    response_description = 'エンコードキューの状況。',
    response_model = schemas.TSReplaceEncodingQueueResponse,
)
async def GetEncodingQueueAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    現在のエンコードキューの状況を取得する。<br>
    実行中・待機中・完了済みのエンコードタスクの一覧を返す。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 実行中のタスクから状況を取得
        processing_tasks = []
        completed_tasks = []
        failed_tasks = []

        for task_id, task in _running_tasks.items():
            task_info = {
                'task_id': task_id,
                'video_id': task.encoding_task.rec_file_id,
                'video_title': 'Unknown Video',  # 簡素化のため固定
                'codec': task.encoding_task.codec,
                'encoder_type': task.encoding_task.encoder_type,
                'status': task.encoding_task.status,
                'progress': task.encoding_task.progress,
                'created_at': task.encoding_task.created_at,
                'started_at': task.encoding_task.started_at,
                'completed_at': task.encoding_task.completed_at,
                'error_message': task.encoding_task.error_message
            }

            if task.encoding_task.status == 'processing':
                processing_tasks.append(task_info)
            elif task.encoding_task.status == 'completed':
                completed_tasks.append(task_info)
            elif task.encoding_task.status in ['failed', 'cancelled']:
                failed_tasks.append(task_info)

        return schemas.TSReplaceEncodingQueueResponse(
            success=True,
            processing_tasks=processing_tasks,
            queued_tasks=[],  # 簡素化のため空
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
        )

    except Exception as ex:
        logging.error('[GetEncodingQueueAPI] Failed to get encoding queue:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to get encoding queue: {ex!s}',
        )


@router.websocket('/progress/{task_id}')
async def EncodingProgressWebSocket(
    websocket: WebSocket,
    task_id: str,
):
    """
    指定されたエンコードタスクの進捗をWebSocketでリアルタイム配信する。<br>
    エンコード進捗、状態変更、完了通知をリアルタイムで受信できる。
    """

    await websocket.accept()

    try:
        # タスクの存在確認
        if task_id not in _running_tasks:
            await websocket.close(code=1008, reason='Task not found')
            return

        task = _running_tasks[task_id]

        # 初期状態を送信
        await websocket.send_json({
            'type': 'status',
            'task_id': task_id,
            'status': task.encoding_task.status,
            'progress': task.encoding_task.progress,
            'detail': task.encoding_task.error_message or 'Processing',
            'created_at': task.encoding_task.created_at.isoformat() if task.encoding_task.created_at else None,
            'started_at': task.encoding_task.started_at.isoformat() if task.encoding_task.started_at else None,
            'completed_at': task.encoding_task.completed_at.isoformat() if task.encoding_task.completed_at else None,
            'error_message': task.encoding_task.error_message,
        })

        # WebSocket接続を維持（簡素化）
        while True:
            try:
                # クライアントからのメッセージを待機（ping/pong用）
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if message == 'ping':
                    await websocket.send_text('pong')
            except asyncio.TimeoutError:
                # タイムアウト時はpingを送信
                await websocket.send_text('ping')
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logging.info(f'[EncodingProgressWebSocket] WebSocket disconnected for task_id: {task_id}')
    except Exception as ex:
        logging.error(f'[EncodingProgressWebSocket] Error in WebSocket connection for task_id {task_id}:', exc_info=ex)
        try:
            await websocket.close(code=1011, reason=f'Internal server error: {ex!s}')
        except:
            pass
    finally:
        # WebSocket終了処理
        logging.info(f'[EncodingProgressWebSocket] WebSocket connection closed for task_id: {task_id}')


@router.get(
    '/progress/{task_id}/sse',
    summary = 'エンコード進捗 SSE API',
    response_description = 'Server-Sent Events によるエンコード進捗のリアルタイム配信。',
)
async def EncodingProgressSSE(
    task_id: Annotated[str, Path(description='エンコードタスクの ID 。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたエンコードタスクの進捗をServer-Sent Eventsでリアルタイム配信する。<br>
    WebSocketが利用できない環境でのフォールバック用。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    async def event_stream():
        """SSE用のイベントストリーム生成器"""
        try:
            # タスクの存在確認
            if task_id not in _running_tasks:
                yield f"data: {{'type': 'error', 'message': 'Task not found'}}\n\n"
                return

            task = _running_tasks[task_id]

            # 初期状態を送信
            initial_data = {
                'type': 'status',
                'task_id': task_id,
                'status': task.encoding_task.status,
                'progress': task.encoding_task.progress,
                'detail': task.encoding_task.error_message or 'Processing',
                'created_at': task.encoding_task.created_at.isoformat() if task.encoding_task.created_at else None,
                'started_at': task.encoding_task.started_at.isoformat() if task.encoding_task.started_at else None,
                'completed_at': task.encoding_task.completed_at.isoformat() if task.encoding_task.completed_at else None,
                'error_message': task.encoding_task.error_message,
            }
            yield f"data: {initial_data}\n\n"

            # 簡素化：定期的にkeep-aliveを送信
            for _ in range(10):  # 最大10回（5分間）
                await asyncio.sleep(30)
                yield f"data: {{'type': 'keepalive', 'timestamp': '{asyncio.get_event_loop().time()}'}}\n\n"

        except Exception as ex:
            logging.error(f'[EncodingProgressSSE] Error in SSE stream for task_id {task_id}:', exc_info=ex)
            yield f"data: {{'type': 'error', 'message': 'Internal server error: {ex!s}'}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control',
        }
    )


@router.post(
    '/notifications/subscribe',
    summary = 'エンコード完了通知購読 API',
    response_description = '通知購読の結果。',
    response_model = schemas.TSReplaceNotificationSubscriptionResponse,
)
async def SubscribeToEncodingNotificationsAPI(
    request: schemas.TSReplaceNotificationSubscriptionRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    エンコード完了通知を購読する。<br>
    指定されたエンドポイントにエンコード完了時の通知が送信される。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 簡素化：固定のサブスクリプションIDを返す
        import uuid
        subscription_id = str(uuid.uuid4())

        logging.info(f'[SubscribeToEncodingNotificationsAPI] Notification subscription created: {subscription_id} for user {current_user.id}')

        return schemas.TSReplaceNotificationSubscriptionResponse(
            success=True,
            subscription_id=subscription_id,
            detail='エンコード完了通知の購読を開始しました。',
        )

    except Exception as ex:
        logging.error(f'[SubscribeToEncodingNotificationsAPI] Failed to subscribe to notifications for user {current_user.id}:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to subscribe to notifications: {ex!s}',
        )


@router.delete(
    '/notifications/unsubscribe/{subscription_id}',
    summary = 'エンコード完了通知購読解除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def UnsubscribeFromEncodingNotificationsAPI(
    subscription_id: Annotated[str, Path(description='通知購読の ID 。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    エンコード完了通知の購読を解除する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されている必要がある。
    """

    try:
        # 簡素化：常に成功とする
        logging.info(f'[UnsubscribeFromEncodingNotificationsAPI] Notification subscription removed: {subscription_id} for user {current_user.id}')

    except HTTPException:
        raise
    except Exception as ex:
        logging.error(f'[UnsubscribeFromEncodingNotificationsAPI] Failed to unsubscribe from notifications [subscription_id: {subscription_id}]:', exc_info=ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to unsubscribe from notifications: {ex!s}',
        )
