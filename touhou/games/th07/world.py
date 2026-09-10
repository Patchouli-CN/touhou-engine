"""th07 的对局世界: engine field 组合 + 帧管线 + ECL/MSG 接线 + 事件结算入口。

帧序对齐 old/touhou/games/th07/world.py 的 tick(748-1008): 同步 → bomb(触发/
推进/清弹/伤害盒) → 时间轴 → msg → 敌 ECL → 结界 → 自机 → boss → 显示分追赶
(LOGIC); 自机弹/敌弹/道具/激光(MOVEMENT); 体术 → 自机弹伤害 → 敌弹判定 →
结界清弹圆 → 收集 → 激光判定(COLLISION)。对话/结算/换关的作品语义在 msg.py。
"""

from __future__ import annotations

import msgspec

from ...engine import (
    BombClearSystem,
    BombDamageSystem,
    BossField,
    BulletCollisionSystem,
    BulletField,
    BulletMovementSystem,
    Button,
    EnemyShotSystem,
    FrameContext,
    GameAssembly,
    GlobalsField,
    GlobalsSystem,
    InputFrame,
    ItemCollectSystem,
    ItemMovementSystem,
    LaserCollisionSystem,
    LaserField,
    LaserMovementSystem,
    MsgExecutor,
    Pipeline,
    PlayerState,
    PlayerSystem,
    ResourcePaths,
    SceneSnapshot,
    ShotField,
    ShotMovementSystem,
    Slot,
    System,
    World,
    tick_frame,
)
from ...engine.bomb import BOMB_RESPAWN_PENALTY, ClearBox
from ...engine.ecl import EclMachine, TimelineRunner
from ...engine.enemies import Enemy
from ...engine.events import Event, EventHandler
from ...engine.items import STATE_ATTRACT
from ...engine.rng import Rng
from ...engine.score_store import ScoreStore
from ...schemas.archive import Archive, load_entry, open_archive
from ...schemas.ending import EndingFile
from ...schemas.msg import parse_msg
from ...schemas.shot_data import parse_sht
from ...utils.math import Vec2
from . import result as result_flow
from . import settle
from .bomb import (
    BOMB_SUBRANK_PENALTY,
    CHAR_MARISA_B,
    CHAR_SAKUYA_A,
    CHAR_SAKUYA_B,
    EVENT_REMOVE_ALL_ITEMS,
    EVENT_STOP_BULLET_MOVEMENT,
    Th07BombContext,
    Th07BombField,
)
from .data import BULLET_TYPE_SPECS, SPELLCARD_SCORE
from .ecl_host import Th07EclHost
from .ecl_table import parse_ecl
from .ecl_timeline import TL_HANDLERS
from .enemies import Th07EnemyField
from .globals import Th07Globals
from .items import ItemKind, Th07ItemField
from .msg import StageResultPanel, Th07MsgSystem, advance_stage
from .player import BORDER_BREAK_INVULN, BorderState, OptionMachine, Th07PlayerField
from .shot_cbs import SAKUYA_HOMING_WINDOW, Th07ShotHooks
from .snapshot import Th07SnapshotSystem

#: 回放确定性: 显式 seed 时 ECL rng 用派生值(出处 old/touhou/games/th07/world.py:190)
_DEFAULT_SEED = 0x5EED


