<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="timetable-container-wrapper">
                <SPHeaderBar />
                <!-- ヘッダー: チャンネルタブ & 日付操作 -->
                <div class="timetable-header">
                    <div class="channels-tab">
                        <div class="channels-tab__buttons" :style="{
                            '--tab-length': channel_types.length,
                            '--active-tab-index': active_tab_index,
                        }">
                            <v-btn variant="flat" class="channels-tab__button"
                                v-for="(type, index) in channel_types" :key="type.id"
                                @click="onClickChannelType(type.id, index)">
                                {{type.name}}
                            </v-btn>
                            <div class="channels-tab__highlight"></div>
                        </div>
                    </div>
                    <div class="timetable-header__date-control">
                        <v-btn @click="timetableStore.setPreviousDate" class="mr-2">前日</v-btn>
                        <h2 class="mx-4 date-display">{{ formattedDate }}</h2>
                        <v-btn @click="timetableStore.setNextDate" class="ml-2">翌日</v-btn>
                        <v-btn @click="timetableStore.setCurrentDate" class="ml-4">今日</v-btn>
                    </div>
                </div>

                <!-- 番組表本体 -->
                <div class="timetable-body">
                    <div v-if="timetableStore.is_loading" class="loading-container">
                        <v-progress-circular indeterminate size="64"></v-progress-circular>
                    </div>
                    <div v-else-if="timetableStore.timetable_channels && timetableStore.timetable_channels.length > 0" class="timetable-grid-container">
                        <div class="corner-cell"></div>
                        <div class="channels-header" :style="gridStyle">
                            <div v-for="channel in timetableStore.timetable_channels" :key="channel.channel.id" class="channel-header-cell">
                                {{ channel.channel.name }}
                            </div>
                        </div>
                        <div class="timeline-container">
                            <div v-for="hour in 25" :key="hour" class="hour-label">
                                <span class="hour-text">{{ (hour + 3) % 24 }}</span>
                            </div>
                        </div>
                        <div class="programs-grid" :style="gridStyle">
                            <div v-if="isToday" class="current-time-line" :style="currentTimeLineStyle"></div>
                            <div v-for="ch_index in timetableStore.timetable_channels.length" :key="ch_index" class="channel-border" :style="{gridColumn: ch_index}"></div>
                            <div v-for="hour_index in 24" :key="hour_index" class="hour-border" :style="{gridRow: (hour_index * 60) + 1}"></div>
                            <template v-for="(channel, ch_index) in timetableStore.timetable_channels">
                                <template v-for="program in channel.programs" :key="program.id">
                                    <v-tooltip location="top" :disabled="isTooltipDisabled(program)">
                                        <template v-slot:activator="{ props }">
                                            <div v-bind="props" class="program-cell elevation-2"
                                                :style="getProgramStyle(program, ch_index)"
                                                @click="showProgramDetails(program)">
                                                <div class="program-header">
                                                    <div class="program-title">{{ program.title }}</div>
                                                    <div class="program-badges">
                                                        <span v-if="!program.is_free" class="program-badge program-badge--paid">有料</span>
                                                        <span v-if="program.genres.length > 0" class="program-badge program-badge--genre">{{ program.genres[0].major }}</span>
                                                    </div>
                                                </div>
                                                <div class="program-description" v-if="program.description && program.duration >= 900">{{ truncateText(program.description, 50) }}</div>
                                                <div class="program-time">{{ formatTime(program.start_time) }} - {{ formatTime(program.end_time) }} ({{ Math.floor(program.duration / 60) }}分)</div>
                                            </div>
                                        </template>
                                        <span class="tooltip-text">{{ program.title }}</span>
                                    </v-tooltip>
                                </template>
                            </template>
                        </div>
                    </div>
                    <div v-else class="loading-container">
                        <p>番組情報を取得できませんでした。</p>
                        <p>指定された期間・チャンネルに放送される番組がありません。</p>
                    </div>
                </div>

            </div>
        </main>

        <!-- EPG操作ボタン（浮動表示） -->
        <div class="epg-controls-floating">
            <v-btn
                @click="updateEPG"
                :loading="timetableStore.is_loading"
                :disabled="timetableStore.is_loading"
                color="primary"
                variant="tonal"
                size="large"
                class="epg-btn"
            >
                <v-icon icon="mdi-download" class="mr-1" size="large" />
                <span>EPG取得</span>
            </v-btn>
            <v-btn
                @click="reloadEPG"
                :loading="timetableStore.is_loading"
                :disabled="timetableStore.is_loading"
                color="secondary"
                variant="tonal"
                size="large"
                class="epg-btn"
            >
                <v-icon icon="mdi-refresh" class="mr-1" size="large" />
                <span>EPG再読み込み</span>
            </v-btn>
        </div>

        <!-- 番組詳細サイドパネル -->
        <v-navigation-drawer v-model="is_panel_shown" location="right" temporary width="600">
            <v-card v-if="selected_program" class="detail-panel">
                <v-card-title class="text-h5 pb-2">{{ selected_program.title }}</v-card-title>
                <v-card-subtitle class="pb-3">{{ formatFullDateTime(selected_program.start_time) }} - {{ formatFullDateTime(selected_program.end_time) }} ({{ Math.floor(selected_program.duration / 60) }}分)</v-card-subtitle>

                <!-- 番組情報バッジ -->
                <v-card-text class="pt-0 pb-2">
                    <div class="program-info-badges">
                        <v-chip v-if="!selected_program.is_free" color="warning" size="small" class="mr-2 mb-2">
                            <v-icon start>mdi-currency-yen</v-icon>
                            有料放送
                        </v-chip>
                        <v-chip v-if="selected_program.video_resolution === '1080i' || selected_program.video_resolution === '1080p'" color="success" size="small" class="mr-2 mb-2">
                            <v-icon start>mdi-high-definition</v-icon>
                            HD
                        </v-chip>
                        <v-chip v-for="genre in selected_program.genres.slice(0, 2)" :key="genre.major" color="primary" variant="outlined" size="small" class="mr-2 mb-2">
                            {{ genre.major }}
                        </v-chip>
                    </div>
                </v-card-text>

                <!-- 番組説明 -->
                <v-card-text class="py-2">
                    <v-divider class="mb-3"></v-divider>
                    <h4 class="text-subtitle-1 mb-2">番組内容</h4>
                    <p class="text-body-2 mb-3">{{ selected_program.description }}</p>

                    <!-- 詳細情報 -->
                    <div v-if="selected_program.detail && Object.keys(selected_program.detail).length > 0" class="program-detail-section">
                        <h4 class="text-subtitle-1 mb-2">詳細情報</h4>
                        <div class="program-detail-grid">
                            <template v-for="(value, key) in selected_program.detail" :key="key">
                                <div class="detail-item">
                                    <span class="detail-key">{{ key }}:</span>
                                    <span class="detail-value">{{ value }}</span>
                                </div>
                            </template>
                        </div>
                    </div>
                </v-card-text>

                <v-card-actions class="detail-panel__actions">
                    <v-spacer></v-spacer>
                    <v-btn :loading="is_reserving" @click="reserveProgram(selected_program.id)" color="primary" variant="elevated">
                        <v-icon start>mdi-record-rec</v-icon>
                        録画予約
                    </v-btn>
                    <v-btn @click="is_panel_shown = false" variant="outlined">閉じる</v-btn>
                </v-card-actions>
            </v-card>
        </v-navigation-drawer>
    </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch ,nextTick} from 'vue';
