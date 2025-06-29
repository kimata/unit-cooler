#!/usr/bin/env python3
"""流量の状態を JSON で返す API エンドポイントを提供します。"""

import flask
import my_lib.flask_util
import my_lib.webapp.config

import unit_cooler.actuator.monitor

blueprint = flask.Blueprint("flow-status", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)


@blueprint.route("/api/get_flow", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_flow():
    """最後に測定された流量を JSON 形式で返します。"""
    flow = unit_cooler.actuator.monitor.get_mist_condition.last_flow

    response = {
        "flow": flow,
    }

    return flask.jsonify(response)
