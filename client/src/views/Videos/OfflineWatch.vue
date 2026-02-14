<template>
    <Watch :playback_mode="'Video'" />
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import type { NavigationGuardNext, RouteLocationNormalized } from 'vue-router';

import Watch from '@/components/Watch/Watch.vue';
import OfflinePlaybackManager from '@/services/player/managers/OfflinePlaybackManager';
import PlayerController from '@/services/player/PlayerController';
import useOfflineManagerStore from '@/stores/OfflineManagerStore';
import usePlayerStore from '@/stores/PlayerStore';
import useSettingsStore from '@/stores/SettingsStore';

export default defineComponent({
    name: 'Offline-Watch',
    components: {
        Watch,
    },
    data() {
        return {
            // PlayerController のインスタンス（コンポーネントインスタンスに紐づけて管理する）
            playerController: null as PlayerController | null,
        };
    },
    computed: {
        ...mapStores(useOfflineManagerStore, usePlayerStore, useSettingsStore),
    },
    // 開始時に実行
    created() {
        this.init();
    },
    // ルート変更時に実行（async で destroy → init の完了を待ってから next() を呼ぶ）
    async beforeRouteUpdate(to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) {
        try {
            await this.destroy();
            await this.init();
        } catch (error) {
            console.error('Failed to update route in OfflineWatch:', error);
        }
        next();
    },
    // 終了前に実行
    beforeUnmount() {
        this.destroy();
    },
    methods: {

        // オフライン再生セッションを初期化する
        async init() {
            if (this.$route.params.video_id === undefined) {
                this.$router.push({ path: '/not-found/' });
                return;
            }

            await this.offlineManagerStore.initialize();
            const video_id = Number(this.$route.params.video_id as string);
            const offline_program = this.offlineManagerStore.getProgramById(video_id);
            if (offline_program === null || offline_program.download_status !== 'Completed') {
                this.$router.push({ path: '/not-found/' });
                return;
            }

            // オフライン保存済みメタデータを PlayerStore に反映
            this.playerStore.recorded_program = offline_program.recorded_program;

            // PlayerController をオフラインモードで初期化
            const offline_playback_options = OfflinePlaybackManager.createOptions(video_id, offline_program.quality);
            this.playerController = new PlayerController('Video', {
                offline_playback: offline_playback_options,
            });
            await this.playerController.init();
        },

        // 再生セッションを破棄する
        async destroy() {
            if (this.playerController !== null) {
                await this.playerController.destroy();
                this.playerController = null;
            }
        },
    },
});

</script>
