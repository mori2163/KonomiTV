import dayjs from 'dayjs';

import type { OfflineDownloadMetadata, OfflineDownloadProgressUpdate, OfflineSegmentDescriptor } from '@/offline/types';
import type { IRecordedProgram } from '@/services/Videos';

import Message from '@/message';
import OfflineStorage from '@/offline/storage';
import { serializeRecordedProgram } from '@/offline/types';
import APIClient from '@/services/APIClient';
import Videos from '@/services/Videos';
import useOfflineStore from '@/stores/OfflineStore';
import Utils from '@/utils';

interface PlaylistParseResult {
    targetDuration: number;
    cacheKey: string | null;
    segments: OfflineSegmentDescriptor[];
}

const OFFLINE_PLAYLIST_FILENAME = 'playlist.m3u8';
const OFFLINE_SEGMENT_PREFIX = 'segment-';
const OFFLINE_SEGMENT_EXTENSION = '.ts';

class OfflineDownloadManager {

    private static instance: OfflineDownloadManager | null = null;

    private activeDownloads: Map<string, AbortController> = new Map();

    private initialized = false;

    static getInstance(): OfflineDownloadManager {
        if (OfflineDownloadManager.instance === null) {
            OfflineDownloadManager.instance = new OfflineDownloadManager();
        }
        return OfflineDownloadManager.instance;
    }

    async initialize(): Promise<void> {
        if (this.initialized === true) {
            return;
        }
        const offlineStore = useOfflineStore();
        await offlineStore.initialize();
        if (offlineStore.initialization_error !== null) {
            throw new Error(offlineStore.initialization_error);
        }
        this.initialized = true;
    }

