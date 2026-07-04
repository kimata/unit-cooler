#!/usr/bin/env python3
# ruff: noqa: S101, S105, S108
"""unit_cooler.config のテスト"""

import pathlib

import dacite
import pytest

from unit_cooler.config import (
    Config,
    ControlConfig,
    DecisionConfig,
    DecisionThresholdsConfig,
    FlowConfig,
    InfluxDBConfig,
    LivenessConfig,
    MetricsConfig,
    MonitorConfig,
    NightStopConfig,
    RuntimeSettings,
    SensorConfig,
    SensorItemConfig,
    ValveConfig,
    WateringConfig,
    WebServerConfig,
    WebUIWebappConfig,
)

# dacite 設定
DACITE_CONFIG = dacite.Config(
    type_hooks={pathlib.Path: pathlib.Path},
    cast=[pathlib.Path],
    strict=False,
)


class TestRuntimeSettings:
    """RuntimeSettings のテスト"""

    def test_from_dict_converts_bool_strings(self):
        """環境変数由来の文字列 "false"/"true" が bool に変換される"""
        settings = RuntimeSettings.from_dict({"dummy_mode": "false"})
        assert settings.dummy_mode is False

        settings = RuntimeSettings.from_dict({"dummy_mode": "true"})
        assert settings.dummy_mode is True

        settings = RuntimeSettings.from_dict({"dummy_mode": "0"})
        assert settings.dummy_mode is False

    def test_from_dict_keeps_native_bool(self):
        """bool 値はそのまま"""
        settings = RuntimeSettings.from_dict({"dummy_mode": True, "debug_mode": False})
        assert settings.dummy_mode is True
        assert settings.debug_mode is False

    def test_from_dict_converts_int_strings(self):
        """環境変数由来の文字列数値が int に変換される"""
        settings = RuntimeSettings.from_dict({"pub_port": "2222", "speedup": "2"})
        assert settings.pub_port == 2222
        assert settings.speedup == 2

    def test_from_dict_none_int_becomes_zero(self):
        """int フィールドの None は 0 になる"""
        settings = RuntimeSettings.from_dict({"msg_count": None})
        assert settings.msg_count == 0

    def test_from_dict_ignores_unknown_keys(self):
        """未知のキーは無視される"""
        settings = RuntimeSettings.from_dict({"unknown_key": "value", "control_host": "example.com"})
        assert settings.control_host == "example.com"


class TestLivenessConfig:
    """LivenessConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {"file": "/tmp/liveness.txt"}
        config = dacite.from_dict(LivenessConfig, data, DACITE_CONFIG)
        assert config.file == pathlib.Path("/tmp/liveness.txt")

    def test_frozen(self):
        """immutable"""
        import dataclasses

        config = LivenessConfig(file=pathlib.Path("/tmp/test"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.file = "/tmp/other"  # type: ignore


class TestSensorItemConfig:
    """SensorItemConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "name": "outdoor_temp",
            "measure": "sensor.esp32",
            "hostname": "esp32-sensor",
        }
        config = dacite.from_dict(SensorItemConfig, data, DACITE_CONFIG)
        assert config.name == "outdoor_temp"
        assert config.measure == "sensor.esp32"
        assert config.hostname == "esp32-sensor"


class TestInfluxDBConfig:
    """InfluxDBConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "url": "http://localhost:8086",
            "token": "test-token",
            "org": "test-org",
            "bucket": "test-bucket",
        }
        config = dacite.from_dict(InfluxDBConfig, data, DACITE_CONFIG)
        assert config.url == "http://localhost:8086"
        assert config.token == "test-token"
        assert config.org == "test-org"
        assert config.bucket == "test-bucket"

    def test_is_my_lib_alias(self):
        """unit_cooler.config.InfluxDBConfig は my_lib.sensor_data.InfluxDBConfig の再エクスポート"""
        import my_lib.sensor_data

        assert InfluxDBConfig is my_lib.sensor_data.InfluxDBConfig


class TestSensorConfig:
    """SensorConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "temp": [{"name": "temp1", "measure": "m1", "hostname": "h1"}],
            "humi": [{"name": "humi1", "measure": "m2", "hostname": "h2"}],
            "lux": [{"name": "lux1", "measure": "m3", "hostname": "h3"}],
            "solar_rad": [{"name": "solar1", "measure": "m4", "hostname": "h4"}],
            "rain": [{"name": "rain1", "measure": "m5", "hostname": "h5"}],
            "power": [{"name": "power1", "measure": "m6", "hostname": "h6"}],
        }
        config = dacite.from_dict(SensorConfig, data, DACITE_CONFIG)
        assert len(config.temp) == 1
        assert config.temp[0].name == "temp1"
        assert len(config.power) == 1