class Th07World(World):
    """一面 th07 对局的全部状态: engine field 们 + 作品计数 + ECL 接线。"""

    character: int = 0
    difficulty: int = 1
    stage_no: int = 1
    # ---- engine field ----
    player: Th07PlayerField = msgspec.field(default_factory=Th07PlayerField)
    shots: ShotField = msgspec.field(default_factory=ShotField)
    bullets: BulletField = msgspec.field(default_factory=BulletField)
    lasers: LaserField = msgspec.field(default_factory=LaserField)
    items: Th07ItemField = msgspec.field(default_factory=Th07ItemField)
    enemies: Th07EnemyField = msgspec.field(default_factory=Th07EnemyField)
    globals: GlobalsField = msgspec.field(default_factory=GlobalsField)
    bomb: Th07BombField = msgspec.field(default_factory=Th07BombField)
    bomb_ctx: Th07BombContext = msgspec.field(
        default_factory=lambda: Th07BombContext(player_pos=Vec2(0.0, 0.0))
    )
    # ---- 作品状态 ----
    th07: Th07Globals = msgspec.field(default_factory=Th07Globals)
    options: OptionMachine = msgspec.field(default_factory=OptionMachine)
    shot_hooks: Th07ShotHooks = msgspec.field(
        default_factory=lambda: Th07ShotHooks(options=OptionMachine())
    )
    boss: BossField | None = None
    boss_enemy: Enemy | None = None
    # ---- ECL 接线(compose_world 装载; None = 无 ECL 数据) ----
    host: Th07EclHost | None = None
    timelines: list[TimelineRunner] = msgspec.field(default_factory=list)
    # ---- MSG 接线(compose_world 装载; None = 无 msg 数据, 不停轴) ----
    msg_vm: MsgExecutor | None = None
    stage_results: StageResultPanel | None = None  # 结算面板数据(view 消费)
    pending_next_level: bool = False  # NEXT_LEVEL 登记, 次帧帧首换关
    msg_active: bool = False  # 帧首对话门控快照(HasCurrentMsgIdx)
    # ---- 换关资源(compose_world 注入; advance_stage 装新关脚本用) ----
    archive: Archive | None = None
    resources: ResourcePaths | None = None
    # ---- 驱动 ----
    pipeline: Pipeline = msgspec.field(default_factory=Pipeline)
    rng: Rng = msgspec.field(default_factory=Rng)
    ctx: FrameContext | None = None  # 本帧上下文(tick 写入; 宿主/结算回本帧事件口)
    subscribers: list[EventHandler] = msgspec.field(default_factory=list)
    # ---- 作品参数(.sht 抄录, compose_world 注入) ----
    initial_bombs: float = 2.0
    cherry_penalty_multiplier: float = 0.0
    # ---- 账本 ----
    game_over: bool = False
    # ---- 结局/总结算/续关(result_flow 驱动; 数据透出, view 消费) ----
    ending: EndingFile | None = None  # 6 面通关的结局数据(播放器在 engine.ending)
    cleared: bool = False
    result: dict | None = None  # 总结算数据(通关/GameOver 后填)
    store: ScoreStore = msgspec.field(default_factory=ScoreStore)
    max_retries: int = 3  # 续关上限(累计游戏时长 <7h→3/<14h→4/否则5)
    initial_lives: int = 3  # 续关回残基数(与开局同值)
    point_items_prev_stages: int = 0  # 已过关面的点道具累计(结算用)
    catk_idx: int | None = None  # 当前 ECL 符卡的全局编号(catk 入账)
    result_cache: dict | None = None
    rand_spawn_idx: int = 0  # C randomItemSpawnIdx(itemDrop==-1 每 3 杀掉 1)
    rand_table_idx: int = 0  # C randomItemTableIdx
    death_pos: Vec2 | None = None
    border_boxes: list[ClearBox] = msgspec.field(default_factory=list)
    frame_sounds: list[int] = msgspec.field(default_factory=list)
    frame_shakes: list[tuple[int, int, int]] = msgspec.field(default_factory=list)
    last_enemy_hit: Vec2 = Vec2(-999.0, -999.0)  # 索敌回写(追踪炸弹目标)
    spellcard_began_frame: int = -1  # 本张符卡宣言帧(超时误判守卫)

    # ---- 驱动 ----
    def tick(self, input: InputFrame | None = None) -> SceneSnapshot:
        """推进一帧: (次帧帧首换关)→ 建帧上下文 →(结算订阅)→ 管线 → 帧末事件投递。"""
        if self.pending_next_level:
            # NEXT_LEVEL → 换关(curState=3 → GameManager 重建); 事件在帧末
            # flush 登记, 次帧帧首切关, 避免 tick 半途换世界
            self.pending_next_level = False
            advance_stage(self)
        ctx = FrameContext(self.rng, input)
        self.ctx = ctx
        ctx.events.subscribe(self._settle)  # 结算先于外部消费方
        for sub in self.subscribers:
            ctx.events.subscribe(sub)
        self.frame_sounds.clear()
        self.frame_shakes.clear()
        if self.game_over:
            # 无残机死亡(C++ 进 retry 菜单): 可续关则画面冻结, 等 view 选择
            # (continue_play/finalize_game_over); 不可续关(Extra·Phantasm/
            # 次数用尽)同 C++ 直接进结算
            if self.result is None and not result_flow.continue_available(self):
                self.result = result_flow.final_result(self, cleared=False)
            snapshot = ctx.draw.build(self.frame)
            ctx.events.flush()
            return snapshot
        if self.ending is not None or self.cleared:
            # 结局显示中(view 看完调 finish_ending)/已通关进结算: 画面冻结
            snapshot = ctx.draw.build(self.frame)
            ctx.events.flush()
            return snapshot
        snapshot = tick_frame(self, self.pipeline, ctx)
        # 结算在 flush 中回产的事件(SpellcardFailed/ScoreChanged 等)再投递,
        # 有界轮次防级联回环
        for _ in range(4):
            if not ctx.events.has_pending:
                break
            ctx.events.flush()
        return snapshot

    def _settle(self, ev: Event) -> None:
        settle.settle(self, ev)

    # ---- 作品语义小件 ----
    def spellcard_active(self) -> bool:
        """符卡进行中(旧 world._spellcard_active)。"""
        b = self.boss
        return b is not None and bool(b.is_active) and b.spellcard_idx >= 0

    def add_score(self, code: int) -> None:
        """入账代码值分数(tick 期间帧上下文必在)。"""
        assert self.ctx is not None
        self.globals.add_score(code, self.ctx)

    def add_cherry_plus(self, x: int) -> None:
        """CherryPlus 入账; 满樱(cherryStart+50000) → 结界 READY。"""
        # 出处 old/touhou/games/th07/world.py:617
        if x > 0 and self.th07.add_cherry_plus(x):
            self.player.border.ready_border()

    # ---- 结界(宿主/自机 hook 与结界 system 共用) ----
    def _break_border(self) -> None:
        """BreakBorder: 中弹/死亡保命破 —— 清弹圆 + 无敌 + 捕获失败。"""
        # 出处 old/touhou/games/th07/world.py:1509 (Player.cpp:2148-2182)
        player = self.player
        player.border.break_border()
        self.border_boxes.append(
            ClearBox(
                player.pos, Vec2(0.0, 32.0), 50, ItemKind.CHERRY_SMALL, growth=16.0
            )
        )
        self.th07.cherry_plus = self.th07.cherry_start
        player.state = PlayerState.INVULNERABLE
        player.invulnerability_timer = max(
            player.invulnerability_timer, BORDER_BREAK_INVULN
        )
        if self.boss is not None:
            self.boss.mark_death()  # 结界破裂 → 捕获失败 (Player.cpp:2175-2176)
        # 结界破发声 (Player.cpp:2191-2192; 音效号 7=se_tan00 33=se_bonus)
        self.frame_sounds.append(7)
        self.frame_sounds.append(33)

    # ---- ECL 宿主接线(回调在帧内触发, ctx 必在) ----
    def _on_set_boss(self, idx: int, m: EclMachine | None) -> None:
        """SET_BOSS: 建/销 BossField(血条/符卡记账)。"""
        # 出处 old/touhou/games/th07/world.py:388
        if m is None:
            if self.boss is not None and self.boss.boss_id == idx:
                if self.boss.is_active:
                    assert self.ctx is not None
                    self.boss.end_spellcard(self.ctx)
                self.boss = None
                self.boss_enemy = None
            return
        assert self.host is not None
        boss = BossField(boss_id=idx, spellcard_scores=SPELLCARD_SCORE)
        boss.set_life(max(m.enemy.life, 1))
        self.boss = boss
        self.boss_enemy = self.host.machine_enemy.get(id(m))

    def _on_begin_spellcard(
        self, m: EclMachine, gui_id: int, idx: int, name: str
    ) -> None:
        """BeginSpellcard: boss 兜底建档 + 开卡(超时限取 ECL 计时, 兜底 60 秒)。"""
        # 出处 old/touhou/games/th07/world.py:414
        host = self.host
        assert host is not None and self.ctx is not None
        ex = host.extras_of(m)
        if self.boss is None or self.boss_enemy is not host.machine_enemy.get(id(m)):
            self._on_set_boss(ex.boss_id if ex.boss_id >= 0 else 0, m)
        boss = self.boss
        assert boss is not None
        boss.spellcard_face = gui_id
        boss.is_survival_spellcard = bool(ex.is_survival_spellcard)
        e = host.enemy_of(m)
        timeout = e.timer_callback_threshold if e.timer_callback_threshold > 0 else 3600
        boss.set_life(max(m.enemy.life, 1))
        self.spellcard_began_frame = self.frame
        boss.begin_spellcard(
            self.ctx,
            min(idx, len(SPELLCARD_SCORE) - 1),
            timeout,
            timeout_sub=max(e.timer_callback_sub, 0),
        )
        # catk: attempts[shot]/[合计槽] ++ (EclManager.cpp:709-744)
        self.catk_idx = idx
        self.store.record_spellcard_attempt(idx, name, self.character)

    def _on_end_spellcard(self, m: EclMachine) -> None:
        """EndSpellcard: 是当前 boss 的卡则收尾(产 SpellcardEnded)。"""
        host = self.host
        assert host is not None and self.ctx is not None
        if self.boss is not None and self.boss_enemy is host.machine_enemy.get(id(m)):
            self.boss.end_spellcard(self.ctx)


