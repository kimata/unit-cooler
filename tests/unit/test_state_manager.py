#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.state_manager のテスト"""

import threading
import time

from unit_cooler.const import COOLING_STATE, VALVE_STATE
from unit_cooler.messages import ControlMessage, DutyConfig
from unit_cooler.state_manager import (
    StateManager,
    get_state_manager,
    init_state_manager,
    reset_state_manager,
)


class TestStateManagerBasic:
    """StateManager の基本機能テスト"""

    def test_create(self):
        """StateManager の作成"""
        sm = StateManager()
        assert sm.control_worker_count == 0
        assert sm.valve_state is None
        assert sm.cooling_state is None

    def test_update_single_attr(self):
        """単一属性の更新"""
        sm = StateManager()
        sm.update(control_worker_count=5)
        assert sm.control_worker_count == 5

    def test_update_multiple_attrs(self):
        """複数属性の同時更新"""
        sm = StateManager()
        sm.update(
            control_worker_count=3,
            monitor_worker_count=2,
            flow_lpm=2.5,
        )
        assert sm.control_worker_count == 3
        assert sm.monitor_worker_count == 2
        assert sm.flow_lpm == 2.5

    def test_update_unknown_attr_logs_warning(self, caplog):
        """存在しない属性の更新は警告"""
        sm = StateManager()
        sm.update(unknown_attr=123)
        assert "unknown attribute" in caplog.text

    def test_increment(self):
        """インクリメント"""
        sm = StateManager()
        result = sm.increment("control_worker_count")
        assert result == 1
        assert sm.control_worker_count == 1

        result = sm.increment("control_worker_count", 5)
        assert result == 6
        assert sm.control_worker_count == 6

    def test_get(self):
        """属性値の取得"""
        sm = StateManager()
        sm.update(flow_lpm=3.5)
        assert sm.get("flow_lpm") == 3.5
        assert sm.get("nonexistent") is None

    def test_reset(self):
        """リセット"""
        sm = StateManager()
        sm.update(
            control_worker_count=10,
            valve_state=VALVE_STATE.OPEN,
            flow_lpm=5.0,
            hazard_detected=True,
        )

        sm.reset()

        assert sm.control_worker_count == 0
        assert sm.valve_state is None
        assert sm.flow_lpm == 0.0
        assert sm.hazard_detected is False


class TestStateManagerWait:
    """StateManager の待機機能テスト"""

    def test_wait_for_immediate_true(self):
        """既に条件を満たしている場合"""
        sm = StateManager()
        sm.update(control_worker_count=5)

        result = sm.wait_for(lambda s: s.control_worker_count >= 5, timeout=0.1)
        assert result is True

    def test_wait_for_timeout(self):
        """タイムアウト"""
        sm = StateManager()

        start = time.time()
        result = sm.wait_for(lambda s: s.control_worker_count >= 100, timeout=0.1)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.1
        assert elapsed < 0.2

    def test_wait_for_attr(self):
        """特定属性の待機"""
        sm = StateManager()
        sm.update(valve_state=VALVE_STATE.OPEN)

        result = sm.wait_for_attr("valve_state", VALVE_STATE.OPEN, timeout=0.1)
        assert result is True

    def test_wait_for_count(self):
        """カウンター待機"""
        sm = StateManager()
        sm.update(control_worker_count=3)

        result = sm.wait_for_count("control_worker_count", 3, timeout=0.1)
        assert result is True

        result = sm.wait_for_count("control_worker_count", 5, timeout=0.1)
        assert result is False


