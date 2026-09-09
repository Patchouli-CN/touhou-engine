"""ECL 时间轴执行器: 每帧 step 一次, 生敌/msg/boss 等待全走宿主回调。

handler 按 {时间轴指令类: handler} 查表分派(与指令 VM 同形态); handler
返回 True = 停轴等(msg 未完/boss 未退场/事件无匹配)。语义移植
old/touhou/engine/ecl.py EclTimelineRunner(v0) 与
old/touhou/games/th08/ecl_timeline.py(v800), 出处
EnemyManager::RunEclTimeline / EnemyTimeline.cpp:134-283。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...schemas.ecl import (
    TimelineInstr,
    TlEnd,
    TlEndV800,
    TlEventConsume,
    TlEventEmit,
    TlInstr,
    TlMsgRead,
    TlMsgReadV800,
    TlMsgWait,
    TlMsgWaitV800,
    TlSetBossInterrupt,
    TlSetBossPendingSub,
    TlSetPower,
    TlSetPowerV800,
    TlShowRetryMenu,
    TlSpawn,
    TlSpawnAt,
    TlSpawnDrops,
    TlSpawnRandomX,
    TlSpawnRangeX,
    TlWaitBossDead,
    TlWaitBossDeadV800,
)
from ..rng import Rng
from .host import EclHost
from .state import PLAYFIELD_H, PLAYFIELD_W, EnemySpawn

#: 时间轴指令类 → handler(返回 True = 停轴等一帧); 指令参数按 Any 收(同指令 VM)
TlHandler = Callable[["TimelineRunner", Any], "bool | None"]


class TimelineRunner:
    """一条时间轴的执行器; 生敌门控/坐标随机在本层, 敌人本体归宿主。"""

    def __init__(
        self, timeline: tuple[TimelineInstr, ...], host: EclHost, rng: Rng
    ) -> None:
        self.timeline = timeline
        self.host = host
        self.rng = rng
        self.time = 0
        self.idx = 0  # 当前指令下标(模拟 timelineInstr 指针)

    @property
    def done(self) -> bool:
        """时间轴跑完(越界或遇到 time<0 的终止记录)。"""
        return self.idx >= len(self.timeline) or self.timeline[self.idx].time < 0

    def _spawn_gated(self) -> bool:
        """生敌门控: boss 在场或全局抑制时跳过。"""
        if self.host.timeline_spawns_suppressed():
            return False
        return not self.host.boss_present()

    def step(self) -> None:
        """推进一帧: 执行所有到点指令, 停轴指令冻结 time。"""
        while not self.done:
            ins = self.timeline[self.idx]
            if self.time == ins.time:
                # 难度掩码过滤(v800 时间轴指令带掩码, EnemyTimeline.cpp:131-132)
                dm = getattr(ins, "difficulty_mask", None)
                if dm is not None and (dm & (1 << self.host.difficulty)) == 0:
                    self.idx += 1
                    continue
                if TL_HANDLERS[type(ins)](self, ins):
                    self.time -= 1  # 底部 time++ 抵消, 时间轴停住
                    break
            elif self.time < ins.time:
                break
            self.idx += 1
        self.time += 1


# ---- handler(v0) ----


def _tl_spawn(r: TimelineRunner, ins: TlSpawn) -> None:
    """v0 生敌: mode bit0 = 默认数值, bit1(>=2) = 镜像 X。"""
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


# ---- handler(v800) ----


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


def _tl_msg_read_v800(r: TimelineRunner, ins: TlMsgReadV800) -> None:
    r.host.msg_read(ins.msg_id)


def _tl_msg_wait_v800(r: TimelineRunner, ins: TlMsgWaitV800) -> bool:
    return r.host.msg_wait()


def _tl_set_boss_pending_sub(r: TimelineRunner, ins: TlSetBossPendingSub) -> None:
    r.host.set_boss_pending_sub(ins.boss_idx, ins.sub_id)


def _tl_set_power_v800(r: TimelineRunner, ins: TlSetPowerV800) -> None:
    r.host.set_power(ins.value)


def _tl_wait_boss_dead_v800(r: TimelineRunner, ins: TlWaitBossDeadV800) -> bool:
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


#: 时间轴指令类 → handler
TL_HANDLERS: dict[type[TlInstr], TlHandler] = {
    TlSpawn: _tl_spawn,
    TlMsgRead: _tl_msg_read,
    TlMsgWait: _tl_msg_wait,
    TlSetBossInterrupt: _tl_set_boss_interrupt,
    TlSetPower: _tl_set_power,
    TlWaitBossDead: _tl_wait_boss_dead,
    TlEnd: _tl_end,
    TlSpawnAt: _tl_spawn_at,
    TlSpawnRangeX: _tl_spawn_range_x,
    TlSpawnRandomX: _tl_spawn_random_x,
    TlSpawnDrops: _tl_spawn_drops,
    TlMsgReadV800: _tl_msg_read_v800,
    TlMsgWaitV800: _tl_msg_wait_v800,
    TlSetBossPendingSub: _tl_set_boss_pending_sub,
    TlSetPowerV800: _tl_set_power_v800,
    TlWaitBossDeadV800: _tl_wait_boss_dead_v800,
    TlEventConsume: _tl_event_consume,
    TlEventEmit: _tl_event_emit,
    TlShowRetryMenu: _tl_show_retry_menu,
    TlEndV800: _tl_end,
}

__all__ = ["TimelineRunner", "TL_HANDLERS", "TlHandler"]
