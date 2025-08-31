<template>
    <v-dialog v-model="show" max-width="600" persistent>
        <v-card>
            <v-card-title class="d-flex justify-center pt-6 font-weight-bold">
                録画ファイルを再エンコード
            </v-card-title>
            <v-card-text class="pt-4 pb-0">
                <div class="encoding-dialog__program-info mb-4">
                    <div class="encoding-dialog__program-title">{{ program?.title || '取得中...' }}</div>
                    <div class="encoding-dialog__program-meta" v-if="program">
                        <span class="encoding-dialog__program-channel">{{ program.channel?.name || 'チャンネル情報なし' }}</span>
                        <span class="encoding-dialog__program-time">{{ ProgramUtils.getProgramTime(program) }}</span>
                    </div>
                </div>

                <div class="encoding-dialog__settings">
                    <v-row>
                        <v-col cols="12" md="6">
                            <v-select v-model="selectedCodec" :items="codecOptions" item-title="label"
                                item-value="value" label="エンコードコーデック" variant="outlined" density="comfortable"
                                hide-details="auto" :disabled="isEncoding">
                                <template v-slot:item="{ props, item }">
                                    <v-list-item v-bind="props">
                                        <template v-slot:title>
                                            <div class="d-flex align-center">
                                                <span>{{ item.raw.label }}</span>
                                                <v-chip v-if="item.raw.recommended" size="x-small" color="primary"
                                                    class="ml-2">
                                                    推奨
                                                </v-chip>
                                            </div>
                                        </template>
                                        <template v-slot:subtitle>
                                            <span class="text-caption">{{ item.raw.description }}</span>
                                        </template>
                                    </v-list-item>
                                </template>
                            </v-select>
                        </v-col>
                        <v-col cols="12" md="6">
                            <v-select v-model="selectedEncoderType" :items="encoderTypeOptions" item-title="label"
                                item-value="value" label="エンコーダータイプ" variant="outlined" density="comfortable"
                                hide-details="auto" :disabled="isEncoding">
                                <template v-slot:item="{ props, item }">
                                    <v-list-item v-bind="props" :disabled="item.raw.disabled">
                                        <template v-slot:title>
                                            <div class="d-flex align-center">
                                                <span>{{ item.raw.label }}</span>
                                                <v-chip v-if="item.raw.fast" size="x-small" color="success"
                                                    class="ml-2">
                                                    高速
                                                </v-chip>
                                            </div>
                                        </template>
                                        <template v-slot:subtitle>
                                            <span class="text-caption">{{ item.raw.description }}</span>
                                        </template>
                                    </v-list-item>
                                </template>
                            </v-select>
                        </v-col>
                    </v-row>
                    <v-row>
                        <v-col cols="12">
                            <v-select v-model="selectedQualityPreset" :items="qualityPresetOptions" item-title="label"
                                item-value="value" label="エンコード品質" variant="outlined" density="comfortable"
                                hide-details="auto" :disabled="isEncoding">
                                <template v-slot:item="{ props, item }">
                                    <v-list-item v-bind="props">
                                        <template v-slot:title>
                                            <div class="d-flex align-center">
                                                <span>{{ item.raw.label }}</span>
                                                <v-chip v-if="item.raw.recommended" size="x-small" color="primary"
                                                    class="ml-2">
                                                    推奨
                                                </v-chip>
                                            </div>
                                        </template>
                                        <template v-slot:subtitle>
                                            <span class="text-caption">{{ item.raw.description }}</span>
                                        </template>
                                    </v-list-item>
                                </template>
                            </v-select>
                        </v-col>
                    </v-row>

                    <v-alert v-if="!hardwareEncoderAvailable && selectedEncoderType === 'hardware'" type="warning"
                        variant="tonal" class="mt-4">
                        <template v-slot:title>ハードウェアエンコーダーが利用できません</template>
                        ハードウェアエンコーダーが検出されないか、設定で無効になっています。<br>
                        ソフトウェアエンコードを使用してください。
                    </v-alert>

                    <v-alert v-if="program?.recorded_video.video_codec !== 'MPEG-2'" type="info" variant="tonal"
                        class="mt-4">
                        <template v-slot:title>既にエンコード済みのファイルです</template>
                        この録画ファイルは既に {{ program?.recorded_video.video_codec }} でエンコードされています。<br>
                        再エンコードすると画質が劣化する可能性があります。
                    </v-alert>
                </div>
            </v-card-text>
            <v-card-actions class="pt-4 px-6 pb-6">
                <v-spacer></v-spacer>
                <v-btn color="text" variant="text" @click="closeDialog" :disabled="isEncoding">
                    <Icon icon="fluent:dismiss-20-regular" width="18px" height="18px" />
                    <span class="ml-1">キャンセル</span>
                </v-btn>
                <v-btn class="px-3" color="primary" variant="flat" @click="startEncoding" :disabled="!canStartEncoding"
                    :loading="isEncoding">
                    <Icon icon="fluent:arrow-sync-20-regular" width="18px" height="18px" />
                    <span class="ml-1">エンコード開始</span>
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, watch, onMounted } from 'vue';

import Message from '@/message';
import TSReplace, { EncodingCodec, EncoderType } from '@/services/TSReplace';
import { IRecordedProgram } from '@/services/Videos';
import { ProgramUtils } from '@/utils';

