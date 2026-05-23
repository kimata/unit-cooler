#!/usr/bin/env python3
"""
エアコン室外機冷却システムの Web UI です。

Usage:
  webui.py [-c CONFIG] [-s CONTROL_HOST] [-p PUB_PORT] [-a ACTUATOR_HOST] [-l LOG_PORT]
           [-S STATUS_PORT] [-n COUNT] [-D] [-d]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s CONTROL_HOST   : コントローラのホスト名を指定します。 [default: localhost]
  -p PUB_PORT       : ZeroMQ の Pub サーバーを動作させるポートを指定します。 [default: 2222]
  -a ACTUATOR_HOST  : アクチュエータのホスト名を指定します。 [default: localhost]
  -l LOG_PORT       : 動作ログを提供するアクチュエータの WEB サーバーのポートを指定します。 [default: 5001]
  -S STATUS_PORT    : ActuatorStatus を配信するポートを指定します。0 で無効。 [default: 0]
  -n COUNT          : n 回制御メッセージを受信したら終了します。0 は制限なし。 [default: 0]
  -d                : ダミーモードで実行します。
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import pathlib
import signal
import sys
import threading
from typing import TYPE_CHECKING

import flask
import flask_cors
import my_lib.proc_util

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config, RuntimeSettings

SCHEMA_CONFIG = "schema/config.schema"

# グローバル変数でワーカースレッドを管理
worker_threads: list[threading.Thread] = []


def term():
    # ワーカーの終了フラグを設定
    import unit_cooler.webui.worker

    unit_cooler.webui.worker.term()

    # ワーカースレッドの終了を待つ
    for thread in worker_threads:
        if thread and thread.is_alive():
            logger.info("Waiting for worker thread to finish...")
            thread.join(timeout=5)
            if thread.is_alive():
                logger.warning("Worker thread did not finish in time")

    # 子プロセスを終了
    my_lib.proc_util.kill_child()

    # プロセス終了
    logger.info("Graceful shutdown completed")
    sys.exit(0)


def signal_handler(signum, _frame):
    """シグナルハンドラー: CTRL-Cや終了シグナルを受け取った際の処理"""
    logger.info("Received signal %d, shutting down gracefully...", signum)

    term()


def create_app(config: Config, settings: RuntimeSettings) -> flask.Flask:
    logger.info("Using ZMQ server of %s:%d", settings.control_host, settings.pub_port)

    import my_lib.webapp.base
    import my_lib.webapp.config
    import my_lib.webapp.proxy
    import my_lib.webapp.util

    import unit_cooler.const
    import unit_cooler.webui.webapi.cooler_stat
    import unit_cooler.webui.worker

    environment = my_lib.webapp.config.build_environment(
        config.webui.webapp.to_webapp_config(config.base_dir),
        url_prefix=unit_cooler.const.URL_PREFIX,
    )

    message_queue = multiprocessing.Manager().Queue(10)
    global worker_threads

    # 制御メッセージ購読ワーカ
    subscribe_thread = threading.Thread(
        target=unit_cooler.webui.worker.subscribe_worker,
        args=(
            config,
            settings.control_host,
            settings.pub_port,
            message_queue,
            config.webui.subscribe.liveness.file,
            settings.msg_count,
        ),
    )
    subscribe_thread.start()
    worker_threads.append(subscribe_thread)

    # ActuatorStatus 購読ワーカ（status_pub_port が指定されている場合）
    if settings.status_pub_port > 0:
        status_thread = threading.Thread(
            target=unit_cooler.webui.worker.actuator_status_worker,
            args=(
                config,
                settings.actuator_host,
                settings.status_pub_port,
            ),
        )
        status_thread.start()
        worker_threads.append(status_thread)

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    app = flask.Flask("unit-cooler-webui")

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if settings.dummy_mode:
            logger.warning("Set dummy mode")
            # NOTE: オプションでダミーモードが指定された場合、環境変数もそれに揃えておく
            os.environ["DUMMY_MODE"] = "true"
        else:  # pragma: no cover
            pass

        def notify_terminate():  # pragma: no cover
            import my_lib.webapp.log

            term()
            my_lib.webapp.log.info("🏃 アプリを再起動します。")
            my_lib.webapp.log.term()

        atexit.register(notify_terminate)
    else:  # pragma: no cover
        pass

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["MESSAGE_QUEUE"] = message_queue

    app.json.compat = True  # type: ignore[attr-defined]

    # Initialize proxy before registering blueprint
    api_base_url = f"http://{settings.actuator_host}:{settings.log_port}/unit-cooler"
    my_lib.webapp.proxy.init(api_base_url)

    app.register_blueprint(
        my_lib.webapp.base.create_root_redirect_blueprint(url_prefix=unit_cooler.const.URL_PREFIX)
    )
    app.register_blueprint(
        my_lib.webapp.base.create_static_blueprint(environment=environment),
        url_prefix=unit_cooler.const.URL_PREFIX,
    )
    app.register_blueprint(my_lib.webapp.proxy.blueprint, url_prefix=unit_cooler.const.URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=unit_cooler.const.URL_PREFIX)
    app.register_blueprint(
        unit_cooler.webui.webapi.cooler_stat.blueprint, url_prefix=unit_cooler.const.URL_PREFIX
    )

    my_lib.webapp.config.show_handler_list(app)

    # app.debug = True

    return app


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    from unit_cooler.config import Config, RuntimeSettings

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    control_host = os.environ.get("HEMS_CONTROL_HOST", args["-s"])
    pub_port = int(os.environ.get("HEMS_PUB_PORT", args["-p"]))
    actuator_host = os.environ.get("HEMS_ACTUATOR_HOST", args["-a"])
    log_port = int(os.environ.get("HEMS_LOG_PORT", args["-l"]))
    status_pub_port = int(os.environ.get("HEMS_STATUS_PUB_PORT", args["-S"]))
    dummy_mode = args["-d"]
    msg_count = int(args["-n"])
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file, pathlib.Path(SCHEMA_CONFIG))
    settings = RuntimeSettings.from_dict(
        {
            "control_host": control_host,
            "pub_port": pub_port,
            "actuator_host": actuator_host,
            "log_port": log_port,
            "status_pub_port": status_pub_port,
            "dummy_mode": dummy_mode,
            "msg_count": msg_count,
        }
    )

    app = create_app(config, settings)

    # Flaskアプリケーションを実行
    try:
        # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
        app.run(host="0.0.0.0", threaded=True, use_reloader=True, port=config.webui.webapp.port)  # noqa: S104
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        signal_handler(signal.SIGINT, None)
    finally:
        term()
