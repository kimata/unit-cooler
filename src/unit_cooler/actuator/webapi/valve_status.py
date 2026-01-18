#!/usr/bin/env python3
"""バルブの状態を JSON で返す API エンドポイントを提供します。"""

import flask
import my_lib.flask_util
import my_lib.webapp.config

import unit_cooler.actuator.valve_controller
import unit_cooler.const

blueprint = flask.Blueprint("valve-status", __name__)


@blueprint.route("/api/valve_status", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_valve_status():
    """バルブの状態を JSON 形式で返します。"""
    status = unit_cooler.actuator.valve_controller.get_valve_controller().get_status()

    # VALVE_STATE を JSON シリアライズ可能な形式に変換
    response = {
        "state": status.state.name,
        "state_value": status.state.value,
        "duration": status.duration_sec,
    }

    return flask.jsonify(response)
