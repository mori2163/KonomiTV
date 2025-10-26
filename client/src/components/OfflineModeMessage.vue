<template>
    <div class="offline-mode-message">
        <div class="offline-mode-message__container">
            <Icon icon="fluent:wifi-off-24-regular" width="64px" height="64px" class="offline-mode-message__icon" aria-hidden="true" />
            <h2 class="offline-mode-message__title">オフラインモードです</h2>
            <p class="offline-mode-message__description">
                現在、オフラインモードが有効になっています。<br>
                オフラインモードでは、オフライン視聴ページのみ利用できます。
            </p>
            <v-btn
                color="primary"
                variant="flat"
                size="large"
                @click="goToOfflinePage"
            >
                <Icon icon="fluent:play-circle-20-regular" width="20px" class="mr-2" aria-hidden="true" />
                オフライン視聴ページへ
            </v-btn>
        </div>
    </div>
</template>
<script lang="ts" setup>

import { useRouter } from 'vue-router';

const router = useRouter();

// オフライン視聴ページへ移動
const goToOfflinePage = () => {
    router.push('/offline');
};

</script>
<style lang="scss" scoped>

.offline-mode-message {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: calc(100vh - 80px);
    padding: 40px 20px;
    box-sizing: border-box;

    &__container {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        max-width: 600px;
    }

    &__icon {
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 24px;
        opacity: 0.7;
    }

    &__title {
        font-size: 28px;
        font-weight: 600;
        margin-bottom: 16px;
        color: rgb(var(--v-theme-text));
    }

    &__description {
        font-size: 16px;
        line-height: 1.6;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 32px;
    }
}

</style>
