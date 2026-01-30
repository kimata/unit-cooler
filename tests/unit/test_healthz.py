#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""healthz のテスト"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import my_lib.healthz


class TestGetLivenessTargets:
    """get_liveness_targets のテスト"""

    def test_returns_controller_target_for_ctrl_mode(self):
        """CTRL モードの場合、controller ターゲットを返す"""
        from healthz import get_liveness_targets

        config = MagicMock()
        config.controller.liveness.file = pathlib.Path("/dev/shm/healthz.controller")
        config.controller.interval_sec = 60

        targets = get_liveness_targets(config, "CTRL")

        assert len(targets) == 1
        assert targets[0].name == "controller"
        assert targets[0].liveness_file == pathlib.Path("/dev/shm/healthz.controller")
        assert targets[0].interval == 60

    def test_returns_webui_target_for_web_mode(self):
        """WEB モードの場合、webui ターゲットを返す"""
        from healthz import get_liveness_targets

        config = MagicMock()
        config.webui.subscribe.liveness.file = pathlib.Path("/dev/shm/healthz.webui")
        config.controller.interval_sec = 60

        targets = get_liveness_targets(config, "WEB")

        assert len(targets) == 1
        assert targets[0].name == "webui - subscribe"
        assert targets[0].liveness_file == pathlib.Path("/dev/shm/healthz.webui")

    def test_returns_actuator_targets_for_act_mode(self):
        """ACT モードの場合、actuator ターゲットを返す"""
        from healthz import get_liveness_targets

        config = MagicMock()
        config.controller.interval_sec = 60
        config.actuator.subscribe.liveness.file = pathlib.Path("/dev/shm/healthz.subscribe")
        config.actuator.control.liveness.file = pathlib.Path("/dev/shm/healthz.control")
        config.actuator.control.interval_sec = 30
        config.actuator.monitor.liveness.file = pathlib.Path("/dev/shm/healthz.monitor")
        config.actuator.monitor.interval_sec = 10

        targets = get_liveness_targets(config, "ACT")

        assert len(targets) == 3
        assert targets[0].name == "actuator - subscribe"
        assert targets[1].name == "actuator - control"
        assert targets[2].name == "actuator - monitor"

    def test_returns_healthz_target_instances(self):
        """HealthzTarget インスタンスを返す"""
        from healthz import get_liveness_targets

        config = MagicMock()
        config.controller.liveness.file = pathlib.Path("/dev/shm/healthz.controller")
        config.controller.interval_sec = 60

        targets = get_liveness_targets(config, "CTRL")

        assert all(isinstance(t, my_lib.healthz.HealthzTarget) for t in targets)
