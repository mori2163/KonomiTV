<template>
<<<<<<< HEAD
    <div class="reservation-list">
        <div v-if="title" class="reservation-list__header">
            <h2 class="reservation-list__title">{{ title }}</h2>
            <div class="reservation-list__actions">
                <v-btn
                    v-if="showMoreButton"
                    variant="text"
                    class="reservation-list__more"
                    @click="$emit('more')"
                >
=======
    <div class="reservation-list" :class="{'reservation-list--show-sort': !hideSort}">
        <div class="reservation-list__header" v-if="!hideHeader">
            <h2 class="reservation-list__title">
                <div v-if="showBackButton" v-ripple class="reservation-list__title-back" @click="$router.back()">
                    <Icon icon="fluent:chevron-left-12-filled" width="27px" />
                </div>
                <span class="reservation-list__title-text">{{ title }}</span>
                <div class="reservation-list__title-count" v-if="!showMoreButton">
                    <template v-if="isLoading">
                        <Icon icon="line-md:loading-twotone-loop" class="mr-1 spin" width="20px" height="20px" />
                    </template>
                    <template v-else>{{ displayTotal }}件</template>
                </div>
            </h2>
            <div class="reservation-list__actions">
                <v-select v-if="!hideSort"
                    v-model="sort_order"
                    :items="[
                        { title: '放送が近い順', value: 'asc' },
                        { title: '放送が遠い順', value: 'desc' },
                    ]"
                    item-title="title"
                    item-value="value"
                    class="reservation-list__sort"
                    color="primary"
                    bg-color="background-lighten-1"
                    variant="solo"
                    density="comfortable"
                    hide-details
                    @update:model-value="$emit('update:sortOrder', $event)">
                </v-select>
                <v-btn v-if="showMoreButton"
                    variant="text"
                    class="reservation-list__more"
                    @click="$emit('more')">
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
                    <span class="text-primary">もっと見る</span>
                    <Icon icon="fluent:chevron-right-12-regular" width="18px" class="ml-1 text-text-darken-1" style="margin: 0px -4px;" />
                </v-btn>
            </div>
        </div>
<<<<<<< HEAD

        <div v-if="isLoading && reservations.length === 0" class="reservation-list__loading">
            <v-progress-circular indeterminate size="32"></v-progress-circular>
        </div>

        <div v-else-if="showEmptyMessage && reservations.length === 0" class="reservation-list__empty">
            <v-icon :size="48" color="grey">{{ emptyIcon || 'mdi-calendar-blank' }}</v-icon>
            <div class="reservation-list__empty-message">
                <p v-html="emptyMessage || '近日中の予約はありません。'" class="text-white"></p>
                <p v-html="emptySubMessage || '番組表から新しい予約を追加できます。'" class="reservation-list__empty-submessage text-white"></p>
            </div>
        </div>

        <div v-else class="reservation-list__table-container">
            <table class="reservation-list__table">
                <thead>
                    <tr>
                        <th class="reservation-list__table-channel">チャンネル</th>
                        <th class="reservation-list__table-program">番組名</th>
                        <th class="reservation-list__table-time">放送時間</th>
                        <th class="reservation-list__table-status">状態</th>
                        <th class="reservation-list__table-actions">操作</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="reservation in reservations" :key="reservation.id" class="reservation-list__row"
                        :class="{ 'reservation-list__row--conflict': reservation.recording_availability !== 'Full' }">
                        <td class="reservation-list__channel">
                            {{ reservation.channel.name }}
                        </td>
                        <td class="reservation-list__program">
                            {{ reservation.program.title }}
                            <v-chip v-if="reservation.recording_availability !== 'Full'" color="error" size="x-small" class="ml-1">競合</v-chip>
                        </td>
                        <td class="reservation-list__time">
                            <div>{{ formatDateTime(reservation.program.start_time) }}</div>
                        </td>
                        <td class="reservation-list__status">
                            <v-chip
                                :color="getReservationStatusColor(reservation)"
                                size="small"
                            >
                                {{ getReservationStatusLabel(reservation) }}
                            </v-chip>
                        </td>
                        <td class="reservation-list__actions">
                            <v-btn icon="mdi-delete" variant="tonal" size="small" @click="onClickDelete(reservation)" :loading="deleting_reservation_id === reservation.id"></v-btn>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
        <!-- 確認ダイアログ -->
        <v-dialog v-model="show_confirm_dialog" max-width="450">
            <v-card>
                <v-card-title class="text-h6">予約の削除</v-card-title>
                <v-card-text>
                    「{{ deleting_reservation_title }}」を削除しますか？<br>
                    この操作は取り消せません。
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn color="secondary" @click="show_confirm_dialog = false">キャンセル</v-btn>
                    <v-btn color="error" @click="confirmDeleteReservation" :loading="is_deleting">削除</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script lang="ts" setup>
