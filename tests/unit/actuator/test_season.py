#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.season のテスト（稼働期間 = 散水を行う季節）"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

import unit_cooler.actuator.season
from unit_cooler.actuator.season import MonthDay, SeasonSetting


@pytest.fixture
def config_mock(tmp_path):
    """hazard ファイルが tmp_path 配下にある config のモック"""
    config = MagicMock()
    config.actuator.control.hazard.file = tmp_path / "unit_cooler.hazard"
    return config


class TestMonthDay:
    """MonthDay のテスト"""

    @pytest.mark.parametrize(("month", "day"), [(1, 1), (2, 29), (4, 30), (12, 31)])
    def test_accepts_valid_date(self, month, day):
        """実在する月日は受け付ける（2月29日を含む）"""
        assert MonthDay(month, day).to_dict() == {"month": month, "day": day}

    @pytest.mark.parametrize(("month", "day"), [(0, 1), (13, 1), (1, 0), (2, 30), (4, 31), (12, 32)])
    def test_rejects_invalid_date(self, month, day):
        """存在しない月日は拒否する"""
        with pytest.raises(ValueError, match="must be between"):
            MonthDay(month, day)

    def test_ordering(self):
        """月 → 日の順で比較される"""
        assert MonthDay(4, 30) < MonthDay(5, 1)
        assert MonthDay(5, 1) < MonthDay(5, 2)

    @pytest.mark.parametrize(
        "data",
        [
            {"month": "5", "day": 1},
            {"month": 5, "day": 1.0},
            {"month": True, "day": 1},
        ],
    )
    def test_parse_rejects_non_integer(self, data):
        """整数以外（文字列・小数・bool）は拒否する"""
        with pytest.raises(ValueError, match="must be an integer"):
            MonthDay.parse(data)


class TestSeasonSettingContains:
    """SeasonSetting.contains のテスト"""

    def test_disabled_always_contains(self):
        """無効時は通年稼働"""
        setting = SeasonSetting(enabled=False, start=MonthDay(5, 1), end=MonthDay(10, 31))

        assert setting.contains(datetime.date(2026, 1, 15)) is True

    @pytest.mark.parametrize(
        ("date", "expected"),
        [
            (datetime.date(2026, 4, 30), False),
            (datetime.date(2026, 5, 1), True),  # 開始日は含む
            (datetime.date(2026, 8, 15), True),
            (datetime.date(2026, 10, 31), True),  # 終了日は含む
            (datetime.date(2026, 11, 1), False),
            (datetime.date(2027, 1, 15), False),
        ],
    )
    def test_normal_range(self, date, expected):
        """開始 <= 終了 の期間（5月1日〜10月31日）"""
        setting = SeasonSetting(enabled=True, start=MonthDay(5, 1), end=MonthDay(10, 31))

        assert setting.contains(date) is expected

    @pytest.mark.parametrize(
        ("date", "expected"),
        [
            (datetime.date(2026, 10, 31), False),
            (datetime.date(2026, 11, 1), True),
            (datetime.date(2026, 12, 31), True),
            (datetime.date(2027, 1, 1), True),
            (datetime.date(2027, 3, 31), True),
            (datetime.date(2027, 4, 1), False),
        ],
    )
    def test_range_across_year_end(self, date, expected):
        """開始 > 終了 は年をまたぐ期間（11月1日〜3月31日）"""
        setting = SeasonSetting(enabled=True, start=MonthDay(11, 1), end=MonthDay(3, 31))

        assert setting.contains(date) is expected

    def test_same_start_and_end_is_single_day(self):
        """開始 = 終了 はその 1 日だけ稼働"""
        setting = SeasonSetting(enabled=True, start=MonthDay(7, 1), end=MonthDay(7, 1))

        assert setting.contains(datetime.date(2026, 7, 1)) is True
        assert setting.contains(datetime.date(2026, 7, 2)) is False

    def test_feb_29_boundary_in_common_year(self):
        """2月29日を境界にしても平年で破綻しない"""
        ends_feb_29 = SeasonSetting(enabled=True, start=MonthDay(1, 1), end=MonthDay(2, 29))
        starts_feb_29 = SeasonSetting(enabled=True, start=MonthDay(2, 29), end=MonthDay(12, 31))

        # 2027 年は平年
        assert ends_feb_29.contains(datetime.date(2027, 2, 28)) is True
        assert ends_feb_29.contains(datetime.date(2027, 3, 1)) is False
        assert starts_feb_29.contains(datetime.date(2027, 2, 28)) is False
        assert starts_feb_29.contains(datetime.date(2027, 3, 1)) is True


class TestSeasonSettingParse:
    """SeasonSetting の parse / to_dict のテスト"""

    def test_round_trip(self):
        """to_dict → parse で往復できる"""
        setting = SeasonSetting(enabled=True, start=MonthDay(5, 1), end=MonthDay(10, 31))

        assert SeasonSetting.parse(setting.to_dict()) == setting

    def test_rejects_non_boolean_enabled(self):
        """enabled が bool でなければ拒否する"""
        with pytest.raises(ValueError, match="enabled"):
            SeasonSetting.parse(
                {"enabled": 1, "start": {"month": 5, "day": 1}, "end": {"month": 10, "day": 31}}
            )

    def test_rejects_missing_key(self):
        """キー欠落は KeyError"""
        with pytest.raises(KeyError):
            SeasonSetting.parse({"enabled": True, "start": {"month": 5, "day": 1}})


class TestPersistence:
    """get_setting / set_setting のテスト"""

    def test_default_is_all_year(self, config_mock):
        """未設定なら通年稼働"""
        setting = unit_cooler.actuator.season.get_setting(config_mock)

        assert setting == SeasonSetting.default()
        assert setting.enabled is False

    def test_file_is_next_to_hazard_file(self, config_mock, tmp_path):
        """ハザードファイルと同じディレクトリ（永続領域）に配置される"""
        path = unit_cooler.actuator.season.get_file_path(config_mock)

        assert path.parent == tmp_path
        assert unit_cooler.actuator.season.SEASON_FILE_NAME in path.name

    def test_persists_setting(self, config_mock):
        """設定がファイルに永続化され、読み戻せる（再起動を跨いだ保持の担保）"""
        setting = SeasonSetting(enabled=True, start=MonthDay(5, 1), end=MonthDay(10, 31))

        unit_cooler.actuator.season.set_setting(config_mock, setting)

        assert unit_cooler.actuator.season.get_file_path(config_mock).exists()
        assert unit_cooler.actuator.season.get_setting(config_mock) == setting

    def test_broken_file_falls_back_to_all_year(self, config_mock):
        """破損したファイルは無視して通年稼働にする"""
        path = unit_cooler.actuator.season.get_file_path(config_mock)
        path.write_text('{"enabled": true, "start": {"month": 13, "day": 1}, "end": {"month": 1, "day": 1}}')

        assert unit_cooler.actuator.season.get_setting(config_mock) == SeasonSetting.default()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
