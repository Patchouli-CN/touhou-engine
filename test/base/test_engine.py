"""engine 骨架测试: 管线序/事件流/快照/RNG/命令队列。"""

from __future__ import annotations

import msgspec
import pytest

from touhou.engine import (
    Button,
    Command,
    Event,
    EventStream,
    FrameContext,
    InputFrame,
    MenuAction,
    Pipeline,
    Rng,
    Slot,
    SpriteDraw,
    System,
    World,
    tick_frame,
)


class _World(World):
    log: list[str] = msgspec.field(default_factory=list)


class _Hit(Event, tag="hit"):
    dmg: int


class _Rec(System[_World]):
    """记录自己名字的 system。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def tick(self, world: _World, ctx: FrameContext) -> None:
        world.log.append(self.name)


def test_pipeline_slot_order() -> None:
    """槽位执行序固定(与挂载先后无关), 同槽按挂载序。"""
    world = _World()
    pipe: Pipeline[_World] = Pipeline()
    pipe.add(Slot.OUTPUT, _Rec("out1"))
    pipe.add(Slot.LOGIC, _Rec("logic"))
    pipe.add(Slot.INPUT, _Rec("in"))
    pipe.add(Slot.OUTPUT, _Rec("out2"))
    pipe.add(Slot.MOVEMENT, _Rec("move"))
    tick_frame(world, pipe, FrameContext(Rng(0)))
    assert world.log == ["in", "logic", "move", "out1", "out2"]
    assert world.frame == 1


def test_tick_frame_returns_snapshot_and_resets_builder() -> None:
    """tick_frame 产出本帧快照, 收集器帧末清空(每帧全量重建)。"""

    class _Draw(System[_World]):
        def tick(self, world: _World, ctx: FrameContext) -> None:
            ctx.draw.sprites.append(SpriteDraw("player", float(world.frame), 2.0))

    world = _World()
    ctx = FrameContext(Rng(0))
    pipe: Pipeline[_World] = Pipeline()
    pipe.add(Slot.OUTPUT, _Draw())
    s1 = tick_frame(world, pipe, ctx)
    s2 = tick_frame(world, pipe, ctx)
    assert s1.frame == 1 and s1.sprites == (SpriteDraw("player", 0.0, 2.0),)
    assert s2.frame == 2 and s2.sprites == (SpriteDraw("player", 1.0, 2.0),)
    assert ctx.draw.sprites == []


def test_event_stream_flush_delivers_and_clears() -> None:
    """帧内 emit 的事件帧末一次性发订阅者, 清空后不重复投递。"""
    stream = EventStream()
    got: list[Event] = []
    stream.subscribe(got.append)
    stream.emit(_Hit(dmg=1))
    stream.flush()
    stream.flush()
    assert got == [_Hit(dmg=1)]


def test_events_flow_through_frame_and_clear() -> None:
    """管线 system 产的事件经 tick_frame 帧末 flush, 帧间不串。"""

    class _Emitter(System[_World]):
        def tick(self, world: _World, ctx: FrameContext) -> None:
            ctx.events.emit(_Hit(dmg=world.frame))

    world = _World()
    ctx = FrameContext(Rng(0))
    got: list[Event] = []
    ctx.events.subscribe(got.append)
    pipe: Pipeline[_World] = Pipeline()
    pipe.add(Slot.LOGIC, _Emitter())
    tick_frame(world, pipe, ctx)
    tick_frame(world, pipe, ctx)
    assert got == [_Hit(dmg=0), _Hit(dmg=1)]


def test_snapshot_value_semantics() -> None:
    """快照是不可变值对象: 相等按值, 字段不可改。"""
    a = SpriteDraw("player", 1.0, 2.0)
    b = SpriteDraw("player", 1.0, 2.0)
    assert a == b
    with pytest.raises(AttributeError):
        a.x = 9.0


def test_input_frame_value_semantics() -> None:
    """InputFrame 是值语义 struct: 按键集 + 菜单动作, 默认全空。"""
    assert InputFrame() == InputFrame()
    inp = InputFrame(
        held=frozenset({Button.SHOT, Button.RIGHT}),
        pressed=frozenset({Button.SHOT}),
        menu=frozenset({MenuAction.CONFIRM}),
    )
    assert Button.SHOT in inp.held and MenuAction.CONFIRM in inp.menu


def test_rng_deterministic_same_seed() -> None:
    """同种子同序列, 不同种子不同序列。"""
    a, b = Rng(42), Rng(42)
    assert [a.u32() for _ in range(10)] == [b.u32() for _ in range(10)]
    assert Rng(42).u16() != Rng(43).u16()


def test_rng_state_restore() -> None:
    """state()/restore() 快照恢复后续序列完全一致。"""
    rng = Rng(7)
    head = [rng.u16() for _ in range(5)]
    state = rng.state()
    tail = [rng.u16() for _ in range(5)]
    rng.restore(state)
    assert [rng.u16() for _ in range(5)] == tail
    rng2 = Rng(7)
    assert [rng2.u16() for _ in range(10)] == head + tail


class _Log(Command):
    """往 world.log 追加的命令。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def apply(self, world: World, ctx: FrameContext) -> None:
        assert isinstance(world, _World)
        world.log.append(f"cmd:{self.name}")


def test_commands_applied_at_frame_boundary() -> None:
    """命令在帧边界统一应用: 帧前入队先于 system 生效, 帧中入队下一帧生效。"""

    class _QueueMid(System[_World]):
        def tick(self, world: _World, ctx: FrameContext) -> None:
            world.log.append("sys")
            ctx.commands.push(_Log("mid"))

    world = _World()
    ctx = FrameContext(Rng(0))
    pipe: Pipeline[_World] = Pipeline()
    pipe.add(Slot.LOGIC, _QueueMid())
    ctx.commands.push(_Log("pre"))
    tick_frame(world, pipe, ctx)
    assert world.log == ["cmd:pre", "sys"]
    tick_frame(world, pipe, ctx)
    assert world.log == ["cmd:pre", "sys", "cmd:mid", "sys"]


def test_commands_apply_in_push_order() -> None:
    """同批命令按入队序应用。"""
    world = _World()
    ctx = FrameContext(Rng(0))
    for name in ("a", "b", "c"):
        ctx.commands.push(_Log(name))
    tick_frame(world, Pipeline(), ctx)
    assert world.log == ["cmd:a", "cmd:b", "cmd:c"]
