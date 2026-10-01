#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.state_file のテスト（WebUI 由来の状態の永続化）"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import unit_cooler.actuator.state_file


class TestGetPath:
    """get_path のテスト"""

    def test_file_is_next_to_hazard_file(self, tmp_path):
        """ハザードファイルと同じディレクトリに配置される"""
        config = MagicMock()
        config.actuator.control.hazard.file = tmp_path / "unit_cooler.hazard"

        path = unit_cooler.actuator.state_file.get_path(config, "state.json")

        assert path.parent == tmp_path
        assert "state.json" in path.name


class TestSaveLoad:
    """save / load のテスト"""

    def test_round_trip(self, tmp_path):
        """save したデータを load で読み戻せる"""
        path = tmp_path / "state.json"

        unit_cooler.actuator.state_file.save(path, {"value": 1})

        assert unit_cooler.actuator.state_file.load(path, lambda data: data["value"]) == 1

    def test_save_creates_parent_directory(self, tmp_path):
        """親ディレクトリがなければ作成する"""
        path = tmp_path / "sub" / "state.json"

        unit_cooler.actuator.state_file.save(path, {"value": 1})

        assert path.exists()

    def test_save_leaves_no_temporary_file(self, tmp_path):
        """置き換え後に一時ファイルを残さない"""
        path = tmp_path / "state.json"

        unit_cooler.actuator.state_file.save(path, {"value": 1})

        assert list(tmp_path.iterdir()) == [path]

    def test_load_returns_none_when_missing(self, tmp_path):
        """ファイルがなければ None"""
        assert unit_cooler.actuator.state_file.load(tmp_path / "state.json", lambda data: data) is None

    def test_load_returns_none_when_json_is_broken(self, tmp_path):
        """JSON として壊れていれば None"""
        path = tmp_path / "state.json"
        path.write_text("{ broken json")

        assert unit_cooler.actuator.state_file.load(path, lambda data: data) is None

    def test_load_returns_none_when_parse_fails(self, tmp_path):
        """parse が失敗（キー欠落など）すれば None"""
        path = tmp_path / "state.json"
        unit_cooler.actuator.state_file.save(path, {"other": 1})

        assert unit_cooler.actuator.state_file.load(path, lambda data: data["value"]) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
