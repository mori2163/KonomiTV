<template>
    <!-- ベース画面の中にそれぞれの設定画面で異なる部分を記述する -->
    <SettingsBase>
        <h2 class="settings__heading">
            <a v-ripple class="settings__back-button" @click="$router.back()">
                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
            </a>
            <Icon icon="fluent:server-surface-16-filled" width="22px" />
            <span class="ml-2">サーバー設定</span>
        </h2>
        <div class="settings__description">
            サーバー設定を変更するには、管理者アカウントでログインしている必要があります。<br>
        </div>
        <div class="settings__description mt-1">
            [サーバー設定を更新] ボタンを押さずにこのページから離れると、変更内容は破棄されます。<br>
            変更を反映するには KonomiTV サーバーの再起動が必要です。<br>
        </div>
        <div class="settings__content" :class="{'settings__content--disabled': is_disabled}">
            <div class="settings__content-heading">
                <Icon icon="fa-solid:sliders-h" width="22px" style="padding: 0 3px;" />
                <span class="ml-2">全般</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">利用するバックエンド</div>
                <div class="settings__item-label">
                    EDCB・Mirakurun のいずれかを選択してください。<br>
                    バックエンドに EDCB が選択されているときは、レコーダーも EDCB に固定されます。<br>
                    バックエンドに Mirakurun が選択されているときは、レコーダーに EPGStation または EDCB を選択できます。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="['EDCB', 'Mirakurun']" v-model="server_settings.general.backend">
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">利用する録画管理ソフト (レコーダー)</div>
                <div class="settings__item-label">
                    バックエンドが Mirakurun の場合のみ変更できます。<br>
                    EPGStation・EDCB のいずれかを選択してください。<br>
                    録画予約および自動録画予約条件の管理に利用されます。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="['EPGStation', 'EDCB']"
                    :disabled="server_settings.general.backend !== 'Mirakurun'"
                    v-model="server_settings.general.recorder">
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">EDCB (EpgTimerNW) の TCP API の URL</div>
                <div class="settings__item-label">
                    バックエンドまたはレコーダーに EDCB が選択されているときに利用されます。<br>
                    tcp://edcb-namedpipe/ と指定すると、TCP API の代わりに名前付きパイプを使って通信します (ローカルのみ)。<br>
                </div>
                <div class="settings__item-label mt-1">
                    一部 Windows 環境では localhost の名前解決が遅いため、ストリーミング開始までの待機時間が長くなる場合があります。
                    EDCB と同じ PC に KonomiTV をインストールしている場合、localhost ではなく 127.0.0.1 の利用を推奨します。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.general.edcb_url">
                </v-text-field>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">Mirakurun / mirakc の HTTP API の URL</div>
                <div class="settings__item-label">
                    バックエンドに Mirakurun が選択されているときに利用されます。<br>
                </div>
                <div class="settings__item-label mt-1">
                    一部 Windows 環境では localhost の名前解決が遅いため、ストリーミング開始までの待機時間が長くなる場合があります。
                    Mirakurun / mirakc と同じ PC に KonomiTV をインストールしている場合、localhost ではなく 127.0.0.1 の利用を推奨します。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.general.mirakurun_url">
                </v-text-field>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">EPGStation の HTTP API の URL</div>
                <div class="settings__item-label">
                    レコーダーに EPGStation が選択されているときに利用されます。<br>
                </div>
                <div class="settings__item-label mt-1">
                    一部 Windows 環境では localhost の名前解決が遅いため、リクエストの待機時間が長くなる場合があります。
                    EPGStation と同じ PC に KonomiTV をインストールしている場合、localhost ではなく 127.0.0.1 の利用を推奨します。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.general.epgstation_url">
                </v-text-field>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">利用するエンコーダー</div>
                <div class="settings__item-label">
                    FFmpeg はソフトウェアエンコーダーです。<br>
                    すべての PC で利用できますが、CPU に多大な負荷がかかり、パフォーマンスが悪いです。<br>
                </div>
                <div class="settings__item-label mt-1">
                    QSVEncC・NVEncC・VCEEncC・rkmppenc はハードウェアエンコーダーです。<br>
                    CPU 負荷が低く、パフォーマンスがとても高いです（おすすめ）。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="[
                        {title: 'FFmpeg : ソフトウェアエンコーダー', value: 'FFmpeg'},
                        {title: 'QSVEncC : Intel Graphics 搭載 CPU / Intel Arc GPU で利用可能', value: 'QSVEncC'},
                        {title: 'NVEncC : NVIDIA GPU で利用可能', value: 'NVEncC'},
                        {title: 'VCEEncC : AMD GPU で利用可能', value: 'VCEEncC'},
                        {title: 'rkmppenc : Rockchip RK3588 系 SoC 搭載 SBC で利用可能', value: 'rkmppenc'}
                    ]"
                    v-model="server_settings.general.encoder">
                </v-select>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">番組情報の更新間隔 (分)</div>
                <div class="settings__item-label">
                    番組情報を EDCB または Mirakurun / mirakc から取得する間隔を設定します。デフォルトは 5 (分) です。<br>
                </div>
                <v-slider class="settings__item-form" color="primary" show-ticks="always" thumb-label hide-details
                    :min="0.5" :max="60" :step="0.5"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.general.program_update_interval">
                </v-slider>
            </div>
            <div class="settings__item settings__item--switch">
                <label class="settings__item-heading" for="debug">デバッグモードを有効にする</label>
                <label class="settings__item-label" for="debug">
                    有効にすると、デバッグログも出力されるようになります。<br>
                </label>
                <v-switch class="settings__item-switch" color="primary" id="debug" hide-details
                    v-model="server_settings.general.debug">
                </v-switch>
            </div>
            <div class="settings__item settings__item--switch">
                <label class="settings__item-heading" for="debug_encoder">エンコーダーのログを有効にする</label>
                <label class="settings__item-label" for="debug_encoder">
                    有効にすると、ライブ視聴時のエンコーダーのログが server/logs/ 以下に保存されます。
                    さらにデバッグモードが有効のときは、デバッグログとしてリアルタイムにエンコーダーのログが出力されます。<br>
                </label>
                <v-switch class="settings__item-switch" color="primary" id="debug_encoder" hide-details
                    v-model="server_settings.general.debug_encoder">
                </v-switch>
            </div>
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:server-surface-16-filled" width="22px" />
                <span class="ml-2">サーバー</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">KonomiTV サーバーのリッスンポート</div>
                <div class="settings__item-label">
                    デフォルトのリッスンポートは 7000 です。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.server.port">
                </v-text-field>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">HTTPS リバースプロキシのカスタム HTTPS 証明書/秘密鍵ファイルへの絶対パス</div>
                <div class="settings__item-label">
                    設定すると、カスタム HTTPS 証明書を使って HTTPS リバースプロキシを開始します。<br>
                    カスタム HTTPS 証明書を有効化すると、https://192-168-x-xx.local.konomi.tv:7000/ の URL では KonomiTV にアクセスできなくなります。<br>
                    基本空欄のままで問題ありません。HTTPS 証明書について詳細に理解している方のみ設定してください。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    label="例: C:\path\to\cert.pem"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.server.custom_https_certificate">
                </v-text-field>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    label="例: C:\path\to\key.pem"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.server.custom_https_private_key">
                </v-text-field>
            </div>
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:tv-20-filled" width="22px" />
                <span class="ml-2">テレビのライブストリーミング</span>
            </div>
            <div class="settings__item settings__item--switch">
                <label class="settings__item-heading" for="always_receive_tv_from_mirakurun">常に Mirakurun / mirakc から放送波を受信する</label>
                <label class="settings__item-label" for="always_receive_tv_from_mirakurun">
                    利用するバックエンドが EDCB のとき、常に Mirakurun / mirakc から放送波を受信するかを設定します。
                    バックエンドに Mirakurun が選択されているときは効果がありません。<br>
                </label>
                <label class="settings__item-label mt-1" for="always_receive_tv_from_mirakurun">
                    KonomiTV から EDCB と Mirakurun / mirakc 両方にアクセスできる必要があります。<br>
                    EDCB はチューナー起動やチャンネル切り替えに時間がかかるため、Mirakurun / mirakc が利用できる環境であれば、この設定を有効にするとより快適に使えます。<br>
                </label>
                <v-switch class="settings__item-switch" color="primary" id="always_receive_tv_from_mirakurun" hide-details
                    v-model="server_settings.general.always_receive_tv_from_mirakurun">
                </v-switch>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">誰も見ていないチャンネルのエンコードタスクを維持する秒数</div>
                <div class="settings__item-label">
                    10 秒に設定したなら、10 秒間誰も見ていない状態が継続したらエンコードタスク（エンコーダー）を終了します。<br>
                    0 秒に設定すると、ネット回線が瞬断したりリロードしただけでチューナーとエンコーダーの再起動が必要になり、再生復帰までに時間がかかります。余裕をもたせておく事をおすすめします。<br>
                </div>
                <v-slider class="settings__item-form" color="primary" show-ticks="always" thumb-label hide-details
                    :min="0" :max="60" :step="1"
                    :density="is_form_dense ? 'compact' : 'default'"
                    v-model="server_settings.tv.max_alive_time">
                </v-slider>
            </div>
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:movies-and-tv-20-filled" width="22px" />
                <span class="ml-2">ビデオのオンデマンドストリーミング</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">録画済み番組の保存先フォルダの絶対パス</div>
                <div class="settings__item-label" style="padding-bottom: 2px;">
                    指定フォルダ以下に保存されている MPEG-TS 形式の録画ファイルを KonomiTV サーバーが自動的に見つけ出し、メタデータの解析とサムネイルの作成を行います。<br>
                    解析が完了すると、録画番組一覧から再生できるようになります。<br>
                </div>
                <div class="settings__item-label mt-1" style="padding-bottom: 2px;">
                    複数の保存先フォルダを指定できます。シンボリックリンクには対応していません。<br>
                </div>
                <div v-for="(folder, index) in server_settings.video.recorded_folders" :key="'recorded-folder-' + index">
                    <div class="d-flex align-center mt-3">
                        <v-text-field class="settings__item-form mt-0" color="primary" variant="outlined" hide-details
                            placeholder="例: E:\TV-Record"
                            :density="is_form_dense ? 'compact' : 'default'"
                            v-model="server_settings.video.recorded_folders[index]">
                        </v-text-field>
                        <button v-ripple class="settings__item-delete-button"
                            @click="server_settings.video.recorded_folders.splice(index, 1)">
                            <svg class="iconify iconify--fluent" width="20px" height="20px" viewBox="0 0 16 16">
                                <path fill="currentColor" d="M7 3h2a1 1 0 0 0-2 0ZM6 3a2 2 0 1 1 4 0h4a.5.5 0 0 1 0 1h-.564l-1.205 8.838A2.5 2.5 0 0 1 9.754 15H6.246a2.5 2.5 0 0 1-2.477-2.162L2.564 4H2a.5.5 0 0 1 0-1h4Zm1 3.5a.5.5 0 0 0-1 0v5a.5.5 0 0 0 1 0v-5ZM9.5 6a.5.5 0 0 0-.5.5v5a.5.5 0 0 0 1 0v-5a.5.5 0 0 0-.5-.5Z"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <v-btn class="mt-3" color="background-lighten-2" variant="flat" height="40px"
                    @click="server_settings.video.recorded_folders.push('')">
                    <Icon icon="fluent:add-12-filled" height="17px" />
                    <span class="ml-1">保存先フォルダを追加</span>
                </v-btn>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">ストレージ使用状況</div>
                <div class="settings__item-label">
                    録画フォルダが配置されているドライブのストレージ使用状況です。<br>
                    録画可能時間は、平均ビットレート 18Mbps を基に計算されています。<br>
                </div>
                <div v-if="storage_info.length === 0" class="storage-info-empty mt-3">
                    <Icon icon="fluent:hard-drive-call-20-regular" width="48px" height="48px" />
                    <div class="storage-info-empty__text">録画フォルダが設定されていません</div>
                    <div class="storage-info-empty__subtext">上の設定で録画フォルダを追加してください</div>
                </div>
                <div v-for="(info, index) in storage_info" :key="'storage-info-' + index" class="storage-card mt-4">
                    <div class="storage-card__header">
                        <div class="storage-card__drive">
                            <Icon icon="fluent:hard-drive-20-filled" width="24px" height="24px" />
                            <span class="storage-card__drive-name">{{ info.drive_root }}</span>
                        </div>
                        <div class="storage-card__usage-badge"
                            :class="{
                                'storage-card__usage-badge--critical': info.usage_percent > 90,
                                'storage-card__usage-badge--warning': info.usage_percent > 75 && info.usage_percent <= 90,
                                'storage-card__usage-badge--normal': info.usage_percent <= 75
                            }">
                            {{ info.usage_percent.toFixed(1) }}% 使用中
                        </div>
                    </div>

                    <div class="storage-card__progress">
                        <div class="storage-card__progress-bar-container"
                            role="progressbar"
                            :aria-valuenow="Math.min(info.usage_percent, 100)"
                            aria-valuemin="0"
                            aria-valuemax="100"
                            :aria-label="`ストレージ使用率: ${info.usage_percent.toFixed(1)}%`">
                            <div class="storage-card__progress-bar"
                                :style="{ width: Math.min(info.usage_percent, 100) + '%' }"
                                :class="{
                                    'storage-card__progress-bar--critical': info.usage_percent > 90,
                                    'storage-card__progress-bar--warning': info.usage_percent > 75 && info.usage_percent <= 90,
                                    'storage-card__progress-bar--normal': info.usage_percent <= 75
                                }">
                            </div>
                        </div>
                    </div>

                    <div class="storage-card__stats">
                        <div class="storage-card__stat">
                            <Icon icon="fluent:database-20-regular" width="20px" class="storage-card__stat-icon" />
                            <div class="storage-card__stat-content">
                                <div class="storage-card__stat-label">合計容量</div>
                                <div class="storage-card__stat-value">{{ formatBytes(info.total_bytes) }}</div>
                            </div>
                        </div>
                        <div class="storage-card__stat">
                            <Icon icon="fluent:arrow-upload-20-regular" width="20px" class="storage-card__stat-icon storage-card__stat-icon--used" />
                            <div class="storage-card__stat-content">
                                <div class="storage-card__stat-label">使用中</div>
                                <div class="storage-card__stat-value storage-card__stat-value--used">{{ formatBytes(info.used_bytes) }}</div>
                            </div>
                        </div>
                        <div class="storage-card__stat">
                            <Icon icon="fluent:arrow-download-20-regular" width="20px" class="storage-card__stat-icon storage-card__stat-icon--free" />
                            <div class="storage-card__stat-content">
                                <div class="storage-card__stat-label">空き容量</div>
                                <div class="storage-card__stat-value storage-card__stat-value--free">{{ formatBytes(info.free_bytes) }}</div>
                            </div>
                        </div>
                        <div class="storage-card__stat storage-card__stat--highlight">
                            <Icon icon="fluent:clock-20-regular" width="20px" class="storage-card__stat-icon storage-card__stat-icon--time" />
                            <div class="storage-card__stat-content">
                                <div class="storage-card__stat-label">録画可能時間</div>
                                <div class="storage-card__stat-value storage-card__stat-value--time">約 {{ formatRecordingHours(info.available_recording_hours) }}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:image-multiple-16-filled" width="22px" />
                <span class="ml-2">キャプチャ</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">アップロードしたキャプチャ画像の保存先フォルダの絶対パス</div>
                <div class="settings__item-label">
                    クライアントの [キャプチャの保存先] 設定で [KonomiTV サーバーにアップロード] または
                    [ブラウザでのダウンロードと、KonomiTV サーバーへのアップロードを両方行う] が選択されているときに利用されます。<br>
                </div>
                <div class="settings__item-label mt-1" style="padding-bottom: 2px;">
                    複数の保存先フォルダを指定できます。先頭から順に利用され、保存先フォルダがいっぱいになったら次の保存先フォルダに保存されます。<br>
                </div>
                <div v-for="(folder, index) in server_settings.capture.upload_folders" :key="'upload-folder-' + index">
                    <div class="d-flex align-center mt-3">
                        <v-text-field class="settings__item-form mt-0" color="primary" variant="outlined" hide-details
                            placeholder="例: E:\TV-Capture"
                            :density="is_form_dense ? 'compact' : 'default'"
                            v-model="server_settings.capture.upload_folders[index]">
                        </v-text-field>
                        <button v-ripple class="settings__item-delete-button"
                            @click="server_settings.capture.upload_folders.splice(index, 1)">
                            <svg class="iconify iconify--fluent" width="20px" height="20px" viewBox="0 0 16 16">
                                <path fill="currentColor" d="M7 3h2a1 1 0 0 0-2 0ZM6 3a2 2 0 1 1 4 0h4a.5.5 0 0 1 0 1h-.564l-1.205 8.838A2.5 2.5 0 0 1 9.754 15H6.246a2.5 2.5 0 0 1-2.477-2.162L2.564 4H2a.5.5 0 0 1 0-1h4Zm1 3.5a.5.5 0 0 0-1 0v5a.5.5 0 0 0 1 0v-5ZM9.5 6a.5.5 0 0 0-.5.5v5a.5.5 0 0 0 1 0v-5a.5.5 0 0 0-.5-.5Z"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <v-btn class="mt-3" color="background-lighten-2" variant="flat" height="40px"
                    @click="server_settings.capture.upload_folders.push('')">
                    <Icon icon="fluent:add-12-filled" height="17px" />
                    <span class="ml-1">保存先フォルダを追加</span>
                </v-btn>
            </div>
            <v-btn class="settings__save-button bg-secondary mt-6" variant="flat" @click="updateServerSettings()">
                <Icon icon="fluent:save-16-filled" class="mr-2" height="23px" />サーバー設定を更新
            </v-btn>
            <div class="settings__content-heading mt-8">
                <Icon icon="fluent:person-board-20-filled" width="22px" />
                <span class="ml-2">アカウント</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">アカウントの管理</div>
                <div class="settings__item-label">
                    現在 KonomiTV に登録されているすべてのアカウントの一覧の確認、管理者権限の付与/剥奪、アカウントの削除ができます。<br>
                </div>
                <div class="settings__item-label mt-1">
                    ログイン中ユーザーの設定変更は、別途 <router-link class="link" to="/settings/account">アカウント設定画面</router-link> から行ってください。<br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-4" variant="flat" @click="account_manage_settings_modal = !account_manage_settings_modal">
                <Icon icon="fluent:person-board-20-filled" height="20px" />
                <span class="ml-1">アカウントの管理設定を開く</span>
            </v-btn>
        </div>
        <div class="settings__content">
            <div class="settings__content-heading mt-8">
                <Icon icon="fluent:wrench-settings-20-filled" width="22px" />
                <span class="ml-2">メンテナンス</span>
            </div>
        </div>
        <div class="settings__content" :class="{'settings__content--disabled': is_disabled}">
            <div class="settings__item">
                <div class="settings__item-heading">サーバーログの表示</div>
                <div class="settings__item-label">
                    KonomiTV サーバーの動作ログとアクセスログをリアルタイムで表示します。<br>
                    サーバーの動作状況の確認やトラブルシューティングに役立ちます。<br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-5" color="background-lighten-2" variant="flat"
                @click="server_log_dialog = !server_log_dialog">
                <Icon icon="fluent:document-text-16-regular" height="20px" />
                <span class="ml-2">サーバーログを表示</span>
            </v-btn>
        </div>
        <div class="settings__content">
            <div class="settings__item">
                <div class="settings__item-heading">KonomiTV のデータベースを更新</div>
                <div class="settings__item-label">
                    KonomiTV のデータベースに保存されている、チャンネル情報・番組情報・Twitter アカウント情報などの外部 API に依存するデータをすべて更新します。<br>
                    即座に外部 API からのデータ更新を反映させたいときに利用してください。<br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-5" color="background-lighten-2" variant="flat"
                @click="updateDatabase()">
                <Icon icon="iconoir:database-backup" height="20px" />
                <span class="ml-2">データベースを更新</span>
            </v-btn>
            <div class="settings__item">
                <div class="settings__item-heading">録画フォルダの一括スキャンを手動実行</div>
                <div class="settings__item-label">
                    録画フォルダ内のファイルは、通常 KonomiTV サーバーの起動時に自動的にスキャンされます。<br>
                    録画ファイルが KonomiTV に正しく反映されていない場合にのみ実行してみてください。<br>
                </div>
                <div class="settings__item-label mt-1">
                    <strong>大量の録画ファイルが保存されている環境では、処理完了まで数時間〜数日以上かかることがあります。</strong><br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-5" color="background-lighten-2" variant="flat"
                @click="runBatchScan()">
                <Icon icon="fluent:folder-sync-20-regular" height="20px" />
                <span class="ml-2">録画フォルダの一括スキャンを手動実行</span>
            </v-btn>
            <div class="settings__item">
                <div class="settings__item-heading">録画ファイルのバックグラウンド解析タスクを再実行</div>
                <div class="settings__item-label">
                    録画ファイルのメタデータ解析やサムネイル作成が完了していない場合に、これらの処理を再度実行します。<br>
                    PC のシャットダウンなどで途中で中断してしまった場合は、このボタンから処理を再開できます。<br>
                </div>
                <div class="settings__item-label mt-1">
                    <strong>大量の録画ファイルが保存されている環境では、処理完了まで数時間〜数日以上かかることがあります。</strong><br>
                </div>
            </div>
            <v-btn class="settings__save-button mt-5" color="background-lighten-2" variant="flat"
                @click="startBackgroundAnalysis()">
                <Icon icon="fluent:book-arrow-clockwise-20-regular" height="20px" />
                <span class="ml-2">バックグラウンド解析タスクを再実行</span>
            </v-btn>
        </div>
        <div class="settings__content" :class="{'settings__content--disabled': is_disabled}">
            <div class="settings__item">
                <div class="settings__item-heading text-error-lighten-1">KonomiTV サーバーを再起動</div>
                <div class="settings__item-label">
                    KonomiTV サーバーを再起動します。サーバー設定の変更を反映するには再起動が必要です。<br>
                    <strong>再起動を実行すると、すべての視聴中セッションが切断されます。</strong>十分注意してください。<br>
                </div>
            </div>
            <v-btn class="settings__save-button bg-error mt-5" variant="flat"
                @click="restartServer()">
                <Icon icon="fluent:arrow-counterclockwise-20-filled" height="20px" />
                <span class="ml-2">KonomiTV サーバーを再起動</span>
            </v-btn>
            <div class="settings__item">
                <div class="settings__item-heading text-error-lighten-1">KonomiTV サーバーをシャットダウン</div>
                <div class="settings__item-label">
                    KonomiTV サーバーをシャットダウンします。<br>
                    <strong>シャットダウンを実行すると、再度手動で KonomiTV サーバーを起動するまで KonomiTV にアクセスできなくなります。</strong>十分注意してください。<br>
                </div>
                <div class="settings__item-label mt-1">
                    なお、Linux 版 KonomiTV サーバーはプロセス管理を PM2 / Docker に委譲しているため、シャットダウン後は自動で再起動されます。完全にシャットダウンするには、PM2 / Docker 側でサービスを停止してください。<br>
                </div>
            </div>
            <v-btn class="settings__save-button bg-error mt-5" variant="flat"
                @click="shutdownServer()">
                <Icon icon="fluent:power-20-filled" height="20px" />
                <span class="ml-2">KonomiTV サーバーをシャットダウン</span>
            </v-btn>
        </div>
        <AccountManageSettings :modelValue="account_manage_settings_modal" @update:modelValue="account_manage_settings_modal = $event" />
        <ServerLogDialog :modelValue="server_log_dialog" @update:modelValue="server_log_dialog = $event" />
    </SettingsBase>
