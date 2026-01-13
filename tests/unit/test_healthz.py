#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""healthz のテスト"""

from __future__ import annotations


class TestCheckLiveness:
    """check_liveness のテスト"""

    def test_returns_true_when_all_healthy(self, mocker):
        """全てのターゲットが健全な場合 True を返す"""
        from my_lib.healthz import HealthzTarget

        from healthz import check_liveness

        mocker.patch("my_lib.healthz.check_liveness_all", return_value=[])

        targets = [
            HealthzTarget(name="test1", liveness_file="/tmp/test1", interval=60),
            HealthzTarget(name="test2", liveness_file="/tmp/test2", interval=60),
        ]

        result = check_liveness(targets)

        assert result is True

    def test_returns_false_when_some_failed(self, mocker):
        """一部のターゲットが失敗した場合 False を返す"""
        from my_lib.healthz import HealthzTarget

        from healthz import check_liveness

        mocker.patch("my_lib.healthz.check_liveness_all", return_value=["test1"])

        targets = [
            HealthzTarget(name="test1", liveness_file="/tmp/test1", interval=60),
        ]

        result = check_liveness(targets)

        assert result is False

    def test_checks_http_port_when_provided(self, mocker):
        """ポートが指定された場合、HTTP ポートもチェックする"""
        from my_lib.healthz import HealthzTarget

        from healthz import check_liveness

        mocker.patch("my_lib.healthz.check_liveness_all", return_value=[])
        mock_check_http = mocker.patch("my_lib.healthz.check_http_port", return_value=True)

        targets = [
            HealthzTarget(name="test1", liveness_file="/tmp/test1", interval=60),
        ]

        result = check_liveness(targets, port=5000)

        assert result is True
        mock_check_http.assert_called_once_with(5000)

    def test_returns_false_when_http_port_fails(self, mocker):
        """HTTP ポートチェックが失敗した場合 False を返す"""
        from my_lib.healthz import HealthzTarget

        from healthz import check_liveness

        mocker.patch("my_lib.healthz.check_liveness_all", return_value=[])
        mocker.patch("my_lib.healthz.check_http_port", return_value=False)

        targets = [
            HealthzTarget(name="test1", liveness_file="/tmp/test1", interval=60),
        ]

        result = check_liveness(targets, port=5000)

        assert result is False

    def test_skips_http_port_when_not_provided(self, mocker):
        """ポートが指定されない場合、HTTP ポートをチェックしない"""
        from my_lib.healthz import HealthzTarget

        from healthz import check_liveness

        mocker.patch("my_lib.healthz.check_liveness_all", return_value=[])
        mock_check_http = mocker.patch("my_lib.healthz.check_http_port")

        targets = [
            HealthzTarget(name="test1", liveness_file="/tmp/test1", interval=60),
        ]

        result = check_liveness(targets, port=None)

        assert result is True
        mock_check_http.assert_not_called()
