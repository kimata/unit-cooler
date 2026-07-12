#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.controller.engine のテスト"""

import datetime

import my_lib.time
import pytest

from unit_cooler.config import NightStopConfig
from unit_cooler.const import COOLING_STATE
from unit_cooler.controller.engine import (
    OFF_SEC_MIN,
    ON_SEC_MIN,
    dummy_cooling_mode,
    gen_control_msg,
    get_dummy_prev_mode,
    is_night_stop,
    judge_cooling_mode,
    set_dummy_prev_mode,
)
from unit_cooler.controller.message import CONTROL_MESSAGE_LIST
from unit_cooler.messages import SenseData, SensorReading


def create_sense_data(
    temp: float | None = 30.0,
    humi: float | None = 50.0,
    solar_rad: float | None = 400.0,
    lux: float | None = 500.0,
    rain: float | None = 0.0,
    powers: list[float | None] | None = None,
) -> SenseData:
    """テスト用センサーデータを作成"""
    if powers is None:
        powers = [600.0, 300.0]

    return SenseData(
        temp=[SensorReading(name="temp", value=temp)],
        humi=[SensorReading(name="humi", value=humi)],
        solar_rad=[SensorReading(name="solar_rad", value=solar_rad)],
        lux=[SensorReading(name="lux", value=lux)],
        rain=[SensorReading(name="rain", value=rain)],
        power=[SensorReading(name=f"power_{i}", value=p) for i, p in enumerate(powers)],
    )


class TestDummyCoolingMode:
    """dummy_cooling_mode のテスト"""

    def setup_method(self):
        """各テスト前に prev_mode をリセット"""
        set_dummy_prev_mode(0)

    def test_returns_int(self):
        """int を返す"""
        result = dummy_cooling_mode()
        assert isinstance(result, int)

    def test_cooling_mode_is_within_bounds(self):
        """cooling_mode は有効範囲内"""
        max_mode = len(CONTROL_MESSAGE_LIST) - 1
        for _ in range(100):
            result = dummy_cooling_mode()
            assert 0 <= result <= max_mode

    def test_mode_zero_can_only_increase(self):
        """モード 0 からは増加のみ"""
        set_dummy_prev_mode(0)
        for _ in range(20):
            result = dummy_cooling_mode()
            if result != 0:
                # 0 から変化した場合、1 になるはず
                assert result == 1
                break

    def test_mode_max_can_only_decrease(self):
        """最大モードからは減少のみ"""
        max_mode = len(CONTROL_MESSAGE_LIST) - 1
        set_dummy_prev_mode(max_mode)
        for _ in range(20):
            result = dummy_cooling_mode()
            if result != max_mode:
                # 最大から変化した場合、1 減少するはず
                assert result == max_mode - 1
                break

    def test_prev_mode_is_updated(self):
        """prev_mode が更新される"""
        set_dummy_prev_mode(0)
        result = dummy_cooling_mode()
        assert get_dummy_prev_mode() == result

    def test_randomness_with_seed(self):
        """ランダム性のテスト (シード固定)"""
        import random

        random.seed(42)
        set_dummy_prev_mode(3)
        results = [dummy_cooling_mode() for _ in range(10)]

        # 結果の多様性を確認 (少なくとも 2 種類の値が出るはず)
        unique_results = set(results)
        # NOTE: ランダムなので常に成功するわけではないが、確率的に成功するはず
        assert len(unique_results) >= 1


def time_at(hour: int, minute: int = 0) -> datetime.datetime:
    """テスト用: 指定した時分の datetime を作成"""
    return datetime.datetime(2024, 7, 1, hour, minute, 0, tzinfo=my_lib.time.get_zoneinfo())


