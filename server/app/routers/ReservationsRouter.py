
import asyncio
import configparser
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from tortoise import transactions

from app import logging, schemas
from app.config import Config
from app.models.Channel import Channel
from app.models.Program import Program
from app.utils.edcb import (
    RecFileSetInfoRequired,
    RecSettingData,
    RecSettingDataRequired,
    ReserveData,
    ReserveDataRequired,
    ServiceEventInfo,
)
from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
from app.utils.edcb.EDCBUtil import EDCBUtil
from app.utils.epgstation.EPGStationUtil import EPGStationUtil
from app.utils.epgstation.types import (
    EPGStationProgram,
    EPGStationRecording,
    EPGStationReserve,
    EPGStationReserveOption,
)
from app.utils.TSInformation import TSInformation


# ルーター
router = APIRouter(
    tags = ['Reservations'],
    prefix = '/api/recording/reservations',
)


# Bitrate.ini のキャッシュ (TTL: 15分)
_bitrate_ini_cache: dict[str, int] | None = None
_bitrate_ini_cache_timestamp: float | None = None


async def GetBitrateFromEDCB(network_id: int | None, transport_stream_id: int | None, service_id: int | None) -> int:
    """
    EDCB から Bitrate.ini を取得して、指定されたチャンネルのビットレートを取得する
    ref: https://github.com/tkntrec/EDCB/blob/my-build/EpgTimer/EpgTimer/DefineClass/SearchItem.cs#L265-L290

    Args:
        network_id (int | None): ネットワーク ID (ONID)
        transport_stream_id (int | None): トランスポートストリーム ID (TSID)
        service_id (int | None): サービス ID (SID)

    Returns:
        int: ビットレート (kbps)
    """

    global _bitrate_ini_cache, _bitrate_ini_cache_timestamp

    # None の場合は 0xFFFF として扱う（ワイルドカード検索用）
    network_id = network_id if network_id is not None else 0xFFFF
    transport_stream_id = transport_stream_id if transport_stream_id is not None else 0xFFFF
    service_id = service_id if service_id is not None else 0xFFFF

    # 常時マルチチャンネル放送のため、例外的に決め打ちの値を使うチャンネルリスト
    # キー: (NID, SID), 値: ビットレート (kbps)
    hardcoded_bitrates = {
        (32391, 23608): 12000,  # TOKYO MX1(091ch) (12Mbps)
        (32391, 23609): 12000,  # TOKYO MX1(092ch) (12Mbps)
        (32391, 23610): 4800,   # TOKYO MX2(093ch) (4.8Mbps)
        (32381, 24680): 10000,  # イッツコムch10(101ch) (10Mbps)
        (32381, 24681): 10000,  # イッツコムch10(102ch) (10Mbps)
        (32383, 24696): 10000,  # イッツコムch10(111ch) (10Mbps)
        (32383, 24697): 10000,  # イッツコムch10(112ch) (10Mbps)
    }

    # 決めうちの値が設定されているかチェック
    channel_key = (network_id, service_id)
    if channel_key in hardcoded_bitrates:
        return hardcoded_bitrates[channel_key]

    # キャッシュが存在し、かつ15分以内の場合はそれを使用
    current_time = time.time()
    if (_bitrate_ini_cache is not None and
        _bitrate_ini_cache_timestamp is not None and
        current_time - _bitrate_ini_cache_timestamp < 900):  # 900秒 = 15分
        # 段階的に検索: 全指定 -> SID=0xFFFF -> TSID=0xFFFF -> ONID=0xFFFF
        for i in range(4):
            onid = 0xFFFF if i > 2 else network_id
            tsid = 0xFFFF if i > 1 else transport_stream_id
            sid = 0xFFFF if i > 0 else service_id

            # EpgTimer の Create64Key ロジックを移植: (onid << 32 | tsid << 16 | sid)
            key = f"{(onid << 32 | tsid << 16 | sid):012X}"

            if key in _bitrate_ini_cache and _bitrate_ini_cache[key] > 0:
                return _bitrate_ini_cache[key]

        # キャッシュに該当なし、デフォルト値を返す
        return 19456

    # EDCB の API から Bitrate.ini を取得
    try:
        files = await CtrlCmdUtil().sendFileCopy2(['Bitrate.ini'])
        if not files or len(files) == 0:
            return 19456

        # ファイルデータをテキストとして解析
        bitrate_ini_data = files[0]['data']
        if not bitrate_ini_data:
            return 19456

        # バイナリデータを文字列に変換 (UTF-16 BOM つきまたは UTF-8)
        try:
            # UTF-16 BOM つきの場合
            if bitrate_ini_data.startswith(b'\xff\xfe'):
                ini_text = bitrate_ini_data.decode('utf-16')
            else:
                # UTF-8 として試行
                ini_text = bitrate_ini_data.decode('utf-8')
        except UnicodeDecodeError:
            # システムデフォルトエンコーディングで試行
            ini_text = bitrate_ini_data.decode('shift_jis', errors='ignore')

        # Bitrate.ini をパースしてキャッシュに保存
        bitrate_ini = configparser.ConfigParser()
        bitrate_ini.read_string(ini_text)
        _bitrate_ini_cache = {}
        for section in bitrate_ini.sections():
            # bitrate の値を取得して kbps に変換 (値の単位は bps)
            if 'bitrate' not in bitrate_ini[section]:
                continue
            bitrate = bitrate_ini[section].getint('bitrate', 19456000) // 1000
            _bitrate_ini_cache[section] = bitrate
        _bitrate_ini_cache_timestamp = current_time

        # 再度段階的に検索
        for i in range(4):
            onid = 0xFFFF if i > 2 else network_id
            tsid = 0xFFFF if i > 1 else transport_stream_id
            sid = 0xFFFF if i > 0 else service_id

            # EpgTimer の Create64Key ロジックを移植: (onid << 32 | tsid << 16 | sid)
            key = f"{(onid << 32 | tsid << 16 | sid):012X}"

            if key in _bitrate_ini_cache and _bitrate_ini_cache[key] > 0:
                return _bitrate_ini_cache[key]

        # 見つからない場合はデフォルト値を返す
        return 19456

    except Exception as ex:
        logging.error('[ReservationsRouter][GetBitrateFromEDCB] Failed to parse Bitrate.ini:', exc_info=ex)
        return 19456


def CalculateEstimatedFileSize(duration_seconds: float, bitrate_kbps: int, recording_mode: str) -> int:
    """
    録画予定時間とビットレートから想定ファイルサイズを計算する

    Args:
        duration_seconds (float): 録画予定時間 (秒)
        bitrate_kbps (int): ビットレート (kbps)
        recording_mode (str): 録画モード (視聴モードの場合は想定サイズ 0 を返す)

    Returns:
        int: 想定ファイルサイズ (バイト)
    """

    # 視聴モードの場合は想定サイズ 0 を返す (録画されないため)
    if recording_mode == 'View':
        return 0

    # EpgTimer のロジック: bitrate / 8 * 1000 * duration (秒)
    # ビットレート (kbps) を バイト/秒 に変換: kbps / 8 * 1000 = bytes/sec
    estimated_size_bytes = max(int(bitrate_kbps / 8 * 1000 * duration_seconds), 0)

    return estimated_size_bytes


