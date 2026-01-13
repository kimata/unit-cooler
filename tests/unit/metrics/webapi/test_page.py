#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.metrics.webapi.page のテスト

このテストは Config dataclass を使用してエンドポイントが正しく動作することを確認します。
config.get() のような dict スタイルのアクセスが残っている場合、このテストで検出されます。
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path


class TestMetricsView:
    """metrics_view エンドポイントのテスト"""

    def test_returns_html_response_with_data(self, config, mocker):
        """データがある場合に HTML レスポンスを返す"""
        import flask
        import my_lib.webapp.config

        import unit_cooler.metrics.webapi.page as page

        # URL_PREFIX を設定
        my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

        app = flask.Flask(__name__)
        app.register_blueprint(page.blueprint, url_prefix="/unit-cooler")

        # データベースファイルを一時的に作成
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        # config をモック（frozen dataclass なので新しいモックを作成）
        mock_config = mocker.MagicMock()
        mock_config.actuator.metrics.data = str(tmp_path)
        app.config["CONFIG"] = mock_config

        # メトリクスコレクターをモック
        mock_collector = mocker.MagicMock()
        mock_collector.get_minute_data.return_value = [
            {
                "timestamp": datetime.datetime.now(),
                "cooling_mode": 1,
                "duty_ratio": 0.5,
                "temperature": 30.0,
                "humidity": 60.0,
                "lux": 1000.0,
                "solar_radiation": 500.0,
                "rain_amount": 0.0,
            }
        ]
        mock_collector.get_hourly_data.return_value = [
            {
                "timestamp": datetime.datetime.now(),
                "valve_operations": 10,
            }
        ]
        mock_collector.get_error_data.return_value = []

        mocker.patch(
            "unit_cooler.metrics.webapi.page.get_metrics_collector",
            return_value=mock_collector,
        )

        with app.test_client() as client:
            response = client.get("/unit-cooler/api/metrics")

            # ステータスコードが 200 であることを確認
            # これが失敗する場合、config.get() のような dict アクセスが残っている可能性がある
            assert response.status_code == 200
            assert response.content_type == "text/html; charset=utf-8"

        # クリーンアップ
        tmp_path.unlink(missing_ok=True)

    def test_returns_503_when_db_not_found(self, config, mocker):
        """データベースが存在しない場合に 503 を返す"""
        import flask
        import my_lib.webapp.config

        import unit_cooler.metrics.webapi.page as page

        my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

        app = flask.Flask(__name__)
        app.register_blueprint(page.blueprint, url_prefix="/unit-cooler")

        # config をモック（frozen dataclass なので新しいモックを作成）
        mock_config = mocker.MagicMock()
        mock_config.actuator.metrics.data = "/nonexistent/path/to/db"
        app.config["CONFIG"] = mock_config

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

        # data は文字列パス
        assert isinstance(config.actuator.metrics.data, str)

    def test_endpoint_with_real_config_catches_dict_access(self, config, mocker):
        """実際の Config dataclass を使用してエンドポイントをテスト

        このテストは config.get() のような dict スタイルのアクセスが残っている場合に
        AttributeError を発生させて検出します。

        これは今回のバグ（config.get() を使用していた）を検出するための回帰テストです。
        """
        import flask
        import my_lib.webapp.config

        import unit_cooler.metrics.webapi.page as page

        my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

        app = flask.Flask(__name__)
        app.register_blueprint(page.blueprint, url_prefix="/unit-cooler")
        # 実際の Config dataclass を使用
        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/unit-cooler/api/metrics")

            # 503 (DBなし) または 200 (正常) のいずれかであるべき
            # 500 エラーの場合は config アクセスに問題がある
            assert response.status_code in (200, 503), (
                f"Expected 200 or 503, got {response.status_code}. "
                f"Response: {response.get_data(as_text=True)[:200]}"
            )


class TestFavicon:
    """favicon エンドポイントのテスト"""

    def test_returns_ico_response(self, config, mocker):
        """ICO レスポンスを返す"""
        import flask
        import my_lib.webapp.config

        import unit_cooler.metrics.webapi.page as page

        my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

        app = flask.Flask(__name__)
        app.register_blueprint(page.blueprint, url_prefix="/unit-cooler")
        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/unit-cooler/favicon.ico")

            assert response.status_code == 200
            assert response.content_type == "image/x-icon"
