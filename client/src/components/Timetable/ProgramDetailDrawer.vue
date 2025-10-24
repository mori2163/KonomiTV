<template>
    <div>
        <div
            class="timetable-program-detail-drawer__scrim"
            :class="{ 'timetable-program-detail-drawer__scrim--visible': isVisible }"
            @click="handleClose"
        ></div>
        <div
            class="timetable-program-detail-drawer"
            :class="{ 'timetable-program-detail-drawer--visible': isVisible }"
        >
            <div class="timetable-program-detail-drawer__header">
                <div class="timetable-program-detail-drawer__header-body" v-if="program">
                    <h2 class="timetable-program-detail-drawer__title">
                        {{ program.title }}
                    </h2>
                    <p class="timetable-program-detail-drawer__period">
                        {{ programPeriod }}
                    </p>
                </div>
                <div class="timetable-program-detail-drawer__header-body" v-else>
                    <h2 class="timetable-program-detail-drawer__title">
                        番組情報を取得できませんでした
                    </h2>
                </div>
                <div v-ripple class="timetable-program-detail-drawer__close" @click="handleClose">
                    <Icon icon="fluent:dismiss-16-filled" width="22px" height="22px" />
                </div>
            </div>
            <div class="timetable-program-detail-drawer__content" v-if="program">
                <div class="timetable-program-detail-drawer__badges">
                    <v-chip
                        v-if="isReserved"
                        color="error"
                        size="small"
                        variant="flat"
                        class="mr-2 mb-2"
                    >
                        <v-icon start>mdi-record-circle</v-icon>
                        録画予約済み
                    </v-chip>
                    <v-chip
                        v-if="!program.is_free"
                        color="warning"
                        size="small"
                        variant="flat"
                        class="mr-2 mb-2"
                    >
                        <v-icon start>mdi-currency-yen</v-icon>
                        有料放送
                    </v-chip>
                    <v-chip
                        v-if="isHdProgram"
                        color="success"
                        size="small"
                        variant="flat"
                        class="mr-2 mb-2"
                    >
                        <v-icon start>mdi-high-definition</v-icon>
                        HD
                    </v-chip>
                    <v-chip
                        v-for="genre in displayGenres"
                        :key="genre"
                        color="primary"
                        variant="outlined"
                        size="small"
                        class="mr-2 mb-2"
                    >
                        {{ genre }}
                    </v-chip>
                </div>
                <section class="timetable-program-detail-drawer__section">
                    <h3 class="timetable-program-detail-drawer__section-title">番組内容</h3>
                    <p class="timetable-program-detail-drawer__description">
                        {{ program.description || '番組説明が登録されていません。' }}
                    </p>
                </section>
                <section v-if="hasDetails" class="timetable-program-detail-drawer__section">
                    <h3 class="timetable-program-detail-drawer__section-title">詳細情報</h3>
                    <div class="timetable-program-detail-drawer__detail-grid">
                        <div
                            v-for="(value, key) in program.detail"
                            :key="key"
                            class="timetable-program-detail-drawer__detail-item"
                        >
                            <span class="timetable-program-detail-drawer__detail-key">{{ key }}:</span>
                            <span class="timetable-program-detail-drawer__detail-value">{{ value }}</span>
                        </div>
                    </div>
                </section>
            </div>
            <div v-else class="timetable-program-detail-drawer__empty">
                番組情報の読み込みに失敗しました。
            </div>
            <div v-if="program" class="timetable-program-detail-drawer__footer">
                <div class="timetable-program-detail-drawer__actions">
                    <v-btn
                        v-if="!isReserved"
                        color="primary"
                        variant="flat"
                        class="px-4"
                        :loading="isReserving"
                        @click="handleReserve"
                    >
                        録画予約
                    </v-btn>
                    <v-btn
                        v-else
                        color="error"
                        variant="flat"
                        class="px-4"
                        :loading="isReserving"
                        @click="handleRemove"
                    >
                        <Icon icon="fluent:delete-16-regular" width="20px" height="20px" />
                        <span class="ml-2">予約削除</span>
                    </v-btn>
                    <v-btn variant="text" color="text" class="px-4" @click="handleClose">
                        閉じる
                    </v-btn>
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { Icon } from '@iconify/vue';
import { computed, onUnmounted, watch } from 'vue';

import type { IProgram } from '@/services/Programs';

const props = defineProps<{
    modelValue: boolean;
    program: IProgram | null;
    isReserved: boolean;
    isReserving: boolean;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'reserve', programId: string): void;
    (e: 'remove', programId: string): void;
}>();

const isVisible = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value),
});

const displayGenres = computed(() => {
    if (!props.program) return [] as string[];
    return props.program.genres.slice(0, 2).map((genre) => genre.major);
});

