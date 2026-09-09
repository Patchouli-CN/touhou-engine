"""archive 容器解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ArchiveFormatError
from touhou.schemas.archive import (
    load_entry,
    lzss_decompress,
    open_archive,
    parse_pbg4,
    parse_pbgz,
    raw_entry,
    sniff_archive,
)
from touhou.schemas.archive.pbgz import decrypt


def _lzss_encode_literals(data: bytes, dict_bits: int = 13, len_bits: int = 4) -> bytes:
    """测试用编码器: 只发字面量 token, 末尾 EOD(flag=0, offset=0)。"""
    bits = 0
    nbits = 0

    def push(value: int, n: int) -> bytes:
        nonlocal bits, nbits
        bits = (bits << n) | value
        nbits += n
        out = bytearray()
        while nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
        return bytes(out)

    out = bytearray()
    for byte in data:
        out += push(0x100 | byte, 9)  # flag=1 + 字面量
    # EOD: flag=0 + offset 高 8 位全 0, 再 dict_bits+len_bits-8 位全 0
    out += push(0, 9)
    out += push(0, dict_bits + len_bits - 8)
    if nbits:
        out += push(0, 8 - nbits)
    return bytes(out)


def _lzss_pack_tokens(
    tokens: list[tuple], dict_bits: int = 13, len_bits: int = 4
) -> bytes:
    """测试用编码器: ("lit", b) / ("match", off, run) / ("eod",)。"""
    bits = 0
    nbits = 0

    def push(value: int, n: int) -> bytes:
        nonlocal bits, nbits
        bits = (bits << n) | value
        nbits += n
        out = bytearray()
        while nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
        return bytes(out)

    read2 = dict_bits + len_bits - 8
    out = bytearray()
    for tok in tokens:
        if tok[0] == "lit":
            out += push(0x100 | tok[1], 9)
        elif tok[0] == "match":
            off, run = tok[1], tok[2]
            out += push(off >> (read2 - len_bits), 9)  # flag=0 + offset 高 8 位
            out += push(
                ((off & ((1 << (read2 - len_bits)) - 1)) << len_bits) | (run - 3),
                read2,
            )
        else:  # eod
            out += push(0, 9)
            out += push(0, read2)
    if nbits:
        out += push(0, 8 - nbits)
    return bytes(out)


def test_lzss_literals() -> None:
    data = bytes(range(100))
    assert lzss_decompress(_lzss_encode_literals(data), len(data)) == data


def test_lzss_match_backreference() -> None:
    """匹配 = 输出流自复制: 'AB' + match(off=1, run=5) → 'ABABABA'。"""
    src = _lzss_pack_tokens(
        [("lit", ord("A")), ("lit", ord("B")), ("match", 1, 5), ("eod",)]
    )
    assert lzss_decompress(src, 7) == b"ABABABA"


def test_lzss_match_overlap_run() -> None:
    """Run 超过距离时模式自叠: 'A' + match(off=1, run=4) → 'AAAAA'。"""
    src = _lzss_pack_tokens([("lit", ord("A")), ("match", 1, 4), ("eod",)])
    assert lzss_decompress(src, 5) == b"AAAAA"


def test_lzss_eod_terminates() -> None:
    src = _lzss_pack_tokens([("lit", ord("X")), ("eod",)]) + b"\xff" * 16
    assert lzss_decompress(src) == b"X"


def test_lzss_dict_bits_validation() -> None:
    with pytest.raises(ValueError, match="dict_bits"):
        lzss_decompress(b"", dict_bits=7)


def _build_pbg4(items: dict[str, bytes]) -> bytes:
    """造一个 PBG4 包(目录表紧接头后, 条目数据随后; 均为纯字面量 LZSS)。"""
    header_size = 16
    blobs = bytearray()
    table = bytearray()
    for name, payload in items.items():
        table += name.encode("latin-1") + b"\0"
        table += struct.pack("<III", len(payload), len(payload), 0)  # 占位, 下面回填
        blobs += _lzss_encode_literals(payload)
    # 条目 offset 是绝对偏移(头 + 压缩表之后); 纯字面量编码长度只取决于输入
    # 长度, 表内容定长, 故先打包一次拿表长, 再回填真实偏移重打
    data_base = header_size + len(_lzss_encode_literals(bytes(table)))
    table = bytearray()
    blob_off = 0
    for name, payload in items.items():
        table += name.encode("latin-1") + b"\0"
        table += struct.pack("<III", data_base + blob_off, len(payload), 0)
        blob_off += len(_lzss_encode_literals(payload))
    packed_table = _lzss_encode_literals(bytes(table))
    header = b"PBG4" + struct.pack("<III", len(items), header_size, len(table))
    return header + packed_table + bytes(blobs)


def test_pbg4_roundtrip() -> None:
    items = {"a.txt": b"hello pbg4", "dir/b.bin": bytes(range(50))}
    arc = parse_pbg4(_build_pbg4(items))
    assert arc.format_name == "pbg4"
    assert [e.name for e in arc.entries] == ["a.txt", "dir/b.bin"]
    for name, payload in items.items():
        assert load_entry(arc, name) == payload
    with pytest.raises(KeyError):
        load_entry(arc, "nope")


def test_pbg4_bad_magic() -> None:
    with pytest.raises(ArchiveFormatError, match="PBG4"):
        parse_pbg4(b"NOPE" + b"\0" * 32)


def _encrypt(plain: bytes, key: int, inc: int, chunk: int, max_bytes: int) -> bytes:
    """Decrypt 的逆: 迭代到 decrypt(x) == plain(变换是双射, 必收敛)。"""
    x = decrypt(plain, key, inc, chunk, max_bytes)
    while decrypt(x, key, inc, chunk, max_bytes) != plain:
        x = decrypt(x, key, inc, chunk, max_bytes)
    return x


def _build_pbgz(items: dict[str, bytes]) -> bytes:
    """造一个 PBGZ 包(加密头/文件表按格式参数反向构造)。"""
    blobs = bytearray()
    table = bytearray()
    data_off = 16
    for name, payload in items.items():
        table += name.encode("latin-1") + b"\0"
        table += struct.pack("<III", data_off + len(blobs), len(payload), 0)
        blobs += _lzss_encode_literals(payload)
    table_off = data_off + len(blobs)
    packed_table = _lzss_encode_literals(bytes(table))
    enc_table = _encrypt(packed_table, 0x3E, 0x9B, 0x80, 0x400)
    header = struct.pack(
        "<iii",
        len(items) + 123456,
        table_off + 345678,
        len(table) + 567891,
    )
    enc_header = _encrypt(header, 0x1B, 0x37, 12, 0x400)
    return b"PBGZ" + enc_header + bytes(blobs) + enc_table


def test_pbgz_roundtrip() -> None:
    items = {"x.anm": b"fake anm bytes", "y.std": bytes(range(30))}
    arc = parse_pbgz(_build_pbgz(items))
    assert arc.format_name == "pbgz"
    for name, payload in items.items():
        assert load_entry(arc, name) == payload


def test_pbgz_bad_magic() -> None:
    with pytest.raises(ArchiveFormatError, match="PBGZ"):
        parse_pbgz(b"PBG4" + b"\0" * 32)


def test_sniff_archive() -> None:
    assert sniff_archive(_build_pbg4({"a": b"1"})) == "pbg4"
    assert sniff_archive(_build_pbgz({"a": b"1"})) == "pbgz"
    assert sniff_archive(b"\0" * 64) is None


def test_open_archive_sniff_and_format_name(tmp_path) -> None:
    p4 = tmp_path / "a.dat"
    p4.write_bytes(_build_pbg4({"a.txt": b"hi"}))
    arc = open_archive(p4)
    assert arc.format_name == "pbg4"
    assert load_entry(arc, "a.txt") == b"hi"
    arc2 = open_archive(p4, format_name="pbg4")
    assert load_entry(arc2, "a.txt") == b"hi"
    with pytest.raises(ArchiveFormatError, match="未知资源包格式名"):
        open_archive(p4, format_name="pbg9")


def test_open_archive_unrecognized(tmp_path) -> None:
    p = tmp_path / "junk.dat"
    p.write_bytes(b"\xde\xad" * 32)
    with pytest.raises(ArchiveFormatError, match="无法识别"):
        open_archive(p)


def test_open_archive_wrong_format_fails(tmp_path) -> None:
    p = tmp_path / "a.dat"
    p.write_bytes(_build_pbg4({"a": b"1"}))
    with pytest.raises(ArchiveFormatError, match="PBGZ"):
        open_archive(p, format_name="pbgz")


def test_raw_entry_undecoded(tmp_path) -> None:
    payload = b"raw check"
    arc = parse_pbg4(_build_pbg4({"f": payload}))
    assert lzss_decompress(raw_entry(arc, "f"), len(payload)) == payload
