"""敌人场测试: 伤害结算/体术/击坠死亡分支/生命周期回调/索敌。

数值权威: EnemyManager.cpp:754-943 (OnUpdate 伤害段) + Player.cpp:1003-1040;
语义移植自 old/touhou/engine/enemies.py, 关键用例改写自
old/tests/game_test/th07/test_th07_enemies.py 与 test_th07_boss.py 的
settle_damage 部分(樱点/机型修正属作品概念, 不进 engine, 故不搬)。
"""

from __future__ import annotations

from touhou.engine import (
    DamageSettle,
    EnemyDamaged,
    EnemyDespawned,
    EnemyDied,
    EnemyEscaped,
    EnemyField,
    EnemyLifeCallback,
    EnemySpawned,
    EnemyTimerCallback,
    FrameContext,
    PlayerDied,
    PlayerField,
    PlayerGrazed,
    PlayerShot,
    PlayerState,
    Rng,
    ShotField,
    settle_damage,
)
from touhou.engine.bomb import BombField, DamageBox
from touhou.engine.ecl.host import EclHost
from touhou.engine.ecl.machine import EclMachine
from touhou.engine.ecl.state import EnemySpawn, Vec3
from touhou.engine.enemies import Targeting
from touhou.schemas.ecl import EclFile, EclSub, Nop, SubEnd
from touhou.utils.math import Vec2


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


def _wait_sub(t: int = 9999) -> EclSub:
    """一个空转 sub: Nop 到点永不至, 机器一直活。"""
    return EclSub(
        0,
        (
            Nop(offset=0, time=t, skip_difficulty=0xFF),
            SubEnd(offset=12, time=0xFFFFFFFF, skip_difficulty=0xFF),
        ),
    )


def _machine(n_subs: int = 1) -> EclMachine:
    f = EclFile(0, tuple(_wait_sub() for _ in range(n_subs)), ())
    m = EclMachine(f, EclHost(), Rng(0))
    m.start(0)
    return m


def _enemy_at(field: EnemyField, ctx: FrameContext, x: float, y: float, **flags):
    e = field.spawn(_machine(), EnemySpawn(sub_id=0, x=x, y=y), ctx)
    e.anm_idx = 0  # 无贴图敌人 step 后失去碰撞; 测试给贴图
    for k, v in flags.items():
        if k == "life":
            e.machine.enemy.life = v
        else:
            setattr(e, k, v)
    return e


def _player(**kw) -> PlayerField:
    kw.setdefault("pos", Vec2(192, 400))
    return PlayerField(**kw)


# ======================================================================
# settle_damage (EnemyManager.cpp:782-890 的作品无关段)
# ======================================================================
def test_settle_cap_and_raw() -> None:
    r = settle_damage(69, is_boss=False)
    assert r == DamageSettle(69, 69)
    # 70 封顶; raw 保留封顶前值(作品算分用)
    r = settle_damage(100, is_boss=False)
    assert r.raw_damage == 100 and r.damage == 70


def test_settle_spellcard_scaling() -> None:
    # 非 bomb: max(damage/7, 1)
    assert settle_damage(70, is_boss=True, spellcard_active=True).damage == 10
    assert settle_damage(5, is_boss=True, spellcard_active=True).damage == 1
    # bomb 且 used_bomb: 先封顶 70 再 max(damage/2.5, 1)
    r = settle_damage(
        100, is_boss=True, spellcard_active=True, bomb_damage=True, used_bomb=True
    )
    assert r.damage == 28  # int(70/2.5)
    r = settle_damage(
        2, is_boss=True, spellcard_active=True, bomb_damage=True, used_bomb=True
    )
    assert r.damage == 1
    # bomb 未 used_bomb: 0
    r = settle_damage(100, is_boss=True, spellcard_active=True, bomb_damage=True)
    assert r.damage == 0


def test_settle_invincibility() -> None:
    # boss 无敌: /9; 非 boss 无敌: 0
    assert settle_damage(63, is_boss=True, invincibility_timer=10).damage == 7
    assert settle_damage(63, is_boss=False, invincibility_timer=10).damage == 0


