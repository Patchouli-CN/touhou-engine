"""th08 受击反馈测试 —— 受击闪光 + damageFeedbackLevel + ENEMY 警示灯。

对照 th08-ref(行号相对其 src/):
- 受击闪光 FSM (EnemyManagerUpdate.cpp:599-624): 受伤帧 flag17+color2
  (255,96,128) 置位 + timer=1, 次帧衰减清位(持续命中 → 隔帧闪烁);
  youkai_aligned 敌人不走闪光, 常驻 color2 (32,32,192) 深蓝染色 (:626-633)。
- damageFeedbackLevel (EnemyManager.cpp:435/:497-574): 每帧按 life 与
  生命阈值距离重算, 驱动受击 SE 分档(20/37, EnemyManagerUpdate.cpp:
  609-612)与警示灯闪烁档。
- ENEMY 警示灯 (AsciiManager.cpp:474-549): ascii.anm sprite 157/158,
  槽数据由 world 写入 boss.marker_x/marker_state
  (EnemyManagerUpdate.cpp:635-660)。

纯逻辑用例不打标记; world/view 层全打 @needs_data。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from types import SimpleNamespace

import pygame  # noqa: E402

import touhou  # noqa: F401, E402  # import 即完成 th08 全维度注册
from touhou.engine.ecl import Vec3  # noqa: E402
from touhou.games.th08.ecl_state import Th08ContextArgs, Th08EnemyState  # noqa: E402
from touhou.games.th08.ecl_vm import Th08EclOpcode as Op  # noqa: E402
from touhou.games.th08.world import (  # noqa: E402
    ImperishableNight,
    _feedback_level,
    _update_damage_flash,
)
from touhou.paths import DEFAULT_DATA_PATHS  # noqa: E402
from touhou.utils import Vec2  # noqa: E402

from .conftest import needs_data  # noqa: E402
from .test_th08_ecl import _f, _instr  # noqa: E402
from .test_th08_mechanics import _inject_boss_sub  # noqa: E402
from .test_th08_world import _inject_ecl, _isolate, _tick_until_alive  # noqa: E402

pygame.init()


# ---- 纯逻辑: damageFeedbackLevel 档位 ----


def test_feedback_level_tiers_no_threshold() -> None:
    """无生命阈值时按绝对 life 分档 (EnemyManager.cpp:527-574)。"""
    st = Th08EnemyState()
    st.is_boss = 0
    # 非 boss 无符卡: life<50 → 3 (:562-568)
    st.life = 49
    assert _feedback_level(st, False) == 3
    st.life = 50
    assert _feedback_level(st, False) == 0
    # 非 boss 符卡中: life<10 → 3 (:555-561)
    st.life = 9
    assert _feedback_level(st, True) == 3
    st.life = 10
    assert _feedback_level(st, True) == 0
    # boss 无符卡: 600/1600/2400 (:544-553)
    st.is_boss = 1
    for life, want in ((599, 3), (600, 2), (1599, 2), (1600, 1), (2399, 1), (2400, 0)):
        st.life = life
        assert _feedback_level(st, False) == want, life
    # boss 符卡: 120/300/400 (:534-542)
    for life, want in ((119, 3), (120, 2), (299, 2), (300, 1), (399, 1), (400, 0)):
        st.life = life
        assert _feedback_level(st, True) == want, life


def test_feedback_level_tiers_with_threshold() -> None:
    """有生命阈值时按到阈值的距离分档 (:497-524), 取各阈值最大档。"""
    st = Th08EnemyState()
    st.life_callback_threshold = [1000, -1, -1, -1]
    st.life = 1100  # work=100: 符卡 <120 → 3
    assert _feedback_level(st, True) == 3
    st.life = 1299  # work=299: 符卡 → 1
    assert _feedback_level(st, True) == 1
    st.life = 1300  # work=300: 符卡 → 0
    assert _feedback_level(st, True) == 0
    st.life = 1499  # work=499: 非符卡 <500 → 3
    assert _feedback_level(st, False) == 3
    st.life = 3199  # work=2199 → 1
    assert _feedback_level(st, False) == 1
    st.life = 3200  # work=2200 → 0
    assert _feedback_level(st, False) == 0


# ---- 纯逻辑: 受击闪光 FSM ----


def test_damage_flash_fsm() -> None:
    """受伤帧置位+timer=1, 次帧 timer 衰减清位; 持续命中 → 隔帧闪烁
    (EnemyManagerUpdate.cpp:599-624)。"""
    st = Th08EnemyState()
    _update_damage_flash(st, False)
    assert st.damage_flash == 0 and st.damage_flash_timer == 0
    _update_damage_flash(st, True)
    assert st.damage_flash == 1 and st.damage_flash_timer == 1
    _update_damage_flash(st, False)
    assert st.damage_flash == 0 and st.damage_flash_timer == 0
    # 衰减帧即使受伤也不置位 → 隔帧闪烁
    _update_damage_flash(st, True)
    _update_damage_flash(st, True)
    assert st.damage_flash == 0 and st.damage_flash_timer == 0
    _update_damage_flash(st, True)
    assert st.damage_flash == 1


# ---- world 接线(needs_data) ----


def _inject_zako(g: ImperishableNight, life: int) -> None:
    """注入一个原地不动的杂鱼 sub(SET_ANM + 判定盒 + 可受伤后空转)。"""
    _inject_ecl(
        g,
        [
            _instr(0, int(Op.SET_ANM), (4,)),
            _instr(0, int(Op.SET_HITBOX_SIZE), (_f(24.0), _f(24.0))),
            _instr(0, int(Op.ENABLE_ENEMY_FLAGS), (0x27,)),
            _instr(0, int(Op.SET_LIFE), (life,)),
            _instr(0, int(Op.WAIT), (99999,)),
        ],
    )


def _spawn_zako(g: ImperishableNight, life: int):
    _inject_zako(g, life)
    e = g.ecl_host.spawn_enemy(
        0,
        Vec3(g.player.pos.x, 100.0, 0.0),
        life=-1,
        item_drop=-2,
        score=1000,
        mirror=0,
        context_args=Th08ContextArgs(),
    )
    assert e is not None
    return e


_SHOOT_KEYS = (False, False, False, False, False, True)


@needs_data
def test_world_hit_flash_set_and_decay() -> None:
    """伤害 → damage_flash 置位/衰减全链: shoot_hits 受伤帧置 1,
    持续命中下出现清位帧(隔帧闪烁), 受击 SE 20 入账。"""
    g = ImperishableNight(character=0, difficulty=1, seed=42)
    _tick_until_alive(g)
    _isolate(g)
    e = _spawn_zako(g, 100000)
    st = e.state
    seen_on = seen_off = 0
    se_seen: set[int] = set()
    for _ in range(120):
        g.tick(keys=_SHOOT_KEYS)
        se_seen.update(g.frame_sounds)
        if not e.alive:
            break
        if st.damage_flash:
            seen_on += 1
        elif st.damage_flash_timer == 0:
            seen_off += 1
    assert seen_on > 0, "受击闪光从未置位"
    assert seen_off > 0, "受击闪光从未清位"
    assert 20 in se_seen  # level 0 → SE 20 (EnemyManagerUpdate.cpp:609-610)


@needs_data
def test_world_feedback_level_drives_se_tier() -> None:
    """低血敌人 damageFeedbackLevel=3 → 受击 SE 换 37 (:611-612)。"""
    g = ImperishableNight(character=0, difficulty=1, seed=42)
    _tick_until_alive(g)
    _isolate(g)
    e = _spawn_zako(g, 40)  # 非 boss 无阈值 life<50 → 3 (EnemyManager.cpp:564-568)
    st = e.state
    g.tick(keys=_SHOOT_KEYS)
    assert st.damage_feedback_level == 3
    se_seen: set[int] = set()
    for _ in range(60):
        if not e.alive:
            break
        g.tick(keys=_SHOOT_KEYS)
        se_seen.update(g.frame_sounds)
    assert 37 in se_seen and 20 not in se_seen


@needs_data
def test_boss_marker_slot_sync() -> None:
    """警示灯槽每帧同步 (EnemyManagerUpdate.cpp:635-660): x=pos+32,
    noSprite → -999, state = level+1(低血) / flash?1:0(level 0)。"""
    g = ImperishableNight(character=0, difficulty=1, seed=42)
    _tick_until_alive(g)
    _isolate(g)
    _inject_boss_sub(g, life=100000, timeout=3600, bonus=1_000_000)
    e = g.ecl_host.spawn_enemy(
        0,
        Vec3(g.player.pos.x, 100.0, 0.0),
        life=-1,
        item_drop=-2,
        score=1000,
        mirror=0,
        context_args=Th08ContextArgs(),
    )
    assert e is not None and g.boss is not None
    st = g._boss_ecl_state
    st.can_be_damaged = 0  # 防流弹击毙, 钉住场面测槽同步
    for _ in range(3):
        g.tick()
    assert g.boss is not None
    assert g.boss.marker_x == st.pos.x + 32.0
    # 满血: level 0 且无受击 → state 0
    assert st.damage_feedback_level == 0 and g.boss.marker_state == 0
    # 低血(符卡中): work<120 → level 3 → state 4 (:532-542, :657-659)
    st.life = 100
    g.tick()
    assert g.boss is not None
    assert st.damage_feedback_level == 3 and g.boss.marker_state == 4
    # level 0 + 受击闪光帧 → state 1 (:652-655)
    st.life = 100000
    g.tick()  # 重算 level → 0
    assert g.boss is not None and st.damage_feedback_level == 0
    st.damage_flash = 1
    g._tick_boss()
    assert g.boss.marker_state == 1
    # noSprite → 隐藏 (:644-647)
    st.damage_flash = 0
    st.no_sprite = 1
    g._tick_boss()
    assert g.boss.marker_x == -999.0


# ---- view(needs_data) ----


def _count_alpha(surf: pygame.Surface, x0: int, y0: int, w: int, h: int) -> int:
    n = 0
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            if surf.get_at((xx, yy)).a:
                n += 1
    return n


def _max_alpha_pixel(surf: pygame.Surface, x0: int, y0: int, w: int, h: int):
    best = None
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            c = surf.get_at((xx, yy))
            if c.a and (best is None or c.a > best.a):
                best = c
    return best


@needs_data
def test_view_enemy_damage_flash_colors() -> None:
    """受击闪光/妖对齐染色应用到敌人 VM: flash 帧 flag17+color2
    (255,96,128); youkai_aligned 常驻 (32,32,192) (:614-619/:628-632)。"""
    from touhou.games.th08.view.sprite_view import GameView

    g = ImperishableNight(character=0, difficulty=1, seed=42)
    _tick_until_alive(g)
    _isolate(g)
    e = _spawn_zako(g, 100000)
    st = e.state
    g.tick()  # 跑一帧 ECL 让 SET_ANM 生效
    view = GameView(DEFAULT_DATA_PATHS["th08"], character=0)
    surf = pygame.Surface((384, 448), pygame.SRCALPHA)
    st.damage_flash = 1
    view.render(surf, g)
    avm = view._enemy_vis[id(st)]["vm"].vm
    assert avm.flag17 == 1
    assert list(avm.color2[:3]) == [255, 96, 128]
    assert avm.color2[3] == avm.color[3]
    # 无闪光帧: flag17 清位
    st.damage_flash = 0
    view.render(surf, g)
    assert avm.flag17 == 0
    # 妖对齐使魔: 常驻深蓝染色, 闪光不生效 (:626-633)
    st.youkai_aligned = 1
    st.damage_flash = 1
    view.render(surf, g)
    assert avm.flag17 == 1
    assert list(avm.color2[:3]) == [32, 32, 192]
    assert avm.color2[3] == avm.color[3] // 2


@needs_data
def test_view_boss_marker_states() -> None:
    """ENEMY 警示灯 4 态渲染 (AsciiManager.cpp:474-549): 常态白(近机压
    alpha)/受击暗红/红闪帧与间歇帧用色不同; 隐藏域不画。"""
    from touhou.games.th08.view.hud_view import HudView

    hud = HudView(DEFAULT_DATA_PATHS["th08"])

    def _game(x: float, state: int, frame: int, player_x: float = 100.0):
        return SimpleNamespace(
            boss=SimpleNamespace(marker_x=x, marker_state=state),
            player=SimpleNamespace(pos=Vec2(player_x, 400.0)),
            frame=frame,
        )

    def _draw(game) -> pygame.Surface:
        surf = pygame.Surface((640, 480), pygame.SRCALPHA)
        hud._render_boss_marker(surf, game)
        return surf

    region = (170, 460, 60, 20)
    # 常态: 远离自机 → alpha 160; 画在 (200,472) 一带
    far = _draw(_game(200.0, 0, 0, player_x=100.0))
    assert _count_alpha(far, *region) > 0
    # 隐藏: marker_x=-999(noSprite/退场)与 x 出可见域 (:476) 都不画
    hidden = _draw(_game(-999.0, 0, 0))
    assert _count_alpha(hidden, *region) == 0
    out_of_range = _draw(_game(400.0, 0, 0))
    assert _count_alpha(out_of_range, *region) == 0
    # 靠近自机 x 时压 alpha (:489-495): 正上方(space<64)比远离更暗
    near = _draw(_game(200.0, 0, 0, player_x=200.0))
    px_far = _max_alpha_pixel(far, *region)
    px_near = _max_alpha_pixel(near, *region)
    assert px_far is not None and px_near is not None
    assert px_near.a < px_far.a
    # 受击帧(state 1): 暗红 (:498-503)
    flash = _draw(_game(200.0, 1, 0, player_x=100.0))
    px_flash = _max_alpha_pixel(flash, *region)
    assert px_flash is not None
    assert px_flash.r > px_flash.b
    # 红闪(state 2): frame%8==0 用 sprite 158, 否则回常态 (:504-516)
    red_on = _draw(_game(200.0, 2, 0, player_x=100.0))
    red_off = _draw(_game(200.0, 2, 1, player_x=100.0))
    px_on = _max_alpha_pixel(red_on, *region)
    px_off = _max_alpha_pixel(red_off, *region)
    assert px_on is not None and px_off is not None
    assert (px_on.r, px_on.g, px_on.b, px_on.a) != (
        px_off.r,
        px_off.g,
        px_off.b,
        px_off.a,
    )
