<template>
    <SettingsBase>
        <h2 class="settings__heading">
            <a v-ripple class="settings__back-button" @click="$router.back()">
                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
            </a>
            <Icon icon="fluent:video-clip-wand-16-filled" width="19px" style="margin: 0 4px;" />
            <span class="ml-3">エンコード</span>
        </h2>
        <div class="settings__description">
            録画終了時の自動エンコードと録画一覧からの手動再エンコードの設定を行えます。<br>
            tsreplaceを使用してH.262-TSからH.264/HEVCへの映像変換を行い、ファイルサイズの削減と互換性の向上を図ります。
        </div>
        <div class="settings__content">
            <div class="settings__content-heading">
                <Icon icon="fluent:settings-16-filled" width="20px" />
                <span class="ml-3">自動エンコード設定</span>
            </div>
            <div class="settings__item settings__item--switch settings__item">
                <label class="settings__item-heading" for="tsreplace_auto_encoding_enabled">録画終了時に自動エンコードを実行する</label>
                <label class="settings__item-label" for="tsreplace_auto_encoding_enabled">
                    録画が完了した際に、自動的にH.264またはHEVCにエンコードします。<br>
                    手動でのエンコード作業を削減し、ストレージ効率を向上させることができます。
                </label>
                <v-switch class="settings__item-switch" color="primary" id="tsreplace_auto_encoding_enabled" hide-details
                    v-model="settingsStore.settings.tsreplace_auto_encoding_enabled">
                </v-switch>
            </div>
            <div class="settings__item" :class="{'settings__item--disabled': !settingsStore.settings.tsreplace_auto_encoding_enabled}">
                <div class="settings__item-heading">自動エンコードのコーデック</div>
                <div class="settings__item-label">
                    自動エンコード時に使用するコーデックを選択します。<br>
                    H.264は互換性が高く、HEVCはより高い圧縮効率を提供します。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="codec_options" v-model="settingsStore.settings.tsreplace_auto_encoding_codec"
                    :disabled="!settingsStore.settings.tsreplace_auto_encoding_enabled">
                </v-select>
            </div>
            <div class="settings__item" :class="{'settings__item--disabled': !settingsStore.settings.tsreplace_auto_encoding_enabled}">
                <div class="settings__item-heading">自動エンコードのエンコーダー</div>
                <div class="settings__item-label">
                    自動エンコード時に使用するエンコーダーを選択します。<br>
                    ハードウェアエンコードは高速ですが、利用可能な環境が限られます。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="encoder_options" v-model="settingsStore.settings.tsreplace_auto_encoding_encoder"
                    :disabled="!settingsStore.settings.tsreplace_auto_encoding_enabled">
                </v-select>
            </div>
            <div class="settings__item" :class="{'settings__item--disabled': !settingsStore.settings.tsreplace_auto_encoding_enabled}">
                <div class="settings__item-heading">エンコード品質プリセット</div>
                <div class="settings__item-label">
                    エンコード時の品質プリセットを選択します。<br>
                    高品質ほどファイルサイズが大きくなり、エンコード時間も長くなります。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="quality_preset_options" v-model="settingsStore.settings.tsreplace_encoding_quality_preset"
                    :disabled="!settingsStore.settings.tsreplace_auto_encoding_enabled">
                </v-select>
            </div>
            <div class="settings__item settings__item--switch settings__item" :class="{'settings__item--disabled': !settingsStore.settings.tsreplace_auto_encoding_enabled}">
                <label class="settings__item-heading" for="tsreplace_delete_original_after_encoding">エンコード後に元ファイルを削除する</label>
                <label class="settings__item-label" for="tsreplace_delete_original_after_encoding">
                    エンコードが完了した後、元のH.262-TSファイルを自動的に削除します。<br>
                    ストレージ容量を節約できますが、元ファイルは復元できなくなります。
                </label>
                <v-switch class="settings__item-switch" color="primary" id="tsreplace_delete_original_after_encoding" hide-details
                    v-model="settingsStore.settings.tsreplace_delete_original_after_encoding"
                    :disabled="!settingsStore.settings.tsreplace_auto_encoding_enabled">
                </v-switch>
            </div>
            <v-divider class="mt-6"></v-divider>
            <div class="settings__content-heading">
                <Icon icon="fluent:wrench-16-filled" width="20px" />
                <span class="ml-3">エンコード処理設定</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">最大同時エンコード数</div>
                <div class="settings__item-label">
                    同時に実行できるエンコード処理の最大数を設定します。<br>
                    値を大きくするとより多くのファイルを並行処理できますが、システムリソースを多く消費します。
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    type="number" min="1" max="10"
                    :rules="[validateMaxConcurrentEncodings]"
                    v-model.number="settingsStore.settings.tsreplace_max_concurrent_encodings">
                </v-text-field>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">ハードウェアエンコーダーの利用可否</div>
                <div class="settings__item-label">
                    現在の環境でハードウェアエンコーダーが利用可能かどうかを表示します。<br>
                    この値はサーバー起動時に自動検出されます。
                </div>
                <v-chip class="mt-2" :color="settingsStore.settings.tsreplace_hardware_encoder_available ? 'success' : 'error'" variant="flat">
                    <Icon :icon="settingsStore.settings.tsreplace_hardware_encoder_available ? 'fluent:checkmark-16-filled' : 'fluent:dismiss-16-filled'" width="16px" />
                    <span class="ml-2">{{ settingsStore.settings.tsreplace_hardware_encoder_available ? '利用可能' : '利用不可' }}</span>
                </v-chip>
            </div>
            <v-divider class="mt-6"></v-divider>
            <div class="settings__quote mt-4">
                <p>
                    <strong>注意事項:</strong><br>
                    • エンコード処理は録画ファイルのサイズや品質設定によって長時間かかる場合があります。<br>
                    • ハードウェアエンコードを使用する場合は、対応するGPUまたはCPUが必要です。<br>
                    • 元ファイルの削除設定は慎重に行ってください。削除されたファイルは復元できません。
                </p>
            </div>
        </div>
    </SettingsBase>
