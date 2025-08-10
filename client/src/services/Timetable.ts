
import APIClient from './APIClient';
import { IChannel } from './Channels';
import { IProgram } from './Programs';

/**
 * 番組表のチャンネル情報を表すインターフェース
 */
export interface ITimetableChannel {
    channel: IChannel;
    programs: IProgram[];
}

class Timetable {

    /**
     * 番組表データを取得する
     * @param start_time 取得する番組表の開始時刻
     * @param end_time 取得する番組表の終了時刻
     * @returns 番組表データ
     */
    static async fetchTimetable(start_time: Date, end_time: Date): Promise<ITimetableChannel[] | null> {
        const response = await APIClient.get<ITimetableChannel[]>('/timetable', {
            params: {
                start_time: start_time.toISOString(),
                end_time: end_time.toISOString(),
            }
        });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, '番組表の情報を取得できませんでした。');
            return null;
        }

        return response.data;
    }
}

export default Timetable;
