
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

/**
 * 番組検索結果を表すインターフェース
 */
export interface IProgramSearchResult extends IProgram {
    channel: IChannel;
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
     * EPG 機能の利用可否を取得する
     * @returns EPG 機能の利用可否
     */
    static async getEPGCapabilities(): Promise<{can_update_epg: boolean, can_reload_epg: boolean} | null> {
        const response = await APIClient.get<{can_update_epg: boolean, can_reload_epg: boolean}>('/timetable/epg-capabilities');

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'EPG 機能の情報を取得できませんでした。');
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

    /**
     * 番組を検索する
     * @param query 検索キーワード
     * @param channel_type チャンネルタイプ
     * @param start_time 検索範囲の開始時刻
     * @param end_time 検索範囲の終了時刻
     * @param limit 取得する番組数の上限
     * @returns 検索結果の番組リスト
     */
    static async searchPrograms(
        query: string,
        channel_type?: 'ALL' | 'GR' | 'BS' | 'CS',
        start_time?: Date,
        end_time?: Date,
        limit: number = 50
    ): Promise<IProgramSearchResult[] | null> {
        const params: Record<string, any> = { query, limit };
        if (channel_type) params.channel_type = channel_type;
        if (start_time) params.start_time = start_time.toISOString();
        if (end_time) params.end_time = end_time.toISOString();

        const response = await APIClient.get<IProgramSearchResult[]>('/timetable/search', { params });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, '番組の検索に失敗しました。');
            return null;
        }

        return response.data;
    }
}

export default Timetable;
