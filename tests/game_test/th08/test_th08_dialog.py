"""th08 对话立绘测试 —— msg VM 的 op15/17/18 状态 + DialogueViewTh08 渲染。

纯逻辑用例用合成 msg(不需要真实资源); 渲染/立绘选择正确性用例打
needs_data(真 th08.dat + SDL dummy)。避雷对照: th07 BUGS.md 增量#2
(压暗缓存跨关撞键) —— 本实现压暗走 face anm 脚本调制, 无派生图缓存,
跨关隔离用例直接钉"换关 face 集不串 / 压暗用的是本槽自己的脸"。
"""

from __future__ import annotations

import os
import struct

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from touhou.games.th08.msg_vm import MsgVmTh08  # noqa: E402
from touhou.schema.msg import MsgFile  # noqa: E402

from .conftest import needs_data  # noqa: E402

pygame.init()


def _ins(time: int, op: int, args: bytes = b"") -> bytes:
    return struct.pack("<HBB", time, op, len(args)) + args


def _synth_msg(*msgs: bytes) -> MsgFile:
    offs = []
    blob = b""
    for m in msgs:
        offs.append(len(blob))
        blob += m
    head = struct.pack("<i", len(msgs)) + struct.pack(
        f"<{len(msgs)}i", *[4 + 4 * len(msgs) + o for o in offs]
    )
    return MsgFile.parse(head + blob, text_xor=0x77)


def _portrait_msg() -> MsgFile:
    """msg0: 立绘配置序列 —— op15 全槽(speaker 0, 槽0 sprite 6) →
    op15 跨对换 speaker 2 → op15 跨对换 speaker 1 → op17 单槽 speaker 3 →
    op15 同对(敌方对内)换 speaker 2 → op18 关文本框 → DELETE。"""
    msg0 = (
        _ins(0, 15, struct.pack("<5i", 0, 6, -1, -1, -1))
        + _ins(1, 15, struct.pack("<5i", 2, -1, -1, 2, -1))
        + _ins(2, 15, struct.pack("<5i", 1, -1, -1, -1, -1))
        + _ins(3, 17, struct.pack("<2i", 3, 4))
        + _ins(4, 15, struct.pack("<5i", 2, -1, -1, -1, -1))
        + _ins(5, 18, b"\x00")
        + _ins(6, 0)
    )
    return _synth_msg(msg0)


def test_op15_first_configure_dances_all_dim() -> None:
    """首次配置(C currentPortraitIndex=0xff): 其余槽全 4, 说话方 3。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    vm.step()
    assert [p.pending_interrupt for p in vm.portraits] == [3, 4, 4, 4]
    assert vm.portrait_sprites == [6, -1, -1, -1]
    assert vm.current_portrait_index == 0


def test_op15_cross_side_switch_dims_in_place() -> None:
    """跨对切换(自机 0 → 敌方 2): 旧说话方 6(原地压暗), 其余 4, 新方 3
    (Gui.cpp:291-306)。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    vm.step()
    vm.step()
    assert [p.pending_interrupt for p in vm.portraits] == [6, 4, 3, 4]
    assert vm.portrait_sprites == [6, -1, 2, -1]
    assert vm.current_portrait_index == 2


def test_op15_switch_back_cross_side() -> None:
    """再换回自机侧(speaker 2 → 1, 跨对): 旧方 6, 其余 4, 新方 3。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    for _ in range(3):
        vm.step()
    assert [p.pending_interrupt for p in vm.portraits] == [4, 3, 6, 4]
    assert vm.current_portrait_index == 1


def test_op17_single_portrait() -> None:
    """op17: 单槽配置, sprite 只写该槽(Gui.cpp:330-383); 旧说话方跨对
    (自机 1 → 敌方 3)得 6(原地压暗)。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    for _ in range(4):
        vm.step()
    assert vm.current_portrait_index == 3
    assert [p.pending_interrupt for p in vm.portraits] == [4, 6, 4, 3]
    assert vm.portrait_sprites == [6, -1, 2, 4]


