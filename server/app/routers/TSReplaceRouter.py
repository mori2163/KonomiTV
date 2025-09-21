import asyncio
import json
from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from tortoise.exceptions import DoesNotExist

from app import logging, schemas
from app.models.RecordedProgram import RecordedProgram
from app.models.User import User
from app.routers.UsersRouter import GetCurrentUser
from app.streams.TSReplaceEncodingTask import TSReplaceEncodingTask
from app.schemas import EncodingTask


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

    async def broadcast_json(self, data: Dict[str, Any] | List[Any]):
        await self.broadcast(json.dumps(data, ensure_ascii=False))

manager = ConnectionManager()

router = APIRouter(
    tags = ['TSReplace'],
    prefix = '/api/tsreplace',
)

# 実行中のタスクを管理する辞書
_running_tasks: Dict[str, TSReplaceEncodingTask] = {}
_last_broadcast_states: Dict[str, Dict[str, Any]] = {}
broadcast_task: Any = None


async def broadcast_progress_updates():
    """実行中のタスクの進捗を定期的に監視し、変更があればブロードキャストする"""
    logging.info('Started WebSocket progress broadcasting task.')
    while True:
        try:
            # 接続がない場合はタスクを一旦終了
            if not manager.active_connections:
                logging.info('No active WebSocket connections. Stopping progress broadcasting task.')
                global broadcast_task
                broadcast_task = None
                break

            tasks_to_broadcast = []

            for task_id, task in list(_running_tasks.items()):
                current_status = task.encoding_task.status
                current_progress = round(task.encoding_task.progress, 1)

                # 前回の状態と比較
                last_state = _last_broadcast_states.get(task_id)
                if last_state is None or last_state['status'] != current_status or last_state['progress'] != current_progress:
                    # 番組タイトルを取得
                    video_title = 'Unknown Video'
                    try:
                        if task.encoding_task.rec_file_id > 0:
                            recorded_program = await RecordedProgram.get(id=task.encoding_task.rec_file_id)
                            video_title = recorded_program.title or 'Unknown Video'
                    except Exception as e:
                        logging.warning(f'Failed to get video title for task {task_id}: {e}')

                    task_info = {
                        'task_id': task_id,
                        'video_id': task.encoding_task.rec_file_id,
                        'video_title': video_title,
                        'codec': task.encoding_task.codec,
                        'encoder_type': task.encoding_task.encoder_type,
                        'status': current_status,
                        'progress': current_progress,
                        'error_message': task.encoding_task.error_message,
                        'created_at': task.encoding_task.created_at.isoformat() if task.encoding_task.created_at else None,
                        'started_at': task.encoding_task.started_at.isoformat() if task.encoding_task.started_at else None,
                        'completed_at': task.encoding_task.completed_at.isoformat() if task.encoding_task.completed_at else None,
                    }
                    tasks_to_broadcast.append(task_info)
                    _last_broadcast_states[task_id] = {'status': current_status, 'progress': current_progress}

            if tasks_to_broadcast:
                await manager.broadcast_json({'type': 'progress_update', 'tasks': tasks_to_broadcast})

            # 完了/失敗/キャンセルしたタスクを _last_broadcast_states から削除
            finished_task_ids = {task_id for task_id, state in list(_last_broadcast_states.items()) if state['status'] in ['completed', 'failed', 'cancelled']}
            for task_id in finished_task_ids:
                del _last_broadcast_states[task_id]

        except Exception as ex:
            logging.error(f'[broadcast_progress_updates] Error: {ex}', exc_info=ex)

        # 1秒待機
        await asyncio.sleep(1)

def _generate_output_file_path(input_file_path: str, codec: str) -> str:
    """入力ファイルパスから出力ファイルパスを生成する"""
    from pathlib import Path

    input_path = Path(input_file_path)
    stem = input_path.stem.replace(' （', '（')
    output_filename = f"{stem}_{codec}{input_path.suffix}"
    return str(input_path.parent / output_filename)


def register_auto_encoding_task(tsreplace_task: 'TSReplaceEncodingTask') -> None:
    """自動エンコードタスクをWebSocket通知システムに登録する"""
    import asyncio

    # タスクを管理辞書に追加
    _running_tasks[tsreplace_task.encoding_task.task_id] = tsreplace_task

    # WebSocketブロードキャストタスクが実行されていない場合は開始
    global broadcast_task
    if broadcast_task is None and manager.active_connections:
        broadcast_task = asyncio.create_task(broadcast_progress_updates())


