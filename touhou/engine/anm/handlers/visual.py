"""视觉状态指令 handler(sprite/位置/旋转/缩放/颜色/插值/滚动)。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....schemas.anm_script import (
    Anchor3,
    AnmInstr,
    Fade,
    FlipX,
    FlipY,
    InterpAlpha,
    InterpColor,
    InterpPos,
    InterpRotate,
    InterpScale,
    InterpScale2,
    PosTimeAccel,
    PosTimeDecel,
    PosTimeLinear,
    SetActiveSprite,
    SetAlpha,
    SetAngleVel,
    SetAutoRotate,
    SetBlend,
    SetCameraMode,
    SetColor,
    SetRotation,
    SetScale,
    SetScaleSpeed,
    SetScrollPosX,
    SetScrollPosY,
    SetScrollVelX,
    SetScrollVelY,
    SetTranslation,
    SetUseOffset,
    SetVisibility,
    SetZwriteDisable,
)
from .base import Handler, pos_interp_begin
from .control import _noop

if TYPE_CHECKING:
    from ..vm import AnmMachine


def _set_active_sprite(vm: AnmMachine, ins: SetActiveSprite) -> None:
    # arg + spriteIndices[anmFileIdx] — AnmManager.cpp:1674-1678
    vm.visible = True
    vm.active_sprite_idx = vm.ivar(ins.sprite, ins.flags, 0) + vm.sprite_base


def _set_translation(vm: AnmMachine, ins: SetTranslation) -> None:
    v = [
        vm.fvar(ins.x, ins.flags, 0),
        vm.fvar(ins.y, ins.flags, 1),
        vm.fvar(ins.z, ins.flags, 2),
    ]
    if vm.use_offset:
        vm.offset = v
    else:
        vm.pos = v


def _set_scale(vm: AnmMachine, ins: SetScale) -> None:
    vm.scale = [vm.fvar(ins.x, ins.flags, 0), vm.fvar(ins.y, ins.flags, 1)]


def _set_alpha(vm: AnmMachine, ins: SetAlpha) -> None:
    vm.color[3] = ins.alpha & 255


def _set_color(vm: AnmMachine, ins: SetColor) -> None:
    vm.color[0] = (ins.rgb >> 16) & 255
    vm.color[1] = (ins.rgb >> 8) & 255
    vm.color[2] = ins.rgb & 255


def _flip_x(vm: AnmMachine, ins: FlipX) -> None:
    vm.scale[0] *= -1.0


def _flip_y(vm: AnmMachine, ins: FlipY) -> None:
    vm.scale[1] *= -1.0


def _set_rotation(vm: AnmMachine, ins: SetRotation) -> None:
    vm.rotation = [
        vm.fvar(ins.x, ins.flags, 0),
        vm.fvar(ins.y, ins.flags, 1),
        vm.fvar(ins.z, ins.flags, 2),
    ]


def _set_angle_vel(vm: AnmMachine, ins: SetAngleVel) -> None:
    vm.angle_vel = [
        vm.fvar(ins.x, ins.flags, 0),
        vm.fvar(ins.y, ins.flags, 1),
        vm.fvar(ins.z, ins.flags, 2),
    ]


def _set_scale_speed(vm: AnmMachine, ins: SetScaleSpeed) -> None:
    vm.scale_growth = [vm.fvar(ins.x, ins.flags, 0), vm.fvar(ins.y, ins.flags, 1)]


def _fade(vm: AnmMachine, ins: Fade) -> None:
    vm.color_initial[3] = vm.color[3]
    vm.color_final[3] = ins.alpha & 255
    vm.alpha_interp.restart(vm.ivar(ins.duration, ins.flags, 1), 0)


def _set_blend(vm: AnmMachine, ins: SetBlend) -> None:
    vm.blend_mode = ins.mode


def _pos_time(
    vm: AnmMachine, ins: PosTimeLinear | PosTimeDecel | PosTimeAccel, ease: int
) -> None:
    pos_interp_begin(
        vm,
        vm.ivar(ins.duration, ins.flags, 3),
        ease,
        [
            vm.fvar(ins.x, ins.flags, 0),
            vm.fvar(ins.y, ins.flags, 1),
            vm.fvar(ins.z, ins.flags, 2),
        ],
    )


def _pos_time_linear(vm: AnmMachine, ins: PosTimeLinear) -> None:
    _pos_time(vm, ins, 0)


def _pos_time_decel(vm: AnmMachine, ins: PosTimeDecel) -> None:
    _pos_time(vm, ins, 4)


def _pos_time_accel(vm: AnmMachine, ins: PosTimeAccel) -> None:
    _pos_time(vm, ins, 6)


def _anchor3(vm: AnmMachine, ins: Anchor3) -> None:
    vm.anchor = 3


def _set_use_offset(vm: AnmMachine, ins: SetUseOffset) -> None:
    vm.use_offset = bool(ins.value)


def _set_auto_rotate(vm: AnmMachine, ins: SetAutoRotate) -> None:
    vm.auto_rotate = ins.value & 0xFFFF


def _set_scroll_pos_x(vm: AnmMachine, ins: SetScrollPosX) -> None:
    vm.uv_scroll[0] = (vm.uv_scroll[0] + vm.fvar(ins.delta, ins.flags, 0)) % 1.0


def _set_scroll_pos_y(vm: AnmMachine, ins: SetScrollPosY) -> None:
    vm.uv_scroll[1] = (vm.uv_scroll[1] + vm.fvar(ins.delta, ins.flags, 0)) % 1.0


def _set_visibility(vm: AnmMachine, ins: SetVisibility) -> None:
    vm.visible = bool(ins.visible)


def _interp_scale(vm: AnmMachine, ins: InterpScale) -> None:
    vm.scale_interp.restart(vm.ivar(ins.duration, ins.flags, 2), 0)
    vm.scale_initial = list(vm.scale)
    vm.scale_final = [vm.fvar(ins.x, ins.flags, 0), vm.fvar(ins.y, ins.flags, 1)]


def _set_zwrite_disable(vm: AnmMachine, ins: SetZwriteDisable) -> None:
    vm.zwrite_disable = ins.value


def _interp_pos(vm: AnmMachine, ins: InterpPos) -> None:
    pos_interp_begin(
        vm,
        vm.ivar(ins.duration, ins.flags, 0),
        ins.ease & 255,
        [
            vm.fvar(ins.x, ins.flags, 2),
            vm.fvar(ins.y, ins.flags, 3),
            vm.fvar(ins.z, ins.flags, 4),
        ],
    )


def _interp_color(vm: AnmMachine, ins: InterpColor) -> None:
    vm.color_interp.restart(vm.ivar(ins.duration, ins.flags, 0), ins.ease & 255)
    vm.color_initial[:3] = vm.color[:3]
    # 参数是 b[0..2] 连续三字节 = 0xBBGGRR 小端 — AnmManager.cpp:1915-1917
    vm.color_final[:3] = [ins.rgb & 255, (ins.rgb >> 8) & 255, (ins.rgb >> 16) & 255]


def _interp_alpha(vm: AnmMachine, ins: InterpAlpha) -> None:
    vm.alpha_interp.restart(vm.ivar(ins.duration, ins.flags, 0), ins.ease & 255)
    vm.color_initial[3] = vm.color[3]
    vm.color_final[3] = ins.alpha & 255


def _interp_rotate(vm: AnmMachine, ins: InterpRotate) -> None:
    vm.rot_interp.restart(vm.ivar(ins.duration, ins.flags, 0), ins.ease & 255)
    vm.rot_initial = list(vm.rotation)
    vm.rot_final = [
        vm.fvar(ins.x, ins.flags, 2),
        vm.fvar(ins.y, ins.flags, 3),
        vm.fvar(ins.z, ins.flags, 4),
    ]


def _interp_scale2(vm: AnmMachine, ins: InterpScale2) -> None:
    vm.scale_interp.restart(vm.ivar(ins.duration, ins.flags, 0), ins.ease & 255)
    vm.scale_initial = list(vm.scale)
    vm.scale_final = [vm.fvar(ins.x, ins.flags, 2), vm.fvar(ins.y, ins.flags, 3)]


def _set_scroll_vel_x(vm: AnmMachine, ins: SetScrollVelX) -> None:
    vm.uv_scroll_vel[0] = vm.fvar(ins.v, ins.flags, 0)


def _set_scroll_vel_y(vm: AnmMachine, ins: SetScrollVelY) -> None:
    vm.uv_scroll_vel[1] = vm.fvar(ins.v, ins.flags, 0)


VISUAL: dict[type[AnmInstr], Handler] = {
    SetActiveSprite: _set_active_sprite,
    SetTranslation: _set_translation,
    SetScale: _set_scale,
    SetAlpha: _set_alpha,
    SetColor: _set_color,
    FlipX: _flip_x,
    FlipY: _flip_y,
    SetRotation: _set_rotation,
    SetAngleVel: _set_angle_vel,
    SetScaleSpeed: _set_scale_speed,
    Fade: _fade,
    SetBlend: _set_blend,
    PosTimeLinear: _pos_time_linear,
    PosTimeDecel: _pos_time_decel,
    PosTimeAccel: _pos_time_accel,
    Anchor3: _anchor3,
    SetUseOffset: _set_use_offset,
    SetAutoRotate: _set_auto_rotate,
    SetScrollPosX: _set_scroll_pos_x,
    SetScrollPosY: _set_scroll_pos_y,
    SetVisibility: _set_visibility,
    InterpScale: _interp_scale,
    SetZwriteDisable: _set_zwrite_disable,
    SetCameraMode: _noop,
    InterpPos: _interp_pos,
    InterpColor: _interp_color,
    InterpAlpha: _interp_alpha,
    InterpRotate: _interp_rotate,
    InterpScale2: _interp_scale2,
    SetScrollVelX: _set_scroll_vel_x,
    SetScrollVelY: _set_scroll_vel_y,
}
