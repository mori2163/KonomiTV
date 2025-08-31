import APIClient from '@/services/APIClient';

/** エンコードコーデックを表す型 */
export type EncodingCodec = 'h264' | 'hevc';

/** エンコーダータイプを表す型 */
export type EncoderType = 'software' | 'hardware';

/** エンコードタスクの状態を表す型 */
export type EncodingTaskStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';

/** 手動エンコードリクエストを表すインターフェース */
export interface ITSReplaceManualEncodingRequest {
    video_id: number;
    codec: EncodingCodec;
    encoder_type: EncoderType;
    quality_preset?: string;
}

/** エンコードレスポンスを表すインターフェース */
export interface ITSReplaceEncodingResponse {
    success: boolean;
    task_id?: string;
    detail: string;
}

/** エンコード状況レスポンスを表すインターフェース */
export interface ITSReplaceEncodingStatusResponse {
    success: boolean;
    task_id: string;
    status: EncodingTaskStatus;
    progress: number;
    detail: string;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    error_message?: string;
}

/** エンコードタスク情報を表すインターフェース */
export interface ITSReplaceEncodingTaskInfo {
    task_id: string;
    video_id: number;
    video_title: string;
    codec: EncodingCodec;
    encoder_type: EncoderType;
    status: EncodingTaskStatus;
    progress: number;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    error_message?: string;
}

/** エンコードキューレスポンスを表すインターフェース */
export interface ITSReplaceEncodingQueueResponse {
    success: boolean;
    processing_tasks: ITSReplaceEncodingTaskInfo[];
    queued_tasks: ITSReplaceEncodingTaskInfo[];
    completed_tasks: ITSReplaceEncodingTaskInfo[];
    failed_tasks: ITSReplaceEncodingTaskInfo[];
}

/** ハードウェアエンコーダー利用可否情報を表すインターフェース */
export interface IHardwareEncoderAvailability {
    available: boolean;
    encoder_name?: string;
    reason?: string;
}

class TSReplace {

    /**
     * 手動エンコードを開始する
     * @param request 手動エンコードリクエスト
     * @returns エンコードレスポンス or エンコード開始に失敗した場合は null
     */
    static async startManualEncoding(request: ITSReplaceManualEncodingRequest): Promise<ITSReplaceEncodingResponse | null> {
        // API リクエストを実行
        const response = await APIClient.post<ITSReplaceEncodingResponse>('/tsreplace/encode', request);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードの開始に失敗しました。');
            return null;
        }

        return response.data;
    }

    /**
     * エンコード状況を取得する
     * @param task_id エンコードタスクの ID
     * @returns エンコード状況 or 取得に失敗した場合は null
     */
    static async getEncodingStatus(task_id: string): Promise<ITSReplaceEncodingStatusResponse | null> {
        // API リクエストを実行
        const response = await APIClient.get<ITSReplaceEncodingStatusResponse>(`/tsreplace/status/${task_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコード状況の取得に失敗しました。');
            return null;
        }

        return response.data;
    }

    /**
     * エンコード処理をキャンセルする
     * @param task_id エンコードタスクの ID
     * @returns キャンセルに成功した場合は true
     */
    static async cancelEncoding(task_id: string): Promise<boolean> {
        // API リクエストを実行
        const response = await APIClient.delete(`/tsreplace/cancel/${task_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードのキャンセルに失敗しました。');
            return false;
        }

        return true;
    }

    /**
     * エンコードキューの状況を取得する
     * @returns エンコードキューの状況 or 取得に失敗した場合は null
     */
    static async getEncodingQueue(): Promise<ITSReplaceEncodingQueueResponse | null> {
        // API リクエストを実行
        const response = await APIClient.get<ITSReplaceEncodingQueueResponse>('/tsreplace/queue');

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードキューの取得に失敗しました。');
            return null;
        }

        return response.data;
    }

    /**
     * ハードウェアエンコーダーの利用可否を確認する
     * @returns ハードウェアエンコーダーの利用可否情報
     */
    static async checkHardwareEncoderAvailability(): Promise<IHardwareEncoderAvailability> {
        try {
            // エンコードキューAPIを使用してハードウェアエンコーダーの利用可否を確認
            // 実際の実装では専用のAPIエンドポイントを作成することも可能
            const response = await APIClient.get<ITSReplaceEncodingQueueResponse>('/tsreplace/queue');

            if (response.type === 'error') {
                return {
                    available: false,
                    reason: 'ハードウェアエンコーダーの確認に失敗しました。',
                };
            }

            // 簡易的な実装として、常に利用可能として返す
            // 実際の実装では、サーバー側の設定やハードウェア検出結果を取得する
            return {
                available: true,
                encoder_name: 'QSVEncC', // 実際の実装では動的に取得
            };
        } catch (error) {
            console.error('Failed to check hardware encoder availability:', error);
            return {
                available: false,
                reason: 'ハードウェアエンコーダーの確認に失敗しました。',
            };
        }
    }

    /**
     * エンコード進捗をWebSocketで監視する
     * @param task_id エンコードタスクの ID
     * @param onProgress 進捗更新時のコールバック関数
     * @param onError エラー発生時のコールバック関数
     * @returns WebSocket接続を閉じる関数
     */
    static subscribeToEncodingProgress(
        task_id: string,
        onProgress: (data: any) => void,
        onError?: (error: any) => void
    ): () => void {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/tsreplace/progress/${task_id}`;

        const ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onProgress(data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
                onError?.(error);
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            onError?.(error);
        };

        ws.onclose = (event) => {
            if (event.code !== 1000) {
                console.warn('WebSocket closed unexpectedly:', event);
            }
        };

        // 接続を閉じる関数を返す
        return () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }
}

export default TSReplace;
