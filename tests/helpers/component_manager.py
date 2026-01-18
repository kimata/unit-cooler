#!/usr/bin/env python3
"""コンポーネント管理ユーティリティ

テスト用のコンポーネント起動・終了を管理する。
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

import flask

if TYPE_CHECKING:
    from unit_cooler.config import Config

# 型定義
ControllerHandle = tuple[threading.Thread | None, threading.Thread | None]
ActuatorHandle = tuple[concurrent.futures.ThreadPoolExecutor, list[Any], Any]
WebuiHandle = tuple[threading.Thread, flask.Flask]


class ComponentManager:
    """コンポーネント管理クラス

    テスト用のコンポーネント（Controller, Actuator）の
    ライフサイクルを管理する。
    """

    def __init__(self):
        """初期化"""
        self.handles: dict[str, Any] = {}
        self.auto_teardown = True
        self._lock = threading.Lock()

    def start_controller(
        self,
        config: Config,
        server_port: int,
        real_port: int,
        **kwargs: Any,
    ) -> ControllerHandle:
        """Controller を起動

        Args:
            config: アプリケーション設定
            server_port: ZeroMQ サーバーポート
            real_port: 実サーバーポート
            **kwargs: 追加オプション

        Returns:
            (control_thread, proxy_thread) のタプル
        """
        import controller
        from unit_cooler.config import RuntimeSettings

        default_options = {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        }
        default_options.update(kwargs)
        settings = RuntimeSettings.from_dict(default_options)

        with self._lock:
            self.handles["controller"] = controller.start(config, settings)
            logging.debug("Controller started on port %d", server_port)
            return self.handles["controller"]

    def start_actuator(
        self,
        config: Config,
        server_port: int,
        log_port: int,
        **kwargs: Any,
    ) -> ActuatorHandle:
        """Actuator を起動

        Args:
            config: アプリケーション設定
            server_port: ZeroMQ パブリッシュポート
            log_port: ログポート
            **kwargs: 追加オプション

        Returns:
            (executor, thread_list, log_server_handle) のタプル
        """
        import actuator
        from unit_cooler.config import RuntimeSettings

        default_options = {
            "speedup": 100,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
            "dummy_mode": True,
        }
        default_options.update(kwargs)
        settings = RuntimeSettings.from_dict(default_options)

        with self._lock:
            self.handles["actuator"] = actuator.start(config, settings)
            logging.debug("Actuator started on port %d", server_port)
            return self.handles["actuator"]

    def start_webui(
        self,
        config: Config,
        server_port: int,
        log_port: int,
        http_port: int = 5000,
        **kwargs: Any,
    ) -> WebuiHandle:
        """WebUI を起動

        Note: webui モジュールは start/wait_and_term パターンを使用しないため、
        Flask アプリを別スレッドで起動する。

        Args:
            config: アプリケーション設定
            server_port: ZeroMQ パブリッシュポート
            log_port: ログポート
            http_port: HTTP サーバーポート
            **kwargs: 追加オプション

        Returns:
            (thread, app) のタプル
        """
        import webui
        from unit_cooler.config import RuntimeSettings

        default_options = {
            "msg_count": 1,
            "dummy_mode": True,
            "pub_port": server_port,
            "log_port": log_port,
        }
        default_options.update(kwargs)
        settings = RuntimeSettings.from_dict(default_options)

        app = webui.create_app(config, settings)

        def run_webui():
            app.run(host="127.0.0.1", port=http_port, threaded=True, use_reloader=False)

        thread = threading.Thread(target=run_webui, daemon=True)
        thread.start()

        with self._lock:
            self.handles["webui"] = (thread, app)
            logging.debug("WebUI started on port %d", http_port)
            return self.handles["webui"]

    def wait_and_term_controller(self) -> None:
        """Controller を終了"""
        with self._lock:
            if "controller" not in self.handles:
                return

            import controller

            controller.wait_and_term(*self.handles["controller"])
            del self.handles["controller"]
            logging.debug("Controller terminated")

    def wait_and_term_actuator(self) -> None:
        """Actuator を終了"""
        with self._lock:
            if "actuator" not in self.handles:
                return

            import actuator

            actuator.wait_and_term(*self.handles["actuator"])
            del self.handles["actuator"]
            logging.debug("Actuator terminated")

    def wait_and_term_webui(self) -> None:
        """WebUI を終了

        Note: Flask app は daemon スレッドで起動されているため、
        プロセス終了時に自動的に終了する。明示的な終了処理は行わない。
        """
        with self._lock:
            if "webui" not in self.handles:
                return

            import webui

            webui.term()
            del self.handles["webui"]
            logging.debug("WebUI terminated")

    def wait_and_term_all(self) -> None:
        """全コンポーネントを終了"""
        # 終了順序: WebUI -> Actuator -> Controller
        self.wait_and_term_webui()
        self.wait_and_term_actuator()
        self.wait_and_term_controller()

    def teardown_all(self) -> None:
        """全コンポーネントを強制終了"""
        if not self.auto_teardown:
            return

        with self._lock:
            if "webui" in self.handles:
                try:
                    import webui

                    webui.term()
                except Exception as e:
                    logging.warning("Error terminating webui: %s", e)
                self.handles.pop("webui", None)

            if "actuator" in self.handles:
                try:
                    import actuator

                    actuator.wait_and_term(*self.handles["actuator"])
                except Exception as e:
                    logging.warning("Error terminating actuator: %s", e)
                self.handles.pop("actuator", None)

            if "controller" in self.handles:
                try:
                    import controller

                    controller.wait_and_term(*self.handles["controller"])
                except Exception as e:
                    logging.warning("Error terminating controller: %s", e)
                self.handles.pop("controller", None)

    def is_running(self, component: str) -> bool:
        """コンポーネントが実行中かチェック

        Args:
            component: コンポーネント名 ("controller", "actuator", "webui")

        Returns:
            実行中の場合 True
        """
        with self._lock:
            if component not in self.handles:
                return False

            if component == "controller":
                control_thread, proxy_thread = self.handles[component]
                return (control_thread is not None and control_thread.is_alive()) or (
                    proxy_thread is not None and proxy_thread.is_alive()
                )
            elif component == "actuator":
                executor, thread_list, _ = self.handles[component]
                return any(t["future"].running() for t in thread_list)
            elif component == "webui":
                thread, _ = self.handles[component]
                return thread.is_alive()

            return False

    def wait_for_startup(
        self,
        component: str,
        timeout: float = 10.0,
        check_interval: float = 0.1,
    ) -> bool:
        """コンポーネントの起動を待機

        Args:
            component: コンポーネント名
            timeout: タイムアウト秒数
            check_interval: チェック間隔秒数

        Returns:
            起動した場合 True

        Raises:
            TimeoutError: タイムアウトした場合
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.is_running(component):
                return True
            time.sleep(check_interval)

        raise TimeoutError(f"{component} did not start within {timeout}s")

    @property
    def running_components(self) -> list[str]:
        """実行中のコンポーネント一覧を取得"""
        with self._lock:
            return [name for name in self.handles if self.is_running(name)]


