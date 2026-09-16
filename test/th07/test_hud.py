"""th07 对局 HUD 贴图化测试: snapshot 产出 + 后端 powerbar 渐变。

合成世界(无数据)断言快照键/坐标/个数; needs_data 全链走真 compose_world。
"""

from __future__ import annotations

from touhou.engine import FrameContext, InputFrame, Rng, SceneSnapshot, SpriteDraw
from touhou.engine.input import Button
from touhou.engine.score_store import make_highscore_record
from touhou.games.th07.player import BorderState
from touhou.games.th07.snapshot import Th07SnapshotSystem
from touhou.games.th07.view import PygameBackend
from touhou.games.th07.world import Th07World

from .conftest import needs_data


def _produce(world: Th07World) -> FrameContext:
    """跑一帧生产 system, 返回带快照的帧上下文。"""
    ctx = FrameContext(Rng(0), InputFrame())
    Th07SnapshotSystem().tick(world, ctx)
    return ctx


def _row(sprites, y: float):
    """取某一 y 行的 sprite(按 x 排序)。"""
    return sorted((s for s in sprites if s.y == y), key=lambda s: s.x)


def test_chrome_layout() -> None:
    """边框/面板 tile + 横条 + 标签的个数与落位 (Gui.cpp:1458-1499)。"""
    ctx = _produce(Th07World())
    sprs = ctx.draw.sprites
    tiles = [s for s in sprs if s.image == "front.anm:12"]
    # 左列 15 + 右栏 7x14 (无数据缺省 32x32 → 中心锚 = 左上+16)
    assert len(tiles) == 15 + 7 * 14
    assert (16.0, 16.0) in [(t.x, t.y) for t in tiles]  # 左列首 tile
    assert (432.0, 32.0) in [(t.x, t.y) for t in tiles]  # 右栏首 tile (416,16)
    strips = [s for s in sprs if s.image == "front.anm:13"]
    # 顶/底 5x2 + 底栏 3 + 下划线 7 + fps 位 1 (缺省 128x16 → 中心 +64/+8)
    assert len(strips) == 10 + 3 + 7 + 1
    assert (560.0, 72.0) in [(s.x, s.y) for s in strips]  # Score 行下划线 (496,64)
    labels = {s.image: (s.x, s.y) for s in sprs if s.image.startswith("front.anm:")}
    assert labels["front.anm:2"] == (464.0, 56.0)  # HiScore 标签 (432,48)
    assert labels["front.anm:8"] == (464.0, 184.0)  # Point 标签 (432,176)
    # 右下 logo 两件
    assert labels["front.anm:0"] == (544.0, 336.0)  # 竖排 logo (480,208) 128x256
    assert labels["front.anm:1"] == (512.0, 376.0)  # 英文 logo (448,336) 128x80


