"""th08(v800)时间轴: 指令类 + 布局解码 + TL_HANDLERS 执行绑定。

v800 布局: i32 time + i16 opcode + u8 size + u8 difficultyMask + args[7]×4B
(th08 EnemyManager.hpp:419-430); opcode 0-16 语义 EnemyTimeline.cpp:134-283
(均转引 scratch_dbg/investigation/engine-internals.md ECL 节与旧实现)。
执行语义移植 old/touhou/games/th08/ecl_timeline.py。
"""

from __future__ import annotations

import struct

from ...engine.ecl import TimelineRunner
from ...engine.ecl.state import PLAYFIELD_W, EnemySpawn
from ...engine.ecl.timeline import TlHandler
from ...schemas.ecl import TlInstr
from ...schemas.ecl.decode import _f32, _i32
from ...schemas.exceptions import ParseError

_TL_HEADER = struct.Struct("<ihBB")  # time, opcode, size, difficultyMask


class TlSpawnAt(TlInstr, frozen=True, tag="tl_spawn_at"):
    """定点生敌(mirror = 镜像 X, forced = 无 boss 门控)。"""

    # v800 时间轴指令带难度位掩码(EnemyTimeline.cpp:131-132)
    difficulty_mask: int
    sub_id: int
    mirror: bool
    forced: bool
    x: float
    y: float
    life: int
    item_drop: int
    score: int


class TlSpawnRangeX(TlInstr, frozen=True, tag="tl_spawn_range_x"):
    """x 区间随机生敌。"""

    difficulty_mask: int
    sub_id: int
    mirror: bool
    x_lo: float
    x_hi: float
    y: float
    life: int
    item_drop: int
    score: int


class TlSpawnRandomX(TlInstr, frozen=True, tag="tl_spawn_random_x"):
    """全屏随机 x 生敌。"""

    difficulty_mask: int
    sub_id: int
    y: float
    life: int
    item_drop: int
    score: int


class TlSpawnDrops(TlInstr, frozen=True, tag="tl_spawn_drops"):
    """带掉落数生敌: 点道具数/火力或点道具数落到新敌。"""

    # EnemyTimeline.cpp:165-185
    difficulty_mask: int
    sub_id: int
    mirror: bool
    x: float
    y: float
    life: int
    point_drops: int
    power_or_point_drops: int
    score: int


class TlMsgReadV800(TlInstr, frozen=True, tag="tl_msg_read_v800"):
    """读 msg。"""

    difficulty_mask: int
    msg_id: int


class TlMsgWaitV800(TlInstr, frozen=True, tag="tl_msg_wait_v800"):
    """等 msg 显示完。"""

    difficulty_mask: int


class TlSetBossPendingSub(TlInstr, frozen=True, tag="tl_set_boss_pending_sub"):
    """设 boss 的 pendingEclSubroutineIndex。"""

    difficulty_mask: int
    boss_idx: int
    sub_id: int


class TlSetPowerV800(TlInstr, frozen=True, tag="tl_set_power_v800"):
    """设自机火力。"""

    difficulty_mask: int
    value: int


class TlWaitBossDeadV800(TlInstr, frozen=True, tag="tl_wait_boss_dead_v800"):
    """等 boss 退场。"""

    difficulty_mask: int
    boss_idx: int


class TlEventConsume(TlInstr, frozen=True, tag="tl_event_consume"):
    """事件槽同步(消费): 无匹配则停轴等。"""

    # EnemyTimeline.cpp:253-271
    difficulty_mask: int
    value: int


class TlEventEmit(TlInstr, frozen=True, tag="tl_event_emit"):
    """事件槽同步(投放): 填进所有空槽。"""

    # EnemyTimeline.cpp:273-282
    difficulty_mask: int
    value: int


class TlShowRetryMenu(TlInstr, frozen=True, tag="tl_show_retry_menu"):
    """出 Retry 菜单。"""

    difficulty_mask: int


class TlEndV800(TlInstr, frozen=True, tag="tl_end_v800"):
    """时间轴终止记录(time < 0; size=0 的截短记录 args 为空)。"""

    difficulty_mask: int
    args: tuple[int, ...] = ()


