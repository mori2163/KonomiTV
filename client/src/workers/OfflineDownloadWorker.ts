
import * as Comlink from 'comlink';

import OfflineStorageService from '@/services/OfflineStorageService';
import Utils from '@/utils';


/** オフラインダウンロード時に Worker へ渡す設定 */
export interface IOfflineDownloadOptions {
    video_id: number;
    quality: string;
    include_comments: boolean;
    start_sequence: number;
    initial_downloaded_segments: number;
    initial_total_size: number;
    access_token: string | null;
}

/** Worker からメインスレッドへ通知する進捗情報 */
export interface IOfflineDownloadProgress {
    video_id: number;
    total_segments: number;
    downloaded_segments: number;
    total_size: number;
}

/** Worker からメインスレッドへ通知するコールバック */
export interface IOfflineDownloadCallbacks {
    onProgress(progress: IOfflineDownloadProgress): Promise<void> | void;
    onCompleted(result: IOfflineDownloadProgress): Promise<void> | void;
    onError(error_message: string): Promise<void> | void;
}

/** OfflineDownloadWorker が提供する API */
export interface IOfflineDownloadWorker {
    download(options: IOfflineDownloadOptions, callbacks: IOfflineDownloadCallbacks): Promise<void>;
    cancel(): Promise<void>;
}

/** OfflineDownloadWorker のコンストラクタ型 */
export interface IOfflineDownloadWorkerConstructor {
    new (): IOfflineDownloadWorker;
}


/**
 * オフライン保存のために HLS セグメントを順次ダウンロードする Worker
 */
class OfflineDownloadWorker implements IOfflineDownloadWorker {

    private abort_controller: AbortController | null = null;
    private keep_alive_timer_id: number | null = null;


    /**
     * ダウンロードを開始する
     * @param options ダウンロード設定
     * @param callbacks 進捗通知コールバック
     */
    public async download(options: IOfflineDownloadOptions, callbacks: IOfflineDownloadCallbacks): Promise<void> {
        this.abort_controller = new AbortController();

        const request_headers = this.createRequestHeaders(options.access_token);
        const stream_base_url = `${Utils.api_base_url}/streams/video/${options.video_id}/${options.quality}`;
        const session_id = crypto.randomUUID().split('-')[0];

        let downloaded_segments = options.initial_downloaded_segments;
        let total_size = options.initial_total_size;
        let total_segments = 0;

        try {
            // 最初にプレイリストを取得して総セグメント数を確定する
            const playlist_response = await this.fetchWithRetry(
                `${stream_base_url}/playlist?session_id=${session_id}`,
                {
                    method: 'GET',
                    headers: request_headers,
                },
                3,
                10,
            );
            const playlist_text = await playlist_response.text();
            const segment_urls = this.extractSegmentURLs(stream_base_url, playlist_text);
            total_segments = segment_urls.length;
            const start_sequence = Math.min(options.start_sequence, total_segments);
            downloaded_segments = Math.min(downloaded_segments, start_sequence);
            await OfflineStorageService.writePlaylist(options.video_id, playlist_text);

            // 進捗の初期値を通知
            await callbacks.onProgress({
                video_id: options.video_id,
                total_segments: total_segments,
                downloaded_segments: downloaded_segments,
                total_size: total_size,
            });

            // ダウンロード中はセッションを維持する
            this.startKeepAlive(stream_base_url, session_id, request_headers);

            // セグメントを先頭から順次取得する
            for (let segment_index = start_sequence; segment_index < total_segments; segment_index++) {
                this.ensureNotCanceled();
                const segment_url = segment_urls[segment_index];
                const sequence = this.extractSequenceFromSegmentURL(segment_url, segment_index);

                const segment_response = await this.fetchWithRetry(
                    segment_url,
                    {
                        method: 'GET',
                        headers: request_headers,
                    },
                    5,
                    10,
                );
                const segment_data = await segment_response.arrayBuffer();
                await OfflineStorageService.writeSegment(options.video_id, sequence, segment_data);

                downloaded_segments++;
                total_size += segment_data.byteLength;

                await callbacks.onProgress({
                    video_id: options.video_id,
                    total_segments: total_segments,
                    downloaded_segments: downloaded_segments,
                    total_size: total_size,
                });
            }

            // コメント保存が有効ならコメントを保存
            if (options.include_comments === true) {
                const comments_response = await this.fetchWithRetry(
                    `${Utils.api_base_url}/videos/${options.video_id}/jikkyo`,
                    {
                        method: 'GET',
                        headers: request_headers,
                    },
                    3,
                    10,
                );
                const comments = await comments_response.json();
                await OfflineStorageService.writeComments(options.video_id, comments);
            }

            // サムネイルを保存
            const thumbnail_response = await this.fetchWithRetry(
                `${Utils.api_base_url}/videos/${options.video_id}/thumbnail`,
                {
                    method: 'GET',
                    headers: request_headers,
                },
                3,
                10,
            );
            const thumbnail_blob = await thumbnail_response.blob();
            await OfflineStorageService.writeThumbnail(options.video_id, thumbnail_blob);

            await callbacks.onCompleted({
                video_id: options.video_id,
                total_segments: total_segments,
                downloaded_segments: downloaded_segments,
                total_size: total_size,
            });
        } catch (error) {
            const error_message = this.toErrorMessage(error);
            if (error_message !== 'Download canceled.') {
                await callbacks.onError(error_message);
            }
            throw error;
        } finally {
            this.stopKeepAlive();
        }
    }


