<template>
    <div class="encoding-progress" v-if="isVisible">
        <div class="encoding-progress__header">
            <div class="encoding-progress__title">
                <Icon :icon="getStatusIcon()" :class="getStatusIconClass()" width="20px" height="20px" />
                <span class="ml-2">{{ getStatusText() }}</span>
            </div>
            <div class="encoding-progress__actions">
                <v-btn v-if="canCancel"
                    size="small"
                    variant="text"
                    color="error"
                    @click="cancelEncoding"
                    :loading="isCancelling">
                    <Icon icon="fluent:stop-20-regular" width="16px" height="16px" />
                    <span class="ml-1">キャンセル</span>
                </v-btn>
                <v-btn size="small" variant="text" @click="hideProgress">
                    <Icon icon="fluent:dismiss-20-regular" width="16px" height="16px" />
                </v-btn>
            </div>
        </div>

        <div class="encoding-progress__content">
            <div class="encoding-progress__program-info" v-if="programTitle">
                <span class="encoding-progress__program-title">{{ programTitle }}</span>
            </div>

            <div class="encoding-progress__details">
                <div class="encoding-progress__codec-info">
                    <v-chip size="small" color="primary" variant="tonal">
                        {{ getCodecDisplayName() }}
                    </v-chip>
                    <v-chip size="small" color="secondary" variant="tonal" class="ml-2">
                        {{ getEncoderTypeDisplayName() }}
                    </v-chip>
                </div>

                <div class="encoding-progress__status-detail" v-if="statusDetail">
                    {{ statusDetail }}
                </div>
            </div>

            <div class="encoding-progress__progress-bar" v-if="showProgressBar">
                <v-progress-linear
                    :model-value="progress"
                    :color="getProgressColor()"
                    height="8"
                    rounded
                    :indeterminate="isIndeterminate">
                </v-progress-linear>
                <div class="encoding-progress__progress-text">
                    <span v-if="!isIndeterminate">{{ Math.round(progress) }}%</span>
                    <span v-else>処理中...</span>
                    <span v-if="estimatedTimeRemaining" class="ml-2 text-caption">
                        残り約 {{ estimatedTimeRemaining }}
                    </span>
                </div>
            </div>

            <div class="encoding-progress__error" v-if="errorMessage">
                <v-alert type="error" variant="tonal" density="compact">
                    {{ errorMessage }}
                </v-alert>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch, onUnmounted } from 'vue';

import Message from '@/message';
import TSReplace, { EncodingCodec, EncoderType, EncodingTaskStatus } from '@/services/TSReplace';
import useTSReplaceEncodingStore from '@/stores/TSReplaceEncodingStore';

// Props
const props = withDefaults(defineProps<{
    taskId?: string;
    programTitle?: string;
    codec?: EncodingCodec;
    encoderType?: EncoderType;
    autoHide?: boolean;
}>(), {
    autoHide: true,
});

// Emits
const emit = defineEmits<{
    (e: 'completed', taskId: string): void;
    (e: 'failed', taskId: string, error: string): void;
    (e: 'cancelled', taskId: string): void;
    (e: 'hidden'): void;
}>();

// 状態管理
const isVisible = ref(false);
const status = ref<EncodingTaskStatus>('queued');
const progress = ref(0);
const statusDetail = ref('');
const errorMessage = ref('');
const isCancelling = ref(false);
const startTime = ref<Date | null>(null);

// WebSocket接続管理
let unsubscribeProgress: (() => void) | null = null;

// 表示制御
const showProgressBar = computed(() => {
    return ['queued', 'processing'].includes(status.value);
});

const isIndeterminate = computed(() => {
    return status.value === 'queued' || (status.value === 'processing' && progress.value === 0);
});

const canCancel = computed(() => {
    return ['queued', 'processing'].includes(status.value) && !isCancelling.value;
});

// ステータス表示
const getStatusText = () => {
    switch (status.value) {
        case 'queued':
            return 'エンコード待機中';
        case 'processing':
            return 'エンコード中';
        case 'completed':
            return 'エンコード完了';
        case 'failed':
            return 'エンコード失敗';
        case 'cancelled':
            return 'エンコードキャンセル';
        default:
            return 'エンコード状況不明';
    }
};

const getStatusIcon = () => {
    switch (status.value) {
        case 'queued':
            return 'fluent:clock-20-regular';
        case 'processing':
            return 'fluent:arrow-sync-20-regular';
        case 'completed':
            return 'fluent:checkmark-circle-20-regular';
        case 'failed':
            return 'fluent:error-circle-20-regular';
        case 'cancelled':
            return 'fluent:dismiss-circle-20-regular';
        default:
            return 'fluent:question-circle-20-regular';
    }
};

const getStatusIconClass = () => {
    switch (status.value) {
        case 'processing':
            return 'encoding-progress__icon--spin';
        case 'completed':
            return 'text-success';
        case 'failed':
            return 'text-error';
        case 'cancelled':
            return 'text-warning';
        default:
            return 'text-primary';
    }
};

const getProgressColor = () => {
    switch (status.value) {
        case 'completed':
            return 'success';
        case 'failed':
            return 'error';
        case 'cancelled':
            return 'warning';
        default:
            return 'primary';
    }
};

const getCodecDisplayName = () => {
    switch (props.codec) {
        case 'h264':
            return 'H.264';
        case 'hevc':
            return 'H.265';
        default:
            return 'Unknown';
    }
};