# ---- 管线 system(作品侧槽位件; engine 件落位见 compose_world) ----


class Th07SyncSystem(System[Th07World]):
    """LOGIC 槽头: 每帧把世界状态同步给宿主与各 field(旧 frame_update + 世界层赋值段)。"""

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        host = world.host
        assert host is not None
        player = world.player
        g = world.th07
        # 帧首对话门控(Gui::HasCurrentMsgIdx): 本帧射击/炸弹以此为准,
        # msg 系统在其后步进(当帧新读的对话下帧才门控, 同旧 world.py:787)
        world.msg_active = (
            world.msg_vm is not None and world.msg_vm.has_current_msg_idx()
        )
        player.dialog_active = world.msg_active
        # 宿主快照(出处 old/touhou/games/th07/ecl_host.py:136 frame_update)
        host.ctx = ctx
        host.player_pos.set(player.pos.x, player.pos.y, 0.0)
        host.difficulty = world.difficulty
        host.rank = g.rank
        host.power = g.power
        host.shottype = world.character
        spell = world.spellcard_active()
        host.spellcard_active = spell
        # 敌人场(冻结 = 自机非 ALIVE; bomb 期间自机被强制 INVULNERABLE 等价,
        # 触发当帧由 Th07BombSystem 补同步, 出处 old world.py:381)
        enemies = world.enemies
        enemies.frozen = player.state != PlayerState.ALIVE
        enemies.spellcard_active = spell
        enemies.spellcard_used_bomb = (
            bool(world.boss.used_bomb) if world.boss else False
        )
        enemies.player_pos = player.pos
        # 追踪炸弹目标: 索敌重置前留住上帧结果 (旧 world.py:908-910 回写)
        world.last_enemy_hit = enemies.targeting.position_of_last_enemy_hit
        # exotic 弹回调状态口: homing/咲夜索敌目标(同上, 上帧扫描结果)
        world.shot_hooks.position_of_last_enemy_hit = (
            enemies.targeting.position_of_last_enemy_hit
        )
        world.shot_hooks.sakuya_target_position = enemies.targeting.homing_target
        enemies.targeting.reset()  # 索敌状态每帧重置 (Player::UpdateUI)
        enemies.damage_timers.clear()
        # 敌弹/激光判定门控(出处 old world.py:914-927 的玩家状态门控)
        world.bullets.player_pos = player.pos
        world.bullets.graze_enabled = player.state not in (
            PlayerState.DEAD,
            PlayerState.SPAWNING,
        )
        world.bullets.hit_enabled = player.state == PlayerState.ALIVE
        world.lasers.player_pos = player.pos
        world.lasers.graze_enabled = world.bullets.graze_enabled
        world.lasers.hit_enabled = world.bullets.hit_enabled
        # 道具场
        items = world.items
        items.player_pos = player.pos
        items.player_alive = player.alive
        items.player_spawning = player.state == PlayerState.SPAWNING
        items.power = g.power
        items.border_active = player.border.active
        # 自机弹场(player_pos/focus/firing/state 由 PlayerSystem 同步)
        world.shots.power = g.power
        world.shots.options = world.options.step(
            player.pos, player.velocity, focus=player.focus, firing=player.firing
        )
        # focus 切态的持续弹槽清理(旧 _update_shots 首段, 弹场步进前)
        world.shot_hooks.clear_stale_slots(world.shots)


