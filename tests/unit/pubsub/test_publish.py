#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.pubsub.publish のテスト"""

from __future__ import annotations

from unittest.mock import MagicMock

import zmq


class TestWaitFirstClient:
    """wait_first_client のテスト"""

    def test_returns_on_client_connection(self, mocker):
        """クライアント接続で戻る"""
        import unit_cooler.pubsub.publish

        mock_socket = MagicMock()
        mock_poller = MagicMock()
        mocker.patch("zmq.Poller", return_value=mock_poller)

        # クライアント接続イベント (event[0] == 1)
        mock_socket.recv.return_value = bytes([1]) + b"channel"
        mock_poller.poll.return_value = [(mock_socket, 1)]

        unit_cooler.pubsub.publish.wait_first_client(mock_socket, timeout=0.1)

        mock_socket.send.assert_called()


class TestStartServer:
    """start_server のテスト"""

    def test_server_binds_to_port(self, mocker):
        """サーバーがポートにバインド"""
        import unit_cooler.pubsub.publish

        mock_context = MagicMock()
        mock_socket = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)
        mocker.patch.object(unit_cooler.pubsub.publish, "wait_first_client")
        # ループ内のsleepをスキップして高速化
        mocker.patch("unit_cooler.pubsub.publish.time.sleep")

        # recv でエラーを発生させて早期終了
        mock_socket.recv.side_effect = zmq.Again()

        def test_func():
            return {"test": "data"}

        unit_cooler.pubsub.publish.start_server(
            server_port=12345,
            func=test_func,
            interval_sec=0.01,
            msg_count=1,
        )

        mock_socket.bind.assert_called_with("tcp://*:12345")


class TestPubSubConst:
    """定数のテスト"""

    def test_pubsub_channel_defined(self):
        """PUBSUB_CH が定義されている"""
        import unit_cooler.const

        assert hasattr(unit_cooler.const, "PUBSUB_CH")
        assert unit_cooler.const.PUBSUB_CH == "unit_cooler"