#: th08 的时间轴指令 union
TimelineInstr = (
    TlSpawnAt
    | TlSpawnRangeX
    | TlSpawnRandomX
    | TlSpawnDrops
    | TlMsgReadV800
    | TlMsgWaitV800
    | TlSetBossPendingSub
    | TlSetPowerV800
    | TlWaitBossDeadV800
    | TlEventConsume
    | TlEventEmit
    | TlShowRetryMenu
    | TlEndV800
)


def decode_timeline(data: bytes, off: int) -> tuple[TlInstr, ...]:
    """v800 时间轴: 8 字节头(i32 time + i16 opcode + u8 size + u8 难度掩码) + 参数字。"""
    out: list[TlInstr] = []
    while off < len(data):
        if off + _TL_HEADER.size > len(data):
            tail = (
                struct.unpack_from("<h", data, off)[0] if off + 2 <= len(data) else -1
            )
            if tail < 0:
                out.append(TlEndV800(time=tail, difficulty_mask=0))
                break
            raise ParseError(f"timeline 越界 (off={off:#x})")
        time, opcode, size, dm = _TL_HEADER.unpack_from(data, off)
        if size == 0 and time < 0:
            # 截短终止记录: 只有 8 字节头, size 字段为 0(真实数据 ecldata8 tl1)
            out.append(TlEndV800(time=time, difficulty_mask=dm))
            break
        if size < 8 or (size - 8) % 4 != 0 or off + size > len(data):
            raise ParseError(f"timeline 非法 size={size} (off={off:#x})")
        nargs = (size - 8) // 4
        words = struct.unpack_from(f"<{nargs}I", data, off + 8)
        if time < 0:
            out.append(TlEndV800(time=time, difficulty_mask=dm, args=words))
            break

        def need(n: int) -> None:
            if nargs != n:
                raise ParseError(
                    f"timeline op{opcode} 参数数不符: {nargs} != {n} (off={off:#x})"
                )

        if opcode in (0, 1, 15):  # 定点生敌(1=镜像, 15=无门控)
            need(6)
            out.append(
                TlSpawnAt(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 1,
                    forced=opcode == 15,
                    x=_f32(words[1]),
                    y=_f32(words[2]),
                    life=_i32(words[3]),
                    item_drop=_i32(words[4]),
                    score=_i32(words[5]),
                )
            )
        elif opcode in (2, 4):  # x 区间随机(4=镜像)
            need(7)
            out.append(
                TlSpawnRangeX(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 4,
                    x_lo=_f32(words[1]),
                    x_hi=_f32(words[2]),
                    y=_f32(words[3]),
                    life=_i32(words[4]),
                    item_drop=_i32(words[5]),
                    score=_i32(words[6]),
                )
            )
        elif opcode in (3, 5):  # 全屏随机 x
            need(5)
            out.append(
                TlSpawnRandomX(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    y=_f32(words[1]),
                    life=_i32(words[2]),
                    item_drop=_i32(words[3]),
                    score=_i32(words[4]),
                )
            )
        elif opcode in (11, 12):  # 带掉落数(12=镜像)
            need(7)
            out.append(
                TlSpawnDrops(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 12,
                    x=_f32(words[1]),
                    y=_f32(words[2]),
                    life=_i32(words[3]),
                    point_drops=_i32(words[4]),
                    power_or_point_drops=_i32(words[5]),
                    score=_i32(words[6]),
                )
            )
        elif opcode == 6:
            need(1)
            out.append(TlMsgReadV800(time, difficulty_mask=dm, msg_id=_i32(words[0])))
        elif opcode == 7:
            need(0)
            out.append(TlMsgWaitV800(time, difficulty_mask=dm))
        elif opcode == 8:
            need(2)
            out.append(
                TlSetBossPendingSub(
                    time,
                    difficulty_mask=dm,
                    boss_idx=_i32(words[0]),
                    sub_id=_i32(words[1]),
                )
            )
        elif opcode == 9:
            need(1)
            out.append(TlSetPowerV800(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 10:
            need(1)
            out.append(
                TlWaitBossDeadV800(time, difficulty_mask=dm, boss_idx=_i32(words[0]))
            )
        elif opcode == 13:
            need(1)
            out.append(TlEventConsume(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 14:
            need(1)
            out.append(TlEventEmit(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 16:
            need(0)
            out.append(TlShowRetryMenu(time, difficulty_mask=dm))
        else:
            raise ParseError(f"未知 v800 时间轴 opcode: {opcode} (off={off:#x})")
        off += size
    return tuple(out)


def _tl_spawn_at(r: TimelineRunner, ins: TlSpawnAt) -> None:
    if ins.forced or r._spawn_gated():
        r.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=ins.x,
                y=ins.y,
                life=ins.life,
                item_drop=ins.item_drop,
                score=ins.score,
                mirror=int(ins.mirror),
            ),
            None,
        )


def _tl_spawn_range_x(r: TimelineRunner, ins: TlSpawnRangeX) -> None:
    # x 区间随机(EnemyTimeline.cpp:187-202)
    if r._spawn_gated():
        r.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=r.rng.unit() * (ins.x_hi - ins.x_lo) + ins.x_lo,
                y=ins.y,
                life=ins.life,
                item_drop=ins.item_drop,
                score=ins.score,
                mirror=int(ins.mirror),
            ),
            None,
        )


def _tl_spawn_random_x(r: TimelineRunner, ins: TlSpawnRandomX) -> None:
    # 全屏随机 x(EnemyTimeline.cpp:204-219)
    if r._spawn_gated():
        r.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=r.rng.unit() * PLAYFIELD_W,
                y=ins.y,
                life=ins.life,
                item_drop=ins.item_drop,
                score=ins.score,
            ),
            None,
        )


