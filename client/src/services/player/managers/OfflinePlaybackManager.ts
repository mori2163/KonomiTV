
import OfflineStorageService from '@/services/OfflineStorageService';


/** オフライン再生時に PlayerController へ渡すオプション */
export interface IOfflinePlaybackOptions {
    video_id: number;
    api_quality: string;
    playlist_url: string;
    hls_config: {
        fLoader: any;
        pLoader: any;
    };
}

interface IHLSLoaderContext {
    url: string;
    frag?: {
        sn?: number;
    };
}

interface IHLSLoaderStats {
    aborted: boolean;
    loaded: number;
    retry: number;
    total: number;
    chunkCount: number;
    bwEstimate: number;
    loading: {
        start: number;
        first: number;
        end: number;
    };
    parsing: {
        start: number;
        end: number;
    };
    buffering: {
        start: number;
        first: number;
        end: number;
    };
}

const createLoaderStats = (started_at: number = performance.now()): IHLSLoaderStats => {
    return {
        aborted: false,
        loaded: 0,
        retry: 0,
        total: 0,
        chunkCount: 0,
        bwEstimate: 0,
        loading: {
            start: started_at,
            first: started_at,
            end: started_at,
        },
        parsing: {
            start: started_at,
            end: started_at,
        },
        buffering: {
            start: started_at,
            first: started_at,
            end: started_at,
        },
    };
};


/**
 * オフライン再生に必要な hls.js Loader 設定を生成するマネージャー
 */
class OfflinePlaybackManager {

    /**
     * オフライン再生オプションを生成する
     * @param video_id 録画番組 ID
     * @param api_quality API の画質 ID
     * @returns オフライン再生オプション
     */
    static createOptions(video_id: number, api_quality: string): IOfflinePlaybackOptions {
        return {
            video_id: video_id,
            api_quality: api_quality,
            playlist_url: `offline://videos/${video_id}/playlist.m3u8`,
            hls_config: {
                fLoader: this.createFragmentLoader(video_id),
                pLoader: this.createPlaylistLoader(video_id),
            },
        };
    }


    /**
     * hls.js の Playlist Loader を生成する
     * @param video_id 録画番組 ID
     * @returns Loader クラス
     */
    private static createPlaylistLoader(video_id: number): any {
        return class OfflinePlaylistLoader {

            public context: IHLSLoaderContext | null = null;
            public stats: IHLSLoaderStats = createLoaderStats();
            private aborted: boolean = false;

            constructor(config: any) {
                // 何もしない
            }

            async load(context: IHLSLoaderContext, config: any, callbacks: any): Promise<void> {
                this.aborted = false;
                this.context = context;
                const started_at = performance.now();
                this.stats = createLoaderStats(started_at);
                try {
                    const playlist_text = await OfflineStorageService.readPlaylist(video_id);
                    if (this.isAborted() === true) {
                        this.stats.aborted = true;
                        return;
                    }

                    const completed_at = performance.now();
                    // playlist_text.length は UTF-16 コード単位数であるため、正確なバイト数は TextEncoder で計算する
                    const playlist_byte_length = new TextEncoder().encode(playlist_text).length;
                    this.stats.loaded = playlist_byte_length;
                    this.stats.total = playlist_byte_length;
                    this.stats.chunkCount = 1;
                    this.stats.loading.end = completed_at;
                    this.stats.parsing.start = completed_at;
                    this.stats.parsing.end = completed_at;
                    this.stats.buffering.start = completed_at;
                    this.stats.buffering.first = completed_at;
                    this.stats.buffering.end = completed_at;
                    callbacks.onSuccess({
                        data: playlist_text,
                        url: context.url,
                    }, this.stats, context, null);
                } catch (error) {
                    const failed_at = performance.now();
                    this.stats.loading.end = failed_at;
                    this.stats.parsing.end = failed_at;
                    this.stats.buffering.end = failed_at;
                    callbacks.onError({
                        code: 0,
                        text: error instanceof Error ? error.message : 'Failed to load offline playlist.',
                    }, context, null, this.stats);
                }
            }

            abort(): void {
                this.aborted = true;
                this.stats.aborted = true;
            }

            destroy(): void {
                this.aborted = true;
                this.stats.aborted = true;
                this.context = null;
            }

            private isAborted(): boolean {
                return this.aborted;
            }
        };
    }


