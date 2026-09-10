"""SceneSnapshot: 每帧"要画什么"的值语义快照。"""

from __future__ import annotations

import msgspec


class SpriteDraw(msgspec.Struct, frozen=True):
    """一个精灵绘制项, image 为资源键(由后端解析)。

    x/y 是中心锚点; rotation 弧度制屏幕顺时针为正(D3D LH +z 同向);
    最终缩放 = (scale*scale_x, scale*scale_y), 负值即翻转;
    blend_mode 0=普通 1=加算(AnmManager SetRenderStateForVm)。
    """

    image: str
    x: float
    y: float
    z: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0
    alpha: int = 255
    scale_x: float = 1.0
    scale_y: float = 1.0
    color: tuple[int, int, int] = (255, 255, 255)
    blend_mode: int = 0


class TextDraw(msgspec.Struct, frozen=True):
    """一段文本绘制项。"""

    text: str
    x: float
    y: float
    size: int = 16
    rgba: tuple[int, int, int, int] = (255, 255, 255, 255)


class EffectDraw(msgspec.Struct, frozen=True):
    """一个特效绘制项(按名字, frame 驱动内部动画)。"""

    effect: str
    x: float
    y: float
    frame: int = 0


class SceneSnapshot(msgspec.Struct, frozen=True):
    """一帧要画什么: 渲染后端只认它 + 事件流, 拿不到 world 本体。"""

    frame: int
    sprites: tuple[SpriteDraw, ...] = ()
    texts: tuple[TextDraw, ...] = ()
    effects: tuple[EffectDraw, ...] = ()


class SnapshotBuilder:
    """帧内收集绘制项, build() 冻结成 SceneSnapshot 并清空(每帧全量重建)。"""

    def __init__(self) -> None:
        self.sprites: list[SpriteDraw] = []
        self.texts: list[TextDraw] = []
        self.effects: list[EffectDraw] = []

    def build(self, frame: int) -> SceneSnapshot:
        """冻结成本帧快照, 清空收集器留给下一帧。"""
        snapshot = SceneSnapshot(
            frame, tuple(self.sprites), tuple(self.texts), tuple(self.effects)
        )
        self.sprites.clear()
        self.texts.clear()
        self.effects.clear()
        return snapshot
