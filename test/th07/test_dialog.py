"""对话立绘测试: msg 状态→渲染产出单测(合成 bank) + headless 全链(needs_data)。

历史回归针对: ①立绘串面(右侧用了别面 boss 图) ②跨消息立绘残留(错隐/错出)。
"""

from __future__ import annotations

from types import SimpleNamespace

from touhou.engine import InputFrame
from touhou.engine.anm import AnmBank, SpriteSlot, build_script
from touhou.engine.msg import MsgExecutor
from touhou.engine.rng import Rng
from touhou.games.th07.view.dialog import Z_BOX, Z_PORTRAIT, DialogBox, DialogPortraits
from touhou.games.th07.view.fx import GameFx
from touhou.schemas.anm import AnmSprite
from touhou.schemas.anm_script import (
    Anchor3,
    Exit,
    ExitHide2,
    Fade,
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
    Dialogue,
    MsgFile,
    Pause,
    ShowPortrait,
    Switch,
    TextIntroduce,
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


# ---- 对话窗本体(DialogBox): 底图/文字/介绍名 ----


def _line_script(sprite: int, x: float, y: float, *, intro: bool):
    """text.anm 行信封(脚本 0-3 同构): 对话=12f 淡入后 Exit, 介绍名=60f 到 240 后定时退场。"""
    instrs = [SetActiveSprite(time=0, flags=0, sprite=sprite)]
    if not intro:
        instrs.append(Anchor3(time=0, flags=0))
    instrs += [
        SetTranslation(time=0, flags=0, x=x, y=y, z=0.0),
        SetAlpha(time=0, flags=0, alpha=0),
        Fade(
            time=0, flags=0, alpha=240 if intro else 255, duration=60 if intro else 12
        ),
    ]
    if intro:
        instrs += [
            Fade(time=360, flags=0, alpha=0, duration=60),
            ExitHide2(time=420, flags=0),
        ]
    else:
        instrs.append(Exit(time=12, flags=0))
    return build_script(instrs)


def _text_bank() -> AnmBank:
    """text.anm 合成: 脚本 0/1 对话(72,390)/(72,410), 2/3 介绍名(272,352)/(272,368)。"""
    return AnmBank(
        scripts={
            0: _line_script(0, 72.0, 390.0, intro=False),
            1: _line_script(1, 72.0, 410.0, intro=False),
            2: _line_script(2, 272.0, 352.0, intro=True),
            3: _line_script(3, 272.0, 368.0, intro=True),
        },
        sprites={
            0: _spr(0, 320, 17),
            1: _spr(1, 320, 17),
            2: _spr(2, 256, 17),
            3: _spr(3, 256, 17),
        },
    )


def _box_bank_of(name: str):
    if name == "text.anm":
        return _text_bank()
    return _bank_of(name)


def _box_of(sprites):
    return next((s for s in sprites if s.image == "misc:dialogbox"), None)


def _run_box(ex: MsgExecutor, db: DialogBox, world, frames: int) -> list[tuple]:
    out = []
    for _ in range(frames):
        ex.step()
        out.append(db.step(world, _box_bank_of))
    return out


def test_box_grows_with_msg_timer() -> None:
    """底图: x48..400/y384 起前 60 帧渐高到 48, z 在立绘之上, 消息结束后消失。"""
    ex = MsgExecutor(
        MsgFile(messages=[(Pause(time=120, duration=5), Delete(time=130))])
    )
    ex.read(0)
    db = DialogBox(Rng(0))
    frames = _run_box(ex, db, _world(ex), 200)
    early = _box_of(frames[30][0])
    assert early is not None and 0 < early.scale_y < 48.0  # timer*48/60 渐高
    assert (early.x, early.y, early.scale_x) == (48.0, 384.0, 352.0)
    full = _box_of(frames[100][0])
    assert full is not None and full.scale_y == 48.0
    assert full.z == Z_BOX > Z_PORTRAIT
    assert all(_box_of(s) is None for s, _ in frames[-20:])  # Delete 后不画


def test_box_without_any_banks() -> None:
    """无 anm 数据: 底图照画(程序化), 文字静态信封兜底(alpha 255)。"""
    ex = MsgExecutor(
        MsgFile(
            messages=[
                (
                    Dialogue(time=0, color=0, line=0, text="テスト"),
                    Pause(time=1, duration=300),
                    Delete(time=400),
                )
            ]
        )
    )
    ex.read(0)
    db = DialogBox(Rng(0))
    world = _world(ex)
    out = []
    for _ in range(40):
        ex.step()
        out.append(db.step(world, lambda name: None))
    box = _box_of(out[-1][0])
    assert box is not None
    text = next(t for _, ts in out if (t := next((x for x in ts if x.text), None)))
    assert (text.x, text.y, text.rgba[3]) == (72.0, 390.0, 255)


def test_dialog_lines_typewriter_and_fade() -> None:
    """对话两行: (72,390)/(72,410) 逐字显示 + 12f 淡入, 颜色按 textColorsA 分色。"""
    ex = MsgExecutor(
        MsgFile(
            messages=[
                (
                    Dialogue(time=0, color=0, line=0, text="さむ〜いい加減"),
                    Dialogue(time=0, color=1, line=1, text="かい？"),
                    Pause(time=1, duration=300),
                    Delete(time=400),
                )
            ]
        )
    )
    ex.read(0)
    db = DialogBox(Rng(0))
    frames = _run_box(ex, db, _world(ex), 100)
    # 逐字: 中途某帧是前缀, 最终全量
    line0 = [ts[0] for _, ts in frames if ts and ts[0].y == 390.0]
    assert any(0 < len(t.text) < 7 for t in line0)
    assert line0[-1].text == "さむ〜いい加減"
    assert line0[-1].rgba == (0xE8, 0xF0, 0xFF, 255)
    fading = next(t for t in line0 if t.rgba[3] < 255)
    assert fading is not None  # 12f 淡入途中
    line1 = [t for _, ts in frames for t in ts if t.y == 410.0]
    assert line1[-1].text == "かい？" and line1[-1].x == 72.0
    assert line1[-1].rgba == (0xFF, 0xE8, 0xF0, 255)


def test_intro_name_right_aligned_and_fades_out() -> None:
    """介绍名: 右缘 400(中心锚 272 + sprite 半宽 128)右对齐, 峰值 alpha 240, 420f 自隐。"""
    name0 = "冬の忘れ物　　　　　"
    ex = MsgExecutor(
        MsgFile(
            messages=[
                (
                    TextIntroduce(time=0, color=1, line=0, text=name0),
                    TextIntroduce(time=0, color=1, line=1, text="レティ"),
                    Pause(time=1, duration=600),
                    Delete(time=700),
                )
            ]
        )
    )
    ex.read(0)
    db = DialogBox(Rng(0))
    frames = _run_box(ex, db, _world(ex), 500)
    names = [t for _, ts in frames for t in ts if t.y < 384.0]
    assert names, "介绍名未出现"
    full = next(t for t in names if t.text == name0)
    assert full.x + 15.0 * len(name0) == 400.0  # 全角 15px/字, 右缘 400
    assert full.y == 352.0 - 8.5
    peak = max(t.rgba[3] for t in names)
    assert peak == 240
    assert not [t for _, ts in frames[430:] for t in ts if t.y < 384.0], "420f 后名未隐"


def test_stage6_hidden_also_hides_box() -> None:
    """6 面 msg 1/11: 底图/文字也不画 (Gui.cpp:1124-1129 早退在底图之前)。"""
    msg = (
        Dialogue(time=0, color=0, line=0, text="あ"),
        Pause(time=1, duration=100),
        Delete(time=200),
    )
    ex = MsgExecutor(MsgFile(messages=[msg, msg]))
    db = DialogBox(Rng(0))
    w = _world(ex, stage_no=6)
    ex.read(1)
    frames = _run_box(ex, db, w, 100)
    assert ex.active and all(s == [] and t == [] for s, t in frames)
    ex.read(0)
    frames = _run_box(ex, db, w, 100)
    assert any(_box_of(s) is not None for s, _ in frames)


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


@needs_data
def test_chain_dialog_box_stage1() -> None:
    """一面战前对话: 底图渐高到 48/文字在 (72,390) 起/介绍名出现后定时自隐。"""
    from touhou.engine import Button
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    w.th07.lives = 99
    fx = GameFx(w)
    box_full = box_growing = False
    saw_line0 = saw_name = False
    name_gone_after = False
    name_last_seen = -1
    for i in range(9000):
        pressed = frozenset({Button.SHOT}) if i % 20 == 0 else frozenset()
        w.tick(InputFrame(pressed=pressed, held=frozenset({Button.SHOT})))
        sprites, texts = fx.step()
        box = _box_of(sprites)
        if box is not None:
            box_growing = box_growing or box.scale_y < 48.0
            box_full = box_full or box.scale_y == 48.0
            assert box.z == Z_BOX > Z_PORTRAIT
        for t in texts:
            if t.y == 390.0 and t.x == 72.0:
                saw_line0 = True  # 对话行 1 锚点 (text.anm 脚本 0)
            if "レティ" in t.text:
                saw_name = True
                name_last_seen = i
        if saw_name and i > name_last_seen + 5:
            name_gone_after = True  # 介绍名信封 420f 自隐后不再出现
        if box_full and saw_line0 and name_gone_after:
            break
    assert box_growing and box_full, "底图渐高/满高未观察到"
    assert saw_line0, "对话文字未在 (72,390) 出现"
    assert saw_name, "介绍名(レティ)未出现"
    assert name_gone_after, "介绍名未按时自隐"
