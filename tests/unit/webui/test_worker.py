#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""unit_cooler.webui.worker のテスト"""

from __future__ import annotations

import multiprocessing
import pathlib

from unit_cooler.const import COOLING_STATE


class TestGetLastActuatorStatus:
    """get_last_actuator_status のテスト"""

    def test_returns_none_initially(self):
        """初期状態は None"""
        import unit_cooler.webui.worker

        # リセット
        unit_cooler.webui.worker._last_actuator_status = None

        result = unit_cooler.webui.worker.get_last_actuator_status()

        assert result is None


class TestSetLastActuatorStatus:
    """set_last_actuator_status のテスト"""

    def test_sets_status(self):
        """ステータスを設定"""
        import unit_cooler.webui.worker
        from unit_cooler.const import VALVE_STATE
        from unit_cooler.messages import ActuatorStatus, ValveStatus

        valve_status = ValveStatus(
            state=VALVE_STATE.OPEN,
            duration_sec=10.5,
        )
        status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=1.5,
            cooling_mode_index=3,
            hazard_detected=False,
        )

        unit_cooler.webui.worker.set_last_actuator_status(status)
        result = unit_cooler.webui.worker.get_last_actuator_status()

        assert result == status


class TestTerm:
    """term のテスト"""

    def test_sets_terminate_flag(self):
        """終了フラグを設定"""
        import unit_cooler.webui.worker

        # リセット
        unit_cooler.webui.worker.should_terminate.clear()

        unit_cooler.webui.worker.term()

        assert unit_cooler.webui.worker.should_terminate.is_set()

    def teardown_method(self):
        """終了フラグをリセット"""
        import unit_cooler.webui.worker

        unit_cooler.webui.worker.should_terminate.clear()


class TestQueuePut:
    """queue_put のテスト"""

    def test_puts_message_to_queue(self, mocker):
        """キューにメッセージを追加"""
        import unit_cooler.webui.worker

        mocker.patch("my_lib.footprint.update")
        mocker.patch.object(unit_cooler.webui.worker, "_notify_state_manager_subscribe_processed")

        queue = multiprocessing.Queue(maxsize=10)
        message = {"state": 1, "mode_index": 3}
        liveness_file = pathlib.Path("/tmp/test_liveness")

        unit_cooler.webui.worker.queue_put(queue, message, liveness_file)

        result = queue.get(timeout=1)
        assert result["state"] == COOLING_STATE.WORKING
        assert result["mode_index"] == 3

    def test_converts_state_to_enum(self, mocker):
        """state を Enum に変換"""
        import unit_cooler.webui.worker

        mocker.patch("my_lib.footprint.update")
        mocker.patch.object(unit_cooler.webui.worker, "_notify_state_manager_subscribe_processed")

        queue = multiprocessing.Queue(maxsize=10)
        message = {"state": 1, "mode_index": 5}  # state は int
        liveness_file = pathlib.Path("/tmp/test_liveness")

        unit_cooler.webui.worker.queue_put(queue, message, liveness_file)

        result = queue.get(timeout=1)
        assert result["state"] == COOLING_STATE.WORKING
        assert isinstance(result["state"], COOLING_STATE)

    def test_removes_old_message_when_queue_full(self, mocker):
        """キューが満杯の場合、古いメッセージを削除"""
        import unit_cooler.webui.worker

        mocker.patch("my_lib.footprint.update")
        mocker.patch.object(unit_cooler.webui.worker, "_notify_state_manager_subscribe_processed")

        # maxsize=1 で満杯になるキューを作成
        queue = multiprocessing.Queue(maxsize=1)
        liveness_file = pathlib.Path("/tmp/test_liveness")

        # 最初のメッセージを追加 (state=1: WORKING)
        first_message = {"state": 1, "mode_index": 1}
        unit_cooler.webui.worker.queue_put(queue, first_message, liveness_file)

        # 2番目のメッセージを追加（最初のメッセージは削除される）(state=0: IDLE)
        second_message = {"state": 0, "mode_index": 2}
        unit_cooler.webui.worker.queue_put(queue, second_message, liveness_file)

        # 2番目のメッセージが取得される
        result = queue.get(timeout=1)
        assert result["state"] == COOLING_STATE.IDLE
        assert result["mode_index"] == 2


class TestNotifyStateManagerSubscribeProcessed:
    """_notify_state_manager_subscribe_processed のテスト"""

    def test_notifies_state_manager(self, mocker):
        """StateManager に通知"""
        import unit_cooler.webui.worker

        mock_state_manager = mocker.MagicMock()
        # 動的インポートされるので state_manager モジュール側をパッチ
        mocker.patch(
            "unit_cooler.state_manager.get_state_manager",
            return_value=mock_state_manager,
        )

        unit_cooler.webui.worker._notify_state_manager_subscribe_processed()

        mock_state_manager.notify_subscribe_processed.assert_called_once()

    def test_handles_exception_gracefully(self, mocker):
        """例外を適切に処理"""
        import unit_cooler.webui.worker

        # 動的インポートされるので state_manager モジュール側をパッチ
        mocker.patch(
            "unit_cooler.state_manager.get_state_manager",
            side_effect=Exception("StateManager not available"),
        )

        # 例外が発生しても関数はエラーを投げない
        unit_cooler.webui.worker._notify_state_manager_subscribe_processed()