    // 録画番組のダウンロードを開始し、保存済みメタデータを返す
    async startDownload(recordedProgram: IRecordedProgram, options: {
        quality: string;
        isHevc: boolean;
        saveComments: boolean;
    }): Promise<OfflineDownloadMetadata> {
        await this.initialize();

        const offlineStore = useOfflineStore();
        if (offlineStore.storage_backend === null) {
            throw new Error('Offline storage backend is not available.');
        }

        const downloadId = crypto.randomUUID();
        const sessionId = crypto.randomUUID();
        const qualityPath = options.isHevc === true ? `${options.quality}-hevc` : options.quality;
        const now = new Date().toISOString();

        // 進捗管理とユーザーキャンセルに備えて AbortController を保持する
        const abortController = new AbortController();
        this.activeDownloads.set(downloadId, abortController);

        let metadata: OfflineDownloadMetadata = {
            id: downloadId,
            video_id: recordedProgram.id,
            quality: options.quality,
            is_hevc: options.isHevc,
            save_comments: options.saveComments,
            storage_backend: offlineStore.storage_backend,
            status: 'downloading',
            recorded_program: serializeRecordedProgram(recordedProgram),
            target_duration: 0,
            segment_count: 0,
            segments: [],
            total_size: 0,
            downloaded_bytes: 0,
            created_at: now,
            updated_at: now,
            playlist_path: OFFLINE_PLAYLIST_FILENAME,
            has_thumbnail: false,
        };

        await OfflineStorage.putMetadata(metadata);
        offlineStore.upsertDownload(metadata);

        // ダウンロード開始通知
        Message.info(`「${recordedProgram.title}」の保存を開始しました`);

        try {
            // HLS プレイリストを取得し、セグメント一覧とターゲット長を解析する（リトライ付き）
            const playlist = await this.fetchPlaylistWithRetry(recordedProgram.id, qualityPath, sessionId, abortController);
            const parsed = this.parsePlaylist(playlist);

            if (parsed.segments.length === 0) {
                throw new Error('Playlist does not contain any segments.');
            }

            // プレイリスト内のセグメント URL を、オフライン再生用の仮想パスに置き換える
            const offlinePlaylist = this.buildOfflinePlaylist(playlist, metadata.id, parsed.segments);

            metadata = {
                ...metadata,
                target_duration: parsed.targetDuration,
                segment_count: parsed.segments.length,
                segments: parsed.segments,
            };
            await OfflineStorage.updateMetadata(metadata.id, {
                target_duration: metadata.target_duration,
                segment_count: metadata.segment_count,
                segments: metadata.segments,
            });
            offlineStore.upsertDownload(metadata);

            await OfflineStorage.writePlaylist(metadata, offlinePlaylist);

            const progress: OfflineDownloadProgressUpdate = {
                id: metadata.id,
                downloaded_segments: 0,
                downloaded_bytes: 0,
                total_segments: metadata.segment_count,
                total_bytes_estimated: 0,  // 初期値は0で、ダウンロード中に更新される
                start_time: Date.now(),
            };
            offlineStore.setProgress(progress);

            const cacheKey = parsed.cacheKey;
            for (const segment of parsed.segments) {
                if (abortController.signal.aborted === true) {
                    throw new DOMException('Download aborted.', 'AbortError');
                }
                // 既に同一シーケンスのセグメントが保存済みならスキップ（レジューム対応）
                let segmentBuffer: ArrayBuffer | null = await OfflineStorage.readSegment(metadata, segment.sequence);
                if (segmentBuffer === null) {
                    // セグメントをサーバーから取得（リトライ付き）し、選択されたストレージバックエンドへ保存する
                    segmentBuffer = await this.fetchSegmentWithRetry(
                        recordedProgram.id,
                        qualityPath,
                        sessionId,
                        cacheKey,
                        segment.sequence,
                        abortController,
                    );
                    await OfflineStorage.writeSegment(metadata, segment.sequence, segmentBuffer);
                }

                // メタデータのダウンロード済みバイト数を更新
                metadata = {
                    ...metadata,
                    downloaded_bytes: metadata.downloaded_bytes + segmentBuffer.byteLength,
                    total_size: metadata.total_size + segmentBuffer.byteLength,
                    updated_at: new Date().toISOString(),
                };
                await OfflineStorage.updateMetadata(metadata.id, {
                    downloaded_bytes: metadata.downloaded_bytes,
                    total_size: metadata.total_size,
                });
                offlineStore.upsertDownload(metadata);

                progress.downloaded_segments += 1;
                progress.downloaded_bytes = metadata.downloaded_bytes;

                // 推定合計バイト数を計算 (平均セグメントサイズ × 総セグメント数)
                if (progress.downloaded_segments > 0) {
                    const averageSegmentSize = progress.downloaded_bytes / progress.downloaded_segments;
                    progress.total_bytes_estimated = Math.round(averageSegmentSize * progress.total_segments);
                }

                // 経過時間から推定残り時間を計算
                const elapsed = Date.now() - (progress.start_time || Date.now());
                const rate = progress.downloaded_segments / elapsed;
                const remainingSegments = progress.total_segments - progress.downloaded_segments;
                progress.estimated_remaining_time = remainingSegments > 0 ? Math.round(remainingSegments / rate) : 0;
                offlineStore.setProgress({...progress});
            }

            // コメントデータを取得して保存する
            if (options.saveComments === true) {
                console.log(`[OfflineDownloadManager] Attempting to save comments for video ${recordedProgram.id}`);
                try {
                    const jikkyo_comments = await Videos.fetchVideoJikkyoComments(recordedProgram.id);
                    console.log('[OfflineDownloadManager] Comment fetch result:', jikkyo_comments);
                    if (jikkyo_comments.is_success && jikkyo_comments.comments.length > 0) {
                        // recording_start_time を取得
                        // recorded_video.recording_start_time がない場合は番組の start_time を使用
                        const recording_start_time = recordedProgram.recorded_video?.recording_start_time ?? recordedProgram.start_time;
                        console.log('[OfflineDownloadManager] recording_start_time:', recording_start_time);
                        if (recording_start_time === null || recording_start_time === undefined) {
                            console.warn('[OfflineDownloadManager] recording_start_time is null or undefined, cannot calculate comment times.');
                        } else {
                            // DPlayer のコメント形式に変換して保存
                            // time: MM/DD HH:mm:ss 形式の時刻文字列（28時間表記対応）
                            // playback_position: 再生位置（秒）
                            const comments = jikkyo_comments.comments.map((comment) => ({
                                text: comment.text,
                                time: Utils.apply28HourClock(dayjs(recording_start_time).add(comment.time, 'seconds').format('MM/DD HH:mm:ss')),
                                playback_position: comment.time,
                                user_id: comment.author,
                            }));
                            await OfflineStorage.writeComments(metadata.id, comments);
                            console.log(`[OfflineDownloadManager] Saved ${comments.length} comments for download ${metadata.id}`);
                        }
                    } else {
                        console.log(`[OfflineDownloadManager] No comments available for video ${recordedProgram.id}`);
                    }
                } catch (error) {
                    // コメントの取得・保存に失敗してもダウンロード全体は失敗扱いにしない
                    console.warn('[OfflineDownloadManager] Failed to save comments, but continuing.', error);
                }
            }

            // サムネイル画像を取得して保存する
            try {
                const api_base_url = Utils.api_base_url;
                const thumbnail_url = `${api_base_url}/videos/${recordedProgram.recorded_video.id}/thumbnail`;
                const thumbnail_response = await fetch(thumbnail_url, { signal: abortController.signal });
                if (thumbnail_response.ok === true) {
                    const thumbnail_blob = await thumbnail_response.blob();
                    await OfflineStorage.writeThumbnail(metadata.id, thumbnail_blob);
                    metadata = {
                        ...metadata,
                        has_thumbnail: true,
                    };
                    await OfflineStorage.updateMetadata(metadata.id, { has_thumbnail: true });
                    offlineStore.upsertDownload(metadata);
                    console.log(`[OfflineDownloadManager] Saved thumbnail for download ${metadata.id}`);
                } else {
                    console.warn(`[OfflineDownloadManager] Failed to fetch thumbnail: ${thumbnail_response.status}`);
                }
            } catch (error) {
                // サムネイルの取得・保存に失敗してもダウンロード全体は失敗扱いにしない
                console.warn('[OfflineDownloadManager] Failed to save thumbnail, but continuing.', error);
            }

            metadata = {
                ...metadata,
                status: 'completed',
                updated_at: new Date().toISOString(),
            };
            await OfflineStorage.updateMetadata(metadata.id, {status: 'completed'});
            offlineStore.upsertDownload(metadata);
            offlineStore.clearProgress(metadata.id);

            // ダウンロード完了通知
            Message.success(`「${recordedProgram.title}」の保存が完了しました`);

            return metadata;

        } catch (error) {
            console.error('[OfflineDownloadManager] Failed to download offline content.', error);
            metadata = {
                ...metadata,
                status: abortController.signal.aborted ? 'paused' : 'error',
                updated_at: new Date().toISOString(),
            };
            await OfflineStorage.updateMetadata(metadata.id, {status: metadata.status});
            offlineStore.upsertDownload(metadata);

            // エラー通知（キャンセルの場合は通知しない）
            if (abortController.signal.aborted === false) {
                const errorMessage = error instanceof Error ? error.message : '不明なエラー';
                Message.error(`「${recordedProgram.title}」の保存に失敗しました: ${errorMessage}`);
            }

            throw error;
        } finally {
            this.activeDownloads.delete(downloadId);
        }
    }

