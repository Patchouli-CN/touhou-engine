"""对局特效层测试: 震屏/弹字/横幅/触发的单元(合成 stub) + headless 全链(needs_data)。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from touhou.engine import InputFrame, SceneSnapshot, SpriteDraw
from touhou.engine.boss import SpellcardBegan
from touhou.engine.enemies import EnemyDied
from touhou.games.th07.snapshot import GAME_X, GAME_Y
from touhou.games.th07.view import PygameBackend
from touhou.games.th07.view import backend as backend_mod
from touhou.games.th07.view.effects import FX_TABLE, FxParticles
from touhou.games.th07.view.fx import GameFx
from touhou.games.th07.view.popups import (
    BonusBanners,
    ScorePopups,
    StageTitle,
    StatusBanner,
)
from touhou.games.th07.view.shake import ScreenShake

from .conftest import needs_data


def _stub_world(**kw) -> SimpleNamespace:
    """GameFx/弹字层的最小 world stub(archive=None → anm 全静默)。"""
    base = dict(
        archive=None,
        subscribers=[],
        stage_no=1,
        character=0,
        host=None,
        boss=None,
        boss_enemy=None,
        enemies=SimpleNamespace(enemies=[]),
        rand_spawn_idx=0,
        spellcard_name="",
        frame_popups=[],
        frame_bonus_score=0,
        player=SimpleNamespace(
            pos=SimpleNamespace(x=192.0, y=400.0), border=SimpleNamespace(active=False)
        ),
        th07=SimpleNamespace(power=0.0, cherry=0, cherry_max=10000, cherry_start=0),
        store=SimpleNamespace(catk=[]),
        msg_vm=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---- 震屏 (ScreenEffect.cpp:249-293) ----
def test_shake_decay_and_removal() -> None:
    """振幅线性插值; timer>=duration 移除; 取值 {0, ±amp}。"""
    s = ScreenShake(seed=1)
    assert not s.active
    s.register(4, 8, 8)  # 恒振幅 8
    assert s.active
    seen: set[tuple[int, int]] = set()
    for _ in range(3):  # timer=1..3 存活
        dx, dy = s.tick()
        seen.add((dx, dy))
        assert dx in (0, 8, -8) and dy in (0, 8, -8)
    s.tick()  # timer=4 >= duration → 移除
    assert not s.active
    assert s.tick() == (0, 0)
    assert seen
    s.register(0, 8, 0)  # duration<=0 忽略
    assert not s.active
    # 衰减: amp_start=8 → amp_end=0, 末帧振幅小于首帧
    s2 = ScreenShake(seed=2)
    s2.register(10, 8, 0)
    amps = set()
    for t in range(1, 10):
        s2.tick()
        amps.add(round((0 - 8) * t / 10 + 8, 3))
    assert amps == {round(8 - 0.8 * t, 3) for t in range(1, 10)}


# ---- 特效粒子 ----
def test_particles_silent_without_bank() -> None:
    """无 anm 数据: spawn 静默, step 空产出。"""
    fx = FxParticles()
    fx.spawn(None, 0, 100.0, 100.0, 4)
    assert len(fx) == 0
    assert fx.step() == []


def test_fx_table_ground_truth_keys() -> None:
    """映射表抽查: 链式脚本键 = C 全局 id - 0x200 (EffectManager.cpp:15-78)。"""
    assert FX_TABLE[0][0] == 0x2AB - 0x200  # 击坠爆风环
    assert FX_TABLE[4][0] == 0x2B3 - 0x200  # deathAnm2+4 默认
    assert FX_TABLE[25][0] == 0x2DA - 0x200  # 符卡环
    assert FX_TABLE[29][0] == 0x2B2 - 0x200  # 结界破裂樱点


# ---- 收点弹字 (AsciiManager::DrawPopups) ----
def test_score_popups_lifecycle_and_alpha() -> None:
    """喂 frame_popups → 数字 sprite; 60 帧消; 远离自机 alpha=208, 贴近 80。"""
    w = _stub_world()
    w.frame_popups.append((100.0, 100.0, 500, 0xFFFFFFFF, 1))
    pop = ScorePopups()
    pop.feed(w)
    w.frame_popups.clear()
    far = pop.step((400.0, 400.0))  # 距离^2 > 4096
    assert [s.image for s in far] == ["ascii.anm:5", "ascii.anm:0", "ascii.anm:0"]
    assert all(s.alpha == 208 for s in far)
    assert all(s.z >= 100.0 for s in far)  # Gui 层
    near = pop.step((101.0, 101.0))  # 贴近 → alpha 80
    assert all(s.alpha == 80 for s in near)
    for _ in range(70):
        out = pop.step((400.0, 400.0))
    assert out == [] and len(pop) == 0


def test_score_popups_powerup_glyph_and_cap() -> None:
    """value=-1 恒 sprite 10 (PowerUp 字形); 槽 2 容量 3 覆盖最旧。"""
    w = _stub_world()
    w.frame_popups.append((50.0, 50.0, -1, 0xFFFFC0A0, 1))
    pop = ScorePopups()
    pop.feed(w)
    out = pop.step((400.0, 400.0))
    assert len(out) == 1 and out[0].image == "ascii.anm:10"
    for i in range(60):  # 三段字形切换也不离 10
        out = pop.step((400.0, 400.0))
        if out:
            assert out[0].image == "ascii.anm:10"
    w2 = _stub_world()
    pop2 = ScorePopups()
    for _ in range(5):
        w2.frame_popups.append((0.0, 0.0, 100, 0xFFFFFFFF, 2))
        pop2.feed(w2)
        w2.frame_popups.clear()
    assert len(pop2) == 3  # CreatePopup2 槽容量 3


# ---- 状态横幅 (Gui::ShowStatusPopup 边沿等效) ----
def test_status_banner_edges() -> None:
    """满火力/满樱/结界边沿各触发一次横幅, 180 帧消。"""
    w = _stub_world()
    banner = StatusBanner()
    assert banner.step(w) == []
    w.th07.power = 128.0  # Full Power 边沿
    out = banner.step(w)
    assert out and out[0].image == f"ascii.anm:{ord('F') - 1}"
    x0 = out[0].x
    for _ in range(20):
        out = banner.step(w)
    assert out[0].x < x0  # 滑入中(x 递减靠 104)
    for _ in range(200):
        out = banner.step(w)
    assert out == []  # 已消
    w.th07.cherry = 10000  # CherryPoint Max 边沿
    assert banner.step(w)
    w.player.border.active = True  # 结界边沿覆盖当前横幅
    assert banner.step(w)[0].image == f"ascii.anm:{ord('S') - 1}"


# ---- BONUS / Spell Card Bonus ----
def test_bonus_banners() -> None:
    """frame_bonus_score 触发 BONUS 横幅(250 帧); 符卡捕获触发 Spell Card Bonus!(280 帧)。"""
    w = _stub_world()
    b = BonusBanners()
    assert b.step(w) == []
    w.frame_bonus_score = 123450
    out = b.step(w)
    assert out and out[0].image == f"ascii.anm:{ord('B') - 1}"
    w.frame_bonus_score = 0
    for _ in range(300):
        out = b.step(w)
    assert out == []
    b.on_spellcard_captured(1000000)
    out = b.step(w)
    assert out and out[0].image == f"ascii.anm:{ord('S') - 1}"
    for _ in range(300):
        out = b.step(w)
    assert out == []


# ---- GameFx 事件触发(无 anm 数据全静默, 但路径走完) ----
def test_gamefx_events_silent_without_data() -> None:
    """合成 world(archive=None): 四类事件喂入不炸, 无产出。"""
    w = _stub_world()
    fx = GameFx(w)
    w.subscribers[0](EnemyDied(1, 100.0, 100.0, False, True, 100, 3))
    w.subscribers[0](SpellcardBegan(0, 3, 2280))
    sprites, texts = fx.step()
    assert sprites == [] and texts == []
    assert len(fx.particles) == 0 and not fx.banner.active


def test_stage_title_silent_without_bank() -> None:
    """std{N}txt.anm 缺失: 标题 VM 组空, MSG_MUSIC 重触发静默。"""
    t = StageTitle.__new__(StageTitle)
    from touhou.engine.rng import Rng

    t.__init__(Rng(0))
    t.sync_stage(lambda name: None, 1)
    t.on_music(lambda name: None, 0)
    assert t.step() == []


# ---- 后端 z 分层 + 震屏 ----
@pytest.fixture
def backend():
    b = PygameBackend(None)
    b.open(title="test", scale=1)
    yield b
    b.close()


def test_backend_gui_layer_not_clipped(backend: PygameBackend) -> None:
    """z>=100 的 Gui sprite 不裁进游戏区(画到区外), z<100 照旧裁剪。"""
    snap = SceneSnapshot(
        0,
        sprites=(
            SpriteDraw("item:1", float(GAME_X), float(GAME_Y), z=10.0),  # 世界层, 角上
            SpriteDraw("ascii.anm:1", 10.0, 200.0, z=110.0),  # Gui 层, 游戏区外
        ),
    )
    backend._render(snap)
    frame = backend._frame_surf
    assert frame is not None
    assert frame.get_at((10, 200))[:3] != backend_mod._BG_COLOR  # Gui 层画出区外
    assert (
        frame.get_at((GAME_X - 5, GAME_Y + 5))[:3] == backend_mod._BG_COLOR
    )  # 世界层仍裁


def test_backend_shake_offset(backend: PygameBackend) -> None:
    """register_shakes 后世界层 sprite 随偏移画(与未震画面有像素差)。"""
    snap = SceneSnapshot(0, sprites=(SpriteDraw("item:1", 200.0, 200.0, z=10.0),))
    backend._render(snap)
    clean = backend._frame_surf
    assert clean is not None
    still = clean.copy()
    backend.register_shakes([(30, 16, 16)])  # 恒振幅 16, 方向三选一
    moved = False
    for _ in range(10):
        backend._render(snap)
        frame = backend._frame_surf
        assert frame is not None
        for x in range(170, 231, 4):
            for y in range(180, 221, 4):
                if frame.get_at((x, y)) != still.get_at((x, y)):
                    moved = True
    assert moved


# ---- headless 全链(真机数据) ----
@needs_data
def test_chain_stage_title_death_fx_and_popups() -> None:
    """一面 2000 帧(扫射): 关卡标题开局即在; 杀敌后 etama 爆散粒子; 收点弹字出现。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    fx = GameFx(w)

    def wiggle(i: int) -> InputFrame:
        held = {Button.SHOT}
        held.add(Button.RIGHT if (i // 40) % 2 == 0 else Button.LEFT)
        return InputFrame(held=frozenset(held))

    title_at0 = death_fx = popup_seen = False
    for i in range(2000):
        w.tick(wiggle(i))
        sprites, _ = fx.step()
        fams = {s.image.split(":")[0] for s in sprites}
        if i == 1:
            title_at0 = "std1txt.anm" in fams
            assert all(s.z >= 100.0 for s in sprites if s.image.startswith("std"))
        if "etama.anm" in fams:
            death_fx = True
        if len(fx.popups):
            popup_seen = True
    assert title_at0, "开局无关卡标题"
    assert death_fx, "2000 帧内无敌死亡特效"
    assert popup_seen, "2000 帧内无收点弹字"


@needs_data
def test_chain_spellcard_fx() -> None:
    """Hard 站桩: 符卡宣言 → 横幅(立绘/卡名/底条) + 魔法阵 + 符卡环; 收场全撤。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=2, seed=42)
    w.th07.lives = 99
    fx = GameFx(w)
    held = InputFrame(held=frozenset({Button.SHOT}))
    saw_banner = saw_circle = saw_ring = saw_name = saw_cutin = False
    ended = False
    for i in range(7500):
        w.tick(held)
        sprites, texts = fx.step()
        fams = {s.image.split(":")[0] for s in sprites}
        if fx.banner.active:
            if not saw_banner:
                # 宣言当帧: 立绘(face_NN_00)/装饰(face_rm00) cutin 在场
                saw_cutin = f"face_{w.stage_no:02d}_00.anm" in fams
                assert "face_rm00.anm" in fams
            saw_banner = True
            saw_name = saw_name or any("霜符" in t.text for t in texts)
        if fx.circle.active:
            saw_circle = True
            assert "eff01.anm" in fams
            assert all(s.z < 10.0 for s in sprites if s.image.startswith("eff"))
        if "etama.anm" in fams and fx.banner.active:
            saw_ring = True
        if saw_banner and not fx.banner.active and not fx.circle.active:
            ended = True  # 收场后横幅/魔法阵全撤
    assert saw_banner, "符卡宣言横幅未出现"
    assert saw_cutin, "宣言当帧无立绘 cutin"
    assert saw_name, "符卡名文本未出现"
    assert saw_circle, "魔法阵未出现"
    assert saw_ring, "符卡环未出现"
    assert ended, "符卡收场后演出未撤"
