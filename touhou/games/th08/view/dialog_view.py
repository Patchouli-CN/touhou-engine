"""th08 游戏中对话渲染 —— 4 槽立绘 + 对话框 + 文本, 对照 GuiImpl::DrawDialogue
(Gui.cpp:782-866) 与 RunMsg 的立绘驱动(Gui.cpp:286-463)。

立绘布局(Spellcard.cpp:434-560): 槽 0/1 = 自机双立绘(face_rm00+face_yk00
等 4 组, 单人机体同组), 槽 2/3 = 敌方按面(face_st01..st08m, 5/6B/EX 面
有第二张)。每个槽跑该 anm 的真实脚本(AnmVmTh08): 入场/亮/暗/退场全由
脚本的 interrupt 标签驱动(1=入场 3=亮 4=暗 5=退场 6=原地压暗), msg VM
(MsgVmTh08)只负责转发 pending_interrupt —— 压暗不做派生图缓存, 脚本调制
即原作语义, 从根上避开 th07 的跨关撞键类(BUGS.md 增量#2)。

文本框: x 16..368, y 384 起高 48(前 60 帧渐高), 顶 alpha 0xd0 → 底 0x90,
op18 可关(textBoxVisible, Gui.cpp:835)。文本 15px 带黑影, intro(Boss 名)
右对齐在框上方(坐标近似, 同 th07 手法)。
"""

from __future__ import annotations

from pathlib import Path

import pygame

from ....engine.view.anm_fx import AnmScriptBank, TransformCache, Vm2d
from ....engine.view.sprite_bank import SpriteBank
from ....logger import logger as log
from ....schema.msg import TEXT_COLORS_A, MsgOpcode, MsgVm
from .anm_vm import AnmVmTh08

# 机体 → 自机双立绘(Spellcard.cpp:440-483; 键 0-3 双人组, 4-11 单人归组)
_PLAYER_FACES = (
    ("face_rm00.anm", "face_yk00.anm"),  # 灵梦&紫 / 灵梦 / 紫
    ("face_mr00.anm", "face_al00.anm"),  # 魔理沙&爱丽丝 / 魔理沙 / 爱丽丝
    ("face_sk00.anm", "face_rs00.anm"),  # 咲夜&蕾米莉亚 / 咲夜 / 蕾米莉亚
    ("face_ym00.anm", "face_yy00.anm"),  # 妖梦&幽幽子 / 妖梦 / 幽幽子
)
# 面(stage_no 1-9 = 1/2/3/4A/4B/5/6A/6B/EX)→ 敌方立绘对(Spellcard.cpp:501-549)
_STAGE_FACES = (
    ("face_st01.anm", None),
    ("face_st02.anm", None),
    ("face_st03.anm", None),
    ("face_st04a.anm", None),
    ("face_st04b.anm", None),
    ("face_st05.anm", "face_st05b.anm"),
    ("face_st06.anm", None),
    ("face_st06.anm", "face_st07.anm"),
    ("face_st08m.anm", "face_st08.anm"),
)

BOX_X0, BOX_X1 = 16, 368  # Gui.cpp:796-803
BOX_Y, BOX_H = 384, 48
BOX_FADEIN_FRAMES = 60
TEXT_X, TEXT_Y0, TEXT_LINE_H = 24, 388, 18
INTRO_RIGHT_X, INTRO_Y0, INTRO_LINE_H = 360, 336, 20

_FONT_CANDIDATES = (
    "msgothic",
    "ms gothic",
    "msmincho",
    "meiryo",
    "yu gothic",
    "hiragino sans",
    "noto sans cjk jp",
    "microsoft yahei",
    "simhei",
)
_FONT_SIZE = 15


def _load_font():
    """日文字体; 找不到返回 None(调用方画占位块, 同 th07 容错)。"""
    if not pygame.font.get_init():
        try:
            pygame.font.init()
        except pygame.error:
            return None
    for name in _FONT_CANDIDATES:
        try:
            path = pygame.font.match_font(name)
        except Exception:
            path = None
        if path:
            try:
                return pygame.font.Font(path, _FONT_SIZE)
            except pygame.error:
                continue
    try:
        return pygame.font.SysFont(None, _FONT_SIZE)
    except pygame.error:
        return None


class _FaceVm2d(Vm2d):
    """立绘 VM: 扁平 sprite 号按装载序解析(AnmManager.cpp:2615-2617 的
    currentSpriteNumber 累加, 文件存的 id 被忽略) —— 不走
    AnmScriptBank._spr_loc(face 文件存的 id 本身是全局扁平号, 会错位)。"""

    def __init__(
        self,
        sbank: AnmScriptBank,
        tcache: TransformCache,
        flat: list[tuple[int, int]],
    ) -> None:
        super().__init__(sbank, tcache, vm_cls=AnmVmTh08)
        self._flat = flat  # 扁平 sprite 号 → (entry, 文件存的 id)

    def _set_sprite(self, key: int) -> None:
        if 0 <= key < len(self._flat):
            entry, sid = self._flat[key]
            self.surf = self.sbank.bank.sprite(self.sbank.name, sid, entry=entry)
        else:
            self.surf = None
        self.vm.active_sprite_idx = key


