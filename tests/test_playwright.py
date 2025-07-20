#!/usr/bin/env python3
import logging
import time

import pytest
import requests
from playwright.sync_api import expect

APP_URL_TMPL = "http://{host}:{port}/unit-cooler/"


@pytest.fixture(autouse=True)
def _page_init(page, host, port):
    wait_for_server_ready(host, port)

    time.sleep(5)

    page.on("console", lambda msg: print(msg.text))  # noqa: T201
    page.set_viewport_size({"width": 2400, "height": 1600})


def wait_for_server_ready(host, port):
    TIMEOUT_SEC = 30

    start_time = time.time()
    while time.time() - start_time < TIMEOUT_SEC:
        try:
            res = requests.get(app_url(host, port))  # noqa: S113
            if res.ok:
                logging.info("サーバが %.1f 秒後に起動しました。", time.time() - start_time)
                return
        except Exception:  # noqa: S110
            pass
        time.sleep(1)

    raise RuntimeError(f"サーバーが {TIMEOUT_SEC}秒以内に起動しませんでした。")  # noqa: TRY003, EM102


def app_url(host, port):
    return APP_URL_TMPL.format(host=host, port=port)


######################################################################
def test_valve(page, host, port):
    page.goto(app_url(host, port))

    expect(page.get_by_test_id("aircon-info")).to_have_count(1)
    expect(page.get_by_test_id("sensor-info")).to_have_count(1)
    expect(page.get_by_test_id("watering-amount-info")).to_have_count(1)
    expect(page.get_by_test_id("watering-price-info")).to_have_count(1)
    expect(page.get_by_test_id("history-info")).to_have_count(1)
    expect(page.get_by_test_id("cooling-info")).to_have_count(1, timeout=100 * 1000)
    expect(page.get_by_test_id("log")).to_have_count(1)

    expect(page.get_by_test_id("error")).to_have_count(0)
