"""对局 scene: 把"tick 世界 → 出快照"包成 Scene, 供 runner 驱动。"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import Event, InputFrame, SceneSnapshot
from ....engine.input import Button
from .. import result as result_flow
from ..world import Th07World
from .scene import Scene


class GameScene(Scene):
    """一局对局: Esc 暂停; 世界出结算(result)即结束, next_scene 交给装配处。

    留待: GameOver 续关画面(world 冻结等 view, 续关单接 continue_play/
    finalize_game_over); 6 面结局播放(现直接 finish_ending 跳过, 结局单接)。
    """

    playfield_chrome = True

    def __init__(
        self,
        world: Th07World,
        *,
        on_exit: Callable[[], Scene | None],
        on_result: Callable[[Th07World], None] | None = None,
    ) -> None:
        super().__init__()
        self.world = world
        self._on_exit = on_exit
        self._on_result = on_result
        self._events: list[Event] = []
        world.subscribers.append(self._events.append)
        self._snapshot = world.tick(InputFrame())  # 首帧快照(同原 run_game)
        self._frame_sounds: list[int] = []
        self.paused = False

    def step(self, inp: InputFrame) -> None:
        if Button.PAUSE in inp.pressed:
            self.paused = not self.paused
        if self.paused:
            self._frame_sounds = []
            return
        self._snapshot = self.world.tick(inp)
        self._frame_sounds = list(self.world.frame_sounds)
        w = self.world
        if w.ending is not None:
            result_flow.finish_ending(w)  # 结局画面留待, 先跳过播放直接结算
        if w.result is not None:
            if self._on_result is not None:
                self._on_result(w)
            self.done = True

    def snapshot(self) -> SceneSnapshot:
        return self._snapshot

    def events(self) -> tuple[Event, ...]:
        out = tuple(self._events)
        self._events.clear()
        return out

    def drain_sounds(self) -> list[int]:
        out, self._frame_sounds = self._frame_sounds, []
        return out

    def next_scene(self) -> Scene | None:
        return self._on_exit()
