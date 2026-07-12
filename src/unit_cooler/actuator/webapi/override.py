#!/usr/bin/env python3
"""手動オーバーライド（強制 OFF n 分）の状態取得・設定・解除 API を提供します。"""

import flask
import my_lib.flask_util

import unit_cooler.actuator.override
import unit_cooler.actuator.work_log

blueprint = flask.Blueprint("override", __name__)


def _status_response(state: unit_cooler.actuator.override.OverrideState | None) -> flask.Response:
    return flask.jsonify(
        {
            "enabled": state is not None,
            "until": state.until.isoformat() if state is not None else None,
        }
    )


@blueprint.route("/api/override", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_override():
    """手動オーバーライドの状態を JSON 形式で返します。"""
    config = flask.current_app.config["CONFIG"]

    return _status_response(unit_cooler.actuator.override.get_override(config))


@blueprint.route("/api/override", methods=["POST"])
def set_override():
    """手動オーバーライドを設定します（JSON ボディ: {"duration_min": N}）。"""
    config = flask.current_app.config["CONFIG"]

    data = flask.request.get_json(silent=True) or {}
    duration_min = data.get("duration_min")

    # NOTE: bool は int のサブクラスなので明示的に除外する
    if (
        not isinstance(duration_min, int)
        or isinstance(duration_min, bool)
        or not (
            unit_cooler.actuator.override.DURATION_MIN_LOWER
            <= duration_min
            <= unit_cooler.actuator.override.DURATION_MIN_UPPER
        )
    ):
        return flask.jsonify(
            {
                "error": (
                    "duration_min must be an integer between "
                    f"{unit_cooler.actuator.override.DURATION_MIN_LOWER} and "
                    f"{unit_cooler.actuator.override.DURATION_MIN_UPPER}"
                )
            }
        ), 400

    state = unit_cooler.actuator.override.set_override(config, duration_min)
    unit_cooler.actuator.work_log.add(f"手動で散水を強制停止しました。（{duration_min}分間）")

    return _status_response(state)


@blueprint.route("/api/override/clear", methods=["POST"])
def clear_override():
    """手動オーバーライドを解除します。"""
    config = flask.current_app.config["CONFIG"]

    unit_cooler.actuator.override.clear_override(config)
    unit_cooler.actuator.work_log.add("手動の強制停止を解除しました。")

    return _status_response(None)
