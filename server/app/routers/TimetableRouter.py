
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from tortoise.expressions import Q

from app import schemas
from app.config import Config
from app.models.Channel import Channel
from app.models.Program import Program


router = APIRouter(
    prefix='/api/timetable',
    tags=['Timetable'],
    responses={422: {'description': 'Validation Error'}},
)

@router.get(
    '',
    summary='番組表データを取得',
    response_model=list[schemas.TimetableChannel],
)
async def Timetable(
    start_time: datetime = Query(..., description='取得する番組表の開始時刻'),
    end_time: datetime = Query(..., description='取得する番組表の終了時刻'),
):
    """
    指定された時間範囲の番組表データを取得する。
    """

    # クライアントから渡された datetime (UTC) を JST に変換する
    # JST に変換しないと、DB に格納されている datetime (JST) と比較する際に時刻がずれる
    start_time_jst = start_time.astimezone(ZoneInfo('Asia/Tokyo'))
    end_time_jst = end_time.astimezone(ZoneInfo('Asia/Tokyo'))

    # この時間範囲内に存在するチャンネル情報を取得
    channels = await Channel.filter(
        programs__start_time__lt=end_time_jst,
        programs__end_time__gt=start_time_jst,
    ).distinct().order_by('channel_number')

    # 各チャンネルに紐づく番組情報を取得
    timetable: list[schemas.TimetableChannel] = []
    for channel in channels:
        programs = await Program.filter(
            channel_id=channel.id,
            start_time__lt=end_time_jst,
            end_time__gt=start_time_jst,
        ).order_by('start_time')
        timetable.append(schemas.TimetableChannel(
            channel=schemas.Channel.from_orm(channel),
            programs=[schemas.Program.from_orm(program) for program in programs],
        ))

    return timetable


@router.get(
    '/search',
    summary='番組検索 API',
    response_description='検索条件に一致する番組の情報のリスト。',
    response_model=list[schemas.ProgramSearchResult],
)
async def ProgramSearchAPI(
    query: Annotated[str, Query(description='検索キーワード。title または description のいずれかに部分一致する番組を検索する。')] = '',
    channel_type: Annotated[Literal['ALL', 'GR', 'BS', 'CS'] | None, Query(description='チャンネルタイプでフィルタリング (ALL/GR/BS/CS)。')] = None,
    start_time: Annotated[datetime | None, Query(description='検索範囲の開始時刻。指定しない場合は現在時刻から検索。')] = None,
    end_time: Annotated[datetime | None, Query(description='検索範囲の終了時刻。指定しない場合は開始時刻から7日後まで検索。')] = None,
    limit: Annotated[int, Query(description='取得する番組数の上限。', ge=1, le=100)] = 50,
):
    """
    指定されたキーワードで番組を検索する。<br>
    キーワードは title または description のいずれかに部分一致する番組を検索する。<br>
    半角または全角スペースで区切ることで、複数のキーワードによる AND 検索が可能。<br>
    検索結果は放送開始時刻の昇順で返される。
    """

    # 検索範囲の時刻設定
    if start_time is None:
        start_time_jst = datetime.now(ZoneInfo('Asia/Tokyo'))
    else:
        start_time_jst = start_time.astimezone(ZoneInfo('Asia/Tokyo'))
    
    if end_time is None:
        end_time_jst = start_time_jst.replace(day=start_time_jst.day + 7)
    else:
        end_time_jst = end_time.astimezone(ZoneInfo('Asia/Tokyo'))

    # キーワードを分割（半角・全角スペースで分割）
    import re
    keywords = re.split(r'[\s　]+', query.strip())
    keywords = [k for k in keywords if k]  # 空文字列を除外

    # クエリ条件の構築
    query_conditions = Q(start_time__gte=start_time_jst, end_time__lte=end_time_jst)
    
    # キーワード検索条件（AND 検索）
    for keyword in keywords:
        keyword_condition = Q(title__icontains=keyword) | Q(description__icontains=keyword)
        query_conditions &= keyword_condition

    # チャンネルタイプでフィルタリング
    if channel_type and channel_type != 'ALL':
        query_conditions &= Q(channel__type=channel_type)

    # 番組を検索
    programs = await Program.filter(query_conditions).prefetch_related('channel').order_by('start_time').limit(limit)

    return [schemas.ProgramSearchResult.from_program(program) for program in programs]


@router.get(
    '/epg-capabilities',
    summary='EPG 機能の利用可否を取得',
    response_model=dict[str, bool],
)
async def GetEPGCapabilitiesAPI():
    """
    EPG 取得・再読み込み機能が利用可能かどうかを返す。
    EDCB バックエンドの場合のみ利用可能。
    """

    # 設定を読み込む
    config = Config()

    # EDCB バックエンドの場合のみ EPG 操作が可能
    is_edcb_backend = config.general.backend == 'EDCB'

    return {
        'can_update_epg': is_edcb_backend,
        'can_reload_epg': is_edcb_backend,
    }


@router.post(
    '/update-epg',
    summary='EPG（番組情報）取得 API',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def UpdateEPGAPI():
    """
    EPG（電子番組ガイド）の番組情報を最新状態に取得する。
    EDCB バックエンドでのみ動作します。
    """

    # 設定を読み込む
    config = Config()

    # EDCB バックエンドでない場合はエラーを返す
    if config.general.backend != 'EDCB':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='EPG 取得機能は EDCB バックエンドでのみ利用できます。'
        )

    # EDCB の CtrlCmdUtil を取得
    from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
    edcb = CtrlCmdUtil()

    # EPG 獲得を開始
    result = await edcb.sendEpgCapNow()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='EPGの取得に失敗しました。EDCBが起動していることを確認してください。'
        )
    await Channel.update()
    await Program.update(multiprocess=True)


@router.post(
    '/reload-epg',
    summary='EPG（番組情報）再読み込み API',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def ReloadEPGAPI():
    """
    EPG（電子番組ガイド）の番組情報を再読み込みする。
    EDCB バックエンドでのみ動作します。
    """

    # 設定を読み込む
    config = Config()

    # EDCB バックエンドでない場合はエラーを返す
    if config.general.backend != 'EDCB':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='EPG 再読み込み機能は EDCB バックエンドでのみ利用できます。'
        )

    # EDCB の CtrlCmdUtil を取得
    from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
    edcb = CtrlCmdUtil()

    # EPG 再読み込みを開始
    result = await edcb.sendReloadEpg()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='EPGの再読み込みに失敗しました。EDCBが起動していることを確認してください。'
        )

    # チャンネル情報とともに番組情報も更新する
    await Channel.update()
    await Program.update(multiprocess=True)