def test_score_rows() -> None:
    """HiScore/Score: 8 位 + 续关尾数; HiScore 随显示分反超换尾数。"""
    w = Th07World(character=0, difficulty=1)
    w.globals.gui_score = 12345678
    w.th07.num_retries = 2
    ctx = _produce(w)
    # Score 行 y=64 (中心 72): '1'..'8' → sprite 48..55 + 尾数 '2' → 49
    row = [s for s in _row(ctx.draw.sprites, 72.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in row] == [
        f"ascii.anm:{47 + d}" for d in (1, 2, 3, 4, 5, 6, 7, 8)
    ] + ["ascii.anm:49"]
    assert row[0].x == 504.0 and row[-1].x == 616.0  # (496,64) 起, 尾数 +112
    # HiScore 行 y=48: 空榜底线 100000 < gui_score → 反超, 尾数 = numRetries
    hi = [s for s in _row(ctx.draw.sprites, 56.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in hi] == [s.image for s in row]
    # 榜分高于显示分: 保持榜分 + 榜续关数
    w2 = Th07World(character=0, difficulty=1)
    w2.globals.gui_score = 5000
    w2.store.insert_score(make_highscore_record(77777777, 0, 1, 6, num_retries=4))
    hi2 = [
        s
        for s in _row(_produce(w2).draw.sprites, 56.0)
        if s.image.startswith("ascii.anm:")
    ]
    assert [s.image for s in hi2] == [
        f"ascii.anm:{47 + d}" for d in (7, 7, 7, 7, 7, 7, 7, 7)
    ] + [
        "ascii.anm:51"  # '4'
    ]


def test_score_nine_digits() -> None:
    """≥1 亿: 9 位横缩 0.9, 尾数 x=+113.4 (Gui.cpp:1560-1570)。"""
    w = Th07World()
    w.globals.gui_score = 150000000
    ctx = _produce(w)
    row = [s for s in _row(ctx.draw.sprites, 72.0) if s.image.startswith("ascii.anm:")]
    assert len(row) == 10
    assert all(s.scale_x == 0.9 for s in row[:9])
    assert row[9].scale_x == 1.0 and abs(row[9].x - (496.0 + 113.4 + 8.0)) < 0.01


def test_star_icons() -> None:
    """残机/炸弹 = 星级图标逐个画 (Gui.cpp:1516-1536)。"""
    w = Th07World()
    w.th07.lives = 3.0
    w.th07.bombs = 2.0
    sprs = _produce(w).draw.sprites
    life = [s for s in sprs if s.image == "front.anm:10"]
    bomb = [s for s in sprs if s.image == "front.anm:11"]
    assert [(s.x, s.y) for s in life] == [
        (504.0, 104.0),
        (520.0, 104.0),
        (536.0, 104.0),
    ]
    assert [(s.x, s.y) for s in bomb] == [(504.0, 120.0), (520.0, 120.0)]
    w.th07.lives = 0.0
    assert not [s for s in _produce(w).draw.sprites if s.image == "front.anm:10"]


def test_power_row() -> None:
    """Power: 渐变条 + 数值; 满 128 显 MAX (Gui.cpp:1613-1661)。"""
    w = Th07World()
    w.th07.power = 64.0
    sprs = _produce(w).draw.sprites
    bar = [s for s in sprs if s.image == "misc:powerbar"]
    assert len(bar) == 1
    assert (bar[0].x, bar[0].y, bar[0].scale_x, bar[0].scale_y) == (
        496.0,
        144.0,
        64.0,
        16.0,
    )
    digits = [s for s in _row(sprs, 152.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in digits] == ["ascii.anm:53", "ascii.anm:51"]  # "64"
    w.th07.power = 128.0
    sprs = _produce(w).draw.sprites
    bar = [s for s in sprs if s.image == "misc:powerbar"]
    assert bar[0].scale_x == 128.0
    digits = [s for s in _row(sprs, 152.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in digits] == [
        "ascii.anm:76",  # M
        "ascii.anm:64",  # A
        "ascii.anm:87",  # X
    ]
    w.th07.power = 0.0
    sprs = _produce(w).draw.sprites
    assert not [s for s in sprs if s.image == "misc:powerbar"]
    assert [s.image for s in _row(sprs, 152.0) if s.image.startswith("ascii.anm:")] == [
        "ascii.anm:47"  # "0"
    ]


def test_graze_point_rows() -> None:
    """Graze 数值行 + Point "n/need" 计数行 (Gui.cpp:1598-1611)。"""
    w = Th07World()
    w.th07.graze_in_total = 123
    w.th07.point_items_collected_for_extend = 7
    w.th07.next_needed_point_items_for_extend = 50
    sprs = _produce(w).draw.sprites
    graze = [s for s in _row(sprs, 168.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in graze] == [f"ascii.anm:{47 + d}" for d in (1, 2, 3)]
    point = [s for s in _row(sprs, 184.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in point] == [
        "ascii.anm:54",  # 7
        "ascii.anm:46",  # /
        "ascii.anm:52",  # 5
        "ascii.anm:47",  # 0
    ]


def test_cherry_gauge_no_cherryplus_row() -> None:
    """右栏无 CherryPlus 文本行; 樱点走底部计量条 (AsciiManager.cpp:1140-1295)。

    无数据兜底落点 = 脚本 4 interrupt 1 终值左上 (32,449)(实测 ascii.anm)。
    """
    w = Th07World()
    w.th07.cherry_start = 10000
    w.th07.cherry = 10000 + 20350
    w.th07.cherry_max = 10000 + 200000
    w.th07.cherry_plus = 10000 + 12345
    ctx = _produce(w)
    texts = [t.text for t in ctx.draw.texts]
    assert not any("Cherry" in t or "CHERRY" in t for t in texts)
    sprs = ctx.draw.sprites
    gauge = [s for s in sprs if s.image == "ascii.anm:142"]
    assert len(gauge) == 1 and (gauge[0].x, gauge[0].y) == (
        80.0,
        457.0,
    )  # 左上 (32,449)
    lower = [s for s in _row(sprs, 460.0) if s.image.startswith("ascii.anm:")]
    # "20350" 前导零省略从第二槽 (85,460) 起 + "200000" 从 6 槽步进完 +9 起
    assert [s.image for s in lower[:5]] == [
        f"ascii.anm:{132 + d}" for d in (2, 0, 3, 5, 0)
    ]
    assert lower[0].x == 85.0
    assert [s.image for s in lower[5:]] == [
        f"ascii.anm:{132 + d}" for d in (2, 0, 0, 0, 0, 0)
    ]
    assert lower[5].x == 78.0 + 6 * 7.0 + 9.0
    upper = [s for s in _row(sprs, 451.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in upper] == [f"ascii.anm:{132 + d}" for d in (1, 2, 3, 4, 5)]
    assert upper[0].x == 85.0 and upper[0].color == (192, 128, 176)


def test_cherry_gauge_border_states() -> None:
    """结界 READY/ACTIVE: 上行变色放大步进 10; ACTIVE 加呼吸标记。"""
    w = Th07World()
    w.th07.cherry_start = 0
    w.th07.cherry_plus = 50000
    w.player.border.has_border = BorderState.READY
    sprs = _produce(w).draw.sprites
    upper = [s for s in _row(sprs, 449.0) if s.image.startswith("ascii.anm:13")]
    assert upper and all(s.scale_x == 1.41 for s in upper)
    assert upper[0].x == 87.0  # +2 偏移
    assert not [s for s in sprs if s.image == "ascii.anm:143"]
    w.player.border.has_border = BorderState.ACTIVE
    sprs = _produce(w).draw.sprites
    mark = [s for s in sprs if s.image == "ascii.anm:143"]
    assert len(mark) == 1 and (mark[0].x, mark[0].y) == (56.0, 457.0)


def test_powerbar_backend_pixels() -> None:
    """后端 misc:powerbar: 左缘 alpha 224 → 右缘 128 的渐变 (Gui.cpp:1634-1635)。"""
    b = PygameBackend(None)
    b.open(title="test", scale=1)
    try:
        b._render(
            SceneSnapshot(
                0,
                sprites=(
                    SpriteDraw(
                        "misc:powerbar",
                        496.0,
                        144.0,
                        z=101.0,
                        scale_x=100.0,
                        scale_y=16.0,
                    ),
                ),
            )
        )
        frame = b._frame_surf
        assert frame is not None
        # SRCALPHA 条 src-over 到底色上: 左缘亮(近 224,224,255), 右缘暗(近底色)
        left = frame.get_at((497, 152))[:3]
        right = frame.get_at((595, 152))[:3]
        assert left[0] > 180 and left[2] > 200
        assert right[0] < left[0] and right[0] > 60
    finally:
        b.close()


@needs_data
def test_real_data_hud_full_chain() -> None:
    """真机一面: HUD 贴图键解出真 surface(非兜底块), 后端整帧渲染不炸。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=1)
    b = PygameBackend(w.archive)
    try:
        assert b.bank.get("front.anm:12").get_size() == (32, 32)
        assert b.bank.get("front.anm:2").get_size() == (64, 16)
        assert b.bank.get("ascii.anm:142").get_size() == (96, 16)
        assert b.bank.get("ascii.anm:132").get_size() == (8, 12)
        b.open(title="test", scale=1)
        snap = None
        for _ in range(600):
            snap = w.tick(InputFrame())
        assert snap is not None
        b._render(snap)
        frame = b._frame_surf
        assert frame is not None
        # 右栏面板已被 tile 贴图覆盖(不再是窗外区底色)
        assert frame.get_at((500, 100))[:3] != (8, 12, 30)
        # 游戏区外左列 tile 带贴图
        assert frame.get_at((16, 240))[:3] != (8, 12, 30)
    finally:
        b.close()


# ---- boss 血条 (Gui.cpp:1225-1292 + :1835-1917) ----


def _tick_bar(world: Th07World, sys: Th07SnapshotSystem, frames: int) -> FrameContext:
    """跑 n 帧生产, 返回末帧上下文。"""
    ctx = FrameContext(Rng(0), InputFrame())
    for _ in range(frames):
        ctx = FrameContext(Rng(0), InputFrame())
        sys.tick(world, ctx)
    return ctx


def test_boss_bar_shows_without_spellcard() -> None:
    """道中 boss(无符卡, is_active=0)也亮血条: SET_BOSS 建档即画 (EclManager.cpp:1509-1517)。"""
    from touhou.engine.boss import BossField

    w = Th07World(character=0, difficulty=1)
    w.boss = BossField()
    w.boss.set_life(1000.0)
    sys = Th07SnapshotSystem()
    ctx = _tick_bar(w, sys, 200)  # alpha 淡入 64 帧 + 条长缓动 100 帧
    bars = [s for s in ctx.draw.sprites if s.image == "misc:bossbar"]
    assert bars, "道中 boss 无符卡也必须出血条"
    assert bars[0].scale_x > 300.0  # 满血缓动到位(满宽 320)
    assert bars[0].alpha == 255
    assert bars[0].x == 64.0 and bars[0].y == 19.0  # Gui.cpp:1838-1842
    # 扣血 → 条长缩(0.02/帧)
    w.boss.life = 500.0
    ctx = _tick_bar(w, sys, 200)
    bar = next(s for s in ctx.draw.sprites if s.image == "misc:bossbar")
    assert 100.0 < bar.scale_x < 200.0
    # boss 退场 → 淡出后不再画
    w.boss = None
    ctx = _tick_bar(w, sys, 100)
    assert not [s for s in ctx.draw.sprites if s.image == "misc:bossbar"]


def test_boss_bar_hidden_during_dialog() -> None:
    """对话中整段不画血条 (Gui.cpp:1835 msg.currentMsgIdx<0 门控)。"""
    from types import SimpleNamespace

    from touhou.engine.boss import BossField

    w = Th07World(character=0, difficulty=1)
    w.boss = BossField()
    w.boss.set_life(1000.0)
    sys = Th07SnapshotSystem()
    _tick_bar(w, sys, 200)
    w.msg_vm = SimpleNamespace(active=True)  # type: ignore[assignment]  # duck: 只读 .active
    ctx = _tick_bar(w, sys, 1)
    assert not [s for s in ctx.draw.sprites if s.image == "misc:bossbar"]


def test_boss_bar_spellcard_timer() -> None:
    """符卡剩余秒: 两位数 + 分档色 (Gui.cpp:1889-1916, g_SpellcardTimeColors)。"""
    from touhou.engine.boss import BossField

    w = Th07World(character=0, difficulty=1)
    w.boss = BossField()
    w.boss.set_life(1000.0)
    w.boss.is_active = 1
    w.boss.spellcard_idx = 0
    w.boss.seconds_remaining = 42
    sys = Th07SnapshotSystem()
    ctx = _tick_bar(w, sys, 200)
    timer = [t for t in ctx.draw.texts if t.text == "42"]
    assert timer and timer[0].x == 384.0 and timer[0].y == 16.0
    assert timer[0].rgba[:3] == (0xA0, 0xD0, 0xFF)  # >=20 档
    # 非符卡(道中)不出秒数
    w.boss.is_active = 0
    w.boss.spellcard_idx = -1
    ctx = _tick_bar(w, sys, 1)
    assert not [t for t in ctx.draw.texts if t.text == "42"]


@needs_data
def test_midboss_bar_real_stage() -> None:
    """真一面道中(琪露诺, 无符卡): 血条 + front.anm 框贴图都出 (B#6 回归钉)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=1)
    w.th07.lives = 99
    seen_bar = seen_frame = False
    for _ in range(3200):
        snap = w.tick(InputFrame(held=frozenset({Button.SHOT})))
        if w.boss is not None and not w.boss.is_active:  # 道中(无符卡)区间
            for s in snap.sprites:
                if s.image == "misc:bossbar" and s.scale_x > 0:
                    seen_bar = True
                if s.image == "front.anm:9":  # 血条框 (vms0[11] 稳态 sprite)
                    seen_frame = True
    assert seen_bar and seen_frame


def test_boss_bar_spellcard_segments() -> None:
    """血条符卡彩段: host.boss_health 槽 → 分界彩色段 (Gui.cpp:1847-1869)。"""
    from types import SimpleNamespace

    from touhou.engine.boss import BossField

    w = Th07World(character=0, difficulty=1)
    w.boss = BossField()
    w.boss.set_life(2000.0)
    # 两段: 0..1000 红 / 1000..2000 粉 (ecldata3 sub37 形态)
    w.host = SimpleNamespace(  # type: ignore[assignment]
        boss_health=[(0, 1000, 0xFF8080), (1000, 2000, 0xFFA0A0)] + [(0, 0, 0)] * 6,
        boss_life_markers=0,
    )
    sys = Th07SnapshotSystem()
    ctx = _tick_bar(w, sys, 200)  # 满血缓动到位
    segs = sorted(
        (s for s in ctx.draw.sprites if s.image == "misc:bossseg"), key=lambda s: s.x
    )
    assert len(segs) == 2
    assert segs[0].x == 64.0 and segs[0].scale_x == 160.0  # 0..0.5
    assert segs[0].color == (255, 128, 128)
    assert segs[1].x == 224.0 and segs[1].scale_x == 160.0  # 0.5..1.0
    assert segs[1].color == (255, 160, 160)
    # 血扣到第一段以下: 条长缓过段起点后段消失 (:1854)
    w.boss.life = 0.0
    ctx = _tick_bar(w, sys, 200)
    assert not [s for s in ctx.draw.sprites if s.image == "misc:bossseg"]


# ---- boss 底部▼位置标记 (EnemyManager.cpp:1064-1089) + 计量条滑入淡出 ----


def _ascii_bank():
    """真 ascii.anm 的 AnmBank(needs_data 用)。"""
    from touhou.engine import open_archive
    from touhou.engine.anm import build_bank
    from touhou.schemas.anm import parse_anm
    from touhou.schemas.archive import load_entry

    from .conftest import DATA

    archive = open_archive(DATA)
    return build_bank(
        parse_anm(load_entry(archive, "ascii.anm"), version=2, flat_layout=False),
        flat_layout=False,
    )


def test_boss_marker_silent_without_bank() -> None:
    """无 anm 数据: ▼标记静默(同其它贴图件)。"""
    from touhou.games.th07.hud import BossMarker

    w = Th07World()
    m = BossMarker(Rng(0))
    out: list = []
    m.step(w, out, None)
    assert not out


@needs_data
def test_boss_marker_tracks_boss() -> None:
    """▼标记: SET_BOSS 边沿淡入, 跟 boss 横坐标 y=472; 距自机近变淡; 受击帧蓝化。"""
    from types import SimpleNamespace

    from touhou.games.th07.hud import BossMarker
    from touhou.utils.math import Vec2

    bank = _ascii_bank()
    w = Th07World()
    m = BossMarker(Rng(0))
    out: list = []
    m.step(w, out, bank)
    assert not out  # 无 boss 不画
    e = SimpleNamespace(active=True, has_no_collision=0, pos2=(200.0, 100.0))
    w.boss_enemy = e  # type: ignore[assignment]
    w.player.pos = Vec2(300.0, 400.0)
    m.step(w, (out := []), bank)
    assert len(out) == 1
    mark = out[0]
    assert mark.image == "ascii.anm:144"  # 脚本 6 稳态 sprite
    assert (mark.x, mark.y) == (232.0, 472.0)  # boss.x+32, y=472 (:1076-1082)
    assert mark.alpha == 176  # 距自机 ≥64px (:345)
    # 距自机 64px 内变淡 (:336-343)
    w.player.pos = Vec2(190.0, 400.0)
    m.step(w, (out := []), bank)
    assert out[0].alpha == int(10.0 * 128.0 / 64.0 + 48.0)
    # 受击帧蓝化 (:347-352)
    w.frame_boss_damage = True
    m.step(w, (out := []), bank)
    assert out[0].color == (64, 64, 255) and out[0].alpha == 128
    w.frame_boss_damage = False
    # hasNoCollision → 不画 (:1077-1081)
    e.has_no_collision = 1
    m.step(w, (out := []), bank)
    assert not out
    e.has_no_collision = 0
    m.step(w, (out := []), bank)  # 恢复在场, 标记回 boss 横坐标
    assert out
    # 撤档 → interrupt 2 淡出, 30 帧内仍画在最后位置, 之后消隐
    w.boss_enemy = None
    m.step(w, (out := []), bank)
    assert out and out[0].x == 232.0
    for _ in range(40):
        m.step(w, (out := []), bank)
    assert not out


@needs_data
def test_cherry_gauge_slide_and_fade() -> None:
    """计量条: 开局 interrupt 1 左缘滑入; 自机压底左淡出 64, 离开淡回 (Player.cpp:2196-2221)。"""
    from touhou.games.th07.hud import CherryGauge
    from touhou.utils.math import Vec2

    bank = _ascii_bank()
    w = Th07World()
    w.player.pos = Vec2(192.0, 384.0)
    gauge = CherryGauge(Rng(0))
    out: list = []
    gauge.step(w, out, bank)
    g = [s for s in out if s.image == "ascii.anm:142"]
    assert g and g[0].x < 80.0  # 滑入途中(左上 x<32)
    for _ in range(30):  # 滑入 15 帧到 (32,449)
        gauge.step(w, (out := []), bank)
    g = [s for s in out if s.image == "ascii.anm:142"]
    assert g and (g[0].x, g[0].y) == (80.0, 457.0) and g[0].alpha == 255
    # 自机压到底部左侧 → interrupt 2 淡出至 64
    w.player.pos = Vec2(100.0, 420.0)
    for _ in range(30):
        gauge.step(w, (out := []), bank)
    g = [s for s in out if s.image == "ascii.anm:142"]
    assert g and g[0].alpha == 64
    digits = [s for s in out if s.image.startswith("ascii.anm:13")]
    assert digits and all(s.alpha == 64 for s in digits)  # 数字随条淡隐
    # 离开 → interrupt 3 淡回 255
    w.player.pos = Vec2(300.0, 420.0)
    for _ in range(30):
        gauge.step(w, (out := []), bank)
    g = [s for s in out if s.image == "ascii.anm:142"]
    assert g and g[0].alpha == 255


def test_cherry_gauge_fade_state_without_bank() -> None:
    """淡出状态机无数据也记账(兜底静态绘制不淡出, Player.cpp:2201-2221)。"""
    from touhou.games.th07.hud import CherryGauge
    from touhou.utils.math import Vec2

    w = Th07World()
    w.player.pos = Vec2(100.0, 420.0)  # 底部左侧
    gauge = CherryGauge(Rng(0))
    out: list = []
    gauge.step(w, out, None)
    assert gauge._fade == 2
    assert [s for s in out if s.image == "ascii.anm:142"]  # 兜底仍画
    w.player.pos = Vec2(300.0, 420.0)
    gauge.step(w, [], None)
    assert gauge._fade == 3
    w.player.pos = Vec2(300.0, 300.0)  # y<400 且 fade==2 才回 3; 已是 3 不动
    gauge.step(w, [], None)
    assert gauge._fade == 3
