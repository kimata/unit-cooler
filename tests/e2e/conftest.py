#!/usr/bin/env python3
"""E2E テスト用 conftest.py"""

from __future__ import annotations

import os
import pathlib

import pytest

# NOTE: --host and --port options are defined in tests/conftest.py
# E2E tests inherit those options from the parent conftest


@pytest.fixture(scope="session")
def host(request):
    """テスト対象のホスト (session scope for E2E tests)"""
    return request.config.getoption("--host")


@pytest.fixture(scope="session")
def port(request):
    """テスト対象のポート (session scope for E2E tests)"""
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
