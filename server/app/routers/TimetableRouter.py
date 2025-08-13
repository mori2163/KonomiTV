
from datetime import datetime
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi import status
from zoneinfo import ZoneInfo

from app import schemas
from app.models.Channel import Channel
from app.models.Program import Program
from app.routers.UsersRouter import GetCurrentAdminUser

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


@router.post(
    '/update-epg',
    summary='EPG（番組情報）取得 API',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def UpdateEPGAPI():
    """
    EPG（電子番組ガイド）の番組情報を最新状態に取得する。
    """

    # EDCB の CtrlCmdUtil を取得
    from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil
    edcb = CtrlCmdUtil()

    # EPG 獲得を開始
    result = await edcb.sendEpgCapNow()

    if result is None:
        raise ValueError('EPGの取得に失敗しました。EDCBが起動していることを確認してください。')
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
    """

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
