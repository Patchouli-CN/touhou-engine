"""对局 scene: 把"tick 世界 → 出快照"包成 Scene, 供 runner 驱动。"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import Event, InputFrame, SceneSnapshot, SpriteDraw
from ....engine.input import Button
from .. import result as result_flow
from ..replay import ReplayRecorder
from ..world import Th07World
from .bg3d import StageBg
from .fx import GameFx
from .music import BgmPlayer, StageBgm
from .pause import SE_PAUSED, PauseMenu
from .retry import RetryMenu
from .scene import Scene


class GameScene(Scene):
    """一局对局: Esc 暂停菜单; GameOver 可续关时冻结开续关菜单。

    暂停 = PauseMenu 子态(世界冻结不 tick; Resume 继续, Return to Title 经
    on_quit 直回标题不进结算, AsciiManager.cpp:755-759); 续关 = RetryMenu
    子态(世界冻结不重建); 结局/结算出炉即结束, 后续画面(结局/结算/标题)由
    装配处链。recorder 注入即录制(ReplayManager::OnUpdate 每帧一记,
    ReplayManager.cpp:33-77): 每个喂给 tick 的 InputFrame 录一码, 过面自动打
    锚点, 存盘由结算画面选槽完成(ResultScene, ResultScreen.cpp
    HandleReplaySaveKeyboard)。fx 注入即特效层(敌死亡爆散/符卡宣言/关卡标题/
    弹字): 每帧 tick 后 step, 产出合进快照。
    """

    playfield_chrome = True

    def __init__(
        self,
        world: Th07World,
        *,
        on_exit: Callable[[], Scene | None],
        on_quit: Callable[[], Scene | None] | None = None,
        recorder: ReplayRecorder | None = None,
        fx: GameFx | None = None,
        music: BgmPlayer | None = None,
        bg: StageBg | None = None,
        anm_version: int = 2,
        input_source: Callable[[Th07World], InputFrame] | None = None,
    ) -> None:
        super().__init__()
        self.world = world
        self._on_exit = on_exit
        self._on_quit = on_quit
        self._recorder = recorder
        self._fx = fx
        self._music = music
        self._bg = bg
        self._anm_version = anm_version
        # 逐帧输入源(观战策略, apis 注入): 主路径覆盖键盘输入, 暂停/续关菜单
        # 与 Esc 仍走键盘
        self._input_source = input_source
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
        self._pause: PauseMenu | None = None  # 暂停菜单子态(冻结中)
        self._quit = False  # 暂停菜单选 Return to Title(弃局回标题不进结算)
        self._retry: RetryMenu | None = None  # 续关菜单子态(冻结中)

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
            base.shapes,
        )

    def _step_bg(self) -> None:
        """3D 背景推进一帧(暂停/冻结不走; runner 经 frame_bg 同步给后端)。"""
        if self._bg is not None:
            self._bg_surf = self._bg.step(self.world)

    @property
    def frame_bg(self):  # -> pygame.Surface | None(duck 通道, 不引类型)
        """本帧 3D 背景帧(runner 同步给后端; None = 纯色占位)。"""
        return self._bg_surf

    @property
    def frame_shakes(self) -> list[tuple[int, int, int]]:
        """本帧震屏事件(runner 同步给后端消费, ScreenEffect 的 type=1)。"""
        # 暂停/冻结帧 sim 不走, frame_shakes 是上一 tick 的残留, 不重复消费
        if self.paused or self._retry is not None:
            return []
        return self.world.frame_shakes

    def step(self, inp: InputFrame) -> None:
        if self._retry is not None:
            self._step_retry(inp)
            return
        if self._pause is not None:
            self._step_pause(inp)
            return
        if Button.PAUSE in inp.pressed:
            # Esc 开暂停菜单(GameManager.cpp:129-145: isInPauseMenu=1 +
            # AUDIO_PAUSE + SOUND_PAUSED; BGM pause 在 PauseMenu 内)
            self.paused = True
            self._pause = PauseMenu(
                self.world, anm_version=self._anm_version, music=self._music
            )
            self._frame_sounds = [SE_PAUSED]
            return
        if self._input_source is not None:
            inp = self._input_source(self.world)  # 观战: 策略输入覆盖键盘
        prev = self._snapshot
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
            # 6 面通关 → 结局画面(Gui.cpp NEXT_LEVEL → curState=9, :1073)
            self.done = True
        elif w.game_over and w.result is None and result_flow.continue_available(w):
            # 可续关: 世界冻结开续关菜单(AsciiManager.cpp RetryMenu);
            # 冻结帧沿用死亡前最后一帧快照(C++ menuBackground = 游戏截屏,
            # :870-876), game_over 分支的空快照不采用
            self._snapshot = prev
            self._retry = RetryMenu(w, anm_version=self._anm_version, music=self._music)
        elif w.result is not None:
            self.done = True  # 结算出炉 → 结算画面(ResultScene)

    def _step_retry(self, inp: InputFrame) -> None:
        """续关菜单一帧: 世界冻结(不 tick), 覆层叠在死亡帧快照上。"""
        retry = self._retry
        assert retry is not None
        retry.step(inp)
        self._frame_sounds = retry.drain_sounds()
        if retry.choice == "continue":
            result_flow.continue_play(self.world)  # 当场复活接着打 (:958-1009)
            self._retry = None
        elif retry.choice == "quit":
            result_flow.finalize_game_over(self.world)  # 选 No → 结算 (:942-956)
            self._retry = None
            self.done = True

    def _step_pause(self, inp: InputFrame) -> None:
        """暂停菜单一帧: 世界冻结(不 tick), 覆层叠在冻结快照上。"""
        pause = self._pause
        assert pause is not None
        pause.step(inp)
        self._frame_sounds = pause.drain_sounds()
        if pause.choice == "resume":
            self._pause = None
            self.paused = False
        elif pause.choice == "quit":
            # Return to Title: 弃局直回标题, 不进结算 (:755-759)
            self._pause = None
            self._quit = True
            self.done = True

    def on_exit(self) -> None:
        """离开对局停 BGM(GameManager::DeletedCallback, GameManager.cpp:813)。"""
        if self._music is not None:
            self._music.stop()
        if self._bg is not None:
            self._bg.close()

    def snapshot(self) -> SceneSnapshot:
        overlay: list[SpriteDraw] = []
        if self._retry is not None:
            overlay = self._retry.sprites()
        elif self._pause is not None:
            overlay = self._pause.sprites()
        if not overlay:
            return self._snapshot
        base = self._snapshot  # 冻结帧 + 菜单覆层
        return SceneSnapshot(
            base.frame,
            base.sprites + tuple(overlay),
            base.texts,
            base.effects,
            base.shapes,
        )

    def events(self) -> tuple[Event, ...]:
        out = tuple(self._events)
        self._events.clear()
        return out

    def drain_sounds(self) -> list[int]:
        out, self._frame_sounds = self._frame_sounds, []
        return out

    def next_scene(self) -> Scene | None:
        if self._quit and self._on_quit is not None:
            return self._on_quit()  # 弃局回标题(SUPERVISOR_STATE_MAINMENU)
        return self._on_exit()
