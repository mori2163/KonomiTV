<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="offline-container-wrapper">
                <SPHeaderBar />
                <div class="offline-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'オフライン保存', path: '/offline/', disabled: true },
                    ]" />
                    <section class="offline-toolbar">
                        <div class="offline-toolbar__headline">
                            <h1>オフライン保存</h1>
                            <v-chip size="small" color="primary" variant="tonal">
                                合計 {{ offlineStore.downloads.length }} 件
                            </v-chip>
                        </div>
                        <div class="offline-toolbar__actions">
                            <v-text-field
                                v-model="searchQuery"
                                placeholder="番組を検索..."
                                density="comfortable"
                                variant="outlined"
                                hide-details
                                clearable
                                class="offline-toolbar__search"
                                bg-color="background-lighten-1"
                            >
                                <template #prepend-inner>
                                    <Icon icon="fluent:search-12-regular" width="18" class="text-text-darken-1" />
                                </template>
                            </v-text-field>
                            <v-select
                                v-model="sortOrder"
                                :items="sortOptions"
                                item-title="title"
                                item-value="value"
                                hide-details
                                density="comfortable"
                                variant="solo"
                                bg-color="background-lighten-1"
                                class="offline-toolbar__sort"
                            />
                            <v-btn
                                size="small"
                                variant="text"
                                color="primary"
                                :loading="isRefreshing"
                                :disabled="isRefreshing"
                                @click="refreshDownloads"
                            >
                                <Icon icon="fluent:arrow-sync-12-regular" width="18" class="mr-1" />
                                再読み込み
                            </v-btn>
                        </div>
                    </section>
                    <section v-if="offlineStore.initialization_error" class="offline-alert">
                        <v-alert type="error" variant="tonal">
                            {{ offlineStore.initialization_error }}
                        </v-alert>
                    </section>
                    <section v-if="filteredDownloads.length > 0" class="offline-summary">
                        <Icon icon="fluent:database-20-regular" width="18" class="mr-2" />
                        <span>ストレージ使用量: {{ storageUsageText }}</span>
                    </section>
                    <section class="offline-list">
                        <div v-if="isLoading" class="offline-list__loading">
                            <v-progress-circular indeterminate size="36" color="primary" />
                        </div>
                        <template v-else>
                            <div v-if="filteredDownloads.length > 0" class="offline-list__grid">
                                <article
                                    v-for="download in filteredDownloads"
                                    :key="download.id"
                                    class="offline-download-card"
                                >
                                    <div class="offline-download-card__header">
                                        <div class="offline-download-card__thumbnail">
                                            <!-- サムネイルがあれば表示、なければプレースホルダー -->
                                            <img
                                                v-if="getThumbnailUrl(download)"
                                                :src="getThumbnailUrl(download)!"
                                                alt="サムネイル"
                                                class="offline-download-card__thumbnail-image"
                                            />
                                            <div v-else class="offline-download-card__thumbnail-placeholder">
                                                <Icon icon="fluent:video-20-regular" width="42" />
                                            </div>
                                            <span class="offline-download-card__duration">
                                                {{ formatDuration(calculateActualDuration(download)) }}
                                            </span>
                                            <div
                                                v-if="download.status === 'downloading'"
                                                class="offline-download-card__thumbnail-status offline-download-card__thumbnail-status--downloading"
                                            >
                                                <Icon
                                                    icon="fluent:arrow-download-16-regular"
                                                    width="16"
                                                    height="16"
                                                    class="offline-download-card__thumbnail-status-icon offline-download-card__thumbnail-status-icon--spin"
                                                />
                                                <span>
                                                    {{ formatStatus(download.status) }}
                                                    ({{ calcProgressPercent(download) }}%)
                                                </span>
                                            </div>
                                            <div
                                                v-else-if="download.status === 'completed'"
                                                class="offline-download-card__thumbnail-status offline-download-card__thumbnail-status--completed"
                                            >
                                                <Icon
                                                    icon="fluent:checkmark-circle-16-regular"
                                                    width="16"
                                                    height="16"
                                                    class="offline-download-card__thumbnail-status-icon"
                                                />
                                                <span>{{ formatStatus(download.status) }}</span>
                                            </div>
                                            <div
                                                v-else-if="download.status === 'paused'"
                                                class="offline-download-card__thumbnail-status offline-download-card__thumbnail-status--paused"
                                            >
                                                <Icon
                                                    icon="fluent:pause-16-regular"
                                                    width="16"
                                                    height="16"
                                                    class="offline-download-card__thumbnail-status-icon"
                                                />
                                                <span>{{ formatStatus(download.status) }}</span>
                                            </div>
                                            <div
                                                v-else-if="download.status === 'error'"
                                                class="offline-download-card__thumbnail-status offline-download-card__thumbnail-status--error"
                                            >
                                                <Icon
                                                    icon="fluent:error-circle-16-regular"
                                                    width="16"
                                                    height="16"
                                                    class="offline-download-card__thumbnail-status-icon"
                                                />
                                                <span>{{ formatStatus(download.status) }}</span>
                                            </div>
                                            <div
                                                v-if="download.status === 'downloading'"
                                                class="offline-download-card__thumbnail-progress"
                                            >
                                                <div
                                                    class="offline-download-card__thumbnail-progress-bar"
                                                    :style="`width: ${calcProgressPercent(download)}%`"
                                                ></div>
                                            </div>
                                        </div>
                                        <v-btn
                                            variant="tonal"
                                            color="primary"
                                            size="small"
                                            class="offline-download-card__play"
                                            :disabled="download.status !== 'completed'"
                                            @click="handlePlay(download)"
                                        >
                                            <Icon icon="fluent:play-16-regular" width="18" class="mr-1" />
                                            再生
                                        </v-btn>
                                    </div>
                                    <div class="offline-download-card__body">
                                        <h2 class="offline-download-card__title">
                                            {{ download.recorded_program.title }}
                                        </h2>
                                        <div class="offline-download-card__meta">
                                            <span>{{ formatProgramTime(download.recorded_program.start_time, download.recorded_program.end_time) }}</span>
                                            <span>・{{ download.recorded_program.channel_name }}</span>
                                        </div>
                                        <div class="offline-download-card__chips">
                                            <v-chip size="x-small" variant="tonal">
                                                {{ formatQualityLabel(download.quality as VideoStreamingQuality) }}
                                            </v-chip>
                                            <v-chip size="x-small" variant="tonal">
                                                {{ download.is_hevc ? 'HEVC' : 'H.264' }}
                                            </v-chip>
                                            <v-chip size="x-small" variant="tonal">
                                                {{ download.save_comments ? 'コメントあり' : 'コメントなし' }}
                                            </v-chip>
                                        </div>
                                        <div
                                            v-if="download.status === 'downloading'"
                                            class="offline-download-card__progress"
                                        >
                                            <v-progress-linear
                                                :model-value="calcProgressPercent(download)"
                                                height="8"
                                                rounded
                                                color="primary"
                                            />
                                            <div class="offline-download-card__progress-text">
                                                <span>{{ formatSegmentProgress(download) }} ({{ calcProgressPercent(download) }}%)</span>
                                                <span>{{ formatByteProgress(download) }}</span>
                                            </div>
                                            <div
                                                v-if="formatEstimatedTime(download)"
                                                class="offline-download-card__progress-time"
                                            >
                                                推定残り時間: {{ formatEstimatedTime(download) }}
                                            </div>
                                        </div>
                                        <p
                                            v-if="download.recorded_program.description"
                                            class="offline-download-card__description"
                                        >
                                            {{ download.recorded_program.description }}
                                        </p>
                                    </div>
                                    <div class="offline-download-card__footer">
                                        <div class="offline-download-card__info">
                                            <span>サイズ: {{ formatSize(download) }}</span>
                                            <span>更新: {{ formatDate(download.updated_at) }}</span>
                                        </div>
                                        <div class="offline-download-card__footer-actions">
                                            <v-btn
                                                size="small"
                                                variant="outlined"
                                                color="primary"
                                                class="offline-download-card__action"
                                                @click="openRedownloadDialog(download)"
                                            >
                                                <Icon icon="fluent:arrow-clockwise-16-regular" width="16" class="mr-1" />
                                                再獲得
                                            </v-btn>
                                            <v-btn
                                                size="small"
                                                variant="text"
                                                color="error"
                                                class="offline-download-card__action"
                                                :loading="isDeletingId === download.id"
                                                @click="removeDownload(download)"
                                            >
                                                <Icon icon="fluent:delete-20-regular" width="18" class="mr-1" />
                                                削除
                                            </v-btn>
                                        </div>
                                    </div>
                                </article>
                            </div>
                            <div v-else class="offline-list__empty">
                                <Icon icon="fluent:arrow-download-24-regular" width="42" />
                                <p>まだオフライン保存した番組がありません。</p>
                                <p>録画番組の詳細から「オフライン保存」を選択してください。</p>
                            </div>
                        </template>
                    </section>
                </div>
            </div>
        </main>
    </div>

    <v-dialog v-model="redownloadDialog" max-width="420">
        <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
                再獲得の設定
            </v-card-title>
            <v-card-text>
                <p class="offline-dialog__description">
                    保存する画質とオプションを選択してください。既存のデータを削除して再度ダウンロードします。
                </p>
                <v-select
                    v-model="selectedQuality"
                    :items="qualityOptions"
                    item-title="label"
                    item-value="value"
                    label="保存する画質"
                    density="comfortable"
                    variant="outlined"
                />
                <v-switch
                    v-model="useHevc"
                    class="mt-2"
                    color="primary"
                    hide-details
                    inset
                    :disabled="!hevcSupported"
                    :label="hevcSupported ? 'HEVC (H.265) を使用する' : 'HEVC (H.265) を使用できません'"
                />
                <p class="offline-dialog__hint" :class="{'offline-dialog__hint--disabled': !hevcSupported}">
                    HEVC は同じ画質でもファイルサイズを抑えられますが、非対応端末では再生できません。
                </p>
                <v-switch
                    v-model="saveComments"
                    class="mt-3"
                    color="primary"
                    hide-details
                    inset
                    :label="saveComments ? 'コメントも保存する' : 'コメントは保存しない'"
                />
                <p class="offline-dialog__hint offline-dialog__hint--secondary">
                    コメントを保存すると、オフライン再生時に実況コメントを確認できます。
                </p>
            </v-card-text>
            <v-card-actions class="justify-end">
                <v-btn variant="text" :disabled="isProcessingRedownload" @click="resetRedownloadDialog()">
                    キャンセル
                </v-btn>
                <v-btn
                    variant="flat"
                    color="primary"
                    :loading="isProcessingRedownload"
                    @click="confirmRedownload"
                >
                    再獲得を開始
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>
<script lang="ts" setup>