async def DecodeEDCBReserveData(reserve_data: ReserveDataRequired, channels: list[Channel] | None = None, programs: dict[tuple[int, int, int], Program] | None = None) -> schemas.Reservation:
    """
    EDCB の ReserveData オブジェクトを schemas.Reservation オブジェクトに変換する

    Args:
        reserve_data (ReserveDataRequired): EDCB の ReserveData オブジェクト
        channels (list[Channel] | None): あらかじめ全てのチャンネル情報を取得しておく場合はそのリスト、そうでない場合は None
        programs (dict[tuple[int, int, int], Program] | None): あらかじめ取得しておいた番組情報の辞書 (network_id, service_id, event_id) -> Program

    Returns:
        schemas.Reservation: schemas.Reservation オブジェクト
    """

    # 録画予約 ID
    reserve_id: int = reserve_data['reserve_id']

    # 録画対象チャンネルのネットワーク ID
    network_id: int = reserve_data['onid']

    # 録画対象チャンネルのサービス ID
    service_id: int = reserve_data['sid']

    # 録画対象チャンネルのトランスポートストリーム ID
    transport_stream_id: int = reserve_data['tsid']

    # 録画対象チャンネルのサービス名
    ## 基本全角なので半角に変換する必要がある
    service_name: str = TSInformation.formatString(reserve_data['station_name'])

    # 録画予約番組のイベント ID
    event_id: int = reserve_data['eid']


    # ここでネットワーク ID・サービス ID・トランスポートストリーム ID が一致するチャンネルをデータベースから取得する
    channel: Channel | None
    if channels is not None:
        # あらかじめ全てのチャンネル情報を取得しておく場合はそのリストを使う
        channel = next(
            (channel for channel in channels if (
                channel.network_id == network_id and
                channel.service_id == service_id and
                channel.transport_stream_id == transport_stream_id
            )
        ), None)
    else:
        # そうでない場合はデータベースから取得する
        channel = await Channel.filter(network_id=network_id, service_id=service_id, transport_stream_id=transport_stream_id).get_or_none()
    ## 取得できなかった場合のみ、上記の限定的な情報を使って間に合わせのチャンネル情報を作成する
    ## 通常ここでチャンネル情報が取得できないのはワンセグやデータ放送など KonomiTV ではサポートしていないサービスを予約している場合だけのはず
    if channel is None:
        channel = Channel(
            id = f'NID{network_id}-SID{service_id}',
            display_channel_id = 'gr001',  # 取得できないため一旦 'gr001' を設定
            network_id = network_id,
            service_id = service_id,
            transport_stream_id = transport_stream_id,
            remocon_id = 0,  # 取得できないため一旦 0 を設定
            channel_number = '001',  # 取得できないため一旦 '001' を設定
            type = TSInformation.getNetworkType(network_id),
            name = service_name,
            jikkyo_force = False,
            is_subchannel = False,
            is_radiochannel = False,
            is_watchable = False,
        )
        # GR 以外のみサービス ID からリモコン ID を算出できるので、それを実行
        if channel.type != 'GR':
            channel.remocon_id = TSInformation.calculateRemoconID(channel.type, channel.service_id)
        # チャンネル番号を算出
        channel.channel_number = await TSInformation.calculateChannelNumber(
            channel.type,
            channel.network_id,
            channel.service_id,
            channel.remocon_id,
        )
        # 改めて表示用チャンネル ID を算出
        channel.display_channel_id = channel.type.lower() + channel.channel_number
        # このチャンネルがサブチャンネルかを算出
        channel.is_subchannel = TSInformation.calculateIsSubchannel(channel.type, channel.service_id)

    # 録画予約番組のイベント ID
    event_id: int = reserve_data['eid']

    # 録画予約番組のタイトル
    ## 基本全角なので半角に変換する必要がある
    title: str = TSInformation.formatString(reserve_data['title'])

    # 録画予約番組の番組開始時刻
    start_time: datetime = reserve_data['start_time']

    # 録画予約番組の番組終了時刻
    end_time: datetime = start_time + timedelta(seconds=reserve_data['duration_second'])

    # 録画予約番組の番組長 (秒)
    duration: float = float(reserve_data['duration_second'])

    # ここでネットワーク ID・サービス ID・イベント ID が一致する番組をデータベースから取得する
    program: Program | None = None
    if programs is not None:
        # あらかじめ取得しておいた番組情報の辞書を使用
        program = programs.get((channel.network_id, channel.service_id, event_id))
    else:
        # そうでない場合はデータベースから個別に取得する
        program = await Program.filter(network_id=channel.network_id, service_id=channel.service_id, event_id=event_id).get_or_none()
    ## 取得できなかった場合のみ、上記の限定的な情報を使って間に合わせの番組情報を作成する
    ## 通常ここで番組情報が取得できないのは同じ番組を放送しているサブチャンネルやまだ KonomiTV に反映されていない番組情報など、特殊なケースだけのはず
    if program is None:
        program = Program(
            id = f'NID{channel.network_id}-SID{channel.service_id}-EID{event_id}',
            channel_id = channel.id,
            network_id = channel.network_id,
            service_id = channel.service_id,
            event_id = event_id,
            title = title,
            description = '',
            detail = {},
            start_time = start_time,
            end_time = end_time,
            duration = duration,
            is_free = True,
            genres = [],
            video_type = '映像1080i(1125i)、アスペクト比16:9 パンベクトルなし',
            video_codec = 'mpeg2',
            video_resolution = '1080i',
            primary_audio_type = '1/0モード(シングルモノ)',
            primary_audio_language = '日本語',
            primary_audio_sampling_rate = '48kHz',
            secondary_audio_type = None,
            secondary_audio_language = None,
            secondary_audio_sampling_rate = None,
        )
    ## 番組情報をデータベースから取得できた場合でも、番組タイトル・番組開始時刻・番組終了時刻・番組長は
    ## EDCB から返される情報の方が正確な可能性があるため (特に追従時など)、それらの情報を上書きする
    else:
        program.title = title
        program.start_time = start_time
        program.end_time = end_time
        program.duration = duration

    # 録画予約が現在進行中かどうか
    ## CtrlCmdUtil.sendGetRecFilePath() で「録画中かつ視聴予約でない予約の録画ファイルパス」が返ってくる場合は True、それ以外は False
    ## 歴史的経緯でこう取得することになっているらしい
    is_recording_in_progress: bool = type(await CtrlCmdUtil().sendGetRecFilePath(reserve_id)) is str

    # 実際に録画可能かどうか: 全編録画可能 / チューナー不足のため部分的にのみ録画可能 (一部録画できない) / チューナー不足のため全編録画不可能
    # ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Common/CommonDef.h#L32-L34
    # ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Common/StructDef.h#L62
    recording_availability: Literal['Full', 'Partial', 'Unavailable'] = 'Full'
    if reserve_data['overlap_mode'] == 1:
        recording_availability = 'Partial'
    elif reserve_data['overlap_mode'] == 2:
        recording_availability = 'Unavailable'

    # コメント: EPG 予約で自動追加された予約なら "EPG自動予約" と入る
    comment: str = reserve_data['comment']

    # 録画予定のファイル名
    ## EDCB からのレスポンスでは配列になっているが、大半の場合は 1 つしかないため単一の値としている
    scheduled_recording_file_name: str = ''
    if len(reserve_data['rec_file_name_list']) > 0:
        scheduled_recording_file_name = reserve_data['rec_file_name_list'][0]

    # 録画設定
    record_settings = DecodeEDCBRecSettingData(reserve_data['rec_setting'])

    # 想定録画ファイルサイズを計算
    estimated_recording_file_size: int = 0
    try:
        # EDCB から Bitrate.ini を取得してビットレートを計算
        bitrate_kbps = await GetBitrateFromEDCB(network_id, transport_stream_id, service_id)
        # 想定ファイルサイズを計算
        estimated_recording_file_size = CalculateEstimatedFileSize(duration, bitrate_kbps, record_settings.recording_mode)
    except Exception as ex:
        logging.warning(f'[ReservationsRouter][DecodeEDCBReserveData] Failed to calculate estimated file size. [reserve_id: {reserve_id}]', exc_info=ex)
        estimated_recording_file_size = 0

    # Tortoise ORM モデルは本来 Pydantic モデルと型が非互換だが、FastAPI がよしなに変換してくれるので雑に Any にキャストしている
    ## 逆に自前で変換する方法がわからない…
    return schemas.Reservation(
        id = reserve_id,
        channel = cast(Any, channel),
        program = cast(Any, program),
        is_recording_in_progress = is_recording_in_progress,
        recording_availability = recording_availability,
        comment = comment,
        scheduled_recording_file_name = scheduled_recording_file_name,
        estimated_recording_file_size = estimated_recording_file_size,
        record_settings = record_settings,
    )


