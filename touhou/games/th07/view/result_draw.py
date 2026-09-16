"""结算画面绘制: ResultScene 的快照生产侧(榜/字表/槽表/总结算面板)。

全部从 41 台 result00.anm VM 的 pos 推位置(ResultScreen.cpp OnDraw
:2166-2509 的对局后链部分); 输入状态机在 result.py。
"""

from __future__ import annotations

from ....engine import SpriteDraw, TextDraw
from ....engine.anm import AnmBank
from ....engine.score_store import ScoreStore, default_score
from ..replay import ReplayEntry
from .menu_vms import MenuVm
from .name_entry import NameEntry
from .playerdata import _CHARACTER_NAMES, _with_shadow

_RESULT_ANM = "result00.anm"
_VM_SLOT_HEADER = 24  # 槽表头锚 (:2438-2443)
_VM_SLOT_ROW = 25  # 槽行锚 vms[25..39]

_TOP_SIZE = 10  # 每榜 10 行

# 机体/难度名 (g_CharactersAndShotTypesStrings :41-48 / g_DifficultyNameTable :54-66)
_CHAR_STRINGS = ("ReimuA ", "ReimuB ", "MarisaA", "MarisaB", "SakuyaA", "SakuyaB")
_DIFF_NAMES = (
    "      Easy",
    "    Normal",
    "      Hard",
    "   Lunatic",
    "     Extra",
    "  Phantasm",
)

_SCORE_HEADER = "No  Name      Score(Stage)  Date   Slow"  # :2210
_SLOT_HEADER = "No.   Name     Date   Player Score"  # :2443

_ROW_RGB = (255, 192, 192)  # 0xffffc0c0 榜行 (:2228)
_ROW_PLAYER_RGB = (240, 240, 255)  # 0xfff0f0ff 入榜行 (ENTER_NAME, :2219)
_HEADER_RGB = (224, 224, 239)  # 0xffe0e0ef 榜表头 (:2207)
_CHOSEN_RGB = (255, 128, 128)  # 0xffff8080 选中槽 (:2450)
_SLOT_RGB = (128, 128, 128)  # 0xff808080 未选槽 (:2454)


def vm_sprites(vms: list[MenuVm], bank: AnmBank | None) -> list[SpriteDraw]:
    """41 台 VM 按数组序绘制 (DrawNoRotation, :2189-2195)。"""
    out: list[SpriteDraw] = []
    for i, w in enumerate(vms):
        vm = w.vm
        if not vm.visible or vm.active_sprite_idx < 0 or vm.color[3] <= 0:
            continue
        x = vm.pos[0] + vm.offset[0]  # OnDraw: pos += offset (:2192)
        y = vm.pos[1] + vm.offset[1]
        if vm.anchor & 3 and bank is not None:
            slot = bank.sprites.get(vm.active_sprite_idx)
            if slot is not None:  # 左/顶缘 → 中心锚 (AnmManager.cpp:1011-1041)
                if vm.anchor & 1:
                    x += slot.sprite.w * vm.scale[0] / 2
                if vm.anchor & 2:
                    y += slot.sprite.h * vm.scale[1] / 2
        out.append(
            SpriteDraw(
                f"{_RESULT_ANM}:{vm.active_sprite_idx}",
                x,
                y,
                z=float(i),
                alpha=vm.color[3],
                scale_x=vm.scale[0],
                scale_y=vm.scale[1],
                color=(vm.color[0], vm.color[1], vm.color[2]),
                blend_mode=vm.blend_mode,
            )
        )
    return out


