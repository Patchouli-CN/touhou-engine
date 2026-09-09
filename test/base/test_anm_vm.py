"""AnmMachine 合成脚本测试: 插值/跳转/变量/interrupt/随机确定性 + 建表寻址。"""

from __future__ import annotations

import math
from typing import get_args

import pytest

from touhou.engine.anm import AnmMachine, build_bank, build_script
from touhou.engine.anm.handlers import HANDLERS
from touhou.engine.rng import Rng
from touhou.schemas.anm import AnmEntry, AnmFile, AnmSprite
from touhou.schemas.anm_script import (
    Add2,
    AddFloat2,
    DecJump,
    Exit,
    ExitHide,
    Fade,
    FlipX,
    FlipY,
    Instruction,
    InterpAlpha,
    InterpRotate,
    InterpScale2,
    InterruptLabel,
    Jump,
    JumpIfEq,
    Mov,
    MovFloat,
    MulFloat,
    Nop,
    PosTimeLinear,
    Rand,
    RandFloat,
    SetActiveSprite,
    SetAlpha,
    SetAngleVel,
    SetBlend,
    SetColor,
    SetRotation,
    SetScale,
    SetScrollPosX,
    SetScrollVelX,
    SetTranslation,
    SetUseOffset,
    Sin,
    Stop,
    StopHide,
    Wait,
)


def run(instrs, frames: int = 1, *, sprite_base: int = 0, seed: int = 0) -> AnmMachine:
    """挂脚本跑 frames 帧(start 当帧即第一帧)。"""
    vm = AnmMachine(Rng(seed))
    vm.start(build_script(list(instrs), sprite_base))
    for _ in range(frames - 1):
        vm.execute()
    return vm


def test_handler_registry_covers_union() -> None:
    """指令 union 的每个类都有注册 handler, 没有漏网分派。"""
    assert set(get_args(Instruction)) == set(HANDLERS)


# ---- 基本指令 ----


def test_set_active_sprite_visible_and_base() -> None:
    vm = run(
        [SetActiveSprite(time=0, flags=0, sprite=7), Exit(time=0, flags=0)],
        sprite_base=100,
    )
    assert vm.active_sprite_idx == 107
    assert vm.visible