import { Icon } from '@iconify/vue';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import type { OfflineDownloadMetadata, OfflineDownloadProgressUpdate } from '@/offline/types';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import Message from '@/message';
import OfflineDownloadManager from '@/offline/manager';
import OfflineStorage from '@/offline/storage';
import Videos from '@/services/Videos';
import useOfflineStore from '@/stores/OfflineStore';
import useSettingsStore, { VIDEO_STREAMING_QUALITIES, type VideoStreamingQuality } from '@/stores/SettingsStore';
import useUserStore from '@/stores/UserStore';
import Utils, { PlayerUtils, dayjs } from '@/utils';

const offlineStore = useOfflineStore();
const settingsStore = useSettingsStore();
const userStore = useUserStore();
const router = useRouter();

const isLoading = ref(true);
const isRefreshing = ref(false);
const sortOrder = ref<'newest' | 'oldest' | 'downloading' | 'completed'>('newest');
const searchQuery = ref('');
const redownloadDialog = ref(false);
const redownloadTarget = ref<OfflineDownloadMetadata | null>(null);
const selectedQuality = ref<VideoStreamingQuality>(settingsStore.settings.video_streaming_quality);
const useHevc = ref(false);
const saveComments = ref(true);
const isProcessingRedownload = ref(false);
const isDeletingId = ref<string | null>(null);
const thumbnailUrls = ref<Map<string, string>>(new Map());
const storageEstimate = ref<{usage: number; quota: number} | null>(null);

