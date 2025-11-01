
import APIClient from '@/services/APIClient';


/**
 * ついで録画機能の API クライアント
 */
class LiveStreams {

    /**
     * ついで録画を開始する
     * @param display_channel_id チャンネル ID
     * @param quality 映像の品質
     * @returns 成功したかどうかとメッセージ
     */
    static async startRecording(display_channel_id: string, quality: string): Promise<{ status: string; message: string }> {
        const response = await APIClient.post(`/streams/live/${display_channel_id}/${quality}/recording/start`);
        return response.data;
    }


    /**
     * ついで録画を停止する
     * @param display_channel_id チャンネル ID
     * @param quality 映像の品質
     * @returns 成功したかどうかとメッセージ
     */
    static async stopRecording(display_channel_id: string, quality: string): Promise<{ status: string; message: string }> {
        const response = await APIClient.post(`/streams/live/${display_channel_id}/${quality}/recording/stop`);
        return response.data;
    }
}


export default LiveStreams;
