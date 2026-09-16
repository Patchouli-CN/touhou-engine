"""对外公共魔改 API —— mod 制作者的写入门面(分层命名空间结构)。

与 basic.py 的读写分离约定: ``Game`` = 只读观测, ``ModApi`` = 改写。
**ModApi 是官方魔改口子: 这里的写操作(无敌/资源直改/自定义弹幕/画面
覆盖层)绕过正常游戏规则**, 仅供魔改/实验/调试, 不计入正常对局语义。

写操作全部走 ``Game.queue`` 命令队列(§2.5: sim 状态只有主线程能改,
帧边界统一应用)——调用方随便什么时候调, 下一帧边界生效, 返回值是
Future(应用结果/异常在里面); 模拟冻结(暂停/结算)时滞留到恢复。

命名空间结构::

    api = ModApi(game)
    api.player   自机: god_mode/set_invulnerability_time/set_power/set_bombs/
                 set_lives + pos/full_power(属性)
    api.boss     Boss: exists(属性)/set_life/set_pos
    api.bullets  敌弹: fire/fire_ring/clear + count(属性)
    api.score    分数: add
    api.gui      画面覆盖层: line/circle/polyline/text(叠进下一帧快照)

作品专属机制(th07 樱点/结界…)不进通用核, 由作品包自行提供; 作品数值语义
(满火力等)经注册表装配的 GameData 提供, 弹型模板号含义由作品定义。
"""

from __future__ import annotations

import math
from concurrent.futures import Future

from ..engine import Aim, Burst, FrameContext, ShapeDraw, TextDraw
from ..utils.math import Vec2
from .basic import Game, GameWorld

# 再导出: mod 脚本一条龙, 不必再摸 engine 内部模块
__all__ = [
    "Aim",
    "BossMods",
    "BulletsMods",
    "Burst",
    "GuiMods",
    "ModApi",
    "PlayerMods",
    "ScoreMods",
    "Vec2",
]

#: 通用核能力的一句话说明(available() 用)
_CORE_CAPABILITIES: dict[str, dict[str, str]] = {
    "player": {
        "god_mode": "无敌挂(= set_invulnerability_time(999), 须每帧调用)",
        "set_invulnerability_time": "自机无敌计时直改(帧)",
        "set_power": "火力直改(0..full_power, 上限取自作品数值表)",
        "set_bombs": "Bomb 数直改(>=0)",
        "set_lives": "残机数直改(>=0)",
        "pos": "自机坐标 (x, y)(属性)",
        "full_power": "满火力值(属性, 取自作品数值表)",
    },
    "boss": {
        "exists": "场上是否有 Boss(属性)",
        "set_life": "Boss 当前生命直改(不改上限 max_life)",
        "set_pos": "Boss 位置直改",
    },
    "bullets": {
        "fire": "发射一发自定义 Burst 弹幕(下一帧边界生效)",
        "fire_ring": "便捷: 中心放一圈单层匀速环形弹幕",
        "clear": "清屏: 移除全部敌弹",
        "count": "场上敌弹总数(属性)",
    },
    "score": {
        "add": "真实分加算(直接入账, 不走作品计分规则)",
    },
    "gui": {
        "line": "覆盖层画线段(叠进下一帧快照)",
        "circle": "覆盖层画圆(叠进下一帧快照)",
        "polyline": "覆盖层画折线(叠进下一帧快照)",
        "text": "覆盖层画文字(叠进下一帧快照)",
    },
}


def _set_stat(w: GameWorld, name: str, value: float) -> None:
    """set_stat 能力位(帧边界内调用): 缺钩子的作品报中文错。"""
    hook = getattr(w, "set_stat", None)
    if not callable(hook):
        raise NotImplementedError(
            f"当前作品未提供 set_stat() 写入钩子(apis 魔改面能力位, "
            f"由作品世界实现), 无法改写 {name!r}"
        )
    hook(name, value)


class _ModNamespace:
    """命名空间基座: 持有 Game 门面(读走门面, 写走命令队列)。"""

    def __init__(self, game: Game) -> None:
        self._game = game