import { ref, PropType } from 'vue';
import dayjs from 'dayjs';
import 'dayjs/locale/ja';
import relativeTime from 'dayjs/plugin/relativeTime';
import customParseFormat from 'dayjs/plugin/customParseFormat';

import { IReservation } from '@/services/Reservations';
import Reservations from '@/services/Reservations';
import { useSnackbarsStore } from '@/stores/SnackbarsStore';

dayjs.extend(relativeTime);
dayjs.extend(customParseFormat);
dayjs.locale('ja');

const snackbarsStore = useSnackbarsStore();

const formatDateTime = (dateString: string): string => {
    return dayjs(dateString).format('YYYY年MM月DD日 HH:mm');
};

const props = defineProps({
    reservations: {
        type: Array as PropType<IReservation[]>,
        required: true,
    },
    total: {
        type: Number,
        required: true,
    },
    title: {
        type: String,
        default: '',
    },
    isLoading: {
        type: Boolean,
        default: false,
    },
    showEmptyMessage: {
        type: Boolean,
        default: true,
    },
    emptyIcon: {
        type: String,
        default: 'mdi-calendar-blank',
    },
    emptyMessage: {
        type: String,
        default: '現在、録画予約はありません。',
    },
    emptySubMessage: {
        type: String,
        default: '番組表から録画予約を追加できます。',
    },
    showMoreButton: {
        type: Boolean,
        default: false,
    },
});

const emit = defineEmits<{
=======
        <div class="reservation-list__grid"
            :class="{
                'reservation-list__grid--loading': isLoading,
                'reservation-list__grid--empty': displayTotal === 0 && showEmptyMessage,
            }">
            <div class="reservation-list__empty"
                :class="{
                    'reservation-list__empty--show': displayTotal === 0 && showEmptyMessage && !isLoading,
                }">
                <div class="reservation-list__empty-content">
                    <Icon class="reservation-list__empty-icon" :icon="emptyIcon" width="54px" height="54px" />
                    <h2 v-html="emptyMessage"></h2>
                    <div class="reservation-list__empty-submessage"
                        v-if="emptySubMessage" v-html="emptySubMessage"></div>
                </div>
            </div>
            <div class="reservation-list__grid-content">
                <Reservation v-for="reservation in displayReservations" :key="reservation.id" :reservation="reservation"
                    @deleted="handleReservationDeleted" />
            </div>
        </div>
        <div class="reservation-list__pagination" v-if="!hidePagination && displayTotal > 0">
            <v-pagination
                v-model="current_page"
                active-color="primary"
                density="comfortable"
                :length="Math.ceil(displayTotal / 30)"
                :total-visible="7"
                @update:model-value="$emit('update:page', $event)">
            </v-pagination>
        </div>
    </div>
</template>
<script lang="ts" setup>

import { ref, watch } from 'vue';

import Reservation from '@/components/Reservations/Reservation.vue';
import { IReservation } from '@/services/Reservations';

// Props
const props = withDefaults(defineProps<{
    title: string;
    reservations: IReservation[];
    total: number;
    page?: number;
    sortOrder?: 'desc' | 'asc';
    hideHeader?: boolean;
    hideSort?: boolean;
    hidePagination?: boolean;
    showMoreButton?: boolean;
    showBackButton?: boolean;
    showEmptyMessage?: boolean;
    emptyIcon?: string;
    emptyMessage?: string;
    emptySubMessage?: string;
    isLoading?: boolean;
}>(), {
    page: 1,
    sortOrder: 'desc',
    hideHeader: false,
    hideSort: false,
    hidePagination: false,
    showMoreButton: false,
    showBackButton: false,
    showEmptyMessage: true,
    emptyIcon: 'fluent:warning-20-regular',
    emptyMessage: '録画予約が見つかりませんでした。',
    emptySubMessage: '番組表から録画予約を追加できます。',
    isLoading: false,
});

// 現在のページ番号
const current_page = ref(props.page);

// 並び順
const sort_order = ref<'desc' | 'asc'>(props.sortOrder);

// 内部で管理する予約リスト
const displayReservations = ref<IReservation[]>([...props.reservations]);
// 内部で管理する合計数
const displayTotal = ref<number>(props.total);

// props の page が変更されたら current_page を更新
watch(() => props.page, (newPage) => {
    current_page.value = newPage;
});

// props の sortOrder が変更されたら sort_order を更新
watch(() => props.sortOrder, (newOrder) => {
    sort_order.value = newOrder;
});

// props の reservations が変更されたら displayReservations を更新
watch(() => props.reservations, (newReservations) => {
    displayReservations.value = [...newReservations];
});