def score_rows(
    store: ScoreStore,
    result: dict,
    entry: NameEntry,
    rank: int,
    *,
    in_enter_name: bool,
    pos: list[float],
) -> list[TextDraw]:
    """本难度×机体 Top10 榜 (:2196-2274); ENTER_NAME 时入榜行显示输入中名字。"""
    px, py = pos[0], pos[1]
    difficulty = result["difficulty"]
    character = result["character"]
    texts: list[TextDraw] = []
    if in_enter_name:  # 机体名 (DrawStringFormat2, :1158-1160/:2202-2204)
        texts.extend(
            _with_shadow(_CHARACTER_NAMES[character], px + 64, py, (255, 255, 255, 255))
        )
    texts.extend(_with_shadow(_SCORE_HEADER, px + 24, py + 18, (*_HEADER_RGB, 255)))
    rows = store.entries(difficulty, character)
    y = py + 36
    for i in range(_TOP_SIZE):
        if i < len(rows):
            rec = rows[i]
            name, score = rec["name"], rec["score"]
            retries, stage = rec["numRetries"], rec["stage"]
            date = rec["date"]
        else:  # 默认空位 (AddedCallback :2527-2546)
            name, score, retries, stage, date = (
                "--------",
                default_score(i),
                0,
                1,
                "--/--",
            )
        is_player = in_enter_name and i == rank
        if is_player:  # 输入中名字 + 光标槽 '_' (:2233-2242)
            cur = min(entry.cursor, 7)
            name = entry.name[:cur] + "_" + entry.name[cur + 1 :]
        if len(date) >= 10 and date[4] == "-":  # ISO → MM/DD
            date = f"{date[5:7]}/{date[8:10]}"
        # stage<=6 → (面数), 7/8 → (1), 其余 → (C) (:2244-2266)
        stage_disp = str(stage) if stage <= 6 else ("1" if stage <= 8 else "C")
        if in_enter_name:
            rgba = (*_ROW_PLAYER_RGB, 255) if is_player else (*_ROW_RGB, 192)
        else:
            rgba = (*_ROW_RGB, 255)  # :2228
        texts.extend(_with_shadow(f"{i + 1:>2}", px + 24, y, rgba))
        texts.extend(
            _with_shadow(
                f"{name:>8} {score:>9}{retries}({stage_disp})", px + 72, y, rgba
            )
        )
        # Slow 列: 成绩库无 slowRate 字段, 恒 0.00(同 Player Data 口径)
        texts.extend(_with_shadow(f" {date:>5}   {0.0:.2f}", px + 392, y, rgba))
        y += 18
    return texts


def slot_rows(
    vms: list[MenuVm],
    slots: list[ReplayEntry],
    chosen: int,
    result: dict,
    entry: NameEntry,
    replay_name: str,
    replay_date: str,
    *,
    in_saving: bool,
) -> list[TextDraw]:
    """录像槽表 (:2430-2494): 表头 + 既有录像行 + 末行新槽; SAVING 行带输入名。"""
    texts: list[TextDraw] = []
    hp = vms[_VM_SLOT_HEADER].vm.pos
    texts.extend(_with_shadow(_SLOT_HEADER, hp[0], hp[1], (255, 255, 255, 255)))
    for i in range(len(slots) + 1):
        pos = vms[_VM_SLOT_ROW + i].vm.pos
        rgb = _CHOSEN_RGB if i == chosen else _SLOT_RGB  # :2448-2455
        if in_saving and i == chosen:
            cur = min(entry.cursor, 7)
            shown = entry.name[:cur] + "_" + entry.name[cur + 1 :]  # :2465-2472
            line = (
                f"No.{i + 1:02d} {replay_name:>8} {replay_date:>5}"
                f"  {_CHAR_STRINGS[result['character']]:>7} {result['score']:>9d}0"
            )
            texts.extend(_with_shadow(line, pos[0], pos[1], (*rgb, 255)))
            texts.extend(
                _with_shadow(f"      {shown:>8}", pos[0], pos[1], (240, 240, 255, 255))
            )
        elif i < len(slots):
            r = slots[i].replay
            line = (
                f"No.{i + 1:02d} {r.name:>8} {r.date:>5}"
                f"  {_CHAR_STRINGS[r.character]:>7} {r.score:>9d}0"
            )  # :2487-2492
            texts.extend(_with_shadow(line, pos[0], pos[1], (*rgb, 255)))
        else:  # 新槽(原版空槽行, :2478-2482)
            line = f"No.{i + 1:02d} -------- --/--  -------          0"
            texts.extend(_with_shadow(line, pos[0], pos[1], (*rgb, 255)))
    return texts


def stats_lines(vm_stats, result: dict) -> list[TextDraw]:
    """总结算面板 8 行 (DrawFinalStats :2040-2126); 色随面板 VM 淡入。"""
    alpha = vm_stats.color[3]
    x0 = vm_stats.pos[0] + 210.0
    y = vm_stats.pos[1] + 32.0
    rgba = (255, 255, 255, alpha)
    texts: list[TextDraw] = []
    texts.extend(_with_shadow(f"{result['score']:>9}", x0, y, rgba))
    texts.extend(_with_shadow(f"{result['retries']}", x0 + 126.0, y, rgba))
    y += 22.0
    texts.extend(_with_shadow(_DIFF_NAMES[result["difficulty"]], x0, y, rgba))
    y += 22.0
    if result["cleared"]:
        clear = "      100%"  # :2084-2087
    else:
        clear = f"    {min(result['clear_percent'], 99.0):3.2f}%"  # :2076-2081
    for value in (
        clear,
        f"{result['retries']:>9}",
        f"{int(result['deaths']):>9}",
        f"{int(result['bombs']):>9}",
        f"{result['spellcards']:>9}",
        f"    {result['slow_percent']:3.2f}%",
    ):
        texts.extend(_with_shadow(value, x0 + 14.0, y, rgba))
        y += 22.0
    return texts
