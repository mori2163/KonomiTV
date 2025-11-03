import Hls from 'hls.js';

import type { OfflineDownloadMetadata } from '@/offline/types';

import { PlaybackState, PlaybackStateManager } from '@/offline/PlaybackStateManager';
import OfflineStorage from '@/offline/storage';
import HlsOfflineLoader from '@/services/player/offline/HlsOfflineLoader';

/**
 * オフライン専用の軽量プレイヤーコントローラー
 * 既存の PlayerController とは独立に、<video> 要素 + hls.js でオフライン HLS を再生する簡易コントローラ
 */
export class OfflinePlaybackController {

    private readonly stateManager: PlaybackStateManager;
    private readonly videoElement: HTMLVideoElement;
    private hls: Hls | null = null;

    constructor(videoElement: HTMLVideoElement) {
        this.stateManager = new PlaybackStateManager();
        this.videoElement = videoElement;
        this.setupEventListeners();
    }

    /**
     * 現在の再生状態を取得
     */
    get state(): PlaybackState {
        return this.stateManager.getState();
    }

    /**
     * 状態変更リスナーを登録
     */
    addStateListener(cb: (state: PlaybackState) => void): () => void {
        return this.stateManager.addListener(cb);
    }

    /**
     * オフライン動画を初期化
     * @param videoId 便宜上の引数名。オフライン保存では downloadId (string) を用いるため、内部で string 化して扱う。
     * @param quality オフラインでは単一画質のみ保存される想定のため、URL 生成には使わない（互換のため一応受け取る）。
     */
    async initialize(videoId: number | string, quality: string): Promise<void> {
        try {
            this.stateManager.setState(PlaybackState.INITIALIZING);

            // downloadId を文字列として扱う
            const downloadId = String(videoId);

            // メタデータ確認
            const metadata = await this.loadMetadata(downloadId);
            if (!metadata) {
                throw new Error('Offline metadata not found');
            }

            // プレイリスト存在確認
            this.stateManager.setState(PlaybackState.LOADING_PLAYLIST);
            const playlist = await OfflineStorage.readPlaylist(metadata);
            if (playlist === null) {
                throw new Error('Offline playlist not found');
            }

            // プレイヤー初期化
            const playlistUrl = this.buildOfflinePlaylistUrl(downloadId);
            await this.initializePlayer(playlistUrl);

            this.stateManager.setState(PlaybackState.READY);
        } catch (error) {
            console.error('[OfflinePlayback] Initialization failed:', error);
            this.stateManager.setState(PlaybackState.ERROR);
            throw error;
        }
    }

    /** 再生開始 */
    async play(): Promise<void> {
        const s = this.stateManager.getState();
        if (s !== PlaybackState.READY && s !== PlaybackState.PAUSED) {
            console.warn('[OfflinePlayback] Cannot play in current state');
            return;
        }
        try {
            await this.videoElement.play();
            this.stateManager.setState(PlaybackState.PLAYING);
        } catch (error) {
            console.error('[OfflinePlayback] Play failed:', error);
            this.stateManager.setState(PlaybackState.ERROR);
        }
    }

    /** 一時停止 */
    pause(): void {
        if (this.stateManager.getState() !== PlaybackState.PLAYING) return;
        this.videoElement.pause();
        this.stateManager.setState(PlaybackState.PAUSED);
    }

    /** シーク */
    seek(time: number): void {
        this.stateManager.setState(PlaybackState.SEEKING);
        this.videoElement.currentTime = time;
    }

    /** イベントリスナー設定（<video> 側） */
    private setupEventListeners(): void {
        // 再生開始
        this.videoElement.addEventListener('play', () => {
            const s = this.stateManager.getState();
            if (s === PlaybackState.READY || s === PlaybackState.PAUSED) {
                this.stateManager.setState(PlaybackState.PLAYING);
            }
        });
        // 一時停止
        this.videoElement.addEventListener('pause', () => {
            if (this.stateManager.getState() === PlaybackState.PLAYING) {
                this.stateManager.setState(PlaybackState.PAUSED);
            }
        });
        // シーク完了
        this.videoElement.addEventListener('seeked', () => {
            if (this.stateManager.getState() === PlaybackState.SEEKING) {
                this.stateManager.setState(PlaybackState.PLAYING);
            }
        });
        // バッファリング
        this.videoElement.addEventListener('waiting', () => {
            if (this.stateManager.getState() === PlaybackState.PLAYING) {
                this.stateManager.setState(PlaybackState.BUFFERING);
            }
        });
        // バッファリング完了
        this.videoElement.addEventListener('canplay', () => {
            if (this.stateManager.getState() === PlaybackState.BUFFERING) {
                this.stateManager.setState(PlaybackState.PLAYING);
            }
        });
        // 動画終了
        this.videoElement.addEventListener('ended', () => {
            this.stateManager.setState(PlaybackState.ENDED);
        });
        // エラー
        this.videoElement.addEventListener('error', () => {
            this.stateManager.setState(PlaybackState.ERROR);
        });
    }