def DecodeEDCBRecSettingData(rec_settings_data: RecSettingDataRequired) -> schemas.RecordSettings:
    """
    EDCB の RecSettingData オブジェクトを schemas.RecordSettings オブジェクトに変換する

    Args:
        rec_settings_data (RecSettingDataRequired): EDCB の RecSettingData オブジェクト

    Returns:
        schemas.RecordSettings: schemas.RecordSettings オブジェクト
    """

    # 録画予約が有効かどうか
    is_enabled: bool = rec_settings_data['rec_mode'] <= 4  # 0 ~ 4 なら有効

    # 録画予約の優先度: 1 ~ 5 の数値で数値が大きいほど優先度が高い
    priority: int = rec_settings_data['priority']

    # 保存先の録画フォルダのパスのリスト
    recording_folders: list[schemas.RecordingFolder] = []
    for key in ('rec_folder_list', 'partial_rec_folder'):
        for rec_folder in rec_settings_data[key]:
            # rec_name_plug_in は ? 以降が録画ファイル名テンプレート (マクロ) の値になっているので抽出
            ## RecName_Macro.dll?$title$.ts のような形式で返ってくる
            recording_file_name_template = rec_folder['rec_name_plug_in'].split('?', 1)[1] if '?' in rec_folder['rec_name_plug_in'] else ''
            recording_folders.append(schemas.RecordingFolder(
                recording_folder_path = rec_folder['rec_folder'],
                recording_file_name_template = recording_file_name_template if recording_file_name_template != '' else None,
                is_oneseg_separate_recording_folder = key == 'partial_rec_folder',
            ))

    # 録画開始マージン (秒) / デフォルト設定に従う場合は None
    recording_start_margin: int | None = None
    if 'start_margin' in rec_settings_data:
        recording_start_margin = rec_settings_data['start_margin']

    # 録画終了マージン (秒) / デフォルト設定に従う場合は None
    recording_end_margin: int | None = None
    if 'end_margin' in rec_settings_data:
        recording_end_margin = rec_settings_data['end_margin']

    # 録画モード: 全サービス / 全サービス (デコードなし) / 指定サービスのみ / 指定サービスのみ (デコードなし) / 視聴
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Common/CommonDef.h#L26-L30
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Document/Readme_Mod.txt?plain=1#L264-L266
    recording_mode: Literal['AllServices', 'AllServicesWithoutDecoding', 'SpecifiedService', 'SpecifiedServiceWithoutDecoding', 'View'] = 'SpecifiedService'
    if rec_settings_data['rec_mode'] == 0 or rec_settings_data['rec_mode'] == 9:
        recording_mode = 'AllServices'  # 全サービス
    elif rec_settings_data['rec_mode'] == 1 or rec_settings_data['rec_mode'] == 5:
        recording_mode = 'SpecifiedService'  # 指定サービスのみ
    elif rec_settings_data['rec_mode'] == 2 or rec_settings_data['rec_mode'] == 6:
        recording_mode = 'AllServicesWithoutDecoding'  # 全サービス (デコードなし)
    elif rec_settings_data['rec_mode'] == 3 or rec_settings_data['rec_mode'] == 7:
        recording_mode = 'SpecifiedServiceWithoutDecoding'  # 指定サービスのみ (デコードなし)
    elif rec_settings_data['rec_mode'] == 4 or rec_settings_data['rec_mode'] == 8:
        recording_mode = 'View'

    # 字幕データ/データ放送の録画設定は、デフォルト設定を使うか否かを含めすべて下記のビットフラグになっている
    # ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Common/CommonDef.h#L36-L39
    # #define RECSERVICEMODE_DEF	0x00000000	// デフォルト設定を使用
    # #define RECSERVICEMODE_SET	0x00000001	// 個別の設定値を使用
    # #define RECSERVICEMODE_CAP	0x00000010	// 字幕データを含む
    # #define RECSERVICEMODE_DATA	0x00000020	// データカルーセルを含む

    # 字幕データ/データ放送を録画するかどうか (Default のとき、デフォルト設定に従う)
    caption_recording_mode: Literal['Default', 'Enable', 'Disable']
    data_broadcasting_recording_mode: Literal['Default', 'Enable', 'Disable']
    service_mode = rec_settings_data['service_mode']
    if service_mode & 0x00000001:  # 個別の設定値を使用
        caption_recording_mode = 'Enable' if service_mode & 0x00000010 else 'Disable'
        data_broadcasting_recording_mode = 'Enable' if service_mode & 0x00000020 else 'Disable'
    else:  # デフォルト設定を使用
        caption_recording_mode = 'Default'
        data_broadcasting_recording_mode = 'Default'

    # 録画後動作モード: デフォルト設定に従う / 何もしない / スタンバイ / スタンバイ (復帰後再起動) / 休止 / 休止 (復帰後再起動) / シャットダウン
    # ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/ini/HttpPublic/legacy/util.lua#L522-L528
    post_recording_mode: Literal['Default', 'Nothing', 'Standby', 'StandbyAndReboot', 'Suspend', 'SuspendAndReboot', 'Shutdown'] = 'Default'
    if rec_settings_data['suspend_mode'] == 0:
        post_recording_mode = 'Default'
    elif rec_settings_data['suspend_mode'] == 1 and rec_settings_data['reboot_flag'] is False:
        post_recording_mode = 'Standby'
    elif rec_settings_data['suspend_mode'] == 1 and rec_settings_data['reboot_flag'] is True:
        post_recording_mode = 'StandbyAndReboot'
    elif rec_settings_data['suspend_mode'] == 2 and rec_settings_data['reboot_flag'] is False:
        post_recording_mode = 'Suspend'
    elif rec_settings_data['suspend_mode'] == 2 and rec_settings_data['reboot_flag'] is True:
        post_recording_mode = 'SuspendAndReboot'
    elif rec_settings_data['suspend_mode'] == 3:
        post_recording_mode = 'Shutdown'
    elif rec_settings_data['suspend_mode'] == 4:
        post_recording_mode = 'Nothing'

    # 録画後に実行する bat ファイルのパス / 指定しない場合は None
    post_recording_bat_file_path: str | None = None
    if rec_settings_data['bat_file_path'] != '':
        post_recording_bat_file_path = rec_settings_data['bat_file_path']

    # イベントリレーの追従を行うかどうか
    is_event_relay_follow_enabled: bool = rec_settings_data['tuijyuu_flag']

    # 「ぴったり録画」(録画マージンののりしろを残さず本編のみを正確に録画する？) を行うかどうか
    is_exact_recording_enabled: bool = rec_settings_data['pittari_flag']

    # 録画対象のチャンネルにワンセグ放送が含まれる場合、ワンセグ放送を別ファイルに同時録画するかどうか
    ## partial_rec_flag が 2 の時はワンセグ放送だけを出力できるそうだが、EpgTimer の UI ですら設定できない隠し機能のため無視する
    is_oneseg_separate_output_enabled: bool = rec_settings_data['partial_rec_flag'] == 1

    # 同一チャンネルで時間的に隣接した録画予約がある場合に、それらを同一の録画ファイルに続けて出力するかどうか
    is_sequential_recording_in_single_file_enabled: bool = rec_settings_data['continue_rec_flag']

    # チューナーを強制指定する際のチューナー ID / 自動選択の場合は None
    forced_tuner_id: int | None = None
    if rec_settings_data['tuner_id'] != 0:  # 0 は自動選択
        forced_tuner_id = rec_settings_data['tuner_id']

    return schemas.RecordSettings(
        is_enabled = is_enabled,
        priority = priority,
        recording_folders = recording_folders,
        recording_start_margin = recording_start_margin,
        recording_end_margin = recording_end_margin,
        recording_mode = recording_mode,
        caption_recording_mode = caption_recording_mode,
        data_broadcasting_recording_mode = data_broadcasting_recording_mode,
        post_recording_mode = post_recording_mode,
        post_recording_bat_file_path = post_recording_bat_file_path,
        is_event_relay_follow_enabled = is_event_relay_follow_enabled,
        is_exact_recording_enabled = is_exact_recording_enabled,
        is_oneseg_separate_output_enabled = is_oneseg_separate_output_enabled,
        is_sequential_recording_in_single_file_enabled = is_sequential_recording_in_single_file_enabled,
        forced_tuner_id = forced_tuner_id,
    )


def EncodeEDCBRecSettingData(record_settings: schemas.RecordSettings) -> RecSettingDataRequired:
    """
    schemas.RecordSettings オブジェクトを EDCB の RecSettingData オブジェクトに変換する

    Args:
        record_settings (schemas.RecordSettings): schemas.RecordSettings オブジェクト

    Returns:
        RecSettingData: EDCB の RecSettingData オブジェクト
    """

    # 録画モード: 0: 全サービス / 1: 指定サービスのみ / 2: 全サービス (デコードなし) / 3: 指定サービスのみ (デコードなし) / 4: 視聴
    # 5: 指定サービスのみ (無効) / 6: 全サービス (デコードなし) (無効) / 7: 指定サービスのみ (デコードなし) (無効) / 8: 視聴 (無効) / 9: 全サービス (無効)
    ## 歴史的経緯で予約無効を後から追加したためにこうなっているらしい (5 以降の値は無効)
    rec_mode: int = 1
    if record_settings.is_enabled is True:
        if record_settings.recording_mode == 'AllServices':
            rec_mode = 0
        elif record_settings.recording_mode == 'SpecifiedService':
            rec_mode = 1
        elif record_settings.recording_mode == 'AllServicesWithoutDecoding':
            rec_mode = 2
        elif record_settings.recording_mode == 'SpecifiedServiceWithoutDecoding':
            rec_mode = 3
        elif record_settings.recording_mode == 'View':
            rec_mode = 4
    else:
        if record_settings.recording_mode == 'AllServices':
            rec_mode = 9
        elif record_settings.recording_mode == 'SpecifiedService':
            rec_mode = 5
        elif record_settings.recording_mode == 'AllServicesWithoutDecoding':
            rec_mode = 6
        elif record_settings.recording_mode == 'SpecifiedServiceWithoutDecoding':
            rec_mode = 7
        elif record_settings.recording_mode == 'View':
            rec_mode = 8

    # 録画予約の優先度: 1 ~ 5 の数値で数値が大きいほど優先度が高い
    priority: int = record_settings.priority

    # イベントリレーの追従を行うかどうか
    tuijyuu_flag: bool = record_settings.is_event_relay_follow_enabled

    # 字幕データ/データ放送の録画設定
    ## ビットフラグになっているため、それぞれのフラグを立てる
    service_mode: int = 0
    ## 両方が Default ではない場合のみ個別の設定値を使用するフラグを立てる
    if record_settings.caption_recording_mode != 'Default' and record_settings.data_broadcasting_recording_mode != 'Default':
        service_mode = 1  # 個別の設定値を使用する
    ## 字幕データを含むかどうか
    if record_settings.caption_recording_mode == 'Enable':
        service_mode |= 0x00000010
    ## データカルーセルを含むかどうか
    if record_settings.data_broadcasting_recording_mode == 'Enable':
        service_mode |= 0x00000020

    # 「ぴったり録画」(録画マージンののりしろを残さず本編のみを正確に録画する？) を行うかどうか
    pittari_flag: bool = record_settings.is_exact_recording_enabled

    # 録画後に実行する bat ファイルのパス
    bat_file_path: str = ''
    if record_settings.post_recording_bat_file_path is not None:
        bat_file_path = record_settings.post_recording_bat_file_path

    # 保存先の録画フォルダのパスのリスト
    ## 空リストのときはデフォルトの録画フォルダに保存されるため問題ない
    rec_folder_list: list[RecFileSetInfoRequired] = []
    partial_rec_folder: list[RecFileSetInfoRequired] = []
    for recording_folder in record_settings.recording_folders:
        # TS 書き込みプラグインは基本 Write_Default.dll しかないので固定
        ## 一応 Write_OneService.dll や Write_Multi とかがなくもないが、利用用途があるのかすら知らないため無視
        write_plug_in = 'Write_Default.dll'
        # 録画ファイル名変更プラグインは RecName_Macro.dll しかないので固定
        ## 空文字列にすると EpgTimerSrv 設定の「録画時のファイル名に PlugIn を使用する」が有効かどうか次第になるが、
        ## わざわざ無効にするユースケースがほとんどないため、KonomiTV では EpgTimerSrv での設定値に関わらず常に有効化する
        rec_name_plug_in = 'RecName_Macro.dll'
        # ファイル名テンプレートが指定されている場合は ? 以降に RecName_Macro.dll へのオプションとして追加する
        if recording_folder.recording_file_name_template is not None:
            rec_name_plug_in = f'RecName_Macro.dll?{recording_folder.recording_file_name_template}'
        # ワンセグ録画フォルダかどうかで分ける
        if recording_folder.is_oneseg_separate_recording_folder is False:
            rec_folder_list.append({
                'rec_folder': recording_folder.recording_folder_path,
                'write_plug_in': write_plug_in,
                'rec_name_plug_in': rec_name_plug_in,
            })
        else:
            partial_rec_folder.append({
                'rec_folder': recording_folder.recording_folder_path,
                'write_plug_in': write_plug_in,
                'rec_name_plug_in': rec_name_plug_in,
            })

    # 録画後動作モード: デフォルト設定に従う / 何もしない / スタンバイ / スタンバイ (復帰後再起動) / 休止 / 休止 (復帰後再起動) / シャットダウン
    suspend_mode: int = 0
    reboot_flag: bool = False
    if record_settings.post_recording_mode == 'Default':
        suspend_mode = 0
    elif record_settings.post_recording_mode == 'Nothing':
        suspend_mode = 4
    elif record_settings.post_recording_mode == 'Standby':
        suspend_mode = 1
    elif record_settings.post_recording_mode == 'StandbyAndReboot':
        suspend_mode = 1
        reboot_flag = True
    elif record_settings.post_recording_mode == 'Suspend':
        suspend_mode = 2
    elif record_settings.post_recording_mode == 'SuspendAndReboot':
        suspend_mode = 2
        reboot_flag = True
    elif record_settings.post_recording_mode == 'Shutdown':
        suspend_mode = 3

    # 録画開始マージン (秒) / デフォルト設定に従う場合は存在しない (一旦ここでは None にしておく)
    start_margin: int | None = record_settings.recording_start_margin

    # 録画終了マージン (秒) / デフォルト設定に従う場合は存在しない (一旦ここでは None にしておく)
    end_margin: int | None = record_settings.recording_end_margin

    # 同一チャンネルで時間的に隣接した録画予約がある場合に、それらを同一の録画ファイルに続けて出力するかどうか
    continue_rec_flag: bool = record_settings.is_sequential_recording_in_single_file_enabled

    # 録画対象のチャンネルにワンセグ放送が含まれる場合、ワンセグ放送を別ファイルに同時録画するかどうか
    ## partial_rec_flag が 2 の時はワンセグ放送だけを出力できるそうだが、EpgTimer の UI ですら設定できない隠し機能のため無視する
    partial_rec_flag: int = 1 if record_settings.is_oneseg_separate_output_enabled is True else 0

    # チューナーを強制指定する際のチューナー ID / 自動選択の場合は 0 を指定
    tuner_id: int = 0
    if record_settings.forced_tuner_id is not None:
        tuner_id = record_settings.forced_tuner_id

    # EDCB の RecSettingData オブジェクトを作成
    rec_setting_data: RecSettingDataRequired = {
        'rec_mode': rec_mode,
        'priority': priority,
        'tuijyuu_flag': tuijyuu_flag,
        'service_mode': service_mode,
        'pittari_flag': pittari_flag,
        'bat_file_path': bat_file_path,
        'rec_folder_list': rec_folder_list,
        'suspend_mode': suspend_mode,
        'reboot_flag': reboot_flag,
        'continue_rec_flag': continue_rec_flag,
        'partial_rec_flag': partial_rec_flag,
        'tuner_id': tuner_id,
        'partial_rec_folder': partial_rec_folder,
    }

    # 録画マージンはデフォルト設定に従う場合は存在しないため、それぞれの値が None でない場合のみ追加する
    if start_margin is not None:
        rec_setting_data['start_margin'] = start_margin
    if end_margin is not None:
        rec_setting_data['end_margin'] = end_margin

    return rec_setting_data


