#!/usr/bin/env python3
"""
冷却システムを作業状況を WebUI に渡します。

Usage:
  cooler_stat.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import logging
import os

import flask
import my_lib.flask_util
import my_lib.sensor_data
import my_lib.webapp.config

import unit_cooler.controller.engine
import unit_cooler.controller.sensor

blueprint = flask.Blueprint("cooler-stat", __name__)

api_base_url = None


def init(api_base_url_):
    global api_base_url  # noqa: PLW0603

    api_base_url = api_base_url_


def watering(config, day_before):
    day_offset = 7 if os.environ.get("DUMMY_MODE", "false") == "true" else 0

    amount = my_lib.sensor_data.get_day_sum(
        config["controller"]["influxdb"],
        config["controller"]["watering"]["measure"],
        config["controller"]["watering"]["hostname"],
        "flow",
        1,
        day_before,
        day_offset,
    )

    return {
        "amount": amount,
        "price": amount * config["controller"]["watering"]["unit_price"] / 1000.0,
    }


def watering_list(config):
    return [watering(config, i) for i in range(10)]


def get_last_message(message_queue):
    # NOTE: 現在の実際の制御モードを取得する。
    while not message_queue.empty():
        get_last_message.last_message = message_queue.get()
    return get_last_message.last_message


get_last_message.last_message = None


def get_stats(config, message_queue):
    # NOTE: データを受け渡すのは面倒なので、直接計算してしまう
    sense_data = unit_cooler.controller.sensor.get_sense_data(config)
    mode = unit_cooler.controller.engine.judge_cooling_mode(config, sense_data)

    return {
        "watering": watering_list(config),
        "sensor": mode["sense_data"],
        "mode": get_last_message(message_queue),
        "cooler_status": mode["cooler_status"],
        "outdoor_status": mode["outdoor_status"],
    }


@blueprint.route("/api/stat", methods=["GET"])
@my_lib.flask_util.support_jsonp
def api_get_stats():
    try:
        config = flask.current_app.config["CONFIG"]
        message_queue = flask.current_app.config["MESSAGE_QUEUE"]

        return flask.jsonify(get_stats(config, message_queue))
    except Exception as e:
        logging.exception("Error in api_get_stats")
        return flask.jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    logging.info(my_lib.pretty.format(watering_list(config)))