class Th07TimelineSystem(System[Th07World]):
    """LOGIC 槽: 推进全部 ECL 时间轴(刷怪/msg/等 boss 停轴), 挂在敌 ECL 前。"""

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        for tl in world.timelines:
            tl.step()


class Th07EnemyEclSystem(System[Th07World]):
    """LOGIC 槽: 敌 ECL 步进 + 帧末宿主账本清理(销账/boss 槽联动)。"""

    def __init__(self, field: Th07EnemyField, host: Th07EclHost) -> None:
        self.field = field
        self.host = host

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        self.field.step(ctx)
        self.host.sweep()


class Th07BorderSystem(System[Th07World]):
    """LOGIC 槽: 结界每帧(READY 激活/死亡保命破/倒计时/自然破入账), 挂在自机前。"""

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        # 出处 old/touhou/games/th07/world.py:1466 (_tick_border)
        player = world.player
        border = player.border
        g = world.th07
        if border.has_border == BorderState.READY:
            if player.state == PlayerState.DEAD and player.respawn_timer != 0:
                world._break_border()  # 死亡中结界保命 (ActivateBorder DEAD 分支)
            elif player.state == PlayerState.ALIVE:
                border.activate_border()
        plus, res = border.tick(
            cherry=g.cherry, cherry_start=g.cherry_start, cherry_max=g.cherry_max
        )
        if res is not None:
            # 自然破: +10000 上限/樱点, 得分 (cherry-cherryStart)*10
            g.cherry = res.cherry
            g.cherry_max = res.cherry_max
            g.cherry_plus = res.cherry_plus
            world.add_score(res.score)
            player.state = PlayerState.INVULNERABLE
            player.invulnerability_timer = max(
                player.invulnerability_timer, res.invulnerability_timer
            )
        elif border.active:
            g.cherry_plus = plus  # 结界中 cherryPlus 随剩余时间衰减的显示值


