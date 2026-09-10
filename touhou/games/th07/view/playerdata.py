"""Player Data(Result 画面): ResultScreen.cpp 的 scene 化(独立 chain, RegisterChain type=0)。

难度选择菜单 → 各难度最高分榜(←→换机体)/符卡收集表(←→翻页 ↑↓换机体)/総合データ
三页, 状态机与版面逐行对照 ResultScreen.cpp OnUpdate/OnDraw; 数据全来自
ScoreStore(JSON 版 score.dat)。对局后的入榜/REPLAY 保存态(ENTER_NAME 等)
属结算画面, 不在本画面。
"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.input import Button
from ....engine.rng import Rng
from ....engine.score_store import ScoreStore, default_score
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from .menu_vms import SE_BACK, SE_MOVE, MenuScene, MenuVm
from .scene import Scene

_BG = "result.jpg"  # LoadSurface("data/result/result.jpg") (ResultScreen.cpp:2551)
_RESULT_ANM = "result00.anm"  # ResultScreen.cpp:2556

_VM_COUNT = 41  # vms[41] (ResultScreen.hpp:426)
_PANEL_VM = 16  # 表格面板 VM, 表格位置全从它的 pos 推 (ResultScreen.cpp:2196)
_BAR_SPRITE = 16  # ANM_SPRITE_RESULT_SPELLCARD_BAR (AnmIdx.hpp:295)

# 状态机 (ResultScreen.hpp:206-231 ResultScreenState; 只取 Player Data 用到的)
_ST_INIT = 0
_ST_SELECT = 1
_ST_EXITING = 2
_ST_SCORE_BASE = 3  # 3..8 = SCORE_EASY..SCORE_PHANTASM
_ST_SPELLCARD_LIST = 9
_ST_OVERALL_INIT = 19
_ST_OVERALL_INPUT = 20
_ST_OVERALL_EXIT = 21

_MENU_COUNT = 9  # 难度 6 项 + 符卡一览 + 総合データ + 终了
_MENU_PHANTASM = 5
_MENU_SPELLCARDS = 6
_MENU_OVERALL = 7
_MENU_EXIT = 8

_SHOT_COUNT = 6  # 机体(装备)数
_TOP_SIZE = 10  # 每榜 10 行

_INIT_GATE = 20  # INIT 20 帧后才进选择态 (:814)
_PAGE_GATE = 30  # 分数页/符卡页 30 帧输入门 (:1002/:1066)
_NAME_REFRESH = 20  # 机体名/符卡名单在 frameTimer==20 重绘 (:995/:1033)
_EXIT_FRAMES = 60  # 离场动画帧数 (:919)
_STATS_FADE_IN = 40  # 総合データ淡入 (:1961)
_STATS_FADE_OUT = 20  # 総合データ淡出 (:1996)

_FONT = 15  # DrawVmTextFmt fontWidth/Height=15 (ResultScreen.cpp:2575-2576)
_FONT_SMALL = 12  # MaxBonus 行 scale 0.8 (:2338-2339)

_ROW_RGB = (255, 192, 192)  # 0xffffc0c0 分数榜行 (:2228)
_HEADER_RGB = (224, 224, 239)  # 0xffe0e0ef 榜表头 (:2207)
_UNKNOWN_RGB = (192, 192, 255)  # 0xc0c0c0ff 未遇到符卡 (:2301)
_FAILED_RGB = (192, 160, 160)  # 0xffc0a0a0 遇到未取得 (:2306)
_BONUS_RGB = (160, 128, 144)  # 0xffa08090 MaxBonus (:2337)
_WHITE = (255, 255, 255)

# 机体名 (g_CharacterList, ResultScreen.cpp:28-35; 原文 i18n.csv TH_RESULT_*)
_CHARACTER_NAMES = (
    "博麗 霊夢 (霊)　",
    "博麗 霊夢 (夢)　",
    "霧雨 魔理沙 (魔)",
    "霧雨 魔理沙 (恋)",
    "十六夜 咲夜 (幻)",
    "十六夜 咲夜 (時)",
)
_TOTAL_NAME = "全主人公合計  　"  # TH_RESULT_TOTAL
_SPELL_UNKNOWN = "？？？？？"  # TH_RESULT_SPELL_UNKNOWN
# 原文 i18n.csv TH_RESULT_PLAY_COUNT / TH_RESULT_PLAY_COUNT_INCL_PHANTASM
_PLAY_HEADER = "プレイ回数　　　 　Easy 　Norm 　Hard 　Luna  Extra  Total"
_PLAY_HEADER_PH = "プレイ回数　　　 　Easy 　Norm 　Hard 　Luna  Extra Phants  Total"

# 分数榜表头 (ResultScreen.cpp:2210)
_SCORE_HEADER = "No  Name      Score(Stage)  Date   Slow"


def _fmt_date(iso: str) -> str:
    """ISO 日期串 → 原版 Hscr date 的 "MM/DD" 5 字符。"""
    if len(iso) >= 10 and iso[4] == "-" and iso[7] == "-":
        return f"{iso[5:7]}/{iso[8:10]}"
    return iso[:5]


def _with_shadow(
    text: str, x: float, y: float, rgba: tuple[int, int, int, int], size: int = _FONT
) -> tuple[TextDraw, TextDraw]:
    """DrawVmTextFmt 的白字黑影(第 2 色参 0 = 影色, ResultScreen.cpp:1047 等)。"""
    return (
        TextDraw(text, x + 1, y + 1, size, (0, 0, 0, rgba[3])),
        TextDraw(text, x, y, size, rgba),
    )


def _phantasm_unlocked(store: ScoreStore, spellcard_count: int = 0) -> bool:
    """Phantasm 解锁判定 (HasUnlockedPhantomAndMaxClears, GameManager.cpp:1014-1049)。

    C++ 就地把 clrd[shot].withRetries[5] 写成 99, 这里纯查询不 mutate:
    任一有 Phantasm 通关记录(with_retries[5]>=8), 或 >=60 张捕获且有
    Extra 通关记录(with_retries[4]>=7; clrd 值=通过面数)。
    """
    total = store.catk_slot_count - 1
    for c in store.clrd:
        if c["with_retries"][5] >= 8:
            return True
    if spellcard_count <= 0:
        spellcard_count = len(store.catk)
    captured = sum(1 for e in store.catk[:spellcard_count] if e["successes"][total] > 0)
    if captured < 60:
        return False
    return any(c["with_retries"][4] >= 7 for c in store.clrd)


def _load_bank(archive: Archive | None, anm_version: int) -> AnmBank | None:
    if archive is None:
        return None
    try:
        return build_bank(
            parse_anm(
                load_entry(archive, _RESULT_ANM),
                version=anm_version,
                flat_layout=False,
            ),
            flat_layout=False,
        )
    except (KeyError, ValueError):
        return None


class PlayerDataScene(MenuScene):
    """Player Data: 难度菜单 + 最高分榜/符卡收集表/総合データ三页, 取消回主菜单。

    与 Music Room 同为独立 chain(进它时 MainMenu 已销毁, 不复用 MenuVmSet);
    返回主菜单光标停 Player Data(MainMenu.cpp:2627-2628)。
    """

    def __init__(
        self,
        archive: Archive | None,
        store: ScoreStore,
        *,
        anm_version: int = 2,
        spellcard_count: int = 0,
        on_exit: Callable[[], Scene],
    ) -> None:
        super().__init__()
        self._on_exit = on_exit
        self._store = store
        # 符卡张数 = 作品表口径(SPELLCARD_COUNT); 读档扩容多出的条目不显示(:1037)
        self._spellcard_count = (
            spellcard_count if spellcard_count > 0 else len(store.catk)
        )
        self._page_count = (self._spellcard_count + 9) // 10  # 141 → 15 组 (:1070)
        self._phantasm = _phantasm_unlocked(store, self._spellcard_count)
        # 账本 (ResultScreen.hpp:404-422; 构造 cursor=1, spellcardListPage=6=合计)
        self._state = _ST_INIT
        self._state_step = _ST_INIT
        self.cursor = 1
        self._prev_cursor = 0
        self._saved_cursor = 0
        self._diff_played = 0
        self._char_used = -1
        self._last_selected = -1  # 已重绘的符卡组 (lastSpellcardSelected)
        self.spellcard_list_page = 6  # 0..5=各机体, 6=合计
        self._prev_page = 6
        self._list_scroll_anim = 0
        self._frame_timer = 0
        self._frame = 0
        # 各页的符卡取得枚数 (totalPlayCountPerShot, AddedCallback :2618-2633)
        self._obtained = [
            sum(
                1
                for e in store.catk[: self._spellcard_count]
                if e["successes"][slot] > 0
            )
            for slot in range(store.catk_slot_count)
        ]
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        self._bank = _load_bank(archive, anm_version)
        scripts = self._bank.scripts if self._bank is not None else {}
        self._vms: list[MenuVm] = []
        for i in range(_VM_COUNT):
            m = AnmMachine(rng)
            m.start(scripts.get(i))  # ANM_SCRIPT_RESULT_ARRAY+i ↔ 链式键 i (:2562-2567)
            self._vms.append(MenuVm(m))

    # ---- Scene 接口 ----
    def on_enter(self) -> None:
        """进 Player Data(标题 BGM 不停, MainMenu.cpp:2656; BGM 链留待后续单)。"""

    def on_exit(self) -> None:
        """离开 Player Data(回主菜单不重载标题 BGM, 同上; BGM 链留待)。"""

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        if self._state == _ST_INIT:
            self._update_init()
        elif self._state == _ST_SELECT:
            self._update_select()
        elif self._state == _ST_EXITING:
            if self._frame_timer >= _EXIT_FRAMES:
                self.done = True  # curState=MAINMENU + REMOVE_JOB (:923-924)
        elif _ST_SCORE_BASE <= self._state < _ST_SPELLCARD_LIST:
            self._update_score()
        elif self._state == _ST_SPELLCARD_LIST:
            self._update_spellcards()
        else:
            self._update_overall()
        for w in self._vms:
            w.vm.execute()  # ExecuteScript 全阵列 (:1122-1126)
        self._frame_timer += 1
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = [
            SpriteDraw(_BG, 320.0, 240.0, z=-1.0)
        ]  # CopySurfaceToBackBuffer (:2188)
        sprites.extend(self._vm_sprites())
        texts: list[TextDraw] = []
        panel = self._vms[_PANEL_VM].vm
        if panel.pos[0] < 640:  # 面板滑进屏内才画表格 (:2197)
            if self._state_step == _ST_SPELLCARD_LIST:
                sub_sprites, sub_texts = self._spellcard_page(panel.pos)
                sprites.extend(sub_sprites)
                texts.extend(sub_texts)
            elif 0 <= self._diff_played <= 5 and 0 <= self._char_used <= 5:
                # C++ 此处无界读 scoreLists[diffPlayed][charUsed](状态外越界),
                # 靠面板在屏外兜住; 这里显式判界(行为等价, 见报告)
                texts.extend(self._score_rows(panel.pos))
        if self._state in (_ST_OVERALL_INIT, _ST_OVERALL_INPUT, _ST_OVERALL_EXIT):
            texts.extend(self._stats_lines())
        return SceneSnapshot(self._frame, tuple(sprites), tuple(texts))

    def next_scene(self) -> Scene | None:
        return self._on_exit()

    # ---- 难度选择菜单 (:777-917) ----
    def _update_init(self) -> None:
        if self._frame_timer == 0:
            self._init_setup()
        if self._frame_timer < _INIT_GATE:
            return
        self._state = _ST_SELECT
        self._frame_timer = 0
        self._update_select()  # C++ 落到 DIFFICULTY_SELECT 当帧执行 (:818-820)

    def _init_setup(self) -> None:
        """INIT 帧 0 设置(也服务各页取消后的 goto CASE_RESULT_STATE_INIT)。"""
        for w in self._vms:
            w.vm.pending_interrupt = 1  # :782-787
        self._highlight_labels()

    def _highlight_labels(self) -> None:
        """9 个菜单项亮暗/偏移; Phantasm 未解锁: 隐藏且下方项上移 32 (:788-812)。"""
        for i in range(_MENU_COUNT):
            w = self._vms[i]
            sel = i == self.cursor
            w.vm.color = [255, 255, 255, 255 if sel else 0xB0]  # 0xffffffff/0xb0ffffff
            w.vm.offset = [-4.0, -4.0, 0.0] if sel else [0.0, 0.0, 0.0]
        self._vms[_MENU_PHANTASM].active = self._phantasm
        if not self._phantasm:
            for i in (_MENU_SPELLCARDS, _MENU_OVERALL, _MENU_EXIT):
                self._vms[i].vm.offset[1] -= 32.0

    def _update_select(self) -> None:
        moved = self._move_cursor_vertical(_MENU_COUNT)  # MoveCursor (:672)
        if self.cursor == _MENU_PHANTASM and not self._phantasm:
            self.cursor += moved  # 未解锁滑过不停 (:822-826)
        self._highlight_labels()
        if self._cancel_pressed():
            if self.cursor == _MENU_EXIT:
                self._go_back()  # GO_BACK (:905-913)
            else:
                self.cursor = _MENU_EXIT  # 取消 = 光标跳"终了" (:851-856)
                self._sounds.append(SE_BACK)
        if self._confirm_pressed():
            self._confirm_select()

    def _confirm_select(self) -> None:
        """确认分派 (:858-915); C++ 进各页无确认音, 只有移动/返回音。"""
        c = self.cursor
        if c <= _MENU_PHANTASM:
            self._interrupt_all(c + 3)
            self._diff_played = c
            self._state = _ST_SCORE_BASE + c
            self._state_step = self._state
            self.cursor = self._prev_cursor  # 记得上次看的机体
            self._char_used = -1
            self._last_selected = -1
        elif c == _MENU_SPELLCARDS:
            self._interrupt_all(10)
            self._diff_played = c
            self._state = _ST_SPELLCARD_LIST
            self._state_step = _ST_SPELLCARD_LIST
            self._char_used = -1
            self.cursor = self._saved_cursor  # 记得上次看的组
            self._last_selected = -1
        elif c == _MENU_OVERALL:
            self._interrupt_all(9)
            self._diff_played = c
            self._state = _ST_OVERALL_INIT
            self._state_step = _ST_OVERALL_INIT
            self._char_used = -1
        else:
            self._go_back()
            return
        self._frame_timer = 0

    def _go_back(self) -> None:
        """离场: interrupt 2 + 60 帧后回主菜单 (:905-913/:918-924)。"""
        self._interrupt_all(2)
        self._state = _ST_EXITING
        self._sounds.append(SE_BACK)
        self._frame_timer = 0

    # ---- 最高分榜页 (:925-1029) ----
    def _update_score(self) -> None:
        # Hard 页作弊码(FOCUS+↑↑↑DD↓↓↓QQQ, :926-989)不移植: 引擎输入层无字母键
        if self._char_used != self.cursor and self._frame_timer == _NAME_REFRESH:
            self._char_used = self.cursor  # 机体名重绘 (:995-1001)
        if self._frame_timer < _PAGE_GATE:
            return
        if self._move_cursor_horizontal(_SHOT_COUNT):  # ←→换机体 (:1006)
            self._frame_timer = 0
            self._interrupt_all(self._diff_played + 3)
        if self._cancel_pressed():
            self._sounds.append(SE_BACK)
            self._prev_cursor = self.cursor
            self.cursor = self._diff_played
            self._enter_init()  # goto CASE_RESULT_STATE_INIT (:1027)

    # ---- 符卡收集表页 (:1030-1098) ----
    def _update_spellcards(self) -> None:
        if self._frame_timer == _NAME_REFRESH:
            self._last_selected = self.cursor  # 名单/计数行重绘 (:1031-1064)
            self._prev_page = self.spellcard_list_page
        if self._frame_timer >= 40:
            self._list_scroll_anim = 0  # 翻页滚动动画收尾 (:2368-2371)
        if self._frame_timer < _PAGE_GATE:
            return
        if self._move_cursor_horizontal(self._page_count):  # ←→换 10 张组 (:1070)
            self._frame_timer = 0
            self._interrupt_all(10)
        elif self._move_page(7):  # ↑↓换机体/合计页 (MoveCursor2, :698)
            self._frame_timer = 0
            self._list_scroll_anim = 1
        if self._cancel_pressed():
            self._sounds.append(SE_BACK)
            self._saved_cursor = self.cursor
            self.cursor = self._diff_played
            self._enter_init()

    def _move_page(self, count: int) -> int:
        """MoveCursor2 (:698-721): spellcardListPage 上下环绕 + 移动音。"""
        if self._move_edge(Button.UP):
            self.spellcard_list_page = (self.spellcard_list_page - 1) % count
            self._sounds.append(SE_MOVE)
            return -1
        if self._move_edge(Button.DOWN):
            self.spellcard_list_page = (self.spellcard_list_page + 1) % count
            self._sounds.append(SE_MOVE)
            return 1
        return 0

    # ---- 総合データ页 (DrawStats, :1728-2011) ----
    def _update_overall(self) -> None:
        if self._state == _ST_OVERALL_INIT:
            if self._frame_timer >= _STATS_FADE_IN:
                self._state = _ST_OVERALL_INPUT  # 淡入完进输入态 (:1969-1972)
        elif self._state == _ST_OVERALL_INPUT:
            # SHOOT|BOMB|MENU|ENTER 任一键离场 (:1987-1992; Enter 无 Button 对应)
            if (
                self._pressed(Button.SHOT)
                or self._pressed(Button.BOMB)
                or self._pressed(Button.PAUSE)
            ):
                self._state = _ST_OVERALL_EXIT
                self._frame_timer = 0
        else:
            if self._frame_timer >= _STATS_FADE_OUT:
                self._enter_init()  # DrawStats return 1 → goto INIT (:2005-2007)

    def _enter_init(self) -> None:
        """各页取消/総合データ退出共用: 回 INIT 态并当帧跑 INIT 设置。"""
        self._state = _ST_INIT
        self._frame_timer = 0
        self._init_setup()

    def _interrupt_all(self, n: int) -> None:
        """全 41 台 pendingInterrupt=n(直接赋值, 非 SetInterruptActiveVms)。"""
        for w in self._vms:
            w.vm.pending_interrupt = n

    # ---- 绘制 ----
    def _vm_sprites(self) -> list[SpriteDraw]:
        """41 台 VM 按数组序绘制 (DrawNoRotation, :2189-2195)。"""
        out: list[SpriteDraw] = []
        for i, w in enumerate(self._vms):
            vm = w.vm
            if (
                not w.active
                or not vm.visible
                or vm.active_sprite_idx < 0
                or vm.color[3] <= 0
            ):
                continue
            x = vm.pos[0] + vm.offset[0]  # OnDraw: pos += offset (:2192)
            y = vm.pos[1] + vm.offset[1]
            if vm.anchor & 3 and self._bank is not None:
                slot = self._bank.sprites.get(vm.active_sprite_idx)
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

    def _score_rows(self, pos: list[float]) -> list[TextDraw]:
        """难度×机体 Top10 榜 (:2196-2274); 黑影 = ascii 字库烘焙描边的近似。"""
        px, py = pos[0], pos[1]
        texts = [
            TextDraw(  # 机体名 (DrawStringFormat2 白字黑影, :998-1000)
                _CHARACTER_NAMES[self._char_used],
                px + 65,
                py + 1,
                _FONT,
                (0, 0, 0, 255),
            ),
            TextDraw(
                _CHARACTER_NAMES[self._char_used], px + 64, py, _FONT, (*_WHITE, 255)
            ),
        ]
        texts.extend(_with_shadow(_SCORE_HEADER, px + 24, py + 18, (*_HEADER_RGB, 255)))
        rows = self._store.entries(self._diff_played, self._char_used)
        y = py + 36
        for i in range(_TOP_SIZE):
            if i < len(rows):
                rec = rows[i]
                name, score = rec["name"], rec["score"]
                retries, stage = rec["numRetries"], rec["stage"]
                date = _fmt_date(rec["date"])
            else:  # 默认空位 (AddedCallback :2527-2546)
                name, score, retries, stage, date = (
                    "--------",
                    default_score(i),
                    0,
                    1,
                    "--/--",
                )
            # stage<=6 → (面数), 7/8(Ex/Ph) → (1), 其余 → (C) (:2244-2266)
            stage_disp = str(stage) if stage <= 6 else ("1" if stage <= 8 else "C")
            texts.extend(_with_shadow(f"{i + 1:>2}", px + 24, y, (*_ROW_RGB, 255)))
            texts.extend(
                _with_shadow(
                    f"{name:>8} {score:>9}{retries}({stage_disp})",
                    px + 72,
                    y,
                    (*_ROW_RGB, 255),
                )
            )
            # Slow 列: 成绩库无 slowRate 字段(引擎未记低速率), 恒 0.00 —— 见报告
            texts.extend(
                _with_shadow(f" {date:>5}   {0.0:.2f}", px + 392, y, (*_ROW_RGB, 255))
            )
            y += 18
        return texts

    def _spellcard_page(
        self, pos: list[float]
    ) -> tuple[list[SpriteDraw], list[TextDraw]]:
        """符卡收集表: 10 张一组, 计数行 + No./卡名/取得数/MaxBonus (:2276-2372)。"""
        sprites: list[SpriteDraw] = []
        texts: list[TextDraw] = []
        if self._last_selected < 0:
            return sprites, texts
        px, py = pos[0], pos[1]
        page = self._prev_page
        catk = self._store.catk
        total_slot = self._store.catk_slot_count - 1
        # page 6(合计) C++ 越界读 g_CharacterList[6], 实际显示相邻的合计名
        page_name = _CHARACTER_NAMES[page] if page < _SHOT_COUNT else _TOTAL_NAME
        count_line = (
            f"{page_name} {self._spellcard_count:>3}枚中{self._obtained[page]:>3}枚取得"
            "（キャラ切り替え↓↑）"  # TH_RESULT_SPELL_OBTAINED_COUNT
        )
        texts.extend(_with_shadow(count_line, px, py, (*_WHITE, 255)))
        if self._list_scroll_anim == 0:
            spacing = 33.0
        elif self._frame_timer < 20:  # 换页动画: 行距 33→0→33 (:2353-2366)
            spacing = (20 - self._frame_timer) * 33 / 20
        else:
            spacing = (self._frame_timer - 20) * 33 / 20
        y = float(py + 16)
        for i in range(10):
            idx = self._last_selected * 10 + i
            if idx >= min(
                len(catk), self._spellcard_count
            ):  # SPELLCARD_COUNT 止 (:1041)
                break
            card = catk[idx]
            att = card["attempts"][page]
            succ = card["successes"][page]
            sprites.append(
                SpriteDraw(  # 卡名底条, scale.x=2.375 (:2292-2294)
                    f"{_RESULT_ANM}:{_BAR_SPRITE}",
                    px + 320,
                    y + 16,
                    z=100.0,
                    scale_x=2.375,
                )
            )
            if att == 0:
                rgb, alpha = _UNKNOWN_RGB, 0xC0
            elif succ == 0:
                rgb, alpha = _FAILED_RGB, 0xFF
            else:  # 0xfff0f0ff - i*0x80800 (:2310)
                rgb, alpha = (0xF0 - 8 * i, 0xF0 - 8 * i, 0xFF), 0xFF
            texts.extend(_with_shadow(f"No.{idx + 1:02d}", px, y, (*rgb, alpha)))
            # 卡名按合计槽遭遇记录解锁, 未遇到 = ？？？？？ (:1045-1056)
            name = card["name"] if card["attempts"][total_slot] > 0 else _SPELL_UNKNOWN
            texts.extend(_with_shadow(name, px + 96, y, (*_WHITE, 255)))
            count = f"{succ:>3}/{att:>3}" if att else "---/---"  # :2317-2333
            texts.extend(_with_shadow(count, px + 496, y, (*rgb, alpha)))
            if att:
                texts.extend(
                    _with_shadow(
                        f"MaxBonus {card['highscore'][page]:>8}",
                        px + 424,
                        y - 13,
                        (*_BONUS_RGB, 255),
                        _FONT_SMALL,
                    )
                )
            y += spacing
        return sprites, texts

    def _stats_lines(self) -> list[TextDraw]:
        """総合データ 14 行 (:1735-1959), 淡入/淡出 alpha (:1961-1972/:1995-2004)。"""
        plst = self._store.plst
        secs = plst["total_frames"] // 60  # 総プレイ時間(60fps 帧数折算)
        lines = [
            # 総起動時間: 成绩库无该字段(C++ 是 Supervisor 进程计时), 恒 0 —— 见报告
            f"総起動時間   {0:02d}:{0:02d}:{0:02d}",
            f"総プレイ時間 {secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}",
            _PLAY_HEADER_PH if self._phantasm else _PLAY_HEADER,
        ]
        # プレイ回数: pscr[难度,机体].play_count ↔ playCountPerShotType
        per_d = [
            [
                int(self._store.pscr.get(f"{d},{s}", {}).get("play_count", 0))
                for s in range(_SHOT_COUNT)
            ]
            for d in range(6)
        ]
        for s in range(_SHOT_COUNT):
            cols = [per_d[d][s] for d in range(6)]
            lines.append(_CHARACTER_NAMES[s] + self._stat_cols(cols, sum(cols)))
        totals = [sum(per_d[d]) for d in range(6)]
        lines.append(_TOTAL_NAME + self._stat_cols(totals, sum(totals)))
        # クリア/コンティニュー/プラクティス/リトライ: 分难度计数成绩库未存(见报告),
        # Total 列给 plst 总数(clear_count/retry_count; 后两项本就为 0)
        lines.append("クリア回数  　　" + self._stat_cols([0] * 6, plst["clear_count"]))
        lines.append("コンティニュー  " + self._stat_cols([0] * 6, plst["retry_count"]))
        lines.append("プラクティス　  " + self._stat_cols([0] * 6, 0))
        lines.append("リトライ回数  　" + self._stat_cols([0] * 6, 0))
        if self._state == _ST_OVERALL_INIT:
            alpha = min(self._frame_timer * 255 // _STATS_FADE_IN, 255)
        elif self._state == _ST_OVERALL_INPUT:
            alpha = 255
        else:
            alpha = max(255 - self._frame_timer * 255 // _STATS_FADE_OUT, 0)
        ys = [128.0 + 17 * i for i in range(10)]
        ys.append(ys[-1] + 34)  # クリア回数行空一档 (:1837)
        ys += [ys[-1] + 17, ys[-1] + 34, ys[-1] + 51]
        return [
            td
            for line, y in zip(lines, ys, strict=True)
            for td in _with_shadow(line, 56.0, y, (*_WHITE, alpha))
        ]

    def _stat_cols(self, counts: list[int], total: int) -> str:
        """%6d 列: 未解锁跳过 Phantasm 列(d5), Total 收尾 (:1782-1804)。"""
        cols = counts[:5] + ([counts[5]] if self._phantasm else []) + [total]
        return " " + " ".join(f"{c:>6}" for c in cols)
