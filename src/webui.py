#!/usr/bin/env python3
"""
エアコン室外機冷却システムの Web UI です。

Usage:
  webapp.py [-c CONFIG] [-s CONTROL_HOST] [-p PUB_PORT] [-a ACTUATOR_HOST] [-n COUNT] [-D] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s CONTROL_HOST   : コントローラのホスト名を指定します。 [default: localhost]
  -p PUB_PORT       : ZeroMQ の Pub サーバーを動作させるポートを指定します。 [default: 2222]
  -a ACTUATOR_HOST  : アクチュエータのホスト名を指定します。 [default: localhost]
  -n COUNT          : n 回制御メッセージを受信したら終了します。0 は制限なし。 [default: 0]
  -d                : ダミーモードで実行します。
  -D                : デバッグモードで動作します。
"""

import atexit
import logging
import multiprocessing
import os
import pathlib
import signal
import threading

import flask
import flask_cors
import my_lib.proc_util
import my_lib.webapp.base
import my_lib.webapp.config
import my_lib.webapp.proxy
import my_lib.webapp.util

import unit_cooler.webui.webapi.cooler_stat
import unit_cooler.webui.worker

SCHEMA_CONFIG = "config.schema"

# グローバル変数でワーカースレッドを管理
worker_thread = None


def term():
    # ワーカーの終了フラグを設定
    import unit_cooler.webui.worker

    unit_cooler.webui.worker.term()

    # ワーカースレッドの終了を待つ
    if worker_thread and worker_thread.is_alive():
        logging.info("Waiting for worker thread to finish...")
        worker_thread.join(timeout=5)
        if worker_thread.is_alive():
            logging.warning("Worker thread did not finish in time")

    # 子プロセスを終了
    my_lib.proc_util.kill_child()

    # プロセス終了
    logging.info("Graceful shutdown completed")
    os._exit(0)


def signal_handler(signum, _frame):
    """シグナルハンドラー: CTRL-Cや終了シグナルを受け取った際の処理"""
    logging.info("Received signal %d, shutting down gracefully...", signum)

    term()


def create_app(config, arg):
    setting = {
        "control_host": "localhost",
        "pub_port": 2222,
        "actuator_host": "localhost",
        "log_port": 5001,
        "dummy_mode": False,
        "msg_count": 0,
    }

    setting.update(arg)

    logging.info("Using ZMQ server of %s:%d", setting["control_host"], setting["pub_port"])

    my_lib.webapp.config.URL_PREFIX = "/unit_cooler"
    my_lib.webapp.config.init(config["webui"])

    message_queue = multiprocessing.Manager().Queue(10)
    global worker_thread  # noqa: PLW0603
    worker_thread = threading.Thread(
        target=unit_cooler.webui.worker.subscribe_worker,
        args=(
            config,
            setting["control_host"],
            setting["pub_port"],
            message_queue,
            pathlib.Path(config["webui"]["subscribe"]["liveness"]["file"]),
            setting["msg_count"],
        ),
    )
    worker_thread.start()

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flask.Flask("unit-cooler-webui")

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if setting["dummy_mode"]:
            logging.warning("Set dummy mode")
            # NOTE: オプションでダミーモードが指定された場合、環境変数もそれに揃えておく
            os.environ["DUMMY_MODE"] = "true"
        else:  # pragma: no cover
            pass

        def notify_terminate():  # pragma: no cover
            term()
            my_lib.webapp.log.info("🏃 アプリを再起動します。")
            my_lib.webapp.log.term()

        atexit.register(notify_terminate)
    else:  # pragma: no cover
        pass

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["MESSAGE_QUEUE"] = message_queue

    app.json.compat = True

    # Initialize proxy before registering blueprint
    api_base_url = f"http://{setting['actuator_host']}:{setting['log_port']}/unit_cooler"
    my_lib.webapp.proxy.init(api_base_url)

    app.register_blueprint(my_lib.webapp.base.blueprint_default)
    app.register_blueprint(my_lib.webapp.base.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.proxy.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX)
    app.register_blueprint(
        unit_cooler.webui.webapi.cooler_stat.blueprint, url_prefix=my_lib.webapp.config.URL_PREFIX
    )

    my_lib.webapp.config.show_handler_list(app)

    unit_cooler.webui.webapi.cooler_stat.init(api_base_url)

    # app.debug = True

    return app


if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    control_host = os.environ.get("HEMS_CONTROL_HOST", args["-s"])
    pub_port = int(os.environ.get("HEMS_PUB_PORT", args["-p"]))
    actuator_host = os.environ.get("HEMS_ACTUATOR_HOST", args["-a"])
    dummy_mode = args["-d"]
    msg_count = int(args["-n"])
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    app = create_app(
        config,
        {
            "control_host": control_host,
            "pub_port": pub_port,
            "actuator_host": actuator_host,
            "log_port": config["actuator"]["web_server"]["webapp"]["port"],
            "dummy_mode": dummy_mode,
            "msg_count": msg_count,
        },
    )

    # Flaskアプリケーションを実行
    try:
        # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
        app.run(host="0.0.0.0", threaded=True, use_reloader=True, port=config["webui"]["webapp"]["port"])  # noqa: S104
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
        signal_handler(signal.SIGINT, None)
    finally:
        term()
