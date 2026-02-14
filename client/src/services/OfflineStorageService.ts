
import type { IJikkyoComments, IRecordedProgram } from '@/services/Videos';

import { dayjs } from '@/utils';



/** オフライン保存のステータス */
export type OfflineDownloadStatus = 'Pending' | 'Downloading' | 'Completed' | 'Failed' | 'Paused';

/** IndexedDB に保存するオフライン番組レコード */
export interface IOfflineProgramRecord {
    id: number;
    recorded_program: IRecordedProgram;
    download_status: OfflineDownloadStatus;
    quality: string;
    include_comments: boolean;
    total_segments: number;
    downloaded_segments: number;
    total_size: number;
    download_started_at: string;
    download_completed_at: string | null;
    failed_at: string | null;
    error_message: string | null;
}

/** オフライン保存で利用可能なストレージ情報 */
export interface IOfflineStorageEstimate {
    usage: number;
    quota: number;
    available: number;
}


/**
 * オフライン保存データ (IndexedDB + OPFS) を管理するサービス
 */
class OfflineStorageService {

    private static readonly DATABASE_NAME = 'KonomiTV-Offline';
    private static readonly DATABASE_VERSION = 1;
    private static readonly OFFLINE_PROGRAMS_STORE_NAME = 'offline_programs';
    private static readonly OFFLINE_DIRECTORY_NAME = 'offline-videos';

    private static database_promise: Promise<IDBDatabase> | null = null;
    private static opfs_root_promise: Promise<FileSystemDirectoryHandle> | null = null;


    /**
     * オフライン保存機能を利用可能か判定する
     * @returns 利用可能かどうか
     */
    static isSupported(): boolean {
        const storage_manager = navigator.storage as StorageManager & {
            getDirectory?: () => Promise<FileSystemDirectoryHandle>;
        };
        return 'indexedDB' in globalThis && storage_manager.getDirectory !== undefined;
    }


    /**
     * ストレージ使用量を取得する
     * @returns 使用量・上限・残容量
     */
    static async estimateStorage(): Promise<IOfflineStorageEstimate> {
        const estimate = await navigator.storage.estimate();
        const usage = estimate.usage ?? 0;
        const quota = estimate.quota ?? 0;
        return {
            usage: usage,
            quota: quota,
            available: Math.max(0, quota - usage),
        };
    }


    /**
     * IndexedDB の Database インスタンスを取得する
     * @returns Database インスタンス
     */
    private static async getDatabase(): Promise<IDBDatabase> {
        if (this.database_promise !== null) {
            return await this.database_promise;
        }

        this.database_promise = new Promise((resolve, reject) => {
            const request = indexedDB.open(this.DATABASE_NAME, this.DATABASE_VERSION);

            request.onupgradeneeded = () => {
                const database = request.result;
                let offline_programs_store: IDBObjectStore;

                // オブジェクトストアが未作成なら新規作成し、既存なら参照を取得する
                if (database.objectStoreNames.contains(this.OFFLINE_PROGRAMS_STORE_NAME) === false) {
                    offline_programs_store = database.createObjectStore(this.OFFLINE_PROGRAMS_STORE_NAME, { keyPath: 'id' });
                } else {
                    const transaction = request.transaction;
                    if (transaction === null) {
                        return;
                    }
                    offline_programs_store = transaction.objectStore(this.OFFLINE_PROGRAMS_STORE_NAME);
                }

                // オフライン一覧で利用するインデックスを作成
                if (offline_programs_store.indexNames.contains('download_status') === false) {
                    offline_programs_store.createIndex('download_status', 'download_status', { unique: false });
                }
                if (offline_programs_store.indexNames.contains('download_completed_at') === false) {
                    offline_programs_store.createIndex('download_completed_at', 'download_completed_at', { unique: false });
                }
                // ステータスでフィルタリングしつつ完了日時で降順ソートするための複合インデックス
                if (offline_programs_store.indexNames.contains('status_completed_at') === false) {
                    offline_programs_store.createIndex('status_completed_at', ['download_status', 'download_completed_at'], { unique: false });
                }
            };

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => {
                // 失敗時は Promise キャッシュをクリアし、次回の getDatabase() 呼び出しでリトライできるようにする
                this.database_promise = null;
                reject(request.error ?? new Error('Failed to open offline IndexedDB.'));
            };
        });

        // Promise が reject された場合もキャッシュをクリアする（onupgradeneeded 内のエラー等に備える）
        this.database_promise.catch(() => {
            this.database_promise = null;
        });

        return await this.database_promise;
    }


