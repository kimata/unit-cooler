#!/usr/bin/env python3
"""
メッセージスキーマ定義

Controller, Actuator, WebUI 間の通信に使用するメッセージの型を定義します。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import unit_cooler.const


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
class ControlMessage:
    """Controller から Actuator への制御メッセージ"""

    state: unit_cooler.const.COOLING_STATE
    duty: DutyConfig
    mode_index: int
    sense_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "duty": self.duty.to_dict(),
            "mode_index": self.mode_index,
            "sense_data": self.sense_data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlMessage:
        return cls(
            state=unit_cooler.const.COOLING_STATE(data["state"]),
            duty=DutyConfig.from_dict(data["duty"]),
            mode_index=data["mode_index"],
            sense_data=data.get("sense_data", {}),
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
