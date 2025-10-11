# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Dict, Literal, Optional, Tuple

from app import logging
from app.config import Config
from app.constants import LIBRARY_PATH, LOGS_DIR
from app.models.RecordedVideo import RecordedVideo
from app.schemas import EncodingTask


TSREPLACE_VERSION = "0.16"

class TSReplaceEncodingTask:
    """
    tsreplaceを使用したH.262-TSからH.264/HEVCへの映像変換を行うエンコードタスククラス
    エラーハンドリング、ログ機能、ポストプロセッシング機能を統合
    """

    # tsreplace.exe のパス
    TSREPLACE_PATH: ClassVar[str] = LIBRARY_PATH['tsreplace']

    # エンコードタスクの最大リトライ回数
    MAX_RETRY_COUNT: ClassVar[int] = 3

    # H.264 再生時のエンコード後のストリームの GOP 長 (秒)
    GOP_LENGTH_SECONDS_H264: ClassVar[float] = 0.5

    # H.265 再生時のエンコード後のストリームの GOP 長 (秒)
    GOP_LENGTH_SECONDS_H265: ClassVar[float] = float(2)

    # エラーの分類
    ERROR_CATEGORIES = {
        'FILE_ACCESS': 'ファイルアクセスエラー',
        'ENCODER': 'エンコーダーエラー',
        'RESOURCE': 'リソース不足エラー',
        'CONFIGURATION': '設定エラー',
        'NETWORK': 'ネットワークエラー',
        'UNKNOWN': '不明なエラー'
    }

    # リトライ可能なエラーカテゴリ
    RETRYABLE_CATEGORIES = ['RESOURCE', 'NETWORK', 'ENCODER', 'PROCESS', 'STREAM_CHANGE', 'VCEENCC_PARAM', 'FFMPEG_STREAM']

    # 共通品質設定
    DEFAULT_QUALITY_CONFIG = {
        'video_bitrate': '6000',
        'video_bitrate_max': '8000',
        'audio_bitrate': '192',
        'width': 1920,
        'height': 1080,
        'is_60fps': False
    }

    # エラーパターンの定義
    ERROR_PATTERNS = {
        'FILE_ACCESS': [
            r'No such file or directory',
            r'Permission denied',
            r'Disk full',
            r'Access is denied'
        ],
        'ENCODER': [
            r'Encoder.*not found',
            r'Hardware encoder.*not available',
            r'Codec initialization failed'
        ],
        'RESOURCE': [
            r'Out of memory',
            r'Cannot allocate memory',
            r'Too many open files'
        ],
        'PROCESS': [
            r'Process.*terminated',
            r'Command.*not found',
            r'Execution.*failed'
        ],
        'STREAM_CHANGE': [
            r'PMT.*version.*change',
            r'New PMT',
            r'program_number.*changed',
            r'stream.*configuration.*change',
            r'Stream.*#.*not found',
            r'Cannot find a matching stream',
            r'Invalid stream identifier'
        ],
        'VCEENCC_PARAM': [
            r'storage->SetProperty.*failed',
            r'invalid param',
            r'VCEEncC.*parameter.*error',
            r'AMF.*property.*error'
        ],
        'FFMPEG_STREAM': [
            r'Stream mapping failed',
            r'Cannot find stream',
            r'Invalid stream specifier',
            r'No suitable output format found',
            r'Failed to open.*for reading',
            r'Invalid data found when processing input',
            r'Invalid frame dimensions',
            r'Option.*cannot be applied to input url',
            r'Error parsing options for input file',
            r'Error opening input files'
        ]
    }

    def _getQualityConfig(self) -> Dict[str, Any]:
        """品質設定を取得する"""
        config = self.DEFAULT_QUALITY_CONFIG.copy()
        config['is_hevc'] = self.encoding_task.codec == 'hevc'
        return config


    def __init__(self,
        input_file_path: str,
        output_file_path: str,
        codec: Literal['h264', 'hevc'],
        encoder_type: Literal['software', 'hardware'],
        quality_preset: str = 'medium',
        delete_original: bool = False
    ) -> None:
        """
        TSReplaceEncodingTaskのインスタンスを初期化する

        Args:
            input_file_path (str): 入力ファイルパス
            output_file_path (str): 出力ファイルパス
            codec (Literal['h264', 'hevc']): 使用するコーデック
            encoder_type (Literal['software', 'hardware']): エンコーダータイプ
            quality_preset (str): 品質プリセット
            delete_original (bool): 元ファイルを削除するかどうか

        Raises:
            RuntimeError: tsreplaceが利用できない場合
        """

        # tsreplaceが利用可能かチェック
        if not Path(self.TSREPLACE_PATH).is_file():
            raise RuntimeError(
                'tsreplace is not installed. '
                'Please install it to use TSReplace encoding feature. '
                f'For Ubuntu: wget https://github.com/rigaya/tsreplace/releases/download/{TSREPLACE_VERSION}/tsreplace_{TSREPLACE_VERSION}_Ubuntu22.04_amd64.deb && '
                f'sudo apt install ./tsreplace_{TSREPLACE_VERSION}_Ubuntu22.04_amd64.deb'
            )

        # エンコードタスク情報を作成
        self.encoding_task = EncodingTask(
            rec_file_id=0,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            codec=codec,
            encoder_type=encoder_type,
            quality_preset=quality_preset
        )
        self.delete_original = delete_original

        # エンコードプロセス
        self._tsreplace_process: asyncio.subprocess.Process | None = None

        # エンコード完了フラグ
        self._is_finished: bool = False

        # キャンセルフラグ
        self._is_cancelled: bool = False

        # ログディレクトリの設定
        self.log_dir = Path(LOGS_DIR) / 'tsreplace_encoding'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 各種ログファイルのパス
        self.encoding_log_path = self.log_dir / 'encoding.log'
        self.error_log_path = self.log_dir / 'error.log'
        self.encoding_json_log_path = self.log_dir / 'encoding.jsonl'
        self.error_json_log_path = self.log_dir / 'error.jsonl'


    def isFullHDChannel(self, network_id: int, service_id: int) -> bool:
        """
        ネットワーク ID とサービス ID から、そのチャンネルでフル HD 放送が行われているかを返す
        """
        # 地デジでフル HD 放送を行っているチャンネルのネットワーク ID と一致する
        if network_id in [31811, 31940, 32038, 32162, 32311, 32466]:
            return True
        # BS でフル HD 放送を行っているチャンネルのサービス ID と一致する
        if network_id == 0x0004 and service_id in [103, 191, 192, 193, 211]:
            return True
        # BS4K・CS4K は 4K 放送なのでフル HD 扱いとする
        if network_id == 0x000B or network_id == 0x000C:
            return True
        return False

    def _getEncoderPath(self) -> str:
        """
        設定に基づいてエンコーダーの実行ファイルパスを取得する

        Returns:
            str: エンコーダーの実行ファイルパス
        """
        try:
            config = Config()
            if self.encoding_task.encoder_type == 'software':
                # ソフトウェアエンコードの場合はFFmpegを使用
                encoder_name = 'FFmpeg'
            else:
                # ハードウェアエンコードの場合は設定から取得
                encoder_name = config.general.encoder

            return LIBRARY_PATH[encoder_name]
        except Exception as e:
            logging.warning(f'Failed to get encoder path, falling back to FFmpeg: {e}')
            return LIBRARY_PATH['FFmpeg']

    async def _updateProgressFromOutput(self, output_line: str) -> None:
        """エンコーダーの出力からプログレスを更新する（簡略化）"""
        if not output_line or not output_line.strip():
            return

        import re

        # 初期化
        current_time = time.time()
        if not hasattr(self, '_encoding_start_time'):
            self._encoding_start_time = current_time
            self._last_progress_update = current_time
            self._completion_detected = False
            if self.encoding_task.progress == 0.0:
                self.encoding_task.progress = 1.0

        # 完了検出
        completion_patterns = [r'encode completed', r'encoding finished', r'finished.*100%']
        for pattern in completion_patterns:
            if re.search(pattern, output_line, re.IGNORECASE):
                if not self._completion_detected:
                    self.encoding_task.progress = 100.0
                    self._completion_detected = True
                    logging.info('Encoding completion detected')
                    return

        # 進捗抽出
        progress_patterns = [
            r'frames:\s*(\d+)/(\d+)\s*\((\d+(?:\.\d+)?)%\)',
            r'\[(\d+(?:\.\d+)?)%\]',
            r'Progress:\s*(\d+(?:\.\d+)?)%',
            r'(\d+(?:\.\d+)?)%\s*complete'
        ]

        for pattern in progress_patterns:
            match = re.search(pattern, output_line, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) >= 3:
                        progress = float(match.group(3))
                    else:
                        progress = float(match.group(1))

                    self.encoding_task.progress = min(max(progress, 0.0), 100.0)
                    self._last_progress_update = current_time
                    return
                except (ValueError, IndexError):
                    continue

        # 時間ベースの推定進捗（パターンが一致しない場合）
        elapsed_time = current_time - self._encoding_start_time
        if elapsed_time > 5 and current_time - self._last_progress_update > 5:
            estimated_progress = min((elapsed_time / 3600) * 50, 95.0)  # 1時間で50%と仮定
            if estimated_progress > self.encoding_task.progress:
                self.encoding_task.progress = estimated_progress
                self._last_progress_update = current_time

    async def _getVideoDuration(self) -> float:
        """
        ffprobeを使用して動画の長さを取得する

        Returns:
            float: 動画の長さ（秒）、取得できない場合は0
        """
        try:
            # ffprobeコマンドを構築
            ffprobe_cmd = [
                LIBRARY_PATH['FFprobe'],
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                self.encoding_task.input_file_path
            ]

            # ffprobeを実行
            process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logging.warning(f'ffprobe failed to get duration: {stderr.decode("utf-8", errors="ignore") if stderr else "Unknown error"}')
                return 0

            # JSON出力をパース
            import json
            probe_data = json.loads(stdout.decode('utf-8'))

            duration_str = probe_data.get('format', {}).get('duration')
            if duration_str:
                duration = float(duration_str)
                logging.info(f'Video duration detected: {duration:.1f} seconds')
                return duration

        except Exception as e:
            logging.warning(f'Failed to get video duration: {e}')

        return 0

    async def _analyzeInputStreams(self, input_file_path: str) -> dict[str, Any]:
        """
        ffprobeを使用して入力ファイルのストリーム情報を解析する

        Args:
            input_file_path (str): 入力ファイルパス

        Returns:
            dict[str, Any]: ストリーム情報（video_count, audio_count, data_count）
        """
        try:
            # ffprobeコマンドを構築
            ffprobe_cmd = [
                LIBRARY_PATH['FFprobe'],
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                input_file_path
            ]

            # ffprobeを実行
            process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else 'Unknown ffprobe error'
                logging.warning(f'ffprobe failed: {error_msg}')
                # デフォルト値を返す（従来の動作）
                return {'video_count': 1, 'audio_count': 2, 'data_count': 1}

            # JSON出力をパース
            import json
            probe_data = json.loads(stdout.decode('utf-8'))

            # ストリーム数をカウント
            video_count = 0
            audio_count = 0
            data_count = 0

            for stream in probe_data.get('streams', []):
                codec_type = stream.get('codec_type', '').lower()
                if codec_type == 'video':
                    video_count += 1
                elif codec_type == 'audio':
                    audio_count += 1
                elif codec_type == 'data':
                    data_count += 1

            logging.info(f'Stream analysis result: video={video_count}, audio={audio_count}, data={data_count}')

            return {
                'video_count': video_count,
                'audio_count': audio_count,
                'data_count': data_count
            }

        except Exception as e:
            logging.warning(f'Failed to analyze input streams: {e}')
            # エラー時はデフォルト値を返す（従来の動作）
            return {'video_count': 1, 'audio_count': 2, 'data_count': 1}

    async def buildEncoderCommand(self) -> list[str]:
        """
        エンコーダーコマンドを生成する（LiveEncodingTaskのロジックを統合）

        Returns:
            list[str]: エンコーダーコマンドの配列
        """
        if self.encoding_task.encoder_type == 'software':
            return await self._buildFFmpegCommand()
        else:
            return await self._buildHardwareEncoderCommand()

    async def _buildFFmpegCommand(self) -> list[str]:
        """
        FFmpegエンコードコマンドを生成する（README.mdの例に基づく）
        """
        config = Config()
        is_hevc = self.encoding_task.codec == 'hevc'

        # 設定からカスタムオプションを取得
        if is_hevc:
            custom_options = config.tsreplace_encoding.ffmpeg_hevc_options
        else:
            custom_options = config.tsreplace_encoding.ffmpeg_h264_options

        if custom_options and custom_options.strip():
            # カスタムオプションがある場合はそれを使用
            return custom_options.split()
        else:
            # デフォルトオプション
            if is_hevc:
                # x265 の例
                return [
                    '-y', '-f', 'mpegts', '-i', '-', '-copyts', '-start_at_zero',
                    '-vf', 'yadif', '-an', '-c:v', 'libx265', '-preset', 'medium',
                    '-crf', '23', '-g', '90', '-f', 'mpegts', '-'
                ]
            else:
                # x264 の例
                return [
                    '-y', '-f', 'mpegts', '-i', '-', '-copyts', '-start_at_zero',
                    '-vf', 'yadif', '-an', '-c:v', 'libx264', '-preset', 'slow',
                    '-crf', '23', '-g', '90', '-f', 'mpegts', '-'
                ]

    async def _buildHardwareEncoderCommand(self) -> list[str]:
        """ハードウェアエンコードコマンドを生成する"""
        try:
            config = Config()
            encoder = config.general.encoder
        except:
            encoder = 'QSVEncC'

        if encoder == 'QSVEncC':
            return self._buildQSVEncCCommand()
        elif encoder == 'NVEncC':
            return self._buildNVEncCCommand()
        elif encoder == 'VCEEncC':
            return self._buildVCEEncCCommand()
        else:
            return await self._buildFFmpegCommand()

    def _buildQSVEncCCommand(self) -> list[str]:
        """QSVEncCエンコードコマンドを生成する（README.mdの例に基づく）"""
        config = Config()
        is_hevc = self.encoding_task.codec == 'hevc'

        # 設定からカスタムオプションを取得
        custom_options = config.tsreplace_encoding.intel_hevc_options if is_hevc else config.tsreplace_encoding.intel_h264_options

        if custom_options and custom_options.strip():
            # カスタムオプションがある場合はそれを使用
            return custom_options.split()
        else:
            # デフォルトオプション
            if is_hevc:
                # HEVC エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--tff', '--vpp-deinterlace', 'normal',
                    '-c', 'hevc', '--icq', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]
            else:
                # H.264 エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--tff', '--vpp-deinterlace', 'normal',
                    '-c', 'h264', '--icq', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]

    def _buildNVEncCCommand(self) -> list[str]:
        """
        NVEncCエンコードコマンドを生成する（README.mdの例に基づく）
        """
        config = Config()
        is_hevc = self.encoding_task.codec == 'hevc'

        # 設定からカスタムオプションを取得
        if is_hevc:
            custom_options = config.tsreplace_encoding.nvidia_hevc_options
        else:
            custom_options = config.tsreplace_encoding.nvidia_h264_options

        if custom_options and custom_options.strip():
            # カスタムオプションがある場合はそれを使用
            return custom_options.split()
        else:
            # デフォルトオプション
            if is_hevc:
                # HEVC エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--tff', '--vpp-deinterlace', 'normal',
                    '-c', 'hevc', '--qvbr', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]
            else:
                # H.264 エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--tff', '--vpp-deinterlace', 'normal',
                    '-c', 'h264', '--qvbr', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]

    def _buildVCEEncCCommand(self) -> list[str]:
        """
        VCEEncCエンコードコマンドを生成する（他のハードウェアエンコーダーと同様の形式）
        """
        config = Config()
        is_hevc = self.encoding_task.codec == 'hevc'

        # 設定からカスタムオプションを取得
        if is_hevc:
            custom_options = config.tsreplace_encoding.amd_hevc_options
        else:
            custom_options = config.tsreplace_encoding.amd_h264_options

        if custom_options and custom_options.strip():
            # カスタムオプションがある場合はそれを使用
            return custom_options.split()
        else:
            # デフォルトオプション
            if is_hevc:
                # HEVC エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--interlace', 'tff', '--vpp-afs',
                    '-c', 'hevc', '--cqp', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]
            else:
                # H.264 エンコード
                return [
                    '-i', '-', '--input-format', 'mpegts', '--interlace', 'tff', '--vpp-afs',
                    '-c', 'h264', '--cqp', '23', '--gop-len', '90', '--output-format', 'mpegts', '-o', '-'
                ]


    async def execute(self) -> bool:
        """エンコード処理を実行する（リトライ機能付き）"""
        from datetime import datetime
        self.encoding_task.started_at = datetime.now()
        self.encoding_task.status = 'processing'

        # エンコード中のファイルをトラッカーに追加
        from app.utils.EncodingFileTracker import EncodingFileTracker
        encoding_tracker = await EncodingFileTracker.getInstance()
        await encoding_tracker.addEncodingFile(self.encoding_task.output_file_path)

        self._logEncodingStart(self.encoding_task)

        try:
            while self.encoding_task.retry_count <= self.encoding_task.max_retry_count:
                try:
                    if not await self._prepareEncoding():
                        return False

                    success = await self._executeEncoding()

                    if success:
                        self.encoding_task.completed_at = datetime.now()
                        self.encoding_task.status = 'completed'
                        self.encoding_task.progress = 100.0
                        self._is_finished = True

                        # データベース更新
                        try:
                            await self._updateEncodedFlag()
                        except Exception as e:
                            logging.error(f'Post-processing failed: {e}')

                        # 完了処理
                        duration = (self.encoding_task.completed_at - self.encoding_task.started_at).total_seconds()
                        self.encoding_task.encoding_duration = duration
                        self._logEncodingComplete(self.encoding_task, True, duration)
                        await self._sendEncodingCompleteNotification()

                        logging.info(f'Encoding completed: {self.encoding_task.output_file_path}')
                        return True
                    else:
                        await self._handleEncodingFailure()
                        if not await self._shouldRetry():
                            break
                    await self._waitForRetry()

                except Exception as e:
                    await self._handleUnexpectedError(e)
                    if not await self._shouldRetry():
                        break
                    await self._waitForRetry()

            # すべてのリトライが失敗
            self.encoding_task.status = 'failed'
            self.encoding_task.completed_at = datetime.now()
            self.encoding_task.progress = 0.0

            await self._cleanupFailedEncoding()

            if not self._is_cancelled:
                await self._sendEncodingFailedNotification()
                self._logEncodingComplete(self.encoding_task, False)
                logging.error(f'Encoding failed after {self.encoding_task.retry_count} retries')

            return False

        finally:
            try:
                await encoding_tracker.removeEncodingFile(self.encoding_task.output_file_path)
            except Exception as e:
                logging.error(f'Failed to remove file from tracker: {e}')


    async def _prepareEncoding(self) -> bool:
        """
        エンコード前の準備処理を行う

        Returns:
            bool: 準備成功時True、失敗時False
        """

        try:
            # データベースレコードの事前確認（rec_file_idが0でない場合のみ）
            if self.encoding_task.rec_file_id > 0:
                try:
                    from app.models.RecordedVideo import RecordedVideo
                    original_video = await RecordedVideo.get(id=self.encoding_task.rec_file_id)
                    logging.info(f'Verified database record exists: RecordedVideo ID {self.encoding_task.rec_file_id}')
                    logging.debug(f'Original video file path: {original_video.file_path}')
                except Exception as e:
                    error_msg = f'Database record not found for RecordedVideo ID {self.encoding_task.rec_file_id}: {e}'
                    self.encoding_task.error_message = error_msg
                    logging.error(error_msg)
                    logging.error('This indicates the video record was deleted before encoding started')
                    return False
            else:
                logging.warning(f'rec_file_id is 0 or not set - skipping database verification')

            # 入力ファイルの存在確認
            if not os.path.exists(self.encoding_task.input_file_path):
                error_msg = f'Input file not found: {self.encoding_task.input_file_path}'
                self.encoding_task.error_message = error_msg
                logging.error(error_msg)
                return False

            # 入力ファイルサイズを記録
            self.encoding_task.original_file_size = os.path.getsize(self.encoding_task.input_file_path)

            # 出力ディレクトリの作成
            output_dir = os.path.dirname(self.encoding_task.output_file_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # ディスク容量の確認
            if not await self._checkDiskSpace():
                error_msg = f'Insufficient disk space for encoding: {self.encoding_task.output_file_path}'
                self.encoding_task.error_message = error_msg
                logging.error(error_msg)
                return False

            return True

        except Exception as e:
            error_msg = f'Preparation failed: {str(e)}'
            self.encoding_task.error_message = error_msg
            logging.error(error_msg, exc_info=True)
            return False


    async def _executeEncoding(self) -> bool:
        """
        実際のエンコード処理を実行する

        Returns:
            bool: エンコード成功時True、失敗時False
        """

        try:
            # エンコーダーの実行ファイルパスを取得
            encoder_path = self._getEncoderPath()

            # tsreplaceコマンドを構築
            encoder_command = await self.buildEncoderCommand()
            tsreplace_cmd = [
                self.TSREPLACE_PATH,
                '-i', self.encoding_task.input_file_path,
                '-o', self.encoding_task.output_file_path,
                '-e', encoder_path
            ] + encoder_command

            logging.info(f'Starting tsreplace encoding: {" ".join(tsreplace_cmd)}')

            # tsreplaceプロセスを開始
            self._tsreplace_process = await asyncio.create_subprocess_exec(
                *tsreplace_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # エンコーディング開始時に初期進捗を設定
            if self.encoding_task.progress == 0.0:
                self.encoding_task.progress = 1.0

                # ファイル情報を含む詳細なログ
                input_size_mb = self.encoding_task.original_file_size / (1024 * 1024) if self.encoding_task.original_file_size else 0
                codec_info = f"{self.encoding_task.codec.upper()}/{self.encoding_task.encoder_type}"

                logging.info(f'TSReplace encoding started [{codec_info}]: {os.path.basename(self.encoding_task.input_file_path)} ({input_size_mb:.1f}MB) -> {os.path.basename(self.encoding_task.output_file_path)}')

            # プロセスの出力を監視してプログレスを更新
            stdout_data = []
            stderr_data = []

            async def read_stdout():
                if self._tsreplace_process and self._tsreplace_process.stdout:
                    async for line in self._tsreplace_process.stdout:
                        if self._is_cancelled:
                            break
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:  # 空行をスキップ
                            stdout_data.append(line_str)
                            await self._updateProgressFromOutput(line_str)
                            if any(keyword in line_str.lower() for keyword in ['progress', '%', 'frame=', 'time=']):
                                logging.debug(f'Encoding output: {line_str}')

            async def read_stderr():
                if self._tsreplace_process and self._tsreplace_process.stderr:
                    async for line in self._tsreplace_process.stderr:
                        if self._is_cancelled:
                            break
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:  # 空行をスキップ
                            stderr_data.append(line_str)
                            await self._updateProgressFromOutput(line_str)
                            if any(keyword in line_str.lower() for keyword in ['progress', '%', 'frame=', 'time=']):
                                logging.debug(f'Encoding error output: {line_str}')

            # 出力読み取りタスクを開始
            stdout_task = asyncio.create_task(read_stdout())
            stderr_task = asyncio.create_task(read_stderr())

            # 定期的な進捗更新タスクを開始
            async def periodic_progress_update():
                start_time = time.time()
                last_update_time = start_time
                while self._tsreplace_process and self._tsreplace_process.returncode is None and not self._is_cancelled:
                    await asyncio.sleep(0.5)  # 0.5秒ごとに確認
                    current_time = time.time()
                    elapsed_time = current_time - start_time

                    # 時間ベースの進捗推定を定期的に更新
                    if current_time - last_update_time > 1.0:  # 1秒ごとに更新
                        # ファイルサイズに基づく推定処理時間
                        input_file_size = os.path.getsize(self.encoding_task.input_file_path) if os.path.exists(self.encoding_task.input_file_path) else 0
                        file_size_mb = input_file_size / (1024 * 1024) if input_file_size > 0 else 1

                        # より短い推定時間（MB当たり0.5-1秒、最低5秒）でより積極的な進捗表示
                        estimated_total_time = max(file_size_mb * 0.8, 5)
                        time_based_progress = min((elapsed_time / estimated_total_time) * 100, 95.0)

                        # 進捗が1%以上増加する場合、または初回の場合は更新
                        if (time_based_progress > self.encoding_task.progress + 1.0) or (elapsed_time > 1.0 and self.encoding_task.progress == 0.0):
                            self.encoding_task.progress = min(time_based_progress, 95.0)

                            # より詳細な情報を表示
                            codec_info = f"{self.encoding_task.codec.upper()}/{self.encoding_task.encoder_type}"
                            estimated_remaining = estimated_total_time - elapsed_time if estimated_total_time > elapsed_time else 0
                            eta_str = f", ETA: {estimated_remaining:.0f}s" if estimated_remaining > 0 else ""

                            logging.info(f'TSReplace progress: {self.encoding_task.progress:.1f}% (elapsed: {elapsed_time:.1f}s{eta_str}) [{codec_info}] - {os.path.basename(self.encoding_task.input_file_path)}')
                            last_update_time = current_time

            progress_update_task = asyncio.create_task(periodic_progress_update())

            # プロセスの完了を待機
            await self._tsreplace_process.wait()

            # すべてのタスクの完了を待機
            progress_update_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            stderr = b'\n'.join(line.encode('utf-8') for line in stderr_data)

            # 結果を確認
            if self._tsreplace_process.returncode == 0:
                # エンコード成功時にプログレスを100%に設定
                self.encoding_task.progress = 100.0

                # エンコード後のファイルサイズを記録
                if os.path.exists(self.encoding_task.output_file_path):
                    self.encoding_task.encoded_file_size = os.path.getsize(self.encoding_task.output_file_path)

                    # 圧縮率を計算
                    compression_ratio = 0.0
                    if self.encoding_task.original_file_size and self.encoding_task.encoded_file_size:
                        compression_ratio = (1 - self.encoding_task.encoded_file_size / self.encoding_task.original_file_size) * 100

                    # 詳細な完了ログ
                    original_mb = self.encoding_task.original_file_size / (1024 * 1024) if self.encoding_task.original_file_size else 0
                    encoded_mb = self.encoding_task.encoded_file_size / (1024 * 1024)
                    codec_info = f"{self.encoding_task.codec.upper()}/{self.encoding_task.encoder_type}"

                    logging.info(f'TSReplace encoding completed [{codec_info}]: {os.path.basename(self.encoding_task.output_file_path)} - {original_mb:.1f}MB -> {encoded_mb:.1f}MB (compression: {compression_ratio:.1f}%)')
                else:
                    logging.info(f'TSReplace encoding process completed successfully. Progress set to 100.0%')

                # エンコード後の処理を実行
                post_process_success = await self._processEncodedFile()
                if post_process_success:
                    return True
                else:
                    self.encoding_task.error_message = 'Post-processing failed'
                    logging.error(f'Post-processing failed for: {self.encoding_task.output_file_path}')
                    logging.error(f'Original video ID: {self.encoding_task.rec_file_id}')
                    logging.error(f'Output file path: {self.encoding_task.output_file_path}')
                    logging.error(f'Codec: {self.encoding_task.codec}, Encoder: {self.encoding_task.encoder_type}')
                    logging.error(f'Delete original: {self.delete_original}')
                    return False
            else:
                # エラーメッセージを記録
                error_msg = f'TSReplace encoding failed with return code {self._tsreplace_process.returncode}'
                if stderr:
                    stderr_text = stderr.decode("utf-8", errors="ignore")
                    error_msg += f': {stderr_text}'

                    # PMT変更やストリーム構成変化に関連するエラーを特定
                    if 'PMT' in stderr_text or 'version' in stderr_text:
                        error_msg += ' [PMT version change detected]'
                    if 'storage->SetProperty' in stderr_text:
                        error_msg += ' [VCEEncC parameter error detected]'
                    if 'invalid param' in stderr_text:
                        error_msg += ' [Invalid parameter error - may be resolved with retry]'
                    if 'Stream mapping failed' in stderr_text or 'Cannot find stream' in stderr_text:
                        error_msg += ' [FFmpeg stream mapping error - may be resolved with retry]'
                    if 'Invalid data found when processing input' in stderr_text:
                        error_msg += ' [Input data error - may be resolved with retry]'
                    if 'Invalid frame dimensions' in stderr_text:
                        error_msg += ' [Frame dimension error - may be resolved with retry]'
                    if 'Option.*cannot be applied' in stderr_text or 'Error parsing options' in stderr_text:
                        error_msg += ' [FFmpeg option error - may be resolved with retry]'

                self.encoding_task.error_message = error_msg

                # 詳細なエラーログ
                codec_info = f"{self.encoding_task.codec.upper()}/{self.encoding_task.encoder_type}"
                logging.error(f'TSReplace encoding failed [{codec_info}]: {os.path.basename(self.encoding_task.input_file_path)} - {error_msg}')

                if ('PMT' in error_msg or 'storage->SetProperty' in error_msg or
                    'invalid param' in error_msg or 'Stream mapping failed' in error_msg or
                    'Cannot find stream' in error_msg or 'Invalid data found' in error_msg or
                    'Invalid frame dimensions' in error_msg or 'Error parsing options' in error_msg):
                    logging.warning(f'Detected potentially recoverable error for {os.path.basename(self.encoding_task.input_file_path)} - encoding may succeed on retry')

                return False

        except Exception as e:
            error_msg = f'Encoding execution failed: {str(e)}'
            self.encoding_task.error_message = error_msg
            logging.error(error_msg, exc_info=True)
            return False
        finally:
            # プロセスのクリーンアップ
            await self._cleanupProcess()


    async def _checkDiskSpace(self) -> bool:
        """
        ディスク容量をチェックする

        Returns:
            bool: 十分な容量がある場合True
        """

        try:
            import shutil

            # 出力ディレクトリの空き容量を取得
            output_dir = os.path.dirname(self.encoding_task.output_file_path)
            free_space = shutil.disk_usage(output_dir).free

            # 入力ファイルサイズの2倍の容量があるかチェック（安全マージン）
            required_space = (self.encoding_task.original_file_size or 0) * 2

            return free_space > required_space

        except Exception as e:
            logging.warning(f'Failed to check disk space: {e}')
            # チェックに失敗した場合は続行を許可
            return True


    async def _handleEncodingFailure(self) -> None:
        """
        エンコード失敗時の処理を行う（リトライ中の個別失敗処理）
        """

        try:
            # エラーを処理
            error_exception = Exception(self.encoding_task.error_message or 'Unknown encoding error')
            _, processed_error_msg = await self._handleEncodingError(
                self.encoding_task,
                error_exception
            )

            # 処理されたエラーメッセージを更新
            if processed_error_msg:
                self.encoding_task.error_message = processed_error_msg

            # リトライ中は詳細ログのみ記録（最終失敗時は別途記録）
            logging.warning(f'Encoding attempt failed for task {self.encoding_task.task_id}, retry {self.encoding_task.retry_count}: {self.encoding_task.error_message}')

        except Exception as e:
            logging.error(f'Error handling encoding failure: {e}', exc_info=True)


    async def _handleUnexpectedError(self, error: Exception) -> None:
        """
        予期しないエラーの処理を行う

        Args:
            error (Exception): 発生したエラー
        """

        try:
            # エラーメッセージを記録
            self.encoding_task.error_message = f'Unexpected error: {str(error)}'

            # エラーを処理
            _, processed_error_msg = await self._handleEncodingError(
                self.encoding_task,
                error
            )

            # 処理されたエラーメッセージを更新
            if processed_error_msg:
                self.encoding_task.error_message = processed_error_msg

            # エラーをログに記録
            error_category = self._categorizeError(self.encoding_task.error_message or '')
            self._logEncodingError(self.encoding_task, error, error_category)

            logging.error(f'Unexpected error in task {self.encoding_task.task_id}: {self.encoding_task.error_message}', exc_info=True)

        except Exception as e:
            logging.error(f'Error handling unexpected error: {e}', exc_info=True)


    async def _shouldRetry(self) -> bool:
        """
        リトライすべきかを判定する

        Returns:
            bool: リトライする場合True
        """

        try:
            # キャンセルされている場合はリトライしない
            if self._is_cancelled:
                return False

            # リトライ判定
            error_category = self._categorizeError(self.encoding_task.error_message or '')
            should_retry = self._isRetryable(
                error_category,
                self.encoding_task.retry_count,
                self.encoding_task.max_retry_count
            )

            if should_retry:
                self.encoding_task.retry_count += 1
                logging.info(f'Task {self.encoding_task.task_id} will be retried (attempt {self.encoding_task.retry_count}/{self.encoding_task.max_retry_count})')
            else:
                logging.info(f'Task {self.encoding_task.task_id} will not be retried (category: {error_category}, retry_count: {self.encoding_task.retry_count})')

            return should_retry

        except Exception as e:
            logging.error(f'Error determining retry: {e}', exc_info=True)
            return False


    async def _waitForRetry(self) -> None:
        """
        リトライ前の待機処理を行う
        """

        try:
            # エラーカテゴリに基づいて待機時間を決定
            error_category = self._categorizeError(self.encoding_task.error_message or '')
            delay = self._getRetryDelay(error_category, self.encoding_task.retry_count - 1)

            logging.info(f'Waiting {delay} seconds before retry for task {self.encoding_task.task_id}')
            await asyncio.sleep(delay)

        except Exception as e:
            logging.error(f'Error during retry wait: {e}', exc_info=True)
            # デフォルトの待機時間
            await asyncio.sleep(10)


    async def _cleanupFailedEncoding(self) -> None:
        """
        失敗したエンコードのクリーンアップを行う
        """

        try:
            # クリーンアップ処理
            await self._cleanupFailedEncodingFiles(self.encoding_task)

            # プロセスのクリーンアップ
            await self._cleanupProcess()

            logging.info(f'Cleanup completed for failed task: {self.encoding_task.task_id}')

        except Exception as e:
            logging.error(f'Error during cleanup for task {self.encoding_task.task_id}: {e}', exc_info=True)


    async def _cleanupProcess(self) -> None:
        """
        プロセスのクリーンアップを行う
        """

        if self._tsreplace_process and self._tsreplace_process.returncode is None:
            try:
                self._tsreplace_process.terminate()
                await asyncio.wait_for(self._tsreplace_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logging.warning('TSReplace process did not terminate gracefully, killing it')
                self._tsreplace_process.kill()
                await self._tsreplace_process.wait()


    async def cancel(self) -> None:
        """
        エンコード処理をキャンセルする
        """

        self._is_cancelled = True
        self.encoding_task.status = 'cancelled'

        if self._tsreplace_process and self._tsreplace_process.returncode is None:
            try:
                logging.info(f'Cancelling TSReplace encoding process for task: {self.encoding_task.task_id}')
                self._tsreplace_process.terminate()
                await asyncio.wait_for(self._tsreplace_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logging.warning('TSReplace process did not terminate gracefully, killing it')
                self._tsreplace_process.kill()
                await self._tsreplace_process.wait()

        # キャンセル時のクリーンアップ
        await self._cleanupFailedEncoding()

        # キャンセル時にもトラッカーからファイルを除去
        try:
            from app.utils.EncodingFileTracker import EncodingFileTracker
            encoding_tracker = await EncodingFileTracker.getInstance()
            logging.info(f'Removing cancelled file from encoding tracker: {self.encoding_task.output_file_path}')
            await encoding_tracker.removeEncodingFile(self.encoding_task.output_file_path)
        except Exception as e:
            logging.error(f'Failed to remove cancelled file from encoding tracker: {e}', exc_info=True)

        logging.info(f'TSReplace encoding cancelled for task: {self.encoding_task.task_id}')


    @property
    def is_finished(self) -> bool:
        """エンコード完了状態を取得"""
        return self._is_finished


    @property
    def is_cancelled(self) -> bool:
        """キャンセル状態を取得"""
        return self._is_cancelled

    # ===== エラーハンドリング機能（統合） =====

    def _categorizeError(self, error_message: str) -> str:
        """エラーメッセージを分類する"""
        if not error_message:
            return 'UNKNOWN'

        error_message_lower = error_message.lower()

        # 各カテゴリのパターンをチェック
        for category, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern.lower(), error_message_lower):
                    return category

        return 'UNKNOWN'

    def _isRetryable(self, error_category: str, retry_count: int, max_retries: int = 3) -> bool:
        """エラーがリトライ可能かを判定する"""
        if retry_count >= max_retries:
            return False
        return error_category in self.RETRYABLE_CATEGORIES

    def _getRetryDelay(self, error_category: str, retry_count: int) -> int:
        """リトライまでの遅延時間を取得する"""
        base_delays = {
            'RESOURCE': 30,
            'NETWORK': 10,
            'ENCODER': 5,
            'PROCESS': 15,
            'STREAM_CHANGE': 5,
            'VCEENCC_PARAM': 3,
            'FFMPEG_STREAM': 3,
        }
        base_delay = base_delays.get(error_category, 10)
        delay = min(base_delay * (2 ** retry_count), 300)
        return delay

    async def _handleEncodingError(self, task: EncodingTask, error: Exception) -> Tuple[bool, str]:
        """エンコードエラーを処理し、適切な対応を決定する"""
        error_message = str(error)
        error_category = self._categorizeError(error_message)

        logging.error(f'Encoding error for task {task.task_id}: {error_message}')
        logging.error(f'Error category: {error_category}')

        should_retry = self._isRetryable(error_category, task.retry_count, task.max_retry_count)

        if should_retry:
            retry_delay = self._getRetryDelay(error_category, task.retry_count)
            logging.info(f'Task {task.task_id} will be retried in {retry_delay} seconds')
        else:
            logging.error(f'Task {task.task_id} will not be retried (category: {error_category}, retry_count: {task.retry_count})')

        return should_retry, error_message

    async def _cleanupFailedEncodingFiles(self, task: EncodingTask) -> None:
        """失敗したエンコードのクリーンアップを行う"""
        try:
            # 不完全な出力ファイルを削除
            if task.output_file_path and os.path.exists(task.output_file_path):
                try:
                    file_size = os.path.getsize(task.output_file_path)
                    if file_size < 1024:  # 1KB未満の場合は不完全とみなす
                        os.remove(task.output_file_path)
                        logging.info(f'Removed incomplete output file: {task.output_file_path} (size: {file_size} bytes)')
                    else:
                        logging.warning(f'Output file exists but may be incomplete: {task.output_file_path} (size: {file_size} bytes)')
                except Exception as e:
                    logging.warning(f'Failed to remove incomplete output file {task.output_file_path}: {e}')

            # 一時ファイルのクリーンアップ
            temp_files = [
                task.output_file_path + '.tmp',
                task.output_file_path + '.part',
                task.output_file_path + '.temp',
                task.output_file_path + '.lock'
            ]

            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logging.info(f'Removed temporary file: {temp_file}')
                    except Exception as e:
                        logging.warning(f'Failed to remove temporary file {temp_file}: {e}')

        except Exception as e:
            logging.error(f'Error during cleanup for task {task.task_id}: {e}', exc_info=True)

    # ===== ログ機能（統合） =====

    def _logEncodingStart(self, task: EncodingTask) -> None:
        """エンコード開始をログに記録する"""
        try:
            message = f'Encoding started - Task: {task.task_id}, Codec: {task.codec}, Encoder: {task.encoder_type}'
            logging.info(message)
        except Exception as e:
            logging.error(f'Failed to log encoding start: {e}')

    async def _updateEncodedFlag(self) -> None:
        """
        エンコード完了後にデータベースの再エンコード済みフラグを更新し、メタデータ解析を実行する
        """
        try:
            if self.encoding_task.rec_file_id > 0:
                from app.models.RecordedVideo import RecordedVideo
                from app.metadata.KeyFrameAnalyzer import KeyFrameAnalyzer
                from app.metadata.CMSectionsDetector import CMSectionsDetector

                # データベースレコードを取得
                recorded_video = await RecordedVideo.get(id=self.encoding_task.rec_file_id)

                # 元のファイルパスを記録（ログ用）
                original_file_path = recorded_video.file_path
                logging.info(f'Updating RecordedVideo ID {self.encoding_task.rec_file_id}: original_path={original_file_path}, current_encoded_flag={recorded_video.is_tsreplace_encoded}')

                # 再エンコード済みフラグを更新
                recorded_video.is_tsreplace_encoded = True
                recorded_video.tsreplace_encoded_at = datetime.now()

                # 元の映像コーデックを保存（まだ設定されていない場合のみ）
                if recorded_video.original_video_codec is None:
                    recorded_video.original_video_codec = recorded_video.video_codec

                # エンコード後のコーデック情報を更新
                old_codec = recorded_video.video_codec
                if self.encoding_task.codec == 'h264':
                    recorded_video.video_codec = 'H.264'
                elif self.encoding_task.codec == 'hevc':
                    recorded_video.video_codec = 'H.265'

                # エンコード済みファイルのパスを専用フィールドに保存（file_pathは元のままにする）
                recorded_video.encoded_file_path = str(self.encoding_task.output_file_path)

                # file_size と file_modified_at は元のファイル情報を保持する
                # エンコード済みファイルのサイズは別途必要に応じて取得
                # （クライアント側での表示は元のファイル情報を使用することが一般的）

                logging.info(f'About to save: ID={recorded_video.id}, is_encoded={recorded_video.is_tsreplace_encoded}, codec={old_codec}->{recorded_video.video_codec}, path={original_file_path}->{self.encoding_task.output_file_path}')

                # データベースに保存
                await recorded_video.save()

                # 保存後の確認
                logging.info(f'Successfully saved RecordedVideo ID {self.encoding_task.rec_file_id} with encoded flag')

                # 保存されたかどうかを再確認
                verification_record = await RecordedVideo.get(id=self.encoding_task.rec_file_id)
                logging.info(f'Verification: ID={verification_record.id}, is_encoded={verification_record.is_tsreplace_encoded}, path={verification_record.file_path}')
                logging.info(f'Updated encoded flag for RecordedVideo ID {self.encoding_task.rec_file_id}')
                logging.info(f'Set is_tsreplace_encoded=True, video_codec={recorded_video.video_codec}, original_video_codec={recorded_video.original_video_codec}')

                # エンコード済みファイルのメタデータ解析を実行
                try:
                    output_file_path = Path(self.encoding_task.output_file_path)
                    logging.info(f'Analyzing metadata for encoded file: {self.encoding_task.output_file_path}')

                    # キーフレーム情報とCM区間情報を個別に解析（一つが失敗しても他に影響しないように）
                    try:
                        # エンコード済みファイルのキーフレーム情報を解析し DB に保存
                        await KeyFrameAnalyzer(output_file_path, recorded_video.container_format).analyzeAndSave()
                        logging.info(f'KeyFrame analysis completed for: {self.encoding_task.output_file_path}')
                    except Exception as keyframe_error:
                        logging.warning(f'KeyFrame analysis failed for encoded file: {keyframe_error}', exc_info=True)

                    try:
                        # エンコード済みファイルの CM 区間を検出し DB に保存
                        await CMSectionsDetector(output_file_path, recorded_video.duration).detectAndSave()
                        logging.info(f'CM detection completed for: {self.encoding_task.output_file_path}')
                    except Exception as cm_error:
                        logging.warning(f'CM detection failed for encoded file: {cm_error}', exc_info=True)

                    logging.info(f'Completed metadata analysis for encoded file: {self.encoding_task.output_file_path}')

                except Exception as metadata_error:
                    # メタデータ解析エラーは致命的ではないので警告レベル
                    logging.error(f'Failed to analyze encoded file metadata: {self.encoding_task.output_file_path}')
                    logging.warning(f'Failed to analyze metadata for encoded file: {metadata_error}', exc_info=True)
                    # メタデータ解析の失敗をキャッチして再度例外を投げる
                    raise Exception(f'Post-processing failed')

            else:
                logging.warning(f'Cannot update encoded flag - rec_file_id is 0 or not set')

        except Exception as e:
            logging.error(f'Failed to update encoded flag: {e}', exc_info=True)

    def _logEncodingComplete(self, task: EncodingTask, success: bool, duration: Optional[float] = None) -> None:
        """エンコード完了をログに記録する"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'encoding_complete',
                'task_id': task.task_id,
                'success': success,
                'status': task.status,
                'input_file': task.input_file_path,
                'output_file': task.output_file_path,
                'codec': task.codec,
                'encoder_type': task.encoder_type,
                'original_file_size': task.original_file_size,
                'encoded_file_size': task.encoded_file_size,
                'encoding_duration': duration or task.encoding_duration,
                'retry_count': task.retry_count,
                'compression_ratio': None
            }

            if task.original_file_size and task.encoded_file_size:
                log_entry['compression_ratio'] = task.encoded_file_size / task.original_file_size

            status_text = 'completed successfully' if success else 'failed'
            encoding_duration = duration or task.encoding_duration or 0.0
            message = f'Encoding {status_text} - Task: {task.task_id}, Duration: {encoding_duration:.2f}s'
            if log_entry['compression_ratio']:
                message += f', Compression: {log_entry["compression_ratio"]:.2%}'

            log_level = 'INFO' if success else 'ERROR'
            self._writeTextLog(self.encoding_log_path, log_level, message)
            self._writeJsonLog(self.encoding_json_log_path, log_entry)

            if success:
                logging.info(f'TSReplace encoding completed: {task.task_id}')
            else:
                logging.error(f'TSReplace encoding failed: {task.task_id}')

        except Exception as e:
            logging.error(f'Failed to log encoding completion: {e}', exc_info=True)

    def _logEncodingError(self, task: EncodingTask, error: Exception, error_category: Optional[str] = None) -> None:
        """エンコードエラーをログに記録する"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'encoding_error',
                'task_id': task.task_id,
                'error_message': str(error),
                'error_type': type(error).__name__,
                'error_category': error_category,
                'input_file': task.input_file_path,
                'output_file': task.output_file_path,
                'codec': task.codec,
                'encoder_type': task.encoder_type,
                'retry_count': task.retry_count,
                'max_retry_count': task.max_retry_count,
                'status': task.status
            }

            message = f'Encoding error - Task: {task.task_id}, Error: {str(error)}'
            if error_category:
                message += f', Category: {error_category}'
            message += f', Retry: {task.retry_count}/{task.max_retry_count}'

            self._writeTextLog(self.error_log_path, 'ERROR', message)
            self._writeJsonLog(self.error_json_log_path, log_entry)
            logging.error(f'TSReplace encoding error: {task.task_id} - {str(error)}', exc_info=True)

        except Exception as e:
            logging.error(f'Failed to log encoding error: {e}', exc_info=True)

    def _writeTextLog(self, log_path: Path, level: str, message: str) -> None:
        """テキスト形式のログを書き込む"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_line = f'[{timestamp}] [{level}] {message}\n'

            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)

        except Exception as e:
            logging.error(f'Failed to write text log to {log_path}: {e}')

    def _writeJsonLog(self, log_path: Path, log_entry: Dict[str, Any]) -> None:
        """JSON形式のログを書き込む（JSONL形式）"""
        try:
            json_line = json.dumps(log_entry, ensure_ascii=False, default=str) + '\n'

            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json_line)

        except Exception as e:
            logging.error(f'Failed to write JSON log to {log_path}: {e}')

    # ===== ポストプロセッシング機能（統合） =====

    async def _processEncodedFile(self) -> bool:
        """エンコード後のファイル処理を実行する（簡略化版：元ファイルのメタデータをそのまま使用）"""
        try:
            # 元の録画ファイル情報を取得
            original_video = None
            try:
                original_video = await RecordedVideo.get(id=self.encoding_task.rec_file_id)
                logging.debug(f'Found original video: ID {self.encoding_task.rec_file_id}, Path: {original_video.file_path}')
            except Exception as e:
                logging.error(f'Original video not found: ID {self.encoding_task.rec_file_id}, Error: {e}')
                return False

            # 出力ファイルの存在確認
            if not os.path.exists(self.encoding_task.output_file_path):
                logging.error(f'Output file not found: {self.encoding_task.output_file_path}')
                return False

            # 出力ファイルのサイズを確認
            output_file_size = os.path.getsize(self.encoding_task.output_file_path)
            logging.info(f'Output file size: {output_file_size} bytes ({output_file_size / (1024*1024):.2f} MB)')

            if output_file_size < 1024 * 1024:  # 1MB未満
                logging.warning(f'Output file size is unusually small: {output_file_size} bytes')

            # ファイルが完全に書き込まれるまで待機
            await self._waitForFileCompletion()

            # エンコード済みファイルを適切なフォルダに移動
            final_output_path = await self._moveEncodedFileToDestination()
            if not final_output_path:
                logging.error(f'Failed to move encoded file to destination')
                return False

            # データベースを簡略更新（元ファイルのメタデータを保持）
            if original_video is not None:
                # 元ファイルパスを削除処理のために保存
                original_file_path_for_deletion = original_video.file_path

                logging.info(f'Updating database with TSReplace encoding information (preserving original metadata)')
                success = await self._updateDatabaseSimple(original_video, final_output_path)
                if not success:
                    logging.error(f'Failed to update database with encoded file information')
                    return False

                # サムネイル処理：元ファイルと同じ内容なので既存サムネイルをそのまま使用
                logging.info(f'Using existing thumbnails from original file (no regeneration needed)')

                # 元ファイルの削除・保持処理
                if self.delete_original:
                    await self._deleteOriginalFile(original_file_path_for_deletion)
                else:
                    logging.info(f'Original file preserved: {original_file_path_for_deletion}')

                # エンコード完了をログに記録
                logging.info(f'TSReplace encoding completed successfully. Original: {original_file_path_for_deletion} -> Encoded: {final_output_path}')
            else:
                logging.warning(f'Skipping database update due to missing original video record')
                logging.info(f'Encoded file created successfully: {final_output_path}')

                if self.delete_original:
                    logging.warning(f'Cannot delete original file - original video record not found')

            logging.info(f'Post-processing completed successfully for: {final_output_path}')
            return True

        except Exception as e:
            logging.error(f'Post-processing error: {e}', exc_info=True)
            return False

    async def _updateDatabaseSimple(self, original_video: RecordedVideo, encoded_file_path: str) -> bool:
        """データベースを簡略更新（元ファイルのメタデータを保持してTSReplaceエンコード情報のみ更新）"""
        try:
            # 元の映像コーデックを保存（まだ設定されていない場合のみ）
            if not original_video.is_tsreplace_encoded:
                original_video.original_video_codec = original_video.video_codec

            # TSReplace エンコード情報を記録
            original_video.is_tsreplace_encoded = True
            original_video.tsreplace_encoded_at = datetime.now()
            original_video.encoded_file_path = encoded_file_path

            # 映像コーデック情報のみ更新（エンコード設定に基づく）
            if self.encoding_task.codec == 'h264':
                original_video.video_codec = 'H.264'
            elif self.encoding_task.codec == 'hevc':
                original_video.video_codec = 'H.265'

            # その他の元ファイル情報（解像度、フレームレート、音声、時間情報など）はそのまま保持
            # キーフレーム情報とCM区間情報も保持（再エンコードしても映像内容は同じため）

            # データベースに保存
            await original_video.save()

            logging.info(f'Database updated successfully for video ID: {original_video.id}')
            logging.info(f'Set is_tsreplace_encoded=True, video_codec={original_video.video_codec}, original_video_codec={original_video.original_video_codec}')
            return True

        except Exception as e:
            logging.error(f'Database update error: {e}', exc_info=True)
            return False

    async def _deleteOriginalFile(self, original_file_path: str) -> None:
        """元ファイルを安全に削除する"""
        try:
            if os.path.exists(original_file_path):
                os.remove(original_file_path)
                logging.info(f'Original file deleted: {original_file_path}')

                # 関連ファイルも削除
                for ext in ['.program.txt', '.err']:
                    related_file = original_file_path + ext
                    if os.path.exists(related_file):
                        os.remove(related_file)
                        logging.info(f'Related file deleted: {related_file}')
            else:
                logging.warning(f'Original file not found for deletion: {original_file_path}')

        except Exception as e:
            logging.error(f'Failed to delete original file: {e}', exc_info=True)

    async def _waitForFileCompletion(self) -> None:
        """ファイルが完全に書き込まれるまで待機する"""
        try:
            max_wait_time = 30
            check_interval = 1
            stable_duration = 3

            start_time = time.time()
            last_size = 0
            stable_start_time = None

            while time.time() - start_time < max_wait_time:
                if not os.path.exists(self.encoding_task.output_file_path):
                    await asyncio.sleep(check_interval)
                    continue

                current_size = os.path.getsize(self.encoding_task.output_file_path)

                if current_size == last_size and current_size > 0:
                    if stable_start_time is None:
                        stable_start_time = time.time()
                    elif time.time() - stable_start_time >= stable_duration:
                        logging.debug(f'File appears to be complete: {self.encoding_task.output_file_path} (size: {current_size} bytes)')
                        return
                else:
                    stable_start_time = None
                    last_size = current_size

                await asyncio.sleep(check_interval)

            logging.warning(f'File completion wait timed out for: {self.encoding_task.output_file_path}')

        except Exception as e:
            logging.warning(f'Error waiting for file completion: {e}')

    async def _moveEncodedFileToDestination(self) -> str | None:
        """エンコード済みファイルを適切なフォルダに移動する"""
        try:
            config = Config()
            encoded_folder = config.tsreplace_encoding.encoded_folder

            # 設定でEncodedフォルダが指定されていない場合、録画フォルダ内にEncodedフォルダを自動作成
            if not encoded_folder:
                # 元ファイルの場所を取得
                original_file_path = Path(self.encoding_task.output_file_path)

                # recorded_foldersから適切なフォルダを選択
                recorded_folders = config.server.video.recorded_folders
                if recorded_folders:
                    # 元ファイルが存在する録画フォルダを探す
                    selected_folder = None
                    for folder in recorded_folders:
                        try:
                            # 元ファイルのパスが録画フォルダ配下にあるかチェック
                            original_file_path.relative_to(folder)
                            selected_folder = folder
                            break
                        except ValueError:
                            continue

                    # 適切なフォルダが見つからない場合は最初の録画フォルダを使用
                    if not selected_folder:
                        selected_folder = recorded_folders[0]

                    # Encodedサブフォルダを作成
                    encoded_folder = str(Path(selected_folder) / "Encoded")
                    logging.info(f'Auto-creating Encoded folder: {encoded_folder}')
                else:
                    # 録画フォルダが設定されていない場合は元の場所に保持
                    logging.info(f'No recorded folders configured, keeping file in original location: {self.encoding_task.output_file_path}')
                    return self.encoding_task.output_file_path

            logging.info(f'Encoded folder target: {encoded_folder}')

            # Encodedフォルダが存在しない場合は作成
            encoded_folder_path = Path(encoded_folder)
            encoded_folder_path.mkdir(parents=True, exist_ok=True)

            # 移動先のファイルパスを生成
            original_file = Path(self.encoding_task.output_file_path)
            destination_file = encoded_folder_path / original_file.name

            # 同名ファイルが存在する場合は番号を付ける
            counter = 1
            while destination_file.exists():
                stem = original_file.stem
                suffix = original_file.suffix
                destination_file = encoded_folder_path / f"{stem}_{counter}{suffix}"
                counter += 1

            # ファイルを移動
            logging.info(f'Moving encoded file from {self.encoding_task.output_file_path} to {destination_file}')
            shutil.move(str(self.encoding_task.output_file_path), str(destination_file))

            logging.info(f'Successfully moved encoded file to: {destination_file}')
            return str(destination_file)

        except Exception as e:
            logging.error(f'Failed to move encoded file: {e}', exc_info=True)
            return None

    async def _sendEncodingCompleteNotification(self) -> None:
        """エンコード完了通知をWebSocketで送信する"""
        try:
            # 番組タイトルを取得
            video_title = 'Unknown Video'
            try:
                if self.encoding_task.rec_file_id > 0:
                    from app.models.RecordedProgram import RecordedProgram
                    recorded_program = await RecordedProgram.get(id=self.encoding_task.rec_file_id)
                    video_title = recorded_program.title or 'Unknown Video'
            except Exception as e:
                logging.warning(f'Failed to get video title for notification: {e}')

            # 完了通知メッセージを作成
            notification = {
                'type': 'encoding_complete',
                'task_id': self.encoding_task.task_id,
                'video_id': self.encoding_task.rec_file_id,
                'video_title': video_title,
                'codec': self.encoding_task.codec.upper(),
                'encoder_type': 'ハードウェア' if self.encoding_task.encoder_type == 'hardware' else 'ソフトウェア',
                'message': f'「{video_title}」のエンコード（{self.encoding_task.codec.upper()}）が完了しました。',
                'output_file': str(self.encoding_task.output_file_path),
                'duration': getattr(self.encoding_task, 'encoding_duration', 0)
            }

            # WebSocket経由で通知を送信
            try:
                from app.routers.TSReplaceRouter import manager
                await manager.broadcast_json(notification)
                logging.info(f'Sent encoding complete notification for task {self.encoding_task.task_id}')
            except Exception as ws_error:
                logging.warning(f'Failed to send WebSocket notification: {ws_error}')

        except Exception as e:
            logging.error(f'Failed to send encoding complete notification: {e}', exc_info=True)

    async def _sendEncodingFailedNotification(self) -> None:
        """エンコード失敗通知をWebSocketで送信する"""
        try:
            # キャンセルされた場合は通知を送信しない
            if self._is_cancelled:
                logging.debug(f'Skipping failed notification for cancelled task: {self.encoding_task.task_id}')
                return

            # 番組タイトルを取得
            video_title = 'Unknown Video'
            try:
                if self.encoding_task.rec_file_id > 0:
                    from app.models.RecordedProgram import RecordedProgram
                    recorded_program = await RecordedProgram.get(id=self.encoding_task.rec_file_id)
                    video_title = recorded_program.title or 'Unknown Video'
            except Exception as e:
                logging.warning(f'Failed to get video title for notification: {e}')

            # 失敗通知メッセージを作成
            error_message = self.encoding_task.error_message or 'エンコード処理中にエラーが発生しました'
            notification = {
                'type': 'encoding_failed',
                'task_id': self.encoding_task.task_id,
                'video_id': self.encoding_task.rec_file_id,
                'video_title': video_title,
                'codec': self.encoding_task.codec.upper(),
                'encoder_type': 'ハードウェア' if self.encoding_task.encoder_type == 'hardware' else 'ソフトウェア',
                'message': f'「{video_title}」のエンコード（{self.encoding_task.codec.upper()}）が失敗しました。',
                'error_message': error_message,
                'retry_count': self.encoding_task.retry_count
            }

            # WebSocket経由で通知を送信
            try:
                from app.routers.TSReplaceRouter import manager
                await manager.broadcast_json(notification)
                logging.info(f'Sent encoding failed notification for task {self.encoding_task.task_id}')
            except Exception as ws_error:
                logging.warning(f'Failed to send WebSocket notification: {ws_error}')

        except Exception as e:
            logging.error(f'Failed to send encoding failed notification: {e}', exc_info=True)
