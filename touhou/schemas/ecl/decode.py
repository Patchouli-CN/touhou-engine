"""ECL 指令字节流 decode/encode(规格驱动的取字段机制 + 符卡定制编解码)。"""

from __future__ import annotations

import struct
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from ..exceptions import ParseError
from .base import EclInstr, ImmFloat, ImmInt, VarRef
from .boss import BeginSpellcard, BeginSpellcardV800
from .control import SubEnd
from .spec import _A, _Entry
from .tables import _REVERSE, _TABLES

if TYPE_CHECKING:
    from . import Instruction  # 仅类型检查期(__init__ 运行时依赖本模块)


# ---- 指令头常量与字视图辅助 ----

_INSTR_HEADER = struct.Struct("<IhhBBH")  # time, id, size, unused, skip, paramMask
_HEADER_SIZE = _INSTR_HEADER.size  # 12

_TERMINATOR_ID = -1
_SPELLCARD_XOR = 0xAA  # 符卡字符串 XOR(v0/v800 同, EclManager.cpp BeginSpellcard)


def _i32(w: int) -> int:
    return w - 0x100000000 if w >= 0x80000000 else w


def _i16(w: int, half: int) -> int:
    v = (w >> (16 * half)) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def _u16(w: int, half: int) -> int:
    return (w >> (16 * half)) & 0xFFFF


def _f32(w: int) -> float:
    f: float = struct.unpack("<f", struct.pack("<I", w))[0]
    return f


def _i8(w: int, idx: int) -> int:
    v = (w >> (8 * idx)) & 0xFF
    return v - 0x100 if v >= 0x80 else v


def _decode_field(spec: _A, words: tuple[int, ...], mask: int) -> Any:
    bit = spec.bit if spec.bit >= 0 else spec.word
    masked = bool(mask & (1 << bit))
    w = words[spec.word] if spec.view != "rest" else 0
    if spec.view == "int":
        return VarRef(_i32(w)) if masked else ImmInt(_i32(w))
    if spec.view == "float":
        f = _f32(w)
        return VarRef(int(f)) if masked else ImmFloat(f)
    if spec.view == "int_t":
        return VarRef(_i32(w)) if masked else None
    if spec.view == "float_t":
        return VarRef(int(_f32(w))) if masked else None
    if spec.view == "ri":
        return _i32(w)
    if spec.view == "rf":
        return _f32(w)
    if spec.view == "h0":
        return _i16(w, 0)
    if spec.view == "h1":
        return _i16(w, 1)
    if spec.view == "hu0":
        return _u16(w, 0)
    if spec.view == "hu1":
        return _u16(w, 1)
    if spec.view == "h0m":
        v = _i16(w, 0)
        return VarRef(v) if masked else ImmInt(v)
    if spec.view == "h1m":
        v = _i16(w, 1)
        return VarRef(v) if masked else ImmInt(v)
    if spec.view == "b0":
        return w & 0xFF
    if spec.view == "b1":
        return (w >> 8) & 0xFF
    if spec.view == "sb0":
        return _i8(w, 0)
    if spec.view == "sb2":
        return _i8(w, 2)
    if spec.view == "fvid":
        return int(_f32(w))
    if spec.view == "rest":
        return tuple(words[spec.word :])
    raise ParseError(f"未知字段视图: {spec.view!r}")


