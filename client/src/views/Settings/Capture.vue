<template>
    <!-- ベース画面の中にそれぞれの設定画面で異なる部分を記述する -->
    <SettingsBase>
        <h2 class="settings__heading">
            <a v-ripple class="settings__back-button" @click="$router.back()">
                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
            </a>
            <Icon icon="fluent:image-multiple-16-filled" width="26px" />
            <span class="ml-2">キャプチャ</span>
        </h2>
        <div class="settings__content">
            <div class="settings__item">
                <div class="settings__item-heading">キャプチャの保存先</div>
                <div class="settings__item-label">
                    <p>
                        [ブラウザでダウンロード] に設定すると、視聴中のデバイスのダウンロードフォルダに保存されます。<br>
                        視聴中のデバイスにそのまま保存されるためシンプルですが、保存先のフォルダを変更できないこと、iOS Safari (PWA モード) ではダウンロードするとファイル概要画面が表示されて視聴に支障することがデメリットです (将来的には、iOS / Android アプリ版や拡張機能などで解消される予定) 。<br>
                    </p>
                    <p>
                        [KonomiTV サーバーにアップロード] に設定すると、サーバー設定で指定されたキャプチャ保存フォルダに保存されます。視聴したデバイスにかかわらず、今までに撮ったキャプチャをひとつのフォルダにまとめて保存できます。<br>
                        他のデバイスでキャプチャを見るにはキャプチャ保存フォルダをネットワークに共有する必要があること、スマホ・タブレットではネットワーク上のフォルダへのアクセスがやや面倒なことがデメリットです。(将来的には、保存フォルダ内のキャプチャを Google フォトのように表示する機能を追加予定)<br>
                    </p>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="capture_save_mode" v-model="settingsStore.settings.capture_save_mode">
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">字幕表示時のキャプチャの保存モード</div>
                <div class="settings__item-label">
                    字幕表示時、キャプチャした画像に字幕を合成するかを設定します。<br>
                    映像のみのキャプチャと、字幕を合成したキャプチャを両方同時に保存することもできます。<br>
                    なお、字幕非表示時は、常に映像のみ (+コメント付きキャプチャではコメントを合成して) 保存されます。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="capture_caption_mode" v-model="settingsStore.settings.capture_caption_mode">
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">キャプチャの保存ファイル名パターン</div>
                <div class="settings__item-label">
                    キャプチャの保存ファイル名（拡張子なし）を設定します。デフォルトは Capture_%date%-%time% です。<br>
                    字幕を合成したキャプチャのファイル名には、自動的に _caption のサフィックスが追加されます。<br>
                    ファイル名には、下記の TVTest 互換マクロを使用できます。<br>
                    <v-btn class="settings__save-button mt-3 px-3 py-0" style="height: 36px; font-size: 14px;" variant="flat"
                        @click="is_macro_list_visible = !is_macro_list_visible">
                        <Icon :icon="is_macro_list_visible ? 'fluent:chevron-up-20-filled' : 'fluent:chevron-down-20-filled'"
                            class="mr-1" height="19px" />
                        {{ is_macro_list_visible ? 'マクロ一覧を非表示' : 'マクロ一覧を表示' }}
                    </v-btn>
                    <ul class="ml-4 mt-3" v-if="is_macro_list_visible">
                        <li>現在日時
                            <ul class="ml-4">
                                <li>%date%: 年月日 (YYYYMMDD)</li>
                                <li>%year%: 年 (YYYY)</li>
                                <li>%year2%: 年 (YY)</li>
                                <li>%month%: 月</li>
                                <li>%month2%: 月 (2桁)</li>
                                <li>%day%: 日</li>
                                <li>%day2%: 日 (2桁)</li>
                                <li>%time%: 時分秒 (時分秒 / HHMMSS)</li>
                                <li>%hour%: 時</li>
                                <li>%hour2%: 時 (2桁)</li>
                                <li>%minute%: 分</li>
                                <li>%minute2%: 分 (2桁)</li>
                                <li>%second%: 秒</li>
                                <li>%second2%: 秒 (2桁)</li>
                                <li>%day-of-week%: 曜日 (漢字)</li>
                            </ul>
                        </li>
                        <li>番組開始日時
                            <ul class="ml-4">
                                <li>%start-date%: 年月日 (YYYYMMDD)</li>
                                <li>%start-year%: 年 (YYYY)</li>
                                <li>%start-year2%: 年 (YY)</li>
                                <li>%start-month%: 月</li>
                                <li>%start-month2%: 月 (2桁)</li>
                                <li>%start-day%: 日</li>
                                <li>%start-day2%: 日 (2桁)</li>
                                <li>%start-time%: 時刻 (時分秒 / HHMMSS)</li>
                                <li>%start-hour%: 時</li>
                                <li>%start-hour2%: 時 (2桁)</li>
                                <li>%start-minute%: 分</li>
                                <li>%start-minute2%: 分 (2桁)</li>
                                <li>%start-second%: 秒</li>
                                <li>%start-second2%: 秒 (2桁)</li>
                                <li>%start-day-of-week%: 曜日 (漢字)</li>
                            </ul>
                        </li>
                        <li>番組終了日時
                            <ul class="ml-4">
                                <li>%end-date%: 年月日 (YYYYMMDD)</li>
                                <li>%end-year%: 年 (YYYY)</li>
                                <li>%end-year2%: 年 (YY)</li>
                                <li>%end-month%: 月</li>
                                <li>%end-month2%: 月 (2桁)</li>
                                <li>%end-day%: 日</li>
                                <li>%end-day2%: 日 (2桁)</li>
                                <li>%end-time%: 時分秒 (時分秒 / HHMMSS)</li>
                                <li>%end-hour%: 時</li>
                                <li>%end-hour2%: 時 (2桁)</li>
                                <li>%end-minute%: 分</li>
                                <li>%end-minute2%: 分 (2桁)</li>
                                <li>%end-second%: 秒</li>
                                <li>%end-second2%: 秒 (2桁)</li>
                                <li>%end-day-of-week%: 曜日 (漢字)</li>
                            </ul>
                        </li>
                        <li>番組長
                            <ul class="ml-4">
                                <li>%event-duration-hour%: 時間</li>
                                <li>%event-duration-hour2%: 時間 (2桁)</li>
                                <li>%event-duration-min%: 分</li>
                                <li>%event-duration-min2%: 分 (2桁)</li>
                                <li>%event-duration-sec%: 秒</li>
                                <li>%event-duration-sec2%: 秒 (2桁)</li>
                            </ul>
                        </li>
                        <li>%channel-name%: チャンネル名</li>
                        <li>%channel-no%: リモコン番号</li>
                        <li>%channel-no2%: リモコン番号 (2桁)</li>
                        <li>%channel-no3%: リモコン番号 (3桁)</li>
                        <li>%event-name%: 番組名</li>
                        <li>%event-id%: イベント ID</li>
                        <li>%service-name%: サービス名</li>
                        <li>%service-id%: サービス ID</li>
                    </ul>
                </div>
                <v-text-field class="settings__item-form mt-6" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :label="capture_filename_pattern_preview"
                    v-model="settingsStore.settings.capture_filename_pattern">
                </v-text-field>
            </div>
            <div class="settings__item settings__item--switch settings__item--sync-disabled">
                <label class="settings__item-heading" for="capture_copy_to_clipboard">キャプチャをクリップボードにコピーする</label>
                <label class="settings__item-label" for="capture_copy_to_clipboard">
                    この設定をオンにすると、撮ったキャプチャ画像がクリップボードにもコピーされます。<br>
                    クリップボードの履歴をサポートしていない環境では、この設定をオンにしてキャプチャを撮ると、以前のクリップボードが上書きされます。注意してください。<br>
                </label>
                <v-switch class="settings__item-switch" color="primary" id="capture_copy_to_clipboard" hide-details
                    v-model="settingsStore.settings.capture_copy_to_clipboard">
                </v-switch>
            </div>
        </div>
    </SettingsBase>
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import CaptureManager from '@/services/player/managers/CaptureManager';
import useSettingsStore from '@/stores/SettingsStore';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