    cancelDownload(id: string): void {
        const controller = this.activeDownloads.get(id);
        if (controller === undefined) {
            return;
        }
        controller.abort();
    }

    private async fetchPlaylist(videoId: number, qualityPath: string, sessionId: string, abortController: AbortController): Promise<string> {
        const response = await APIClient.get<string>(`/streams/video/${videoId}/${qualityPath}/playlist`, {
            params: {
                session_id: sessionId,
            },
            responseType: 'text',
            signal: abortController.signal,
            transformResponse: data => data,
        });
        if (response.type === 'error') {
            const message = this.getErrorMessage(response.data.detail, 'Failed to fetch playlist.');
            throw new Error(message);
        }
        return response.data;
    }

    // プレイリスト取得 (リトライ付き)
    private async fetchPlaylistWithRetry(
        videoId: number,
        qualityPath: string,
        sessionId: string,
        abortController: AbortController,
    ): Promise<string> {
        const attempt = async () => this.fetchPlaylist(videoId, qualityPath, sessionId, abortController);
        return await this.withRetry(attempt, 'playlist', abortController.signal);
    }

    private async fetchSegment(
        videoId: number,
        qualityPath: string,
        sessionId: string,
        cacheKey: string | null,
        sequence: number,
        abortController: AbortController,
    ): Promise<ArrayBuffer> {
        const response = await APIClient.get<ArrayBuffer>(`/streams/video/${videoId}/${qualityPath}/segment`, {
            params: {
                session_id: sessionId,
                sequence,
                cache_key: cacheKey ?? undefined,
            },
            responseType: 'arraybuffer',
            signal: abortController.signal,
        });
        if (response.type === 'error') {
            const message = this.getErrorMessage(response.data.detail, 'Failed to fetch segment.');
            throw new Error(message);
        }
        return response.data;
    }

