#!/usr/bin/env python3
"""
冷却システムを作業状況を WebUI に渡します。

Usage:
  cooler_stat.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flask
import my_lib.flask_util
import my_lib.sensor_data
import my_lib.webapp.config

import unit_cooler.webui.worker
from unit_cooler.messages import ControlMessage

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

blueprint = flask.Blueprint("cooler-stat", __name__)


@dataclass(frozen=True)
class WateringInfo:
    """散水情報"""

    amount: float
    price: float

    def to_dict(self) -> dict[str, float]:
        return {"amount": self.amount, "price": self.price}


@dataclass(frozen=True)
class CoolerStats:
    """冷却システム統計情報"""

    sensor: dict[str, Any]
    mode: dict[str, Any] | None
    cooler_status: dict[str, Any] | None
    outdoor_status: dict[str, Any] | None
    actuator_status: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor": self.sensor,
            "mode": self.mode,
            "cooler_status": self.cooler_status,
            "outdoor_status": self.outdoor_status,
            "actuator_status": self.actuator_status,
        }


def watering(config: Config, day_before: int) -> WateringInfo:
    day_offset = 7 if os.environ.get("DUMMY_MODE", "false") == "true" else 0

    amount = my_lib.sensor_data.get_day_sum(
        config.controller.influxdb.to_dict(),  # type: ignore[arg-type]
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


# モジュールレベル変数（関数属性パターンの代替）
_last_message: ControlMessage | None = None


def get_last_message(message_queue: Queue[ControlMessage]) -> ControlMessage | None:
    # NOTE: 現在の実際の制御モードを取得する。
    global _last_message
    while not message_queue.empty():
        _last_message = message_queue.get()
    return _last_message


def get_stats(message_queue: Queue[ControlMessage]) -> CoolerStats:
    # ZMQ 経由で Controller から受信したメッセージを使用
    control_message = get_last_message(message_queue)

    # ActuatorStatus を取得（ZeroMQ 経由で受信した最新のステータス）
    actuator_status = unit_cooler.webui.worker.get_last_actuator_status()
    actuator_status_dict = actuator_status.to_dict() if actuator_status else None

    if control_message is None:
        return CoolerStats(
            sensor={},
            mode=None,
            cooler_status=None,
            outdoor_status=None,
            actuator_status=actuator_status_dict,
        )

    return CoolerStats(
        sensor=control_message.sense_data,
        mode=control_message.to_dict(),
        cooler_status=control_message.cooler_status.to_dict() if control_message.cooler_status else None,
        outdoor_status=control_message.outdoor_status.to_dict() if control_message.outdoor_status else None,
        actuator_status=actuator_status_dict,
    )


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


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    logging.info(my_lib.pretty.format(watering_list(config)))  # type: ignore[arg-type]