def _encode_field(spec: _A, value: Any, words: list[int], mask: int) -> int:
    """把字段值写回 words[spec.word] 的对应视图, 返回更新后的 paramMask。"""

    def set_bit() -> int:
        return mask | (1 << (spec.bit if spec.bit >= 0 else spec.word))

    w = words[spec.word] if spec.word < len(words) else 0
    if spec.view == "int":
        if isinstance(value, VarRef):
            words[spec.word] = value.var_id & 0xFFFFFFFF
            return set_bit()
        words[spec.word] = value.value & 0xFFFFFFFF
        return mask
    if spec.view == "float":
        f = float(value.var_id) if isinstance(value, VarRef) else value.value
        words[spec.word] = struct.unpack("<I", struct.pack("<f", f))[0]
        return set_bit() if isinstance(value, VarRef) else mask
    if spec.view == "int_t":
        if value is None:
            return mask
        words[spec.word] = value.var_id & 0xFFFFFFFF
        return set_bit()
    if spec.view == "float_t":
        if value is None:
            return mask
        words[spec.word] = struct.unpack("<I", struct.pack("<f", float(value.var_id)))[
            0
        ]
        return set_bit()
    if spec.view == "ri":
        words[spec.word] = value & 0xFFFFFFFF
    elif spec.view == "rf":
        words[spec.word] = struct.unpack("<I", struct.pack("<f", value))[0]
    elif spec.view in ("h0", "h0m", "hu0"):
        if isinstance(value, VarRef):
            v = value.var_id
        elif isinstance(value, ImmInt):
            v = value.value
        else:
            v = value
        words[spec.word] = (w & 0xFFFF0000) | (v & 0xFFFF)
        if spec.view == "h0m" and isinstance(value, VarRef):
            return set_bit()
    elif spec.view in ("h1", "h1m", "hu1"):
        if isinstance(value, VarRef):
            v = value.var_id
        elif isinstance(value, ImmInt):
            v = value.value
        else:
            v = value
        words[spec.word] = (w & 0xFFFF) | ((v & 0xFFFF) << 16)
        if spec.view == "h1m" and isinstance(value, VarRef):
            return set_bit()
    elif spec.view == "b0":
        words[spec.word] = (w & ~0xFF) | (value & 0xFF)
    elif spec.view == "b1":
        words[spec.word] = (w & ~0xFF00) | ((value & 0xFF) << 8)
    elif spec.view == "sb0":
        words[spec.word] = (w & ~0xFF) | (value & 0xFF)
    elif spec.view == "sb2":
        words[spec.word] = (w & ~0xFF0000) | ((value & 0xFF) << 16)
    elif spec.view == "fvid":
        words[spec.word] = struct.unpack("<I", struct.pack("<f", float(value)))[0]
    elif spec.view == "rest":
        pass  # 由 encode_instr 末尾统一追加
    else:
        raise ParseError(f"未知字段视图: {spec.view!r}")
    return mask


def _spec_nwords(spec: tuple[_A, ...]) -> int:
    """规格覆盖的字数; 含 rest 视图时返回 rest 起始字(表示至少需要的字数)。"""
    n = 0
    for a in spec:
        if a.view == "rest":
            continue
        n = max(n, a.word + 1)
    return n


def _spec_rest(spec: tuple[_A, ...]) -> _A | None:
    for a in spec:
        if a.view == "rest":
            return a
    return None


# ---- 符卡指令定制编解码(内嵌 XOR 0xAA 字符串, 字段规格表达不了) ----


def _decode_text(words: tuple[int, ...]) -> str:
    raw = b"".join(struct.pack("<I", w) for w in words)
    raw = bytes(b ^ _SPELLCARD_XOR for b in raw)
    return raw.split(b"\x00")[0].decode("shift_jis", errors="replace")


def _encode_text(text: str, nbytes: int) -> list[int]:
    raw = text.encode("shift_jis", errors="replace")
    if len(raw) > nbytes:
        raise ParseError(f"符卡字符串超长: {len(raw)} > {nbytes}")
    enc = bytes(b ^ _SPELLCARD_XOR for b in raw).ljust(nbytes, b"\xaa")
    return list(struct.unpack(f"<{nbytes // 4}I", enc))


