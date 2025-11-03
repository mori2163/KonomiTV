import { openDB, type IDBPDatabase } from 'idb';

import type { OfflineDownloadMetadata, OfflineStorageBackend } from '@/offline/types';

import { serializeMetadata } from '@/offline/types';


interface OfflineDBSchema {
    downloads: {
        key: string;
        value: OfflineDownloadMetadata;
    };
    segments: {
        key: string;
        value: ArrayBuffer;
    };
    playlists: {
        key: string;
        value: string;
    };
    comments: {
        key: string;
        value: any[];
    };
    thumbnails: {
        key: string;
        value: Blob;
    };
}

const DB_NAME = 'konomitv-offline';
const DB_VERSION = 1;
const CACHE_STORAGE_NAME = 'konomitv-offline-cache';
const OFFLINE_ROOT_DIRECTORY = 'konomitv-offline';

let dbPromise: Promise<IDBPDatabase<OfflineDBSchema>> | null = null;

function normalizeMetadata(metadata: OfflineDownloadMetadata): OfflineDownloadMetadata {
    return {
        ...metadata,
        save_comments: metadata.save_comments ?? true,
        has_thumbnail: metadata.has_thumbnail ?? false,
    };
}

async function getDatabase(): Promise<IDBPDatabase<OfflineDBSchema>> {
    if (dbPromise !== null) {
        return dbPromise;
    }
    dbPromise = openDB<OfflineDBSchema>(DB_NAME, DB_VERSION, {
        upgrade(database, oldVersion) {
            if (!database.objectStoreNames.contains('downloads')) {
                database.createObjectStore('downloads', {keyPath: 'id'});
            }
            if (!database.objectStoreNames.contains('segments')) {
                database.createObjectStore('segments');
            }
            if (!database.objectStoreNames.contains('playlists')) {
                database.createObjectStore('playlists');
            }
            if (!database.objectStoreNames.contains('comments')) {
                database.createObjectStore('comments');
            }
            if (!database.objectStoreNames.contains('thumbnails')) {
                database.createObjectStore('thumbnails');
            }
        },
    });
    return dbPromise;
}

async function getOPFSRoot(create: boolean = false): Promise<FileSystemDirectoryHandle | null> {
    if (typeof navigator === 'undefined' || navigator.storage === undefined || navigator.storage.getDirectory === undefined) {
        return null;
    }
    try {
        const root = await navigator.storage.getDirectory();
        if (OFFLINE_ROOT_DIRECTORY.length === 0) {
            return root;
        }
        let current = root;
        const parts = OFFLINE_ROOT_DIRECTORY.split('/').filter(part => part.length > 0);
        for (const part of parts) {
            current = await current.getDirectoryHandle(part, {create});
        }
        return current;
    } catch (error) {
        console.warn('[OfflineStorage] Failed to access OPFS root.', error);
        return null;
    }
}

async function getOPFSFileHandle(path: string[], options: {create: boolean}): Promise<FileSystemFileHandle | null> {
    const root = await getOPFSRoot(options.create);
    if (root === null) {
        return null;
    }
    let current: FileSystemDirectoryHandle = root;
    const directories = path.slice(0, -1);
    const filename = path[path.length - 1];
    try {
        for (const dir of directories) {
            current = await current.getDirectoryHandle(dir, {create: options.create});
        }
        return await current.getFileHandle(filename, {create: options.create});
    } catch (error) {
        // 期待される未存在 (create=false) は静かに null を返す
        if (options.create === false) {
            const name = (error as any)?.name ?? '';
            if (name === 'NotFoundError' || name === 'TypeMismatchError' || name === 'NotAllowedError') {
                return null;
            }
        }
        console.warn('[OfflineStorage] Failed to access OPFS file handle.', error);
        return null;
    }
}

async function removeOPFSDirectory(path: string[]): Promise<void> {
    const root = await getOPFSRoot(false);
    if (root === null) {
        return;
    }
    let current: FileSystemDirectoryHandle = root;
    try {
        for (let index = 0; index < path.length - 1; index++) {
            current = await current.getDirectoryHandle(path[index]);
        }
        await current.removeEntry(path[path.length - 1], {recursive: true});
    } catch (error) {
        console.warn('[OfflineStorage] Failed to remove OPFS directory.', error);
    }
}

export class OfflineStorage {

