"""每帧输入: sim 的唯一输入通道。"""

from __future__ import annotations

import enum

import msgspec


class Button(enum.Enum):
    """自机按键(含菜单/系统键: 字母键是通用原始键, 语义由消费方定)。"""

    SHOT = "shot"
    BOMB = "bomb"
    FOCUS = "focus"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SKIP = "skip"
    PAUSE = "pause"
    Q = "q"  # TH_BUTTON_Q (Controller.hpp:16)
    S = "s"  # TH_BUTTON_S
    HOME = "home"  # TH_BUTTON_HOME
    ENTER = "enter"  # TH_BUTTON_ENTER
    D = "d"  # TH_BUTTON_D
    RESET = "reset"  # TH_BUTTON_RESET (R 键, Controller.cpp:406)


class MenuAction(enum.Enum):
    """菜单动作(沿触发)。"""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class InputFrame(msgspec.Struct, frozen=True):
    """一帧的输入: 按住的键 + 本帧按下沿 + 本帧菜单动作。"""

    held: frozenset[Button] = frozenset()
    pressed: frozenset[Button] = frozenset()
    menu: frozenset[MenuAction] = frozenset()
