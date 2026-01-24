#!/usr/bin/env python3
# ruff: noqa: S101
"""API スキーマ整合性テスト

フロントエンド（TypeScript）の型定義とバックエンド（Python）の
API レスポンスの整合性を検証する。

フロントエンド型定義: frontend/src/lib/ApiResponse.ts
"""

from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from typing import Any

import flask

import unit_cooler.const
from unit_cooler.messages import ActuatorStatus, ControlMessage, DutyConfig, StatusInfo, ValveStatus

# =============================================================================
# フロントエンド型定義に対応する検証スキーマ
# =============================================================================


@dataclass(frozen=True)
class SchemaField:
    """スキーマフィールド定義"""

    name: str
    expected_type: type | tuple[type, ...]
    nullable: bool = False
    nested_validator: Any = None


def validate_schema(data: dict[str, Any], fields: list[SchemaField], path: str = "") -> list[str]:
    """スキーマに対してデータを検証し、エラーリストを返す"""
    errors: list[str] = []

    for field in fields:
        field_path = f"{path}.{field.name}" if path else field.name

        # フィールドの存在確認
        if field.name not in data:
            errors.append(f"Missing field: {field_path}")
            continue

        value = data[field.name]

        # null 許容チェック
        if value is None:
            if not field.nullable:
                errors.append(f"Unexpected null value: {field_path}")
            continue

        # 型チェック
        if not isinstance(value, field.expected_type):
            errors.append(
                f"Type mismatch at {field_path}: expected {field.expected_type}, got {type(value).__name__}"
            )
            continue

        # ネストされたバリデーション
        if field.nested_validator and isinstance(value, dict):
            nested_errors = field.nested_validator(value, field_path)
            errors.extend(nested_errors)
        elif field.nested_validator and isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    nested_errors = field.nested_validator(item, f"{field_path}[{i}]")
                    errors.extend(nested_errors)

    return errors


# =============================================================================
# フロントエンド TypeScript 型定義に対応するバリデータ
# =============================================================================


def validate_sensor_data(data: dict[str, Any], path: str = "") -> list[str]:
    """SensorData インターフェースの検証

    interface SensorData {
        name: string;
        time: string;
        value: number;
    }
    """
    fields = [
        SchemaField("name", str),
        SchemaField("time", str),
        SchemaField("value", (int, float)),
    ]
    return validate_schema(data, fields, path)


def validate_sensor_array(data: list[Any], path: str = "") -> list[str]:
    """SensorData[] の検証"""
    errors: list[str] = []

    for i, item in enumerate(data):
        if isinstance(item, dict):
            errors.extend(validate_sensor_data(item, f"{path}[{i}]"))
        else:
            errors.append(f"Expected object at {path}[{i}], got {type(item).__name__}")
    return errors


def validate_duty(data: dict[str, Any], path: str = "") -> list[str]:
    """Mode.duty インターフェースの検証

    duty: {
        enable: boolean;
        off_sec: number;
        on_sec: number;
    }
    """
    fields = [
        SchemaField("enable", bool),
        SchemaField("off_sec", int),
        SchemaField("on_sec", int),
    ]
    return validate_schema(data, fields, path)


def validate_mode(data: dict[str, Any], path: str = "") -> list[str]:
    """Mode インターフェースの検証

    interface Mode {
        duty: { enable: boolean; off_sec: number; on_sec: number; };
        mode_index: number;
        state: number;
    }
    """
    errors: list[str] = []
    fields = [
        SchemaField("duty", dict, nested_validator=validate_duty),
        SchemaField("mode_index", int),
        SchemaField("state", int),
    ]
    errors.extend(validate_schema(data, fields, path))
    return errors


def validate_cooler_status(data: dict[str, Any], path: str = "") -> list[str]:
    """CoolerStatus / OutdoorStatus インターフェースの検証

    interface CoolerStatus {
        message: string;
        status: number;
    }
    """
    fields = [
        SchemaField("message", str, nullable=True),
        SchemaField("status", int),
    ]
    return validate_schema(data, fields, path)


def validate_valve_status_nested(data: dict[str, Any], path: str = "") -> list[str]:
    """ActuatorStatus.valve の検証（内部用）

    バックエンドは state を int (0/1) で返す
    """
    fields = [
        SchemaField("state", int),
        SchemaField("duration", (int, float)),
    ]
    return validate_schema(data, fields, path)


def validate_actuator_status(data: dict[str, Any], path: str = "") -> list[str]:
    """ActuatorStatus の検証"""
    fields = [
        SchemaField("timestamp", str),
        SchemaField("valve", dict, nested_validator=validate_valve_status_nested),
        SchemaField("flow_lpm", (int, float), nullable=True),
        SchemaField("cooling_mode_index", int),
        SchemaField("hazard_detected", bool),
    ]
    return validate_schema(data, fields, path)


