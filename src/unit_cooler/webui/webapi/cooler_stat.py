#!/usr/bin/env python3
"""冷却システムの作業状況を WebUI に渡します。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flask
import my_lib.flask_util
import my_lib.sensor_data
import my_lib.time
import my_lib.webapp.config

import unit_cooler.const
import unit_cooler.messages
import unit_cooler.webui.worker

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import datetime

    from unit_cooler.config import Config, SensorItemConfig
    from unit_cooler.messages import ControlMessage, DutyConfig, StatusInfo

# センサー値列の背景グラフに使う種別（power は UI 非表示のため除外）
SENSOR_GRAPH_KINDS: tuple[str, ...] = ("temp", "humi", "lux", "solar_rad", "rain")

# ActuatorStatus をこの秒数より長く受信していない場合は None 扱いにする
# （Actuator 停止後に古い「バルブ OPEN」表示が残留するのを防ぐ）
ACTUATOR_STATUS_STALE_SEC = 60.0

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
class ModeInfo:
    """冷却モード情報（/api/stat の mode フィールド）"""

    state: int
    mode_index: int
    duty: DutyConfig
    night_stop: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "mode_index": self.mode_index,
            "duty": self.duty.to_dict(),
            "night_stop": self.night_stop,
        }


@dataclass(frozen=True)
class FreshnessInfo:
    """Controller / Actuator からの最終受信からの経過秒（未受信なら None）"""

    controller_sec: float | None
    actuator_sec: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "controller_sec": self.controller_sec,
            "actuator_sec": self.actuator_sec,
        }


@dataclass(frozen=True)
class CoolerStats:
    """冷却システム統計情報

    Controller 停止時も全フィールドを非 null で返すことで、フロントエンドは
    単一の Stat 型（null 分岐なし）で扱える。actuator_status のみ未受信・鮮度切れ時 None。
    """

    # NOTE: sensor / cooler_status / outdoor_status / actuator_status は
    # シリアライゼーション境界（to_dict 済みの JSON 相当データ）なので dict のまま扱う
    sensor: dict[str, Any]
    mode: ModeInfo
    cooler_status: dict[str, Any]
    outdoor_status: dict[str, Any]
    actuator_status: dict[str, Any] | None
    freshness: FreshnessInfo

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor": self.sensor,
            "mode": self.mode.to_dict(),
            "cooler_status": self.cooler_status,
            "outdoor_status": self.outdoor_status,
            "actuator_status": self.actuator_status,
            "freshness": self.freshness.to_dict(),
        }

    @classmethod
    def from_message(
        cls,
        control_message: ControlMessage,
        actuator_status: dict[str, Any] | None,
        freshness: FreshnessInfo,
    ) -> CoolerStats:
        # NOTE: mode に ControlMessage 全体を入れると sense_data / cooler_status /
        # outdoor_status が重複してペイロードに含まれるため、必要なフィールドのみ返す
        return cls(
            sensor=(
                control_message.sense_data.to_dict()
                if control_message.sense_data
                else unit_cooler.messages.SenseData().to_dict()
            ),
            mode=ModeInfo(
                state=control_message.state.value,
                mode_index=control_message.mode_index,
                duty=control_message.duty,
                night_stop=control_message.night_stop,
            ),
            cooler_status=_status_to_dict(control_message.cooler_status),
            outdoor_status=_status_to_dict(control_message.outdoor_status),
            actuator_status=actuator_status,
            freshness=freshness,
        )

    @classmethod
    def idle(cls, actuator_status: dict[str, Any] | None, freshness: FreshnessInfo) -> CoolerStats:
        """Controller 未接続時のデフォルト統計情報（全フィールド非 null）"""
        return cls(
            sensor=unit_cooler.messages.SenseData().to_dict(),
            mode=ModeInfo(
                state=unit_cooler.const.COOLING_STATE.IDLE.value,
                mode_index=0,
                duty=unit_cooler.messages.DutyConfig(enable=False, on_sec=0, off_sec=0),
                night_stop=False,
            ),
            cooler_status={"status": 0, "message": ""},
            outdoor_status={"status": 0, "message": ""},
            actuator_status=actuator_status,
            freshness=freshness,
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
    # NOTE: InfluxDB へのクエリが直列だと 10 日分で応答が遅くなるため並列化する
    # （executor.map は入力順を保持する）
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        return [info.to_dict() for info in executor.map(lambda i: watering(config, i), range(10))]


def sensor_graph(config: Config) -> dict[str, Any]:
    """各センサーの過去12時間系列を取得し、背景グラフ用に整形する。

    取得失敗・データなしの種別は省略する（フロントは存在チェックで分岐）。
    エアコン消費電力は ``power`` キーに、stat.sensor.power と同順のリストで返す
    （頻度ヒートバー用。欠損アエコンは None で詰めてインデックスを揃える）。
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

    # エアコンごとの消費電力履歴（頻度ヒートバー用）。stat.sensor.power と同順で取得する。
    requests.extend(
        my_lib.sensor_data.DataRequest(
            measure=sensor.measure,
            hostname=sensor.hostname,
            field="power",
            start=start,
            stop=stop,
            every_min=10,
            window_min=10,
            last=False,
        )
        for sensor in config.controller.sensor.power
    )

    results = asyncio.run(my_lib.sensor_data.fetch_data_parallel(config.controller.influxdb, requests))

    def to_series(result: Any, scale: float = 1.0) -> dict[str, Any] | None:
        if isinstance(result, BaseException) or not result.valid or not result.value:
            return None
        values = [v * scale for v in result.value]
        return SensorGraphSeries(
            values=values, min=min(values), max=max(values), current=values[-1]
        ).to_dict()

    graph: dict[str, Any] = {}
    n_single = len(kinds)
    for kind, result in zip(kinds, results[:n_single], strict=True):
        # NOTE: rain の観測値は1分間の降水量なので、1時間雨量に換算（sensor.py と同様）
        series = to_series(result, scale=60.0 if kind == "rain" else 1.0)
        if series is not None:
            graph[kind] = series

    power_series = [to_series(result) for result in results[n_single:]]
    if any(series is not None for series in power_series):
        graph["power"] = power_series

    return graph


