#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.valve_controller のテスト"""

from __future__ import annotations

import threading

from unit_cooler.const import COOLING_STATE, VALVE_STATE
from unit_cooler.messages import DutyConfig, ValveStatus


def create_footprint_mock(mocker):
    """footprint の状態を追跡するモックを作成"""
    state = {"valve/open": False, "valve/close": False, "state/working": False, "state/idle": True}

    def exists_side_effect(path):
        path_str = str(path)
        for key in state:
            if key in path_str:
                return state[key]
        return True  # 他のパスは True を返す

    def update_side_effect(path):
        path_str = str(path)
        for key in state:
            if key in path_str:
                state[key] = True
                return

    def clear_side_effect(path):
        path_str = str(path)
        for key in state:
            if key in path_str:
                state[key] = False
                return

    mock_exists = mocker.patch("my_lib.footprint.exists", side_effect=exists_side_effect)
    mock_update = mocker.patch("my_lib.footprint.update", side_effect=update_side_effect)
    mock_clear = mocker.patch("my_lib.footprint.clear", side_effect=clear_side_effect)
    mock_elapsed = mocker.patch("my_lib.footprint.elapsed", return_value=10.0)

    return {
        "exists": mock_exists,
        "update": mock_update,
        "clear": mock_clear,
        "elapsed": mock_elapsed,
        "state": state,
    }


class TestValveControllerInit:
    """ValveController の初期化テスト"""

    def test_init_sets_gpio_mode(self, config, mocker):
        """初期化時に GPIO モードを設定"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        ValveController(config=config, pin_no=17)

        mock_gpio.setwarnings.assert_called_once_with(False)
        mock_gpio.setmode.assert_called_once()
        mock_gpio.setup.assert_called_once_with(17, mock_gpio.OUT)

    def test_init_closes_valve(self, config, mocker):
        """初期化時にバルブを閉じる"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        ValveController(config=config, pin_no=17)

        # CLOSE (value=0) で出力されることを確認
        mock_gpio.output.assert_called_with(17, VALVE_STATE.CLOSE.value)


class TestValveControllerGetState:
    """get_state のテスト"""

    def test_get_state_open(self, config, mocker):
        """GPIO HIGH で OPEN を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化時は CLOSE、その後 OPEN
        mock_gpio.input.side_effect = [0, 0, 1]
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        state = controller.get_state()

        assert state == VALVE_STATE.OPEN

    def test_get_state_close(self, config, mocker):
        """GPIO LOW で CLOSE を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        state = controller.get_state()

        assert state == VALVE_STATE.CLOSE


class TestValveControllerSetState:
    """set_state のテスト"""

    def test_set_state_open(self, config, mocker):
        """OPEN 状態を設定"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 最初は CLOSE、set_state 後は OPEN
        mock_gpio.input.side_effect = [0, 0, 1, 1, 1, 1]
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.set_state(VALVE_STATE.OPEN)

        # OPEN で output が呼ばれたことを確認
        calls = [call for call in mock_gpio.output.call_args_list if call[0][1] == VALVE_STATE.OPEN.value]
        assert len(calls) > 0

    def test_set_state_close(self, config, mocker):
        """CLOSE 状態を設定"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.set_state(VALVE_STATE.CLOSE)

        mock_gpio.output.assert_called_with(17, VALVE_STATE.CLOSE.value)

    def test_set_state_returns_valve_status(self, config, mocker):
        """ValveStatus を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        status = controller.set_state(VALVE_STATE.CLOSE)

        assert isinstance(status, ValveStatus)
        assert status.state == VALVE_STATE.CLOSE

    def test_set_state_increments_operation_count(self, config, mocker):
        """状態変更時に操作回数をインクリメント"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化時 CLOSE (2回呼ばれる)、set_state 時 CLOSE -> set_state 後 OPEN
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1]
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        initial_count = controller.operation_count

        controller.set_state(VALVE_STATE.OPEN)  # CLOSE -> OPEN

        assert controller.operation_count == initial_count + 1

    def test_set_state_no_change_no_increment(self, config, mocker):
        """状態変更なしで操作回数をインクリメントしない"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0  # 常に CLOSE
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        initial_count = controller.operation_count

        controller.set_state(VALVE_STATE.CLOSE)  # 同じ状態

        assert controller.operation_count == initial_count

    def test_set_state_records_history_in_test_mode(self, config, mocker, monkeypatch):
        """テストモードで履歴を記録"""
        monkeypatch.setenv("TEST", "true")
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化時 CLOSE、set_state 時 CLOSE -> OPEN
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1]
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.set_state(VALVE_STATE.OPEN)  # CLOSE -> OPEN

        hist = controller.get_hist()
        assert len(hist) > 0
        assert VALVE_STATE.CLOSE in hist


class TestValveControllerGetStatus:
    """get_status のテスト"""

    def test_get_status_open(self, config, mocker):
        """OPEN 状態のステータス取得"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化時は CLOSE、その後 OPEN に設定、get_status 時も OPEN
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 1]
        fp_mock = create_footprint_mock(mocker)
        fp_mock["elapsed"].return_value = 30.5

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.set_state(VALVE_STATE.OPEN)  # OPEN に設定
        status = controller.get_status()

        assert status.state == VALVE_STATE.OPEN
        assert status.duration_sec == 30.5

    def test_get_status_close(self, config, mocker):
        """CLOSE 状態のステータス取得"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0  # CLOSE
        fp_mock = create_footprint_mock(mocker)
        fp_mock["elapsed"].return_value = 15.0

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        status = controller.get_status()

        assert status.state == VALVE_STATE.CLOSE
        assert status.duration_sec == 15.0

    def test_get_status_dict(self, config, mocker):
        """dict 形式でステータス取得"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        fp_mock = create_footprint_mock(mocker)
        fp_mock["elapsed"].return_value = 20.0

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        status_dict = controller.get_status_dict()

        assert "state" in status_dict
        assert "duration" in status_dict
        assert status_dict["state"] == VALVE_STATE.CLOSE
        assert status_dict["duration"] == 20.0