class TestWateringConfig:
    """WateringConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "measure": "rasp.cooler",
            "hostname": "rasp-cooler",
            "unit_price": 0.24,
        }
        config = dacite.from_dict(WateringConfig, data, DACITE_CONFIG)
        assert config.measure == "rasp.cooler"
        assert config.hostname == "rasp-cooler"
        assert config.unit_price == 0.24


class TestDecisionThresholdsConfig:
    """DecisionThresholdsConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "lux": 300,
            "solar_rad_low": 200,
            "solar_rad_high": 700,
            "solar_rad_daytime": 50,
            "humi_max": 96,
            "temp_high_h": 35,
            "temp_high_l": 32,
            "temp_mid": 29,
            "temp_cooling": 20,
            "rain_max": 0.01,
            "power_work": 20,
            "power_normal": 500,
            "power_full": 900,
        }
        config = dacite.from_dict(DecisionThresholdsConfig, data, DACITE_CONFIG)
        assert config.lux == 300
        assert config.humi_max == 96
        assert config.rain_max == 0.01

    def test_default(self):
        """デフォルト値"""
        config = DecisionThresholdsConfig.default()
        assert config.lux == 300
        assert config.solar_rad_low == 200
        assert config.solar_rad_high == 700
        assert config.humi_max == 96


class TestNightStopConfig:
    """NightStopConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {"enable": False, "start_hour": 22, "end_hour": 5}
        config = dacite.from_dict(NightStopConfig, data, DACITE_CONFIG)
        assert config.enable is False
        assert config.start_hour == 22
        assert config.end_hour == 5

    def test_default(self):
        """デフォルト値（21時〜6時停止）"""
        config = NightStopConfig.default()
        assert config.enable is True
        assert config.start_hour == 21
        assert config.end_hour == 6


class TestDecisionConfig:
    """DecisionConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "thresholds": {
                "lux": 400,
                "solar_rad_low": 250,
                "solar_rad_high": 750,
                "solar_rad_daytime": 60,
                "humi_max": 95,
                "temp_high_h": 36,
                "temp_high_l": 33,
                "temp_mid": 30,
                "temp_cooling": 21,
                "rain_max": 0.02,
                "power_work": 25,
                "power_normal": 550,
                "power_full": 950,
            }
        }
        config = dacite.from_dict(DecisionConfig, data, DACITE_CONFIG)
        assert config.thresholds.lux == 400

    def test_default(self):
        """デフォルト値"""
        config = DecisionConfig.default()
        assert config.thresholds.lux == 300

    def test_night_stop_defaults_when_missing(self):
        """night_stop を省略した場合はデフォルト値が使われる（既存 config との互換性）"""
        config = dacite.from_dict(DecisionConfig, {}, DACITE_CONFIG)
        assert config.night_stop == NightStopConfig.default()


class TestValveConfig:
    """ValveConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "pin_no": 17,
            "on": {"min": 2.0, "max": 10.0},
            "off": {"max": 0.5},
            "power_off_sec": 300,
        }
        config = dacite.from_dict(ValveConfig, data, DACITE_CONFIG)
        assert config.pin_no == 17
        assert config.on.min == 2.0
        assert config.on.max == 10.0
        assert config.off.max == 0.5
        assert config.power_off_sec == 300


class TestFlowConfig:
    """FlowConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "on": {"min": 0.5, "max": [5.0, 10.0]},
            "off": {"max": 0.1},
            "power_off_sec": 60,
        }
        config = dacite.from_dict(FlowConfig, data, DACITE_CONFIG)
        assert config.on.min == 0.5
        assert config.on.max == [5.0, 10.0]
        assert config.off.max == 0.1
        assert config.power_off_sec == 60


