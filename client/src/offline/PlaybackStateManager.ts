export enum PlaybackState {
    UNINITIALIZED = 'uninitialized',
    INITIALIZING = 'initializing',
    LOADING_METADATA = 'loading_metadata',
    LOADING_PLAYLIST = 'loading_playlist',
    READY = 'ready',
    PLAYING = 'playing',
    PAUSED = 'paused',
    SEEKING = 'seeking',
    BUFFERING = 'buffering',
    ENDED = 'ended',
    ERROR = 'error',
}

export class PlaybackStateManager {
    private currentState: PlaybackState = PlaybackState.UNINITIALIZED;
    private listeners: Set<(state: PlaybackState) => void> = new Set();

    // 状態を変更
    setState(newState: PlaybackState): void {
        const oldState = this.currentState;
        if (!this.isValidTransition(oldState, newState)) {
            console.warn(`[PlaybackState] Invalid state transition: ${oldState} -> ${newState}`);
            return;
        }
        this.currentState = newState;
        console.log(`[PlaybackState] Transition: ${oldState} -> ${newState}`);
        this.notifyListeners(newState);
    }

    // 現在の状態
    getState(): PlaybackState {
        return this.currentState;
    }

    // 状態遷移の定義
    private isValidTransition(from: PlaybackState, to: PlaybackState): boolean {
        const validTransitions: Record<PlaybackState, PlaybackState[]> = {
            [PlaybackState.UNINITIALIZED]: [PlaybackState.INITIALIZING],
            [PlaybackState.INITIALIZING]: [PlaybackState.LOADING_METADATA, PlaybackState.ERROR],
            [PlaybackState.LOADING_METADATA]: [PlaybackState.LOADING_PLAYLIST, PlaybackState.ERROR],
            [PlaybackState.LOADING_PLAYLIST]: [PlaybackState.READY, PlaybackState.ERROR],
            [PlaybackState.READY]: [PlaybackState.PLAYING, PlaybackState.ERROR],
            [PlaybackState.PLAYING]: [
                PlaybackState.PAUSED,
                PlaybackState.SEEKING,
                PlaybackState.BUFFERING,
                PlaybackState.ENDED,
                PlaybackState.ERROR,
            ],
            [PlaybackState.PAUSED]: [PlaybackState.PLAYING, PlaybackState.SEEKING, PlaybackState.ERROR],
            [PlaybackState.SEEKING]: [PlaybackState.PLAYING, PlaybackState.BUFFERING, PlaybackState.ERROR],
            [PlaybackState.BUFFERING]: [PlaybackState.PLAYING, PlaybackState.ERROR],
            [PlaybackState.ENDED]: [PlaybackState.LOADING_PLAYLIST, PlaybackState.UNINITIALIZED],
            [PlaybackState.ERROR]: [PlaybackState.UNINITIALIZED],
        };
        return validTransitions[from]?.includes(to) ?? false;
    }

    // リスナー登録
    addListener(callback: (state: PlaybackState) => void): () => void {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    // リスナー通知
    private notifyListeners(state: PlaybackState): void {
        this.listeners.forEach(callback => callback(state));
    }
}
