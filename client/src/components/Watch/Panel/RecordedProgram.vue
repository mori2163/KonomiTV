<template>
    <div class="program-container">
        <section class="program-info">
            <h1 class="program-info__title"
                v-html="ProgramUtils.decorateProgramInfo(playerStore.recorded_program, 'title')">
            </h1>
            <div class="program-info__broadcaster">
                <img class="program-info__broadcaster-icon"
                    :src="`${Utils.api_base_url}/channels/${playerStore.recorded_program.channel?.id ?? 'NID0-SID0'}/logo`">
                <div class="program-info__broadcaster-container">
                    <div class="d-flex align-center" v-if="playerStore.recorded_program.channel !== null">
                        <div class="program-info__broadcaster-number">Ch: {{playerStore.recorded_program.channel.channel_number}}</div>
                        <div class="program-info__broadcaster-name">{{playerStore.recorded_program.channel.name}}</div>
                    </div>
                    <div class="d-flex align-center" v-else>
                        <div class="program-info__broadcaster-number">チャンネル情報なし</div>
                    </div>
                    <div class="program-info__broadcaster-time">
                        {{ProgramUtils.getProgramTime(playerStore.recorded_program)}}
                    </div>
                </div>
            </div>
            <div class="program-info__description"
                v-html="ProgramUtils.decorateProgramInfo(playerStore.recorded_program, 'description')">
            </div>
            <div class="program-info__genre-container">
                <div class="program-info__genre" :key="genre_index"
                    v-for="(genre, genre_index) in playerStore.recorded_program.genres ?? []">
                    {{genre.major}} / {{genre.middle}}
                </div>
            </div>
            <div class="mt-5">
                <div class="program-info__status">
                    <Icon icon="ic:round-date-range" height="17px" style="margin-left: -2px; margin-right: -1.7px; margin-bottom: -3px;" />
                    <span class="ml-2">録画期間: {{playerStore.recorded_program.is_partially_recorded ? '(一部のみ録画)' : ''}}</span><br>
                    <span>{{ProgramUtils.getRecordingTime(playerStore.recorded_program)}}</span>
                </div>
                <div class="program-info__status">
                    <Icon icon="bi:chat-left-text-fill" height="12.5px" style="margin-bottom: -3px" />
                    <span class="ml-2">コメント数:</span>
                    <span class="ml-2">{{comment_count ?? '--'}}</span>
                </div>
                <div v-ripple class="program-info__button" @click="toggleMylist">
                    <template v-if="isInMylist">
                        <Icon icon="fluent:checkmark-16-filled" width="18px" height="18px"
                            style="color: rgb(var(--v-theme-primary)); margin-bottom: -1px" />
                        <span style="margin-left: 6px;">マイリストに追加済み</span>
                    </template>
                    <template v-else>
                        <Icon icon="fluent:add-16-filled" width="18px" height="18px" style="margin-bottom: -1px" />
                        <span style="margin-left: 6px;">マイリストに追加</span>
                    </template>
                </div>
                <div class="program-info__offline">
                    <div class="program-info__offline-header">
                        <Icon icon="fluent:arrow-download-24-regular" width="20px" class="program-info__offline-icon" />
                        <div>
                            <div class="program-info__offline-title">オフライン視聴</div>
                            <div class="program-info__offline-subtitle">ダウンロードしてネットワークがなくても視聴できます。</div>
                        </div>
                    </div>
                    <v-alert
                        v-if="offlineStore.initialization_error"
                        type="error"
                        variant="tonal"
                        density="comfortable"
                        class="program-info__offline-alert"
                    >
                        {{ offlineStore.initialization_error }}
                    </v-alert>
                    <template v-else>
                        <div v-if="offlineDownload" class="program-info__offline-status">
                            <div class="program-info__offline-status-header">
                                <span class="program-info__offline-badge" :class="`program-info__offline-badge--${offlineDownload.status}`">
                                    {{ offlineStatusLabel }}
                                </span>
                                <span v-if="offlineSummaryText" class="program-info__offline-summary">{{ offlineSummaryText }}</span>
                            </div>
                            <div v-if="offlineDownload.status === 'downloading'" class="program-info__offline-progress">
                                <v-progress-linear
                                    color="primary"
                                    height="8"
                                    rounded
                                    :model-value="offlineProgressPercent"
                                />
                                <div class="program-info__offline-progress-text">
                                    <span>{{ offlineProgressSegments }}</span>
                                    <span>{{ offlineProgressBytes }}</span>
                                </div>
                            </div>
                            <div class="program-info__offline-actions">
                                <v-btn
                                    size="small"
                                    variant="flat"
                                    color="primary"
                                    class="program-info__offline-action"
                                    @click="navigateOfflineManagePage"
                                >
                                    <Icon icon="fluent:open-16-regular" width="16px" class="mr-1" />
                                    管理ページを開く
                                </v-btn>
                                <v-btn
                                    v-if="offlineDownload.status === 'downloading'"
                                    size="small"
                                    variant="outlined"
                                    color="warning"
                                    class="program-info__offline-action"
                                    :loading="offline_is_canceling"
                                    @click="cancelOfflineDownload"
                                >
                                    <Icon icon="fluent:pause-16-regular" width="16px" class="mr-1" />
                                    ダウンロードを停止
                                </v-btn>
                                <v-btn
                                    v-else-if="offlineDownload.status === 'paused' || offlineDownload.status === 'error'"
                                    size="small"
                                    variant="outlined"
                                    color="primary"
                                    class="program-info__offline-action"
                                    @click="retryOfflineDownload"
                                >
                                    <Icon icon="fluent:arrow-clockwise-16-regular" width="16px" class="mr-1" />
                                    再ダウンロード
                                </v-btn>
                                <v-btn
                                    v-else
                                    size="small"
                                    variant="outlined"
                                    color="primary"
                                    class="program-info__offline-action"
                                    @click="navigateOfflineWatchPage"
                                >
                                    <Icon icon="fluent:play-16-regular" width="16px" class="mr-1" />
                                    オフラインで再生
                                </v-btn>
                            </div>
                        </div>
                        <div v-else class="program-info__offline-empty">
                            <p>録画番組の詳細を保存して、外出先でも視聴できます。</p>
                            <div class="program-info__offline-actions">
                                <v-btn
                                    size="small"
                                    variant="tonal"
                                    color="primary"
                                    class="program-info__offline-action"
                                    @click="openOfflineDialog"
                                >
                                    <Icon icon="fluent:arrow-download-20-regular" width="16px" class="mr-1" />
                                    オフライン保存を開始
                                </v-btn>
                            </div>
                        </div>
                    </template>
                </div>
            </div>
        </section>
        <section class="program-detail-container">
            <div class="program-detail" :key="detail_heading"
                v-for="(detail_text, detail_heading) in playerStore.recorded_program.detail ?? {}">
                <h2 class="program-detail__heading">{{detail_heading}}</h2>
                <div class="program-detail__text" v-html="Utils.URLtoLink(detail_text)"></div>
            </div>
        </section>
        <v-dialog v-model="is_offline_dialog_open" max-width="420">
            <v-card>
                <v-card-title class="text-subtitle-1 font-weight-bold">オフライン保存</v-card-title>
                <v-card-text>
                    <p class="offline-dialog__description">
                        保存する画質と映像コーデックを選択してください。保存処理中もこの画面で進捗を確認できます。
                    </p>
                    <v-select
                        v-model="offline_selected_quality"
                        :items="videoQualityOptions"
                        item-title="label"
                        item-value="value"
                        label="保存する画質"
                        density="comfortable"
                        variant="outlined"
                    />
                    <v-switch
                        v-model="offline_use_hevc"
                        class="mt-2"
                        color="primary"
                        hide-details
                        inset
                        :disabled="!canUseHevc"
                        :label="canUseHevc ? 'HEVC (H.265) を使用する' : 'HEVC (H.265) を使用できません'"
                    />
                    <p class="offline-dialog__hint" :class="{'offline-dialog__hint--disabled': !canUseHevc}">
                        HEVC は同じ画質でもファイルサイズを抑えられますが、対応していない端末では再生できません。
                    </p>
                    <v-switch
                        v-model="offline_save_comments"
                        class="mt-3"
                        color="primary"
                        hide-details
                        inset
                        :label="offline_save_comments ? 'コメントも保存する' : 'コメントは保存しない'"
                    />
                    <p class="offline-dialog__hint offline-dialog__hint--secondary">
                        コメントを保存すると、オフライン再生時に実況コメントを表示できます。
                    </p>
                </v-card-text>
                <v-card-actions class="justify-end">
                    <v-btn variant="text" @click="closeOfflineDialog" :disabled="offline_is_starting">キャンセル</v-btn>
                    <v-btn
                        variant="flat"
                        color="primary"
                        :loading="offline_is_starting"
                        @click="startOfflineDownload"
                    >
                        保存を開始
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>
<script lang="ts">


