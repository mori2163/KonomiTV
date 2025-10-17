
import math
import re
from typing import Annotated, Any, Literal, cast

import ariblib.constants
from fastapi import APIRouter, Body, Depends, HTTPException, Path, status

from app import logging, schemas
from app.config import Config
from app.models.Channel import Channel
from app.routers.ReservationsRouter import (
    DecodeEDCBRecSettingData,
    EncodeEDCBRecSettingData,
    GetCtrlCmdUtil,
)
from app.utils.edcb import (
    AutoAddData,
    AutoAddDataRequired,
    ContentData,
    RecSettingData,
    SearchDateInfoRequired,
    SearchKeyInfo,
    SearchKeyInfoRequired,
)
from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
from app.utils.epgstation.EPGStationUtil import EPGStationUtil
from app.utils.epgstation.types import (
    EPGStationRule,
)


# ルーター
router = APIRouter(
    tags = ['Reservation Conditions'],
    prefix = '/api/recording/conditions',
)


async def DecodeEDCBAutoAddData(auto_add_data: AutoAddDataRequired) -> schemas.ReservationCondition:
    """
    EDCB の AutoAddData オブジェクトを schemas.ReservationCondition オブジェクトに変換する

    Args:
        auto_add_data (AutoAddDataRequired): EDCB の AutoAddData オブジェクト

    Returns:
        schemas.ReservationCondition: schemas.ReservationCondition オブジェクト
    """

    # キーワード自動予約条件 ID
    reservation_condition_id = auto_add_data['data_id']

    # このキーワード自動予約条件で登録されている録画予約の数
    reserve_count = auto_add_data['add_count']

    # 番組検索条件
    program_search_condition = await DecodeEDCBSearchKeyInfo(auto_add_data['search_info'])

    # 録画設定
    record_settings = DecodeEDCBRecSettingData(auto_add_data['rec_setting'])

    return schemas.ReservationCondition(
        id = reservation_condition_id,
        reservation_count = reserve_count,
        program_search_condition = program_search_condition,
        record_settings = record_settings,
    )


