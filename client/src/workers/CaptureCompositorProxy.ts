
import { ICaptureCompositor, ICaptureCompositorOptions } from '@/workers/CaptureCompositor';


// Worker 側で expose している API の型
export type ICaptureCompositorWorkerAPI = {
    loadFonts(): Promise<void>;
    create(options: ICaptureCompositorOptions): Promise<ICaptureCompositor>;
};

// CaptureCompositor を Web Worker 上で動作させるためのラッパー
// Comlink を経由し、Web Worker とメインスレッド間でオブジェクトをやり取りする
// ラップ元と同じファイルに定義するとビルド時に循環参照の警告が出る可能性があるため、別ファイルに定義している
const CaptureCompositorProxy =
    new ComlinkWorker<ICaptureCompositorWorkerAPI>(new URL('./CaptureCompositor', import.meta.url));
export default CaptureCompositorProxy;