    // セグメント取得 (リトライ付き)
    private async fetchSegmentWithRetry(
        videoId: number,
        qualityPath: string,
        sessionId: string,
        cacheKey: string | null,
        sequence: number,
        abortController: AbortController,
    ): Promise<ArrayBuffer> {
        const attempt = async () => this.fetchSegment(videoId, qualityPath, sessionId, cacheKey, sequence, abortController);
        return await this.withRetry(attempt, `segment#${sequence}`, abortController.signal);
    }

    // 共通: バックオフリトライ (0s -> 2s -> 5s -> 10s)
    private async withRetry<T>(fn: () => Promise<T>, label: string, signal: AbortSignal): Promise<T> {
        const delays = [0, 2000, 5000, 10000];
        let lastError: unknown = null;
        for (let i = 0; i < delays.length; i++) {
            if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
            const delay = delays[i];
            if (delay > 0) {
                await new Promise(resolve => setTimeout(resolve, delay));
                if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
            }
            try {
                const result = await fn();
                return result;
            } catch (error) {
                lastError = error;
                console.warn(`[OfflineDownloadManager] ${label} fetch failed (attempt ${i + 1}/${delays.length}).`, error);
            }
        }
        throw lastError instanceof Error ? lastError : new Error(`Failed to fetch ${label}.`);
    }

    private parsePlaylist(content: string): PlaylistParseResult {
        const lines = content.split('\n');
        const segments: OfflineSegmentDescriptor[] = [];
        let targetDuration = 0;
        let pendingDuration = 0;
        let cacheKey: string | null = null;

        for (const rawLine of lines) {
            const line = rawLine.trim();
            if (line.length === 0) {
                continue;
            }
            if (line.startsWith('#EXT-X-TARGETDURATION:')) {
                const value = line.split(':')[1];
                targetDuration = Number.parseInt(value, 10) || 0;
                continue;
            }
            if (line.startsWith('#EXTINF:')) {
                const durationPart = line.split(':')[1]?.split(',')[0];
                pendingDuration = Number.parseFloat(durationPart ?? '0');
                continue;
            }
            if (line.startsWith('segment?') === true) {
                const url = new URL(line, `${Utils.api_base_url}/`);
                const sequenceParam = url.searchParams.get('sequence');
                if (sequenceParam === null) {
                    throw new Error(`Playlist segment missing sequence parameter: ${line}`);
                }
                const descriptor: OfflineSegmentDescriptor = {
                    sequence: Number.parseInt(sequenceParam, 10),
                    duration: pendingDuration,
                };
                segments.push(descriptor);
                pendingDuration = 0;
                if (cacheKey === null) {
                    cacheKey = url.searchParams.get('cache_key');
                }
                continue;
            }
        }

        return {
            targetDuration,
            cacheKey,
            segments,
        };
    }

    private buildOfflinePlaylist(original: string, downloadId: string, segments: OfflineSegmentDescriptor[]): string {
        const lines = original.split('\n');
        const rewritten: string[] = [];
        let segmentIndex = 0;
        for (const rawLine of lines) {
            if (rawLine.trim().startsWith('segment?') === true) {
                if (segmentIndex >= segments.length) {
                    throw new Error(`Playlist mismatch: more segment lines (${segmentIndex + 1}) than parsed segments (${segments.length})`);
                }
                const descriptor = segments[segmentIndex];
                const filename = `${OFFLINE_SEGMENT_PREFIX}${descriptor.sequence.toString().padStart(8, '0')}${OFFLINE_SEGMENT_EXTENSION}`;
                rewritten.push(`/offline/streams/${downloadId}/segments/${filename}`);
                segmentIndex += 1;
            } else {
                rewritten.push(rawLine);
            }
        }
        return rewritten.join('\n');
    }

    private getErrorMessage(detail: unknown, fallback: string): string {
        if (typeof detail === 'string') {
            return detail;
        }
        if (Array.isArray(detail) === true && detail.length > 0) {
            const first = detail[0] as {msg?: string} | undefined;
            if (first !== undefined && typeof first.msg === 'string') {
                return first.msg;
            }
        }
        return fallback;
    }
}

export default OfflineDownloadManager.getInstance();
