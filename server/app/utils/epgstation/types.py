"""
EPGStation の API レスポンス型定義
EPGStation v2.10.0 の API 仕様に基づく
"""

from typing import TypedDict


# ***** チャンネル情報 *****

class EPGStationChannel(TypedDict, total=False):
    """EPGStation のチャンネル情報"""
    id: int  # チャンネル ID
    serviceId: int  # サービス ID
    networkId: int  # ネットワーク ID
    name: str  # チャンネル名
    halfWidthName: str  # 半角チャンネル名
    hasLogoData: bool  # ロゴデータの有無
    channelType: str  # チャンネルタイプ (GR, BS, CS, SKY)
    channel: str  # チャンネル番号


# ***** 番組情報 *****

class EPGStationProgram(TypedDict, total=False):
    """EPGStation の番組情報"""
    id: int  # 番組 ID (NID32736-SID1024-EID65535 形式を数値化したもの)
    channelId: int  # チャンネル ID
    eventId: int  # イベント ID
    serviceId: int  # サービス ID
    networkId: int  # ネットワーク ID
    startAt: int  # 開始時刻 (UNIX タイムスタンプ・ミリ秒)
    endAt: int  # 終了時刻 (UNIX タイムスタンプ・ミリ秒)
    isFree: bool  # 無料放送かどうか
    name: str  # 番組名
    description: str | None  # 番組概要
    extended: str | None  # 番組詳細
    genre1: int | None  # ジャンル1
    subGenre1: int | None  # サブジャンル1
    genre2: int | None  # ジャンル2
    subGenre2: int | None  # サブジャンル2
    genre3: int | None  # ジャンル3
    subGenre3: int | None  # サブジャンル3
    videoType: str | None  # 映像タイプ
    videoResolution: str | None  # 映像解像度
    videoStreamContent: int | None  # 映像ストリームコンテンツ
    videoComponentType: int | None  # 映像コンポーネントタイプ
    audioSamplingRate: int | None  # 音声サンプリングレート
    audioComponentType: int | None  # 音声コンポーネントタイプ


# ***** 予約情報 *****

class EPGStationReserveOption(TypedDict, total=False):
    """EPGStation の予約オプション"""
    enable: bool  # 予約が有効かどうか
    directory: str | None  # 保存先ディレクトリ
    recordedFormat: str | None  # 録画ファイル名フォーマット
    mode1: int | None  # 録画モード1
    directory1: str | None  # 保存先ディレクトリ1
    mode2: int | None  # 録画モード2
    directory2: str | None  # 保存先ディレクトリ2
    mode3: int | None  # 録画モード3
    directory3: str | None  # 保存先ディレクトリ3
    encodeMode1: str | None  # エンコードモード1
    encodeDirectory1: str | None  # エンコード保存先ディレクトリ1
    encodeMode2: str | None  # エンコードモード2
    encodeDirectory2: str | None  # エンコード保存先ディレクトリ2
    encodeMode3: str | None  # エンコードモード3
    encodeDirectory3: str | None  # エンコード保存先ディレクトリ3
    isDeleteOriginalAfterEncode: bool | None  # エンコード後に元ファイルを削除するか


class EPGStationReserve(TypedDict, total=False):
    """EPGStation の予約情報"""
    id: int  # 予約 ID
    programId: int  # 番組 ID
    isSkip: bool  # スキップ状態かどうか
    isOverlap: bool  # 重複状態かどうか
    isIgnoreOverlap: bool  # 重複を無視するかどうか
    isConflict: bool  # 競合状態かどうか
    ruleId: int | None  # ルール ID (手動予約の場合は None)
    allowEndLack: bool  # 終了時刻が欠けることを許可するか
    tags: list[int]  # タグ ID のリスト
    option: EPGStationReserveOption  # 予約オプション


# ***** ルール情報 *****

class EPGStationGenre(TypedDict, total=False):
    """ジャンル情報"""
    genre: int
    subGenre: int

class EPGStationTime(TypedDict, total=False):
    """時間帯情報"""
    start: int
    end: int
    week: int

class EPGStationRuleSearchOption(TypedDict, total=False):
    """EPGStation のルール検索オプション"""
    enable: bool  # ルールが有効かどうか
    keyword: str | None  # 検索キーワード
    ignoreKeyword: str | None  # 除外キーワード
    keyCS: bool | None  # 大文字小文字を区別するか
    keyRegExp: bool | None  # 正規表現検索を行うか
    name: bool | None  # 番組名を検索対象にするか
    description: bool | None  # 番組概要を検索対象にするか
    extended: bool | None  # 番組詳細を検索対象にするか
    ignoreKeyCS: bool | None  # 除外キーワードで大文字小文字を区別するか
    ignoreKeyRegExp: bool | None  # 除外キーワードで正規表現検索を行うか
    ignoreName: bool | None  # 除外キーワードで番組名を検索対象にするか
    ignoreDescription: bool | None  # 除外キーワードで番組概要を検索対象にするか
    ignoreExtended: bool | None  # 除外キーワードで番組詳細を検索対象にするか
    GR: bool | None  # 地デジを検索対象にするか
    BS: bool | None  # BSを検索対象にするか
    CS: bool | None  # CSを検索対象にするか
    SKY: bool | None  # スカパー!を検索対象にするか
    stations: list[int] | None  # 検索対象のチャンネル ID リスト
    genres: list[EPGStationGenre] | None  # 検索対象のジャンルリスト
    times: list[EPGStationTime] | None  # 検索対象の時間帯リスト
    isFree: bool | None  # 無料放送のみを検索対象にするか
    durationMin: int | None  # 番組長の最小値 (分)
    durationMax: int | None  # 番組長の最大値 (分)
    searchPeriods: list[dict[str, int]] | None  # 検索期間リスト
    avoidDuplicate: bool | None  # 重複を避けるか
    periodToAvoidDuplicate: int | None  # 重複を避ける期間 (時間)


class EPGStationRule(TypedDict, total=False):
    """EPGStation のルール情報"""
    id: int  # ルール ID
    isTimeSpecification: bool  # 時刻指定かどうか
    keyword: str | None  # 検索キーワード
    halfWidthKeyword: str | None  # 半角検索キーワード
    searchOption: EPGStationRuleSearchOption  # ルール検索オプション
    reserveOption: EPGStationReserveOption  # 予約オプション


# ***** 録画中情報 *****

class EPGStationRecording(TypedDict, total=False):
    """EPGStation の録画中情報"""
    id: int  # 録画中 ID (予約 ID と同じ)
    programId: int  # 番組 ID
    channelId: int  # チャンネル ID
    startAt: int  # 開始時刻 (UNIX タイムスタンプ・ミリ秒)
    endAt: int  # 終了時刻 (UNIX タイムスタンプ・ミリ秒)
    name: str  # 番組名
    description: str | None  # 番組概要
    extended: str | None  # 番組詳細
    mode: str  # 録画モード
    isRecording: bool  # 録画中かどうか
