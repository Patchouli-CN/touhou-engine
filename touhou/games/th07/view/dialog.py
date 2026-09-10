"""boss 战前/后对话立绘: msg 透出状态驱动 face 链 ANM VM (GuiImpl::DrawDialogue 立绘段)。

状态来自 engine.msg 的 MsgExecutor(每帧采 MsgPortraitState 做边沿检测): 入场
起 SHOW 脚本(左 0/右 2, SHOW_PORTRAIT 实参恒 0, 全 8 个 msg 文件扫描确认),
CHANGE_FACE 换 sprite + 按宽调 offset, SWITCH interrupt 边沿喂 VM——滑入/说话
方亮(alpha 255)非说话方暗(128)/退场滑出全是 face 脚本原生行为, 不做手工压暗。
立绘画在对话窗之下(先画), 脚本坐标即窗口坐标。无 anm 数据全层静默。
"""

from __future__ import annotations

from ....engine import SpriteDraw
from ....engine.anm import AnmBank, AnmMachine
from ....engine.rng import Rng
from ..world import Th07World
from .spellcard import _FACE_ANM

_SCR_SHOW = (0, 2)  # SHOW_PORTRAIT 脚本: 左/右 (Gui.cpp:850-856 + AnmIdx.hpp:250-252)
# 6 面这两个 msg 整段不画 (Gui.cpp:1124-1129)
_ST6_HIDDEN_MSGS = (1, 11)

Z_PORTRAIT = 104.0  # Gui 层(z>=100 不裁剪不振), 对话窗(未接)之下


class DialogPortraits:
    """左右两槽对话立绘: 每帧采 msg VM 状态推进两台 face 链 ANM VM。"""

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vms: list[AnmMachine | None] = [None, None]
        self._faces = [-1, -1]  # 已应用到 VM 的 face(换脸边沿)
        self._fed = [0, 0]  # 已喂给 VM 的 interrupt(跳转边沿)
        self._was_active = False  # msg 活动边沿: 新对话 = MsgRead memset, VM 重置

    @property
    def active(self) -> bool:
        return any(m is not None for m in self._vms)

    def reset(self) -> None:
        self._vms = [None, None]
        self._faces = [-1, -1]
        self._fed = [0, 0]

    # ---- 每帧 ----
    def step(self, world: Th07World, bank_of) -> list[SpriteDraw]:
        vm = world.msg_vm
        if vm is None or not vm.active:
            # currentMsgIdx < 0: 不画也不跑 (Gui.cpp:1120-1122)
            self.reset()
            self._was_active = False
            return []
        if not self._was_active:
            self.reset()  # MsgRead memset (Gui.cpp:763)
            self._was_active = True
        hidden = world.stage_no == 6 and vm.current_msg_idx in _ST6_HIDDEN_MSGS
        out: list[SpriteDraw] = []
        for side in (0, 1):
            p = vm.portraits[side]
            machine = self._vms[side]
            if p.visible and machine is None:
                machine = self._show(world, bank_of, side, p.face)
                self._vms[side] = machine
                self._faces[side] = p.face
                self._fed[side] = 0
            if machine is None:
                continue
            if p.face != self._faces[side]:
                self._change_face(world, bank_of, side, machine, p.face)
                self._faces[side] = p.face
            if p.pending_interrupt != self._fed[side]:
                machine.pending_interrupt = p.pending_interrupt
                self._fed[side] = p.pending_interrupt
            machine.execute()  # RunMsg 帧尾 ExecuteScript (Gui.cpp:1097-1098)
            if not machine.alive:
                self._vms[side] = None  # 退场脚本 ExitHide2 自收
                continue
            if hidden:
                continue
            spr = self._draw(world, bank_of, side, machine)
            if spr is not None:
                out.append(spr)
        return out

    # ---- 内部 ----
    def _side_name(self, world: Th07World, side: int) -> str:
        """该侧立绘图所在的 anm: 左=自机 face 链, 右=本面 boss (sprite 基址分侧, Gui.cpp:871-877)。"""
        if side == 0:
            return _FACE_ANM[world.character // 2]
        return f"face_{world.stage_no:02d}_00.anm"

    def _show(
        self, world: Th07World, bank_of, side: int, face: int
    ) -> AnmMachine | None:
        """MSG_SHOW_PORTRAIT: 起入场脚本(两侧脚本都在自机 face 链), 应用同帧换脸。"""
        bank: AnmBank | None = bank_of(_FACE_ANM[world.character // 2])
        if bank is None:
            return None
        m = AnmMachine(self._rng)
        m.start(bank.scripts.get(_SCR_SHOW[side]))
        if not m.alive:
            return None
        # 宽度规则 (Gui.cpp:857-868): 脚本首 sprite 宽 >128 → offset.x=-112
        slot = bank.sprites.get(m.active_sprite_idx)
        if slot is not None:
            m.offset[0] = -112.0 if slot.sprite.w > 128 else 0.0
        self._change_face(world, bank_of, side, m, face)
        return m

    def _change_face(
        self, world: Th07World, bank_of, side: int, m: AnmMachine, face: int
    ) -> None:
        """MSG_CHANGE_FACE: 换 sprite(分侧图) + 按宽调 offset (Gui.cpp:870-898)。"""
        bank: AnmBank | None = bank_of(self._side_name(world, side))
        if bank is None:
            return
        slot = bank.sprites.get(face)
        if slot is None:
            return
        m.active_sprite_idx = face
        w = slot.sprite.w
        if w > 256:
            m.offset[0] = -208.0
            m.offset[1] = -50.0
        elif w > 128:
            m.offset[0] = -80.0  # y 不动 (Gui.cpp:887-893)
        else:
            m.offset[0] = 0.0  # y 不动 (Gui.cpp:894-898)

    def _draw(
        self, world: Th07World, bank_of, side: int, m: AnmMachine
    ) -> SpriteDraw | None:
        """DrawNoRotation (Gui.cpp:1150-1154): 左侧画 pos, 右侧画 pos+offset。"""
        if not m.visible or m.active_sprite_idx < 0 or not m.color[3]:
            return None
        name = self._side_name(world, side)
        bank: AnmBank | None = bank_of(name)
        w = h = 0.0
        if bank is not None:
            slot = bank.sprites.get(m.active_sprite_idx)
            if slot is not None:
                w, h = float(slot.sprite.w), float(slot.sprite.h)
        x, y = m.pos[0], m.pos[1]
        if side == 1:
            x += m.offset[0]
            y += m.offset[1]
        # anchor3: pos 是 quad 左上 → 中心锚平移 (AnmManager.cpp:1018-1041)
        if m.anchor & 1:
            x += w * abs(m.scale[0]) / 2.0
        if m.anchor & 2:
            y += h * abs(m.scale[1]) / 2.0
        return SpriteDraw(
            f"{name}:{m.active_sprite_idx}",
            x,
            y,
            z=Z_PORTRAIT,
            alpha=m.color[3],
            scale_x=m.scale[0],
            scale_y=m.scale[1],
            color=(m.color[0], m.color[1], m.color[2]),
            blend_mode=m.blend_mode,
        )
