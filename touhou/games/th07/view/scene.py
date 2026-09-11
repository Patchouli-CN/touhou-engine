"""scene 骨架: 画面基类 + 显式装配的帧驱动 runner。

scene 之间不靠注册表: 装配处(run_app)把"下一个 scene 怎么来"以工厂
闭包显式注入, 后续单加新画面 = 新 Scene 子类 + 装配处多接一个工厂。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ....engine import Event, InputFrame, RenderBackend, SceneSnapshot
from .music import BgmPlayer


class Scene(ABC):
    """一个画面: step 吃输入推进状态, snapshot 出本帧要画什么。

    playfield_chrome: True = 后端把世界 sprite 裁进游戏区 + 震屏偏移(对局画面);
    边框/右栏面板贴图由快照 HUD 生产(Gui 层 sprite)。菜单画面保持 False 全屏绘制。
    """

    playfield_chrome = False

    def __init__(self) -> None:
        self.done = False  # True 后 runner 取 next_scene() 换画面(None = 退出)

    def on_enter(self) -> None:
        """切进本画面(BGM 起播 hook 点)。"""

    def on_exit(self) -> None:
        """离开本画面(BGM 停播 hook 点)。"""

    @abstractmethod
    def step(self, inp: InputFrame) -> None:
        """推进一帧。"""

    @abstractmethod
    def snapshot(self) -> SceneSnapshot:
        """本帧要画什么。"""

    def events(self) -> tuple[Event, ...]:
        """本帧要随快照喂给后端的事件流(sim 事件, 菜单画面恒空)。"""
        return ()

    def drain_sounds(self) -> list[int]:
        """取出本帧积攒的 SE(idx 语义在 schemas 音效表), 取完即清。"""
        return []

    @abstractmethod
    def next_scene(self) -> Scene | None:
        """Done 后的下一个画面; None = 应用退出。"""


def run_scenes(
    first: Scene,
    backend: RenderBackend,
    *,
    title: str,
    scale: int | None = None,
    music: BgmPlayer | None = None,
) -> None:
    """帧驱动主循环: 渲染/采输入 → step → 播 SE, done 就换 scene 直到退出。

    music 注入即 BGM 链: 每帧 poll() 做 WAV 循环段回卷(与 scene 无关,
    否则菜单画面的 WAV 曲播完一遍就停)。
    """
    backend.open(title=title, scale=scale)
    scene = first
    scene.on_enter()
    _sync_chrome(scene, backend)
    try:
        while True:
            inp = backend.frame(scene.events(), scene.snapshot())
            if inp is None:  # 窗口关闭 = 整个应用退出
                break
            scene.step(inp)
            backend.play_sounds(scene.drain_sounds())
            _sync_shakes(scene, backend)
            _sync_bg(scene, backend)
            if music is not None:
                music.poll()
            if scene.done:
                scene.on_exit()
                nxt = scene.next_scene()
                if nxt is None:
                    break
                scene = nxt
                scene.on_enter()
                _sync_chrome(scene, backend)
    finally:
        backend.close()


def _sync_chrome(scene: Scene, backend: RenderBackend) -> None:
    """把 scene 的游戏区 chrome 开关同步给后端(有该属性的后端才吃)。"""
    setattr(backend, "playfield_chrome", scene.playfield_chrome)


def _sync_shakes(scene: Scene, backend: RenderBackend) -> None:
    """把 scene 本帧的震屏事件喂给后端(两侧都 duck-typed, 缺任一侧即跳过)。"""
    shakes = getattr(scene, "frame_shakes", None)
    register = getattr(backend, "register_shakes", None)
    if shakes and register is not None:
        register(shakes)


def _sync_bg(scene: Scene, backend: RenderBackend) -> None:
    """把 scene 的 3D 背景帧喂给后端(两侧都 duck-typed, 缺任一侧即跳过)。"""
    set_bg = getattr(backend, "set_background", None)
    if set_bg is not None:
        set_bg(getattr(scene, "frame_bg", None))
