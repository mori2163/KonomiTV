
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

    /**
     * EPG（番組情報）を取得する
     * @returns 更新が成功したかどうか
     */
    static async updateEPG(): Promise<boolean> {
        const response = await APIClient.post('/timetable/update-epg');

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'EPG の取得に失敗しました。');
            return false;
        }

        return true;
    }

    /**
     * EPG（番組情報）を再読み込みする
     * @returns 再読み込みが成功したかどうか
     */
    static async reloadEPG(): Promise<boolean> {
        const response = await APIClient.post('/timetable/reload-epg');

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'EPG の再読み込みに失敗しました。');
            return false;
        }

        return true;
    }
}

export default Timetable;