class TestValveControllerSetCoolingWorking:
    """set_cooling_working のテスト"""

    def test_first_call_opens_valve(self, config, mocker):
        """初回呼び出しでバルブを開く"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化: CLOSE, set_cooling_working 時: CLOSE -> OPEN
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 1]
        create_footprint_mock(mocker)
        mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        duty = {"enable": True, "on_sec": 100, "off_sec": 60}
        controller.set_cooling_working(duty)

        # OPEN で output が呼ばれたことを確認
        calls = [call for call in mock_gpio.output.call_args_list if call[0][1] == VALVE_STATE.OPEN.value]
        assert len(calls) > 0

    def test_accepts_duty_config_object(self, config, mocker):
        """DutyConfig オブジェクトを受け入れる"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 1]
        create_footprint_mock(mocker)
        mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        duty_config = DutyConfig(enable=True, on_sec=100, off_sec=60)
        status = controller.set_cooling_working(duty_config)

        assert isinstance(status, ValveStatus)


class TestValveControllerSetCoolingIdle:
    """set_cooling_idle のテスト"""

    def test_closes_valve(self, config, mocker):
        """IDLE でバルブを閉じる"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)
        mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        status = controller.set_cooling_idle()

        mock_gpio.output.assert_called_with(17, VALVE_STATE.CLOSE.value)
        assert status.state == VALVE_STATE.CLOSE

    def test_logs_transition(self, config, mocker):
        """WORKING -> IDLE 遷移をログ"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        fp_mock = create_footprint_mock(mocker)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        # ValveController 初期化後に state/idle を False に設定して
        # set_cooling_idle で IDLE 遷移をトリガー
        fp_mock["state"]["state/idle"] = False
        controller.set_cooling_idle()

        # work_log にメッセージが追加されることを確認
        mock_add.assert_called()


class TestValveControllerSetCoolingState:
    """set_cooling_state のテスト"""

    def test_working_state(self, config, mocker):
        """WORKING 状態で set_cooling_working を呼ぶ"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 1]
        create_footprint_mock(mocker)
        mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        control_message = {
            "state": COOLING_STATE.WORKING,
            "duty": {"enable": True, "on_sec": 100, "off_sec": 60},
        }
        status = controller.set_cooling_state(control_message)

        assert isinstance(status, ValveStatus)

    def test_idle_state(self, config, mocker):
        """IDLE 状態で set_cooling_idle を呼ぶ"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)
        mocker.patch("unit_cooler.actuator.work_log.add")

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        control_message = {
            "state": COOLING_STATE.IDLE,
        }
        status = controller.set_cooling_state(control_message)

        assert status.state == VALVE_STATE.CLOSE


class TestValveControllerThreadSafety:
    """スレッドセーフティテスト"""

    def test_concurrent_get_status(self, config, mocker):
        """並行 get_status 呼び出し"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        results = []
        errors = []

        def get_status():
            try:
                status = controller.get_status()
                results.append(status)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_status) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20


class TestValveControllerClose:
    """close のテスト"""

    def test_close_closes_valve(self, config, mocker):
        """close() でバルブを閉じる"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.close()

        mock_gpio.output.assert_called_with(17, VALVE_STATE.CLOSE.value)


class TestValveControllerClearStat:
    """clear_stat のテスト"""

    def test_clears_footprints(self, config, mocker):
        """footprint をクリア"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        fp_mock = create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.clear_stat()

        # clear が複数回呼ばれることを確認
        assert fp_mock["clear"].call_count >= 4

    def test_clears_history(self, config, mocker, monkeypatch):
        """履歴をクリア"""
        monkeypatch.setenv("TEST", "true")
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 0, 0]
        create_footprint_mock(mocker)

        from unit_cooler.actuator.valve_controller import ValveController

        controller = ValveController(config=config, pin_no=17)
        controller.set_state(VALVE_STATE.OPEN)  # CLOSE -> OPEN
        assert len(controller.get_hist()) > 0

        controller.clear_stat()
        assert len(controller.get_hist()) == 0
