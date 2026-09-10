"""th07 对局应用壳: 组合根 → 世界 + pygame 后端 → 60fps 主循环。

菜单/结算/续关画面留待后续单; 本壳直进一面, Esc 暂停, 窗口关闭退出。
"""

from __future__ import annotations

from ....engine import Event, GameAssembly, InputFrame, RenderBackend
from ....engine.input import Button
from ..world import Th07World, compose_world
from .backend import PygameBackend


def run_game(
    assembly: GameAssembly,
    *,
    character: int = 0,
    difficulty: int = 1,
    stage_no: int = 1,
    seed: int | None = None,
    scale: int | None = None,
    backend: RenderBackend | None = None,
    world: Th07World | None = None,
) -> Th07World:
    """开窗口打一局: 主循环 = 渲染/采输入 → tick → 播 SE; 返回打完的世界。"""
    if world is None:
        world = compose_world(
            assembly,
            character=character,
            difficulty=difficulty,
            stage_no=stage_no,
            seed=seed,
        )
    if backend is None:
        backend = PygameBackend(world.archive, anm_version=assembly.scripts.anm_version)
    events: list[Event] = []
    world.subscribers.append(events.append)
    backend.open(title=assembly.title, scale=scale)
    paused = False
    try:
        snapshot = world.tick(InputFrame())
        while True:
            inp = backend.frame(tuple(events), snapshot)
            events.clear()
            if inp is None:
                break
            if Button.PAUSE in inp.pressed:
                paused = not paused
            if paused:
                continue
            snapshot = world.tick(inp)
            backend.play_sounds(world.frame_sounds)
    finally:
        backend.close()
    return world