class TestStateManagerThreading:
    """StateManager のスレッドセーフティテスト"""

    def test_concurrent_update(self):
        """並行更新"""
        sm = StateManager()
        results = []

        def incrementer():
            for _ in range(100):
                sm.increment("control_worker_count")
                results.append(True)

        threads = [threading.Thread(target=incrementer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sm.control_worker_count == 500
        assert len(results) == 500

    def test_wait_with_update_from_another_thread(self):
        """別スレッドからの更新を待機"""
        sm = StateManager()

        def delayed_update():
            time.sleep(0.05)
            sm.update(control_worker_count=10)

        thread = threading.Thread(target=delayed_update)
        thread.start()

        result = sm.wait_for(lambda s: s.control_worker_count >= 10, timeout=1.0)
        thread.join()

        assert result is True
        assert sm.control_worker_count == 10


class TestStateManagerValve:
    """StateManager のバルブ関連メソッドテスト"""

    def test_notify_valve_state_changed(self):
        """バルブ状態変更通知"""
        sm = StateManager()

        sm.notify_valve_state_changed(VALVE_STATE.OPEN)

        assert sm.valve_state == VALVE_STATE.OPEN
        assert sm.valve_operation_count == 1
        assert sm.valve_last_change is not None

    def test_wait_for_valve_open(self):
        """バルブ OPEN 待機"""
        sm = StateManager()
        sm.update(valve_state=VALVE_STATE.OPEN)

        result = sm.wait_for_valve_open(timeout=0.1)
        assert result is True

    def test_wait_for_valve_close(self):
        """バルブ CLOSE 待機"""
        sm = StateManager()
        sm.update(valve_state=VALVE_STATE.CLOSE)

        result = sm.wait_for_valve_close(timeout=0.1)
        assert result is True

    def test_wait_for_valve_operation_count(self):
        """バルブ操作回数待機"""
        sm = StateManager()
        sm.notify_valve_state_changed(VALVE_STATE.OPEN)
        sm.notify_valve_state_changed(VALVE_STATE.CLOSE)

        result = sm.wait_for_valve_operation_count(2, timeout=0.1)
        assert result is True


class TestStateManagerCooling:
    """StateManager の冷却関連メソッドテスト"""

    def test_notify_cooling_state_changed(self):
        """冷却状態変更通知"""
        sm = StateManager()

        sm.notify_cooling_state_changed(COOLING_STATE.WORKING, mode_index=3)

        assert sm.cooling_state == COOLING_STATE.WORKING
        assert sm.cooling_mode_index == 3

    def test_wait_for_cooling_working(self):
        """冷却 WORKING 待機"""
        sm = StateManager()
        sm.update(cooling_state=COOLING_STATE.WORKING)

        result = sm.wait_for_cooling_working(timeout=0.1)
        assert result is True

    def test_wait_for_cooling_idle(self):
        """冷却 IDLE 待機"""
        sm = StateManager()
        sm.update(cooling_state=COOLING_STATE.IDLE)

        result = sm.wait_for_cooling_idle(timeout=0.1)
        assert result is True


class TestStateManagerWorker:
    """StateManager のワーカー関連メソッドテスト"""

    def test_notify_control_processed(self):
        """control_worker 処理完了通知"""
        sm = StateManager()

        sm.notify_control_processed()

        assert sm.control_worker_count == 1
        assert sm.control_worker_last_time is not None

    def test_notify_monitor_processed(self):
        """monitor_worker 処理完了通知"""
        sm = StateManager()

        sm.notify_monitor_processed()

        assert sm.monitor_worker_count == 1
        assert sm.monitor_worker_last_time is not None

    def test_notify_subscribe_processed(self):
        """subscribe_worker 処理完了通知"""
        sm = StateManager()

        sm.notify_subscribe_processed()

        assert sm.subscribe_worker_count == 1
        assert sm.subscribe_worker_last_time is not None

    def test_wait_for_control_count(self):
        """control_worker 処理回数待機"""
        sm = StateManager()
        for _ in range(5):
            sm.notify_control_processed()

        result = sm.wait_for_control_count(5, timeout=0.1)
        assert result is True

    def test_wait_for_monitor_count(self):
        """monitor_worker 処理回数待機"""
        sm = StateManager()
        for _ in range(3):
            sm.notify_monitor_processed()

        result = sm.wait_for_monitor_count(3, timeout=0.1)
        assert result is True


class TestStateManagerMessage:
    """StateManager のメッセージ関連メソッドテスト"""

    def test_notify_message_received(self):
        """メッセージ受信通知"""
        sm = StateManager()
        msg = ControlMessage(
            state=COOLING_STATE.WORKING,
            mode_index=2,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        sm.notify_message_received(msg)

        assert sm.message_receive_count == 1
        assert sm.last_message == msg

    def test_wait_for_message_count(self):
        """メッセージ受信回数待機"""
        sm = StateManager()
        for i in range(3):
            msg = ControlMessage(
                state=COOLING_STATE.IDLE,
                mode_index=i,
                duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
            )
            sm.notify_message_received(msg)

        result = sm.wait_for_message_count(3, timeout=0.1)
        assert result is True
        assert sm.last_message is not None
        assert sm.last_message.mode_index == 2


class TestStateManagerServer:
    """StateManager のサーバー関連メソッドテスト"""

    def test_notify_server_ready(self):
        """サーバー起動完了通知"""
        sm = StateManager()

        sm.notify_server_ready()

        assert sm.server_ready is True

    def test_wait_for_server_ready(self):
        """サーバー起動待機"""
        sm = StateManager()
        sm.notify_server_ready()

        result = sm.wait_for_server_ready(timeout=0.1)
        assert result is True


class TestStateManagerLog:
    """StateManager のログ関連メソッドテスト"""

    def test_notify_log_written(self):
        """ログ書き込み通知"""
        sm = StateManager()

        sm.notify_log_written()
        sm.notify_log_written()

        assert sm.log_write_count == 2

    def test_wait_for_log_count(self):
        """ログ書き込み回数待機"""
        sm = StateManager()
        for _ in range(5):
            sm.notify_log_written()

        result = sm.wait_for_log_count(5, timeout=0.1)
        assert result is True


class TestGlobalStateManager:
    """グローバル StateManager 関数のテスト"""

    def test_get_state_manager(self):
        """get_state_manager はシングルトンを返す"""
        sm1 = get_state_manager()
        sm2 = get_state_manager()
        assert sm1 is sm2

    def test_reset_state_manager(self):
        """reset_state_manager は状態をリセット"""
        sm = get_state_manager()
        sm.update(control_worker_count=100)

        reset_state_manager()

        assert sm.control_worker_count == 0

    def test_init_state_manager(self):
        """init_state_manager はリセットして返す"""
        sm1 = get_state_manager()
        sm1.update(flow_lpm=10.0)

        sm2 = init_state_manager()

        assert sm2.flow_lpm == 0.0
        assert sm1 is sm2
