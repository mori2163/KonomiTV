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
            TSReplaceを使用してH.262-TSからH.264/HEVCへの映像変換を行い、ファイルサイズの削減と互換性の向上を図ります。
        </div>
        <div class="settings__description">
            サーバー設定を変更するには、管理者アカウントでログインしている必要があります。<br>
        </div>
        <div class="settings__description mt-1">
            [サーバー設定を更新] ボタンを押さずにこのページから離れると、変更内容は破棄されます。<br>
            変更を反映するには KonomiTV サーバーの再起動が必要です。<br>
        </div>

        <!-- 基本エンコード設定 -->
        <div class="settings__content" v-if="server_settings">
            <div class="settings__content-heading">
                <Icon icon="fluent:settings-16-filled" width="20px" />
                <span class="ml-3">基本設定</span>
            </div>
            <div class="settings__item settings__item--switch">
                <label class="settings__item-heading" for="auto_encoding">自動エンコード</label>
                <label class="settings__item-label" for="auto_encoding">
                    録画終了時に自動的にエンコードを行います。<br>
                </label>
                <v-switch class="settings__item-switch" color="primary" id="auto_encoding" hide-details
                    v-model="server_settings.tsreplace_encoding.auto_encoding_enabled">
                </v-switch>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">エンコードコーデック</div>
                <div class="settings__item-label">
                    エンコードに使用するビデオコーデックを選択します。<br>
                    H.264は高い互換性、H.265(HEVC)はより高い圧縮効率を提供しますが処理時間が長くなります。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined"
                    :items="[
                        { title: 'H.264 (AVC)', value: 'h264' },
                        { title: 'H.265 (HEVC)', value: 'hevc' }
                    ]"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.auto_encoding_codec"
                    :disabled="is_auto_encoding_disabled"
                    hide-details>
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">エンコーダー種類</div>
                <div class="settings__item-label">
                    ソフトウェアエンコードは高品質、ハードウェアエンコードは高速処理が可能です。<br>
                    ハードウェアエンコードを使用する場合は、対応するGPUが必要です。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined"
                    :items="encoder_options"
                    v-model="server_settings.tsreplace_encoding.auto_encoding_encoder"
                    :density="is_form_dense ? 'compact' : 'default'"
                    :disabled="is_auto_encoding_disabled"
                    hide-details
                    item-title="title"
                    item-value="value"
                    item-key="key">
                    <template v-slot:item="{ props, item }">
                        <v-list-item v-bind="props"
                            :disabled="item.raw.disabled"
                            :subtitle="item.raw.subtitle">
                        </v-list-item>
                    </template>
                </v-select>
            </div>
            <div class="settings__item" v-show="server_settings.tsreplace_encoding.auto_encoding_encoder === 'hardware'">
                <div class="settings__item-heading">ハードウェアエンコーダー種類</div>
                <div class="settings__item-label">
                    使用するGPUエンコーダーの種類を選択します。<br>
                    お使いのGPUに対応したエンコーダーを選択してください。
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined"
                    :items="[
                        { title: 'NVEncC : NVIDIA GPU で利用可能', value: 'nvidia' },
                        { title: 'VCEEncC : AMD GPU で利用可能', value: 'amd' },
                        { title: 'QSVEncC : Intel Graphics 搭載 CPU / Intel Arc GPU で利用可能', value: 'intel' }
                    ]"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.hardware_encoder_type"
                    :disabled="is_auto_encoding_disabled"
                    hide-details>
                </v-select>
            </div>
                <div class="settings__item settings__item--switch">
                <label class="settings__item-heading">エンコード完了後に元ファイルを削除</label>
                <label class="settings__item-label" for="delete_original_after_encoding">
                    エンコード完了後に元のTSファイルを自動的に削除します。<br>
                    ストレージ容量の節約になりますが、元ファイルは復元できないため注意してください。
                </label>
                <v-switch class="settings__item-switch" color="primary" id="delete_original_after_encoding" hide-details
                    v-model="server_settings.tsreplace_encoding.delete_original_after_encoding"
                    :disabled="is_auto_encoding_disabled">
                </v-switch>
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
                    v-model.number="server_settings.tsreplace_encoding.max_concurrent_encodings"
                    :disabled="is_auto_encoding_disabled">
                </v-text-field>
            </div>

            <v-btn class="settings__save-button bg-secondary mt-6" variant="flat" @click="updateServerSettings()">
                <Icon icon="fluent:save-16-filled" class="mr-2" height="23px" />エンコード設定を更新
            </v-btn>

            <!-- コマンドラインオプション設定 -->
             <div class="settings__content-heading mt-6">
                <Icon icon="fluent:developer-board-16-filled" width="20px" />
                <span class="ml-2">コマンドラインオプション</span>
            </div>
            <div class="settings__description">
                高度なエンコーディング設定です。よくわからない場合はそのままにしてください。<br>
            </div>
            <!-- ソフトウェアエンコード設定 -->
            <div class="settings__item">
                <div class="settings__item-heading">
                    ソフトウェアエンコード (CPU) H.264 オプション
                    <v-chip size="small" color="blue-darken-1" variant="outlined" class="ml-2">
                        <span>libx264</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    TSReplace経由でFFmpegのlibx264エンコーダーを使用します。高い互換性を持ちます。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.ffmpeg_h264_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <div class="settings__item">
                <div class="settings__item-heading">
                    ソフトウェアエンコード (CPU) H.265 オプション
                    <v-chip size="small" color="purple-darken-1" variant="outlined" class="ml-2">
                        <span>libx265</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    TSReplace経由でFFmpegのlibx265エンコーダーを使用します。H.264より高い圧縮効率を持ちますが、エンコード時間が長くなります。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.ffmpeg_hevc_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <!-- ハードウェアエンコード設定 (NVIDIA) -->
            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'nvidia'">
                <div class="settings__item-heading">
                    NVIDIA GPU H.264 エンコードオプション
                    <v-chip size="small" color="green-darken-1" variant="outlined" class="ml-2">
                        <span>NVEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    NVIDIA GPU使用時のH.264エンコード設定です（NVEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.nvidia_h264_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'nvidia'">
                <div class="settings__item-heading">
                    NVIDIA GPU H.265 エンコードオプション
                    <v-chip size="small" color="green-darken-2" variant="outlined" class="ml-2">
                        <span>NVEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    NVIDIA GPU使用時のH.265エンコード設定です（NVEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.nvidia_hevc_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <!-- ハードウェアエンコード設定 (AMD) -->
            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'amd'">
                <div class="settings__item-heading">
                    AMD GPU H.264 エンコードオプション
                    <v-chip size="small" color="red-darken-1" variant="outlined" class="ml-2">
                        <span>VCEEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    AMD GPU使用時のH.264エンコード設定です（VCEEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.amd_h264_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'amd'">
                <div class="settings__item-heading">
                    AMD GPU H.265 エンコードオプション
                    <v-chip size="small" color="red-darken-2" variant="outlined" class="ml-2">
                        <span>VCEEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    AMD GPU使用時のH.265エンコード設定です（VCEEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.amd_hevc_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <!-- ハードウェアエンコード設定 (Intel) -->
            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'intel'">
                <div class="settings__item-heading">
                    Intel GPU H.264 エンコードオプション
                    <v-chip size="small" color="blue-darken-1" variant="outlined" class="ml-2">
                        <span>QSVEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    Intel GPU使用時のH.264エンコード設定です（QSVEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.intel_h264_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>

            <div class="settings__item" v-show="server_settings.tsreplace_encoding.hardware_encoder_type === 'intel'">
                <div class="settings__item-heading">
                    Intel GPU H.265 エンコードオプション
                    <v-chip size="small" color="blue-darken-2" variant="outlined" class="ml-2">
                        <span>QSVEncC</span>
                    </v-chip>
                </div>
                <div class="settings__item-label">
                    Intel GPU使用時のH.265エンコード設定です（QSVEncC経由）。<br>
                    <span v-if="is_auto_encoding_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定は自動エンコードが有効な場合のみ変更可能です。</strong></span>
                    <span v-else-if="is_disabled" class="text-orange-500 d-block mt-1"><strong>※ この設定の変更には管理者権限が必要です。</strong></span>
                </div>
                <v-text-field
                    class="settings__item-form"
                    color="primary"
                    variant="outlined"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tsreplace_encoding.intel_hevc_options"
                    prepend-inner-icon="fluent:code-16-filled"
                    hide-details>
                </v-text-field>
            </div>
        </div>
    </SettingsBase>