# ***** EPGStation 用のヘルパー関数 *****

def ValidateEPGStationRecordSettings(record_settings: schemas.RecordSettings) -> None:
    """
    EPGStation では設定できない項目が含まれていないかを検証する
    """

    unsupported_fields: list[str] = []

    if record_settings.priority != 3:
        unsupported_fields.append('priority')
    if record_settings.recording_start_margin is not None:
        unsupported_fields.append('recording_start_margin')
    if record_settings.recording_end_margin is not None:
        unsupported_fields.append('recording_end_margin')
    if record_settings.recording_mode != 'SpecifiedService':
        unsupported_fields.append('recording_mode')
    if record_settings.caption_recording_mode != 'Default':
        unsupported_fields.append('caption_recording_mode')
    if record_settings.data_broadcasting_recording_mode != 'Default':
        unsupported_fields.append('data_broadcasting_recording_mode')
    if record_settings.post_recording_mode != 'Default':
        unsupported_fields.append('post_recording_mode')
    if record_settings.post_recording_bat_file_path is not None:
        unsupported_fields.append('post_recording_bat_file_path')
    if record_settings.is_event_relay_follow_enabled is not True:
        unsupported_fields.append('is_event_relay_follow_enabled')
    if record_settings.is_exact_recording_enabled:
        unsupported_fields.append('is_exact_recording_enabled')
    if record_settings.is_oneseg_separate_output_enabled:
        unsupported_fields.append('is_oneseg_separate_output_enabled')
    if record_settings.is_sequential_recording_in_single_file_enabled:
        unsupported_fields.append('is_sequential_recording_in_single_file_enabled')
    if record_settings.forced_tuner_id is not None:
        unsupported_fields.append('forced_tuner_id')

    # EPGStation は最大3つの保存先フォルダをサポート
    if len(record_settings.recording_folders) > 3:
        unsupported_fields.append('recording_folders (maximum 3 folders supported)')

    for index, folder in enumerate(record_settings.recording_folders):
        if folder.is_oneseg_separate_recording_folder:
            unsupported_fields.append(f'recording_folders[{index}].is_oneseg_separate_recording_folder')

    if unsupported_fields:
        unsupported_fields = sorted(set(unsupported_fields))
        detail = 'Unsupported record settings for EPGStation: ' + ', '.join(unsupported_fields)
        logging.error(f'[ReservationsRouter][ValidateEPGStationRecordSettings] {detail}')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = detail,
        )


def normalize_epgstation_title(raw_title: str | None) -> str:
    """
    EPGStation の番組タイトル文字列をマッチング用に整形する
    """

    if not raw_title:
        return ''
    return TSInformation.formatString(raw_title).casefold()


def _is_direct_epgstation_program_match(program_data: EPGStationProgram | None, program_model: Program) -> bool:
    """
    Mirakurun 互換 ID から直接取得した番組情報が対象番組と一致するか簡易チェックする
    """

    if program_data is None:
        return False

    if program_data.get('networkId') != program_model.network_id:
        return False
    if program_data.get('serviceId') != program_model.service_id:
        return False
    if program_data.get('eventId') != program_model.event_id:
        return False

    candidate_start = program_data.get('startAt')
    try:
        program_start_ms = int(program_model.start_time.timestamp() * 1000)
    except Exception:
        return False
    if candidate_start is None:
        return False
    # 15分以上ずれている場合は別番組とみなす
    if abs(candidate_start - program_start_ms) > 15 * 60 * 1000:
        return False

    return True


