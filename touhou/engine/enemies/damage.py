"""敌人伤害结算: 封顶/符卡缩放/无敌缩放的纯函数, 得分与作品资源修正在外。"""

from __future__ import annotations

import msgspec

#: 单帧伤害封顶 (EnemyManager.cpp:836 一带)
DAMAGE_CAP = 70


class DamageSettle(msgspec.Struct, frozen=True):
    """一次伤害结算的产出: raw 供作品算分/算资源, damage 是实际扣血。"""

    raw_damage: int = 0  # graze 追加后、封顶前
    damage: int = 0  # 封顶+缩放后


def settle_damage(
    damage: int,
    *,
    is_boss: bool,
    bomb_damage: bool = False,
    spellcard_active: bool = False,
    used_bomb: bool = False,
    invincibility_timer: int = 0,
    can_be_damaged: bool = True,
    graze_damage: int = 0,
) -> DamageSettle:
    """敌人受击结算 (EnemyManager.cpp:782-890 的作品无关段; C++ int 截断语义)。

    顺序: grazeSize 额外伤害 → 70 封顶 → 符卡缩放 → 无敌时间缩放。
    作品级修正(机型减免/资源获取)不在这: 调用方在 graze 追加后、本函数前
    自行调整, 或消费 DamageSettle.raw_damage 自行入账。
    """
    # grazeSize 额外伤害: 无 bomb 伤害时 damage += grazeDamage/2.5
    if graze_damage > 0 and not bomb_damage:
        damage = int(damage + graze_damage / 2.5)
    if damage <= 0:
        return DamageSettle()
    raw = damage
    if damage >= DAMAGE_CAP:
        damage = DAMAGE_CAP
    if can_be_damaged:
        # 符卡中的伤害缩放
        if spellcard_active:
            if not bomb_damage:
                damage = damage // 7 if damage > 7 else (1 if damage != 0 else 0)
            elif used_bomb:
                damage = int(damage / 2.5) if damage > 2 else (1 if damage != 0 else 0)
            else:
                damage = 0
        if invincibility_timer > 0:
            damage = damage // 9 if is_boss else 0
    else:
        damage = 0
    return DamageSettle(raw, damage)
