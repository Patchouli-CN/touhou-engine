"""结局播放状态机测试: .end 指令流解析 + EndingPlayer 逐帧语义。

数值权威来源: th07-ref Ending.cpp (ParseEndFile/OnUpdate/FadingEffect);
改写自 old/tests/game_test/th07/test_th07_ending.py。
注意: 测试数据里的参数分隔符是字面 NUL 字符; NUL 后随数字的
转义写法会被 Python 当八进制, 需写成单独的十六进制转义。
"""

from __future__ import annotations

import pytest

from touhou.engine.ending import (
    FADE_IN_BLACK,
    FADE_IN_WHITE,
    FADE_OUT_BLACK,
    FADE_OUT_WHITE,
    EndingPlayer,
)
from touhou.schemas.ending import (
    Bg,
    BgScroll,
    BgY,
    ClearFaces,
    End,
    Face,
    Fade,
    LineSpeed,
    Load,
    Music,
    MusicFade,
    Text,
    TextColor,
    Wait,
    WaitReset,
    parse_end,
)


def _end(lines: list[bytes]) -> bytes:
    return b"\n".join(lines)


# ---- parse_end: 指令全集 (Ending.cpp:242-372) ----


def test_parse_ops_full_coverage() -> None:
    data = _end(
        [
            b"@mbgm/th07_14.mid\x00",
            b"@s70\x0012\x00",
            b"@bdata/end/end00.jpg\x00",
            b"@c15790320\x00",
            b"@v147\x00",
            b"@V120\x003100\x00",
            b"@a1\x002\x003\x00",
            b"@R\x00",
            b"@w120\x00120\x00",
            b"@r1200\x004\x00",
            b"@030\x00",
            b"@160\x00",
            b"@2180\x00",
            b"@3240\x00",
            b"@M5\x00",
            "咲夜　「セリフ」".encode("cp932"),
            b"@Fdata/staff00.end\x00",
            b"@z",
        ]
    )
    f = parse_end(data)
    ops = f.ops
    assert Music("th07_14.mid") in ops
    assert LineSpeed(70, 12) in ops
    assert Bg("end00.jpg") in ops
    assert TextColor(15790320) in ops
    assert BgY(147) in ops
    assert BgScroll(120, 3100) in ops
    assert Face(1, 2, 3) in ops
    assert ClearFaces() in ops
    assert Wait(120, 120) in ops
    assert WaitReset(1200, 4) in ops
    assert Fade(FADE_OUT_BLACK, 30) in ops  # @0
    assert Fade(FADE_IN_BLACK, 60) in ops  # @1
    assert Fade(FADE_OUT_WHITE, 180) in ops  # @2
    assert Fade(FADE_IN_WHITE, 240) in ops  # @3
    assert MusicFade(5) in ops
    assert Text("咲夜　「セリフ」") in ops
    assert Load("staff00.end") in ops
    assert ops[-1] == End()
    assert f.music == "th07_14.mid"  # 首个 @m


def test_parse_segments_view() -> None:
    """分段视图: @b 切段, 文本行归段。"""
    data = (
        b"@mbgm/x.mid\x00\n@bdata/end/end00.jpg\x00\n"
        b"\x81@\x81@line1\x00\nline2\x00\n"
        b"@bdata/end/end03.jpg\x00\nline3\x00\n"
    )
    segs = parse_end(data).segments
    assert [s.bg for s in segs] == ["end00.jpg", "end03.jpg"]
    assert segs[0].lines == ("line1", "line2")
    assert segs[1].lines == ("line3",)


# ---- EndingPlayer: 文本行节奏 (ParseEndFile :386-410) ----


def test_player_text_pacing() -> None:
    """文本逐行显示, 间隔 line2Delay 帧; @s 改 (line2Delay, topLineDelay)。"""
    p = EndingPlayer(
        _end(
            [
                b"@s3\x009\x00",
                "第一行".encode("cp932"),
                "第二行".encode("cp932"),
                b"@z",
            ]
        )
    )
    p.tick()
    assert [line.text for line in p.texts] == ["第一行"]
    for _ in range(3):  # timer2=3 等待 3 帧
        p.tick()
        assert len(p.texts) == 1
    p.tick()  # 第 4 帧解析出第二行
    assert [line.text for line in p.texts] == ["第一行", "第二行"]


def test_player_advance_held_uses_top_delay() -> None:
    """按住确认键: 行间隔换 topLineDelay (:399-408)。"""
    p = EndingPlayer(
        _end(
            [
                b"@s70\x002\x00",
                "一".encode("cp932"),
                "二".encode("cp932"),
                b"@z",
            ]
        )
    )
    p.tick(advance_held=True)
    assert len(p.texts) == 1
    for _ in range(2):  # topLineDelay=2 等待 2 帧
        p.tick(advance_held=True)
        assert len(p.texts) == 1
    p.tick(advance_held=True)
    assert len(p.texts) == 2