const hevcSupported = computed(() => PlayerUtils.isHEVCVideoSupported());

const sortOptions = [
    { title: '新しい順', value: 'newest' },
    { title: '古い順', value: 'oldest' },
    { title: 'ダウンロード中', value: 'downloading' },
] as const;

const formatQualityLabel = (quality: VideoStreamingQuality): string => {
    switch (quality) {
        case '1080p-60fps':
            return '1080p (60fps)';
        case '1080p':
            return '1080p';
        case '810p':
            return '810p';
        case '720p':
            return '720p';
        case '540p':
            return '540p';
        case '480p':
            return '480p';
        case '360p':
            return '360p';
        case '240p':
            return '240p';
        default:
            return quality;
    }
};

const qualityOptions = VIDEO_STREAMING_QUALITIES.map((quality) => ({
    label: formatQualityLabel(quality),
    value: quality,
}));

const ensureOfflineReady = async (): Promise<boolean> => {
    if (offlineStore.initialized === false) {
        await offlineStore.initialize();
    }
    if (offlineStore.initialization_error !== null) {
        Message.error(offlineStore.initialization_error);
        return false;
    }
    return true;
};

const filteredDownloads = computed(() => {
    let list = [...offlineStore.downloads];
    const keyword = searchQuery.value.trim().toLowerCase();
    if (keyword.length > 0) {
        list = list.filter((download) => {
            const text = [
                download.recorded_program.title,
                download.recorded_program.description,
                download.recorded_program.channel_name,
            ].join(' ').toLowerCase();
            return text.includes(keyword);
        });
    }
    switch (sortOrder.value) {
        case 'newest':
            return list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        case 'oldest':
            return list.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
        case 'downloading':
            return list
                .filter(item => item.status === 'downloading')
                .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        case 'completed':
            return list
                .filter(item => item.status === 'completed')
                .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        default:
            return list;
    }
});

