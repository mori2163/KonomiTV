import Hls from 'hls.js';

import type { OfflineDownloadMetadata } from '@/offline/types';

import OfflineStorage from '@/offline/storage';

// hls.js Loader 実装: /offline/streams/... を OfflineStorage から読み出して返す
// それ以外の URL はデフォルトの FetchLoader にフォールバックする
export default class HlsOfflineLoader {

    private readonly delegate: any | null;
    private aborted = false;
    private stats = HlsOfflineLoader.createEmptyStats();

    constructor(config: any) {
        // フォールバック用のデフォルトローダー
        // @ts-ignore - FetchLoader は存在するが型が公開されていない場合がある
        const FetchLoader = (Hls as any).DefaultConfig.loader as { new(config: any): any };
        this.delegate = FetchLoader ? new FetchLoader(config) : null;
    }

    destroy(): void {
        if (this.delegate) this.delegate.destroy();
        // no-op
    }

    abort(context: any): void {
        this.aborted = true;
        if (this.delegate) this.delegate.abort(context);
    }

    async load(context: any, config: any, callbacks: any): Promise<void> {
        const url = context.url;
        this.aborted = false;
        this.stats = HlsOfflineLoader.createEmptyStats();
        const stats = this.stats;
        stats.loading.start = performance.now();
        context.stats = stats;
        try {
            const offline = this.parseOfflineUrl(url);
            if (offline !== null) {
                console.log('[HlsOfflineLoader] Handling offline request:', {
                    url,
                    downloadId: offline.downloadId,
                    kind: offline.kind,
                    sequence: offline.kind === 'segment' ? offline.sequence : undefined,
                    responseType: context.responseType,
                });
                // メタデータを取得
                const meta: OfflineDownloadMetadata | undefined = await OfflineStorage.getMetadata(offline.downloadId);
                if (meta === undefined) {
                    throw new Error(`Offline metadata not found: ${offline.downloadId}`);
                }

                if (offline.kind === 'playlist') {
                    const content = meta ? await OfflineStorage.readPlaylist(meta) : null;
                    if (content === null) {
                        throw new Error('Offline playlist not found.');
                    }
                    if (this.aborted) return;
                    const loaded = content.length;
                    stats.loading.first = performance.now();
                    stats.loading.end = stats.loading.first;
                    stats.loaded = loaded;
                    stats.total = loaded;
                    callbacks.onSuccess({
                        url,
                        data: content,
                        networkDetails: null,
                    }, stats, context, null);
                    console.log('[HlsOfflineLoader] Served offline playlist:', offline.downloadId, 'bytes:', loaded);
                    return;
                }

                if (offline.kind === 'segment') {
                    const buffer = meta ? await OfflineStorage.readSegment(meta, offline.sequence) : null;
                    if (buffer === null) {
                        throw new Error(`Offline segment not found: ${offline.sequence}`);
                    }
                    if (this.aborted) return;
                    const loaded = buffer.byteLength;
                    stats.loading.first = performance.now();
                    stats.loading.end = stats.loading.first;
                    stats.loaded = loaded;
                    stats.total = loaded;
                    callbacks.onSuccess({
                        url,
                        data: buffer,
                        networkDetails: null,
                    }, stats, context, null);
                    console.log('[HlsOfflineLoader] Served offline segment:', offline.downloadId, 'sequence:', offline.sequence, 'bytes:', loaded);
                    return;
                }
            }
            // オフライン URL でなければフォールバック
            if (this.delegate) {
                this.delegate.load(context, config, callbacks);
                return;
            }
            throw new Error('No delegate loader available.');
        } catch (error) {
            if (this.aborted) {
                callbacks.onTimeout?.(context, null);
                return;
            }
            stats.loading.end = performance.now();
            callbacks.onError({
                code: 0,
                text: (error as Error).message,
                type: context.type,
                url: context.url,
                details: undefined,
                fatal: true,
                response: undefined,
            } as any, context, null);
            console.error('[HlsOfflineLoader] Failed to handle request:', url, error);
        }
    }

    private static createEmptyStats() {
        return {
            aborted: false,
            loaded: 0,
            retry: 0,
            total: 0,
            chunkCount: 0,
            bwEstimate: 0,
            loading: {
                start: 0,
                first: 0,
                end: 0,
            },
            parsing: {
                start: 0,
                end: 0,
            },
            buffering: {
                start: 0,
                end: 0,
            },
        };
    }

    private parseOfflineUrl(rawUrl: string): { downloadId: string; kind: 'playlist' | 'segment'; sequence: number } | { downloadId: string; kind: 'playlist'; sequence?: undefined } | null {
        let pathname = rawUrl;
        try {
            const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
            const resolved = new URL(rawUrl, base);
            pathname = resolved.pathname;
        } catch (error) {
            if (!rawUrl.startsWith('/')) {
                pathname = `/${rawUrl}`;
            }
        }

        const parts = pathname.split('/').filter(Boolean);
        if (parts.length < 3 || parts[0] !== 'offline' || parts[1] !== 'streams') {
            return null;
        }
        const downloadId = parts[2];
        if (!downloadId) {
            return null;
        }

        if (parts.length === 4 && parts[3].startsWith('playlist.m3u8')) {
            return { downloadId, kind: 'playlist' };
        }

        const segmentsIndex = parts.indexOf('segments');
        if (segmentsIndex !== -1 && parts.length > segmentsIndex + 1) {
            const filename = parts[segmentsIndex + 1];
            const match = filename.match(/segment-(\d{8})\.ts$/);
            if (!match) {
                throw new Error(`Invalid offline segment filename: ${filename}`);
            }
            const sequence = Number.parseInt(match[1], 10);
            return { downloadId, kind: 'segment', sequence };
        }

        return null;
    }
}