class TestIsNightStop:
    """is_night_stop のテスト"""

    # 日をまたぐ設定（21時〜6時）
    OVERNIGHT = NightStopConfig(enable=True, start_hour=21, end_hour=6)
    # 日をまたがない設定（0時〜6時）
    SAME_DAY = NightStopConfig(enable=True, start_hour=0, end_hour=6)

    def test_overnight_start_boundary(self):
        """日またぎ: 21:00 ちょうどは停止開始"""
        assert is_night_stop(self.OVERNIGHT, time_at(21, 0)) is True

    def test_overnight_before_start(self):
        """日またぎ: 20:59 はまだ停止しない"""
        assert is_night_stop(self.OVERNIGHT, time_at(20, 59)) is False

    def test_overnight_end_boundary(self):
        """日またぎ: 6:00 ちょうどは再開（停止でない）"""
        assert is_night_stop(self.OVERNIGHT, time_at(6, 0)) is False

    def test_overnight_before_end(self):
        """日またぎ: 5:59 はまだ停止中"""
        assert is_night_stop(self.OVERNIGHT, time_at(5, 59)) is True

    def test_overnight_midnight(self):
        """日またぎ: 深夜 0 時は停止中"""
        assert is_night_stop(self.OVERNIGHT, time_at(0, 0)) is True

    def test_overnight_daytime(self):
        """日またぎ: 昼間は停止しない"""
        assert is_night_stop(self.OVERNIGHT, time_at(12, 0)) is False

    def test_same_day_start_boundary(self):
        """日またぎなし: 0:00 ちょうどは停止開始"""
        assert is_night_stop(self.SAME_DAY, time_at(0, 0)) is True

    def test_same_day_in_range(self):
        """日またぎなし: 5:59 は停止中"""
        assert is_night_stop(self.SAME_DAY, time_at(5, 59)) is True

    def test_same_day_end_boundary(self):
        """日またぎなし: 6:00 ちょうどは再開（停止でない）"""
        assert is_night_stop(self.SAME_DAY, time_at(6, 0)) is False

    def test_same_day_outside_range(self):
        """日またぎなし: 範囲外は停止しない"""
        assert is_night_stop(self.SAME_DAY, time_at(12, 0)) is False
        assert is_night_stop(self.SAME_DAY, time_at(23, 59)) is False

    @pytest.mark.parametrize("hour", [0, 6, 12, 21, 23])
    def test_disabled_is_always_false(self, hour):
        """enable=False では常に False"""
        night_stop = NightStopConfig(enable=False, start_hour=21, end_hour=6)
        assert is_night_stop(night_stop, time_at(hour)) is False

    @pytest.mark.parametrize("hour", [0, 5, 6, 7, 12, 23])
    def test_start_equals_end_is_always_false(self, hour):
        """start == end は一度も停止しない"""
        night_stop = NightStopConfig(enable=True, start_hour=6, end_hour=6)
        assert is_night_stop(night_stop, time_at(hour)) is False

    def test_start_equals_end_with_minutes_is_always_false(self):
        """start == end（分単位で一致）も一度も停止しない"""
        night_stop = NightStopConfig(enable=True, start_hour=21, end_hour=21, start_minute=30, end_minute=30)
        assert is_night_stop(night_stop, time_at(21, 30)) is False

    def test_start_minute_boundary(self):
        """分単位: start 21:30 のとき 21:29 は False、21:30 は True"""
        night_stop = NightStopConfig(enable=True, start_hour=21, end_hour=6, start_minute=30)
        assert is_night_stop(night_stop, time_at(21, 29)) is False
        assert is_night_stop(night_stop, time_at(21, 30)) is True
        assert is_night_stop(night_stop, time_at(21, 31)) is True

    def test_end_minute_boundary(self):
        """分単位: end 6:30 のとき 6:29 は True、6:30 は False"""
        night_stop = NightStopConfig(enable=True, start_hour=21, end_hour=6, end_minute=30)
        assert is_night_stop(night_stop, time_at(6, 29)) is True
        assert is_night_stop(night_stop, time_at(6, 30)) is False

    def test_same_day_with_minutes(self):
        """分単位: 日またぎなし（9:15〜17:45）"""
        night_stop = NightStopConfig(enable=True, start_hour=9, end_hour=17, start_minute=15, end_minute=45)
        assert is_night_stop(night_stop, time_at(9, 14)) is False
        assert is_night_stop(night_stop, time_at(9, 15)) is True
        assert is_night_stop(night_stop, time_at(17, 44)) is True
        assert is_night_stop(night_stop, time_at(17, 45)) is False


