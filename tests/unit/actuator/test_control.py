#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.control のテスト"""

from __future__ import annotations

import datetime
import multiprocessing
from unittest.mock import MagicMock

import unit_cooler.actuator.control
from unit_cooler.const import COOLING_STATE, LOG_LEVEL
from unit_cooler.messages import ControlMessage, DutyConfig


class TestGenHandle:
    """gen_handle のテスト"""

    def test_returns_control_handle_with_required_attrs(self, config):
        """必要な属性を含む ControlHandle を返す"""
        queue = multiprocessing.Queue()

        handle = unit_cooler.actuator.control.gen_handle(config, queue)

        assert hasattr(handle, "config")
        assert hasattr(handle, "message_queue")
        assert hasattr(handle, "receive_time")
        assert hasattr(handle, "receive_count")

    def test_config_is_stored(self, config):
        """config が保存される"""
        queue = multiprocessing.Queue()

        handle = unit_cooler.actuator.control.gen_handle(config, queue)

        assert handle.config == config

    def test_queue_is_stored(self, config):
        """queue が保存される"""
        queue = multiprocessing.Queue()

        handle = unit_cooler.actuator.control.gen_handle(config, queue)

        assert handle.message_queue == queue

    def test_receive_count_is_zero(self, config):
        """receive_count が 0"""
        queue = multiprocessing.Queue()

        handle = unit_cooler.actuator.control.gen_handle(config, queue)

        assert handle.receive_count == 0


class TestHazardRegister:
    """hazard_register のテスト"""

    def test_updates_hazard_footprint(self, config, mocker):
        """hazard footprint を更新"""
        mock_update = mocker.patch("my_lib.footprint.update")

        unit_cooler.actuator.control.hazard_register(config)

        mock_update.assert_called_once_with(config.actuator.control.hazard.file)


class TestHazardClear:
    """hazard_clear のテスト"""

    def test_clears_hazard_footprint(self, config, mocker):
        """hazard footprint をクリア"""
        mock_clear = mocker.patch("my_lib.footprint.clear")

        unit_cooler.actuator.control.hazard_clear(config)

        mock_clear.assert_called_once_with(config.actuator.control.hazard.file)


class TestHazardNotify:
    """hazard_notify のテスト"""

    def test_notifies_with_suppress_interval(self, config, mocker):
        """work_log の共通抑制機構を使って ERROR を記録する"""
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ", suppress_key="テスト")

        mock_add.assert_called_once_with(
            "テストメッセージ",
            LOG_LEVEL.ERROR,
            suppress_interval_min=unit_cooler.actuator.control.HAZARD_NOTIFY_INTERVAL_MIN,
            suppress_key="テスト",
        )

    def test_registers_latch_on_first_detection(self, config, mocker):
        """ラッチが存在しない場合は登録する"""
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mock_update = mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ")

        mock_update.assert_called_once_with(config.actuator.control.hazard.file)

    def test_keeps_first_detection_time_when_latch_exists(self, config, mocker):
        """既にラッチが存在する場合は上書きせず初回検知時刻を保持する"""
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mock_update = mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ")

        mock_update.assert_not_called()

    def test_closes_valve(self, config, mocker):
        """バルブを閉じる"""
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ")

        from unit_cooler.const import VALVE_STATE

        mock_controller.set_state.assert_called_once_with(VALVE_STATE.CLOSE)


class TestHazardCheck:
    """hazard_check のテスト"""

    def test_returns_true_when_hazard_exists(self, config, mocker):
        """hazard 存在時に True"""
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        result = unit_cooler.actuator.control.hazard_check(config)

        assert result is True

    def test_returns_false_when_no_hazard(self, config, mocker):
        """hazard なしで False"""
        mocker.patch("my_lib.footprint.exists", return_value=False)

        result = unit_cooler.actuator.control.hazard_check(config)

        assert result is False

    def test_calls_hazard_notify_when_exists(self, config, mocker):
        """hazard 存在時に hazard_notify を呼ぶ"""
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_check(config)

        mock_add.assert_called()


