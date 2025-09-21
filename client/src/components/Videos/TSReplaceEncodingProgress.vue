<template>
    <div class="encoding-progress" v-if="isVisible" :class="{
        'encoding-progress--collapsed': isCollapsed,
        'encoding-progress--expanded': !isCollapsed,
        'encoding-progress--initial-show': isInitialShow
    }">
        <!-- 折り畳み状態のヘッダー（常に表示） -->
        <div class="encoding-progress__compact-header" @click="toggleCollapse">
            <div class="encoding-progress__compact-info">
                <Icon :icon="getStatusIcon" :class="getStatusIconClass" width="16px" height="16px" />
                <span class="ml-2">{{ getStatusText }}</span>
                <!-- 折りたたみ時のみ進捗バーを表示 -->
                <div class="encoding-progress__compact-progress" v-if="showProgressBar && isCollapsed">
                    <v-progress-linear
                        :model-value="progress"
                        :color="getProgressColor"
                        height="4"
                        rounded
                        :indeterminate="isIndeterminate">
                    </v-progress-linear>
                    <span class="encoding-progress__compact-percentage">
                        {{ !isIndeterminate ? Math.round(progress) + '%' : '...' }}
                    </span>
                </div>
            </div>
            <div class="encoding-progress__compact-actions">
                <v-btn size="x-small" variant="text" @click.stop="toggleCollapse" class="mr-1">
                    <Icon :icon="isCollapsed ? 'fluent:chevron-down-20-regular' : 'fluent:chevron-up-20-regular'"
                          width="16px" height="16px" />
                </v-btn>
                <v-btn v-if="canCancel && isCollapsed"
                    size="x-small"
                    variant="text"
                    color="error"
                    @click.stop="cancelEncoding"
                    :loading="isCancelling">
                    <Icon icon="fluent:stop-20-regular" width="14px" height="14px" />
                </v-btn>
                <v-btn v-if="isCollapsed" size="x-small" variant="text" @click.stop="hideProgress">
                    <Icon icon="fluent:dismiss-20-regular" width="14px" height="14px" />
                </v-btn>
            </div>
        </div>

        <!-- 展開状態の詳細コンテンツ -->
        <v-expand-transition>
            <div v-show="!isCollapsed" class="encoding-progress__expanded-content">
                <div class="encoding-progress__header">
                    <div class="encoding-progress__title">
                        <Icon :icon="getStatusIcon" :class="getStatusIconClass" width="20px" height="20px" />
                        <span class="ml-2">{{ getStatusText }}</span>
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
                                {{ getCodecDisplayName }}
                            </v-chip>
                            <v-chip size="small" color="secondary" variant="tonal" class="ml-2">
                                {{ getEncoderTypeDisplayName }}
                            </v-chip>
                        </div>
                    </div>

                    <div class="encoding-progress__progress-bar" v-if="showProgressBar">
                        <v-progress-linear
                            :model-value="progress"
                            :color="getProgressColor"
                            height="8"
                            rounded
                            :indeterminate="isIndeterminate">
                        </v-progress-linear>
                        <div class="encoding-progress__progress-text">
                            <span v-if="!isIndeterminate">{{ Math.round(progress) }}%</span>
                            <span v-else>処理中...</span>
                        </div>
                    </div>

                    <div class="encoding-progress__error" v-if="errorMessage">
                        <v-alert type="error" variant="tonal" density="compact">
                            {{ errorMessage }}
                        </v-alert>
                    </div>
                </div>
            </div>
        </v-expand-transition>
    </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch } from 'vue';

import type { EncodingTaskStatus } from '@/services/TSReplace';

import Message from '@/message';
import TSReplace from '@/services/TSReplace';
import useTSReplaceEncodingStore from '@/stores/TSReplaceEncodingStore';

const props = withDefaults(defineProps<{
    taskId?: string;
    autoHide?: boolean;
}>(), {
    autoHide: true,
});

const emit = defineEmits<{
    (e: 'completed', taskId: string): void;
    (e: 'failed', taskId: string, error: string): void;
    (e: 'cancelled', taskId: string): void;
    (e: 'hidden'): void;
}>();

const store = useTSReplaceEncodingStore();
const task = computed(() => props.taskId ? store.getTask(props.taskId) : null);

// WebSocketを初期化
store.initializeWebSocket();

// ローカルの状態
const isVisible = ref(false);
const isCancelling = ref(false);
const isCollapsed = ref(false);
const isInitialShow = ref(true); // 初回表示かどうかのフラグ

