#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.sensor のテスト"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSensorInit:
    """sensor.init のテスト"""

    def test_init_sets_pin_no(self, monkeypatch):
        """init で pin_no を設定"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)

        assert unit_cooler.actuator.sensor._pin_no == 17

    def test_init_creates_fd_q10c(self, monkeypatch):
        """init で FD_Q10C を作成"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)

        assert unit_cooler.actuator.sensor._sensor is not None


class TestSensorStop:
    """sensor.stop のテスト"""

    def test_stop_calls_fd_q10c_stop(self, monkeypatch):
        """stop で fd_q10c.stop を呼ぶ"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor.stop()

        # stop 後は電源状態が False になる
        assert unit_cooler.actuator.sensor._sensor.get_state() is False  # ty: ignore[possibly-missing-attribute]

    def test_stop_handles_runtime_error(self, monkeypatch):
        """stop で RuntimeError をハンドリング"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor._sensor.stop = MagicMock(side_effect=RuntimeError("test"))  # ty: ignore[invalid-assignment]

        # 例外が発生しないことを確認
        unit_cooler.actuator.sensor.stop()


class TestSensorGetPowerState:
    """sensor.get_power_state のテスト"""

    def test_returns_power_state(self, monkeypatch):
        """電源状態を返す"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)

        state = unit_cooler.actuator.sensor.get_power_state()

        assert state is True  # 初期状態は True

    def test_returns_false_after_stop(self, monkeypatch):
        """stop 後は False"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor.stop()

        state = unit_cooler.actuator.sensor.get_power_state()

        assert state is False


class TestSensorGetFlow:
    """sensor.get_flow のテスト"""

    def test_returns_flow_value(self, mocker, monkeypatch):
        """流量値を返す"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 1  # バルブ OPEN

        unit_cooler.actuator.sensor.init(17)
        flow = unit_cooler.actuator.sensor.get_flow()

        assert flow is not None
        assert flow > 0

    def test_returns_zero_when_valve_closed(self, mocker, monkeypatch):
        """バルブ閉で 0"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0  # バルブ CLOSE

        unit_cooler.actuator.sensor.init(17)
        flow = unit_cooler.actuator.sensor.get_flow()

        assert flow == 0

    def test_handles_exception(self, monkeypatch):
        """例外をハンドリング"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor._sensor.get_value = MagicMock(side_effect=Exception("test"))  # ty: ignore[invalid-assignment]

        flow = unit_cooler.actuator.sensor.get_flow()

        assert flow is None

    def test_force_power_on_default_true(self, mocker, monkeypatch):
        """force_power_on デフォルト True"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor.stop()  # 電源 OFF

        unit_cooler.actuator.sensor.get_flow()  # force_power_on=True

        # 電源が ON になることを確認
        state = unit_cooler.actuator.sensor.get_power_state()
        assert state is True

    def test_force_power_on_false(self, mocker, monkeypatch):
        """force_power_on=False で電源状態を変えない"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0

        unit_cooler.actuator.sensor.init(17)
        unit_cooler.actuator.sensor.stop()  # 電源 OFF

        unit_cooler.actuator.sensor.get_flow(force_power_on=False)

        # 電源が OFF のままであることを確認
        state = unit_cooler.actuator.sensor.get_power_state()
        assert state is False


class TestDummyFDQ10C:
    """ダミー FD_Q10C のテスト"""

    def test_get_value_with_valve_open(self, mocker, monkeypatch):
        """バルブ OPEN で流量 > 1"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 1  # OPEN

        unit_cooler.actuator.sensor.init(17)
        assert unit_cooler.actuator.sensor._sensor is not None
        value = unit_cooler.actuator.sensor._sensor.get_value()

        assert value is not None
        assert value >= 1.0
        assert value <= 2.5  # 1 + random(0, 1.5)

    def test_get_value_with_valve_closed(self, mocker, monkeypatch):
        """バルブ CLOSE で流量 = 0"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0  # CLOSE

        unit_cooler.actuator.sensor.init(17)
        assert unit_cooler.actuator.sensor._sensor is not None
        value = unit_cooler.actuator.sensor._sensor.get_value()  # ty: ignore[possibly-missing-attribute]

        assert value == 0

    def test_worker_id_isolation(self, monkeypatch):
        """ワーカー ID による分離"""
        monkeypatch.setenv("DUMMY_MODE", "true")
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        unit_cooler.actuator.sensor.init(17)
        assert unit_cooler.actuator.sensor._sensor is not None
        worker_id = unit_cooler.actuator.sensor._sensor._get_worker_id()  # ty: ignore[unresolved-attribute]

        assert worker_id == "gw0"

    def test_power_state_per_worker(self, monkeypatch):
        """ワーカーごとの電源状態"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        # ワーカー1 で初期化
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
        unit_cooler.actuator.sensor.init(17)

        # 初期状態は True
        assert unit_cooler.actuator.sensor._sensor is not None
        assert unit_cooler.actuator.sensor._sensor.get_state() is True  # ty: ignore[possibly-missing-attribute]

        # stop で False
        unit_cooler.actuator.sensor._sensor.stop()  # ty: ignore[possibly-missing-attribute]
        assert unit_cooler.actuator.sensor._sensor.get_state() is False  # ty: ignore[possibly-missing-attribute]


class TestSensorFlowRange:
    """流量範囲のテスト"""

    def test_flow_within_expected_range(self, mocker, monkeypatch):
        """流量が期待範囲内"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 1  # OPEN

        unit_cooler.actuator.sensor.init(17)

        # 複数回取得してすべて範囲内であることを確認
        for _ in range(10):
            flow = unit_cooler.actuator.sensor.get_flow()
            assert flow is not None, "Flow should not be None when valve is open"
            if flow is not None:
                assert flow >= 1.0
                assert flow <= 2.5

    def test_flow_zero_when_closed(self, mocker, monkeypatch):
        """バルブ閉で常に 0"""
        monkeypatch.setenv("DUMMY_MODE", "true")

        import importlib

        import unit_cooler.actuator.sensor

        importlib.reload(unit_cooler.actuator.sensor)

        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0  # CLOSE

        unit_cooler.actuator.sensor.init(17)

        for _ in range(10):
            flow = unit_cooler.actuator.sensor.get_flow()
            assert flow == 0
