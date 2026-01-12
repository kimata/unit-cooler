#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.pubsub.subscribe のテスト"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import zmq


class TestStartClient:
    """start_client のテスト"""

    def test_connects_to_server(self, mocker):
        """サーバーに接続"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        # すぐにタイムアウト
        mock_socket.recv_string.side_effect = zmq.Again()

        # 終了フラグを使用
        should_terminate = threading.Event()
        should_terminate.set()  # すぐに終了

        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=lambda x: None,
            msg_count=0,
            should_terminate=should_terminate,
        )

        mock_socket.connect.assert_called_with("tcp://localhost:2222")

    def test_subscribes_to_channel(self, mocker):
        """チャンネルを購読"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        mock_socket.recv_string.side_effect = zmq.Again()

        should_terminate = threading.Event()
        should_terminate.set()

        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=lambda x: None,
            msg_count=0,
            should_terminate=should_terminate,
        )

        mock_socket.setsockopt_string.assert_called_with(zmq.SUBSCRIBE, "unit_cooler")

    def test_calls_func_on_message(self, mocker):
        """メッセージ受信時にコールバック関数を呼ぶ"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        # メッセージを返してから終了
        mock_socket.recv_string.return_value = 'unit_cooler {"test": "data"}'

        received = []

        def callback(data):
            received.append(data)

        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=callback,
            msg_count=1,  # 1回受信で終了
        )

        assert len(received) == 1
        assert received[0] == {"test": "data"}

    def test_terminates_on_msg_count(self, mocker):
        """指定回数受信で終了"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        mock_socket.recv_string.return_value = 'unit_cooler {"count": 1}'

        receive_count = [0]

        def callback(data):
            receive_count[0] += 1

        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=callback,
            msg_count=3,
        )

        assert receive_count[0] == 3

    def test_cleans_up_resources(self, mocker):
        """リソースをクリーンアップ"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        mock_socket.recv_string.side_effect = zmq.Again()

        should_terminate = threading.Event()
        should_terminate.set()

        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=lambda x: None,
            msg_count=0,
            should_terminate=should_terminate,
        )

        mock_socket.disconnect.assert_called_with("tcp://localhost:2222")
        mock_socket.close.assert_called()
        mock_context.destroy.assert_called()


class TestMessageParsing:
    """メッセージパースのテスト"""

    def test_parses_json_message(self, mocker):
        """JSON メッセージをパース"""
        import unit_cooler.pubsub.subscribe

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        mock_socket.recv_string.return_value = 'unit_cooler {"mode_index": 5, "state": 1}'

        received = []
        unit_cooler.pubsub.subscribe.start_client(
            server_host="localhost",
            server_port=2222,
            func=lambda x: received.append(x),
            msg_count=1,
        )

        assert received[0]["mode_index"] == 5
        assert received[0]["state"] == 1