// 折り畳み状態の切り替え
const toggleCollapse = () => {
    isCollapsed.value = !isCollapsed.value;
    isInitialShow.value = false; // 初回表示フラグをfalseに
};

const status = computed<EncodingTaskStatus>(() => task.value?.status ?? 'queued');
const progress = computed(() => task.value?.progress ?? 0);
const errorMessage = computed(() => task.value?.errorMessage ?? '');
const programTitle = computed(() => task.value?.programTitle ?? '読み込み中...');
const codec = computed(() => task.value?.codec);
const encoderType = computed(() => task.value?.encoderType);
const startTime = computed(() => task.value?.startedAt);

const showProgressBar = computed(() => {
    return ['queued', 'processing'].includes(status.value);
});

const isIndeterminate = computed(() => {
    return status.value === 'queued' || (status.value === 'processing' && progress.value === 0);
});

const canCancel = computed(() => {
    return ['queued', 'processing'].includes(status.value) && !isCancelling.value;
});

const getStatusText = computed(() => {
    switch (status.value) {
        case 'queued': return 'エンコード待機中';
        case 'processing': return 'エンコード中';
        case 'completed': return 'エンコード完了';
        case 'failed': return 'エンコード失敗';
        case 'cancelled': return 'エンコードキャンセル';
        default: return '状況不明';
    }
});

const getStatusIcon = computed(() => {
    switch (status.value) {
        case 'queued': return 'fluent:clock-20-regular';
        case 'processing': return 'fluent:arrow-sync-20-regular';
        case 'completed': return 'fluent:checkmark-circle-20-regular';
        case 'failed': return 'fluent:error-circle-20-regular';
        case 'cancelled': return 'fluent:dismiss-circle-20-regular';
        default: return 'fluent:question-circle-20-regular';
    }
});

const getStatusIconClass = computed(() => {
    switch (status.value) {
        case 'processing': return 'encoding-progress__icon--spin';
        case 'completed': return 'text-success';
        case 'failed': return 'text-error';
        case 'cancelled': return 'text-warning';
        default: return 'text-primary';
    }
});

const getProgressColor = computed(() => {
    switch (status.value) {
        case 'completed': return 'success';
        case 'failed': return 'error';
        case 'cancelled': return 'warning';
        default: return 'primary';
    }
});

const getCodecDisplayName = computed(() => {
    switch (codec.value) {
        case 'h264': return 'H.264';
        case 'hevc': return 'H.265';
        default: return '-';
    }
});

const getEncoderTypeDisplayName = computed(() => {
    switch (encoderType.value) {
        case 'software': return 'ソフトウェア';
        case 'hardware': return 'ハードウェア';
        default: return '-';
    }
});

// エンコードキャンセル処理
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

const hideProgress = () => {
    isVisible.value = false;
    emit('hidden');
};

const showProgress = () => {
    if (props.taskId) {
        isVisible.value = true;
    }
};

// taskId の変更を監視して表示を切り替え
watch(() => props.taskId, (newTaskId) => {
    if (newTaskId) {
        showProgress();
    } else {
        hideProgress();
    }
}, { immediate: true });

// タスクの状態変更を監視して emit や自動非表示を行う
watch(status, (newStatus, oldStatus) => {
    if (newStatus === oldStatus || !props.taskId) return;

    if (newStatus === 'completed') {
        emit('completed', props.taskId);
        if (props.autoHide) {
            setTimeout(() => hideProgress(), 5000);
        }
    } else if (newStatus === 'failed') {
        emit('failed', props.taskId, errorMessage.value || 'Unknown error');
    } else if (newStatus === 'cancelled') {
        emit('cancelled', props.taskId);
        if (props.autoHide) {
            setTimeout(() => hideProgress(), 3000);
        }
    }
});

defineExpose({
    showProgress,
    hideProgress,
});
</script>

