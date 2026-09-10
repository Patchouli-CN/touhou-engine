"""th07 的道具场: ItemField 子类(满火力转樱/POC 线/结界吸附) + 道具类型号 + 奖残门槛。

类型号语义与收集分值出处 old/touhou/games/th07/items.py(ItemManager.cpp);
运动学/收集判定全在 engine ItemField, 本模块只接 th07 的触发条件。
"""

from __future__ import annotations

from enum import IntEnum

from ...engine.items import STATE_ATTRACT, STATE_FALL, STATE_SPAWN, Item, ItemField
from ...utils.math import Vec2
from .data import FULL_POWER

#: 点道具掉出屏幕的 subrank 惩罚(ItemManager OnUpdate: DecreaseSubrank(3))
OFFSCREEN_SUBRANK_PENALTY = 3


class ItemKind(IntEnum):
    """th07 道具类型号(ItemManager.cpp ItemType)。"""

    POWER_SMALL = 0
    POINT = 1
    POWER_BIG = 2
    BOMB = 3
    FULL_POWER = 4
    LIFE = 5
    POINT_BULLET = 6
    CHERRY = 7
    CHERRY_SMALL = 8
    STAR = 9


def next_needed_point_items_for_extend(extends: int, difficulty: int) -> int:
    """第 extends 次(0 起)点道具残机所需累计点道具数 (ItemManager.cpp:289-315)。"""
    # 出处 old/touhou/games/th07/items.py:52
    if difficulty < 4:
        if extends < 3:
            return extends * 75 + 50  # 50/125/200
        if extends < 5:
            return (extends - 3) * 150 + 300
        return (extends - 5) * 200 + 800
    if extends == 0:
        return 200
    if extends == 1:
        return 500
    return (extends - 2) * 500 + 800


class Th07ItemField(ItemField):
    """th07 的道具场: 满火力 P 转樱(spawn 钩子) + POC 线/结界吸附触发。

    power/poc_y/border_active/difficulty 由 world 的 sync system 每帧同步。
    """

    power: float = 0.0
    poc_y: float = 128.0
    border_active: bool = False
    difficulty: int = 1

    def spawn(self, at: Vec2, kind: int, state: int = STATE_FALL) -> Item:
        """放一个道具; 满火力时 P 系自动转樱点 (ItemManager::SpawnItem)。"""
        # 出处 old/touhou/games/th07/items.py:143
        if self.power >= FULL_POWER and kind in (
            ItemKind.POWER_SMALL,
            ItemKind.POWER_BIG,
        ):
            kind = ItemKind.CHERRY
        return super().spawn(at, kind, state)

    def _status_change(self, item: Item) -> None:
        """吸附触发 (ItemManager.cpp:150-168): 已吸附/POC 线(满火力或 Extra)/结界。"""
        # 出处 old/touhou/games/th07/items.py:170
        if item.state == STATE_SPAWN:
            return
        trigger = (
            item.state == STATE_ATTRACT
            or (
                (self.power >= FULL_POWER or self.difficulty >= 4)
                and self.player_pos.y < self.poc_y
            )
            or self.border_active
        )
        if not trigger:
            return
        if self.player_spawning:
            # 玩家重生中: 连已吸附的道具也改回下落缓降(死亡爆道具重撒)
            item.start = Vec2(0.0, -0.5)
            item.state = STATE_FALL
            return
        item.state = STATE_ATTRACT
        if self.border_active:
            item.auto_collect = True  # 仅结界收集标满分(C++ 仅 hasBorder 时置位)

    def despawn_power_items(self) -> None:
        """场上 P 系道具转樱点 (ItemManager::DespawnAllItems, 满火力/满火力道具时)。"""
        # 出处 old/touhou/games/th07/items.py:322
        for item in self.items:
            if item.kind in (ItemKind.POWER_SMALL, ItemKind.POWER_BIG):
                if item.start.y > -0.5:
                    item.start = Vec2(0.0, -0.5)
                item.kind = ItemKind.CHERRY
