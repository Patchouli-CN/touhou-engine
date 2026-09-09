"""thbgm.dat / thbgm.fmt 解析: 高音质 WAV BGM 流索引。"""

from __future__ import annotations

import struct

import msgspec

# ThBgmFormat (dsutil.hpp:47-57, sizeof=0x34): name[16] + i32 startOffset +
# u32 preloadAllocSize + i32 introLength + i32 totalLength + WAVEFORMATEX(18B+2B
# 对齐); fmt 以 name[0]==0 的空条目终止(SoundPlayer.cpp:198-230)。
# thbgm.dat 头 16 字节: "ZWAV" + u32 version(1) + u32 game id + u32 保留
# (Supervisor.cpp:1183-1230); 循环语义: intro 播一遍, [introLength,
# totalLength) 段无限循环(dsutil.cpp:1071-1112 CWaveFile::ResetFile)
FMT_ENTRY_SIZE = 0x34
THBGM_HEADER_SIZE = 16
THBGM_MAGIC = b"ZWAV"
THBGM_VERSION = 1


class ThbgmTrack(msgspec.Struct, frozen=True):
    """thbgm.fmt 里的一首曲目。"""

    name: str  # 形如 "<作品>_<编号>.wav"
    start_offset: int  # PCM 在 thbgm.dat 里的绝对偏移
    intro_length: int  # 前奏字节数(只播一遍)
    total_length: int  # 整曲 PCM 字节数
    channels: int
    sample_rate: int
    bits_per_sample: int
    preload_size: int = 0  # 原版预读缓冲大小, 仅记录

    @property
    def bytes_per_second(self) -> float:
        """PCM 字节流速。"""
        return self.sample_rate * self.channels * self.bits_per_sample / 8

    @property
    def intro_seconds(self) -> float:
        """循环起点(秒)。"""
        return self.intro_length / self.bytes_per_second

    @property
    def total_seconds(self) -> float:
        """整曲时长(秒)。"""
        return self.total_length / self.bytes_per_second

    @property
    def loop_seconds(self) -> float:
        """循环段时长(秒)。"""
        return (self.total_length - self.intro_length) / self.bytes_per_second


def parse_fmt(data: bytes) -> dict[str, ThbgmTrack]:
    """解析解压后的 thbgm.fmt 字节流, 返回 {曲目名: ThbgmTrack}。"""
    tracks: dict[str, ThbgmTrack] = {}
    pos = 0
    while pos + FMT_ENTRY_SIZE <= len(data):
        raw_name = data[pos : pos + 16]
        if raw_name[0] == 0:
            break
        name = raw_name.split(b"\x00")[0].decode("latin-1")
        start, preload, intro, total = struct.unpack_from("<iIii", data, pos + 16)
        _tag, ch, rate, _avg, _align, bits = struct.unpack_from(
            "<HHIIHH", data, pos + 32
        )
        tracks[name] = ThbgmTrack(name, start, intro, total, ch, rate, bits, preload)
        pos += FMT_ENTRY_SIZE
    return tracks


def check_thbgm_header(header: bytes, *, game_id: int) -> bool:
    """校验 thbgm.dat 头 16 字节(magic/version/game id; 作品 id 显式传入)。"""
    if len(header) < THBGM_HEADER_SIZE:
        return False
    magic, version, gid, _reserved = struct.unpack("<4sIII", header[:THBGM_HEADER_SIZE])
    return bool(magic == THBGM_MAGIC and version == THBGM_VERSION and gid == game_id)


def build_wav(track: ThbgmTrack, pcm: bytes) -> bytes:
    """把 thbgm.dat 里读出的裸 PCM 包成完整 RIFF/WAVE。

    pcm 长度以 track.total_length 为准(截断/不足容忍)。
    """
    pcm = pcm[: track.total_length]
    byte_rate = int(track.bytes_per_second)
    block_align = track.channels * track.bits_per_sample // 8
    fmt_chunk = struct.pack(
        "<HHIIHH",
        1,  # WAVE_FORMAT_PCM
        track.channels,
        track.sample_rate,
        byte_rate,
        block_align,
        track.bits_per_sample,
    )
    data_size = len(pcm)
    riff_size = 4 + (8 + len(fmt_chunk)) + (8 + data_size)
    return (
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt_chunk))
        + fmt_chunk
        + b"data"
        + struct.pack("<I", data_size)
        + pcm
    )


__all__ = [
    "FMT_ENTRY_SIZE",
    "THBGM_HEADER_SIZE",
    "THBGM_MAGIC",
    "THBGM_VERSION",
    "ThbgmTrack",
    "build_wav",
    "check_thbgm_header",
    "parse_fmt",
]
