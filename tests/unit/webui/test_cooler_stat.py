#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.webui.webapi.cooler_stat のテスト"""

from __future__ import annotations

import multiprocessing


class TestInit:
    """init のテスト"""

    def test_sets_api_base_url(self):
        """api_base_url を設定"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        cooler_stat.init("/api/v1")

        assert cooler_stat.api_base_url == "/api/v1"


class TestWatering:
    """watering のテスト"""

    def test_calculates_amount_and_price(self, config, mocker):
        """使用量と料金を計算"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100.0)

        result = cooler_stat.watering(config, 0)

        assert "amount" in result
        assert "price" in result
        assert result["amount"] == 100.0

    def test_calculates_price_from_amount(self, config, mocker):
        """使用量から料金を計算"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=1000.0)

        result = cooler_stat.watering(config, 0)

        # price = amount * unit_price / 1000.0
        expected_price = 1000.0 * config.controller.watering.unit_price / 1000.0
        assert result["price"] == expected_price


class TestWateringList:
    """watering_list のテスト"""

    def test_returns_10_days(self, config, mocker):
        """10日分のデータを返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        result = cooler_stat.watering_list(config)

        assert len(result) == 10
        for item in result:
            assert "amount" in item
            assert "price" in item


class TestGetLastMessage:
    """get_last_message のテスト"""

    def setup_method(self):
        """各テスト前に状態をリセット"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        cooler_stat.get_last_message.last_message = None  # pyright: ignore[reportFunctionMemberAccess]

    def test_returns_none_when_empty(self):
        """空キューで None"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        queue = multiprocessing.Queue()

        result = cooler_stat.get_last_message(queue)

        assert result is None

    def test_returns_last_message_from_queue(self):
        """キューから最後のメッセージを取得"""
        import time

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        queue = multiprocessing.Queue()
        queue.put({"mode_index": 1})
        queue.put({"mode_index": 2})
        queue.put({"mode_index": 3})
        # キューにデータが入るのを待つ
        time.sleep(0.01)

        result = cooler_stat.get_last_message(queue)

        assert result == {"mode_index": 3}

    def test_stores_last_message(self):
        """最後のメッセージを保存"""
        import time

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        queue = multiprocessing.Queue()
        queue.put({"mode_index": 5})
        # キューにデータが入るのを待つ
        time.sleep(0.01)

        cooler_stat.get_last_message(queue)

        assert cooler_stat.get_last_message.last_message == {"mode_index": 5}  # pyright: ignore[reportFunctionMemberAccess]

    def test_returns_cached_message_when_queue_empty(self):
        """キュー空時にキャッシュを返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        queue = multiprocessing.Queue()
        cooler_stat.get_last_message.last_message = {"mode_index": 10}  # pyright: ignore[reportFunctionMemberAccess]

        result = cooler_stat.get_last_message(queue)

        assert result == {"mode_index": 10}


class TestGetStats:
    """get_stats のテスト"""

    def test_returns_stats_dict(self, config, mocker):
        """統計辞書を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        queue = multiprocessing.Queue()
        # ZMQ メッセージをシミュレート
        cooler_stat.get_last_message.last_message = {  # pyright: ignore[reportFunctionMemberAccess]
            "mode_index": 3,
            "sense_data": {"outdoor": {"temp": 30}},
            "cooler_status": {"status": 1, "message": None},
            "outdoor_status": {"status": 0, "message": None},
        }

        result = cooler_stat.get_stats(config, queue)

        assert "watering" in result
        assert "sensor" in result
        assert "mode" in result
        assert "cooler_status" in result
        assert "outdoor_status" in result
        assert "actuator_status" in result

    def test_returns_empty_data_when_no_message(self, config, mocker):
        """ZMQ メッセージがない場合は空データを返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        queue = multiprocessing.Queue()
        cooler_stat.get_last_message.last_message = None  # pyright: ignore[reportFunctionMemberAccess]

        result = cooler_stat.get_stats(config, queue)

        assert result["sensor"] == {}
        assert result["mode"] is None
        assert result["cooler_status"] is None
        assert result["outdoor_status"] is None

    def test_includes_actuator_status_when_available(self, config, mocker):
        """ActuatorStatus が利用可能時に含める"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat
        from unit_cooler.const import VALVE_STATE
        from unit_cooler.messages import ActuatorStatus, ValveStatus

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        valve_status = ValveStatus(
            state=VALVE_STATE.OPEN,
            duration_sec=10.5,
        )
        actuator_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=1.5,
            cooling_mode_index=3,
            hazard_detected=False,
        )
        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status",
            return_value=actuator_status,
        )

        queue = multiprocessing.Queue()
        cooler_stat.get_last_message.last_message = {  # pyright: ignore[reportFunctionMemberAccess]
            "mode_index": 3,
            "sense_data": {},
            "cooler_status": {"status": 0, "message": None},
            "outdoor_status": {"status": 0, "message": None},
        }

        result = cooler_stat.get_stats(config, queue)

        assert result["actuator_status"] is not None
        assert result["actuator_status"]["valve"]["state"] == VALVE_STATE.OPEN.value


class TestApiGetStats:
    """api_get_stats のテスト"""

    def test_returns_json_response(self, config, mocker):
        """JSON レスポンスを返す"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)
        cooler_stat.get_last_message.last_message = {  # pyright: ignore[reportFunctionMemberAccess]
            "mode_index": 3,
            "sense_data": {},
            "cooler_status": {"status": 0, "message": None},
            "outdoor_status": {"status": 0, "message": None},
        }

        with app.test_client() as client:
            response = client.get("/api/stat")

            assert response.status_code == 200
            data = response.get_json()
            assert "watering" in data

    def test_returns_error_on_exception(self, config, mocker):
        """例外時にエラーを返す"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue

        # watering_list で例外を発生させる
        mocker.patch(
            "unit_cooler.webui.webapi.cooler_stat.watering_list",
            side_effect=Exception("test error"),
        )

        with app.test_client() as client:
            response = client.get("/api/stat")

            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data
