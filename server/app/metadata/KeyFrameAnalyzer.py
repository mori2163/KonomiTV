
import asyncio
import json
import time
from pathlib import Path
from typing import Literal

import anyio
import typer
from tortoise import Tortoise
from tortoise.exceptions import MultipleObjectsReturned

from app import logging, schemas
from app.config import Config, LoadConfig
from app.constants import DATABASE_CONFIG, LIBRARY_PATH
from app.models.RecordedVideo import RecordedVideo


class KeyFrameAnalyzer:
    """
    録画ファイルのキーフレーム情報を解析するクラス
    ffprobe を使用して、録画ファイルのキーフレーム情報を取得し、DB に保存する
    解析した情報はストリーミング再生時に活用される
    """

    def __init__(self, file_path: anyio.Path, container_format: Literal['MPEG-TS', 'MPEG-4']) -> None:
        """
        録画ファイルのキーフレーム情報を解析するクラスを初期化する

        Args:
            file_path (anyio.Path): 解析対象の録画ファイルのパス
            container_format (Literal['MPEG-TS', 'MPEG-4']): 解析対象の録画ファイルのコンテナ形式
        """

        self.file_path = file_path
        self.container_format = container_format

    def _is_encoded_file(self) -> bool:
        """
        ファイルがエンコード済みファイルかどうかを判定する

        Returns:
            bool: エンコード済みファイルの場合True
        """
        try:
            # まず、ファイル名にエンコード識別子が含まれているかチェック（最も確実）
            import pathlib
            filename = pathlib.Path(self.file_path).name
            if '_h264' in filename or '_h265' in filename or '_av1' in filename:
                return True

            # 設定が利用可能な場合のみエンコード済みフォルダをチェック
            try:
                config = Config()
                if config.general.tsreplace and config.general.tsreplace.encoded_folders:
                    # ファイルパスがエンコード済みフォルダ内にあるかチェック
                    for encoded_folder in config.general.tsreplace.encoded_folders:
                        encoded_path = pathlib.Path(encoded_folder)
                        try:
                            # ファイルがエンコード済みフォルダ内にあるかチェック
                            pathlib.Path(self.file_path).relative_to(encoded_path)
                            return True
                        except ValueError:
                            # relative_to で ValueError が発生した場合、パスが含まれていない
                            continue
            except Exception:
                # 設定が利用できない場合は、ファイル名のみで判定
                pass

            return False

        except Exception:
            # エラーが発生した場合はエンコード済みファイルではないと仮定
            return False


    async def analyzeAndSave(self) -> None:
        """
        録画ファイルのキーフレーム情報を解析し、データベースに保存する
        ffprobe を使い、録画ファイルから以下の情報を取得して、DB に保存する
        - キーフレームの位置 (ファイル内のバイトオフセット)
        - キーフレームの DTS (Decoding Time Stamp)
        """

        start_time = time.time()
        logging.info(f'{self.file_path}: Analyzing keyframes...')

        # エンコード済みファイルの場合は、キーフレーム解析をスキップする
        # エンコード済みファイルのキーフレーム情報は元ファイルから継承されるべき
        if self._is_encoded_file():
            logging.info(f'{self.file_path}: Skipping keyframe analysis for encoded file (should inherit from original)')
            return

        try:
            if self.container_format != 'MPEG-TS':
                # エンコードタスクで psisimux を使用するので、予めオープンできない形式ならばキーフレームの取得を中断する
                options = [
                    # 1バイトだけ出力
                    '-r', '1',
                    # 文字コードが UTF-8 の字幕を ARIB8 単位符号に変換する
                    '-8',
                    # 字幕ファイルの拡張子
                    '-x', '.vtt',
                    # 入力ファイル名
                    str(self.file_path),
                    # 標準出力
                    '-',
                ]

                # psisimux プロセスを非同期で実行
                psisimux_process = await asyncio.subprocess.create_subprocess_exec(
                    LIBRARY_PATH['psisimux'],
                    *options,
                    # 明示的に標準入力を無効化しないと、親プロセスの標準入力が引き継がれてしまう
                    stdin = asyncio.subprocess.DEVNULL,
                    # 標準出力・標準エラー出力をパイプで受け取る
                    stdout = asyncio.subprocess.PIPE,
                    stderr = asyncio.subprocess.PIPE,
                )

                # プロセスの出力を取得
                _, stderr = await psisimux_process.communicate()

                # 終了コードを確認
                if psisimux_process.returncode != 0:
                    error_message = stderr.decode('utf-8', errors='ignore')
                    logging.error(f'{self.file_path}: psisimux execution failed with return code {psisimux_process.returncode}. Error: {error_message}')
                    return

            # ffprobe のオプションを設定
            ## -i: 入力ファイルを指定
            ## -select_streams v:0: 最初の映像ストリームのみを選択
            ## -show_packets: パケット情報を表示
            ## -show_entries packet=pos,dts,flags: パケットの位置, DTS, フラグを表示
            ## -of json: JSON 形式で出力
            options = [
                '-i', str(self.file_path),
                '-select_streams', 'v:0',
                '-show_packets',
                # MPEG-TS 形式でない場合、時間で効率よくシークできるためパケットの位置は出力しない
                # MPEG-TS 形式でない場合、time_base も出力する
                '-show_entries', 'packet=pos,dts,flags' if self.container_format == 'MPEG-TS' else 'packet=dts,flags:stream=time_base',
                '-of', 'json',
            ]

            # FFprobe プロセスを非同期で実行
            ffprobe_process = await asyncio.subprocess.create_subprocess_exec(
                LIBRARY_PATH['FFprobe'],
                *options,
                # 明示的に標準入力を無効化しないと、親プロセスの標準入力が引き継がれてしまう
                stdin = asyncio.subprocess.DEVNULL,
                # 標準出力・標準エラー出力をパイプで受け取る
                stdout = asyncio.subprocess.PIPE,
                stderr = asyncio.subprocess.PIPE,
            )

            # プロセスの出力を取得
            stdout, stderr = await ffprobe_process.communicate()

            # 終了コードを確認
            if ffprobe_process.returncode != 0:
                error_message = stderr.decode('utf-8', errors='ignore')
                logging.error(f'{self.file_path}: ffprobe analysis failed with return code {ffprobe_process.returncode}. Error: {error_message}')
                return

            # ffprobe の出力を JSON としてパース
            try:
                ffprobe_json = json.loads(stdout.decode('utf-8'))
                packets = ffprobe_json['packets']
                if self.container_format != 'MPEG-TS':
                    streams = ffprobe_json['streams']
                else:
                    streams = None
            except (json.JSONDecodeError, KeyError) as ex:
                logging.error(f'{self.file_path}: Failed to parse ffprobe output:', exc_info=ex)
                return

            # MPEG-TS 形式でない場合は time_base を取得
            if self.container_format != 'MPEG-TS':
                # time_base が見つからなかった場合
                if not streams or 'time_base' not in streams[0] or len(streams[0]['time_base'].split('/')) != 2:
                    logging.error(f'{self.file_path}: No time_base found in streams of ffprobe output.')
                    return
                # 分数をパース
                time_base = (int(streams[0]['time_base'].split('/')[0]), int(streams[0]['time_base'].split('/')[1]))
                if time_base[0] <= 0 or time_base[1] <= 0:
                    logging.error(f'{self.file_path}: Invalid time_base in streams of ffprobe output.')
            else:
                time_base = None

            # キーフレーム情報を抽出
            ## pos はファイル内のバイトオフセット
            ## dts は Decoding Time Stamp (デコード時刻)
            ## flags に 'K' が含まれているパケットがキーフレーム
            key_frames: list[schemas.KeyFrame] = []
            first_dts: int | None = None
            for packet in packets:
                # 必要なフィールドが存在することを確認（存在しないパケットは無視）
                if 'flags' not in packet or 'dts' not in packet or \
                   (self.container_format == 'MPEG-TS' and 'pos' not in packet):
                    continue
                # キーフレームのみを抽出
                # ただし、最後のフレームが非キーフレームの場合、シーク可能性のために追加
                if 'K' in packet['flags'] or packet is packets[-1]:
                    # MPEG-TS 形式の場合
                    if self.container_format == 'MPEG-TS':
                        key_frames.append({
                            'offset': int(packet['pos']),
                            'dts': int(packet['dts']),
                        })
                    # MPEG-TS 形式でない場合
                    else:
                        assert time_base is not None
                        if first_dts is None:
                            first_dts = int(packet['dts'])
                        # offset: 添え字と同値とする
                        # dts: time_base を 90000Hz に変換したもの
                        key_frames.append({
                            'offset': len(key_frames),
                            'dts': (int(packet['dts']) - first_dts) * time_base[0] * 90000 // time_base[1],
                        })

            # パケットが1つも見つからなかった場合
            if not packets:
                logging.error(f'{self.file_path}: No packets found in ffprobe output.')
                return

            # キーフレームが1つも見つからなかった場合
            if not key_frames:
                logging.error(f'{self.file_path}: No keyframes found in the video.')
                return

            # DB に保存
            ## ファイルパスから対応する RecordedVideo レコードを取得
            try:
                db_recorded_video = await RecordedVideo.get_or_none(file_path=str(self.file_path))
            except MultipleObjectsReturned:
                # 複数のレコードが存在する場合、最新のものを取得
                db_recorded_video = await RecordedVideo.filter(file_path=str(self.file_path)).order_by('-id').first()
                logging.warning(f'{self.file_path}: Multiple RecordedVideo records found, using latest (ID: {db_recorded_video.id if db_recorded_video else "None"})')

            if db_recorded_video is not None:
                # キーフレーム情報を更新
                db_recorded_video.key_frames = key_frames
                await db_recorded_video.save()
                logging.info(f'{self.file_path}: Keyframe analysis completed. ({len(key_frames)} keyframes found / {time.time() - start_time:.2f} sec)')
            else:
                logging.warning(f'{self.file_path}: RecordedVideo record not found.')

        except Exception as ex:
            logging.error(f'{self.file_path}: Error in keyframe analysis:', exc_info=ex)


if __name__ == '__main__':
    # デバッグ用: 録画ファイルのパスを引数に取り、そのファイルのキーフレーム情報を解析する
    # Usage: poetry run python -m app.metadata.KeyFrameAnalyzer /path/to/recorded_file.ts
    def main(recorded_file_path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True)):
        LoadConfig(bypass_validation=True)  # 一度実行しておかないと設定値を参照できない
        key_frame_analyzer = KeyFrameAnalyzer(anyio.Path(str(recorded_file_path)), 'MPEG-TS')
        async def amain():
            await Tortoise.init(config=DATABASE_CONFIG)
            await key_frame_analyzer.analyzeAndSave()
            await Tortoise.close_connections()
        asyncio.run(amain())
    typer.run(main)
