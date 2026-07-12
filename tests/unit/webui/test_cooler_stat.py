#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.webui.webapi.cooler_stat のテスト"""

from __future__ import annotations

import datetime
import queue

import my_lib.time

from unit_cooler.const import COOLING_STATE
from unit_cooler.messages import ControlMessage, DutyConfig, SenseData, SensorReading, StatusInfo


def _reset_last_message():
    import unit_cooler.webui.webapi.cooler_stat as cooler_stat

    cooler_stat._last_message = None
    cooler_stat._last_message_time = None


class TestWatering:
    """watering のテスト"""

    def test_calculates_amount_and_price(self, config, mocker):
        """使用量と料金を計算"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100.0)

        result = cooler_stat.watering(config, 0)

        assert hasattr(result, "amount")
        assert hasattr(result, "price")
        assert result.amount == 100.0

    def test_calculates_price_from_amount(self, config, mocker):
        """使用量から料金を計算"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=1000.0)

        result = cooler_stat.watering(config, 0)

        # price = amount * unit_price / 1000.0
        expected_price = 1000.0 * config.controller.watering.unit_price / 1000.0
        assert result.price == expected_price

    def test_to_dict_returns_correct_structure(self, config, mocker):
        """to_dict() が正しい構造を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100.0)

        result = cooler_stat.watering(config, 0)
        result_dict = result.to_dict()

        assert "amount" in result_dict
        assert "price" in result_dict
        assert result_dict["amount"] == result.amount
        assert result_dict["price"] == result.price


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
        _reset_last_message()

    def test_returns_none_when_empty(self):
        """空キューで None"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        message_queue: queue.Queue[ControlMessage] = queue.Queue()

        result = cooler_stat.get_last_message(message_queue)

        assert result is None
        assert cooler_stat._last_message_time is None

    def test_returns_last_message_from_queue(self):
        """キューから最後のメッセージを取得"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        for i in range(1, 4):
            msg = ControlMessage(
                mode_index=i,
                state=COOLING_STATE.IDLE,
                duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
            )
            message_queue.put(msg)

        result = cooler_stat.get_last_message(message_queue)

        assert result is not None
        assert result.mode_index == 3

    def test_stores_last_message(self):
        """最後のメッセージと受信時刻を保存"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        msg = ControlMessage(
            mode_index=5,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        message_queue.put(msg)

        cooler_stat.get_last_message(message_queue)

        assert cooler_stat._last_message == msg
        # 受信時刻も記録される（freshness 用）
        assert cooler_stat._last_message_time is not None

    def test_returns_cached_message_when_queue_empty(self):
        """キュー空時にキャッシュを返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        cached_msg = ControlMessage(
            mode_index=10,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
        )
        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        cooler_stat._last_message = cached_msg

        result = cooler_stat.get_last_message(message_queue)

        assert result == cached_msg


def _make_actuator_status():
    from unit_cooler.const import VALVE_STATE
    from unit_cooler.messages import ActuatorStatus, ValveStatus

    return ActuatorStatus(
        timestamp="2024-01-01T12:00:00",
        valve=ValveStatus(state=VALVE_STATE.OPEN, duration_sec=10.5),
        flow_lpm=1.5,
        cooling_mode_index=3,
        hazard_detected=False,
    )


class TestGetStats:
    """get_stats のテスト"""

    def setup_method(self):
        """各テスト前に状態をリセット"""
        _reset_last_message()

    def test_returns_cooler_stats(self, mocker):
        """CoolerStats を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status_time", return_value=None)

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        # ZMQ メッセージをシミュレート
        cooler_stat._last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
            sense_data=SenseData(temp=[SensorReading(name="temp", value=30.0)]),
            cooler_status=StatusInfo(status=1, message=None),
            outdoor_status=StatusInfo(status=0, message=None),
        )

        result = cooler_stat.get_stats(message_queue)

        assert hasattr(result, "sensor")
        assert hasattr(result, "mode")
        assert hasattr(result, "cooler_status")
        assert hasattr(result, "outdoor_status")
        assert hasattr(result, "actuator_status")
        assert hasattr(result, "freshness")

    def test_returns_idle_defaults_when_no_message(self, mocker):
        """ZMQ メッセージがない場合は全フィールド非 null のデフォルト値を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status_time", return_value=None)

        message_queue: queue.Queue[ControlMessage] = queue.Queue()

        result = cooler_stat.get_stats(message_queue)

        # フロントエンドが単一の Stat 型で扱えるよう、null ではなくデフォルト値を返す
        assert result.sensor == SenseData().to_dict()
        assert result.mode.to_dict() == {
            "state": COOLING_STATE.IDLE.value,
            "mode_index": 0,
            "duty": {"enable": False, "on_sec": 0, "off_sec": 0},
            "night_stop": False,
        }
        assert result.cooler_status == {"status": 0, "message": ""}
        assert result.outdoor_status == {"status": 0, "message": ""}
        # 未受信なので freshness は両方 null
        assert result.freshness.controller_sec is None
        assert result.freshness.actuator_sec is None

    def test_includes_actuator_status_when_available(self, mocker):
        """ActuatorStatus が利用可能（かつ新鮮）時に含める"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat
        from unit_cooler.const import VALVE_STATE

        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status",
            return_value=_make_actuator_status(),
        )
        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status_time",
            return_value=my_lib.time.now(),
        )

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        cooler_stat._last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
            sense_data={},
            cooler_status=StatusInfo(status=0, message=None),
            outdoor_status=StatusInfo(status=0, message=None),
        )

        result = cooler_stat.get_stats(message_queue)

        assert result.actuator_status is not None
        assert result.actuator_status["valve"]["state"] == VALVE_STATE.OPEN.value
        assert result.freshness.actuator_sec is not None
        assert result.freshness.actuator_sec < 10

    def test_nullifies_actuator_status_when_stale(self, mocker):
        """鮮度切れの ActuatorStatus は None にする（古い表示の残留防止）"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        stale_time = my_lib.time.now() - datetime.timedelta(
            seconds=cooler_stat.ACTUATOR_STATUS_STALE_SEC + 60
        )
        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status",
            return_value=_make_actuator_status(),
        )
        mocker.patch(
            "unit_cooler.webui.worker.get_last_actuator_status_time",
            return_value=stale_time,
        )

        message_queue: queue.Queue[ControlMessage] = queue.Queue()

        result = cooler_stat.get_stats(message_queue)

        assert result.actuator_status is None
        # 経過秒自体は freshness で報告される
        assert result.freshness.actuator_sec is not None
        assert result.freshness.actuator_sec > cooler_stat.ACTUATOR_STATUS_STALE_SEC

    def test_includes_night_stop_in_mode(self, mocker):
        """night_stop が mode に含まれる"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status_time", return_value=None)

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        message_queue.put(
            ControlMessage(
                mode_index=0,
                state=COOLING_STATE.IDLE,
                duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
                night_stop=True,
            )
        )

        result = cooler_stat.get_stats(message_queue)

        assert result.mode.night_stop is True
        assert result.mode.to_dict()["night_stop"] is True
        # メッセージ受信により controller の freshness が更新される
        assert result.freshness.controller_sec is not None
        assert result.freshness.controller_sec < 10


