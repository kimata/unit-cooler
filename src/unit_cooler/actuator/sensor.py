#!/usr/bin/env python3
import logging
import os
import random
from typing import ClassVar

import my_lib.rpi

import unit_cooler.const

fd_q10c = None
pin_no = None

if os.environ.get("DUMMY_MODE", "false") != "true":  # pragma: no cover
    from my_lib.sensor.fd_q10c import FD_Q10C
else:

    class FD_Q10C:
        # ワーカーごとの電源状態を管理する辞書（初期値はTrue）
        _power_states: ClassVar[dict[str, bool]] = {}

        def __init__(self, lock_file="DUMMY", timeout=2):
            worker_id = self._get_worker_id()
            self._power_states[worker_id] = True

        def _get_worker_id(self):
            """現在のワーカーIDを取得"""
            return os.environ.get("PYTEST_XDIST_WORKER", "main")

        def get_value(self, force_power_on=True):
            global pin_no
            worker_id = self._get_worker_id()

            # force_power_on=Trueで呼ばれた場合、電源状態をTrueに設定
            if force_power_on:
                self._power_states[worker_id] = True

            if my_lib.rpi.gpio.input(pin_no) == unit_cooler.const.VALVE_STATE.OPEN.value:
                return 1 + random.random() * 1.5  # noqa: S311
            else:
                return 0

        def get_state(self):
            worker_id = self._get_worker_id()

            return self._power_states[worker_id]

        def stop(self):
            worker_id = self._get_worker_id()
            # stopが呼ばれたら電源状態をFalseに設定
            self._power_states[worker_id] = False


def init(pin_no_):
    global fd_q10c
    global pin_no

    pin_no = pin_no_
    fd_q10c = FD_Q10C()


def stop():
    global fd_q10c

    logging.info("Stop flow sensing")

    try:
        fd_q10c.stop()
    except RuntimeError:
        logging.exception("Failed to stop FD-Q10C")


def get_power_state():
    global fd_q10c

    return fd_q10c.get_state()


def get_flow(force_power_on=True):
    global fd_q10c

    try:
        flow = fd_q10c.get_value(force_power_on)
    except Exception:
        logging.exception("バグの可能性あり。")
        flow = None
        # エラーメトリクス記録
        try:
            from unit_cooler.actuator.webapi.metrics import record_error

            record_error("sensor_read_error", "Flow sensor read failed")
        except ImportError:
            pass

    if flow is not None:
        logging.info("Valve flow = %.2f", flow)
    else:
        logging.info("Valve flow = UNKNOWN")

    # センサー読み取りメトリクス記録
    try:
        from unit_cooler.actuator.webapi.metrics import record_sensor_read

        record_sensor_read("flow_sensor", flow)
    except ImportError:
        pass

    return flow
