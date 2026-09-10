"""结局(.end)逐帧播放器: 纯逻辑状态机, 渲染/放音由 view 消费透出数据。

tick() 一帧 = OnUpdate 的一次 ParseEndFile + OnDraw 的 FadingEffect 推进
(出处 old/touhou/engine/ending.py EndingPlayer, 对照 th07-ref Ending.cpp)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar

import msgspec

from ..schemas.ending import (
    Bg,
    BgScroll,
    BgY,
    ClearFaces,
    End,
    Face,
    Fade,
    Instruction,
    LineSpeed,
    Load,
    Music,
    MusicFade,
    Text,
    TextColor,
    Wait,
    WaitReset,
    parse_end,
)

# fadeType (Ending.hpp; ParseEndFile @0..@3 → 1..4)
FADE_OUT_BLACK = 1  # @0: 黑幕淡出(从黑场进入)
FADE_IN_BLACK = 2  # @1: 黑幕淡入(渐黑, 停在全黑)
FADE_OUT_WHITE = 3  # @2: 白幕淡出
FADE_IN_WHITE = 4  # @3: 白幕淡入(渐白, 停在全白)


class EndingLine(msgspec.Struct, frozen=True):
    """一行已显示文本 (DrawVmTextFmt 画进 sprites[timesFileParsed])。"""

    text: str
    color: int  # 0xRRGGBB (@c)


class EndingPlayer:
    """.end 指令流的逐帧播放器。

    透出: bg_name/bg_y(背景与滚动) / texts(已显示文本行) / faces(立绘槽位)
    / fade_overlay()(淡色覆盖) / music_events / done(@z 或 @F 失败)。
    advance_held = 确认键按住(行间隔换 topLineDelay, ParseEndFile:399-408);
    advance_pressed = 确认键按下沿(minWait 耗尽后提前结束等待, :199-205/227-234)。
    """

    def __init__(
        self,
        data: bytes | Sequence[Instruction],
        loader: Callable[[str], bytes | None] | None = None,
    ) -> None:
        self._ops = list(parse_end(data).ops) if isinstance(data, bytes) else list(data)
        self._loader = loader  # @F 续载用: (archive 裸文件名) -> bytes | None
        self._pc = 0
        # ParseEndFile 计时器/参数 (LoadEnding: line2Delay=8, timer2=0)
        self.timer2 = 0
        self.min_wait = 0  # minWaitFrames (文本行/@w)
        self.timer3 = 0
        self.min_wait_reset = 0  # minWaitResetFrames (@r)
        self.line2_delay = 8
        self.top_line_delay = 8
        self.text_color = 0xFFFFFF
        # 背景 (backgroundPos.y/backgroundScrollSpeed)
        self.bg_name: str | None = None
        self.bg_y = 0.0
        self.bg_scroll = 0.0
        # 立绘槽位: vm_idx → (anm_script_idx, anm_sprite_idx) (@a)
        self.faces: dict[int, tuple[int, int]] = {}
        self.faces_version = 0  # faces 变更计数(view 据此重建/清 VM)
        self.texts: list[EndingLine] = []
        # 淡入淡出 (FadingEffect)
        self.fade_type = 0
        self.fade_frames = 0
        self.time_fading = 0
        # 音乐事件: ("play", name) / ("fadeout", seconds)
        self.music_events: list[tuple] = []
        self.done = False

    # ---- 每帧 ----
    def tick(
        self, *, advance_held: bool = False, advance_pressed: bool = False
    ) -> None:
        """推进一帧: 淡色推进(与解析停止无关) + 一次解析。"""
        if self.done:
            return
        self._advance_fade()  # OnDraw 的 FadingEffect (每帧)
        self._parse_once(advance_held=advance_held, advance_pressed=advance_pressed)

    def _advance_fade(self) -> None:
        """FadingEffect (Ending.cpp:99-165) 的计时推进; 颜色见 fade_overlay。"""
        if self.fade_type in (FADE_OUT_BLACK, FADE_OUT_WHITE):
            if self.time_fading >= self.fade_frames:
                self.fade_type = 0  # 淡出完成 → 无覆盖
            else:
                self.time_fading += 1
        elif self.fade_type in (FADE_IN_BLACK, FADE_IN_WHITE):
            if self.time_fading < self.fade_frames:
                self.time_fading += 1  # 淡入完成 → 停在不透明色

    def fade_overlay(self) -> tuple[int, int, int, int] | None:
        """本帧淡色覆盖 (r, g, b, a); None = 无覆盖 (endingFadeRectColor alpha==0)。"""
        ft = self.fade_type
        if ft == 0 or self.fade_frames <= 0:
            return None
        t, frames = self.time_fading, self.fade_frames
        if ft in (FADE_OUT_BLACK, FADE_OUT_WHITE):
            if t >= frames:
                return None
            a = 255 - t * 255 // frames
            return (0, 0, 0, a) if ft == FADE_OUT_BLACK else (255, 255, 255, a)
        a = min(255, t * 255 // frames)
        return (0, 0, 0, a) if ft == FADE_IN_BLACK else (255, 255, 255, a)

    def _scroll_bg(self) -> None:
        """ParseEndFile 的 stop 收尾 (:420-427): 背景上滚, 夹到 0 停。"""
        self.bg_y -= self.bg_scroll
        if self.bg_y <= 0.0:
            self.bg_y = 0.0
            self.bg_scroll = 0.0

    def _parse_once(self, *, advance_held: bool, advance_pressed: bool) -> None:
        # @r 等待 (timer3): 归零当帧清空文本行并继续解析 (:190-217)
        if self.timer3 > 0:
            self.timer3 -= 1
            if self.min_wait_reset > 0:
                self.min_wait_reset -= 1
            elif advance_pressed:
                self.timer3 = 0
            if self.timer3 <= 0:
                self.texts.clear()  # sprites[*].pendingInterrupt=2, timesFileParsed=0
            else:
                self._scroll_bg()
                return
        # @w/文本行等待 (timer2) (:219-236)
        if self.timer2 > 0:
            self.timer2 -= 1
            if self.min_wait > 0:
                self.min_wait -= 1
            elif advance_pressed:
                self.timer2 = 0
            self._scroll_bg()
            return
        while True:
            if self._pc >= len(self._ops):
                self.done = True  # 无 @z 兜底: 文件播完即结束
                return
            instr = self._ops[self._pc]
            self._pc += 1
            # {指令类型: handler} 分派; True = 本帧解析停(等计时/结束)
            if self._HANDLERS[type(instr)](self, instr, advance_held):
                return

    # ---- 指令 handler(返回 True = 本帧解析停) ----
    def _on_bg(self, instr: Bg, held: bool) -> bool:
        self.bg_name = instr.path
        return False

    def _on_face(self, instr: Face, held: bool) -> bool:
        self.faces[instr.vm] = (instr.script, instr.sprite)
        self.faces_version += 1
        return False

    def _on_bg_scroll(self, instr: BgScroll, held: bool) -> bool:
        self.bg_scroll = instr.dist / instr.duration if instr.duration else 0.0
        return False

    def _on_bg_y(self, instr: BgY, held: bool) -> bool:
        self.bg_y = float(instr.y)
        return False

    def _on_load(self, instr: Load, held: bool) -> bool:
        data = self._loader(instr.path) if self._loader is not None else None
        if data is None:
            self.done = True  # LoadEnding 失败 → ZUN_ERROR → 链移除
            return True
        self._ops = list(parse_end(data).ops)
        self._pc = 0
        self.line2_delay = 8  # LoadEnding 重置 (:446)
        self.timer2 = 0
        self.faces.clear()  # @F fallthrough @R (:292-297)
        self.faces_version += 1
        return False

    def _on_clear_faces(self, instr: ClearFaces, held: bool) -> bool:
        self.faces.clear()
        self.faces_version += 1
        return False

    def _on_music(self, instr: Music, held: bool) -> bool:
        self.music_events.append(("play", instr.path))
        return False

    def _on_music_fade(self, instr: MusicFade, held: bool) -> bool:
        self.music_events.append(("fadeout", instr.seconds))
        return False

    def _on_line_speed(self, instr: LineSpeed, held: bool) -> bool:
        self.line2_delay, self.top_line_delay = instr.line2_delay, instr.top_line_delay
        return False

    def _on_text_color(self, instr: TextColor, held: bool) -> bool:
        self.text_color = instr.color
        return False

    def _on_wait_reset(self, instr: WaitReset, held: bool) -> bool:
        self.timer3, self.min_wait_reset = instr.frames, instr.min_wait
        self._scroll_bg()
        return True

    def _on_wait(self, instr: Wait, held: bool) -> bool:
        self.timer2, self.min_wait = instr.frames, instr.min_wait
        self._scroll_bg()
        return True

    def _on_fade(self, instr: Fade, held: bool) -> bool:
        self.fade_type, self.time_fading, self.fade_frames = (
            instr.fade_type,
            0,
            instr.frames,
        )
        return False

    def _on_text(self, instr: Text, held: bool) -> bool:
        self.texts.append(EndingLine(instr.text, self.text_color))
        d = self.top_line_delay if held else self.line2_delay
        self.timer2 = d
        self.min_wait = d
        self._scroll_bg()
        return True

    def _on_end(self, instr: End, held: bool) -> bool:
        self.done = True
        return True

    #: 指令类 → handler(同 settle.py 的 Any 收参惯例); True = 本帧解析停
    _HANDLERS: ClassVar[dict[type, Callable[[EndingPlayer, Any, bool], bool]]]


EndingPlayer._HANDLERS = {
    Bg: EndingPlayer._on_bg,
    Face: EndingPlayer._on_face,
    BgScroll: EndingPlayer._on_bg_scroll,
    BgY: EndingPlayer._on_bg_y,
    Load: EndingPlayer._on_load,
    ClearFaces: EndingPlayer._on_clear_faces,
    Music: EndingPlayer._on_music,
    MusicFade: EndingPlayer._on_music_fade,
    LineSpeed: EndingPlayer._on_line_speed,
    TextColor: EndingPlayer._on_text_color,
    WaitReset: EndingPlayer._on_wait_reset,
    Wait: EndingPlayer._on_wait,
    Fade: EndingPlayer._on_fade,
    Text: EndingPlayer._on_text,
    End: EndingPlayer._on_end,
}