    /**
     * プレイヤーを初期化（hls.js + OfflineLoader）
     */
    private async initializePlayer(playlistUrl: string): Promise<void> {
        // 既存インスタンス破棄
        if (this.hls) {
            this.hls.destroy();
            this.hls = null;
        }

        // hls.js を利用（Safari のネイティブ HLS でも動くが、オフラインローダーは hls.js を介す前提）
        if (Hls.isSupported()) {
            this.hls = new Hls({
                enableWorker: true,
                preferManagedMediaSource: false,
                // オフライン読み出し用のローダーに差し替え
                // 型が公開されていないため any キャスト
                loader: HlsOfflineLoader as any,
                // 初回の開始位置は 0 （必要に応じて外から seek()）
                startPosition: 0,
                // 余裕を持ってタイムアウト/リトライを緩める（オフライン I/O レイヤで遅延が出ることがある）
                manifestLoadPolicy: {
                    default: {
                        maxTimeToFirstByteMs: 1000000,
                        maxLoadTimeMs: 1000000,
                        timeoutRetry: {
                            maxNumRetry: 2,
                            retryDelayMs: 0,
                            maxRetryDelayMs: 0,
                        },
                        errorRetry: {
                            maxNumRetry: 1,
                            retryDelayMs: 1000,
                            maxRetryDelayMs: 8000,
                        },
                    },
                },
                playlistLoadPolicy: {
                    default: {
                        maxTimeToFirstByteMs: 1000000,
                        maxLoadTimeMs: 1000000,
                        timeoutRetry: {
                            maxNumRetry: 2,
                            retryDelayMs: 0,
                            maxRetryDelayMs: 0,
                        },
                        errorRetry: {
                            maxNumRetry: 2,
                            retryDelayMs: 1000,
                            maxRetryDelayMs: 8000,
                        },
                    },
                },
                fragLoadPolicy: {
                    default: {
                        maxTimeToFirstByteMs: 1000000,
                        maxLoadTimeMs: 1000000,
                        timeoutRetry: {
                            maxNumRetry: 4,
                            retryDelayMs: 0,
                            maxRetryDelayMs: 0,
                        },
                        errorRetry: {
                            maxNumRetry: 6,
                            retryDelayMs: 1000,
                            maxRetryDelayMs: 8000,
                        },
                    },
                },
            });

            // <video> にアタッチ → ソース読み込み
            this.hls.attachMedia(this.videoElement);
            this.hls.on(Hls.Events.MEDIA_ATTACHED, () => {
                this.hls?.loadSource(playlistUrl);
            });

            // マニフェスト解析完了
            this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
                // READY 状態遷移は initialize() 側で行うため、ここでは自動再生のみ任意
                // void を付けて Lint の未使用 Promise 警告回避
                void this.videoElement.play().catch(() => {/* 自動再生失敗は無視 */});
            });

            // エラーハンドリング
            this.hls.on(Hls.Events.ERROR, (_e, data) => {
                if (!data) return;
                const fatal = (data as any).fatal === true;
                if (fatal) {
                    console.error('[OfflinePlayback] hls.js fatal error:', data);
                    this.stateManager.setState(PlaybackState.ERROR);
                } else {
                    console.warn('[OfflinePlayback] hls.js non-fatal error:', data);
                }
            });
        } else {
            // 極力 hls.js を利用する想定。どうしても未対応環境なら、<source> に直接指定（ただし OfflineLoader は効かない）
            this.videoElement.src = playlistUrl;
        }
    }

    /**
     * メタデータを読み込み（存在チェックも兼ねる）
     */
    private async loadMetadata(downloadId: string): Promise<OfflineDownloadMetadata | undefined> {
        this.stateManager.setState(PlaybackState.LOADING_METADATA);
        const meta = await OfflineStorage.getMetadata(downloadId);
        return meta;
    }

    /**
     * オフライン用プレイリスト URL を構築
     */
    private buildOfflinePlaylistUrl(downloadId: string): string {
        // 既存実装（HlsOfflineLoader）と揃える
        return `/offline/streams/${downloadId}/playlist.m3u8`;
    }

    /** クリーンアップ */
    destroy(): void {
        if (this.hls) {
            this.hls.destroy();
            this.hls = null;
        }
        this.videoElement.removeAttribute('src');
        this.videoElement.load();
        this.stateManager.setState(PlaybackState.UNINITIALIZED);
    }
}

export default OfflinePlaybackController;
