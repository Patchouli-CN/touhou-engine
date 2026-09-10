"""对局 scene: 把"tick 世界 → 出快照"包成 Scene, 供 runner 驱动。"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import Event, InputFrame, SceneSnapshot
from ....engine.input import Button
from .. import result as result_flow
from ..replay import ReplayRecorder
from ..world import Th07World
from .bg3d import StageBg
from .fx import GameFx
from .music import BgmPlayer, StageBgm
from .scene import Scene


class GameScene(Scene):
    """一局对局: Esc 暂停; 世界出结算(result)即结束, next_scene 交给装配处。

    recorder 注入即录制(ReplayManager::OnUpdate 每帧一记, ReplayManager.cpp:33-77):
    每个喂给 tick 的 InputFrame 录一码, 过面自动打锚点, 结算时由装配处落盘。
    fx 注入即特效层(敌死亡爆散/符卡宣言/关卡标题/弹字): 每帧 tick 后 step,
    产出合进快照。留待: GameOver 续关画面(world 冻结等 view, 续关单接
    continue_play/finalize_game_over); 6 面结局播放(现直接 finish_ending 跳过,
    结局单接)。
    """

    playfield_chrome = True

    def __init__(
        self,
        world: Th07World,
        *,
        on_exit: Callable[[], Scene | None],
        on_result: Callable[[Th07World], None] | None = None,
        recorder: ReplayRecorder | None = None,
        fx: GameFx | None = None,
        music: BgmPlayer | None = None,
        bg: StageBg | None = None,
    ) -> None:
        super().__init__()
        self.world = world
        self._on_exit = on_exit
        self._on_result = on_result
        self._recorder = recorder
        self._fx = fx
        self._music = music
        self._bg = bg
        self._bg_surf = None
        self._bgm = StageBgm(music, world.archive) if music is not None else None
        self._events: list[Event] = []
        world.subscribers.append(self._events.append)
        if self._bgm is not None:
            world.subscribers.append(self._bgm.on_event)
        self._snapshot = world.tick(InputFrame())  # 首帧快照(同原 run_game)
        self._merge_fx()
        self._step_bg()
        if self._bgm is not None:
            self._bgm.step(world)  # 关头主曲(GameManager.cpp:782)
        if recorder is not None:
            recorder.record_tick(world, InputFrame())  # 首帧也录(回放逐帧对齐)
        self._frame_sounds: list[int] = []
        self.paused = False

    def _merge_fx(self) -> None:
        """特效层产出合进本帧快照(frozen Struct 重建, 原快照不动)。"""
        if self._fx is None:
            return
        sprites, texts = self._fx.step()
        base = self._snapshot
        self._snapshot = SceneSnapshot(
            base.frame,
            base.sprites + tuple(sprites),
            base.texts + tuple(texts),
            base.effects,
        )

    def _step_bg(self) -> None:
        """3D 背景推进一帧(暂停不走; runner 经 frame_bg 同步给后端)。"""
        if self._bg is not None:
            self._bg_surf = self._bg.step(self.world)

    @property
    def frame_bg(self):  # -> pygame.Surface | None(duck 通道, 不引类型)
        """本帧 3D 背景帧(runner 同步给后端; None = 纯色占位)。"""
        return self._bg_surf

    @property
    def frame_shakes(self) -> list[tuple[int, int, int]]:
        """本帧震屏事件(runner 同步给后端消费, ScreenEffect 的 type=1)。"""
        # 暂停帧 sim 不走, frame_shakes 是上一 tick 的残留, 不重复消费
        return [] if self.paused else self.world.frame_shakes

    def step(self, inp: InputFrame) -> None:
        if Button.PAUSE in inp.pressed:
            self.paused = not self.paused
            if self._music is not None:
                # 暂停菜单开关联动 BGM 暂停(GameManager.cpp:138-144, 仅 WAV 音源)
                if self.paused:
                    self._music.pause()
                else:
                    self._music.unpause()
        if self.paused:
            self._frame_sounds = []
            return
        self._snapshot = self.world.tick(inp)
        self._merge_fx()
        self._step_bg()
        if self._bgm is not None:
            self._bgm.step(self.world)
        if self._recorder is not None:
            self._recorder.record_tick(self.world, inp)
        self._frame_sounds = list(self.world.frame_sounds)
        w = self.world
        if w.ending is not None:
            if self._music is not None and w.ending.music:
                # 结局曲(Ending.cpp:300-301); 结局画面留待, 起播后即被标题曲接管
                self._music.play(w.ending.music)
            result_flow.finish_ending(w)  # 结局画面留待, 先跳过播放直接结算
        if w.result is not None:
            if self._on_result is not None:
                self._on_result(w)
            self.done = True

    def on_exit(self) -> None:
        """离开对局停 BGM(GameManager::DeletedCallback, GameManager.cpp:813)。"""
        if self._music is not None:
            self._music.stop()
        if self._bg is not None:
            self._bg.close()

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
