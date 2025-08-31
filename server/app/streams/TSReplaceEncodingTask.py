# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple
from zoneinfo import ZoneInfo

import anyio

from app import logging
from app.config import Config
from app.constants import LIBRARY_PATH, LOGS_DIR, QUALITY, QUALITY_TYPES, THUMBNAILS_DIR
from app.metadata.MetadataAnalyzer import MetadataAnalyzer
from app.metadata.ThumbnailGenerator import ThumbnailGenerator
from app.models.RecordedProgram import RecordedProgram
from app.models.RecordedVideo import RecordedVideo
from app.schemas import EncodingTask, RecordedProgram as RecordedProgramSchema


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
    RETRYABLE_CATEGORIES = ['RESOURCE', 'NETWORK', 'ENCODER', 'PROCESS']

    # エラーパターンの定義
    ERROR_PATTERNS = {
        'FILE_ACCESS': [
            r'No such file or directory',
            r'Permission denied',
            r'Input file not found',
            r'Cannot open.*for reading',
            r'Cannot create.*for writing',
            r'Disk full',
            r'No space left on device',
            r'Insufficient disk space',
            r'Access is denied',
            r'File is being used by another process'
        ],
        'ENCODER': [
            r'Encoder.*not found',
            r'Unknown encoder',
            r'Encoding failed',
            r'Invalid codec',
            r'Unsupported format',
            r'Hardware encoder.*not available',
            r'GPU.*not found',
            r'QSVEncC.*not found',
            r'NVEncC.*not found',
            r'VCEEncC.*not found',
            r'FFmpeg.*not found',
            r'tsreplace.*not found',
            r'Hardware acceleration.*failed',
            r'Codec initialization failed'
        ],
        'RESOURCE': [
            r'Out of memory',
            r'Cannot allocate memory',
            r'Resource temporarily unavailable',
            r'Too many open files',
            r'System overloaded',
            r'Insufficient memory',
            r'Memory allocation failed',
            r'System resources exhausted',
            r'Process limit exceeded'
        ],
        'CONFIGURATION': [
            r'Invalid.*parameter',
            r'Configuration error',
            r'Missing required.*setting',
            r'Invalid quality preset',
            r'Unsupported.*option',
            r'Invalid codec configuration',
            r'Unsupported encoder settings',
            r'Configuration validation failed'
        ],
        'NETWORK': [
            r'Connection.*refused',
            r'Network.*unreachable',
            r'Timeout',
            r'Connection.*reset',
            r'Network error',
            r'Connection lost'
        ],
        'PROCESS': [
            r'Process.*terminated',
            r'Process.*killed',
            r'Subprocess.*failed',
            r'Command.*not found',
            r'Execution.*failed',
            r'Process.*crashed'
        ]
    }


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
        """

        # エンコードタスク情報を作成
        self.encoding_task = EncodingTask(
            rec_file_id=0,  # デフォルト値
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

    def buildEncoderCommand(self) -> list[str]:
        """
        エンコーダーコマンドを生成する（LiveEncodingTaskのロジックを統合）

        Returns:
            list[str]: エンコーダーコマンドの配列
        """
        if self.encoding_task.encoder_type == 'software':
            return self._buildFFmpegCommand()
        else:
            return self._buildHardwareEncoderCommand()

    def _buildFFmpegCommand(self) -> list[str]:
        """
        FFmpegエンコードコマンドを生成する
        """
        # 品質設定を取得（デフォルト値を設定）
        quality_config = {
            'video_bitrate': '6000K',
            'video_bitrate_max': '8000K',
            'audio_bitrate': '192K',
            'width': 1920,
            'height': 1080,
            'is_hevc': self.encoding_task.codec == 'hevc',
            'is_60fps': False
        }

        # オプションの入る配列
        options: list[str] = []

        # 入力
        analyzeduration = 500000
        options.append(f'-f mpegts -analyzeduration {analyzeduration} -i pipe:0')

        # ストリームのマッピング
        options.append('-map 0:v:0 -map 0:a:0 -map 0:a:1 -map 0:d? -ignore_unknown')

        # フラグ
        max_interleave_delta = 500
        options.append(f'-fflags nobuffer -flags low_delay -max_delay 250000 -max_interleave_delta {max_interleave_delta}K -threads auto')

        # 映像コーデック
        if quality_config['is_hevc']:
            options.append('-vcodec libx265')
        else:
            options.append('-vcodec libx264')

        # ビットレートと品質
        options.append(f'-flags +cgop -vb {quality_config["video_bitrate"]} -maxrate {quality_config["video_bitrate_max"]}')
        options.append('-preset veryfast -aspect 16:9')

        if quality_config['is_hevc']:
            options.append('-profile:v main')
        else:
            options.append('-profile:v high')

        # 解像度とフレームレート
        video_width = quality_config['width']
        video_height = quality_config['height']

        # GOP長の設定
        gop_length_second = self.GOP_LENGTH_SECONDS_H264
        if quality_config['is_hevc']:
            gop_length_second = self.GOP_LENGTH_SECONDS_H265

        # インターレース解除とフレームレート設定
        if quality_config['is_60fps']:
            options.append(f'-vf yadif=mode=1:parity=-1:deint=1,scale={video_width}:{video_height}')
            options.append(f'-r 60000/1001 -g {int(gop_length_second * 60)}')
        else:
            options.append(f'-vf yadif=mode=0:parity=-1:deint=1,scale={video_width}:{video_height}')
            options.append(f'-r 30000/1001 -g {int(gop_length_second * 30)}')

        # 音声
        options.append(f'-acodec aac -aac_coder twoloop -ac 2 -ab {quality_config["audio_bitrate"]} -ar 48000 -af volume=2.0')

        # 出力
        options.append('-y -f mpegts pipe:1')

        # オプションをスペースで区切って配列にする
        result: list[str] = []
        for option in options:
            result += option.split(' ')

        return result

    def _buildHardwareEncoderCommand(self) -> list[str]:
        """
        ハードウェアエンコードコマンドを生成する
        """
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
            logging.warning(f'Unknown hardware encoder: {encoder}, falling back to FFmpeg')
            return self._buildFFmpegCommand()

    def _buildQSVEncCCommand(self) -> list[str]:
        """
        QSVEncCエンコードコマンドを生成する（LiveEncodingTaskから改良）
        """
        # 品質設定
        quality_config = {
            'video_bitrate': '6000',
            'video_bitrate_max': '8000',
            'audio_bitrate': '192',
            'width': 1920,
            'height': 1080,
            'is_hevc': self.encoding_task.codec == 'hevc',
            'is_60fps': False
        }

        options: list[str] = []

        # 入力
        input_probesize = 1000
        input_analyze = 0.7
        options.append(f'--input-format mpegts --input-probesize {input_probesize}K --input-analyze {input_analyze}')
        options.append('--fps 30000/1001')
        options.append('--input - --avhw')

        # ストリームのマッピング
        options.append('--audio-stream 1?:stereo --audio-stream 2?:stereo --data-copy timed_id3')

        # フラグ
        max_interleave_delta = 500
        options.append('-m avioflags:direct -m fflags:nobuffer+flush_packets -m flush_packets:1 -m max_delay:250000')
        options.append(f'-m max_interleave_delta:{max_interleave_delta}K --output-thread 0 --lowlatency')
        options.append('--log-level debug --disable-opencl')

        # 映像コーデック
        if quality_config['is_hevc']:
            options.append('--codec hevc')
            options.append(f'--qvbr {quality_config["video_bitrate"]} --fallback-rc')
            options.append('--qvbr-quality 30')
        else:
            options.append('--codec h264')
            options.append(f'--vbr {quality_config["video_bitrate"]}')

        options.append(f'--max-bitrate {quality_config["video_bitrate_max"]}')

        # ヘッダ情報制御
        options.append('--repeat-headers')

        # 品質設定
        options.append('--quality balanced')
        if quality_config['is_hevc']:
            options.append('--profile main')
        else:
            options.append('--profile high')
        options.append('--dar 16:9')

        # GOP長
        gop_length_second = self.GOP_LENGTH_SECONDS_H264
        if quality_config['is_hevc']:
            gop_length_second = self.GOP_LENGTH_SECONDS_H265

        # インターレース解除
        options.append('--interlace tff')
        if quality_config['is_60fps']:
            options.append('--vpp-deinterlace bob')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 60)}')
        else:
            options.append('--vpp-deinterlace normal')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 30)}')

        # 解像度
        options.append(f'--output-res {quality_config["width"]}x{quality_config["height"]}')

        # 音声
        options.append(f'--audio-codec aac:aac_coder=twoloop --audio-bitrate {quality_config["audio_bitrate"]}')
        options.append('--audio-samplerate 48000 --audio-filter volume=2.0 --audio-ignore-decode-error 30')

        # 出力
        options.append('--output-format mpegts --output -')

        # オプションをスペースで区切って配列にする
        result: list[str] = []
        for option in options:
            result += option.split(' ')

        return result

    def _buildNVEncCCommand(self) -> list[str]:
        """
        NVEncCエンコードコマンドを生成する
        """
        # QSVEncCと同様の構造で実装
        quality_config = {
            'video_bitrate': '6000',
            'video_bitrate_max': '8000',
            'audio_bitrate': '192',
            'width': 1920,
            'height': 1080,
            'is_hevc': self.encoding_task.codec == 'hevc',
            'is_60fps': False
        }

        options: list[str] = []

        # 入力
        options.append('--input-format mpegts --input-probesize 1000K --input-analyze 0.7')
        options.append('--fps 30000/1001 --input - --avhw')

        # ストリームのマッピング
        options.append('--audio-stream 1?:stereo --audio-stream 2?:stereo --data-copy timed_id3')

        # フラグ
        options.append('-m avioflags:direct -m fflags:nobuffer+flush_packets -m flush_packets:1 -m max_delay:250000')
        options.append('-m max_interleave_delta:500K --output-thread 0 --lowlatency')
        options.append('--log-level debug --disable-nvml 1 --disable-dx11 --disable-vulkan')

        # 映像コーデック
        if quality_config['is_hevc']:
            options.append('--codec hevc')
            options.append('--qp-min 23:26:30 --lookahead 16 --multipass 2pass-full --weightp --bref-mode middle --aq --aq-temporal')
        else:
            options.append('--codec h264')

        options.append(f'--vbr {quality_config["video_bitrate"]} --max-bitrate {quality_config["video_bitrate_max"]}')

        # 品質とプロファイル
        options.append('--repeat-headers --preset default')
        if quality_config['is_hevc']:
            options.append('--profile main')
        else:
            options.append('--profile high')
        options.append('--dar 16:9')

        # インターレース解除
        options.append('--interlace tff')
        gop_length_second = self.GOP_LENGTH_SECONDS_H265 if quality_config['is_hevc'] else self.GOP_LENGTH_SECONDS_H264

        if quality_config['is_60fps']:
            options.append('--vpp-yadif mode=bob')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 60)}')
        else:
            options.append('--vpp-afs preset=default')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 30)}')

        # 解像度と音声
        options.append(f'--output-res {quality_config["width"]}x{quality_config["height"]}')
        options.append(f'--audio-codec aac:aac_coder=twoloop --audio-bitrate {quality_config["audio_bitrate"]}')
        options.append('--audio-samplerate 48000 --audio-filter volume=2.0 --audio-ignore-decode-error 30')
        options.append('--output-format mpegts --output -')

        result: list[str] = []
        for option in options:
            result += option.split(' ')
        return result

    def _buildVCEEncCCommand(self) -> list[str]:
        """
        VCEEncCエンコードコマンドを生成する
        """
        quality_config = {
            'video_bitrate': '6000',
            'video_bitrate_max': '8000',
            'audio_bitrate': '192',
            'width': 1920,
            'height': 1080,
            'is_hevc': self.encoding_task.codec == 'hevc',
            'is_60fps': False
        }

        options: list[str] = []

        # 入力（VCEEncCはSWデコーダーを使用）
        options.append('--input-format mpegts --input-probesize 1000K --input-analyze 0.7')
        options.append('--fps 30000/1001 --input - --avsw')

        # ストリームのマッピング
        options.append('--audio-stream 1?:stereo --audio-stream 2?:stereo --data-copy timed_id3')

        # フラグ
        options.append('-m avioflags:direct -m fflags:nobuffer+flush_packets -m flush_packets:1 -m max_delay:250000')
        options.append('-m max_interleave_delta:500K --output-thread 0 --lowlatency --log-level debug')

        # 映像コーデック
        options.append(f'--codec {self.encoding_task.codec}')
        options.append(f'--vbr {quality_config["video_bitrate"]} --max-bitrate {quality_config["video_bitrate_max"]}')

        # 品質設定
        options.append('--preset balanced')
        if quality_config['is_hevc']:
            options.append('--profile main')
        else:
            options.append('--profile high')
        options.append('--dar 16:9')

        # インターレース解除（VCEEncCは--vpp-afsを使用）
        options.append('--interlace tff')
        gop_length_second = self.GOP_LENGTH_SECONDS_H265 if quality_config['is_hevc'] else self.GOP_LENGTH_SECONDS_H264

        if quality_config['is_60fps']:
            options.append('--vpp-yadif mode=bob')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 60)}')
        else:
            options.append('--vpp-afs preset=default')
            options.append(f'--avsync vfr --gop-len {int(gop_length_second * 30)}')

        # 解像度と音声
        options.append(f'--output-res {quality_config["width"]}x{quality_config["height"]}')
        options.append(f'--audio-codec aac:aac_coder=twoloop --audio-bitrate {quality_config["audio_bitrate"]}')
        options.append('--audio-samplerate 48000 --audio-filter volume=2.0 --audio-ignore-decode-error 30')
        options.append('--output-format mpegts --output -')

        result: list[str] = []
        for option in options:
            result += option.split(' ')
        return result


    async def execute(self) -> bool:
        """
        エンコード処理を実行する（リトライ機能付き）

        Returns:
            bool: エンコード成功時True、失敗時False
        """

        # エンコード開始時刻を記録
        from datetime import datetime
        self.encoding_task.started_at = datetime.now()
        self.encoding_task.status = 'processing'

        # エンコード中のファイルをトラッカーに追加
        from app.utils.EncodingFileTracker import EncodingFileTracker
        encoding_tracker = await EncodingFileTracker.getInstance()
        logging.info(f'Adding file to encoding tracker (instance ID: {id(encoding_tracker)}): {self.encoding_task.output_file_path}')
        await encoding_tracker.addEncodingFile(self.encoding_task.output_file_path)

        # エンコード開始をログに記録
        self._logEncodingStart(self.encoding_task)

        try:
            while self.encoding_task.retry_count <= self.encoding_task.max_retry_count:
                try:
                    # エンコード前の準備処理
                    if not await self._prepareEncoding():
                        return False

                    # エンコード実行
                    success = await self._executeEncoding()

                    if success:
                        # エンコード完了時刻を記録
                        self.encoding_task.completed_at = datetime.now()
                        self.encoding_task.status = 'completed'

                        # エンコード時間を計算
                        if self.encoding_task.started_at:
                            duration = (self.encoding_task.completed_at - self.encoding_task.started_at).total_seconds()
                            self.encoding_task.encoding_duration = duration

                        self._is_finished = True

                        # エンコード完了をログに記録
                        self._logEncodingComplete(self.encoding_task, True, duration)

                        logging.info(f'TSReplace encoding completed successfully: {self.encoding_task.output_file_path}')
                        return True
                    else:
                        # エンコード失敗時の処理
                        await self._handleEncodingFailure()

                        # リトライ判定
                        if not await self._shouldRetry():
                            break

                        # リトライ前の待機
                        await self._waitForRetry()

                except Exception as e:
                    # 予期しないエラーの処理
                    await self._handleUnexpectedError(e)

                    # リトライ判定
                    if not await self._shouldRetry():
                        break

                    # リトライ前の待機
                    await self._waitForRetry()

            # すべてのリトライが失敗した場合
            self.encoding_task.status = 'failed'
            self.encoding_task.completed_at = datetime.now()

            # 失敗時のクリーンアップ
            await self._cleanupFailedEncoding()

            # エンコード失敗をログに記録
            self._logEncodingComplete(self.encoding_task, False)

            logging.error(f'TSReplace encoding failed after {self.encoding_task.retry_count} retries: {self.encoding_task.output_file_path}')
            return False

        finally:
            # 成功・失敗・例外に関わらず、必ずトラッカーからファイルを除去
            try:
                logging.info(f'Removing file from encoding tracker (instance ID: {id(encoding_tracker)}): {self.encoding_task.output_file_path}')
                await encoding_tracker.removeEncodingFile(self.encoding_task.output_file_path)
            except Exception as e:
                logging.error(f'Failed to remove file from encoding tracker: {e}', exc_info=True)


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
            # tsreplaceコマンドを構築
            encoder_command = self.buildEncoderCommand()
            tsreplace_cmd = [
                self.TSREPLACE_PATH,
                '-i', self.encoding_task.input_file_path,
                '-o', self.encoding_task.output_file_path,
                '-e'
            ] + encoder_command

            logging.info(f'Starting tsreplace encoding: {" ".join(tsreplace_cmd)}')

            # tsreplaceプロセスを開始
            self._tsreplace_process = await asyncio.create_subprocess_exec(
                *tsreplace_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # プロセスの完了を待機
            stdout, stderr = await self._tsreplace_process.communicate()

            # 結果を確認
            if self._tsreplace_process.returncode == 0:
                # エンコード後のファイルサイズを記録
                if os.path.exists(self.encoding_task.output_file_path):
                    self.encoding_task.encoded_file_size = os.path.getsize(self.encoding_task.output_file_path)

                # エンコード後の処理を実行
                post_process_success = await self._processEncodedFile()
                if post_process_success:
                    logging.info(f'Post-processing completed successfully for: {self.encoding_task.output_file_path}')
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

                self.encoding_task.error_message = error_msg
                logging.error(error_msg)
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
        エンコード失敗時の処理を行う
        """

        try:
            # エラーを処理
            error_exception = Exception(self.encoding_task.error_message or 'Unknown encoding error')
            should_retry, processed_error_msg = await self._handleEncodingError(
                self.encoding_task,
                error_exception
            )

            # 処理されたエラーメッセージを更新
            if processed_error_msg:
                self.encoding_task.error_message = processed_error_msg

            # エラーをログに記録
            error_category = self._categorizeError(self.encoding_task.error_message or '')
            self._logEncodingError(self.encoding_task, error_exception, error_category)

            logging.error(f'Encoding failed for task {self.encoding_task.task_id}: {self.encoding_task.error_message}')

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
            should_retry, processed_error_msg = await self._handleEncodingError(
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
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'encoding_start',
                'task_id': task.task_id,
                'input_file': task.input_file_path,
                'output_file': task.output_file_path,
                'codec': task.codec,
                'encoder_type': task.encoder_type,
                'quality_preset': task.quality_preset,
                'original_file_size': task.original_file_size,
                'retry_count': task.retry_count
            }

            message = f'Encoding started - Task: {task.task_id}, Input: {task.input_file_path}, Codec: {task.codec}, Encoder: {task.encoder_type}'
            self._writeTextLog(self.encoding_log_path, 'INFO', message)
            self._writeJsonLog(self.encoding_json_log_path, log_entry)
            logging.info(f'TSReplace encoding started: {task.task_id}')

        except Exception as e:
            logging.error(f'Failed to log encoding start: {e}', exc_info=True)

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
        """エンコード後のファイル処理を実行する"""
        try:
            # 元の録画ファイル情報を取得
            original_video = None
            try:
                original_video = await RecordedVideo.get(id=self.encoding_task.rec_file_id).prefetch_related('recorded_program')
                logging.debug(f'Found original video: ID {self.encoding_task.rec_file_id}, Path: {original_video.file_path}')
            except Exception as e:
                logging.error(f'Original video not found: ID {self.encoding_task.rec_file_id}, Error: {e}')

                config = Config()
                if hasattr(config.client, 'tsreplace_continue_on_missing_record') and config.client.tsreplace_continue_on_missing_record:
                    logging.warning(f'Proceeding with limited post-processing without database record')
                    original_video = None
                else:
                    logging.error(f'Aborting post-processing due to missing database record')
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

            # 出力ファイルのメタデータを解析
            logging.info(f'Analyzing metadata for encoded file: {self.encoding_task.output_file_path}')
            encoded_program_schema = await self._analyzeEncodedFileMetadata()
            if not encoded_program_schema:
                logging.error(f'Failed to analyze encoded file metadata: {self.encoding_task.output_file_path}')
                return False

            # データベースに新しいファイル情報を登録
            if original_video is not None:
                logging.info(f'Updating database with encoded file information')
                success = await self._updateDatabaseWithEncodedFile(original_video, encoded_program_schema)
                if not success:
                    logging.error(f'Failed to update database with encoded file information')
                    return False

                # サムネイル再生成処理
                await self._regenerateThumbnails(original_video)

                # 元ファイルの削除・保持処理
                if self.delete_original:
                    await self._deleteOriginalFile(original_video)
                else:
                    logging.info(f'Original file preserved: {original_video.file_path}')
            else:
                logging.warning(f'Skipping database update and thumbnail regeneration due to missing original video record')
                logging.info(f'Encoded file created successfully: {self.encoding_task.output_file_path}')

                if self.delete_original:
                    logging.warning(f'Cannot delete original file - original video record not found')

            logging.info(f'Post-processing completed successfully for: {self.encoding_task.output_file_path}')
            return True

        except Exception as e:
            logging.error(f'Post-processing error: {e}', exc_info=True)
            return False

    async def _analyzeEncodedFileMetadata(self) -> RecordedProgramSchema | None:
        """エンコード後のファイルのメタデータを解析する"""
        try:
            analyzer = MetadataAnalyzer(Path(self.encoding_task.output_file_path))
            recorded_program_schema = await asyncio.to_thread(analyzer.analyze)

            if not recorded_program_schema:
                logging.warning(f'Failed to analyze metadata for encoded file: {self.encoding_task.output_file_path}')
                return None

            logging.debug(f'Metadata analysis completed for: {self.encoding_task.output_file_path}')
            return recorded_program_schema

        except Exception as e:
            logging.error(f'Metadata analysis error: {e}', exc_info=True)
            return None

    async def _updateDatabaseWithEncodedFile(self, original_video: RecordedVideo, encoded_program_schema: RecordedProgramSchema) -> bool:
        """データベースに新しいエンコード済みファイル情報を登録する"""
        try:
            # 元のRecordedVideoの情報を更新
            original_video.file_path = encoded_program_schema.recorded_video.file_path
            original_video.file_hash = encoded_program_schema.recorded_video.file_hash
            original_video.file_size = encoded_program_schema.recorded_video.file_size
            original_video.file_created_at = encoded_program_schema.recorded_video.file_created_at
            original_video.file_modified_at = encoded_program_schema.recorded_video.file_modified_at

            # 映像・音声コーデック情報を更新
            original_video.container_format = encoded_program_schema.recorded_video.container_format
            original_video.video_codec = encoded_program_schema.recorded_video.video_codec
            original_video.video_codec_profile = encoded_program_schema.recorded_video.video_codec_profile
            original_video.video_scan_type = encoded_program_schema.recorded_video.video_scan_type
            original_video.video_frame_rate = encoded_program_schema.recorded_video.video_frame_rate
            original_video.video_resolution_width = encoded_program_schema.recorded_video.video_resolution_width
            original_video.video_resolution_height = encoded_program_schema.recorded_video.video_resolution_height
            original_video.primary_audio_codec = encoded_program_schema.recorded_video.primary_audio_codec
            original_video.primary_audio_channel = encoded_program_schema.recorded_video.primary_audio_channel
            original_video.primary_audio_sampling_rate = encoded_program_schema.recorded_video.primary_audio_sampling_rate
            original_video.secondary_audio_codec = encoded_program_schema.recorded_video.secondary_audio_codec
            original_video.secondary_audio_channel = encoded_program_schema.recorded_video.secondary_audio_channel
            original_video.secondary_audio_sampling_rate = encoded_program_schema.recorded_video.secondary_audio_sampling_rate

            # 録画時間情報を更新
            if encoded_program_schema.recorded_video.recording_start_time:
                original_video.recording_start_time = encoded_program_schema.recorded_video.recording_start_time
            if encoded_program_schema.recorded_video.recording_end_time:
                original_video.recording_end_time = encoded_program_schema.recorded_video.recording_end_time
            original_video.duration = encoded_program_schema.recorded_video.duration

            # キーフレーム情報とCM区間情報をクリア
            original_video.key_frames = []
            original_video.cm_sections = None

            # データベースに保存
            await original_video.save()

            logging.info(f'Database updated successfully for video ID: {original_video.id}')
            return True

        except Exception as e:
            logging.error(f'Database update error: {e}', exc_info=True)
            return False

    async def _deleteOriginalFile(self, original_video: RecordedVideo) -> None:
        """元ファイルを安全に削除する"""
        try:
            original_file_path = original_video.file_path

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

    async def _regenerateThumbnails(self, updated_video: RecordedVideo) -> None:
        """エンコード後のファイルに対してサムネイルを再生成する（既存サムネイルがある場合は保持）"""
        try:
            logging.info(f'Checking thumbnail status for: {self.encoding_task.output_file_path}')

            # 設定から既存サムネイルの扱いを取得
            try:
                config = Config()
                preserve_existing_thumbnails = getattr(config.tsreplace_encoding, 'preserve_existing_thumbnails', True)
            except:
                preserve_existing_thumbnails = True  # デフォルトは既存サムネイルを保持

            # 既存のサムネイルが存在するかチェック
            existing_thumbnails = await self._checkExistingThumbnails(updated_video.id)

            if preserve_existing_thumbnails and existing_thumbnails['has_all_thumbnails']:
                logging.info(f'All thumbnails already exist for video ID {updated_video.id}, skipping regeneration')
                logging.info(f'Existing thumbnails: {existing_thumbnails["existing_files"]}')
                return

            if preserve_existing_thumbnails and existing_thumbnails['has_some_thumbnails']:
                logging.info(f'Some thumbnails exist for video ID {updated_video.id}: {existing_thumbnails["existing_files"]}')
                logging.info('Generating only missing thumbnails')
            elif not preserve_existing_thumbnails and existing_thumbnails['has_some_thumbnails']:
                logging.info(f'Force regenerating all thumbnails (preserve_existing_thumbnails=False)')
                # 既存のサムネイルを削除
                await self._removeExistingThumbnails(updated_video.id)

            recorded_program = await RecordedProgram.get(id=updated_video.recorded_program_id)
            if not recorded_program:
                logging.error(f'RecordedProgram not found for video ID: {updated_video.id}')
                return

            face_detection_mode = self._determineFaceDetectionMode(recorded_program)

            thumbnail_generator = ThumbnailGenerator(
                file_path=anyio.Path(self.encoding_task.output_file_path),
                container_format=updated_video.container_format,
                file_hash=updated_video.file_hash,
                duration_sec=updated_video.duration,
                candidate_time_ranges=self._generateCandidateTimeRanges(updated_video.duration),
                face_detection_mode=face_detection_mode
            )

            # 設定に基づいてサムネイル生成
            skip_if_exists = preserve_existing_thumbnails
            await thumbnail_generator.generateAndSave(skip_tile_if_exists=skip_if_exists)

            logging.info(f'Thumbnail processing completed for: {self.encoding_task.output_file_path}')

        except Exception as e:
            logging.error(f'Thumbnail processing error: {e}', exc_info=True)

    def _determineFaceDetectionMode(self, recorded_program: RecordedProgram) -> Literal['Human', 'Anime'] | None:
        """番組情報に基づいて顔検出モードを決定する"""
        try:
            anime_genres = ['アニメ/特撮', 'アニメ', '特撮']

            if hasattr(recorded_program, 'genre_major') and recorded_program.genre_major:
                if recorded_program.genre_major in anime_genres:
                    return 'Anime'

            if hasattr(recorded_program, 'genre_middle') and recorded_program.genre_middle:
                if any(anime_genre in recorded_program.genre_middle for anime_genre in anime_genres):
                    return 'Anime'

            anime_keywords = ['アニメ', 'アニメーション', '劇場版', '映画']
            title = recorded_program.title.lower()
            if any(keyword in title for keyword in anime_keywords):
                return 'Anime'

            return 'Human'

        except Exception as e:
            logging.warning(f'Failed to determine face detection mode: {e}')
            return 'Human'

    def _generateCandidateTimeRanges(self, duration: float) -> list[tuple[float, float]]:
        """サムネイル候補時間範囲を生成する"""
        try:
            start_offset = duration * 0.1
            end_offset = duration * 0.9

            if end_offset - start_offset < 30:
                center = duration / 2
                start_offset = max(0, center - 15)
                end_offset = min(duration, center + 15)

            return [(start_offset, end_offset)]

        except Exception as e:
            logging.warning(f'Failed to generate candidate time ranges: {e}')
            quarter = duration * 0.25
            return [(quarter, duration - quarter)]

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

    async def _checkExistingThumbnails(self, video_id: int) -> Dict[str, Any]:
        """既存のサムネイルファイルの存在をチェックする"""
        try:
            thumbnail_dir = anyio.Path(THUMBNAILS_DIR)

            # チェック対象のサムネイルファイル
            thumbnail_files = {
                'tile_webp': thumbnail_dir / f'{video_id}.webp',
                'tile_jpg': thumbnail_dir / f'{video_id}.jpg',
                'representative_webp': thumbnail_dir / f'{video_id}_representative.webp',
                'representative_jpg': thumbnail_dir / f'{video_id}_representative.jpg'
            }

            existing_files = []
            missing_files = []

            for file_type, thumbnail_path in thumbnail_files.items():
                if await thumbnail_path.exists():
                    existing_files.append(str(thumbnail_path))
                    logging.debug(f'Found existing thumbnail: {thumbnail_path}')
                else:
                    missing_files.append(str(thumbnail_path))

            # サムネイルの完全性をチェック
            # タイル画像（.webp または .jpg）と代表サムネイル（_representative.webp または _representative.jpg）の両方が必要
            has_tile = (await thumbnail_files['tile_webp'].exists() or
                       await thumbnail_files['tile_jpg'].exists())
            has_representative = (await thumbnail_files['representative_webp'].exists() or
                                await thumbnail_files['representative_jpg'].exists())

            has_all_thumbnails = has_tile and has_representative
            has_some_thumbnails = len(existing_files) > 0

            return {
                'has_all_thumbnails': has_all_thumbnails,
                'has_some_thumbnails': has_some_thumbnails,
                'has_tile': has_tile,
                'has_representative': has_representative,
                'existing_files': existing_files,
                'missing_files': missing_files,
                'total_existing': len(existing_files),
                'total_missing': len(missing_files)
            }

        except Exception as e:
            logging.warning(f'Failed to check existing thumbnails: {e}')
            return {
                'has_all_thumbnails': False,
                'has_some_thumbnails': False,
                'has_tile': False,
                'has_representative': False,
                'existing_files': [],
                'missing_files': [],
                'total_existing': 0,
                'total_missing': 4
            }

    async def _removeExistingThumbnails(self, video_id: int) -> None:
        """既存のサムネイルファイルを削除する（必要な場合のみ使用）"""
        try:
            thumbnail_dir = anyio.Path(THUMBNAILS_DIR)

            thumbnail_files = [
                thumbnail_dir / f'{video_id}.webp',
                thumbnail_dir / f'{video_id}.jpg',
                thumbnail_dir / f'{video_id}_representative.webp',
                thumbnail_dir / f'{video_id}_representative.jpg'
            ]

            for thumbnail_path in thumbnail_files:
                if await thumbnail_path.exists():
                    await thumbnail_path.unlink()
                    logging.debug(f'Removed existing thumbnail: {thumbnail_path}')

        except Exception as e:
            logging.warning(f'Failed to remove existing thumbnails: {e}')