def validate_sensor_object(data: dict[str, Any], path: str = "") -> list[str]:
    """sensor オブジェクトの検証

    sensor: {
        temp: SensorData[];
        humi: SensorData[];
        lux: SensorData[];
        rain: SensorData[];
        solar_rad: SensorData[];
        power: SensorData[];
    }
    """
    errors: list[str] = []
    expected_keys = ["temp", "humi", "lux", "rain", "solar_rad", "power"]

    for key in expected_keys:
        if key in data:
            value = data[key]
            if isinstance(value, list):
                errors.extend(validate_sensor_array(value, f"{path}.{key}"))
            elif value is not None:
                errors.append(f"Expected array or null at {path}.{key}, got {type(value).__name__}")
        # キーが存在しない場合もOK（空のセンサーデータ）

    return errors


def validate_stat_response(data: dict[str, Any]) -> list[str]:
    """Stat インターフェースの検証

    interface Stat {
        cooler_status: CoolerStatus;
        outdoor_status: OutdoorStatus;
        mode: Mode;
        sensor: { ... };
    }
    """
    errors: list[str] = []

    # cooler_status と outdoor_status は null 許容
    if "cooler_status" in data and data["cooler_status"] is not None:
        errors.extend(validate_cooler_status(data["cooler_status"], "cooler_status"))

    if "outdoor_status" in data and data["outdoor_status"] is not None:
        errors.extend(validate_cooler_status(data["outdoor_status"], "outdoor_status"))

    # mode も null 許容（Controller 未接続時）
    if "mode" in data and data["mode"] is not None:
        errors.extend(validate_mode(data["mode"], "mode"))

    # sensor は空オブジェクトの場合がある
    if data.get("sensor"):
        errors.extend(validate_sensor_object(data["sensor"], "sensor"))

    # actuator_status は null 許容
    if "actuator_status" in data and data["actuator_status"] is not None:
        errors.extend(validate_actuator_status(data["actuator_status"], "actuator_status"))

    return errors


def validate_watering(data: dict[str, Any], path: str = "") -> list[str]:
    """Watering インターフェースの検証

    interface Watering {
        amount: number;
        price: number;
    }
    """
    fields = [
        SchemaField("amount", (int, float)),
        SchemaField("price", (int, float)),
    ]
    return validate_schema(data, fields, path)


def validate_watering_response(data: dict[str, Any]) -> list[str]:
    """WateringResponse インターフェースの検証

    interface WateringResponse {
        watering: Watering[];
    }
    """
    errors: list[str] = []

    if "watering" not in data:
        errors.append("Missing field: watering")
        return errors

    watering_list = data["watering"]
    if not isinstance(watering_list, list):
        errors.append(f"Expected array at watering, got {type(watering_list).__name__}")
        return errors

    for i, item in enumerate(watering_list):
        if isinstance(item, dict):
            errors.extend(validate_watering(item, f"watering[{i}]"))
        else:
            errors.append(f"Expected object at watering[{i}], got {type(item).__name__}")

    return errors


def validate_valve_status_response(data: dict[str, Any]) -> list[str]:
    """ValveStatus インターフェースの検証

    interface ValveStatus {
        state: "OPEN" | "CLOSE";
        state_value: 0 | 1;
        duration: number;
    }
    """
    errors: list[str] = []

    # state フィールド（文字列 "OPEN" | "CLOSE"）
    if "state" not in data:
        errors.append("Missing field: state")
    elif data["state"] not in ("OPEN", "CLOSE"):
        errors.append(f"Invalid state value: {data['state']}, expected 'OPEN' or 'CLOSE'")

    # state_value フィールド（数値 0 | 1）
    if "state_value" not in data:
        errors.append("Missing field: state_value")
    elif data["state_value"] not in (0, 1):
        errors.append(f"Invalid state_value: {data['state_value']}, expected 0 or 1")

    # duration フィールド
    if "duration" not in data:
        errors.append("Missing field: duration")
    elif not isinstance(data["duration"], int | float):
        errors.append(f"Type mismatch at duration: expected number, got {type(data['duration']).__name__}")

    return errors


def validate_flow_status_response(data: dict[str, Any]) -> list[str]:
    """FlowStatus インターフェースの検証

    interface FlowStatus {
        flow: number;
    }
    """
    errors: list[str] = []

    if "flow" not in data:
        errors.append("Missing field: flow")
    elif not isinstance(data["flow"], int | float):
        errors.append(f"Type mismatch at flow: expected number, got {type(data['flow']).__name__}")

    return errors


# =============================================================================
# テストクラス
# =============================================================================