class TestGetControlMessage:
    """get_control_message のテスト"""

    def test_returns_last_message_when_queue_empty(self, config, mocker):
        """キュー空で last_message を返す"""
        mocker.patch("my_lib.time.now", return_value=datetime.datetime.now())
        mocker.patch("unit_cooler.actuator.work_log.add")

        queue = multiprocessing.Queue()
        handle = unit_cooler.actuator.control.gen_handle(config, queue)
        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        result = unit_cooler.actuator.control.get_control_message(handle, last_message)

        assert result == last_message

    def test_falls_back_to_idle_on_timeout(self, config, mocker):
        """制御指示が閾値を超えて途絶したら IDLE にフォールバックする (BUG #6)"""
        now = datetime.datetime.now()
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        queue = multiprocessing.Queue()
        handle = unit_cooler.actuator.control.gen_handle(config, queue)
        # receive_time を閾値（interval_sec*3）より十分過去にして途絶状態を作る
        handle.receive_time = now - datetime.timedelta(seconds=config.controller.interval_sec * 3 + 10)
        mocker.patch("my_lib.time.now", return_value=now)

        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=10, off_sec=5),
        )

        result = unit_cooler.actuator.control.get_control_message(handle, last_message)

        assert result.state == COOLING_STATE.IDLE
        assert result.mode_index == 0
        assert result.duty.enable is False
        assert handle.timeout_notified is True
        assert mock_add.call_args[0][1] == LOG_LEVEL.ERROR

    def test_timeout_error_logged_once(self, config, mocker):
        """途絶中の ERROR ログは毎サイクルではなく途絶開始時の 1 回のみ"""
        now = datetime.datetime.now()
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        queue = multiprocessing.Queue()
        handle = unit_cooler.actuator.control.gen_handle(config, queue)
        handle.receive_time = now - datetime.timedelta(seconds=config.controller.interval_sec * 3 + 10)
        mocker.patch("my_lib.time.now", return_value=now)

        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        unit_cooler.actuator.control.get_control_message(handle, last_message)
        unit_cooler.actuator.control.get_control_message(handle, last_message)

        assert mock_add.call_count == 1

    def test_returns_new_message_from_queue(self, config, mocker):
        """キューからメッセージを取得"""
        now = datetime.datetime.now()
        mocker.patch("my_lib.time.now", return_value=now)
        mocker.patch("unit_cooler.actuator.work_log.add")

        new_message = ControlMessage(
            mode_index=5,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        # モックキューを使用（multiprocessing.Queue.empty() は信頼性が低い）
        # empty() は2回呼ばれる: 1回目は関数冒頭のif文、2回目はwhileループ条件
        mock_queue = MagicMock()
        mock_queue.empty.side_effect = [False, False, True]  # if文、while条件、while終了条件
        mock_queue.get.return_value = new_message

        handle = unit_cooler.actuator.control.gen_handle(config, mock_queue)

        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        result = unit_cooler.actuator.control.get_control_message(handle, last_message)

        assert result == new_message

    def test_updates_receive_time_and_count(self, config, mocker):
        """receive_time と receive_count を更新"""
        now = datetime.datetime.now()
        mocker.patch("my_lib.time.now", return_value=now)
        mocker.patch("unit_cooler.actuator.work_log.add")

        new_message = ControlMessage(
            mode_index=5,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        # モックキューを使用
        # empty() は2回呼ばれる: 1回目は関数冒頭のif文、2回目はwhileループ条件
        mock_queue = MagicMock()
        mock_queue.empty.side_effect = [False, False, True]
        mock_queue.get.return_value = new_message

        handle = unit_cooler.actuator.control.gen_handle(config, mock_queue)
        initial_count = handle.receive_count

        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        unit_cooler.actuator.control.get_control_message(handle, last_message)

        assert handle.receive_count == initial_count + 1
        assert handle.receive_time == now

    def test_logs_mode_change(self, config, mocker):
        """モード変更をログ"""
        now = datetime.datetime.now()
        mocker.patch("my_lib.time.now", return_value=now)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        new_message = ControlMessage(
            mode_index=5,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        # モックキューを使用
        # empty() は2回呼ばれる: 1回目は関数冒頭のif文、2回目はwhileループ条件
        mock_queue = MagicMock()
        mock_queue.empty.side_effect = [False, False, True]
        mock_queue.get.return_value = new_message

        handle = unit_cooler.actuator.control.gen_handle(config, mock_queue)

        last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        unit_cooler.actuator.control.get_control_message(handle, last_message)

        mock_add.assert_called()
        call_message = mock_add.call_args[0][0]
        assert "3" in call_message
        assert "5" in call_message

    def test_handles_initial_mode_index(self, config, mocker):
        """初期モード (-1) からの変更"""
        mocker.patch("my_lib.time.now", return_value=datetime.datetime.now())
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        new_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )

        # モックキューを使用
        # empty() は2回呼ばれる: 1回目は関数冒頭のif文、2回目はwhileループ条件
        mock_queue = MagicMock()
        mock_queue.empty.side_effect = [False, False, True]
        mock_queue.get.return_value = new_message

        handle = unit_cooler.actuator.control.gen_handle(config, mock_queue)

        last_message = ControlMessage(
            mode_index=-1,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        unit_cooler.actuator.control.get_control_message(handle, last_message)

        mock_add.assert_called()
        call_message = mock_add.call_args[0][0]
        assert "init" in call_message


class TestExecute:
    """execute のテスト"""

    def test_calls_set_cooling_state(self, config, mocker):
        """set_cooling_state を呼ぶ"""
        mocker.patch("my_lib.footprint.exists", return_value=False)  # hazard なし
        mocker.patch("unit_cooler.actuator.override.is_active", return_value=False)
        mocker.patch("unit_cooler.metrics.get_metrics_collector", return_value=MagicMock())
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        control_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=100, off_sec=60),
        )
        result = unit_cooler.actuator.control.execute(config, control_message)

        mock_controller.set_cooling_state.assert_called_once_with(control_message)
        # 差し替えがない場合は受信メッセージがそのまま実効メッセージになる
        assert result == control_message

    def test_overrides_to_idle_when_hazard(self, config, mocker):
        """hazard 時に IDLE に上書きし、実効メッセージを返す"""
        mocker.patch("my_lib.footprint.exists", return_value=True)  # hazard あり
        mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("unit_cooler.metrics.get_metrics_collector", return_value=MagicMock())
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        control_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=100, off_sec=60),
        )
        result = unit_cooler.actuator.control.execute(config, control_message)

        # IDLE に上書きされることを確認
        call_args = mock_controller.set_cooling_state.call_args[0][0]
        assert call_args.mode_index == 0
        assert call_args.state == COOLING_STATE.IDLE
        # 実効メッセージ（IDLE）が返されることを確認
        assert result.mode_index == 0
        assert result.state == COOLING_STATE.IDLE

    def test_overrides_to_idle_when_manual_override(self, config, mocker):
        """手動オーバーライド有効時に IDLE に差し替える"""
        mocker.patch("my_lib.footprint.exists", return_value=False)  # hazard なし
        mocker.patch("unit_cooler.actuator.override.is_active", return_value=True)
        mocker.patch("unit_cooler.metrics.get_metrics_collector", return_value=MagicMock())
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        control_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=100, off_sec=60),
        )
        result = unit_cooler.actuator.control.execute(config, control_message)

        call_args = mock_controller.set_cooling_state.call_args[0][0]
        assert call_args.state == COOLING_STATE.IDLE
        assert result.mode_index == 0
        assert result.state == COOLING_STATE.IDLE

    def test_returns_to_normal_when_override_inactive(self, config, mocker):
        """オーバーライドが無効（失効）なら通常運転に戻る"""
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.override.is_active", return_value=False)
        mocker.patch("unit_cooler.metrics.get_metrics_collector", return_value=MagicMock())
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        control_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=100, off_sec=60),
        )
        result = unit_cooler.actuator.control.execute(config, control_message)

        assert result == control_message
        mock_controller.set_cooling_state.assert_called_once_with(control_message)

    def test_collects_metrics(self, config, mocker):
        """メトリクスを収集"""
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mock_collector = MagicMock()
        # 関数が直接インポートされているので、使用場所でパッチ
        mocker.patch("unit_cooler.actuator.control.get_metrics_collector", return_value=mock_collector)
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        control_message = ControlMessage(
            mode_index=5,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=100, off_sec=60),
        )
        unit_cooler.actuator.control.execute(config, control_message)

        mock_collector.update_cooling_mode.assert_called_once_with(5)
        mock_collector.update_duty_ratio.assert_called_once()

    def test_handles_metrics_exception(self, config, mocker):
        """メトリクス例外をハンドリング"""
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.control.get_metrics_collector", side_effect=Exception("test"))
        mock_controller = MagicMock()
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller", return_value=mock_controller
        )

        control_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.WORKING,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        # 例外が発生しても set_cooling_state は呼ばれる
        unit_cooler.actuator.control.execute(config, control_message)

        mock_controller.set_cooling_state.assert_called_once()


class TestHazardNotifyInterval:
    """HAZARD_NOTIFY_INTERVAL_MIN のテスト

    抑制間隔の境界動作自体は work_log 側の共通機構のテスト（test_work_log.py）で担保する。
    """

    def test_interval_is_30_minutes(self):
        """間隔は 30 分"""
        assert unit_cooler.actuator.control.HAZARD_NOTIFY_INTERVAL_MIN == 30
