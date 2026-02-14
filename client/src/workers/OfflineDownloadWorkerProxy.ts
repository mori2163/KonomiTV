
import * as Comlink from 'comlink';

import type {
    IOfflineDownloadCallbacks,
    IOfflineDownloadOptions,
    IOfflineDownloadWorkerConstructor,
    IOfflineDownloadWorker,
} from '@/workers/OfflineDownloadWorker';


/**
 * OfflineDownloadWorker を Web Worker 上で動作させるためのラッパー
 *
 * Comlink の releaseProxy と Worker.terminate() の両方を明示的に呼び出し、
 * pause/restart が連続した場合でも古い Worker が残留しないようにする。
 */
class OfflineDownloadWorkerProxy implements IOfflineDownloadWorker {

    private readonly worker: Worker;
    private readonly remote_worker_constructor: Comlink.Remote<IOfflineDownloadWorkerConstructor>;
    private readonly remote_worker_promise: Promise<Comlink.Remote<IOfflineDownloadWorker>>;
    private is_terminated: boolean = false;


    constructor() {
        this.worker = new Worker(new URL('./OfflineDownloadWorker', import.meta.url), {
            type: 'module',
        });
        this.remote_worker_constructor = Comlink.wrap<IOfflineDownloadWorkerConstructor>(this.worker);
        this.remote_worker_promise = new this.remote_worker_constructor();
    }


    /**
     * ダウンロードを開始する
     * @param options ダウンロード設定
     * @param callbacks 進捗通知コールバック
     */
    public async download(options: IOfflineDownloadOptions, callbacks: IOfflineDownloadCallbacks): Promise<void> {
        const remote_worker = await this.remote_worker_promise;
        // Comlink 越しに関数を渡すには proxy 化が必要
        const proxied_callbacks: IOfflineDownloadCallbacks = {
            onProgress: Comlink.proxy(callbacks.onProgress),
            onCompleted: Comlink.proxy(callbacks.onCompleted),
            onError: Comlink.proxy(callbacks.onError),
        };
        await remote_worker.download(options, proxied_callbacks);
    }


    /**
     * 進行中ダウンロードを中断する
     */
    public async cancel(): Promise<void> {
        const remote_worker = await this.remote_worker_promise;
        await remote_worker.cancel();
    }


    /**
     * Worker と Comlink プロキシを解放する
     */
    public async terminate(): Promise<void> {
        if (this.is_terminated === true) {
            return;
        }
        this.is_terminated = true;

        // Comlink の Remote Proxy を解放する
        const remote_worker = await this.remote_worker_promise.catch(() => null);
        if (remote_worker !== null) {
            const remote_with_release = remote_worker as Comlink.Remote<IOfflineDownloadWorker> & {
                [Comlink.releaseProxy]?: () => void;
            };
            remote_with_release[Comlink.releaseProxy]?.();
        }

        // Remote Constructor Proxy も解放する
        const constructor_with_release = this.remote_worker_constructor as Comlink.Remote<IOfflineDownloadWorkerConstructor> & {
            [Comlink.releaseProxy]?: () => void;
        };
        constructor_with_release[Comlink.releaseProxy]?.();

        // Worker スレッド自体を終了させる
        this.worker.terminate();
    }
}

export default OfflineDownloadWorkerProxy;