// props の total が変更されたら displayTotal を更新
watch(() => props.total, (newTotal) => {
    displayTotal.value = newTotal;
});

// Emits
const emit = defineEmits<{
    (e: 'update:page', page: number): void;
    (e: 'update:sortOrder', order: 'desc' | 'asc'): void;
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
    (e: 'more'): void;
    (e: 'delete', reservation_id: number): void;
}>();

<<<<<<< HEAD
// 予約状態のラベルを取得
const getReservationStatusLabel = (reservation: IReservation): string => {
    if (reservation.is_recording_in_progress) {
        return '録画中';
    }
    if (reservation.recording_availability !== 'Full') {
        return '競合';
    }
    return dayjs(reservation.program.end_time).isBefore(dayjs()) ? '終了' : '予約済み';
};

// 予約状態の色を取得
const getReservationStatusColor = (reservation: IReservation): string => {
    if (reservation.is_recording_in_progress) {
        return 'primary';
    }
    if (reservation.recording_availability !== 'Full') {
        return 'error';
    }
    return dayjs(reservation.program.end_time).isBefore(dayjs()) ? 'grey' : 'success';
};

// 削除関連
const show_confirm_dialog = ref(false);
const deleting_reservation_id = ref<number | null>(null);
const deleting_reservation_title = ref<string>('');
const is_deleting = ref(false);

const onClickDelete = (reservation: IReservation) => {
    deleting_reservation_id.value = reservation.id;
    deleting_reservation_title.value = reservation.program.title;
    show_confirm_dialog.value = true;
};

const confirmDeleteReservation = async () => {
    if (deleting_reservation_id.value === null) return;
    is_deleting.value = true;
    try {
        const result = await Reservations.deleteReservation(deleting_reservation_id.value);
        if (result === true) {
            snackbarsStore.show('success', '予約を削除しました。');
            emit('delete', deleting_reservation_id.value);
        } else if (typeof result === 'object' && result.detail) {
            snackbarsStore.show('error', `予約の削除に失敗しました。${result.detail}`);
        } else {
            snackbarsStore.show('error', '予約の削除に失敗しました。');
        }
    } catch (error) {
        console.error('Failed to delete reservation:', error);
        snackbarsStore.show('error', '予約の削除に失敗しました。');
    } finally {
        is_deleting.value = false;
        show_confirm_dialog.value = false;
    }
};

</script>

<style lang="scss" scoped>
=======
// 予約が削除された時の処理
const handleReservationDeleted = (id: number) => {
    // 内部の予約リストから削除された予約を除外
    displayReservations.value = displayReservations.value.filter(reservation => reservation.id !== id);
    // 合計数を1減らす
    displayTotal.value = Math.max(0, displayTotal.value - 1);
    // 親コンポーネントに削除イベントを発行
    emit('delete', id);
};

</script>
<style lang="scss" scoped>