import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import type { OfflineDownloadMetadata, OfflineDownloadProgressUpdate } from '@/offline/types';
import type { VideoStreamingQuality } from '@/stores/SettingsStore';

import Message from '@/message';
import OfflineDownloadManager from '@/offline/manager';
import OfflineStorage from '@/offline/storage';
import useOfflineStore from '@/stores/OfflineStore';
import usePlayerStore from '@/stores/PlayerStore';
import useSettingsStore, { VIDEO_STREAMING_QUALITIES } from '@/stores/SettingsStore';
import Utils, { PlayerUtils, ProgramUtils, dayjs } from '@/utils';

export default defineComponent({
    name: 'Panel-RecordedProgramTab',
    data() {
        return {
            // ユーティリティをテンプレートで使えるように
            Utils: Object.freeze(Utils),
            ProgramUtils: Object.freeze(ProgramUtils),

            // コメント数カウント
            comment_count: null as number | null,
            // オフライン保存 UI の状態
            is_offline_dialog_open: false,
            offline_selected_quality: '1080p' as VideoStreamingQuality,
            offline_use_hevc: false,
            offline_save_comments: true,
            offline_is_starting: false,
            offline_is_canceling: false,
            offline_dialog_mode: 'create' as 'create' | 'redownload',
            hevc_supported: PlayerUtils.isHEVCVideoSupported(),
        };
    },
    computed: {
        ...mapStores(usePlayerStore, useSettingsStore, useOfflineStore),

        // マイリストに追加されているかどうか
        isInMylist(): boolean {
            return this.settingsStore.settings.mylist.some(item =>
                item.type === 'RecordedProgram' && item.id === this.playerStore.recorded_program.id
            );
        },
        // 現在の録画番組に紐づくオフラインダウンロードメタデータ
        offlineDownload(): OfflineDownloadMetadata | null {
            return this.offlineStore.downloads.find(download => download.video_id === this.playerStore.recorded_program.id) ?? null;
        },
        // 現在進行中のダウンロード進捗
        offlineProgress(): OfflineDownloadProgressUpdate | undefined {
            if (this.offlineDownload === null) {
                return undefined;
            }
            return this.offlineStore.progress[this.offlineDownload.id];
        },
        // オフラインダウンロードの状態ラベル
        offlineStatusLabel(): string {
            if (this.offlineDownload === null) {
                return '';
            }
            switch (this.offlineDownload.status) {
                case 'downloading':
                    return 'ダウンロード中';
                case 'completed':
                    return '保存済み';
                case 'paused':
                    return '停止中';
                case 'error':
                    return 'エラー';
                default:
                    return this.offlineDownload.status;
            }
        },
        // オフラインメタデータの概要テキスト
        offlineSummaryText(): string {
            if (this.offlineDownload === null) {
                return '';
            }
            const quality = this.formatQualityLabel(this.offlineDownload.quality);
            const codec = this.offlineDownload.is_hevc ? 'HEVC' : 'H.264';
            const updated = dayjs(this.offlineDownload.updated_at).format('YYYY/MM/DD HH:mm');
            const comment = this.offlineDownload.save_comments ? 'コメント保存あり' : 'コメントなし';
            return `${quality} ・ ${codec} ・ ${comment} ・ 更新: ${updated}`;
        },
        // プログレスバーに表示する進捗率
        offlineProgressPercent(): number {
            if (this.offlineDownload === null) {
                return 0;
            }
            if (this.offlineDownload.status === 'completed') {
                return 100;
            }
            const progress = this.offlineProgress;
            if (progress === undefined || progress.total_segments === 0) {
                return 0;
            }
            return Math.min(100, Math.round((progress.downloaded_segments / progress.total_segments) * 100));
        },
        // セグメント数の進捗表示
        offlineProgressSegments(): string {
            const total = this.offlineProgress?.total_segments ?? this.offlineDownload?.segment_count ?? 0;
            const current = this.offlineProgress?.downloaded_segments ?? (this.offlineDownload?.status === 'completed' ? total : 0);
            if (total === 0) {
                return '';
            }
            return `${current} / ${total} セグメント`;
        },
        // ダウンロード済みサイズの進捗表示
        offlineProgressBytes(): string {
            if (this.offlineDownload === null) {
                return '';
            }
            const downloaded = this.offlineProgress?.downloaded_bytes ?? this.offlineDownload.downloaded_bytes;
            const totalBytes = this.offlineProgress?.total_bytes_estimated ?? this.offlineDownload.total_size;
            const totalText = totalBytes > 0 ? Utils.formatBytes(totalBytes) : '--';
            return `${Utils.formatBytes(downloaded)} / ${totalText}`;
        },
        // オフライン保存で選択可能な画質一覧
        videoQualityOptions(): Array<{label: string; value: VideoStreamingQuality}> {
            return VIDEO_STREAMING_QUALITIES.map(quality => ({
                label: this.formatQualityLabel(quality),
                value: quality,
            }));
        },
        // HEVC が利用できるかどうか
        canUseHevc(): boolean {
            return this.hevc_supported === true;
        },
    },
    methods: {
        // マイリストの追加/削除を切り替える
        toggleMylist(): void {
            const program = this.playerStore.recorded_program;
            if (this.isInMylist) {
                // マイリストから削除
                this.settingsStore.settings.mylist = this.settingsStore.settings.mylist.filter(item =>
                    !(item.type === 'RecordedProgram' && item.id === program.id)
                );
                Message.show('マイリストから削除しました。');
            } else {
                // マイリストに追加
                this.settingsStore.settings.mylist.push({
                    type: 'RecordedProgram',
                    id: program.id,
                    created_at: Utils.time(),  // 秒単位
                });
            }
        },
        // オフライン保存用の画質ラベルを整形する
        formatQualityLabel(quality: string): string {
            return quality === '1080p-60fps' ? '1080p (60fps)' : quality;
        },
        // オフライン保存のためにストアを初期化する
        async prepareOfflineContext(showError: boolean = true): Promise<void> {
            if (this.offlineStore.initialized === false) {
                await this.offlineStore.initialize();
            }
            if (this.offlineStore.initialization_error !== null && showError === true) {
                Message.error(this.offlineStore.initialization_error);
            }
        },
        // 既定の画質と HEVC 設定を同期する
        syncDefaultOfflineOptions(): void {
            const defaultQuality = this.settingsStore.settings.video_streaming_quality as VideoStreamingQuality;
            this.offline_selected_quality = defaultQuality;
            this.offline_use_hevc = this.hevc_supported === true && this.settingsStore.settings.video_data_saver_mode === true;
            this.offline_save_comments = true;
            if (this.offlineDownload !== null) {
                this.offline_selected_quality = this.offlineDownload.quality as VideoStreamingQuality;
                this.offline_use_hevc = this.offlineDownload.is_hevc;
                this.offline_save_comments = this.offlineDownload.save_comments ?? true;
            }
            if (this.hevc_supported === false) {
                this.offline_use_hevc = false;
            }
        },
        // オフライン保存ダイアログを開く
        async openOfflineDialog(mode: 'create' | 'redownload' = 'create'): Promise<void> {
            await this.prepareOfflineContext();
            if (this.offlineStore.initialization_error !== null) {
                return;
            }
            this.syncDefaultOfflineOptions();
            this.offline_dialog_mode = mode;
            this.is_offline_dialog_open = true;
        },
        // オフライン保存ダイアログを閉じる
        closeOfflineDialog(): void {
            this.is_offline_dialog_open = false;
            this.offline_dialog_mode = 'create';
        },
        // オフライン保存を開始する
        async startOfflineDownload(): Promise<void> {
            await this.prepareOfflineContext();
            if (this.offlineStore.initialization_error !== null) {
                Message.error(this.offlineStore.initialization_error);
                return;
            }
            const isRedownload = this.offline_dialog_mode === 'redownload';
            this.offline_is_starting = true;
            if (isRedownload === true && this.offlineDownload === null) {
                Message.error('再ダウンロード対象のデータが見つかりませんでした。');
                this.offline_is_starting = false;
                this.offline_dialog_mode = 'create';
                return;
            }
            if (isRedownload === true && this.offlineDownload !== null) {
                try {
                    await OfflineStorage.removeDownload(this.offlineDownload);
                    this.offlineStore.removeDownload(this.offlineDownload.id);
                    await this.offlineStore.refreshDownloads();
                } catch (error) {
                    console.error('[Panel-RecordedProgramTab] Failed to remove existing offline data before redownload.', error);
                    Message.error('既存のオフラインデータを削除できませんでした。');
                    this.offline_is_starting = false;
                    this.offline_dialog_mode = 'create';
                    return;
                }
            }
            const successMessage = isRedownload ? '再ダウンロードを開始しました。' : 'オフライン保存を開始しました。';
            const metadata = await this.runOfflineDownload(
                this.offline_selected_quality,
                this.offline_use_hevc,
                this.offline_save_comments,
                successMessage,
            );
            this.offline_is_starting = false;
            if (metadata !== null) {
                this.is_offline_dialog_open = false;
                this.syncDefaultOfflineOptions();
                Message.success(successMessage);
            }
            this.offline_dialog_mode = 'create';
        },
        // 実際のオフライン保存処理を呼び出す共通メソッド
        async runOfflineDownload(
            quality: VideoStreamingQuality,
            useHevc: boolean,
            saveComments: boolean,
            successMessage: string,
        ): Promise<OfflineDownloadMetadata | null> {
            try {
                const metadata = await OfflineDownloadManager.startDownload(this.playerStore.recorded_program, {
                    quality,
                    isHevc: useHevc,
                    saveComments,
                });
                return metadata;
            } catch (error: unknown) {
                if (error instanceof DOMException && error.name === 'AbortError') {
                    Message.info('オフライン保存を中止しました。');
                } else {
                    console.error('[Panel-RecordedProgramTab] Failed to start offline download.', error);
                    const message = error instanceof Error && error.message ? error.message : 'オフライン保存を開始できませんでした。';
                    Message.error(message);
                }
                return null;
            }
        },
        // 進行中のダウンロードを停止する
        cancelOfflineDownload(): void {
            if (this.offlineDownload === null) {
                return;
            }
            this.offline_is_canceling = true;
            OfflineDownloadManager.cancelDownload(this.offlineDownload.id);
            setTimeout(() => {
                this.offline_is_canceling = false;
            }, 300);
            Message.info('ダウンロードを停止しました。');
        },
        // オフラインデータを削除して再ダウンロードする
        async retryOfflineDownload(): Promise<void> {
            if (this.offlineDownload === null) {
                return;
            }
            if (window.confirm('既存のオフラインデータを削除して再ダウンロードしますか？') === false) {
                return;
            }
            await this.prepareOfflineContext();
            if (this.offlineStore.initialization_error !== null) {
                Message.error(this.offlineStore.initialization_error);
                return;
            }
            this.syncDefaultOfflineOptions();
            this.offline_dialog_mode = 'redownload';
            this.is_offline_dialog_open = true;
        },
        // オフライン管理ページへ遷移する
        navigateOfflineManagePage(): void {
            const query = this.offlineDownload ? { id: this.offlineDownload.id } : undefined;
            this.$router.push({ path: '/offline/', query }).catch(() => undefined);
        },
        // オフライン再生ページへ遷移する
        navigateOfflineWatchPage(): void {
            if (this.offlineDownload === null) {
                this.$router.push({ path: '/offline/' }).catch(() => undefined);
                return;
            }
            this.$router.push({ path: `/offline/watch/${this.offlineDownload.id}` }).catch(() => undefined);
        },
    },
    watch: {
        'playerStore.recorded_program.id': {
            immediate: true,
            handler() {
                this.syncDefaultOfflineOptions();
                void this.prepareOfflineContext(false);
            },
        },
    },
    created() {
        // PlayerController 側からCommentReceived イベントで過去ログコメントを受け取り、コメント数を算出する
        this.playerStore.event_emitter.on('CommentReceived', (event) => {
            if (event.is_initial_comments === true) {  // 録画では初期コメントしか発生しない
                this.comment_count = event.comments.length;
            }
        });
        void this.prepareOfflineContext(false);
    },
    beforeUnmount() {
        // CommentReceived イベントの全てのイベントハンドラーを削除
        this.playerStore.event_emitter.off('CommentReceived');
    },
});

