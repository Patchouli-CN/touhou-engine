"""bomb 演出测试: 暗转公式/cutin 表/事件接线的单元(合成 stub) + 六机体全链(needs_data)。"""

from __future__ import annotations

from types import SimpleNamespace

from touhou.engine import InputFrame, Rng
from touhou.engine.bomb import BombEnded, BombStarted
from touhou.games.th07.bomb import (
    CHAR_MARISA_A,
    CHAR_MARISA_B,
    CHAR_REIMU_A,
    CHAR_SAKUYA_B,
)
from touhou.games.th07.view.bombfx import _BOMB_CUTIN, BombFx, _darken_alpha
from touhou.games.th07.view.fx import GameFx

from .conftest import needs_data


def _stub_world(**kw) -> SimpleNamespace:
    """BombFx/GameFx 的最小 world stub(archive=None → anm 全静默)。"""
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
        bomb=SimpleNamespace(
            is_in_use=False,
            timer=0,
            duration=140,
            invulnerability_timer=200,
            start_pos=SimpleNamespace(x=192.0, y=400.0),
            sub_info=[
                SimpleNamespace(state=0, pos=None, vel=None, accel=0.0, angle=0.0)
            ]
            * 128,
            damage_boxes=[SimpleNamespace(damage=0)] * 112,
        ),
        th07=SimpleNamespace(power=0.0, cherry=0, cherry_max=10000, cherry_start=0),
        store=SimpleNamespace(catk=[]),
        msg_vm=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---- 暗转公式 (DarkenViewport, BombData.cpp:31-61) ----
def test_darken_alpha_curve() -> None:
    """淡入 0→160(60 帧) → 保持 160 → 对称淡出; duration=140。"""
    assert _darken_alpha(0, 140) == 0
    assert _darken_alpha(30, 140) == 80  # c=128-40=88 → (128-88)*2
    assert _darken_alpha(60, 140) == 160  # c=48 → 保持段
    assert _darken_alpha(79, 140) == 160
    assert _darken_alpha(110, 140) == 80  # 淡出: 140-110=30
    assert _darken_alpha(140, 140) == 0
    # 短 bomb (duration<120) 两段公式直接相接, 不出负值
    assert _darken_alpha(70, 100) == 80  # 70 >= 100-60=40 → 淡出段
    assert all(0 <= _darken_alpha(t, 140) <= 255 for t in range(200))


# ---- cutin 表 ground truth (BombData.cpp 各 ShowBombNamePortrait 调用点) ----
def test_bomb_cutin_table_ground_truth() -> None:
    """立绘 sprite = ANM_SPRITE_FACE_PORTRAIT_ARRAY+n (文件内键 n); 名十二套齐。"""
    assert len(_BOMB_CUTIN) == 12
    assert _BOMB_CUTIN[(CHAR_REIMU_A, False)] == (1, "霊符「夢想封印　散」")  # :137
    assert _BOMB_CUTIN[(CHAR_MARISA_A, False)][0] == 3  # :732 (+3 姿势差分)
    assert _BOMB_CUTIN[(CHAR_MARISA_A, True)][0] == 2  # :843
    assert _BOMB_CUTIN[(CHAR_MARISA_B, False)][0] == 1  # :995
    assert _BOMB_CUTIN[(CHAR_SAKUYA_B, False)] == (3, "時符「パーフェクトスクウェア」")


# ---- 事件接线(无 anm 数据全静默, 但状态机走完) ----
def test_bombfx_events_silent_without_data() -> None:
    """合成 world(archive=None): BombStarted/Ended 喂入不炸, 无产出, 状态复位。"""
    w = _stub_world()
    fx = GameFx(w)
    emit = w.subscribers[0]
    emit(BombStarted(192.0, 400.0, False))
    assert fx.bombfx.running
    sprites, texts = fx.step()
    assert sprites == [] and texts == []
    assert fx.bombfx.active  # 仍在 bomb(状态在, 只是无贴图产出)
    emit(BombEnded())
    assert not fx.bombfx.running
    sprites, texts = fx.step()
    assert sprites == [] and texts == []


def test_bombfx_darken_emitted_without_bank() -> None:
    """暗转黑罩不依赖 anm 数据: bomb 中必产 misc:veil(世界层 z), 结束即撤。"""
    w = _stub_world()
    fx = GameFx(w)
    emit = w.subscribers[0]
    emit(BombStarted(192.0, 400.0, False))
    w.bomb.is_in_use = True
    w.bomb.timer = 70  # 保持段
    sprites, _ = fx.bombfx.step(w, fx.particles)
    veils = [s for s in sprites if s.image == "misc:veil"]
    assert len(veils) == 1 and veils[0].alpha == 160 and veils[0].z < 100.0
    emit(BombEnded())
    sprites, _ = fx.bombfx.step(w, fx.particles)
    assert not [s for s in sprites if s.image == "misc:veil"]