def _flat_sprites(bank: SpriteBank, name: str) -> list[tuple[int, int]]:
    """anm 的扁平 sprite 号 → (entry, 存的 id) 表(按 entry 链顺序装载序)。"""
    anm = bank.anm(name)
    if anm is None:
        return []
    return [(ei, sid) for ei, e in enumerate(anm.entries) for sid in e.sprites]


class DialogueViewTh08:
    """把一个 MsgVmTh08 的当前状态画到游戏面上(384x448)。"""

    def __init__(
        self, data_path: str | Path, *, character: int = 0, stage: int = 1
    ) -> None:
        self._font = _load_font()
        self._text_cache: dict = {}
        self._tcache = TransformCache()
        bank = SpriteBank(data_path, game="th08")
        group = character if character < 4 else (character - 4) // 2
        player = _PLAYER_FACES[group % len(_PLAYER_FACES)]
        enemy = _STAGE_FACES[min(max(stage - 1, 0), len(_STAGE_FACES) - 1)]
        names = (player[0], player[1], enemy[0], enemy[1])
        # face 集身份 = (character, stage) 四元组; 换关/换机体由后端整体
        # 重建本视图, 视图内无任何跨关共享缓存(避雷: BUGS.md 增量#2/#3)
        self._slots: list[_FaceVm2d | None] = []
        for name in names:
            vm2d = None
            if name is not None:
                sb = AnmScriptBank(bank, name, 0)
                if sb.ok:
                    vm2d = _FaceVm2d(sb, self._tcache, _flat_sprites(bank, name))
                else:
                    log.warning("对话立绘 anm 缺失: {}", name)
            self._slots.append(vm2d)
        # 槽位已应用状态: [script, sprite, interrupt](-1/-1/0 = 未应用)
        self._applied = [[-1, -1, 0] for _ in range(4)]
        self._last_frame = -1
        # 预建对话框渐变纹理(宽 1, 逐行 alpha)
        grad = pygame.Surface((1, BOX_H), pygame.SRCALPHA)
        for y in range(BOX_H):
            a = 0xD0 + (0x90 - 0xD0) * y // max(BOX_H - 1, 1)
            grad.set_at((0, y), (0, 0, 0, a))
        self._grad = grad

    # ---- 立绘 ----
    def _sync_slot(self, i: int, vm: MsgVm) -> None:
        """把 msg VM 的槽位状态落到立绘 VM(脚本换 → 重起; sprite/interrupt
        变化 → 转发; 槽位清空(换消息)→ 立绘 VM 复位)。"""
        v = self._slots[i]
        if v is None:
            return
        p = vm.portraits[i]
        st = self._applied[i]
        if not p.visible:
            if st[0] != -1:
                v.vm.__init__()  # reset_and_run 同款复位(脚本/中断全清)
                v.vm.pc = -1
                v.surf = None
                st[0], st[1], st[2] = -1, -1, 0
            return
        if p.face != st[0]:
            # op1 SET_PORTRAIT_ANM_SCRIPT: 扁平脚本号(Gui.cpp:385-417)
            v.start(p.face)
            st[0], st[1], st[2] = p.face, -1, 0
        # op15/17 SetSprite(Gui.cpp:309-324/:354-378); th08 无该扩展字段的
        # VM(如 th07 基类)按无覆写处理
        sprite = getattr(vm, "portrait_sprites", None)
        if sprite is not None and 0 <= sprite[i] != st[1]:
            v.set_sprite(sprite[i])
            st[1] = sprite[i]
        if p.pending_interrupt != st[2]:
            v.vm.pending_interrupt = p.pending_interrupt
            st[2] = p.pending_interrupt

    def _draw_vm(self, surf: pygame.Surface, v: _FaceVm2d) -> None:
        """DrawNoRotation 子集: pos 锚点(anchor &1=左锚 &2=顶锚,
        AnmManager.cpp:1303-1323) + 颜色/alpha 调制; pos2 不进 2D 绘制。"""
        vm = v.vm
        img = v.surf
        if not vm.visible or img is None:
            return
        r, g, b, a = vm.color2 if vm.flag17 else vm.color  # :987 二选一
        if a <= 0 or vm.scale[0] == 0.0 or vm.scale[1] == 0.0:
            return
        out = self._tcache.get(img, vm.scale[0], vm.scale[1], vm.rotation[2])
        if (r, g, b) != (255, 255, 255) or a < 255:
            out = self._tcache.get_modulated(out, r, g, b, a)
        x, y = int(vm.pos[0]), int(vm.pos[1])
        if not vm.anchor & 1:
            x -= out.get_width() // 2
        if not vm.anchor & 2:
            y -= out.get_height() // 2
        surf.blit(out, (x, y))

    def _draw_portraits(self, surf: pygame.Surface) -> None:
        """Gui.cpp:809-831: 自机对/敌方对各自按 pos.z 大先画(z 高者垫底)。"""
        for pair in ((0, 1), (2, 3)):
            a, b = self._slots[pair[0]], self._slots[pair[1]]
            if a is None or b is None:
                for v in (a, b):
                    if v is not None:
                        self._draw_vm(surf, v)
                continue
            order = (a, b) if a.vm.pos[2] >= b.vm.pos[2] else (b, a)
            for v in order:
                self._draw_vm(surf, v)

    # ---- 文本(带缓存与无字体容错, 同 th07 dialog_view) ----
    def _text(self, text: str, color: int) -> pygame.Surface | None:
        if not text or self._font is None:
            return None
        key = (text, color)
        surf = self._text_cache.get(key)
        if surf is None:
            rgb = ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)
            try:
                main = self._font.render(text, True, rgb)
            except pygame.error:
                return None
            shadow = self._font.render(text, True, (0, 0, 0))
            w, h = main.get_size()
            surf = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
            surf.blit(shadow, (1, 1))
            surf.blit(main, (0, 0))
            if len(self._text_cache) > 256:
                self._text_cache.clear()
            self._text_cache[key] = surf
        return surf

    def _blit_text(
        self,
        surf: pygame.Surface,
        text: str,
        color: int,
        pos: tuple[int, int],
        *,
        right: bool = False,
    ) -> None:
        img = self._text(text, color)
        if img is not None:
            rect = img.get_rect()
            if right:
                rect.topright = pos
            else:
                rect.topleft = pos
            surf.blit(img, rect)
            return
        # 无字体容错: 每个字符画一个占位块
        x, y = pos
        w = _FONT_SIZE
        if right:
            x -= w * len(text)
        for i, _ in enumerate(text):
            pygame.draw.rect(
                surf, (200, 200, 220, 160), (x + i * w, y, w - 2, _FONT_SIZE)
            )

    # ---- 主入口 ----
    def render(self, surf: pygame.Surface, vm: MsgVm, *, frame: int = -1) -> None:
        """DrawDialogue: currentMsgIdx < 0 时不画。frame = 游戏帧号, 用于
        暂停/菜单冻结 tick 时不推进立绘脚本(一帧只 execute 一次)。"""
        if vm is None or not vm.active:
            return
        do_tick = frame != self._last_frame
        self._last_frame = frame
        for i in range(len(self._slots)):
            if i < len(vm.portraits):
                self._sync_slot(i, vm)
        # 立绘(先画, 垫在对话框下; Gui.cpp:748-751 的 ExecuteScript 在每帧
        # RunMsg 尾部, 这里 render 一帧一次)
        if do_tick:
            for v in self._slots:
                if v is not None:
                    v.execute()
        self._draw_portraits(surf)
        # 对话框(前 60 帧渐高; op18 可关, Gui.cpp:835)
        if getattr(vm, "text_box_visible", True):
            height = (
                BOX_H
                if vm.timer >= BOX_FADEIN_FRAMES
                else vm.timer * BOX_H // BOX_FADEIN_FRAMES
            )
            if height > 0:
                box = pygame.transform.scale(
                    self._grad.subsurface((0, 0, 1, height)),
                    (BOX_X1 - BOX_X0, height),
                )
                surf.blit(box, (BOX_X0, BOX_Y))
        # 对话两行 + 打字机 reveal
        for i, line in enumerate(vm.dialogue_lines):
            if line.visible and line.shown_text:
                color = TEXT_COLORS_A[line.color & 3]
                self._blit_text(
                    surf, line.shown_text, color, (TEXT_X, TEXT_Y0 + i * TEXT_LINE_H)
                )
        # Boss 名(TEXT_INTRODUCE), 右对齐在对话框上方
        for i, line in enumerate(vm.intro_lines):
            if line.visible and line.shown_text:
                color = TEXT_COLORS_A[line.color & 3]
                self._blit_text(
                    surf,
                    line.shown_text,
                    color,
                    (INTRO_RIGHT_X, INTRO_Y0 + i * INTRO_LINE_H),
                    right=True,
                )
        # 推进提示: 停在 PAUSE 且当前行已全部显示时, 右下角画闪烁箭头
        if vm.instr_idx < len(vm.msg_file.messages[vm.current_msg_idx]):
            if (
                vm.msg_file.messages[vm.current_msg_idx][vm.instr_idx].opcode
                == MsgOpcode.PAUSE
            ):
                lines_done = all(
                    (not ln.visible) or ln.reveal >= len(ln.text)
                    for ln in vm.dialogue_lines
                )
                if lines_done and (vm.timer // 16) % 2 == 0:
                    pygame.draw.polygon(
                        surf,
                        (255, 255, 255),
                        [
                            (BOX_X1 - 14, BOX_Y + BOX_H - 12),
                            (BOX_X1 - 6, BOX_Y + BOX_H - 12),
                            (BOX_X1 - 10, BOX_Y + BOX_H - 5),
                        ],
                    )
