/// <reference lib="webworker" />

// Vite の injectManifest 方式でビルドされるサービスワーカー
// ここでは Workbox のプリキャッシュと KonomiTV 独自のオフライン再生ルーティングを実装する

import {cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute} from 'workbox-precaching';
import {NavigationRoute, registerRoute} from 'workbox-routing';

import type { OfflineDownloadMetadata } from '@/offline/types';

import OfflineStorage from '@/offline/storage';

// self は ServiceWorkerGlobalScope だが、__WB_MANIFEST を追加で持つ
declare const self: ServiceWorkerGlobalScope & {__WB_MANIFEST: Array<{url: string; revision?: string;} | string>;};

// オフライン再生用の仮想パス。クライアント側の HLS プレイリスト/セグメントリクエストをこのパスに切り替えている
const OFFLINE_STREAM_BASE_PATH = '/offline/streams/';
const OFFLINE_PLAYLIST_SUFFIX = '/playlist.m3u8';
const OFFLINE_SEGMENT_DIRECTORY = '/segments/';
const SEGMENT_FILE_PREFIX = 'segment-';
const SEGMENT_FILE_EXTENSION = '.ts';
const NAVIGATE_FALLBACK_DENYLIST = [/^\/api/, /^\/cdn-cgi/];

// ***** Service Worker ライフサイクル制御 *****

self.addEventListener('install', (event) => {
    // 新しいサービスワーカーが検出された時点で即座にアクティブ化できるよう skipWaiting()
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    // 既存クライアントへの制御を奪い、旧キャッシュを片付ける
    event.waitUntil((async () => {
        await self.clients.claim();
        await cleanupOutdatedCaches();
    })());
});

// Workbox によるプリキャッシュ。__WB_MANIFEST は VitePWA がビルド時に挿入する
precacheAndRoute(self.__WB_MANIFEST);

// SPA でのルーティング: /api/, /cdn-cgi/ 以外のナビゲーションリクエストは index.html を返す
registerRoute(new NavigationRoute(
    createHandlerBoundToURL('/index.html'),
    {
        denylist: NAVIGATE_FALLBACK_DENYLIST,
    }
));

// ***** メッセージハンドラ *****

self.addEventListener('message', (event) => {
    // 新バージョン適用リクエスト (registerType: 'prompt' で利用)
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
        return;
    }
});

// ***** Fetch ルーティング *****

self.addEventListener('fetch', (event) => {
    // 同一オリジンの /offline/streams/ に対するリクエストのみを捕捉
    const requestURL = new URL(event.request.url);
    if (requestURL.origin !== self.location.origin) {
        return;
    }
    if (requestURL.pathname.startsWith(OFFLINE_STREAM_BASE_PATH) === false) {
        return;
    }

    // HLS プレイリスト or セグメントのどちらかを判定
    if (requestURL.pathname.endsWith(OFFLINE_PLAYLIST_SUFFIX) === true) {
        const downloadId = requestURL.pathname
            .slice(OFFLINE_STREAM_BASE_PATH.length, -OFFLINE_PLAYLIST_SUFFIX.length);
        event.respondWith(handleOfflinePlaylistRequest(downloadId));
        return;
    }

    if (requestURL.pathname.includes(OFFLINE_SEGMENT_DIRECTORY) === true) {
        const {downloadId, sequence} = parseSegmentRequest(requestURL.pathname);
        if (downloadId !== null && sequence !== null) {
            event.respondWith(handleOfflineSegmentRequest(downloadId, sequence));
            return;
        }
    }

    // パターンにマッチしないオフラインストリームパスは 404 を返す
    event.respondWith(new Response('Offline stream path not recognized.', {status: 404}));
});

// ***** オフラインデータ応答ロジック *****

async function handleOfflinePlaylistRequest(downloadId: string): Promise<Response> {
    try {
        const metadata = await getDownloadMetadata(downloadId);
        if (metadata === null) {
            return new Response('Offline playlist metadata not found.', {status: 404});
        }
        const playlist = await OfflineStorage.readPlaylist(metadata);
        if (playlist === null) {
            return new Response('Offline playlist data not available.', {status: 404});
        }
        return new Response(playlist, {
            headers: {
                'Content-Type': 'application/vnd.apple.mpegurl',
                'Cache-Control': 'no-store',
            },
        });
    } catch (error) {
        console.warn('[ServiceWorker][handleOfflinePlaylistRequest] Failed to serve offline playlist.', error);
        return new Response('Failed to serve offline playlist.', {status: 500});
    }
}

async function handleOfflineSegmentRequest(downloadId: string, sequence: number): Promise<Response> {
    try {
        const metadata = await getDownloadMetadata(downloadId);
        if (metadata === null) {
            return new Response('Offline segment metadata not found.', {status: 404});
        }
        const buffer = await OfflineStorage.readSegment(metadata, sequence);
        if (buffer === null) {
            return new Response('Offline segment not available.', {status: 404});
        }
        return new Response(buffer, {
            headers: {
                'Content-Type': 'video/mp2t',
                'Cache-Control': 'no-store',
            },
        });
    } catch (error) {
        console.warn('[ServiceWorker][handleOfflineSegmentRequest] Failed to serve offline segment.', error);
        return new Response('Failed to serve offline segment.', {status: 500});
    }
}

// ***** ユーティリティ *****

async function getDownloadMetadata(downloadId: string): Promise<OfflineDownloadMetadata | null> {
    try {
        const metadata = await OfflineStorage.getMetadata(downloadId);
        if (metadata === undefined) {
            return null;
        }
        return metadata;
    } catch (error) {
        console.warn('[ServiceWorker][getDownloadMetadata] Failed to read metadata.', error);
        return null;
    }
}

function parseSegmentRequest(pathname: string): {downloadId: string | null; sequence: number | null;} {
    // パス形式: /offline/streams/{id}/segments/segment-XXXXXXXX.ts
    const segmentIndex = pathname.indexOf(OFFLINE_SEGMENT_DIRECTORY);
    if (segmentIndex === -1) {
        return {downloadId: null, sequence: null};
    }
    const downloadId = pathname.slice(OFFLINE_STREAM_BASE_PATH.length, segmentIndex);
    const segmentFilename = pathname.slice(segmentIndex + OFFLINE_SEGMENT_DIRECTORY.length);
    if (segmentFilename.startsWith(SEGMENT_FILE_PREFIX) === false ||
        segmentFilename.endsWith(SEGMENT_FILE_EXTENSION) === false) {
        return {downloadId: null, sequence: null};
    }
    const sequenceString = segmentFilename
        .slice(SEGMENT_FILE_PREFIX.length, -SEGMENT_FILE_EXTENSION.length)
        .replace(/^0+/, '') || '0';
    const sequence = Number.parseInt(sequenceString, 10);
    if (Number.isNaN(sequence)) {
        return {downloadId: null, sequence: null};
    }
    return {downloadId, sequence};
}

export {}; // このファイルをモジュール扱いにするためのダミーエクスポート