async def DecodeEDCBSearchKeyInfo(search_info: SearchKeyInfoRequired) -> schemas.ProgramSearchCondition:
    """
    EDCB の SearchKeyInfo オブジェクトを schemas.ProgramSearchCondition オブジェクトに変換する

    Args:
        search_info (SearchKeyInfoRequired): EDCB の SearchKeyInfo オブジェクト

    Returns:
        schemas.ProgramSearchCondition: schemas.ProgramSearchCondition オブジェクト
    """

    # 番組検索条件が有効かどうか
    is_enabled: bool = not search_info['key_disabled']

    # 検索キーワード
    keyword: str = search_info['and_key']

    # 除外キーワード
    ## 後述のメモ欄が :note: から始まる除外キーワードになっているので除去している
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240221/EpgTimer/EpgTimer/DefineClass/EpgAutoDataItem.cs#L35-L38
    exclude_keyword: str = re.sub(r'^:note:[^ 　]*[ 　]?', '', search_info['not_key'])

    # メモ欄
    ## EDCB の内部実装上は :note: から始まる除外キーワードになっているので抽出する
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240221/EpgTimer/EpgTimer/DefineClass/EpgAutoDataItem.cs#L39-L50
    note: str = ''
    note_match = re.match(r"^:note:([^ 　]*)", search_info['not_key'])
    if note_match is not None:
        note = note_match.group(1).replace('\\s', ' ').replace('\\m', '　').replace('\\\\', '\\')

    # 番組名のみを検索対象とするかどうか
    is_title_only: bool = search_info['title_only_flag']

    # 大文字小文字を区別するかどうか
    is_case_sensitive: bool = search_info['case_sensitive']

    # あいまい検索を行うかどうか
    is_fuzzy_search_enabled: bool = search_info['aimai_flag']

    # 正規表現で検索するかどうか
    is_regex_search_enabled: bool = search_info['reg_exp_flag']

    # 検索対象を絞り込むチャンネル範囲のリスト
    ## None を指定すると全てのチャンネルが検索対象になる
    ## ジャンル範囲や放送日時範囲とは異なり、全チャンネルが検索対象の場合は空リストにはならず、全チャンネルの ID が返ってくる
    ## 全てのチャンネルを検索対象にすると検索処理が比較的重くなるので、可能であれば絞り込む方が望ましいとのこと
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Document/Readme_Mod.txt?plain=1#L165-L170
    service_ranges: list[schemas.ProgramSearchConditionService] | None = []
    for service in search_info['service_list']:
        # service_list は (NID << 32 | TSID << 16 | SID) のリストになっているので、まずはそれらの値を分解する
        network_id = service >> 32
        transport_stream_id = (service >> 16) & 0xffff
        service_id = service & 0xffff
        # schemas.ProgramSearchConditionChannel オブジェクトを作成
        service_ranges.append(schemas.ProgramSearchConditionService(
            network_id = network_id,
            transport_stream_id = transport_stream_id,
            service_id = service_id,
        ))
    ## この時点で service_ranges の内容がデフォルトの番組検索条件のチャンネル範囲のリスト (全チャンネルが検索対象) と一致する場合、
    ## 全チャンネルを検索対象にしているのと同義なので、None に変換する
    ## 一旦リストの中の Pydantic モデルを dict に変換し、サービス ID でソートして条件を整えてから比較している
    default_service_ranges = await GetDefaultServiceRanges()
    if (sorted([service.model_dump() for service in service_ranges], key=lambda x: x['service_id']) ==
        sorted([service.model_dump() for service in default_service_ranges], key=lambda x: x['service_id'])):
        service_ranges = None

    # 検索対象を絞り込むジャンル範囲のリスト
    ## None を指定すると全てのジャンルが検索対象になる
    ## 以下の処理は app.models.Program から移植して少し調整したもの
    genre_ranges: list[schemas.Genre] | None = None
    for content in search_info['content_list']:  # ジャンルごとに
        # 大まかなジャンルを取得
        genre_tuple = ariblib.constants.CONTENT_TYPE.get(content['content_nibble'] >> 8)
        if genre_tuple is not None:
            # major … 大分類
            # middle … 中分類
            genre_dict: schemas.Genre = {
                'major': genre_tuple[0].replace('／', '・'),
                'middle': genre_tuple[1].get(content['content_nibble'] & 0xf, '未定義').replace('／', '・'),
            }
            # もし content_nibble & 0xff が 0xff なら、その大分類ジャンルの配下のすべての中分類ジャンルが検索対象になる
            if content['content_nibble'] & 0xff == 0xff:
                genre_dict['middle'] = 'すべて'
            # BS/地上デジタル放送用番組付属情報がジャンルに含まれている場合、user_nibble から値を取得して書き換える
            # たとえば「中止の可能性あり」や「延長の可能性あり」といった情報が取れる
            if genre_dict['major'] == '拡張':
                if genre_dict['middle'] == 'BS/地上デジタル放送用番組付属情報':
                    user_nibble = (content['user_nibble'] >> 8 << 4) | (content['user_nibble'] & 0xf)
                    genre_dict['middle'] = ariblib.constants.USER_TYPE.get(user_nibble, '未定義')
                # 「拡張」はあるがBS/地上デジタル放送用番組付属情報でない場合はなんの値なのかわからないのでパス
                else:
                    continue
            # ジャンルを追加
            if genre_ranges is None:
                genre_ranges = []
            genre_ranges.append(genre_dict)

    # genre_ranges で指定したジャンルを逆に検索対象から除外するかどうか
    is_exclude_genre_ranges: bool = search_info['not_contet_flag']

    # 検索対象を絞り込む放送日時範囲のリスト
    ## None を指定すると全ての放送日時が検索対象になる
    date_ranges: list[schemas.ProgramSearchConditionDate] | None = None
    for date in search_info['date_list']:
        if date_ranges is None:
            date_ranges = []
        date_ranges.append(schemas.ProgramSearchConditionDate(
            start_day_of_week = date['start_day_of_week'],
            start_hour = date['start_hour'],
            start_minute = date['start_min'],
            end_day_of_week = date['end_day_of_week'],
            end_hour = date['end_hour'],
            end_minute = date['end_min'],
        ))

    # date_ranges で指定した放送日時を逆に検索対象から除外するかどうか
    is_exclude_date_ranges: bool = search_info['not_date_flag']

    # 番組長で絞り込む最小範囲 (秒)
    ## 指定しない場合は None になる
    duration_range_min: int | None = None
    if search_info['chk_duration_min'] > 0:
        duration_range_min = search_info['chk_duration_min']

    # 番組長で絞り込む最大範囲 (秒)
    ## 指定しない場合は None になる
    duration_range_max: int | None = None
    if search_info['chk_duration_max'] > 0:
        duration_range_max = search_info['chk_duration_max']

    # 番組の放送種別で絞り込む: すべて / 無料のみ / 有料のみ
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240212/Document/Readme_Mod.txt?plain=1#L1443
    broadcast_type: Literal['All', 'FreeOnly', 'PaidOnly'] = 'All'
    if search_info['free_ca_flag'] == 0:
        broadcast_type = 'All'
    elif search_info['free_ca_flag'] == 1:
        broadcast_type = 'FreeOnly'
    elif search_info['free_ca_flag'] == 2:
        broadcast_type = 'PaidOnly'

    # 同じ番組名の既存録画との重複チェック: 何もしない / 同じチャンネルのみ対象にする / 全てのチャンネルを対象にする
    ## 同じチャンネルのみ対象にする: 同じチャンネルで同名の番組が既に録画されていれば、新しい予約を無効状態で登録する
    ## 全てのチャンネルを対象にする: 任意のチャンネルで同名の番組が既に録画されていれば、新しい予約を無効状態で登録する
    ## 仕様上予約自体を削除してしまうとすぐ再登録されてしまうので、無効状態で登録することで有効になるのを防いでいるらしい
    duplicate_title_check_scope: Literal['None', 'SameChannelOnly', 'AllChannels'] = 'None'
    if search_info['chk_rec_end'] is True:
        if search_info['chk_rec_no_service'] is True:
            duplicate_title_check_scope = 'AllChannels'
        else:
            duplicate_title_check_scope = 'SameChannelOnly'

    # 同じ番組名の既存録画との重複チェックの対象期間 (日単位)
    duplicate_title_check_period_days: int = search_info['chk_rec_day']

    return schemas.ProgramSearchCondition(
        is_enabled = is_enabled,
        keyword = keyword,
        exclude_keyword = exclude_keyword,
        note = note,
        is_title_only = is_title_only,
        is_case_sensitive = is_case_sensitive,
        is_fuzzy_search_enabled = is_fuzzy_search_enabled,
        is_regex_search_enabled = is_regex_search_enabled,
        service_ranges = cast(Any, service_ranges),
        genre_ranges = genre_ranges,
        is_exclude_genre_ranges = is_exclude_genre_ranges,
        date_ranges = date_ranges,
        is_exclude_date_ranges = is_exclude_date_ranges,
        duration_range_min = duration_range_min,
        duration_range_max = duration_range_max,
        broadcast_type = broadcast_type,
        duplicate_title_check_scope = duplicate_title_check_scope,
        duplicate_title_check_period_days = duplicate_title_check_period_days,
    )