    /**
     * OPFS の Root Directory を取得する
     * @returns Root Directory
     */
    private static async getOPFSRootDirectory(): Promise<FileSystemDirectoryHandle> {
        if (this.opfs_root_promise !== null) {
            return await this.opfs_root_promise;
        }

        const storage_manager = navigator.storage as StorageManager & {
            getDirectory?: () => Promise<FileSystemDirectoryHandle>;
        };
        if (storage_manager.getDirectory === undefined) {
            throw new Error('OPFS is not supported in this browser.');
        }
        this.opfs_root_promise = storage_manager.getDirectory();

        // 失敗時は Promise キャッシュをクリアし、次回の getOPFSRootDirectory() 呼び出しでリトライできるようにする
        this.opfs_root_promise.catch(() => {
            this.opfs_root_promise = null;
        });

        return await this.opfs_root_promise;
    }


    /**
     * OPFS の offline-videos ディレクトリを取得する
     * @param create ディレクトリが無い場合に作成するか
     * @returns offline-videos ディレクトリ
     */
    private static async getOfflineRootDirectory(create: boolean): Promise<FileSystemDirectoryHandle> {
        const root_directory = await this.getOPFSRootDirectory();
        if (create === true) {
            return await root_directory.getDirectoryHandle(this.OFFLINE_DIRECTORY_NAME, { create: true });
        }
        return await root_directory.getDirectoryHandle(this.OFFLINE_DIRECTORY_NAME);
    }


    /**
     * 指定した録画番組 ID の OPFS ディレクトリを取得する
     * @param video_id 録画番組 ID
     * @param create ディレクトリが無い場合に作成するか
     * @returns 録画番組ディレクトリ
     */
    private static async getVideoDirectory(video_id: number, create: boolean): Promise<FileSystemDirectoryHandle> {
        const offline_root_directory = await this.getOfflineRootDirectory(create);
        if (create === true) {
            return await offline_root_directory.getDirectoryHandle(String(video_id), { create: true });
        }
        return await offline_root_directory.getDirectoryHandle(String(video_id));
    }


    /**
     * OPFS にファイルを書き込む
     * @param directory 書き込み先ディレクトリ
     * @param filename ファイル名
     * @param data 書き込むデータ
     */
    private static async writeFile(
        directory: FileSystemDirectoryHandle,
        filename: string,
        data: string | Blob | BufferSource,
    ): Promise<void> {
        const file_handle = await directory.getFileHandle(filename, { create: true });
        let writable: FileSystemWritableFileStream | undefined = undefined;
        try {
            writable = await file_handle.createWritable();
            await writable.write(data);
        } finally {
            if (writable !== undefined) {
                await writable.close();
            }
        }
    }


    /**
     * IndexedDB からオフライン保存済み番組をすべて取得する
     * @returns オフライン保存済み番組一覧
     */
    static async getAllPrograms(): Promise<IOfflineProgramRecord[]> {
        const database = await this.getDatabase();
        const records = await new Promise<IOfflineProgramRecord[]>((resolve, reject) => {
            const transaction = database.transaction(this.OFFLINE_PROGRAMS_STORE_NAME, 'readonly');
            const request = transaction.objectStore(this.OFFLINE_PROGRAMS_STORE_NAME).getAll();
            request.onsuccess = () => resolve(request.result as IOfflineProgramRecord[]);
            request.onerror = () => reject(request.error ?? new Error('Failed to load offline program records.'));
        });

        // ダウンロード完了日時の降順で並び替える
        records.sort((record_a, record_b) => {
            const record_a_time = dayjs(record_a.download_completed_at ?? record_a.download_started_at).valueOf();
            const record_b_time = dayjs(record_b.download_completed_at ?? record_b.download_started_at).valueOf();
            return record_b_time - record_a_time;
        });
        return records;
    }


