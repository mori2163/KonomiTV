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
                    <div class="timetable-header__search-bar">
                        <v-text-field
                            v-model="search_query"
                            @keyup.enter="searchPrograms"
                            placeholder="番組を検索..."
                            prepend-inner-icon="mdi-magnify"
                            clearable
                            hide-details
                            density="compact"
                            variant="outlined"
                            class="search-input"
                        >
                            <template v-slot:append-inner>
                                <v-btn
                                    @click="searchPrograms"
                                    :loading="is_searching"
                                    icon
                                    variant="text"
                                    size="small"
                                >
                                    <v-icon>mdi-arrow-right</v-icon>
                                </v-btn>
                            </template>
                        </v-text-field>
                    </div>
                    <div class="timetable-header__date-control">
                        <v-btn @click="timetableStore.setPreviousDate" class="mr-2" icon="mdi-chevron-left" variant="text" size="large">
                            <v-icon>mdi-chevron-left</v-icon>
                            <v-tooltip activator="parent" location="bottom">前日</v-tooltip>
                        </v-btn>
                        <v-menu v-model="is_date_menu_open" :close-on-content-click="false">
                            <template v-slot:activator="{ props }">
                                <h2 v-bind="props" class="mx-4 date-display date-display--clickable">{{ formattedDate }}</h2>
                            </template>
                            <v-date-picker
                                v-model="picker_date"
                                @update:model-value="onDatePickerChange"
                                :max="maxSelectableDate"
                                header="日付を選択"
                                show-adjacent-months
                            ></v-date-picker>
                        </v-menu>
                        <v-btn @click="timetableStore.setNextDate" class="ml-2" icon="mdi-chevron-right" variant="text" size="large">
                            <v-icon>mdi-chevron-right</v-icon>
                            <v-tooltip activator="parent" location="bottom">翌日</v-tooltip>
                        </v-btn>
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
                                                :class="{'program-cell--reserved': isReserved(program.id)}"
                                                :style="getProgramStyle(program, ch_index)"
                                                @click="showProgramDetails(program)">
                                                <div class="program-header">
                                                    <div class="program-title">
                                                        {{ program.title }}
                                                    </div>
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
        <div v-if="timetableStore.can_update_epg || timetableStore.can_reload_epg" class="epg-controls-floating">
            <v-btn
                v-if="timetableStore.can_update_epg"
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
                v-if="timetableStore.can_reload_epg"
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

        <!-- 番組詳細ドロワー -->
        <ProgramDetailDrawer
            v-model="is_panel_shown"
            :program="selected_program"
            :is-reserved="selected_program ? isReserved(selected_program.id) : false"
            :is-reserving="is_reserving"
            @reserve="reserveProgram"
            @remove="deleteReservation"
        />

        <!-- 番組検索結果ダイアログ -->
        <v-dialog v-model="is_search_dialog_open" max-width="800px" scrollable>
            <v-card>
                <v-card-title class="d-flex align-center">
                    <v-icon class="mr-2">mdi-magnify</v-icon>
                    検索結果: "{{ search_query }}"
                    <v-spacer></v-spacer>
                    <v-btn icon @click="is_search_dialog_open = false">
                        <v-icon>mdi-close</v-icon>
                    </v-btn>
                </v-card-title>
                <v-divider></v-divider>
                <v-card-text style="max-height: 600px;">
                    <div v-if="is_searching" class="text-center py-8">
                        <v-progress-circular indeterminate size="64"></v-progress-circular>
                        <p class="mt-4">検索中...</p>
                    </div>
                    <div v-else-if="search_results.length === 0" class="text-center py-8">
                        <v-icon size="64" color="grey">mdi-information-outline</v-icon>
                        <p class="mt-4">検索結果が見つかりませんでした。</p>
                    </div>
                    <v-list v-else>
                        <v-list-item
                            v-for="program in search_results"
                            :key="program.id"
                            @click="showSearchResult(program)"
                            class="search-result-item"
                        >
                            <template v-slot:prepend>
                                <v-avatar color="primary" size="40">
                                    <span class="text-caption">{{ formatTime(program.start_time).substring(0, 5) }}</span>
                                </v-avatar>
                            </template>
                            <v-list-item-title>{{ program.title }}</v-list-item-title>
                            <v-list-item-subtitle>
                                {{ program.channel.name }} - {{ formatTime(program.start_time) }} ~ {{ formatTime(program.end_time) }}
                            </v-list-item-subtitle>
                            <v-list-item-subtitle v-if="program.description" class="mt-1">
                                {{ truncateText(program.description, 80) }}
                            </v-list-item-subtitle>
                        </v-list-item>
                    </v-list>
                </v-card-text>
            </v-card>
        </v-dialog>
    </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue';

import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import ProgramDetailDrawer from '@/components/Timetable/ProgramDetailDrawer.vue';
import { ChannelType } from '@/services/Channels';
import { IProgram } from '@/services/Programs';
import Reservations, { IRecordSettings } from '@/services/Reservations';
import Timetable, { IProgramSearchResult } from '@/services/Timetable';
import { useSnackbarsStore } from '@/stores/SnackbarsStore';
import { useTimetableStore } from '@/stores/TimetableStore';

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

