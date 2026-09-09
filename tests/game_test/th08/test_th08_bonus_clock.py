"""th08 符卡/清场 BONUS 横幅 + 时刻三演出件测试 —— 缺口 #2/#6 回归。

对照 th08-ref(行号相对其 src/):
- "Spell Card Bonus!" 横幅 (Gui.cpp:1951-1965): 居中红标题 + 2 倍粉字
  "+N"; 数据侧 280 帧计时 (Gui.cpp:1024-1028 → globals.step_popups)。
- " BONUS %8d" 清场横幅 (Gui.cpp:1892-1897 + :1000-1009): 30 帧滑入
  416→104, 250 帧消。
- 开局大钟 (Gui.cpp:2093-2095): 换面时 times.anm script 0 跑一遍自隐。
- op181 表盘闪动 (EclRunHigh.inl:957-967 → Gui.cpp:2012-2029):
  clock_flash interrupt 1/2 由 ecl_host 透出, hud_view 消费清零。
- 结算时刻步进 (Gui.cpp:1098-1127 + :1861-1882): 60 帧延迟后逐分钟走,
  按住射击/跳过 +3 快进, AM/PM "%s%2d:%.2d"。

纯逻辑用例不打标记; view/世界层全打 @needs_data。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from types import SimpleNamespace

import pygame  # noqa: E402

from touhou.games.th08.clock import Th08Clock  # noqa: E402
from touhou.games.th08.ecl_host import Th08GameEclHost  # noqa: E402
from touhou.games.th08.globals import Th08Globals  # noqa: E402
from touhou.games.th08.view.pygame_backend import (  # noqa: E402
    PygameTh08Renderer,
    _clock_step,
    _fmt_clock,
)
from touhou.paths import DEFAULT_DATA_PATHS  # noqa: E402

from .conftest import needs_data  # noqa: E402

pygame.init()


def _count_alpha(surf: pygame.Surface, x: int, y: int, w: int, h: int) -> int:
    n = 0
    for yy in range(y, min(y + h, surf.get_height())):
        for xx in range(x, min(x + w, surf.get_width())):
            if surf.get_at((xx, yy)).a:
                n += 1
    return n


# ---- 纯逻辑: 结算时刻文本/步进 ----


def test_fmt_clock_period_labels() -> None:
    """AM/PM + 12 进制小时 (Gui.cpp:1866-1880; 0 点显示 " 0")。"""
    assert _fmt_clock(660) == "PM11:00"  # 开局 23:00
    assert _fmt_clock(690) == "PM11:30"
    assert _fmt_clock(720) == "AM 0:00"
    assert _fmt_clock(1020) == "AM 5:00"  # 封顶 12 单位


def test_clock_step_fsm() -> None:
    """60 帧延迟 → 每帧 +1 → 快进 +3 → 到 target 停 (Gui.cpp:1098-1127)。"""
    st = [0, 660, 690]
    for _ in range(60):
        _clock_step(st, False)
    assert st == [60, 660, 690]  # 延迟期内不动
    _clock_step(st, False)
    assert st[1] == 661
    _clock_step(st, True)  # 按住射击/跳过: +1+3 (:1108-1110)
    assert st[1] == 665
    st[1] = 689
    _clock_step(st, True)  # 越界夹回 target (:1112-1116)
    assert st[1] == 690
    _clock_step(st, True)  # 到位后停
    assert st == [60, 690, 690]


def test_results_panel_clock_line() -> None:
    """结算面板的时刻步进状态: 新快照重置 [0,start,target], 仅 stage<=6。"""
    r = PygameTh08Renderer()
    surf = pygame.Surface((384, 448), pygame.SRCALPHA)
    sr = {
        "stage": 1,
        "lines": [],
        "total": 0,
        "snapshot": {"clock_start": 0, "clock_increment": 1},
    }
    r._render_stage_results(surf, sr)
    assert r._results_clock == [1, 660, 690]  # 首帧即 timer+1 (:1124-1126)
    r._last_held = frozenset({"shoot"})
    for _ in range(60):
        r._render_stage_results(surf, sr)
    assert r._results_clock[1] == 664  # 60 帧延迟满, 快进帧 +4
    # stage 7(6A) 不画时刻行 (:1861 currentStage<=STAGE5)
    r2 = PygameTh08Renderer()
    sr7 = {
        "stage": 7,
        "lines": [],
        "total": 0,
        "snapshot": {"clock_start": 0, "clock_increment": 0},
    }
    r2._render_stage_results(surf, sr7)
    assert r2._results_clock is None


# ---- 纯逻辑: 横幅计时与 op181 闪动事件 ----


def test_bonus_banner_lifetimes() -> None:
    """符卡横幅 280 帧 / 清场横幅 250 帧消 (globals.step_popups)。"""
    g = Th08Globals()
    g.show_spellcard_bonus(1000000)
    g.show_bonus_score(50000)
    for _ in range(250):
        g.step_popups()
    assert g.bonus_score == 0
    assert g.spellcard_bonus != 0
    for _ in range(30):
        g.step_popups()
    assert g.spellcard_bonus == 0


def test_clock_advance_flash_events() -> None:
    """op181 (EclRunHigh.inl:957-967): 推进时透出 interrupt 号, 到 12 快闪。"""
    host = Th08GameEclHost()
    host.clock.units = 5
    host.clock_advance()
    assert host.clock.units == 6
    assert host.clock_flash == 1  # 慢闪
    host.clock.units = 11
    host.clock_advance()
    assert host.clock.units == 12
    assert host.clock_flash == 2  # 到 12 快闪
    host.clock_flash = 0
    host.clock_advance()  # 已封顶: 不推进不闪
    assert host.clock.units == 12
    assert host.clock_flash == 0


# ---- view 渲染(真数据) ----


@needs_data
def test_view_spellcard_bonus_banner() -> None:
    """符卡收取横幅: 红标题 (y≈80) + 2 倍粉字 +N (y≈96), 居中于游戏区。"""
    from touhou.games.th08.view.hud_view import HudView

    hud = HudView(DEFAULT_DATA_PATHS["th08"])
    g = Th08Globals()
    game = SimpleNamespace(globals=g)
    surf = pygame.Surface((640, 480), pygame.SRCALPHA)
    hud._render_spellcard_bonus(surf, game)
    assert _count_alpha(surf, 100, 78, 240, 20) == 0  # 未触发不画
    g.show_spellcard_bonus(1000000)
    hud._render_spellcard_bonus(surf, game)
    assert _count_alpha(surf, 100, 78, 240, 20) > 0  # 标题行
    assert _count_alpha(surf, 150, 94, 160, 36) > 0  # 2 倍数字行


@needs_data
def test_view_bonus_score_slide() -> None:
    """清场 BONUS: timer<30 从 x=416 滑入, 之后停 104 (Gui.cpp:1000-1009)。"""
    from touhou.games.th08.view.hud_view import HudView

    hud = HudView(DEFAULT_DATA_PATHS["th08"])
    g = Th08Globals()
    game = SimpleNamespace(globals=g)
    surf = pygame.Surface((640, 480), pygame.SRCALPHA)
    g.show_bonus_score(50000)  # timer=0 → x=416 (右栏侧)
    hud._render_bonus_score(surf, game)
    assert _count_alpha(surf, 410, 46, 220, 20) > 0
    assert _count_alpha(surf, 100, 46, 200, 20) == 0
    surf.fill((0, 0, 0, 0))
    g.bonus_score_timer = 40  # 滑入结束 → x=104
    hud._render_bonus_score(surf, game)
    assert _count_alpha(surf, 100, 46, 200, 20) > 0


@needs_data
def test_view_clock_dial_flash() -> None:
    """表盘活 VM: sprite=时刻单位; clock_flash interrupt 被消费清零;
    hidden 不画 (Gui.cpp:2006-2007/:2012-2029/:2032-2035)。"""
    from touhou.games.th08.view.hud_view import HudView

    hud = HudView(DEFAULT_DATA_PATHS["th08"])
    host = SimpleNamespace(clock=Th08Clock(), clock_flash=0)
    game = SimpleNamespace(ecl_host=host, stage_no=1)
    surf = pygame.Surface((640, 480), pygame.SRCALPHA)
    hud._render_clock(surf, game)
    assert hud._dial is not None
    assert hud._dial.vm.active_sprite_idx == 0  # SetSprite(GetClockTime)
    for _ in range(70):  # 表盘淡入 30 帧 + 红脉冲循环
        hud._render_clock(surf, game)
    assert _count_alpha(surf, 280, 60, 80, 72) > 0
    host.clock.units = 3
    host.clock_flash = 1  # op181 慢闪
    hud._render_clock(surf, game)
    assert host.clock_flash == 0  # view 消费后清零
    assert hud._dial.vm.active_sprite_idx == 3
    host.clock_flash = 2  # 快闪同样接通
    hud._render_clock(surf, game)
    assert host.clock_flash == 0
    host.clock.hidden = True
    surf.fill((0, 0, 0, 0))
    hud._render_clock(surf, game)
    assert _count_alpha(surf, 280, 60, 80, 72) == 0


@needs_data
def test_view_clock_intro_lifecycle() -> None:
    """开局大钟 (Gui.cpp:2093-2095): 换面启动 script 0, 播完(420 帧)自隐。"""
    from touhou.games.th08.view.hud_view import HudView

    hud = HudView(DEFAULT_DATA_PATHS["th08"])
    host = SimpleNamespace(clock=Th08Clock(), clock_flash=0)
    game = SimpleNamespace(ecl_host=host, stage_no=1)
    surf = pygame.Surface((640, 480), pygame.SRCALPHA)
    hud._render_clock(surf, game)
    assert hud._intro is not None and hud._intro.alive
    assert hud._intro.vm.active_sprite_idx == 0  # SetSprite(GetClockTime)
    for _ in range(300):  # t=240 淡入 + t=256 缩放到位后可见
        hud._render_clock(surf, game)
    assert hud._intro is not None
    assert _count_alpha(surf, 200, 210, 112, 116) > 0  # (256,268) 中心锚
    for _ in range(200):  # t=420 Delete → 自隐
        hud._render_clock(surf, game)
    assert hud._intro is None
    game2 = SimpleNamespace(ecl_host=host, stage_no=2)  # 换面重开
    hud._render_clock(surf, game2)
    assert hud._intro is not None and hud._intro.alive
