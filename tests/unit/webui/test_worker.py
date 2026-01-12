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
