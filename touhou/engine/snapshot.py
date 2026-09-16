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
    """一段文本绘制项。

    z 参与和 sprite 的统一排序; 缺省 1e9 = 恒在 sprite 之上(旧行为),
    需要被覆盖层压住的文本显式给低 z(如结局淡色覆盖层, FadingEffect)。
    """

    text: str
    x: float
    y: float
    size: int = 16
    rgba: tuple[int, int, int, int] = (255, 255, 255, 255)
    z: float = 1e9


class EffectDraw(msgspec.Struct, frozen=True):
    """一个特效绘制项(按名字, frame 驱动内部动画)。"""

    effect: str
    x: float
    y: float
    frame: int = 0


class ShapeDraw(msgspec.Struct, frozen=True):
    """一个几何覆盖层绘制项(mod 导航线/安全圈等; 后端可选消费, 不消费静默丢弃)。

    kind: "line"(points 两端点) / "circle"(points[0] 圆心 + radius) /
    "polyline"(points 顺次相连, closed 首尾闭合)。
    """

    kind: str
    points: tuple[tuple[float, float], ...]
    radius: float = 0.0
    color: tuple[int, int, int] = (255, 255, 255)
    width: int = 1
    closed: bool = False


class SceneSnapshot(msgspec.Struct, frozen=True):
    """一帧要画什么: 渲染后端只认它 + 事件流, 拿不到 world 本体。"""

    frame: int
    sprites: tuple[SpriteDraw, ...] = ()
    texts: tuple[TextDraw, ...] = ()
    effects: tuple[EffectDraw, ...] = ()
    shapes: tuple[ShapeDraw, ...] = ()


class SnapshotBuilder:
    """帧内收集绘制项, build() 冻结成 SceneSnapshot 并清空(每帧全量重建)。"""

    def __init__(self) -> None:
        self.sprites: list[SpriteDraw] = []
        self.texts: list[TextDraw] = []
        self.effects: list[EffectDraw] = []
        self.shapes: list[ShapeDraw] = []

    def build(self, frame: int) -> SceneSnapshot:
        """冻结成本帧快照, 清空收集器留给下一帧。"""
        snapshot = SceneSnapshot(
            frame,
            tuple(self.sprites),
            tuple(self.texts),
            tuple(self.effects),
            tuple(self.shapes),
        )
        self.sprites.clear()
        self.texts.clear()
        self.effects.clear()
        self.shapes.clear()
        return snapshot