</template>
<script lang="ts" setup>

import { computed, onMounted } from 'vue';

import SettingsBase from '@/views/Settings/Base.vue';
import useSettingsStore from '@/stores/SettingsStore';
import Settings from '@/services/Settings';
import Utils from '@/utils';

// ストア
const settingsStore = useSettingsStore();

// フォームの密度 (スマホ横画面では compact にする)
const is_form_dense = computed(() => Utils.isSmartphoneHorizontal());

// コーデック選択肢
const codec_options = [
    { title: 'H.264 (AVC)', value: 'h264' },
    { title: 'H.265 (HEVC)', value: 'hevc' },
];

// エンコーダー選択肢
const encoder_options = computed(() => {
    const options = [
        { title: 'ソフトウェアエンコード (FFmpeg)', value: 'software' },
    ];

    // ハードウェアエンコーダーが利用可能な場合のみ追加
    if (settingsStore.settings.tsreplace_hardware_encoder_available) {
        options.push({ title: 'ハードウェアエンコード', value: 'hardware' });
    }

    return options;
});

// 品質プリセット選択肢
const quality_preset_options = [
    { title: '高速 (fast)', value: 'fast' },
    { title: '標準 (medium)', value: 'medium' },
    { title: '高品質 (slow)', value: 'slow' },
];

// バリデーション関数
const validateMaxConcurrentEncodings = (value: number) => {
    if (!value || value < 1 || value > 10) {
        return '1から10の間の数値を入力してください';
    }
    return true;
};

// コンポーネントマウント時にサーバー設定を取得してハードウェアエンコーダーの利用可否を更新
onMounted(async () => {
    try {
        const serverSettings = await Settings.fetchServerSettings();
        if (serverSettings && serverSettings.tsreplace_encoding) {
            settingsStore.settings.tsreplace_hardware_encoder_available =
                serverSettings.tsreplace_encoding.hardware_encoder_available;
        }
    } catch (error) {
        console.error('Failed to fetch server settings:', error);
    }
});

</script>