async def EncodeEDCBSearchKeyInfo(program_search_condition: schemas.ProgramSearchCondition) -> SearchKeyInfoRequired:
    """
    schemas.ProgramSearchCondition オブジェクトを EDCB の SearchKeyInfo オブジェクトに変換する

    Args:
        program_search_condition (schemas.ProgramSearchCondition): schemas.ProgramSearchCondition オブジェクト

    Returns:
        SearchKeyInfoRequired: EDCB の SearchKeyInfo オブジェクト
    """

    ## メモ欄は EDCB の内部実装上は :note: から始まる除外キーワードになっているので再構築する
    ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240221/EpgTimer/EpgTimer/UserCtrlView/SearchKeyView.xaml.cs#L141-L142
    not_key: str = program_search_condition.exclude_keyword
    if program_search_condition.note != '':
        not_key = ':note:' + program_search_condition.note.replace('\\', '\\\\').replace(' ', '\\s').replace('　', '\\m')
        if program_search_condition.exclude_keyword != '':
            not_key += f' {program_search_condition.exclude_keyword}'  # 半角スペースを挟んでから元の除外キーワードを追加

    # 番組の放送種別で絞り込む: すべて / 無料のみ / 有料のみ
    free_ca_flag: int = 0
    if program_search_condition.broadcast_type == 'All':
        free_ca_flag = 0
    elif program_search_condition.broadcast_type == 'FreeOnly':
        free_ca_flag = 1
    elif program_search_condition.broadcast_type == 'PaidOnly':
        free_ca_flag = 2

    # 検索対象を絞り込むチャンネル範囲のリスト
    ## service_list は (NID << 32 | TSID << 16 | SID) のリストになっている
    ## ジャンル範囲や放送日時範囲とは異なり、空リストにしても全チャンネルが検索対象にはならないため、
    ## もし service_ranges が None だった場合はデフォルトの番組検索条件のチャンネル範囲のリスト (全チャンネルが検索対象) を設定する
    service_list: list[int] = []
    for channel in program_search_condition.service_ranges or await GetDefaultServiceRanges():
        service_list.append(channel.network_id << 32 | channel.transport_stream_id << 16 | channel.service_id)

    # 検索対象を絞り込むジャンル範囲のリスト
    ## 空リストを指定すると全てのジャンルが検索対象になる
    ## content_list は ContentData のリストになっている
    content_list: list[ContentData] = []
    if program_search_condition.genre_ranges is not None:
        for genre in program_search_condition.genre_ranges:
            # KonomiTV では見栄えのために ／ を ・ に置換しているので、ここで元に戻す
            major = genre['major'].replace('・', '／')
            middle = genre['middle'].replace('・', '／')
            # 万が一見つからなかった場合のデフォルト値
            content_nibble_level1 = 0xF  # "その他"
            content_nibble_level2 = 0xF  # "その他"
            user_nibble = 0x0  # user_nibble はユーザージャンルがある場合のみ値が入る
            # ariblib.constants.CONTENT_TYPE から文字列表現と一致する値を探す
            for major_key, major_value in ariblib.constants.CONTENT_TYPE.items():
                if major_value[0] == major:
                    # content_nibble_level1 には大分類の値を入れる
                    content_nibble_level1 = major_key
                    # もし大分類が "拡張" の時のみ、中分類の文字列表現に当てはまるBS/地上デジタル放送用番組付属情報を探す
                    # TODO: 本来は広帯域CSデジタル放送用拡張にも対応すべきだが、ariblib に対応する定数がなく各所で対応できてないため今のところ未対応
                    if content_nibble_level1 == 0xE:
                        for user_key, user_value in ariblib.constants.USER_TYPE.items():
                            if user_value == middle:
                                # content_nibble_level2 にはBS/地上デジタル放送用番組付属情報を示す値を入れる
                                content_nibble_level2 = 0x0
                                # user_nibble には中分類の値を入れる
                                user_nibble = user_key
                                break
                    # もし中分類の文字列が "すべて" だった場合、その大分類の全ての中分類を検索対象にする
                    elif middle == 'すべて':
                        # 0xFF は全ての中分類を示す (おそらく EDCB 独自仕様？)
                        ## 本来の放送波に含まれる content_nibble_level2 は 4 ビットの値なので本来は 0x0 ~ 0xF までの値が入る
                        content_nibble_level2 = 0xFF
                        break
                    # 中分類の値を探す
                    else:
                        for middle_key, middle_value in major_value[1].items():
                            if middle_value == middle:
                                # content_nibble_level2 には中分類の値を入れる
                                content_nibble_level2 = middle_key
                                break
            # EDCB の ContentData の content_nibble は content_nibble_level1 * 256 + content_nibble_level2 になっている
            ## ref: https://github.com/xtne6f/EDCB/blob/work-plus-s-240221/Document/Readme_Mod.txt?plain=1#L1450
            content_list.append({
                'content_nibble': content_nibble_level1 * 256 + content_nibble_level2,
                'user_nibble': user_nibble,
            })

    # 検索対象を絞り込む放送日時範囲のリスト
    ## 空リストを指定すると全ての放送日時が検索対象になる
    ## date_list は SearchDateInfoRequired のリストになっている
    date_list: list[SearchDateInfoRequired] = []
    if program_search_condition.date_ranges is not None:
        for date in program_search_condition.date_ranges:
            # これだけデータ構造がキー名以外 EDCB と KonomiTV で同一なのでそのまま追加
            date_list.append({
                'start_day_of_week': date.start_day_of_week,
                'start_hour': date.start_hour,
                'start_min': date.start_minute,
                'end_day_of_week': date.end_day_of_week,
                'end_hour': date.end_hour,
                'end_min': date.end_minute,
            })

    # EDCB の SearchKeyInfo オブジェクトを作成
    search_info: SearchKeyInfoRequired = {
        'and_key': program_search_condition.keyword,
        'not_key': not_key,
        'key_disabled': not program_search_condition.is_enabled,
        'case_sensitive': program_search_condition.is_case_sensitive,
        'reg_exp_flag': program_search_condition.is_regex_search_enabled,
        'title_only_flag': program_search_condition.is_title_only,
        'content_list': content_list,
        'date_list': date_list,
        'service_list': service_list,
        'video_list': [],  # 内部で未使用らしい
        'audio_list': [],  # 内部で未使用らしい
        'aimai_flag': program_search_condition.is_fuzzy_search_enabled,
        'not_contet_flag': program_search_condition.is_exclude_genre_ranges,
        'not_date_flag': program_search_condition.is_exclude_date_ranges,
        'free_ca_flag': free_ca_flag,
        'chk_rec_end': program_search_condition.duplicate_title_check_scope != 'None',
        'chk_rec_day': program_search_condition.duplicate_title_check_period_days,
        'chk_rec_no_service': program_search_condition.duplicate_title_check_scope == 'AllChannels',
        'chk_duration_min': program_search_condition.duration_range_min if program_search_condition.duration_range_min is not None else 0,
        'chk_duration_max': program_search_condition.duration_range_max if program_search_condition.duration_range_max is not None else 0,
    }

    return search_info


