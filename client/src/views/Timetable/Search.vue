<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="timetable-search-page-wrapper">
                <SPHeaderBar />
                <div class="timetable-search-page">
                    <Breadcrumbs :crumbs="breadcrumbs" />
                    <section class="search-page-header">
                        <div>
                            <h1>{{ searchTitle }}</h1>
                            <p class="search-page-subtitle">{{ searchSubtitle }}</p>
                        </div>
                        <v-btn
                            variant="text"
                            prepend-icon="mdi-table"
                            class="search-back-btn"
                            @click="goToTimetable"
                        >
                            番組表に戻る
                        </v-btn>
                    </section>

                    <section class="search-input-card">
                        <v-text-field
                            v-model="search_keyword_input"
                            label="番組名・出演者・番組説明"
                            variant="outlined"
                            density="comfortable"
                            prepend-inner-icon="mdi-magnify"
                            clearable
                            hide-details
                            @keyup.enter="submitKeywordSearch"
                        />
                        <div class="keyword-actions">
                            <v-btn
                                class="keyword-search-btn"
                                color="primary"
                                block
                                @click="submitKeywordSearch"
                                :disabled="!search_keyword_input.trim()"
                            >
                                この条件で検索
                            </v-btn>
                            <small class="keyword-hint">Enter キーでも検索できます</small>
                        </div>

                        <div class="search-panels search-panels--inline">
                            <v-expansion-panels
                                v-model="activeSearchPanels"
                                multiple
                                class="search-panels__list"
                            >
                                <v-expansion-panel value="search" elevation="4" class="search-panel">
                                    <v-expansion-panel-title expand-icon="mdi-chevron-down" class="search-panel__title">
                                        <div class="search-panel__title-text">
                                            <v-icon icon="mdi-filter-variant-plus" class="mr-2" />
                                            検索条件
                                        </div>
                                    </v-expansion-panel-title>
                                    <v-expansion-panel-text>
                                        <div class="search-panel__body">
                                            <div class="search-panel__section">
                                                <p class="search-panel__section-title">キーワードの検索方法</p>
                                                <div class="filter-switches">
                                                    <v-switch
                                                        v-model="search_is_title_only"
                                                        label="タイトルのみ検索"
                                                        color="primary"
                                                        density="compact"
                                                        hide-details
                                                    />
                                                    <v-switch
                                                        v-model="search_is_free_only"
                                                        label="無料番組のみ"
                                                        color="primary"
                                                        density="compact"
                                                        hide-details
                                                    />
                                                </div>
                                            </div>
                                            <div class="search-panel__section">
                                                <p class="search-panel__section-title">検索フィルター</p>
                                                <v-select
                                                    v-model="search_selected_channels"
                                                    :items="channel_options"
                                                    label="チャンネルを絞り込む"
                                                    multiple
                                                    chips
                                                    closable-chips
                                                    clearable
                                                    density="comfortable"
                                                    variant="outlined"
                                                    class="filter-select"
                                                />

                                                <div class="filter-group">
                                                    <span class="filter-label">放送タイミング</span>
                                                    <v-chip-group
                                                        v-model="search_time_filter"
                                                        column
                                                        mandatory
                                                        class="time-filter-chips"
                                                    >
                                                        <v-chip value="all" prepend-icon="mdi-all-inclusive">すべて</v-chip>
                                                        <v-chip value="upcoming" prepend-icon="mdi-clock-outline">これから放送</v-chip>
                                                        <v-chip value="today" prepend-icon="mdi-calendar-today">今日放送</v-chip>
                                                    </v-chip-group>
                                                </div>

                                                <v-btn
                                                    variant="text"
                                                    prepend-icon="mdi-restore"
                                                    class="filter-reset-btn"
                                                    @click="resetSearchFilters"
                                                    :disabled="!hasActiveSearchFilter"
                                                >
                                                    条件をリセット
                                                </v-btn>
                                            </div>
                                        </div>
                                    </v-expansion-panel-text>
                                </v-expansion-panel>
                            </v-expansion-panels>
                        </div>
                    </section>

                    <section class="search-results-section">
                        <div class="search-content__top-bar" v-if="has_submitted_search && !search_is_searching">
                            <div>
                                <p class="search-info">
                                    {{ filtered_search_results.length }}件を表示（全{{ search_total }}件）
                                    <span v-if="hasActiveSearchFilter" class="search-info__filters">フィルター適用中</span>
                                </p>
                                <p v-if="search_last_executed_at" class="search-updated">
                                    最終更新: {{ formatDateTime(search_last_executed_at) }}
                                </p>
                            </div>
                            <div class="sort-controls">
                                <span class="sort-label">並び替え</span>
                                <v-btn-toggle
                                    v-model="search_sort_order"
                                    color="primary"
                                    mandatory
                                    density="comfortable"
                                    class="sort-toggle"
                                >
                                    <v-btn value="newest">新しい順</v-btn>
                                    <v-btn value="oldest">古い順</v-btn>
                                </v-btn-toggle>
                            </div>
                        </div>

                        <div v-if="search_is_searching" class="loading-container">
                            <v-progress-circular indeterminate size="64" />
                            <p class="mt-4">番組を検索しています...</p>
                        </div>

                        <div v-else-if="search_error_message" class="error-container">
                            <v-icon icon="mdi-alert-circle" size="64" color="error" />
                            <p class="mt-4">{{ search_error_message }}</p>
                        </div>

                        <div v-else-if="!has_submitted_search">
                            <div class="no-results">
                                <v-icon icon="mdi-magnify" size="64" color="grey-darken-1" />
                                <p class="mt-4">キーワードを入力して番組を検索してください。</p>
                            </div>
                        </div>

                        <div v-else-if="grouped_search_results.length === 0" class="no-results">
                            <v-icon icon="mdi-magnify-remove-outline" size="64" color="grey-darken-1" />
                            <p class="mt-4">検索条件に一致する番組が見つかりませんでした</p>
                            <p v-if="hasActiveSearchFilter" class="no-results__hint">フィルターを緩めると見つかる場合があります</p>
                        </div>

                        <div v-else class="search-results-list">
                            <div
                                v-for="group in grouped_search_results"
                                :key="group.key"
                                class="result-group"
                            >
                                <div class="result-group-header">
                                    <div>
                                        <p class="group-date">{{ group.label }}</p>
                                        <p class="group-count">{{ group.programs.length }}件</p>
                                    </div>
                                </div>
                                <v-card
                                    v-for="program in group.programs"
                                    :key="program.id"
                                    class="result-card result-card--list"
                                    @click="handleSearchResultClick(program)"
                                >
                                    <div class="result-card-meta">
                                        <v-chip size="small" class="channel-chip" prepend-icon="mdi-television-classic">
                                            {{ getChannelLabel(program.channel_id) }}
                                        </v-chip>
                                        <span class="time-info">{{ formatProgramRange(program.start_time, program.end_time) }}</span>
                                    </div>
                                    <h3 class="result-title" v-html="highlightKeyword(program.title)"></h3>
                                    <p
                                        v-if="program.description"
                                        class="result-description"
                                        v-html="highlightKeyword(truncateText(program.description, 160))"
                                    />
                                    <div class="result-badges">
                                        <v-chip v-if="program.is_free === false" size="small" color="warning" class="mr-1">有料</v-chip>
                                        <v-chip v-if="isReserved(program.id)" size="small" color="error" class="mr-1">予約済</v-chip>
                                        <v-chip
                                            v-for="genre in program.genres"
                                            :key="genre.major + genre.middle"
                                            size="small"
                                            class="mr-1"
                                        >
                                            {{ genre.major }}
                                        </v-chip>
                                    </div>
                                </v-card>
                            </div>
                        </div>
                    </section>
                </div>
            </div>
        </main>

        <ProgramDetailDrawer
            v-model="is_panel_shown"
            :program="selected_program"
            :is-reserved="selected_program ? isReserved(selected_program.id) : false"
            :is-reserving="is_reserving"
            @reserve="reserveProgram"
            @remove="deleteReservation"
        />
    </div>