async def ResolveEPGStationProgram(
    epgstation: EPGStationUtil,
    program_model: Program,
) -> tuple[int, EPGStationProgram]:
    """
    Mirakurun ベースの番組情報から EPGStation の番組 ID を高精度に特定する
    """

    # EPGStation のチャンネル情報を取得して channelId -> (networkId, serviceId) のマッピングを構築
    epgstation_channels = await epgstation.getChannels()
    channel_mapping: dict[int, tuple[int, int]] = {}  # channelId -> (networkId, serviceId)
    target_channel_id: int | None = None

    for channel in epgstation_channels:
        channel_id = channel.get('id')
        network_id = channel.get('networkId')
        service_id = channel.get('serviceId')

        if channel_id is not None and network_id is not None and service_id is not None:
            channel_mapping[channel_id] = (network_id, service_id)

            # 対象チャンネルの channelId を特定
            if network_id == program_model.network_id and service_id == program_model.service_id:
                target_channel_id = channel_id

    # まずは Mirakurun 互換の番組 ID で直接取得を試す
    expected_program_id = (
        ((program_model.network_id & 0xFFFF) << 32) |
        ((program_model.service_id & 0xFFFF) << 16) |
        (program_model.event_id & 0xFFFF)
    )
    direct_program = await epgstation.getProgram(expected_program_id, is_half_width=True)
    if _is_direct_epgstation_program_match(direct_program, program_model):
        logging.info(
            '[ReservationsRouter][ResolveEPGStationProgram] Program resolved by direct ID lookup. '
            f'[program_id: {program_model.id}, epgstation_program_id: {expected_program_id}]'
        )
        return expected_program_id, cast(EPGStationProgram, direct_program)

    # 直接取得に失敗した場合は、スケジュール検索によるフォールバック処理を実行
    logging.debug(
        '[ReservationsRouter][ResolveEPGStationProgram] Direct ID lookup failed, falling back to schedule search. '
        f'[program_id: {program_model.id}, expected_epgstation_id: {expected_program_id}]'
    )

    try:
        program_start_ms = int(program_model.start_time.timestamp() * 1000)
        program_end_ms = int(program_model.end_time.timestamp() * 1000)
    except Exception as ex:
        logging.error(
            '[ReservationsRouter][ResolveEPGStationProgram] Failed to convert program timestamps.',
            exc_info = ex,
        )
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Failed to resolve the program timestamp',
        ) from ex

    program_duration_ms = max(program_end_ms - program_start_ms, 0)

    # Phase 1: getSchedules API を使った広範囲検索（前後12時間）
    search_window = timedelta(hours=12)
    wide_search_start = max(int((program_model.start_time - search_window).timestamp() * 1000), 0)
    wide_search_end = int((program_model.end_time + search_window).timestamp() * 1000)
    if wide_search_end <= wide_search_start:
        wide_search_end = wide_search_start + 1

    # スコアリングで使う「近さ」の閾値（ミリ秒）
    SCORE_TIME_WINDOW_MINUTES = 20
    SCORE_TIME_WINDOW_MS = SCORE_TIME_WINDOW_MINUTES * 60 * 1000

    wide_schedules_data = await epgstation.getSchedules(
        is_half_width = True,
        start_at = wide_search_start,
        end_at = wide_search_end,
    )

    best_candidate: tuple[int, EPGStationProgram, float, float, float, bool] | None = None
    best_score = -1.0
    normalized_target_title = normalize_epgstation_title(program_model.title)

    matching_channel = 0
    unique_channel_ids: set[int] = set()
    for schedule in wide_schedules_data:
        programs_list = schedule.get('programs', [])
        for prog in programs_list:
            ch_id = prog.get('channelId')
            if ch_id is not None:
                unique_channel_ids.add(ch_id)
            if ch_id == target_channel_id:
                matching_channel += 1

    # マッチするチャンネルが見つからない場合は、利用可能なチャンネルリストをログ出力
    if matching_channel == 0:
        available_channel_info = []
        for ch_id in sorted(list(unique_channel_ids))[:10]:  # 最初の10件のみ
            if ch_id in channel_mapping:
                nid, sid = channel_mapping[ch_id]
                available_channel_info.append(f'(chId:{ch_id}, NID:{nid}, SID:{sid})')

        logging.warning(
            '[ReservationsRouter][ResolveEPGStationProgram] No programs found for target channel. '
            f'[program_id: {program_model.id}, target_channel_id: {target_channel_id}, '
            f'target_nid: {program_model.network_id}, target_sid: {program_model.service_id}, '
            f'available_channels_from_schedules: {available_channel_info}]'
        )

    # 広範囲検索の結果から最適な候補を選択
    for schedule in wide_schedules_data:
        programs_list = schedule.get('programs', [])
        for candidate in programs_list:
            # channelId でフィルタリング
            if candidate.get('channelId') != target_channel_id:
                continue

            candidate_id = candidate.get('id')
            candidate_start = candidate.get('startAt')
            candidate_end = candidate.get('endAt')
            if candidate_id is None or candidate_start is None or candidate_end is None:
                continue
            candidate_duration = max(candidate_end - candidate_start, 0)

            score = 0.0

            # イベント ID が一致する場合は大幅加点
            event_match = candidate.get('eventId') == program_model.event_id
            if event_match:
                score += 50.0

            # 開始時刻の近さで評価（20分以内なら高評価）
            start_diff = abs(candidate_start - program_start_ms)
            score += max(0.0, 1.0 - (start_diff / SCORE_TIME_WINDOW_MS)) * 25.0

            # 番組長の近さで評価（20分以内なら高評価）
            duration_diff = abs(candidate_duration - program_duration_ms)
            score += max(0.0, 1.0 - (duration_diff / SCORE_TIME_WINDOW_MS)) * 15.0

            # タイトルの類似度で評価
            candidate_title = normalize_epgstation_title(candidate.get('name'))
            title_similarity = 0.0
            if normalized_target_title and candidate_title:
                title_similarity = SequenceMatcher(None, candidate_title, normalized_target_title).ratio()
                score += title_similarity * 10.0

            # 無料/有料の一致で加点
            if candidate.get('isFree') == program_model.is_free:
                score += 2.0

            if score > best_score:
                best_score = score
                best_candidate = (
                    candidate_id,
                    cast(EPGStationProgram, candidate),
                    float(start_diff),
                    float(duration_diff),
                    float(title_similarity),
                    bool(event_match),
                )

    if best_candidate is None:
        logging.error(
            '[ReservationsRouter][ResolveEPGStationProgram] Failed to resolve program ID from schedules. '
            f'[program_id: {program_model.id}, network_id: {program_model.network_id}, service_id: {program_model.service_id}, '
            f'event_id: {program_model.event_id}, title: {program_model.title}, start_time: {program_model.start_time}]'
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Program not found in EPGStation. Please ensure Mirakurun and EPGStation are properly synchronized.',
        )

    candidate_id, candidate_program, start_diff_ms, duration_diff_ms, title_similarity, event_match = best_candidate

    # 信頼度の閾値を下げて、より柔軟にマッチングを許容する
    confidence_threshold = 25.0
    if best_score < confidence_threshold:
        logging.warning(
            '[ReservationsRouter][ResolveEPGStationProgram] Low confidence program match, but accepting it. '
            f'[program_id: {program_model.id}, candidate_program_id: {candidate_id}, score: {best_score:.2f}, '
            f'start_diff_ms: {start_diff_ms}, duration_diff_ms: {duration_diff_ms}, title_similarity: {title_similarity:.3f}, '
            f'event_match: {event_match}]'
        )
    else:
        logging.info(
            '[ReservationsRouter][ResolveEPGStationProgram] Program resolved by schedule search. '
            f'[program_id: {program_model.id}, epgstation_program_id: {candidate_id}, score: {best_score:.2f}, '
            f'start_diff_ms: {start_diff_ms}, duration_diff_ms: {duration_diff_ms}, title_similarity: {title_similarity:.3f}, '
            f'event_match: {event_match}]'
        )
    return candidate_id, candidate_program


# ***** EPGStation 用のデータ変換関数 *****

async def DecodeEPGStationReserveData(
    reserve: EPGStationReserve,
    program: EPGStationProgram,
    channel: Channel,
    recordings: list[EPGStationRecording] | None = None,
) -> schemas.Reservation:
    """
    EPGStation の予約情報を schemas.Reservation オブジェクトに変換する

    Args:
        reserve (EPGStationReserve): EPGStation の予約情報
        program (EPGStationProgram): EPGStation の番組情報
        channel (Channel): KonomiTV のチャンネル情報
        recordings (list[EPGStationRecording] | None): 録画中情報のリスト（録画中判定用）

    Returns:
        schemas.Reservation: schemas.Reservation オブジェクト
    """

    # 予約 ID
    reserve_id = reserve.get('id', 0)

    # EPGStation の番組 ID
    epgstation_program_id = program.get('id', 0)

    # EPGStation から取得した番組情報から network_id, service_id, event_id を取得
    # EPGStation の番組情報に含まれていない場合は、番組 ID から逆算する
    # EPGStation の番組 ID は文字列として扱うと "networkId + serviceId + eventId" の10進数連結形式
    # 例: 324172151209780 -> networkId=32417, serviceId=21512, eventId=09780
    network_id = program.get('networkId')
    service_id = program.get('serviceId')
    event_id = program.get('eventId')

    if network_id is None or service_id is None or event_id is None:
        # 番組 ID を文字列に変換して各値を抽出
        program_id_str = str(epgstation_program_id)
        # 右から5桁が eventId、その左5桁が serviceId、残りが networkId
        if len(program_id_str) >= 10:
            event_id = int(program_id_str[-5:])
            service_id = int(program_id_str[-10:-5])
            network_id = int(program_id_str[:-10]) if len(program_id_str) > 10 else 0
        else:
            # フォーマットが想定外の場合はデフォルト値
            network_id = 0
            service_id = 0
            event_id = 0

    # 番組情報を KonomiTV の Program オブジェクトに変換
    program_obj = Program(
        id = f'NID{network_id}-SID{service_id}-EID{event_id}',
        channel_id = channel.id,
        network_id = network_id,
        service_id = service_id,
        event_id = event_id,
        title = TSInformation.formatString(program.get('name', '')),
        description = program.get('description', '') or '',
        detail = {},  # EPGStation の extended を解析して detail に変換する処理は省略
        start_time = datetime.fromtimestamp(program.get('startAt', 0) / 1000, tz=timezone(timedelta(hours=9))),
        end_time = datetime.fromtimestamp(program.get('endAt', 0) / 1000, tz=timezone(timedelta(hours=9))),
        duration = float((program.get('endAt', 0) - program.get('startAt', 0)) / 1000),
        is_free = program.get('isFree', True),
        genres = [],  # ジャンル変換は省略
        video_type = program.get('videoType'),
        video_codec = None,
        video_resolution = program.get('videoResolution'),
        primary_audio_type = '2/0モード(ステレオ)',
        primary_audio_language = '日本語',
        primary_audio_sampling_rate = f"{program.get('audioSamplingRate', 48000)}Hz" if program.get('audioSamplingRate') else '48kHz',
        secondary_audio_type = None,
        secondary_audio_language = None,
        secondary_audio_sampling_rate = None,
    )

    # 録画中かどうかを判定
    is_recording_in_progress = False
    if recordings is not None and len(recordings) > 0:
        # recordings が取得できている場合はそちらから判定
        is_recording_in_progress = any(rec.get('id') == reserve_id for rec in recordings if rec.get('isRecording', False))
    # recordings が取得できない場合は、予約の開始/終了時刻からは判定しない
    # （EPGStation では時刻範囲内でも実際には録画されていない可能性があるため、
    #  recordings API が取得できない場合は録画中と判定しない）

    # EPGStation は重複状態の詳細情報を提供しないため、簡易的に判定
    recording_availability: Literal['Full', 'Partial', 'Unavailable'] = 'Full'
    if reserve.get('isConflict', False):
        recording_availability = 'Unavailable'
    elif reserve.get('isOverlap', False):
        recording_availability = 'Partial'

    # コメント（EPGStation はルール ID から判定）
    comment = ''
    if reserve.get('ruleId') is not None:
        comment = 'EPG自動予約'

    # 録画ファイル名（EPGStation の recordedFormat から生成）
    scheduled_recording_file_name = ''
    if 'option' in reserve and reserve.get('option', {}).get('recordedFormat'):
        scheduled_recording_file_name = str(reserve.get('option', {}).get('recordedFormat', ''))

    # 録画設定を変換
    record_settings = DecodeEPGStationRecordSettings(reserve.get('option', {}))

    # 想定録画ファイルサイズを計算
    estimated_recording_file_size: int = 0
    try:
        # EDCB から Bitrate.ini を取得してビットレートを計算
        ## EPGStation の場合も、KonomiTV のチャンネル情報から network_id, transport_stream_id, service_id を取得できる
        bitrate_kbps = await GetBitrateFromEDCB(channel.network_id, channel.transport_stream_id, channel.service_id)
        # 想定ファイルサイズを計算
        estimated_recording_file_size = CalculateEstimatedFileSize(program_obj.duration, bitrate_kbps, record_settings.recording_mode)
    except Exception as ex:
        logging.warning(f'[ReservationsRouter][DecodeEPGStationReserveData] Failed to calculate estimated file size. [reserve_id: {reserve_id}]', exc_info=ex)
        estimated_recording_file_size = 0

    return schemas.Reservation(
        id = reserve_id,
        channel = cast(Any, channel),
        program = cast(Any, program_obj),
        is_recording_in_progress = is_recording_in_progress,
        recording_availability = recording_availability,
        comment = comment,
        scheduled_recording_file_name = scheduled_recording_file_name,
        estimated_recording_file_size = estimated_recording_file_size,
        record_settings = record_settings,
    )


