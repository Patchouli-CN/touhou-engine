"""th08(v800)时间轴语义测试: 门控/难度掩码/事件槽/掉落数(合成指令流)。"""

from __future__ import annotations

from touhou.engine.ecl import EclHost, TimelineRunner
from touhou.engine.ecl.state import EnemySpawn
from touhou.engine.rng import Rng
from touhou.games.th08.ecl_timeline import (
    TL_HANDLERS,
    TimelineInstr,
    TlEndV800,
    TlEventConsume,
    TlEventEmit,
    TlSetPowerV800,
    TlSpawnAt,
    TlSpawnDrops,
)


class TlHost(EclHost):
    """时间轴记录宿主: 各钩子开关可拨。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.boss = False
        self.suppressed = False
        self.events: list[int] = []

    def spawn_enemy(self, spawn: EnemySpawn, m) -> object | None:
        self.calls.append(("spawn", spawn))
        return object()

    def boss_present(self) -> bool:
        return self.boss

    def timeline_spawns_suppressed(self) -> bool:
        return self.suppressed

    def set_power(self, value: int) -> None:
        self.calls.append(("power", value))

    def consume_event(self, value: int) -> bool:
        if value in self.events:
            self.events.remove(value)
            return True
        return False

    def emit_event(self, value: int) -> None:
        self.events.append(value)


def make_runner(tl: list[TimelineInstr], host: TlHost) -> TimelineRunner:
    return TimelineRunner(tuple(tl), host, Rng(0), TL_HANDLERS)


def spawn_at(
    t: int, sub: int, *, mirror: bool = False, forced: bool = False
) -> TlSpawnAt:
    return TlSpawnAt(
        time=t,
        difficulty_mask=0xFF,
        sub_id=sub,
        mirror=mirror,
        forced=forced,
        x=10.0,
        y=20.0,
        life=50,
        item_drop=1,
        score=100,
    )


def test_forced_spawn_ignores_gate() -> None:
    host = TlHost()
    host.boss = True
    r = make_runner(
        [
            spawn_at(0, 8, forced=True),
            spawn_at(0, 9, mirror=True),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    assert [c[1].sub_id for c in host.calls] == [8]  # forced 过门控, 普通被拦


def test_difficulty_mask_filter() -> None:
    class Hard(TlHost):
        difficulty = 2

    host = Hard()
    r = make_runner(
        [
            TlSetPowerV800(time=0, difficulty_mask=0b0011, value=1),  # 无 H 位 → 跳过
            TlSetPowerV800(time=0, difficulty_mask=0b1100, value=2),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    assert host.calls == [("power", 2)]


def test_event_slots() -> None:
    """事件槽: emit 填槽, consume 无匹配停轴、有匹配继续。"""
    host = TlHost()
    r = make_runner(
        [
            TlEventConsume(time=0, difficulty_mask=0xFF, value=7),
            TlEventEmit(time=1, difficulty_mask=0xFF, value=9),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    assert r.idx == 0 and r.time == 0  # 无匹配, 停轴
    host.events.append(7)
    r.step()
    r.step()
    assert host.events == [9]  # 7 被消费, 9 被投放
    assert r.done


def test_spawn_drops_fields() -> None:
    host = TlHost()
    r = make_runner(
        [
            TlSpawnDrops(
                time=0,
                difficulty_mask=0xFF,
                sub_id=4,
                mirror=False,
                x=1.0,
                y=2.0,
                life=3,
                point_drops=5,
                power_or_point_drops=6,
                score=7,
            ),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    s = host.calls[0][1]
    assert (s.item_drop, s.point_drops, s.power_or_point_drops) == (-1, 5, 6)


def test_suppress_blocks_spawn() -> None:
    host = TlHost()
    host.suppressed = True
    r = make_runner([spawn_at(0, 8), TlEndV800(time=-1, difficulty_mask=0)], host)
    r.step()
    assert not host.calls