</template>
<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import ProgramDetailDrawer from '@/components/Timetable/ProgramDetailDrawer.vue';
import { IProgram } from '@/services/Programs';
import Reservations, { IRecordSettings } from '@/services/Reservations';
import TimetableService from '@/services/Timetable';
import useChannelsStore from '@/stores/ChannelsStore';
import { useSnackbarsStore } from '@/stores/SnackbarsStore';
import { useTimetableStore } from '@/stores/TimetableStore';

const route = useRoute();
const router = useRouter();
const channelsStore = useChannelsStore();
const timetableStore = useTimetableStore();
const snackbarsStore = useSnackbarsStore();

const breadcrumbs = [
    { name: 'ホーム', path: '/' },
    { name: '番組表', path: '/timetable/' },
    { name: '検索結果', path: '/timetable/search', disabled: true },
];

const query = ref('');
const search_keyword_input = ref('');

const search_sort_order = ref<'newest' | 'oldest'>('newest');
const search_time_filter = ref<'all' | 'upcoming' | 'today'>('all');
const search_selected_channels = ref<string[]>([]);
const search_is_title_only = ref(false);
const search_is_free_only = ref(false);

const search_results = ref<IProgram[]>([]);
const search_total = ref(0);
const search_is_searching = ref(false);
const search_error_message = ref('');
const has_submitted_search = ref(false);
const search_last_executed_at = ref<Date | null>(null);
const is_loading = ref(true);

