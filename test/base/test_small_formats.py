"""musiccmt / thbgm / sound 的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

from touhou.schemas.musiccmt import parse_musiccmt
from touhou.schemas.sound import SOUND_EFFECTS
from touhou.schemas.thbgm import (
    THBGM_MAGIC,
    ThbgmTrack,
    build_wav,
    check_thbgm_header,
    parse_fmt,
)


def _cmt_block(path: str, title: str, comments: list[str]) -> str:
    return "\r\n".join([f"@{path}", title, *comments, ""])


def test_musiccmt_basic() -> None:
    text = (
        "0123456789\r\n"  # 首个 '@' 前的占位内容忽略
        + _cmt_block("bgm/x_01.mid", "曲目一", ["感想その1", "", "感想その2"])
        + _cmt_block("bgm/x_02.mid", "曲目二", [])
    )
    tracks = parse_musiccmt(text.encode("shift_jis"))
    assert len(tracks) == 2
    t0 = tracks[0]
    assert t0.path == "bgm/x_01.mid"
    assert t0.title == "曲目一"
    assert t0.comment == ("感想その1", "感想その2")  # 空行跳过
    assert t0.file_name == "x_01.mid"
    assert tracks[1].comment == ()


def test_musiccmt_comment_cap() -> None:
    """评论最多 8 行(TrackDescriptor.description[8])。"""
    text = _cmt_block("bgm/x_03.mid", "t", [f"c{i}" for i in range(12)])
    (t,) = parse_musiccmt(text.encode("shift_jis"))
    assert t.comment == tuple(f"c{i}" for i in range(8))


def test_musiccmt_empty() -> None:
    assert parse_musiccmt("ブロック無し".encode("shift_jis")) == []


def _fmt_entry(name: bytes, start: int, preload: int, intro: int, total: int) -> bytes:
    out = name.ljust(16, b"\x00")
    out += struct.pack("<iIii", start, preload, intro, total)
    out += struct.pack("<HHIIHHH", 1, 2, 44100, 176400, 4, 16, 0)
    out += b"\x00" * 2
    assert len(out) == 0x34
    return out


def test_parse_fmt() -> None:
    data = _fmt_entry(b"x_01.wav", 16, 1024, 100, 500)
    data += _fmt_entry(b"x_02.wav", 516, 2048, 200, 1000)
    data += b"\x00" * 0x34  # 空条目终止
    data += _fmt_entry(b"trailing.wav", 0, 0, 0, 0)  # 终止后不读
    tracks = parse_fmt(data)
    assert set(tracks) == {"x_01.wav", "x_02.wav"}
    t = tracks["x_01.wav"]
    assert t.start_offset == 16 and t.preload_size == 1024
    assert t.intro_length == 100 and t.total_length == 500
    assert t.channels == 2 and t.sample_rate == 44100 and t.bits_per_sample == 16
    assert t.bytes_per_second == 176400.0
    assert t.loop_seconds == 400 / 176400.0


def test_check_header() -> None:
    good = struct.pack("<4sIII", THBGM_MAGIC, 1, 0x700, 0)
    assert check_thbgm_header(good, game_id=0x700)
    assert not check_thbgm_header(good, game_id=0x800)
    assert not check_thbgm_header(good[:8], game_id=0x700)
    bad = struct.pack("<4sIII", b"XXXX", 1, 0x700, 0)
    assert not check_thbgm_header(bad, game_id=0x700)


def test_build_wav_roundtrip() -> None:
    track = ThbgmTrack("x.wav", 16, 100, 500, 2, 44100, 16)
    pcm = bytes(range(256)) * 3  # 768 字节, 截到 500
    wav = build_wav(track, pcm)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    riff_size = struct.unpack_from("<I", wav, 4)[0]
    assert riff_size == len(wav) - 8
    assert wav[12:16] == b"fmt "
    _tag, ch, rate, _avg, _align, bits = struct.unpack_from("<HHIIHH", wav, 20)
    assert (ch, rate, bits) == (2, 44100, 16)
    assert wav[36:40] == b"data"
    data_size = struct.unpack_from("<I", wav, 40)[0]
    assert data_size == 500
    assert wav[44:] == pcm[:500]


def test_sound_effects_table() -> None:
    """SE 槽位表: 38 槽, 下标即 PlaySoundByIdx 的 idx。"""
    assert len(SOUND_EFFECTS) == 38
    assert SOUND_EFFECTS[0].file_name == "se_plst00.wav"
    assert SOUND_EFFECTS[0].volume == -2000
    assert SOUND_EFFECTS[4].file_name == "se_pldead00.wav"  # 玩家死亡
    assert SOUND_EFFECTS[10].file_name == "se_ok00.wav"
    assert SOUND_EFFECTS[33].file_name == "se_bonus.wav"  # 结界破
    assert SOUND_EFFECTS[37].file_name == "se_pause.wav"
    assert SOUND_EFFECTS[37].volume == -300
    for se in SOUND_EFFECTS:
        assert se.file_name.endswith(".wav")
        assert se.volume <= 0