    static get cacheStorageName(): string {
        return CACHE_STORAGE_NAME;
    }

    static async detectAvailableBackend(): Promise<OfflineStorageBackend> {
        const opfsRoot = await getOPFSRoot(true);
        if (opfsRoot !== null) {
            return 'opfs';
        }
        if (typeof indexedDB !== 'undefined') {
            return 'indexeddb';
        }
        if (typeof caches !== 'undefined') {
            return 'cache';
        }
        throw new Error('No available offline storage backend.');
    }

    static async putMetadata(metadata: OfflineDownloadMetadata): Promise<void> {
        const database = await getDatabase();
        // IndexedDB に保存する前にシリアライズして、確実にプレーンオブジェクトにする
        const serialized = serializeMetadata(metadata);
        await database.put('downloads', serialized);
    }

    static async updateMetadata(id: string, update: Partial<OfflineDownloadMetadata>): Promise<void> {
        const database = await getDatabase();
        const current = await database.get('downloads', id);
        if (current === undefined) {
            throw new Error(`[OfflineStorage] Metadata ${id} not found.`);
        }
        const normalized = normalizeMetadata(current as OfflineDownloadMetadata);
        const updated = {...normalized, ...update, updated_at: new Date().toISOString()};
        // 更新時もシリアライズする
        const serialized = serializeMetadata(updated);
        await database.put('downloads', serialized);
    }

    static async getMetadata(id: string): Promise<OfflineDownloadMetadata | undefined> {
        const database = await getDatabase();
        const metadata = await database.get('downloads', id) as OfflineDownloadMetadata | undefined;
        return metadata !== undefined ? normalizeMetadata(metadata) : undefined;
    }

    static async listMetadata(): Promise<OfflineDownloadMetadata[]> {
        const database = await getDatabase();
        const all = await database.getAll('downloads') as OfflineDownloadMetadata[];
        return all
            .map(normalizeMetadata)
            .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    }

    static async deleteMetadata(id: string): Promise<void> {
        const database = await getDatabase();
        await database.delete('downloads', id);
    }

    static async writePlaylist(metadata: OfflineDownloadMetadata, content: string): Promise<void> {
        if (metadata.storage_backend === 'opfs') {
            const fileHandle = await getOPFSFileHandle([metadata.id, metadata.playlist_path], {create: true});
            if (fileHandle === null) {
                throw new Error('Failed to create playlist file in OPFS.');
            }
            const writable = await fileHandle.createWritable();
            await writable.write(content);
            await writable.close();
        } else if (metadata.storage_backend === 'indexeddb') {
            const database = await getDatabase();
            await database.put('playlists', content, metadata.id);
        } else {
            const cache = await caches.open(CACHE_STORAGE_NAME);
            const request = new Request(`/offline/streams/${metadata.id}/playlist.m3u8`, {cache: 'reload'});
            await cache.put(request, new Response(content, {headers: {'Content-Type': 'application/vnd.apple.mpegurl'}}));
        }
    }

    static async readPlaylist(metadata: OfflineDownloadMetadata): Promise<string | null> {
        if (metadata.storage_backend === 'opfs') {
            const fileHandle = await getOPFSFileHandle([metadata.id, metadata.playlist_path], {create: false});
            if (fileHandle === null) {
                return null;
            }
            const file = await fileHandle.getFile();
            return await file.text();
        } else if (metadata.storage_backend === 'indexeddb') {
            const database = await getDatabase();
            return await database.get('playlists', metadata.id) ?? null;
        } else {
            const cache = await caches.open(CACHE_STORAGE_NAME);
            const response = await cache.match(new Request(`/offline/streams/${metadata.id}/playlist.m3u8`));
            if (response === undefined) {
                return null;
            }
            return await response.text();
        }
    }

    static async writeSegment(metadata: OfflineDownloadMetadata, sequence: number, data: ArrayBuffer): Promise<void> {
        const filename = `segment-${sequence.toString().padStart(8, '0')}.ts`;
        if (metadata.storage_backend === 'opfs') {
            const fileHandle = await getOPFSFileHandle([metadata.id, 'segments', filename], {create: true});
            if (fileHandle === null) {
                throw new Error('Failed to create segment file in OPFS.');
            }
            const writable = await fileHandle.createWritable();
            await writable.write(data);
            await writable.close();
        } else if (metadata.storage_backend === 'indexeddb') {
            const database = await getDatabase();
            await database.put('segments', data, `${metadata.id}:${sequence}`);
        } else {
            const cache = await caches.open(CACHE_STORAGE_NAME);
            const request = new Request(`/offline/streams/${metadata.id}/segments/${filename}`, {cache: 'reload'});
            await cache.put(request, new Response(data, {headers: {'Content-Type': 'video/mp2t'}}));
        }
    }