</template>

<script setup lang="ts">

import { computed, ref, onMounted } from 'vue';

import Message from '@/message';
import Settings from '@/services/Settings';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils/Utils';
import SettingsBase from '@/views/Settings/Base.vue';

// ストア
const userStore = useUserStore();

// サーバー設定を ref として保持（初期値をnullに設定）
const server_settings = ref<any>(null);

// ハードウェアエンコーダーの利用可否
const hardware_encoder_available = ref<boolean>(false);

// サーバー設定をロード
async function loadServerSettings() {
    const settings = await Settings.fetchServerSettings();
    server_settings.value = settings;
}

// ハードウェアエンコーダーの利用可否を確認
async function checkHardwareEncoderAvailability() {
    try {
        const status = await Settings.fetchHardwareEncoderStatus();
        hardware_encoder_available.value = status.hardware_encoder_available;
    } catch (error) {
        console.error('Failed to check hardware encoder availability:', error);
        hardware_encoder_available.value = false;
    }
}

// エンコーダー選択肢（ハードウェアエンコーダーの利用可否によって動的に変更）
const encoder_options = computed(() => {
    if (hardware_encoder_available.value) {
        return [
            { title: 'ソフトウェア (CPU)', value: 'software', disabled: false, key: 'software' },
            { title: 'ハードウェア (GPU)', value: 'hardware', disabled: false, key: 'hardware' }
        ];
    } else {
        return [
            { title: 'ソフトウェア (CPU)', value: 'software', disabled: false, key: 'software' },
            {
                title: 'ハードウェア (GPU)',
                value: 'hardware',
                disabled: true,
                subtitle: '使用できません（対応するGPUが検出されませんでした）',
                key: 'hardware-disabled'
            }
        ];
    }
});// フォームのサイズ
const is_form_dense = computed(() => Utils.isSmartphoneHorizontal());