async def GetDefaultServiceRanges() -> list[schemas.ProgramSearchConditionService]:
    """
    デフォルトの番組検索条件のチャンネル範囲のリスト (全チャンネルが検索対象) を取得する
    KonomiTV のデータベース上に保存されているチャンネル数と EDCB 上で有効とされている (EPG 取得対象の) チャンネル数が一致する前提の元、
    Channel モデルから EPG 取得対象のチャンネルの情報を取得している

    Returns:
        list[schemas.ProgramSearchConditionService]: デフォルトの番組検索条件のチャンネル範囲のリスト
    """

    # チャンネル情報を取得
    ## リモコン番号順にソートしておく
    ## EDCB が返すレスポンスが必ずしもリモコン ID でソートされているとは限らない (サービス ID でソートされていることもある？) ので、
    ## この関数で返す値が順序含めて完全に一致するとは限らないし、等価か比較する際は別途ソートする必要がある
    channels = await Channel.filter(is_watchable=True).order_by('channel_number').order_by('remocon_id')

    # チャンネルタイプごとにグループ化
    ground_channels: dict[Literal['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'], list[Channel]] = {}
    for channel in channels:
        if channel.type not in ground_channels:
            ground_channels[channel.type] = []
        ground_channels[channel.type].append(channel)

    # 地上波・BS・110度CS・CATV・124/128度CS・BS4K の順に連結
    sorted_channels: list[Channel] = []
    for channel_type in ['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K']:
        if channel_type in ground_channels:
            sorted_channels.extend(ground_channels[channel_type])

    # ProgramSearchConditionService オブジェクトに変換
    default_service_ranges: list[schemas.ProgramSearchConditionService] = []
    for channel in sorted_channels:
        assert channel.transport_stream_id is not None, 'transport_stream_id is missing.'
        default_service_ranges.append(schemas.ProgramSearchConditionService(
            network_id = channel.network_id,
            transport_stream_id = channel.transport_stream_id,
            service_id = channel.service_id,
        ))

    return default_service_ranges


async def GetAutoAddDataList(
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
) -> list[AutoAddDataRequired]:
    """ すべてのキーワード自動予約条件の情報を取得する """

    # EDCB から現在のすべてのキーワード自動予約条件の情報を取得
    auto_add_data_list: list[AutoAddDataRequired] | None = await edcb.sendEnumAutoAdd()
    if auto_add_data_list is None:
        # None が返ってきた場合はエラーを返す
        logging.error('[ReservationConditionsRouter][GetAutoAddDataList] Failed to get the list of reserve conditions.')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Failed to get the list of reserve conditions',
        )

    return auto_add_data_list


