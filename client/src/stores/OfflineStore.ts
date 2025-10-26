import { defineStore } from 'pinia';

import type { OfflineDownloadMetadata, OfflineDownloadProgressUpdate, OfflineStorageBackend } from '@/offline/types';

import OfflineStorage from '@/offline/storage';
import APIClient from '@/services/APIClient';
import Message from '@/message';

interface ProgressState {
    [id: string]: OfflineDownloadProgressUpdate;
}

// オフラインダウンロードに関するメタデータと進捗を集中管理する Pinia ストア
const useOfflineStore = defineStore('offline', {
    state: () => ({
        initialized: false,
        storage_backend: null as OfflineStorageBackend | null,
        downloads: [] as OfflineDownloadMetadata[],
        progress: {} as ProgressState,
        initialization_error: null as string | null,
        // オフラインモード: true の場合、サーバーとの通信が行われず、オフライン視聴のみ可能
        is_offline_mode: false,
    }),
    getters: {
        activeDownloads(state): OfflineDownloadMetadata[] {
            return state.downloads.filter(download => download.status === 'downloading');
        },
    },
    actions: {
        // 利用可能なバックエンドを確定させ、保存済みメタデータを読み込む
        async initialize(): Promise<void> {
            if (this.initialized === true) {
                return;
            }
            try {
                const backend = await OfflineStorage.detectAvailableBackend();
                this.storage_backend = backend;
                await this.refreshDownloads();
                this.initialized = true;
                this.initialization_error = null;
            } catch (error) {
                console.error('[OfflineStore] Failed to initialize offline storage backend.', error);
                this.initialization_error = 'オフライン保存用ストレージを初期化できませんでした。ブラウザの設定をご確認ください。';
            }
        },
        // IndexedDB などに保存されているダウンロードメタデータを読み直す
        async refreshDownloads(): Promise<void> {
            try {
                this.downloads = await OfflineStorage.listMetadata();
            } catch (error) {
                console.error('[OfflineStore] Failed to refresh downloads metadata.', error);
            }
        },
        // メタデータを新規追加または更新する
        upsertDownload(metadata: OfflineDownloadMetadata): void {
            const index = this.downloads.findIndex(download => download.id === metadata.id);
            if (index === -1) {
                this.downloads = [...this.downloads, metadata];
            } else {
                const updated = [...this.downloads];
                updated.splice(index, 1, metadata);
                this.downloads = updated;
            }
        },
        // 進捗情報をマージする
        setProgress(update: OfflineDownloadProgressUpdate): void {
            this.progress = {
                ...this.progress,
                [update.id]: {
                    ...this.progress[update.id],
                    ...update,
                },
            };
        },
        // ダウンロード完了などで不要になった進捗を破棄する
        clearProgress(id: string): void {
            if (this.progress[id] === undefined) {
                return;
            }
            const {[id]: _, ...rest} = this.progress;
            this.progress = rest;
        },
        // メタデータと進捗をあわせて削除する
        removeDownload(id: string): void {
            this.downloads = this.downloads.filter(download => download.id !== id);
            this.clearProgress(id);
        },
        // 状態のみを変更する際のユーティリティ
        updateDownloadStatus(id: string, status: OfflineDownloadMetadata['status']): void {
            const index = this.downloads.findIndex(download => download.id === id);
            if (index === -1) {
                return;
            }
            const updatedDownload: OfflineDownloadMetadata = {
                ...this.downloads[index],
                status,
                updated_at: new Date().toISOString(),
            };
            const updated = [...this.downloads];
            updated.splice(index, 1, updatedDownload);
            this.downloads = updated;
        },
        // オフラインモードの切り替え
        setOfflineMode(enabled: boolean): void {
            this.is_offline_mode = enabled;
            // localStorage に保存して永続化
            if (enabled) {
                localStorage.setItem('offline_mode', 'true');
            } else {
                localStorage.removeItem('offline_mode');
            }
        },
        // オフラインモードの状態を localStorage から復元
        restoreOfflineMode(): void {
            const stored = localStorage.getItem('offline_mode');
            this.is_offline_mode = stored === 'true';
        },
        // オフライン保存したコメントデータを取得する
        async getJikkyoComments(downloadId: string): Promise<any[] | null> {
            try {
                return await OfflineStorage.readComments(downloadId);
            } catch (error) {
                console.error('[OfflineStore] Failed to read comments:', error);
                return null;
            }
        },
        // サーバーへの接続を確認し、接続できたらオフラインモードを自動解除する
        async checkServerConnection(): Promise<boolean> {
            // オフラインモードが無効なら何もしない
            if (this.is_offline_mode === false) {
                return true;
            }

            try {
                // /api/version エンドポイントに軽量なリクエストを送信してサーバー接続を確認
                // タイムアウトは5秒に設定
                const response = await APIClient.get('/version', {
                    timeout: 5000,
                });

                if (response.type === 'success') {
                    // サーバーへの接続が成功したらオフラインモードを解除
                    console.log('[OfflineStore] Server connection restored. Disabling offline mode.');
                    this.setOfflineMode(false);
                    Message.success('サーバーへの接続が復旧しました。オフラインモードを解除します。');
                    return true;
                }
                return false;
            } catch (error) {
                // 接続失敗時はログのみ出力（ユーザーには通知しない）
                console.log('[OfflineStore] Server connection check failed. Staying in offline mode.');
                return false;
            }
        },
    },
});

export default useOfflineStore;