def DecodeEPGStationRecordSettings(option: EPGStationReserveOption | dict[str, Any]) -> schemas.RecordSettings:
    """
    EPGStation の予約オプションを schemas.RecordSettings オブジェクトに変換する

    Args:
        option (EPGStationReserveOption | dict[str, Any]): EPGStation の予約オプション

    Returns:
        schemas.RecordSettings: schemas.RecordSettings オブジェクト
    """

    # EPGStation は EDCB ほど詳細な設定をサポートしていないため、基本的な設定のみ変換
    # サポートされていない設定項目はデフォルト値を使用

    # 予約が有効かどうか
    is_enabled = option.get('enable', True)

    # 保存先フォルダ（EPGStation は最大3つのモードをサポート）
    recording_folders: list[schemas.RecordingFolder] = []
    for i in range(1, 4):
        mode_key = f'mode{i}'
        directory_key = f'directory{i}'
        if mode_key in option and option[mode_key] is not None:
            folder_path = option.get(directory_key, option.get('directory', ''))
            if folder_path:
                recording_folders.append(schemas.RecordingFolder(
                    recording_folder_path = folder_path,
                    recording_file_name_template = option.get('recordedFormat'),
                    is_oneseg_separate_recording_folder = False,
                ))
                break

    # デフォルトの保存先フォルダ
    if not recording_folders and option.get('directory'):
        recording_folders.append(schemas.RecordingFolder(
            recording_folder_path = str(option.get('directory', '')),
            recording_file_name_template = option.get('recordedFormat'),
            is_oneseg_separate_recording_folder = False,
        ))

    return schemas.RecordSettings(
        is_enabled = is_enabled,
        priority = 3,  # EPGStation は優先度をサポートしていないためデフォルト値
        recording_folders = recording_folders,
        recording_start_margin = None,  # EPGStation では設定不可
        recording_end_margin = None,  # EPGStation では設定不可
        recording_mode = 'SpecifiedService',  # EPGStation は指定サービスのみ固定
        caption_recording_mode = 'Default',  # EPGStation では設定不可
        data_broadcasting_recording_mode = 'Default',  # EPGStation では設定不可
        post_recording_mode = 'Default',  # EPGStation では設定不可
        post_recording_bat_file_path = None,  # EPGStation では設定不可
        is_event_relay_follow_enabled = True,  # EPGStation では設定不可（デフォルト有効と仮定）
        is_exact_recording_enabled = False,  # EPGStation では設定不可
        is_oneseg_separate_output_enabled = False,  # EPGStation では設定不可
        is_sequential_recording_in_single_file_enabled = False,  # EPGStation では設定不可
        forced_tuner_id = None,  # EPGStation では設定不可
    )


def EncodeEPGStationRecordSettings(record_settings: schemas.RecordSettings) -> dict[str, Any]:
    """
    schemas.RecordSettings オブジェクトを EPGStation の予約オプションに変換する

    Args:
        record_settings (schemas.RecordSettings): schemas.RecordSettings オブジェクト

    Returns:
        dict[str, Any]: EPGStation の予約オプション
    """

    # 事前に EPGStation 互換性を検証
    ValidateEPGStationRecordSettings(record_settings)

    option: dict[str, Any] = {
        'enable': record_settings.is_enabled,
    }

    # 保存先フォルダ（最大3つまで対応）
    for i, folder in enumerate(record_settings.recording_folders[:3]):
        if i == 0:
            # デフォルト保存先
            option['directory'] = folder.recording_folder_path
            if folder.recording_file_name_template:
                option['recordedFormat'] = folder.recording_file_name_template
        else:
            # 追加保存先（mode1/directory1, mode2/directory2）
            mode_key = f'mode{i}'
            dir_key = f'directory{i}'
            # mode 値は録画モード ID を指定（EPGStation の設定ファイルで定義されている）
            # ここでは仮に 1 を設定（実際の値は環境依存のため、EPGStation の設定に従う）
            option[mode_key] = 1
            option[dir_key] = folder.recording_folder_path
            logging.info(f'[ReservationsRouter][EncodeEPGStationRecordSettings] Multiple recording folders configured. [index: {i}, path: {folder.recording_folder_path}]')

    # EPGStation でサポートされていない設定は無視
    # クライアント側で EPGStation 使用時はこれらの設定を無効化する必要がある

    return option


def GetCtrlCmdUtil() -> CtrlCmdUtil:
    """
    レコーダーが EDCB かのチェックを行い、EDCB の CtrlCmdUtil インスタンスを返す
    レコーダーが EDCB でない場合は HTTPException を発生させる

    Returns:
        CtrlCmdUtil: EDCB の CtrlCmdUtil インスタンス

    Raises:
        HTTPException: レコーダーが EDCB でない場合
    """
    if Config().general.recorder != 'EDCB':
        logging.error('[ReservationsRouter][GetCtrlCmdUtil] Recorder is not EDCB')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = f'This API requires EDCB recorder. Current recorder is configured as {Config().general.recorder}',
        )
    return CtrlCmdUtil()


async def GetReserveDataList(
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
) -> list[ReserveDataRequired]:
    """ すべての録画予約の情報を取得する """

    # EDCB から録画予約の一覧を取得
    reserve_data_list: list[ReserveDataRequired] | None = await edcb.sendEnumReserve()
    if reserve_data_list is None:
        # None が返ってきた場合はエラーを返す
        logging.error('[ReservationsRouter][GetReserveDataList] Failed to get the list of recording reservations.')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Failed to get the list of recording reservations',
        )

    return reserve_data_list


async def GetRequiredProgramsForReservations(reserve_data_list: list[ReserveDataRequired]) -> dict[tuple[int, int, int], Program]:
    """
    録画予約に必要な番組情報を一括取得する

    Args:
        reserve_data_list (list[ReserveDataRequired]): EDCB の ReserveData オブジェクトのリスト

    Returns:
        dict[tuple[int, int, int], Program]: (network_id, service_id, event_id) をキーとした番組情報の辞書
    """

    if not reserve_data_list:
        return {}

    # 録画予約から必要な番組の (network_id, service_id, event_id) の組み合わせを抽出
    program_keys = set()
    for reserve_data in reserve_data_list:
        program_keys.add((reserve_data['onid'], reserve_data['sid'], reserve_data['eid']))

    if not program_keys:
        return {}

    # SQL の検索条件を生成
    ## network_id, service_id, event_id は整数値で SQL インジェクションの心配はないので直接埋め込む
    ## Tortoise ORM の Model.raw() がパラメーターバインディング自体に対応していないのも理由
    safe_conditions = []
    for network_id, service_id, event_id in program_keys:
        safe_conditions.append(f'(network_id = {network_id} AND service_id = {service_id} AND event_id = {event_id})')
    if not safe_conditions:
        return {}

    # 高速化のため生 SQL クエリを実行
    sql = f'''
        SELECT *
        FROM programs
        WHERE {' OR '.join(safe_conditions)}
    '''
    programs = cast(list[Program], await Program.raw(sql))

    # 結果を辞書形式に変換
    programs_dict: dict[tuple[int, int, int], Program] = {}
    for program in programs:
        key = (program.network_id, program.service_id, program.event_id)
        programs_dict[key] = program

    return programs_dict


async def GetReserveData(
    reservation_id: Annotated[int, Path(description='録画予約 ID 。')],
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
) -> ReserveDataRequired | None:
    """ 指定された録画予約の情報を取得する (EDCB 利用時のみ) """

    # 指定された録画予約の情報を取得
    for reserve_data in await GetReserveDataList(edcb):
        if reserve_data['reserve_id'] == reservation_id:
            return reserve_data

    # 指定された録画予約が見つからなかった場合はエラーを返す
    logging.error(f'[ReservesRouter][GetReserveData] Specified reservation_id was not found. [reservation_id: {reservation_id}]')
    raise HTTPException(
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail = 'Specified reservation_id was not found',
    )


async def GetServiceEventInfo(
    channel: Channel,
    program: Program,
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
) -> ServiceEventInfo:
    """ EDCB から指定されたチャンネル情報・番組情報に合致する ServiceEventInfo を取得する """

    # EDCB からサービスと当該番組の開始時刻を指定して番組情報を取得
    ## API 仕様がお世辞にも意味わからんのだが、一応これでほぼピンポイントで当該番組のみ取得できる
    assert channel.transport_stream_id is not None, 'transport_stream_id is missing.'
    service_event_info_list = await edcb.sendEnumPgInfoEx([
        # 絞り込み対象のネットワーク ID・トランスポートストリーム ID・サービス ID に掛けるビットマスク (?????)
        ## 意味が分からないけどとりあえず今回はビットマスクは使用しないので 0 を指定
        0,
        # 絞り込み対象のネットワーク ID・トランスポートストリーム ID・サービス ID
        ## (network_id << 32 | transport_stream_id << 16 | service_id) の形式で指定しなければならないらしい
        channel.network_id << 32 | channel.transport_stream_id << 16 | channel.service_id,
        # 絞り込み対象の番組開始時刻の最小値
        EDCBUtil.datetimeToFileTime(program.start_time, timezone(timedelta(hours=9))),
        # 絞り込み対象の番組開始時刻の最大値
        EDCBUtil.datetimeToFileTime(program.start_time + timedelta(minutes=1), timezone(timedelta(hours=9))),
    ])

    # 番組情報が取得できなかった場合はエラーを返す
    if service_event_info_list is None or len(service_event_info_list) == 0:
        logging.error(f'[ReservesRouter][GetServiceEventInfo] Failed to get the program information. [channel_id: {channel.id} / program_id: {program.id}]')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Failed to get the program information',
        )

    # イベント ID が一致する番組情報を探す
    for service_event_info in service_event_info_list:
        if ('event_list' in service_event_info and len(service_event_info['event_list']) > 0 and
            service_event_info['event_list'][0]['eid'] == program.event_id):
            return service_event_info

    # イベント ID が一致する番組情報が見つからなかった場合はエラーを返す
    logging.error(f'[ReservesRouter][GetServiceEventInfo] Failed to get the program information. [channel_id: {channel.id} / program_id: {program.id}]')
    raise HTTPException(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail = 'Failed to get the program information',
    )


