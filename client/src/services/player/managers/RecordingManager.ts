
import assert from 'assert';

import DPlayer from 'dplayer';

import LiveStreams from '@/services/LiveStreams';
import PlayerManager from '@/services/player/PlayerManager';
import useChannelsStore from '@/stores/ChannelsStore';
import usePlayerStore from '@/stores/PlayerStore';
import useSettingsStore from '@/stores/SettingsStore';
import { useSnackbarsStore } from '@/stores/SnackbarsStore';


/**
 * ついで録画ボタンとクリックイベントをセットアップし、録画開始/停止を行う PlayerManager
 * ライブ視聴時のみ有効
 */
class RecordingManager implements PlayerManager {

    // ユーザー操作により DPlayer 側で画質が切り替わった際、この PlayerManager の再起動が必要かどうかを PlayerController に示す値
    public readonly restart_required_when_quality_switched = false;

    // DPlayer のインスタンス
    private readonly player: DPlayer;

    // 再生モード
    private readonly playback_mode: 'Live' | 'Video';

    // 録画ボタンの HTML 要素
    private recording_button: HTMLDivElement | null = null;

    /**
     * コンストラクタ
     * @param player DPlayer のインスタンス
     * @param playback_mode 再生モード
     */
    constructor(player: DPlayer, playback_mode: 'Live' | 'Video') {
        this.player = player;
        this.playback_mode = playback_mode;
    }


    /**
     * 録画ボタンとクリックイベントのセットアップを行う
     * ライブ視聴時のみボタンを追加する
     */
    public async init(): Promise<void> {

        // ビデオ視聴時は何もしない (ライブ視聴時のみついで録画機能が有効)
        if (this.playback_mode !== 'Live') {
            console.log('[RecordingManager] Skipped (Video mode).');
            return;
        }

        // 万が一すでに録画ボタンが存在していた場合は削除する
        const current_recording_button = this.player.container.querySelector('.dplayer-recording-icon');
        if (current_recording_button !== null) {
            current_recording_button.remove();
        }

        // 録画ボタンの HTML を追加
        // キャプチャボタンの後ろに挿入する
        const capture_button = this.player.container.querySelector('.dplayer-capture-icon');
        if (capture_button === null) {
            console.error('[RecordingManager] Capture button not found.');
            return;
        }

        capture_button.insertAdjacentHTML('afterend', `
            <div class="dplayer-icon dplayer-recording-icon" aria-label="ついで録画"
                data-balloon-nofocus="" data-balloon-pos="up">
                <span class="dplayer-icon-content">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="10" /></svg>
                </span>
            </div>
        `);
        this.recording_button = this.player.container.querySelector('.dplayer-recording-icon');
        if (this.recording_button === null) {
            console.error('[RecordingManager] Failed to create recording button.');
            return;
        }

        // 録画ボタンがクリックされたときのイベントを登録
        this.recording_button.addEventListener('click', () => this.toggleRecording());

        // PlayerStore の録画状態を監視し、録画中はボタンのハイライトを追加/削除する
        const playerStore = usePlayerStore();
        playerStore.$subscribe((mutation, state) => {
            if (state.is_live_recording) {
                this.addHighlight();
            } else {
                this.removeHighlight();
            }
        });

        // 初期状態で録画中の場合はハイライトを追加
        if (playerStore.is_live_recording) {
            this.addHighlight();
        }

        console.log('[RecordingManager] Initialized.');
    }


    /**
     * 録画ボタンのハイライト (ボタンの周囲が赤くなる) を追加する
     */
    private addHighlight(): void {
        assert(this.recording_button !== null);
        this.recording_button.classList.add('dplayer-recording');
    }


    /**
     * 録画ボタンのハイライト (ボタンの周囲が赤くなる) を外す
     */
    private removeHighlight(): void {
        assert(this.recording_button !== null);
        this.recording_button.classList.remove('dplayer-recording');
    }


    /**
     * ついで録画の開始/停止を切り替える
     */
    private async toggleRecording(): Promise<void> {
        const channelsStore = useChannelsStore();
        const playerStore = usePlayerStore();
        const settingsStore = useSettingsStore();
        const snackbarsStore = useSnackbarsStore();

        // ビデオ視聴モードでは使用不可（UI から呼ばれない想定だが二重にガードしておく）
        if (this.playback_mode !== 'Live') {
            console.debug('[RecordingManager] Recording is disabled in Video mode.');
            snackbarsStore.show('error', 'ついで録画はビデオ視聴モードでは使用できません。', 5);
            return;
        }

        // ONAir 状態でない場合は録画できない
        if (playerStore.live_stream_status !== 'ONAir') {
            snackbarsStore.show('error', '放送中のみ録画できます。', 5);
            return;
        }

        try {
            const quality = settingsStore.settings.tv_streaming_quality;

            if (playerStore.is_live_recording) {
                // 録画を停止
                const result = await LiveStreams.stopRecording(channelsStore.display_channel_id, quality);
                // スナックバーで通知を表示
                await snackbarsStore.show('success', result.message, 5);
            } else {
                // 録画を開始
                const result = await LiveStreams.startRecording(channelsStore.display_channel_id, quality);
                // スナックバーで通知を表示
                await snackbarsStore.show('success', result.message, 5);
            }
        } catch (error) {
            console.error('Recording toggle error:', error);
            // エラーメッセージを表示
            const error_message = error instanceof Error ? error.message : '録画の切り替えに失敗しました。';
            await snackbarsStore.show('error', error_message, 7);
        }
    }

    public async destroy(): Promise<void> {
    }
}


export default RecordingManager;
