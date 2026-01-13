#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.controller.sensor のテスト"""

import dataclasses

import pytest

from unit_cooler.config import DecisionThresholdsConfig
from unit_cooler.const import AIRCON_MODE
from unit_cooler.controller.sensor import (
    get_cooler_activity,
    get_cooler_state,
    get_outdoor_status,
)

# デフォルト閾値
DEFAULT_THRESHOLDS = dataclasses.asdict(DecisionThresholdsConfig.default())


def create_sense_data(
    temp: float = 30.0,
    humi: float = 50.0,
    solar_rad: float = 400.0,
    lux: float = 500.0,
    rain: float = 0.0,
    powers: list[float] | None = None,
) -> dict:
    """テスト用センサーデータを作成"""
    if powers is None:
        powers = [600.0, 300.0]

    return {
        "temp": [{"name": "temp", "value": temp}],
        "humi": [{"name": "humi", "value": humi}],
        "solar_rad": [{"name": "solar_rad", "value": solar_rad}],
        "lux": [{"name": "lux", "value": lux}],
        "rain": [{"name": "rain", "value": rain}],
        "power": [{"name": f"power_{i}", "value": p} for i, p in enumerate(powers)],
    }


class TestGetOutdoorStatus:
    """get_outdoor_status のテスト"""

    def test_normal_conditions(self):
        """通常条件では status=0"""
        sense_data = create_sense_data(temp=30, humi=50, solar_rad=400, lux=500, rain=0)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 0
        assert result["message"] is None

    def test_rain_stops_cooling(self):
        """雨が降ると冷却停止 (status=-4)"""
        sense_data = create_sense_data(rain=0.1)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -4
        assert "雨" in result["message"]

    def test_high_humidity_stops_cooling(self):
        """高湿度で冷却停止 (status=-4)"""
        sense_data = create_sense_data(humi=98)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -4
        assert "湿度" in result["message"]

    def test_very_high_temp_and_solar_rad_boosts_cooling(self):
        """高温 + 日射量で冷却強化 (status=3)"""
        sense_data = create_sense_data(temp=36, solar_rad=100)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 3

    def test_high_temp_and_solar_rad_boosts_cooling(self):
        """やや高温 + 日射量で冷却強化 (status=2)"""
        sense_data = create_sense_data(temp=33, solar_rad=100)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 2

    def test_high_solar_rad_boosts_cooling(self):
        """高日射量で冷却やや強化 (status=1)"""
        sense_data = create_sense_data(temp=28, solar_rad=800)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 1

    def test_low_lux_reduces_cooling(self):
        """低照度で冷却弱化 (status=-2)"""
        sense_data = create_sense_data(temp=28, lux=200, solar_rad=400)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -2

    def test_high_temp_low_lux_reduces_cooling(self):
        """高温 + 低照度で冷却やや弱化 (status=-1)"""
        sense_data = create_sense_data(temp=30, lux=200, solar_rad=400)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -1

    def test_low_solar_rad_reduces_cooling(self):
        """低日射量で冷却やや弱化 (status=-1)"""
        sense_data = create_sense_data(temp=28, solar_rad=100, lux=500)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -1

    def test_missing_sensor_data_stops_cooling(self):
        """センサーデータ欠損で冷却停止 (status=-10)"""
        sense_data = create_sense_data(temp=30)
        sense_data["temp"][0]["value"] = None  # データ欠損
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == -10

    @pytest.mark.parametrize(
        "temp,humi,solar_rad,lux,rain,expected_status",
        [
            (30, 50, 400, 500, 0.0, 0),  # 通常
            (30, 50, 400, 500, 0.05, -4),  # 小雨
            (30, 97, 400, 500, 0.0, -4),  # 高湿度
            (36, 50, 100, 500, 0.0, 3),  # 酷暑
            (33, 50, 100, 500, 0.0, 2),  # 高温
            (28, 50, 800, 500, 0.0, 1),  # 高日射
            (28, 50, 400, 200, 0.0, -2),  # 低照度
            (30, 50, 400, 200, 0.0, -1),  # 高温+低照度
            (28, 50, 100, 500, 0.0, -1),  # 低日射
        ],
    )
    def test_outdoor_status_combinations(self, temp, humi, solar_rad, lux, rain, expected_status):
        """屋外ステータスのパラメトライズドテスト"""
        sense_data = create_sense_data(temp=temp, humi=humi, solar_rad=solar_rad, lux=lux, rain=rain)
        result = get_outdoor_status(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == expected_status


class TestGetCoolerState:
    """get_cooler_state のテスト"""

    def test_off_when_low_power(self):
        """低電力で OFF"""
        aircon_power = {"name": "aircon1", "value": 10}
        result = get_cooler_state(aircon_power, 25.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.OFF

    def test_idle_when_mid_power(self):
        """中電力で IDLE"""
        aircon_power = {"name": "aircon1", "value": 100}
        result = get_cooler_state(aircon_power, 25.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.IDLE

    def test_normal_when_high_power(self):
        """高電力で NORMAL"""
        aircon_power = {"name": "aircon1", "value": 600}
        result = get_cooler_state(aircon_power, 25.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.NORMAL

    def test_full_when_very_high_power(self):
        """超高電力で FULL"""
        aircon_power = {"name": "aircon1", "value": 1000}
        result = get_cooler_state(aircon_power, 25.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.FULL

    def test_off_when_low_temp(self):
        """低温 (暖房?) では OFF"""
        aircon_power = {"name": "aircon1", "value": 1000}
        result = get_cooler_state(aircon_power, 15.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.OFF

    def test_off_when_power_is_none(self):
        """電力データなしで OFF"""
        aircon_power = {"name": "aircon1", "value": None}
        result = get_cooler_state(aircon_power, 25.0, DEFAULT_THRESHOLDS)
        assert result == AIRCON_MODE.OFF

    def test_raises_when_temp_is_none(self):
        """外気温データなしで例外"""
        aircon_power = {"name": "aircon1", "value": 600}
        with pytest.raises(RuntimeError, match="外気温が不明"):
            get_cooler_state(aircon_power, None, DEFAULT_THRESHOLDS)

    @pytest.mark.parametrize(
        "power,temp,expected_mode",
        [
            (10, 25.0, AIRCON_MODE.OFF),
            (50, 25.0, AIRCON_MODE.IDLE),
            (100, 25.0, AIRCON_MODE.IDLE),
            (500, 25.0, AIRCON_MODE.IDLE),
            (501, 25.0, AIRCON_MODE.NORMAL),
            (700, 25.0, AIRCON_MODE.NORMAL),
            (900, 25.0, AIRCON_MODE.NORMAL),
            (901, 25.0, AIRCON_MODE.FULL),
            (1200, 25.0, AIRCON_MODE.FULL),
            (1000, 15.0, AIRCON_MODE.OFF),  # 低温
            (1000, 19.9, AIRCON_MODE.OFF),  # 境界
            (1000, 20.0, AIRCON_MODE.FULL),  # 境界
        ],
    )
    def test_cooler_state_thresholds(self, power, temp, expected_mode):
        """電力閾値のパラメトライズドテスト"""
        aircon_power = {"name": "aircon1", "value": power}
        result = get_cooler_state(aircon_power, temp, DEFAULT_THRESHOLDS)
        assert result == expected_mode


class TestGetCoolerActivity:
    """get_cooler_activity のテスト"""

    def test_no_activity(self):
        """エアコン稼働なし (status=0)"""
        sense_data = create_sense_data(powers=[10, 10])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 0

    def test_one_idle_activity(self):
        """1 台アイドル (status=1)"""
        sense_data = create_sense_data(powers=[100, 10])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 1

    def test_two_idle_activity(self):
        """2 台アイドル (status=2)"""
        sense_data = create_sense_data(powers=[100, 100])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 2

    def test_one_normal_activity(self):
        """1 台平常運転 (status=3)"""
        sense_data = create_sense_data(powers=[600, 10])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 3

    def test_two_normal_activity(self):
        """2 台平常運転 (status=4)"""
        sense_data = create_sense_data(powers=[600, 600])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 4

    def test_one_full_activity(self):
        """1 台フル稼働 (status=4)"""
        sense_data = create_sense_data(powers=[1000, 10])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 4

    def test_full_and_normal_activity(self):
        """1 台フル + 1 台平常 (status=5)"""
        sense_data = create_sense_data(powers=[1000, 600])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 5

    def test_two_full_activity(self):
        """2 台フル稼働 (status=6)"""
        sense_data = create_sense_data(powers=[1000, 1000])
        result = get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)
        assert result["status"] == 6

    def test_raises_when_temp_is_none(self):
        """外気温データなしで例外"""
        sense_data = create_sense_data()
        sense_data["temp"][0]["value"] = None
        with pytest.raises(RuntimeError, match="外気温が不明"):
            get_cooler_activity(sense_data, DEFAULT_THRESHOLDS)


class TestGetSenseData:
    """get_sense_data のテスト"""

    def test_fetches_all_sensor_kinds(self, config, mocker):
        """全センサー種別のデータを取得"""
        import datetime
        import zoneinfo

        from unit_cooler.controller.sensor import get_sense_data

        tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        mock_time = datetime.datetime(2024, 1, 1, 12, 0, 0)

        # 全センサーで有効なデータを返す
        mock_data = mocker.MagicMock()
        mock_data.valid = True
        mock_data.value = [25.0]
        mock_data.time = [mock_time]

        async def mock_fetch_parallel(db_config, requests):
            return [mock_data] * len(requests)

        mocker.patch("my_lib.sensor_data.fetch_data_parallel", side_effect=mock_fetch_parallel)
        mocker.patch("my_lib.time.get_zoneinfo", return_value=tz)

        result = get_sense_data(config)

        # 全種別が含まれている
        assert "temp" in result
        assert "humi" in result
        assert "lux" in result
        assert "solar_rad" in result
        assert "rain" in result
        assert "power" in result

    def test_notifies_error_on_failed_sensors(self, config, mocker):
        """センサーデータ取得失敗時にエラー通知"""
        from unit_cooler.controller.sensor import get_sense_data

        # 無効なデータを返す
        mock_data = mocker.MagicMock()
        mock_data.valid = False

        async def mock_fetch_parallel(db_config, requests):
            return [mock_data] * len(requests)

        mocker.patch("my_lib.sensor_data.fetch_data_parallel", side_effect=mock_fetch_parallel)
        mock_notify = mocker.patch("unit_cooler.util.notify_error")

        get_sense_data(config)

        # エラー通知が呼ばれる
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[0]
        assert "センサー" in call_args[1]
        assert "取得できませんでした" in call_args[1]

    def test_dummy_mode_uses_old_data_range(self, config, mocker):
        """DUMMY_MODEでは古いデータ範囲を使用"""
        import datetime
        import os
        import zoneinfo

        from unit_cooler.controller.sensor import get_sense_data

        tz = zoneinfo.ZoneInfo("Asia/Tokyo")
        mock_time = datetime.datetime(2024, 1, 1, 12, 0, 0)

        mock_data = mocker.MagicMock()
        mock_data.valid = True
        mock_data.value = [25.0]
        mock_data.time = [mock_time]

        captured_requests = []

        async def mock_fetch_parallel(db_config, requests):
            captured_requests.extend(requests)
            return [mock_data] * len(requests)

        mocker.patch("my_lib.sensor_data.fetch_data_parallel", side_effect=mock_fetch_parallel)
        mocker.patch("my_lib.time.get_zoneinfo", return_value=tz)
        mocker.patch.dict(os.environ, {"DUMMY_MODE": "true"})

        get_sense_data(config)

        # 最初のリクエストの start/stop を確認
        assert len(captured_requests) > 0
        first_request = captured_requests[0]
        assert first_request.start == "-169h"
        assert first_request.stop == "-168h"
