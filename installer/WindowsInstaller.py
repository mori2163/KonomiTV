# Windows インストーラー (Inno Setup) と連携するための実装
# Inno Setup 製のインストーラー (KonomiTV-Setup.exe) から、以下の3つのモードで実行される
#   1. バックエンドの自動検出: --detect-backend <IP> で EDCB / Mirakurun を判定する
#   2. エンコーダーの自動検出: --detect-encoder で GPU から推奨エンコーダーを判定する
#   3. 無人インストール: --install でウィザードで集めた設定値を使ってインストールを実行する
# 検出結果は key=value 形式のテキストで標準出力に出力し、Inno Setup 側 (Pascal スクリプト) でパースする
# なお、この実装は Windows 専用である (Linux は従来の対話式インストーラーを使う)

import asyncio
from pathlib import Path
from typing import Literal, cast

import requests

from Installer import Installer, InstallerSettings
from Utils import CtrlCmdConnectionCheckUtil, DetectEncoderInfo, ProgressFileReporter


def WriteKeyValue(output_file: Path, result: dict[str, str]) -> None:
    """
    検出結果 (dict) を key=value 形式で出力ファイルに書き込む
    Inno Setup 側 (Pascal スクリプト) でこのファイルを読み込んでパースする

    Args:
        output_file (Path): 出力ファイルのパス
        result (dict[str, str]): 検出結果
    """
    with open(output_file, mode='w', encoding='utf-8') as file:
        file.write('\n'.join(f'{key}={value}' for key, value in result.items()))


def DetectBackend(ip: str) -> dict[str, str]:
    """
    指定された IP アドレスからバックエンド (EDCB / Mirakurun) を自動検出する

    EDCB は TCP API (tcp://<ip>:4510) への接続確認で、Mirakurun は HTTP API (http://<ip>:40772) へのリクエストで判定する
    両方で検出できた場合は EDCB を優先する (Windows でよくある構成のため)

    Args:
        ip (str): バックエンドの IP アドレス (またはホスト名)

    Returns:
        dict[str, str]: 検出結果 (backend: 検出されたバックエンド、検出できなかった場合は空文字列。
            あわせて検出されたバックエンドの URL も格納される)
    """

    # localhost を 127.0.0.1 に置き換え (localhost だと一部 Windows 環境で TCP API への接続が遅くなる)
    ip = ip.replace('localhost', '127.0.0.1')

    # 検出に使う URL (ポート番号は既定値のみ対応。カスタムポートは後から設定画面で変更できる)
    edcb_url = f'tcp://{ip}:4510/'
    mirakurun_url = f'http://{ip}:40772/'

    # EDCB の検出
    ## 現在の EpgTimerSrv の動作ステータスを取得できるかで判定する
    is_edcb = False
    try:
        edcb = CtrlCmdConnectionCheckUtil(ip, 4510)
        is_edcb = asyncio.run(edcb.sendGetNotifySrvStatus()) is not None
    except Exception:
        pass  # 接続できなければ検出失敗として扱う

    # Mirakurun の検出
    ## /api/version にリクエストを送り、200 (OK) が返ってきたら検出成功とする
    is_mirakurun = False
    try:
        response = requests.get(f'{mirakurun_url}api/version', timeout=5)
        is_mirakurun = response.status_code == 200
    except Exception:
        pass  # 接続できなければ検出失敗として扱う

    # 検出結果を返す (両方で検出できた場合は EDCB を優先する)
    if is_edcb is True:
        return {'backend': 'EDCB', 'edcb_url': edcb_url}
    elif is_mirakurun is True:
        return {'backend': 'Mirakurun', 'mirakurun_url': mirakurun_url}
    else:
        return {'backend': ''}