class TestMonitorConfig:
    """MonitorConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "flow": {
                "on": {"min": 0.5, "max": [5.0]},
                "off": {"max": 0.1},
                "power_off_sec": 60,
            },
            "fluent": {"host": "localhost"},
            "sense": {"giveup": 5},
            "interval_sec": 10,
            "liveness": {"file": "/tmp/monitor.txt"},
        }
        config = dacite.from_dict(MonitorConfig, data, DACITE_CONFIG)
        assert config.flow.on.min == 0.5
        assert config.fluent.host == "localhost"
        assert config.sense.giveup == 5
        assert config.interval_sec == 10


class TestControlConfig:
    """ControlConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "valve": {
                "pin_no": 17,
                "on": {"min": 2.0, "max": 10.0},
                "off": {"max": 0.5},
                "power_off_sec": 300,
            },
            "interval_sec": 5,
            "hazard": {"file": "/tmp/hazard.json"},
            "liveness": {"file": "/tmp/control.txt"},
        }
        config = dacite.from_dict(ControlConfig, data, DACITE_CONFIG)
        assert config.valve.pin_no == 17
        assert config.interval_sec == 5
        assert config.hazard.file == "/tmp/hazard.json"


class TestWebServerConfig:
    """WebServerConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {"webapp": {"data": {"log_file_path": "/tmp/log.db"}}}
        config = dacite.from_dict(WebServerConfig, data, DACITE_CONFIG)
        assert config.webapp.data.log_file_path == "/tmp/log.db"


class TestMetricsConfig:
    """MetricsConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {"data": "/tmp/metrics.db"}
        config = dacite.from_dict(MetricsConfig, data, DACITE_CONFIG)
        assert config.data == pathlib.Path("/tmp/metrics.db")


class TestWebUIWebappConfig:
    """WebUIWebappConfig のテスト"""

    def test_from_dict(self):
        """dict から変換"""
        data = {
            "static_dir_path": "/var/www/static",
            "port": 5000,
        }
        config = dacite.from_dict(WebUIWebappConfig, data, DACITE_CONFIG)
        assert config.static_dir_path == "/var/www/static"
        assert config.port == 5000


class TestConfigLoad:
    """Config.load のテスト"""

    def test_load_example_config(self):
        """config.example.yaml を読み込める"""
        config = Config.load("config.example.yaml", pathlib.Path("schema/config.schema"))

        # 基本構造の確認
        assert config.base_dir is not None
        assert config.controller is not None
        assert config.actuator is not None
        assert config.webui is not None

    def test_controller_section(self, config):
        """controller セクション"""
        assert config.controller.influxdb is not None
        assert config.controller.sensor is not None
        assert config.controller.watering is not None
        assert config.controller.interval_sec > 0

    def test_actuator_section(self, config):
        """actuator セクション"""
        assert config.actuator.subscribe is not None
        assert config.actuator.control is not None
        assert config.actuator.monitor is not None
        assert config.actuator.web_server is not None
        assert config.actuator.metrics is not None

    def test_webui_section(self, config):
        """webui セクション"""
        assert config.webui.webapp is not None
        assert config.webui.subscribe is not None
        assert config.webui.webapp.port > 0

    def test_decision_section(self, config):
        """decision セクション (オプション)"""
        # decision はオプションで、存在しない場合はデフォルト値が使用される
        assert config.controller.decision is not None
        assert config.controller.decision.thresholds is not None

    def test_load_without_decision(self, tmp_path):
        """decision セクションがない config でも読み込める（本番 config との互換性）"""
        import yaml

        with pathlib.Path("config.example.yaml").open() as f:
            raw = yaml.safe_load(f)
        del raw["controller"]["decision"]

        config_path = tmp_path / "config.yaml"
        with config_path.open("w") as f:
            yaml.safe_dump(raw, f, allow_unicode=True)

        config = Config.load(str(config_path), pathlib.Path("schema/config.schema"))
        assert config.controller.decision.night_stop == NightStopConfig.default()

    def test_influxdb_is_my_lib_type(self, config):
        """InfluxDB 設定は my_lib.sensor_data.InfluxDBConfig のインスタンス"""
        import my_lib.sensor_data

        assert isinstance(config.controller.influxdb, my_lib.sensor_data.InfluxDBConfig)

    def test_webapp_to_webapp_config(self, config):
        """webapp 設定の変換"""
        webapp_config = config.webui.webapp.to_webapp_config()
        assert webapp_config is not None
        assert webapp_config.static_dir_path is not None


class TestConfigFrozen:
    """Config の immutability テスト"""

    def test_config_is_frozen(self, config):
        """Config は変更不可"""
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            config.base_dir = pathlib.Path("/other")

    def test_nested_config_is_frozen(self, config):
        """ネストされた Config も変更不可"""
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            config.controller.interval_sec = 999