class TestApiGetStats:
    """api_get_stats のテスト"""

    def setup_method(self):
        """各テスト前に状態をリセット"""
        _reset_last_message()

    def test_returns_json_response(self, config, mocker):
        """JSON レスポンスを返す（freshness / mode.night_stop 含む）"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = message_queue

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)
        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status_time", return_value=None)
        cooler_stat._last_message = ControlMessage(
            mode_index=3,
            state=COOLING_STATE.IDLE,
            duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
            sense_data={},
            cooler_status=StatusInfo(status=0, message=None),
            outdoor_status=StatusInfo(status=0, message=None),
        )

        with app.test_client() as client:
            response = client.get("/api/stat")

            assert response.status_code == 200
            data = response.get_json()
            assert "sensor" in data
            assert "mode" in data
            assert data["mode"]["night_stop"] is False
            # freshness は契約フィールド（フロントエンドと合意済み）
            assert data["freshness"] == {"controller_sec": None, "actuator_sec": None}

    def test_returns_error_on_exception(self, config, mocker):
        """例外時にエラーを返す"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        message_queue: queue.Queue[ControlMessage] = queue.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = message_queue

        # get_stats で例外を発生させる
        mocker.patch(
            "unit_cooler.webui.webapi.cooler_stat.get_stats",
            side_effect=Exception("test error"),
        )

        with app.test_client() as client:
            response = client.get("/api/stat")

            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data


class TestApiGetWatering:
    """api_get_watering のテスト"""

    def test_returns_json_response(self, config, mocker):
        """JSON レスポンスを返す"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        with app.test_client() as client:
            response = client.get("/api/watering")

            assert response.status_code == 200
            data = response.get_json()
            assert "watering" in data
            assert len(data["watering"]) == 10

    def test_returns_error_on_exception(self, config, mocker):
        """例外時にエラーを返す"""
        import flask

        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        # watering_list で例外を発生させる
        mocker.patch(
            "unit_cooler.webui.webapi.cooler_stat.watering_list",
            side_effect=Exception("test error"),
        )

        with app.test_client() as client:
            response = client.get("/api/watering")

            assert response.status_code == 500
            data = response.get_json()
            assert "error" in data
