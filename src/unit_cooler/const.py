#!/usr/bin/env python3
import enum

import my_lib.webapp.log

PUBSUB_CH = "unit_cooler"
URL_PREFIX = "/unit-cooler"

# my_lib の LOG_LEVEL を再エクスポート
LOG_LEVEL = my_lib.webapp.log.LOG_LEVEL


class VALVE_STATE(enum.IntEnum):
    OPEN = 1
    CLOSE = 0


class COOLING_STATE(enum.IntEnum):
    WORKING = 1
    IDLE = 0


class AIRCON_MODE(enum.IntEnum):
    OFF = 0  # 停止中 or 暖房中 or 不明
    IDLE = 1  # アイドル動作中
    NORMAL = 2  # 平常運転中
    FULL = 3  # フル稼働中
