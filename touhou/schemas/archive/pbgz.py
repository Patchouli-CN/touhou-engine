"""PBGZ 容器解析。"""

from __future__ import annotations

import struct

from ..exceptions import ArchiveFormatError
from .base import Archive, ArchiveEntry
from .lzss import lzss_decompress

MAGIC = b"PBGZ"
DICT_BITS = 13
LEN_BITS = 4

# 加密头/文件表的 decrypt 参数(PbgArchive.cpp:177 / :209)
_HEADER_KEY, _HEADER_INC, _HEADER_CHUNK, _HEADER_MAX = 0x1B, 0x37, 12, 0x400
_TABLE_KEY, _TABLE_INC, _TABLE_CHUNK, _TABLE_MAX = 0x3E, 0x9B, 0x80, 0x400
# 加密头三字段的解偏码常量(PbgArchive.cpp:181-183)
_HEADER_BIAS = (123456, 345678, 567891)


def decrypt(data: bytes, key: int, inc: int, chunk: int, max_bytes: int) -> bytes:
    """FileSystem::Decrypt 移植(分块异或 + 块内逆序写回)。"""
    # 逐行出处 old/touhou/schema/archive/pbgz.py(Global.cpp:821-879)
    size = len(data)
    num_unencrypted = (size % chunk) if size % chunk < chunk // 4 else 0
    num_unencrypted += size & 1
    size -= num_unencrypted
    out = bytearray(len(data))
    in_pos = 0
    out_pos = 0
    while size > 0 and max_bytes > 0:
        if size < chunk:
            chunk = size
        p = out_pos + chunk - 1
        for _ in range((chunk + 1) // 2):
            out[p] = data[in_pos] ^ key
            key = (key + inc) & 0xFF
            p -= 2
            in_pos += 1
        p = out_pos + chunk - 2
        for _ in range(chunk // 2):
            out[p] = data[in_pos] ^ key
            key = (key + inc) & 0xFF
            p -= 2
            in_pos += 1
        size -= chunk
        out_pos += chunk
        max_bytes -= chunk
    rest = size + num_unencrypted
    if rest > 0:
        out[out_pos : out_pos + rest] = data[in_pos : in_pos + rest]
    return bytes(out)


def sniff_pbgz(header: bytes) -> bool:
    """凭文件头判断是不是 PBGZ。"""
    return header[:4] == MAGIC


# g_DecryptParams(Global.cpp:891-896): (key, xorValue, xorValueInc, chunkSize, maxBytes)
_DECRYPT_PARAMS: tuple[tuple[int, int, int, int, int], ...] = (
    (0x5D, 0x1B, 0x37, 0x0040, 0x2800),
    (0x74, 0x51, 0xE9, 0x0040, 0x3000),
    (0x71, 0xC1, 0x51, 0x1400, 0x2000),
    (0x8A, 0x03, 0x19, 0x1400, 0x7800),
    (0x95, 0xAB, 0xCD, 0x0200, 0x1000),
    (0xB7, 0x12, 0x34, 0x0400, 0x2800),
    (0x9D, 0x35, 0x97, 0x0080, 0x2800),
    (0xAA, 0x99, 0x37, 0x0400, 0x1000),
)
# g_CryptSignature 各减 0x20/0x40/0x60(Global.cpp:898,906-908) = "edz"
_SIGNATURE = (0x85 - 0x20, 0xA4 - 0x40, 0xDA - 0x60)


def try_decrypt_signed(data: bytes) -> bytes:
    """条目内层签名解密: 命中 "edz" 前缀则按参数行解密, 否则原样返回。"""
    # TryDecryptFromTable(Global.cpp:901-927); 出处 old/touhou/games/th08/crypt.py
    if len(data) < 4 or tuple(data[:3]) != _SIGNATURE:
        return data
    # C 的循环是 int 比较(key - (i<<4) - 0x10 可为负, 负值永远不等 u8 字节)
    for i, (key, xor, inc, chunk, max_bytes) in enumerate(_DECRYPT_PARAMS):
        if data[3] == key - (i << 4) - 0x10:
            return decrypt(data[4:], xor, inc, chunk, max_bytes)
    return data


def parse_pbgz(data: bytes, path: str | None = None) -> Archive:
    """解析 PBGZ 整包字节; 头不对抛 ArchiveFormatError。"""
    # 布局出处 old/touhou/schema/archive/pbgz.py(PbgArchive.cpp:138-269):
    # 12 字节加密头先整体 decrypt 再减偏码得 条目数/文件表偏移/表解压后大小;
    # 文件表先 decrypt 再 LZSS, 记录 = 名字\0 + u32 dataOffset + u32
    # decompressedSize + u32 不读; 条目数据紧接文件表前连续存放,
    # 压缩长度 = 下一条 dataOffset - 本条的(哨兵 = 文件表偏移)
    if not sniff_pbgz(data):
        raise ArchiveFormatError(f"不是 PBGZ 容器，识别到的格式：{data[:4]!r}")
    header = decrypt(data[4:16], _HEADER_KEY, _HEADER_INC, _HEADER_CHUNK, _HEADER_MAX)
    num_entries, table_offset, table_size = (
        v - bias for v, bias in zip(struct.unpack("<iii", header), _HEADER_BIAS)
    )
    if num_entries <= 0 or table_offset >= len(data):
        raise ArchiveFormatError(
            f"PBGZ 头损坏: 条目数 {num_entries}, 文件表偏移 {table_offset}"
        )
    table_lzss = decrypt(
        data[table_offset:], _TABLE_KEY, _TABLE_INC, _TABLE_CHUNK, _TABLE_MAX
    )
    table = lzss_decompress(
        table_lzss, table_size, dict_bits=DICT_BITS, len_bits=LEN_BITS
    )
    entries: list[ArchiveEntry] = []
    offsets: list[int] = []
    pos = 0
    for _ in range(num_entries):
        end = table.index(b"\x00", pos)
        name = table[pos:end].decode("latin-1")
        pos = end + 1
        offset, size, _ = struct.unpack_from("<III", table, pos)
        pos += 12
        entries.append(ArchiveEntry(name, offset, size, 0))
        offsets.append(offset)
    # raw_size = next.dataOffset - cur.dataOffset, 哨兵 = 文件表偏移
    out = [
        ArchiveEntry(e.name, e.offset, e.size, nxt - e.offset)
        for e, nxt in zip(entries, [*offsets[1:], table_offset])
    ]
    return Archive("pbgz", out, data, path=path)
