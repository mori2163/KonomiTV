<<<<<<< HEAD
import APIClient from './APIClient';
import { IChannel } from './Channels';
import { IProgram } from './Programs';

/**
 * 録画フォルダの設定
 */
export interface IRecordingFolder {
    recording_folder_path: string;
    recording_file_name_template: string | null;
    is_oneseg_separate_recording_folder: boolean;
}
=======

import APIClient from '@/services/APIClient';
import { IChannel } from '@/services/Channels';
import { IProgram } from '@/services/Programs';

>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33

/**
 * 録画設定
 */
export interface IRecordSettings {
    is_enabled: boolean;
    priority: 1 | 2 | 3 | 4 | 5;
    recording_folders: IRecordingFolder[];
    recording_start_margin: number | null;
    recording_end_margin: number | null;
    recording_mode: 'AllServices' | 'AllServicesWithoutDecoding' | 'SpecifiedService' | 'SpecifiedServiceWithoutDecoding' | 'View';
    caption_recording_mode: 'Default' | 'Enable' | 'Disable';
    data_broadcasting_recording_mode: 'Default' | 'Enable' | 'Disable';
    post_recording_mode: 'Default' | 'Nothing' | 'Standby' | 'StandbyAndReboot' | 'Suspend' | 'SuspendAndReboot' | 'Shutdown';
    post_recording_bat_file_path: string | null;
    is_event_relay_follow_enabled: boolean;
    is_exact_recording_enabled: boolean;
    is_oneseg_separate_output_enabled: boolean;
    is_sequential_recording_in_single_file_enabled: boolean;
    forced_tuner_id: number | null;
}

/**
<<<<<<< HEAD
=======
 * 録画フォルダの設定
 */
export interface IRecordingFolder {
    recording_folder_path: string;
    recording_file_name_template: string | null;
    is_oneseg_separate_recording_folder: boolean;
}

/**
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
 * 録画予約情報
 */
export interface IReservation {
    id: number;
    channel: IChannel;
    program: IProgram;
    is_recording_in_progress: boolean;
    recording_availability: 'Full' | 'Partial' | 'Unavailable';
    comment: string;
    scheduled_recording_file_name: string;
    record_settings: IRecordSettings;
}

/**
 * 録画予約情報リスト API のレスポンス
 */
export interface IReservations {
    total: number;
    reservations: IReservation[];
}

/**
<<<<<<< HEAD
=======
 * 録画予約追加リクエスト
 */
export interface IReservationAddRequest {
    program_id: string;
    record_settings: IRecordSettings;
}

/**
 * 録画予約更新リクエスト
 */
export interface IReservationUpdateRequest {
    record_settings: IRecordSettings;
}

/**
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
 * 録画予約に関する API 操作を提供するクラス
 */
class Reservations {
    /**
     * すべての録画予約の情報を取得する
     * @returns 録画予約情報のリスト、取得失敗時は null
     */
    static async fetchReservations(): Promise<IReservations | null> {
        const response = await APIClient.get<IReservations>('/recording/reservations');

        if (response.type === 'error') {
            APIClient.showGenericError(response, '録画予約一覧を取得できませんでした。');
            return null;
        }

        return response.data;
    }

