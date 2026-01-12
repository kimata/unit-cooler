#!/usr/bin/env python3
"""単体テスト用 conftest.py

単体テスト専用の fixture を定義する。
"""

from __future__ import annotations

import pathlib

import pytest

from unit_cooler.config import Config

CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "config.schema"


@pytest.fixture
def config() -> Config:
    """Config オブジェクト"""
    return Config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))
