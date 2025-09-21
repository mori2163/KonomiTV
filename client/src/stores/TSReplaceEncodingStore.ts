import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

import Message from '@/message';
import TSReplace, { EncodingTaskStatus } from '@/services/TSReplace';

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
    const activeTasks = ref<Map<string, IActiveEncodingTask>>(new Map());
    const webSocket = ref<WebSocket | null>(null);
    const isWebSocketConnected = ref(false);

    const activeTaskCount = computed(() => {
        return Array.from(activeTasks.value.values()).filter(task =>
            ['queued', 'processing'].includes(task.status)
        ).length;
    });

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

    const initializeWebSocket = () => {
        if (webSocket.value && webSocket.value.readyState === WebSocket.OPEN) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/tsreplace/progress`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('WebSocket connection for progress updates established.');
            isWebSocketConnected.value = true;
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // エンコード完了通知の処理
                if (data.type === 'encoding_complete') {
                    Message.success(data.message, 8000);
                    console.log('Encoding completed:', data);

                    // 完了タスクの情報も更新
                    const existingTask = activeTasks.value.get(data.task_id);
                    if (existingTask) {
                        existingTask.status = 'completed';
                        existingTask.progress = 100;
                        existingTask.completedAt = new Date();
                        activeTasks.value.set(data.task_id, existingTask);
                    }
                }

                // エンコード失敗通知の処理
                if (data.type === 'encoding_failed') {
                    Message.error(`${data.message}\nエラー: ${data.error_message}`, 10000);
                    console.log('Encoding failed:', data);

                    // 失敗タスクの情報も更新
                    const existingTask = activeTasks.value.get(data.task_id);
                    if (existingTask) {
                        existingTask.status = 'failed';
                        existingTask.errorMessage = data.error_message;
                        existingTask.completedAt = new Date();
                        activeTasks.value.set(data.task_id, existingTask);
                    }
                }

                // 進捗更新の処理
                if (data.type === 'progress_update' && Array.isArray(data.tasks)) {
                    for (const taskUpdate of data.tasks) {
                        let existingTask = activeTasks.value.get(taskUpdate.task_id);
                        if (!existingTask) {
                            // 新しいタスクの場合は作成
                            existingTask = {
                                taskId: taskUpdate.task_id,
                                programTitle: taskUpdate.video_title || 'Unknown Video',
                                codec: taskUpdate.codec,
                                encoderType: taskUpdate.encoder_type,
                                status: taskUpdate.status,
                                progress: taskUpdate.progress,
                                errorMessage: taskUpdate.error_message,
                            };
                            activeTasks.value.set(taskUpdate.task_id, existingTask);
                        } else {
                            // 既存のタスクを更新
                            existingTask.status = taskUpdate.status;
                            existingTask.progress = taskUpdate.progress;
                            if (taskUpdate.error_message) {
                                existingTask.errorMessage = taskUpdate.error_message;
                            }
                        }

                        // タイムスタンプの更新
                        if (taskUpdate.started_at && !existingTask.startedAt) {
                            existingTask.startedAt = new Date(taskUpdate.started_at);
                        }
                        if (taskUpdate.completed_at && !existingTask.completedAt) {
                            existingTask.completedAt = new Date(taskUpdate.completed_at);
                        }
                    }
                }
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };

        ws.onclose = () => {
            console.log('WebSocket connection for progress updates closed. Reconnecting in 5 seconds...');
            isWebSocketConnected.value = false;
            setTimeout(initializeWebSocket, 5000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            isWebSocketConnected.value = false;
            ws.close();
        };

        webSocket.value = ws;
    };

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
            if (status === 'processing' && !task.startedAt) {
                task.startedAt = new Date();
            }
            if (['completed', 'failed', 'cancelled'].includes(status)) {
                task.completedAt = new Date();
            }
            activeTasks.value.set(taskId, task);
        }
    };

    const removeTask = (taskId: string) => {
        activeTasks.value.delete(taskId);
    };

    const cleanupCompletedTasks = () => {
        const now = Date.now();
        const CLEANUP_DELAY = 5 * 60 * 1000; // 5分
        for (const [taskId, task] of activeTasks.value.entries()) {
            if (['completed', 'failed', 'cancelled'].includes(task.status) &&
                task.completedAt &&
                (now - task.completedAt.getTime()) > CLEANUP_DELAY) {
                activeTasks.value.delete(taskId);
            }
        }
    };

    const getTask = (taskId: string): IActiveEncodingTask | undefined => {
        return activeTasks.value.get(taskId);
    };

    const getAllTasks = (): IActiveEncodingTask[] => {
        return Array.from(activeTasks.value.values());
    };

    const refreshEncodingQueue = async () => {
        try {
            const queueResponse = await TSReplace.getEncodingQueue();
            if (queueResponse && queueResponse.success) {
                const allTasks = [
                    ...queueResponse.processing_tasks,
                    ...queueResponse.queued_tasks,
                    ...queueResponse.completed_tasks,
                    ...queueResponse.failed_tasks,
                ];

                // 現在のタスクリストをAPIからの情報で更新
                const newTasks = new Map<string, IActiveEncodingTask>();
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
                    newTasks.set(taskInfo.task_id, task);
                }
                activeTasks.value = newTasks;
            }
        } catch (error) {
            console.error('Failed to refresh encoding queue:', error);
        }
    };

    const startPeriodicCleanup = () => {
        setInterval(cleanupCompletedTasks, 60 * 1000); // 1分ごと
    };

    return {
        activeTasks: computed(() => activeTasks.value),
        isWebSocketConnected: computed(() => isWebSocketConnected.value),

        activeTaskCount,
        latestActiveTask,

        initializeWebSocket,
        addTask,
        updateTaskStatus,
        removeTask,
        getTask,
        getAllTasks,
        refreshEncodingQueue,
        startPeriodicCleanup,
    };
});

export default useTSReplaceEncodingStore;
