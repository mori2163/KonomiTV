<template>
    <v-dialog :model-value="modelValue" max-width="720" @update:model-value="emit('update:modelValue', $event)">
        <v-card>
            <v-card-title class="d-flex align-center pt-6 pb-3 px-6 font-weight-bold">
                <Icon icon="fluent:cloud-download-20-regular" width="24px" />
                <span class="ml-2">オフラインに保存</span>
            </v-card-title>
            <v-card-text class="px-6 pb-2">
                <div class="offline-download-dialog__program">
                    <div class="offline-download-dialog__program-title">{{ program.title }}</div>
                    <div class="offline-download-dialog__program-time">{{ ProgramUtils.getProgramTime(program) }}</div>
                </div>

                <v-select
                    v-model="quality"
                    :items="quality_items"
                    item-title="title"
                    item-value="value"
                    label="画質"
                    variant="outlined"
                    color="primary"
                    density="comfortable"
                    class="mt-5"
                    hide-details
                >
                </v-select>
                <v-select
                    v-model="codec"
                    :items="codec_items"
                    item-title="title"
                    item-value="value"
                    label="コーデック"
                    variant="outlined"
                    color="primary"
                    density="comfortable"
                    class="mt-4"
                    hide-details
                >
                </v-select>
                <v-switch
                    v-model="include_comments"
                    color="primary"
                    class="mt-4"
                    density="comfortable"
                    hide-details
                    inset
                    label="ニコニコ実況過去ログを保存する"
                >
                </v-switch>

                <div class="offline-download-dialog__summary mt-4">
                    <div class="offline-download-dialog__summary-item">
                        <span>推定サイズ:</span>
                        <span class="font-weight-bold">{{ estimated_size_text }}</span>
                    </div>
                    <div class="offline-download-dialog__summary-item">
                        <span>空き容量:</span>
                        <span class="font-weight-bold">
                            <template v-if="storage_estimate !== null">{{ free_storage_text }}</template>
                            <template v-else>取得中…</template>
                        </span>
                    </div>
                </div>
                <div v-if="is_other_downloading" class="text-warning mt-2">
                    他の番組のダウンロード中です。完了または一時停止後に開始できます。
                </div>
                <div v-if="is_storage_insufficient" class="text-error mt-2">
                    ストレージ容量が不足しています。画質を下げるか不要なオフラインデータを削除してください。
                </div>
            </v-card-text>
            <v-card-actions class="px-6 pt-2 pb-5">
                <v-spacer></v-spacer>
                <v-btn color="text" variant="text" @click="emit('update:modelValue', false)">
                    <Icon icon="fluent:dismiss-20-regular" width="18px" height="18px" />
                    <span class="ml-1">キャンセル</span>
                </v-btn>
                <v-btn
                    color="primary"
                    variant="flat"
                    :disabled="is_start_disabled"
                    @click="startDownload"
                >
                    <Icon icon="fluent:arrow-download-20-regular" width="18px" height="18px" />
                    <span class="ml-1">ダウンロード開始</span>
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">

import { computed, ref, watch } from 'vue';

import type { IRecordedProgram } from '@/services/Videos';

import Message from '@/message';
import useOfflineManagerStore from '@/stores/OfflineManagerStore';
import useSettingsStore, { VIDEO_STREAMING_QUALITIES } from '@/stores/SettingsStore';
import Utils, { PlayerUtils, ProgramUtils } from '@/utils';

// Props
const props = defineProps<{
    modelValue: boolean;
    program: IRecordedProgram;
}>();

// Emits
const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
}>();

// Store
const settingsStore = useSettingsStore();
const offlineManagerStore = useOfflineManagerStore();

// ダウンロード設定
// もし設定値が現在の選択肢に含まれていない場合は 1080p にフォールバックする
const initial_quality = VIDEO_STREAMING_QUALITIES.includes(settingsStore.settings.video_streaming_quality)
    ? settingsStore.settings.video_streaming_quality
    : '1080p';
const quality = ref(initial_quality);
const codec = ref<'H.264' | 'H.265'>(PlayerUtils.isHEVCVideoSupported() && settingsStore.settings.video_data_saver_mode ? 'H.265' : 'H.264');
const include_comments = ref(true);

// ストレージ情報
const storage_estimate = ref<{
    usage: number;
    quota: number;
    available: number;
} | null>(null);