class TestSubscribeWorker:
    """subscribe_worker のテスト"""

    def test_starts_client(self, config, mocker):
        """クライアントを開始"""
        import unit_cooler.webui.worker

        mock_start_client = mocker.patch("unit_cooler.pubsub.subscribe.start_client")
        unit_cooler.webui.worker.should_terminate.clear()

        queue = multiprocessing.Queue(maxsize=10)
        liveness_file = pathlib.Path("/tmp/test_liveness")

        result = unit_cooler.webui.worker.subscribe_worker(
            config=config,
            control_host="localhost",
            pub_port=2222,
            message_queue=queue,
            liveness_file=liveness_file,
            msg_count=1,
        )

        assert result == 0
        mock_start_client.assert_called_once()

    def test_returns_error_on_exception(self, config, mocker):
        """例外時にエラーを返す"""
        import unit_cooler.webui.worker

        mocker.patch(
            "unit_cooler.pubsub.subscribe.start_client",
            side_effect=Exception("test"),
        )
        mocker.patch("unit_cooler.util.notify_error")

        queue = multiprocessing.Queue(maxsize=10)
        liveness_file = pathlib.Path("/tmp/test_liveness")

        result = unit_cooler.webui.worker.subscribe_worker(
            config=config,
            control_host="localhost",
            pub_port=2222,
            message_queue=queue,
            liveness_file=liveness_file,
        )

        assert result == -1


class TestActuatorStatusWorker:
    """actuator_status_worker のテスト"""

    def test_disabled_when_port_zero(self, config):
        """ポート 0 で無効"""
        import unit_cooler.webui.worker

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=0,
        )

        assert result == 0

    def test_disabled_when_port_negative(self, config):
        """負のポートで無効"""
        import unit_cooler.webui.worker

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=-1,
        )

        assert result == 0

    def test_receives_actuator_status(self, config, mocker):
        """ActuatorStatus を受信してキャッシュ"""
        import json

        import zmq

        import unit_cooler.webui.worker
        from unit_cooler.const import VALVE_STATE
        from unit_cooler.messages import ActuatorStatus, ValveStatus

        # 終了フラグをリセット
        unit_cooler.webui.worker.should_terminate.clear()
        unit_cooler.webui.worker._last_actuator_status = None

        # テスト用のActuatorStatus
        valve_status = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=5.0)
        test_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=2.5,
            cooling_mode_index=4,
            hazard_detected=False,
        )

        # モックソケットを作成
        mock_socket = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_context.socket.return_value = mock_socket

        # recv_string の動作をシミュレート
        # 1回目: メッセージ受信, 2回目: タイムアウト
        call_count = [0]

        def recv_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return f"actuator_status {json.dumps(test_status.to_dict())}"
            else:
                # 2回目以降は終了フラグを設定してタイムアウト
                unit_cooler.webui.worker.should_terminate.set()
                raise zmq.Again()

        mock_socket.recv_string.side_effect = recv_side_effect
        mocker.patch("zmq.Context", return_value=mock_context)

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=5560,
        )

        assert result == 0
        # ステータスがキャッシュされている
        cached = unit_cooler.webui.worker.get_last_actuator_status()
        assert cached is not None
        assert cached.flow_lpm == 2.5
        assert cached.cooling_mode_index == 4

    def test_handles_zmq_timeout(self, config, mocker):
        """ZMQ タイムアウトを処理"""
        import zmq

        import unit_cooler.webui.worker

        # 終了フラグをリセット
        unit_cooler.webui.worker.should_terminate.clear()

        mock_socket = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_context.socket.return_value = mock_socket

        # 最初のタイムアウト後に終了フラグを設定
        def recv_side_effect():
            unit_cooler.webui.worker.should_terminate.set()
            raise zmq.Again()

        mock_socket.recv_string.side_effect = recv_side_effect
        mocker.patch("zmq.Context", return_value=mock_context)

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=5560,
        )

        assert result == 0

    def test_handles_invalid_message_format(self, config, mocker):
        """無効なメッセージ形式を処理"""
        import zmq

        import unit_cooler.webui.worker

        unit_cooler.webui.worker.should_terminate.clear()

        mock_socket = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_context.socket.return_value = mock_socket

        call_count = [0]

        def recv_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                # 無効なプレフィックス
                return "invalid_prefix {}"
            elif call_count[0] == 2:
                # 不正な JSON
                return "actuator_status not_valid_json"
            else:
                unit_cooler.webui.worker.should_terminate.set()
                raise zmq.Again()

        mock_socket.recv_string.side_effect = recv_side_effect
        mocker.patch("zmq.Context", return_value=mock_context)

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=5560,
        )

        # エラーが発生しても正常終了
        assert result == 0

    def test_handles_connection_error(self, config, mocker):
        """接続エラーを処理"""
        import unit_cooler.webui.worker

        mocker.patch("zmq.Context", side_effect=Exception("Connection failed"))
        mocker.patch("unit_cooler.util.notify_error")

        result = unit_cooler.webui.worker.actuator_status_worker(
            config=config,
            actuator_host="localhost",
            status_pub_port=5560,
        )

        assert result == -1