const totalStorageText = computed(() => {
    const total = offlineStore.downloads.reduce((sum, download) => sum + download.downloaded_bytes, 0);
    return Utils.formatBytes(total);
});

const storageUsageText = computed(() => {
    const total = offlineStore.downloads.reduce((sum, download) => sum + download.downloaded_bytes, 0);
    if (storageEstimate.value === null || storageEstimate.value.quota === 0) {
        return Utils.formatBytes(total);
    }
    const usageText = Utils.formatBytes(storageEstimate.value.usage);
    const quotaText = Utils.formatBytes(storageEstimate.value.quota);
    return `${usageText} / ${quotaText}`;
});

const getProgress = (download: OfflineDownloadMetadata): OfflineDownloadProgressUpdate | undefined => {
    return offlineStore.progress[download.id];
};

const calcProgressPercent = (download: OfflineDownloadMetadata): number => {
    if (download.status === 'completed') {
        return 100;
    }
    const progress = getProgress(download);
    if (progress === undefined || progress.total_segments === 0) {
        return 0;
    }
    return Math.min(100, Math.round((progress.downloaded_segments / progress.total_segments) * 100));
};

const formatSegmentProgress = (download: OfflineDownloadMetadata): string => {
    const progress = getProgress(download);
    const totalSegments = progress?.total_segments ?? download.segment_count;
    if (totalSegments === 0) {
        return '';
    }
    const current = progress?.downloaded_segments ?? (download.status === 'completed' ? totalSegments : 0);
    return `${current} / ${totalSegments} セグメント`;
};

const formatByteProgress = (download: OfflineDownloadMetadata): string => {
    const progress = getProgress(download);
    const downloadedBytes = progress?.downloaded_bytes ?? download.downloaded_bytes;
    const totalBytes = progress?.total_bytes_estimated ?? download.total_size;
    const totalText = totalBytes > 0 ? Utils.formatBytes(totalBytes) : '--';
    return `${Utils.formatBytes(downloadedBytes)} / ${totalText}`;
};

const formatSize = (download: OfflineDownloadMetadata): string => {
    return Utils.formatBytes(download.downloaded_bytes);
};

const formatStatus = (status: OfflineDownloadMetadata['status']): string => {
    switch (status) {
        case 'downloading':
            return 'ダウンロード中';
        case 'completed':
            return '保存済み';
        case 'paused':
            return '停止中';
        case 'error':
            return 'エラー';
        default:
            return status;
    }
};

