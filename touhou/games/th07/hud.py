"""th07 对局 HUD 快照生产: front.anm 贴图面板/边框 + ascii 贴字 + 樱点底栏。

坐标 = 640x480 窗口像素, 全部左上锚件按 sprite 宽高换算成 SpriteDraw 中心锚
(宽高优先取 bank, 无数据用表内缺省尺寸)。原版右栏没有 CherryPlus 行: 樱点
走游戏区底部左侧的 Cherry+ 计量条(AsciiManager 弹点层)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...engine import SpriteDraw
from ...engine.anm import AnmBank
from .player import BorderState

if TYPE_CHECKING:
    from .world import Th07World

_FRONT = "front.anm"
_ASCII = "ascii.anm"

Z_CHROME = 100.0  # 边框/面板 tile + 横条 + logo + 标签(Gui 层, 不裁剪不振屏)
Z_VALUE = 101.0  # 星级/各行数值/power 渐变条
Z_GAUGE = 102.0  # 樱点计量条底图
Z_GAUGE_NUM = 103.0  # 樱点数字 + 结界呼吸标记

_VALUE_X = 496.0  # 各行数值列左缘 (Gui.cpp:1503 起)
_LABEL_X = 432.0  # 标签列左缘 (front.anm script 2-8 稳态)

# 标签行: (front sprite id, 左上 y) (Gui.cpp:1487-1495, vms0[2..8])
_LABELS = (
    (2, 48.0),
    (3, 64.0),
    (4, 96.0),
    (5, 112.0),
    (6, 144.0),
    (7, 160.0),
    (8, 176.0),
)
# 行下划线 y (Gui.cpp:1504-1534, vms0[13] 常画近似)
_UNDERLINE_YS = (48.0, 64.0, 96.0, 112.0, 144.0, 160.0, 176.0)

# 缺省 sprite 尺寸(bank 取不到时用; 实测原版 front/ascii.anm)
_DIMS = {0: (128, 256), 1: (128, 80), 12: (32, 32), 13: (128, 16), 142: (96, 16)}
_DIM_LABEL = (64, 16)
_DIM_STAR = (16, 16)

_ASCII_STEP = 14.0  # 16x16 大字步进 fontSpacing (AsciiManager.cpp:126/284)
_GAUGE_POS = (32.0, 464.0)  # 计量条稳态左上 (ascii script 4 interrupt 1 终值)
_GAUGE_DIGIT = 132  # 8x12 数字 sprite 基址 (AnmIdx.hpp:161)

# 樱点数字颜色 (AsciiManager.cpp:1153-1171/1204-1206/1256-1263)
_CHERRY_AT_MAX = (255, 208, 128)
_CHERRY_HIGH = (255, 255, 128)
_CHERRY_NORMAL = (255, 255, 255)
_CHERRY_MAX_RGB = (240, 208, 224)
_CHERRY_PLUS_RGB = (192, 128, 176)


def _dims(
    bank: AnmBank | None, gid: int, fallback: tuple[int, int]
) -> tuple[float, float]:
    """Sprite 宽高: 优先 bank 实取, 无数据回落表内缺省。"""
    if bank is not None:
        slot = bank.sprites.get(gid)
        if slot is not None:
            return float(slot.sprite.w), float(slot.sprite.h)
    return float(fallback[0]), float(fallback[1])


def _lt(
    out: list[SpriteDraw],
    bank: AnmBank | None,
    gid: int,
    x: float,
    y: float,
    fallback: tuple[int, int],
    z: float,
) -> None:
    """左上锚 front.anm 件 → 中心锚 SpriteDraw。"""
    w, h = _dims(bank, gid, fallback)
    out.append(SpriteDraw(f"{_FRONT}:{gid}", x + w / 2, y + h / 2, z=z))


def _ascii_text(
    out: list[SpriteDraw],
    s: str,
    x: float,
    y: float,
    *,
    step: float = _ASCII_STEP,
    sx: float = 1.0,
) -> None:
    """一行 16x16 ascii 大字 (c → sprite ord(c)-1); x/y 左上, 白色。"""
    for ch in s:
        if ch == " ":
            x += step
            continue
        out.append(
            SpriteDraw(
                f"{_ASCII}:{ord(ch) - 1}", x + 8.0 * sx, y + 8.0, z=Z_VALUE, scale_x=sx
            )
        )
        x += step


def _score_row(
    out: list[SpriteDraw], x: float, y: float, value: int, suffix: int
) -> None:
    """8 位分 + 续关尾数; ≥1 亿时 9 位横缩 0.9 (Gui.cpp:1545-1597)。"""
    if value < 100000000:
        _ascii_text(out, f"{value:08d}", x, y)
        _ascii_text(out, f"{suffix}", x + 112.0, y)
    else:
        _ascii_text(out, f"{value:09d}", x, y, step=_ASCII_STEP * 0.9, sx=0.9)
        _ascii_text(out, f"{suffix}", x + 113.4, y)


def _gauge_digits(
    out: list[SpriteDraw],
    x: float,
    y: float,
    value: int,
    slots: int,
    rgb: tuple[int, int, int],
    *,
    step: float = 7.0,
    scale: float = 1.0,
) -> None:
    """樱点 8x12 数字(中心锚, 前导零省略微, 个位恒画; AsciiManager.cpp:1176-1190)。"""
    divisor = 10 ** (slots - 1)
    shown = False
    for _ in range(slots):
        d = value // divisor
        value %= divisor
        if d:
            shown = True
        if (shown or divisor == 1) and d <= 9:  # d>9 = 百万溢出(原版 ZUN bug), 不画
            out.append(
                SpriteDraw(
                    f"{_ASCII}:{_GAUGE_DIGIT + d}",
                    x,
                    y,
                    z=Z_GAUGE_NUM,
                    scale_x=scale,
                    scale_y=scale,
                    color=rgb,
                )
            )
        x += step
        divisor //= 10


def _emit_chrome(out: list[SpriteDraw], bank: AnmBank | None) -> None:
    """边框/面板 tile + 横条 + logo + 标签 (Gui.cpp:1458-1499)。"""
    for y in range(0, 464, 32):  # 左区整列
        _lt(out, bank, 12, 0.0, float(y), _DIMS[12], Z_CHROME)
    for x in range(416, 624, 32):  # 右栏面板平铺
        for y in range(16, 464, 32):
            _lt(out, bank, 12, float(x), float(y), _DIMS[12], Z_CHROME)
    for x in range(0, 624, 128):  # 顶/底横条
        _lt(out, bank, 13, float(x), 0.0, _DIMS[13], Z_CHROME)
        _lt(out, bank, 13, float(x), 464.0, _DIMS[13], Z_CHROME)
    for x in range(32, 368, 128):  # 游戏区下沿底栏 (Gui.cpp:1540-1544)
        _lt(out, bank, 13, float(x), 464.0, _DIMS[13], Z_CHROME)
    for uy in _UNDERLINE_YS:  # 行下划线(原版仅值刷新帧画, 常画近似)
        _lt(out, bank, 13, _VALUE_X, uy, _DIMS[13], Z_CHROME)
    _lt(out, bank, 13, 512.0, 464.0, _DIMS[13], Z_CHROME)  # fps 底栏位
    _lt(out, bank, 0, 480.0, 208.0, _DIMS[0], Z_CHROME)  # 竖排 logo
    _lt(out, bank, 1, 448.0, 336.0, _DIMS[1], Z_CHROME)  # 英文 logo
    for gid, ly in _LABELS:
        _lt(out, bank, gid, _LABEL_X, ly, _DIM_LABEL, Z_CHROME)


def _emit_stats(out: list[SpriteDraw], world: Th07World, bank: AnmBank | None) -> None:
    """右栏数值行: 分数/星级/power 条/Graze/Point (Gui.cpp:1503-1661)。"""
    g = world.th07
    gl = world.globals
    # HiScore: 随显示分实时反超, 反超后续关尾数换本局 numRetries (GameManager.cpp:265-269)
    hi = world.store.high_score(world.difficulty, world.character)
    cont = world.store.high_score_continues(world.difficulty, world.character)
    if gl.gui_score > hi:
        hi, cont = gl.gui_score, g.num_retries
    _score_row(out, _VALUE_X, 48.0, hi, cont)
    _score_row(out, _VALUE_X, 64.0, gl.gui_score, g.num_retries)
    for i in range(max(0, int(g.lives))):  # 残机星 (Gui.cpp:1516-1525)
        _lt(out, bank, 10, _VALUE_X + i * 16, 96.0, _DIM_STAR, Z_VALUE)
    for i in range(max(0, int(g.bombs))):  # 炸弹星 (Gui.cpp:1527-1536)
        _lt(out, bank, 11, _VALUE_X + i * 16, 112.0, _DIM_STAR, Z_VALUE)
    power = max(0, min(128, int(g.power)))
    if power:
        # 渐变条 quad (496,144)-(496+power,160), 0xe0e0e0ff→0x80e0e0ff
        # (Gui.cpp:1620-1656); 程序化键, x/y 为左上, scale_x=宽 scale_y=高
        out.append(
            SpriteDraw(
                "misc:powerbar",
                _VALUE_X,
                144.0,
                z=Z_VALUE,
                scale_x=float(power),
                scale_y=16.0,
            )
        )
    _ascii_text(out, f"{power}" if power < 128 else "MAX", _VALUE_X, 144.0)
    _ascii_text(out, f"{g.graze_in_total}", _VALUE_X, 160.0)
    _ascii_text(
        out,
        f"{g.point_items_collected_for_extend}/{g.next_needed_point_items_for_extend}",
        _VALUE_X,
        176.0,
    )


def _emit_cherry(out: list[SpriteDraw], world: Th07World, bank: AnmBank | None) -> None:
    """樱点计量条: 底图 + cherry/max 下行 + cherryPlus 上行 (AsciiManager.cpp:1140-1295)。"""
    g = world.th07
    gx, gy = _GAUGE_POS
    w, h = _dims(bank, 142, _DIMS[142])
    out.append(SpriteDraw(f"{_ASCII}:142", gx + w / 2, gy + h / 2, z=Z_GAUGE))
    cherry = max(0, g.cherry - g.cherry_start)
    if g.cherry >= g.cherry_max:
        rgb = _CHERRY_AT_MAX
    elif cherry >= 50000:
        rgb = _CHERRY_HIGH
    else:
        rgb = _CHERRY_NORMAL
    _gauge_digits(out, gx + 46.0, gy + 11.0, cherry, 6, rgb)
    cherry_max = max(0, g.cherry_max - g.cherry_start)
    # 下行 max 组: 起点 = 6 槽步进完再 +9; ≥百万扩 7 槽 (AsciiManager.cpp:1200-1223)
    _gauge_digits(
        out,
        gx + 46.0 + 6 * 7.0 + 9.0,
        gy + 11.0,
        cherry_max,
        7 if cherry_max >= 1000000 else 6,
        _CHERRY_MAX_RGB,
    )
    plus = max(0, g.cherry_plus - g.cherry_start)
    border = world.player.border.has_border
    if border != BorderState.NONE:
        # 结界 READY/ACTIVE: 变色+放大 1.41+步进 10 (AsciiManager.cpp:1230-1253)
        tri = plus % 4000
        if tri >= 2000:
            tri = 4000 - tri
        gb = min(255, plus * 192 // 50000 + tri * 64 // 2000)
        _gauge_digits(out, gx + 55.0, gy, plus, 5, (255, gb, gb), step=10.0, scale=1.41)
    else:
        _gauge_digits(out, gx + 53.0, gy + 2.0, plus, 5, _CHERRY_PLUS_RGB)
    if border == BorderState.ACTIVE:
        # 呼吸标记 sprite 143 (script 5 的 0.8↔1.2/60 帧, 手工等效旧 hud_view)
        t = world.frame % 60
        if t < 30:
            u = t / 30.0
            s = 0.8 + 0.4 * (1.0 - (1.0 - u) ** 2)
        else:
            u = (t - 30) / 30.0
            s = 1.2 - 0.4 * u * u
        out.append(
            SpriteDraw(
                f"{_ASCII}:143",
                gx + 24.0,
                gy + 8.0,
                z=Z_GAUGE_NUM,
                scale_x=s,
                scale_y=s,
            )
        )


def emit_hud(
    world: Th07World,
    out: list[SpriteDraw],
    bank_of: Callable[[str], AnmBank | None],
) -> None:
    """对局 HUD 全件: 边框/面板 + 右栏数值 + 樱点底栏(每帧全量, 原版重画门控不移植)。"""
    front = bank_of(_FRONT)
    _emit_chrome(out, front)
    _emit_stats(out, world, front)
    _emit_cherry(out, world, bank_of(_ASCII))
