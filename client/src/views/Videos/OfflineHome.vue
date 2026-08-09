<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="offline-home-container-wrapper">
                <SPHeaderBar />
                <div class="offline-home-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'オフライン視聴', path: '/videos/offline', disabled: true },
                    ]" />

                    <div class="text-error mb-4" v-if="offlineManagerStore.is_supported === false">
                        このブラウザではオフライン保存機能を利用できません。
                    </div>

                    <RecordedProgramList
                        title="オフライン視聴"
                        :programs="programs"
                        :total="totalPrograms"
                        :countText="headerCountText"
                        :countAtRight="true"
                        :hideSort="true"
                        :hidePagination="true"
                        :showBackButton="true"
                        :isLoading="isLoading"
                        :showEmptyMessage="!isLoading"
                        :forOffline="true"
                        :emptyIcon="'fluent:cloud-download-20-regular'"
                        :emptyMessage="'オフラインに保存された番組はありません'"
                        :emptySubMessage="'ビデオをみるページから、番組をオフラインに保存できます'"
                    />
                </div>
            </div>
        </main>
    </div>
</template>

<script setup lang="ts">

import { computed, onMounted, ref } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import RecordedProgramList from '@/components/Videos/RecordedProgramList.vue';
import useOfflineManagerStore from '@/stores/OfflineManagerStore';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils';

// Store
const userStore = useUserStore();
const offlineManagerStore = useOfflineManagerStore();

const isLoading = ref(true);

// オフライン番組一覧
const programs = computed(() => {
    return offlineManagerStore.offline_programs.map((offline_program) => offline_program.recorded_program);
});

// 合計件数
const totalPrograms = computed(() => programs.value.length);

// オフライン保存データの使用量（オフライン保存対象のみ）
const offlineUsageBytes = computed(() => {
    return offlineManagerStore.offline_programs
        .filter((offline_program) => offline_program.download_status !== 'Failed')
        .reduce((total_size, offline_program) => total_size + offline_program.total_size, 0);
});

// ヘッダーの件数/容量表示
const headerCountText = computed(() => {
    const usage_text = Utils.formatBytes(offlineUsageBytes.value, 2, true);
    if (offlineManagerStore.storage_estimate === null || offlineManagerStore.storage_estimate.quota <= 0) {
        return `${totalPrograms.value}件 ${usage_text}/--`;
    }
    const quota_text = Utils.formatBytes(offlineManagerStore.storage_estimate.quota, 0, true);
    return `${totalPrograms.value}件 ${usage_text}/${quota_text}`;
});

// 開始時に実行
onMounted(async () => {
    try {
        await userStore.fetchUser();
        await offlineManagerStore.initialize();
        await offlineManagerStore.refreshPrograms();
        await offlineManagerStore.refreshStorageEstimate();
    } catch (error) {
        console.error('Failed to initialize offline home:', error);
    } finally {
        isLoading.value = false;
    }
});

</script>

<style lang="scss" scoped>

.offline-home-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.offline-home-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    padding: 20px;
    margin: 0 auto;
    min-width: 0;
    max-width: 1000px;
    @include smartphone-horizontal {
        padding: 16px 20px !important;
    }
    @include smartphone-horizontal-short {
        padding: 16px 16px !important;
    }
    @include smartphone-vertical {
        padding: 16px 8px !important;
        padding-top: 8px !important;
    }
}

</style>
