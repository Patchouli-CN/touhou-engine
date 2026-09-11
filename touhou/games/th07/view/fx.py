"""对局特效层总装: 订阅 sim 事件流驱动演出 VM, 每帧产出额外绘制项合进快照。

特效是 view 层演出, 不进 sim: 本层经 world.subscribers 收事件(结算之后),
ANM VM 用独立 Rng(0) 不碰 sim rng; 贴图键与快照生产同一链式 id 空间
(``<anm文件名>:<链式全局sprite id>``), 后端照常寻址。触发映射:
EnemyDied→爆散 (EnemyManager.cpp:951-1020), PlayerDied→大爆 (Player.cpp:1233-1234),
SpellcardBegan→宣言横幅+魔法阵+符卡环 (EclManager.cpp:658-708),
BombStarted→bomb 演出 (BombData.cpp 各 *Draw + Gui.cpp:343-362),
MsgMusicChange→标题 BGM 行 (Gui.cpp:959-973), 收点/BONUS 弹字经
world.frame_popups/frame_bonus_score 透出消费, 对话窗(立绘+底图+文字+介绍名)每帧
采 world.msg_vm 透出状态 (Gui.cpp:848-898/1115-1185)。

无 anm 数据(archive None)时全层静默, 与快照的语义键兜底同理。
"""

from __future__ import annotations

from ....engine import SpriteDraw, TextDraw
from ....engine.anm import AnmBank, build_bank
from ....engine.bomb import BombEnded, BombStarted
from ....engine.boss import SpellcardBegan, SpellcardEnded, SpellcardFailed
from ....engine.enemies import EnemyDied
from ....engine.events import Event
from ....engine.msg import MsgMusicChange
from ....engine.player import PlayerDied
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import load_entry
from ..world import Th07World
from .bombfx import BombFx
from .dialog import DialogBox, DialogPortraits
from .effects import FxParticles
from .popups import BonusBanners, ScorePopups, StageTitle, StatusBanner
from .spellcard import _FACE_ANM, _SC_BG_VMS, MagicCircle, SpellcardBanner, SpellRing