export default defineComponent({
    name: 'Settings-Capture',
    components: {
        SettingsBase,
    },
    data() {
        return {

            // フォームを小さくするかどうか
            is_form_dense: Utils.isSmartphoneHorizontal(),

            // キャプチャの保存先の選択肢
            capture_save_mode: [
                {title: 'ブラウザでダウンロード', value: 'Browser'},
                {title: 'KonomiTV サーバーにアップロード', value: 'UploadServer'},
                {title: 'ブラウザでのダウンロードと、KonomiTV サーバーへのアップロードを両方行う', value: 'Both'},
            ],

            // 字幕が表示されているときのキャプチャの保存モードの選択肢
            capture_caption_mode: [
                {title: '映像のみのキャプチャを保存する', value: 'VideoOnly'},
                {title: '字幕を合成したキャプチャを保存する', value: 'CompositingCaption'},
                {title: '映像のみのキャプチャと、字幕を合成したキャプチャを両方保存する', value: 'Both'},
            ],

            // キャプチャの保存ファイル名パターンのプレビュー
            capture_filename_pattern_preview: '',

            // マクロ一覧を表示するか
            is_macro_list_visible: false,
        };
    },
    computed: {
        ...mapStores(useSettingsStore),
    },
    watch: {
        'settingsStore.settings.capture_filename_pattern': {
            handler() {
                this.capture_filename_pattern_preview = `プレビュー: ${CaptureManager.generateCaptureFilename()}.jpg`;
            },
            immediate: true,
        },
    }
});

</script>