def test_settle_graze_extra() -> None:
    # grazeSize 额外伤害: 无 bomb 时 +grazeDamage/2.5; bomb 伤害不加
    assert settle_damage(10, is_boss=False, graze_damage=25).damage == 20
    r = settle_damage(
        10,
        is_boss=True,
        bomb_damage=True,
        spellcard_active=True,
        used_bomb=True,
        graze_damage=25,
    )
    assert r.damage == 4  # int(10/2.5), 未加 graze


def test_settle_can_be_damaged_off() -> None:
    # canBeDamaged=0: 不扣血但 raw 照记(作品照算分, 同 C++ score 段在门槛外)
    r = settle_damage(50, is_boss=False, can_be_damaged=False)
    assert r.raw_damage == 50 and r.damage == 0


# ======================================================================
# 生成/生命周期
# ======================================================================
def test_spawn_applies_template_and_event() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 100, 50)
    st = e.machine.enemy
    assert st.life == st.max_life == 1  # enemyTemplate 默认
    assert e.score == 100 and e.can_die == 1 and e.has_contact_hitbox == 1
    ctx.events.flush()
    assert isinstance(got[0], EnemySpawned) and got[0].x == 100


def test_script_end_despawns_with_event() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    # 单 sub: Nop(t=0) → SubEnd: 首帧执行完即结束
    fin = EclFile(
        0,
        (
            EclSub(
                0,
                (
                    Nop(offset=0, time=0, skip_difficulty=0xFF),
                    SubEnd(offset=12, time=0, skip_difficulty=0xFF),
                ),
            ),
        ),
        (),
    )
    m = EclMachine(fin, EclHost(), Rng(0))
    m.start(0)
    e = f.spawn(m, None, ctx)
    f.step(ctx)
    assert not e.active and len(f) == 0
    ctx.events.flush()
    assert any(isinstance(ev, EnemyDespawned) for ev in got)


def test_enemy_without_anm_loses_collision() -> None:
    # EnemyManager.cpp:697-700: 未 SET_ANM 的敌人 step 后 hasNoCollision=1
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 100, 50)
    e.anm_idx = -1
    f.step(ctx)
    assert e.has_no_collision == 1


def test_freeze_keeps_timer_and_ticks_invuln() -> None:
    """冻结帧: timer 净不变, invincibilityTimer 照减。

    freeze_ecl_during_bombs + field.frozen 时整帧跳过
    (EnemyManager.cpp:658-663 → :1096-1100)。
    """
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 100, 50)
    st = e.machine.enemy
    e.freeze_ecl_during_bombs = 1
    st.invincibility_timer = 5
    st.timer = 10
    f.frozen = True
    f.step(ctx)
    assert st.timer == 10 and st.invincibility_timer == 4
    f.frozen = False
    f.step(ctx)
    assert st.timer == 11


