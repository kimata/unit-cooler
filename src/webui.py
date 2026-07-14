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

import logging
import os
import queue
import sys
import threading
from typing import TYPE_CHECKING

import flask
import flask_cors
import my_lib.webapp.runner

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config, RuntimeSettings
    from unit_cooler.messages import ControlMessage

# グローバル変数でワーカースレッドを管理
worker_threads: list[threading.Thread] = []


def _shutdown_workers():
    """ワーカーを停止して終了を待つ (プロセス終了はしない)"""
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
    worker_threads.clear()


def term():
    _shutdown_workers()

    # プロセス終了
    logger.info("Graceful shutdown completed")
    sys.exit(0)


def create_app(config: Config, settings: RuntimeSettings) -> flask.Flask:
    logger.info("Using ZMQ server of %s:%d", settings.control_host, settings.pub_port)

    import my_lib.webapp.base
    import my_lib.webapp.config
    import my_lib.webapp.proxy
    import my_lib.webapp.util

    import unit_cooler.const
    import unit_cooler.metrics.webapi.page
    import unit_cooler.webui.webapi.cooler_stat
    import unit_cooler.webui.worker

    environment = my_lib.webapp.config.build_environment(
        config.webui.webapp.to_webapp_config(config.base_dir),
        url_prefix=unit_cooler.const.URL_PREFIX,
    )

    # NOTE: 生産者（購読ワーカスレッド）も消費者（Flask スレッド）も同一プロセス内のため、
    # multiprocessing.Manager().Queue ではなく queue.Queue で十分
    message_queue: queue.Queue[ControlMessage] = queue.Queue(10)

    # NOTE: 再呼び出し（テスト等）に備えて、前回のワーカ状態をリセットする
    unit_cooler.webui.worker.should_terminate.clear()
    worker_threads.clear()

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

    flask_cors.CORS(app)

    app.config["CONFIG"] = config
    app.config["MESSAGE_QUEUE"] = message_queue

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
    # メトリクスページ（プロキシ経由で表示）が参照する JS/CSS/favicon を Web UI 側でも配信する
    app.register_blueprint(
        unit_cooler.metrics.webapi.page.static_blueprint, url_prefix=unit_cooler.const.URL_PREFIX
    )

    my_lib.webapp.config.show_handler_list(app)

    # app.debug = True

    return app


def _load_config(config_file, args):
    import pathlib

    from unit_cooler.config import Config

    return Config.load(config_file, pathlib.Path("schema/config.schema"))


def _app_factory(config, ctx):
    from unit_cooler.config import RuntimeSettings

    settings = RuntimeSettings.from_args(
        ctx.args,
        {
            "control_host": "-s",
            "pub_port": "-p",
            "actuator_host": "-a",
            "log_port": "-l",
            "status_pub_port": "-S",
            "dummy_mode": "-d",
            "msg_count": "-n",
            "debug_mode": "-D",
        },
    )

    if settings.dummy_mode:
        logger.warning("Set dummy mode")
        # NOTE: ダミーモード指定時は下流コードが参照する環境変数も揃えておく
        os.environ["DUMMY_MODE"] = "true"

    return create_app(config, settings)


SPEC = my_lib.webapp.runner.WebAppSpec(
    logger_name="hems.unit_cooler",
    config_loader=_load_config,
    app_factory=_app_factory,
    term_hooks=(_shutdown_workers,),
    # NOTE: use_reloader=True にすると reloader の親プロセスでも create_app() が走り、
    # ZMQ 購読ワーカースレッドが親子で二重起動してしまう。本番では自動リロードは
    # 不要なので False にする。
    use_reloader=False,
    # -p は ZMQ Pub ポートのため、WEB サーバのポートは config から取る
    port_resolver=lambda config, args: config.webui.webapp.port,
)

if __name__ == "__main__":
    assert __doc__ is not None  # noqa: S101
    my_lib.webapp.runner.run(SPEC, __doc__)
