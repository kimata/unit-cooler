#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.control のテスト"""

from __future__ import annotations

import datetime
import multiprocessing
from unittest.mock import MagicMock

import pytest

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

    def test_notifies_when_interval_exceeded(self, config, mocker):
        """間隔超過時に通知"""
        mocker.patch("my_lib.footprint.elapsed", return_value=31 * 60)  # 31分
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ")

        mock_add.assert_called_once()
        args = mock_add.call_args[0]
        assert args[0] == "テストメッセージ"
        assert args[1] == LOG_LEVEL.ERROR

    def test_no_notify_when_interval_not_exceeded(self, config, mocker):
        """間隔未満で通知しない"""
        mocker.patch("my_lib.footprint.elapsed", return_value=10 * 60)  # 10分
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テストメッセージ")

        mock_add.assert_not_called()

    def test_closes_valve(self, config, mocker):
        """バルブを閉じる"""
        mocker.patch("my_lib.footprint.elapsed", return_value=10 * 60)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
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
        mocker.patch("my_lib.footprint.elapsed", return_value=31 * 60)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
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
        mocker.patch("my_lib.footprint.elapsed", return_value=31 * 60)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
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
        unit_cooler.actuator.control.execute(config, control_message)

        mock_controller.set_cooling_state.assert_called_once_with(control_message)

    def test_overrides_to_idle_when_hazard(self, config, mocker):
        """hazard 時に IDLE に上書き"""
        mocker.patch("my_lib.footprint.exists", return_value=True)  # hazard あり
        mocker.patch("my_lib.footprint.elapsed", return_value=10 * 60)
        mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
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
        unit_cooler.actuator.control.execute(config, control_message)

        # IDLE に上書きされることを確認
        call_args = mock_controller.set_cooling_state.call_args[0][0]
        assert call_args.mode_index == 0
        assert call_args.state == COOLING_STATE.IDLE

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
    """HAZARD_NOTIFY_INTERVAL_MIN のテスト"""

    def test_interval_is_30_minutes(self):
        """間隔は 30 分"""
        assert unit_cooler.actuator.control.HAZARD_NOTIFY_INTERVAL_MIN == 30

    @pytest.mark.parametrize(
        "elapsed_min,should_notify",
        [
            (29, False),  # 29分 < 30分
            (30, False),  # 30分 = 30分 (境界)
            (31, True),  # 31分 > 30分
            (60, True),  # 60分 > 30分
        ],
    )
    def test_notify_interval_boundary(self, config, mocker, elapsed_min, should_notify):
        """通知間隔の境界テスト"""
        mocker.patch("my_lib.footprint.elapsed", return_value=elapsed_min * 60)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=MagicMock())

        unit_cooler.actuator.control.hazard_notify(config, "テスト")

        if should_notify:
            mock_add.assert_called()
        else:
            mock_add.assert_not_called()