# ======================================================================
# 体术 (contact_pass)
# ======================================================================
def test_contact_hit_kills_player_and_damages_enemy() -> None:
    """本体命中: 玩家 ALIVE → 死; 敌人(非 boss/弹) life -= 10 (C++:589-594)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 400, life=100)
    e.hitbox_size = Vec3(48, 48, 48)
    p = _player(state=PlayerState.ALIVE)
    f.contact_pass(p, ctx)
    assert p.state == PlayerState.DEAD
    assert e.machine.enemy.life == 90
    ctx.events.flush()
    assert any(isinstance(ev, PlayerDied) for ev in got)


def test_contact_hitbox_is_hitbox_div_1_5() -> None:
    """判定盒 = hitboxSize/1.5 (C++:588)。

    半宽 48/1.5/2=16, 加玩家半宽 2 → |dx|<=18 命中, 19 不中。
    """
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 192 + 18.0, 400)
    e.hitbox_size = Vec3(48, 48, 48)
    p = _player(state=PlayerState.ALIVE)
    f.contact_pass(p, ctx)
    assert p.state == PlayerState.DEAD
    f2, p2 = EnemyField(), _player(state=PlayerState.ALIVE)
    e2 = _enemy_at(f2, _ctx(), 192 + 19.0, 400)
    e2.hitbox_size = Vec3(48, 48, 48)
    f2.contact_pass(p2, _ctx())
    assert p2.state == PlayerState.ALIVE


def test_contact_exemptions() -> None:
    """豁免 (C++:754-756): hasNoCollision / hasContactHitbox=0 / invisibleOnBomb。"""
    for flag in ("has_no_collision", "has_contact_hitbox", "invisible_on_bomb"):
        ctx = _ctx()
        f = EnemyField()
        _enemy_at(f, ctx, 192, 400, **{flag: 1 if flag != "has_contact_hitbox" else 0})
        p = _player(state=PlayerState.ALIVE)
        f.contact_pass(p, ctx)
        assert p.state == PlayerState.ALIVE, flag


def test_contact_boss_and_projectile_lose_no_life() -> None:
    """命中扣血仅对 canDie && !isBoss && !isProjectile (C++:591-593)。"""
    ctx = _ctx()
    f = EnemyField()
    boss = _enemy_at(f, ctx, 192, 400, life=100, is_boss=1)
    f.contact_pass(_player(state=PlayerState.ALIVE), ctx)
    assert boss.machine.enemy.life == 100
    f2 = EnemyField()
    proj = _enemy_at(f2, _ctx(), 192, 400, life=100, is_projectile=1)
    f2.contact_pass(_player(state=PlayerState.ALIVE), _ctx())
    assert proj.machine.enemy.life == 100


def test_contact_hit_while_invulnerable_still_damages_enemy() -> None:
    """玩家无敌中相交: C++ 仍返回 1 → 玩家不死, 敌人 -10。"""
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 400, life=100)
    p = _player(state=PlayerState.INVULNERABLE)
    f.contact_pass(p, ctx)
    assert p.state == PlayerState.INVULNERABLE
    assert e.machine.enemy.life == 90


def test_contact_kill_settles_in_damage_pass() -> None:
    """体术把血撞空 → life<=0 击杀分支在门槛外 (C++:941), 由 damage_pass 结算。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 400, life=5)
    p = _player(state=PlayerState.INVULNERABLE)  # 不死, 只看敌人侧
    f.contact_pass(p, ctx)
    assert e.machine.enemy.life == -5
    f.damage_pass(ShotField(), None, ctx)
    assert not e.active and len(f) == 0
    ctx.events.flush()
    died = [ev for ev in got if isinstance(ev, EnemyDied)]
    assert died and died[0].scored and died[0].enemy_id == e.enemy_id


def test_contact_projectile_grazes_every_6_frames() -> None:
    """IsProjectile 敌人: timer%6==0 时按 hitboxSize/0.7 擦弹 (C++:582-587)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    # 不相撞(体术盒半宽 6/1.5/2+2=4)但在擦弹圈(12/0.7/2≈8.6+20+24≈52)内
    e = _enemy_at(f, ctx, 192 + 40.0, 400, is_projectile=1)
    p = _player(state=PlayerState.ALIVE)
    e.machine.enemy.timer = 5  # %6 != 0 → 不擦
    f.contact_pass(p, ctx)
    e.machine.enemy.timer = 6  # %6 == 0 → 擦
    f.contact_pass(p, ctx)
    ctx.events.flush()
    grazes = [ev for ev in got if isinstance(ev, PlayerGrazed)]
    assert len(grazes) == 1


def test_contact_trail_history_node_hits() -> None:
    """Trail 敌人: 历史节点也做体术判定 (C++:760-774, j=1..trailInterval 步进 6)。"""
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 0, -500, life=100)
    e.hitbox_size = Vec3(48, 48, 48)
    e.trail = [25, 32, 16, 1, 0]
    e.trail_history = [Vec3(-999.0, 0.0, 0.0)] * 32
    e.trail_history[1] = Vec3(192, 400, 0.0)
    p = _player(state=PlayerState.ALIVE)
    f.contact_pass(p, ctx)
    assert p.state == PlayerState.DEAD
    assert e.machine.enemy.life == 90  # trail 节点命中也扣


def test_contact_trail_node_beyond_interval_not_checked() -> None:
    """节点 j >= trailInterval 不判定 (C++:763 循环上界)。"""
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 0, -500, life=100)
    e.hitbox_size = Vec3(48, 48, 48)
    e.trail = [25, 32, 16, 1, 0]
    e.trail_history = [Vec3(-999.0, 0.0, 0.0)] * 32
    e.trail_history[17] = Vec3(192, 400, 0.0)  # j=17 >= 16
    p = _player(state=PlayerState.ALIVE)
    f.contact_pass(p, ctx)
    assert p.state == PlayerState.ALIVE


# ======================================================================
# 自机弹伤害 (damage_pass)
# ======================================================================
def _shot_at(pos: Vec2, damage: int, **kw) -> PlayerShot:
    return PlayerShot(pos=pos, damage=damage, bullet_state=1, **kw)


def test_shot_damage_and_graze_extra() -> None:
    """主盒 10 + graze 盒 25 → 10 + 25/2.5 = 20; 事件带 raw/damage。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 100, life=1000)
    e.hitbox_size = Vec3(24, 24, 24)
    e.graze_size = Vec3(80, 80, 80)
    shots = ShotField(
        pool=[
            _shot_at(Vec2(192, 100), 10),  # 只中主盒
            _shot_at(Vec2(192 + 30, 100), 25),  # 主盒外(12+3=15), graze 盒内
        ]
    )
    f.damage_pass(shots, None, ctx)
    assert e.machine.enemy.life == 980
    ctx.events.flush()
    dmg = [ev for ev in got if isinstance(ev, EnemyDamaged)]
    assert len(dmg) == 1 and dmg[0].raw_damage == 20 and dmg[0].damage == 20
    assert not dmg[0].by_bomb


