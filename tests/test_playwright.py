#!/usr/bin/env python3
from playwright.sync_api import expect

APP_URL_TMPL = "http://{host}:{port}/unit-cooler/"


def app_url(host, port):
    return APP_URL_TMPL.format(host=host, port=port)


def init(page):
    page.on("console", lambda msg: print(msg.text))  # noqa: T201
    page.set_viewport_size({"width": 2400, "height": 1600})


######################################################################
def test_valve(page, host, port):
    init(page)
    page.goto(app_url(host, port))

    expect(page.get_by_test_id("aircon-info")).to_have_count(1)
    expect(page.get_by_test_id("sensor-info")).to_have_count(1)
    expect(page.get_by_test_id("watering-amount-info")).to_have_count(1)
    expect(page.get_by_test_id("watering-price-info")).to_have_count(1)
    expect(page.get_by_test_id("history-info")).to_have_count(1)
    expect(page.get_by_test_id("cooling-info")).to_have_count(1, timeout=100 * 1000)
    expect(page.get_by_test_id("log")).to_have_count(1)

    expect(page.get_by_test_id("error")).to_have_count(0)
