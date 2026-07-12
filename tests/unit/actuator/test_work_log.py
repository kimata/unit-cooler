#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.work_log のテスト"""

from __future__ import annotations

import multiprocessing

import pytest

import unit_cooler.actuator.work_log
from unit_cooler.const import LOG_LEVEL


class TestWorkLogInit:
    """work_log.init のテスト"""

    def test_init_sets_config(self, config):
        """init で config を設定"""
        queue = multiprocessing.Queue()

        unit_cooler.actuator.work_log.init(config, queue)

        assert unit_cooler.actuator.work_log.config == config

    def test_init_sets_event_queue(self, config):
        """init で event_queue を設定"""
        queue = multiprocessing.Queue()

        unit_cooler.actuator.work_log.init(config, queue)

        assert unit_cooler.actuator.work_log.event_queue == queue


class TestWorkLogTerm:
    """work_log.term のテスト"""

    def test_term_calls_webapp_log_term(self, mocker):
        """term で webapp.log.term を呼ぶ"""
        mock_term = mocker.patch("my_lib.webapp.log.term")

        unit_cooler.actuator.work_log.term()

        mock_term.assert_called_once()


class TestWorkLogHistClear:
    """work_log.hist_clear のテスト"""

    def test_clears_history(self):
        """履歴をクリア"""
        unit_cooler.actuator.work_log.log_hist.extend(["message1", "message2"])

        unit_cooler.actuator.work_log.hist_clear()

        assert list(unit_cooler.actuator.work_log.log_hist) == []


class TestWorkLogHistGet:
    """work_log.hist_get のテスト"""

    def test_returns_history(self):
        """履歴を返す"""
        unit_cooler.actuator.work_log.hist_clear()
        expected = ["message1", "message2"]
        unit_cooler.actuator.work_log.log_hist.extend(expected)

        result = unit_cooler.actuator.work_log.hist_get()

        assert result == expected


class TestWorkLogHistBounded:
    """log_hist の上限のテスト（メモリリーク防止）"""

    def test_hist_does_not_grow_unbounded(self, mocker):
        """上限を超えた古い履歴は捨てられる"""
        mocker.patch("my_lib.webapp.log.add")
        unit_cooler.actuator.work_log.hist_clear()

        for i in range(unit_cooler.actuator.work_log.LOG_HIST_MAX + 10):
            unit_cooler.actuator.work_log.add(f"メッセージ {i}")

        hist = unit_cooler.actuator.work_log.hist_get()
        assert len(hist) == unit_cooler.actuator.work_log.LOG_HIST_MAX
        # 古いものから捨てられる
        assert hist[-1] == f"メッセージ {unit_cooler.actuator.work_log.LOG_HIST_MAX + 9}"


