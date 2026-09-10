"""Option 设置画面: OnUpdateOptionsMenu(MainMenu.cpp:475-818)的 scene 化。

9 项 = 初始残机/色数/BGM 模式/効果音/ウィンドウ/低速/リセット/キーコンフィグ/終了;
标签 = vms[9..17] 亮暗, 值指示 = vms[18..33] 按 cfg 每帧刷新, 与主菜单共用
同一 VM 阵列(C++ 里 Option 只是 MainMenu 的一个菜单态)。
"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import InputFrame, SceneSnapshot
from ....engine.input import Button
from ..config import MUSIC_WAV, Th07Config
from .menu_vms import (
    SE_BACK,
    SE_MOVE,
    SE_SELECT,
    MenuScene,
    MenuVmSet,
    description_texts,
)
from .scene import Scene

_BG_TITLE = "title00.jpg"  # option 叠在标题背景上(主菜单不切背景直接进入)

# 菜单项(MainMenu.hpp:53-62 MenuCursorOptions)
_OPTION_LIVES = 0
_OPTION_KEY_CONFIG = 7
_OPTION_EXIT = 8
_OPTION_COUNT = 9

# 标签 VM = vms[9..17]; 值指示 VM 分组: (首 idx, 档数, cfg 字段)(MainMenu.cpp:528-586)
_LABEL_VM_FIRST = 9
_VALUE_GROUPS = (
    (18, 5, "life_count"),
    (23, 2, "color_mode16bit"),
    (25, 3, "music_mode"),
    (28, 2, "play_sounds"),
    (30, 2, "windowed"),
    (32, 2, "slow_mode"),
)

# 左右调档表: 光标项 → (cfg 字段, 档数)(MainMenu.cpp:593-749)
_ADJUST = {
    0: ("life_count", 5),
    1: ("color_mode16bit", 2),
    2: ("music_mode", 3),
    3: ("play_sounds", 2),
    4: ("windowed", 2),
    5: ("slow_mode", 2),
}

# 说明文字(MainMenu.cpp:121-130 g_OptionsStrings, 原文 i18n.csv TH_OPTIONS_*)
_DESCRIPTIONS = (
    "プレイヤーの初期数を変更します。（初期設定　３）",
    "画面の色数を変更します。３２ＢＩＴだと最も綺麗に表示されます。",
    "ＢＧＭの再生方法を変更します。（初期設定　ＷＡＶ）",
    "効果音を再生するか選択します",
    "ウィンドウかフルスクリーンか選択します",
    "弾が多い場面でわざと処理落ちさせます(スコア、リプレイ記録不可)",
    "全て初期設定にします",
    "パッド操作のボタン配置を変更します",
    "おいそれと終了します",
)


class OptionScene(MenuScene):
    """Option 设置页: 上下移光标, 左右调档, 确认执行(Reset/KeyConfig/Exit)。"""

    def __init__(
        self,
        config: Th07Config,
        vm_set: MenuVmSet,
        *,
        on_exit: Callable[[], Scene],
        on_config_changed: Callable[[Th07Config], None] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._vm_set = vm_set
        self._on_exit = on_exit
        self._on_config_changed = on_config_changed
        self._substate = 0  # 0=转场 1=INPUT
        self._selected = -1
        self._input_delay = 0
        self._state_timer = 0
        self._idle_frames = 0
        self._frame = 0

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        if self._substate == 0:
            # 主菜单确认后 30 帧转场才进 option 态(MainMenu.cpp:453-465)
            if self._input_delay >= 30:
                self._substate = 1
                self._input_delay = 0
                self._state_timer = 0
                self.cursor = _OPTION_LIVES  # :462
            else:
                self._input_delay += 1
        else:
            self._update_options()
        self._vm_set.execute()
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = self._vm_set.sprites(_BG_TITLE)
        texts = description_texts(self._vm_set.cur_desc, _DESCRIPTIONS[self.cursor])
        return SceneSnapshot(self._frame, tuple(sprites), texts)

    def next_scene(self) -> Scene | None:
        return self._on_exit()

    # ---- option 态 (MainMenu.cpp:475-818) ----
    def _update_options(self) -> None:
        mv = self._vm_set
        if self._state_timer == 0:  # MENU_SUBSTATE_SELECT_INIT(:483-504)
            mv.interrupt_all(3)  # :486
            mv.highlight(_LABEL_VM_FIRST, _OPTION_COUNT, self.cursor)
            self._selected = -1
            # C++ 同帧落入 INPUT
        if self._move_cursor_vertical(_OPTION_COUNT):
            mv.highlight(_LABEL_VM_FIRST, _OPTION_COUNT, self.cursor)  # :509-519
        if self._selected != self.cursor:
            mv.cur_desc = mv.desc_vms[self.cursor]
            mv.cur_desc.pending_interrupt = 1
        self._selected = self.cursor
        self._refresh_values()
        if self._state_timer >= 4:  # :588-591 进场 4 帧不吃调档/确认/取消
            self._adjust()
            if self._inp.held or self._inp.pressed:
                self._idle_frames = 0  # :752-755
            if self._idle_frames >= 3600:  # :757-760 无操作自动返回
                self._leave()
            elif not self._confirm():
                self._cancel()
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _refresh_values(self) -> None:
        """值指示按 cfg 每帧刷新: 当前档亮(base), 其余暗(:528-586)。"""
        for first, count, field in _VALUE_GROUPS:
            value = getattr(self._config, field)
            for i in range(count):
                self._vm_set.set_sprite(first + i, dim=i != value)

    def _adjust(self) -> None:
        """左右调档: 环形(左: 0→顶档; 右: 顶档→0), 动了发移动音(:593-749)。"""
        item = _ADJUST.get(self.cursor)
        if item is None:
            return  # Reset/KeyConfig/Exit 不吃左右(C++ default 分支)
        field, count = item
        value = getattr(self._config, field)
        if self._move_edge(Button.LEFT):
            setattr(self._config, field, (value - 1) % count)
        elif self._move_edge(Button.RIGHT):
            setattr(self._config, field, (value + 1) % count)
        else:
            return
        self._sounds.append(SE_MOVE)
        # music_mode 变更的 StopAudio/重载标题 BGM(:617-637)由 on_config_changed 消费
        self._notify_changed()

    def _confirm(self) -> bool:
        """确认分派(:762-794); 返回 True = 按下了确认键。"""
        if not self._confirm_pressed():
            return False
        cfg = self._config
        if self.cursor == 6:  # MENU_CURSOR_OPTIONS_RESET
            cfg.life_count = 2
            cfg.bomb_count = 3
            cfg.music_mode = MUSIC_WAV
            cfg.play_sounds = 1
            cfg.slow_mode = 0  # :766-774
            self._sounds.append(SE_SELECT)
            self._notify_changed()
        elif self.cursor == _OPTION_KEY_CONFIG:
            self._sounds.append(SE_SELECT)
            # KeyConfig 页(MENU_STATE_KEY_CONFIG, OnUpdateKeyConfig:863)留待后续单
        elif self.cursor == _OPTION_EXIT:
            self._leave()
        return True

    def _cancel(self) -> None:
        """取消: 停在 Exit 上直接返回; 否则光标跳 Exit(:796-811)。"""
        if not self._cancel_pressed():
            return
        if self.cursor == _OPTION_EXIT:
            self._leave()
            return
        self._vm_set.set_sprite(_LABEL_VM_FIRST + self.cursor, dim=True)
        self.cursor = _OPTION_EXIT
        self._vm_set.set_sprite(_LABEL_VM_FIRST + self.cursor, dim=False)
        self._sounds.append(SE_BACK)

    def _leave(self) -> None:
        """回主菜单(光标停在 Option): RETURN_TO_PREINPUT(:782-792)。"""
        self._sounds.append(SE_BACK)
        self.done = True
        # C++ 在此对比进场 cfg 快照, 色数/窗口模式变更要重启进程才生效
        # (EXIT_GAME_ERROR, :787-791); 本作配置落盘下次启动生效
        # (RenderBackend 协议无全屏/色深能力, 框架层 hook 留待)

    def _notify_changed(self) -> None:
        if self._on_config_changed is not None:
            self._on_config_changed(self._config)
