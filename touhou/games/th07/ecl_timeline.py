"""th07(v0)时间轴: 指令类 + 布局解码 + TL_HANDLERS 执行绑定。

v0 布局 EclTimelineInstr: i16 time + i16 arg0 + i16 opcode + i16 size +
args[6]×4B (Reference/th07/src/th07/EclManager.hpp:307-324); opcode 语义
EnemyManager::RunEclTimeline(0-7 生敌, 8 msg, 9 msgWait, 10 boss interrupt,
11 火力, 12 等 boss 退场)。执行语义移植 old/touhou/engine/ecl.py
EclTimelineRunner。
"""

from __future__ import annotations

import struct

from ...engine.ecl import TimelineRunner
from ...engine.ecl.state import PLAYFIELD_H, PLAYFIELD_W, EnemySpawn
from ...engine.ecl.timeline import TlHandler
from ...schemas.ecl import TlInstr
from ...schemas.ecl.decode import _f32, _i32
from ...schemas.exceptions import ParseError

_TL_HEADER = struct.Struct("<hhhh")  # time, arg0, opcode, size


class TlSpawn(TlInstr, frozen=True, tag="tl_spawn"):
    """时间轴生敌: mode 0-7(bit0 = 默认数值, bit1 = 镜像 X)。"""

    sub_id: int
    mode: int
    x: float
    y: float
    z: float
    life: int
    item_drop: int
    score: int


class TlMsgRead(TlInstr, frozen=True, tag="tl_msg_read"):
    """读 msg。"""

    msg_id: int


class TlMsgWait(TlInstr, frozen=True, tag="tl_msg_wait"):
    """等 msg 显示完(时间轴停住)。"""


class TlSetBossInterrupt(TlInstr, frozen=True, tag="tl_set_boss_interrupt"):
    """设 boss 的 run_interrupt。"""

    boss_idx: int
    interrupt: int


class TlSetPower(TlInstr, frozen=True, tag="tl_set_power"):
    """设自机火力。"""

    value: int


class TlWaitBossDead(TlInstr, frozen=True, tag="tl_wait_boss_dead"):
    """等 boss 退场(时间轴停住)。"""

    boss_idx: int


class TlEnd(TlInstr, frozen=True, tag="tl_end"):
    """时间轴终止记录(time < 0; args 收残余字)。"""

    args: tuple[int, ...] = ()


#: th07 的时间轴指令 union
TimelineInstr = (
    TlSpawn
    | TlMsgRead
    | TlMsgWait
    | TlSetBossInterrupt
    | TlSetPower
    | TlWaitBossDead
    | TlEnd
)


def decode_timeline(data: bytes, off: int) -> tuple[TlInstr, ...]:
    """v0 时间轴: 8 字节头(i16×4) + 6 个 u32 参数字, time<0 结束。"""
    out: list[TlInstr] = []
    while off < len(data):
        if off + _TL_HEADER.size > len(data):
            # 尾部可能有截短终止记录(如 ff ff 04 00, time=-1)
            tail = (
                struct.unpack_from("<h", data, off)[0] if off + 2 <= len(data) else -1
            )
            if tail < 0:
                out.append(TlEnd(time=tail))
                break
            raise ParseError(f"timeline 越界 (off={off:#x})")
        time, arg0, opcode, size = _TL_HEADER.unpack_from(data, off)
        if size < 8 or (size - 8) % 4 != 0 or off + size > len(data):
            raise ParseError(f"timeline 非法 size={size} (off={off:#x})")
        nargs = (size - 8) // 4
        words = struct.unpack_from(f"<{nargs}I", data, off + 8)
        if time < 0:
            out.append(TlEnd(time=time, args=words))
            break
        if 0 <= opcode <= 7:
            if nargs != 6:
                raise ParseError(f"tl_spawn 参数数不符: {nargs} != 6 (off={off:#x})")
            out.append(
                TlSpawn(
                    time,
                    sub_id=arg0,
                    mode=opcode,
                    x=_f32(words[0]),
                    y=_f32(words[1]),
                    z=_f32(words[2]),
                    life=_i32(words[3]),
                    item_drop=_i32(words[4]),
                    score=_i32(words[5]),
                )
            )
        elif opcode == 8:
            out.append(TlMsgRead(time, msg_id=arg0))
        elif opcode == 9:
            out.append(TlMsgWait(time))
        elif opcode == 10:
            if nargs != 2:
                raise ParseError(
                    f"tl_set_boss_interrupt 参数数不符: {nargs} != 2 (off={off:#x})"
                )
            out.append(
                TlSetBossInterrupt(
                    time, boss_idx=_i32(words[0]), interrupt=_i32(words[1])
                )
            )
        elif opcode == 11:
            out.append(TlSetPower(time, value=arg0))
        elif opcode == 12:
            out.append(TlWaitBossDead(time, boss_idx=arg0))
        else:
            raise ParseError(f"未知 v0 时间轴 opcode: {opcode} (off={off:#x})")
        off += size
    return tuple(out)


def _tl_spawn(r: TimelineRunner, ins: TlSpawn) -> None:
    """生敌: mode bit0 = 默认数值, bit1(>=2) = 镜像 X。"""
    if not r.host.boss_present():
        x, y, z = ins.x, ins.y, ins.z
        if x <= -990.0:
            x = r.rng.unit() * PLAYFIELD_W
        if y <= -990.0:
            y = r.rng.unit() * PLAYFIELD_H
        if z <= -990.0:
            z = r.rng.unit() * 800.0
        default = bool(ins.mode & 1)
        r.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=x,
                y=y,
                z=z,
                life=-1 if default else ins.life,
                item_drop=-1 if default else ins.item_drop,
                score=-1 if default else ins.score,
                mirror=1 if ins.mode >= 2 else 0,
            ),
            None,
        )


def _tl_msg_read(r: TimelineRunner, ins: TlMsgRead) -> None:
    r.host.msg_read(ins.msg_id)


def _tl_msg_wait(r: TimelineRunner, ins: TlMsgWait) -> bool:
    return r.host.msg_wait()


def _tl_set_boss_interrupt(r: TimelineRunner, ins: TlSetBossInterrupt) -> None:
    r.host.set_boss_interrupt(ins.boss_idx & 7, ins.interrupt)


def _tl_set_power(r: TimelineRunner, ins: TlSetPower) -> None:
    r.host.set_power(ins.value)


def _tl_wait_boss_dead(r: TimelineRunner, ins: TlWaitBossDead) -> bool:
    return r.host.boss_active(ins.boss_idx & 7)


def _tl_end(r: TimelineRunner, ins: TlInstr) -> None:
    """终止记录(time<0 已被 done 拦截, 到不了这里; 注册表兜底用)。"""


#: th07 时间轴指令类 → handler
TL_HANDLERS: dict[type[TlInstr], TlHandler] = {
    TlSpawn: _tl_spawn,
    TlMsgRead: _tl_msg_read,
    TlMsgWait: _tl_msg_wait,
    TlSetBossInterrupt: _tl_set_boss_interrupt,
    TlSetPower: _tl_set_power,
    TlWaitBossDead: _tl_wait_boss_dead,
    TlEnd: _tl_end,
}
