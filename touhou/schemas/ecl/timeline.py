"""ECL 时间轴指令(生敌/msg/boss 等待), v0 与 v800 两种布局。"""

from __future__ import annotations

from .base import TlInstr

# v0 布局 EclTimelineInstr: i16 time + i16 arg0 + i16 opcode + i16 size +
# args[6]×4B (Reference/th07/src/th07/EclManager.hpp:307-324);
# opcode 语义 EnemyManager::RunEclTimeline(0-7 生敌, 8 msg, 9 msgWait,
# 10 boss interrupt, 11 火力, 12 等 boss 退场)
# v800 布局: i32 time + i16 opcode + u8 size + u8 difficultyMask + args[7]×4B
# (th08 EnemyManager.hpp:419-430); opcode 0-16 语义 EnemyTimeline.cpp:134-283
# (均转引 scratch_dbg/investigation/engine-internals.md ECL 节与旧实现)


class TlSpawn(TlInstr, frozen=True, tag="tl_spawn"):
    """时间轴生敌(v0): mode 0-7(bit0 = 默认数值, bit1 = 镜像 X)。"""

    sub_id: int
    mode: int
    x: float
    y: float
    z: float
    life: int
    item_drop: int
    score: int


class TlMsgRead(TlInstr, frozen=True, tag="tl_msg_read"):
    """读 msg(v0)。"""

    msg_id: int


class TlMsgWait(TlInstr, frozen=True, tag="tl_msg_wait"):
    """等 msg 显示完(v0, 时间轴停住)。"""


class TlSetBossInterrupt(TlInstr, frozen=True, tag="tl_set_boss_interrupt"):
    """设 boss 的 run_interrupt(v0)。"""

    boss_idx: int
    interrupt: int


class TlSetPower(TlInstr, frozen=True, tag="tl_set_power"):
    """设自机火力(v0)。"""

    value: int


class TlWaitBossDead(TlInstr, frozen=True, tag="tl_wait_boss_dead"):
    """等 boss 退场(v0, 时间轴停住)。"""

    boss_idx: int


class TlEnd(TlInstr, frozen=True, tag="tl_end"):
    """时间轴终止记录(v0, time < 0; args 收残余字)。"""

    args: tuple[int, ...] = ()


class TlSpawnAt(TlInstr, frozen=True, tag="tl_spawn_at"):
    """定点生敌(v800; mirror = 镜像 X, forced = 无 boss 门控)。"""

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
    """x 区间随机生敌(v800)。"""

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
    """全屏随机 x 生敌(v800)。"""

    difficulty_mask: int
    sub_id: int
    y: float
    life: int
    item_drop: int
    score: int


class TlSpawnDrops(TlInstr, frozen=True, tag="tl_spawn_drops"):
    """带掉落数生敌(v800): 点道具数/火力或点道具数落到新敌。"""

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
    """读 msg(v800)。"""

    difficulty_mask: int
    msg_id: int


class TlMsgWaitV800(TlInstr, frozen=True, tag="tl_msg_wait_v800"):
    """等 msg 显示完(v800)。"""

    difficulty_mask: int


class TlSetBossPendingSub(TlInstr, frozen=True, tag="tl_set_boss_pending_sub"):
    """设 boss 的 pendingEclSubroutineIndex(v800)。"""

    difficulty_mask: int
    boss_idx: int
    sub_id: int


class TlSetPowerV800(TlInstr, frozen=True, tag="tl_set_power_v800"):
    """设自机火力(v800)。"""

    difficulty_mask: int
    value: int


class TlWaitBossDeadV800(TlInstr, frozen=True, tag="tl_wait_boss_dead_v800"):
    """等 boss 退场(v800)。"""

    difficulty_mask: int
    boss_idx: int


class TlEventConsume(TlInstr, frozen=True, tag="tl_event_consume"):
    """事件槽同步(消费): 无匹配则停轴等(v800)。"""

    # EnemyTimeline.cpp:253-271
    difficulty_mask: int
    value: int


class TlEventEmit(TlInstr, frozen=True, tag="tl_event_emit"):
    """事件槽同步(投放): 填进所有空槽(v800)。"""

    # EnemyTimeline.cpp:273-282
    difficulty_mask: int
    value: int


class TlShowRetryMenu(TlInstr, frozen=True, tag="tl_show_retry_menu"):
    """出 Retry 菜单(v800)。"""

    difficulty_mask: int


class TlEndV800(TlInstr, frozen=True, tag="tl_end_v800"):
    """时间轴终止记录(v800, time < 0; size=0 的截短记录 args 为空)。"""

    difficulty_mask: int
    args: tuple[int, ...] = ()


TimelineInstr = (
    TlSpawn
    | TlMsgRead
    | TlMsgWait
    | TlSetBossInterrupt
    | TlSetPower
    | TlWaitBossDead
    | TlEnd
    | TlSpawnAt
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