    /**
     * IndexedDB からオフライン保存済み番組を取得する
     * @param video_id 録画番組 ID
     * @returns オフライン保存済み番組レコード
     */
    static async getProgram(video_id: number): Promise<IOfflineProgramRecord | null> {
        const database = await this.getDatabase();
        return await new Promise<IOfflineProgramRecord | null>((resolve, reject) => {
            const transaction = database.transaction(this.OFFLINE_PROGRAMS_STORE_NAME, 'readonly');
            const request = transaction.objectStore(this.OFFLINE_PROGRAMS_STORE_NAME).get(video_id);
            request.onsuccess = () => resolve((request.result as IOfflineProgramRecord | undefined) ?? null);
            request.onerror = () => reject(request.error ?? new Error('Failed to load an offline program record.'));
        });
    }


    /**
     * IndexedDB にオフライン保存済み番組を保存する
     * @param record オフライン保存済み番組レコード
     */
    static async setProgram(record: IOfflineProgramRecord): Promise<void> {
        const database = await this.getDatabase();
        await new Promise<void>((resolve, reject) => {
            const transaction = database.transaction(this.OFFLINE_PROGRAMS_STORE_NAME, 'readwrite');
            const request = transaction.objectStore(this.OFFLINE_PROGRAMS_STORE_NAME).put(record);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error ?? new Error('Failed to save an offline program record.'));
        });
    }


    /**
     * IndexedDB 上のオフライン保存済み番組レコードを部分更新する
     * @param video_id 録画番組 ID
     * @param partial 更新する項目
     * @returns 更新後のレコード
     */
    static async updateProgram(
        video_id: number,
        partial: Partial<IOfflineProgramRecord>,
    ): Promise<IOfflineProgramRecord | null> {
        const record = await this.getProgram(video_id);
        if (record === null) {
            return null;
        }
        const next_record: IOfflineProgramRecord = {
            ...record,
            ...partial,
        };
        await this.setProgram(next_record);
        return next_record;
    }


    /**
     * IndexedDB と OPFS からオフライン保存済み番組を削除する
     * @param video_id 録画番組 ID
     */
    static async deleteProgram(video_id: number): Promise<void> {
        await this.deleteVideoDirectory(video_id);

        const database = await this.getDatabase();
        await new Promise<void>((resolve, reject) => {
            const transaction = database.transaction(this.OFFLINE_PROGRAMS_STORE_NAME, 'readwrite');
            const request = transaction.objectStore(this.OFFLINE_PROGRAMS_STORE_NAME).delete(video_id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error ?? new Error('Failed to delete an offline program record.'));
        });
    }


    /**
     * アプリ起動時にダウンロード中だったレコードを一時停止に変更する
     */
    static async markDownloadingRecordsAsPaused(): Promise<void> {
        const records = await this.getAllPrograms();
        const downloading_records = records.filter((record) => record.download_status === 'Downloading');
        await Promise.all(downloading_records.map(async (record) => {
            await this.setProgram({
                ...record,
                download_status: 'Paused',
                error_message: record.error_message ?? 'ダウンロードが中断されました。',
            });
        }));
    }


    /**
     * 録画番組の OPFS ディレクトリを作成する
     * @param video_id 録画番組 ID
     */
    static async ensureVideoDirectory(video_id: number): Promise<void> {
        await this.getVideoDirectory(video_id, true);
    }


    /**
     * 録画番組の OPFS ディレクトリを削除する
     * @param video_id 録画番組 ID
     */
    static async deleteVideoDirectory(video_id: number): Promise<void> {
        try {
            const offline_root_directory = await this.getOfflineRootDirectory(false);
            await offline_root_directory.removeEntry(String(video_id), { recursive: true });
        } catch (error) {
            // ディレクトリが存在しない場合は削除済みとして扱う
            if (error instanceof DOMException && error.name === 'NotFoundError') {
                return;
            }
            throw error;
        }
    }


    /**
     * HLS プレイリストを OPFS に保存する
     * @param video_id 録画番組 ID
     * @param playlist_text プレイリスト
     */
    static async writePlaylist(video_id: number, playlist_text: string): Promise<void> {
        const video_directory = await this.getVideoDirectory(video_id, true);
        await this.writeFile(video_directory, 'playlist.m3u8', playlist_text);
    }


    /**
     * HLS プレイリストを OPFS から取得する
     * @param video_id 録画番組 ID
     * @returns プレイリスト文字列
     */
    static async readPlaylist(video_id: number): Promise<string> {
        const video_directory = await this.getVideoDirectory(video_id, false);
        const playlist_handle = await video_directory.getFileHandle('playlist.m3u8');
        const playlist_file = await playlist_handle.getFile();
        return await playlist_file.text();
    }


    /**
     * HLS セグメントを OPFS に保存する
     * @param video_id 録画番組 ID
     * @param sequence セグメント番号
     * @param data セグメントデータ
     */
    static async writeSegment(video_id: number, sequence: number, data: ArrayBuffer): Promise<void> {
        const video_directory = await this.getVideoDirectory(video_id, true);
        const segments_directory = await video_directory.getDirectoryHandle('segments', { create: true });
        await this.writeFile(segments_directory, `${sequence}.ts`, data);
    }


    /**
     * HLS セグメントを OPFS から取得する
     * @param video_id 録画番組 ID
     * @param sequence セグメント番号
     * @returns セグメントデータ
     */
    static async readSegment(video_id: number, sequence: number): Promise<ArrayBuffer> {
        const video_directory = await this.getVideoDirectory(video_id, false);
        const segments_directory = await video_directory.getDirectoryHandle('segments');
        const segment_handle = await segments_directory.getFileHandle(`${sequence}.ts`);
        const segment_file = await segment_handle.getFile();
        return await segment_file.arrayBuffer();
    }


    /**
     * ニコニコ実況過去ログコメントを OPFS に保存する
     * @param video_id 録画番組 ID
     * @param comments ニコニコ実況過去ログコメント
     */
    static async writeComments(video_id: number, comments: IJikkyoComments): Promise<void> {
        const video_directory = await this.getVideoDirectory(video_id, true);
        await this.writeFile(video_directory, 'comments.json', JSON.stringify(comments));
    }


    /**
     * ニコニコ実況過去ログコメントを OPFS から取得する
     * @param video_id 録画番組 ID
     * @returns ニコニコ実況過去ログコメント
     */
    static async readComments(video_id: number): Promise<IJikkyoComments | null> {
        try {
            const video_directory = await this.getVideoDirectory(video_id, false);
            const comments_handle = await video_directory.getFileHandle('comments.json');
            const comments_file = await comments_handle.getFile();
            return JSON.parse(await comments_file.text()) as IJikkyoComments;
        } catch (error) {
            if (error instanceof DOMException && error.name === 'NotFoundError') {
                return null;
            }
            throw error;
        }
    }


    /**
     * サムネイル画像を OPFS に保存する
     * @param video_id 録画番組 ID
     * @param thumbnail_blob サムネイル画像データ
     */
    static async writeThumbnail(video_id: number, thumbnail_blob: Blob): Promise<void> {
        const video_directory = await this.getVideoDirectory(video_id, true);
        await this.writeFile(video_directory, 'thumbnail.webp', thumbnail_blob);
    }


    /**
     * サムネイル画像を OPFS から取得する
     * @param video_id 録画番組 ID
     * @returns サムネイル画像データ
     */
    static async readThumbnail(video_id: number): Promise<Blob | null> {
        try {
            const video_directory = await this.getVideoDirectory(video_id, false);
            const thumbnail_handle = await video_directory.getFileHandle('thumbnail.webp');
            const thumbnail_file = await thumbnail_handle.getFile();
            return thumbnail_file;
        } catch (error) {
            if (error instanceof DOMException && error.name === 'NotFoundError') {
                return null;
            }
            throw error;
        }
    }
}

export default OfflineStorageService;