class GameFx:
    """一局对局的特效层: 事件订阅 + 每帧 step 产出 (sprites, texts)。"""

    def __init__(self, world: Th07World, *, anm_version: int = 2) -> None:
        self._world = world
        self._anm_version = anm_version
        self._rng = Rng(0)
        self._banks: dict[str, AnmBank | None] = {}
        self._preloaded_stage = -1
        self.particles = FxParticles()
        self.bombfx = BombFx(self._rng)
        self.dialog = DialogPortraits(self._rng)
        self.dialog_box = DialogBox(self._rng)
        self.banner = SpellcardBanner(self._rng)
        self.circle = MagicCircle(self._rng)
        self.ring = SpellRing(self._rng)
        self.popups = ScorePopups()
        self.status = StatusBanner()
        self.bonuses = BonusBanners()
        self.title = StageTitle(self._rng)
        world.subscribers.append(self._on_event)

    # ---- anm 数据(惰性; 缺资源 → None → 该件静默) ----
    def _bank(self, name: str) -> AnmBank | None:
        if name in self._banks:
            return self._banks[name]
        bank: AnmBank | None = None
        archive = self._world.archive
        if archive is not None:
            try:
                anm = parse_anm(
                    load_entry(archive, name),
                    version=self._anm_version,
                    flat_layout=False,
                )
                bank = build_bank(anm, flat_layout=False)
            except (KeyError, ValueError):
                bank = None
        self._banks[name] = bank
        return bank

    def _preload_stage(self, stage_no: int) -> None:
        """按关预载特效贴图包(懒加载会在符卡宣言当帧解压 lzss 卡顿)。"""
        # C++ 在关卡装载时 LoadAnms (EffectManager.cpp:861-940/Gui.cpp:521-648)
        if stage_no == self._preloaded_stage:
            return
        self._preloaded_stage = stage_no
        w = self._world
        names = ["etama.anm", "ascii.anm", "text.anm", f"std{stage_no}txt.anm"]
        names.append(_FACE_ANM[w.character // 2])
        names.append(f"face_{stage_no:02d}_00.anm")
        names.append(f"player0{w.character // 2}.anm")  # bomb 机体视觉
        names += [name for name, _ in _SC_BG_VMS.get(stage_no, ())]
        for name in names:
            self._bank(name)

    # ---- 事件 → 触发 ----
    def _on_event(self, ev: Event) -> None:
        w = self._world
        if isinstance(ev, EnemyDied):
            self._enemy_death_fx(ev)
        elif isinstance(ev, PlayerDied):
            # 玩家死亡: 大爆风 ×1 + 爆散 ×16 (Player.cpp:1233-1234)
            bank = self._bank("etama.anm")
            self.particles.spawn(bank, 12, ev.x, ev.y, 1, 0xFF4040FF)
            self.particles.spawn(bank, 6, ev.x, ev.y, 16)
        elif isinstance(ev, SpellcardBegan):
            self.banner.begin(w, self._bank)
            self.circle.begin(self._bank, w.stage_no)
            self.ring.begin(self._bank("etama.anm"), ev.time_limit)
        elif isinstance(ev, SpellcardEnded):
            self.banner.end()
            self.circle.end()
            self.ring.end()
            if ev.captured:
                self.bonuses.on_spellcard_captured(ev.score)
        elif isinstance(ev, SpellcardFailed):
            self.banner.end()
            self.circle.end()
            self.ring.end()
        elif isinstance(ev, MsgMusicChange):
            self.title.on_music(self._bank, ev.music_idx)
        elif isinstance(ev, BombStarted):
            self.bombfx.begin(w, focus=ev.focus, bank_of=self._bank)
        elif isinstance(ev, BombEnded):
            self.bombfx.end()

    def _enemy_death_fx(self, ev: EnemyDied) -> None:
        """敌击坠爆散 (EnemyManager.cpp:959-1019): deathAnm1 + deathAnm2+4。"""
        w = self._world
        death_anm = (0, 0, 0)
        if w.host is not None:
            for e in w.enemies.enemies:
                if e.enemy_id == ev.enemy_id:
                    ex = w.host.extras.get(id(e.machine))
                    if ex is not None:
                        death_anm = ex.death_anm
                    break
        bank = self._bank("etama.anm")
        # 道具爆皮段 (:981-998): itemDrop>=0 ×3; 随机表每 3 杀 ×6
        extra = 0
        if ev.item_drop >= 0:
            extra = 3
        elif ev.item_drop == -1 and (w.rand_spawn_idx - 1) % 3 == 0:
            extra = 6
        if extra:
            self.particles.spawn(bank, death_anm[1] + 4, ev.x, ev.y, extra)
        if death_anm[0] < 0:
            return
        if ev.is_boss:
            # boss 击坠: deathAnm1 ×3 (:961-963) + 通用段 ×1 + 爆皮 ×4 (:1018-1019)
            self.particles.spawn(bank, death_anm[0], ev.x, ev.y, 3)
        self.particles.spawn(bank, death_anm[0], ev.x, ev.y, 1)
        self.particles.spawn(bank, death_anm[1] + 4, ev.x, ev.y, 4)

    # ---- 每帧 ----
    def step(self) -> tuple[list[SpriteDraw], list[TextDraw]]:
        """推进全部演出 VM 一帧, 返回本帧额外绘制项(合进对局快照)。"""
        w = self._world
        self._preload_stage(w.stage_no)
        self.title.sync_stage(self._bank, w.stage_no)
        self.popups.feed(w)
        boss_pos: tuple[float, float] | None = None
        if w.boss_enemy is not None:
            boss_pos = w.boss_enemy.pos2
        sprites: list[SpriteDraw] = []
        texts: list[TextDraw] = []
        sprites += self.circle.step()
        sprites += self.particles.step()
        sprites += self.ring.step(boss_pos)
        sp, tx = self.banner.step(w)
        sprites += sp
        texts += tx
        sp, tx = self.bombfx.step(w, self.particles)
        sprites += sp
        texts += tx
        sprites += self.dialog.step(w, self._bank)
        sp, tx = self.dialog_box.step(w, self._bank)
        sprites += sp
        texts += tx
        sprites += self.title.step()
        sprites += self.popups.step((w.player.pos.x, w.player.pos.y))
        sprites += self.status.step(w)
        sprites += self.bonuses.step(w)
        return sprites, texts
