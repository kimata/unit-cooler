#!/usr/bin/env python3
import os
import pathlib

import pytest

# Import test helper fixtures for use across test modules
from .test_helpers import component_manager, controller_mocks, standard_mocks, webapp_client  # noqa: F401


def pytest_addoption(parser):
    parser.addoption("--host", default="127.0.0.1")
    parser.addoption("--port", default="5000")


@pytest.fixture
def host(request):
    return request.config.getoption("--host")


@pytest.fixture
def port(request):
    return request.config.getoption("--port")


@pytest.fixture
def page(page):
    from playwright.sync_api import expect

    timeout = 30000
    page.set_default_navigation_timeout(timeout)
    page.set_default_timeout(timeout)
    expect.set_options(timeout=timeout)

    return page


@pytest.fixture
def browser_context_args(browser_context_args, request):
    """環境変数 RECORD_VIDEO=true でビデオ録画を有効化"""
    args = {**browser_context_args}

    if os.environ.get("RECORD_VIDEO", "").lower() == "true":
        video_dir = pathlib.Path("reports/videos") / request.node.name
        video_dir.mkdir(parents=True, exist_ok=True)
        args["record_video_dir"] = str(video_dir)
        args["record_video_size"] = {"width": 2400, "height": 1600}

    return args
