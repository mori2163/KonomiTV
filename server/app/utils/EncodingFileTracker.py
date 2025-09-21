from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Dict, Set

from app import logging


class EncodingFileTracker:
    """
    エンコード中のファイルを追跡するシングルトンクラス
    RecordedScanTaskがエンコード中のファイルを処理しないようにするために使用
    """

    _instance: EncodingFileTracker | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        # エンコード中のファイルパスを保持するセット
        self._encoding_files: Set[str] = set()
        # ファイルの追加時刻を記録する辞書（タイムアウト判定用）
        self._file_timestamps: Dict[str, float] = {}
        self._file_lock = asyncio.Lock()
        # タイムアウト時間（秒）- デフォルト60分
        self._timeout_seconds = 3600
        # 最後にデバッグログを出力した時刻（ログ出力頻度制限用）
        self._last_debug_log_time = 0.0

    @classmethod
    async def getInstance(cls) -> EncodingFileTracker:
        """
        シングルトンインスタンスを取得する

        Returns:
            EncodingFileTracker: シングルトンインスタンス
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def addEncodingFile(self, file_path: str | Path) -> None:
        """
        エンコード中のファイルを追加する

        Args:
            file_path (str | Path): エンコード中のファイルパス
        """
        async with self._file_lock:
            file_path_str = str(file_path)
            self._encoding_files.add(file_path_str)
            self._file_timestamps[file_path_str] = time.time()
            logging.debug(f'Added encoding file to tracker: {file_path_str}')

    async def removeEncodingFile(self, file_path: str | Path) -> None:
        """
        エンコード中のファイルを削除する

        Args:
            file_path (str | Path): エンコード完了したファイルパス
        """
        async with self._file_lock:
            file_path_str = str(file_path)
            self._encoding_files.discard(file_path_str)
            self._file_timestamps.pop(file_path_str, None)
            logging.debug(f'Removed encoding file from tracker: {file_path_str}')

    async def isEncodingFile(self, file_path: str | Path) -> bool:
        """
        指定されたファイルがエンコード中かどうかを確認する

        Args:
            file_path (str | Path): 確認するファイルパス

        Returns:
            bool: エンコード中の場合True
        """
        async with self._file_lock:
            file_path_str = str(file_path)
            is_encoding = file_path_str in self._encoding_files

            # エンコード中のファイルが見つかった場合のみ、かつ30秒に1回だけログ出力（頻度を抑制）
            if is_encoding:
                current_time = time.time()
                if current_time - self._last_debug_log_time > 30:  # 30秒間隔
                    logging.debug(f'File is currently being encoded: {file_path_str}')
                    if len(self._encoding_files) > 1:
                        logging.debug(f'Total encoding files: {len(self._encoding_files)}')
                    self._last_debug_log_time = current_time

            return is_encoding

    async def getEncodingFiles(self) -> Set[str]:
        """
        現在エンコード中のファイル一覧を取得する

        Returns:
            Set[str]: エンコード中のファイルパスのセット
        """
        async with self._file_lock:
            return self._encoding_files.copy()

    async def clearAll(self) -> None:
        """
        すべてのエンコード中ファイルをクリアする
        """
        async with self._file_lock:
            self._encoding_files.clear()
            self._file_timestamps.clear()
            logging.info('Cleared all encoding files from tracker')

    async def forceRemoveEncodingFile(self, file_path: str | Path) -> None:
        """
        エンコード中のファイルを強制的に削除する（デバッグ用）

        Args:
            file_path (str | Path): 削除するファイルパス
        """
        async with self._file_lock:
            file_path_str = str(file_path)
            if file_path_str in self._encoding_files:
                self._encoding_files.discard(file_path_str)
                self._file_timestamps.pop(file_path_str, None)
                logging.info(f'Force removed encoding file from tracker: {file_path_str}')
            else:
                logging.warning(f'File not found in encoding tracker: {file_path_str}')

    async def debugPrintTrackedFiles(self) -> None:
        """
        現在追跡中のファイル一覧をログに出力する（デバッグ用）
        """
        async with self._file_lock:
            if self._encoding_files:
                logging.info(f'Currently tracked encoding files ({len(self._encoding_files)} files): {list(self._encoding_files)}')
            else:
                logging.info('No files currently being tracked for encoding')

    async def cleanupStaleEntries(self, timeout_seconds: int | None = None) -> int:
        """
        長時間残っているエントリをクリーンアップする

        Args:
            timeout_seconds (int | None): タイムアウト時間（秒）。Noneの場合はデフォルト値を使用

        Returns:
            int: クリーンアップされたファイル数
        """
        if timeout_seconds is None:
            timeout_seconds = self._timeout_seconds

        current_time = time.time()
        stale_files = []

        async with self._file_lock:
            for file_path, timestamp in self._file_timestamps.items():
                if current_time - timestamp > timeout_seconds:
                    # ファイルが実際に存在し、最近更新されていないかチェック
                    if os.path.exists(file_path):
                        try:
                            file_mtime = os.path.getmtime(file_path)
                            # ファイルが5分以上更新されていない場合はstale
                            if current_time - file_mtime > 300:  # 5分
                                stale_files.append(file_path)
                        except OSError:
                            # ファイルアクセスエラーの場合もstaleとして扱う
                            stale_files.append(file_path)
                    else:
                        # ファイルが存在しない場合もstale
                        stale_files.append(file_path)

            # staleファイルを除去
            for file_path in stale_files:
                self._encoding_files.discard(file_path)
                self._file_timestamps.pop(file_path, None)
                logging.warning(f'Removed stale encoding file from tracker: {file_path}')

        return len(stale_files)

    async def isFileStale(self, file_path: str | Path, timeout_seconds: int | None = None) -> bool:
        """
        指定されたファイルがstale（長時間残っている）かどうかを確認する

        Args:
            file_path (str | Path): 確認するファイルパス
            timeout_seconds (int | None): タイムアウト時間（秒）

        Returns:
            bool: staleの場合True
        """
        if timeout_seconds is None:
            timeout_seconds = self._timeout_seconds

        async with self._file_lock:
            file_path_str = str(file_path)
            if file_path_str not in self._file_timestamps:
                return False

            current_time = time.time()
            timestamp = self._file_timestamps[file_path_str]
            return current_time - timestamp > timeout_seconds

    async def getFileAge(self, file_path: str | Path) -> float | None:
        """
        指定されたファイルがトラッカーに追加されてからの経過時間を取得する

        Args:
            file_path (str | Path): 確認するファイルパス

        Returns:
            float | None: 経過時間（秒）。ファイルが追跡されていない場合はNone
        """
        async with self._file_lock:
            file_path_str = str(file_path)
            if file_path_str not in self._file_timestamps:
                return None

            current_time = time.time()
            timestamp = self._file_timestamps[file_path_str]
            return current_time - timestamp