</template>
<script lang="ts" setup>

import { onMounted, ref, watch } from 'vue';

import AccountManageSettings from '@/components/Settings/AccountManageSettings.vue';
import ServerLogDialog from '@/components/Settings/ServerLogDialog.vue';
import Message from '@/message';
import Maintenance from '@/services/Maintenance';
import Settings, { IServerSettings, IServerSettingsDefault, IStorageInfo } from '@/services/Settings';
import Version from '@/services/Version';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

// フォームを小さくするかどうか
const is_form_dense = Utils.isSmartphoneHorizontal();

// ユーザー情報を取得し、もし管理者権限であれば無効化を解除
const is_disabled = ref(true);
const user_store = useUserStore();
user_store.fetchUser().then((user) => {
    if (user && user.is_admin) {
        is_disabled.value = false;
    }
});

// サーバー設定を取得
const server_settings = ref<IServerSettings>(structuredClone(IServerSettingsDefault));

const storage_info = ref<IStorageInfo[]>([]);

Settings.fetchServerSettings().then((settings) => {
    if (settings) {
        server_settings.value = settings;
    }
});
const fetchStorageInfo = async () => {
    const result = await Settings.fetchStorageStatus();
    storage_info.value = result.storage_info;
};

// マウント時にストレージ情報を取得
onMounted(() => {
    fetchStorageInfo();
});

