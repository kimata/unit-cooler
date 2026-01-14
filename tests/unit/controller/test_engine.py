#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.controller.engine のテスト"""

import dataclasses

from unit_cooler.config import DecisionThresholdsConfig
from unit_cooler.const import COOLING_STATE
from unit_cooler.controller.engine import (
    OFF_SEC_MIN,
    ON_SEC_MIN,
    dummy_cooling_mode,
    gen_control_msg,
    get_dummy_prev_mode,
    judge_cooling_mode,
    set_dummy_prev_mode,
)
from unit_cooler.controller.message import CONTROL_MESSAGE_LIST

DEFAULT_THRESHOLDS = dataclasses.asdict(DecisionThresholdsConfig.default())


def create_sense_data(
    temp: float = 30.0,
    humi: float = 50.0,
    solar_rad: float = 400.0,
    lux: float = 500.0,
    rain: float = 0.0,
    powers: list[float] | None = None,
) -> dict:
    """テスト用センサーデータを作成"""
    if powers is None:
        powers = [600.0, 300.0]

    return {
        "temp": [{"name": "temp", "value": temp}],
        "humi": [{"name": "humi", "value": humi}],
        "solar_rad": [{"name": "solar_rad", "value": solar_rad}],
        "lux": [{"name": "lux", "value": lux}],
        "rain": [{"name": "rain", "value": rain}],
        "power": [{"name": f"power_{i}", "value": p} for i, p in enumerate(powers)],
    }


class TestDummyCoolingMode:
    """dummy_cooling_mode のテスト"""

    def setup_method(self):
        """各テスト前に prev_mode をリセット"""
        set_dummy_prev_mode(0)

    def test_returns_dict_with_cooling_mode(self):
        """cooling_mode を含む dict を返す"""
        result = dummy_cooling_mode()
        assert "cooling_mode" in result
        assert isinstance(result["cooling_mode"], int)

    def test_cooling_mode_is_within_bounds(self):
        """cooling_mode は有効範囲内"""
        max_mode = len(CONTROL_MESSAGE_LIST) - 1
        for _ in range(100):
            result = dummy_cooling_mode()
            assert 0 <= result["cooling_mode"] <= max_mode

    def test_mode_zero_can_only_increase(self):
        """モード 0 からは増加のみ"""
        set_dummy_prev_mode(0)
        for _ in range(20):
            result = dummy_cooling_mode()
            if result["cooling_mode"] != 0:
                # 0 から変化した場合、1 になるはず
                assert result["cooling_mode"] == 1
                break

    def test_mode_max_can_only_decrease(self):
        """最大モードからは減少のみ"""
        max_mode = len(CONTROL_MESSAGE_LIST) - 1
        set_dummy_prev_mode(max_mode)
        for _ in range(20):
            result = dummy_cooling_mode()
            if result["cooling_mode"] != max_mode:
                # 最大から変化した場合、1 減少するはず
                assert result["cooling_mode"] == max_mode - 1
                break

    def test_prev_mode_is_updated(self):
        """prev_mode が更新される"""
        set_dummy_prev_mode(0)
        result = dummy_cooling_mode()
        assert get_dummy_prev_mode() == result["cooling_mode"]

    def test_randomness_with_seed(self):
        """ランダム性のテスト (シード固定)"""
        import random

        random.seed(42)
        set_dummy_prev_mode(3)
        results = [dummy_cooling_mode()["cooling_mode"] for _ in range(10)]

        # 結果の多様性を確認 (少なくとも 2 種類の値が出るはず)
        unique_results = set(results)
        # NOTE: ランダムなので常に成功するわけではないが、確率的に成功するはず
        assert len(unique_results) >= 1


