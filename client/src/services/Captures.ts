
import { AxiosError } from 'axios';

import Message from '@/message';
import APIClient from '@/services/APIClient';


interface ICapture {
    path: string;
    name: string;
    size: number;
    url: string;
    time: string | null;
    program_title: string | null;
    channel_name: string | null;
}

class Captures {

    /**
     * キャプチャの一覧を取得する
     * @returns キャプチャの一覧
     */
    static async fetchCaptures(): Promise<ICapture[] | null> {
        const response = await APIClient.get<ICapture[]>('/captures');
        if (response.type === 'success') {
            response.data.forEach(capture => {
                capture.url = `/api${capture.url}`;
            });
            return response.data;
        }
        return null;
    }

    /**
     * キャプチャをサーバーにアップロードし保存する
     * @param blob キャプチャ画像の Blob
     * @param filename サーバーに保存するときのファイル名
     */
    static async uploadCapture(blob: Blob, filename: string): Promise<void> {

        // キャプチャ画像の File オブジェクト (= Blob) を FormData に入れる
        // multipart/form-data で送るために必要
        // ref: https://r17n.page/2020/02/04/nodejs-axios-file-upload-api/
        const form_data = new FormData();
        form_data.append('image', blob, filename);

        // API リクエストを実行
        const response = await APIClient.post('/captures', form_data, {headers: {'Content-Type': 'multipart/form-data'}});

        // エラー処理
        if (response.type === 'error') {
            switch (response.data.detail) {
                case 'Permission denied to save the file': {
                    Message.error('キャプチャのアップロードに失敗しました。保存先フォルダに書き込み権限がありません。');
                    break;
                }
                case 'No space left on the device': {
                    Message.error('キャプチャのアップロードに失敗しました。保存先フォルダに空き容量がありません。');
                    break;
                }
                case 'Unexpected error occurred while saving the file': {
                    Message.error('キャプチャのアップロードに失敗しました。保存中に予期しないエラーが発生しました。');
                    break;
                }
                default: {
                    if (Number.isNaN(response.status)) {
                        // HTTP リクエスト自体が失敗した場合はネットワークエラーの可能性が高い & 基本アップロードに失敗してはならないので、リトライする
                        if (response.error.code === AxiosError.ECONNABORTED) {
                            // ネットワーク接続エラーの場合
                            Message.warning('キャプチャのアップロード中にサーバーへの接続が切断されました。リトライします。');
                        } else if (response.error.code === AxiosError.ETIMEDOUT) {
                            // タイムアウトの場合
                            Message.warning('キャプチャのアップロード中にサーバーへの接続がタイムアウトしました。リトライします。');
                        } else if (response.error.code === AxiosError.ERR_NETWORK) {
                            // 予期しないネットワークエラーの場合
                            Message.warning('キャプチャのアップロード中に予期しないネットワークエラーが発生しました。リトライします。');
                        } else {
                            // それ以外のエラーの場合
                            Message.warning('キャプチャのアップロードに失敗しました。リトライします。');
                        }
                        await this.uploadCapture(blob, filename);
                    } else {
                        APIClient.showGenericError(response, 'キャプチャのアップロードに失敗しました。');
                    }
                    break;
                }
            }
        }
    }

    /**
     * キャプチャをサーバーから削除する
     * @param capture_name 削除するキャプチャのファイル名
     * @returns 成否
     */
    static async deleteCapture(capture_name: string): Promise<boolean> {
        const response = await APIClient.delete(`/captures/${capture_name}`);
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'キャプチャの削除に失敗しました。');
            return false;
        }
        return true;
    }
}

export { ICapture, Captures };
export default Captures;
