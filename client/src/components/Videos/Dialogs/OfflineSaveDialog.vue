<template>
    <v-dialog v-model="show" max-width="600" persistent>
        <v-card>
            <v-card-title class="d-flex justify-center pt-6 font-weight-bold">
                オフライン保存
            </v-card-title>
            <v-card-text class="pt-4 pb-0">
                <div class="offline-save-dialog__program-info mb-4">
                    <div class="offline-save-dialog__program-title">{{ program?.title || '取得中...' }}</div>
                    <div class="offline-save-dialog__program-meta" v-if="program">
                        <span class="offline-save-dialog__program-channel">{{ program.channel?.name || 'チャンネル情報なし' }}</span>
                        <span class="offline-save-dialog__program-time">{{ ProgramUtils.getProgramTime(program) }}</span>
                    </div>
                </div>

                <div class="offline-save-dialog__settings">
                    <v-row>
                        <v-col cols="12" md="6">
                            <v-select v-model="selectedQuality" :items="qualityOptions" item-title="label"
                                item-value="value" label="画質" variant="outlined" density="comfortable"
                                hide-details="auto" :disabled="isSaving" />
                        </v-col>
                        <v-col cols="12" md="6">
                            <v-checkbox v-model="useHevc" :disabled="isSaving" hide-details="auto">
                                <template #label>
                                    <div class="d-flex align-center">
                                        <span>H.265 / HEVC で保存する</span>
                                    </div>
                                </template>
                            </v-checkbox>
                        </v-col>
                    </v-row>
                    <v-row>
                        <v-col cols="12">
                            <v-checkbox v-model="saveComments" :disabled="isSaving" hide-details="auto">
                                <template #label>
                                    <div class="d-flex align-center">
                                        <span>ニコニコ実況の過去ログコメントも保存する</span>
                                    </div>
                                </template>
                            </v-checkbox>
                        </v-col>
                    </v-row>
                </div>
            </v-card-text>
            <v-card-actions class="pt-4 px-6 pb-6">
                <v-spacer></v-spacer>
                <v-btn color="text" variant="text" @click="closeDialog" :disabled="isSaving">
                    <Icon icon="fluent:dismiss-20-regular" width="18px" height="18px" />
                    <span class="ml-1">キャンセル</span>
                </v-btn>
                <v-btn class="px-3" color="primary" variant="flat" @click="startSave" :disabled="!canStart"
                    :loading="isSaving">
                    <Icon icon="fluent:arrow-download-24-regular" width="18px" height="18px" />
                    <span class="ml-1">保存開始</span>
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue';

import type { IRecordedProgram } from '@/services/Videos';

import OfflineDownloadManager from '@/offline/manager';
import { VIDEO_STREAMING_QUALITIES } from '@/stores/SettingsStore';
import { ProgramUtils } from '@/utils';

const props = withDefaults(defineProps<{
    show: boolean;
    program?: IRecordedProgram;
}>(), {
    show: false,
});

const emit = defineEmits<{ (e: 'update:show', show: boolean): void; (e: 'saved', downloadId: string): void }>();

const show = computed({
    get: () => props.show,
    set: (value) => emit('update:show', value),
});

const isSaving = ref(false);
const selectedQuality = ref<string>(VIDEO_STREAMING_QUALITIES[0]);
const useHevc = ref(false);
const saveComments = ref(true);

const qualityOptions = VIDEO_STREAMING_QUALITIES.map((q) => ({
    value: q,
    label: q === '1080p-60fps' ? '1080p (60fps)' : q,
}));

const canStart = computed(() => !!props.program && !isSaving.value);

const closeDialog = () => {
    emit('update:show', false);
};

const startSave = () => {
    if (!props.program) return;
    closeDialog();

    // バックグラウンドでダウンロードを開始
    OfflineDownloadManager.startDownload(props.program, {
        quality: selectedQuality.value,
        isHevc: useHevc.value,
        saveComments: saveComments.value,
    }).catch((error: any) => {
        console.error('[OfflineSaveDialog] Offline save failed:', error);
    });
};
</script>

<style scoped>
.offline-save-dialog__program-title {
    font-weight: 600;
}
.offline-save-dialog__program-meta {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.7);
}
</style>
