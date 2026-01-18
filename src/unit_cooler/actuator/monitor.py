#!/usr/bin/env python3
from __future__ import annotations

import logging
import math
import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING

import fluent.sender
import my_lib.pretty

import unit_cooler.actuator.control
import unit_cooler.actuator.sensor
import unit_cooler.actuator.valve_controller
import unit_cooler.actuator.work_log
import unit_cooler.const
import unit_cooler.messages
from unit_cooler.messages import ControlMessage

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config

# last_flow をモジュールレベル変数として管理
_last_flow: float = 0.0


@dataclass
class MistData:
    """ミスト状態データ（Fluentd 送信用）"""

    hostname: str
    state: int
    cooling_mode: int
    flow: float | None = None

    def to_dict(self) -> dict[str, float | int | str]:
        """Fluentd 送信用の辞書に変換"""
        result: dict[str, float | int | str] = {
            "hostname": self.hostname,
            "state": self.state,
            "cooling_mode": self.cooling_mode,
        }
        if self.flow is not None:
            result["flow"] = self.flow
        return result


@dataclass
class MonitorHandle:
    """モニターワーカーのハンドル"""

    config: Config
    hostname: str
    sender: fluent.sender.FluentSender
    log_period: int
    flow_unknown: int = 0
    monitor_count: int = 0


@dataclass(frozen=True)
class MistCondition:
    """ミスト状態"""

    valve: unit_cooler.messages.ValveStatus
    flow: float | None


def init(pin_no: int) -> None:
    unit_cooler.actuator.sensor.init(pin_no)


def gen_handle(config: Config, interval_sec: float) -> MonitorHandle:
    return MonitorHandle(
        config=config,
        hostname=os.environ.get("NODE_HOSTNAME", socket.gethostname()),
        sender=fluent.sender.FluentSender("sensor", host=config.actuator.monitor.fluent.host),
        log_period=max(math.ceil(60 / interval_sec), 1),
    )


def send_mist_condition(
    handle: MonitorHandle,
    mist_condition: MistCondition,
    control_message: ControlMessage,
    dummy_mode: bool = False,
) -> None:
    mist_data = MistData(
        hostname=handle.hostname,
        state=mist_condition.valve.state.value,
        cooling_mode=control_message.mode_index,
        flow=mist_condition.flow,
    )

    logger.debug("Send: %s", my_lib.pretty.format(mist_data.to_dict()))

    if dummy_mode:
        return

    send_data = mist_data.to_dict()

    if handle.sender.emit("rasp", send_data):
        logger.debug("Send OK")
    else:
        logger.error(handle.sender.last_error)


def get_mist_condition() -> MistCondition:
    global _last_flow

    valve_status = unit_cooler.actuator.valve_controller.get_valve_controller().get_status()

    if valve_status.state == unit_cooler.const.VALVE_STATE.OPEN:
        flow = unit_cooler.actuator.sensor.get_flow()
        # NOTE: get_flow() の内部で流量センサーの電源を入れている場合は計測に時間がかかるので、
        # その間に電磁弁の状態が変化している可能性があるので、再度状態を取得する。
        valve_status = unit_cooler.actuator.valve_controller.get_valve_controller().get_status()
    else:
        # NOTE: 電磁弁が閉じている場合、流量が 0 になるまでは計測を継続する。
        # (電磁弁の電源を切るため、流量が 0 になった場合は、電磁弁が開かれるまで計測は再開しない)
        flow = unit_cooler.actuator.sensor.get_flow() if _last_flow != 0 else 0

    if flow is not None:
        _last_flow = flow

    return MistCondition(valve=valve_status, flow=flow)


def get_last_flow() -> float:
    """最後に測定された流量を取得します。"""
    return _last_flow


def check_sensing(handle: MonitorHandle, mist_condition: MistCondition) -> None:
    if mist_condition.flow is None:
        handle.flow_unknown += 1
    else:
        handle.flow_unknown = 0

    config = handle.config
    if handle.flow_unknown > config.actuator.monitor.sense.giveup:
        unit_cooler.actuator.work_log.add("流量計が使えません。", unit_cooler.const.LOG_LEVEL.ERROR)
    elif handle.flow_unknown > (config.actuator.monitor.sense.giveup / 2):
        unit_cooler.actuator.work_log.add(
            "流量計が応答しないので一旦、リセットします。", unit_cooler.const.LOG_LEVEL.WARN
        )
        unit_cooler.actuator.sensor.stop()


def check_mist_condition(handle: MonitorHandle, mist_condition: MistCondition) -> None:
    logger.debug("Check mist condition")

    # NOTE: この関数は mist_condition.flow が None ではない場合にのみ呼ばれる
    assert mist_condition.flow is not None  # noqa: S101

    config = handle.config
    flow_config = config.actuator.monitor.flow

    if mist_condition.valve.state == unit_cooler.const.VALVE_STATE.OPEN:
        for i in range(len(flow_config.on.max)):
            if (mist_condition.flow > flow_config.on.max[i]) and (
                mist_condition.valve.duration_sec > 5 * (i + 1)
            ):
                unit_cooler.actuator.control.hazard_notify(
                    config,
                    (
                        "水漏れしています。"
                        f"(バルブを開いてから{mist_condition.valve.duration_sec:.1f}秒経過しても流量が "
                        f"{mist_condition.flow:.1f} L/min [> {flow_config.on.max[i]:.1f} L/min])"
                    ),
                )

        if (mist_condition.flow < flow_config.on.min) and (mist_condition.valve.duration_sec > 5):
            # NOTE: ハザード扱いにはしない
            duration = mist_condition.valve.duration_sec
            flow = mist_condition.flow
            unit_cooler.actuator.work_log.add(
                f"元栓が閉じています。(バルブを開いてから{duration:.1f}秒経過しても流量が {flow:.1f} L/min)",
                unit_cooler.const.LOG_LEVEL.ERROR,
            )
    else:
        logger.debug("Valve is close for %.1f sec", mist_condition.valve.duration_sec)
        if (mist_condition.valve.duration_sec >= flow_config.power_off_sec) and (mist_condition.flow == 0):
            # バルブが閉じてから長い時間が経っていて流量も 0 の場合、センサーを停止する
            if unit_cooler.actuator.sensor.get_power_state():
                unit_cooler.actuator.work_log.add(
                    "長い間バルブが閉じられていますので、流量計の電源を OFF します。"
                )
                unit_cooler.actuator.sensor.stop()
        elif (mist_condition.valve.duration_sec > 120) and (mist_condition.flow > flow_config.off.max):
            duration = mist_condition.valve.duration_sec
            flow = mist_condition.flow
            msg = "電磁弁が壊れていますので制御を停止します。"
            msg += f"(バルブを閉じてから{duration:.1f}秒経過しても流量が {flow:.1f} L/min)"
            unit_cooler.actuator.control.hazard_notify(config, msg)


def check(handle: MonitorHandle, mist_condition: MistCondition, need_logging: bool) -> bool:
    handle.monitor_count += 1

    if need_logging:
        logger.info(
            "Valve Condition: %s (flow = %s L/min)",
            mist_condition.valve.state.name,
            "?" if mist_condition.flow is None else f"{mist_condition.flow:.2f}",
        )

    check_sensing(handle, mist_condition)

    if mist_condition.flow is not None:
        check_mist_condition(handle, mist_condition)

    return True
