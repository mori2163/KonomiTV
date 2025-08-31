import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

import TSReplace, { EncodingTaskStatus, ITSReplaceEncodingTaskInfo } from '@/services/TSReplace';

export interface IActiveEncodingTask {
    taskId: string;
    programTitle: string;
    codec: 'h264' | 'hevc';
    encoderType: 'software' | 'hardware';
    status: EncodingTaskStatus;
    progress: number;
    startedAt?: Date;
    completedAt?: Date;
    errorMessage?: string;
}

const useTSReplaceEncodingStore = defineStore('tsreplace-encoding', () => {
    // アクティブなエンコードタスクのリスト
    const activeTasks = ref<Map<string, IActiveEncodingTask>>(new Map());

    // 現在実行中のタスク数
    const activeTaskCount = computed(() => {
        return Array.from(activeTasks.value.values()).filter(task =>
            ['queued', 'processing'].includes(task.status)
        ).length;
    });

    // 最新のアクティブタスク（進捗表示用）
    const latestActiveTask = computed(() => {
        const tasks = Array.from(activeTasks.value.values())
            .filter(task => ['queued', 'processing'].includes(task.status))
            .sort((a, b) => {
                if (a.startedAt && b.startedAt) {
                    return b.startedAt.getTime() - a.startedAt.getTime();
                }
                return 0;
            });
        return tasks[0] || null;
    });

    // エンコードタスクを追加
    const addTask = (
        taskId: string,
        programTitle: string,
        codec: 'h264' | 'hevc',
        encoderType: 'software' | 'hardware'
    ) => {
        const task: IActiveEncodingTask = {
            taskId,
            programTitle,
            codec,
            encoderType,
            status: 'queued',
            progress: 0,
        };
        activeTasks.value.set(taskId, task);
    };

    // エンコードタスクの状態を更新
    const updateTaskStatus = (
        taskId: string,
        status: EncodingTaskStatus,
        progress?: number,
        errorMessage?: string
    ) => {
        const task = activeTasks.value.get(taskId);
        if (task) {
            task.status = status;
            if (progress !== undefined) {
                task.progress = progress;
            }
            if (errorMessage !== undefined) {
                task.errorMessage = errorMessage;
            }

            // 開始時刻を記録
            if (status === 'processing' && !task.startedAt) {
                task.startedAt = new Date();
            }

            // 完了時刻を記録
            if (['completed', 'failed', 'cancelled'].includes(status)) {
                task.completedAt = new Date();
            }

            activeTasks.value.set(taskId, task);
        }
    };

    // エンコードタスクを削除
    const removeTask = (taskId: string) => {
        activeTasks.value.delete(taskId);
    };

    // 完了したタスクをクリーンアップ
    const cleanupCompletedTasks = () => {
        const now = Date.now();
        const CLEANUP_DELAY = 5 * 60 * 1000; // 5分後にクリーンアップ

        for (const [taskId, task] of activeTasks.value.entries()) {
            if (['completed', 'failed', 'cancelled'].includes(task.status) &&
                task.completedAt &&
                (now - task.completedAt.getTime()) > CLEANUP_DELAY) {
                activeTasks.value.delete(taskId);
            }
        }
    };

    // 指定されたタスクを取得
    const getTask = (taskId: string): IActiveEncodingTask | undefined => {
        return activeTasks.value.get(taskId);
    };

    // すべてのアクティブタスクを取得
    const getAllTasks = (): IActiveEncodingTask[] => {
        return Array.from(activeTasks.value.values());
    };

    // エンコードキューの状況を取得してストアを更新
    const refreshEncodingQueue = async () => {
        try {
            const queueResponse = await TSReplace.getEncodingQueue();
            if (queueResponse && queueResponse.success) {
                // 現在のタスクリストをクリア
                activeTasks.value.clear();

                // 処理中・待機中のタスクを追加
                const allTasks = [
                    ...queueResponse.processing_tasks,
                    ...queueResponse.queued_tasks,
                ];

                for (const taskInfo of allTasks) {
                    const task: IActiveEncodingTask = {
                        taskId: taskInfo.task_id,
                        programTitle: taskInfo.video_title,
                        codec: taskInfo.codec,
                        encoderType: taskInfo.encoder_type,
                        status: taskInfo.status,
                        progress: taskInfo.progress,
                        startedAt: taskInfo.started_at ? new Date(taskInfo.started_at) : undefined,
                        completedAt: taskInfo.completed_at ? new Date(taskInfo.completed_at) : undefined,
                        errorMessage: taskInfo.error_message,
                    };
                    activeTasks.value.set(taskInfo.task_id, task);
                }
            }
        } catch (error) {
            console.error('Failed to refresh encoding queue:', error);
        }
    };

    // 定期的なクリーンアップを開始
    const startPeriodicCleanup = () => {
        setInterval(cleanupCompletedTasks, 60 * 1000); // 1分ごと
    };

    return {
        // State
        activeTasks: computed(() => activeTasks.value),
        activeTaskCount,
        latestActiveTask,

        // Actions
        addTask,
        updateTaskStatus,
        removeTask,
        cleanupCompletedTasks,
        getTask,
        getAllTasks,
        refreshEncodingQueue,
        startPeriodicCleanup,
    };
});

export default useTSReplaceEncodingStore;
