<template>
    <Watch :playback_mode="'Video'" :is_offline="true" />
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import type { OfflineDownloadMetadata } from '@/offline/types';
import type { IChannel } from '@/services/Channels';

import Watch from '@/components/Watch/Watch.vue';
import Message from '@/message';
import PlayerController from '@/services/player/PlayerController';
import { IRecordedProgramDefault, IRecordedVideoDefault, type IRecordedProgram, type IRecordedVideo } from '@/services/Videos';
import useOfflineStore from '@/stores/OfflineStore';
import usePlayerStore from '@/stores/PlayerStore';
import useSettingsStore from '@/stores/SettingsStore';

// PlayerController のインスタンス
let player_controller: PlayerController | null = null;

// オフライン保存メタデータから録画番組情報を組み立てるユーティリティ
const createRecordedProgramFromDownload = (download: OfflineDownloadMetadata): IRecordedProgram => {

    const recorded_video: IRecordedVideo = {
        ...IRecordedVideoDefault,
        id: download.recorded_program.video_id,
        status: 'Recorded',
        file_path: download.recorded_program.video_file_path,
        file_size: download.recorded_program.video_file_size,
        file_created_at: download.recorded_program.start_time,
        file_modified_at: download.recorded_program.end_time,
        recording_start_time: download.recorded_program.start_time,
        recording_end_time: download.recorded_program.end_time,
        duration: download.recorded_program.duration,
        container_format: 'MPEG-TS',
        video_codec: download.is_hevc ? 'H.265' : 'H.264',
        video_codec_profile: 'High',
        video_scan_type: 'Interlaced',
        video_frame_rate: 29.97,
        video_resolution_width: download.recorded_program.video_resolution_width,
        video_resolution_height: download.recorded_program.video_resolution_height,
        primary_audio_codec: 'AAC-LC',
        primary_audio_channel: 'Stereo',
        primary_audio_sampling_rate: 48000,
        secondary_audio_codec: null,
        secondary_audio_channel: null,
        secondary_audio_sampling_rate: null,
        has_key_frames: true,
        cm_sections: [],
        is_tsreplace_encoded: false,
        tsreplace_encoded_at: null,
        original_video_codec: download.is_hevc ? 'H.265' : 'H.264',
        created_at: download.created_at,
        updated_at: download.updated_at,
    };

    const recorded_program: IRecordedProgram = {
        ...IRecordedProgramDefault,
        id: download.recorded_program.id,
        recorded_video,
        recording_start_margin: 0,
        recording_end_margin: 0,
        is_partially_recorded: false,
        channel: null,
        network_id: null,
        service_id: null,
        event_id: null,
        series_id: null,
        series_broadcast_period_id: null,
        title: download.recorded_program.title,
        series_title: download.recorded_program.series_title,
        episode_number: download.recorded_program.episode_number,
        subtitle: download.recorded_program.subtitle,
        description: download.recorded_program.description,
        detail: {},
        start_time: download.recorded_program.start_time,
        end_time: download.recorded_program.end_time,
        duration: download.recorded_program.duration,
        is_free: true,
        genres: download.recorded_program.genres.map((genre) => ({
            major: genre.major,
            middle: genre.middle,
        })),
        primary_audio_type: '2/0モード(ステレオ)',
        primary_audio_language: '日本語',
        secondary_audio_type: null,
        secondary_audio_language: null,
        created_at: download.created_at,
        updated_at: download.updated_at,
    };

    let channel: IChannel | null = null;
    const channelId = download.recorded_program.channel_id ?? null;
    if (channelId !== null) {
        channel = {
            id: channelId,
            display_channel_id: download.recorded_program.channel_display_id ?? channelId,
            network_id: download.recorded_program.channel_network_id ?? 0,
            service_id: download.recorded_program.channel_service_id ?? 0,
            transport_stream_id: download.recorded_program.channel_transport_stream_id ?? null,
            remocon_id: download.recorded_program.channel_remocon_id ?? 0,
            channel_number: download.recorded_program.channel_number ?? '--',
            type: download.recorded_program.channel_type ?? 'GR',
            name: download.recorded_program.channel_name ?? 'オフライン再生',
            jikkyo_force: null,
            is_subchannel: download.recorded_program.channel_is_subchannel ?? false,
            is_radiochannel: download.recorded_program.channel_is_radiochannel ?? false,
            is_watchable: download.recorded_program.channel_is_watchable ?? true,
        };
    }

    recorded_program.channel = channel;
    recorded_program.network_id = channel?.network_id ?? null;
    recorded_program.service_id = channel?.service_id ?? null;

    return recorded_program;
};

