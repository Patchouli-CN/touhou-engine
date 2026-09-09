"""TimelineRunner 合成测试: 生敌回调序/门控/停轴/随机确定性/事件槽/难度掩码。"""

from __future__ import annotations

from touhou.engine.ecl import EclHost, TimelineRunner
from touhou.engine.ecl.state import EnemySpawn
from touhou.engine.rng import Rng
from touhou.schemas.ecl import (
    TimelineInstr,
    TlEnd,
    TlEndV800,
    TlEventConsume,
    TlEventEmit,
    TlMsgRead,
    TlMsgWait,
    TlSetBossInterrupt,
    TlSetPower,
    TlSetPowerV800,
    TlSpawn,
    TlSpawnAt,
    TlSpawnDrops,
    TlWaitBossDead,
)


class TlHost(EclHost):
    """时间轴记录宿主: 各钩子开关可拨。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.boss = False
        self.msg_showing = False
        self.suppressed = False
        self.events: list[int] = []

    def spawn_enemy(self, spawn: EnemySpawn, m) -> object | None:
        self.calls.append(("spawn", spawn))
        return object()

    def boss_present(self) -> bool:
        return self.boss

    def boss_active(self, idx: int) -> bool:
        self.calls.append(("boss_active", idx))
        return self.boss

    def timeline_spawns_suppressed(self) -> bool:
        return self.suppressed

    def set_boss_interrupt(self, boss_idx: int, interrupt: int) -> None:
        self.calls.append(("boss_interrupt", boss_idx, interrupt))

    def msg_read(self, msg_id: int) -> None:
        self.calls.append(("msg_read", msg_id))
        self.msg_showing = True

    def msg_wait(self) -> bool:
        return self.msg_showing

    def set_power(self, value: int) -> None:
        self.calls.append(("power", value))

    def consume_event(self, value: int) -> bool:
        if value in self.events:
            self.events.remove(value)
            return True
        return False

    def emit_event(self, value: int) -> None:
        self.events.append(value)


def make_runner(tl: list[TimelineInstr], host: TlHost, seed: int = 0) -> TimelineRunner:
    return TimelineRunner(tuple(tl), host, Rng(seed))


def spawn(
    t: int, sub: int, mode: int = 0, x: float = 32.0, y: float = -16.0
) -> TlSpawn:
    return TlSpawn(
        time=t, sub_id=sub, mode=mode, x=x, y=y, z=0.0, life=100, item_drop=0, score=500
    )


def test_spawn_callback_order_and_fields() -> None:
    host = TlHost()
    r = make_runner(
        [spawn(0, 3), spawn(2, 4, mode=1), spawn(2, 5, mode=3), TlEnd(time=-1)], host
    )
    r.step()
    r.step()  # time=1 无活
    r.step()
    assert r.done
    calls = host.calls
    assert [c[1].sub_id for c in calls] == [3, 4, 5]
    assert calls[0][1].life == 100
    # mode bit0 = 默认数值(-1/-1/-1), bit1(>=2) = 镜像
    assert (calls[1][1].life, calls[1][1].mirror) == (-1, 0)
    assert (calls[2][1].life, calls[2][1].mirror) == (-1, 1)


def test_boss_gate_blocks_spawn() -> None:
    host = TlHost()
    host.boss = True
    r = make_runner([spawn(0, 3), TlMsgRead(time=0, msg_id=7), TlEnd(time=-1)], host)
    r.step()
    assert [c[0] for c in host.calls] == ["msg_read"]


def test_random_pos_deterministic() -> None:
    """坐标 <= -990 的分量走注入 rng, 同种子同序列。"""
    tl = [spawn(0, 3, x=-999.0, y=-999.0), TlEnd(time=-1)]
    h1, h2 = TlHost(), TlHost()
    make_runner(tl, h1, seed=42).step()
    make_runner(tl, h2, seed=42).step()
    s1, s2 = h1.calls[0][1], h2.calls[0][1]
    assert (s1.x, s1.y) == (s2.x, s2.y)
    assert 0.0 <= s1.x < 384.0 and 0.0 <= s1.y < 448.0


def test_msg_wait_stalls_timeline() -> None:
    host = TlHost()
    r = make_runner(
        [TlMsgRead(time=0, msg_id=1), TlMsgWait(time=0), spawn(1, 3), TlEnd(time=-1)],
        host,
    )
    r.step()  # msg_read → msg_wait 停轴
    assert [c[0] for c in host.calls] == ["msg_read"]
    r.step()
    assert r.time == 0 and r.idx == 1 and not r.done  # 时刻冻结在 msg_wait
    host.msg_showing = False
    r.step()
    r.step()
    assert [c[1].sub_id for c in host.calls if c[0] == "spawn"] == [3]
    assert r.done


def test_wait_boss_dead_stalls() -> None:
    host = TlHost()
    host.boss = True
    r = make_runner(
        [TlWaitBossDead(time=0, boss_idx=1), spawn(0, 3), TlEnd(time=-1)], host
    )
    r.step()
    assert ("spawn",) not in [(c[0],) for c in host.calls]
    assert r.idx == 0 and r.time == 0  # 停轴
    host.boss = False
    r.step()
    assert [c[1].sub_id for c in host.calls if c[0] == "spawn"] == [3]


def test_set_power_and_boss_interrupt() -> None:
    host = TlHost()
    r = make_runner(
        [
            TlSetPower(time=0, value=64),
            TlSetBossInterrupt(time=0, boss_idx=3, interrupt=9),
            TlEnd(time=-1),
        ],
        host,
    )
    r.step()
    assert host.calls == [("power", 64), ("boss_interrupt", 3, 9)]


# ---- v800 ----


def test_v800_forced_spawn_ignores_gate() -> None:
    host = TlHost()
    host.boss = True
    r = make_runner(
        [
            TlSpawnAt(
                time=0,
                difficulty_mask=0xFF,
                sub_id=8,
                mirror=False,
                forced=True,
                x=10.0,
                y=20.0,
                life=50,
                item_drop=1,
                score=100,
            ),
            TlSpawnAt(
                time=0,
                difficulty_mask=0xFF,
                sub_id=9,
                mirror=True,
                forced=False,
                x=0.0,
                y=0.0,
                life=1,
                item_drop=0,
                score=0,
            ),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    assert [c[1].sub_id for c in host.calls] == [8]  # forced 过门控, 普通被拦


def test_v800_difficulty_mask_filter() -> None:
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


def test_v800_event_slots() -> None:
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


def test_v800_spawn_drops_fields() -> None:
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


def test_suppress_blocks_v800_spawn() -> None:
    host = TlHost()
    host.suppressed = True
    r = make_runner(
        [
            TlSpawnAt(
                time=0,
                difficulty_mask=0xFF,
                sub_id=8,
                mirror=False,
                forced=False,
                x=0.0,
                y=0.0,
                life=1,
                item_drop=0,
                score=0,
            ),
            TlEndV800(time=-1, difficulty_mask=0),
        ],
        host,
    )
    r.step()
    assert not host.calls