class PlayerMods(_ModNamespace):
    """``ModApi.player`` —— 自机写入面: 无敌/火力/Bomb/残机 + 坐标观测。"""

    @property
    def full_power(self) -> int:
        """满火力值(作品数值表 GameData.full_power)。"""
        return self._game.assembly.data.full_power

    # ---- 无敌 ----
    def god_mode(self) -> Future:
        """无敌挂(= set_invulnerability_time(999))。"""
        return self.set_invulnerability_time(999)

    def set_invulnerability_time(self, timer: int = 999) -> Future:
        """无敌时间设置: 把自机无敌计时重置为 ``timer`` 帧(下一帧边界生效)。

        引擎每帧递减该计时(归零即恢复可中弹), 故须在输入策略(policy)里
        **每帧调用**才能持续无敌; 单次调用只保 ``timer`` 帧。
        """
        return self._game.queue(
            lambda w, ctx: setattr(w.player, "invulnerability_timer", timer)
        )

    # ---- 资源直改(公共签名用 int; 引擎内部 float 表示不外泄) ----
    def set_power(self, power: int) -> Future:
        """火力直改为 ``power``(合法域 0..``self.full_power``, 上限取自作品数值表)。"""
        if not 0 <= power <= self.full_power:
            raise ValueError(
                f"火力 {power} 超出本作品合法范围 0..{self.full_power}"
                f"(满火力值来自注册表 GameData.full_power)"
            )
        return self._game.queue(lambda w, ctx: _set_stat(w, "power", float(power)))

    def set_bombs(self, bombs: int) -> Future:
        """Bomb 数直改为 ``bombs``(>=0; HUD 显示即此值)。"""
        if bombs < 0:
            raise ValueError(f"Bomb 数 {bombs} 非法(须 >= 0)")
        return self._game.queue(lambda w, ctx: _set_stat(w, "bombs", float(bombs)))

    def set_lives(self, lives: int) -> Future:
        """残机数直改为 ``lives``(>=0; HUD 显示即此值)。"""
        if lives < 0:
            raise ValueError(f"残机数 {lives} 非法(须 >= 0)")
        return self._game.queue(lambda w, ctx: _set_stat(w, "lives", float(lives)))

    # ---- 观测补充(mod 常用的坐标; 全景观测仍走 Game.snapshot) ----
    @property
    def pos(self) -> tuple[float, float]:
        """自机坐标 (x, y)(自定义弹幕起点等场景用)。"""
        return self._game.player_pos


class BossMods(_ModNamespace):
    """``ModApi.boss`` —— Boss 写入面(场上无 Boss 时写操作报中文错)。"""

    @property
    def exists(self) -> bool:
        """场上当前是否有 Boss。"""
        return self._game._world.boss is not None

    def _require_boss(self, w: GameWorld) -> object:
        """取当前 Boss 对象(帧边界内); 无 Boss 时报中文错。"""
        boss = w.boss
        if boss is None:
            raise ValueError(
                "当前场上没有 Boss(未进 Boss 战或已击破), 先判 api.boss.exists 再写"
            )
        return boss

    def set_life(self, life: float) -> Future:
        """Boss 当前生命直改为 ``life``(不改上限 max_life; 下一帧边界生效)。

        跌破引擎生命阈值后, 阶段切换/清场仍由引擎正常流程驱动 —— 本方法
        只写数值, 不绕过作品机制语义。
        """

        def apply(w: GameWorld, ctx: FrameContext) -> None:
            setattr(self._require_boss(w), "life", float(life))

        return self._game.queue(apply)

    def set_pos(self, x: float, y: float) -> Future:
        """Boss 位置直改为 (x, y)(下一帧边界生效)。"""

        def apply(w: GameWorld, ctx: FrameContext) -> None:
            self._require_boss(w)
            enemy = getattr(w, "boss_enemy", None)
            if enemy is None:
                raise NotImplementedError("当前作品未透出 boss_enemy, 无法直改位置")
            enemy.machine.enemy.pos.set(x, y, 0.0)

        return self._game.queue(apply)


class BulletsMods(_ModNamespace):
    """``ModApi.bullets`` —— 敌弹写入面: 自定义弹幕发射/清屏 + 计数观测。"""

    def fire(self, burst: Burst) -> Future:
        """发射一发自定义 ``Burst``(下一帧边界生效), Future 结果是生成颗数。"""
        return self._game.queue(lambda w, ctx: w.bullets.fire(burst, ctx))

    def fire_ring(
        self,
        x: float,
        y: float,
        *,
        arms: int = 24,
        speed: float = 1.5,
        sprite: int = 1,
        sprite_offset: int = 6,
    ) -> Future:
        """便捷: 以 (x, y) 为中心发一圈 ``arms`` 颗的单层匀速环形弹幕。

        ``sprite``/``sprite_offset`` 是弹型模板号/变体偏移, **取值含义由作品
        定义**(th07: sprite 0..10 弹型模板, offset 为颜色/变体偏移); 本 API
        不做作品假设, 原样透传给引擎。Future 结果是生成颗数。
        """
        return self.fire(
            Burst(
                path=Vec2(x, y),
                base_angle=math.pi / 2,
                aim=Aim.RING_ABSOLUTE,
                arms=arms,
                rings=1,
                speed_a=speed,
                speed_b=speed,
                angle_step=0.0,
                sprite=sprite,
                sprite_offset=sprite_offset,
            )
        )

    def clear(self) -> Future:
        """清屏: 移除全部敌弹(下一帧边界生效; 产 BulletDespawned 事件)。

        只清弹体本身, 不动引擎的清弹窗口等记账 —— 与 Bomb/结界破裂的
        规则内清弹不同, 这是魔改直清。
        """
        return self._game.queue(lambda w, ctx: w.bullets.clear(ctx.events))

    # ---- 观测补充(mod 常用的计数; 全景观测仍走 Game.snapshot) ----
    @property
    def count(self) -> int:
        """场上敌弹总数(含出生特效态的弹)。"""
        return len(self._game._world.bullets.alive())