import { useTimetableStore } from '@/stores/TimetableStore';
import { useSnackbarsStore } from '@/stores/SnackbarsStore';
import { IProgram } from '@/services/Programs';
import Reservations, { IRecordSettings } from '@/services/Reservations';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import { ChannelType } from '@/services/Channels';

const timetableStore = useTimetableStore();
const snackbarsStore = useSnackbarsStore();

const channel_types: {id: 'ALL' | ChannelType, name: string}[] = [
    {id: 'ALL', name: 'すべて'},
    {id: 'GR', name: '地デジ'},
    {id: 'BS', name: 'BS'},
    {id: 'CS', name: 'CS'},
];

const active_tab_index = ref(0);

const onClickChannelType = (type: 'ALL' | ChannelType, index: number) => {
    timetableStore.setChannelType(type);
    active_tab_index.value = index;
};

// ジャンルごとに色分け
const genre_colors: { [key: string]: { background: string; text: string } } = {
    'ニュース・報道': { background: '#5a88a7', text: '#ffffff' },
    'スポーツ': { background: '#e07f5a', text: '#ffffff' },
    '情報・ワイドショー': { background: '#e7a355', text: '#ffffff' },
    'ドラマ': { background: '#b464a8', text: '#ffffff' },
    '音楽': { background: '#64b46e', text: '#ffffff' },
    'バラエティ': { background: '#e05a8e', text: '#ffffff' },
    '映画': { background: '#a7647e', text: '#ffffff' },
    'アニメ・特撮': { background: '#e76b55', text: '#ffffff' },
    'ドキュメンタリー・教養': { background: '#5a88a7', text: '#ffffff' },
    '劇場・公演': { background: '#a7647e', text: '#ffffff' },
    '趣味・教育': { background: '#64b46e', text: '#ffffff' },
    '福祉': { background: '#5aa788', text: '#ffffff' },
    'その他': { background: '#7f7f7f', text: '#ffffff' },
};
const default_genre_color = { background: 'rgb(var(--v-theme-background-lighten-3))', text: 'rgb(var(--v-theme-text))' };