def GetEPGStationUtil() -> EPGStationUtil:
    """
    レコーダーが EPGStation かのチェックを行い、EPGStation の EPGStationUtil インスタンスを返す
    レコーダーが EDCB の場合は HTTPException を発生させる

    Returns:
        EPGStationUtil: EPGStation の EPGStationUtil インスタンス

    Raises:
        HTTPException: レコーダーが EDCB の場合
    """

    if Config().general.recorder == 'EPGStation':
        return EPGStationUtil()
    else:
        logging.error('[ReservationsRouter][GetEPGStationUtil] Recorder is not EPGStation')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Recorder is not EPGStation',
        )


@router.get(
    '',
    summary = '録画予約情報一覧 API',
    response_description = '録画予約の情報のリスト。',
    response_model = schemas.Reservations,
)
async def ReservationsAPI():
    """
    すべての録画予約の情報を取得する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        edcb = CtrlCmdUtil()

        # EDCB から現在のすべての録画予約の情報を取得
        reserve_data_list: list[ReserveDataRequired] | None = await edcb.sendEnumReserve()
        if reserve_data_list is None:
            # None が返ってきた場合は空のリストを返す
            return schemas.Reservations(total=0, reservations=[])

        # データベースアクセスを伴うので、トランザクション下に入れた上で並行して行う
        async with transactions.in_transaction():

            # 高速化のため、あらかじめ全てのチャンネル情報を取得しておく
            channels = await Channel.all()

            # 高速化のため、録画予約に必要な番組情報を一括取得しておく
            programs = await GetRequiredProgramsForReservations(reserve_data_list)

            # EDCB の ReserveData オブジェクトを schemas.Reservation オブジェクトに変換
            reserves = await asyncio.gather(*(DecodeEDCBReserveData(reserve_data, channels, programs) for reserve_data in reserve_data_list))

        # 録画予約番組の番組開始時刻でソート
        reserves.sort(key=lambda reserve: reserve.program.start_time)

        return schemas.Reservations(total=len(reserve_data_list), reservations=reserves)

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation から予約一覧を取得
        async with EPGStationUtil() as epgstation:
            reserves_data = await epgstation.getReserves(is_half_width=True)
            if reserves_data is None:
                return schemas.Reservations(total=0, reservations=[])

            # 録画中情報を取得
            recordings_data = await epgstation.getRecordings(is_half_width=True)
            if recordings_data is None:
                recordings_data = []

            # チャンネル ID からネットワーク ID・サービス ID を参照するためのマッピングを用意
            epgstation_channels = await epgstation.getChannels()
            epgstation_channel_map: dict[int, tuple[int, int]] = {}
            for epgstation_channel in epgstation_channels:
                channel_id = epgstation_channel.get('id')
                network_id = epgstation_channel.get('networkId')
                service_id = epgstation_channel.get('serviceId')
                if channel_id is None or network_id is None or service_id is None:
                    continue
                epgstation_channel_map[channel_id] = (network_id, service_id)

            # EPGStation の番組 ID から番組情報を取得するため、全スケジュールを取得してマッピングを作成
            schedules_data = await epgstation.getSchedules(is_half_width=True)
            program_map: dict[int, EPGStationProgram] = {}
            for schedule in schedules_data:
                programs_list = schedule.get('programs', [])
                for program in programs_list:
                    program_id = program.get('id')
                    if program_id is not None:
                        program_map[program_id] = cast(EPGStationProgram, program)

            # データベースアクセスを伴うので、トランザクション下に入れる
            async with transactions.in_transaction():

                # 高速化のため、あらかじめ全てのチャンネル情報を取得しておく
                channels = await Channel.all()
                channel_map: dict[tuple[int, int], Channel] = {}
                for channel in channels:
                    if channel.network_id is None or channel.service_id is None:
                        continue
                    channel_map[(channel.network_id, channel.service_id)] = channel

                # スケジュールに存在しない場合に備え、個別取得した番組情報をキャッシュ
                fallback_program_cache: dict[int, EPGStationProgram] = {}

                # 各予約を変換
                reservations: list[schemas.Reservation] = []
                for reserve in reserves_data:
                    # 番組情報を取得
                    program_id = reserve.get('programId')
                    if program_id is None:
                        continue

                    # マッピングから番組情報を取得（見つからない場合は個別取得）
                    program_data = program_map.get(program_id)
                    if program_data is None:
                        program_data = fallback_program_cache.get(program_id)
                        if program_data is None:
                            program_detail = await epgstation.getProgram(program_id, is_half_width=True)
                            if program_detail is None:
                                logging.warning(f'[ReservationsRouter][ReservationsAPI] Program not found: programId={program_id}')
                                continue
                            program_data = program_detail
                            fallback_program_cache[program_id] = program_data

                    service_id = program_data.get('serviceId')
                    network_id = program_data.get('networkId')

                    # networkId / serviceId が取得できない場合はチャンネル ID から補完する
                    if service_id is None or network_id is None:
                        channel_id = reserve.get('channelId') or program_data.get('channelId')
                        if channel_id is not None:
                            channel_ids = epgstation_channel_map.get(channel_id)
                            if channel_ids is not None:
                                network_id = network_id or channel_ids[0]
                                service_id = service_id or channel_ids[1]

                    if service_id is None or network_id is None:
                        logging.warning(
                            '[ReservationsRouter][ReservationsAPI] serviceId or networkId is missing. '
                            f'[program_id: {program_id}, channel_id: {reserve.get("channelId")}]'
                        )
                        continue

                    channel = channel_map.get((network_id, service_id))
                    if channel is None:
                        logging.warning(
                            '[ReservationsRouter][ReservationsAPI] Channel not found. '
                            f'[network_id: {network_id}, service_id: {service_id}]'
                        )
                        continue

                    # 予約情報を変換
                    reservation = await DecodeEPGStationReserveData(reserve, program_data, channel, recordings_data)
                    reservations.append(reservation)

            # 録画予約番組の番組開始時刻でソート
            reservations.sort(key=lambda reserve: reserve.program.start_time)

            return schemas.Reservations(total=len(reservations), reservations=reservations)

    else:
        logging.error('[ReservationsRouter][ReservationsAPI] Unknown recorder type configured.')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.post(
    '',
    summary = '録画予約追加 API',
    status_code = status.HTTP_201_CREATED,
)
async def AddReservationAPI(
    reserve_add_request: Annotated[schemas.ReservationAddRequest, Body(description='追加する録画予約の設定。')],
):
    """
    録画予約を追加する。
    """

    # 指定された番組 ID の番組があるかを確認
    program = await Program.filter(id=reserve_add_request.program_id).get_or_none()
    if program is None:
        logging.error(f'[ReservesRouter][AddReserveAPI] Specified program was not found. [program_id: {reserve_add_request.program_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified program was not found',
        )

    # 指定された番組 ID に関連付けられたチャンネルがあるかを確認
    channel = await Channel.filter(id=program.channel_id).get_or_none()
    if channel is None:
        logging.error(f'[ReservesRouter][AddReserveAPI] Specified channel was not found. [channel_id: {program.channel_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified channel was not found',
        )

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        edcb = CtrlCmdUtil()

        # EDCB バックエンド利用時は必ずチャンネル情報に transport_stream_id が含まれる
        assert channel.transport_stream_id is not None, 'transport_stream_id is missing.'

        # すでに同じ番組 ID の録画予約が存在するかを確認
        for reserve_data in await GetReserveDataList(edcb):
            if (reserve_data['onid'] == channel.network_id and
                reserve_data['tsid'] == channel.transport_stream_id and
                reserve_data['sid'] == channel.service_id and
                reserve_data['eid'] == program.event_id):
                logging.error(f'[ReservesRouter][AddReserveAPI] The same program_id is already reserved. [program_id: {reserve_add_request.program_id}]')
                raise HTTPException(
                    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail = 'The same program_id is already reserved',
                )

        # EDCB から録画予約対象の番組に一致する ServiceEventInfo を取得
        ## KonomiTV のデータベースに保存されているチャンネル名・番組名は表示上に半角に加工されているため、EDCB に設定するには不適切
        ## 内部仕様がわからないけど予約に設定されている番組名と EPG 上の番組名が異なると予期せぬ問題が発生しそうな気もする
        ## それ以外にも KonomiTV 側に保存されている情報が古くなっている可能性もあるため、毎回 EDCB から最新の情報を取得する
        service_event_info = await GetServiceEventInfo(channel, program, edcb)

        # ReserveData オブジェクトに設定するチャンネル情報・番組情報を取得
        ## 放送時間未定運用などでごく稀に取得できないことも考えられるため、その場合は KonomiTV 側が持っている情報にフォールバックする
        ## 当然 TSInformation.formatString() はかけずにそのままの情報を使う
        ## ref: https://github.com/EMWUI/EDCB_Material_WebUI/blob/master/HttpPublic/api/SetReserve#L4-L39
        title: str = program.title
        start_time: datetime = program.start_time
        duration_second: int = int(program.duration)
        station_name: str = service_event_info['service_info']['service_name']
        if len(service_event_info['event_list']) > 0:
            if 'short_info' in service_event_info['event_list'][0]:
                if 'event_name' in service_event_info['event_list'][0]['short_info']:
                    title = service_event_info['event_list'][0]['short_info']['event_name']
            if 'start_time' in service_event_info['event_list'][0]:
                start_time = service_event_info['event_list'][0]['start_time']
            if 'duration_sec' in service_event_info['event_list'][0]:
                duration_second = service_event_info['event_list'][0]['duration_sec']

        # EDCB の ReserveData オブジェクトを組み立てる
        ## 一見省略しても良さそうな録画予約対象のチャンネル情報や番組情報なども省略せずに全て含める必要がある (さもないと録画予約情報が破壊される…)
        ## ただし reserve_id / overlap_mode / rec_file_name_list は EDCB 側で自動設定される (?) ため省略している
        add_reserve_data: ReserveData = {
            'title': title,
            'start_time': start_time,
            'start_time_epg': start_time,
            'duration_second': duration_second,
            'station_name': station_name,
            'onid': channel.network_id,
            'tsid': channel.transport_stream_id,
            'sid': channel.service_id,
            'eid': program.event_id,
            'comment': '',  # 単発予約の場合は空文字列で問題ないはず
            'rec_setting': cast(RecSettingData, EncodeEDCBRecSettingData(reserve_add_request.record_settings)),
        }

        # EDCB に録画予約を追加するように指示
        result = await edcb.sendAddReserve([add_reserve_data])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error('[ReservationsRouter][AddReserveAPI] Failed to add a recording reservation.')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to add a recording reservation',
            )

        # どの録画予約 ID で追加されたかは sendAddReserve() のレスポンスからは取れないので、201 Created を返す

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # 録画設定を EPGStation 形式に変換（同時に互換性チェックを実施）
        option = EncodeEPGStationRecordSettings(reserve_add_request.record_settings)

        # EPGStation の番組 ID を高精度に判定して予約を追加
        async with EPGStationUtil() as epgstation:
            epgstation_program_id, _ = await ResolveEPGStationProgram(epgstation, program)

            logging.info(f'[ReservationsRouter][AddReservationAPI] Adding reservation to EPGStation. [program_id: {program.id}, epgstation_program_id: {epgstation_program_id}]')
            reserve_id = await epgstation.addReserve(epgstation_program_id, option)
            if reserve_id is None:
                logging.error('[ReservationsRouter][AddReservationAPI] Failed to add a recording reservation to EPGStation.')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to add a recording reservation',
                )
            logging.info(f'[ReservationsRouter][AddReservationAPI] Successfully added reservation to EPGStation. [reserve_id: {reserve_id}]')

        # 201 Created を返す

    else:
        logging.error(f'[ReservationsRouter][AddReservationAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.get(
    '/{reservation_id}',
    summary = '録画予約情報取得 API',
    response_description = '録画予約の情報。',
    response_model = schemas.Reservation,
)
async def ReservationAPI(
    reservation_id: Annotated[int, Path(description='録画予約 ID ')],
    reserve_data: Annotated[ReserveDataRequired | None, Depends(GetReserveData)] = None,
):
    """
    指定された録画予約の情報を取得する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        if reserve_data is None:
            logging.error(f'[ReservationsRouter][ReservationAPI] ReserveData is None. [reservation_id: {reservation_id}]')
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail = 'Specified reservation was not found',
            )

        # EDCB の ReserveData オブジェクトを schemas.Reservation オブジェクトに変換して返す
        return await DecodeEDCBReserveData(reserve_data)

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation から予約情報を取得
        async with EPGStationUtil() as epgstation:
            reserve = await epgstation.getReserve(reservation_id, is_half_width=True)
            if reserve is None:
                logging.error(f'[ReservationsRouter][ReservationAPI] Failed to get the reservation from EPGStation. [reservation_id: {reservation_id}]')
                raise HTTPException(
                    status_code = status.HTTP_404_NOT_FOUND,
                    detail = 'Specified reservation was not found',
                )

            # 番組情報を取得（先に詳細 API を参照し、見つからない場合はスケジュールから検索）
            program_id = reserve.get('programId')
            if program_id is None:
                logging.error(f'[ReservationsRouter][ReservationAPI] programId is missing. [reservation_id: {reservation_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to get the program information',
                )

            program_data = await epgstation.getProgram(program_id, is_half_width=True)
            if program_data is None:
                schedules_data = await epgstation.getSchedules(is_half_width=True)
                for schedule in schedules_data:
                    programs_list = schedule.get('programs', [])
                    for program in programs_list:
                        if program.get('id') == program_id:
                            program_data = cast(EPGStationProgram, program)
                            break
                    if program_data is not None:
                        break

            if program_data is None:
                logging.error(f'[ReservationsRouter][ReservationAPI] Program not found. [program_id: {program_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to get the program information',
                )

            # 録画中情報を取得
            recordings_data = await epgstation.getRecordings(is_half_width=True)
            if recordings_data is None:
                recordings_data = []

            # チャンネル情報を取得
            service_id = program_data.get('serviceId')
            network_id = program_data.get('networkId')
            if service_id is None or network_id is None:
                logging.error(f'[ReservationsRouter][ReservationAPI] serviceId or networkId is missing. [program_id: {program_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to get the channel information',
                )

            channel = await Channel.filter(network_id=network_id, service_id=service_id).get_or_none()
            if channel is None:
                logging.error(
                    '[ReservationsRouter][ReservationAPI] Channel not found. '
                    f'[network_id: {network_id}, service_id: {service_id}]'
                )
                raise HTTPException(
                    status_code = status.HTTP_404_NOT_FOUND,
                    detail = 'Channel not found',
                )

            # 予約情報を変換
            return await DecodeEPGStationReserveData(reserve, program_data, channel, recordings_data)

    else:
        logging.error(f'[ReservationsRouter][ReservationAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.put(
    '/{reservation_id}',
    summary = '録画予約設定更新 API',
    response_description = '更新された録画予約の情報。',
    response_model = schemas.Reservation,
)
async def UpdateReservationAPI(
    reservation_id: Annotated[int, Path(description='録画予約 ID 。')],
    reserve_update_request: Annotated[schemas.ReservationUpdateRequest, Body(description='更新する録画予約の設定。')],
    reserve_data: Annotated[ReserveDataRequired | None, Depends(GetReserveData)] = None,
):
    """
    指定された録画予約の設定を更新する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        if reserve_data is None:
            logging.error(f'[ReservationsRouter][UpdateReservationAPI] ReserveData is None. [reservation_id: {reservation_id}]')
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail = 'Specified reservation was not found',
            )
        edcb = CtrlCmdUtil()

        # 現在の録画予約の ReserveData に新しい録画設定を上書きマージする形で EDCB に送信する
        ## 一見省略しても良さそうな録画予約対象のチャンネル情報や番組情報なども省略せずに全て含める必要がある (さもないと録画予約情報が破壊される…)
        reserve_data['rec_setting'] = EncodeEDCBRecSettingData(reserve_update_request.record_settings)

        # EDCB に指定された録画予約を更新するように指示
        result = await edcb.sendChgReserve([cast(ReserveData, reserve_data)])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error('[ReservationsRouter][UpdateReserveAPI] Failed to update the specified recording reservation.')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to update the specified recording reservation',
            )

        # 更新された録画予約の情報を schemas.Reservation オブジェクトに変換して返す
        updated_reserve_data = await GetReserveData(reserve_data['reserve_id'], edcb)
        assert updated_reserve_data is not None, 'Updated reserve data is None'
        return await DecodeEDCBReserveData(updated_reserve_data)

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # 録画設定を EPGStation 形式に変換（互換性チェック込み）
        option = EncodeEPGStationRecordSettings(reserve_update_request.record_settings)

        # EPGStation の予約を更新
        async with EPGStationUtil() as epgstation:
            logging.info(f'[ReservationsRouter][UpdateReservationAPI] Updating reservation in EPGStation. [reservation_id: {reservation_id}]')
            success = await epgstation.updateReserve(reservation_id, option)
            if not success:
                logging.error(f'[ReservationsRouter][UpdateReservationAPI] Failed to update the reservation. [reservation_id: {reservation_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to update the specified recording reservation',
                )
            logging.info(f'[ReservationsRouter][UpdateReservationAPI] Successfully updated reservation in EPGStation. [reservation_id: {reservation_id}]')

        # 更新後の予約情報を返す
        return await ReservationAPI(reservation_id)

    else:
        logging.error(f'[ReservationsRouter][UpdateReservationAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.delete(
    '/{reservation_id}',
    summary = '録画予約削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def DeleteReservationAPI(
    reservation_id: Annotated[int, Path(description='録画予約 ID 。')],
):
    """
    指定された録画予約を削除する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        edcb = CtrlCmdUtil()

        # EDCB から現在のすべての録画予約の情報を取得
        reserve_data_list: list[ReserveDataRequired] | None = await edcb.sendEnumReserve()
        if reserve_data_list is None:
            logging.error('[ReservationsRouter][DeleteReservationAPI] Failed to get the list of recording reservations.')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to get the list of recording reservations',
            )

        # 指定された録画予約の情報を取得
        reserve_data: ReserveDataRequired | None = None
        for reserve in reserve_data_list:
            if reserve['reserve_id'] == reservation_id:
                reserve_data = reserve
                break

        if reserve_data is None:
            logging.error(f'[ReservationsRouter][DeleteReservationAPI] ReserveData is None. [reservation_id: {reservation_id}]')
            raise HTTPException(
                status_code = status.HTTP_404_NOT_FOUND,
                detail = 'Specified reservation was not found',
            )

        # EDCB に指定された録画予約を削除するように指示
        result = await edcb.sendDelReserve([reserve_data['reserve_id']])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error('[ReservationsRouter][DeleteReserveAPI] Failed to delete the specified recording reservation.')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to delete the specified recording reservation',
            )

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation から予約を削除
        async with EPGStationUtil() as epgstation:
            logging.info(f'[ReservationsRouter][DeleteReservationAPI] Attempting to delete reservation. [reservation_id: {reservation_id}]')
            success = await epgstation.deleteReserve(reservation_id)
            if not success:
                logging.error(f'[ReservationsRouter][DeleteReservationAPI] Failed to delete the reservation. [reservation_id: {reservation_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to delete the specified recording reservation',
                )
            logging.info(f'[ReservationsRouter][DeleteReservationAPI] Successfully deleted reservation. [reservation_id: {reservation_id}]')

    else:
        logging.error(f'[ReservationsRouter][DeleteReservationAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )

