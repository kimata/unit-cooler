#!/usr/bin/env python3
"""稼働期間（散水を行う季節）の取得・設定 API を提供します。"""

import flask
import my_lib.flask_util
import my_lib.time

import unit_cooler.actuator.season
import unit_cooler.actuator.work_log

blueprint = flask.Blueprint("season", __name__)


def _status_response(setting: unit_cooler.actuator.season.SeasonSetting) -> flask.Response:
    return flask.jsonify(
        {
            **setting.to_dict(),
            "in_season": setting.contains(my_lib.time.now().date()),
        }
    )


def _format_month_day(month_day: unit_cooler.actuator.season.MonthDay) -> str:
    return f"{month_day.month}月{month_day.day}日"


@blueprint.route("/api/season", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_season():
    """稼働期間の設定を JSON 形式で返します。"""
    config = flask.current_app.config["CONFIG"]

    return _status_response(unit_cooler.actuator.season.get_setting(config))


@blueprint.route("/api/season", methods=["POST"])
def set_season():
    """稼働期間を設定します。

    JSON ボディ: {"enabled": bool, "start": {"month": M, "day": D}, "end": {"month": M, "day": D}}
    """
    config = flask.current_app.config["CONFIG"]

    try:
        setting = unit_cooler.actuator.season.SeasonSetting.parse(flask.request.get_json(silent=True) or {})
    except (ValueError, KeyError, TypeError) as e:
        return flask.jsonify({"error": f"invalid season setting: {e}"}), 400

    unit_cooler.actuator.season.set_setting(config, setting)

    if setting.enabled:
        unit_cooler.actuator.work_log.add(
            "稼働期間を設定しました。"
            f"（{_format_month_day(setting.start)}〜{_format_month_day(setting.end)}）"
        )
    else:
        unit_cooler.actuator.work_log.add("稼働期間の限定を解除しました。（通年稼働）")

    return _status_response(setting)