<style lang="scss" scoped>
.encoding-progress {
    position: fixed;
    right: 20px;
    width: 400px;
    max-width: calc(100vw - 40px);
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgb(var(--v-theme-border));
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    z-index: 1000;
    transition: all 0.3s ease-out;

    &--expanded {
        top: 20px;
        animation: none;

        // 初回表示時のみスライドインアニメーション
        &.encoding-progress--initial-show {
            animation: slideInRight 0.3s ease-out;
        }
    }

    // 折り畳み状態
    &--collapsed {
        top: 20px;
        animation: none; // アニメーションを無効化して位置移動を防ぐ

        .encoding-progress__compact-header {
            border-bottom: none; // 折りたたみ時は境界線を非表示
        }
    }

    @include smartphone-vertical {
        right: 10px;
        left: 10px;
        width: auto;
        max-width: none;
        // 展開状態
        &.encoding-progress--expanded {
            top: max(20px, env(safe-area-inset-top, 20px));
            bottom: auto;
            animation: none; // デフォルトはアニメーションなし

            // 初回表示時のみスライドインアニメーション
            &.encoding-progress--initial-show {
                animation: slideInRight 0.3s ease-out;
            }
        }
        // 折り畳み状態
        &.encoding-progress--collapsed {
            top: max(20px, env(safe-area-inset-top, 20px));
            bottom: auto;
            animation: none;
        }
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        // z-indexを下げてナビゲーションバーの下に表示
        z-index: 999;
    }

    &__compact-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        cursor: pointer;
        border-bottom: 1px solid rgb(var(--v-theme-border));
        transition: background-color 0.2s ease;

        &:hover {
            background: rgb(var(--v-theme-surface-lighten-1));
        }

        @include smartphone-vertical {
            padding: 6px 10px;
        }

        @include smartphone-horizontal {
            padding: 5px 10px;
        }
    }

    &__compact-info {
        display: flex;
        align-items: center;
        flex: 1;
        min-width: 0;
    }

    &__compact-progress {
        display: flex;
        align-items: center;
        margin-left: 12px;
        flex: 1;
        min-width: 100px; // 最小幅を確保
        max-width: 150px; // 最大幅を制限

        .v-progress-linear {
            flex: 1;
            margin-right: 8px;
        }
    }

    &__compact-percentage {
        font-size: 12px;
        font-weight: 500;
        color: rgb(var(--v-theme-text-darken-1));
        min-width: 35px;
        text-align: right;
    }

    &__compact-actions {
        display: flex;
        align-items: center;
        gap: 4px;
    }

    // 展開
    &__expanded-content {
        border-top: none;
    }

    @include smartphone-horizontal {
        right: 10px;
        left: 10px;
        width: auto;
        max-width: none;
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        z-index: 999;
        // 展開状態
        &.encoding-progress--expanded {
            top: max(15px, env(safe-area-inset-top, 15px));
            bottom: auto;
            animation: none; // デフォルトはアニメーションなし

            // 初回表示時のみスライドインアニメーション
            &.encoding-progress--initial-show {
                animation: slideInRight 0.3s ease-out;
            }
        }
        // 折り畳み状態
        &.encoding-progress--collapsed {
            top: max(15px, env(safe-area-inset-top, 15px));
            bottom: auto;
            animation: none;
        }
    }

    @media screen and (max-height: 600px) and (orientation: portrait) {
        // 小さい画面での調整 - 位置は固定
        &.encoding-progress--expanded {
            top: max(20px, env(safe-area-inset-top, 20px)) !important;
        }
        &.encoding-progress--collapsed {
            top: max(20px, env(safe-area-inset-top, 20px)) !important;
        }
    }

    @media screen and (max-height: 400px) and (orientation: landscape) {
        &.encoding-progress--expanded {
            top: max(15px, env(safe-area-inset-top, 15px)) !important;
        }
        &.encoding-progress--collapsed {
            top: max(15px, env(safe-area-inset-top, 15px)) !important;
        }
        border-radius: 6px;
    }

    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 20px 12px;
        border-bottom: 1px solid rgb(var(--v-theme-border));

        @include smartphone-vertical {
            padding: 12px 16px 10px;
        }

        @include smartphone-horizontal {
            padding: 10px 16px 8px;
        }
    }

    &__title {
        display: flex;
        align-items: center;
        font-size: 16px;
        font-weight: 600;

        @include smartphone-vertical {
            font-size: 15px;
        }

        @include smartphone-horizontal {
            font-size: 14px;
        }
    }

    &__actions {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    &__content {
        padding: 16px 20px;

        @include smartphone-vertical {
            padding: 10px 16px 12px;
        }

        @include smartphone-horizontal {
            padding: 8px 16px 10px;
        }
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
        line-clamp: 2;
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

@keyframes slideInBottom {
    from {
        transform: translateY(100%);
        opacity: 0;
    }
    to {
        transform: translateY(0);
        opacity: 1;
    }
}

@keyframes slideInFromTop {
    from {
        transform: translateY(-100%);
        opacity: 0;
    }
    to {
        transform: translateY(0);
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