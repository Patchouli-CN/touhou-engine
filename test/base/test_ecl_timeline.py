"""TimelineRunner 推进框架的合成测试(合成指令类 + 合成 handler, 作品语义在作品侧测)。"""

from __future__ import annotations

from touhou.engine.ecl import EclHost, TimelineRunner
from touhou.engine.rng import Rng
from touhou.schemas.ecl import TlInstr


class TlPing(TlInstr, frozen=True, tag="tl_ping"):
    """合成指令: 到点记录一次。"""

    value: int = 0


class TlStall(TlInstr, frozen=True, tag="tl_stall"):
    """合成指令: 停轴等待(host 放行前 time 冻结)。"""


class TlMasked(TlInstr, frozen=True, tag="tl_masked"):
    """合成指令: 带难度掩码(过滤机制在框架层)。"""

    difficulty_mask: int


class TlHost(EclHost):
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.open = False


def _ping(r: TimelineRunner, ins: TlPing) -> None:
    r.host.calls.append(("ping", ins.value))  # type: ignore[attr-defined]


def _stall(r: TimelineRunner, ins: TlStall) -> bool:
    return not r.host.open  # type: ignore[attr-defined]


def _masked(r: TimelineRunner, ins: TlMasked) -> None:
    r.host.calls.append(("masked", ins.difficulty_mask))  # type: ignore[attr-defined]


_HANDLERS = {TlPing: _ping, TlStall: _stall, TlMasked: _masked}


def make_runner(tl: list[TlInstr], host: TlHost) -> TimelineRunner:
    return TimelineRunner(tuple(tl), host, Rng(0), _HANDLERS)


def test_step_executes_due_instrs_and_finishes() -> None:
    host = TlHost()
    r = make_runner([TlPing(time=0, value=1), TlPing(time=2, value=2)], host)
    r.step()
    assert host.calls == [("ping", 1)]
    r.step()  # time=1 无活
    assert host.calls == [("ping", 1)]
    r.step()
    assert host.calls == [("ping", 1), ("ping", 2)]
    assert r.done  # 越界 = 跑完


def test_stall_freezes_time() -> None:
    host = TlHost()
    r = make_runner([TlStall(time=0), TlPing(time=1, value=9)], host)
    r.step()
    assert r.idx == 0 and r.time == 0  # 停轴: 下标与时刻都冻结
    host.open = True
    r.step()
    r.step()
    assert host.calls == [("ping", 9)]
    assert r.done


def test_difficulty_mask_filter() -> None:
    """指令带 difficulty_mask 且不含当前难度位 → 跳过(机制同 v800 时间轴)。"""

    class Hard(TlHost):
        difficulty = 2

    host = Hard()
    r = make_runner(
        [
            TlMasked(time=0, difficulty_mask=0b0011),
            TlMasked(time=0, difficulty_mask=0b1100),
        ],
        host,
    )
    r.step()
    assert host.calls == [("masked", 0b1100)]


def test_negative_time_marks_done() -> None:
    host = TlHost()
    r = make_runner([TlPing(time=-1, value=1)], host)
    assert r.done
    r.step()  # 不执行, 不炸
    assert host.calls == []