const formatProgramTime = (start: string, end: string): string => {
    const startTime = dayjs(start);
    const endTime = dayjs(end);
    return `${startTime.format('YYYY/MM/DD HH:mm')} - ${endTime.format('HH:mm')}`;
};

const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
        return `${hours}時間${minutes}分`;
    }
    return `${minutes}分`;
};

// 実際の録画時間を計算する (セグメントの合計時間から算出)
const calculateActualDuration = (download: OfflineDownloadMetadata): number => {
    // セグメント情報がある場合は、セグメントの合計時間を使用
    if (download.segments && download.segments.length > 0) {
        const totalDuration = download.segments.reduce((sum, segment) => sum + segment.duration, 0);
        return Math.round(totalDuration);
    }
    // セグメント情報がない場合は recorded_program.duration をフォールバック
    return download.recorded_program.duration;
};

const formatDate = (iso: string): string => {
    return dayjs(iso).format('YYYY/MM/DD HH:mm');
};

const formatEstimatedTime = (download: OfflineDownloadMetadata): string | null => {
    const progress = getProgress(download);
    if (progress === undefined || progress.estimated_remaining_time === undefined) {
        return null;
    }
    const seconds = Math.ceil(progress.estimated_remaining_time / 1000);
    if (seconds < 60) {
        return `約 ${seconds} 秒`;
    }
    const minutes = Math.ceil(seconds / 60);
    if (minutes < 60) {
        return `約 ${minutes} 分`;
    }
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (remainingMinutes === 0) {
        return `約 ${hours} 時間`;
    }
    return `約 ${hours} 時間 ${remainingMinutes} 分`;
};

const handlePlay = (download: OfflineDownloadMetadata): void => {
    if (download.status !== 'completed') {
        Message.info('ダウンロードが完了すると再生できます。');
        return;
    }
    router.push({ path: `/offline/watch/${download.id}` }).catch(() => undefined);
};

const openRedownloadDialog = (download: OfflineDownloadMetadata): void => {
    redownloadTarget.value = download;
    selectedQuality.value = download.quality as VideoStreamingQuality;
    useHevc.value = hevcSupported.value && download.is_hevc;
    saveComments.value = download.save_comments ?? true;
    redownloadDialog.value = true;
};

const resetRedownloadDialog = (): void => {
    redownloadDialog.value = false;
    redownloadTarget.value = null;
    isProcessingRedownload.value = false;
};

const confirmRedownload = async (): Promise<void> => {
    const target = redownloadTarget.value;
    if (target === null) {
        return;
    }
    const ready = await ensureOfflineReady();
    if (!ready) {
        return;
    }
    isProcessingRedownload.value = true;
    try {
        const recordedProgram = await Videos.fetchVideo(target.video_id);
        if (recordedProgram === null) {
            Message.error('録画番組情報を取得できませんでした。');
            return;
        }
        if (target.status === 'downloading') {
            OfflineDownloadManager.cancelDownload(target.id);
        }
        await OfflineStorage.removeDownload(target);
        offlineStore.removeDownload(target.id);
        await offlineStore.refreshDownloads();
        resetRedownloadDialog();
        await OfflineDownloadManager.startDownload(recordedProgram, {
            quality: selectedQuality.value,
            isHevc: useHevc.value,
            saveComments: saveComments.value,
        });
    } catch (error) {
        console.error('[OfflineIndex] Failed to re-download offline data.', error);
        // エラーはマネージャー側で通知されるため、ここでは追加の通知は不要
    } finally {
        isProcessingRedownload.value = false;
    }
};

const removeDownload = async (download: OfflineDownloadMetadata): Promise<void> => {
    if (window.confirm('オフライン保存したデータを削除しますか？') === false) {
        return;
    }
    const ready = await ensureOfflineReady();
    if (!ready) {
        return;
    }
    if (download.status === 'downloading') {
        OfflineDownloadManager.cancelDownload(download.id);
    }
    isDeletingId.value = download.id;
    try {
        await OfflineStorage.removeDownload(download);
        offlineStore.removeDownload(download.id);
        await offlineStore.refreshDownloads();
        Message.success('オフラインデータを削除しました。');
    } catch (error) {
        console.error('[OfflineIndex] Failed to remove offline data.', error);
        Message.error('オフラインデータの削除に失敗しました。');
    } finally {
        isDeletingId.value = null;
    }
};