// 選択可能な画質候補
const quality_items = computed(() => {
    return VIDEO_STREAMING_QUALITIES.map((quality_name) => ({
        title: quality_name === '1080p-60fps' ? '1080p (60fps)' : quality_name,
        value: quality_name,
    }));
});

// 選択可能なコーデック候補
const codec_items = computed(() => {
    const items: Array<{ title: string; value: 'H.264' | 'H.265'; }> = [
        { title: 'H.264', value: 'H.264' },
    ];
    if (PlayerUtils.isHEVCVideoSupported() === true) {
        items.push({ title: 'H.265', value: 'H.265' });
    }
    return items;
});

// API に渡す画質 ID
const selected_api_quality = computed(() => {
    return codec.value === 'H.265' ? `${quality.value}-hevc` : quality.value;
});

// 推定サイズ計算に利用する画質ごとのビットレート (Mbps)
const bitrate_map = {
    '1080p-60fps': { 'H.264': 14.0, 'H.265': 6.8 },
    '1080p': { 'H.264': 9.5, 'H.265': 4.3 },
    '810p': { 'H.264': 6.8, 'H.265': 3.2 },
    '720p': { 'H.264': 4.5, 'H.265': 2.0 },
    '540p': { 'H.264': 3.0, 'H.265': 1.45 },
    '480p': { 'H.264': 2.0, 'H.265': 1.05 },
    '360p': { 'H.264': 1.1, 'H.265': 0.65 },
    '240p': { 'H.264': 0.6, 'H.265': 0.38 },
} as const;

// 推定サイズ (bytes)
const estimated_size_bytes = computed(() => {
    // quality.value が bitrate_map に存在しない場合は 0 を返す
    // 基本的に初期化時にバリデーションしているため、ここには到達しないはず
    if (bitrate_map[quality.value] === undefined) {
        return 0;
    }
    const selected_bitrate = bitrate_map[quality.value][codec.value];
    const bytes_per_second = (selected_bitrate * 1000 * 1000) / 8;
    return Math.max(0, Math.floor(bytes_per_second * props.program.recorded_video.duration));
});

// 推定サイズ表示テキスト
const estimated_size_text = computed(() => Utils.formatBytes(estimated_size_bytes.value, 2, true));

// 空き容量表示テキスト
const free_storage_text = computed(() => {
    if (storage_estimate.value === null) {
        return '--';
    }
    return Utils.formatBytes(storage_estimate.value.available, 2, true);
});

// 容量不足かどうか
const is_storage_insufficient = computed(() => {
    if (storage_estimate.value === null) {
        return false;
    }
    return estimated_size_bytes.value > storage_estimate.value.available;
});

// 他番組のダウンロード中か
const is_other_downloading = computed(() => {
    return (
        offlineManagerStore.active_download_video_id !== null &&
        offlineManagerStore.active_download_video_id !== props.program.id
    );
});

// ダウンロード開始ボタンを無効化する条件
const is_start_disabled = computed(() => {
    return is_other_downloading.value || is_storage_insufficient.value || offlineManagerStore.is_supported === false;
});

// ダイアログ表示時にストレージ情報を更新
watch(() => props.modelValue, async (is_open) => {
    if (is_open === false) {
        return;
    }
    await offlineManagerStore.initialize();
    await offlineManagerStore.refreshStorageEstimate();
    storage_estimate.value = offlineManagerStore.storage_estimate;
});

// ダウンロード開始
const startDownload = async () => {
    try {
        const is_started = await offlineManagerStore.startDownload(props.program, {
            quality: selected_api_quality.value,
            include_comments: include_comments.value,
        });
        // ダウンロード開始に成功した場合のみダイアログを閉じる
        if (is_started === true) {
            emit('update:modelValue', false);
        }
    } catch (error) {
        // 例外が上がった場合はユーザーへ明示的に通知する
        Message.error('ダウンロードの開始に失敗しました。時間をおいて再度お試しください。');
        console.error('Failed to start download:', error);
    }
};
</script>

<style lang="scss" scoped>

.offline-download-dialog__program {
    &-title {
        font-size: 16px;
        font-weight: 700;
        line-height: 1.5;
        word-break: break-word;
    }

    &-time {
        margin-top: 4px;
        color: rgb(var(--v-theme-text-darken-1));
        font-size: 13px;
    }
}

.offline-download-dialog__summary {
    padding: 10px 14px;
    border-radius: 6px;
    background: rgb(var(--v-theme-background-lighten-1));

    &-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 13px;
        line-height: 1.6;
    }
}

</style>
