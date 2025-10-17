"""
EPGStation API クライアント
EPGStation v2.10.0 の API を利用するためのユーティリティクラス
"""

from typing import Any, cast

import httpx
from pydantic_core import Url

from app import logging
from app.config import Config
from app.constants import API_REQUEST_HEADERS
from app.utils.epgstation.types import (
    EPGStationChannel,
    EPGStationProgram,
    EPGStationRecording,
    EPGStationReserve,
    EPGStationRule,
)


class EPGStationAPIError(Exception):
    """EPGStation API のエラー"""
    pass


class EPGStationUtil:
    """
    EPGStation API と通信するためのユーティリティクラス
    """

    def __init__(self, epgstation_url: Url | None = None):
        """
        Args:
            epgstation_url (Url | None): EPGStation の URL (指定されなかった場合は Config().general.epgstation_url から取得する)
        """
        if epgstation_url is None:
            self.epgstation_url = str(Config().general.epgstation_url).rstrip('/')
        else:
            self.epgstation_url = str(epgstation_url).rstrip('/')

        # API の Base URL
        self.api_base_url = self.epgstation_url + '/api'

        # HTTP クライアントはコンテキストマネージャで初期化
        self.client: httpx.AsyncClient | None = None


    async def close(self) -> None:
        """HTTP クライアントを閉じる"""
        if self.client is not None:
            await self.client.aclose()
            self.client = None


    async def __aenter__(self) -> 'EPGStationUtil':
        """async with 文で使用するための __aenter__"""
        self.client = httpx.AsyncClient(
            headers = API_REQUEST_HEADERS,
            timeout = 20.0,
            follow_redirects = True,
        )
        return self


    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """async with 文で使用するための __aexit__"""
        await self.close()


    def _handleAPIError(self, method_name: str, error: Exception, context: str = '') -> None:
        """
        API エラーを統一的に処理する

        Args:
            method_name (str): エラーが発生したメソッド名
            error (Exception): 発生した例外
            context (str): エラーの文脈情報（ID など）
        """
        context_str = f' ({context})' if context else ''

        if isinstance(error, httpx.ConnectError):
            logging.error(f'[EPGStationUtil][{method_name}] Cannot connect to EPGStation at {self.epgstation_url}{context_str}')
        elif isinstance(error, httpx.TimeoutException):
            logging.error(f'[EPGStationUtil][{method_name}] Request timeout to EPGStation{context_str}')
        elif isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            try:
                response_body = error.response.text
                logging.error(f'[EPGStationUtil][{method_name}] HTTP {status_code} error{context_str}: {error}. Response body: {response_body}')
            except Exception:
                logging.error(f'[EPGStationUtil][{method_name}] HTTP {status_code} error{context_str}: {error}')
        else:
            logging.error(f'[EPGStationUtil][{method_name}] Unexpected error{context_str}: {error}', exc_info=True)


    async def checkConnection(self) -> bool:
        """
        EPGStation への接続を確認する

        Returns:
            bool: 接続成功の場合は True、失敗の場合は False
        """
        try:
            # チャンネル一覧を取得してみる（軽量なエンドポイント）
            response = await self.client.get(f'{self.api_base_url}/channels')
            response.raise_for_status()
            logging.info(f'[EPGStationUtil][checkConnection] Successfully connected to EPGStation at {self.epgstation_url}')
            return True
        except httpx.ConnectError as ex:
            logging.error(f'[EPGStationUtil][checkConnection] Cannot connect to EPGStation at {self.epgstation_url}: {ex}')
            return False
        except httpx.TimeoutException as ex:
            logging.error(f'[EPGStationUtil][checkConnection] Request timeout to EPGStation at {self.epgstation_url}: {ex}')
            return False
        except httpx.HTTPStatusError as ex:
            status_code = ex.response.status_code
            logging.error(f'[EPGStationUtil][checkConnection] HTTP {status_code} error at {self.epgstation_url}: {ex}')
            return False
        except Exception as ex:
            logging.error(f'[EPGStationUtil][checkConnection] Unexpected error at {self.epgstation_url}: {ex}')
            return False


    # ***** チャンネル関連 *****

    async def getChannels(self) -> list[EPGStationChannel]:
        """
        放送局情報を取得する

        Returns:
            list[EPGStationChannel]: 放送局情報のリスト
        """
        try:
            response = await self.client.get(f'{self.api_base_url}/channels')
            response.raise_for_status()
            return cast(list[EPGStationChannel], response.json())
        except Exception as ex:
            self._handleAPIError('getChannels', ex)
            return []


    async def getSchedules(self, is_half_width: bool = False, start_at: int | None = None, end_at: int | None = None) -> list[dict[str, Any]]:
        """
        番組表情報を取得する（全チャンネル・全番組）

        Args:
            is_half_width (bool): 半角文字列で取得するかどうか
            start_at (int | None): 取得開始時刻（Unix timestamp ミリ秒、省略時は現在時刻）
            end_at (int | None): 取得終了時刻（Unix timestamp ミリ秒、省略時は start_at + 8日）

        Returns:
            list[dict[str, Any]]: 番組表情報のリスト（チャンネルごとの番組リスト）
        """
        try:
            # EPGStation API の必須パラメーター: startAt, endAt, isHalfWidth
            # 現在時刻を取得（ミリ秒単位の Unix timestamp）
            import time
            now_ms = int(time.time() * 1000)

            # デフォルト値の設定
            if start_at is None:
                start_at = now_ms
            if end_at is None:
                # デフォルトで8日分（8日 * 24時間 * 60分 * 60秒 * 1000ミリ秒）
                end_at = start_at + (8 * 24 * 60 * 60 * 1000)

            # EPGStation API は isHalfWidth を 'true'/'false' の文字列で受け付ける
            # また、放送波タイプのパラメーター (GR, BS, CS, SKY) も必要
            params: dict[str, Any] = {
                'startAt': start_at,
                'endAt': end_at,
                'isHalfWidth': 'true' if is_half_width else 'false',
                # すべての放送波タイプを取得（パラメーター未指定だとエラーになる可能性がある）
                'GR': 'true',
                'BS': 'true',
                'CS': 'true',
                'SKY': 'true',
            }

            response = await self.client.get(f'{self.api_base_url}/schedules', params=params)
            response.raise_for_status()
            data = response.json()

            # レスポンスは直接配列形式
            if not isinstance(data, list):
                logging.warning(f'[EPGStationUtil][getSchedules] Unexpected response type: {type(data)}')
                data = []
            return cast(list[dict[str, Any]], data)
        except Exception as ex:
            self._handleAPIError('getSchedules', ex)
            return []


    # ***** 番組関連 *****

    async def getProgram(self, program_id: int, is_half_width: bool = True) -> EPGStationProgram | None:
        """
        指定された番組情報を取得する

        Args:
            program_id (int): 番組 ID
            is_half_width (bool): 半角文字で取得するか (デフォルト: True)

        Returns:
            EPGStationProgram | None: 番組情報 (取得できなかった場合は None)
        """
        try:
            response = await self.client.get(
                f'{self.api_base_url}/schedules/detail/{program_id}',
                params = {'isHalfWidth': 'true' if is_half_width else 'false'},
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'program' in data:
                    data = data.get('program')
                elif 'item' in data:
                    data = data.get('item')
            return cast(EPGStationProgram, data)
        except httpx.HTTPStatusError as ex:
            if ex.response.status_code == 404:
                # 404エラーは想定内（フォールバック処理があるため）
                # DEBUGレベルでログ出力し、詳細なエラーメッセージは出さない
                logging.debug(
                    '[EPGStationUtil][getProgram] Program not found by direct ID lookup (fallback to search will be attempted). '
                    f'[program_id: {program_id}]'
                )
                return None
            self._handleAPIError('getProgram', ex, f'Program ID: {program_id}')
            return None
        except Exception as ex:
            self._handleAPIError('getProgram', ex, f'Program ID: {program_id}')
            return None


    async def searchPrograms(self, search_option: dict[str, Any]) -> list[EPGStationProgram]:
        """
        番組を検索する

        Args:
            search_option (dict[str, Any]): 検索オプション

        Returns:
            list[EPGStationProgram]: 検索結果の番組リスト
        """
        try:
            response = await self.client.post(
                f'{self.api_base_url}/schedules/search',
                json = search_option,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'items' in data:
                    data = data.get('items')
            if not isinstance(data, list):
                data = []
            return cast(list[EPGStationProgram], data)
        except Exception as ex:
            self._handleAPIError('searchPrograms', ex)
            return []


    # ***** 予約関連 *****

    async def getReserves(self, is_half_width: bool = False) -> list[EPGStationReserve]:
        """
        予約情報のリストを取得する

        Args:
            is_half_width (bool): 半角文字列で取得するかどうか

        Returns:
            list[EPGStationReserve]: 予約情報のリスト
        """
        try:
            params = {'isHalfWidth': str(is_half_width).lower()}
            response = await self.client.get(f'{self.api_base_url}/reserves', params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'items' in data:
                    data = data.get('items')
                elif 'reserves' in data:
                    data = data.get('reserves')
            if not isinstance(data, list):
                data = []
            return cast(list[EPGStationReserve], data)
        except Exception as ex:
            self._handleAPIError('getReserves', ex)
            return []


    async def getReserve(self, reserve_id: int, is_half_width: bool = False) -> EPGStationReserve | None:
        """
        指定された予約情報を取得する

        Args:
            reserve_id (int): 予約 ID
            is_half_width (bool): 半角文字列で取得するかどうか

        Returns:
            EPGStationReserve | None: 予約情報 (取得できなかった場合は None)
        """
        try:
            params = {'isHalfWidth': str(is_half_width).lower()}
            response = await self.client.get(f'{self.api_base_url}/reserves/{reserve_id}', params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'reserve' in data:
                    data = data.get('reserve')
                elif 'item' in data:
                    data = data.get('item')
            if not isinstance(data, dict):
                return None
            return cast(EPGStationReserve, data)
        except Exception as ex:
            self._handleAPIError('getReserve', ex, f'Reserve ID: {reserve_id}')
            return None


    async def addReserve(
        self,
        program_id: int,
        option: dict[str, Any] | None = None,
        allow_end_lack: bool | None = None,
    ) -> int | None:
        """
        予約を追加する

        Args:
            program_id (int): 番組 ID
            option (dict[str, Any] | None): 予約オプション
            allow_end_lack (bool | None): 終了時刻が欠けることを許可するかどうか

        Returns:
            int | None: 追加された予約 ID (失敗した場合は None)
        """
        try:
            request_data: dict[str, Any] = {'programId': program_id}
            if option is not None:
                request_data['option'] = option
                if allow_end_lack is None:
                    option_allow_end_lack = option.get('allowEndLack')
                    if isinstance(option_allow_end_lack, bool):
                        allow_end_lack = option_allow_end_lack

            if allow_end_lack is None:
                allow_end_lack = True

            request_data['allowEndLack'] = allow_end_lack

            response = await self.client.post(
                f'{self.api_base_url}/reserves',
                json = request_data,
            )
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict):
                if 'reserveId' in result:
                    return cast(int, result.get('reserveId'))
                if 'id' in result:
                    return cast(int, result.get('id'))
            return None
        except httpx.HTTPStatusError as ex:
            # HTTP エラーの場合はレスポンスボディも出力
            logging.error(
                f'[EPGStationUtil][addReserve] HTTP {ex.response.status_code} error (Program ID: {program_id}). '
                f'Request: {request_data}, Response: {ex.response.text}'
            )
            return None
        except Exception as ex:
            self._handleAPIError('addReserve', ex, f'Program ID: {program_id}')
            return None


    async def updateReserve(
        self,
        reserve_id: int,
        option: dict[str, Any],
        allow_end_lack: bool | None = None,
    ) -> bool:
        """
        予約を更新する

        Args:
            reserve_id (int): 予約 ID
            option (dict[str, Any]): 予約オプション
            allow_end_lack (bool | None): 終了時刻が欠けることを許可するかどうか

        Returns:
            bool: 成功したかどうか
        """
        try:
            # 既存の予約情報を取得
            reserve = await self.getReserve(reserve_id)
            if reserve is None:
                logging.warning(f'[EPGStationUtil][updateReserve] Reserve not found (ID: {reserve_id})')
                return False

            # 予約情報を更新
            request_data: dict[str, Any] = {
                'programId': reserve.get('programId'),
                'option': option,
            }

            if allow_end_lack is None:
                option_allow_end_lack = option.get('allowEndLack')
                if isinstance(option_allow_end_lack, bool):
                    allow_end_lack = option_allow_end_lack
                else:
                    reserve_allow_end_lack = reserve.get('allowEndLack')
                    if isinstance(reserve_allow_end_lack, bool):
                        allow_end_lack = reserve_allow_end_lack

            if allow_end_lack is None:
                allow_end_lack = True

            request_data['allowEndLack'] = allow_end_lack

            response = await self.client.put(
                f'{self.api_base_url}/reserves/{reserve_id}',
                json = request_data,
            )
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('updateReserve', ex, f'Reserve ID: {reserve_id}')
            return False


    async def deleteReserve(self, reserve_id: int) -> bool:
        """
        予約を削除する

        Args:
            reserve_id (int): 予約 ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            url = f'{self.api_base_url}/reserves/{reserve_id}'
            logging.info(f'[EPGStationUtil][deleteReserve] Attempting to delete reserve. URL: {url}, Reserve ID: {reserve_id}')
            response = await self.client.delete(url)
            logging.info(f'[EPGStationUtil][deleteReserve] Response status: {response.status_code}, Reserve ID: {reserve_id}')
            response.raise_for_status()
            logging.info(f'[EPGStationUtil][deleteReserve] Successfully deleted reserve. Reserve ID: {reserve_id}')
            return True
        except Exception as ex:
            self._handleAPIError('deleteReserve', ex, f'Reserve ID: {reserve_id}')
            return False


    async def cancelReserveSkip(self, reserve_id: int) -> bool:
        """
        予約のスキップ状態を解除する

        Args:
            reserve_id (int): 予約 ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.delete(f'{self.api_base_url}/reserves/{reserve_id}/skip')
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('cancelReserveSkip', ex, f'Reserve ID: {reserve_id}')
            return False


    async def cancelReserveOverlap(self, reserve_id: int) -> bool:
        """
        予約の重複状態を解除する

        Args:
            reserve_id (int): 予約 ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.delete(f'{self.api_base_url}/reserves/{reserve_id}/overlap')
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('cancelReserveOverlap', ex, f'Reserve ID: {reserve_id}')
            return False


    # ***** ルール関連 *****

    async def getRules(self) -> list[EPGStationRule]:
        """
        ルール情報のリストを取得する

        Returns:
            list[EPGStationRule]: ルール情報のリスト
        """
        try:
            response = await self.client.get(f'{self.api_base_url}/rules')
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'items' in data:
                    data = data.get('items')
                elif 'rules' in data:
                    data = data.get('rules')
            if not isinstance(data, list):
                data = []
            return cast(list[EPGStationRule], data)
        except Exception as ex:
            self._handleAPIError('getRules', ex)
            return []


    async def getRule(self, rule_id: int) -> EPGStationRule | None:
        """
        指定されたルール情報を取得する

        Args:
            rule_id (int): ルール ID

        Returns:
            EPGStationRule | None: ルール情報 (取得できなかった場合は None)
        """
        try:
            response = await self.client.get(f'{self.api_base_url}/rules/{rule_id}')
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'rule' in data:
                    data = data.get('rule')
                elif 'item' in data:
                    data = data.get('item')
            if not isinstance(data, dict):
                return None
            return cast(EPGStationRule, data)
        except Exception as ex:
            self._handleAPIError('getRule', ex, f'Rule ID: {rule_id}')
            return None


    async def addRule(self, rule_data: dict[str, Any]) -> int | None:
        """
        ルールを追加する

        Args:
            rule_data (dict[str, Any]): ルールデータ

        Returns:
            int | None: 追加されたルール ID (失敗した場合は None)
        """
        try:
            response = await self.client.post(
                f'{self.api_base_url}/rules',
                json = rule_data,
            )
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict):
                if 'ruleId' in result:
                    return cast(int, result.get('ruleId'))
                if 'id' in result:
                    return cast(int, result.get('id'))
            return None
        except Exception as ex:
            self._handleAPIError('addRule', ex)
            return None


    async def updateRule(self, rule_id: int, rule_data: dict[str, Any]) -> bool:
        """
        ルールを更新する

        Args:
            rule_id (int): ルール ID
            rule_data (dict[str, Any]): ルールデータ

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.put(
                f'{self.api_base_url}/rules/{rule_id}',
                json = rule_data,
            )
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('updateRule', ex, f'Rule ID: {rule_id}')
            return False


    async def deleteRule(self, rule_id: int) -> bool:
        """
        ルールを削除する

        Args:
            rule_id (int): ルール ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.delete(f'{self.api_base_url}/rules/{rule_id}')
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('deleteRule', ex, f'Rule ID: {rule_id}')
            return False


    async def enableRule(self, rule_id: int) -> bool:
        """
        ルールを有効化する

        Args:
            rule_id (int): ルール ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.put(f'{self.api_base_url}/rules/{rule_id}/enable')
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('enableRule', ex, f'Rule ID: {rule_id}')
            return False


    async def disableRule(self, rule_id: int) -> bool:
        """
        ルールを無効化する

        Args:
            rule_id (int): ルール ID

        Returns:
            bool: 成功したかどうか
        """
        try:
            response = await self.client.put(f'{self.api_base_url}/rules/{rule_id}/disable')
            response.raise_for_status()
            return True
        except Exception as ex:
            self._handleAPIError('disableRule', ex, f'Rule ID: {rule_id}')
            return False


    # ***** 録画中情報関連 *****

    async def getRecordings(self, is_half_width: bool = False, offset: int = 0, limit: int = 24) -> list[EPGStationRecording]:
        """
        録画中情報のリストを取得する

        Args:
            is_half_width (bool): 半角文字列で取得するかどうか
            offset (int): オフセット
            limit (int): 取得件数の上限

        Returns:
            list[EPGStationRecording]: 録画中情報のリスト
        """
        try:
            params = {
                'isHalfWidth': str(is_half_width).lower(),
                'offset': offset,
                'limit': limit,
            }
            response = await self.client.get(f'{self.api_base_url}/recording', params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if 'items' in data:
                    data = data.get('items')
                elif 'records' in data:
                    data = data.get('records')
            if not isinstance(data, list):
                data = []
            return cast(list[EPGStationRecording], data)
        except Exception as ex:
            self._handleAPIError('getRecordings', ex)
            return []
