#!/usr/bin/env python3
# ruff: noqa: S108
"""ポート管理ユーティリティ

並列テスト実行時のポート割り当てを管理する。
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import pathlib
import socket
import time

# ポート管理ファイル
USED_PORTS_FILE = pathlib.Path("/tmp/pytest_used_ports")
PORT_LOCK_FILE = pathlib.Path("/tmp/pytest_port_lock")

# ポート範囲
MIN_PORT = 10000
MAX_PORT = 60000

# リトライ設定
MAX_RETRIES = 100
RETRY_DELAY = 0.1


class PortManager:
    """ポート管理クラス

    並列テスト実行時に、各ワーカーが異なるポートを使用するように管理する。
    """

    def __init__(self):
        """初期化"""
        self.allocated_ports: list[int] = []

    @staticmethod
    def _get_worker_id() -> str:
        """pytest-xdist のワーカー ID を取得"""
        return os.environ.get("PYTEST_XDIST_WORKER", "main")

    @staticmethod
    def _acquire_lock() -> int:
        """ファイルロックを取得

        Returns:
            ファイルディスクリプタ
        """
        fd = os.open(str(PORT_LOCK_FILE), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @staticmethod
    def _release_lock(fd: int) -> None:
        """ファイルロックを解放

        Args:
            fd: ファイルディスクリプタ
        """
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    @staticmethod
    def _load_used_ports() -> set[int]:
        """使用中のポートを読み込む

        Returns:
            使用中のポートのセット
        """
        if not USED_PORTS_FILE.exists():
            return set()
        try:
            with USED_PORTS_FILE.open() as f:
                data = json.load(f)
                return set(data.get("ports", []))
        except (json.JSONDecodeError, OSError):
            return set()

    @staticmethod
    def _save_used_ports(ports: set[int]) -> None:
        """使用中のポートを保存する

        Args:
            ports: 使用中のポートのセット
        """
        with USED_PORTS_FILE.open("w") as f:
            json.dump({"ports": list(ports)}, f)

    @staticmethod
    def _is_port_available(port: int) -> bool:
        """ポートが使用可能か確認

        Args:
            port: 確認するポート番号

        Returns:
            使用可能な場合 True
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def find_unused_port(self) -> int:
        """未使用のポートを見つける

        Returns:
            未使用のポート番号

        Raises:
            RuntimeError: 利用可能なポートが見つからない場合
        """
        worker_id = self._get_worker_id()
        logging.debug("Worker %s: finding unused port", worker_id)

        fd = self._acquire_lock()
        try:
            used_ports = self._load_used_ports()

            for _ in range(MAX_RETRIES):
                # ランダムなポートを選択
                port = MIN_PORT + (hash(f"{worker_id}_{time.time()}") % (MAX_PORT - MIN_PORT))

                if port in used_ports:
                    continue

                if self._is_port_available(port):
                    used_ports.add(port)
                    self._save_used_ports(used_ports)
                    self.allocated_ports.append(port)
                    logging.debug("Worker %s: allocated port %d", worker_id, port)
                    return port

                time.sleep(RETRY_DELAY)

            raise RuntimeError(f"Worker {worker_id}: Could not find an available port")
        finally:
            self._release_lock(fd)

    def release_port(self, port: int) -> None:
        """ポートを解放する

        Args:
            port: 解放するポート番号
        """
        worker_id = self._get_worker_id()
        logging.debug("Worker %s: releasing port %d", worker_id, port)

        fd = self._acquire_lock()
        try:
            used_ports = self._load_used_ports()
            used_ports.discard(port)
            self._save_used_ports(used_ports)

            if port in self.allocated_ports:
                self.allocated_ports.remove(port)
        finally:
            self._release_lock(fd)

    def release_all(self) -> None:
        """全ての割り当て済みポートを解放"""
        for port in self.allocated_ports.copy():
            self.release_port(port)

    @classmethod
    def cleanup_stale_ports(cls) -> None:
        """古いポート情報をクリーンアップ"""
        fd = cls._acquire_lock()
        try:
            used_ports = cls._load_used_ports()
            available_ports = {p for p in used_ports if cls._is_port_available(p)}
            stale_ports = used_ports - available_ports

            if stale_ports:
                logging.debug("Cleaning up stale ports: %s", stale_ports)
                cls._save_used_ports(available_ports)
        finally:
            cls._release_lock(fd)


# シングルトンインスタンス
_port_manager: PortManager | None = None


def get_port_manager() -> PortManager:
    """ポートマネージャーのシングルトンインスタンスを取得"""
    global _port_manager
    if _port_manager is None:
        _port_manager = PortManager()
    return _port_manager


def find_unused_port() -> int:
    """未使用のポートを見つける (便利関数)"""
    return get_port_manager().find_unused_port()


def release_port(port: int) -> None:
    """ポートを解放する (便利関数)"""
    get_port_manager().release_port(port)
