
from datetime import datetime
from zoneinfo import ZoneInfo

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

    channel_id_list = [channel.id for channel in channels]

    # 対象チャンネルの番組情報を一括で取得し、チャンネルごとにグルーピングする
    programs: list[Program] = []
    if channel_id_list:
        programs = await Program.filter(
            channel_id__in=channel_id_list,
            start_time__lt=end_time_jst,
            end_time__gt=start_time_jst,
        ).order_by('channel_id', 'start_time')

    programs_by_channel: dict[str, list[Program]] = {}
    for program in programs:
        programs_by_channel.setdefault(program.channel_id, []).append(program)

    timetable: list[schemas.TimetableChannel] = []
    for channel in channels:
        channel_programs = programs_by_channel.get(channel.id, [])
        timetable.append(schemas.TimetableChannel(
            channel=schemas.Channel.from_orm(channel),
            programs=[schemas.Program.from_orm(program) for program in channel_programs],
        ))

    return timetable


@router.post(
    '/update-epg',
    summary='EPG（番組情報）取得 API',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def UpdateEPGAPI():
    """
    EPG（電子番組ガイド）の番組情報を最新状態に取得する。
    """

    config = Config()

    if config.general.backend == 'EDCB':
        # EDCB の CtrlCmdUtil を取得
        from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
        edcb = CtrlCmdUtil()

        # EPG 獲得を開始
        result = await edcb.sendEpgCapNow()

        if result is None:
            raise ValueError('EPGの取得に失敗しました。EDCBが起動していることを確認してください。')
        await Channel.update()
        await Program.update(multiprocess=True)

    elif config.general.backend == 'Mirakurun':
        # Mirakurun / EPGStation 構成では、Mirakurun から番組情報を再取得する
        await Channel.update()
        await Program.update(multiprocess=True)

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported backend configuration')


@router.post(
    '/reload-epg',
    summary='EPG（番組情報）再読み込み API',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def ReloadEPGAPI():
    """
    EPG（電子番組ガイド）の番組情報を再読み込みする。
    """

    config = Config()

    if config.general.backend == 'EDCB':
        # EDCB の CtrlCmdUtil を取得
        from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
        edcb = CtrlCmdUtil()

        # EPG 再読み込みを開始
        result = await edcb.sendReloadEpg()

        if not result:
            raise ValueError('EPGの再読み込みに失敗しました。EDCBが起動していることを確認してください。')

        # チャンネル情報とともに番組情報も更新する
        await Channel.update()
        await Program.update(multiprocess=True)

    elif config.general.backend == 'Mirakurun':
        # Mirakurun / EPGStation 構成では Channel / Program を再同期するのみ
        await Channel.update()
        await Program.update(multiprocess=True)

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported backend configuration')

@router.get(
    '/search',
    summary='番組表検索 API',
    response_model=schemas.Programs,
)
async def TimetableSearchAPI(
    keyword: str = Query(..., min_length=1, description='検索キーワード'),
    title_only: bool = Query(False, description='番組名のみを検索対象にする'),
    is_free_only: bool = Query(False, description='無料番組のみを対象にする'),
    channel_ids: list[str] = Query(default_factory=list, description='検索対象のチャンネルID'),
    start_time: datetime | None = Query(None, description='検索対象の開始時刻'),
    end_time: datetime | None = Query(None, description='検索対象の終了時刻'),
    limit: int = Query(200, ge=1, le=500, description='取得する件数'),
    offset: int = Query(0, ge=0, description='スキップする件数'),
):
    """
    指定条件に一致する番組を検索する。
    """

    keyword = keyword.strip()
    if keyword == '':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Keyword must not be empty')

    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='start_time must be earlier than end_time')

    start_time_jst = start_time.astimezone(ZoneInfo('Asia/Tokyo')) if start_time else None
    end_time_jst = end_time.astimezone(ZoneInfo('Asia/Tokyo')) if end_time else None

    base_query = Program.filter()

    if start_time_jst:
        # 番組終了時刻が開始時刻より後のものを対象にする
        base_query = base_query.filter(end_time__gt=start_time_jst)
    if end_time_jst:
        # 番組開始時刻が終了時刻より前のものを対象にする
        base_query = base_query.filter(start_time__lt=end_time_jst)

    if channel_ids:
        base_query = base_query.filter(channel_id__in=channel_ids)

    if is_free_only:
        base_query = base_query.filter(is_free=True)

    if title_only:
        filtered_query = base_query.filter(title__icontains=keyword)
    else:
        filtered_query = base_query.filter(
            Q(title__icontains=keyword) | Q(description__icontains=keyword),
        )

    filtered_query = filtered_query.order_by('start_time')

    total = await filtered_query.count()
    program_models = await filtered_query.offset(offset).limit(limit).all()

    programs = [schemas.Program.from_orm(program) for program in program_models]
    return schemas.Programs(total=total, programs=programs)

