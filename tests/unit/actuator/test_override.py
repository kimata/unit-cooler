#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.override のテスト（手動オーバーライド = 強制 OFF）"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import my_lib.time
import pytest

import unit_cooler.actuator.override


@pytest.fixture
def config_mock(tmp_path):
    """hazard ファイルが tmp_path 配下にある config のモック"""
    config = MagicMock()
    config.actuator.control.hazard.file = tmp_path / "unit_cooler.hazard"
    return config


class TestGetFilePath:
    """get_file_path のテスト"""

    def test_file_is_next_to_hazard_file(self, config_mock, tmp_path):
        """ハザードファイルと同じディレクトリに配置される"""
        path = unit_cooler.actuator.override.get_file_path(config_mock)

        assert path.parent == tmp_path
        assert unit_cooler.actuator.override.OVERRIDE_FILE_NAME in path.name


class TestSetOverride:
    """set_override のテスト"""

    def test_persists_state_to_file(self, config_mock):
        """状態をファイルに永続化する"""
        state = unit_cooler.actuator.override.set_override(config_mock, 30)

        path = unit_cooler.actuator.override.get_file_path(config_mock)
        assert path.exists()
        # ファイルから復元した状態が一致する（再起動を跨いだ永続化の担保）
        restored = unit_cooler.actuator.override.get_override(config_mock)
        assert restored == state

    def test_until_is_duration_min_later(self, config_mock):
        """失効時刻は duration_min 分後になる"""
        before = my_lib.time.now()
        state = unit_cooler.actuator.override.set_override(config_mock, 30)
        after = my_lib.time.now()

        assert before + datetime.timedelta(minutes=30) <= state.until
        assert state.until <= after + datetime.timedelta(minutes=30)

    @pytest.mark.parametrize("duration_min", [0, -1, 1441])
    def test_rejects_out_of_range_duration(self, config_mock, duration_min):
        """範囲外（1〜1440 以外）の duration_min は拒否する"""
        with pytest.raises(ValueError, match="duration_min"):
            unit_cooler.actuator.override.set_override(config_mock, duration_min)

    @pytest.mark.parametrize("duration_min", [1, 1440])
    def test_accepts_boundary_duration(self, config_mock, duration_min):
        """境界値（1 分・1440 分）は受け付ける"""
        state = unit_cooler.actuator.override.set_override(config_mock, duration_min)

        assert state is not None


class TestGetOverride:
    """get_override / is_active のテスト"""

    def test_returns_none_when_not_set(self, config_mock):
        """未設定なら None"""
        assert unit_cooler.actuator.override.get_override(config_mock) is None
        assert unit_cooler.actuator.override.is_active(config_mock) is False

    def test_active_while_not_expired(self, config_mock):
        """失効前は有効"""
        unit_cooler.actuator.override.set_override(config_mock, 30)

        assert unit_cooler.actuator.override.is_active(config_mock) is True

    def test_expired_override_is_inactive_and_removed(self, config_mock):
        """失効時刻を過ぎたら自動で無効になり、ファイルも削除される"""
        path = unit_cooler.actuator.override.get_file_path(config_mock)
        path.parent.mkdir(parents=True, exist_ok=True)
        expired = unit_cooler.actuator.override.OverrideState(
            until=my_lib.time.now() - datetime.timedelta(minutes=1)
        )
        path.write_text(expired.to_json())

        assert unit_cooler.actuator.override.get_override(config_mock) is None
        assert not path.exists()

    def test_broken_file_is_ignored(self, config_mock):
        """破損したファイルは無視して None"""
        path = unit_cooler.actuator.override.get_file_path(config_mock)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ broken json")

        assert unit_cooler.actuator.override.get_override(config_mock) is None


class TestClearOverride:
    """clear_override のテスト"""

    def test_clears_state(self, config_mock):
        """解除でファイルが削除され無効になる"""
        unit_cooler.actuator.override.set_override(config_mock, 30)

        unit_cooler.actuator.override.clear_override(config_mock)

        assert unit_cooler.actuator.override.is_active(config_mock) is False
        assert not unit_cooler.actuator.override.get_file_path(config_mock).exists()

    def test_clear_without_set_is_noop(self, config_mock):
        """未設定状態での解除は何もしない（例外を送出しない）"""
        unit_cooler.actuator.override.clear_override(config_mock)


class TestOverrideState:
    """OverrideState の parse / to_json のテスト"""

    def test_round_trip(self):
        """to_json → parse で往復できる"""
        import json

        state = unit_cooler.actuator.override.OverrideState(until=my_lib.time.now())

        restored = unit_cooler.actuator.override.OverrideState.parse(json.loads(state.to_json()))

        assert restored == state


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