>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
.reservation-list {
    display: flex;
    flex-direction: column;
    width: 100%;
<<<<<<< HEAD
=======
    height: 100%;

    &--show-sort {
        .reservation-list__grid {
            @include smartphone-vertical {
                margin-top: 3px;
            }
        }
    }
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33

    &__header {
        display: flex;
        align-items: center;
<<<<<<< HEAD
        margin-bottom: 12px;
    }

    &__title {
        font-size: 24px;
        font-weight: 700;
        margin: 0;
        @include smartphone-vertical {
            font-size: 22px;
=======
        @include smartphone-vertical {
            padding: 0px 8px;
        }
    }

    &__title {
        display: flex;
        align-items: center;
        position: relative;
        font-size: 24px;
        font-weight: 700;
        padding-top: 8px;
        padding-bottom: 20px;
        @include smartphone-vertical {
            font-size: 22px;
            padding-bottom: 16px;
        }

        &-back {
            display: none;
            position: absolute;
            left: -8px;
            padding: 6px;
            border-radius: 50%;
            color: rgb(var(--v-theme-text));
            cursor: pointer;
            @include smartphone-vertical {
                display: flex;
            }

            & + .reservation-list__title-text {
                @include smartphone-vertical {
                    margin-left: 32px;
                }
            }
        }

        &-count {
            display: flex;
            align-items: center;
            flex-shrink: 0;
            padding-top: 8px;
            margin-left: 12px;
            font-size: 14px;
            font-weight: 400;
            color: rgb(var(--v-theme-text-darken-1));

            .spin {
                animation: spin 1.15s linear infinite;
            }

            @keyframes spin {
                from {
                    transform: rotate(0deg);
                }
                to {
                    transform: rotate(360deg);
                }
            }
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
        }
    }

    &__actions {
        display: flex;
        align-items: center;
        margin-left: auto;
<<<<<<< HEAD
    }

    &__more {
        padding: 0px 10px;
        font-size: 15px;
        letter-spacing: 0.05em;
    }

    &__loading {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 32px;
        min-height: 150px;
    }

    &__empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 24px 16px;
        text-align: center;
        color: rgb(var(--v-theme-on-surface-variant));
        border: 1px dashed rgba(var(--v-theme-on-surface), 0.12);
        border-radius: 8px;
        min-height: 150px;
    }

    &__empty-message {
        margin-top: 16px;
        font-size: 1.1rem;
        font-weight: bold;
        p {
            margin-bottom: 4px;
        }
    }

    &__empty-submessage {
        margin-top: 8px;
        font-size: 0.9rem;
        color: rgb(var(--v-theme-on-surface-variant), 0.8);
    }

    &__table-container {
        overflow-x: auto;
        background: rgb(var(--v-theme-background-lighten-1));
        border-radius: 8px;
    }

    &__table {
        width: 100%;
        border-collapse: collapse;

        th {
            padding: 12px 16px;
            text-align: left;
            white-space: nowrap;
            font-weight: bold;
            color: rgb(var(--v-theme-on-surface));
            border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
        }

        td {
            padding: 12px 16px;
            text-align: left;
            white-space: nowrap;
            color: rgb(var(--v-theme-on-surface));
            border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
        }

        tr:last-child td {
            border-bottom: none;
        }
    }

    &__row {
        &--conflict {
            td:first-child {
                border-left: 3px solid rgb(var(--v-theme-error));
=======
        :deep(.v-field) {
            padding-right: 4px !important;
        }
        :deep(.v-field__input) {
            padding-left: 12px !important;
            padding-right: 0px !important;
        }

        .v-select {
            width: 129px;
        }
    }

    &__sort {
        :deep(.v-field__input) {
            font-size: 14px !important;
            padding-top: 6px !important;
            padding-bottom: 6px !important;
            min-height: unset !important;
        }
    }

    &__more {
        margin-bottom: 12px;
        padding: 0px 10px;
        font-size: 15px;
        letter-spacing: 0.05em;
        @include smartphone-vertical {
            margin-bottom: 6px;
        }
    }

    &__grid {
        display: flex;
        flex-direction: column;
        position: relative;
        width: 100%;
        background: rgb(var(--v-theme-background-lighten-1));
        border-radius: 8px;
        overflow: hidden;

        &--loading {
            .reservation-list__grid-content {
                visibility: hidden;
                opacity: 0;
            }
        }
        &--empty {
            height: 100%;
            min-height: 200px;
        }

        .reservation-list__grid-content {
            height: 100%;
            transition: visibility 0.2s ease, opacity 0.2s ease;
        }

        :deep(.reservation) {
            // 最後の項目以外の下にボーダーを追加
            &:not(:last-child) > .reservation__container {
                border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
            }
        }
    }

<<<<<<< HEAD
    &__channel {
        min-width: 120px;
    }

    &__program {
        min-width: 200px;
        max-width: 250px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    &__time {
        min-width: 160px;
        font-size: 0.95em;
    }

    &__status {
        min-width: 100px;
    }

    &__actions {
        min-width: 80px;
        text-align: right;
    }
}
</style>
=======
    &__pagination {
        display: flex;
        justify-content: center;
        margin-top: 24px;
        @include smartphone-vertical {
            margin-top: 20px;
        }
    }

    &__empty {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
        padding-top: 28px;
        padding-bottom: 40px;
        flex-grow: 1;
        visibility: hidden;
        opacity: 0;
        transition: visibility 0.2s ease, opacity 0.2s ease;

        &--show {
            visibility: visible;
            opacity: 1;
        }

        &-content {
            text-align: center;

            .reservation-list__empty-icon {
                color: rgb(var(--v-theme-text-darken-1));
            }

            h2 {
                font-size: 21px;
                @include tablet-vertical {
                    font-size: 19px !important;
                }
                @include smartphone-horizontal {
                    font-size: 19px !important;
                }
                @include smartphone-horizontal-short {
                    font-size: 19px !important;
                }
                @include smartphone-vertical {
                    font-size: 19px !important;
                    text-align: center;
                }
            }

            .reservation-list__empty-submessage {
                margin-top: 8px;
                color: rgb(var(--v-theme-text-darken-1));
                font-size: 15px;
                @include tablet-vertical {
                    font-size: 13px !important;
                    text-align: center;
                }
                @include smartphone-horizontal {
                    font-size: 13px !important;
                    text-align: center;
                }
                @include smartphone-vertical {
                    font-size: 13px !important;
                    text-align: center;
                    margin-top: 7px !important;
                    line-height: 1.65;
                }
            }
        }
    }
}

</style>
>>>>>>> 8d353214e0dd9682011461904c6537bfc51e7f33