    /**
     * hls.js の Fragment Loader を生成する
     * @param video_id 録画番組 ID
     * @returns Loader クラス
     */
    private static createFragmentLoader(video_id: number): any {
        return class OfflineFragmentLoader {

            public context: IHLSLoaderContext | null = null;
            public stats: IHLSLoaderStats = createLoaderStats();
            private aborted: boolean = false;

            constructor(config: any) {
                // 何もしない
            }

            async load(context: IHLSLoaderContext, config: any, callbacks: any): Promise<void> {
                this.aborted = false;
                this.context = context;
                const started_at = performance.now();
                this.stats = createLoaderStats(started_at);
                try {
                    const sequence = this.extractSequenceFromContext(context);
                    const segment_data = await OfflineStorageService.readSegment(video_id, sequence);
                    if (this.isAborted() === true) {
                        this.stats.aborted = true;
                        return;
                    }

                    const completed_at = performance.now();
                    this.stats.loaded = segment_data.byteLength;
                    this.stats.total = segment_data.byteLength;
                    this.stats.chunkCount = 1;
                    this.stats.loading.end = completed_at;
                    this.stats.parsing.start = completed_at;
                    this.stats.parsing.end = completed_at;
                    this.stats.buffering.start = completed_at;
                    this.stats.buffering.first = completed_at;
                    this.stats.buffering.end = completed_at;
                    callbacks.onSuccess({
                        data: segment_data,
                        url: context.url,
                    }, this.stats, context, null);
                } catch (error) {
                    const failed_at = performance.now();
                    this.stats.loading.end = failed_at;
                    this.stats.parsing.end = failed_at;
                    this.stats.buffering.end = failed_at;
                    callbacks.onError({
                        code: 0,
                        text: error instanceof Error ? error.message : 'Failed to load offline segment.',
                    }, context, null, this.stats);
                }
            }

            abort(): void {
                this.aborted = true;
                this.stats.aborted = true;
            }

            destroy(): void {
                this.aborted = true;
                this.stats.aborted = true;
                this.context = null;
            }

            private isAborted(): boolean {
                return this.aborted;
            }

            /**
             * hls.js の Context からセグメント番号を抽出する
             * @param context hls.js の Loader Context
             * @returns セグメント番号
             */
            private extractSequenceFromContext(context: IHLSLoaderContext): number {
                if (typeof context.frag?.sn === 'number' && context.frag.sn >= 0) {
                    return context.frag.sn;
                }

                const segment_match = context.url.match(/\/(\d+)\.ts(?:$|\?)/);
                if (segment_match !== null) {
                    const parsed = parseInt(segment_match[1], 10);
                    if (Number.isFinite(parsed) && parsed >= 0) {
                        return parsed;
                    }
                    console.warn(`[OfflineFragmentLoader] Invalid segment number in URL: ${context.url}, raw value: ${segment_match[1]}`);
                }

                const url = new URL(context.url, 'https://dummy.local');
                const sequence = url.searchParams.get('sequence');
                if (sequence !== null) {
                    const parsed = parseInt(sequence, 10);
                    if (Number.isFinite(parsed) && parsed >= 0) {
                        return parsed;
                    }
                    console.warn(`[OfflineFragmentLoader] Invalid sequence parameter in URL: ${context.url}, raw value: ${sequence}`);
                }

                throw new Error(`Failed to parse segment sequence from fragment URL: ${context.url}`);
            }
        };
    }
}

export default OfflinePlaybackManager;
