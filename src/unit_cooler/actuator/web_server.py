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
import werkzeug.serving


def create_app(config, event_queue):
    import my_lib.webapp.config

    my_lib.webapp.config.URL_PREFIX = "/unit_cooler"
    my_lib.webapp.config.init(config["actuator"]["web_server"])

    import my_lib.webapp.base
    import my_lib.webapp.event
    import my_lib.webapp.log
    import my_lib.webapp.util

    import unit_cooler.actuator.webapi.flow_status
    import unit_cooler.actuator.webapi.metrics
    import unit_cooler.actuator.webapi.valve_status
    import unit_cooler.metrics.webapi.page

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flask.Flask("unit-cooler-web")

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["CONFIG_FILE_NORMAL"] = "config.yaml"  # メトリクス用設定

    app.json.compat = True

    app.register_blueprint(my_lib.webapp.log.blueprint)
    app.register_blueprint(my_lib.webapp.event.blueprint)
    app.register_blueprint(my_lib.webapp.util.blueprint)
    app.register_blueprint(unit_cooler.actuator.webapi.valve_status.blueprint)
    app.register_blueprint(unit_cooler.actuator.webapi.flow_status.blueprint)
    app.register_blueprint(unit_cooler.actuator.webapi.metrics.blueprint)
    app.register_blueprint(unit_cooler.metrics.webapi.page.blueprint)

    my_lib.webapp.config.show_handler_list(app)

    my_lib.webapp.log.init(config)
    my_lib.webapp.event.start(event_queue)

    # メトリクスデータベースの初期化
    with app.app_context():
        import unit_cooler.actuator.webapi.metrics

        unit_cooler.actuator.webapi.metrics.init_metrics_db()

    # app.debug = True

    return app


def start(config, event_queue, port):
    # NOTE: Flask は別のプロセスで実行
    server = werkzeug.serving.make_server(
        "0.0.0.0",  # noqa: S104
        port,
        create_app(config, event_queue),
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
