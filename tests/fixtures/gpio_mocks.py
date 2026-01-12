#!/usr/bin/env python3
# ruff: noqa: S101
"""GPIO モックユーティリティ"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class GPIOMockFactory:
    """GPIO モックファクトリー

    Raspberry Pi の GPIO 操作をモックする。
    """

    def __init__(self):
        self.pin_states: dict[int, int] = {}
        self.output_history: list[tuple[int, int]] = []

    def create(self, mocker: MockerFixture, initial_states: dict[int, int] | None = None) -> MagicMock:
        """GPIO モックを作成

        Args:
            mocker: pytest-mock の mocker fixture
            initial_states: ピンの初期状態 {pin_no: value}

        Returns:
            GPIO モックオブジェクト
        """
        if initial_states:
            self.pin_states = initial_states.copy()
        else:
            self.pin_states = {}

        self.output_history = []

        gpio_mock = MagicMock()

        def output_side_effect(pin: int, value: int) -> None:
            self.pin_states[pin] = value
            self.output_history.append((pin, value))

        def input_side_effect(pin: int) -> int:
            return self.pin_states.get(pin, 0)

        gpio_mock.output.side_effect = output_side_effect
        gpio_mock.input.side_effect = input_side_effect
        gpio_mock.IN = 1
        gpio_mock.OUT = 0
        gpio_mock.HIGH = 1
        gpio_mock.LOW = 0

        mocker.patch("my_lib.rpi.gpio", new=gpio_mock)

        return gpio_mock

    def get_pin_state(self, pin: int) -> int:
        """ピンの現在状態を取得"""
        return self.pin_states.get(pin, 0)

    def set_pin_state(self, pin: int, value: int) -> None:
        """ピンの状態を設定"""
        self.pin_states[pin] = value

    def get_output_history(self) -> list[tuple[int, int]]:
        """出力履歴を取得"""
        return self.output_history.copy()

    def clear_history(self) -> None:
        """履歴をクリア"""
        self.output_history = []

    def assert_pin_set(self, pin: int, value: int) -> None:
        """ピンが特定の値に設定されたことを確認"""
        assert (pin, value) in self.output_history, (
            f"Pin {pin} was not set to {value}. History: {self.output_history}"
        )

    def assert_pin_state(self, pin: int, expected: int) -> None:
        """ピンの現在状態を確認"""
        actual = self.pin_states.get(pin, 0)
        assert actual == expected, f"Pin {pin} state: expected {expected}, got {actual}"
