"""敌人场: EnemyField 状态容器(列表/索敌/体术与自机弹伤害管线)。

帧序槽位: LOGIC 跑 ECL(bomb 盒伤害若用须在更前) → COLLISION 先体术后
自机弹伤害+击坠结算, 同 C++ OnUpdate 伤害段顺序; system 落位见 system.py。
"""

from __future__ import annotations

import math

import msgspec

from ...utils.math import Vec2
from ..bomb import BombField
from ..context import FrameContext
from ..ecl.machine import EclMachine
from ..ecl.state import EnemySpawn, Vec3
from ..player import PlayerField
from ..shots import ShotField
from .damage import DamageSettle, settle_damage
from .enemy import Enemy, EnemyDamaged, EnemySpawned


class Targeting(msgspec.Struct):
    """每帧的索敌状态(Player.hpp positionOfLastEnemyHit/sakuyaTargetPosition)。

    每帧由作品侧 reset, 伤害扫描中按敌人顺序 update, 扫完读回喂追踪弹。
    homing_window 非空时启用窗口索敌(旧 is_sakuya 分支的通用化):
    目标相对玩家的 atan2 角度须落在窗口内。
    """

    position_of_last_enemy_hit: Vec2 = msgspec.field(
        default_factory=lambda: Vec2(-999.0, -999.0)
    )
    homing_target: Vec2 = msgspec.field(default_factory=lambda: Vec2(-999.0, -999.0))
    targeting: bool = False
    homing_window: tuple[float, float] | None = None  # (lo, hi) 弧度

    def reset(self) -> None:
        """帧首复位 (Player::UpdateUI 对应)。"""
        self.position_of_last_enemy_hit = Vec2(-999.0, -999.0)
        self.homing_target = Vec2(-999.0, -999.0)
        self.targeting = False

    def update(self, enemy_pos: Vec2, player_pos: Vec2, *, is_boss: bool) -> None:
        """EnemyManager.cpp:894-938; boss 取 |dx| 更近者, 否则取最靠下者。"""
        windowed = self.homing_window is not None
        if is_boss:
            enemy_diff = enemy_pos - player_pos
            diff = self.position_of_last_enemy_hit - player_pos
            if not self.targeting or abs(diff.x) > abs(enemy_diff.x):
                self.position_of_last_enemy_hit = enemy_pos
            if windowed:
                lo, hi = self.homing_window or (0.0, 0.0)
                diff = self.homing_target - player_pos
                angle = math.atan2(enemy_diff.y, enemy_diff.x)
                if lo <= angle <= hi and (
                    not self.targeting or abs(diff.x) > abs(enemy_diff.x)
                ):
                    self.homing_target = enemy_pos
                    self.targeting = True
            else:
                self.targeting = True
        if not self.targeting:
            if self.position_of_last_enemy_hit.y < enemy_pos.y:
                self.position_of_last_enemy_hit = enemy_pos
            if windowed and self.homing_target.y < -900.0:
                lo, hi = self.homing_window or (0.0, 0.0)
                angle = math.atan2(
                    enemy_pos.y - player_pos.y, enemy_pos.x - player_pos.x
                )
                if lo <= angle <= hi:
                    self.homing_target = enemy_pos


def _target_in_bounds(pos: Vec2, full_size: tuple[float, float]) -> bool:
    """GameManager::IsInBounds (GameManager.cpp:42-65): 盒心±半宽/半高在版内。"""
    hw, hh = full_size[0] / 2.0, full_size[1] / 2.0
    return not (
        hw + pos.x < 0.0 or pos.x - hw > 384.0 or hh + pos.y < 0.0 or pos.y - hh > 448.0
    )