def test_bombfx_ring_outlives_bomb() -> None:
    """无敌环独立倒计时(invulnerability_timer), bomb 结束后仍跟随自机直到归零。"""
    w = _stub_world()
    fx = GameFx(w)
    bombfx = BombFx(Rng(0))
    bombfx._ring = SimpleNamespace(
        execute=lambda: None,
        alive=True,
        visible=True,
        active_sprite_idx=0,
        offset=[0.0, 0.0, 0.0],
        rotation=[0.0, 0.0, 0.0],
        scale=[1.0, 1.0],
        color=[255, 64, 64, 255],
        blend_mode=0,
    )
    bombfx._ring_left = 3
    for _ in range(2):  # 先减后判 (旧 bomb_view 同口径): left 2/1 两帧有环
        sprites, _ = bombfx.step(w, fx.particles)
        assert [s for s in sprites if s.image == "etama.anm:0"]
    sprites, _ = bombfx.step(w, fx.particles)  # left 归零, 撤
    assert not [s for s in sprites if s.image.startswith("etama")]
    assert bombfx._ring is None


# ---- headless 全链(真机数据): 六机体 × 集/散 各触发一次 ----
@needs_data
def test_chain_bomb_fx_all_characters() -> None:
    """12 套 bomb: 触发 → 暗转+本体+cutin/卡名+无敌环出现 → 收场全撤(环按无敌计时)。"""
    from touhou.engine import Button
    from touhou.games.th07.bomb import BOMB_PARAMS
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    asm = compose()
    for char in range(6):
        for focus in (False, True):
            w = compose_world(asm, character=char, difficulty=1, seed=42)
            w.th07.lives = 99
            fx = GameFx(w)
            held = {Button.SHOT}
            if focus:
                held.add(Button.FOCUS)
            held = frozenset(held)
            for _ in range(120):  # 站桩让场上有些东西
                w.tick(InputFrame(held=held))
                fx.step()
            w.tick(InputFrame(held=held, pressed=frozenset({Button.BOMB})))
            assert w.bomb.is_in_use and w.bomb.is_focus == focus, (char, focus)
            saw_veil = saw_body = saw_ring = saw_name = saw_cutin = False
            player_anm = f"player0{char // 2}.anm:"
            frames = 0
            while w.bomb.is_in_use and frames < 600:
                w.tick(InputFrame(held=held))
                sprites, texts = fx.step()
                saw_veil = saw_veil or any(s.image == "misc:veil" for s in sprites)
                saw_body = saw_body or any(
                    s.image.startswith(player_anm) for s in sprites
                )
                saw_ring = saw_ring or any(
                    s.image.startswith("etama.anm:") for s in sprites
                )
                saw_name = saw_name or any("「" in t.text for t in texts)
                saw_cutin = saw_cutin or any(
                    s.image.startswith(
                        f"{('face_rm00', 'face_mr00', 'face_sk00')[char // 2]}.anm:"
                    )
                    and s.z >= 100.0
                    for s in sprites
                )
                frames += 1
            assert frames < 600, (char, focus, "bomb 未结束")
            assert saw_veil, (char, focus, "暗转未出现")
            assert saw_body, (char, focus, "机体本体视觉未出现")
            assert saw_ring, (char, focus, "无敌环未出现")
            assert saw_name, (char, focus, "符卡名横幅未出现")
            assert saw_cutin, (char, focus, "cutin 立绘未出现")
            # 收场: 本体/暗转/横幅全撤(环可活过 bomb, 按 invulnerability 计时归零)
            invuln = BOMB_PARAMS[(char, focus)].invulnerability
            for _ in range(invuln + 90):
                w.tick(InputFrame(held=held))
                sprites, texts = fx.step()
            assert not fx.bombfx.running and not fx.bombfx.active, (char, focus)
            assert not [s for s in sprites if s.image == "misc:veil" and s.z == 55.0]
            assert not [s for s in sprites if s.image.startswith(player_anm)]


@needs_data
def test_chain_bomb_shakes_flow() -> None:
    """震屏数据链: 灵梦B 散首帧/60 帧的 bomb.shakes 已进 world.frame_shakes。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=1, difficulty=1, seed=42)
    w.th07.lives = 99
    fx = GameFx(w)
    for _ in range(120):
        w.tick(InputFrame())
        fx.step()
    w.tick(InputFrame(pressed=frozenset({Button.BOMB})))
    fx.step()
    assert w.bomb.is_in_use
    assert w.frame_shakes, "首帧震屏未透出 (BombData.cpp:559)"
    saw_big = False
    while w.bomb.is_in_use:
        w.tick(InputFrame())
        fx.step()
        if any(amp >= 20 for _, amp, _ in w.frame_shakes):
            saw_big = True  # timer==60 大震屏 (BombData.cpp:566)
    assert saw_big, "60 帧大震屏未透出"
