#!/usr/bin/env python3
"""冷却システムの作業状況を WebUI に渡します。"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flask
import my_lib.flask_util
import my_lib.sensor_data
import my_lib.webapp.config

import unit_cooler.const
import unit_cooler.messages
import unit_cooler.webui.worker

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config, SensorItemConfig
    from unit_cooler.messages import ControlMessage, StatusInfo

# センサー値列の背景グラフに使う種別（power は UI 非表示のため除外）
SENSOR_GRAPH_KINDS: tuple[str, ...] = ("temp", "humi", "lux", "solar_rad", "rain")

blueprint = flask.Blueprint("cooler-stat", __name__)


@dataclass(frozen=True)
class WateringInfo:
    """散水情報"""

    amount: float
    price: float

    def to_dict(self) -> dict[str, float]:
        return {"amount": self.amount, "price": self.price}


@dataclass(frozen=True)
class SensorGraphSeries:
    """センサー値の過去系列（背景スパークライン用）"""

    values: list[float]  # 古い→新しい順
    min: float
    max: float
    current: float | None  # 系列末尾（最新値）

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "min": self.min,
            "max": self.max,
            "current": self.current,
        }


def _status_to_dict(status: StatusInfo | None) -> dict[str, Any]:
    """StatusInfo を非 null の dict に正規化する（message の None は空文字に揃える）"""
    if status is None:
        return {"status": 0, "message": ""}
    return {"status": status.status, "message": status.message or ""}


@dataclass(frozen=True)
class CoolerStats:
    """冷却システム統計情報

    Controller 停止時も全フィールドを非 null で返すことで、フロントエンドは
    単一の Stat 型（null 分岐なし）で扱える。actuator_status のみ未受信時 None。
    """

    sensor: dict[str, Any]
    mode: dict[str, Any]
    cooler_status: dict[str, Any]
    outdoor_status: dict[str, Any]
    actuator_status: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor": self.sensor,
            "mode": self.mode,
            "cooler_status": self.cooler_status,
            "outdoor_status": self.outdoor_status,
            "actuator_status": self.actuator_status,
        }

    @classmethod
    def from_message(
        cls, control_message: ControlMessage, actuator_status: dict[str, Any] | None
    ) -> CoolerStats:
        # NOTE: mode に ControlMessage 全体を入れると sense_data / cooler_status /
        # outdoor_status が重複してペイロードに含まれるため、必要なフィールドのみ返す
        return cls(
            sensor=(
                control_message.sense_data.to_dict()
                if control_message.sense_data
                else unit_cooler.messages.SenseData().to_dict()
            ),
            mode={
                "state": control_message.state.value,
                "mode_index": control_message.mode_index,
                "duty": control_message.duty.to_dict(),
            },
            cooler_status=_status_to_dict(control_message.cooler_status),
            outdoor_status=_status_to_dict(control_message.outdoor_status),
            actuator_status=actuator_status,
        )

    @classmethod
    def idle(cls, actuator_status: dict[str, Any] | None) -> CoolerStats:
        """Controller 未接続時のデフォルト統計情報（全フィールド非 null）"""
        return cls(
            sensor=unit_cooler.messages.SenseData().to_dict(),
            mode={
                "state": unit_cooler.const.COOLING_STATE.IDLE.value,
                "mode_index": 0,
                "duty": {"enable": False, "on_sec": 0, "off_sec": 0},
            },
            cooler_status={"status": 0, "message": ""},
            outdoor_status={"status": 0, "message": ""},
            actuator_status=actuator_status,
        )


def watering(config: Config, day_before: int) -> WateringInfo:
    day_offset = 7 if os.environ.get("DUMMY_MODE", "false") == "true" else 0

    amount = my_lib.sensor_data.get_day_sum(
        config.controller.influxdb,
        config.controller.watering.measure,
        config.controller.watering.hostname,
        "flow",
        1,
        day_before,
        day_offset,
    )

    return WateringInfo(
        amount=amount,
        price=amount * config.controller.watering.unit_price / 1000.0,
    )


def watering_list(config: Config) -> list[dict[str, float]]:
    return [watering(config, i).to_dict() for i in range(10)]


def sensor_graph(config: Config) -> dict[str, dict[str, Any]]:
    """各センサーの過去12時間系列を取得し、背景グラフ用に整形する。

    取得失敗・データなしの種別は省略する（フロントは存在チェックで分岐）。
    """
    if os.environ.get("DUMMY_MODE", "false") == "true":
        # NOTE: get_sense_data と同様、DUMMY 時は1週間前の12時間窓を参照する
        start = "-180h"
        stop = "-168h"
    else:
        start = "-12h"
        stop = "now()"

    sensor_map: dict[str, list[SensorItemConfig]] = {
        "temp": config.controller.sensor.temp,
        "humi": config.controller.sensor.humi,
        "lux": config.controller.sensor.lux,
        "solar_rad": config.controller.sensor.solar_rad,
        "rain": config.controller.sensor.rain,
    }

    requests: list[my_lib.sensor_data.DataRequest] = []
    kinds: list[str] = []
    for kind in SENSOR_GRAPH_KINDS:
        sensors = sensor_map[kind]
        if not sensors:
            continue
        sensor = sensors[0]
        requests.append(
            my_lib.sensor_data.DataRequest(
                measure=sensor.measure,
                hostname=sensor.hostname,
                field=kind,
                start=start,
                stop=stop,
                every_min=10,  # 12時間 ≒ 72 点に間引く（背景スパークラインには十分）
                window_min=10,
                last=False,
            )
        )
        kinds.append(kind)

    results = asyncio.run(my_lib.sensor_data.fetch_data_parallel(config.controller.influxdb, requests))

    graph: dict[str, dict[str, Any]] = {}
    for kind, result in zip(kinds, results, strict=True):
        if isinstance(result, BaseException) or not result.valid or not result.value:
            continue
        values = list(result.value)
        if kind == "rain":
            # NOTE: 観測値は1分間の降水量なので、1時間雨量に換算（sensor.py と同様）
            values = [v * 60 for v in values]
        graph[kind] = SensorGraphSeries(
            values=values,
            min=min(values),
            max=max(values),
            current=values[-1],
        ).to_dict()

    return graph


# モジュールレベル変数（関数属性パターンの代替）
_last_message: ControlMessage | None = None


def get_last_message(message_queue: Queue[ControlMessage]) -> ControlMessage | None:
    # NOTE: 現在の実際の制御モードを取得する。
    # empty() でチェックしてから get() すると、並行リクエストが間にキューを空にした場合に
    # get() がブロックし得る（TOCTOU）。get_nowait() + queue.Empty 捕捉でブロックを避ける。
    global _last_message
    while True:
        try:
            _last_message = message_queue.get_nowait()
        except queue.Empty:
            break
    return _last_message


def get_stats(message_queue: Queue[ControlMessage]) -> CoolerStats:
    # ZMQ 経由で Controller から受信したメッセージを使用
    control_message = get_last_message(message_queue)

    # ActuatorStatus を取得（ZeroMQ 経由で受信した最新のステータス）
    actuator_status = unit_cooler.webui.worker.get_last_actuator_status()
    actuator_status_dict = actuator_status.to_dict() if actuator_status else None

    if control_message is None:
        return CoolerStats.idle(actuator_status_dict)

    return CoolerStats.from_message(control_message, actuator_status_dict)


@blueprint.route("/api/stat", methods=["GET"])
@my_lib.flask_util.support_jsonp
def api_get_stats():
    try:
        message_queue = flask.current_app.config["MESSAGE_QUEUE"]

        return flask.jsonify(get_stats(message_queue).to_dict())
    except Exception as e:
        logger.exception("Error in api_get_stats")
        return flask.jsonify({"error": str(e)}), 500


@blueprint.route("/api/watering", methods=["GET"])
@my_lib.flask_util.support_jsonp
def api_get_watering():
    try:
        config = flask.current_app.config["CONFIG"]

        return flask.jsonify({"watering": watering_list(config)})
    except Exception as e:
        logger.exception("Error in api_get_watering")
        return flask.jsonify({"error": str(e)}), 500


@blueprint.route("/api/sensor_graph", methods=["GET"])
@my_lib.flask_util.support_jsonp
def api_get_sensor_graph():
    try:
        config = flask.current_app.config["CONFIG"]

        return flask.jsonify(sensor_graph(config))
    except Exception as e:
        logger.exception("Error in api_get_sensor_graph")
        return flask.jsonify({"error": str(e)}), 500