def cleanup_auto_encoding_task(task_id: str) -> None:
    """
    自動エンコードタスクをクリーンアップする

    Args:
        task_id: タスクID
    """
    if task_id in _running_tasks:
        del _running_tasks[task_id]
    if task_id in _last_broadcast_states:
        del _last_broadcast_states[task_id]


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

        # 再エンコード済み動画のチェック
        if recorded_program.recorded_video.is_tsreplace_encoded:
            logging.warning(f'[StartManualEncodingAPI] Cannot re-encode already encoded video [video_id: {request.video_id}]')
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Cannot re-encode already encoded video',
            )

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
            quality_preset=request.quality_preset,
            delete_original=request.delete_original
        )

        # エンコードタスクのrec_file_idを設定
        tsreplace_task.encoding_task.rec_file_id = recorded_program.recorded_video.id

        # タスクを管理辞書に追加
        _running_tasks[encoding_task.task_id] = tsreplace_task

        # バックグラウンドでエンコード実行
        async def execute_and_cleanup():
            try:
                await tsreplace_task.execute()
            finally:
                # 完了後も一定時間タスクリストに残し、最終状態をクライアントが取得できるようにする
                await asyncio.sleep(60 * 5)  # 5分間保持
                if encoding_task.task_id in _running_tasks:
                    del _running_tasks[encoding_task.task_id]
                if encoding_task.task_id in _last_broadcast_states:
                    del _last_broadcast_states[encoding_task.task_id]

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

        # キャンセル後すぐにタスクを削除せず、状態が 'cancelled' になるのを待つ
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
async def GetEncodingQueueAPI():
    """
    現在のエンコードキューの状況を取得する。<br>
    実行中・待機中・完了済みのエンコードタスクの一覧を返す。<br>
    認証は不要です。
    """

    try:
        processing_tasks = []
        queued_tasks = []
        completed_tasks = []
        failed_tasks = []

        for task_id, task in _running_tasks.items():
            # 番組タイトルを取得
            video_title = 'Unknown Video'
            try:
                if task.encoding_task.rec_file_id > 0:
                    recorded_program = await RecordedProgram.get(id=task.encoding_task.rec_file_id)
                    video_title = recorded_program.title or 'Unknown Video'
            except Exception as e:
                logging.warning(f'Failed to get video title for task {task_id}: {e}')

            task_info = {
                'task_id': task_id,
                'video_id': task.encoding_task.rec_file_id,
                'video_title': video_title,
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
            elif task.encoding_task.status == 'queued':
                queued_tasks.append(task_info)
            elif task.encoding_task.status == 'completed':
                completed_tasks.append(task_info)
            elif task.encoding_task.status in ['failed', 'cancelled']:
                failed_tasks.append(task_info)

        return schemas.TSReplaceEncodingQueueResponse(
            success=True,
            processing_tasks=processing_tasks,
            queued_tasks=queued_tasks,
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

        # 進捗監視ループ
        last_progress = -1
        last_status = None

        while True:
            try:
                # タスクの現在の状態を取得
                current_status = task.encoding_task.status
                current_progress = task.encoding_task.progress

                # 状態や進捗が変化した場合、または定期的に更新を送信
                progress_changed = abs(current_progress - last_progress) >= 0.1  # 0.1%以上の変化
                status_changed = current_status != last_status

                if status_changed or progress_changed or last_progress == -1:
                    await websocket.send_json({
                        'type': 'status',
                        'task_id': task_id,
                        'status': current_status,
                        'progress': current_progress,
                        'detail': task.encoding_task.error_message or 'Processing',
                        'created_at': task.encoding_task.created_at.isoformat() if task.encoding_task.created_at else None,
                        'started_at': task.encoding_task.started_at.isoformat() if task.encoding_task.started_at else None,
                        'completed_at': task.encoding_task.completed_at.isoformat() if task.encoding_task.completed_at else None,
                        'error_message': task.encoding_task.error_message,
                    })

                    last_progress = current_progress
                    last_status = current_status

                # 完了・失敗・キャンセル時は接続を閉じる
                if current_status in ['completed', 'failed', 'cancelled']:
                    break

                # クライアントからのメッセージを待機（ping/pong用）
                try:
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)  # より短い間隔で監視
                    if message == 'ping':
                        await websocket.send_text('pong')
                except asyncio.TimeoutError:
                    # タイムアウトは正常（0.5秒ごとに進捗をチェック）
                    pass

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


@router.websocket('/progress')
async def encoding_progress_websocket_multiplexed(websocket: WebSocket):
    """
    全てのエンコードタスクの進捗を単一のWebSocketでリアルタイムに多重配信する。
    """
    global broadcast_task
    await manager.connect(websocket)

    # バックグラウンドタスクが実行されていなければ開始
    if broadcast_task is None or broadcast_task.done():
        broadcast_task = asyncio.create_task(broadcast_progress_updates())

    try:
        while True:
            # クライアントが接続している間、メッセージの受信を待機
            message = await websocket.receive_text()
            if message == 'ping':
                await websocket.send_text('pong')
    except WebSocketDisconnect:
        logging.info('Client disconnected from multiplexed progress WebSocket.')
    finally:
        manager.disconnect(websocket)