def test_shot_hit_explodes_and_slowing() -> None:
    """命中弹进爆炸态(state=2)且速度/8 (Player.cpp CalcDamageToEnemy)。"""
    ctx = _ctx()
    f = EnemyField()
    _enemy_at(f, ctx, 192, 100, life=1000)
    shot = _shot_at(Vec2(192, 100), 10, velocity=Vec2(0, -8))
    f.damage_pass(ShotField(pool=[shot]), None, ctx)
    assert shot.bullet_state == 2
    assert shot.velocity == Vec2(0, -1)


def test_bomb_box_hit_skips_graze_extra() -> None:
    """Bomb 盒命中 graze 盒 (collisionOut!=0) 时跳过 graze 额外伤 (EnemyManager.cpp:783-790)。

    未命中照常追加; bomb 中自机弹已预 /3。
    """
    # bomb 盒命中 graze 盒 → 跳过 graze 追加
    ctx = _ctx()
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 100, life=1000)
    e.hitbox_size = Vec3(24, 24, 24)
    e.graze_size = Vec3(80, 80, 80)
    bombs = BombField(
        is_in_use=True,
        damage_boxes=[DamageBox(Vec2(192, 100), Vec2(200, 200), 5)],
    )
    shots = ShotField(pool=[_shot_at(Vec2(192, 100), 10), _shot_at(Vec2(222, 100), 25)])
    f.damage_pass(shots, bombs, ctx)
    # 主盒 10/3=3, graze 追加被跳 → 扣 3
    assert e.machine.enemy.life == 997
    # bomb 盒未命中 graze 盒 → 照常追加 (25/3=8 → 8/2.5=3.2 → 3+3=6)
    f2 = EnemyField()
    e2 = _enemy_at(f2, _ctx(), 192, 100, life=1000)
    e2.hitbox_size = Vec3(24, 24, 24)
    e2.graze_size = Vec3(80, 80, 80)
    bombs2 = BombField(
        is_in_use=True,
        damage_boxes=[DamageBox(Vec2(500, 100), Vec2(20, 20), 5)],
    )
    shots2 = ShotField(
        pool=[_shot_at(Vec2(192, 100), 10), _shot_at(Vec2(222, 100), 25)]
    )
    f2.damage_pass(shots2, bombs2, _ctx())
    assert e2.machine.enemy.life == 994


