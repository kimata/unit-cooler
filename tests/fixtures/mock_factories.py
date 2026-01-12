#!/usr/bin/env python3
"""モックファクトリーモジュール"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class FDQ10CMockFactory:
    """FD-Q10C 流量センサーモックファクトリー

    Keyence FD-Q10C 流量センサーの SPI 通信をモックする。
    """

    # SPI トランザクションパターン
    NORMAL_FLOW_TRANSACTIONS: ClassVar[list[dict]] = [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
        {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x01, 0x2D]},  # 流量あり
        {"send": [0xE2, 0x0B], "recv": [0xE2, 0x0B, 0x01, 0x2D]},
        {"send": [0xE3, 0x3A], "recv": [0xE3, 0x3A, 0x01, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]

    ZERO_FLOW_TRANSACTIONS: ClassVar[list[dict]] = [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
        {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x00, 0x2D]},  # 流量なし
        {"send": [0xE2, 0x0B], "recv": [0xE2, 0x0B, 0x00, 0x2D]},
        {"send": [0xE3, 0x3A], "recv": [0xE3, 0x3A, 0x00, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]

    PING_TRANSACTIONS: ClassVar[list[dict]] = [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]

    def __init__(self):
        self.transactions: list[dict] = []
        self.transaction_index = 0
        self.call_count = 0

    def create(
        self,
        mocker: MockerFixture,
        transactions: list[dict] | None = None,
        flow_value: float = 2.57,
        is_zero: bool = False,
    ) -> MagicMock:
        """FD-Q10C モックを作成

        Args:
            mocker: pytest-mock の mocker fixture
            transactions: SPI トランザクションリスト
            flow_value: 返す流量値
            is_zero: ゼロ流量の場合 True

        Returns:
            FD-Q10C モックオブジェクト
        """
        if transactions is not None:
            self.transactions = transactions
        elif is_zero:
            self.transactions = self.ZERO_FLOW_TRANSACTIONS.copy()
        else:
            self.transactions = self.NORMAL_FLOW_TRANSACTIONS.copy()

        self.transaction_index = 0
        self.call_count = 0

        fd_q10c_mock = MagicMock()
        fd_q10c_mock.get_value.return_value = flow_value if not is_zero else 0.0
        fd_q10c_mock.get_state.return_value = True

        # SPI 通信モック
        def xfer2_side_effect(data: list[int]) -> list[int]:
            if self.transaction_index < len(self.transactions):
                trans = self.transactions[self.transaction_index]
                self.transaction_index += 1
                return trans.get("recv", data)
            return data

        spi_mock = MagicMock()
        spi_mock.xfer2.side_effect = xfer2_side_effect

        mocker.patch("spidev.SpiDev", return_value=spi_mock)
        mocker.patch("my_lib.sensor.fd_q10c.FD_Q10C", return_value=fd_q10c_mock)

        return fd_q10c_mock

    def reset(self) -> None:
        """トランザクションインデックスをリセット"""
        self.transaction_index = 0
        self.call_count = 0


class InfluxDBMockFactory:
    """InfluxDB モックファクトリー"""

    def __init__(self):
        self.query_results: list = []
        self.write_calls: list = []

    def create(
        self,
        mocker: MockerFixture,
        query_results: list | None = None,
        raise_on_query: Exception | None = None,
    ) -> MagicMock:
        """InfluxDB クライアントモックを作成

        Args:
            mocker: pytest-mock の mocker fixture
            query_results: クエリ結果のリスト
            raise_on_query: クエリ時に発生させる例外

        Returns:
            InfluxDB クライアントモック
        """
        self.query_results = query_results or []
        self.write_calls = []

        client_mock = MagicMock()
        query_api_mock = MagicMock()
        write_api_mock = MagicMock()

        if raise_on_query:
            query_api_mock.query.side_effect = raise_on_query
        else:
            query_api_mock.query.return_value = self.query_results

        def write_side_effect(*args, **kwargs):
            self.write_calls.append((args, kwargs))

        write_api_mock.write.side_effect = write_side_effect

        client_mock.query_api.return_value = query_api_mock
        client_mock.write_api.return_value = write_api_mock

        mocker.patch("influxdb_client.InfluxDBClient", return_value=client_mock)

        return client_mock

    def get_write_calls(self) -> list:
        """書き込み呼び出しを取得"""
        return self.write_calls.copy()


class ZeroMQMockFactory:
    """ZeroMQ モックファクトリー"""

    def __init__(self):
        self.sent_messages: list[str] = []
        self.received_messages: list[str] = []
        self.receive_index = 0

    def create(
        self,
        mocker: MockerFixture,
        received_messages: list[str] | None = None,
        raise_on_send: Exception | None = None,
        raise_on_recv: Exception | None = None,
    ) -> MagicMock:
        """ZeroMQ ソケットモックを作成

        Args:
            mocker: pytest-mock の mocker fixture
            received_messages: 受信するメッセージのリスト
            raise_on_send: 送信時に発生させる例外
            raise_on_recv: 受信時に発生させる例外

        Returns:
            ZeroMQ コンテキストモック
        """
        self.received_messages = received_messages or []
        self.receive_index = 0
        self.sent_messages = []

        context_mock = MagicMock()
        socket_mock = MagicMock()

        def send_string_side_effect(msg: str, flags: int = 0) -> None:
            if raise_on_send:
                raise raise_on_send
            self.sent_messages.append(msg)

        def recv_string_side_effect(flags: int = 0) -> str:
            if raise_on_recv:
                raise raise_on_recv
            if self.receive_index < len(self.received_messages):
                msg = self.received_messages[self.receive_index]
                self.receive_index += 1
                return msg
            return ""

        socket_mock.send_string.side_effect = send_string_side_effect
        socket_mock.recv_string.side_effect = recv_string_side_effect

        context_mock.socket.return_value = socket_mock

        mocker.patch("zmq.Context", return_value=context_mock)

        return context_mock

    def get_sent_messages(self) -> list[str]:
        """送信されたメッセージを取得"""
        return self.sent_messages.copy()

    def add_received_message(self, message: str) -> None:
        """受信メッセージを追加"""
        self.received_messages.append(message)

    def reset(self) -> None:
        """状態をリセット"""
        self.sent_messages = []
        self.receive_index = 0


class SlackMockFactory:
    """Slack API モックファクトリー"""

    def __init__(self):
        self.posted_messages: list[dict] = []
        self.uploaded_files: list[dict] = []

    def create(self, mocker: MockerFixture) -> tuple[MagicMock, MagicMock]:
        """Slack API モックを作成

        Args:
            mocker: pytest-mock の mocker fixture

        Returns:
            (chat_postMessage モック, files_upload_v2 モック) のタプル
        """
        self.posted_messages = []
        self.uploaded_files = []

        def post_message_side_effect(**kwargs):
            self.posted_messages.append(kwargs)
            return {"ok": True, "ts": "1234567890.123456"}

        def upload_file_side_effect(**kwargs):
            self.uploaded_files.append(kwargs)
            return {"ok": True, "files": [{"id": "test_file_id"}]}

        chat_mock = mocker.patch(
            "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
            side_effect=post_message_side_effect,
        )
        file_mock = mocker.patch(
            "my_lib.notify.slack.slack_sdk.web.client.WebClient.files_upload_v2",
            side_effect=upload_file_side_effect,
        )

        return chat_mock, file_mock

    def get_posted_messages(self) -> list[dict]:
        """投稿されたメッセージを取得"""
        return self.posted_messages.copy()

    def get_uploaded_files(self) -> list[dict]:
        """アップロードされたファイルを取得"""
        return self.uploaded_files.copy()

    def assert_message_posted(self, text_contains: str) -> None:
        """特定のテキストを含むメッセージが投稿されたことを確認"""
        for msg in self.posted_messages:
            if text_contains in msg.get("text", ""):
                return
        raise AssertionError(f"Message containing '{text_contains}' was not posted")