const getEncoderTypeDisplayName = () => {
    switch (props.encoderType) {
        case 'software':
            return 'ソフトウェア';
        case 'hardware':
            return 'ハードウェア';
        default:
            return 'Unknown';
    }
};

// 推定残り時間の計算
const estimatedTimeRemaining = computed(() => {
    if (!startTime.value || status.value !== 'processing' || progress.value <= 0) {
        return null;
    }

    const elapsedMs = Date.now() - startTime.value.getTime();
    const elapsedMinutes = elapsedMs / (1000 * 60);
    const progressRatio = progress.value / 100;
    const totalEstimatedMinutes = elapsedMinutes / progressRatio;
    const remainingMinutes = totalEstimatedMinutes - elapsedMinutes;

    if (remainingMinutes < 1) {
        return '1分未満';
    } else if (remainingMinutes < 60) {
        return `${Math.round(remainingMinutes)}分`;
    } else {
        const hours = Math.floor(remainingMinutes / 60);
        const minutes = Math.round(remainingMinutes % 60);
        return `${hours}時間${minutes}分`;
    }
});

// エンコード進捗の監視を開始
const startProgressMonitoring = (taskId: string) => {
    if (unsubscribeProgress) {
        unsubscribeProgress();
    }

    unsubscribeProgress = TSReplace.subscribeToEncodingProgress(
        taskId,
        (data) => {
            handleProgressUpdate(data);
        },
        (error) => {
            console.error('Encoding progress WebSocket error:', error);
            Message.error('エンコード進捗の監視でエラーが発生しました。');
        }
    );
};

// 進捗更新の処理
const handleProgressUpdate = (data: any) => {
    if (data.type === 'status') {
        status.value = data.status;
        progress.value = data.progress || 0;
        statusDetail.value = data.detail || '';
        errorMessage.value = data.error_message || '';

        // 開始時刻を記録
        if (data.status === 'processing' && data.started_at && !startTime.value) {
            startTime.value = new Date(data.started_at);
        }

        // エンコードストアも更新
        const encodingStore = useTSReplaceEncodingStore();
        if (props.taskId) {
            encodingStore.updateTaskStatus(
                props.taskId,
                data.status,
                data.progress,
                data.error_message
            );
        }

        // 完了・失敗・キャンセル時の処理
        if (data.status === 'completed') {
            progress.value = 100;
            emit('completed', props.taskId!);

            if (props.autoHide) {
                setTimeout(() => {
                    hideProgress();
                }, 3000);
            }
        } else if (data.status === 'failed') {
            emit('failed', props.taskId!, data.error_message || 'Unknown error');
        } else if (data.status === 'cancelled') {
            emit('cancelled', props.taskId!);

            if (props.autoHide) {
                setTimeout(() => {
                    hideProgress();
                }, 2000);
            }
        }
    }
};

// エンコードキャンセル
const cancelEncoding = async () => {
    if (!props.taskId || !canCancel.value) return;

    isCancelling.value = true;

    try {
        const success = await TSReplace.cancelEncoding(props.taskId);
        if (success) {
            Message.info('エンコードのキャンセルを要求しました。');
        }
    } catch (error) {
        console.error('Failed to cancel encoding:', error);
        Message.error('エンコードのキャンセルに失敗しました。');
    } finally {
        isCancelling.value = false;
    }
};

// 進捗表示を隠す
const hideProgress = () => {
    isVisible.value = false;
    emit('hidden');
};

// 進捗表示を開始
const showProgress = () => {
    if (props.taskId) {
        isVisible.value = true;
        startProgressMonitoring(props.taskId);
    }
};

// taskIdが変更された時の処理
watch(() => props.taskId, (newTaskId) => {
    if (newTaskId) {
        showProgress();
    } else {
        hideProgress();
    }
});

// コンポーネントのクリーンアップ
onUnmounted(() => {
    if (unsubscribeProgress) {
        unsubscribeProgress();
    }
});

// 外部から呼び出し可能なメソッドを公開
defineExpose({
    showProgress,
    hideProgress,
});
</script>

<style lang="scss" scoped>
.encoding-progress {
    position: fixed;
    top: 80px;
    right: 20px;
    width: 400px;
    max-width: calc(100vw - 40px);
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgb(var(--v-theme-border));
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    z-index: 1000;
    animation: slideInRight 0.3s ease-out;

    @include smartphone-vertical {
        top: 60px;
        right: 10px;
        left: 10px;
        width: auto;
        max-width: none;
    }

    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 12px;
        border-bottom: 1px solid rgb(var(--v-theme-border));
    }

    &__title {
        display: flex;
        align-items: center;
        font-size: 16px;
        font-weight: 600;
    }

    &__actions {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    &__content {
        padding: 16px 20px;
    }

    &__program-info {
        margin-bottom: 12px;
    }

    &__program-title {
        font-size: 14px;
        font-weight: 500;
        color: rgb(var(--v-theme-text-darken-1));
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }

    &__details {
        margin-bottom: 16px;
    }

    &__codec-info {
        display: flex;
        align-items: center;
        margin-bottom: 8px;
    }

    &__status-detail {
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
        line-height: 1.4;
    }

    &__progress-bar {
        margin-bottom: 12px;
    }

    &__progress-text {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 8px;
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__error {
        margin-top: 12px;
    }

    &__icon--spin {
        animation: spin 1.5s linear infinite;
    }
}

@keyframes slideInRight {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

@keyframes spin {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}
</style>