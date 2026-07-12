#!/usr/bin/env python3
"""ハザード（水漏れ等の永続ラッチ）の状態取得・手動解除 API を提供します。"""

import datetime

import flask
import my_lib.flask_util
import my_lib.footprint
import my_lib.time

import unit_cooler.actuator.control
import unit_cooler.actuator.work_log

blueprint = flask.Blueprint("hazard", __name__)


@blueprint.route("/api/hazard", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_hazard():
    """ハザードの状態を JSON 形式で返します。"""
    config = flask.current_app.config["CONFIG"]
    hazard_file = config.actuator.control.hazard.file

    registered_at = None
    hazard = my_lib.footprint.exists(hazard_file)
    if hazard:
        try:
            registered_at = datetime.datetime.fromtimestamp(
                my_lib.footprint.mtime(hazard_file), tz=my_lib.time.get_zoneinfo()
            ).isoformat()
        except (ValueError, OSError):
            # ファイルが破損している場合は登録時刻不明として扱う
            registered_at = None

    return flask.jsonify({"hazard": hazard, "registered_at": registered_at})


@blueprint.route("/api/hazard/clear", methods=["POST"])
def clear_hazard():
    """ハザードのラッチを手動でクリアします。"""
    config = flask.current_app.config["CONFIG"]

    unit_cooler.actuator.control.hazard_clear(config)
    unit_cooler.actuator.work_log.add("ハザードを手動で解除しました。")

    return flask.jsonify({"hazard": False})
