#!/usr/bin/env python3
"""
室外機冷却システムの WebUI サーバーを提供します。

Usage:
  web_server.py [-c CONFIG] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -p PORT           : Web サーバーを動作させるポートを指定します。[default: 5000]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flask
import flask_cors
import my_lib.webapp.base
import my_lib.webapp.config
import my_lib.webapp.event
import my_lib.webapp.log
import my_lib.webapp.util
import werkzeug.serving

import unit_cooler.actuator.webapi.flow_status
import unit_cooler.actuator.webapi.valve_status
import unit_cooler.metrics.webapi.page
from unit_cooler.metrics import get_metrics_collector

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config


@dataclass
class WebServerHandle:
    """Web サーバーのハンドル"""

    server: werkzeug.serving.BaseWSGIServer
    thread: threading.Thread


def create_app(config: Config, event_queue: Queue[Any]) -> flask.Flask:
    my_lib.webapp.config.URL_PREFIX = "/unit-cooler"
    my_lib.webapp.config.init(config.actuator.web_server.webapp.to_webapp_config(config.base_dir))

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flask.Flask("unit-cooler-web")

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["CONFIG_FILE_NORMAL"] = "config.yaml"  # メトリクス用設定

    app.json.compat = True  # type: ignore[attr-defined]

    app.register_blueprint(my_lib.webapp.log.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.event.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(
        unit_cooler.actuator.webapi.valve_status.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX
    )
    app.register_blueprint(
        unit_cooler.actuator.webapi.flow_status.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX
    )
    app.register_blueprint(
        unit_cooler.metrics.webapi.page.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX
    )

    my_lib.webapp.config.show_handler_list(app, True)

    my_lib.webapp.log.init(config.actuator.web_server.webapp.to_webapp_config(config.base_dir))  # type: ignore[arg-type]
    my_lib.webapp.event.start(event_queue)

    # メトリクスデータベースの初期化
    metrics_db_path = config.actuator.metrics.data
    try:
        metrics_collector = get_metrics_collector(metrics_db_path)
        logger.info("Metrics database initialized at: %s", metrics_db_path)
        app.config["METRICS_COLLECTOR"] = metrics_collector
    except Exception:
        logger.exception("Failed to initialize metrics database")

    return app


def start(config: Config, event_queue: Queue[Any], port: int) -> WebServerHandle:
    # NOTE: Flask は別のプロセスで実行
    try:
        app = create_app(config, event_queue)
        logger.info("Web app created successfully")
    except Exception:
        logger.exception("Failed to create web app")
        raise

    server = werkzeug.serving.make_server(
        "0.0.0.0",  # noqa: S104
        port,
        app,
        threaded=True,
    )
    thread = threading.Thread(target=server.serve_forever)

    logger.info("Start web server")

    thread.start()

    return WebServerHandle(server=server, thread=thread)


def term(handle: WebServerHandle) -> None:
    import my_lib.webapp.event

    logging.warning("Stop web server")

    my_lib.webapp.event.term()

    handle.server.shutdown()
    handle.server.server_close()
    handle.thread.join()

    my_lib.webapp.log.term()


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.logger

    from unit_cooler.config import Config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    port = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)
    event_queue: multiprocessing.Queue = multiprocessing.Queue()

    log_server_handle = start(config, event_queue, port)