def test_scale_alpha_color_rotation_flip() -> None:
    vm = run(
        [
            SetScale(time=0, flags=0, x=2.0, y=0.5),
            SetAlpha(time=0, flags=0, alpha=128),
            SetColor(time=0, flags=0, rgb=0x0080FF40),
            SetRotation(time=0, flags=0, x=0.0, y=0.0, z=1.0),
            FlipX(time=0, flags=0),
            FlipY(time=0, flags=0),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.scale == [-2.0, -0.5]
    assert vm.color == [0x80, 0xFF, 0x40, 128]
    assert vm.rotation[2] == pytest.approx(1.0)


def test_blend_mode() -> None:
    vm = run([SetBlend(time=0, flags=0, mode=1), Exit(time=0, flags=0)])
    assert vm.blend_mode == 1


def test_exit_hides_and_stops() -> None:
    vm = run([SetActiveSprite(time=0, flags=0, sprite=0), ExitHide(time=0, flags=0)])
    assert vm.pc == -1 and not vm.visible and not vm.alive
    vm.execute()  # 结束后 execute 无副作用
    assert vm.pc == -1


def test_nop_is_noop() -> None:
    vm = run(
        [
            Nop(time=0, flags=0),
            SetAlpha(time=0, flags=0, alpha=7),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.color[3] == 7


# ---- 插值 ----


def test_fade_interpolation() -> None:
    # SET_ALPHA 200; FADE(0, 10) → 每帧插值, 第 10 帧到 0
    vm = run(
        [
            SetAlpha(time=0, flags=0, alpha=200),
            Fade(time=0, flags=0, alpha=0, duration=10),
            Stop(time=0, flags=0),
        ]
    )
    assert 0 < vm.color[3] < 200
    for _ in range(9):
        vm.execute()
    assert vm.color[3] == 0


def test_interp_scale_and_rotate() -> None:
    # INTERP_SCALE_2(dur=4, sx 1→3); INTERP_ROTATE(dur=4, z 0→pi)
    vm = run(
        [
            InterpScale2(time=0, flags=0, duration=4, ease=0, x=3.0, y=1.0),
            InterpRotate(time=0, flags=0, duration=4, ease=0, x=0.0, y=0.0, z=math.pi),
            Stop(time=0, flags=0),
        ]
    )
    for _ in range(3):  # 首帧已执行 1 次, 共 4 帧到 t=1
        vm.execute()
    assert vm.scale[0] == pytest.approx(3.0)
    assert vm.scale[1] == pytest.approx(1.0)
    assert abs(vm.rotation[2]) == pytest.approx(math.pi)


def test_interp_alpha_ease_modes() -> None:
    # ease=1(in quad): 第 1 帧 t=0.5²=0.25 → 25; ease=4(out quad): 0.75 → 75
    ins = lambda ease: [  # noqa: E731
        SetAlpha(time=0, flags=0, alpha=0),
        InterpAlpha(time=0, flags=0, duration=2, ease=ease, alpha=100),
        Stop(time=0, flags=0),
    ]
    assert run(ins(1)).color[3] == 25
    assert run(ins(4)).color[3] == 75
    vm = run(ins(1), frames=2)
    assert vm.color[3] == 100


def test_pos_time_linear() -> None:
    vm = run(
        [
            PosTimeLinear(time=0, flags=0, x=8.0, y=0.0, z=0.0, duration=4),
            Stop(time=0, flags=0),
        ]
    )
    for _ in range(3):
        vm.execute()
    assert vm.pos[0] == pytest.approx(8.0)


def test_use_offset_redirects_translation_and_interp() -> None:
    vm = run(
        [
            SetUseOffset(time=0, flags=0, value=1),
            SetTranslation(time=0, flags=0, x=1.0, y=2.0, z=3.0),
            PosTimeLinear(time=0, flags=0, x=9.0, y=8.0, z=7.0, duration=2),
            Stop(time=0, flags=0),
        ],
        frames=2,
    )
    assert vm.pos == [0.0, 0.0, 0.0]  # pos 不受影响
    assert vm.offset == [pytest.approx(9.0), pytest.approx(8.0), pytest.approx(7.0)]


def test_angle_vel_normalizes() -> None:
    vm = run([SetAngleVel(time=0, flags=0, x=0.0, y=0.0, z=2.0), Stop(time=0, flags=0)])
    for _ in range(3):  # 共 4 帧累计 8.0 > pi → 包回 [-pi,pi]
        vm.execute()
    assert -math.pi <= vm.rotation[2] <= math.pi
    assert vm.rotation[2] == pytest.approx(8.0 - 2 * math.pi)


def test_uv_scroll_wraps() -> None:
    vm = run(
        [
            SetScrollPosX(time=0, flags=0, delta=0.7),
            SetScrollPosX(time=0, flags=0, delta=0.7),
            SetScrollVelX(time=0, flags=0, v=0.3),
            Stop(time=0, flags=0),
        ]
    )
    assert vm.uv_scroll[0] == pytest.approx(0.7)  # 1.4 绕回 0.4, 帧尾再 +0.3
    vm.execute()
    assert vm.uv_scroll[0] == pytest.approx(0.0)  # 0.7+0.3=1.0 再绕回 0


# ---- 控制流 ----


def test_wait_holds_pc() -> None:
    vm = run(
        [
            SetAlpha(time=0, flags=0, alpha=10),
            Wait(time=0, flags=0, frames=3),
            SetAlpha(time=0, flags=0, alpha=99),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.color[3] == 10
    vm.execute()
    assert vm.color[3] == 10  # 等待中
    vm.execute()
    vm.execute()
    assert vm.color[3] == 99  # 3 帧后放行
    assert vm.pc == -1


def test_jump_unknown_dest_halts() -> None:
    vm = run([Jump(time=0, flags=0, dest=999, set_time=0), Exit(time=0, flags=0)])
    assert vm.pc == -1
    assert not vm.alive


def test_dec_jump_loop() -> None:
    # var10000=2; DEC_JUMP 跳自身(偏移 16) → 减 2 次后顺序退出
    vm = run(
        [
            Mov(time=0, flags=1, dst=10000, src=2),
            DecJump(time=0, flags=1, var=10000, dest=16, set_time=0),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.pc == -1
    assert vm.int_vars1[0] == 0


def test_cond_jump_int_eq() -> None:
    # JumpIfEq 4 参数 24B + SetAlpha 12B → Exit 在偏移 36
    vm = run(
        [
            JumpIfEq(time=0, flags=0, x=5, y=5, dest=36, set_time=0),
            SetAlpha(time=0, flags=0, alpha=77),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.pc == -1
    assert vm.color[3] == 255  # 被跳过, 保持初始
    vm2 = run(
        [
            JumpIfEq(time=0, flags=0, x=5, y=6, dest=36, set_time=0),
            SetAlpha(time=0, flags=0, alpha=77),
            Exit(time=0, flags=0),
        ]
    )
    assert vm2.color[3] == 77


def test_int_float_var_ops() -> None:
    vm = run(
        [
            Add2(time=0, flags=1, dst=10000, a=3, b=4),
            AddFloat2(time=0, flags=1, dst=10004.0, a=1.5, b=2.0),
            MulFloat(time=0, flags=1, dst=10004.0, src=2.0),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.int_vars1[0] == 7
    assert vm.float_vars[0] == pytest.approx(7.0)


def test_indirect_read_across_var_banks() -> None:
    # MovFloat fvar10004=5.5; Mov var10000=读 float 变量(截断) → 5
    vm = run(
        [
            MovFloat(time=0, flags=1, dst=10004.0, src=5.5),
            Mov(time=0, flags=0b11, dst=10000, src=10004),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.int_vars1[0] == 5


def test_interrupt_jumps_to_label() -> None:
    vm = run(
        [
            Stop(time=0, flags=0),
            InterruptLabel(time=0, flags=0, label=1),
            SetAlpha(time=0, flags=0, alpha=44),
            Exit(time=0, flags=0),
        ]
    )
    assert vm.is_stopped and vm.color[3] == 255
    vm.pending_interrupt = 1
    vm.execute()
    assert vm.color[3] == 44
    assert vm.pc == -1


def test_interrupt_fallback_label() -> None:
    # 没有匹配标号时跳 label=-1 的兜底标号
    vm = run(
        [
            Stop(time=0, flags=0),
            InterruptLabel(time=0, flags=0, label=-1),
            SetAlpha(time=0, flags=0, alpha=7),
            ExitHide(time=0, flags=0),
        ]
    )
    vm.pending_interrupt = 5
    vm.execute()
    assert vm.color[3] == 7
    assert vm.pc == -1 and not vm.visible


def test_interrupt_no_label_exits_next_frame() -> None:
    # 找不到标号: 停在脚本尾, 下一帧由收尾的 ExitHide 结束脚本
    vm = run([Stop(time=0, flags=0), ExitHide(time=0, flags=0)])
    assert vm.is_stopped
    vm.pending_interrupt = 9
    vm.execute()
    assert not vm.is_stopped and vm.alive  # 本帧只走帧尾
    vm.execute()
    assert vm.pc == -1 and not vm.visible


def test_stop_hide_hides_while_waiting() -> None:
    vm = run([SetActiveSprite(time=0, flags=0, sprite=0), StopHide(time=0, flags=0)])
    assert vm.is_stopped and not vm.visible


# ---- 随机 ----


def test_rand_deterministic_same_seed() -> None:
    script = [Rand(time=0, flags=1, dst=10000, bound=100), Exit(time=0, flags=0)]
    a, b = run(script, seed=42), run(script, seed=42)
    assert a.int_vars1[0] == b.int_vars1[0]
    assert 0 <= a.int_vars1[0] < 100


def test_rand_float_and_trig() -> None:
    vm = run(
        [
            RandFloat(time=0, flags=1, dst=10004.0, bound=2.0),
            Sin(time=0, flags=1, dst=10008.0, src=math.pi / 2),
            Exit(time=0, flags=0),
        ],
        seed=7,
    )
    assert 0.0 <= vm.float_vars[0] < 2.0
    # dst 10008 不在 float 变量范围, 写入丢弃
    assert vm.float_vars[1] == 0.0
    vm2 = run(
        [Sin(time=0, flags=1, dst=10004.0, src=math.pi / 2), Exit(time=0, flags=0)]
    )
    assert vm2.float_vars[0] == pytest.approx(1.0)


# ---- 建表寻址 ----


def _entry(sprites: dict[int, AnmSprite], name: str = "t") -> AnmEntry:
    return AnmEntry(name, 1, 0, 1, 1, 1, 1, None, sprites)


def _spr(sid: int) -> AnmSprite:
    return AnmSprite(sid, 0, 0, 1, 1)


def test_build_script_offsets() -> None:
    # SetActiveSprite 1 参数 12B → Exit 在偏移 12
    script = build_script(
        [SetActiveSprite(time=0, flags=0, sprite=1), Exit(time=0, flags=0)]
    )
    assert script.offsets == {0: 0, 12: 1}


def test_build_bank_chain_offsets() -> None:
    """链式偏移: 键 = 存储 id + 按 max(存储 id)+1 累计的基址。"""
    anm = AnmFile(
        [_entry({2: _spr(2)}), _entry({0: _spr(0)})],
        [{1: [ExitHide(time=0, flags=0)]}, {0: [Exit(time=0, flags=0)]}],
    )
    bank = build_bank(anm, flat_layout=False)
    assert sorted(bank.sprites) == [2, 3]  # 基址 max(2,1)+1 = 3
    assert sorted(bank.scripts) == [1, 3]
    assert bank.scripts[1].sprite_base == 0
    assert bank.scripts[3].sprite_base == 3
    assert bank.sprites[3].entry == 1


def test_build_bank_flat_layout_keys_are_load_order() -> None:
    """扁平装载序: 键 = 装载序号, 文件存的 id(此处已是全局扁平号)不参与寻址。"""
    anm = AnmFile(
        [_entry({5: _spr(5), 6: _spr(6)}), _entry({7: _spr(7)})],
        [
            {0: [ExitHide(time=0, flags=0)], 1: [Exit(time=0, flags=0)]},
            {0: [Exit(time=0, flags=0)]},
        ],
    )
    bank = build_bank(anm, flat_layout=True)
    assert sorted(bank.sprites) == [0, 1, 2]
    assert bank.sprites[2].sprite.id == 7  # 键是装载序 2, 不是存储 id 7
    assert bank.sprites[2].entry == 1
    assert sorted(bank.scripts) == [0, 1, 2]
    assert all(s.sprite_base == 0 for s in bank.scripts.values())
