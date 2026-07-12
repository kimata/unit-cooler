#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.webapi.hazard / override のテスト"""

from __future__ import annotations

import datetime
import multiprocessing

import my_lib.footprint
import pytest

import unit_cooler.actuator.control
import unit_cooler.actuator.web_server

URL_PREFIX = "/unit-cooler"


@pytest.fixture
def client(config, mocker):
    """actuator Web サーバーのテストクライアント"""
    mocker.patch("my_lib.webapp.config.build_environment")
    mocker.patch("my_lib.webapp.log.init")
    mocker.patch("my_lib.webapp.event.start")
    mocker.patch("unit_cooler.actuator.web_server.get_metrics_collector")

    app = unit_cooler.actuator.web_server.create_app(config, multiprocessing.Queue())
    app.config["TESTING"] = True

    return app.test_client()


@pytest.fixture
def override_file(mocker, tmp_path):
    """オーバーライドの永続化先を tmp_path に隔離する"""
    path = tmp_path / "unit_cooler.override.json"
    mocker.patch("unit_cooler.actuator.override.get_file_path", return_value=path)
    return path


class TestHazardApi:
    """/api/hazard のテスト"""

    def test_get_returns_false_when_no_hazard(self, client, config):
        """ハザードなしで hazard=False"""
        unit_cooler.actuator.control.hazard_clear(config)

        response = client.get(f"{URL_PREFIX}/api/hazard")

        assert response.status_code == 200
        assert response.json == {"hazard": False, "registered_at": None}

    def test_get_returns_true_with_registered_at(self, client, config):
        """ハザードありで hazard=True と登録時刻（ISO 文字列）を返す"""
        unit_cooler.actuator.control.hazard_register(config)

        response = client.get(f"{URL_PREFIX}/api/hazard")

        assert response.status_code == 200
        assert response.json["hazard"] is True
        # ISO 文字列としてパースできること
        datetime.datetime.fromisoformat(response.json["registered_at"])

    def test_clear_removes_latch_and_logs(self, client, config, mocker):
        """clear でラッチが解除され work_log に記録される"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        unit_cooler.actuator.control.hazard_register(config)

        response = client.post(f"{URL_PREFIX}/api/hazard/clear")

        assert response.status_code == 200
        assert response.json == {"hazard": False}
        assert my_lib.footprint.exists(config.actuator.control.hazard.file) is False
        mock_add.assert_called_once()


class TestOverrideApi:
    """/api/override のテスト"""

    def test_get_returns_disabled_initially(self, client, override_file):
        """未設定なら enabled=False"""
        response = client.get(f"{URL_PREFIX}/api/override")

        assert response.status_code == 200
        assert response.json == {"enabled": False, "until": None}

    def test_post_sets_override(self, client, override_file, mocker):
        """設定すると enabled=True と失効時刻を返し、ファイルに永続化する"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")

        response = client.post(f"{URL_PREFIX}/api/override", json={"duration_min": 30})

        assert response.status_code == 200
        assert response.json["enabled"] is True
        datetime.datetime.fromisoformat(response.json["until"])
        assert override_file.exists()
        mock_add.assert_called_once()

        # GET でも同じ状態が見える
        get_response = client.get(f"{URL_PREFIX}/api/override")
        assert get_response.json["enabled"] is True

    @pytest.mark.parametrize(
        "body",
        [
            {"duration_min": 0},
            {"duration_min": 1441},
            {"duration_min": "30"},
            {"duration_min": True},
            {},
        ],
    )
    def test_post_rejects_invalid_duration(self, client, override_file, body):
        """1〜1440 の整数以外は 400 を返す"""
        response = client.post(f"{URL_PREFIX}/api/override", json=body)

        assert response.status_code == 400
        assert "error" in response.json
        assert not override_file.exists()

    @pytest.mark.parametrize("duration_min", [1, 1440])
    def test_post_accepts_boundary_duration(self, client, override_file, mocker, duration_min):
        """境界値（1 分・1440 分）は受け付ける"""
        mocker.patch("unit_cooler.actuator.work_log.add")

        response = client.post(f"{URL_PREFIX}/api/override", json={"duration_min": duration_min})

        assert response.status_code == 200
        assert response.json["enabled"] is True

    def test_clear_disables_override(self, client, override_file, mocker):
        """clear で解除され enabled=False を返す"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        client.post(f"{URL_PREFIX}/api/override", json={"duration_min": 30})

        response = client.post(f"{URL_PREFIX}/api/override/clear")

        assert response.status_code == 200
        assert response.json == {"enabled": False, "until": None}
        assert not override_file.exists()
        # 設定時と解除時の 2 回記録される
        assert mock_add.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