def _decode_spellcard_v0(
    base: dict[str, Any], words: tuple[int, ...], mask: int
) -> EclInstr:
    # v0 布局: word0 = gui_id i16|spellcard_idx u16, word1-12 = 符卡名 48B
    # (EclManager.cpp BeginSpellcard: 名字取 instr->args[1] 起 0x30 字节)
    if len(words) != 13:
        raise ParseError(f"begin_spellcard 参数数不符: {len(words)} != 13")
    return BeginSpellcard(
        **base,
        gui_id=_i16(words[0], 0),
        spellcard_idx=_u16(words[0], 1),
        name=_decode_text(words[1:13]),
    )


def _decode_spellcard_v800(
    base: dict[str, Any], words: tuple[int, ...], mask: int
) -> EclInstr:
    # v800 布局(EclDependencies.cpp:18-36): word0 = face i16|number u16,
    # bonus i32 @word1, name[48] @word2, owner[48] @word14, comment[64]×2 @word26/42
    if len(words) != 58:
        raise ParseError(f"begin_spellcard_v800 参数数不符: {len(words)} != 58")
    return BeginSpellcardV800(
        **base,
        gui_id=_i16(words[0], 0),
        spellcard_idx=_u16(words[0], 1),
        bonus=_i32(words[1]),
        name=_decode_text(words[2:14]),
        owner=words[14:26],
        comment1=words[26:42],
        comment2=words[42:58],
    )


def _encode_spellcard_v0(instr: BeginSpellcard) -> list[int]:
    words = [(instr.gui_id & 0xFFFF) | ((instr.spellcard_idx & 0xFFFF) << 16)]
    return words + _encode_text(instr.name, 48)


def _encode_spellcard_v800(instr: BeginSpellcardV800) -> list[int]:
    words = [(instr.gui_id & 0xFFFF) | ((instr.spellcard_idx & 0xFFFF) << 16)]
    words.append(instr.bonus & 0xFFFFFFFF)
    words += _encode_text(instr.name, 48)
    for raw in (instr.owner, instr.comment1, instr.comment2):
        words.extend(raw)
    return words


_CUSTOM_DECODE: dict[
    type[EclInstr], Callable[[dict[str, Any], tuple[int, ...], int], EclInstr]
] = {
    BeginSpellcard: _decode_spellcard_v0,
    BeginSpellcardV800: _decode_spellcard_v800,
}
_CUSTOM_ENCODE: dict[type[EclInstr], Callable[[Any], list[int]]] = {
    BeginSpellcard: _encode_spellcard_v0,
    BeginSpellcardV800: _encode_spellcard_v800,
}


def decode_instr(data: bytes, p: int, *, version: int = 0) -> Instruction:
    """把 p 处一条指令 decode 成指令对象(12 字节头 + 4 字节倍数的参数区)。"""
    table = _TABLES.get(version)
    if table is None:
        raise ParseError(f"未知 ecl 格式版本: {version:#x} (已知: {sorted(_TABLES)})")
    if p + _HEADER_SIZE > len(data):
        raise ParseError(f"ecl 指令头越界 (off={p:#x})")
    time, opcode, size, _unused, skip, mask = _INSTR_HEADER.unpack_from(data, p)
    if size < _HEADER_SIZE or (size - _HEADER_SIZE) % 4 != 0:
        raise ParseError(f"非法 ecl 指令 size={size} (off={p:#x})")
    if p + size > len(data):
        raise ParseError(f"ecl 指令截断 (off={p:#x})")
    nargs = (size - _HEADER_SIZE) // 4
    words = struct.unpack_from(f"<{nargs}I", data, p + _HEADER_SIZE)
    base: dict[str, Any] = {"offset": p, "time": time, "skip_difficulty": skip}
    if opcode == _TERMINATOR_ID:
        return SubEnd(**base, rest=words)
    entry = table.get(opcode)
    if entry is None:
        raise ParseError(
            f"未知 ecl 指令 opcode: {opcode} (off={p:#x}, version={version:#x})"
        )
    custom = _CUSTOM_DECODE.get(entry.cls)
    if custom is not None:
        return cast("Instruction", custom(base, words, mask))
    rest = _spec_rest(entry.args)
    need = _spec_nwords(entry.args)
    if rest is not None:
        if nargs < max(need, rest.word):
            raise ParseError(
                f"{entry.cls.__name__} 参数区过短: {nargs} 字 (off={p:#x})"
            )
    elif nargs != need:
        raise ParseError(
            f"{entry.cls.__name__} 参数数不符: 布局 {need} 字, 实际 {nargs} (off={p:#x})"
        )
    kwargs: dict[str, Any] = {}
    grouped: dict[str, list[Any]] = {}
    order: list[str] = []
    for spec in entry.args:
        v = _decode_field(spec, words, mask)
        if spec.name in grouped:
            grouped[spec.name].append(v)
        elif spec.name in order:
            grouped[spec.name] = [kwargs.pop(spec.name), v]
        else:
            kwargs[spec.name] = v
            order.append(spec.name)
    for name, vals in grouped.items():
        kwargs[name] = tuple(vals)
    kwargs.update(entry.consts)
    return cast("Instruction", entry.cls(**base, **kwargs))