class FullSystemManager(ComponentManager):
    """フルシステム管理クラス

    Controller + Actuator + WebUI の完全なシステムを管理する。
    """

    def start_full_system(
        self,
        config: Config,
        controller_port: int,
        actuator_port: int,
        log_port: int,
        webui_http_port: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """フルシステムを起動

        Args:
            config: アプリケーション設定
            controller_port: Controller のサーバーポート
            actuator_port: Actuator の ZeroMQ ポート
            log_port: ログポート
            webui_http_port: WebUI の HTTP ポート (None の場合は起動しない)
            **kwargs: 追加オプション

        Returns:
            各コンポーネントのハンドル
        """
        controller_kwargs = kwargs.get("controller", {})
        actuator_kwargs = kwargs.get("actuator", {})
        webui_kwargs = kwargs.get("webui", {})

        # 起動順序: Controller -> Actuator -> (WebUI)
        self.start_controller(
            config,
            server_port=controller_port,
            real_port=actuator_port,
            **controller_kwargs,
        )

        self.start_actuator(
            config,
            server_port=actuator_port,
            log_port=log_port,
            **actuator_kwargs,
        )

        if webui_http_port is not None:
            self.start_webui(
                config,
                server_port=controller_port,
                log_port=log_port,
                http_port=webui_http_port,
                **webui_kwargs,
            )

        return self.handles.copy()

    def wait_for_full_startup(self, timeout: float = 30.0) -> bool:
        """フルシステムの起動を待機

        Args:
            timeout: タイムアウト秒数

        Returns:
            全コンポーネントが起動した場合 True
        """
        start = time.time()
        components = ["controller", "actuator"]
        if "webui" in self.handles:
            components.append("webui")

        per_component_timeout = timeout / len(components)

        for component in components:
            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                raise TimeoutError(f"Full system did not start within {timeout}s")

            self.wait_for_startup(
                component,
                timeout=min(remaining, per_component_timeout),
            )

        return True