def test_split_settlement_bullet_vs_bomb_box() -> None:
    """钉住【分路径结算】现状: 子弹 /7 与 bomb 盒 /2.5 分路径各自截断相加。

    符卡中 used_bomb 时子弹走 /7 分支, bomb 盒走 /2.5 分支 —— 而非 C++
    合并成一笔统一缩放 (Player.cpp:825-938 → EnemyManager.cpp:849-868)。
    21+25 混合命中: 本实现 21//7 + int(25/2.5) = 3+10 = 13;
    C++ 合并为 int(46/2.5) = 18。
    """
    ctx = _ctx()
    f = EnemyField()
    f.spellcard_active = True
    f.spellcard_used_bomb = True
    e = _enemy_at(f, ctx, 192, 100, life=100000, is_boss=1)
    # 子弹路径(无 bomb 预除, 对齐旧测试钉值): 符卡中 /7
    shots = ShotField(pool=[_shot_at(Vec2(192, 100), 21)])
    f.damage_pass(shots, None, ctx)
    assert e.machine.enemy.life == 100000 - 3
    # bomb 盒路径: 符卡中 bomb_damage=True + used_bomb → /2.5
    bombs = BombField(
        is_in_use=True,
        damage_boxes=[DamageBox(Vec2(192, 100), Vec2(200, 200), 25)],
    )
    f.bomb_damage_pass(bombs, ctx)
    assert e.machine.enemy.life == 100000 - 13
    assert int((21 + 25) / 2.5) == 18  # C++ 对照值(文档用, 非实现目标)


def test_bomb_damage_pass_gates_and_events() -> None:
    """Bomb 盒伤害门控 canDie && isHittable (EnemyManager.cpp:776-779)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 100, life=100)
    bombs = BombField(
        is_in_use=True, damage_boxes=[DamageBox(Vec2(192, 100), Vec2(40, 40), 5)]
    )
    f.bomb_damage_pass(bombs, ctx)
    assert e.machine.enemy.life == 95
    assert bombs.damage_boxes[0].damage == 5  # lifetime 累计
    e2 = _enemy_at(f, ctx, 192, 100, life=100, is_hittable=0)
    f.bomb_damage_pass(bombs, ctx)
    assert e2.machine.enemy.life == 100  # 门控外不掉血
    assert e.machine.enemy.life == 90  # 门控内的照常再吃一次
    # bomb 结束后不再结算
    bombs.is_in_use = False
    f.bomb_damage_pass(bombs, ctx)
    assert e.machine.enemy.life == 90
    ctx.events.flush()
    by_bomb = [ev for ev in got if isinstance(ev, EnemyDamaged) and ev.by_bomb]
    assert len(by_bomb) == 2 and by_bomb[0].damage == 5


# ======================================================================
# 击坠死亡分支 (kill, death_type 0/1/2/3)
# ======================================================================
def _kill(e, f, ctx):
    e.machine.enemy.life = 0
    f.damage_pass(ShotField(), None, ctx)


def test_death_type0_normal_kill() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = _enemy_at(f, ctx, 192, 100, life=1)
    _kill(e, f, ctx)
    assert not e.active and len(f) == 0
    ctx.events.flush()
    died = [ev for ev in got if isinstance(ev, EnemyDied)]
    assert died and died[0].scored and died[0].score == 100


def test_death_type1_scored_keeps_running() -> None:
    """dt=1: 计分后 canDie=0 继续跑死亡 sub (C case 1 → END_BOSS → case 2)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(2), None, ctx)
    e.machine.enemy.pos = Vec3(192, 100, 0)
    e.anm_idx = 0
    e.death_type = 1
    e.death_callback_sub = 1
    _kill(e, f, ctx)
    assert e.active and e.can_die == 0 and len(f) == 1
    ctx.events.flush()
    assert any(isinstance(ev, EnemyDied) and ev.scored for ev in got)
    # 死亡回调已切 sub 1
    assert e.machine.current.sub_id == 1


def test_death_type2_phase_break_no_score() -> None:
    """dt=2: 阶段击破不计分, 保持 active, 跑死亡回调(通常 SET_LIFE 复活)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(2), None, ctx)
    e.anm_idx = 0
    e.death_type = 2
    e.death_callback_sub = 1
    _kill(e, f, ctx)
    assert e.active and len(f) == 1
    ctx.events.flush()
    died = [ev for ev in got if isinstance(ev, EnemyDied)]
    assert died and not died[0].scored


def test_death_type3_boss_escape() -> None:
    """dt=3: boss 离场, 不计分不掉落, 钉 life=1 继续跑死亡 sub。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(2), None, ctx)
    e.anm_idx = 0
    e.is_boss = 1
    e.death_type = 3
    e.death_callback_sub = 1
    _kill(e, f, ctx)
    assert e.active and e.machine.enemy.life == 1 and e.can_be_damaged == 0
    ctx.events.flush()
    assert any(isinstance(ev, EnemyEscaped) for ev in got)
    assert not [ev for ev in got if isinstance(ev, EnemyDied)]