const isHdProgram = computed(() => {
    const resolution = props.program?.video_resolution;
    return resolution === '1080i' || resolution === '1080p';
});

const hasDetails = computed(() => {
    if (!props.program) return false;
    return Object.keys(props.program.detail ?? {}).length > 0;
});

const formatFullDateTime = (time: string) => {
    const date = new Date(time);
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    return `${y}/${m}/${d} ${hh}:${mm}`;
};

const programPeriod = computed(() => {
    if (!props.program) return '';
    const start = formatFullDateTime(props.program.start_time);
    const end = formatFullDateTime(props.program.end_time);
    const duration = Math.floor(props.program.duration / 60);
    return `${start} - ${end} (${duration}分)`;
});

// ドロワー表示時にページスクロールを抑制
watch(isVisible, (value) => {
    if (value) {
        document.documentElement.classList.add('v-overlay-scroll-blocked');
    } else {
        document.documentElement.classList.remove('v-overlay-scroll-blocked');
    }
}, { immediate: true });

onUnmounted(() => {
    document.documentElement.classList.remove('v-overlay-scroll-blocked');
});

const handleClose = () => {
    emit('update:modelValue', false);
};

const handleReserve = () => {
    if (!props.program || props.isReserving) return;
    emit('reserve', props.program.id);
};

const handleRemove = () => {
    if (!props.program || props.isReserving) return;
    emit('remove', props.program.id);
};
</script>

<style lang="scss" scoped>
.timetable-program-detail-drawer__scrim {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1009;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.25s ease, visibility 0.25s ease;
    pointer-events: none;

    &--visible {
        opacity: 1;
        visibility: visible;
        pointer-events: auto;
    }
}

.timetable-program-detail-drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 420px;
    display: flex;
    flex-direction: column;
    background: rgb(var(--v-theme-background));
    border-top-left-radius: 16px;
    border-bottom-left-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.16);
    z-index: 1010;
    transform: translateX(100%);
    transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);

    &--visible {
        transform: translateX(0);
    }

    @media (max-width: 480px) {
        width: calc(100vw - 32px);
    }

    &__header {
        display: flex;
        position: relative;
        min-height: 64px;
        padding: 16px 16px 16px 24px;
        background: rgb(var(--v-theme-background-lighten-1));
        border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
        border-top-left-radius: 16px;
        align-items: flex-start;
    }

    &__header-body {
        flex: 1;
        padding-right: 12px;
    }

    &__title {
        font-size: 20px;
        font-weight: 600;
        line-height: 1.3;
        margin: 0;
        color: rgb(var(--v-theme-text));
        word-break: break-word;
    }

    &__period {
        margin: 6px 0 0;
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
        font-weight: 400;
    }

    &__close {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border-radius: 8px;
        color: rgb(var(--v-theme-text));
        cursor: pointer;
        transition: background-color 0.15s ease;

        &:hover {
            background: rgb(var(--v-theme-background-lighten-2));
        }

        @media (hover: none) {
            &:hover {
                background: rgb(var(--v-theme-background-lighten-1));
            }
        }
    }

    &__content {
        flex: 1;
        overflow-y: auto;
        padding: 20px 24px 24px;
        background: rgb(var(--v-theme-background));
    }

    &__badges {
        display: flex;
        flex-wrap: wrap;
        margin-bottom: 16px;
    }

    &__section {
        &:not(:last-child) {
            margin-bottom: 24px;
        }
    }

    &__section-title {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 8px;
        color: rgb(var(--v-theme-text));
    }

    &__description {
        font-size: 13px;
        line-height: 1.6;
        color: rgb(var(--v-theme-text-darken-1));
        font-weight: 400;
        white-space: pre-wrap;
        word-break: break-word;
    }

    &__detail-grid {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    &__detail-item {
        display: flex;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
    }

    &__detail-key {
        min-width: 96px;
        font-weight: 600;
        color: rgb(var(--v-theme-primary));
        margin-right: 12px;
    }

    &__detail-value {
        flex: 1;
        color: rgb(var(--v-theme-text-darken-1));
        word-break: break-word;
        font-size: 13px;
        font-weight: 400;
    }

    &__empty {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 1;
        padding: 24px;
        font-size: 14px;
        color: rgb(var(--v-theme-text));
        background: rgb(var(--v-theme-background));
    }

    &__footer {
        padding: 12px 16px;
        background: rgb(var(--v-theme-background-lighten-1));
        border-top: 1px solid rgb(var(--v-theme-background-lighten-2));
        border-bottom-left-radius: 16px;
    }

    &__actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 8px;
    }
}
</style>
