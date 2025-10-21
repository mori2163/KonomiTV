
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app import logging
from app.config import ClientSettings, Config, SaveConfig, ServerSettings
from app.models.User import User
from app.routers.UsersRouter import GetCurrentAdminUser, GetCurrentUser


# ルーター
router = APIRouter(
    tags = ['Settings'],
    prefix = '/api/settings',
)


@router.get(
    '/client',
    summary = 'クライアント設定取得 API',
    response_description = 'ログイン中のユーザーアカウントのクライアント設定。',
    response_model = ClientSettings,
)
async def ClientSettingsAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    現在ログイン中のユーザーアカウントのクライアント設定を取得する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """
    return current_user.client_settings


@router.put(
    '/client',
    summary = 'クライアント設定更新 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def ClientSettingsUpdateAPI(
    client_settings: Annotated[ClientSettings, Body(description='更新するクライアント設定のデータ。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    現在ログイン中のユーザーアカウントのクライアント設定を更新する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """

    # 現在サーバーに保存されているクライアント設定の最終同期時刻よりも古いクライアント設定が送られてきた場合、エラーを返す
    current_client_settings = ClientSettings.model_validate(current_user.client_settings)
    if client_settings.last_synced_at < current_client_settings.last_synced_at:
        logging.error(f'[ClientSettingsUpdateAPI] Client settings are outdated! [{client_settings.last_synced_at} < {current_client_settings.last_synced_at}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'The client settings are outdated. Please update the client settings from the server.',
        )

    # dict に変換してから入れる
    ## Pydantic モデルのままだと JSON にシリアライズできないので怒られる
    current_user.client_settings = dict(client_settings)

    # レコードを保存する
    await current_user.save()


@router.get(
    '/server',
    summary = 'サーバー設定取得 API',
    response_description = '現在稼働中の KonomiTV サーバーのサーバー設定。',
    response_model = ServerSettings,
)
async def ServerSettingsAPI():
    """
    現在稼働中の KonomiTV サーバーのサーバー設定を取得する。<br>
    Docker 環境では、パス指定の項目は Docker 環境向けの Prefix (/host-rootfs) が付与された状態で返される。<br>
    """

    return Config()


@router.put(
    '/server',
    summary = 'サーバー設定更新 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def ServerSettingsUpdateAPI(
    server_settings: Annotated[ServerSettings, Body(description='更新するサーバー設定のデータ。')],
    current_user: Annotated[User, Depends(GetCurrentAdminUser)],
):
    """
    現在稼働中の KonomiTV サーバーのサーバー設定を更新する。<br>
    Docker 環境では、パス指定の項目には Docker 環境向けの Prefix (/host-rootfs) を付与した状態でリクエストする必要がある。<br>
    Pydantic のカスタムバリデーターの実装の都合上、バリデーション処理中はメインスレッドが数秒間ブロッキングされることがあるので注意。<br>

    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていて、かつ管理者アカウントでないとアクセスできない。
    """

    # バリデーションが完了したサーバー設定を config.yaml に保存する
    SaveConfig(server_settings)

@router.get(
    '/tsreplace-encoding/hardware-encoder-status',
    summary = 'TSReplaceエンコード ハードウェアエンコーダー状況取得 API',
    response_description = 'ハードウェアエンコーダーの利用可否と利用可能なコーデック情報。',
)
async def TSReplaceEncodingHardwareEncoderStatusAPI():
    """
    TSReplaceエンコード機能で利用可能なハードウェアエンコーダーの状況を取得する。<br>
    ハードウェアエンコーダーの利用可否と、利用可能なコーデックの一覧を返す。
    """

    from app.utils.TSReplaceEncodingUtil import TSReplaceEncodingUtil

    hardware_available = TSReplaceEncodingUtil.detectHardwareEncoderAvailability()
    available_codecs = TSReplaceEncodingUtil.getAvailableCodecs()

    return {
        'hardware_encoder_available': hardware_available,
        'available_codecs': available_codecs,
        'encoder_name': Config().general.encoder,
    }


@router.get(
    '/storage-status',
    summary = 'ストレージ状態取得 API',
    response_description = '録画フォルダのストレージ使用状況と録画可能時間の情報。',
)
async def StorageStatusAPI():
    """
    録画フォルダが配置されているドライブのストレージ使用状況を取得する。<br>
    各録画フォルダごとに、合計容量・使用容量・空き容量・使用率・録画可能時間を返す。<br>
    録画可能時間は、平均ビットレート 18Mbps を基に計算される。
    """

    config = Config()
    storage_info_list = []

    # 録画フォルダごとにストレージ情報を取得
    ## 同じドライブに複数の録画フォルダがある場合は重複を避けるため、ドライブごとに集計する
    drive_folder_map: dict[str, list[str]] = defaultdict(list)

    for recording_folder_path_str in config.video.recorded_folders:
        recording_folder_path = Path(recording_folder_path_str)
        resolved_path = recording_folder_path.resolve()
        if not resolved_path.exists():
            continue

        # ドライブのルートパスを取得 (Windows: C:\, Linux: マウントポイント)
        try:
            # Windows: ドライブレターを使用
            if resolved_path.drive:
                drive_root = str(resolved_path.drive) + '\\'
            else:
                # Linux: マウントポイントを取得
                drive_root = str(resolved_path)
                # 親ディレクトリを辿ってマウントポイントを見つける
                while not os.path.ismount(drive_root):
                    parent = os.path.dirname(drive_root)
                    if parent == drive_root:  # ルートに到達
                        drive_root = '/'
                        break
                    drive_root = parent

            # このドライブに録画フォルダを追加
            drive_folder_map[drive_root].append(recording_folder_path_str)

        except Exception as ex:
            logging.warning(f'[StorageStatusAPI] Failed to resolve drive for {recording_folder_path}: {ex}')
            continue

    # ドライブごとにストレージ情報を集計
    for drive_root, folders in drive_folder_map.items():
        try:
            disk_usage = shutil.disk_usage(folders[0])

            # 録画可能時間を計算
            # ビットレートは 18Mbps と仮定
            ## 地デジは 18Mbps, BS は 24Mbps と規定はされているが、実際はどちらも18Mbpsぐらい
            available_recording_hours = (
                disk_usage.free / (18 * 1000 * 1000 / 8)
            ) / 3600

            storage_info_list.append({
                'drive_root': drive_root,
                'recording_folders': folders,
                'total_bytes': disk_usage.total,
                'used_bytes': disk_usage.used,
                'free_bytes': disk_usage.free,
                'usage_percent': round((disk_usage.used / disk_usage.total) * 100, 2) if disk_usage.total > 0 else 0,
                'available_recording_hours': round(available_recording_hours, 2),
            })

        except Exception as ex:
            logging.error(f'[StorageStatusAPI] Failed to get storage info for drive {drive_root}: {ex}')
            continue

    return {
        'storage_info': storage_info_list,
    }