class TestApiStatSchema:
    """API /api/stat のスキーマ整合性テスト"""

    def test_stat_response_matches_frontend_schema(self, config, mocker):
        """API /api/stat のレスポンスがフロントエンド型定義に準拠する"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        # センサーデータをフロントエンドが期待する形式でモック
        sense_data = {
            "temp": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 30.5}],
            "humi": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 50.0}],
            "lux": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 10000}],
            "rain": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 0}],
            "solar_rad": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 500}],
            "power": [{"name": "outdoor_unit", "time": "2024-01-01T12:00:00", "value": 1500}],
        }

        control_message = ControlMessage(
            state=unit_cooler.const.COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=60, off_sec=30),
            mode_index=3,
            sense_data=sense_data,
            cooler_status=StatusInfo(status=1, message="冷却中"),
            outdoor_status=StatusInfo(status=1, message="稼働中"),
        )

        valve_status = ValveStatus(
            state=unit_cooler.const.VALVE_STATE.OPEN,
            duration_sec=15.5,
        )
        actuator_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=2.5,
            cooling_mode_index=3,
            hazard_detected=False,
        )

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=actuator_status)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue: multiprocessing.Queue[ControlMessage] = multiprocessing.Queue()
        queue.put(control_message)

        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue

        with app.test_client() as client:
            response = client.get("/api/stat")
            assert response.status_code == 200

            data = response.get_json()
            errors = validate_stat_response(data)

            assert errors == [], f"Schema validation errors: {errors}"

    def test_stat_response_with_null_values(self, config, mocker):
        """API /api/stat のレスポンスが null 値を正しく返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=None)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue: multiprocessing.Queue[ControlMessage] = multiprocessing.Queue()
        # キューは空（Controller 未接続状態）

        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue

        with app.test_client() as client:
            response = client.get("/api/stat")
            assert response.status_code == 200

            data = response.get_json()

            # null 許容フィールドが正しく null を返すことを確認
            assert data["mode"] is None
            assert data["cooler_status"] is None
            assert data["outdoor_status"] is None
            assert data["actuator_status"] is None
            assert data["sensor"] == {}

    def test_stat_response_actuator_status_valve_format(self, config, mocker):
        """API /api/stat の actuator_status.valve が正しい形式を返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        valve_status = ValveStatus(
            state=unit_cooler.const.VALVE_STATE.CLOSE,
            duration_sec=0.0,
        )
        actuator_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=None,
            cooling_mode_index=0,
            hazard_detected=True,
        )

        mocker.patch("unit_cooler.webui.worker.get_last_actuator_status", return_value=actuator_status)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        queue: multiprocessing.Queue[ControlMessage] = multiprocessing.Queue()
        app.config["CONFIG"] = config
        app.config["MESSAGE_QUEUE"] = queue

        with app.test_client() as client:
            response = client.get("/api/stat")
            data = response.get_json()

            # valve の state は int (0 or 1) であることを確認
            valve_data = data["actuator_status"]["valve"]
            assert valve_data["state"] == unit_cooler.const.VALVE_STATE.CLOSE.value
            assert isinstance(valve_data["state"], int)
            assert valve_data["duration"] == 0.0


class TestApiWateringSchema:
    """API /api/watering のスキーマ整合性テスト"""

    def test_watering_response_matches_frontend_schema(self, config, mocker):
        """API /api/watering のレスポンスがフロントエンド型定義に準拠する"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/api/watering")
            assert response.status_code == 200

            data = response.get_json()
            errors = validate_watering_response(data)

            assert errors == [], f"Schema validation errors: {errors}"

    def test_watering_response_has_10_days(self, config, mocker):
        """API /api/watering が 10 日分のデータを返す"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=50.0)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/api/watering")
            data = response.get_json()

            assert len(data["watering"]) == 10

    def test_watering_item_has_correct_types(self, config, mocker):
        """API /api/watering の各アイテムが正しい型を持つ"""
        import unit_cooler.webui.webapi.cooler_stat as cooler_stat

        mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100.0)

        app = flask.Flask(__name__)
        app.register_blueprint(cooler_stat.blueprint)

        app.config["CONFIG"] = config

        with app.test_client() as client:
            response = client.get("/api/watering")
            data = response.get_json()

            for item in data["watering"]:
                assert isinstance(item["amount"], int | float)
                assert isinstance(item["price"], int | float)
                # price は amount から計算されるので、非負であるべき
                assert item["amount"] >= 0
                assert item["price"] >= 0


class TestApiValveStatusSchema:
    """API /api/valve_status のスキーマ整合性テスト"""

    def test_valve_status_response_matches_frontend_schema(self, mocker):
        """API /api/valve_status のレスポンスがフロントエンド型定義に準拠する"""
        import unit_cooler.actuator.webapi.valve_status as valve_status_api

        valve_status = ValveStatus(
            state=unit_cooler.const.VALVE_STATE.OPEN,
            duration_sec=30.5,
        )

        mock_controller = mocker.Mock()
        mock_controller.get_status.return_value = valve_status
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller",
            return_value=mock_controller,
        )

        app = flask.Flask(__name__)
        app.register_blueprint(valve_status_api.blueprint)

        with app.test_client() as client:
            response = client.get("/api/valve_status")
            assert response.status_code == 200

            data = response.get_json()
            errors = validate_valve_status_response(data)

            assert errors == [], f"Schema validation errors: {errors}"

    def test_valve_status_state_is_string(self, mocker):
        """API /api/valve_status の state が文字列 ('OPEN' | 'CLOSE') である"""
        import unit_cooler.actuator.webapi.valve_status as valve_status_api

        for valve_state in [unit_cooler.const.VALVE_STATE.OPEN, unit_cooler.const.VALVE_STATE.CLOSE]:
            valve_status = ValveStatus(
                state=valve_state,
                duration_sec=0.0,
            )

            mock_controller = mocker.Mock()
            mock_controller.get_status.return_value = valve_status
            mocker.patch(
                "unit_cooler.actuator.valve_controller.get_valve_controller",
                return_value=mock_controller,
            )

            app = flask.Flask(__name__)
            app.register_blueprint(valve_status_api.blueprint)

            with app.test_client() as client:
                response = client.get("/api/valve_status")
                data = response.get_json()

                # state は文字列
                assert data["state"] == valve_state.name
                assert data["state"] in ("OPEN", "CLOSE")

                # state_value は数値
                assert data["state_value"] == valve_state.value
                assert data["state_value"] in (0, 1)


class TestMessageSchemaConsistency:
    """messages.py の dataclass と API レスポンスの整合性テスト"""

    def test_control_message_to_dict_matches_mode_schema(self):
        """ControlMessage.to_dict() が Mode スキーマに準拠する"""
        control_message = ControlMessage(
            state=unit_cooler.const.COOLING_STATE.WORKING,
            duty=DutyConfig(enable=True, on_sec=60, off_sec=30),
            mode_index=5,
            sense_data={},
            cooler_status=StatusInfo(status=1, message="テスト"),
            outdoor_status=StatusInfo(status=0, message=None),
        )

        mode_dict = control_message.to_dict()
        errors = validate_mode(mode_dict)

        assert errors == [], f"Schema validation errors: {errors}"

    def test_actuator_status_to_dict_matches_schema(self):
        """ActuatorStatus.to_dict() がスキーマに準拠する"""
        valve_status = ValveStatus(
            state=unit_cooler.const.VALVE_STATE.OPEN,
            duration_sec=100.0,
        )
        actuator_status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve_status,
            flow_lpm=3.5,
            cooling_mode_index=2,
            hazard_detected=False,
        )

        status_dict = actuator_status.to_dict()
        errors = validate_actuator_status(status_dict)

        assert errors == [], f"Schema validation errors: {errors}"

    def test_status_info_to_dict_matches_schema(self):
        """StatusInfo.to_dict() が CoolerStatus/OutdoorStatus スキーマに準拠する"""
        status_info = StatusInfo(status=1, message="テストメッセージ")
        status_dict = status_info.to_dict()
        errors = validate_cooler_status(status_dict)

        assert errors == [], f"Schema validation errors: {errors}"

    def test_status_info_null_message(self):
        """StatusInfo の message が null の場合もスキーマに準拠する"""
        status_info = StatusInfo(status=0, message=None)
        status_dict = status_info.to_dict()
        errors = validate_cooler_status(status_dict)

        assert errors == [], f"Schema validation errors: {errors}"


class TestSensorDataFormat:
    """センサーデータ形式の整合性テスト"""

    def test_sensor_data_array_format(self):
        """センサーデータが配列形式であること"""
        # フロントエンドが期待する形式
        sensor_data = {
            "temp": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 30.5}],
            "humi": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 50.0}],
        }

        errors = validate_sensor_object(sensor_data, "sensor")
        assert errors == [], f"Schema validation errors: {errors}"

    def test_sensor_data_empty_arrays(self):
        """センサーデータの空配列が許容されること"""
        sensor_data = {
            "temp": [],
            "humi": [],
            "lux": [],
            "rain": [],
            "solar_rad": [],
            "power": [],
        }

        errors = validate_sensor_object(sensor_data, "sensor")
        assert errors == [], f"Schema validation errors: {errors}"

    def test_sensor_data_partial_keys(self):
        """センサーデータが一部のキーのみでも許容されること"""
        sensor_data = {
            "temp": [{"name": "outdoor", "time": "2024-01-01T12:00:00", "value": 30.5}],
        }

        errors = validate_sensor_object(sensor_data, "sensor")
        assert errors == [], f"Schema validation errors: {errors}"
