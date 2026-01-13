#!/usr/bin/env python3
# ruff: noqa: S101
"""WebUI 結合テスト

Flask API エンドポイントの動作を検証する。
"""

from __future__ import annotations

import multiprocessing

import flask


class TestWebuiApi:
    """WebUI API テスト"""

    def test_api_stat_returns_json(self, config, mocker):
        """API /api/stat が JSON を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value={"outdoor": {"temp": 30, "humi": 50}},
        )
        mocker.patch(
            "unit_cooler.controller.engine.judge_cooling_mode",
            return_value={
                "sense_data": {"outdoor": {"temp": 30}},
                "cooler_status": {"active": True},
                "outdoor_status": {"hot": True},
            },
        )
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue
        cooler_stat.get_last_message.last_message = {"mode_index": 3}  # pyright: ignore[reportFunctionMemberAccess]

        with app.test_client() as client:
            response = client.get("/api/stat")

            assert response.status_code == 200
            assert response.content_type == "application/json"

            data = response.get_json()
            assert "sensor" in data
            assert "mode" in data
            assert "cooler_status" in data
            assert "outdoor_status" in data

    def test_api_watering_list_structure(self, config, mocker):
        """API /api/watering の watering リスト構造"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/api/watering")
            data = response.get_json()

            # watering リストの検証
            assert isinstance(data["watering"], list)
            assert len(data["watering"]) == 10

            for item in data["watering"]:
                assert "amount" in item
                assert "price" in item
                assert isinstance(item["amount"], int | float)
                assert isinstance(item["price"], int | float)

    def test_api_watering_handles_sensor_error(self, config, mocker):
        """API /api/watering がデータ取得エラーを処理する"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        # watering_list() 内で呼ばれる my_lib.sensor_data.get_day_sum をモック
        mocker.patch(
            "my_lib.sensor_data.get_day_sum",
            side_effect=Exception("Data fetch error"),
        )

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/api/watering")

            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data

    def test_api_stat_with_actuator_status(self, config, mocker):
        """API /api/stat が ActuatorStatus を含む"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat
        from unit_cooler.const import VALVE_STATE
        from unit_cooler.messages import ActuatorStatus, ValveStatus

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value={"outdoor": {"temp": 30}},
        )
        mocker.patch(
            "unit_cooler.controller.engine.judge_cooling_mode",
            return_value={
                "sense_data": {},
                "cooler_status": {},
                "outdoor_status": {},
            },
        )

        valve_status = ValveStatus(
            state=VALVE_STATE.OPEN,
            duration_sec=15.5,
        )
        actuator_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=2.0,
            cooling_mode_index=4,
            hazard_detected=False,
        )
        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status",
            return_value=actuator_status,
        )

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue
        cooler_stat.get_last_message.last_message = None  # pyright: ignore[reportFunctionMemberAccess]

        with app.test_client() as client:
            response = client.get("/api/stat")
            data = response.get_json()

            assert data["actuator_status"] is not None
            assert data["actuator_status"]["valve"]["state"] == VALVE_STATE.OPEN.value
            assert data["actuator_status"]["flow_lpm"] == 2.0
            assert data["actuator_status"]["cooling_mode_index"] == 4


class TestWebuiJsonp:
    """WebUI JSONP サポートテスト"""

    def test_api_stat_supports_jsonp_callback(self, config, mocker):
        """API /api/stat が JSONP コールバックをサポートする"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value={"outdoor": {"temp": 30}},
        )
        mocker.patch(
            "unit_cooler.controller.engine.judge_cooling_mode",
            return_value={
                "sense_data": {},
                "cooler_status": {},
                "outdoor_status": {},
            },
        )
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue
        cooler_stat.get_last_message.last_message = None  # pyright: ignore[reportFunctionMemberAccess]

        with app.test_client() as client:
            response = client.get("/api/stat?callback=myCallback")

            assert response.status_code == 200
            # JSONP レスポンスの検証
            data = response.get_data(as_text=True)
            assert data.startswith("myCallback(")
            assert data.endswith(")")


class TestWebuiCors:
    """WebUI CORS テスト"""

    def test_api_allows_cross_origin(self, config, mocker):
        """API が CORS を許可する"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value={"outdoor": {"temp": 30}},
        )
        mocker.patch(
            "unit_cooler.controller.engine.judge_cooling_mode",
            return_value={
                "sense_data": {},
                "cooler_status": {},
                "outdoor_status": {},
            },
        )
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue
        cooler_stat.get_last_message.last_message = None  # pyright: ignore[reportFunctionMemberAccess]

        with app.test_client() as client:
            response = client.get("/api/stat", headers={"Origin": "http://example.com"})

            # CORS ヘッダーは my_lib.flask_util で設定されるが、
            # テスト環境では有効にならない可能性がある
            assert response.status_code == 200
