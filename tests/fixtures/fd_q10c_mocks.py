#!/usr/bin/env python3
"""FD-Q10C センサー専用モック"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


# SPI トランザクションパターン定義
def gen_fd_q10c_ser_trans_sense(is_zero: bool = False) -> list[dict]:
    """FD-Q10C センサー読み取りトランザクションを生成

    Args:
        is_zero: ゼロ流量の場合 True

    Returns:
        SPI トランザクションリスト
    """
    if is_zero:
        return [
            {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
            {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
            {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
            {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
            {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x00, 0x2D]},
            {"send": [0xE2, 0x0B], "recv": [0xE2, 0x0B, 0x00, 0x2D]},
            {"send": [0xE3, 0x3A], "recv": [0xE3, 0x3A, 0x00, 0x2D]},
            {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
        ]
    return [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
        {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x01, 0x2D]},
        {"send": [0xE2, 0x0B], "recv": [0xE2, 0x0B, 0x01, 0x2D]},
        {"send": [0xE3, 0x3A], "recv": [0xE3, 0x3A, 0x01, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]


def gen_fd_q10c_ser_trans_ping() -> list[dict]:
    """FD-Q10C ping トランザクションを生成"""
    return [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]


def gen_fd_q10c_ser_trans_stop() -> list[dict]:
    """FD-Q10C stop トランザクションを生成"""
    return [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
        {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
        {"send": [0x81, 0x0F, 0xD5], "recv": [0x81, 0x0F, 0xD5, 0x2D]},
    ]


def gen_fd_q10c_ser_trans_error(error_type: str = "checksum") -> list[dict]:
    """FD-Q10C エラートランザクションを生成

    Args:
        error_type: エラータイプ ("checksum", "header", "timeout", "short")

    Returns:
        エラーを含む SPI トランザクションリスト
    """
    error_transactions = {
        "checksum": [
            {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
            {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
            {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0xFF]},  # 不正なチェックサム
        ],
        "header": [
            {"send": [0x70, 0x09, 0x93], "recv": [0xFF, 0xFF, 0xFF, 0xFF]},  # 不正なヘッダー
        ],
        "timeout": [],  # 空のレスポンス（タイムアウトをシミュレート）
        "short": [
            {"send": [0x70, 0x09, 0x93], "recv": [0x70]},  # 短いレスポンス
        ],
    }
    return error_transactions.get(error_type, gen_fd_q10c_ser_trans_sense())


class FDQ10CDetailedMock:
    """FD-Q10C 詳細モッククラス

    SPI 通信レベルでのモックを提供する。
    """

    def __init__(self):
        self.transactions: list[dict] = []
        self.transaction_index = 0
        self.power_state = True
        self.spi_mock: MagicMock | None = None

    def setup(
        self,
        mocker: MockerFixture,
        transactions: list[dict] | None = None,
        count: int = 1,
        spi_read_value: int | None = None,
    ) -> MagicMock:
        """詳細モックをセットアップ

        Args:
            mocker: pytest-mock の mocker fixture
            transactions: SPI トランザクションリスト
            count: トランザクションの繰り返し回数
            spi_read_value: SPI 読み取り値のオーバーライド

        Returns:
            SPI モックオブジェクト
        """
        if transactions is None:
            transactions = gen_fd_q10c_ser_trans_sense()

        self.transactions = transactions * count
        self.transaction_index = 0

        spi_mock = MagicMock()

        def xfer2_side_effect(data: list[int]) -> list[int]:
            if self.transaction_index < len(self.transactions):
                trans = self.transactions[self.transaction_index]
                self.transaction_index += 1
                if spi_read_value is not None:
                    return [spi_read_value] * len(data)
                return trans.get("recv", data)
            return data

        spi_mock.xfer2.side_effect = xfer2_side_effect
        spi_mock.readbytes.return_value = [0x2D]

        self.spi_mock = spi_mock
        mocker.patch("spidev.SpiDev", return_value=spi_mock)

        return spi_mock

    def get_transaction_count(self) -> int:
        """実行されたトランザクション数を取得"""
        return self.transaction_index

    def reset_transactions(self) -> None:
        """トランザクションインデックスをリセット"""
        self.transaction_index = 0


def mock_fd_q10c(
    mocker: MockerFixture,
    ser_trans: list[dict] | None = None,
    count: int = 1,
    spi_read: int | None = None,
) -> MagicMock:
    """FD-Q10C をモックする簡易関数

    Args:
        mocker: pytest-mock の mocker fixture
        ser_trans: SPI トランザクションリスト
        count: トランザクションの繰り返し回数
        spi_read: SPI 読み取り値のオーバーライド

    Returns:
        SPI モックオブジェクト
    """
    mock = FDQ10CDetailedMock()
    return mock.setup(mocker, ser_trans, count, spi_read)
