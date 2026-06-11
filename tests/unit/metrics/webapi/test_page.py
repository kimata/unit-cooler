#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.metrics.webapi.page のテスト

このテストは Config dataclass を使用してエンドポイントが正しく動作することを確認します。
config.get() のような dict スタイルのアクセスが残っている場合、このテストで検出されます。
"""

from __future__ import annotations

import datetime
import zoneinfo
from pathlib import Path

import flask
import pytest

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")


def create_app(config) -> flask.Flask:
    """メトリクス blueprint を登録した Flask アプリを作成"""
    import unit_cooler.metrics.webapi.page as page

    app = flask.Flask(__name__)
    app.register_blueprint(page.blueprint, url_prefix="/unit-cooler")
    app.config["CONFIG"] = config
    return app


@pytest.fixture
def real_collector(tmp_path):
    """実 SQLite にデータを書き込んだ MetricsCollector"""
    from unit_cooler.metrics.collector import MetricsCollector

    current = {"now": datetime.datetime(2024, 6, 15, 12, 0, 0, tzinfo=TIMEZONE)}
    collector = MetricsCollector(tmp_path / "metrics.db", time_func=lambda: current["now"])

    for i in range(5):
        collector.update_cooling_mode(2)
        collector.update_duty_ratio(30.0, 60.0)
        collector.update_environmental_data(
            temperature=30.0 + i, humidity=60.0, lux=1000.0, solar_radiation=500.0, rain_amount=0.0
        )
        current["now"] += datetime.timedelta(minutes=1)

    collector.record_valve_operation()
    collector.close()
    yield collector


@pytest.fixture
def app_with_real_collector(mocker, real_collector):
    """実データ入り collector を使用する Flask アプリ"""
    mock_config = mocker.MagicMock()
    mock_config.actuator.metrics.data = str(real_collector.db_path)

    mocker.patch(
        "unit_cooler.metrics.collector.get_metrics_collector",
        return_value=real_collector,
    )
    return create_app(mock_config)


class TestMetricsView:
    """metrics_view エンドポイントのテスト"""

    def test_returns_html_response_with_data(self, app_with_real_collector):
        """データがある場合に HTML レスポンスを返す"""
        with app_with_real_collector.test_client() as client:
            response = client.get("/unit-cooler/api/metrics")

            assert response.status_code == 200
            assert response.content_type == "text/html; charset=utf-8"

            html = response.get_data(as_text=True)
            assert "メトリクス ダッシュボード" in html
            assert "2024年06月15日" in html
            # チャート用 canvas が存在する
            for canvas_id in [
                "coolingModeHourlyChart",
                "dutyRatioHourlyChart",
                "valveOpsHourlyChart",
                "coolingDutyTimeseriesChart",
                "environmentTimeseriesChart",
                "tempCoolingCorrelationChart",
                "humidityDutyCorrelationChart",
                "solarCoolingCorrelationChart",
                "luxDutyCorrelationChart",
            ]:
                assert canvas_id in html
            # JS にデータ取得先 URL が渡される
            assert 'data-api-url="/unit-cooler/api/metrics/data"' in html

    def test_returns_503_when_db_not_found(self, mocker):
        """データベースが存在しない場合に 503 を返す"""
        mock_config = mocker.MagicMock()
        mock_config.actuator.metrics.data = "/nonexistent/path/to/db"
        app = create_app(mock_config)

        with app.test_client() as client:
            response = client.get("/unit-cooler/api/metrics")

            assert response.status_code == 503
            assert "データベースが見つかりません" in response.get_data(as_text=True)

    def test_config_dataclass_access(self, config):
        """Config dataclass のアクセス方法が正しいことを確認

        このテストは config.get() ではなく config.actuator.metrics.data で
        アクセスできることを確認します。
        """
        # Config は dataclass なので .get() メソッドを持たない
        assert not hasattr(config, "get")

        # 正しいアクセス方法
        assert hasattr(config, "actuator")
        assert hasattr(config.actuator, "metrics")
        assert hasattr(config.actuator.metrics, "data")

        # data は pathlib.Path
        assert isinstance(config.actuator.metrics.data, Path)

    def test_endpoint_with_real_config_catches_dict_access(self, config):
        """実際の Config dataclass を使用してエンドポイントをテスト

        このテストは config.get() のような dict スタイルのアクセスが残っている場合に
        AttributeError を発生させて検出します。
        """
        app = create_app(config)

        with app.test_client() as client:
            response = client.get("/unit-cooler/api/metrics")

            # 503 (DBなし) または 200 (正常) のいずれかであるべき
            # 500 エラーの場合は config アクセスに問題がある
            assert response.status_code in (200, 503), (
                f"Expected 200 or 503, got {response.status_code}. "
                f"Response: {response.get_data(as_text=True)[:200]}"
            )


class TestMetricsData:
    """metrics_data エンドポイントのテスト"""

    def test_returns_json_with_chart_keys(self, app_with_real_collector):
        """全チャートキーを含む JSON を返す"""
        with app_with_real_collector.test_client() as client:
            response = client.get("/unit-cooler/api/metrics/data")

            assert response.status_code == 200
            assert response.content_type == "application/json"

            data = response.get_json()
            for key in [
                "boxplot_cooling_mode",
                "boxplot_duty_ratio",
                "boxplot_valve_ops",
                "timeseries",
                "correlation",
            ]:
                assert key in data

            # 箱ヒゲ図は 24 時間分
            assert len(data["boxplot_cooling_mode"]) == 24
            # 12 時台に書き込んだデータが反映されている
            assert data["boxplot_cooling_mode"][12]["y"]["median"] == 2
            assert data["boxplot_duty_ratio"][12]["y"]["median"] == 50.0

            # 散布図ペアは x, y が同じ長さ
            for key in ["temp_cooling", "humidity_duty", "solar_cooling", "lux_duty"]:
                pair = data["correlation"][key]
                assert len(pair["x"]) == len(pair["y"])

            # 時系列は昇順（古い順）
            assert data["timeseries"][0]["timestamp"] == "06/15 12:00"

    def test_returns_503_when_db_not_found(self, mocker):
        """データベースが存在しない場合に 503 の JSON を返す"""
        mock_config = mocker.MagicMock()
        mock_config.actuator.metrics.data = "/nonexistent/path/to/db"
        app = create_app(mock_config)

        with app.test_client() as client:
            response = client.get("/unit-cooler/api/metrics/data")

            assert response.status_code == 503
            assert "error" in response.get_json()


class TestFavicon:
    """favicon エンドポイントのテスト"""

    def test_returns_ico_response(self, config):
        """ICO レスポンスを返す"""
        app = create_app(config)

        with app.test_client() as client:
            response = client.get("/unit-cooler/favicon.ico")

            assert response.status_code == 200
            assert response.content_type == "image/x-icon"
            assert len(response.get_data()) > 0


class TestStatic:
    """静的ファイル配信のテスト"""

    def test_serves_css_and_js(self, config):
        """CSS と JS が配信される"""
        app = create_app(config)

        with app.test_client() as client:
            assert client.get("/unit-cooler/metrics/static/metrics.css").status_code == 200
            assert client.get("/unit-cooler/metrics/static/metrics.js").status_code == 200
