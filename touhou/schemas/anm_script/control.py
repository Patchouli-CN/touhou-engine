"""ANM 控制流指令(退出/跳转/等待/interrupt)。"""

from __future__ import annotations

from .base import AnmInstr

# opcode 出处 Reference/th07/src/th07/AnmManager.hpp:30-114(AnmOpcode 枚举)


class Nop(AnmInstr, frozen=True, tag=0):
    """空转(枚举外但真实数据存在, ExecuteScript 无 case 0)。"""

    # eff08/etama/stgNenm 等脚本实测含 size=8 无参数的 opcode 0


class ExitHide(AnmInstr, frozen=True, tag=-1):
    """隐藏并结束脚本。"""


class ExitHide2(AnmInstr, frozen=True, tag=1):
    """隐藏并结束脚本(同 ExitHide)。"""


class Exit(AnmInstr, frozen=True, tag=2):
    """结束脚本(保持显示)。"""


class Jump(AnmInstr, frozen=True, tag=4):
    """无条件跳转: dest 为相对脚本起点的字节偏移。"""

    dest: int
    set_time: int


class DecJump(AnmInstr, frozen=True, tag=5):
    """变量自减, 仍为正则跳转。"""

    var: int
    dest: int
    set_time: int


class Stop(AnmInstr, frozen=True, tag=20):
    """停住等待 interrupt。"""


class InterruptLabel(AnmInstr, frozen=True, tag=21):
    """interrupt 跳转标号。"""

    label: int


class StopHide(AnmInstr, frozen=True, tag=23):
    """隐藏并停住等待 interrupt。"""


class Wait(AnmInstr, frozen=True, tag=79):
    """等待指定帧数。"""

    frames: int
