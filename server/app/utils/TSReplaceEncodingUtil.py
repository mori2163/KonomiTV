import subprocess
from typing import Literal

from app.config import Config
from app.constants import LIBRARY_PATH


class TSReplaceEncodingUtil:
    """tsreplaceエンコード関連のユーティリティクラス"""

    @staticmethod
    def detectHardwareEncoderAvailability() -> bool:
        """
        ハードウェアエンコーダーが利用可能かどうかを検出する
        config.yamlで設定されたエンコーダーに基づいて判定を行う

        Returns:
            bool: ハードウェアエンコーダーが利用可能な場合はTrue
        """

        config = Config()
        encoder = config.general.encoder

        # FFmpegの場合はハードウェアエンコーダーとして扱わない
        if encoder == 'FFmpeg':
            return False

        try:
            # --check-hw でハードウェアエンコーダーが利用できるかをチェック
            # 利用可能なら標準出力に "H.264/AVC" という文字列が出力される
            result = subprocess.run(
                [LIBRARY_PATH[encoder], '--check-hw'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,  # タイムアウトを設定
            )

            result_stdout = result.stdout.decode('utf-8')
            # reader: 行を除外（ログノイズを除去）
            result_stdout = '\n'.join([line for line in result_stdout.split('\n') if 'reader:' not in line])

            # "unavailable." が含まれている場合は利用不可
            if 'unavailable.' in result_stdout:
                return False

            # "H.264/AVC" が含まれている場合は利用可能
            if 'H.264/AVC' in result_stdout:
                return True

            return False

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            # エラーが発生した場合は利用不可とみなす
            return False

    @staticmethod
    def getAvailableCodecs() -> list[Literal['h264', 'hevc']]:
        """
        利用可能なコーデックのリストを取得する
        ハードウェアエンコーダーが利用可能な場合はHEVCも含める

        Returns:
            list[Literal['h264', 'hevc']]: 利用可能なコーデックのリスト
        """

        config = Config()
        encoder = config.general.encoder
        available_codecs: list[Literal['h264', 'hevc']] = ['h264']  # H.264は常に利用可能

        # FFmpegの場合はソフトウェアエンコードでHEVCも利用可能
        if encoder == 'FFmpeg':
            available_codecs.append('hevc')
            return available_codecs

        try:
            # --check-hw でハードウェアエンコーダーの対応コーデックをチェック
            result = subprocess.run(
                [LIBRARY_PATH[encoder], '--check-hw'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )

            result_stdout = result.stdout.decode('utf-8')
            result_stdout = '\n'.join([line for line in result_stdout.split('\n') if 'reader:' not in line])

            # "unavailable." が含まれている場合はH.264のみ（ソフトウェアフォールバック）
            if 'unavailable.' in result_stdout:
                return available_codecs

            # "H.265/HEVC" が含まれている場合はHEVCも利用可能
            if 'H.265/HEVC' in result_stdout:
                available_codecs.append('hevc')

            return available_codecs

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            # エラーが発生した場合はH.264のみ利用可能とみなす
            return available_codecs

    @staticmethod
    def validateEncodingSettings(
        codec: Literal['h264', 'hevc'],
        encoder_type: Literal['software', 'hardware'],
        quality_preset: str
    ) -> tuple[bool, str]:
        """
        エンコード設定の妥当性を検証する

        Args:
            codec: 使用するコーデック
            encoder_type: エンコーダータイプ
            quality_preset: 品質プリセット

        Returns:
            tuple[bool, str]: (妥当性, エラーメッセージ)
        """

        # ハードウェアエンコーダーが指定されているが利用できない場合
        if encoder_type == 'hardware' and not TSReplaceEncodingUtil.detectHardwareEncoderAvailability():
            return False, 'ハードウェアエンコーダーが利用できません。ソフトウェアエンコードを使用してください。'

        # 指定されたコーデックが利用できない場合
        available_codecs = TSReplaceEncodingUtil.getAvailableCodecs()
        if codec not in available_codecs:
            return False, f'コーデック {codec.upper()} は利用できません。利用可能なコーデック: {", ".join([c.upper() for c in available_codecs])}'

        # HEVCがハードウェアエンコーダーで利用できない場合
        if codec == 'hevc' and encoder_type == 'hardware':
            config = Config()
            encoder = config.general.encoder
            if encoder != 'FFmpeg':
                try:
                    result = subprocess.run(
                        [LIBRARY_PATH[encoder], '--check-hw'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                    )
                    result_stdout = result.stdout.decode('utf-8')
                    if 'H.265/HEVC' not in result_stdout:
                        return False, 'ハードウェアエンコーダーでHEVCは利用できません。H.264を使用するか、ソフトウェアエンコードを使用してください。'
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    return False, 'ハードウェアエンコーダーの確認中にエラーが発生しました。'

        # 品質プリセットの妥当性チェック（基本的な値のみ）
        valid_presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
        if quality_preset not in valid_presets:
            return False, f'無効な品質プリセットです。有効な値: {", ".join(valid_presets)}'

        return True, ''