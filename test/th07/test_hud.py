"""th07 对局 HUD 贴图化测试: snapshot 产出 + 后端 powerbar 渐变。

合成世界(无数据)断言快照键/坐标/个数; needs_data 全链走真 compose_world。
"""

from __future__ import annotations

from touhou.engine import FrameContext, InputFrame, Rng, SceneSnapshot, SpriteDraw
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
    """右栏无 CherryPlus 文本行; 樱点走底部计量条 (AsciiManager.cpp:1140-1295)。"""
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
        472.0,
    )  # 左上 (32,464)
    lower = [s for s in _row(sprs, 475.0) if s.image.startswith("ascii.anm:")]
    # "20350" 前导零省略从第二槽 (85,475) 起 + "200000" 从 6 槽步进完 +9 起
    assert [s.image for s in lower[:5]] == [
        f"ascii.anm:{132 + d}" for d in (2, 0, 3, 5, 0)
    ]
    assert lower[0].x == 85.0
    assert [s.image for s in lower[5:]] == [
        f"ascii.anm:{132 + d}" for d in (2, 0, 0, 0, 0, 0)
    ]
    assert lower[5].x == 78.0 + 6 * 7.0 + 9.0
    upper = [s for s in _row(sprs, 466.0) if s.image.startswith("ascii.anm:")]
    assert [s.image for s in upper] == [f"ascii.anm:{132 + d}" for d in (1, 2, 3, 4, 5)]
    assert upper[0].x == 85.0 and upper[0].color == (192, 128, 176)


def test_cherry_gauge_border_states() -> None:
    """结界 READY/ACTIVE: 上行变色放大步进 10; ACTIVE 加呼吸标记。"""
    w = Th07World()
    w.th07.cherry_start = 0
    w.th07.cherry_plus = 50000
    w.player.border.has_border = BorderState.READY
    sprs = _produce(w).draw.sprites
    upper = [s for s in _row(sprs, 464.0) if s.image.startswith("ascii.anm:13")]
    assert upper and all(s.scale_x == 1.41 for s in upper)
    assert upper[0].x == 87.0  # +2 偏移
    assert not [s for s in sprs if s.image == "ascii.anm:143"]
    w.player.border.has_border = BorderState.ACTIVE
    sprs = _produce(w).draw.sprites
    mark = [s for s in sprs if s.image == "ascii.anm:143"]
    assert len(mark) == 1 and (mark[0].x, mark[0].y) == (56.0, 472.0)


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