class EnemyField(msgspec.Struct):
    """敌人场状态容器: 敌人列表 + 帧内同步标志(作品侧每帧按需写)。

    frozen = bomb 冻结 ECL(作品同步); spellcard_active/spellcard_used_bomb =
    符卡伤害缩放输入(作品按 boss 状态同步); targeting/player_pos 供索敌。
    扩展点: ``adjust_damage``(70 封顶前的作品级伤害修正) 与
    ``enemy_callback_reset``(回调切换时的作品侧复位), 基类恒等/无操作。
    """

    enemies: list[Enemy] = msgspec.field(default_factory=list)
    next_id: int = 1
    frozen: bool = False
    spellcard_active: bool = False
    spellcard_used_bomb: bool = False
    player_pos: Vec2 = Vec2(192, 400)
    targeting: Targeting = msgspec.field(default_factory=Targeting)

    # ---- 生成(作品宿主的 spawn_enemy 回调进来) ----
    def spawn(
        self, machine: EclMachine, desc: EnemySpawn | None, ctx: FrameContext
    ) -> Enemy:
        """把一台 ECL 机登记成敌人; desc 应用生敌描述(坐标/生命/分/掉落/镜像)。"""
        # enemyTemplate 默认值 (EnemyManager::Initialize): life=1 score=100
        # canDie/hasContactHitbox/canBeDamaged/isHittable=1, 见 Enemy 字段默认
        e = Enemy(machine=machine, enemy_id=self.next_id)
        self.next_id += 1
        st = machine.enemy
        sub_id = -1
        if desc is not None:
            sub_id = desc.sub_id
            st.pos = Vec3(desc.x, desc.y, desc.z)
            st.prev_pos = st.pos.copy()
            st.mirror = desc.mirror
            if desc.score >= 0:
                e.score = desc.score
            if desc.item_drop >= 0:
                e.item_drop = desc.item_drop
        st.life = st.max_life = desc.life if desc is not None and desc.life >= 0 else 1
        self.enemies.append(e)
        ctx.events.emit(EnemySpawned(e.enemy_id, st.pos.x, st.pos.y, sub_id))
        return e

    # ---- 每帧(LOGIC 槽): ECL 步进 + 回调 ----
    def step(self, ctx: FrameContext) -> None:
        """逐敌推进 ECL; 脚本结束/击坠 deactivate 的当帧摘除。"""
        for e in self.enemies:
            if e.active:
                e.step(self, ctx)
        self.enemies = [e for e in self.enemies if e.active]

    # ---- 体术(COLLISION 槽, 在 damage_pass 前) ----
    def contact_pass(self, player: PlayerField, ctx: FrameContext) -> None:
        """敌人体术判定 (EnemyManager.cpp:754-775 → CheckBulletPlayerCollision :576-595)。

        门槛 (C++:754-756): !hasNoCollision && !invisibleOnBomb && canDie
        && hasContactHitbox。判定盒 = hitboxSize/1.5 vs 玩家判定盒; 带 trail 的
        敌人追加历史位置节点 (j=1..trailInterval 步进 6, trailFlags&2 时盒随 j
        线性收缩)。命中按 CalcKillboxCollision==1 语义(含玩家无敌中的纯相交):
        canDie && !isBoss && !isProjectile → life -= 10 (撞空由 damage_pass
        的 life<=0 分支统一结算, 同 C++:941 在门槛外)。isProjectile 敌人另有
        擦弹 (timer%6==0, 盒=hitboxSize/0.7, C++:582-587); 普通敌人无擦弹。
        """
        for e in self.enemies:
            if not e.active or e.has_no_collision or e.invisible_on_bomb:
                continue
            if not (e.can_die and e.has_contact_hitbox):
                continue
            fw, fh = e.hitbox_size.x, e.hitbox_size.y
            x, y = e.pos2
            boxes: list[tuple[Vec2, float, float]] = [(Vec2(x, y), fw, fh)]
            if e.trail[0] != 0:
                interval = e.trail[2]
                for j in range(1, interval, 6):
                    if j >= len(e.trail_history):
                        break
                    cw, ch = fw, fh
                    if e.trail[0] & 2:  # 收缩: hitboxSize - hitboxSize*j/interval
                        cw = fw - fw * j / interval
                        ch = fh - fh * j / interval
                    hp = e.trail_history[j]
                    boxes.append((Vec2(hp.x, hp.y), cw, ch))
            for center, w, h in boxes:
                if e.is_projectile and e.machine.enemy.timer % 6 == 0:
                    player.graze_check(center, w / 0.7, h / 0.7, ctx)
                if not player.contact_hit(center, w / 1.5, h / 1.5, ctx):
                    continue
                if e.can_die and not e.is_boss and not e.is_projectile:
                    e.machine.enemy.life -= 10

    # ---- 自机弹伤害 + 击坠结算(COLLISION 槽) ----
    def damage_pass(
        self, shots: ShotField, bombs: BombField | None, ctx: FrameContext
    ) -> None:
        """自机弹 vs 敌人全管线 (EnemyManager.cpp:754-938 OnUpdate 伤害段)。

        每个 can_die/is_hittable 敌人: 主盒 + graze 盒(graze_size.x>0)各算一次
        自机弹伤害(有副作用: 命中弹进爆炸态); bomb 中且 bomb 伤害盒命中 graze
        盒时丢弃 graze 额外伤 (EnemyManager.cpp:783-790 collisionOut!=0 分支)。
        每个敌人(无论是否受伤)都参与索敌, 但仅当部分位于版面内 (IsInBounds)。
        life<=0 && canDie 的击杀分支在门槛外 (C++:941), 体术撞掉的血也在此结算。

        【与 C++ 的已知偏差: 分路径结算】 沿用旧实现: 子弹走这里 (bomb_damage=
        False → 符卡中恒 /7 分支), bomb 盒走 bomb_damage_pass (/2.5 分支),
        各自 int 截断; C++ 是合成一笔再按 collisionOut 统一缩放
        (Player.cpp:825-938 → EnemyManager.cpp:849-868)。同帧混合命中与 C++
        差一个截断级, 旧 test_th07_enemies.py 有钉住该语义的用例。
        """
        bomb_in_use = bombs is not None and bombs.is_in_use
        for e in self.enemies:
            if not e.active:
                continue
            st = e.machine.enemy
            if (
                not (e.has_no_collision or e.invisible_on_bomb)
                and e.can_die
                and e.is_hittable
            ):
                x, y = e.pos2
                pos = Vec2(x, y)
                full = (e.hitbox_size.x, e.hitbox_size.y)
                damage = shots.calc_damage_to_enemy(
                    pos, full, ctx, bomb_active=bomb_in_use
                )
                graze_damage = 0
                if e.graze_size.x > 0.0:
                    gfull = (e.graze_size.x, e.graze_size.y)
                    graze_damage = shots.calc_damage_to_enemy(
                        pos, gfull, ctx, bomb_active=bomb_in_use
                    )
                    if (
                        bomb_in_use
                        and bombs is not None
                        and bombs.hits(
                            pos, Vec2(e.graze_size.x / 2, e.graze_size.y / 2)
                        )
                    ):
                        # collisionOut!=0: grazeDamage 整体丢弃
                        graze_damage = 0
                r = self._settle(e, damage, graze_damage=graze_damage)
                st.life -= r.damage
                if r.raw_damage > 0:
                    ctx.events.emit(
                        EnemyDamaged(
                            e.enemy_id, x, y, r.raw_damage, r.damage, bool(e.is_boss)
                        )
                    )
                if _target_in_bounds(pos, full):
                    self.targeting.update(pos, self.player_pos, is_boss=bool(e.is_boss))
            if st.life <= 0 and e.can_die:
                e.kill(self, ctx)
        self.enemies = [e for e in self.enemies if e.active]

    # ---- bomb 伤害盒(LOGIC 槽, ECL 步进前; 旧 impl._apply_bomb_boxes 帧内作用点) ----
    def bomb_damage_pass(self, bombs: BombField, ctx: FrameContext) -> None:
        """Bomb 伤害盒对敌结算: lifetime 即每帧伤害, 门控 canDie && isHittable。"""
        if not bombs.is_in_use:
            return
        for e in self.enemies:
            if not e.active:
                continue
            if not (e.can_die and e.is_hittable):
                # 无门控时不可击目标也会掉血 (EnemyManager.cpp:776-779)
                continue
            x, y = e.pos2
            dmg = bombs.damage_to(
                Vec2(x, y), Vec2(e.hitbox_size.x / 2, e.hitbox_size.y / 2)
            )
            if not dmg:
                continue
            r = self._settle(e, int(dmg), bomb_damage=True)
            e.machine.enemy.life -= r.damage
            ctx.events.emit(
                EnemyDamaged(
                    e.enemy_id,
                    x,
                    y,
                    r.raw_damage,
                    r.damage,
                    bool(e.is_boss),
                    by_bomb=True,
                )
            )

    def _settle(
        self, e: Enemy, damage: int, *, bomb_damage: bool = False, graze_damage: int = 0
    ) -> DamageSettle:
        """结算一笔记账: graze 追加 → 作品修正 hook → 封顶/缩放。"""
        if graze_damage > 0 and not bomb_damage:
            damage = int(damage + graze_damage / 2.5)
        if damage <= 0:
            return DamageSettle()
        damage = self.adjust_damage(e, damage, bomb_damage=bomb_damage)
        return settle_damage(
            damage,
            is_boss=bool(e.is_boss),
            bomb_damage=bomb_damage,
            spellcard_active=self.spellcard_active,
            used_bomb=self.spellcard_used_bomb,
            invincibility_timer=e.machine.enemy.invincibility_timer,
            can_be_damaged=bool(e.can_be_damaged),
        )

    def adjust_damage(self, e: Enemy, damage: int, *, bomb_damage: bool) -> int:
        """作品级伤害修正 hook(70 封顶前调用; 基类恒等, 作品层覆盖)。"""
        return damage

    def enemy_callback_reset(self, e: Enemy) -> None:
        """敌人回调切换时的作品侧复位 hook(弹幕参数等; 基类无操作)。"""

    # ---- 批量操作 ----
    def clear_field(self, source: Enemy, ctx: FrameContext) -> None:
        """回调切阶段时的清场 (C: 非 boss 敌 life=0, !canDie 的跑死亡回调)。"""
        for e in self.enemies:
            if e is source or not e.active or e.is_boss:
                continue
            e.machine.enemy.life = 0
            if not e.can_die and e.death_callback_sub >= 0:
                e._run_death_callback(self)

    def clear(self) -> None:
        """清空。"""
        self.enemies.clear()

    def alive(self) -> list[Enemy]:
        """在场敌人列表(内部容器, 别改)。"""
        return self.enemies

    def __len__(self) -> int:
        return len(self.enemies)