// Props
const props = withDefaults(defineProps<{
    show: boolean;
    program?: IRecordedProgram;
}>(), {
    show: false,
});

// Emits
const emit = defineEmits<{
    (e: 'update:show', show: boolean): void;
    (e: 'encoding-started', taskId: string, codec: EncodingCodec, encoderType: EncoderType): void;
}>();

// ダイアログの表示状態
const show = computed({
    get: () => props.show,
    set: (value) => emit('update:show', value),
});

// エンコード中フラグ
const isEncoding = ref(false);

// ハードウェアエンコーダー利用可否
const hardwareEncoderAvailable = ref(false);

// 選択された設定
const selectedCodec = ref<EncodingCodec>('h264');
const selectedEncoderType = ref<EncoderType>('software');
const selectedQualityPreset = ref('medium');

// コーデック選択肢
const codecOptions = [
    {
        value: 'h264',
        label: 'H.264 (AVC)',
        description: '互換性が高く、多くのデバイスで再生可能',
        recommended: true,
    },
    {
        value: 'hevc',
        label: 'H.265 (HEVC)',
        description: 'より高い圧縮効率、ファイルサイズが小さくなる',
        recommended: false,
    },
];

// エンコーダータイプ選択肢
const encoderTypeOptions = computed(() => [
    {
        value: 'software',
        label: 'ソフトウェアエンコード',
        description: 'FFmpegを使用、時間がかかる',
        disabled: false,
        fast: false,
    },
    {
        value: 'hardware',
        label: 'ハードウェアエンコード',
        description: 'GPU/専用チップを使用、高速で高品質',
        disabled: !hardwareEncoderAvailable.value,
        fast: true,
    },
]);

// 品質プリセット選択肢
const qualityPresetOptions = [
    {
        value: 'fast',
        label: '高速',
        description: 'エンコード時間を優先、品質は標準的',
        recommended: false,
    },
    {
        value: 'medium',
        label: '標準',
        description: 'バランスの取れた設定',
        recommended: true,
    },
    {
        value: 'slow',
        label: '高品質',
        description: '品質を優先、エンコード時間は長くなる',
        recommended: false,
    },
];

// エンコード開始可能かどうか
const canStartEncoding = computed(() => {
    if (isEncoding.value) return false;
    if (!props.program) return false;
    if (selectedEncoderType.value === 'hardware' && !hardwareEncoderAvailable.value) return false;
    return true;
});

// ハードウェアエンコーダーの利用可否を確認
const checkHardwareEncoderAvailability = async () => {
    try {
        const availability = await TSReplace.checkHardwareEncoderAvailability();
        hardwareEncoderAvailable.value = availability.available;

        // ハードウェアエンコーダーが利用できない場合はソフトウェアエンコードに切り替え
        if (!availability.available && selectedEncoderType.value === 'hardware') {
            selectedEncoderType.value = 'software';
        }
    } catch (error) {
        console.error('Failed to check hardware encoder availability:', error);
        hardwareEncoderAvailable.value = false;
        if (selectedEncoderType.value === 'hardware') {
            selectedEncoderType.value = 'software';
        }
    }
};

// エンコード開始
const startEncoding = async () => {
    if (!props.program || !canStartEncoding.value) return;

    isEncoding.value = true;

    try {
        const response = await TSReplace.startManualEncoding({
            video_id: props.program.id,
            codec: selectedCodec.value,
            encoder_type: selectedEncoderType.value,
            quality_preset: selectedQualityPreset.value,
        });

        if (response && response.success && response.task_id) {
            Message.success('エンコードを開始しました。');
            emit('encoding-started', response.task_id, selectedCodec.value, selectedEncoderType.value);
            closeDialog();
        } else {
            Message.error('エンコードの開始に失敗しました。');
        }
    } catch (error) {
        console.error('Failed to start encoding:', error);
        Message.error('エンコードの開始に失敗しました。');
    } finally {
        isEncoding.value = false;
    }
};

// ダイアログを閉じる
const closeDialog = () => {
    if (!isEncoding.value) {
        show.value = false;
    }
};

// ダイアログが開かれた時の処理
watch(() => props.show, (newShow) => {
    if (newShow) {
        // ハードウェアエンコーダーの利用可否を確認
        checkHardwareEncoderAvailability();

        // 設定をリセット
        selectedCodec.value = 'h264';
        selectedEncoderType.value = 'software';
        selectedQualityPreset.value = 'medium';
        isEncoding.value = false;
    }
});

// コンポーネント初期化時
onMounted(() => {
    checkHardwareEncoderAvailability();
});
</script>

<style lang="scss" scoped>
.encoding-dialog {
    &__program-info {
        padding: 16px;
        background: rgb(var(--v-theme-background-lighten-1));
        border-radius: 8px;
    }

    &__program-title {
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 8px;
        line-height: 1.4;
    }

    &__program-meta {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 14px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__program-channel {
        font-weight: 500;
    }

    &__program-time {
        font-size: 13px;
    }

    &__settings {
        .v-select {
            :deep(.v-field__input) {
                font-size: 14px;
            }
        }
    }
}

:deep(.v-list-item-subtitle) {
    opacity: 0.7 !important;
    line-height: 1.3 !important;
    margin-top: 2px !important;
}
</style>