#!/usr/bin/env python3
"""センサーデータ生成ユーティリティ"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from my_lib.sensor_data import SensorDataResult

if TYPE_CHECKING:
    from typing import Any


class SensorDataFactory:
    """センサーデータファクトリー

    InfluxDB から取得するセンサーデータのモックを生成する。
    """

    @staticmethod
    def create(
        value: list[float] | None = None,
        valid: bool = True,
        error_message: str | None = None,
    ) -> SensorDataResult:
        """センサーデータを生成

        Args:
            value: センサー値のリスト (デフォルト: [30, 34, 25])
            valid: データが有効かどうか
            error_message: エラーメッセージ

        Returns:
            SensorDataResult オブジェクト
        """
        if value is None:
            value = [30.0, 34.0, 25.0]

        time_list = [
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=i - len(value))
            for i in range(len(value))
        ]

        return SensorDataResult(
            value=value,
            time=time_list,
            valid=valid,
            raw_record_count=len(value) if valid else 0,
            error_message=error_message,
        )

    @staticmethod
    def create_temp_data(temp: float = 30.0, valid: bool = True) -> SensorDataResult:
        """温度データを生成"""
        return SensorDataFactory.create(value=[temp], valid=valid)

    @staticmethod
    def create_humidity_data(humi: float = 50.0, valid: bool = True) -> SensorDataResult:
        """湿度データを生成"""
        return SensorDataFactory.create(value=[humi], valid=valid)

    @staticmethod
    def create_power_data(power: float = 500.0, valid: bool = True) -> SensorDataResult:
        """電力データを生成"""
        return SensorDataFactory.create(value=[power], valid=valid)

    @staticmethod
    def create_lux_data(lux: float = 500.0, valid: bool = True) -> SensorDataResult:
        """照度データを生成"""
        return SensorDataFactory.create(value=[lux], valid=valid)

    @staticmethod
    def create_solar_rad_data(solar_rad: float = 400.0, valid: bool = True) -> SensorDataResult:
        """日射量データを生成"""
        return SensorDataFactory.create(value=[solar_rad], valid=valid)

    @staticmethod
    def create_rain_data(rain: float = 0.0, valid: bool = True) -> SensorDataResult:
        """降雨量データを生成"""
        return SensorDataFactory.create(value=[rain], valid=valid)

    @staticmethod
    def create_invalid() -> SensorDataResult:
        """無効なセンサーデータを生成"""
        return SensorDataFactory.create(value=[], valid=False)

    @staticmethod
    def create_with_error(error_message: str = "Connection error") -> SensorDataResult:
        """エラー付きセンサーデータを生成"""
        return SensorDataResult(
            value=[],
            time=[],
            valid=False,
            raw_record_count=0,
            error_message=error_message,
        )


def create_sense_data_dict(
    temp: float = 30.0,
    humi: float = 50.0,
    lux: float = 500.0,
    solar_rad: float = 400.0,
    rain: float = 0.0,
    power: float = 500.0,
    valid: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """センサーデータ辞書を生成

    get_sense_data() の戻り値形式に合わせた辞書を生成する。

    Args:
        temp: 温度
        humi: 湿度
        lux: 照度
        solar_rad: 日射量
        rain: 降雨量
        power: 電力
        valid: データが有効かどうか

    Returns:
        センサーデータ辞書
    """
    now = datetime.datetime.now(datetime.UTC)

    def make_entry(name: str, value: float) -> dict[str, Any]:
        return {
            "name": name,
            "time": now if valid else None,
            "value": value if valid else None,
        }

    return {
        "temp": [
            make_entry("屋外の気温", temp),
            make_entry("リビング", temp + 2),
            make_entry("書斎", temp + 1),
            make_entry("和室", temp + 0.5),
            make_entry("洋室A", temp + 1.5),
            make_entry("洋室B", temp + 1),
        ],
        "humi": [make_entry("屋外の湿度", humi)],
        "lux": [make_entry("屋外の照度", lux)],
        "solar_rad": [make_entry("太陽の日射量", solar_rad)],
        "rain": [make_entry("降雨量", rain)],
        "power": [make_entry("エアコン", power)],
    }


class FetchDataMock:
    """fetch_data モッククラス

    InfluxDB の fetch_data をモックするためのクラス。
    フィールドごとに異なるデータを返すことができる。
    """

    def __init__(self, field_mappings: dict[str, SensorDataResult] | None = None):
        """初期化

        Args:
            field_mappings: フィールド名から SensorDataResult へのマッピング
        """
        self.field_mappings = field_mappings or {}
        self.call_count: dict[str, int] = {}

    def __call__(
        self,
        db_config: Any,
        measure: str,
        hostname: str,
        field: str,
        start: str = "-30h",
        stop: str = "now()",
        every_min: int = 1,
        window_min: int = 3,
        create_empty: bool = True,
        last: bool = False,
    ) -> SensorDataResult:
        """fetch_data の代替実装"""
        self.call_count[field] = self.call_count.get(field, 0) + 1

        if field in self.field_mappings:
            return self.field_mappings[field]

        # デフォルト値を返す
        return SensorDataFactory.create()

    def set_field_data(self, field: str, data: SensorDataResult) -> None:
        """フィールドのデータを設定"""
        self.field_mappings[field] = data

    def get_call_count(self, field: str) -> int:
        """フィールドの呼び出し回数を取得"""
        return self.call_count.get(field, 0)
