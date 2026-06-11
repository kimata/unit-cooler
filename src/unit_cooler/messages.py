#!/usr/bin/env python3
"""
メッセージスキーマ定義

Controller, Actuator, WebUI 間の通信に使用するメッセージの型を定義します。
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import unit_cooler.const


@dataclass(frozen=True)
class SensorReading:
    """センサーの 1 計測値"""

    name: str
    value: float | None
    time: datetime.datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "time": self.time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SensorReading:
        return cls(
            name=data["name"],
            value=data.get("value"),
            time=data.get("time"),
        )


@dataclass(frozen=True)
class SenseData:
    """制御判断に使うセンサーデータ一式

    power 以外のフィールドはすべて屋外環境センサーで、有効性チェックの対象。
    """

    temp: list[SensorReading] = field(default_factory=list)
    humi: list[SensorReading] = field(default_factory=list)
    lux: list[SensorReading] = field(default_factory=list)
    solar_rad: list[SensorReading] = field(default_factory=list)
    rain: list[SensorReading] = field(default_factory=list)
    power: list[SensorReading] = field(default_factory=list)

    @classmethod
    def environment_field_names(cls) -> list[str]:
        """屋外環境センサーのフィールド名（power 以外）

        有効性チェックの対象をフィールド定義から導出することで、
        センサー追加時のチェック漏れを構造的に防ぐ。
        """
        return [f.name for f in dataclasses.fields(cls) if f.name != "power"]

    def first_value(self, key: str) -> float | None:
        """指定センサーの最初の計測値を返す（欠損時は None）"""
        readings: list[SensorReading] = getattr(self, key)
        return readings[0].value if readings else None

    def to_dict(self) -> dict[str, Any]:
        return {f.name: [r.to_dict() for r in getattr(self, f.name)] for f in dataclasses.fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SenseData:
        return cls(
            **{
                f.name: [SensorReading.from_dict(r) for r in (data.get(f.name) or [])]
                for f in dataclasses.fields(cls)
            }
        )


@dataclass(frozen=True)
class DutyConfig:
    """冷却動作のデューティサイクル設定"""

    enable: bool
    on_sec: int
    off_sec: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable": self.enable,
            "on_sec": self.on_sec,
            "off_sec": self.off_sec,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DutyConfig:
        return cls(
            enable=data["enable"],
            on_sec=data["on_sec"],
            off_sec=data["off_sec"],
        )


@dataclass(frozen=True)
class StatusInfo:
    """ステータス情報（cooler_status と outdoor_status の共通構造）"""

    status: int
    message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusInfo:
        return cls(
            status=data["status"],
            message=data.get("message"),
        )


@dataclass(frozen=True)
class CoolingModeResult:
    """冷却モード判定結果"""

    cooling_mode: int
    cooler_status: StatusInfo
    outdoor_status: StatusInfo
    sense_data: SenseData | None = None


@dataclass(frozen=True)
class ControlMessage:
    """Controller から Actuator への制御メッセージ"""

    state: unit_cooler.const.COOLING_STATE
    duty: DutyConfig
    mode_index: int
    sense_data: SenseData | None = None
    cooler_status: StatusInfo | None = None
    outdoor_status: StatusInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "duty": self.duty.to_dict(),
            "mode_index": self.mode_index,
            "sense_data": self.sense_data.to_dict() if self.sense_data else None,
            "cooler_status": self.cooler_status.to_dict() if self.cooler_status else None,
            "outdoor_status": self.outdoor_status.to_dict() if self.outdoor_status else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlMessage:
        sense_data = data.get("sense_data")
        cooler_status_data = data.get("cooler_status")
        outdoor_status_data = data.get("outdoor_status")
        return cls(
            state=unit_cooler.const.COOLING_STATE(data["state"]),
            duty=DutyConfig.from_dict(data["duty"]),
            mode_index=data["mode_index"],
            sense_data=SenseData.from_dict(sense_data) if sense_data else None,
            cooler_status=StatusInfo.from_dict(cooler_status_data) if cooler_status_data else None,
            outdoor_status=StatusInfo.from_dict(outdoor_status_data) if outdoor_status_data else None,
        )

    @classmethod
    def from_json(cls, json_str: str) -> ControlMessage:
        return cls.from_dict(json.loads(json_str))


@dataclass(frozen=True)
class ValveStatus:
    """電磁弁の状態"""

    state: unit_cooler.const.VALVE_STATE
    duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "duration": self.duration_sec,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValveStatus:
        return cls(
            state=unit_cooler.const.VALVE_STATE(data["state"]),
            duration_sec=data["duration"],
        )


@dataclass(frozen=True)
class ActuatorStatus:
    """Actuator の状態（WebUI への配信用）"""

    timestamp: str
    valve: ValveStatus
    flow_lpm: float | None
    cooling_mode_index: int
    hazard_detected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "valve": self.valve.to_dict(),
            "flow_lpm": self.flow_lpm,
            "cooling_mode_index": self.cooling_mode_index,
            "hazard_detected": self.hazard_detected,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActuatorStatus:
        return cls(
            timestamp=data["timestamp"],
            valve=ValveStatus.from_dict(data["valve"]),
            flow_lpm=data["flow_lpm"],
            cooling_mode_index=data["cooling_mode_index"],
            hazard_detected=data["hazard_detected"],
        )

    @classmethod
    def from_json(cls, json_str: str) -> ActuatorStatus:
        return cls.from_dict(json.loads(json_str))