class ScoreMods(_ModNamespace):
    """``ModApi.score`` —— 分数写入面。"""

    def add(self, score: int) -> Future:
        """真实分 += ``score``(直接入账, 不走作品的道具/符卡计分规则)。"""

        def apply(w: GameWorld, ctx: FrameContext) -> None:
            w.globals.score += score

        return self._game.queue(apply)


class GuiMods(_ModNamespace):
    """``ModApi.gui`` —— 画面覆盖层(自定义导航线/文字弹出等)。

    调用即入队一条绘制命令, 下一帧边界叠进该帧 SceneSnapshot 的
    shapes/texts(快照每帧全量重建, 故**每帧都要重新推**, 在 policy 里
    调用)。后端不消费 shapes 时静默丢弃, 同一 policy 脚本两种模式通用。

    坐标系: 游戏区像素(th07: 384x448, 原点左上, **y 向下**), 与
    ``game.player_pos`` / ``bullets_array()`` 同一坐标系; 颜色 RGB 三元组。
    """

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        width: int = 1,
    ) -> Future:
        """画一条线段 (x1, y1)-(x2, y2)(叠进下一帧快照)。"""
        shape = ShapeDraw("line", ((x1, y1), (x2, y2)), color=color, width=width)
        return self._game.queue(lambda w, ctx: ctx.draw.shapes.append(shape))

    def circle(
        self,
        x: float,
        y: float,
        radius: float,
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        width: int = 1,
    ) -> Future:
        """画一个圆 (x, y) 半径 ``radius``; ``width=0`` 为实心填充(叠进下一帧快照)。"""
        shape = ShapeDraw("circle", ((x, y),), radius=radius, color=color, width=width)
        return self._game.queue(lambda w, ctx: ctx.draw.shapes.append(shape))

    def polyline(
        self,
        points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        width: int = 1,
        closed: bool = False,
    ) -> Future:
        """画一条折线(导航路线等); ``closed=True`` 首尾相连成多边形。"""
        shape = ShapeDraw(
            "polyline",
            tuple((float(px), float(py)) for px, py in points),
            color=color,
            width=width,
            closed=closed,
        )
        return self._game.queue(lambda w, ctx: ctx.draw.shapes.append(shape))

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        size: int = 16,
    ) -> Future:
        """画一段文字, 左上角锚在 (x, y)(自定义弹出提示; 叠进下一帧快照)。"""
        draw = TextDraw(content, x, y, size=size, rgba=(*color, 255))
        return self._game.queue(lambda w, ctx: ctx.draw.texts.append(draw))


class ModApi:
    """mod 制作的官方入口: 包住一个 ``Game``(只读观测), 叠加写操作面。用法::

        mods = ModApi(game)
        def policy(game):                    # 输入策略每帧被调
            mods.player.god_mode()           # 无敌挂(计时每帧递减, 故要每帧重置)
            mods.player.set_power(mods.player.full_power)
            mods.gui.circle(*mods.player.pos, 32, color=(0, 255, 0))
            return Input(shoot=True)

    写操作绕过正常游戏规则(见模块 docstring), 且全部经命令队列在下一帧
    边界生效(返回 Future); 观测仍走 Game 的只读属性。作品专属机制不进
    通用核, 由作品包自行提供。
    """

    def __init__(self, game: Game) -> None:
        self.game = game
        self.player = PlayerMods(game)
        self.boss = BossMods(game)
        self.bullets = BulletsMods(game)
        self.score = ScoreMods(game)
        self.gui = GuiMods(game)

    def __getattr__(self, name: str) -> object:
        """未知成员的中文提示(必须是 AttributeError, hasattr 语义才正确)。"""
        namespaces = sorted(
            k for k in self.__dict__ if not k.startswith("_") and k != "game"
        )
        raise AttributeError(
            f"ModApi 没有成员 {name!r}: 现有命名空间 {namespaces}"
            f"(全量能力清单见 available())"
        )

    def is_capabilities_exist(self, path: str) -> bool:
        """能力是否存在, 点路径 ``"命名空间.能力名"``(如 ``"player.set_power"``)。"""
        ns_name, _, cap = path.partition(".")
        if not cap:
            return False
        ns = self.__dict__.get(ns_name)
        return ns is not None and hasattr(ns, cap)

    def available(self) -> dict[str, dict[str, str]]:
        """全部可用能力的分层清单: 命名空间 → {能力名: 一句话说明}。"""
        return {ns: dict(caps) for ns, caps in _CORE_CAPABILITIES.items()}