type SearchPanelValue = 'search';
const activeSearchPanels = ref<SearchPanelValue[]>([]);

const is_panel_shown = ref(false);
const selected_program = ref<IProgram | null>(null);
const is_reserving = ref(false);

const searchTitle = computed(() => {
    const keyword = query.value.trim();
    return keyword ? `「${keyword}」の検索結果` : '番組検索';
});

const searchSubtitle = computed(() => {
    if (!query.value.trim()) {
        return 'キーワードを入力して番組を検索してください。';
    }
    if (search_is_searching.value) {
        return `「${query.value}」で検索中…`;
    }
    if (has_submitted_search.value) {
        return `${search_total.value}件ヒットしました。`;
    }
    return 'Enter キーでも検索を実行できます。';
});

const hasActiveSearchFilter = computed(() => {
    return (
        search_selected_channels.value.length > 0 ||
        search_is_title_only.value ||
        search_is_free_only.value ||
        search_time_filter.value !== 'all'
    );
});

const channel_options = computed(() => {
    const channels_list = channelsStore.channels_list;
    if (!channels_list) {
        return [];
    }
    const all_channels = [...channels_list.GR, ...channels_list.BS, ...channels_list.CS, ...channels_list.CATV, ...channels_list.SKY];
    return all_channels.map((ch) => ({
        title: `${ch.channel_number} ${ch.name}`,
        value: ch.id,
    }));
});

const channel_metadata_map = computed(() => {
    const map = new Map<string, { channel_number: string; name: string }>();
    const channels_list = channelsStore.channels_list;
    if (channels_list) {
        const all_channels = [...channels_list.GR, ...channels_list.BS, ...channels_list.CS, ...channels_list.CATV, ...channels_list.SKY];
        for (const ch of all_channels) {
            map.set(ch.id, { channel_number: ch.channel_number, name: ch.name });
        }
    }
    return map;
});

const getChannelLabel = (channel_id: string): string => {
    const meta = channel_metadata_map.value.get(channel_id);
    return meta ? `${meta.channel_number} ${meta.name}` : channel_id;
};