class Th07BombSystem(System[Th07World]):
    """LOGIC 槽: bomb 键(结界破分支) → try_start → 每帧推进/樱点 drain/事件消费。

    帧内位置对齐旧 world.py:803-842(ECL 步进前)。触发入账同步做: 决死窗状态
    翻转/respawn+6/首帧无敌须先于 PlayerSystem(帧末 flush 的 BombStarted 订阅
    太晚), 订阅侧只挂音效(settle.py)。
    """

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        player = world.player
        bomb = world.bomb
        bctx = world.bomb_ctx
        # bctx 同步 (旧 _bomb_ctx, old world.py:1317-1329)
        bctx.player_pos = player.pos
        bctx.difficulty = world.difficulty
        bctx.cherry = world.th07.cherry
        bctx.cherry_start = world.th07.cherry_start
        bctx.last_enemy_hit = world.last_enemy_hit
        # bomb/结界键 (Player.cpp:1686-1692 + UpdateBorderAndBombState 触发分支;
        # 对话中不可 bomb, Player.cpp:1722 以 !HasCurrentMsgIdx 为前提)
        if (
            Button.BOMB in ctx.input.pressed
            and not bomb.is_in_use
            and not world.msg_active
        ):
            if player.border.has_border != BorderState.NONE:
                world._break_border()  # 有结界时按 bomb 键 = 主动破
                world.items.remove_all_items()  # Player.cpp:1691
            else:
                self._try_start(world, ctx)
        # 每帧推进 (UpdateBombProjectiles 无条件 → drain → 机体 calc)
        was_in_use = bomb.is_in_use
        bomb.tick(ctx, bctx)
        if was_in_use and bomb.invulnerable:
            # bomb 期间 playerState=INVULNERABLE, 结束后剩余无敌继续倒数
            # (旧 world.py:824-831, BUGS.md 增量#2)
            player.state = PlayerState.INVULNERABLE
        if was_in_use:
            if bomb.drain_applied:
                world.th07.subtract_cherry_drain(bomb.drain_applied)
            for ev in bomb.events:
                if ev == EVENT_REMOVE_ALL_ITEMS:
                    world.items.remove_all_items()
                elif ev == EVENT_STOP_BULLET_MOVEMENT:
                    world.bullets.stop_bullet_movement()  # 咲夜B 停时
                # EVENT_END_PLAYER_SPELLCARD 是 GUI 横幅事件, 逻辑侧无影响
            bomb.events.clear()
            world.frame_shakes.extend(bomb.shakes)
            bomb.shakes.clear()

    def _try_start(self, world: Th07World, ctx: FrameContext) -> None:
        """触发 + 同步入账 (旧 _try_bomb 成功分支, old world.py:1331-1384)。"""
        player = world.player
        bomb = world.bomb
        g = world.th07
        started = bomb.try_start(
            ctx,
            world.bomb_ctx,
            # 本帧输入(PlayerSystem 尚未 push, 旧世界层在帧首已喂当帧 keys)
            focus=Button.FOCUS in ctx.input.held,
            bombs_remaining=g.bombs,
            respawn_timer=player.respawn_timer,
            border_invulnerability_time=player.border.border_invulnerability_time,
            bomb_pressed=True,
        )
        if not started:
            return
        g.bombs_used += 1
        g.bombs -= 1
        g.decrease_subrank(BOMB_SUBRANK_PENALTY)
        player.respawn_timer = min(
            player.respawn_timer + BOMB_RESPAWN_PENALTY, player.initial_respawn_timer
        )
        if world.boss is not None:
            world.boss.mark_bombed()  # 用弹 → 本张符卡不算捕获
        # 触发当帧补同步 enemy 门控(旧在 host step 调用点取值; SyncSystem 跑在触发前)
        world.enemies.frozen = True
        world.enemies.spellcard_used_bomb = (
            bool(world.boss.used_bomb) if world.boss else False
        )
        # 炸弹首帧无敌由机体 calc 设定 (BombData *Calc timer==0 分支)
        player.invulnerability_timer = max(
            player.invulnerability_timer, bomb.invulnerability_timer
        )
        if player.state == PlayerState.DEAD:
            # 决死B: 死亡窗口内 bomb 代替丢残机, 本帧起死亡倒计时即停
            # (Player.cpp:1764-1779 UpdateDeath 只在 DEAD 时跑)
            player.state = PlayerState.INVULNERABLE