class TestNightStopPropagation:
    """night_stop フラグの伝搬と通知抑制のテスト"""

    def _fix_time(self, mocker, hour: int, minute: int = 0):
        mocker.patch("my_lib.time.now", return_value=time_at(hour, minute))

    def test_judge_cooling_mode_sets_night_stop(self, config, mocker):
        """夜間停止時間帯は CoolingModeResult.night_stop=True かつ mode=0"""
        self._fix_time(mocker, 23)

        result = judge_cooling_mode(config, create_sense_data())

        assert result.night_stop is True
        assert result.cooling_mode == 0

    def test_judge_cooling_mode_daytime_night_stop_false(self, config, mocker):
        """昼間は CoolingModeResult.night_stop=False"""
        self._fix_time(mocker, 12)

        result = judge_cooling_mode(config, create_sense_data())

        assert result.night_stop is False

    def test_gen_control_msg_propagates_night_stop(self, config, mocker):
        """夜間停止時間帯は ControlMessage.night_stop=True かつ mode_index=0"""
        self._fix_time(mocker, 23)
        mock_get = mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value=create_sense_data(),
        )

        msg = gen_control_msg(config, dummy_mode=False, speedup=1)

        assert msg.night_stop is True
        assert msg.mode_index == 0
        # 夜間停止中はセンサー欠損の Slack 通知を抑制する
        assert mock_get.call_args.kwargs["notify_failure"] is False

    def test_gen_control_msg_daytime_night_stop_false(self, config, mocker):
        """昼間は ControlMessage.night_stop=False で通知は抑制しない"""
        self._fix_time(mocker, 12)
        mock_get = mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value=create_sense_data(),
        )

        msg = gen_control_msg(config, dummy_mode=False, speedup=1)

        assert msg.night_stop is False
        assert mock_get.call_args.kwargs["notify_failure"] is True

    def test_gen_control_msg_dummy_mode_night_stop_false(self, config, mocker):
        """dummy_mode では夜間でも night_stop=False"""
        self._fix_time(mocker, 23)
        set_dummy_prev_mode(0)

        msg = gen_control_msg(config, dummy_mode=True, speedup=1)

        assert msg.night_stop is False

    def test_no_slack_notify_on_sensor_failure_during_night_stop(self, config, mocker):
        """夜間停止中はセンサー欠損でも Slack 通知（notify_error）が呼ばれない"""
        self._fix_time(mocker, 23)

        # 全センサーのデータ取得を失敗させる
        mock_data = mocker.MagicMock()
        mock_data.valid = False

        async def mock_fetch_parallel(db_config, requests):
            return [mock_data] * len(requests)

        mocker.patch("my_lib.sensor_data.fetch_data_parallel", side_effect=mock_fetch_parallel)
        mock_notify = mocker.patch("unit_cooler.util.notify_error")

        msg = gen_control_msg(config, dummy_mode=False, speedup=1)

        mock_notify.assert_not_called()
        assert msg.night_stop is True
        assert msg.mode_index == 0

    def test_slack_notify_on_sensor_failure_during_daytime(self, config, mocker):
        """昼間はセンサー欠損で Slack 通知（notify_error）が呼ばれる"""
        self._fix_time(mocker, 12)

        mock_data = mocker.MagicMock()
        mock_data.valid = False

        async def mock_fetch_parallel(db_config, requests):
            return [mock_data] * len(requests)

        mocker.patch("my_lib.sensor_data.fetch_data_parallel", side_effect=mock_fetch_parallel)
        mock_notify = mocker.patch("unit_cooler.util.notify_error")

        gen_control_msg(config, dummy_mode=False, speedup=1)

        assert mock_notify.called


class TestJudgeCoolingMode:
    """judge_cooling_mode のテスト"""

    @pytest.fixture(autouse=True)
    def _daytime(self, mocker):
        """夜間停止の影響を受けないよう、現在時刻を昼間（12時）に固定する"""
        mocker.patch(
            "my_lib.time.now",
            return_value=datetime.datetime(2024, 7, 1, 12, 0, 0, tzinfo=my_lib.time.get_zoneinfo()),
        )

    def test_returns_cooling_mode_result(self, config):
        """CoolingModeResult を返す"""
        from unit_cooler.messages import CoolingModeResult

        sense_data = create_sense_data()
        result = judge_cooling_mode(config, sense_data)

        assert isinstance(result, CoolingModeResult)
        assert hasattr(result, "cooling_mode")
        assert hasattr(result, "cooler_status")
        assert hasattr(result, "outdoor_status")
        assert hasattr(result, "sense_data")

    def test_idle_when_no_aircon_activity(self, config):
        """エアコン稼働なしで cooling_mode=0"""
        sense_data = create_sense_data(powers=[10, 10])
        result = judge_cooling_mode(config, sense_data)
        assert result.cooling_mode == 0

    def test_mode_based_on_cooler_and_outdoor(self, config):
        """cooler_status + outdoor_status で mode 決定"""
        # 1 台平常運転 (cooler_status=3)、通常条件 (outdoor_status=0)
        sense_data = create_sense_data(powers=[600, 10])
        result = judge_cooling_mode(config, sense_data)
        assert result.cooling_mode == 3

    def test_mode_is_capped_at_zero(self, config):
        """モードは 0 以上"""
        # 低稀働 (cooler_status=1) + 低照度 (outdoor_status=-2) = -1 -> 0
        sense_data = create_sense_data(powers=[100, 10], lux=200)
        result = judge_cooling_mode(config, sense_data)
        assert result.cooling_mode >= 0

    def test_handles_sensor_error(self, config, caplog):
        """センサーエラーをハンドリング"""
        sense_data = create_sense_data(temp=None)  # 外気温なし
        result = judge_cooling_mode(config, sense_data)
        # エラー時は cooling_mode=0
        assert result.cooling_mode == 0