// 日付ピッカー関連
const is_date_menu_open = ref(false);
const picker_date = ref(new Date());

// ピッカーで選択可能な最大日付（今日から7日後まで）
const maxSelectableDate = computed(() => {
    const max = new Date();
    max.setDate(max.getDate() + 7);
    return max;
});

// 日付ピッカーの値が変更されたとき
const onDatePickerChange = (date: Date | null) => {
    if (date) {
        timetableStore.setDate(date);
        is_date_menu_open.value = false;
    }
};

// current_dateの変化をピッカーに反映
watch(() => timetableStore.current_date, (new_date) => {
    picker_date.value = new Date(new_date);
});

// 番組検索機能
const search_query = ref('');
const is_searching = ref(false);
const is_search_dialog_open = ref(false);
const search_results = ref<IProgramSearchResult[]>([]);

const searchPrograms = async () => {
    if (!search_query.value || search_query.value.trim() === '') {
        snackbarsStore.show('error', '検索キーワードを入力してください。');
        return;
    }

    is_searching.value = true;
    is_search_dialog_open.value = true;
    
    try {
        // 現在選択中のチャンネルタイプと日付範囲で検索
        const start_time = new Date(timetableStore.current_date);
        start_time.setHours(4, 0, 0, 0);
        const end_time = new Date(start_time);
        end_time.setDate(end_time.getDate() + 7); // 7日分検索

        const channel_type = timetableStore.selected_channel_type === 'ALL' ? undefined : 
            (timetableStore.selected_channel_type as 'GR' | 'BS' | 'CS');
        const results = await Timetable.searchPrograms(search_query.value, channel_type, start_time, end_time, 50);
        
        if (results) {
            search_results.value = results;
        } else {
            search_results.value = [];
        }
    } catch (error) {
        console.error('番組検索エラー:', error);
        snackbarsStore.show('error', '番組の検索に失敗しました。');
        search_results.value = [];
    } finally {
        is_searching.value = false;
    }
};

const showSearchResult = (program: IProgramSearchResult) => {
    is_search_dialog_open.value = false;
    selected_program.value = program;
    is_panel_shown.value = true;
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
    };

    // 予約済みでない番組のみborder-colorを設定(予約済みの赤枠を優先)
    if (!isReserved(program.id)) {
        style['border-color'] = color.background;
    }

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

// 番組が録画予約されているか判定
const reservedProgramIdsSet = computed(() => {
    const set = new Set(timetableStore.reserved_program_ids);
    return set;
});

const isReserved = (program_id: string) => {
    return reservedProgramIdsSet.value.has(program_id);
};

const is_panel_shown = ref(false);
const selected_program = ref<IProgram | null>(null);
const showProgramDetails = (program: IProgram) => {
    selected_program.value = program;
    is_panel_shown.value = true;
};

const is_reserving = ref(false);

// 録画予約を追加する
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
        // 録画予約情報を再取得して表示を更新
        await timetableStore.fetchReservations();
    } else {
        snackbarsStore.show('error', '録画予約の追加に失敗しました。');
    }
    is_reserving.value = false;
};

// 録画予約を削除する
const deleteReservation = async (program_id: string) => {
    is_reserving.value = true;
    const reservation_id = timetableStore.program_id_to_reservation_id[program_id];
    if (!reservation_id) {
        snackbarsStore.show('error', '録画予約情報が見つかりませんでした。');
        is_reserving.value = false;
        return;
    }

    const success = await Reservations.deleteReservation(reservation_id);
    if (success) {
        snackbarsStore.show('success', '録画予約を削除しました。');
        is_panel_shown.value = false;
        // 録画予約情報を再取得して表示を更新
        await timetableStore.fetchReservations();
    } else {
        snackbarsStore.show('error', '録画予約の削除に失敗しました。');
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
    timetableStore.fetchEPGCapabilities();
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

    &__search-bar {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 12px 16px;
        border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));

        .search-input {
            max-width: 600px;
            width: 100%;
        }

        @include smartphone-vertical {
            padding: 8px 12px;
            
            .search-input {
                max-width: 100%;
            }
        }
    }

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
            
            &--clickable {
                cursor: pointer;
                padding: 8px 16px;
                border-radius: 4px;
                transition: background-color 0.2s;
                
                &:hover {
                    background-color: rgba(var(--v-theme-primary), 0.1);
                }
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

    // 録画予約されている番組
    &--reserved {
        border: 3px solid #E53935 !important;
        box-shadow: 0 0 8px rgba(229, 57, 53, 0.5) !important;
    }

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
        line-clamp: 2;
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

.search-result-item {
    cursor: pointer;
    transition: background-color 0.2s;

    &:hover {
        background-color: rgba(var(--v-theme-primary), 0.1);
    }
}

</style>