async def GetAutoAddData(
    reservation_condition_id: Annotated[int, Path(description='キーワード自動予約条件 ID 。')],
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
) -> AutoAddDataRequired:
    """ 指定されたキーワード自動予約条件の情報を取得する """

    # 指定されたキーワード自動予約条件の情報を取得
    for auto_add_data in await GetAutoAddDataList(edcb):
        if auto_add_data['data_id'] == reservation_condition_id:
            return auto_add_data

    # 指定されたキーワード自動予約条件が見つからなかった場合はエラーを返す
    logging.error('[ReservationConditionsRouter][GetAutoAddData] Specified reservation_condition_id was not found. '
                    f'[reservation_condition_id: {reservation_condition_id}]')
    raise HTTPException(
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail = 'Specified reservation_condition_id was not found',
    )


async def DecodeEPGStationRuleData(rule: EPGStationRule) -> schemas.ReservationCondition:
    """
    EPGStation の Rule オブジェクトを schemas.ReservationCondition オブジェクトに変換する

    Args:
        rule (EPGStationRule): EPGStation の Rule オブジェクト

    Returns:
        schemas.ReservationCondition: schemas.ReservationCondition オブジェクト
    """

    # ルール ID
    reservation_condition_id = rule.get('id', 0)

    # このルールで登録されている録画予約の数（EPGStation の API では取得できないため 0 固定）
    reserve_count = 0

    search_option = cast(dict[str, Any], rule.get('searchOption', {}))

    # 番組検索条件
    program_search_condition = DecodeEPGStationSearchOption(rule, search_option)

    # 録画設定（reserveOption の内容を KonomiTV の形式へ変換）
    from app.routers.ReservationsRouter import DecodeEPGStationRecordSettings
    reserve_option = cast(dict[str, Any], rule.get('reserveOption', {}))
    record_settings = DecodeEPGStationRecordSettings(reserve_option)

    return schemas.ReservationCondition(
        id = reservation_condition_id,
        reservation_count = reserve_count,
        program_search_condition = program_search_condition,
        record_settings = record_settings,
    )


