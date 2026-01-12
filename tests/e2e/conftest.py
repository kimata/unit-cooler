#!/usr/bin/env python3
"""E2E テスト用 conftest.py"""

from __future__ import annotations

import os
import pathlib

import pytest


def pytest_addoption(parser):
    """コマンドラインオプションを追加"""
    parser.addoption(
        "--host",
        action="store",
        default="localhost",
        help="Target host for E2E tests",
    )
    parser.addoption(
        "--port",
        action="store",
        default="5000",
        help="Target port for E2E tests",
    )


@pytest.fixture(scope="session")
def host(request):
    """テスト対象のホスト"""
    return request.config.getoption("--host")


@pytest.fixture(scope="session")
def port(request):
    """テスト対象のポート"""
    return request.config.getoption("--port")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Playwright ブラウザコンテキスト引数"""
    # レコード設定
    record_video = os.environ.get("RECORD_VIDEO", "false").lower() == "true"

    if record_video:
        evidence_dir = pathlib.Path("reports/evidence")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        return {
            **browser_context_args,
            "record_video_dir": str(evidence_dir),
            "record_video_size": {"width": 1920, "height": 1080},
        }

    return browser_context_args