class Th07PlayerSystem(PlayerSystem):
    """LOGIC 槽: 自机步进; bomb 中输入向量乘 move_speed_multiplier (旧 world.py:854-863)。"""

    def __init__(
        self,
        field: Th07PlayerField,
        shots: ShotField,
        bomb: Th07BombField,
        *,
        suppress_bomb_fire: bool = False,
    ) -> None:
        super().__init__(field, shots)
        self.bomb = bomb
        self.suppress_bomb_fire = suppress_bomb_fire  # MarisaB: 炸弹中不发射

    def tick(self, world: World, ctx: FrameContext) -> None:
        f = self.field  # world 用不上: bomb/field/shots 均构造注入
        if self.read_input:
            f.push_frame(ctx.input)
        if f.dialog_active:
            # 对话门控: 可移动不可射击 (Player.cpp:1616 以 !HasCurrentMsgIdx 为前提)
            f.firing = False
        mult = self.bomb.move_speed_multiplier if self.bomb.is_in_use else 1.0
        orig = f._move
        if mult != 1.0:
            # C++ 是炸弹中对最终移速乘倍率; 线性缩放入输入向量与之等价
            f._move = orig * mult
        f.step(ctx)
        f._move = orig
        if self.shots is not None:
            s = self.shots
            s.player_pos = f.pos
            s.focus = f.focus
            s.firing = f.firing
            s.player_state = int(f.state)
            s.dialog_active = f.dialog_active
            # 持续弹压计时/伤害 /3 与机体发射抑制 (旧 world.py:854 + is_marisa_b)
            s.bomb_active = self.bomb.is_in_use
            s.fire_suppressed = self.bomb.is_in_use and self.suppress_bomb_fire


class Th07ContactSystem(System[Th07World]):
    """COLLISION 槽: 体术判定; bomb 中整段跳过(CheckBombGraze 短路, Player.cpp:1009-1012)。"""

    def __init__(self, field: Th07EnemyField, player: Th07PlayerField) -> None:
        self.field = field
        self.player = player

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        if not world.bomb.is_in_use:
            self.field.contact_pass(self.player, ctx)


class Th07BossSystem(System[Th07World]):
    """LOGIC 槽: boss 血条同步 + 符卡计时/捕获分衰减 + 退场兜底收尾。"""

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        # 出处 old/touhou/games/th07/world.py:1659 (_tick_boss_ecl)
        boss = world.boss
        if boss is None:
            return
        e = world.boss_enemy
        if e is not None:
            st = e.machine.enemy
            boss.life = max(float(st.life), 0.0)
            boss.max_life = max(float(st.max_life), 1.0)
        boss.tick(ctx)
        if e is None or not e.active:
            # Boss 敌人已退场且 ECL 未自己 END_SPELLCARD 时兜底
            if boss.is_active:
                boss.end_spellcard(ctx)
            world.boss = None
            world.boss_enemy = None


class Th07BorderClearSystem(System[Th07World]):
    """COLLISION 槽: 结界破裂的清弹圆(半径 32 每帧 +16 持续 50 帧), 弹转小樱点。"""

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        # 出处 old/touhou/games/th07/world.py:1541 (_tick_border_clear_boxes)
        if not world.border_boxes:
            return
        r = world.bullets.bullet_radius * 2.0
        size = Vec2(r, r)
        keep: list[ClearBox] = []
        for box in world.border_boxes:
            box.tick()
            if not box.active:
                continue
            for b in world.bullets.alive():
                if b.spawn_state:
                    continue  # 出生态弹不吃清弹圆(CheckBombGraze 路径不到)
                if box.hits(b.pos, size):
                    world.items.spawn(b.pos, box.item_type, state=STATE_ATTRACT)
                    b.dead = True
            keep.append(box)
        world.border_boxes = keep


# ---- 组合根 ----


