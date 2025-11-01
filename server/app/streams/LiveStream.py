
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

import anyio
from hashids import Hashids

from app import logging
from app.config import Config
from app.constants import LIBRARY_PATH, QUALITY_TYPES
from app.schemas import LiveStreamStatus
from app.streams.LiveEncodingTask import LiveEncodingTask
from app.streams.LivePSIDataArchiver import LivePSIDataArchiver
from app.utils.edcb.EDCBTuner import EDCBTuner


class LiveStreamClient:
    """ ライブストリームのクライアントを表すクラス """

    def __init__(self, live_stream: LiveStream, client_type: Literal['mpegts']) -> None:
        """
        ライブストリーミングクライアントのインスタンスを初期化する
        LiveStreamClient は LiveStream クラス外から初期化してはいけない
        (必ず LiveStream.connect() で取得した LiveStreamClient を利用すること)

        Args:
            live_stream (LiveStream): クライアントが紐づくライブストリームのインスタンス
            client_type (Literal['mpegts']): クライアントの種別 (mpegts, ll-hls クライアントは廃止された)
        """

        # このクライアントが紐づくライブストリームのインスタンス
        self._live_stream: LiveStream = live_stream

        # クライアント ID
        ## ミリ秒単位のタイムスタンプをもとに、Hashids による10文字のユニーク ID が生成される
        self.client_id: str = 'MPEGTS-' + Hashids(min_length=10).encode(int(time.time() * 1000))

        # クライアントの種別 (mpegts)
        self.client_type: Literal['mpegts'] = client_type

        # ストリームデータが入る Queue
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        # ストリームデータの最終読み取り時刻のタイミング
        ## 最終読み取り時刻から 10 秒経過したクライアントは LiveStream.writeStreamData() でタイムアウトと判断され、削除される
        self._stream_data_read_at: float = time.time()


    @property
    def stream_data_read_at(self) -> float:
        """ ストリームデータの最終読み取り時刻のタイミング (読み取り専用) """
        return self._stream_data_read_at


    async def readStreamData(self) -> bytes | None:
        """
        自分自身の Queue からストリームデータを読み取って返す
        Queue 内のストリームデータは writeStreamData() で書き込まれたもの

        Args:
            client (LiveStreamClient): ライブストリームクライアントのインスタンス

        Returns:
            bytes | None: ストリームデータ (エンコードタスクが終了した場合は None が返る)
        """

        # mpegts クライアント以外では実行しない
        if self.client_type != 'mpegts':
            return None

        # ストリームデータの最終読み取り時刻を更新
        self._stream_data_read_at = time.time()

        # Queue から読み取ったストリームデータを返す
        try:
            return await self._queue.get()
        except TypeError:
            return None


    def writeStreamData(self, stream_data: bytes | None) -> None:
        """
        自分自身の Queue にストリームデータを書き込む
        Queue 内のストリームデータは readStreamData() で読み取られる

        Args:
            stream_data (bytes): 書き込むストリームデータ (エンコードタスクが終了した場合は None を渡す)
        """

        # mpegts クライアント以外では実行しない
        if self.client_type != 'mpegts':
            return None

        # Queue にストリームデータを書き込む
        self._queue.put_nowait(stream_data)