// 録画フォルダが変更されたときにストレージ情報を再取得
watch(() => server_settings.value.video.recorded_folders, () => {
    fetchStorageInfo();
}, { deep: true });

// バイト数を人間が読みやすい形式にフォーマットする関数
const formatBytes = (bytes: number): string => {
    return Utils.formatBytes(bytes);
};

// 録画可能時間をフォーマットする関数
const formatRecordingHours = (hours: number): string => {
    if (hours < 1) {
        return `${Math.round(hours * 60)}分`;
    } else if (hours < 24) {
        return `${hours.toFixed(1)}時間`;
    } else {
        const days = Math.floor(hours / 24);
        const remainingHours = Math.round(hours % 24);
        return `${days}日${remainingHours > 0 ? remainingHours + '時間' : ''}`;
    }
};

// バックエンドが変更されたときに、レコーダー設定を適切に調整する
watch(() => server_settings.value.general.backend, (newBackend) => {
    // EDCB バックエンドの場合、レコーダーも EDCB に固定
    if (newBackend === 'EDCB') {
        server_settings.value.general.recorder = 'EDCB';
    }
    // Mirakurun バックエンドの場合、レコーダーは EPGStation または EDCB を選択可能
    // デフォルトは EPGStation
    else if (newBackend === 'Mirakurun' && server_settings.value.general.recorder !== 'EPGStation' && server_settings.value.general.recorder !== 'EDCB') {
        server_settings.value.general.recorder = 'EPGStation';
    }
});