const refreshDownloads = async (): Promise<void> => {
    const ready = await ensureOfflineReady();
    if (!ready) {
        return;
    }
    isRefreshing.value = true;
    try {
        await offlineStore.refreshDownloads();
        await loadThumbnails();
        await updateStorageEstimate();
    } finally {
        isRefreshing.value = false;
    }
};

const updateStorageEstimate = async (): Promise<void> => {
    try {
        storageEstimate.value = await OfflineStorage.getStorageEstimate();
    } catch (error) {
        console.warn('[OfflineIndex] Failed to get storage estimate.', error);
        storageEstimate.value = null;
    }
};

const loadThumbnails = async (): Promise<void> => {
    // 既存のサムネイルURLを解放
    for (const url of thumbnailUrls.value.values()) {
        URL.revokeObjectURL(url);
    }
    thumbnailUrls.value.clear();

    // 各ダウンロードのサムネイルをロード
    for (const download of offlineStore.downloads) {
        if (download.has_thumbnail === true) {
            try {
                const dataUrl = await OfflineStorage.getThumbnailDataUrl(download.id);
                if (dataUrl !== null) {
                    thumbnailUrls.value.set(download.id, dataUrl);
                }
            } catch (error) {
                console.warn(`[OfflineIndex] Failed to load thumbnail for ${download.id}`, error);
            }
        }
    }
};

const getThumbnailUrl = (download: OfflineDownloadMetadata): string | null => {
    return thumbnailUrls.value.get(download.id) ?? null;
};

onMounted(async () => {
    await userStore.fetchUser();
    const ready = await ensureOfflineReady();
    if (ready) {
        await offlineStore.refreshDownloads();
        await loadThumbnails();
        await updateStorageEstimate();
    }
    if (hevcSupported.value === true) {
        useHevc.value = settingsStore.settings.video_data_saver_mode === true;
    }
    isLoading.value = false;
});

</script>
<style lang="scss" scoped>

.offline-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.offline-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    margin: 0 auto;
    padding: 20px;
    min-width: 0;
    max-width: 1000px;
    @include smartphone-horizontal {
        padding: 16px 20px !important;
    }
    @include smartphone-horizontal-short {
        padding: 16px 16px !important;
    }
    @include smartphone-vertical {
        padding: 12px 8px !important;
    }
}

.offline-toolbar {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 20px;

    &__headline {
        display: flex;
        align-items: center;
        gap: 12px;

        h1 {
            font-size: 26px;
            font-weight: 700;
        }
    }

    &__actions {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }

    &__search {
        flex: 1 1 260px;
        min-width: 220px;
    }

    &__sort {
        width: 160px;
        :deep(.v-field__input) {
            padding-top: 6px !important;
            padding-bottom: 6px !important;
        }
    }
}

.offline-alert {
    margin-bottom: 16px;
}

.offline-summary {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    color: rgb(var(--v-theme-text-darken-1));
}

.offline-list {
    display: flex;
    flex-direction: column;
    gap: 12px;

    &__loading {
        display: flex;
        justify-content: center;
        padding: 48px 0;
    }

    &__grid {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    &__empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        min-height: 200px;
        padding: 60px 16px;
        border-radius: 8px;
        background: rgb(var(--v-theme-background-lighten-1));
        text-align: center;

        :deep(.iconify) {
            color: rgb(var(--v-theme-text-darken-1));
            width: 54px;
            height: 54px;
        }

        p {
            margin: 0;
            line-height: 1.6;
            &:first-of-type {
                font-size: 19px;
                font-weight: 600;
                color: rgb(var(--v-theme-text));
                @include smartphone-vertical {
                    font-size: 18px;
                }
            }
            &:last-of-type {
                margin-top: 4px;
                font-size: 15px;
                color: rgb(var(--v-theme-text-darken-1));
                @include smartphone-vertical {
                    font-size: 13px;
                    line-height: 1.65;
                }
            }
        }
    }
}

