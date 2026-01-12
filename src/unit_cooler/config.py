#!/usr/bin/env python3
"""設定ファイルの型定義"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any, Self

import my_lib.config
import my_lib.notify.slack
import my_lib.webapp.config


# =============================================================================
# 共通設定
# =============================================================================
@dataclass(frozen=True)
class LivenessConfig:
    """Liveness チェック設定"""

    file: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(file=data["file"])


@dataclass(frozen=True)
class SensorItemConfig:
    """センサー項目設定"""

    name: str
    measure: str
    hostname: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data["name"],
            measure=data["measure"],
            hostname=data["hostname"],
        )


# =============================================================================
# Controller 設定
# =============================================================================
@dataclass(frozen=True)
class InfluxDBConfig:
    """InfluxDB 接続設定"""

    url: str
    token: str
    org: str
    bucket: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            url=data["url"],
            token=data["token"],
            org=data["org"],
            bucket=data["bucket"],
        )

    def to_dict(self) -> dict[str, str]:
        """dict 形式に変換する（my_lib.sensor_data との互換性のため）"""
        return {
            "url": self.url,
            "token": self.token,
            "org": self.org,
            "bucket": self.bucket,
        }


@dataclass(frozen=True)
class SensorConfig:
    """センサー設定"""

    temp: list[SensorItemConfig]
    humi: list[SensorItemConfig]
    lux: list[SensorItemConfig]
    solar_rad: list[SensorItemConfig]
    rain: list[SensorItemConfig]
    power: list[SensorItemConfig]

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            temp=[SensorItemConfig.parse(item) for item in data["temp"]],
            humi=[SensorItemConfig.parse(item) for item in data["humi"]],
            lux=[SensorItemConfig.parse(item) for item in data["lux"]],
            solar_rad=[SensorItemConfig.parse(item) for item in data["solar_rad"]],
            rain=[SensorItemConfig.parse(item) for item in data["rain"]],
            power=[SensorItemConfig.parse(item) for item in data["power"]],
        )


@dataclass(frozen=True)
class WateringConfig:
    """水やり設定"""

    measure: str
    hostname: str
    unit_price: float

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            measure=data["measure"],
            hostname=data["hostname"],
            unit_price=data["unit_price"],
        )


@dataclass(frozen=True)
class ControllerConfig:
    """Controller 設定"""

    influxdb: InfluxDBConfig
    sensor: SensorConfig
    watering: WateringConfig
    interval_sec: int
    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            influxdb=InfluxDBConfig.parse(data["influxdb"]),
            sensor=SensorConfig.parse(data["sensor"]),
            watering=WateringConfig.parse(data["watering"]),
            interval_sec=data["interval_sec"],
            liveness=LivenessConfig.parse(data["liveness"]),
        )


# =============================================================================
# Actuator 設定
# =============================================================================
@dataclass(frozen=True)
class SubscribeConfig:
    """Subscribe 設定"""

    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(liveness=LivenessConfig.parse(data["liveness"]))


@dataclass(frozen=True)
class ValveOnConfig:
    """バルブ ON 時設定"""

    min: float
    max: float

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(min=data["min"], max=data["max"])


@dataclass(frozen=True)
class ValveOffConfig:
    """バルブ OFF 時設定"""

    max: float

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(max=data["max"])


@dataclass(frozen=True)
class ValveConfig:
    """バルブ設定"""

    pin_no: int
    on: ValveOnConfig
    off: ValveOffConfig
    power_off_sec: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            pin_no=data["pin_no"],
            on=ValveOnConfig.parse(data["on"]),
            off=ValveOffConfig.parse(data["off"]),
            power_off_sec=data["power_off_sec"],
        )


@dataclass(frozen=True)
class HazardConfig:
    """ハザード設定"""

    file: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(file=data["file"])


@dataclass(frozen=True)
class ControlConfig:
    """Control 設定"""

    valve: ValveConfig
    interval_sec: int
    hazard: HazardConfig
    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            valve=ValveConfig.parse(data["valve"]),
            interval_sec=data["interval_sec"],
            hazard=HazardConfig.parse(data["hazard"]),
            liveness=LivenessConfig.parse(data["liveness"]),
        )


@dataclass(frozen=True)
class FlowOnConfig:
    """Flow ON 時設定"""

    min: float
    max: list[float]

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(min=data["min"], max=data["max"])


@dataclass(frozen=True)
class FlowOffConfig:
    """Flow OFF 時設定"""

    max: float

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(max=data["max"])


@dataclass(frozen=True)
class FlowConfig:
    """Flow 設定"""

    on: FlowOnConfig
    off: FlowOffConfig
    power_off_sec: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            on=FlowOnConfig.parse(data["on"]),
            off=FlowOffConfig.parse(data["off"]),
            power_off_sec=data["power_off_sec"],
        )


@dataclass(frozen=True)
class FluentConfig:
    """Fluent 設定"""

    host: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(host=data["host"])


@dataclass(frozen=True)
class SenseConfig:
    """Sense 設定"""

    giveup: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(giveup=data["giveup"])


@dataclass(frozen=True)
class MonitorConfig:
    """Monitor 設定"""

    flow: FlowConfig
    fluent: FluentConfig
    sense: SenseConfig
    interval_sec: int
    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            flow=FlowConfig.parse(data["flow"]),
            fluent=FluentConfig.parse(data["fluent"]),
            sense=SenseConfig.parse(data["sense"]),
            interval_sec=data["interval_sec"],
            liveness=LivenessConfig.parse(data["liveness"]),
        )


@dataclass(frozen=True)
class WebServerDataConfig:
    """Web サーバーデータ設定"""

    log_file_path: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(log_file_path=data["log_file_path"])


@dataclass(frozen=True)
class WebServerWebappConfig:
    """Web サーバー webapp 設定"""

    data: WebServerDataConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(data=WebServerDataConfig.parse(data["data"]))

    def to_webapp_config(self) -> my_lib.webapp.config.WebappConfig:
        """my_lib.webapp.config.WebappConfig に変換"""
        return my_lib.webapp.config.WebappConfig(
            data=my_lib.webapp.config.WebappDataConfig(
                log_file_path=pathlib.Path(self.data.log_file_path).resolve(),
            ),
        )


@dataclass(frozen=True)
class WebServerConfig:
    """Web サーバー設定"""

    webapp: WebServerWebappConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(webapp=WebServerWebappConfig.parse(data["webapp"]))


@dataclass(frozen=True)
class MetricsConfig:
    """Metrics 設定"""

    data: str

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(data=data["data"])


@dataclass(frozen=True)
class ActuatorConfig:
    """Actuator 設定"""

    subscribe: SubscribeConfig
    control: ControlConfig
    monitor: MonitorConfig
    web_server: WebServerConfig
    metrics: MetricsConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            subscribe=SubscribeConfig.parse(data["subscribe"]),
            control=ControlConfig.parse(data["control"]),
            monitor=MonitorConfig.parse(data["monitor"]),
            web_server=WebServerConfig.parse(data["web_server"]),
            metrics=MetricsConfig.parse(data["metrics"]),
        )


# =============================================================================
# WebUI 設定
# =============================================================================
@dataclass(frozen=True)
class WebUIWebappConfig:
    """WebUI webapp 設定"""

    static_dir_path: str
    port: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            static_dir_path=data["static_dir_path"],
            port=data["port"],
        )

    def to_webapp_config(self) -> my_lib.webapp.config.WebappConfig:
        """my_lib.webapp.config.WebappConfig に変換"""
        return my_lib.webapp.config.WebappConfig(
            static_dir_path=pathlib.Path(self.static_dir_path).resolve(),
        )


@dataclass(frozen=True)
class WebUIConfig:
    """WebUI 設定"""

    webapp: WebUIWebappConfig
    subscribe: SubscribeConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            webapp=WebUIWebappConfig.parse(data["webapp"]),
            subscribe=SubscribeConfig.parse(data["subscribe"]),
        )


# =============================================================================
# アプリケーション設定
# =============================================================================
@dataclass(frozen=True)
class Config:
    """アプリケーション設定"""

    base_dir: pathlib.Path
    controller: ControllerConfig
    actuator: ActuatorConfig
    webui: WebUIConfig
    slack: my_lib.notify.slack.HasErrorConfig | my_lib.notify.slack.SlackEmptyConfig

    @classmethod
    def load(cls, config_path: str, schema_path: str | pathlib.Path | None = None) -> Self:
        """設定ファイルを読み込んで Config を生成する"""
        raw_config = my_lib.config.load(config_path, schema_path)

        slack = my_lib.notify.slack.parse_config(raw_config.get("slack", {}))

        # このプロジェクトでは error を持つ設定、または設定なしのパターンに対応
        if not isinstance(
            slack,
            my_lib.notify.slack.SlackErrorOnlyConfig
            | my_lib.notify.slack.SlackErrorInfoConfig
            | my_lib.notify.slack.SlackConfig
            | my_lib.notify.slack.SlackEmptyConfig,
        ):
            raise ValueError("Slack 設定には error が必要です（または設定なし）")

        return cls(
            base_dir=pathlib.Path(raw_config["base_dir"]),
            controller=ControllerConfig.parse(raw_config["controller"]),
            actuator=ActuatorConfig.parse(raw_config["actuator"]),
            webui=WebUIConfig.parse(raw_config["webui"]),
            slack=slack,
        )
