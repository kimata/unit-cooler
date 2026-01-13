#!/usr/bin/env python3
"""設定ファイルの型定義"""

from __future__ import annotations

import dataclasses
import pathlib
from dataclasses import dataclass
from typing import Any, Self

import my_lib.config
import my_lib.notify.slack
import my_lib.webapp.config


# =============================================================================
# 実行時設定 (CLI引数・環境変数由来)
# =============================================================================
@dataclass
class RuntimeSettings:
    """実行時設定 (config.yaml ではなく起動時に指定される設定)

    各コンポーネント (Controller, Actuator, WebUI) の起動時に
    CLI引数や環境変数から設定される値を型安全に管理する。
    """

    # ネットワーク設定 (共通)
    control_host: str = "localhost"
    pub_port: int = 2222

    # Actuator 固有
    log_port: int = 5001
    status_pub_port: int = 0

    # Controller 固有
    server_host: str = "localhost"
    server_port: int = 2222
    real_port: int = 2200
    disable_proxy: bool = False
    idle_timeout_sec: int = 0  # proxy のアイドルタイムアウト（0=無制限）

    # WebUI 固有
    actuator_host: str = "localhost"

    # 実行モード設定 (共通)
    dummy_mode: bool = False
    speedup: int = 1
    msg_count: int = 0
    debug_mode: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """dict から RuntimeSettings を生成 (未知のキーは無視)

        型変換も自動的に行う:
        - 文字列 "true"/"false" → bool
        - 文字列の数値 → int
        """
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        field_types = {f.name: f.type for f in dataclasses.fields(cls)}
        filtered: dict[str, Any] = {}

        for k, v in data.items():
            if k not in valid_fields:
                continue

            expected_type = field_types[k]

            # bool 型フィールドの変換
            if expected_type is bool:
                if isinstance(v, str):
                    filtered[k] = v.lower() in ("true", "1", "yes")
                else:
                    filtered[k] = bool(v)
            # int 型フィールドの変換
            elif expected_type is int:
                filtered[k] = int(v) if v is not None else 0
            else:
                filtered[k] = v

        return cls(**filtered)


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
class DecisionThresholdsConfig:
    """判定閾値設定"""

    # 屋外の照度がこの値未満の場合、冷却の強度を弱める
    lux: int
    # 太陽の日射量がこの値未満の場合、冷却の強度を弱める
    solar_rad_low: int
    # 太陽の日射量がこの値を超える場合、冷却の強度を強める
    solar_rad_high: int
    # 太陽の日射量がこの値より大きい場合、昼間とする
    solar_rad_daytime: int
    # 屋外の湿度がこの値を超えていたら、冷却を停止する
    humi_max: int
    # 屋外の温度がこの値を超えていたら、冷却の強度を大きく強める
    temp_high_h: int
    # 屋外の温度がこの値を超えていたら、冷却の強度を強める
    temp_high_l: int
    # 屋外の温度がこの値を超えていたら、冷却の強度を少し強める
    temp_mid: int
    # エアコンの冷房動作と判定する温度閾値
    temp_cooling: int
    # 降雨量〔mm/h〕がこの値を超えていたら、冷却を停止する
    rain_max: float
    # クーラー動作中と判定する電力閾値(W)
    power_work: int
    # クーラー平常運転中と判定する電力閾値(W)
    power_normal: int
    # クーラーフル稼働中と判定する電力閾値(W)
    power_full: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(
            lux=data["lux"],
            solar_rad_low=data["solar_rad_low"],
            solar_rad_high=data["solar_rad_high"],
            solar_rad_daytime=data["solar_rad_daytime"],
            humi_max=data["humi_max"],
            temp_high_h=data["temp_high_h"],
            temp_high_l=data["temp_high_l"],
            temp_mid=data["temp_mid"],
            temp_cooling=data["temp_cooling"],
            rain_max=data["rain_max"],
            power_work=data["power_work"],
            power_normal=data["power_normal"],
            power_full=data["power_full"],
        )

    @classmethod
    def default(cls) -> Self:
        """デフォルト値を返す（既存動作との互換性のため）"""
        return cls(
            lux=300,
            solar_rad_low=200,
            solar_rad_high=700,
            solar_rad_daytime=50,
            humi_max=96,
            temp_high_h=35,
            temp_high_l=32,
            temp_mid=29,
            temp_cooling=20,
            rain_max=0.01,
            power_work=20,
            power_normal=500,
            power_full=900,
        )


@dataclass(frozen=True)
class DecisionConfig:
    """判定設定"""

    thresholds: DecisionThresholdsConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(thresholds=DecisionThresholdsConfig.parse(data["thresholds"]))

    @classmethod
    def default(cls) -> Self:
        """デフォルト値を返す（既存動作との互換性のため）"""
        return cls(thresholds=DecisionThresholdsConfig.default())


@dataclass(frozen=True)
class ControllerConfig:
    """Controller 設定"""

    influxdb: InfluxDBConfig
    sensor: SensorConfig
    watering: WateringConfig
    decision: DecisionConfig
    interval_sec: int
    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        # decision は省略可能（後方互換性のため）
        decision = DecisionConfig.parse(data["decision"]) if "decision" in data else DecisionConfig.default()

        return cls(
            influxdb=InfluxDBConfig.parse(data["influxdb"]),
            sensor=SensorConfig.parse(data["sensor"]),
            watering=WateringConfig.parse(data["watering"]),
            decision=decision,
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
