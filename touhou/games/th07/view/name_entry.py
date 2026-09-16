"""入榜/录像名的 8 字符字表输入: HandleResultKeyboard (ResultScreen.cpp:1133-1317)。

ENTER_NAME 与 REPLAY_SAVING 共用同一套字表逻辑 (:1529-1644 同构);
绘制 = ascii.anm 大字号贴字 (c → sprite ord(c)-1)。
"""

from __future__ import annotations

import msgspec

from ....engine import SpriteDraw
from ....engine.input import Button

# 字表 g_AlphabetList (ResultScreen.cpp:25): 6 行 x 16 列; 93 号空格不可停,
# 94 = 输入空格(贴字 0x80), 95 = 结束输入 END(贴字 0x81)
_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ.,:;_@"
    "abcdefghijklmnopqrstuvwxyz+-/*=%"
    "0123456789#!?'\"$(){}[]<>&\\|~^ --"
)
NAME_LEN = 8  # Hscr name[9] = 8 字符 + NUL
CELL_END = 95

_GRID_POS = (160.0, 356.0)  # :2376
_GRID_PITCH = (20.0, 18.0)  # :2422-2425
_GRID_SEL_RGB = (255, 255, 192)  # 0xffffffc0 选中 (:2385)
_GRID_RGB = (192, 192, 192)  # 0xc0c0c0c0 未选 (:2401)


class NameEntry(msgspec.Struct):
    """8 字符名字输入: 字表光标 + 名字槽 (:1204-1300)。"""

    slots: list[str]
    cursor: int = 0
    selected: int = 0

    @staticmethod
    def create(name: str, *, has_lsnm: bool) -> NameEntry:
        """初始名带出 LSNM; 有 LSNM 时光标直接停 END 格 (:1194-1197)。"""
        return NameEntry(
            list(name[:NAME_LEN].ljust(NAME_LEN)), 0, CELL_END if has_lsnm else 0
        )

    @property
    def name(self) -> str:
        return "".join(self.slots)

    def move(self, b: Button) -> None:
        """四方向移动 (±16 整表回绕 / 行内 ±1 回绕, 跳空格格, :1204-1263)。"""
        while True:
            if b is Button.UP:
                self.selected -= 16
                if self.selected < 0:
                    self.selected += 96
            elif b is Button.DOWN:
                self.selected += 16
                if self.selected >= 96:
                    self.selected -= 96
            elif b is Button.LEFT:
                self.selected -= 1
                if self.selected % 16 == 15:
                    self.selected += 16
                if self.selected < 0:
                    self.selected = 15
            else:
                self.selected += 1
                if self.selected % 16 == 0:
                    self.selected -= 16
            if _ALPHABET[self.selected] != " ":
                return

    def confirm(self) -> bool:
        """写入选中字; True = 按到 END 格(完成输入, :1264-1289)。"""
        cur = min(self.cursor, NAME_LEN - 1)
        if self.selected < 94:
            self.slots[cur] = _ALPHABET[self.selected]
        elif self.selected == 94:
            self.slots[cur] = " "
        else:
            return True
        if self.cursor < NAME_LEN:
            self.cursor += 1
            if self.cursor == NAME_LEN:
                self.selected = CELL_END  # 输满自动跳 END (:1283-1286)
        return False

    def delete(self) -> None:
        """退格 (:1290-1300)。"""
        if self.cursor > 0:
            self.slots[min(self.cursor, NAME_LEN - 1)] = " "
            self.cursor -= 1
            self.slots[self.cursor] = " "


def name_grid_sprites(entry: NameEntry, frame_timer: int) -> list[SpriteDraw]:
    """6x16 字表绘制项 (:2374-2427): 选中字 1.2~2.0 脉动, 末行两格图标。"""
    out: list[SpriteDraw] = []
    ft = frame_timer % 64
    scale = 1.2 + 0.8 * (ft % 32) / 32.0 if ft < 32 else 2.0 - 0.8 * (ft % 32) / 32.0
    gx, gy = _GRID_POS
    for idx in range(96):
        row, col = divmod(idx, 16)
        selected = idx == entry.selected
        # 94=空格图标(char 128) 95=END 图标(char 0x81); c → sprite ord(c)-1
        code = idx if idx < 94 else 128 + (idx - 94)
        out.append(
            SpriteDraw(
                f"ascii.anm:{code - 1}",
                gx + col * _GRID_PITCH[0] + 8.0,
                gy + row * _GRID_PITCH[1] + 8.0,
                z=50.0,
                scale=scale if selected else 1.0,
                alpha=192,
                color=_GRID_SEL_RGB if selected else _GRID_RGB,
            )
        )
    return out