    /**
     * 進行中ダウンロードを中断する
     */
    public async cancel(): Promise<void> {
        if (this.abort_controller !== null && this.abort_controller.signal.aborted === false) {
            this.abort_controller.abort();
        }
    }


    /**
     * 認証情報付きのリクエストヘッダーを生成する
     * @param access_token アクセストークン
     * @returns リクエストヘッダー
     */
    private createRequestHeaders(access_token: string | null): Headers {
        const headers = new Headers();
        if (access_token !== null) {
            headers.set('Authorization', `Bearer ${access_token}`);
        }
        headers.set('X-KonomiTV-Version', Utils.version);
        return headers;
    }


    /**
     * プレイリストからセグメント URL 一覧を抽出する
     * プレイリストに含まれる URL をそのまま利用することで、cache_key など必須クエリの抜け漏れを防ぐ
     * @param stream_base_url ストリーミング API のベース URL
     * @param playlist_text プレイリスト
     * @returns セグメント URL 一覧
     */
    private extractSegmentURLs(stream_base_url: string, playlist_text: string): string[] {
        const segment_urls = playlist_text
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line !== '' && line.startsWith('#') === false && line.includes('segment?'))
            .map((line) => new URL(line, `${stream_base_url}/`).toString());

        if (segment_urls.length > 0) {
            return segment_urls;
        }

        throw new Error('Failed to parse segment URLs from playlist.');
    }


    /**
     * セグメント URL から sequence を抽出する
     * @param segment_url セグメント URL
     * @param fallback_sequence 抽出できなかった場合のフォールバック値
     * @returns sequence
     */
    private extractSequenceFromSegmentURL(segment_url: string, fallback_sequence: number): number {
        const url = new URL(segment_url);
        const sequence = url.searchParams.get('sequence');
        if (sequence !== null) {
            const parsed_sequence = Number(sequence);
            if (Number.isInteger(parsed_sequence) && parsed_sequence >= 0) {
                return parsed_sequence;
            }
        }
        return fallback_sequence;
    }


    /**
     * keep-alive タイマーを開始する
     * @param stream_base_url ストリーミング API のベース URL
     * @param session_id セッション ID
     * @param request_headers リクエストヘッダー
     */
    private startKeepAlive(stream_base_url: string, session_id: string, request_headers: Headers): void {
        this.stopKeepAlive();
        this.keep_alive_timer_id = self.setInterval(() => {
            // keep-alive の失敗は次回以降で回復できる可能性があるため、ここでは例外を握りつぶす
            fetch(`${stream_base_url}/keep-alive?session_id=${session_id}`, {
                method: 'PUT',
                headers: request_headers,
            }).catch(() => {
                // 何もしない
            });
        }, 5 * 1000);
    }


    /**
     * keep-alive タイマーを停止する
     */
    private stopKeepAlive(): void {
        if (this.keep_alive_timer_id !== null) {
            clearInterval(this.keep_alive_timer_id);
            this.keep_alive_timer_id = null;
        }
    }


    /**
     * キャンセル済みなら例外を送出する
     */
    private ensureNotCanceled(): void {
        if (this.abort_controller !== null && this.abort_controller.signal.aborted === true) {
            throw new Error('Download canceled.');
        }
    }


    /**
     * リトライ付きで fetch を実行する
     * @param url URL
     * @param request_init fetch のオプション
     * @param max_retries 最大リトライ回数
     * @param retry_interval_seconds リトライ間隔 (秒)
     * @returns fetch レスポンス
     */
    private async fetchWithRetry(
        url: string,
        request_init: RequestInit,
        max_retries: number,
        retry_interval_seconds: number,
    ): Promise<Response> {
        let last_error: unknown = null;

        for (let retry_count = 0; retry_count <= max_retries; retry_count++) {
            this.ensureNotCanceled();

            try {
                const response = await fetch(url, {
                    ...request_init,
                    signal: this.abort_controller?.signal,
                });
                if (response.ok === true) {
                    return response;
                }
                throw new Error(`HTTP Error ${response.status}`);
            } catch (error) {
                last_error = error;

                // キャンセルされた場合は即時終了
                if (error instanceof DOMException && error.name === 'AbortError') {
                    throw new Error('Download canceled.');
                }

                // 最終リトライでなければ待ってから再試行
                if (retry_count < max_retries) {
                    await Utils.sleep(retry_interval_seconds);
                    continue;
                }
            }
        }

        throw last_error ?? new Error('Failed to fetch resource.');
    }


    /**
     * 例外を UI 向けメッセージへ変換する
     * @param error 例外
     * @returns エラーメッセージ
     */
    private toErrorMessage(error: unknown): string {
        if (error instanceof Error) {
            return error.message;
        }
        return 'Unknown error';
    }
}

Comlink.expose(OfflineDownloadWorker);
