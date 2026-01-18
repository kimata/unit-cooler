#!/usr/bin/env python3
import logging
import os
import random
from typing import ClassVar, Protocol

import my_lib.rpi

import unit_cooler.const

logger = logging.getLogger(__name__)


class FlowSensorProtocol(Protocol):
    """流量センサーのプロトコル"""

    def get_value(self, force_power_on: bool = True) -> float | None: ...
    def get_state(self) -> bool: ...
    def stop(self) -> None: ...


class DummyFlowSensor:
    """ダミー流量センサー（テスト用）"""

    # ワーカーごとの電源状態を管理する辞書（初期値はTrue）
    _power_states: ClassVar[dict[str, bool]] = {}

    def __init__(self, pin_no: int) -> None:
        self._pin_no = pin_no
        worker_id = self._get_worker_id()
        self._power_states[worker_id] = True

    def _get_worker_id(self) -> str:
        """現在のワーカーIDを取得"""
        return os.environ.get("PYTEST_XDIST_WORKER", "main")

    def get_value(self, force_power_on: bool = True) -> float | None:
        worker_id = self._get_worker_id()

        # force_power_on=Trueで呼ばれた場合、電源状態をTrueに設定
        if force_power_on:
            self._power_states[worker_id] = True

        if my_lib.rpi.gpio.input(self._pin_no) == unit_cooler.const.VALVE_STATE.OPEN.value:
            return 1 + random.random() * 1.5  # noqa: S311
        else:
            return 0.0

    def get_state(self) -> bool:
        worker_id = self._get_worker_id()
        return self._power_states[worker_id]

    def stop(self) -> None:
        worker_id = self._get_worker_id()
        # stopが呼ばれたら電源状態をFalseに設定
        self._power_states[worker_id] = False


# グローバル変数
_sensor: FlowSensorProtocol | None = None
_pin_no: int | None = None


def init(pin_no: int) -> None:
    """流量センサーを初期化する

    Args:
        pin_no: バルブの GPIO ピン番号
    """
    global _sensor
    global _pin_no

    _pin_no = pin_no

    if os.environ.get("DUMMY_MODE", "false") != "true":  # pragma: no cover
        from my_lib.sensor.fd_q10c import FD_Q10C

        _sensor = FD_Q10C()
    else:
        _sensor = DummyFlowSensor(pin_no)


def stop() -> None:
    """流量センサーを停止する"""
    global _sensor

    logger.info("Stop flow sensing")

    assert _sensor is not None  # noqa: S101
    try:
        _sensor.stop()
    except RuntimeError:
        logger.exception("Failed to stop FD-Q10C")


def get_power_state() -> bool:
    """電源状態を取得する"""
    global _sensor

    assert _sensor is not None  # noqa: S101
    return _sensor.get_state()


def get_flow(force_power_on: bool = True) -> float | None:
    """流量を取得する

    Args:
        force_power_on: True の場合、電源を強制的に ON にする

    Returns:
        流量値。取得できない場合は None
    """
    global _sensor

    assert _sensor is not None  # noqa: S101
    try:
        flow = _sensor.get_value(force_power_on)
    except Exception:
        logger.exception("バグの可能性あり。")
        flow = None

    if flow is not None:
        logger.info("Valve flow = %.2f", flow)
    else:
        logger.info("Valve flow = UNKNOWN")

    return flow