    static async readSegment(metadata: OfflineDownloadMetadata, sequence: number): Promise<ArrayBuffer | null> {
        const filename = `segment-${sequence.toString().padStart(8, '0')}.ts`;
        if (metadata.storage_backend === 'opfs') {
            const fileHandle = await getOPFSFileHandle([metadata.id, 'segments', filename], {create: false});
            if (fileHandle === null) {
                return null;
            }
            const file = await fileHandle.getFile();
            return await file.arrayBuffer();
        } else if (metadata.storage_backend === 'indexeddb') {
            const database = await getDatabase();
            const buffer = await database.get('segments', `${metadata.id}:${sequence}`);
            return buffer ?? null;
        } else {
            const cache = await caches.open(CACHE_STORAGE_NAME);
            const response = await cache.match(new Request(`/offline/streams/${metadata.id}/segments/${filename}`));
            if (response === undefined) {
                return null;
            }
            return await response.arrayBuffer();
        }
    }

    static async removeDownload(metadata: OfflineDownloadMetadata): Promise<void> {
        if (metadata.storage_backend === 'opfs') {
            await removeOPFSDirectory([metadata.id]);
        } else if (metadata.storage_backend === 'indexeddb') {
            const database = await getDatabase();
            const tx = database.transaction(['segments', 'playlists', 'comments', 'thumbnails'], 'readwrite');
            await tx.objectStore('playlists').delete(metadata.id);
            await tx.objectStore('comments').delete(metadata.id);
            await tx.objectStore('thumbnails').delete(metadata.id);
            for (let index = 0; index < metadata.segment_count; index++) {
                await tx.objectStore('segments').delete(`${metadata.id}:${index}`);
            }
            await tx.done;
        } else {
            const cache = await caches.open(CACHE_STORAGE_NAME);
            await cache.delete(new Request(`/offline/streams/${metadata.id}/playlist.m3u8`));
            for (let index = 0; index < metadata.segment_count; index++) {
                const filename = `segment-${index.toString().padStart(8, '0')}.ts`;
                await cache.delete(new Request(`/offline/streams/${metadata.id}/segments/${filename}`));
            }
        }
        await OfflineStorage.deleteMetadata(metadata.id);
    }

    // コメントデータを保存する
    static async writeComments(downloadId: string, comments: any[]): Promise<void> {
        const database = await getDatabase();
        await database.put('comments', comments, downloadId);
    }

    // コメントデータを取得する
    static async readComments(downloadId: string): Promise<any[] | null> {
        const database = await getDatabase();
        const comments = await database.get('comments', downloadId);
        return comments ?? null;
    }

    // サムネイル画像を保存する
    static async writeThumbnail(downloadId: string, blob: Blob): Promise<void> {
        const database = await getDatabase();
        await database.put('thumbnails', blob, downloadId);
    }

    // サムネイル画像を取得する
    static async readThumbnail(downloadId: string): Promise<Blob | null> {
        const database = await getDatabase();
        const blob = await database.get('thumbnails', downloadId);
        return blob ?? null;
    }

    // サムネイル画像のdata URLを取得する
    static async getThumbnailDataUrl(downloadId: string): Promise<string | null> {
        const blob = await OfflineStorage.readThumbnail(downloadId);
        if (blob === null) {
            return null;
        }
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    // ストレージの使用量と割り当て量を取得する
    static async getStorageEstimate(): Promise<{usage: number; quota: number} | null> {
        if (typeof navigator === 'undefined' || navigator.storage === undefined || navigator.storage.estimate === undefined) {
            return null;
        }
        try {
            const estimate = await navigator.storage.estimate();
            return {
                usage: estimate.usage ?? 0,
                quota: estimate.quota ?? 0,
            };
        } catch (error) {
            console.warn('[OfflineStorage] Failed to get storage estimate.', error);
            return null;
        }
    }
}

export default OfflineStorage;