def _tl_spawn_drops(r: TimelineRunner, ins: TlSpawnDrops) -> None:
    # 带掉落数(EnemyTimeline.cpp:165-185): item_drop=-1, 掉落数落到新敌
    if r._spawn_gated():
        r.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=ins.x,
                y=ins.y,
                life=ins.life,
                item_drop=-1,
                score=ins.score,
                mirror=int(ins.mirror),
                point_drops=ins.point_drops,
                power_or_point_drops=ins.power_or_point_drops,
            ),
            None,
        )


def _tl_msg_read(r: TimelineRunner, ins: TlMsgReadV800) -> None:
    r.host.msg_read(ins.msg_id)


def _tl_msg_wait(r: TimelineRunner, ins: TlMsgWaitV800) -> bool:
    return r.host.msg_wait()


def _tl_set_boss_pending_sub(r: TimelineRunner, ins: TlSetBossPendingSub) -> None:
    r.host.set_boss_pending_sub(ins.boss_idx, ins.sub_id)


def _tl_set_power(r: TimelineRunner, ins: TlSetPowerV800) -> None:
    r.host.set_power(ins.value)


def _tl_wait_boss_dead(r: TimelineRunner, ins: TlWaitBossDeadV800) -> bool:
    return r.host.boss_active(ins.boss_idx)


def _tl_event_consume(r: TimelineRunner, ins: TlEventConsume) -> bool:
    """事件槽消费: 无匹配则停轴等。"""
    return not r.host.consume_event(ins.value)


def _tl_event_emit(r: TimelineRunner, ins: TlEventEmit) -> None:
    r.host.emit_event(ins.value)


def _tl_show_retry_menu(r: TimelineRunner, ins: TlShowRetryMenu) -> None:
    r.host.show_retry_menu()


def _tl_end(r: TimelineRunner, ins: TlInstr) -> None:
    """终止记录(time<0 已被 done 拦截, 到不了这里; 注册表兜底用)。"""


#: th08 时间轴指令类 → handler
TL_HANDLERS: dict[type[TlInstr], TlHandler] = {
    TlSpawnAt: _tl_spawn_at,
    TlSpawnRangeX: _tl_spawn_range_x,
    TlSpawnRandomX: _tl_spawn_random_x,
    TlSpawnDrops: _tl_spawn_drops,
    TlMsgReadV800: _tl_msg_read,
    TlMsgWaitV800: _tl_msg_wait,
    TlSetBossPendingSub: _tl_set_boss_pending_sub,
    TlSetPowerV800: _tl_set_power,
    TlWaitBossDeadV800: _tl_wait_boss_dead,
    TlEventConsume: _tl_event_consume,
    TlEventEmit: _tl_event_emit,
    TlShowRetryMenu: _tl_show_retry_menu,
    TlEndV800: _tl_end,
}