def DecodeEPGStationSearchOption(rule: EPGStationRule, search_option: dict[str, Any]) -> schemas.ProgramSearchCondition:
    """
    EPGStation の Rule オブジェクトから schemas.ProgramSearchCondition オブジェクトを生成する

    Args:
        rule (EPGStationRule): EPGStation の Rule オブジェクト

    Returns:
        schemas.ProgramSearchCondition: schemas.ProgramSearchCondition オブジェクト
    """

    # 番組検索条件が有効かどうか
    is_enabled: bool = bool(search_option.get('enable', True)) and not rule.get('isDisabled', False)

    # 検索キーワード
    keyword: str = cast(str, search_option.get('keyword') or rule.get('keyword') or '')

    # 除外キーワード
    exclude_keyword: str = cast(str, search_option.get('ignoreKeyword') or '')

    # メモ欄（EPGStation にはメモ欄がないため空文字列）
    note: str = ''

    # 番組名のみを検索対象とするかどうか
    name_flag = bool(search_option.get('name', True))
    description_flag = bool(search_option.get('description', True))
    extended_flag = bool(search_option.get('extended', True))
    is_title_only: bool = name_flag and not description_flag and not extended_flag

    # 大文字小文字を区別するかどうか
    is_case_sensitive: bool = bool(search_option.get('keyCS', False))

    # 正規表現で検索するかどうか
    is_regex_search_enabled: bool = bool(search_option.get('keyRegExp', False))

    # あいまい検索（EPGStation では未サポートのため False 固定）
    is_fuzzy_search_enabled: bool = False

    # 対象サービス（EPGStation の stations を利用）
    ## 現時点では EPGStation のチャンネル ID と KonomiTV のチャンネル情報を
    ## 完全にマッピングする手段がないため None を返す
    service_ranges: list[schemas.ProgramSearchConditionService] | None = None

    # ジャンル（EPGStation は genres で ARIB ジャンル配列を指定）
    genre_ranges: list[schemas.Genre] | None = None
    genres_data = search_option.get('genres', []) or []
    if genres_data:
        genre_ranges = []
        for genre_data in genres_data:
            lv1 = genre_data.get('lv1', genre_data.get('genre'))
            lv2 = genre_data.get('lv2', genre_data.get('subGenre'))
            if lv1 is not None and lv2 is not None:
                genre_ranges.append(schemas.Genre(
                    major = lv1,
                    middle = lv2,
                ))

    # ジャンルを除外するかどうか
    is_exclude_genre_ranges: bool = False

    # 番組長（EPGStation は durationMin, durationMax で分単位で指定）
    duration_range_min: int | None = cast(int | None, search_option.get('durationMin'))
    duration_range_max: int | None = cast(int | None, search_option.get('durationMax'))

    # 検索対象期間（EPGStation は searchPeriods で時間帯を指定）
    ## searchPeriods は [{startHour: number, startMin: number, endHour: number, endMin: number, week: number}] 形式
    ## week は曜日のビットフラグ (0x01=日, 0x02=月, ..., 0x40=土)
    date_ranges: list[schemas.ProgramSearchConditionDate] | None = None
    search_periods = search_option.get('searchPeriods', []) or []
    if search_periods:
        date_ranges = []
        for period in search_periods:
            start_hour = period.get('startHour', period.get('startHourOfDay', 0))
            start_min = period.get('startMin', period.get('startMinute', 0))
            end_hour = period.get('endHour', period.get('endHourOfDay', 0))
            end_min = period.get('endMin', period.get('endMinute', 0))
            week = period.get('week', 0)

            # 曜日ビットフラグから開始曜日と終了曜日を特定
            ## EPGStation の week は複数曜日を指定できるが、KonomiTV は開始曜日と終了曜日のペアのみ対応
            ## 簡易的に最初にセットされている曜日を開始、最後にセットされている曜日を終了とする
            start_dow = 0
            end_dow = 0
            for i in range(7):
                if week & (1 << i):
                    if start_dow == 0 and end_dow == 0:
                        start_dow = i
                    end_dow = i

            date_ranges.append(schemas.ProgramSearchConditionDate(
                start_day_of_week = start_dow,
                start_hour = start_hour,
                start_minute = start_min,
                end_day_of_week = end_dow,
                end_hour = end_hour,
                end_minute = end_min,
            ))

    # 日付範囲を除外するかどうか
    is_exclude_date_ranges: bool = False

    # 放送種別（EPGStation では指定できないため All 固定）
    broadcast_type: Literal['All', 'FreeOnly', 'PaidOnly'] = 'All'
    is_free_value = search_option.get('isFree')
    if is_free_value is True:
        broadcast_type = 'FreeOnly'
    elif is_free_value is False:
        broadcast_type = 'PaidOnly'

    # 重複チェック（EPGStation では指定できないため None 固定）
    duplicate_title_check_scope: Literal['None', 'SameChannelOnly', 'AllChannels'] = 'None'
    duplicate_title_check_period_days: int = 6
    if search_option.get('avoidDuplicate'):
        duplicate_title_check_scope = 'AllChannels'
        period_hours = cast(int | None, search_option.get('periodToAvoidDuplicate'))
        if period_hours is not None and period_hours > 0:
            duplicate_title_check_period_days = max(1, math.ceil(period_hours / 24))

    return schemas.ProgramSearchCondition(
        is_enabled = is_enabled,
        keyword = keyword,
        exclude_keyword = exclude_keyword,
        note = note,
        is_title_only = is_title_only,
        is_case_sensitive = is_case_sensitive,
        is_regex_search_enabled = is_regex_search_enabled,
        is_fuzzy_search_enabled = is_fuzzy_search_enabled,
        service_ranges = service_ranges,
        genre_ranges = genre_ranges,
        is_exclude_genre_ranges = is_exclude_genre_ranges,
        date_ranges = date_ranges,
        is_exclude_date_ranges = is_exclude_date_ranges,
        duration_range_min = duration_range_min,
        duration_range_max = duration_range_max,
        broadcast_type = broadcast_type,
        duplicate_title_check_scope = duplicate_title_check_scope,
        duplicate_title_check_period_days = duplicate_title_check_period_days,
    )


def EncodeEPGStationRuleData(
    condition_request: schemas.ReservationConditionAddRequest | schemas.ReservationConditionUpdateRequest,
) -> dict[str, Any]:
    """
    schemas.ReservationConditionAddRequest/UpdateRequest を EPGStation の Rule 作成/更新用のデータに変換する

    Args:
        condition_request: 予約条件リクエスト

    Returns:
        dict[str, Any]: EPGStation の Rule データ
    """

    search_cond = condition_request.program_search_condition

    search_option: dict[str, Any] = {
        'enable': search_cond.is_enabled,
        'keyword': search_cond.keyword,
        'ignoreKeyword': search_cond.exclude_keyword or None,
        'keyCS': search_cond.is_case_sensitive,
        'keyRegExp': search_cond.is_regex_search_enabled,
        'name': True,
        'description': not search_cond.is_title_only,
        'extended': not search_cond.is_title_only,
        'stations': [],
    }

    if search_cond.genre_ranges:
        search_option['genres'] = [
            {'genre': genre.major, 'subGenre': genre.middle}
            for genre in search_cond.genre_ranges
        ]

    if search_cond.duration_range_min is not None and search_cond.duration_range_min > 0:
        search_option['durationMin'] = search_cond.duration_range_min
    if search_cond.duration_range_max is not None and search_cond.duration_range_max > 0:
        search_option['durationMax'] = search_cond.duration_range_max

    if search_cond.broadcast_type == 'FreeOnly':
        search_option['isFree'] = True
    elif search_cond.broadcast_type == 'PaidOnly':
        search_option['isFree'] = False

    if search_cond.date_ranges:
        search_periods = []
        for date_range in search_cond.date_ranges:
            week = 0
            start_dow = date_range.start_day_of_week
            end_dow = date_range.end_day_of_week

            if start_dow <= end_dow:
                for dow in range(start_dow, end_dow + 1):
                    week |= (1 << dow)
            else:
                for dow in range(start_dow, 7):
                    week |= (1 << dow)
                for dow in range(0, end_dow + 1):
                    week |= (1 << dow)

            search_periods.append({
                'startHour': date_range.start_hour,
                'startMin': date_range.start_minute,
                'endHour': date_range.end_hour,
                'endMin': date_range.end_minute,
                'week': week,
            })

        search_option['searchPeriods'] = search_periods

    if search_cond.duplicate_title_check_scope != 'None':
        search_option['avoidDuplicate'] = True
        search_option['periodToAvoidDuplicate'] = max(1, search_cond.duplicate_title_check_period_days) * 24

    from app.routers.ReservationsRouter import EncodeEPGStationRecordSettings

    rule_data: dict[str, Any] = {
        'keyword': search_cond.keyword,
        'isTimeSpecification': False,
        'isDisabled': not search_cond.is_enabled,
        'searchOption': search_option,
        'reserveOption': EncodeEPGStationRecordSettings(condition_request.record_settings),
    }

    return rule_data


