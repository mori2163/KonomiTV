import { defineStore } from 'pinia';

import type { OfflineDownloadMetadata, OfflineDownloadProgressUpdate, OfflineStorageBackend } from '@/offline/types';

import Message from '@/message';
import OfflineStorage from '@/offline/storage';
import APIClient from '@/services/APIClient';

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
        // オフライン保存したコメントデータを取得する
        async getJikkyoComments(downloadId: string): Promise<any[] | null> {
            try {
                return await OfflineStorage.readComments(downloadId);
            } catch (error) {
                console.error('[OfflineStore] Failed to read comments:', error);
                return null;
            }
        },
    },
});

export default useOfflineStore;
