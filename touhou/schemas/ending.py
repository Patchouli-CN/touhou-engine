"""结局脚本(.end)解析: 文本脚本 decode 成 tagged union 指令流。

.end 是文本脚本: '@' 指令行 + SJIS 文本行, 参数 NUL 分隔, 行 LF 结尾
(出处 old/touhou/engine/ending.py, 指令集对照 th07-ref Ending.cpp
ParseEndFile :171-429 全覆盖)。
"""

from __future__ import annotations

from pathlib import PurePosixPath

import msgspec


class EndInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """指令公共基类(tag = 指令名)。"""


class Bg(EndInstr, frozen=True, tag="bg"):
    """@b: 载入背景图(archive 内裸文件名)。"""

    path: str


class Face(EndInstr, frozen=True, tag="face"):
    """@a vm s f: 立绘/CG VM 槽位 vm 执行脚本 s, 活动 sprite f。"""

    vm: int
    script: int
    sprite: int


class BgScroll(EndInstr, frozen=True, tag="bg_scroll"):
    """@V dist dur: 背景滚动速度 = dist/dur (px/帧)。"""

    dist: int
    duration: int


class BgY(EndInstr, frozen=True, tag="bg_y"):
    """@v y: 直接设 backgroundPos.y。"""

    y: int


class Load(EndInstr, frozen=True, tag="load"):
    """@F: 载入另一份 .end 继续播(结局末尾接 staff roll)。"""

    path: str


class ClearFaces(EndInstr, frozen=True, tag="clear_faces"):
    """@R: 清空全部立绘 VM。"""


class Music(EndInstr, frozen=True, tag="music"):
    """@m: 切 BGM(archive 内裸文件名)。"""

    path: str


class MusicFade(EndInstr, frozen=True, tag="music_fade"):
    """@M sec: 音乐淡出(参数单位是秒, ParseEndFile 直接传 FadeOutMusic(f32))。"""

    seconds: int


class LineSpeed(EndInstr, frozen=True, tag="line_speed"):
    """@s d1 d2: 行间隔 d1(平常) / d2(按住确认键)。"""

    line2_delay: int
    top_line_delay: int


class TextColor(EndInstr, frozen=True, tag="text_color"):
    """@c color: 文字色(atol 十进制, 0xRRGGBB 的十进制写法)。"""

    color: int


class WaitReset(EndInstr, frozen=True, tag="wait_reset"):
    """@r t minw: 等 t 帧后清空已显示文本行; minw 帧内不可跳过。"""

    frames: int
    min_wait: int


class Wait(EndInstr, frozen=True, tag="wait"):
    """@w t minw: 等 t 帧再继续解析; minw 帧内不可跳过。"""

    frames: int
    min_wait: int


class Fade(EndInstr, frozen=True, tag="fade"):
    """@0-@3 frames: 淡入淡出(fade_type 1..4, 语义见 engine 播放器常量)。"""

    fade_type: int
    frames: int


class End(EndInstr, frozen=True, tag="end"):
    """@z: 结局结束(链移除 → 总结算)。"""


class Text(EndInstr, frozen=True, tag="text"):
    """一行 SJIS 文本(画进文本槽位, 随后停行间隔帧)。"""

    text: str


Instruction = (
    Bg
    | Face
    | BgScroll
    | BgY
    | Load
    | ClearFaces
    | Music
    | MusicFade
    | LineSpeed
    | TextColor
    | WaitReset
    | Wait
    | Fade
    | End
    | Text
)


class EndingSegment(msgspec.Struct, frozen=True):
    """一段结局: 背景图(archive 内裸文件名, None=沿用上一段) + 文本行。"""

    bg: str | None
    lines: tuple[str, ...]


class EndingFile(msgspec.Struct, frozen=True):
    """一份解析好的 .end(渲染/播放层只读): 完整指令流 + 简化分段视图 + BGM。"""

    ops: tuple[Instruction, ...]
    segments: tuple[EndingSegment, ...]
    music: str = ""  # 首个 @m 的裸文件名, 无则空


def _basename(raw: bytes) -> str:
    """@b/@m/@F 的路径参数 → archive 内裸文件名 (data/end/end00.jpg → end00.jpg)。"""
    return PurePosixPath(raw.decode("ascii", "replace")).name


def _int_params(first: bytes, fields: list[bytes], count: int) -> list[int]:
    """ReadEndFileParameter 序列: 指令字符后的余串 + NUL 分隔的后续字段, atol。"""
    seq = [first[2:], *fields[1:]]
    out: list[int] = []
    for s in seq:
        s = s.strip()
        if not s:
            continue
        try:
            out.append(int(s))
        except ValueError:
            break  # atol 遇非数字即停
        if len(out) >= count:
            break
    while len(out) < count:
        out.append(0)
    return out


def parse_end(data: bytes) -> EndingFile:
    """解析 .end: 指令全集 decode + 文本行; 顺带产出分段视图与首个 BGM 名。"""
    # 解析语义出处 old/touhou/engine/ending.py parse_end_ops (:178)
    ops: list[Instruction] = []
    segments: list[EndingSegment] = []
    seg_bg: str | None = None
    seg_lines: list[str] = []
    seg_dirty = False
    music = ""

    def flush_segment() -> None:
        nonlocal seg_bg, seg_lines, seg_dirty
        segments.append(EndingSegment(seg_bg, tuple(seg_lines)))
        seg_bg, seg_lines, seg_dirty = None, [], False

    for raw_line in data.split(b"\n"):
        fields = raw_line.split(b"\0")
        first = fields[0]
        if first.startswith(b"@"):
            c = first[1:2]
            if c == b"b":
                if seg_dirty:
                    flush_segment()
                seg_bg = _basename(first[2:])
                seg_dirty = True
                ops.append(Bg(seg_bg))
            elif c == b"a":
                vm, script, sprite = _int_params(first, fields, 3)
                ops.append(Face(vm, script, sprite))
            elif c == b"V":
                dist, dur = _int_params(first, fields, 2)
                ops.append(BgScroll(dist, dur))
            elif c == b"v":
                (y,) = _int_params(first, fields, 1)
                ops.append(BgY(y))
            elif c == b"F":
                ops.append(Load(_basename(first[2:])))
            elif c == b"R":
                ops.append(ClearFaces())
            elif c == b"m":
                name = _basename(first[2:])
                if not music:
                    music = name
                ops.append(Music(name))
            elif c == b"M":
                (sec,) = _int_params(first, fields, 1)
                ops.append(MusicFade(sec))
            elif c == b"s":
                line2, top = _int_params(first, fields, 2)
                ops.append(LineSpeed(line2, top))
            elif c == b"c":
                (color,) = _int_params(first, fields, 1)
                ops.append(TextColor(color))
            elif c == b"r":
                t, minw = _int_params(first, fields, 2)
                ops.append(WaitReset(t, minw))
            elif c == b"w":
                t, minw = _int_params(first, fields, 2)
                ops.append(Wait(t, minw))
            elif c in (b"0", b"1", b"2", b"3"):
                (frames,) = _int_params(first, fields, 1)
                ops.append(Fade(int(c) + 1, frames))
            elif c == b"z":
                ops.append(End())
            continue
        try:
            text = first.decode("cp932").strip("　 ")
        except UnicodeDecodeError:
            continue
        if text:
            seg_dirty = True
            seg_lines.append(text)
            ops.append(Text(text))
    if seg_dirty or not segments:
        flush_segment()
    return EndingFile(tuple(ops), tuple(segments), music)