class TestWorkLogAdd:
    """work_log.add のテスト"""

    def setup_method(self):
        """各テスト前に履歴をクリア"""
        unit_cooler.actuator.work_log.hist_clear()
        unit_cooler.actuator.work_log.config = None
        unit_cooler.actuator.work_log.event_queue = None

    def test_adds_to_history(self, mocker):
        """履歴にメッセージを追加"""
        mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("テストメッセージ")

        hist = unit_cooler.actuator.work_log.hist_get()
        assert "テストメッセージ" in hist

    def test_calls_webapp_log_add(self, mocker):
        """webapp.log.add を呼ぶ"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("テストメッセージ", LOG_LEVEL.INFO)

        mock_add.assert_called_once_with("テストメッセージ", LOG_LEVEL.INFO)

    def test_puts_event_to_queue(self, config, mocker):
        """キューにイベントを送信"""
        mocker.patch("my_lib.webapp.log.add")
        queue = multiprocessing.Queue()
        unit_cooler.actuator.work_log.init(config, queue)

        unit_cooler.actuator.work_log.add("テストメッセージ")

        # キューにイベントが入っているか確認
        import my_lib.webapp.event

        event = queue.get(timeout=1)
        assert event == my_lib.webapp.event.EVENT_TYPE.LOG

    def test_error_level_calls_notify_error(self, config, mocker):
        """ERROR レベルで notify_error を呼ぶ"""
        mocker.patch("my_lib.webapp.log.add")
        mock_notify = mocker.patch("unit_cooler.util.notify_error")
        queue = multiprocessing.Queue()
        unit_cooler.actuator.work_log.init(config, queue)

        unit_cooler.actuator.work_log.add("エラーメッセージ", LOG_LEVEL.ERROR)

        mock_notify.assert_called_once_with(config, "エラーメッセージ")

    def test_info_level_does_not_call_notify_error(self, config, mocker):
        """INFO レベルで notify_error を呼ばない"""
        mocker.patch("my_lib.webapp.log.add")
        mock_notify = mocker.patch("unit_cooler.util.notify_error")
        queue = multiprocessing.Queue()
        unit_cooler.actuator.work_log.init(config, queue)

        unit_cooler.actuator.work_log.add("情報メッセージ", LOG_LEVEL.INFO)

        mock_notify.assert_not_called()

    def test_warn_level_does_not_call_notify_error(self, config, mocker):
        """WARN レベルで notify_error を呼ばない"""
        mocker.patch("my_lib.webapp.log.add")
        mock_notify = mocker.patch("unit_cooler.util.notify_error")
        queue = multiprocessing.Queue()
        unit_cooler.actuator.work_log.init(config, queue)

        unit_cooler.actuator.work_log.add("警告メッセージ", LOG_LEVEL.WARN)

        mock_notify.assert_not_called()

    def test_default_level_is_info(self, mocker):
        """デフォルトレベルは INFO"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("テストメッセージ")

        mock_add.assert_called_once_with("テストメッセージ", LOG_LEVEL.INFO)

    def test_no_queue_no_error(self, mocker):
        """キューなしでエラーなし"""
        mocker.patch("my_lib.webapp.log.add")
        unit_cooler.actuator.work_log.event_queue = None

        # 例外が発生しないことを確認
        unit_cooler.actuator.work_log.add("テストメッセージ")

    def test_no_config_no_notify_error(self, mocker):
        """config なしで notify_error を呼ばない"""
        mocker.patch("my_lib.webapp.log.add")
        mock_notify = mocker.patch("unit_cooler.util.notify_error")
        unit_cooler.actuator.work_log.config = None

        unit_cooler.actuator.work_log.add("エラーメッセージ", LOG_LEVEL.ERROR)

        mock_notify.assert_not_called()


class TestWorkLogMultipleMessages:
    """複数メッセージのテスト"""

    def setup_method(self):
        """各テスト前に履歴をクリア"""
        unit_cooler.actuator.work_log.hist_clear()

    def test_multiple_messages_in_order(self, mocker):
        """複数メッセージが順序通りに記録される"""
        mocker.patch("my_lib.webapp.log.add")

        messages = ["メッセージ1", "メッセージ2", "メッセージ3"]
        for msg in messages:
            unit_cooler.actuator.work_log.add(msg)

        hist = unit_cooler.actuator.work_log.hist_get()
        assert hist == messages

    def test_history_persists_after_multiple_adds(self, mocker):
        """複数追加後も履歴が保持される"""
        mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("最初")
        unit_cooler.actuator.work_log.add("次")

        hist = unit_cooler.actuator.work_log.hist_get()
        assert len(hist) == 2
        assert "最初" in hist
        assert "次" in hist


