<template>
    <div class="capture-detail-drawer__scrim"
        :class="{ 'capture-detail-drawer__scrim--visible': isVisible }"
        @click="handleClose"></div>

    <div class="capture-detail-drawer" :class="{ 'capture-detail-drawer--visible': isVisible }">
        <div class="capture-detail-drawer__header">
            <div class="capture-detail-drawer__title">キャプチャ情報</div>
            <v-spacer></v-spacer>
            <v-btn icon variant="flat" @click="handleClose">
                <Icon icon="fluent:dismiss-16-filled" />
            </v-btn>
        </div>

        <div v-if="capture" class="capture-detail-drawer__content">
            <div class="capture-detail-drawer__property">
                <div class="capture-detail-drawer__property-label">ファイル名</div>
                <div class="capture-detail-drawer__property-value">{{ capture.name }}</div>
            </div>
            <div v-if="capture.time" class="capture-detail-drawer__property">
                <div class="capture-detail-drawer__property-label">時間</div>
                <div class="capture-detail-drawer__property-value">{{ dayjs(capture.time).format('YYYY/MM/DD HH:mm:ss') }}</div>
            </div>
            <div v-if="capture.program_title" class="capture-detail-drawer__property">
                <div class="capture-detail-drawer__property-label">番組</div>
                <div class="capture-detail-drawer__property-value">{{ capture.channel_name }} - {{ capture.program_title }}</div>
            </div>
            <div class="capture-detail-drawer__property">
                <div class="capture-detail-drawer__property-label">サイズ</div>
                <div class="capture-detail-drawer__property-value">{{ Utils.formatBytes(capture.size) }}</div>
            </div>
            <div class="capture-detail-drawer__property">
                <div class="capture-detail-drawer__property-label">パス</div>
                <div class="capture-detail-drawer__property-value capture-detail-drawer__property-value--path">{{ capture.path }}</div>
            </div>
        </div>

        <div class="capture-detail-drawer__footer">
            <v-btn color="secondary" block size="large" @click="downloadCapture">
                <Icon icon="fluent:download-16-regular" class="mr-2" />
                <span>ダウンロード</span>
            </v-btn>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { computed, watch } from 'vue';

import Message from '@/message';
import { ICapture } from '@/services/Captures';
import Utils, { dayjs } from '@/utils';

const props = defineProps<{
    capture: ICapture | null;
    modelValue: boolean;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
}>();

const isVisible = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value),
});

// ドロワーが開かれたら、ページ全体のスクロールを無効化する
watch(isVisible, (newValue) => {
    if (newValue) {
        document.documentElement.classList.add('v-overlay-scroll-blocked');
    } else {
        document.documentElement.classList.remove('v-overlay-scroll-blocked');
    }
});

const handleClose = () => {
    isVisible.value = false;
};

const downloadCapture = async () => {
    if (!props.capture) return;
    try {
        const response = await fetch(props.capture.url);
        if (!response.ok) {
            throw new Error('Failed to fetch capture image.');
        }
        const blob = await response.blob();
        Utils.downloadBlobData(blob, props.capture.name);
        Message.success('キャプチャをダウンロードしました。');
    } catch (error) {
        console.error('Failed to download capture:', error);
        Message.error('キャプチャのダウンロードに失敗しました。');
    }
};

</script>

<style lang="scss" scoped>

.capture-detail-drawer__scrim {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1008;
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

.capture-detail-drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 370px;
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
        align-items: center;
        flex-shrink: 0;
        padding: 8px 8px 8px 20px;
        background: rgb(var(--v-theme-background-lighten-1));
        border-bottom: 1px solid rgb(var(--v-theme-background-lighten-2));
        border-top-left-radius: 16px;
    }

    &__title {
        font-size: 20px;
        font-weight: 700;
    }

    &__content {
        display: flex;
        flex-direction: column;
        flex-grow: 1;
        padding: 24px;
        overflow-y: auto;
    }

    &__property {
        margin-bottom: 20px;
        &:last-of-type {
            margin-bottom: 0;
        }
    }

    &__property-label {
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 6px;
    }

    &__property-value {
        font-size: 15px;
        font-weight: 500;
        &--path {
            font-family: 'M PLUS 1p', sans-serif;
            word-break: break-all;
            line-height: 1.6;
        }
    }

    &__footer {
        padding: 16px;
        border-top: 1px solid rgb(var(--v-theme-background-lighten-2));
    }
}
</style>
