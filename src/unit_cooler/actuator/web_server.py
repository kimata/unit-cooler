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

import logging
import threading

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


def create_app(config, event_queue):
    my_lib.webapp.config.URL_PREFIX = "/unit_cooler"
    my_lib.webapp.config.init(config["actuator"]["web_server"])

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flask.Flask("unit-cooler-web")

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["CONFIG_FILE_NORMAL"] = "config.yaml"  # メトリクス用設定

    app.json.compat = True

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

    my_lib.webapp.log.init(config)
    my_lib.webapp.event.start(event_queue)

    # メトリクスデータベースの初期化
    if "metrics" in config["actuator"] and "data" in config["actuator"]["metrics"]:
        metrics_db_path = config["actuator"]["metrics"]["data"]
        try:
            metrics_collector = get_metrics_collector(metrics_db_path)
            logging.info("Metrics database initialized at: %s", metrics_db_path)
            app.config["METRICS_COLLECTOR"] = metrics_collector
        except Exception:
            logging.exception("Failed to initialize metrics database")

    # app.debug = True

    return app


def start(config, event_queue, port):
    # NOTE: Flask は別のプロセスで実行
    try:
        app = create_app(config, event_queue)
        logging.info("Web app created successfully")
    except Exception:
        logging.exception("Failed to create web app")
        raise

    server = werkzeug.serving.make_server(
        "0.0.0.0",  # noqa: S104
        port,
        app,
        threaded=True,
    )
    thread = threading.Thread(target=server.serve_forever)

    logging.info("Start web server")

    thread.start()

    return {
        "server": server,
        "thread": thread,
    }


def term(handle):
    import my_lib.webapp.event

    logging.warning("Stop web server")

    my_lib.webapp.event.term()

    handle["server"].shutdown()
    handle["server"].server_close()
    handle["thread"].join()

    my_lib.webapp.log.term()


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    port = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)
    event_queue = multiprocessing.Queue()

    log_server_handle = start(config, event_queue, port)
