"""th07 对局 HUD 快照生产: front.anm 贴图面板/边框 + ascii 贴字 + 樱点底栏。

坐标 = 640x480 窗口像素, 全部左上锚件按 sprite 宽高换算成 SpriteDraw 中心锚
(宽高优先取 bank, 无数据用表内缺省尺寸)。原版右栏没有 CherryPlus 行: 樱点
走游戏区底部左侧的 Cherry+ 计量条(AsciiManager 弹点层)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...engine import SpriteDraw, TextDraw
from ...engine.anm import AnmBank, AnmMachine
from ...engine.rng import Rng
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
    alpha: int = 255,
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
                    alpha=alpha,
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


def _draw_cherry(
    out: list[SpriteDraw],
    world: Th07World,
    bank: AnmBank | None,
    gx: float,
    gy: float,
    alpha: int,
) -> None:
    """樱点计量条绘制: 底图 + cherry/max 下行 + cherryPlus 上行 (AsciiManager.cpp:1140-1295)。

    gx/gy = 计量条左上(脚本 4 的 vm.pos, anchor3); alpha = 整条随计量条淡隐。
    """
    g = world.th07
    w, h = _dims(bank, 142, _DIMS[142])
    out.append(
        SpriteDraw(f"{_ASCII}:142", gx + w / 2, gy + h / 2, z=Z_GAUGE, alpha=alpha)
    )
    cherry = max(0, g.cherry - g.cherry_start)
    if g.cherry >= g.cherry_max:
        rgb = _CHERRY_AT_MAX
    elif cherry >= 50000:
        rgb = _CHERRY_HIGH
    else:
        rgb = _CHERRY_NORMAL
    _gauge_digits(out, gx + 46.0, gy + 11.0, cherry, 6, rgb, alpha=alpha)
    cherry_max = max(0, g.cherry_max - g.cherry_start)
    # 下行 max 组: 起点 = 6 槽步进完再 +9; ≥百万扩 7 槽 (AsciiManager.cpp:1200-1223)
    _gauge_digits(
        out,
        gx + 46.0 + 6 * 7.0 + 9.0,
        gy + 11.0,
        cherry_max,
        7 if cherry_max >= 1000000 else 6,
        _CHERRY_MAX_RGB,
        alpha=alpha,
    )
    plus = max(0, g.cherry_plus - g.cherry_start)
    border = world.player.border.has_border
    if border != BorderState.NONE:
        # 结界 READY/ACTIVE: 变色+放大 1.41+步进 10 (AsciiManager.cpp:1230-1253)
        tri = plus % 4000
        if tri >= 2000:
            tri = 4000 - tri
        gb = min(255, plus * 192 // 50000 + tri * 64 // 2000)
        _gauge_digits(
            out,
            gx + 55.0,
            gy,
            plus,
            5,
            (255, gb, gb),
            step=10.0,
            scale=1.41,
            alpha=alpha,
        )
    else:
        _gauge_digits(out, gx + 53.0, gy + 2.0, plus, 5, _CHERRY_PLUS_RGB, alpha=alpha)
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
                alpha=alpha,
            )
        )


_SCR_GAUGE = 4  # ANM_SCRIPT_ASCII_CHERRY_GAUGE (AnmIdx.hpp:150)
_GAUGE_FALLBACK = (32.0, 449.0)  # 无数据兜底落点(脚本 4 interrupt 1 终值, 实测)


class CherryGauge:
    """樱点计量条显隐: ascii 脚本 4 VM + 自机压底淡出状态机 (Player.cpp:2196-2221)。

    开局 interrupt 1 左缘滑入 (Player.cpp:2476, 换关/重开本面不重发);
    自机在底部左侧(y>=400 且 x<160)interrupt 2 淡出至 alpha 64,
    离开 interrupt 3 淡回。无 anm 数据时兜底静态绘制。
    """

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vm: AnmMachine | None = None
        self._fade = 1  # uiFadeState (AsciiManager.hpp:122-131)

    def step(
        self, world: Th07World, out: list[SpriteDraw], bank: AnmBank | None
    ) -> None:
        """每帧: 淡出状态机 + VM 推进 + 按 VM 落点/透明度绘制。"""
        vm: AnmMachine | None = self._vm
        if bank is not None and (vm is None or not vm.alive):
            vm = AnmMachine(self._rng)
            vm.start(bank.scripts.get(_SCR_GAUGE))
            if vm.alive:
                vm.pending_interrupt = 1  # 开局滑入 (Player.cpp:2476)
                self._vm = vm
        # UpdateUI 的淡出判定 (Player.cpp:2201-2221); 与 VM 无关独立记账
        p = world.player
        intr: int | None = None
        if p.pos.y >= 400.0:
            if self._fade != 2 and p.pos.x < 160.0:
                intr, self._fade = 2, 2
            elif self._fade == 2 and p.pos.x > 160.0:
                intr, self._fade = 3, 3
        elif self._fade == 2:
            intr, self._fade = 3, 3
        if vm is None or not vm.alive:
            _draw_cherry(out, world, bank, *_GAUGE_FALLBACK, 255)  # 无数据兜底
            return
        if intr is not None:
            vm.pending_interrupt = intr
        vm.execute()  # UpdateScripts (AsciiManager.hpp:108)
        if not vm.visible:
            return
        _draw_cherry(out, world, bank, vm.pos[0], vm.pos[1], vm.color[3])


def emit_hud(
    world: Th07World,
    out: list[SpriteDraw],
    bank_of: Callable[[str], AnmBank | None],
) -> None:
    """对局 HUD 静态件: 边框/面板 + 右栏数值(每帧全量, 原版重画门控不移植)。

    樱点计量条(CherryGauge)/boss 血条(BossBar)/boss▼(BossMarker)是状态件,
    由 snapshot 生产侧持实例驱动。
    """
    front = bank_of(_FRONT)
    _emit_chrome(out, front)
    _emit_stats(out, world, front)


# ---- boss 血条 (Gui.cpp:1225-1292 状态机 + :1835-1917 绘制) ----
Z_BOSS = 104.0  # 血条条体/星标(对话立绘 90 带之上, 对话窗 105 之下)
Z_BOSS_FRAME = 104.5  # front.anm 框(画在条体之上, Gui.cpp:1871)

_BAR_X, _BAR_Y = 64.0, 19.0  # 主条左上(窗口坐标, Gui.cpp:1838-1842)
_BAR_W = 320.0  # 主条满宽
_MARKER_X = 33.0  # 残机星标条左缘 (:1873)
_SCR_FRAME = 11  # front.anm 血条框脚本 (vms0[11], Gui.cpp:658)
# 符卡秒数分档色 (g_SpellcardTimeColors, Gui.cpp:25-30)
_TIME_COLORS = (
    (0xA0, 0xD0, 0xFF),
    (0xA0, 0x80, 0xFF),
    (0xE0, 0x80, 0xC0),
    (0xFF, 0x40, 0x40),
)


class BossBar:
    """boss 血条: front.anm 框 VM + 渐变条/星标(程序化键) + 符卡秒数。

    SET_BOSS 建档即亮(道中 boss 同, ECL_SET_BOSS 置 bossPresent,
    EclManager.cpp:1509-1517); 对话中状态机冻结且整段不画(msg.currentMsgIdx>=0,
    Gui.cpp:1225/:1835)。
    """

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vm: AnmMachine | None = None  # 血条框(front.anm 脚本 11)
        # Gui.cpp 状态机: 0=无 1=滑入中 2=恒显 3=滑出中 (bossHealthBarState)
        self._state = 0
        self._alpha = 0
        self._eased = 0.0

    def step(
        self,
        world: Th07World,
        sprites: list[SpriteDraw],
        texts: list[TextDraw],
        bank_of: Callable[[str], AnmBank | None],
    ) -> None:
        """每帧: 状态机推进 + 有血条时出绘制项(对话中只跑 VM 不画)。"""
        boss = world.boss
        present = boss is not None and boss.max_life > 0
        msg = world.msg_vm
        in_dialog = msg is not None and msg.active
        vm = self._vm
        if vm is None or not vm.alive:
            bank = bank_of(_FRONT)
            vm = None
            if bank is not None:
                vm = AnmMachine(self._rng)
                vm.start(bank.scripts.get(_SCR_FRAME))
                if not vm.alive:
                    vm = None
            self._vm = vm
        if not in_dialog:
            # Gui.cpp:1226-1269 状态机(滑入/出完成以框脚本 Stop 为准)
            if present:
                if self._state == 0:
                    if vm is not None:
                        vm.pending_interrupt = 1  # 滑入 (:1230)
                    self._state = 1
                    self._alpha = 0
                else:
                    if vm is None or vm.is_stopped:
                        self._state = 2
                    self._alpha = 255 if self._alpha >= 252 else self._alpha + 4
            elif self._state != 0:
                if self._state <= 2:
                    if vm is not None:
                        vm.pending_interrupt = 2  # 滑出 (:1254)
                    self._state = 3
                self._alpha = max(0, self._alpha - 4)
                if vm is None or vm.is_stopped:
                    self._state = 0
                    self._eased = 0.0
                    self._alpha = 0
            if self._state >= 2 and present:
                assert boss is not None
                frac = max(0.0, min(1.0, boss.life / boss.max_life))
                # 缓动: 涨 0.01/帧, 落 0.02/帧; 仅恒显/滑出态更新 (:1272-1291)
                if frac > self._eased:
                    self._eased = min(frac, self._eased + 0.01)
                else:
                    self._eased = max(frac, self._eased - 0.02)
        if vm is not None:
            vm.execute()  # ExecuteScripts (Gui.cpp:1293, 对话门控外)
        if in_dialog or (not present and self._state == 0):
            return  # 绘制门 (:1835-1837 bossPresent+state>0)
        # 主条: 程序化渐变 quad (64,19)-(64+320*eased,23) (Gui.cpp:1838-1846)
        sprites.append(
            SpriteDraw(
                "misc:bossbar",
                _BAR_X,
                _BAR_Y,
                z=Z_BOSS,
                scale_x=self._eased * _BAR_W,
                scale_y=4.0,
                alpha=self._alpha,
            )
        )
        # 符卡彩段 (Gui.cpp:1847-1869): host.boss_health 槽=(current, max, color)
        # 原值, 按 boss max_life 归一化 (EclManager.cpp:1704-1712)
        host = world.host
        if host is not None and boss is not None and boss.max_life > 0:
            ml = float(boss.max_life)
            for cur, mx, color in host.boss_health:
                if mx == 0:
                    continue  # bossHealth[j]==0 跳过 (:1850)
                eased_j = cur / ml
                if eased_j >= self._eased:
                    continue  # 段起点已出条外 (:1854)
                end = min(mx / ml, self._eased)  # 段尾不超出当前条长 (:1858-1861)
                sprites.append(
                    SpriteDraw(
                        "misc:bossseg",
                        _BAR_X + eased_j * _BAR_W,
                        _BAR_Y,
                        z=Z_BOSS,
                        scale_x=(end - eased_j) * _BAR_W,
                        scale_y=4.0,
                        alpha=self._alpha,
                        color=((color >> 16) & 255, (color >> 8) & 255, color & 255),
                    )
                )
        if vm is not None and vm.visible and vm.active_sprite_idx >= 0:
            bank = bank_of(_FRONT)
            w = h = 0.0
            if bank is not None:
                slot = bank.sprites.get(vm.active_sprite_idx)
                if slot is not None:
                    w, h = float(slot.sprite.w), float(slot.sprite.h)
            x, y = vm.pos[0] + vm.offset[0], vm.pos[1] + vm.offset[1]
            if vm.anchor & 1:  # anchor3: pos 是左上 → 中心锚
                x += w * abs(vm.scale[0]) / 2.0
            if vm.anchor & 2:
                y += h * abs(vm.scale[1]) / 2.0
            sprites.append(
                SpriteDraw(
                    f"{_FRONT}:{vm.active_sprite_idx}",
                    x,
                    y,
                    z=Z_BOSS_FRAME,
                    alpha=vm.color[3],
                    scale_x=vm.scale[0],
                    scale_y=vm.scale[1],
                    color=(vm.color[0], vm.color[1], vm.color[2]),
                    blend_mode=vm.blend_mode,
                )
            )
        # 残机星标 (Gui.cpp:1873-1887; scale_x 载个数, 后端程序化)
        markers = host.boss_life_markers if host is not None else 0
        if markers > 0:
            sprites.append(
                SpriteDraw(
                    "misc:bossmarkers",
                    _MARKER_X,
                    _BAR_Y,
                    z=Z_BOSS,
                    scale_x=float(markers),
                    scale_y=4.0,
                    alpha=self._alpha,
                )
            )
        # 符卡剩余秒 (Gui.cpp:1889-1916; 只在符卡进行中, 同旧仓 hud 行为)
        if boss is not None and boss.is_active == 1 and boss.spellcard_idx >= 0:
            sec = max(0, min(99, boss.seconds_remaining))
            ci = 0 if sec >= 20 else 1 if sec >= 10 else 2 if sec >= 5 else 3
            texts.append(
                TextDraw(
                    f"{sec:02d}",
                    384.0,
                    16.0,
                    size=15,
                    rgba=(*_TIME_COLORS[ci], self._alpha),
                )
            )


# ---- boss 底部▼位置标记 (EnemyManager.cpp:1064-1089 → AsciiManager.cpp:331-361) ----
_SCR_BOSS_MARKER = 6  # ANM_SCRIPT_ASCII_BOSS_MARKER (AnmIdx.hpp:152)
_MARKER_Y = 472.0  # 窗口 y (EnemyManager.cpp:1082)
Z_MARKER = 120.0  # 与弹字同层(AsciiManager OnDrawPopups 一并绘制)


class BossMarker:
    """boss 底部▼位置标记: ascii 脚本 6 VM 管显隐, 每帧跟 boss 横坐标。

    SET_BOSS 建档 interrupt 1 淡入 / 撤档 interrupt 2 淡出
    (EclManager.cpp:1509-1527); hasNoCollision 或 x 出 [56,392] 不画;
    距自机 64px 内变淡, boss 受击帧蓝化 (AsciiManager.cpp:336-352)。
    无 anm 数据静默。
    """

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vm: AnmMachine | None = None
        self._present = False
        self._wx = -999.0  # 标记窗口 x(C++ pos 由 EnemyManager 每帧写, 撤档后留最后值)

    def step(
        self, world: Th07World, out: list[SpriteDraw], bank: AnmBank | None
    ) -> None:
        """每帧: 显隐边沿 + VM 推进 + 按 boss/自机位置出绘制项。"""
        if bank is None:
            return
        vm = self._vm
        if vm is None or not vm.alive:
            vm = AnmMachine(self._rng)
            vm.start(bank.scripts.get(_SCR_BOSS_MARKER))
            if not vm.alive:
                return  # 下帧重试(同 BossBar)
            self._vm = vm
        e = world.boss_enemy
        present = e is not None and e.active
        if present != self._present:
            self._present = present
            vm.pending_interrupt = 1 if present else 2  # EclManager.cpp:1516/:1526
        if present and e is not None:
            # 游戏区 x → 窗口 x (:1076); hasNoCollision → -999 出窗 (:1077-1081)
            self._wx = -999.0 if e.has_no_collision else 32.0 + e.pos2[0]
        vm.execute()  # UpdateScripts (AsciiManager.hpp:110)
        if not vm.visible or vm.active_sprite_idx < 0:
            return
        wx = self._wx
        if not 56.0 <= wx <= 392.0:
            return  # 范围外不画 (AsciiManager.cpp:333-334)
        if e is not None and world.frame_boss_damage:
            rgb, alpha = (64, 64, 255), 128  # 受击帧蓝化 (:347-352)
        else:
            dist = abs(wx - 32.0 - world.player.pos.x)
            # 距自机 64px 内线性变淡 48→176 (:336-345)
            alpha = min(176, int(dist * 128.0 / 64.0 + 48.0)) if dist < 64.0 else 176
            rgb = (255, 255, 255)
        out.append(
            SpriteDraw(
                f"{_ASCII}:{vm.active_sprite_idx}",
                wx,
                _MARKER_Y,
                z=Z_MARKER,
                alpha=alpha,
                color=rgb,
            )
        )
