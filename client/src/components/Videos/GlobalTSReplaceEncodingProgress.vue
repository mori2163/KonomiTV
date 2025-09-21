<template>
    <div class="global-encoding-progress" v-if="latestActiveTask">
        <TSReplaceEncodingProgress
            :task-id="latestActiveTask.taskId"
            :program-title="latestActiveTask.programTitle"
            :codec="latestActiveTask.codec"
            :encoder-type="latestActiveTask.encoderType"
            :auto-hide="true"
            @completed="handleEncodingCompleted"
            @failed="handleEncodingFailed"
            @cancelled="handleEncodingCancelled"
            @hidden="handleProgressHidden" />
    </div>
</template>

<script lang="ts" setup>
import { computed, watch, onMounted, onUnmounted } from 'vue';

import TSReplaceEncodingProgress from '@/components/Videos/TSReplaceEncodingProgress.vue';
import Message from '@/message';
import useTSReplaceEncodingStore from '@/stores/TSReplaceEncodingStore';

// エンコードストア
const encodingStore = useTSReplaceEncodingStore();

// 最新のアクティブタスク
const latestActiveTask = computed(() => encodingStore.latestActiveTask);

// WebSocket接続管理
let progressUnsubscribers: Map<string, () => void> = new Map();

// エンコード完了時の処理
const handleEncodingCompleted = (taskId: string) => {
    const task = encodingStore.getTask(taskId);
    encodingStore.updateTaskStatus(taskId, 'completed', 100);

    // 番組名を含む完了通知
    const programTitle = task?.programTitle || '録画番組';
    Message.success(`「${programTitle}」のエンコードが完了しました。`);

    // WebSocket接続をクリーンアップ
    const unsubscriber = progressUnsubscribers.get(taskId);
    if (unsubscriber) {
        unsubscriber();
        progressUnsubscribers.delete(taskId);
    }

    // エンコード完了後に録画番組リストを更新
    // ページがVideos関連の場合のみ、カスタムイベントを発火して更新を通知
    if (window.location.pathname.startsWith('/videos')) {
        // カスタムイベントを発火して、各ページで録画番組リストの更新を促す
        window.dispatchEvent(new CustomEvent('tsreplace-encoding-completed', {
            detail: { taskId, programTitle }
        }));
    }
};

// エンコード失敗時の処理
const handleEncodingFailed = (taskId: string, error: string) => {
    const task = encodingStore.getTask(taskId);
    encodingStore.updateTaskStatus(taskId, 'failed', undefined, error);

    // 番組名を含むエラー通知
    const programTitle = task?.programTitle || '録画番組';
    Message.error(`「${programTitle}」のエンコードが失敗しました: ${error}`);

    // WebSocket接続をクリーンアップ
    const unsubscriber = progressUnsubscribers.get(taskId);
    if (unsubscriber) {
        unsubscriber();
        progressUnsubscribers.delete(taskId);
    }
};

// エンコードキャンセル時の処理
const handleEncodingCancelled = (taskId: string) => {
    const task = encodingStore.getTask(taskId);
    encodingStore.updateTaskStatus(taskId, 'cancelled');

    // 番組名を含むキャンセル通知
    const programTitle = task?.programTitle || '録画番組';
    Message.warning(`「${programTitle}」のエンコードがキャンセルされました。`);

    // WebSocket接続をクリーンアップ
    const unsubscriber = progressUnsubscribers.get(taskId);
    if (unsubscriber) {
        unsubscriber();
        progressUnsubscribers.delete(taskId);
    }
};

// 進捗表示が隠された時の処理
const handleProgressHidden = () => {
    // 必要に応じて追加の処理を行う
};

// 新しいタスクが追加された時の監視
watch(() => latestActiveTask.value, (newTask, oldTask) => {
    if (newTask && (!oldTask || newTask.taskId !== oldTask.taskId)) {
        console.log('New encoding task detected:', newTask.taskId);
    }
});

// コンポーネント初期化時
onMounted(() => {
    // 定期的なクリーンアップを開始
    encodingStore.startPeriodicCleanup();

    // 既存のエンコードキューを取得
    encodingStore.refreshEncodingQueue();
});

// コンポーネントのクリーンアップ
onUnmounted(() => {
    // すべてのWebSocket接続をクリーンアップ
    for (const unsubscriber of progressUnsubscribers.values()) {
        unsubscriber();
    }
    progressUnsubscribers.clear();
});
</script>

<style lang="scss" scoped>
</style>