def DetectEncoder() -> dict[str, str]:
    """
    接続されている GPU から推奨エンコーダーを自動検出する

    Returns:
        dict[str, str]: 検出結果 (default: 推奨エンコーダー、各エンコーダーの利用可否 (1/0))
    """

    # エンコーダーの自動判定結果を取得
    encoder_info = DetectEncoderInfo()

    # 検出結果を key=value 形式に変換して返す
    ## 各エンコーダーの利用可否は '利用できます' を含むかどうかで判定する
    ## (DetectEncoderInfo の利用可否は表示用文字列のため)
    return {
        'default': encoder_info['default_encoder'],
        # 接続されている GPU 名 (ウィザードの説明ラベルに表示する。複数ある場合はカンマ区切りで連結する)
        'gpu_names': ', '.join(encoder_info['gpu_names']),
        'ffmpeg_available': '1',
        'qsvencc_available': '1' if '利用できます' in encoder_info['qsvencc_available'] else '0',
        'nvencc_available': '1' if '利用できます' in encoder_info['nvencc_available'] else '0',
        'vceencc_available': '1' if '利用できます' in encoder_info['vceencc_available'] else '0',
        'rkmppenc_available': '1' if '利用できます' in encoder_info['rkmppenc_available'] else '0',
    }


def LoadInstallerSettings(settings_file: Path) -> InstallerSettings:
    """
    Windows インストーラー (Inno Setup) が書き出した設定ファイル (key=value 形式) を読み込み、
    InstallerSettings に変換する

    Args:
        settings_file (Path): 設定ファイルのパス

    Returns:
        InstallerSettings: 読み込んだインストール設定
    """

    # 設定ファイル (key=value 形式) を読み込む
    ## Inno Setup 側は UTF-8 (BOM 付きの可能性あり) で書き出すため、utf-8-sig で読み込む
    ## パスワード (service_password) の前後の空白を保持できるよう、行末の改行のみを取り除く
    settings_dict: dict[str, str] = {}
    with open(settings_file, encoding='utf-8-sig') as file:
        for line in file:
            # 行末の改行のみを取り除く (パスワードなどで前後の空白を保持するため、strip() は使わない)
            line = line.rstrip('\r\n')
            # 空行とコメント行は無視する
            if line.strip() == '' or line.lstrip().startswith('#'):
                continue
            # 最初の = で key と value に分割する (パスワードなどに = が含まれていても大丈夫なように)
            if '=' in line:
                key, value = line.split('=', 1)
                settings_dict[key.strip()] = value

    # InstallerSettings に変換して返す
    ## パスワード以外の設定値はここで trim する (パスワードは前後の空白を保持する)
    return InstallerSettings(
        install_path = settings_dict['install_path'].strip(),
        backend = cast(Literal['EDCB', 'Mirakurun'], settings_dict['backend'].strip()),
        encoder = cast(Literal['FFmpeg', 'QSVEncC', 'NVEncC', 'VCEEncC'], settings_dict['encoder'].strip()),
        edcb_url = settings_dict.get('edcb_url', '').strip(),
        mirakurun_url = settings_dict.get('mirakurun_url', '').strip(),
        recorded_folders = [folder.strip() for folder in settings_dict.get('recorded_folders', '').split('|') if folder.strip() != ''],
        capture_upload_folders = [folder.strip() for folder in settings_dict.get('capture_upload_folders', '').split('|') if folder.strip() != ''],
        service_username = settings_dict.get('service_username', '').strip(),
        service_password = settings_dict.get('service_password', ''),
    )


def InstallUnattended(version: str, settings_file: Path, progress_file: Path) -> int:
    """
    無人モードで KonomiTV をインストールする
    Inno Setup ウィザードは管理者権限で実行済みのため、ここでは権限の昇格は行わない

    Args:
        version (str): KonomiTV をインストールするバージョン
        settings_file (Path): Windows インストーラーが書き出した設定ファイルのパス
        progress_file (Path): 進捗を書き込むファイルのパス

    Returns:
        int: 終了コード (0: 成功、1: 失敗)
    """

    # 進捗レポーターを初期化 (Inno Setup ウィザードがこのファイルをポーリングして進捗を表示する)
    progress_reporter = ProgressFileReporter(progress_file)

    # インストールを実行
    try:
        # 設定ファイルを読み込み、インストールを実行する
        settings = LoadInstallerSettings(settings_file)
        result = Installer(version, unattended_settings=settings, progress_reporter=progress_reporter)
    except Exception as ex:
        # 予期しないエラーが発生した場合はエラーを記録して失敗扱いにする
        progress_reporter.error(f'予期しないエラーが発生しました: {ex!r}')
        return 1

    # インストールの結果に応じて終了コードを返す
    ## エラーメッセージは Installer() 内で progress_reporter.error() 済みのため、ここでは記録しない
    if result is True:
        progress_reporter.done()
        return 0
    else:
        return 1