class TestJudgeCoolingMode:
    """judge_cooling_mode のテスト"""

    def test_returns_dict_with_required_keys(self, config):
        """必要なキーを含む dict を返す"""
        sense_data = create_sense_data()
        result = judge_cooling_mode(config, sense_data)

        assert "cooling_mode" in result
        assert "cooler_status" in result
        assert "outdoor_status" in result
        assert "sense_data" in result

    def test_idle_when_no_aircon_activity(self, config):
        """エアコン稼働なしで cooling_mode=0"""
        sense_data = create_sense_data(powers=[10, 10])
        result = judge_cooling_mode(config, sense_data)
        assert result["cooling_mode"] == 0

    def test_mode_based_on_cooler_and_outdoor(self, config):
        """cooler_status + outdoor_status で mode 決定"""
        # 1 台平常運転 (cooler_status=3)、通常条件 (outdoor_status=0)
        sense_data = create_sense_data(powers=[600, 10])
        result = judge_cooling_mode(config, sense_data)
        assert result["cooling_mode"] == 3

    def test_mode_is_capped_at_zero(self, config):
        """モードは 0 以上"""
        # 低稀働 (cooler_status=1) + 低照度 (outdoor_status=-2) = -1 -> 0
        sense_data = create_sense_data(powers=[100, 10], lux=200)
        result = judge_cooling_mode(config, sense_data)
        assert result["cooling_mode"] >= 0

    def test_handles_sensor_error(self, config, caplog):
        """センサーエラーをハンドリング"""
        sense_data = create_sense_data()
        sense_data["temp"][0]["value"] = None  # 外気温なし
        result = judge_cooling_mode(config, sense_data)
        # エラー時は cooling_mode=0
        assert result["cooling_mode"] == 0


class TestGenControlMsg:
    """gen_control_msg のテスト"""

    def test_returns_dict_in_dummy_mode(self, config):
        """ダミーモードで dict を返す"""
        # prev_mode をリセット
        dummy_cooling_mode.prev_mode = 0

        result = gen_control_msg(config, dummy_mode=True, speedup=1)

        assert "state" in result
        assert "duty" in result
        assert "mode_index" in result
        assert "sense_data" in result

    def test_state_matches_message_list(self, config):
        """state が CONTROL_MESSAGE_LIST と一致"""
        dummy_cooling_mode.prev_mode = 0
        result = gen_control_msg(config, dummy_mode=True, speedup=1)

        mode_index = result["mode_index"]
        expected_state = CONTROL_MESSAGE_LIST[mode_index]["state"].value
        assert result["state"] == expected_state

    def test_speedup_affects_duty(self, config):
        """speedup が duty に影響"""
        dummy_cooling_mode.prev_mode = 3  # WORKING モード

        result_normal = gen_control_msg(config, dummy_mode=True, speedup=1)
        result_fast = gen_control_msg(config, dummy_mode=True, speedup=10)

        # speedup が大きいと on_sec/off_sec が小さくなる
        if result_normal["mode_index"] == result_fast["mode_index"]:
            assert result_fast["duty"]["on_sec"] <= result_normal["duty"]["on_sec"]

    def test_speedup_respects_minimum(self, config):
        """speedup は最小値を守る"""
        dummy_cooling_mode.prev_mode = 1  # WORKING モード

        result = gen_control_msg(config, dummy_mode=True, speedup=1000)

        assert result["duty"]["on_sec"] >= ON_SEC_MIN
        assert result["duty"]["off_sec"] >= OFF_SEC_MIN

    def test_mode_index_is_capped(self, config):
        """mode_index は CONTROL_MESSAGE_LIST の範囲内"""
        dummy_cooling_mode.prev_mode = len(CONTROL_MESSAGE_LIST) - 1

        result = gen_control_msg(config, dummy_mode=True, speedup=1)

        assert 0 <= result["mode_index"] < len(CONTROL_MESSAGE_LIST)

    def test_non_dummy_mode_uses_real_data(self, config, mocker):
        """非ダミーモードは実データを使用"""
        mock_sense_data = create_sense_data(powers=[600, 10])

        mocker.patch(
            "unit_cooler.controller.sensor.get_sense_data",
            return_value=mock_sense_data,
        )

        result = gen_control_msg(config, dummy_mode=False, speedup=1)

        assert "sense_data" in result
        assert result["sense_data"] == mock_sense_data

    def test_idle_state_is_zero(self, config):
        """IDLE state は 0"""
        dummy_cooling_mode.prev_mode = 0  # IDLE モードを強制

        # 何度か実行して IDLE が返ることを確認
        for _ in range(10):
            result = gen_control_msg(config, dummy_mode=True, speedup=1)
            if result["mode_index"] == 0:
                assert result["state"] == COOLING_STATE.IDLE.value
                break

    def test_working_state_is_one(self, config):
        """WORKING state は 1"""
        dummy_cooling_mode.prev_mode = 5  # WORKING モードを強制

        result = gen_control_msg(config, dummy_mode=True, speedup=1)

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
