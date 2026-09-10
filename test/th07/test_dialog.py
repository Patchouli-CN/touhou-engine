"""对话立绘测试: msg 状态→渲染产出单测(合成 bank) + headless 全链(needs_data)。

历史回归针对: ①立绘串面(右侧用了别面 boss 图) ②跨消息立绘残留(错隐/错出)。
"""

from __future__ import annotations

from types import SimpleNamespace

from touhou.engine import InputFrame
from touhou.engine.anm import AnmBank, SpriteSlot, build_script
from touhou.engine.msg import MsgExecutor
from touhou.engine.rng import Rng
from touhou.games.th07.view.dialog import Z_PORTRAIT, DialogPortraits
from touhou.games.th07.view.fx import GameFx
from touhou.schemas.anm import AnmSprite
from touhou.schemas.anm_script import (
    Anchor3,
    ExitHide2,
    InterpAlpha,
    InterpPos,
    InterruptLabel,
    SetActiveSprite,
    SetAlpha,
    SetTranslation,
    Stop,
    StopHide,
)
from touhou.schemas.msg import (
    ChangeFace,
    Delete,
    MsgFile,
    Pause,
    ShowPortrait,
    Switch,
)

from .conftest import needs_data

# ---- 合成 bank: face 链 SHOW 脚本结构照抄 face_rm00.anm 脚本 0/2 ----


def _show_script(x_in: float, x_bright: float, x_dim: float, x_out: float):
    """SHOW 脚本(face_rm00.anm 脚本 0/2 同构): interrupt 1入场/3亮/4暗/5退场。"""
    return build_script(
        [
            SetActiveSprite(time=0, flags=0, sprite=0),
            Anchor3(time=0, flags=0),
            SetTranslation(time=0, flags=0, x=x_in, y=16.0, z=0.0),
            StopHide(time=0, flags=0),
            InterruptLabel(time=0, flags=0, label=1),
            SetAlpha(time=0, flags=0, alpha=0),
            SetTranslation(time=0, flags=0, x=x_in, y=560.0, z=0.0),
            InterpPos(time=0, flags=0, duration=30, ease=4, x=x_bright, y=112.0, z=0.0),
            InterpAlpha(time=0, flags=0, duration=30, ease=0, alpha=255),
            Stop(time=30, flags=0),
            InterruptLabel(time=30, flags=0, label=2),
            StopHide(time=60, flags=0),
            InterruptLabel(time=60, flags=0, label=3),
            InterpAlpha(time=60, flags=0, duration=15, ease=0, alpha=255),
            InterpPos(
                time=60, flags=0, duration=15, ease=4, x=x_bright, y=112.0, z=0.0
            ),
            Stop(time=75, flags=0),
            InterruptLabel(time=75, flags=0, label=4),
            InterpAlpha(time=75, flags=0, duration=15, ease=0, alpha=128),
            InterpPos(time=75, flags=0, duration=15, ease=4, x=x_dim, y=128.0, z=0.0),
            Stop(time=90, flags=0),
            InterruptLabel(time=90, flags=0, label=5),
            InterpAlpha(time=90, flags=0, duration=30, ease=0, alpha=0),
            InterpPos(time=90, flags=0, duration=30, ease=0, x=x_out, y=128.0, z=0.0),
            ExitHide2(time=120, flags=0),
        ]
    )


def _spr(sid: int, w: int, h: int) -> SpriteSlot:
    return SpriteSlot(0, AnmSprite(sid, 0, 0, w, h))


def _face_bank() -> AnmBank:
    """自机 face 链: 脚本 0=左 2=右 + 表情 sprite 0/1(126x510)。"""
    return AnmBank(
        scripts={
            0: _show_script(-96.0, 40.0, 24.0, -96.0),
            2: _show_script(280.0, 280.0, 296.0, 416.0),
        },
        sprites={0: _spr(0, 126, 510), 1: _spr(1, 126, 510)},
    )


def _stage_bank() -> AnmBank:
    """本面 boss face: 表情 0/1 常规, 2 宽 200, 3 宽 300(offset 分档用)。"""
    return AnmBank(
        scripts={},
        sprites={
            0: _spr(0, 126, 510),
            1: _spr(1, 126, 510),
            2: _spr(2, 200, 512),
            3: _spr(3, 300, 512),
        },
    )


def _bank_of(name: str) -> AnmBank | None:
    if name in ("face_rm00.anm", "face_mr00.anm", "face_sk00.anm"):
        return _face_bank()
    if name.startswith("face_") and name.endswith("_00.anm"):
        return _stage_bank()
    return None


def _world(ex: MsgExecutor | None, *, stage_no: int = 1, character: int = 0):
    return SimpleNamespace(msg_vm=ex, stage_no=stage_no, character=character)


def _two_side_msg(right_face: int = 0) -> tuple:
    """左右登场 → boss 说话(左暗右亮) → 自机说话(左亮右暗) → 双双退场 → 结束。"""
    return (
        ShowPortrait(time=0, portrait_idx=0, anm_script_idx=0),
        ChangeFace(time=0, portrait_idx=0, anm_script_idx=0),
        Switch(time=0, idx=0, interrupt=1),
        Pause(time=1, duration=40),
        ShowPortrait(time=41, portrait_idx=1, anm_script_idx=0),
        ChangeFace(time=41, portrait_idx=1, anm_script_idx=right_face),
        Switch(time=41, idx=1, interrupt=1),
        Switch(time=41, idx=0, interrupt=4),
        Pause(time=42, duration=40),
        Switch(time=82, idx=0, interrupt=3),
        Switch(time=82, idx=1, interrupt=4),
        Pause(time=83, duration=40),
        Switch(time=123, idx=0, interrupt=5),
        Switch(time=123, idx=1, interrupt=5),
        Pause(time=124, duration=40),
        Delete(time=164),
    )


def _run(ex: MsgExecutor, dp: DialogPortraits, world, frames: int) -> list[list]:
    out = []
    for _ in range(frames):
        ex.step()
        out.append(dp.step(world, _bank_of))
    return out


def _side(sprites, key: str):
    return next((s for s in sprites if s.image.startswith(key)), None)


def test_silent_without_banks() -> None:
    """无 anm 数据(bank None): msg 照跑, 立绘产出空。"""
    ex = MsgExecutor(MsgFile(messages=[_two_side_msg()]))
    ex.read(0)
    dp = DialogPortraits(Rng(0))
    for _ in range(400):
        ex.step()
        assert dp.step(_world(ex), lambda name: None) == []


def test_speak_dim_bright_and_exit() -> None:
    """入场淡入 → boss 说话(左 128/右 255) → 换自机说话(左 255/右 128) → 退场全隐。"""
    ex = MsgExecutor(MsgFile(messages=[_two_side_msg()]))
    ex.read(0)
    dp = DialogPortraits(Rng(0))
    frames = _run(ex, dp, _world(ex), 400)
    # 左入场淡入完成(30f) → 亮; z 为 Gui 层
    left_lit = next(
        (
            i
            for i, f in enumerate(frames)
            if (s := _side(f, "face_rm00.anm:")) and s.alpha == 255
        ),
        None,
    )
    assert left_lit is not None
    assert _side(frames[left_lit], "face_rm00.anm:").z >= 100.0
    # 右侧入场淡入完成帧: boss 说话中, 左已被 SWITCH 4 压暗
    right_lit = next(
        (
            i
            for i, f in enumerate(frames)
            if (s := _side(f, "face_01_00.anm:")) and s.alpha == 255
        ),
        None,
    )
    assert right_lit is not None
    assert _side(frames[right_lit], "face_rm00.anm:").alpha == 128
    # 之后自机说话(SWITCH 3): 左回亮帧, 右已压暗
    left_relit = next(
        (
            i
            for i in range(right_lit + 1, len(frames))
            if (s := _side(frames[i], "face_rm00.anm:")) and s.alpha == 255
        ),
        None,
    )
    assert left_relit is not None
    assert _side(frames[left_relit], "face_01_00.anm:").alpha == 128
    # 双双退场(interrupt 5 滑出 30f 脚本自收) + 消息结束: 不再产出
    assert frames[-1] == [] and frames[-40] == [] and not ex.active


def test_portrait_images_not_cross_stage_or_character() -> None:
    """回归①串面: 左侧恒自机 face 链(按 character), 右侧恒本面 face_NN_00。"""
    for character, left_name in (
        (0, "face_rm00.anm"),
        (2, "face_mr00.anm"),
        (4, "face_sk00.anm"),
    ):
        ex = MsgExecutor(MsgFile(messages=[_two_side_msg()]))
        ex.read(0)
        dp = DialogPortraits(Rng(0))
        frames = _run(ex, dp, _world(ex, stage_no=3, character=character), 200)
        both = next(f for f in frames if len(f) == 2)
        assert {s.image.split(":")[0] for s in both} == {left_name, "face_03_00.anm"}
    for stage in (1, 2, 5):
        ex = MsgExecutor(MsgFile(messages=[_two_side_msg()]))
        ex.read(0)
        dp = DialogPortraits(Rng(0))
        frames = _run(ex, dp, _world(ex, stage_no=stage), 200)
        both = next(f for f in frames if len(f) == 2)
        fams = {s.image.split(":")[0] for s in both}
        assert f"face_{stage:02d}_00.anm" in fams, f"stage {stage} 右侧立绘缺失"
        assert all(
            f == f"face_{stage:02d}_00.anm" or not f.startswith("face_0") for f in fams
        )


def test_no_stale_portrait_across_messages() -> None:
    """回归②错隐/残留: 上一消息立绘不带到下一消息, 换 face 各自正确。"""
    mf = MsgFile(
        messages=[
            _two_side_msg(right_face=1),
            (
                ShowPortrait(time=0, portrait_idx=0, anm_script_idx=0),
                ChangeFace(time=0, portrait_idx=0, anm_script_idx=1),
                Switch(time=0, idx=0, interrupt=1),
                Pause(time=1, duration=40),
                ShowPortrait(time=41, portrait_idx=1, anm_script_idx=0),
                ChangeFace(time=41, portrait_idx=1, anm_script_idx=0),
                Switch(time=41, idx=1, interrupt=1),
                Pause(time=42, duration=40),
                Delete(time=82),
            ),
        ]
    )
    ex = MsgExecutor(mf)
    dp = DialogPortraits(Rng(0))
    w = _world(ex)
    ex.read(0)
    frames = _run(ex, dp, w, 400)
    assert any(_side(f, "face_01_00.anm:1") is not None for f in frames), (
        "msg0 右侧 face 1 未出现"
    )
    assert not ex.active
    assert frames[-1] == [] and dp.step(w, _bank_of) == []  # 消息间无残留
    ex.read(1)  # 下一条消息 = MsgRead memset, VM 全重置
    frames = _run(ex, dp, w, 300)
    assert any(_side(f, "face_rm00.anm:1") is not None for f in frames), (
        "msg1 左侧 face 1 未出现"
    )
    assert any(_side(f, "face_01_00.anm:0") is not None for f in frames), (
        "msg1 右侧 face 0 未出现"
    )
    assert all(_side(f, "face_01_00.anm:1") is None for f in frames), (
        "msg1 带出上一消息的 face"
    )


def test_change_face_width_offset() -> None:
    """CHANGE_FACE offset 分档 (Gui.cpp:878-898): >256 → (-208,-50), >128 → x=-80。"""
    ex = MsgExecutor(
        MsgFile(messages=[_two_side_msg(right_face=2)])
    )  # 右侧 face 2 宽 200
    ex.read(0)
    dp = DialogPortraits(Rng(0))
    frames = _run(ex, dp, _world(ex), 200)
    right = next(
        s for f in frames if (s := _side(f, "face_01_00.anm:2")) and s.alpha == 255
    )
    # 亮位 pos (280,112) + offset (-80,0), anchor3 中心锚 +w/2
    assert right.x == 280.0 - 80.0 + 100.0 and right.y == 112.0 + 256.0
    ex = MsgExecutor(MsgFile(messages=[_two_side_msg(right_face=3)]))  # face 3 宽 300
    ex.read(0)
    dp = DialogPortraits(Rng(0))
    frames = _run(ex, dp, _world(ex), 200)
    right = next(
        s for f in frames if (s := _side(f, "face_01_00.anm:3")) and s.alpha == 255
    )
    assert right.x == 280.0 - 208.0 + 150.0 and right.y == 112.0 - 50.0 + 256.0


def test_stage6_hidden_msgs() -> None:
    """6 面 msg 1/11 不画 (Gui.cpp:1124-1129); 同面其它 msg 照画。"""
    ex = MsgExecutor(MsgFile(messages=[_two_side_msg(), _two_side_msg()]))
    dp = DialogPortraits(Rng(0))
    w = _world(ex, stage_no=6)
    ex.read(1)
    frames = _run(ex, dp, w, 100)
    assert ex.active and all(f == [] for f in frames)
    ex.read(0)
    frames = _run(ex, dp, w, 100)
    assert any(_side(f, "face_rm00.anm:") is not None for f in frames)


def test_z_is_gui_layer() -> None:
    """对话立绘 z = Gui 层(>=100, 不裁剪不振屏), 在弹字(120)之下。"""
    assert 100.0 <= Z_PORTRAIT < 120.0


# ---- headless 全链(真机数据) ----


def _dialog_sprites(sprites):
    """只要对话立绘(z 与符卡宣言 cutin 区分)。"""
    return [s for s in sprites if s.z == Z_PORTRAIT and "face_" in s.image]


@needs_data
def test_chain_dialog_portraits_stage1() -> None:
    """一面战前对话: 左右立绘各一张/谁说话谁亮(另一方 128)/对话结束全隐。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    w.th07.lives = 99
    fx = GameFx(w)
    left_seen = right_seen = False
    left_bright = right_bright = False
    saw_active = False
    ended_at = -1
    hidden_after_end = True
    for i in range(9000):
        pressed = frozenset({Button.SHOT}) if i % 20 == 0 else frozenset()
        w.tick(InputFrame(pressed=pressed, held=frozenset({Button.SHOT})))
        sprites, _ = fx.step()
        ds = _dialog_sprites(sprites)
        left = _side(ds, "face_rm00.anm:")
        right = _side(ds, "face_01_00.anm:")
        left_seen = left_seen or left is not None
        right_seen = right_seen or right is not None
        if left is not None and right is not None:
            if left.alpha == 255 and right.alpha == 128:
                left_bright = True  # 自机说话: 左亮右暗
            if right.alpha == 255 and left.alpha == 128:
                right_bright = True  # boss 说话: 右亮左暗
        msg_active = w.msg_vm is not None and w.msg_vm.active
        saw_active = saw_active or msg_active
        if ended_at < 0 and saw_active and not msg_active and not fx.dialog.active:
            ended_at = i  # 首段对话收场(含退场脚本自收)
        if 0 <= ended_at < i and ds:
            hidden_after_end = False  # 收场后不应再有对话立绘
        if (
            left_seen
            and right_seen
            and left_bright
            and right_bright
            and 0 <= ended_at < i - 60
        ):
            break
    assert left_seen, "左侧(自机)立绘未出现"
    assert right_seen, "右侧(boss)立绘未出现"
    assert left_bright, "自机说话时未左亮右暗"
    assert right_bright, "boss 说话时未右亮左暗"
    assert ended_at > 0, "对话未收场"
    assert hidden_after_end, "对话结束后立绘残留"


@needs_data
def test_chain_dialog_portraits_not_cross_stage() -> None:
    """二面对话右侧是 face_02_00(不串一面图), 左侧仍是自机。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, stage_no=2, seed=42)
    w.th07.lives = 99
    fx = GameFx(w)
    right_img = ""
    for i in range(9000):
        pressed = frozenset({Button.SHOT}) if i % 20 == 0 else frozenset()
        w.tick(InputFrame(pressed=pressed, held=frozenset({Button.SHOT})))
        sprites, _ = fx.step()
        ds = _dialog_sprites(sprites)
        for s in ds:
            assert not s.image.startswith("face_01_00.anm:"), "立绘串到一面"
            if s.image.startswith("face_02_00.anm:"):
                right_img = s.image
        if right_img:
            break
    assert right_img, "二面对话右侧立绘未出现"