def compose_world(
    assembly: GameAssembly,
    *,
    character: int = 0,
    difficulty: int = 1,
    stage_no: int = 1,
    seed: int | None = None,
    store: ScoreStore | None = None,
    score_path: str | None = None,
    life_count: int | None = None,
) -> Th07World:
    """按装配拼出 th07 一关的可 tick 世界: 资源装载 + field 接线 + 管线挂载。

    store/score_path: 成绩库直接注入 > 指定文件读档 > 新建内存库
    (落盘由调用方在结算确认时负责)。
    life_count: cfg.lifeCount(0..4) → 初始残机(GameManager.cpp:532
    SetLivesRemaining); None = 默认 3 残, Extra/Phantasm 固定 2 残不受影响。
    """
    res = assembly.resources
    arc = open_archive(res.data_path, format_name=res.archive_format)
    if store is None:
        if score_path is not None:
            store = ScoreStore.load(
                score_path, spellcard_count=len(assembly.data.spellcard_scores)
            )
        else:
            store = ScoreStore(spellcard_count=len(assembly.data.spellcard_scores))
    store.record_play(character, difficulty)  # PSCR/PLST 开局计数
    # 续关上限 (MainMenu.cpp:2576-2587): 累计游戏时长折算(plst.total_frames)
    play_hours = store.plst.get("total_frames", 0) / (60 * 3600)
    max_retries = 3 if play_hours < 7 else 4 if play_hours < 14 else 5
    sht_unf, sht_foc = assembly.data.character_sht[character]
    shot_data = parse_sht(load_entry(arc, sht_unf))
    shot_data_focus = parse_sht(load_entry(arc, sht_foc))
    ecl_file = parse_ecl(load_entry(arc, res.ecl_file.format(n=stage_no)))
    # 对话系统: msg{stage}.dat (Gui::LoadMsg); 缺资源则不留 VM(不停轴)
    msg_vm: MsgExecutor | None = None
    try:
        msg_vm = MsgExecutor(
            parse_msg(load_entry(arc, res.msg_file.format(n=stage_no)))
        )
    except KeyError:
        pass

    # 回放确定性(出处 old/touhou/games/th07/world.py:190): 显式 seed 时
    # 主 rng 用 seed, ECL rng 用派生值
    main_seed = _DEFAULT_SEED if seed is None else (seed & 0xFFFF)
    ecl_seed = 0 if seed is None else ((main_seed ^ 0x3C7) & 0xFFFF)
    ecl_rng = Rng(ecl_seed)

    # ---- 作品计数(残机/樱点/rank 按难度初始化) ----
    g = Th07Globals()
    g.initialize_rank(difficulty)
    # cherryMax/初始樱点按难度 (GameManager::AddedCallback 新开局分支 switch)
    g.cherry_max = g.cherry_start + (
        200000
        if difficulty <= 1
        else 250000
        if difficulty == 2
        else 300000
        if difficulty == 3
        else 400000
    )
    if difficulty == 4:
        g.cherry = g.cherry_start + 200000
    elif difficulty == 5:
        g.cherry = g.cherry_start + 300000
    if difficulty >= 4:
        # C: difficulty>=4 → lifeCount=2; 点道具奖残门槛 200
        g.lives = 2.0
        g.next_needed_point_items_for_extend = 200
    elif life_count is not None:
        g.lives = float(life_count + 1)  # cfg.lifeCount → 初始残机(:532)
    g.bombs = shot_data.initial_bombs
    initial_lives = (
        2 if difficulty >= 4 else life_count + 1 if life_count is not None else 3
    )

    # ---- field 装配(.sht 注入判定半径/移速/收集参数) ----
    player = Th07PlayerField(
        move_speed=shot_data.speed,
        move_speed_focus=shot_data.speed_focus,
        move_speed_diagonal=shot_data.speed_diagonal,
        move_speed_diagonal_focus=shot_data.speed_diagonal_focus,
        hitbox_radius=shot_data.hitbox_radius / 2,
        graze_radius=shot_data.grab_item_radius / 2,
        initial_respawn_timer=shot_data.initial_respawn_timer,
    )
    shots = ShotField(shot_data=shot_data, shot_data_focus=shot_data_focus)
    option_machine = OptionMachine(rotating=(character == CHAR_SAKUYA_B))  # 旋转子机
    shot_hooks = Th07ShotHooks(options=option_machine)
    shot_hooks.register(shots)  # exotic 弹回调(追踪/orb 激光/导弹等)
    bullets = BulletField(
        type_specs=BULLET_TYPE_SPECS,
        player_radius=shot_data.hitbox_radius / 2,
        graze_radius=shot_data.grab_item_radius / 2,
    )
    lasers = LaserField(player_radius=shot_data.hitbox_radius / 2)
    items = Th07ItemField(
        item_collect_speed=shot_data.item_collect_speed,
        item_collect_radius=shot_data.item_collect_radius,
        poc_y=shot_data.poc_y,
        difficulty=difficulty,
    )
    enemies = Th07EnemyField(stage=stage_no, is_reimu_a=(character == 0))
    if character in (CHAR_SAKUYA_A, CHAR_SAKUYA_B):
        # 咲夜索敌角度窗(旧 Targeting 的 is_sakuya 分支, old world.py:885)
        enemies.targeting.homing_window = SAKUYA_HOMING_WINDOW
    bomb = Th07BombField(character=character)
    bomb_ctx = Th07BombContext(player_pos=player.pos)

    # ---- ECL 宿主/时间轴 ----
    host = Th07EclHost(
        ecl_file,
        bullets=bullets,
        lasers=lasers,
        items=items,
        enemies=enemies,
        rng=ecl_rng,
    )
    enemies.host = host
    timelines = [
        TimelineRunner(tl, host, ecl_rng, TL_HANDLERS) for tl in ecl_file.timelines
    ]

    world = Th07World(
        character=character,
        difficulty=difficulty,
        stage_no=stage_no,
        player=player,
        shots=shots,
        bullets=bullets,
        lasers=lasers,
        items=items,
        enemies=enemies,
        bomb=bomb,
        bomb_ctx=bomb_ctx,
        th07=g,
        options=option_machine,
        shot_hooks=shot_hooks,
        host=host,
        timelines=timelines,
        msg_vm=msg_vm,
        archive=arc,
        resources=res,
        rng=Rng(main_seed),
        initial_bombs=shot_data.initial_bombs,
        cherry_penalty_multiplier=shot_data.cherry_penalty_multiplier,
        store=store,
        max_retries=max_retries,
        initial_lives=initial_lives,
    )
    # ---- 宿主/自机 hook 接线 ----
    host.on_sound = world.frame_sounds.append
    host.on_set_power = lambda v: setattr(world.th07, "power", float(v))
    host.on_add_cherry_plus = world.add_cherry_plus
    host.on_set_boss = world._on_set_boss
    host.on_begin_spellcard = world._on_begin_spellcard
    host.on_end_spellcard = world._on_end_spellcard
    host.msg_vm = msg_vm
    host.msg_character = character // 2  # MsgRead(arg0 + character*10)
    player.on_border_break = world._break_border

    # ---- 管线(engine 件槽位对齐旧 world.py tick 帧序) ----
    p: Pipeline = Pipeline()
    p.add(Slot.LOGIC, Th07SyncSystem())
    p.add(Slot.LOGIC, Th07BombSystem())
    p.add(Slot.LOGIC, BombClearSystem(bomb, bullets))
    p.add(Slot.LOGIC, BombDamageSystem(enemies, bomb))
    p.add(Slot.LOGIC, Th07TimelineSystem())
    p.add(Slot.LOGIC, Th07MsgSystem())
    p.add(Slot.LOGIC, Th07EnemyEclSystem(enemies, host))
    p.add(Slot.LOGIC, Th07BorderSystem())
    p.add(
        Slot.LOGIC,
        Th07PlayerSystem(
            player, shots, bomb, suppress_bomb_fire=(character == CHAR_MARISA_B)
        ),
    )
    p.add(Slot.LOGIC, Th07BossSystem())
    p.add(Slot.LOGIC, GlobalsSystem(world.globals))
    p.add(Slot.MOVEMENT, ShotMovementSystem(shots))
    p.add(Slot.MOVEMENT, BulletMovementSystem(bullets))
    p.add(Slot.MOVEMENT, ItemMovementSystem(items))
    p.add(Slot.MOVEMENT, LaserMovementSystem(lasers))
    p.add(Slot.COLLISION, Th07ContactSystem(enemies, player))
    p.add(Slot.COLLISION, EnemyShotSystem(enemies, shots, bomb))
    p.add(Slot.COLLISION, BulletCollisionSystem(bullets))
    p.add(Slot.COLLISION, Th07BorderClearSystem())
    p.add(Slot.COLLISION, ItemCollectSystem(items))
    p.add(Slot.COLLISION, LaserCollisionSystem(lasers))
    p.add(Slot.OUTPUT, Th07SnapshotSystem(anm_version=assembly.scripts.anm_version))
    world.pipeline = p
    return world