class LiveStream:
    """ ライブストリームを管理するクラス """

    # ライブストリームのインスタンスが入る、ライブストリーム ID をキーとした辞書
    # この辞書にライブストリームに関する全てのデータが格納されている
    __instances: ClassVar[dict[str, LiveStream]] = {}


    # 必ずライブストリーム ID ごとに1つのインスタンスになるように (Singleton)
    def __new__(cls, display_channel_id: str, quality: QUALITY_TYPES) -> LiveStream:

        # まだ同じライブストリーム ID のインスタンスがないときだけ、インスタンスを生成する
        # (チャンネルID)-(映像の品質) で一意な ID になる
        live_stream_id = f'{display_channel_id}-{quality}'
        if live_stream_id not in cls.__instances:

            # 新しいライブストリームのインスタンスを生成する
            instance = super().__new__(cls)

            # ライブストリーム ID を設定
            instance.live_stream_id = live_stream_id

            # チャンネル ID と映像の品質を設定
            instance.display_channel_id = display_channel_id
            instance.quality = quality

            # ライブストリームクライアントが入るリスト
            ## クライアントの接続が切断された場合、このリストからも削除される
            ## したがって、クライアントの数はこのリストの長さで求められる
            instance._clients = []

            # ストリームのステータス
            ## Offline, Standby, ONAir, Idling, Restart のいずれか
            instance._status = 'Offline'

            # ストリームのステータス詳細
            instance._detail = 'ライブストリームは Offline です。'

            # ストリームの開始時刻
            instance._started_at = 0

            # ストリームのステータスの最終更新時刻のタイムスタンプ
            instance._updated_at = 0

            # ストリームデータの最終書き込み時刻のタイムスタンプ
            ## 最終書き込み時刻が 5 秒 (ONAir 時) 20 秒 (Standby 時) 以上更新されていない場合は、
            ## エンコーダーがフリーズしたものとみなしてエンコードタスクを再起動する
            instance._stream_data_written_at = 0

            # 実行中の LiveEncodingTask のタスクへの参照
            # ref: https://docs.astral.sh/ruff/rules/asyncio-dangling-task/
            instance._live_encoding_task_ref = None

            # PSI/SI データアーカイバーのインスタンス
            ## LiveStreamsRouter からアクセスする必要があるためここに設置している
            instance.psi_data_archiver = None

            # EDCB バックエンドのチューナーインスタンス
            ## Mirakurun バックエンドを使っている場合は None のまま
            instance.tuner = None

            # ついで録画機能の状態
            instance._is_recording = False  # 録画中かどうか
            instance._recording_start_time = None  # 録画開始時刻
            instance._recording_file_path = None  # 録画ファイルのパス
            instance._recording_file_handle = None  # 録画ファイルハンドル
            instance._recording_mode = 'raw'  # 録画モード (raw: 放送波そのままの生録画, encoded: エンコード後のストリームを録画)
            # PSI/SI 書庫 (.psc) を録るための psisiarc プロセス
            instance._psi_archive_process = None
            instance._psi_archive_path = None

            # 生成したインスタンスを登録する
            cls.__instances[live_stream_id] = instance

        # 登録されているインスタンスを返す
        return cls.__instances[live_stream_id]


    def __init__(self, display_channel_id: str, quality: QUALITY_TYPES) -> None:
        """
        ライブストリームのインスタンスを取得する

        Args:
            display_channel_id (str): チャンネルID
            quality (QUALITY_TYPES): 映像の品質 (1080p-60fps ~ 240p)
        """

        # インスタンス変数の型ヒントを定義
        # Singleton のためインスタンスの生成は __new__() で行うが、__init__() も定義しておかないと補完がうまく効かない
        self.live_stream_id: str
        self.display_channel_id: str
        self.quality: QUALITY_TYPES
        self._clients: list[LiveStreamClient]
        self._status: Literal['Offline', 'Standby', 'ONAir', 'Idling', 'Restart']
        self._detail: str
        self._started_at: float
        self._updated_at: float
        self._stream_data_written_at: float
        self._live_encoding_task_ref: asyncio.Task[None] | None
        self.psi_data_archiver: LivePSIDataArchiver | None
        self.tuner: EDCBTuner | None
        # ついで録画機能の状態
        self._is_recording: bool
        self._recording_start_time: float | None
        self._recording_file_path: str | None
        self._recording_file_handle: anyio.AsyncFile | None  # type: ignore
        self._recording_mode: Literal['raw', 'encoded']
        self._psi_archive_process: asyncio.subprocess.Process | None
        self._psi_archive_path: str | None


    @classmethod
    def getAllLiveStreams(cls) -> list[LiveStream]:
        """
        全てのライブストリームのインスタンスを取得する

        Returns:
            list[LiveStream]: ライブストリームのインスタンスの入ったリスト
        """

        # __instances 辞書を values() で値だけのリストにしたものを返す
        return list(cls.__instances.values())


    @classmethod
    def getONAirLiveStreams(cls) -> list[LiveStream]:
        """
        現在 ONAir 状態のライブストリームのインスタンスを取得する

        Returns:
            list[LiveStream]: 現在 ONAir 状態のライブストリームのインスタンスのリスト
        """

        result: list[LiveStream] = []

        # 現在 ONAir 状態のライブストリームに絞り込む
        for live_stream in LiveStream.getAllLiveStreams():
            if live_stream.getStatus().status == 'ONAir':
                result.append(live_stream)

        return result


    @classmethod
    def getIdlingLiveStreams(cls) -> list[LiveStream]:
        """
        現在 Idling 状態のライブストリームのインスタンスを取得する

        Returns:
            list[LiveStream]: 現在 Idling 状態のライブストリームのインスタンスのリスト
        """

        result: list[LiveStream] = []

        # 現在 Idling 状態のライブストリームに絞り込む
        for live_stream in LiveStream.getAllLiveStreams():
            if live_stream.getStatus().status == 'Idling':
                result.append(live_stream)

        return result


    @classmethod
    def getViewerCount(cls, display_channel_id: str) -> int:
        """
        指定されたチャンネルのライブストリームの現在の視聴者数を取得する

        Args:
            display_channel_id (str): チャンネルID

        Returns:
            int: 視聴者数
        """

        # 指定されたチャンネル ID に紐づくライブストリームを探して視聴者数を集計
        viewer_count = 0
        for live_stream in LiveStream.getAllLiveStreams():
            if live_stream.display_channel_id == display_channel_id:
                viewer_count += live_stream.getStatus().client_count

        return viewer_count


    async def connect(self, client_type: Literal['mpegts']) -> LiveStreamClient:
        """
        ライブストリームに接続して、新しくライブストリームに登録されたクライアントを返す
        この時点でライブストリームが Offline ならば、新たにエンコードタスクが起動される

        Args:
            client_type (Literal['mpegts']): クライアントの種別 (mpegts, ll-hls クライアントは廃止された)

        Returns:
            LiveStreamClient: ライブストリームクライアントのインスタンス
        """

        # ***** ステータスの切り替え *****

        current_status = self._status

        # ライブストリームが Offline な場合、新たにエンコードタスクを起動する
        if current_status == 'Offline':

            # ステータスを Standby に設定
            # 現在 Idling 状態のライブストリームを探す前に設定しないと多重に LiveEncodingTask が起動しかねず、重篤な不具合につながる
            self.setStatus('Standby', 'エンコードタスクを起動しています…')

            # 現在 Idling 状態のライブストリームがあれば、うち最初のライブストリームを Offline にする
            ## 一般にチューナーリソースは無尽蔵にあるわけではないので、現在 Idling（=つまり誰も見ていない）ライブストリームがあるのなら
            ## それを Offline にしてチューナーリソースを解放し、新しいライブストリームがチューナーを使えるようにする
            for _ in range(8):  # 画質切り替えなどタイミングの問題で Idling なストリームがない事もあるので、8回くらいリトライする

                # 現在 Idling 状態のライブストリームがあれば
                idling_live_streams = self.getIdlingLiveStreams()
                if len(idling_live_streams) > 0:
                    idling_live_stream: LiveStream = idling_live_streams[0]

                    # EDCB バックエンドの場合はチューナーをアンロックし、これから開始するエンコードタスクで再利用できるようにする
                    if idling_live_stream.tuner is not None:
                        idling_live_stream.tuner.unlock()

                    # チューナーリソースを解放する
                    idling_live_stream.setStatus('Offline', '新しいライブストリームが開始されたため、チューナーリソースを解放しました。')
                    break

                # 現在 ONAir 状態のライブストリームがなく、リトライした所で Idling なライブストリームが取得できる見込みがない
                if len(self.getONAirLiveStreams()) == 0:
                    break

                await asyncio.sleep(0.1)

            # エンコードタスクを非同期で実行
            instance = LiveEncodingTask(self)
            self._live_encoding_task_ref = asyncio.create_task(instance.run())

        # ***** クライアントの登録 *****

        # ライブストリームクライアントのインスタンスを生成・登録する
        client = LiveStreamClient(self, client_type)
        self._clients.append(client)
        logging.info(f'[Live: {self.live_stream_id}] Client Connected. Client ID: {client.client_id}')

        # ***** アイドリングからの復帰 *****

        # ライブストリームが Idling 状態な場合、ONAir 状態に戻す（アイドリングから復帰）
        if current_status == 'Idling':
            self.setStatus('ONAir', 'ライブストリームは ONAir です。')

        # ライブストリームクライアントのインスタンスを返す
        return client


    def disconnect(self, client: LiveStreamClient) -> None:
        """
        指定されたクライアントのライブストリームへの接続を切断する
        このメソッドを実行すると LiveStreamClient インスタンスはライブストリームのクライアントリストから削除され、それ以降機能しなくなる
        LiveStreamClient を使い終わったら必ず呼び出すこと (さもなければ誰も見てないのに視聴中扱いでエンコードタスクが実行され続けてしまう)

        Args:
            client (LiveStreamClient): ライブストリームクライアントのインスタンス
        """

        # 指定されたライブストリームクライアントを削除する
        ## すでにタイムアウトなどで削除されていたら何もしない
        try:
            self._clients.remove(client)
            logging.info(f'[Live: {self.live_stream_id}] Client Disconnected. Client ID: {client.client_id}')
        except ValueError:
            pass
        del client


    def disconnectAll(self) -> None:
        """
        すべてのクライアントのライブストリームへの接続を切断する
        disconnect() とは違い、LiveStreamClient の操作元ではなくエンコードタスク側から操作することを想定している
        """

        # すべてのクライアントの接続を切断する
        for client in self._clients:
            # mpegts クライアントのみ、Queue に None を追加して接続切断を通知する
            if client.client_type == 'mpegts':
                client.writeStreamData(None)
            self.disconnect(client)
            del client

        # 念のためクライアントが入るリストを空にする
        self._clients = []


    def getStatus(self) -> LiveStreamStatus:
        """
        ライブストリームのステータスを取得する

        Returns:
            LiveStreamStatus: ライブストリームのステータス
        """

        return LiveStreamStatus(
            status = self._status,  # ライブストリームの現在のステータス
            detail = self._detail,  # ライブストリームの現在のステータスの詳細情報
            started_at = self._started_at,  # ライブストリームが開始された (ステータスが Offline or Restart → Standby に移行した) 時刻
            updated_at = self._updated_at,  # ライブストリームのステータスが最後に更新された時刻
            client_count = len(self._clients),  # ライブストリームに接続中のクライアント数
            # ついで録画機能の状態
            is_recording = self._is_recording,
            recording_start_time = self._recording_start_time,
            recording_file_path = self._recording_file_path,
        )


    def setStatus(self, status: Literal['Offline', 'Standby', 'ONAir', 'Idling', 'Restart'], detail: str, quiet: bool = False) -> bool:
        """
        ライブストリームのステータスを設定する

        Args:
            status (Literal['Offline', 'Standby', 'ONAir', 'Idling', 'Restart']): ライブストリームのステータス
            detail (str): ステータスの詳細
            quiet (bool): ステータス設定のログを出力するかどうか

        Returns:
            bool: ステータスが更新されたかどうか (更新が実際には行われなかった場合は False を返す)
        """

        # ステータスも詳細も現在の状態と重複しているなら、更新を行わない（同じ内容のイベントが複数発生するのを防ぐ）
        if self._status == status and self._detail == detail:
            return False

        # ステータスが Offline or Restart かつ現在の状態と重複している場合は、更新を行わない
        ## Offline や Restart は Standby に移行しない限り同じステータスで詳細が変化することはありえないので、
        ## ステータス詳細が上書きできてしまう状態は不適切
        ## ただ LiveEncodingTask で非同期的にステータスをセットしている関係で上書きしてしまう可能性があるため、ここで上書きを防ぐ
        if (status == 'Offline' or status == 'Restart') and status == self._status:
            return False

        # ステータスは Offline から Restart に移行してはならない
        if self._status == 'Offline' and status == 'Restart':
            return False

        # ストリーム開始 (Offline or Restart → Standby) 時、started_at と stream_data_written_at を更新する
        # ここで更新しておかないと、いつまで経っても初期化時の古いタイムスタンプが使われてしまう
        if ((self._status == 'Offline' or self._status == 'Restart') and status == 'Standby'):
            self._started_at = time.time()
            self._stream_data_written_at = time.time()

        # ステータス変更のログを出力
        if quiet is False:
            logging.info(f'[Live: {self.live_stream_id}] [Status: {status}] {detail}')

        # ストリーム起動完了時 (Standby → ONAir) 時のみ、ストリームの起動にかかった時間も出力
        if self._status == 'Standby' and status == 'ONAir':
            logging.info(f'[Live: {self.live_stream_id}] Startup complete. ({round(time.time() - self._started_at, 2)} sec)')

        # ログ出力を待ってからステータスと詳細をライブストリームにセット
        self._status = status
        self._detail = detail

        # 最終更新のタイムスタンプを更新
        self._updated_at = time.time()

        # チューナーインスタンスが存在する場合 (= EDCB バックエンド利用時) のみ
        if self.tuner is not None:

            # Idling への切り替え時、チューナーをアンロックして再利用できるように
            if self._status == 'Idling':
                self.tuner.unlock()

            # ONAir への切り替え（復帰）時、再びチューナーをロックして制御を横取りされないように
            if self._status == 'ONAir':
                self.tuner.lock()

        return True


    def getStreamDataWrittenAt(self) -> float:
        """
        ストリームデータの最終書き込み時刻を取得する

        Returns:
            float: ストリームデータの最終書き込み時刻
        """

        return self._stream_data_written_at


    async def writeStreamData(self, stream_data: bytes) -> None:
        """
        接続している全ての mpegts クライアントの Queue にストリームデータを書き込む
        同時にストリームデータの最終書き込み時刻を更新し、クライアントがタイムアウトしていたら削除する

        Args:
            stream_data (bytes): 書き込むストリームデータ
        """

        # ストリームデータの書き込み時刻
        now = time.time()

        # 接続している全てのクライアントの Queue にストリームデータを書き込む
        for client in self._clients:

            # タイムアウト秒数は 10 秒
            timeout = 10

            # 最終読み取り時刻を指定秒数過ぎたクライアントはタイムアウトと判断し、クライアントを削除する
            ## 主にネットワークが切断されたなどの理由で発生する
            if now - client.stream_data_read_at > timeout:
                self._clients.remove(client)
                logging.info(f'[Live: {self.live_stream_id}] Client Disconnected (Timeout). Client ID: {client.client_id}')
                del client
                continue

            # ストリームデータを書き込む (クライアント種別が mpegts の場合のみ)
            if client.client_type == 'mpegts':
                client.writeStreamData(stream_data)

        # ストリームデータが空でなければ、最終書き込み時刻を更新
        if stream_data != b'':
            self._stream_data_written_at = now

        # ついで録画機能: 録画中かつ録画モードが encoded の場合、エンコード後のストリームデータをファイルにも書き込む
        if self._is_recording and self._recording_mode == 'encoded' and self._recording_file_handle is not None and stream_data != b'':
            try:
                await self._recording_file_handle.write(stream_data)
                await self._recording_file_handle.flush()
            except Exception as ex:
                # ファイル書き込みエラーが発生した場合は録画を停止
                logging.error(f'[Live: {self.live_stream_id}] Recording file write error: {ex}')
                await self.stopRecording()


    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        ファイル名に使えない文字を安全な文字に置換する

        Args:
            name (str): 元の文字列

        Returns:
            str: 置換後の文字列
        """
        return (
            name.replace('/', '／')
                .replace('\\', '＼')
                .replace(':', '：')
                .replace('*', '＊')
                .replace('?', '？')
                .replace('"', '”')
                .replace('<', '＜')
                .replace('>', '＞')
                .replace('|', '｜')
        )

    async def startRecording(self) -> tuple[bool, str]:
        """
        ついで録画を開始する

        Returns:
            tuple[bool, str]: 成功したかどうかと、メッセージ
        """

        # 既に録画中の場合は何もしない
        if self._is_recording:
            return False, 'すでに録画中です。'

        # ライブストリームが ONAir 状態でない場合は録画できない
        if self._status != 'ONAir':
            return False, 'ライブストリームが ONAir 状態ではありません。'

        # チャンネル情報を取得
        from app.models.Channel import Channel
        channel = await Channel.filter(display_channel_id=self.display_channel_id).first()
        if channel is None:
            return False, 'チャンネル情報が見つかりません。'

        # 現在の番組情報を取得
        program_present = (await channel.getCurrentAndNextProgram())[0]
        if program_present is None:
            program_title = '番組情報なし'
        else:
            program_title = program_present.title

        # 録画ファイル名を生成: チャンネル名_番組名_YYYYMMDD_HHMMSS.ts
        ## ファイル名に使えない文字を置換
        safe_channel_name = self._sanitize_filename(channel.name)
        safe_program_title = self._sanitize_filename(program_title)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{safe_channel_name}_{safe_program_title}_{timestamp}.ts'

        # 録画先フォルダを取得
        config = Config()
        if len(config.video.recorded_folders) == 0:
            return False, '録画先フォルダが設定されていません。'
        recorded_folder = Path(config.video.recorded_folders[0])

        # 録画先フォルダが存在しない場合は作成
        if not recorded_folder.exists():
            try:
                recorded_folder.mkdir(parents=True, exist_ok=True)
            except Exception as ex:
                logging.error(f'[Live: {self.live_stream_id}] Failed to create recorded folder: {ex}')
                return False, f'録画先フォルダの作成に失敗しました: {ex}'

        # 録画ファイルのパスを生成
        recording_file_path = recorded_folder / filename
        self._recording_file_path = str(recording_file_path)

        # 録画ファイルを開く（デフォルトは放送波そのままの raw 録画）
        try:
            self._recording_file_handle = await anyio.open_file(str(recording_file_path), mode='wb')
            # raw : 放送波そのままの生録画, encoded : エンコード後のストリームを録画
            self._recording_mode = 'raw'
            self._is_recording = True
            self._recording_start_time = time.time()

            # PSI/SI 書庫 (.psc) も同時に保存する（EIT を除去しているため、番組情報復元に必要）
            try:
                psc_path = str(Path(self._recording_file_path).with_suffix('.psc'))
                await self.__startPSIArchiveToFile(channel.service_id, psc_path)
            except Exception as ex:
                logging.warning(f'[Live: {self.live_stream_id}] Failed to start PSI archive: {ex}')

            logging.info(f'[Live: {self.live_stream_id}] Recording started: {self._recording_file_path}')

            # RecordedScanTask に録画開始を通知（ついで録画フラグ付与と解析スキップのため）
            try:
                from app.metadata.RecordedScanTask import RecordedScanTask
                recorded_scan_task = RecordedScanTask()
                await recorded_scan_task.registerRecordingFile(self._recording_file_path)
            except Exception as ex:
                # ここでの失敗は録画自体には致命的でないため警告として扱う
                logging.warning(f'[Live: {self.live_stream_id}] Failed to notify RecordedScanTask (register): {ex}')

            return True, f'ついで録画を開始しました: {filename}'
        except Exception as ex:
            logging.error(f'[Live: {self.live_stream_id}] Failed to open recording file: {ex}')
            return False, f'録画ファイルのオープンに失敗しました: {ex}'


    async def stopRecording(self) -> tuple[bool, str]:
        """
        ついで録画を停止する

        Returns:
            tuple[bool, str]: 成功したかどうかと、メッセージ
        """

        # 録画中でない場合は何もしない
        if not self._is_recording:
            return False, '録画中ではありません。'

        async def _reset_recording_state(recording_file_path: str | None) -> None:
            self._is_recording = False
            self._recording_start_time = None
            self._recording_file_handle = None
            self._recording_mode = 'raw'
            self._recording_file_path = None
            self._psi_archive_process = None
            self._psi_archive_path = None

            # RecordedScanTask に録画停止を通知
            if recording_file_path is not None:
                try:
                    from app.metadata.RecordedScanTask import RecordedScanTask
                    recorded_scan_task = RecordedScanTask()
                    await recorded_scan_task.unregisterRecordingFile(recording_file_path)
                except Exception as ex:
                    logging.warning(f'[Live: {self.live_stream_id}] Failed to notify RecordedScanTask: {ex}')

        # 録画ファイルを閉じる
        recording_file_path = self._recording_file_path
        try:
            # PSI/SI 書庫の収集を停止する
            try:
                await self.__stopPSIArchiveToFile()
            except Exception as ex:
                logging.warning(f'[Live: {self.live_stream_id}] Failed to stop PSI archive: {ex}')

            if self._recording_file_handle is not None:
                await self._recording_file_handle.aclose()
                logging.info(f'[Live: {self.live_stream_id}] Recording stopped: {self._recording_file_path}')

            await _reset_recording_state(recording_file_path)

            if recording_file_path is not None:
                return True, f'録画を停止しました: {Path(recording_file_path).name}'
            else:
                return True, '録画を停止しました。'
        except Exception as ex:
            logging.error(f'[Live: {self.live_stream_id}] Failed to close recording file: {ex}')
            # エラーが発生しても状態はリセットする
            await _reset_recording_state(recording_file_path)
            return False, f'録画ファイルのクローズに失敗しました: {ex}'

    async def writeRawRecordingChunk(self, stream_data: bytes) -> None:
        """
        放送波の生 TS チャンクを書き込む（録画モードが raw のときのみ呼び出される想定）

        Args:
            stream_data (bytes): TS チャンクデータ
        """

        if not self._is_recording or self._recording_mode != 'raw':
            return
        if self._recording_file_handle is None or stream_data == b'':
            return
        try:
            await self._recording_file_handle.write(stream_data)
            await self._recording_file_handle.flush()
        except Exception as ex:
            logging.error(f'[Live: {self.live_stream_id}] Recording file write error (raw): {ex}')
            await self.stopRecording()

    async def pushPSIArchiveChunk(self, stream_data: bytes) -> None:
        """
        PSI/SI 書庫 (.psc) 出力中であれば、放送波の生 TS チャンクを psisiarc にも送る

        Args:
            stream_data (bytes): TS チャンクデータ
        """

        if self._psi_archive_process is None or stream_data == b'':
            return
        try:
            assert type(self._psi_archive_process.stdin) is asyncio.StreamWriter
            if self._psi_archive_process.stdin.is_closing() is False:
                self._psi_archive_process.stdin.write(stream_data)
                await self._psi_archive_process.stdin.drain()
        except Exception:
            # アーカイバープロセス側の一時的なエラーは無視（録画自体は継続）
            pass

    async def __startPSIArchiveToFile(self, service_id: int, psc_path: str) -> None:
        """
        psisiarc を起動し、PSI/SI 書庫 (.psc) をファイルに保存する

        Args:
            service_id (int): サービス ID
            psc_path (str): 出力する .psc ファイルパス
        """

        # 既に起動済みなら何もしない
        if self._psi_archive_process is not None:
            return

        psisiarc_options = [
            '-r', 'arib-data',
            '-n', str(service_id),
            '-i', '1',
            '-',              # stdin から放送波を受け取る
            psc_path,         # 出力先ファイル
        ]
        self._psi_archive_process = await asyncio.subprocess.create_subprocess_exec(
            LIBRARY_PATH['psisiarc'], *psisiarc_options,
            stdin = asyncio.subprocess.PIPE,
            stdout = asyncio.subprocess.DEVNULL,
            stderr = asyncio.subprocess.DEVNULL,
        )
        self._psi_archive_path = psc_path
        logging.debug_simple(f'[Live: {self.live_stream_id}] psisiarc (to file) started. (PID: {self._psi_archive_process.pid})')

    async def __stopPSIArchiveToFile(self) -> None:
        """
        psisiarc による PSI/SI 書庫の保存を停止し、プロセスをクリーンアップする
        """

        if self._psi_archive_process is None:
            return
        try:
            if self._psi_archive_process.returncode is None:
                self._psi_archive_process.kill()
                try:
                    await asyncio.wait_for(self._psi_archive_process.wait(), timeout=3.0)
                except Exception:
                    pass
        finally:
            self._psi_archive_process = None