</script>
<style lang="scss" scoped>

.program-container {
    padding-left: 16px;
    padding-right: 16px;
    overflow-y: auto;
    @include tablet-vertical {
        padding-left: 24px;
        padding-right: 24px;
    }

    .program-info {
        .program-info__title {
            font-size: 22px;
            font-weight: bold;
            line-height: 145%;
            font-feature-settings: "palt" 1;  // 文字詰め
            letter-spacing: 0.05em;  // 字間を少し空ける
            @include tablet-vertical {
                margin-top: 16px;
            }
            @include smartphone-horizontal {
                margin-top: 10px;
                font-size: 18px;
            }
            @include smartphone-vertical {
                margin-top: 16px;
                font-size: 19px;
            }
        }

        .program-info__broadcaster {
            display: flex;
            align-items: center;
            min-width: 0;
            margin-top: 16px;
            color: rgb(var(--v-theme-text-darken-1));
            &-icon {
                display: inline-block;
                flex-shrink: 0;
                width: 44px;
                height: 36px;
                border-radius: 3px;
                background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
                object-fit: cover;
                user-select: none;
            }

            .program-info__broadcaster-container {
                display: flex;
                flex-direction: column;
                margin-left: 12px;
                .program-info__broadcaster-number {
                    flex-shrink: 0;
                    font-size: 14px;
                    @include smartphone-horizontal {
                        font-size: 13.5px;
                    }
                }
                .program-info__broadcaster-name {
                    margin-left: 5px;
                    font-size: 14px;
                    overflow: hidden;
                    white-space: nowrap;
                    text-overflow: ellipsis;
                    @include smartphone-horizontal {
                        font-size: 13.5px;
                    }
                }
                .program-info__broadcaster-time {
                    margin-top: 2px;
                    color: rgb(var(--v-theme-text-darken-1));
                    font-size: 13.5px;
                    @include smartphone-horizontal {
                        font-size: 12px;
                    }
                    @include smartphone-vertical {
                        font-size: 12.5px;
                    }
                }
            }
        }

        .program-info__description {
            margin-top: 12px;
            color: rgb(var(--v-theme-text-darken-1));
            font-size: 12px;
            line-height: 168%;
            overflow-wrap: break-word;
            font-feature-settings: "palt" 1;  // 文字詰め
            letter-spacing: 0.08em;  // 字間を少し空ける
            @include smartphone-horizontal {
                margin-top: 8px;
                font-size: 11px;
            }
        }

        .program-info__genre-container {
            display: flex;
            flex-wrap: wrap;
            margin-top: 10px;

            .program-info__genre {
                display: inline-block;
                font-size: 10.5px;
                padding: 3px;
                margin-top: 4px;
                margin-right: 4px;
                border-radius: 4px;
                background: rgb(var(--v-theme-background-lighten-2));
                @include smartphone-horizontal {
                    font-size: 9px;
                }
            }
        }

        .program-info__status {
            margin-top: 8px;
            color: rgb(var(--v-theme-text-darken-1));
            font-size: 12.5px;
            line-height: 170%;
            @include smartphone-horizontal {
                font-size: 11.5px;
            }
        }

        .program-info__button {
            display: inline-flex;
            align-items: center;
            padding: 5px 8px;
            margin-top: 16px;
            color: rgb(var(--v-theme-text-darken-1));
            font-size: 12.7px;
            line-height: 170%;
            background: rgb(var(--v-theme-background-lighten-1));
            border-radius: 4px;
            user-select: none;
            transition: color 0.15s ease;
            cursor: pointer;
            @include smartphone-horizontal {
                font-size: 11.5px;
            }

            &:hover {
                color: rgb(var(--v-theme-text));
            }
        }

        .program-info__offline {
            margin-top: 20px;
            padding: 14px 16px;
            border-radius: 10px;
            background: rgb(var(--v-theme-background-lighten-1));
            @include smartphone-horizontal {
                padding: 12px 14px;
            }

            &-header {
                display: flex;
                gap: 12px;
                align-items: center;
            }

            &-icon {
                color: rgb(var(--v-theme-primary));
            }

            &-title {
                font-size: 14px;
                font-weight: 700;
            }

            &-subtitle {
                margin-top: 2px;
                font-size: 12px;
                color: rgb(var(--v-theme-text-darken-2));
                @include smartphone-horizontal {
                    font-size: 11px;
                }
            }

            &-alert {
                margin-top: 12px;
            }

            &-status {
                margin-top: 14px;
            }

            &-status-header {
                display: flex;
                flex-direction: column;
                gap: 6px;
                @include smartphone-horizontal {
                    gap: 8px;
                }
            }

            &-badge {
                display: inline-flex;
                align-items: center;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 600;

                &--downloading {
                    background: rgba(var(--v-theme-primary), 0.15);
                    color: rgb(var(--v-theme-primary));
                }
                &--completed {
                    background: rgba(76, 175, 80, 0.18);
                    color: #4caf50;
                }
                &--paused {
                    background: rgba(255, 193, 7, 0.18);
                    color: #ffc107;
                }
                &--error {
                    background: rgba(244, 67, 54, 0.18);
                    color: #f44336;
                }
            }

            &-summary {
                font-size: 12px;
                color: rgb(var(--v-theme-text-darken-1));
                line-height: 1.5;
            }

            &-progress {
                margin-top: 12px;
            }

            &-progress-text {
                margin-top: 6px;
                display: flex;
                justify-content: space-between;
                font-size: 11.5px;
                color: rgb(var(--v-theme-text-darken-2));
                @include smartphone-horizontal {
                    flex-direction: column;
                    gap: 4px;
                }
            }

            &-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 14px;
            }

            &-action {
                min-width: 0;
            }

            &-empty {
                margin-top: 14px;
                font-size: 12px;
                color: rgb(var(--v-theme-text-darken-1));
                line-height: 1.6;

                p {
                    margin-bottom: 12px;
                }
            }
        }
    }

    .program-detail-container {
        margin-top: 24px;
        margin-bottom: 24px;
        @include tablet-vertical {
            margin-top: 20px;
            margin-bottom: 20px;
        }
        @include smartphone-horizontal {
            margin-top: 20px;
            margin-bottom: 16px;
        }

        .program-detail {
            margin-top: 16px;

            .program-detail__heading {
                font-size: 18px;
                @include smartphone-horizontal {
                    font-size: 16px;
                }
            }
            .program-detail__text {
                margin-top: 8px;
                color: rgb(var(--v-theme-text-darken-1));
                font-size: 12px;
                line-height: 168%;
                overflow-wrap: break-word;
                white-space: pre-wrap;  // \n で改行する
                font-feature-settings: "palt" 1;  // 文字詰め
                letter-spacing: 0.08em;  // 字間を少し空ける
                @include smartphone-horizontal {
                    font-size: 11px;
                }

                // リンクの色
                :deep(a:link), :deep(a:visited) {
                    color: rgb(var(--v-theme-primary-lighten-1));
                    text-decoration: underline;
                    text-underline-offset: 3px;  // 下線と字の間隔を空ける
                }
            }
        }
    }
}

.offline-dialog__description {
    font-size: 13px;
    color: rgb(var(--v-theme-text-darken-1));
    line-height: 1.7;
}

.offline-dialog__hint {
    margin-top: 10px;
    font-size: 12px;
    color: rgb(var(--v-theme-text-darken-2));

    &--disabled {
        color: rgba(var(--v-theme-text-darken-2), 0.6);
    }

    &--secondary {
        color: rgba(var(--v-theme-text-darken-2), 0.85);
    }
}

</style>