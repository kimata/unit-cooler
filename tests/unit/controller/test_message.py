#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.controller.message のテスト"""

from unit_cooler.const import COOLING_STATE
from unit_cooler.controller.message import CONTROL_MESSAGE_LIST, print_control_msg


class TestControlMessageList:
    """CONTROL_MESSAGE_LIST のテスト"""

    def test_list_length(self):
        """9 エントリが存在"""
        assert len(CONTROL_MESSAGE_LIST) == 9

    def test_first_entry_is_idle(self):
        """最初のエントリは IDLE"""
        first = CONTROL_MESSAGE_LIST[0]
        assert first["state"] == COOLING_STATE.IDLE
        assert first["duty"]["enable"] is False

    def test_other_entries_are_working(self):
        """2 番目以降は WORKING"""
        for i, msg in enumerate(CONTROL_MESSAGE_LIST[1:], start=1):
            assert msg["state"] == COOLING_STATE.WORKING, f"Entry {i} should be WORKING"
            assert msg["duty"]["enable"] is True, f"Entry {i} duty should be enabled"

    def test_duty_structure(self):
        """duty 構造が正しい"""
        for i, msg in enumerate(CONTROL_MESSAGE_LIST):
            duty = msg["duty"]
            assert "enable" in duty, f"Entry {i} missing 'enable'"
            assert "on_sec" in duty, f"Entry {i} missing 'on_sec'"
            assert "off_sec" in duty, f"Entry {i} missing 'off_sec'"

    def test_duty_on_sec_increases(self):
        """on_sec は増加する (WORKING エントリのみ)"""
        working_entries = CONTROL_MESSAGE_LIST[1:]
        on_secs = [msg["duty"]["on_sec"] for msg in working_entries]
        assert on_secs == sorted(on_secs), "on_sec should increase"

    def test_duty_off_sec_decreases(self):
        """off_sec は減少する (WORKING エントリのみ)"""
        working_entries = CONTROL_MESSAGE_LIST[1:]
        off_secs = [msg["duty"]["off_sec"] for msg in working_entries]
        assert off_secs == sorted(off_secs, reverse=True), "off_sec should decrease"

    def test_total_duration_is_15_minutes(self):
        """WORKING エントリの合計は 15 分"""
        for msg in CONTROL_MESSAGE_LIST[1:]:
            duty = msg["duty"]
            total = duty["on_sec"] + duty["off_sec"]
            assert total == 15 * 60, f"Total should be 900 sec (15 min), got {total}"

    def test_idle_entry_has_zero_duration(self):
        """IDLE エントリは 0 秒"""
        idle = CONTROL_MESSAGE_LIST[0]
        assert idle["duty"]["on_sec"] == 0
        assert idle["duty"]["off_sec"] == 0


class TestPrintControlMsg:
    """print_control_msg のテスト"""

    def test_runs_without_error(self, caplog):
        """エラーなく実行できる"""
        import logging

        with caplog.at_level(logging.INFO):
            print_control_msg()
        # ログが出力されることを確認
        assert len(caplog.records) > 0

    def test_logs_all_entries(self, caplog):
        """全エントリをログ出力"""
        import logging

        with caplog.at_level(logging.INFO):
            print_control_msg()
        # 9 エントリ分のログ
        state_logs = [r for r in caplog.records if "state:" in r.message]
        assert len(state_logs) == 9