const formatProgramRange = (start: string, end: string): string => {
    const formatTime = (time: string) => {
        const d = new Date(time);
        return `${String(d.getMonth() + 1)}/${String(d.getDate())} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    };
    return `${formatTime(start)} 〜 ${formatTime(end)}`;
};

const formatDateWithDay = (date: Date): string => {
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const dayOfWeek = ['日', '月', '火', '水', '木', '金', '土'][date.getDay()];
    return `${month}/${day} (${dayOfWeek})`;
};

const formatDateTime = (date: Date): string => {
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${month}/${day} ${hours}:${minutes}`;
};

const escapeHtml = (value: string): string => {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
};

const escapeRegExp = (string: string): string => {
    return string.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
};

const highlightKeyword = (text: string): string => {
    const keyword = query.value.trim();
    if (!keyword) {
        return escapeHtml(text);
    }
    const escapedKeyword = escapeRegExp(keyword);
    const regex = new RegExp(`(${escapedKeyword})`, 'gi');
    return escapeHtml(text).replace(regex, '<mark class="keyword-highlight">$1</mark>');
};

const truncateText = (text: string, maxLength: number): string => {
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.substring(0, maxLength)}...`;
};

const filtered_search_results = computed(() => {
    let filtered = [...search_results.value];
    const nowDate = new Date();

    if (search_time_filter.value === 'upcoming') {
        filtered = filtered.filter(program => new Date(program.end_time) >= nowDate);
    } else if (search_time_filter.value === 'today') {
        const startOfDay = new Date(nowDate);
        startOfDay.setHours(0, 0, 0, 0);
        const endOfDay = new Date(startOfDay);
        endOfDay.setHours(23, 59, 59, 999);
        filtered = filtered.filter(program => {
            const start = new Date(program.start_time);
            return start >= startOfDay && start <= endOfDay;
        });
    }

    filtered.sort((a, b) => {
        const diff = new Date(a.start_time).getTime() - new Date(b.start_time).getTime();
        return search_sort_order.value === 'oldest' ? diff : -diff;
    });

    return filtered;
});

const grouped_search_results = computed(() => {
    const groups = new Map<string, { key: string; label: string; programs: IProgram[] }>();
    for (const program of filtered_search_results.value) {
        const start = new Date(program.start_time);
        const key = start.toISOString().split('T')[0];
        if (!groups.has(key)) {
            groups.set(key, {
                key,
                label: formatDateWithDay(start),
                programs: [],
            });
        }
        groups.get(key)!.programs.push(program);
    }
    return Array.from(groups.values());
});

const reservedProgramIdsSet = computed(() => {
    return new Set(timetableStore.reserved_program_ids);
});

const isReserved = (program_id: string): boolean => {
    return reservedProgramIdsSet.value.has(program_id);
};

const handleSearchResultClick = (program: IProgram) => {
    selected_program.value = program;
    is_panel_shown.value = true;
};

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
        await timetableStore.fetchReservations();
    } else {
        snackbarsStore.show('error', '録画予約の追加に失敗しました。');
    }
    is_reserving.value = false;
};

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
        await timetableStore.fetchReservations();
    } else {
        snackbarsStore.show('error', '録画予約の削除に失敗しました。');
    }
    is_reserving.value = false;
};

const goToTimetable = () => {
    router.push('/timetable/');
};

const resetSearchState = () => {
    search_results.value = [];
    search_total.value = 0;
    search_error_message.value = '';
    has_submitted_search.value = false;
    search_last_executed_at.value = null;
    search_is_searching.value = false;
    is_loading.value = false;
};

const runProgramSearch = async () => {
    const keyword = query.value.trim();
    if (!keyword) {
        resetSearchState();
        return;
    }

    search_is_searching.value = true;
    search_error_message.value = '';
    try {
        const response = await TimetableService.searchPrograms({
            keyword,
            channelIds: search_selected_channels.value.length > 0 ? search_selected_channels.value : undefined,
            titleOnly: search_is_title_only.value || undefined,
            isFreeOnly: search_is_free_only.value || undefined,
        });

        if (response) {
            search_results.value = response.programs;
            search_total.value = response.total;
        }
        search_last_executed_at.value = new Date();
        has_submitted_search.value = true;
    } catch (error: any) {
        console.error('Program search error:', error);
        search_error_message.value = error?.message ?? '番組の検索中にエラーが発生しました。';
        search_results.value = [];
        search_total.value = 0;
    } finally {
        search_is_searching.value = false;
        is_loading.value = false;
    }
};

const submitKeywordSearch = () => {
    const keyword = search_keyword_input.value.trim();
    if (!keyword) {
        router.replace({ path: '/timetable/search' });
        resetSearchState();
        return;
    }

    router.push({
        path: '/timetable/search',
        query: {
            query: keyword,
        },
    });
};

const resetSearchFilters = () => {
    search_selected_channels.value = [];
    search_is_title_only.value = false;
    search_is_free_only.value = false;
    search_time_filter.value = 'all';
};

watch(() => route.query.query, async (newQuery) => {
    const keyword = typeof newQuery === 'string' ? newQuery : '';
    query.value = keyword;
    search_keyword_input.value = keyword;

    if (!keyword) {
        resetSearchState();
        return;
    }

    if (!channelsStore.channels_list) {
        await channelsStore.update();
    }
    await runProgramSearch();
}, { immediate: true });

watch([search_selected_channels, search_is_title_only, search_is_free_only], () => {
    if (query.value.trim() && has_submitted_search.value) {
        void runProgramSearch();
    }
});

onMounted(() => {
    if (!channelsStore.channels_list) {
        void channelsStore.update();
    }
    if (timetableStore.reserved_program_ids.length === 0) {
        void timetableStore.fetchReservations();
    }
});
</script>
<style lang="scss" scoped>
.timetable-search-page-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.timetable-search-page {
    display: flex;
    flex-direction: column;
    width: 100%;
    max-width: 1000px;
    margin: 0 auto;
    padding: 24px 24px 48px;
    @include smartphone-horizontal {
        padding: 20px;
    }
    @include smartphone-horizontal-short {
        padding: 20px 16px;
    }
    @include smartphone-vertical {
        padding: 16px 8px 32px;
    }
}

.search-page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 20px;
    flex-wrap: wrap;

    h1 {
        margin: 0;
        font-size: 26px;
        font-weight: 700;
    }
}

.search-page-subtitle {
    margin-top: 4px;
    color: rgb(var(--v-theme-text-darken-1));
}

.search-back-btn {
    align-self: flex-start;
}

.search-input-card {
    padding: 20px;
    border-radius: 20px;
    background: rgb(var(--v-theme-background-lighten-1));
    border: 1px solid rgb(var(--v-theme-background-lighten-2));
    margin-bottom: 20px;

    @include smartphone-vertical {
        padding: 16px;
    }
}

.keyword-actions {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.keyword-hint {
    color: rgba(var(--v-theme-text), 0.65);
}

.search-panels {
    margin-top: 20px;
}

.search-panels--inline {
    margin-bottom: 0;
}

.search-panels__list {
    border-radius: 18px;
    overflow: hidden;
    background: rgb(var(--v-theme-background-lighten-1));
    border: 1px solid rgb(var(--v-theme-background-lighten-2));
    box-shadow: 0 16px 34px -28px rgba(0, 0, 0, 0.65);

    :deep(.v-expansion-panel) {
        background: rgb(var(--v-theme-background));
    }

    :deep(.v-expansion-panel:not(:last-child)) {
        border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
    }
}

.search-panel__title {
    padding: 20px 24px !important;
    font-weight: 700;
}

.search-panel__title-text {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 1rem;
}

.search-panel__body {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 4px 24px 24px;

    @include smartphone-vertical {
        padding: 0 16px 20px;
    }
}

.search-panel__section {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
    border-radius: 18px;
    background: rgb(var(--v-theme-background-lighten-1));
    border: 1px solid rgb(var(--v-theme-background-lighten-2));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);

    @include smartphone-vertical {
        padding: 16px;
    }
}

.search-panel__section-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: rgb(var(--v-theme-text));
}

.filter-group {
    margin-top: 8px;
}

.filter-label {
    font-size: 0.95em;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: rgb(var(--v-theme-text-darken-1));
}

.time-filter-chips {
    margin-top: 8px;
    gap: 8px;

    :deep(.v-chip) {
        width: 100%;
    }
}

.filter-switches {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.filter-reset-btn {
    margin-top: 4px;
    width: 100%;
}

.search-results-section {
    min-height: 420px;
    padding: 24px;
    border-radius: 24px;
    background: rgb(var(--v-theme-background-lighten-1));
    border: 1px solid rgb(var(--v-theme-background-lighten-2));

    @include smartphone-vertical {
        padding: 16px;
    }
}

.search-content__top-bar {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}

.search-info {
    font-size: 16px;
    color: rgb(var(--v-theme-text-darken-1));
}

.search-info__filters {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-left: 8px;
    font-size: 0.85em;
    color: rgb(var(--v-theme-primary));
    font-weight: 600;
}

.search-updated {
    font-size: 0.85em;
    color: rgba(var(--v-theme-text), 0.65);
}

.sort-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.sort-label {
    font-size: 0.9em;
    color: rgb(var(--v-theme-text-darken-1));
}

.sort-toggle {
    :deep(.v-btn) {
        border: 1px solid rgb(var(--v-theme-outline-variant));
        background-color: rgb(var(--v-theme-surface));
    }
}

.loading-container,
.error-container,
.no-results {
    text-align: center;
    padding: 64px 20px;
    color: rgb(var(--v-theme-text-darken-1));
}

.no-results__hint {
    margin-top: 8px;
    color: rgba(var(--v-theme-text), 0.65);
}

.search-results-list {
    display: flex;
    flex-direction: column;
    gap: 24px;
}

.result-group {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.result-group-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
    padding-bottom: 4px;
}

.group-date {
    font-size: 1.1em;
    font-weight: 700;
}

.group-count {
    font-size: 0.9em;
    color: rgba(var(--v-theme-text), 0.65);
}

.result-card--list {
    padding: 16px 20px;
    cursor: pointer;
    transition: transform 0.2s ease, box-shadow 0.2s ease;

    &:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.18);
    }
}

.result-card-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 8px;
    font-size: 0.9em;
    color: rgb(var(--v-theme-text-darken-1));
}

.channel-chip {
    :deep(.v-chip__content) {
        font-weight: 600;
    }
}

.result-title {
    font-size: 1.1em;
    font-weight: 700;
    margin-bottom: 6px;
    word-break: break-word;
}

.result-description {
    font-size: 0.95em;
    line-height: 1.5;
    color: rgb(var(--v-theme-text-darken-1));
}

.result-badges {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.keyword-highlight {
    background-color: rgba(var(--v-theme-primary), 0.15);
    color: rgb(var(--v-theme-primary));
    padding: 0 2px;
    border-radius: 3px;
}
</style>