export default defineComponent({
    name: 'Offline-Watch',
    components: {
        Watch,
    },
    computed: {
        ...mapStores(useOfflineStore, usePlayerStore, useSettingsStore),
    },
    // 最初に実行
    async beforeCreate() {
        // PlayerStore にオフラインダウンロード情報を事前設定
        // これにより、Watch コンポーネントの startWatching() -> reset() で消されるのを防ぐ
        const player_store = usePlayerStore();
        const offline_store = useOfflineStore();

        // オフラインストアを初期化（まだの場合）
        if (!offline_store.initialized) {
            await offline_store.initialize();
        }

        // URL パラメータからダウンロード ID を取得
        const download_id = this.$route.params.download_id as string;
        if (download_id) {
            const download = offline_store.downloads.find(d => d.id === download_id);
            if (download) {
                console.log('[Offline/Watch] Setting offline_download in beforeCreate:', download.id);
                player_store.offline_download = download;
                player_store.recorded_program = createRecordedProgramFromDownload(download);
            }
        }
    },
    // 開始時に実行
    created() {

        // 下記以外の視聴画面の開始処理は Watch コンポーネントの方で自動的に行われる

        // 再生セッションを初期化
        this.init();
    },
    // ダウンロード切り替え時に実行
    // コンポーネント（インスタンス）は再利用される
    beforeRouteUpdate(to, from, next) {

        // 前の再生セッションを破棄して終了し、完了を待ってから次のルートに進む
        this.destroy().then(() => {
            this.init();
            next();
        });
    },
    // 終了前に実行
    beforeUnmount() {

        // destroy() を実行
        // 別のページへ遷移するため、DPlayer のインスタンスを確実に破棄する
        this.destroy();

        // 上記以外の視聴画面の終了処理は Watch コンポーネントの方で自動的に行われる
    },
    methods: {

        // 再生セッションを初期化する
        async init() {

            // オフラインストアを初期化
            if (this.offlineStore.initialized === false) {
                await this.offlineStore.initialize();
            }
            if (this.offlineStore.initialization_error !== null) {
                Message.error(this.offlineStore.initialization_error);
                this.$router.push({path: '/offline/'});
                return;
            }

            // URL 上のダウンロード ID が未定義なら実行しない (フェイルセーフ)
            if (this.$route.params.download_id === undefined) {
                this.$router.push({path: '/offline/'});
                return;
            }

            // ダウンロード情報を取得
            const download_id = this.$route.params.download_id as string;
            const download = this.offlineStore.downloads.find(d => d.id === download_id);
            if (download === undefined) {
                Message.error('指定されたオフライン保存データが見つかりません。');
                this.$router.push({path: '/offline/'});
                return;
            }

            // ダウンロードが完了していない場合は視聴できない
            if (download.status !== 'completed') {
                Message.warning('ダウンロードが完了していないため視聴できません。');
                this.$router.push({path: '/offline/'});
                return;
            }

            // PlayerStore にオフラインダウンロード情報を設定
            this.playerStore.offline_download = download;

            // 録画番組情報を PlayerStore に設定
            this.playerStore.recorded_program = createRecordedProgramFromDownload(download);

            // Vue の次の DOM 更新サイクルまで待機し、Pinia の状態が確実に反映されるようにする
            await this.$nextTick();

            // PlayerController を初期化
            // オフライン視聴はビデオ視聴として扱う（動画ソースのみオフラインから取得）
            try {
                player_controller = new PlayerController('Video');
                await player_controller.init();
            } catch (error) {
                Message.error('プレイヤーの初期化に失敗しました。');
                console.error('PlayerController initialization failed:', error);
                this.$router.push({path: '/offline/'});
                return;
            }
        },
        // 再生セッションを破棄する
        // 再生するダウンロードを切り替える際にも実行される
        async destroy() {

            // PlayerController を破棄
            if (player_controller !== null) {
                await player_controller.destroy();
                player_controller = null;
            }
            // オフライン視聴用の状態をリセット
            this.playerStore.offline_download = null;
            this.playerStore.recorded_program = IRecordedProgramDefault;
        }
    }
});

</script>