// サーバー設定を更新する関数
async function updateServerSettings() {

    // custom_https_certificate と custom_https_private_key が空文字列の場合は null に変換
    if (server_settings.value.server.custom_https_certificate === '') {
        server_settings.value.server.custom_https_certificate = null;
    }
    if (server_settings.value.server.custom_https_private_key === '') {
        server_settings.value.server.custom_https_private_key = null;
    }

    // サーバー設定を更新
    const result = await Settings.updateServerSettings(server_settings.value);

    // 成功した場合のみメッセージを表示
    // エラー処理は Services 層で行われるため、ここではエラー処理は不要
    // 再起動するまでは設定データは反映されないため、再起動せずにページをリロードすると反映されてないように見える点に注意
    if (result === true) {
        Message.success('サーバー設定を更新しました。\n変更を反映するためには、KonomiTV サーバーを再起動してください。');
    }
}

// ユーザー管理モーダルの表示状態
const account_manage_settings_modal = ref(false);
// サーバーログダイアログの表示状態
const server_log_dialog = ref(false);

// データベースを更新する関数
async function updateDatabase() {
    Message.show('データベースを更新しています...');
    await Maintenance.updateDatabase();
    Message.success('データベースを更新しました。');
}

// 録画フォルダの一括スキャンを実行する関数
async function runBatchScan() {
    Message.info(
        '録画フォルダの一括スキャンを開始しています...\n' +
        '大量の録画ファイルが保存されている環境では、処理完了まで数時間〜数日以上かかることがあります。'
    );
    const result = await Maintenance.runBatchScan();
    if (result === true) {
        Message.success(
            '録画フォルダの一括スキャンが完了しました。\n' +
            'すべての録画ファイルがデータベースに同期されているはずです。'
        );
    }
}