class TestWorkLogSuppress:
    """同一メッセージの抑制間隔のテスト"""

    def setup_method(self):
        """各テスト前に履歴と抑制状態をクリア"""
        unit_cooler.actuator.work_log.hist_clear()
        unit_cooler.actuator.work_log.config = None
        unit_cooler.actuator.work_log.event_queue = None

    def test_suppresses_same_message_within_interval(self, mocker):
        """間隔内の同一メッセージは記録しない"""
        mock_add = mocker.patch("my_lib.webapp.log.add")
        mocker.patch("time.monotonic", side_effect=[1000.0, 1000.0 + 60])

        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)
        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)

        assert mock_add.call_count == 1
        assert unit_cooler.actuator.work_log.hist_get() == ["同じメッセージ"]

    @pytest.mark.parametrize(
        "elapsed_min,should_record",
        [
            (29, False),  # 29分 < 30分
            (30, False),  # 30分 = 30分 (境界)
            (31, True),  # 31分 > 30分
        ],
    )
    def test_suppress_interval_boundary(self, mocker, elapsed_min, should_record):
        """抑制間隔の境界テスト"""
        mock_add = mocker.patch("my_lib.webapp.log.add")
        mocker.patch("time.monotonic", side_effect=[1000.0, 1000.0 + elapsed_min * 60])

        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)
        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)

        assert mock_add.call_count == (2 if should_record else 1)

    def test_different_messages_not_suppressed(self, mocker):
        """異なるメッセージは抑制しない"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("メッセージ A", suppress_interval_min=30)
        unit_cooler.actuator.work_log.add("メッセージ B", suppress_interval_min=30)

        assert mock_add.call_count == 2

    def test_suppress_key_groups_variable_messages(self, mocker):
        """可変値を含むメッセージも suppress_key 単位で抑制する"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add(
            "流量が 1.0 L/min", suppress_interval_min=30, suppress_key="流量異常"
        )
        unit_cooler.actuator.work_log.add(
            "流量が 2.0 L/min", suppress_interval_min=30, suppress_key="流量異常"
        )

        assert mock_add.call_count == 1

    def test_no_interval_always_records(self, mocker):
        """suppress_interval_min 未指定なら常に記録する"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("同じメッセージ")
        unit_cooler.actuator.work_log.add("同じメッセージ")

        assert mock_add.call_count == 2

    def test_suppressed_error_skips_notify(self, config, mocker):
        """抑制された ERROR は Slack 通知もメトリクス記録もしない"""
        mocker.patch("my_lib.webapp.log.add")
        mock_notify = mocker.patch("unit_cooler.util.notify_error")
        queue = multiprocessing.Queue()
        unit_cooler.actuator.work_log.init(config, queue)

        unit_cooler.actuator.work_log.add("エラー", LOG_LEVEL.ERROR, suppress_interval_min=30)
        unit_cooler.actuator.work_log.add("エラー", LOG_LEVEL.ERROR, suppress_interval_min=30)

        assert mock_notify.call_count == 1

    def test_hist_clear_resets_suppression(self, mocker):
        """hist_clear で抑制状態もリセットされる"""
        mock_add = mocker.patch("my_lib.webapp.log.add")

        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)
        unit_cooler.actuator.work_log.hist_clear()
        unit_cooler.actuator.work_log.add("同じメッセージ", suppress_interval_min=30)

        assert mock_add.call_count == 2


class TestWorkLogLevels:
    """ログレベルのテスト"""

    def setup_method(self):
        """各テスト前に履歴をクリア"""
        unit_cooler.actuator.work_log.hist_clear()

    @pytest.mark.parametrize(
        "level",
        [LOG_LEVEL.INFO, LOG_LEVEL.WARN, LOG_LEVEL.ERROR],
    )
    def test_all_levels_add_to_history(self, mocker, level):
        """全レベルで履歴に追加"""
        mocker.patch("my_lib.webapp.log.add")
        mocker.patch("unit_cooler.util.notify_error")

        unit_cooler.actuator.work_log.add("テスト", level)

        hist = unit_cooler.actuator.work_log.hist_get()
        assert "テスト" in hist

    @pytest.mark.parametrize(
        "level,expected_webapp_level",
        [
            (LOG_LEVEL.INFO, LOG_LEVEL.INFO),
            (LOG_LEVEL.WARN, LOG_LEVEL.WARN),
            (LOG_LEVEL.ERROR, LOG_LEVEL.ERROR),
        ],
    )
    def test_webapp_log_receives_correct_level(self, mocker, level, expected_webapp_level):
        """webapp.log に正しいレベルが渡される"""
        mock_add = mocker.patch("my_lib.webapp.log.add")
        mocker.patch("unit_cooler.util.notify_error")

        unit_cooler.actuator.work_log.add("テスト", level)

        mock_add.assert_called_once_with("テスト", expected_webapp_level)