def encode_instr(instr: Instruction, *, version: int = 0) -> bytes:
    """把指令对象写回二进制(decode 的逆运算; unused 头字节写 0)。

    paramMask 从操作数种类推导(VarRef → 置位); 布局分叉的指令须用
    与 decode 相同的 version, 否则抛 ParseError。
    """
    if isinstance(instr, SubEnd):
        return _INSTR_HEADER.pack(
            instr.time, _TERMINATOR_ID, _HEADER_SIZE, 0, instr.skip_difficulty, 0
        )
    rev = _REVERSE.get(version)
    if rev is None:
        raise ParseError(f"未知 ecl 格式版本: {version:#x} (已知: {sorted(_REVERSE)})")
    candidates = rev.get(type(instr))
    if candidates is None:
        raise ParseError(
            f"指令 {type(instr).__name__} 不在 version={version:#x} 的编号表里"
        )
    found: tuple[int, _Entry] | None = None
    for op, entry in candidates:
        if all(getattr(instr, k) == v for k, v in entry.consts.items()):
            found = (op, entry)
            break
    if found is None:
        raise ParseError(
            f"指令 {instr!r} 的常量字段与 version={version:#x} 表项全不匹配"
        )
    opcode, entry = found
    custom = _CUSTOM_ENCODE.get(type(instr))
    if custom is not None:
        words = custom(instr)
        size = _HEADER_SIZE + 4 * len(words)
        return _INSTR_HEADER.pack(
            instr.time, opcode, size, 0, instr.skip_difficulty, 0
        ) + struct.pack(f"<{len(words)}I", *words)
    nwords = _spec_nwords(entry.args)
    rest = _spec_rest(entry.args)
    if rest is not None:
        nwords = max(nwords, rest.word)
    words = [0] * nwords
    mask = 0
    for spec in entry.args:
        if spec.view == "rest":
            continue
        if isinstance(getattr(instr, spec.name), tuple):
            continue  # tuple 收集字段按同名规格逐个写(见下)
        mask = _encode_field(spec, getattr(instr, spec.name), words, mask)
    # tuple 收集字段: 同名多个规格按序取值
    seen: dict[str, int] = {}
    for spec in entry.args:
        if spec.view == "rest":
            words.extend(getattr(instr, spec.name))
            continue
        value = getattr(instr, spec.name)
        if not isinstance(value, tuple):
            continue
        idx = seen.get(spec.name, 0)
        seen[spec.name] = idx + 1
        mask = _encode_field(spec, value[idx], words, mask)
    size = _HEADER_SIZE + 4 * len(words)
    return _INSTR_HEADER.pack(
        instr.time, opcode, size, 0, instr.skip_difficulty, mask
    ) + struct.pack(f"<{len(words)}I", *words)