def test_player_wait_and_skip_gate() -> None:
    """@w: minWait 耗尽后确认键按下沿可提前结束等待 (:222-234)。"""
    p = EndingPlayer(
        _end(
            [
                b"@w10\x004\x00",  # 等 10 帧, 前 4 帧不可跳
                b"@z",
            ]
        )
    )
    p.tick()  # 解析到 @w, timer2=10
    for _ in range(3):
        p.tick(advance_pressed=True)  # minWait=4 内不可跳
    assert not p.done
    p.tick(advance_pressed=True)  # minWait 耗尽 (4→0)
    p.tick(advance_pressed=True)  # 本帧确认沿 → timer2 清零
    assert not p.done  # 清零当帧仍 goto stop
    p.tick()
    assert p.done  # 次帧解析 @z


def test_player_wait_reset_clears_texts() -> None:
    """@r: 等待 timer3 帧, 归零当帧清空已显示文本行并继续解析 (:206-217)。"""
    p = EndingPlayer(
        _end(
            [
                b"@s0\x000\x00",  # 行间隔 0: 文本帧次帧即继续解析
                "一".encode("cp932"),
                b"@r5\x000\x00",
                "二".encode("cp932"),
                b"@z",
            ]
        )
    )
    p.tick()
    assert [line.text for line in p.texts] == ["一"]
    p.tick()  # 解析 @r, timer3=5
    for _ in range(4):
        p.tick()
        assert [line.text for line in p.texts] == ["一"]  # 等待中不清
    p.tick()  # timer3 归零: 清屏 + 继续解析出 "二"
    assert [line.text for line in p.texts] == ["二"]


# ---- 淡入淡出 (FadingEffect :99-165) ----


def test_player_fade_out_black() -> None:
    """@0: 黑幕淡出, alpha 255→0, 完成后无覆盖。"""
    p = EndingPlayer(_end([b"@010\x00", b"@w600\x00600\x00", b"@z"]))
    p.tick()  # 解析 @0 (fade_type=1, t=0), 停在 @w
    ov = p.fade_overlay()
    assert ov is not None and ov[:3] == (0, 0, 0)
    a0 = ov[3]
    p.tick()
    ov2 = p.fade_overlay()
    assert ov2 is not None and ov2[3] < a0  # 渐透明
    for _ in range(20):
        p.tick()
    assert p.fade_overlay() is None  # 淡出完成 → fadeType=0


def test_player_fade_in_white_sticks() -> None:
    """@3: 白幕淡入, 完成后停在不透明白 (:146-156)。"""
    p = EndingPlayer(_end([b"@310\x00", b"@w600\x00600\x00", b"@z"]))
    p.tick()
    ov = p.fade_overlay()
    assert ov is not None and ov[:3] == (255, 255, 255)
    for _ in range(20):
        p.tick()
    assert p.fade_overlay() == (255, 255, 255, 255)


# ---- 背景滚动 (@v/@V, stop 收尾 :420-427) ----


def test_player_bg_scroll_and_clamp() -> None:
    """@v 设 y, @V 设速度 dist/dur; 每次解析停帧 y-=speed, 夹到 0 停。"""
    p = EndingPlayer(
        _end(
            [
                b"@v147\x00",
                b"@V120\x003100\x00",  # speed = 120/3100
                b"@w600\x00600\x00",
                b"@z",
            ]
        )
    )
    speed = 120 / 3100
    p.tick()  # @v/@V/@w 同帧处理, stop 收尾滚一格
    assert p.bg_y == pytest.approx(147.0 - speed)
    p.tick()
    assert p.bg_y == pytest.approx(147.0 - 2 * speed)
    p.bg_y = 0.01  # 快进到底
    for _ in range(5):
        p.tick()
    assert p.bg_y == 0.0 and p.bg_scroll == 0.0


# ---- @F 续载 (staff roll 衔接) / @m 音乐事件 / @z 结束 ----


def test_player_load_chains_staff_roll() -> None:
    staff = _end(
        [
            b"@R\x00",
            b"@bdata/end/staff00.jpg\x00",
            b"@mbgm/th07_15.mid\x00",
            b"@a0\x000\x000\x00",
            b"@z",
        ]
    )
    p = EndingPlayer(
        _end([b"@mbgm/th07_14.mid\x00", b"@Fdata/staff00.end\x00", b"@z"]),
        loader=lambda name: staff if name == "staff00.end" else None,
    )
    p.tick()  # @m + @F(清立绘) + staff 的 @R/@b/@m/@a
    assert p.bg_name == "staff00.jpg"
    assert p.faces == {0: (0, 0)}
    assert p.music_events == [("play", "th07_14.mid"), ("play", "th07_15.mid")]
    p.tick()  # staff 的 @z
    assert p.done


def test_player_load_failure_ends() -> None:
    """@F 载入失败 → LoadEnding 返回 ZUN_ERROR → 结局结束 (:271-275)。"""
    p = EndingPlayer(_end([b"@Fdata/none.end\x00", b"@z"]), loader=lambda name: None)
    p.tick()
    assert p.done


def test_player_music_fade_event() -> None:
    p = EndingPlayer(_end([b"@M5\x00", b"@z"]))
    p.tick()
    assert ("fadeout", 5) in p.music_events