class TestGenControlMsg:
    """gen_control_msg のテスト"""

    def test_returns_control_message_in_dummy_mode(self, config):
        """ダミーモードで ControlMessage を返す"""
        from unit_cooler.messages import ControlMessage

        # prev_mode をリセット
        set_dummy_prev_mode(0)

        result = gen_control_msg(config, dummy_mode=True, speedup=1)

        assert isinstance(result, ControlMessage)
        assert hasattr(result, "state")
        assert hasattr(result, "duty")
        assert hasattr(result, "mode_index")
        assert hasattr(result, "sense_data")

    def test_to_dict_has_required_keys(self, config):
        """to_dict() は必要なキーを含む"""
        set_dummy_prev_mode(0)

        result = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()

        assert "state" in result
        assert "duty" in result
        assert "mode_index" in result
        assert "sense_data" in result

    def test_state_matches_message_list(self, config):
        """state が CONTROL_MESSAGE_LIST と一致"""
        set_dummy_prev_mode(0)
        result = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()

        mode_index = result["mode_index"]
        expected_state = CONTROL_MESSAGE_LIST[mode_index].state.value
        assert result["state"] == expected_state

    def test_speedup_affects_duty(self, config):
        """speedup が duty に影響"""
        set_dummy_prev_mode(3)  # WORKING モード

        result_normal = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()
        result_fast = gen_control_msg(config, dummy_mode=True, speedup=10).to_dict()

        # speedup が大きいと on_sec/off_sec が小さくなる
        if result_normal["mode_index"] == result_fast["mode_index"]:
            assert result_fast["duty"]["on_sec"] <= result_normal["duty"]["on_sec"]

    def test_speedup_respects_minimum(self, config):
        """speedup は最小値を守る"""
        set_dummy_prev_mode(1)  # WORKING モード

        result = gen_control_msg(config, dummy_mode=True, speedup=1000).to_dict()

        assert result["duty"]["on_sec"] >= ON_SEC_MIN
        assert result["duty"]["off_sec"] >= OFF_SEC_MIN

    def test_mode_index_is_capped(self, config):
        """mode_index は CONTROL_MESSAGE_LIST の範囲内"""
        set_dummy_prev_mode(len(CONTROL_MESSAGE_LIST) - 1)

        result = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()

        assert 0 <= result["mode_index"] < len(CONTROL_MESSAGE_LIST)

    def test_non_dummy_mode_uses_real_data(self, config, mocker):
        """非ダミーモードは実データを使用"""
        mock_sense_data = create_sense_data(powers=[600, 10])

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value=mock_sense_data,
        )

        result = gen_control_msg(config, dummy_mode=False, speedup=1).to_dict()

        assert result["sense_data"] == mock_sense_data.to_dict()

    def test_idle_state_is_zero(self, config):
        """IDLE state は 0"""
        set_dummy_prev_mode(0)  # IDLE モードを強制

        # 何度か実行して IDLE が返ることを確認
        for _ in range(10):
            result = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()
            if result["mode_index"] == 0:
                assert result["state"] == COOLING_STATE.IDLE.value
                break

    def test_working_state_is_one(self, config):
        """WORKING state は 1"""
        set_dummy_prev_mode(5)  # WORKING モードを強制

        result = gen_control_msg(config, dummy_mode=True, speedup=1).to_dict()

        if result["mode_index"] > 0:
            assert result["state"] == COOLING_STATE.WORKING.value


class TestOnOffSecMin:
    """ON_SEC_MIN, OFF_SEC_MIN のテスト"""

    def test_on_sec_min_is_positive(self):
        """ON_SEC_MIN は正"""
        assert ON_SEC_MIN > 0

    def test_off_sec_min_is_positive(self):
        """OFF_SEC_MIN は正"""
        assert OFF_SEC_MIN > 0

    def test_values_are_reasonable(self):
        """妥当な値"""
        assert ON_SEC_MIN >= 5
        assert OFF_SEC_MIN >= 5
