#!/usr/bin/env python3
"""
統一的な状態管理モジュール

テストにおける time.sleep() を排除するため、アプリケーション全体の状態を
一元管理し、状態変更の待機を効率的に行えるようにする。

使用例:
    # 状態の更新
    state = get_state_manager()
    state.update(valve_state=VALVE_STATE.OPEN)

    # 状態の待機
    state.wait_for(lambda s: s.valve_state == VALVE_STATE.OPEN, timeout=5.0)

    # 便利メソッドの使用
    state.wait_for_valve_open(timeout=5.0)
    state.wait_for_control_count(5, timeout=10.0)
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from unit_cooler.const import COOLING_STATE, VALVE_STATE


@dataclass
class StateManager:
    """アプリケーション状態の一元管理

    全てのコンポーネントの状態を一元管理し、
    threading.Condition を使用して効率的な状態待機を実現する。
    """

    # Condition 変数（状態変更の通知に使用）
    _condition: threading.Condition = field(default_factory=threading.Condition, init=False)

    # ワーカー処理回数
    control_worker_count: int = field(default=0, init=False)
    monitor_worker_count: int = field(default=0, init=False)
    subscribe_worker_count: int = field(default=0, init=False)

    # ワーカー最終処理時刻
    control_worker_last_time: datetime | None = field(default=None, init=False)
    monitor_worker_last_time: datetime | None = field(default=None, init=False)
    subscribe_worker_last_time: datetime | None = field(default=None, init=False)

    # バルブ状態
    valve_state: VALVE_STATE | None = field(default=None, init=False)
    valve_last_change: datetime | None = field(default=None, init=False)
    valve_operation_count: int = field(default=0, init=False)

    # 冷却状態
    cooling_state: COOLING_STATE | None = field(default=None, init=False)
    cooling_mode_index: int = field(default=0, init=False)

    # メッセージ受信
    message_receive_count: int = field(default=0, init=False)
    last_message: dict[str, Any] | None = field(default=None, init=False)

    # 流量
    flow_lpm: float = field(default=0.0, init=False)

    # フラグ
    hazard_detected: bool = field(default=False, init=False)
    server_ready: bool = field(default=False, init=False)

    # ログ書き込み回数
    log_write_count: int = field(default=0, init=False)

    def update(self, **kwargs: Any) -> None:
        """状態を更新して待機中のスレッドに通知

        Args:
            **kwargs: 更新する状態のキーと値

        Example:
            state.update(valve_state=VALVE_STATE.OPEN, valve_operation_count=1)
        """
        with self._condition:
            for key, value in kwargs.items():
                if hasattr(self, key) and not key.startswith("_"):
                    setattr(self, key, value)
                else:
                    logging.warning("StateManager: unknown attribute %s", key)
            self._condition.notify_all()

    def increment(self, attr: str, delta: int = 1) -> int:
        """カウンターをインクリメントして通知

        Args:
            attr: インクリメントする属性名
            delta: 増分（デフォルト: 1）

        Returns:
            インクリメント後の値
        """
        with self._condition:
            current = getattr(self, attr, 0)
            new_value = current + delta
            setattr(self, attr, new_value)
            self._condition.notify_all()
            return new_value

    def get(self, attr: str) -> Any:
        """属性値を取得"""
        with self._condition:
            return getattr(self, attr, None)

    def wait_for(
        self,
        predicate: Callable[[StateManager], bool],
        timeout: float = 1.0,
    ) -> bool:
        """条件が満たされるまで待機

        Args:
            predicate: 待機条件（StateManager を受け取り bool を返す関数）
            timeout: 最大待機時間（秒）

        Returns:
            条件が満たされた場合 True、タイムアウトした場合 False

        Example:
            # バルブが OPEN になるまで待機
            state.wait_for(lambda s: s.valve_state == VALVE_STATE.OPEN, timeout=5.0)
        """
        with self._condition:
            return self._condition.wait_for(
                lambda: predicate(self),
                timeout=timeout,
            )

    def wait_for_attr(
        self,
        attr: str,
        value: Any,
        timeout: float = 1.0,
    ) -> bool:
        """特定の属性が指定値になるまで待機

        Args:
            attr: 待機する属性名
            value: 期待する値
            timeout: 最大待機時間（秒）

        Returns:
            値が一致した場合 True、タイムアウトした場合 False
        """
        return self.wait_for(lambda s: getattr(s, attr, None) == value, timeout)

    def wait_for_count(
        self,
        attr: str,
        target_count: int,
        timeout: float = 1.0,
    ) -> bool:
        """カウンターが指定値以上になるまで待機

        Args:
            attr: 待機するカウンター属性名
            target_count: 目標回数
            timeout: 最大待機時間（秒）

        Returns:
            目標回数に達した場合 True、タイムアウトした場合 False
        """
        return self.wait_for(lambda s: getattr(s, attr, 0) >= target_count, timeout)

    # =========================================================================
    # 便利メソッド: ワーカー関連
    # =========================================================================
    def notify_control_processed(self) -> None:
        """control_worker の処理完了を通知"""
        with self._condition:
            self.control_worker_count += 1
            self.control_worker_last_time = datetime.now()
            self._condition.notify_all()

    def notify_monitor_processed(self) -> None:
        """monitor_worker の処理完了を通知"""
        with self._condition:
            self.monitor_worker_count += 1
            self.monitor_worker_last_time = datetime.now()
            self._condition.notify_all()

    def notify_subscribe_processed(self) -> None:
        """subscribe_worker の処理完了を通知"""
        with self._condition:
            self.subscribe_worker_count += 1
            self.subscribe_worker_last_time = datetime.now()
            self._condition.notify_all()

    def wait_for_control_process(self, timeout: float = 1.0) -> bool:
        """control_worker の次の処理完了を待機"""
        with self._condition:
            target = self.control_worker_count + 1
            return self._condition.wait_for(
                lambda: self.control_worker_count >= target,
                timeout=timeout,
            )

    def wait_for_monitor_process(self, timeout: float = 1.0) -> bool:
        """monitor_worker の次の処理完了を待機"""
        with self._condition:
            target = self.monitor_worker_count + 1
            return self._condition.wait_for(
                lambda: self.monitor_worker_count >= target,
                timeout=timeout,
            )

    def wait_for_control_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """control_worker が指定回数処理するまで待機"""
        return self.wait_for_count("control_worker_count", target_count, timeout)

    def wait_for_monitor_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """monitor_worker が指定回数処理するまで待機"""
        return self.wait_for_count("monitor_worker_count", target_count, timeout)

    # =========================================================================
    # 便利メソッド: バルブ関連
    # =========================================================================
    def notify_valve_state_changed(self, state: VALVE_STATE) -> None:
        """バルブ状態変更を通知"""
        with self._condition:
            self.valve_state = state
            self.valve_last_change = datetime.now()
            self.valve_operation_count += 1
            self._condition.notify_all()

    def wait_for_valve_state(self, state: VALVE_STATE, timeout: float = 1.0) -> bool:
        """バルブが特定の状態になるまで待機"""
        return self.wait_for_attr("valve_state", state, timeout)

    def wait_for_valve_open(self, timeout: float = 1.0) -> bool:
        """バルブが OPEN になるまで待機"""
        from unit_cooler.const import VALVE_STATE

        return self.wait_for_valve_state(VALVE_STATE.OPEN, timeout)

    def wait_for_valve_close(self, timeout: float = 1.0) -> bool:
        """バルブが CLOSE になるまで待機"""
        from unit_cooler.const import VALVE_STATE

        return self.wait_for_valve_state(VALVE_STATE.CLOSE, timeout)

    def wait_for_valve_operation_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """バルブ操作が指定回数になるまで待機"""
        return self.wait_for_count("valve_operation_count", target_count, timeout)

    # =========================================================================
    # 便利メソッド: 冷却状態関連
    # =========================================================================
    def notify_cooling_state_changed(self, state: COOLING_STATE, mode_index: int = 0) -> None:
        """冷却状態変更を通知"""
        with self._condition:
            self.cooling_state = state
            self.cooling_mode_index = mode_index
            self._condition.notify_all()

    def wait_for_cooling_state(self, state: COOLING_STATE, timeout: float = 1.0) -> bool:
        """冷却が特定の状態になるまで待機"""
        return self.wait_for_attr("cooling_state", state, timeout)

    def wait_for_cooling_working(self, timeout: float = 1.0) -> bool:
        """冷却が WORKING になるまで待機"""
        from unit_cooler.const import COOLING_STATE

        return self.wait_for_cooling_state(COOLING_STATE.WORKING, timeout)

    def wait_for_cooling_idle(self, timeout: float = 1.0) -> bool:
        """冷却が IDLE になるまで待機"""
        from unit_cooler.const import COOLING_STATE

        return self.wait_for_cooling_state(COOLING_STATE.IDLE, timeout)

    # =========================================================================
    # 便利メソッド: メッセージ関連
    # =========================================================================
    def notify_message_received(self, message: dict[str, Any]) -> None:
        """メッセージ受信を通知"""
        with self._condition:
            self.message_receive_count += 1
            self.last_message = message
            self._condition.notify_all()

    def wait_for_message_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """指定回数のメッセージを受信するまで待機"""
        return self.wait_for_count("message_receive_count", target_count, timeout)

    def wait_for_next_message(self, timeout: float = 1.0) -> bool:
        """次のメッセージ受信を待機"""
        with self._condition:
            target = self.message_receive_count + 1
            return self._condition.wait_for(
                lambda: self.message_receive_count >= target,
                timeout=timeout,
            )

    # =========================================================================
    # 便利メソッド: サーバー/ログ関連
    # =========================================================================
    def notify_server_ready(self) -> None:
        """サーバー起動完了を通知"""
        self.update(server_ready=True)

    def wait_for_server_ready(self, timeout: float = 5.0) -> bool:
        """サーバー起動を待機"""
        return self.wait_for_attr("server_ready", True, timeout)

    def notify_log_written(self) -> None:
        """ログ書き込みを通知"""
        self.increment("log_write_count")

    def wait_for_log_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """指定回数のログ書き込みを待機"""
        return self.wait_for_count("log_write_count", target_count, timeout)

    # =========================================================================
    # リセット
    # =========================================================================
    def reset(self) -> None:
        """全ての状態をリセット"""
        with self._condition:
            # ワーカー
            self.control_worker_count = 0
            self.monitor_worker_count = 0
            self.subscribe_worker_count = 0
            self.control_worker_last_time = None
            self.monitor_worker_last_time = None
            self.subscribe_worker_last_time = None

            # バルブ
            self.valve_state = None
            self.valve_last_change = None
            self.valve_operation_count = 0

            # 冷却
            self.cooling_state = None
            self.cooling_mode_index = 0

            # メッセージ
            self.message_receive_count = 0
            self.last_message = None

            # その他
            self.flow_lpm = 0.0
            self.hazard_detected = False
            self.server_ready = False
            self.log_write_count = 0


# =============================================================================
# グローバルインスタンス管理（pytest ワーカー毎に独立）
# =============================================================================
_state_managers: dict[str, StateManager] = {}
_state_managers_lock = threading.Lock()


def _get_worker_id() -> str:
    """pytest ワーカー ID を取得"""
    return os.environ.get("PYTEST_XDIST_WORKER", "")


def get_state_manager() -> StateManager:
    """現在のワーカーの StateManager インスタンスを取得

    pytest-xdist で並列実行する場合、各ワーカーは独立した
    StateManager インスタンスを使用する。

    Returns:
        StateManager インスタンス
    """
    worker_id = _get_worker_id()

    with _state_managers_lock:
        if worker_id not in _state_managers:
            _state_managers[worker_id] = StateManager()
        return _state_managers[worker_id]


def reset_state_manager() -> None:
    """現在のワーカーの StateManager をリセット"""
    get_state_manager().reset()


def init_state_manager() -> StateManager:
    """StateManager を初期化して返す

    テストの setup で呼び出し、クリーンな状態から開始する。
    """
    manager = get_state_manager()
    manager.reset()
    return manager
