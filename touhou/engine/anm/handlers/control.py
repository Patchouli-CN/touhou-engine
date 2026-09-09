"""控制流指令 handler(退出/跳转/等待/interrupt)。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....schemas.anm_script import (
    AnmInstr,
    DecJump,
    Exit,
    ExitHide,
    ExitHide2,
    InterruptLabel,
    Jump,
    Nop,
    Stop,
    StopHide,
    Wait,
)
from .base import Handler, Step

if TYPE_CHECKING:
    from ..vm import AnmMachine


def _noop(vm: AnmMachine, ins: AnmInstr) -> None:
    """空转(Nop/InterruptLabel; SetCameraMode 同旧 VM 忽略相机模式)。"""


def _exit_hide(vm: AnmMachine, ins: ExitHide) -> Step:
    vm.visible = False
    vm.pc = -1
    return Step.HALT


def _exit(vm: AnmMachine, ins: Exit) -> Step:
    vm.pc = -1
    return Step.HALT


def _jump(vm: AnmMachine, ins: Jump) -> Step:
    vm.jump_to(ins.dest, ins.set_time)
    return Step.JUMPED


def _dec_jump(vm: AnmMachine, ins: DecJump) -> Step | None:
    # 自减后仍为正则跳 — AnmManager.cpp:1696-1705
    vm.istore(ins.var, ins.flags, 0, vm.iptr(ins.var, ins.flags, 0) - 1)
    if vm.ivar(ins.var, ins.flags, 0) > 0:
        vm.jump_to(ins.dest, ins.set_time)
        return Step.JUMPED
    return None


def _wait(vm: AnmMachine, ins: Wait) -> Step | None:
    # 倒计时未完则 time 回退并停本帧 — AnmManager.cpp:1787-1802
    if vm.wait_timer == 0:
        vm.wait_timer = vm.ivar(ins.frames, ins.flags, 0)
    else:
        vm.wait_timer -= 1
    if vm.wait_timer <= 0:
        vm.wait_timer = 0
        return None
    vm.time -= 1
    return Step.YIELD


def _stop(vm: AnmMachine, ins: Stop | StopHide, hide: bool) -> Step:
    # 无 pending 则停住等 interrupt; 有 pending 直接走标号跳转 — AnmManager.cpp:1803-1811
    if hide:
        vm.visible = False
    if vm.pending_interrupt:
        return vm.handle_interrupt()
    vm.is_stopped = True
    vm.time -= 1
    return Step.YIELD


def _stop_show(vm: AnmMachine, ins: Stop) -> Step:
    return _stop(vm, ins, hide=False)


def _stop_hide(vm: AnmMachine, ins: StopHide) -> Step:
    return _stop(vm, ins, hide=True)


CONTROL: dict[type[AnmInstr], Handler] = {
    Nop: _noop,
    ExitHide: _exit_hide,
    ExitHide2: _exit_hide,
    Exit: _exit,
    Jump: _jump,
    DecJump: _dec_jump,
    Stop: _stop_show,
    InterruptLabel: _noop,
    StopHide: _stop_hide,
    Wait: _wait,
}
