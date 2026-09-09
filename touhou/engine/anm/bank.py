"""ANM 命名空间: AnmFile → 全局 id 的脚本表/sprite 表(键在建表时一次定死)。"""

from __future__ import annotations

import msgspec

from ...schemas.anm import AnmFile, AnmSprite
from ...schemas.anm_script import Instruction


class AnmScript(msgspec.Struct, frozen=True):
    """一段脚本: 指令列表 + 字节偏移跳转表 + sprite 基址。"""

    instrs: list[Instruction]
    sprite_base: int
    offsets: dict[int, int]


class SpriteSlot(msgspec.Struct, frozen=True):
    """sprite 全局 id → (entry 下标, sprite 数据)。"""

    entry: int
    sprite: AnmSprite


class AnmBank(msgspec.Struct):
    """一个 .anm 的脚本表 + sprite 表, 键为全局 id 的单一寻址空间。"""

    scripts: dict[int, AnmScript]
    sprites: dict[int, SpriteSlot]


def build_script(instrs: list[Instruction], sprite_base: int = 0) -> AnmScript:
    """由指令列表建 AnmScript(跳转表键 = 相对脚本起点的字节偏移)。"""
    # 指令定长: 头 8B + 参数区 4B/个, 布局出处 AnmManager.hpp:192-199
    offsets: dict[int, int] = {}
    off = 0
    for i, ins in enumerate(instrs):
        offsets[off] = i
        off += 8 + 4 * (len(msgspec.structs.fields(type(ins))) - 2)
    return AnmScript(instrs, sprite_base, offsets)


def build_bank(anm: AnmFile, *, flat_layout: bool) -> AnmBank:
    """从 AnmFile 建全局 id 表, 两种布局的键规则由参数显式选定。

    Args:
        anm: 解析后的 .anm
        flat_layout: False = 链式偏移(键 = 存储 id + 按 max(存储 id)+1 累计的基址,
            脚本 sprite 参数是 entry 内 id, sprite_base = 基址);
            True = 扁平装载序(sprite/脚本各按数量累计, 键 = 装载序号, 文件里
            存的 id 一律忽略, sprite_base = 0), 要求 anm 由
            parse_anm(flat_layout=True) 解析(脚本键已是装载序)
    """
    # 链式偏移出处 AnmManager.cpp:398-429/556(LoadAnm spriteIdxOffset, 返回 id+1);
    # 扁平装载序出处 old/touhou/engine/view/anm_vm.py flat_chain_offsets —— 旧
    # _spr_loc 扁平分支用存储 id 当键, 对"存的 id 本身是全局扁平号"的文件错位,
    # 这里键只认 enumerate 装载序, 从根上消掉第二套寻址
    scripts: dict[int, AnmScript] = {}
    sprites: dict[int, SpriteSlot] = {}
    chain = 0
    spr_flat = 0
    scr_flat = 0
    for ei, entry in enumerate(anm.entries):
        escr = anm.scripts[ei]
        if flat_layout:
            for local, sprite in enumerate(entry.sprites.values()):
                sprites[spr_flat + local] = SpriteSlot(ei, sprite)
            spr_flat += len(entry.sprites)
            for key, instrs in escr.items():
                scripts[scr_flat + key] = build_script(instrs)
            scr_flat += len(escr)
        else:
            for sid, sprite in entry.sprites.items():
                sprites[chain + sid] = SpriteSlot(ei, sprite)
            for sid, instrs in escr.items():
                scripts[chain + sid] = build_script(instrs, chain)
            chain += max([*entry.sprites, *escr, 0]) + 1
    return AnmBank(scripts, sprites)
