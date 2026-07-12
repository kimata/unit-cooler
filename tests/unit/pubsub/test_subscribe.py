#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""unit_cooler.pubsub.subscribe のテスト"""

from __future__ import annotations

import multiprocessing
import pathlib
import threading
from unittest.mock import MagicMock

import zmq

from unit_cooler.const import COOLING_STATE
from unit_cooler.messages import DutyConfig


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


class TestQueuePut:
    """queue_put のテスト"""

    def test_puts_message_to_queue(self, mocker):
        """キューにメッセージを追加"""
        import unit_cooler.pubsub.subscribe

        mocker.patch("my_lib.footprint.update")

        queue = multiprocessing.Queue(maxsize=10)
        duty_dict = {"enable": True, "on_sec": 100, "off_sec": 60}
        message = {"state": 1, "mode_index": 3, "duty": duty_dict}
        liveness_file = pathlib.Path("/tmp/test_liveness")

        unit_cooler.pubsub.subscribe.queue_put(queue, message, liveness_file, drop_oldest=True)

        result = queue.get(timeout=1)
        assert result.state == COOLING_STATE.WORKING
        assert result.mode_index == 3
        assert result.duty == DutyConfig(enable=True, on_sec=100, off_sec=60)

    def test_converts_state_to_enum(self, mocker):
        """state を Enum に変換"""
        import unit_cooler.pubsub.subscribe

        mocker.patch("my_lib.footprint.update")

        queue = multiprocessing.Queue(maxsize=10)
        duty_dict = {"enable": False, "on_sec": 0, "off_sec": 0}
        message = {"state": 1, "mode_index": 5, "duty": duty_dict}  # state は int
        liveness_file = pathlib.Path("/tmp/test_liveness")

        unit_cooler.pubsub.subscribe.queue_put(queue, message, liveness_file, drop_oldest=True)

        result = queue.get(timeout=1)
        assert result.state == COOLING_STATE.WORKING
        assert isinstance(result.state, COOLING_STATE)

    def test_removes_old_message_when_queue_full(self, mocker):
        """キューが満杯の場合、古いメッセージを削除"""
        import time

        import unit_cooler.pubsub.subscribe

        mocker.patch("my_lib.footprint.update")

        # maxsize=1 で満杯になるキューを作成
        queue = multiprocessing.Queue(maxsize=1)
        liveness_file = pathlib.Path("/tmp/test_liveness")

        duty_dict = {"enable": True, "on_sec": 100, "off_sec": 60}

        # 最初のメッセージを追加 (state=1: WORKING)
        first_message = {"state": 1, "mode_index": 1, "duty": duty_dict}
        unit_cooler.pubsub.subscribe.queue_put(queue, first_message, liveness_file, drop_oldest=True)

        # NOTE: multiprocessing.Queue は put() 直後だと feeder スレッドが未フラッシュで
        # get_nowait() が空振りし得るため、フラッシュを待つ
        time.sleep(0.1)

        # 2番目のメッセージを追加（最初のメッセージは削除される）(state=0: IDLE)
        second_message = {"state": 0, "mode_index": 2, "duty": duty_dict}
        unit_cooler.pubsub.subscribe.queue_put(queue, second_message, liveness_file, drop_oldest=True)

        # 2番目のメッセージが取得される
        result = queue.get(timeout=1)
        assert result.state == COOLING_STATE.IDLE
        assert result.mode_index == 2

    def test_does_not_block_when_queue_drained_between_full_and_get(self, mocker):
        """full() チェック後に消費側がキューを空にしてもブロックしない（TOCTOU）"""
        import queue as queue_module

        import unit_cooler.pubsub.subscribe

        mocker.patch("my_lib.footprint.update")

        # full() は True を返すが実際には空、というレース状態をモックで再現する
        mock_queue = MagicMock()
        mock_queue.full.return_value = True
        mock_queue.get_nowait.side_effect = queue_module.Empty()

        duty_dict = {"enable": True, "on_sec": 100, "off_sec": 60}
        message = {"state": 1, "mode_index": 3, "duty": duty_dict}
        liveness_file = pathlib.Path("/tmp/test_liveness")

        # ブロッキング get() を使っているとここで凍結する
        unit_cooler.pubsub.subscribe.queue_put(mock_queue, message, liveness_file, drop_oldest=True)

        mock_queue.get_nowait.assert_called_once()
        mock_queue.put.assert_called_once()

    def test_works_with_thread_queue(self, mocker):
        """queue.Queue（webui で使用）でも動作する"""
        import queue as queue_module

        import unit_cooler.pubsub.subscribe

        mocker.patch("my_lib.footprint.update")

        thread_queue: queue_module.Queue = queue_module.Queue(maxsize=1)
        liveness_file = pathlib.Path("/tmp/test_liveness")

        duty_dict = {"enable": True, "on_sec": 100, "off_sec": 60}
        first_message = {"state": 1, "mode_index": 1, "duty": duty_dict}
        second_message = {"state": 0, "mode_index": 2, "duty": duty_dict}

        unit_cooler.pubsub.subscribe.queue_put(thread_queue, first_message, liveness_file, drop_oldest=True)
        unit_cooler.pubsub.subscribe.queue_put(thread_queue, second_message, liveness_file, drop_oldest=True)

        result = thread_queue.get_nowait()
        assert result.mode_index == 2