def test_kill_event_fires_once() -> None:
    """dt=2 的敌人血不回正时每帧重进击杀分支(C 同), 但事件只产一次。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(), None, ctx)
    e.anm_idx = 0
    e.death_type = 2
    _kill(e, f, ctx)
    _kill(e, f, ctx)  # 第二帧: life 仍 <=0
    ctx.events.flush()
    assert len([ev for ev in got if isinstance(ev, EnemyDied)]) == 1


# ======================================================================
# 生命周期回调
# ======================================================================
def test_life_callback_pins_life_switches_sub_and_clears_field() -> None:
    """HandleLifeCallback: 跌破阈值 → 钉生命 + 切 sub + 清场(非 boss 敌 life=0)。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(2), None, ctx)
    e.anm_idx = 0
    e.life_callback_threshold = [50, -1, -1, -1]
    e.life_callback_sub = [1, -1, -1, -1]
    e.machine.enemy.life = 40
    mob = _enemy_at(f, ctx, 300, 100, life=80)  # 同场杂鱼
    f.step(ctx)
    assert e.machine.enemy.life == 50  # 钉住
    assert e.machine.current.sub_id == 1  # 切 sub
    assert mob.machine.enemy.life == 0  # 清场
    ctx.events.flush()
    assert any(isinstance(ev, EnemyLifeCallback) and ev.sub_id == 1 for ev in got)


def test_timer_callback_fires_event_and_pins_higher_threshold() -> None:
    """HandleTimerCallback: 超时 → 切 sub; 更高生命阈值被钉住并清掉。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = EnemyField()
    e = f.spawn(_machine(2), None, ctx)
    e.anm_idx = 0
    e.machine.enemy.life = 600
    e.life_callback_threshold = [500, -1, -1, -1]  # 低于当前生命 → 超时先钉
    e.timer_callback_threshold = 5
    e.timer_callback_sub = 1
    for _ in range(5):
        f.step(ctx)
    assert e.machine.enemy.life == 500
    assert e.life_callback_threshold[0] == -1
    assert e.timer_callback_threshold == -1
    assert e.machine.enemy.timer == 0  # 超时后计时清零
    assert e.machine.current.sub_id == 1
    ctx.events.flush()
    assert any(isinstance(ev, EnemyTimerCallback) and ev.sub_id == 1 for ev in got)


# ======================================================================
# 索敌 (Targeting)
# ======================================================================
def _damage_with(f: EnemyField, ctx: FrameContext) -> None:
    f.damage_pass(ShotField(), None, ctx)


def test_targeting_skips_out_of_bounds_enemies() -> None:
    """索敌只锁定版内敌人 (GameManager::IsInBounds 口径)。

    飞出版底的敌人不被"最靠下"准则选中; 版外敌人照常结算伤害。
    """
    ctx = _ctx()
    f = EnemyField()
    inside = _enemy_at(f, ctx, 192, 200, life=100)
    out = _enemy_at(f, ctx, 192, 600, life=100)  # 已飞出版底
    _damage_with(f, ctx)
    assert f.targeting.position_of_last_enemy_hit == Vec2(192, 200)
    assert inside.active and out.active  # 版外敌人照常参与结算(未死)


def test_targeting_skips_enemy_not_yet_entered() -> None:
    """版顶上方入场中的敌人 (y+半高<0) 不锁定: 索敌保持无效值 (-999)。"""
    ctx = _ctx()
    f = EnemyField()
    _enemy_at(f, ctx, 192, -100, life=100)
    _damage_with(f, ctx)
    assert f.targeting.position_of_last_enemy_hit == Vec2(-999.0, -999.0)
    assert not f.targeting.targeting


def test_targeting_homing_window() -> None:
    """homing_window(旧 is_sakuya 分支通用化): 窗口内的敌人才立 homing_target。"""
    t = Targeting(homing_window=(-2.0943952, -1.0471976))  # 正上方 ±30°
    player = Vec2(192, 400)
    t.update(Vec2(192, 100), player, is_boss=False)  # 正上方 → 入窗
    assert t.homing_target == Vec2(192, 100)
    t.reset()
    t.update(Vec2(300, 400), player, is_boss=False)  # 正右方 → 不入窗
    assert t.homing_target == Vec2(-999.0, -999.0)
