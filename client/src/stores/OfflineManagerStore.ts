
import * as Comlink from 'comlink';
import { defineStore } from 'pinia';
import { computed, ref, toRaw } from 'vue';

import type { IRecordedProgram } from '@/services/Videos';
import type { IOfflineDownloadCallbacks, IOfflineDownloadProgress, IOfflineDownloadWorker } from '@/workers/OfflineDownloadWorker';

import Message from '@/message';
import OfflineStorageService, {
    IOfflineProgramRecord,
    IOfflineStorageEstimate,
} from '@/services/OfflineStorageService';
import Utils, { dayjs } from '@/utils';
import OfflineDownloadWorkerProxy from '@/workers/OfflineDownloadWorkerProxy';


type IOfflineDownloadWorkerProxy = IOfflineDownloadWorker & {
    terminate(): Promise<void>;
};


/**
 * オフライン保存管理ストア
 */
const useOfflineManagerStore = defineStore('offlineManager', () => {

    // 保存済みオフライン番組一覧
    const offline_programs = ref<IOfflineProgramRecord[]>([]);

    // ストレージ使用量
    const storage_estimate = ref<IOfflineStorageEstimate | null>(null);

    // 初期化済みかどうか
    const is_initialized = ref(false);

    // オフライン保存機能を利用可能かどうか
    const is_supported = ref(OfflineStorageService.isSupported());

    // 現在ダウンロード中の録画番組 ID
    const active_download_video_id = ref<number | null>(null);

    // 同時ダウンロード防止用の Worker インスタンス
    let active_download_worker: IOfflineDownloadWorkerProxy | null = null;

    // startDownload() 内の download Promise（停止時に完了待ちするために保持する）
    let active_download_promise: Promise<boolean> | null = null;

    // 一時停止処理中かどうか（再開ボタン連打時のガードに使う）
    const is_pause_in_progress = ref(false);

    // beforeunload ハンドラーの登録状態
    let is_beforeunload_registered = false;

    // ダウンロード中のレコードが存在するか
    const is_any_downloading = computed(() =>
        offline_programs.value.some((record) => record.download_status === 'Downloading'),
    );

    // 再利用する beforeunload ハンドラー
    const beforeunload_handler = (event: BeforeUnloadEvent): void => {
        if (is_any_downloading.value === true) {
            event.preventDefault();
            event.returnValue = '';
        }
    };


    /**
     * レコードを完了日時降順でソートする
     * @param records レコード一覧
     * @returns ソート済みレコード一覧
     */
    const sortRecords = (records: IOfflineProgramRecord[]): IOfflineProgramRecord[] => {
        return [...records].sort((record_a, record_b) => {
            const record_a_time = dayjs(record_a.download_completed_at ?? record_a.download_started_at).valueOf();
            const record_b_time = dayjs(record_b.download_completed_at ?? record_b.download_started_at).valueOf();
            return record_b_time - record_a_time;
        });
    };


    /**
     * state 上のレコードを 1 件更新する
     * @param record 更新するレコード
     */
    const upsertProgramRecordInState = (record: IOfflineProgramRecord): void => {
        const target_index = offline_programs.value.findIndex((offline_program) => offline_program.id === record.id);
        if (target_index !== -1) {
            offline_programs.value[target_index] = record;
        } else {
            offline_programs.value.push(record);
        }
        offline_programs.value = sortRecords(offline_programs.value);
    };


    /**
     * ストアを初期化する
     */
    const initialize = async (): Promise<void> => {
        if (is_initialized.value === true) {
            return;
        }
        if (is_supported.value === false) {
            return;
        }

        // 前回終了時に中断したダウンロードは起動時に一時停止として扱う
        await OfflineStorageService.markDownloadingRecordsAsPaused();
        await refreshPrograms();
        await refreshStorageEstimate();

        // ダウンロード中のタブ離脱を防止する
        if (is_beforeunload_registered === false) {
            window.addEventListener('beforeunload', beforeunload_handler);
            is_beforeunload_registered = true;
        }

        is_initialized.value = true;
    };


    /**
     * 保存済み番組一覧を再読込する
     */
    const refreshPrograms = async (): Promise<void> => {
        if (is_supported.value === false) {
            offline_programs.value = [];
            return;
        }
        offline_programs.value = await OfflineStorageService.getAllPrograms();
    };


    /**
     * ストレージ使用量を再取得する
     */
    const refreshStorageEstimate = async (): Promise<void> => {
        if (is_supported.value === false) {
            storage_estimate.value = null;
            return;
        }
        storage_estimate.value = await OfflineStorageService.estimateStorage();
    };


    /**
     * 録画番組 ID からオフライン保存レコードを取得する
     * @param video_id 録画番組 ID
     * @returns オフライン保存レコード
     */
    const getProgramById = (video_id: number): IOfflineProgramRecord | null => {
        return offline_programs.value.find((offline_program) => offline_program.id === video_id) ?? null;
    };


    /**
     * ダウンロード進捗率を取得する
     * @param video_id 録画番組 ID
     * @returns 進捗率 (0〜100)
     */
    const getProgressPercent = (video_id: number): number => {
        const offline_program = getProgramById(video_id);
        if (offline_program === null) {
            return 0;
        }
        if (offline_program.total_segments <= 0) {
            return 0;
        }
        return Math.min(100, Math.floor((offline_program.downloaded_segments / offline_program.total_segments) * 100));
    };


    /**
     * ダウンロードを開始（または再開）する
     * @param recorded_program 録画番組情報
     * @param options ダウンロード設定
     * @returns 開始に成功したかどうか
     */
    const startDownload = async (
        recorded_program: IRecordedProgram,
        options: {
            quality: string;
            include_comments: boolean;
        },
    ): Promise<boolean> => {
        if (is_supported.value === false) {
            Message.warning('このブラウザではオフライン保存を利用できません。');
            return false;
        }
        await initialize();

        // 既存ダウンロードの終了処理が完了するまで、再開/再実行を抑止する
        if (active_download_promise !== null) {
            Message.warning('前回のダウンロード停止処理が完了するまでお待ちください。');
            return false;
        }

        // 同時ダウンロードは1件まで
        if (active_download_video_id.value !== null && active_download_video_id.value !== recorded_program.id) {
            Message.warning('同時にダウンロードできるのは 1 件までです。');
            return false;
        }

        const current_record = await OfflineStorageService.getProgram(recorded_program.id);
        let start_sequence = 0;
        let initial_downloaded_segments = 0;
        let initial_total_size = 0;

        // 同じ条件で一時停止中なら途中から再開し、それ以外は最初からやり直す
        if (
            current_record !== null &&
            current_record.quality === options.quality &&
            current_record.include_comments === options.include_comments &&
            current_record.download_status === 'Paused'
        ) {
            start_sequence = current_record.downloaded_segments;
            initial_downloaded_segments = current_record.downloaded_segments;
            initial_total_size = current_record.total_size;
        } else if (current_record !== null) {
            await OfflineStorageService.deleteVideoDirectory(recorded_program.id);
        }

        const current_timestamp = dayjs().format();
        const next_record: IOfflineProgramRecord = {
            id: recorded_program.id,
            // props 経由のリアクティブオブジェクトが渡されることがあるため、IndexedDB に保存可能なプレーンデータへ変換する
            recorded_program: structuredClone(toRaw(recorded_program)),
            download_status: 'Downloading',
            quality: options.quality,
            include_comments: options.include_comments,
            total_segments: current_record?.total_segments ?? 0,
            downloaded_segments: initial_downloaded_segments,
            total_size: initial_total_size,
            download_started_at: current_record?.download_started_at ?? current_timestamp,
            download_completed_at: null,
            failed_at: null,
            error_message: null,
        };

        await OfflineStorageService.ensureVideoDirectory(recorded_program.id);
        await OfflineStorageService.setProgram(next_record);
        upsertProgramRecordInState(next_record);

        active_download_video_id.value = recorded_program.id;
        active_download_worker = new OfflineDownloadWorkerProxy();
        const current_worker = active_download_worker;
        Message.show('ダウンロードを開始しました。');
        // `is_error_handled_by_callback` は Worker 側から Comlink 経由で呼ばれる `onError` と、
        // `current_worker.download(...).catch(...)` の Promise rejection ハンドラーで
        // 同じ失敗を二重処理しないための暫定フラグ。
        let is_error_handled_by_callback = false;

        const callbacks = Comlink.proxy<IOfflineDownloadCallbacks>({
            onProgress: async (progress: IOfflineDownloadProgress) => {
                const updated_record = await OfflineStorageService.updateProgram(progress.video_id, {
                    download_status: 'Downloading',
                    total_segments: progress.total_segments,
                    downloaded_segments: progress.downloaded_segments,
                    total_size: progress.total_size,
                    error_message: null,
                });
                if (updated_record !== null) {
                    upsertProgramRecordInState(updated_record);
                }
            },
            onCompleted: async (result: IOfflineDownloadProgress) => {
                const updated_record = await OfflineStorageService.updateProgram(result.video_id, {
                    download_status: 'Completed',
                    total_segments: result.total_segments,
                    downloaded_segments: result.downloaded_segments,
                    total_size: result.total_size,
                    download_completed_at: dayjs().format(),
                    error_message: null,
                });
                if (updated_record !== null) {
                    upsertProgramRecordInState(updated_record);
                }
                Message.success(`${recorded_program.title} のダウンロードが完了しました。`);
            },
            onError: async (error_message: string) => {
                const updated_record = await OfflineStorageService.updateProgram(recorded_program.id, {
                    download_status: 'Failed',
                    failed_at: dayjs().format(),
                    error_message: error_message,
                });
                if (updated_record !== null) {
                    upsertProgramRecordInState(updated_record);
                }
                Message.error(`ダウンロードに失敗しました: ${error_message}`);
                is_error_handled_by_callback = true;
            },
        });
        const callbacks_with_release = callbacks as IOfflineDownloadCallbacks & {
            [Comlink.releaseProxy]?: () => void;
        };

        const download_promise = (async (): Promise<boolean> => {
            try {
                await current_worker.download({
                    video_id: recorded_program.id,
                    quality: options.quality,
                    include_comments: options.include_comments,
                    start_sequence: start_sequence,
                    initial_downloaded_segments: initial_downloaded_segments,
                    initial_total_size: initial_total_size,
                    access_token: Utils.getAccessToken(),
                }, callbacks);
                return true;
            } catch (error) {
                const error_message = error instanceof Error ? error.message : 'Unknown error';
                if (error_message === 'Download canceled.') {
                    const updated_record = await OfflineStorageService.updateProgram(recorded_program.id, {
                        download_status: 'Paused',
                        error_message: null,
                    });
                    if (updated_record !== null) {
                        upsertProgramRecordInState(updated_record);
                    }
                    return false;
                }

                if (is_error_handled_by_callback === false) {
                    const updated_record = await OfflineStorageService.updateProgram(recorded_program.id, {
                        download_status: 'Failed',
                        failed_at: dayjs().format(),
                        error_message: error_message,
                    });
                    if (updated_record !== null) {
                        upsertProgramRecordInState(updated_record);
                    }
                    Message.error(`ダウンロードに失敗しました: ${error_message}`);
                }
                return false;
            } finally {
                if (active_download_video_id.value === recorded_program.id) {
                    active_download_video_id.value = null;
                }
                if (active_download_worker === current_worker) {
                    active_download_worker = null;
                }

                // 次の startDownload() を許可する
                active_download_promise = null;

                // Comlink callback proxy を明示的に解放する
                callbacks_with_release[Comlink.releaseProxy]?.();

                // pause/resume を連続で叩かれた場合でも Worker が残らないよう必ず解放する
                await current_worker.terminate();
                await refreshStorageEstimate();
            }
        })();
        // 非同期ダウンロード本体の失敗を未処理例外にしないため、ここで受け止める
        const safe_download_promise = download_promise.catch((error) => {
            console.error('Failed to finalize offline download task:', error);
            return false;
        });
        active_download_promise = safe_download_promise;
        return true;
    };


    /**
     * ダウンロードを一時停止する
     * @param video_id 録画番組 ID
     */
    const pauseDownload = async (video_id: number): Promise<void> => {
        if (active_download_video_id.value !== video_id || active_download_worker === null) {
            return;
        }

        is_pause_in_progress.value = true;
        try {
            // まず Worker に中断要求を投げる
            await active_download_worker.cancel();

            // startDownload() の finally で active_download_video_id / worker 解放が完了するまで待機する
            // ここを待たずに resume すると旧 Worker の onProgress と競合する可能性がある
            if (active_download_promise !== null) {
                await active_download_promise;
            }

            const updated_record = await OfflineStorageService.updateProgram(video_id, {
                download_status: 'Paused',
                error_message: null,
            });
            if (updated_record !== null) {
                upsertProgramRecordInState(updated_record);
            }
            Message.show('ダウンロードを一時停止しました。');
        } finally {
            is_pause_in_progress.value = false;
        }
    };


    /**
     * 一時停止中ダウンロードを再開する
     * @param video_id 録画番組 ID
     */
    const resumeDownload = async (video_id: number): Promise<void> => {
        // 停止完了前の即再開を防止する
        if (active_download_video_id.value !== null || active_download_promise !== null || is_pause_in_progress.value === true) {
            Message.warning('ダウンロードの停止処理が完了してから再開してください。');
            return;
        }

        const record = await OfflineStorageService.getProgram(video_id);
        if (record === null) {
            return;
        }
        await startDownload(record.recorded_program, {
            quality: record.quality,
            include_comments: record.include_comments,
        });
    };


    /**
     * 保存済みオフライン番組を削除する
     * @param video_id 録画番組 ID
     */
    const deleteProgram = async (video_id: number): Promise<void> => {
        if (active_download_video_id.value === video_id && active_download_worker !== null) {
            await pauseDownload(video_id);
        }

        await OfflineStorageService.deleteProgram(video_id);
        offline_programs.value = offline_programs.value.filter((offline_program) => offline_program.id !== video_id);
        Message.show('オフライン保存データを削除しました。');
        await refreshStorageEstimate();
    };


    return {
        offline_programs,
        storage_estimate,
        is_initialized,
        is_supported,
        is_any_downloading,
        active_download_video_id,
        initialize,
        refreshPrograms,
        refreshStorageEstimate,
        getProgramById,
        getProgressPercent,
        startDownload,
        pauseDownload,
        resumeDownload,
        deleteProgram,
    };
});

export default useOfflineManagerStore;