.offline-download-card {
    display: flex;
    flex-direction: column;
    padding: 16px;
    border-radius: 16px;
    background: rgb(var(--v-theme-background-lighten-1));
    box-shadow: 0 12px 30px -24px rgba(0, 0, 0, 0.6);
    gap: 16px;

    &__header {
        display: flex;
        align-items: flex-start;
        gap: 16px;
        flex-wrap: wrap;
    }

    &__thumbnail {
        position: relative;
        width: 200px;
        aspect-ratio: 16 / 9;
        border-radius: 12px;
        overflow: hidden;
        background: rgba(0, 0, 0, 0.4);
        flex-shrink: 0;

        @include smartphone-vertical {
            width: 160px;
        }
    }

    &__thumbnail-image {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }

    &__thumbnail-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: rgba(255, 255, 255, 0.5);
        background: rgba(0, 0, 0, 0.6);
    }

    &__duration {
        position: absolute;
        right: 8px;
        bottom: 8px;
        padding: 4px 6px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        color: #fff;
        background: rgba(0, 0, 0, 0.7);
    }

    &__thumbnail-status {
        position: absolute;
        left: 12px;
        top: 12px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        color: #fff;
        background: rgba(0, 0, 0, 0.65);
        backdrop-filter: blur(8px);
        box-shadow: 0 12px 26px -18px rgba(0, 0, 0, 0.9);

        &--downloading {
            background: rgba(var(--v-theme-primary), 0.9);
        }

        &--completed {
            background: rgba(76, 175, 80, 0.9);
        }

        &--paused {
            background: rgba(255, 193, 7, 0.92);
            color: #2b2110;
        }

        &--error {
            background: rgba(244, 67, 54, 0.92);
        }
    }

    &__thumbnail-status-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }

    &__thumbnail-status-icon--spin {
        animation: offline-download-card-spin 1.1s linear infinite;
    }

    &__thumbnail-progress {
        position: absolute;
        left: 0;
        bottom: 0;
        width: 100%;
        height: 6px;
        background: rgba(0, 0, 0, 0.35);
        backdrop-filter: blur(6px);
    }

    &__thumbnail-progress-bar {
        width: 0;
        height: 100%;
        background: linear-gradient(90deg, rgba(var(--v-theme-primary), 1), rgba(var(--v-theme-primary), 0.45));
        transition: width 0.25s ease;
    }

    &__play {
        margin-left: auto;
        @include smartphone-vertical {
            margin-top: 8px;
        }
    }

    &__body {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    &__title {
        font-size: 19px;
        font-weight: 700;
        line-height: 1.4;
        margin: 0;
    }

    &__meta {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }

    &__progress {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin-top: 4px;

        :deep(.v-progress-linear) {
            border-radius: 6px;
        }
    }

    &__progress-text {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        color: rgb(var(--v-theme-text-darken-1));
        @include smartphone-vertical {
            flex-direction: column;
            gap: 4px;
        }
    }

    &__progress-time {
        font-size: 12px;
        color: rgb(var(--v-theme-primary));
        font-weight: 600;
        text-align: center;
        margin-top: 2px;
    }

    &__description {
        margin: 0;
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
        line-height: 1.6;
    }

    &__footer {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding-top: 12px;
        border-top: 1px solid rgb(var(--v-theme-background-lighten-2));
    }

    &__info {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__footer-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }

    &__action {
        @include smartphone-vertical {
            flex: 1 1 100px;
        }
    }
}

.offline-dialog__description {
    margin-bottom: 16px;
    font-size: 14px;
    line-height: 1.6;
    color: rgb(var(--v-theme-text-darken-1));
}

.offline-dialog__hint {
    margin-top: 8px;
    font-size: 12px;
    color: rgb(var(--v-theme-text-darken-1));
    line-height: 1.5;

    &--disabled {
        opacity: 0.6;
    }

    &--secondary {
        color: rgba(var(--v-theme-text-darken-1), 0.85);
    }
}

@keyframes offline-download-card-spin {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

</style>