// 現在のユーザーが管理者かどうか（管理者のみコマンドラインオプションを変更可能）
const is_disabled = computed(() => userStore.user === null || userStore.user.is_admin === false);

// 自動エンコードが無効かどうか
const is_auto_encoding_disabled = computed(() =>
    !server_settings.value?.tsreplace_encoding?.auto_encoding_enabled || is_disabled.value
);

// バリデーション
function validateMaxConcurrentEncodings(value: number): boolean | string {
    if (value < 1 || value > 10) {
        return '1以上10以下の値を入力してください。';
    }
    return true;
}

// サーバー設定を更新する関数
async function updateServerSettings() {
    if (server_settings.value === null) return;

    // ハードウェアエンコーダーが利用できない場合で、ハードウェアが選択されている場合はソフトウェアに切り替え
    if (!hardware_encoder_available.value && server_settings.value.tsreplace_encoding.auto_encoding_encoder === 'hardware') {
        server_settings.value.tsreplace_encoding.auto_encoding_encoder = 'software';
        Message.warning('ハードウェアエンコーダーが利用できないため、ソフトウェアエンコードに切り替えました。');
    }

    // サーバー設定を更新
    const result = await Settings.updateServerSettings(server_settings.value);

    // 成功した場合のみメッセージを表示
    // エラー処理は Services 層で行われるため、ここではエラー処理は不要
    // 再起動するまでは設定データは反映されないため、再起動せずにページをリロードすると反映されてないように見える点に注意
    if (result === true) {
        Message.success('エンコード設定を更新しました。\n変更を反映するためには、KonomiTV サーバーを再起動してください。');
    }
}

// コンポーネントマウント時に設定をロード
onMounted(async () => {
    await Promise.all([
        loadServerSettings(),
        checkHardwareEncoderAvailability()
    ]);
});

</script>

<style scoped>
/* 特別なスタイルは不要 - KonomiTVの標準設定スタイルを使用 */
</style>