// バックグラウンド解析タスクを開始する関数
async function startBackgroundAnalysis() {
    Message.info(
        'バックグラウンド解析タスクを開始しています...\n' +
        '大量の録画ファイルが保存されている環境では、処理完了まで数時間〜数日以上かかることがあります。'
    );
    const result = await Maintenance.startBackgroundAnalysis();
    if (result === true) {
        Message.success(
            'バックグラウンド解析タスクの実行が完了しました。\n' +
            'すべての録画番組のメタデータ解析/サムネイル生成が完了しているはずです。'
        );
    }
}

// KonomiTV サーバーの再起動を行う関数
async function restartServer() {
    const result = await Maintenance.restartServer();
    if (result === true) {
        Message.show('KonomiTV サーバーを再起動しています...');
        // バージョン情報が取得できるようになるまで待つ
        await Utils.sleep(1.0);
        while (await Version.fetchServerVersion(true) === null) {
            await Utils.sleep(1.0);
        }
        Message.success('KonomiTV サーバーを再起動しました。');
    }
}

// KonomiTV サーバーのシャットダウンを行う関数
async function shutdownServer() {
    const result = await Maintenance.shutdownServer();
    if (result === true) {
        Message.success('KonomiTV サーバーをシャットダウンしました。');
    }
}

