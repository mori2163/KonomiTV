
from datetime import datetime
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from app import schemas
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

    # この時間範囲内に存在するチャンネル情報を取得
    channels = await Channel.filter(
        programs__start_time__lt=end_time,
        programs__end_time__gt=start_time,
    ).distinct().order_by('channel_number')

    # 各チャンネルに紐づく番組情報を取得
    timetable: list[schemas.TimetableChannel] = []
    for channel in channels:
        programs = await Program.filter(
            channel_id=channel.id,
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).order_by('start_time')
        timetable.append(schemas.TimetableChannel(
            channel=schemas.Channel.from_orm(channel),
            programs=[schemas.Program.from_orm(program) for program in programs],
        ))

    return timetable