// 現在時刻 (1分ごとに更新)
const now = ref(new Date());
const now_timer = setInterval(() => {
    now.value = new Date();
}, 60 * 1000);
onUnmounted(() => {
    clearInterval(now_timer);
});

const formattedDate = computed(() => {
    const date = timetableStore.current_date;
    const year = date.getFullYear();
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const dayOfWeek = ['日', '月', '火', '水', '木', '金', '土'][date.getDay()];
    return `${year}年${month}月${day}日 (${dayOfWeek})`;
});

const formatTime = (time: string) => {
    const date = new Date(time);
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
};

const formatFullDateTime = (time: string) => {
    const date = new Date(time);
    return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${formatTime(time)}`;
};


// テキストを指定した文字数で切り詰める
const truncateText = (text: string, maxLength: number): string => {
    if (text.length <= maxLength) {
        return text;
    }
    return text.substring(0, maxLength) + '...';
};

const gridStyle = computed(() => ({
    'grid-template-columns': `repeat(${timetableStore.timetable_channels?.length || 0}, minmax(200px, 1fr))`,
}));

const getProgramStyle = (program: IProgram, ch_index: number) => {
    const start = new Date(program.start_time);
    const start_minutes = (start.getHours() - 4 + 24) % 24 * 60 + start.getMinutes();
    const duration_minutes = program.duration / 60;
    const genre = program.genres[0]?.major || 'その他';
    const color = genre_colors[genre] || default_genre_color;
    const style: { [key: string]: any } = {
        'grid-column': ch_index + 1,
        'grid-row-start': start_minutes + 1,
        'grid-row-end': start_minutes + duration_minutes + 1,
        'background-color': color.background,
        'color': color.text,
        'border-color': color.background,
    };

    // 過去の番組か判定
    if (new Date(program.end_time) < now.value) {
        style.opacity = 0.6;
        style['pointer-events'] = 'none';
    }

    return style;
};

const isToday = computed(() => {
    const today = new Date();
    const current = timetableStore.current_date;
    return today.getFullYear() === current.getFullYear() &&
           today.getMonth() === current.getMonth() &&
           today.getDate() === current.getDate();
});

const currentTimeLineStyle = computed(() => {
    const minutes_from_4am = ((now.value.getHours() - 4 + 24) % 24) * 60 + now.value.getMinutes();
    return {
        top: `${minutes_from_4am * 2}px`,
    };
});

const isTooltipDisabled = (program: IProgram) => {
    return program.duration / 60 > 15; // 15分より長い番組ではツールチップを無効化
};

const is_panel_shown = ref(false);
const selected_program = ref<IProgram | null>(null);
const showProgramDetails = (program: IProgram) => {
    selected_program.value = program;
    is_panel_shown.value = true;
};

const is_reserving = ref(false);
const reserveProgram = async (program_id: string) => {
    is_reserving.value = true;
    const default_settings: IRecordSettings = {
        is_enabled: true,
        priority: 3,
        recording_folders: [],
        recording_start_margin: null,
        recording_end_margin: null,
        recording_mode: 'SpecifiedService',
        caption_recording_mode: 'Default',
        data_broadcasting_recording_mode: 'Default',
        post_recording_mode: 'Default',
        post_recording_bat_file_path: null,
        is_event_relay_follow_enabled: true,
        is_exact_recording_enabled: false,
        is_oneseg_separate_output_enabled: false,
        is_sequential_recording_in_single_file_enabled: false,
        forced_tuner_id: null,
    };
    const success = await Reservations.addReservation(program_id, default_settings);
    if (success) {
        snackbarsStore.show('success', '録画予約を追加しました。');
        is_panel_shown.value = false;
    } else {
        snackbarsStore.show('error', '録画予約の追加に失敗しました。');
    }
    is_reserving.value = false;
};

// EPG操作メソッド
const updateEPG = async () => {
    try {
        await timetableStore.updateEPG();
        snackbarsStore.show('success', 'EPG 取得を開始しました。');
    } catch (error) {
        snackbarsStore.show('error', 'EPG 取得に失敗しました。EDCBが起動していることを確認してください。');
        console.error('EPG 取得エラー:', error);
    }
};

const reloadEPG = async () => {
    try {
        await timetableStore.reloadEPG();
        snackbarsStore.show('success', 'EPG を再読み込みしました。');
    } catch (error) {
        snackbarsStore.show('error', 'EPG の再読み込みに失敗しました。EDCBが起動していることを確認してください。');
        console.error('EPG再読み込みエラー:', error);
    }
};

onMounted(() => {
    timetableStore.fetchTimetable();
});

const is_initial_load = ref(true);
watch(() => timetableStore.timetable_channels, (new_channels) => {
    // 初回読み込み時かつ、チャンネル情報が読み込まれた後
    if (is_initial_load.value && new_channels && new_channels.length > 0) {
        nextTick(() => {

            const container = document.querySelector('.timetable-grid-container');
            if (!container) return;

            // 現在時刻 (now.value) を使ってスクロール位置を計算
            const current_hours = now.value.getHours();
            const current_minutes = now.value.getMinutes();

            //経過分数を計算(ただし、現在時刻の一時間前にして余裕をもたせる)
            const minutes_from_4am = ((current_hours - 4 + 24 - 1) % 24) * 60 + current_minutes;

            // 1分あたり2pxでスクロール量を計算
            const scroll_top = (minutes_from_4am * 2) - 50;

            // スクロールさせる
            container.scrollTo({
                top: scroll_top > 0 ? scroll_top : 0, // マイナスにはならないように
                behavior: 'smooth',
            });

            is_initial_load.value = false;
        });
    }
});

</script>

<style lang="scss" scoped>
.timetable-container-wrapper {
    width: 100%;
    min-width: 0;
    margin-left: 21px;
    margin-right: 21px;
    @include smartphone-vertical {
        margin-left: 0px;
        margin-right: 0px;
    }
}

.timetable-header {
    position: sticky;
    top: 65px;
    padding-top: 5px;
    background: rgb(var(--v-theme-background));
    z-index: 10;

    &__date-control {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 12px 0;
        border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
        .date-display {
            @include smartphone-horizontal {
                font-size: 20px;
            }
            @include smartphone-vertical {
                font-size: 18px;
            }
        }
    }
}

.channels-tab {
    display: flex;
    .channels-tab__buttons {
        display: flex;
        position: relative;
        align-items: center;
        margin-left: auto;
        margin-right: auto;

        .channels-tab__button {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 98px;
            padding: 16px 0;
            border-radius: 2.5px;
            color: rgb(var(--v-theme-text)) !important;
            background-color: transparent !important;
            font-size: 16px;
            letter-spacing: 0.0892857143em !important;
            text-transform: none;
            cursor: pointer;
            @include smartphone-vertical {
                width: 90px;
                font-size: 15px;
            }
        }

        .channels-tab__highlight {
            position: absolute;
            left: 0;
            bottom: 0;
            width: 98px;
            height: 3px;
            background: rgb(var(--v-theme-primary));
            transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.5, 1);
            transform: translateX(calc(98px * var(--active-tab-index, 0)));
            will-change: transform;
            @include smartphone-vertical {
                width: 90px;
                transform: translateX(calc(90px * var(--active-tab-index, 0)));
            }
        }
    }
}

.timetable-body {
    height: calc(100vh - 65px - 140px);
}

.loading-container {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100%;
}

.timetable-grid-container {
    height: 100%;
    display: grid;
    grid-template-rows: auto 1fr;
    grid-template-columns: auto 1fr;
    overflow: scroll;
}

.corner-cell {
    position: sticky;
    top: 0;
    left: 0;
    z-index: 7;
    background: rgb(var(--v-theme-background));
}

.channels-header {
    grid-column: 2;
    display: grid;
    position: sticky;
    top: 0;
    z-index: 5;
    background: rgb(var(--v-theme-background));

    .channel-header-cell {
        padding: 12px 8px;
        text-align: center;
        font-weight: bold;
        border-right: 1px solid rgb(var(--v-theme-background-lighten-2));
    }
}

.timeline-container {
    grid-row: 2;
    width: 60px;
    position: sticky;
    left: 0;
    z-index: 6;
    background: rgb(var(--v-theme-background));

    .hour-label {
        position: relative;
        height: 120px;
        text-align: right;
        padding-right: 8px;
        font-size: 14px;
        color: rgb(var(--v-theme-text-darken-1));

        .hour-text {
            position: relative;
            top: -0.7em;
        }
    }
}

.programs-grid {
    grid-row: 2;
    grid-column: 2;
    display: grid;
    grid-template-rows: repeat(24 * 60, 2px);
    position: relative;

    .channel-border {
        grid-row: 1 / -1;
        border-right: 1px solid rgb(var(--v-theme-background-lighten-2));
    }
    .hour-border {
        grid-column: 1 / -1;
        border-top: 1px dotted rgb(var(--v-theme-background-lighten-2));
    }

    .current-time-line {
        position: absolute;
        width: 100%;
        height: 3px;
        background: #E53935;
        z-index: 3;
    }
}

.program-cell {
    margin: 1px;
    padding: 8px;
    border-radius: 8px;
    cursor: pointer;
    overflow: hidden;
    transition: filter 0.2s, transform 0.2s;
    text-orientation: mixed;
    display: flex;
    flex-direction: column;
    gap: 4px;

    &:hover {
        filter: brightness(1.1);
        transform: scale(1.02);
        z-index: 2;
    }

    .program-header {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .program-title {
        font-weight: bold;
        font-size: 0.9em;
        line-height: 1.2;
        word-break: break-word;
    }

    .program-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 2px;
    }

    .program-badge {
        font-size: 0.7em;
        padding: 1px 4px;
        border-radius: 3px;
        font-weight: 500;
        white-space: nowrap;

        &--paid {
            background-color: rgba(255, 193, 7, 0.9);
            color: #000;
        }

        &--hd {
            background-color: rgba(76, 175, 80, 0.9);
            color: #fff;
        }

        &--genre {
            background-color: rgba(255, 255, 255, 0.2);
            color: inherit;
        }
    }

    .program-description {
        font-size: 0.75em;
        line-height: 1.3;
        opacity: 0.9;
        word-break: break-word;
        flex-grow: 1;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }

    .program-time {
        font-size: 0.8em;
        opacity: 0.8;
        margin-top: auto; // 時間を下に配置
        writing-mode: horizontal-tb;
        white-space: nowrap;
    }
}

.tooltip-text {
    font-size: 14px;
    color: rgb(var(--v-theme-text));
}

.detail-panel {
    &__actions {
        position: sticky;
        bottom: 0;
        background: rgb(var(--v-theme-background));
        border-top: 1px solid rgb(var(--v-theme-background-lighten-2));
        padding: 16px;
    }
}

.program-info-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.program-detail-section {
    margin-bottom: 16px;
}

.program-detail-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .detail-item {
        display: flex;
        padding: 8px 0;
        border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);

        .detail-key {
            font-weight: 600;
            min-width: 80px;
            margin-right: 12px;
            color: rgb(var(--v-theme-primary));
        }

        .detail-value {
            flex: 1;
            word-break: break-word;
        }
    }
}

.tech-info-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;

    @include smartphone-vertical {
        grid-template-columns: 1fr;
    }

    .tech-info-item {
        display: flex;
        flex-direction: column;
        padding: 12px;
        background-color: rgb(var(--v-theme-background-lighten-1));
        border-radius: 8px;
        border: 1px solid rgb(var(--v-theme-background-lighten-2));

        .tech-info-label {
            font-size: 0.85em;
            font-weight: 600;
            color: rgb(var(--v-theme-text-darken-1));
            margin-bottom: 4px;
        }

        .tech-info-value {
            font-size: 0.9em;
            word-break: break-word;
        }
    }
}

.program-detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;

    .detail-section {
        &:not(:last-child) {
            border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
            padding-bottom: 12px;
        }

        .detail-section-title {
            font-size: 0.9em;
            font-weight: 600;
            color: rgb(var(--v-theme-primary));
            margin-bottom: 8px;
        }

        .detail-section-content {
            font-size: 0.875em;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0;
        }
    }
}

.program-detail {
    white-space: pre-wrap;
    word-break: break-all;
    background-color: rgb(var(--v-theme-background-lighten-1));
    padding: 16px;
    border-radius: 4px;
    margin-top: 16px;
}

.epg-controls-floating {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 100;
    display: flex;
    flex-direction: row;

    .epg-btn:not(:last-child) {
        margin-right: 12px;
    }

    @include smartphone-vertical {
        bottom: calc(56px + env(safe-area-inset-bottom, 0px) + 16px);
        right: 16px;
        flex-direction: column;
        gap: 8px;
    }

    .epg-btn {
        min-width: 140px;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
        background-color: rgb(var(--v-theme-surface)) !important;
        border: 1px solid rgb(var(--v-theme-outline-variant)) !important;

        &:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
            background-color: rgb(var(--v-theme-surface-variant)) !important;
        }

        @include smartphone-vertical {
            width: 140px;
            font-size: 0.95em;
        }
    }
}

</style>
