"""关卡背景(.std)解析: 头 + 物件/实例表 + 场景脚本。"""

from __future__ import annotations

import struct

import msgspec

from .exceptions import ParseError
from .stage_script import Instruction, decode_instr

# 布局出处 old/touhou/schema/stage.py(StdRawHeader/StdRawObject/StdRawQuadBasic/
# StdRawInstance/StdRawInstr, Reference/th07/src/th07/Stage.hpp:69-124);
# th08 同构(转引 scratch_dbg/investigation/th08-ref-facts.md:47)
_HEADER_SIZE = 1168  # StdRawHeader
_OBJECT_HEAD_SIZE = 28  # StdRawObject 到 firstQuad 之前
_QUAD_SIZE = 28  # StdRawQuadBasic
_INSTANCE_SIZE = 16  # StdRawInstance
_INSTR_SIZE = 20  # StdRawInstr(8 字节头 + 12 字节参数)


class StdQuad(msgspec.Struct, frozen=True):
    """一个 3D quad(StdRawQuadBasic): anm_script 是背景 anm 的局部脚本号。"""

    type: int  # 0 = 世界空间 quad
    anm_script: int
    pos: tuple[float, float, float]
    size: tuple[float, float]  # 0 表示用 sprite 原尺寸


class StdObject(msgspec.Struct, frozen=True):
    """一个场景物件(StdRawObject): 一组 quad + 剔除参数。"""

    id: int
    z_level: int  # 0..3, 两个渲染 pass(0/1 高, 2/3 低)
    pos: tuple[float, float, float]
    size: tuple[float, float, float]
    quads: tuple[StdQuad, ...]


class StdInstance(msgspec.Struct, frozen=True):
    """物件实例(StdRawInstance): object_idx 是 objects 数组下标。"""

    object_idx: int
    pos: tuple[float, float, float]


class StdFile(msgspec.Struct):
    """解析后的 .std: 关卡名/曲目 + 物件表 + 实例表 + 场景脚本。"""

    title: str
    bgm_names: tuple[str, ...]
    bgm_paths: tuple[str, ...]
    objects: list[StdObject]
    instances: list[StdInstance]
    script: list[Instruction]
    quad_count: int = 0

    @property
    def main_bgm(self) -> str:
        """主 BGM 路径(取第一个非空的)。"""
        return next((p for p in self.bgm_paths if p), "")


def _sjis(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("cp932", "replace")


def _parse_objects(data: bytes, count: int) -> list[StdObject]:
    out: list[StdObject] = []
    for i in range(count):
        off = struct.unpack_from("<i", data, _HEADER_SIZE + i * 4)[0]
        if not (0 < off + _OBJECT_HEAD_SIZE <= len(data)):
            continue
        oid, z_level, _flags = struct.unpack_from("<Hbb", data, off)
        pos = struct.unpack_from("<3f", data, off + 4)
        size = struct.unpack_from("<3f", data, off + 16)
        quads: list[StdQuad] = []
        qoff = off + _OBJECT_HEAD_SIZE
        while qoff + _QUAD_SIZE <= len(data):
            qtype, qsize, anm_script, _vm = struct.unpack_from("<4h", data, qoff)
            if qtype < 0 or qsize <= 0:
                break
            qpos = struct.unpack_from("<3f", data, qoff + 8)
            qsz = struct.unpack_from("<2f", data, qoff + 20)
            quads.append(StdQuad(qtype, anm_script, qpos, qsz))
            qoff += qsize
        out.append(StdObject(oid, z_level, pos, size, tuple(quads)))
    return out


def _parse_instances(data: bytes, off: int) -> list[StdInstance]:
    # 实例表以 id<0 结束
    out: list[StdInstance] = []
    while 0 < off + _INSTANCE_SIZE <= len(data):
        oid, _pad = struct.unpack_from("<2h", data, off)
        if oid < 0:
            break
        pos = struct.unpack_from("<3f", data, off + 4)
        out.append(StdInstance(oid, pos))
        off += _INSTANCE_SIZE
    return out


def _parse_script(data: bytes, off: int) -> list[Instruction]:
    # 脚本以 frame==-1 的哨兵指令结束; size<20 按 20 步进(旧实现行为)
    out: list[Instruction] = []
    while 0 < off + _INSTR_SIZE <= len(data):
        frame, _opcode, size = struct.unpack_from("<ihh", data, off)
        if frame == -1:
            break
        out.append(decode_instr(data, off))
        off += size if size >= _INSTR_SIZE else _INSTR_SIZE
    return out


def parse_std(data: bytes) -> StdFile:
    """解析 .std 整文件。短于头部抛 ParseError。"""
    if len(data) < _HEADER_SIZE:
        raise ParseError("std 过短")
    objects_count, quad_count, faces_off, script_off = struct.unpack_from(
        "<hhII", data, 0
    )
    title = _sjis(data[16:144])
    bgm_names = tuple(
        _sjis(data[144 + i * 128 : 144 + (i + 1) * 128]) for i in range(4)
    )
    bgm_paths = tuple(
        _sjis(data[656 + i * 128 : 656 + (i + 1) * 128]) for i in range(4)
    )
    return StdFile(
        title,
        bgm_names,
        bgm_paths,
        _parse_objects(data, objects_count),
        _parse_instances(data, faces_off),
        _parse_script(data, script_off),
        quad_count,
    )