    /**
<<<<<<< HEAD
     * 録画予約を追加する
     * @param reservation 追加する録画予約情報
     * @returns 成功した場合は true、失敗した場合は false
     */
    static async addReservation(reservation: Partial<IReservation>): Promise<boolean> {
        // 将来実装予定
        console.warn('addReservation API は未実装です');
        return false;
=======
     * 指定された録画予約の情報を取得する
     * @param reservation_id 録画予約 ID
     * @returns 録画予約情報、取得失敗時は null
     */
    static async fetchReservation(reservation_id: number): Promise<IReservation | null> {
        const response = await APIClient.get<IReservation>(`/recording/reservations/${reservation_id}`);

        if (response.type === 'error') {
            APIClient.showGenericError(response, '録画予約情報を取得できませんでした。');
            return null;
        }

        return response.data;
    }

    /**
     * 録画予約を追加する
     * @param program_id 録画予約を追加する番組の ID
     * @param record_settings 録画設定
     * @returns 成功した場合は true、失敗した場合は false
     */
    static async addReservation(program_id: string, record_settings: IRecordSettings): Promise<boolean> {
        const request_data: IReservationAddRequest = {
            program_id,
            record_settings,
        };

        const response = await APIClient.post('/recording/reservations', request_data);

        if (response.type === 'error') {
            switch (response.data.detail) {
                case 'This API is only available when the backend is EDCB':
                    APIClient.showGenericError(response, 'この機能は EDCB バックエンド利用時のみ使用できます。');
                    break;
                case 'Specified program was not found':
                    APIClient.showGenericError(response, '指定された番組が見つかりませんでした。');
                    break;
                case 'Specified channel was not found':
                    APIClient.showGenericError(response, '指定されたチャンネルが見つかりませんでした。');
                    break;
                case 'The same program_id is already reserved':
                    APIClient.showGenericError(response, 'この番組は既に録画予約されています。');
                    break;
                case 'Failed to add a recording reservation':
                    APIClient.showGenericError(response, '録画予約の追加に失敗しました。');
                    break;
                default:
                    APIClient.showGenericError(response, '録画予約の追加に失敗しました。');
                    break;
            }
            return false;
        }

        return true;
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
    }

    /**
     * 録画予約を更新する
<<<<<<< HEAD
     * @param id 更新する録画予約の ID
     * @param reservation 更新内容
     * @returns 成功した場合は true、失敗した場合は false
     */
    static async updateReservation(id: number, reservation: Partial<IReservation>): Promise<boolean> {
        // 将来実装予定
        console.warn('updateReservation API は未実装です');
        return false;
=======
     * @param reservation_id 更新する録画予約の ID
     * @param record_settings 更新する録画設定
     * @returns 成功した場合は更新された録画予約情報、失敗した場合は null
     */
    static async updateReservation(reservation_id: number, record_settings: IRecordSettings): Promise<IReservation | null> {
        const request_data: IReservationUpdateRequest = {
            record_settings,
        };

        const response = await APIClient.put<IReservation>(`/recording/reservations/${reservation_id}`, request_data);

        if (response.type === 'error') {
            switch (response.data.detail) {
                case 'This API is only available when the backend is EDCB':
                    APIClient.showGenericError(response, 'この機能は EDCB バックエンド利用時のみ使用できます。');
                    break;
                case 'Specified reservation_id was not found':
                    APIClient.showGenericError(response, '指定された録画予約が見つかりませんでした。');
                    break;
                case 'Failed to update the specified recording reservation':
                    APIClient.showGenericError(response, '録画予約の更新に失敗しました。');
                    break;
                default:
                    APIClient.showGenericError(response, '録画予約の更新に失敗しました。');
                    break;
            }
            return null;
        }

        return response.data;
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
    }

    /**
     * 録画予約を削除する
<<<<<<< HEAD
     * @param id 削除する録画予約の ID
     * @returns 成功した場合は true、失敗した場合はエラーメッセージを含むオブジェクトまたは false
     */
    static async deleteReservation(id: number): Promise<boolean | {detail: string}> {
        const response = await APIClient.delete<void>(`/recording/reservations/${id}`);

        if (response.type === 'error') {
            // APIClient.showGenericError は内部で snackbar を表示するので、ここではエラー情報を返す
            // 呼び出し元で snackbar を表示するかどうかを制御できるようにする
            let error_detail = `録画予約 (ID: ${id}) の削除に失敗しました。`;
            if (response.data && response.data.detail) {
                if (typeof response.data.detail === 'string') {
                    error_detail = response.data.detail;
                } else if (Array.isArray(response.data.detail) && response.data.detail.length > 0) {
                    // FastAPI のバリデーションエラーの場合、最初のメッセージを使用
                    error_detail = response.data.detail[0].msg || error_detail;
                }
            }
            // APIClient.showGenericError(response, `録画予約 (ID: ${id}) の削除に失敗しました。`);
            return { detail: error_detail };
        }

        // HTTP ステータス 204 No Content の場合は成功
        if (response.status === 204) {
            return true;
        }

        // その他の予期せぬステータス
        return { detail: `録画予約 (ID: ${id}) の削除中に予期せぬエラーが発生しました。 (Status: ${response.status})` };
=======
     * @param reservation_id 削除する録画予約の ID
     * @returns 成功した場合は true、失敗した場合は false
     */
    static async deleteReservation(reservation_id: number): Promise<boolean> {
        const response = await APIClient.delete<void>(`/recording/reservations/${reservation_id}`);

        if (response.type === 'error') {
            switch (response.data.detail) {
                case 'This API is only available when the backend is EDCB':
                    APIClient.showGenericError(response, 'この機能は EDCB バックエンド利用時のみ使用できます。');
                    break;
                case 'Specified reservation_id was not found':
                    APIClient.showGenericError(response, '指定された録画予約が見つかりませんでした。');
                    break;
                case 'Failed to delete the specified recording reservation':
                    APIClient.showGenericError(response, '録画予約の削除に失敗しました。');
                    break;
                default:
                    APIClient.showGenericError(response, `録画予約 (ID: ${reservation_id}) の削除に失敗しました。`);
                    break;
            }
            return false;
        }

        return true;
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
    }
}

export default Reservations;