@router.get(
    '',
    summary = 'キーワード自動予約条件一覧 API',
    response_description = 'キーワード自動予約条件のリスト。',
    response_model = schemas.ReservationConditions,
)
async def ReservationConditionsAPI(
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
):
    """
    すべてのキーワード自動予約条件 (EPG 予約) の情報を取得する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        edcb = CtrlCmdUtil()

        # EDCB から現在のすべてのキーワード自動予約条件の情報を取得
        auto_add_data_list: list[AutoAddDataRequired] | None = await edcb.sendEnumAutoAdd()
        if auto_add_data_list is None:
            # None が返ってきた場合は空のリストを返す
            return schemas.ReservationConditions(total=0, reservation_conditions=[])

        # EDCB の AutoAddData オブジェクトを schemas.ReservationCondition オブジェクトに変換
        reserve_conditions = [await DecodeEDCBAutoAddData(auto_add_data) for auto_add_data in auto_add_data_list]

        return schemas.ReservationConditions(total=len(reserve_conditions), reservation_conditions=reserve_conditions)

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation からルール一覧を取得
        async with EPGStationUtil() as epgstation:
            rules = await epgstation.getRules()
            if rules is None:
                return schemas.ReservationConditions(total=0, reservation_conditions=[])

            # EPGStation の Rule オブジェクトを schemas.ReservationCondition オブジェクトに変換
            reserve_conditions = [await DecodeEPGStationRuleData(rule) for rule in rules]

            return schemas.ReservationConditions(total=len(reserve_conditions), reservation_conditions=reserve_conditions)

    else:
        logging.error(f'[ReservationConditionsRouter][ReservationConditionsAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.post(
    '',
    summary = 'キーワード自動予約条件登録 API',
    status_code = status.HTTP_201_CREATED,
)
async def RegisterReservationConditionAPI(
    reserve_condition_add_request: Annotated[schemas.ReservationConditionAddRequest, Body(description='登録するキーワード自動予約条件。')],
    edcb: Annotated[CtrlCmdUtil, Depends(GetCtrlCmdUtil)],
):
    """
    キーワード自動予約条件を登録する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        assert edcb is not None, 'CtrlCmdUtil instance is None'

        # EDCB の AutoAddData オブジェクトを組み立てる
        ## data_id は EDCB 側で自動で割り振られるため省略している
        auto_add_data: AutoAddData = {
            'search_info': cast(SearchKeyInfo, await EncodeEDCBSearchKeyInfo(reserve_condition_add_request.program_search_condition)),
            'rec_setting': cast(RecSettingData, EncodeEDCBRecSettingData(reserve_condition_add_request.record_settings)),
        }

        # EDCB にキーワード自動予約条件を登録するように指示
        result = await edcb.sendAddAutoAdd([auto_add_data])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error('[ReservationConditionsRouter][RegisterReservationConditionAPI] Failed to register the reserve condition.')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to register the reserve condition',
            )

        # どのキーワード自動予約条件 ID で追加されたかは sendAddAutoAdd() のレスポンスからは取れないので、201 Created を返す

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation にルールを追加
        async with EPGStationUtil() as epgstation:
            rule_data = EncodeEPGStationRuleData(reserve_condition_add_request)
            rule_id = await epgstation.addRule(rule_data)
            if rule_id is None:
                logging.error('[ReservationConditionsRouter][RegisterReservationConditionAPI] Failed to register the reserve condition.')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to register the reserve condition',
                )

        # 201 Created を返す

    else:
        logging.error(f'[ReservationConditionsRouter][RegisterReservationConditionAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.get(
    '/{reservation_condition_id}',
    summary = 'キーワード自動予約条件取得 API',
    response_description = 'キーワード自動予約条件。',
    response_model = schemas.ReservationCondition,
)
async def ReservationConditionAPI(
    reservation_condition_id: Annotated[int, Path(description='キーワード自動予約条件 ID 。')],
    auto_add_data: Annotated[AutoAddDataRequired | None, Depends(GetAutoAddData)] = None,
):
    """
    指定されたキーワード自動予約条件の情報を取得する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        assert auto_add_data is not None, 'AutoAddData is None'

        # EDCB の AutoAddData オブジェクトを schemas.ReservationCondition オブジェクトに変換して返す
        return await DecodeEDCBAutoAddData(auto_add_data)

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation からルール情報を取得
        async with EPGStationUtil() as epgstation:
            rule = await epgstation.getRule(reservation_condition_id)
            if rule is None:
                logging.error(f'[ReservationConditionsRouter][ReservationConditionAPI] Failed to get the rule. [reservation_condition_id: {reservation_condition_id}]')
                raise HTTPException(
                    status_code = status.HTTP_404_NOT_FOUND,
                    detail = 'Specified reservation_condition_id was not found',
                )

            return await DecodeEPGStationRuleData(rule)

    else:
        logging.error(f'[ReservationConditionsRouter][ReservationConditionAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.put(
    '/{reservation_condition_id}',
    summary = 'キーワード自動予約条件更新 API',
    response_description = '更新されたキーワード自動予約条件。',
    response_model = schemas.ReservationCondition,
)
async def UpdateReservationConditionAPI(
    reservation_condition_id: Annotated[int, Path(description='キーワード自動予約条件 ID 。')],
    reserve_condition_update_request: Annotated[schemas.ReservationConditionUpdateRequest, Body(description='更新するキーワード自動予約条件。')],
    auto_add_data: Annotated[AutoAddDataRequired | None, Depends(GetAutoAddData)] = None,
):
    """
    指定されたキーワード自動予約条件を更新する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        assert auto_add_data is not None, 'AutoAddData is None'
        edcb = CtrlCmdUtil()

        # 現在のキーワード自動予約条件の AutoAddData に新しい検索条件・録画設定を上書きマージする形で EDCB に送信する
        auto_add_data['search_info'] = await EncodeEDCBSearchKeyInfo(reserve_condition_update_request.program_search_condition)
        auto_add_data['rec_setting'] = EncodeEDCBRecSettingData(reserve_condition_update_request.record_settings)

        # EDCB に指定されたキーワード自動予約条件を更新するように指示
        result = await edcb.sendChgAutoAdd([cast(AutoAddData, auto_add_data)])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error('[ReservationConditionsRouter][UpdateReservationConditionAPI] Failed to update the specified reserve condition. '
                          f'[reservation_condition_id: {auto_add_data["data_id"]}]')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to update the specified reserve condition',
            )

        # 更新されたキーワード自動予約条件の情報を schemas.ReservationCondition オブジェクトに変換して返す
        return await DecodeEDCBAutoAddData(await GetAutoAddData(auto_add_data['data_id'], edcb))

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation のルールを更新
        async with EPGStationUtil() as epgstation:
            rule_data = EncodeEPGStationRuleData(reserve_condition_update_request)
            success = await epgstation.updateRule(reservation_condition_id, rule_data)
            if not success:
                logging.error(f'[ReservationConditionsRouter][UpdateReservationConditionAPI] Failed to update the rule. [reservation_condition_id: {reservation_condition_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to update the specified reserve condition',
                )

        # 更新後のルール情報を返す
        return await ReservationConditionAPI(reservation_condition_id)

    else:
        logging.error(f'[ReservationConditionsRouter][UpdateReservationConditionAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )


@router.delete(
    '/{reservation_condition_id}',
    summary = 'キーワード自動予約条件削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def DeleteReservationConditionAPI(
    reservation_condition_id: Annotated[int, Path(description='キーワード自動予約条件 ID 。')],
    auto_add_data: Annotated[AutoAddDataRequired | None, Depends(GetAutoAddData)] = None,
    edcb: Annotated[CtrlCmdUtil | None, Depends(GetCtrlCmdUtil)] = None,
):
    """
    指定されたキーワード自動予約条件を削除する。
    """

    # レコーダーが EDCB の場合
    if Config().general.recorder == 'EDCB':
        assert auto_add_data is not None, 'AutoAddData is None'
        assert edcb is not None, 'CtrlCmdUtil instance is None'

        # TODO: キーワード自動予約条件を削除した後に残った予約をクリーンアップする処理を追加する

        # EDCB に指定されたキーワード自動予約条件を削除するように指示
        result = await edcb.sendDelAutoAdd([auto_add_data['data_id']])
        if result is False:
            # False が返ってきた場合はエラーを返す
            logging.error(f'[ReservationConditionsRouter][DeleteReservationConditionAPI] Failed to delete the specified reserve condition. '
                          f'[reservation_condition_id: {auto_add_data["data_id"]}]')
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = 'Failed to delete the specified reserve condition',
            )

    # レコーダーが EPGStation の場合
    elif Config().general.recorder == 'EPGStation':

        # EPGStation からルールを削除
        async with EPGStationUtil() as epgstation:
            success = await epgstation.deleteRule(reservation_condition_id)
            if not success:
                logging.error(f'[ReservationConditionsRouter][DeleteReservationConditionAPI] Failed to delete the rule. [reservation_condition_id: {reservation_condition_id}]')
                raise HTTPException(
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail = 'Failed to delete the specified reserve condition',
                )

    else:
        logging.error(f'[ReservationConditionsRouter][DeleteReservationConditionAPI] Unknown recorder type: {Config().general.recorder}')
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Unknown recorder type',
        )