# モジュールレベル変数（関数属性パターンの代替）
# _last_message_time は ControlMessage の最終受信時刻（鮮度表示用）
_last_message: ControlMessage | None = None
_last_message_time: datetime.datetime | None = None
_last_message_lock = threading.Lock()


def get_last_message(message_queue: queue.Queue[ControlMessage]) -> ControlMessage | None:
    # NOTE: 現在の実際の制御モードを取得する。
    # empty() でチェックしてから get() すると、並行リクエストが間にキューを空にした場合に
    # get() がブロックし得る（TOCTOU）。get_nowait() + queue.Empty 捕捉でブロックを避ける。
    global _last_message, _last_message_time
    with _last_message_lock:
        while True:
            try:
                _last_message = message_queue.get_nowait()
                _last_message_time = my_lib.time.now()
            except queue.Empty:
                break
        return _last_message


def _get_freshness() -> FreshnessInfo:
    """Controller / Actuator からの最終受信からの経過秒を取得する"""
    now = my_lib.time.now()

    with _last_message_lock:
        last_message_time = _last_message_time
    controller_sec = (now - last_message_time).total_seconds() if last_message_time else None

    actuator_time = unit_cooler.webui.worker.get_last_actuator_status_time()
    actuator_sec = (now - actuator_time).total_seconds() if actuator_time else None

    return FreshnessInfo(controller_sec=controller_sec, actuator_sec=actuator_sec)


def get_stats(message_queue: queue.Queue[ControlMessage]) -> CoolerStats:
    # ZMQ 経由で Controller から受信したメッセージを使用
    control_message = get_last_message(message_queue)

    freshness = _get_freshness()

    # ActuatorStatus を取得（ZeroMQ 経由で受信した最新のステータス）
    # 鮮度切れ（Actuator 停止等）の場合は None にして古い表示の残留を防ぐ
    actuator_status = unit_cooler.webui.worker.get_last_actuator_status()
    is_stale = freshness.actuator_sec is None or freshness.actuator_sec > ACTUATOR_STATUS_STALE_SEC
    actuator_status_dict = actuator_status.to_dict() if actuator_status and not is_stale else None

    if control_message is None:
        return CoolerStats.idle(actuator_status_dict, freshness)

    return CoolerStats.from_message(control_message, actuator_status_dict, freshness)


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