</script>
<style lang="scss" scoped>

// ストレージ情報が空の場合の表示
.storage-info-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    border-radius: 12px;
    background: rgb(var(--v-theme-background-lighten-1));
    color: rgb(var(--v-theme-text-darken-1));
    text-align: center;

    &__text {
        margin-top: 16px;
        font-size: 16px;
        font-weight: 600;
    }

    &__subtext {
        margin-top: 8px;
        font-size: 14px;
        opacity: 0.7;
    }
}

// ストレージカード
.storage-card {
    padding: 24px;
    border-radius: 16px;
    background: linear-gradient(135deg, rgb(var(--v-theme-background-lighten-1)) 0%, rgb(var(--v-theme-background-lighten-2)) 100%);
    border: 1px solid rgba(255, 255, 255, 0.05);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transition: all 0.3s ease;

    &:hover {
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
        transform: translateY(-2px);
    }

    // ヘッダー部分
    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        padding-bottom: 16px;
        border-bottom: 2px solid rgba(255, 255, 255, 0.08);
    }

    &__drive {
        display: flex;
        align-items: center;
        gap: 12px;
        color: rgb(var(--v-theme-text));
    }

    &__drive-name {
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    &__usage-badge {
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.5px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);

        &--normal {
            background: linear-gradient(135deg, rgb(var(--v-theme-primary)) 0%, rgb(var(--v-theme-primary-darken-1)) 100%);
            color: white;
        }

        &--warning {
            background: linear-gradient(135deg, #FFA726 0%, #FB8C00 100%);
            color: white;
        }

        &--critical {
            background: linear-gradient(135deg, rgb(var(--v-theme-error)) 0%, rgb(var(--v-theme-error-darken-1)) 100%);
            color: white;
            animation: pulse 2s ease-in-out infinite;
        }
    }

    // プログレスバー
    &__progress {
        margin-bottom: 24px;
    }

    &__progress-bar-container {
        height: 12px;
        border-radius: 10px;
        background: rgba(0, 0, 0, 0.2);
        overflow: hidden;
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
    }

    &__progress-bar {
        height: 100%;
        border-radius: 10px;
        transition: width 0.6s ease, background 0.3s ease;
        position: relative;
        overflow: hidden;

        &::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
            animation: shimmer 2s infinite;
        }

        &--normal {
            background: linear-gradient(90deg, rgb(var(--v-theme-primary)) 0%, rgb(var(--v-theme-primary-lighten-1)) 100%);
        }

        &--warning {
            background: linear-gradient(90deg, #FFA726 0%, #FFB74D 100%);
        }

        &--critical {
            background: linear-gradient(90deg, rgb(var(--v-theme-error)) 0%, rgb(var(--v-theme-error-lighten-1)) 100%);
        }
    }

    // 統計情報グリッド
    &__stats {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
    }

    &__stat {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px;
        border-radius: 12px;
        background: rgba(0, 0, 0, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.3s ease;

        &:hover {
            background: rgba(0, 0, 0, 0.25);
            transform: translateY(-2px);
        }

        &--highlight {
            background: linear-gradient(135deg, rgba(var(--v-theme-primary-rgb), 0.15) 0%, rgba(var(--v-theme-primary-rgb), 0.05) 100%);
            border: 1px solid rgba(var(--v-theme-primary-rgb), 0.3);

            &:hover {
                background: linear-gradient(135deg, rgba(var(--v-theme-primary-rgb), 0.25) 0%, rgba(var(--v-theme-primary-rgb), 0.1) 100%);
            }
        }
    }

    &__stat-icon {
        flex-shrink: 0;
        color: rgb(var(--v-theme-text-darken-1));

        &--used {
            color: #FB8C00;
        }

        &--free {
            color: #66BB6A;
        }

        &--time {
            color: rgb(var(--v-theme-primary));
        }
    }

    &__stat-content {
        flex: 1;
        min-width: 0;
    }

    &__stat-label {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 4px;
    }

    &__stat-value {
        font-size: 15px;
        font-weight: 700;
        color: rgb(var(--v-theme-text));
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;

        &--used {
            color: #FFA726;
        }

        &--free {
            color: #81C784;
        }

        &--time {
            color: rgb(var(--v-theme-primary-lighten-1));
            font-size: 16px;
        }
    }
}

// アニメーション
@keyframes pulse {
    0%, 100% {
        opacity: 1;
    }
    50% {
        opacity: 0.7;
    }
}

@keyframes shimmer {
    0% {
        transform: translateX(-100%);
    }
    100% {
        transform: translateX(100%);
    }
}

// タブレット/小画面対応
@media (max-width: 1024px) {
    .storage-card {
        &__stats {
            grid-template-columns: repeat(2, 1fr);
        }
    }
}

// スマートフォン縦画面での調整
@include smartphone-vertical {
    .storage-card {
        padding: 20px;

        &__header {
            flex-direction: column;
            align-items: flex-start;
            gap: 12px;
        }

        &__usage-badge {
            align-self: flex-start;
        }

        &__stats {
            grid-template-columns: 1fr;
            gap: 12px;
        }

        &__stat {
            padding: 14px;
        }

        &__stat-value {
            font-size: 14px;

            &--time {
                font-size: 15px;
            }
        }
    }
}

</style>
