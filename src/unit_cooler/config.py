#!/usr/bin/env python3
"""設定ファイルの型定義

dacite を使用して YAML → dataclass 変換を行う。
YAML スキーマで型制約を検証済みのため、assert で型チェックを行う。
"""

from __future__ import annotations

import dataclasses
import pathlib
from dataclasses import dataclass
from typing import Any, Self

import dacite
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

    file: pathlib.Path


@dataclass(frozen=True)
class SensorItemConfig:
    """センサー項目設定"""

    name: str
    measure: str
    hostname: str


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


@dataclass(frozen=True)
class WateringConfig:
    """水やり設定"""

    measure: str
    hostname: str
    unit_price: float


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


# =============================================================================
# Actuator 設定
# =============================================================================
@dataclass(frozen=True)
class SubscribeConfig:
    """Subscribe 設定"""

    liveness: LivenessConfig


@dataclass(frozen=True)
class ValveOnConfig:
    """バルブ ON 時設定"""

    min: float
    max: float


@dataclass(frozen=True)
class ValveOffConfig:
    """バルブ OFF 時設定"""

    max: float


@dataclass(frozen=True)
class ValveConfig:
    """バルブ設定"""

    pin_no: int
    on: ValveOnConfig
    off: ValveOffConfig
    power_off_sec: int


@dataclass(frozen=True)
class HazardConfig:
    """ハザード設定"""

    file: str


@dataclass(frozen=True)
class ControlConfig:
    """Control 設定"""

    valve: ValveConfig
    interval_sec: int
    hazard: HazardConfig
    liveness: LivenessConfig


@dataclass(frozen=True)
class FlowOnConfig:
    """Flow ON 時設定"""

    min: float
    max: list[float]


@dataclass(frozen=True)
class FlowOffConfig:
    """Flow OFF 時設定"""

    max: float


@dataclass(frozen=True)
class FlowConfig:
    """Flow 設定"""

    on: FlowOnConfig
    off: FlowOffConfig
    power_off_sec: int


@dataclass(frozen=True)
class FluentConfig:
    """Fluent 設定"""

    host: str


@dataclass(frozen=True)
class SenseConfig:
    """Sense 設定"""

    giveup: int


@dataclass(frozen=True)
class MonitorConfig:
    """Monitor 設定"""

    flow: FlowConfig
    fluent: FluentConfig
    sense: SenseConfig
    interval_sec: int
    liveness: LivenessConfig


@dataclass(frozen=True)
class WebServerDataConfig:
    """Web サーバーデータ設定"""

    log_file_path: str


@dataclass(frozen=True)
class WebServerWebappConfig:
    """Web サーバー webapp 設定"""

    data: WebServerDataConfig

    def to_webapp_config(self, base_dir: pathlib.Path | None = None) -> my_lib.webapp.config.WebappConfig:
        """my_lib.webapp.config.WebappConfig に変換

        Args:
            base_dir: 設定ファイルの基準ディレクトリ。相対パスを解決するために使用。
        """
        log_path = pathlib.Path(self.data.log_file_path)
        if base_dir and not log_path.is_absolute():
            log_path = base_dir / log_path
        return my_lib.webapp.config.WebappConfig(
            data=my_lib.webapp.config.WebappDataConfig(
                log_file_path=log_path.resolve(),
            ),
        )


@dataclass(frozen=True)
class WebServerConfig:
    """Web サーバー設定"""

    webapp: WebServerWebappConfig


@dataclass(frozen=True)
class MetricsConfig:
    """Metrics 設定"""

    data: pathlib.Path


@dataclass(frozen=True)
class ActuatorConfig:
    """Actuator 設定"""

    subscribe: SubscribeConfig
    control: ControlConfig
    monitor: MonitorConfig
    web_server: WebServerConfig
    metrics: MetricsConfig