def test_op15_same_side_switch_dims_plain() -> None:
    """同对切换(speaker 3 → 2 都是敌方对): 旧方得 4 而非 6
    (Gui.cpp:339-343)。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    for _ in range(5):
        vm.step()
    assert [p.pending_interrupt for p in vm.portraits] == [4, 4, 3, 4]
    assert vm.current_portrait_index == 2


def test_op18_text_box_visible_and_read_reset() -> None:
    """op18 关文本框; read() 复位 text_box_visible/说话方/槽 sprite。"""
    vm = MsgVmTh08(_portrait_msg())
    vm.read(0)
    for _ in range(6):
        vm.step()
    assert vm.text_box_visible is False
    vm.read(0)
    assert vm.text_box_visible is True
    assert vm.current_portrait_index == -1
    assert vm.portrait_sprites == [-1] * 4


# ---- 真机: 立绘选择正确性(needs_data) ----

DAT_FLOW_FRAMES = 300


def _drive(dat, msg_name: str, character: int, stage: int, frames: int):
    """真 msg 跑 frames 帧(定期按 Z), 返回 (view, vm, 末帧 surface)。"""
    from touhou.games.th08.crypt import try_decrypt_from_table
    from touhou.games.th08.view.dialog_view import DialogueViewTh08
    from touhou.schema.archive import open_archive

    arc = open_archive(dat, game="th08")
    mf = MsgFile.parse(try_decrypt_from_table(arc.load(msg_name)), text_xor=0x77)
    vm = MsgVmTh08(mf)
    vm.read(0)
    view = DialogueViewTh08(dat, character=character, stage=stage)
    surf = pygame.Surface((384, 448), pygame.SRCALPHA)
    for f in range(frames):
        if not vm.step(advance_pressed=(f % 30 == 0)):
            break
        surf.fill((0, 0, 0, 0))
        view.render(surf, vm, frame=f)
    return view, vm, surf


@needs_data
def test_face_set_identity() -> None:
    """槽位 anm 归属: 自机双立绘按机体, 敌方按面(Spellcard.cpp:434-560)。"""
    from touhou.games.th08.view.dialog_view import DialogueViewTh08
    from touhou.paths import DEFAULT_DATA_PATHS

    dat = DEFAULT_DATA_PATHS["th08"]

    def names(character: int, stage: int) -> list[str | None]:
        v = DialogueViewTh08(dat, character=character, stage=stage)
        return [None if s is None else s.sbank.name for s in v._slots]

    assert names(0, 1) == ["face_rm00.anm", "face_yk00.anm", "face_st01.anm", None]
    assert names(1, 1)[:2] == ["face_mr00.anm", "face_al00.anm"]
    assert names(7, 1)[:2] == ["face_mr00.anm", "face_al00.anm"]  # 爱丽丝单人
    assert names(2, 1)[:2] == ["face_sk00.anm", "face_rs00.anm"]
    assert names(3, 1)[:2] == ["face_ym00.anm", "face_yy00.anm"]
    assert names(0, 4)[2] == "face_st04a.anm"  # 4A
    assert names(0, 5)[2] == "face_st04b.anm"  # 4B
    assert names(0, 6)[2:] == ["face_st05.anm", "face_st05b.anm"]  # 5 面双 boss
    assert names(0, 8)[2:] == ["face_st06.anm", "face_st07.anm"]  # 6B
    assert names(0, 9)[2:] == ["face_st08m.anm", "face_st08.anm"]  # EX


@needs_data
def test_dialog_render_smoke_real_msg() -> None:
    """msg1a 真跑: boss 登场可见, 说话方切换后自机压暗, 全程不炸。"""
    from touhou.paths import DEFAULT_DATA_PATHS

    view, vm, surf = _drive(
        DEFAULT_DATA_PATHS["th08"], "msg1a.dat", 0, 1, DAT_FLOW_FRAMES
    )
    assert vm.active  # 300 帧内 msg0 还在(首个 PAUSE 500 帧)
    boss = view._slots[2]
    assert boss is not None and boss.vm.visible, "boss 立绘应已登场"
    reimu = view._slots[0]
    assert reimu is not None and reimu.vm.visible
    assert reimu.vm.color[0] < 255, "boss 说话时灵梦应压暗(interrupt 6)"
    yukari = view._slots[1]
    assert yukari is not None and yukari.vm.visible, "双人机体另一人应在场(压暗)"


@needs_data
def test_dimmed_portrait_is_own_face() -> None:
    """A 说话 B 压暗不能显示成 C: 压暗槽的图必须来自本槽自己的 anm
    (SpriteBank 缓存对象身份), 颜色调制 <255。"""
    from touhou.paths import DEFAULT_DATA_PATHS

    view, vm, _ = _drive(DEFAULT_DATA_PATHS["th08"], "msg1a.dat", 0, 1, 200)
    for i, expect in enumerate(("face_rm00.anm", "face_yk00.anm")):
        slot = view._slots[i]
        assert slot is not None and slot.surf is not None
        assert slot.sbank.name == expect
        # SpriteBank 缓存身份: 图必须是该 anm 文件的 sprite, 不是别书的脸
        flat = slot._flat[slot.vm.active_sprite_idx]
        assert slot.surf is slot.sbank.bank.sprite(expect, flat[1], entry=flat[0]), (
            f"槽 {i} 立绘图不是 {expect} 自己的 sprite"
        )


@needs_data
def test_cross_stage_faces_dont_bleed() -> None:
    """跨关 face 集不串: 同一 msg 流程灌进 1 面/2 面两个视图, 敌方侧
    像素必须不同; 同关两视图必须逐字节一致(确定性)。"""
    from touhou.paths import DEFAULT_DATA_PATHS

    dat = DEFAULT_DATA_PATHS["th08"]
    _, _, s1a = _drive(dat, "msg1a.dat", 0, 1, DAT_FLOW_FRAMES)
    _, _, s2 = _drive(dat, "msg1a.dat", 0, 2, DAT_FLOW_FRAMES)
    _, _, s1b = _drive(dat, "msg1a.dat", 0, 1, DAT_FLOW_FRAMES)
    b1a = pygame.image.tobytes(s1a, "RGBA")
    assert b1a != pygame.image.tobytes(s2, "RGBA"), "跨关立绘串台"
    assert b1a == pygame.image.tobytes(s1b, "RGBA"), "同关渲染不确定"


@needs_data
def test_backend_dialog_smoke_real_game() -> None:
    """真对局后端链路: begin_game 建出对话视图, 中超对话激活后
    render_game 走 DialogueViewTh08 渲染不炸(空跑到激活再渲染, 省耗时)。"""
    from touhou.games.th08.view import PygameTh08Renderer
    from touhou.games.th08.world import ImperishableNight
    from touhou.paths import DEFAULT_DATA_PATHS

    dp = DEFAULT_DATA_PATHS["th08"]
    renderer = PygameTh08Renderer(dp)
    renderer.open(scale=1)
    try:
        game = ImperishableNight(data_path=dp, character=0, difficulty=1, seed=1)
        renderer.begin_game(game, character=0)
        assert renderer._dialog_view is not None, "对话视图应建出(未回退纯文字)"
        # 对话在中超后触发(对照 test_th08_world.py 的 msg 门控用例: 9000 帧)
        activated = False
        for f in range(9000):
            keys = [False] * 8
            keys[f % 4] = True  # 周期性挪动防站桩死
            game.tick(keys=tuple(keys), advance=True)
            if game.game_over:
                game.game_over = False
                game.lives = 3.0
            if game.msg_active():
                activated = True
                break
        assert activated, "9000 帧内一面中超对话应激活"
        # 激活后渲染推进: 立绘脚本随渲染跑, 自机槽应已起脚本
        for _ in range(120):
            game.tick(keys=(False,) * 8, advance=True)
            renderer.render_game(game)
        slot0 = renderer._dialog_view._slots[0]
        assert slot0 is not None and slot0.vm.active_sprite_idx >= 0
    finally:
        renderer.close()
