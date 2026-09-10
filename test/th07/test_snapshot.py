"""th07 快照生产测试: OUTPUT 槽 system 把世界状态翻译成 SceneSnapshot。

合成世界(无数据)走语义键兜底; 真机世界(needs_data)走 anm 贴图键。
"""

from __future__ import annotations

from touhou.engine import FrameContext, InputFrame, Rng
from touhou.engine.bullets import Bullet
from touhou.engine.items import Item
from touhou.games.th07.data import bullet_active_sprite_idx
from touhou.games.th07.snapshot import Th07SnapshotSystem
from touhou.games.th07.world import Th07World
from touhou.utils.math import Vec2

from .conftest import needs_data


def _produce(world: Th07World) -> FrameContext:
    """跑一帧生产 system, 返回带快照的帧上下文。"""
    ctx = FrameContext(Rng(0), InputFrame())
    Th07SnapshotSystem().tick(world, ctx)
    return ctx


def test_bullet_sprite_key() -> None:
    """敌弹 → etama 贴图键(弹型表, 无需 anm 数据) + 长条弹带旋转。"""
    w = Th07World()
    w.bullets._bullets.append(
        Bullet(pos=Vec2(100.0, 100.0), angle=1.0, speed=2.0, sprite=2, sprite_offset=3)
    )
    ctx = _produce(w)
    b = w.bullets.alive()[0]
    gid = bullet_active_sprite_idx(2, 3) - 0x200
    spr = next(s for s in ctx.draw.sprites if s.image == f"etama.anm:{gid}")
    assert spr.rotation != 0.0  # 米弹按速度方向转
    assert (spr.x, spr.y) == (32 + b.pos.x, 16 + b.pos.y)


def test_item_and_player_fallback_keys() -> None:
    """无 anm 数据: 道具走语义键, 自机走 player0N 代表帧, HUD 文本在。"""
    w = Th07World(character=0)
    w.items.items.append(Item(pos=Vec2(50.0, 60.0), kind=1))
    ctx = _produce(w)
    keys = {s.image for s in ctx.draw.sprites}
    assert "item:1" in keys
    assert any(k.startswith("player00.anm:") for k in keys)
    texts = [t.text for t in ctx.draw.texts]
    assert "SCORE" in texts and "CHERRY" in texts


@needs_data
def test_stage1_snapshot_contents() -> None:
    """真机一面 1400 帧: 敌/自机/自机弹贴图键齐, HUD 计数随分数变化。"""
    from touhou.engine.input import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=1)
    held = frozenset({Button.SHOT})
    snap = None
    for _ in range(1400):
        snap = w.tick(InputFrame(held=held))
    assert snap is not None
    keys = {s.image.split(":")[0] for s in snap.sprites}
    assert "stg1enm.anm" in keys
    assert "player00.anm" in keys
    assert any(
        s.image.startswith("stg1enm.anm:") and s.image.rsplit(":", 1)[1].isdigit()
        for s in snap.sprites
    )
    texts = [t.text for t in snap.texts]
    assert "SCORE" in texts
    score_row = texts[texts.index("SCORE") + 1]
    assert score_row.strip("0") != ""  # 击坠入账, 不是全零


@needs_data
def test_bullets_appear_in_snapshot() -> None:
    """真机一面 Hard: 敌弹出场当帧快照里有 etama 弹键。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=2)
    found = False
    for _ in range(2000):
        snap = w.tick(InputFrame())
        if w.bullets.alive():
            gid_prefix = "etama.anm:"
            assert any(s.image.startswith(gid_prefix) for s in snap.sprites)
            found = True
            break
    assert found, "2000 帧内敌弹未出场"