# =============================================================================
# WebUI 設定
# =============================================================================
@dataclass(frozen=True)
class WebUIWebappConfig:
    """WebUI webapp 設定"""

    static_dir_path: str
    port: int

    def to_webapp_config(self, base_dir: pathlib.Path | None = None) -> my_lib.webapp.config.WebappConfig:
        """my_lib.webapp.config.WebappConfig に変換

        Args:
            base_dir: 設定ファイルの基準ディレクトリ。相対パスを解決するために使用。
        """
        static_path = pathlib.Path(self.static_dir_path)
        if base_dir and not static_path.is_absolute():
            static_path = base_dir / static_path
        return my_lib.webapp.config.WebappConfig(
            static_dir_path=static_path.resolve(),
        )


@dataclass(frozen=True)
class WebUIConfig:
    """WebUI 設定"""

    webapp: WebUIWebappConfig
    subscribe: SubscribeConfig


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
    # このプロジェクトでは error 通知のみ使用（captcha は使わない）
    slack: my_lib.notify.slack.HasErrorConfig | my_lib.notify.slack.SlackEmptyConfig

    @classmethod
    def load(cls, config_path: str, schema_path: str | pathlib.Path | None = None) -> Self:
        """設定ファイルを読み込んで Config を生成する

        YAML スキーマでバリデーション済みのため、型は保証されている。
        dacite を使用して dict → dataclass 変換を行う。
        """
        raw_config = my_lib.config.load(config_path, schema_path)

        # スキーマでバリデーション済みなので、必須フィールドは存在する
        assert "base_dir" in raw_config  # noqa: S101
        assert "controller" in raw_config  # noqa: S101
        assert "actuator" in raw_config  # noqa: S101
        assert "webui" in raw_config  # noqa: S101

        base_dir = pathlib.Path(raw_config["base_dir"])

        # Slack 設定は my_lib.notify.slack.SlackConfig.parse() で処理
        # このプロジェクトでは error 通知のみ使用するので、
        # SlackCaptchaOnlyConfig は SlackEmptyConfig として扱う
        slack_parsed = my_lib.notify.slack.SlackConfig.parse(raw_config.get("slack", {}))
        if isinstance(slack_parsed, my_lib.notify.slack.SlackCaptchaOnlyConfig):
            slack: my_lib.notify.slack.HasErrorConfig | my_lib.notify.slack.SlackEmptyConfig = (
                my_lib.notify.slack.SlackEmptyConfig()
            )
        else:
            # SlackConfig, SlackErrorInfoConfig, SlackErrorOnlyConfig, SlackEmptyConfig
            # これらは全て HasErrorConfig | SlackEmptyConfig を満たす
            slack = slack_parsed  # type: ignore[assignment]

        # decision がない場合のデフォルト値を設定
        controller_data = dict(raw_config["controller"])
        if "decision" not in controller_data:
            controller_data["decision"] = dataclasses.asdict(DecisionConfig.default())

        # actuator.metrics.data の相対パスを解決
        actuator_data = _resolve_relative_paths(raw_config["actuator"], base_dir)

        # dacite の設定
        dacite_config = dacite.Config(
            type_hooks={
                pathlib.Path: pathlib.Path,
            },
            cast=[pathlib.Path],
            strict=False,
        )

        return cls(
            base_dir=base_dir,
            controller=dacite.from_dict(ControllerConfig, controller_data, dacite_config),
            actuator=dacite.from_dict(ActuatorConfig, actuator_data, dacite_config),
            webui=dacite.from_dict(WebUIConfig, raw_config["webui"], dacite_config),
            slack=slack,
        )


def _resolve_relative_paths(actuator_data: dict[str, Any], base_dir: pathlib.Path) -> dict[str, Any]:
    """Actuator 設定の相対パスを解決する"""
    result = dict(actuator_data)

    # metrics.data の相対パスを解決
    if "metrics" in result:
        metrics = dict(result["metrics"])
        data_path = pathlib.Path(metrics["data"])
        if not data_path.is_absolute():
            data_path = base_dir / data_path
        metrics["data"] = str(data_path.resolve())
        result["metrics"] = metrics

    return result
