#!/usr/bin/env python3
"""
電磁弁を可変デューティ制御します。

Usage:
  valve.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。

Note:
  このモジュールの関数は後方互換性のために維持されています。
  新しいコードでは ValveController クラスを直接使用してください。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import unit_cooler.const
from unit_cooler.actuator.valve_controller import ValveController

if TYPE_CHECKING:
    from unit_cooler.config import Config

# グローバル ValveController インスタンス（後方互換性のため）
_controller: ValveController | None = None


def init(pin: int, valve_config: Config) -> None:
    """バルブを初期化（後方互換性のためのラッパー）"""
    global _controller

    _controller = ValveController(config=valve_config, pin_no=pin)


def clear_stat() -> None:
    """テスト用: 状態をクリア（後方互換性のためのラッパー）"""
    if _controller is not None:
        _controller.clear_stat()


def get_hist() -> list[unit_cooler.const.VALVE_STATE]:
    """テスト用: 操作履歴を取得（後方互換性のためのラッパー）"""
    if _controller is not None:
        return _controller.get_hist()
    return []


def set_state(valve_state: unit_cooler.const.VALVE_STATE) -> dict[str, Any]:
    """バルブ状態を設定（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    status = _controller.set_state(valve_state)
    return {"state": status.state, "duration": status.duration_sec}


def get_state() -> unit_cooler.const.VALVE_STATE:
    """バルブ状態を取得（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    return _controller.get_state()


def get_status() -> dict[str, Any]:
    """バルブ状態と経過時間を取得（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    return _controller.get_status_dict()


def set_cooling_working(duty_info: dict[str, Any]) -> dict[str, Any]:
    """バルブを動作状態に設定（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    status = _controller.set_cooling_working(duty_info)
    return {"state": status.state, "duration": status.duration_sec}


def set_cooling_idle() -> dict[str, Any]:
    """バルブをアイドル状態に設定（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    status = _controller.set_cooling_idle()
    return {"state": status.state, "duration": status.duration_sec}


def set_cooling_state(control_message: dict[str, Any]) -> dict[str, Any]:
    """制御メッセージに基づいてバルブ状態を設定（後方互換性のためのラッパー）"""
    if _controller is None:
        raise RuntimeError("Valve not initialized. Call init() first.")
    status = _controller.set_cooling_state(control_message)
    return {"state": status.state, "duration": status.duration_sec}


if __name__ == "__main__":
    # TEST Code
    import logging
    import multiprocessing

    import docopt
    import my_lib.logger
    import my_lib.webapp.config
    import my_lib.webapp.log

    import unit_cooler.actuator.work_log
    from unit_cooler.config import Config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)
    event_queue: multiprocessing.Queue = multiprocessing.Queue()

    my_lib.webapp.config.init(config.actuator.web_server.webapp.to_webapp_config())
    my_lib.webapp.log.init(config.actuator.web_server.webapp.to_webapp_config())  # type: ignore[arg-type]
    unit_cooler.actuator.work_log.init(config, event_queue)
    init(config.actuator.control.valve.pin_no, config)

    while True:
        set_cooling_state(
            {
                "state": unit_cooler.const.COOLING_STATE.WORKING,
                "mode_index": 1,
                "duty": {"enable": True, "on_sec": 1, "off_sec": 3},
            }
        )
        time.sleep(1)
