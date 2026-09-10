"""msg 对话执行器的单元测试(合成 msg, 不依赖真实游戏数据)。"""

from __future__ import annotations

from touhou.engine.msg import (
    MsgExecutor,
    MsgInput,
    MsgMusicChange,
    MsgMusicFadeout,
    MsgNextLevel,
    MsgStageResults,
)
from touhou.schemas.msg import (
    AllowSkip,
    AppearEnemy,
    ChangeFace,
    Delete,
    Dialogue,
    FadeoutMusic,
    Freeze,
    MsgFile,
    Music,
    NextLevel,
    Pause,
    ShowPortrait,
    StageResults,
    Switch,
    TextIntroduce,
)

_Z = MsgInput(advance_pressed=True)
_SKIP = MsgInput(skip_held=True)


def _vm(*messages: tuple) -> MsgExecutor:
    """造一个执行器: 每个参数是一条消息的指令序列(自带 Delete 结尾)。"""
    return MsgExecutor(MsgFile(messages=[tuple(m) for m in messages]))


def _step_n(vm: MsgExecutor, n: int, inp: MsgInput | None = None) -> None:
    for _ in range(n):
        vm.step(inp)


def test_dialogue_and_pause_advance() -> None:
    """对话行落位 + PAUSE: Z 未满 12 帧不响应, 停满后 Z 提前结束。"""
    vm = _vm(
        (
            Dialogue(0, 1, 0, "一行目"),
            Pause(1, duration=100),
            Dialogue(2, 0, 1, "二行目"),
            Delete(3),
        )
    )
    vm.read(0)
    assert vm.active and vm.msg_wait()
    vm.step()  # time0: Dialogue 落位, timer→1
    assert vm.dialogue_lines[0].visible
    assert vm.dialogue_lines[0].text == "一行目"
    vm.step(_Z)  # PAUSE 第 1 帧: 未满 12 帧, Z 不响应
    assert vm.active and not vm.dialogue_lines[1].visible
    _step_n(vm, 11)  # 停满 12 帧
    vm.step(_Z)  # Z 提前结束: 离开 PAUSE(到点指令下一帧才执行)
    assert not vm.dialogue_lines[1].visible
    vm.step()  # 二行目落位
    assert vm.dialogue_lines[1].text == "二行目"
    vm.step()
    vm.step()  # Delete → 消息结束
    assert not vm.active
    assert not vm.msg_wait()
    assert not vm.has_current_msg_idx()


def test_pause_duration_expires_without_input() -> None:
    """PAUSE 无输入时数满 duration 帧自动前进。"""
    vm = _vm((Pause(0, duration=30), Delete(1)))
    vm.read(0)
    _step_n(vm, 30)
    assert vm.active  # 30 帧都在 PAUSE 上
    vm.step()  # 时长到: 离开 PAUSE(Delete 时刻未到, 仍活动)
    assert vm.active
    vm.step()  # Delete → 消息结束
    assert not vm.active


def test_new_top_line_clears_second_line() -> None:
    """新顶行(line 0)把第 2 行清掉(RunMsg 语义); 打字机逐字推进。"""
    vm = _vm(
        (
            Dialogue(0, 0, 0, "甲乙"),
            Dialogue(1, 0, 1, "丙丁"),
            Dialogue(2, 0, 0, "戊"),
            Delete(9),
        )
    )
    vm.read(0)
    vm.step()
    vm.step()
    assert vm.dialogue_lines[1].text == "丙丁"
    vm.step()
    assert vm.dialogue_lines[0].text == "戊"
    assert not vm.dialogue_lines[1].visible  # 新顶行清掉第 2 行
    _step_n(vm, 2)  # 打字机: 每 2 帧 1 字
    assert vm.dialogue_lines[0].reveal == 1
    assert vm.dialogue_lines[0].shown_text == "戊"[:1]


def test_appear_enemy_releases_msg_wait_one_frame() -> None:
    """APPEAR_ENEMY 放行窗: 执行的当帧 msg_wait 放行, 次帧恢复停轴。"""
    vm = _vm((Dialogue(0, 0, 0, "x"), AppearEnemy(1), Pause(2, 60), Delete(99)))
    vm.read(0)
    vm.step()  # Dialogue, timer→1
    assert vm.msg_wait()
    vm.step()  # AppearEnemy 执行: ignore_wait_counter=1 → 当帧放行
    assert not vm.msg_wait()
    vm.step()  # 次帧: 计数减完, 仍在 PAUSE → 恢复停轴
    assert vm.msg_wait()


def test_portrait_and_switch_states() -> None:
    """立绘显隐/换脸/亮暗(SWITCH interrupt 3=亮 4=暗 5=退场)以数据透出。"""
    vm = _vm(
        (
            ShowPortrait(0, 0, 3),
            ChangeFace(1, 0, 5),
            Switch(2, idx=0, interrupt=3),
            Switch(3, idx=1, interrupt=4),
            Delete(4),
        )
    )
    vm.read(0)
    vm.step()
    p = vm.portraits[0]
    assert p.visible and p.face == 3
    vm.step()
    assert p.face == 5
    vm.step()
    assert p.speaking and not p.exited
    vm.portraits[1].pending_interrupt = 4
    assert not vm.portraits[1].speaking
    vm.portraits[1].pending_interrupt = 5
    assert vm.portraits[1].exited


def test_switch_beyond_portraits_targets_text_line() -> None:
    """SWITCH idx >= num_portraits → 文本行 idx-num_portraits 的 interrupt。"""
    vm = _vm((Switch(0, idx=2, interrupt=1), Delete(1)))
    vm.read(0)
    vm.step()
    assert vm.dialogue_lines[0].pending_interrupt == 1


def test_skip_held_fast_forwards() -> None:
    """Ctrl 按住(可跳过): 到点指令一帧连跑 + PAUSE 不停 + 前 60 帧淡入跳过。"""
    vm = _vm(
        (
            Dialogue(0, 0, 0, "x"),
            Pause(1, duration=600),
            Dialogue(70, 0, 1, "y"),
            Delete(71),
        )
    )
    vm.read(0)
    vm.step(_SKIP)  # Dialogue + PAUSE 被 Ctrl 直接跳过, timer 拉到 60
    assert vm.timer == 60
    vm.step(_SKIP)
    vm.step(_SKIP)
    vm.step(_SKIP)
    vm.step(_SKIP)  # timer 到 70 → 二行目
    assert vm.dialogue_lines[1].text == "y"


def test_allow_skip_zero_disables_skip() -> None:
    """ALLOW_SKIP(0) 后 Ctrl 不再快进 PAUSE。"""
    vm = _vm((AllowSkip(0, 0), Pause(1, duration=30), Delete(2)))
    vm.read(0)
    vm.step(_SKIP)
    assert vm.timer == 1
    _step_n(vm, 30, _SKIP)  # 不可跳过: PAUSE 老实数满 30 帧
    assert vm.active
    vm.step(_SKIP)  # 时长到: 离开 PAUSE(Delete 时刻未到, 仍活动)
    assert vm.active
    vm.step(_SKIP)
    assert not vm.active


def test_freeze_stays_active() -> None:
    """FREEZE 永久停在该指令, 消息保持活动。"""
    vm = _vm((Freeze(0), Delete(1)))
    vm.read(0)
    _step_n(vm, 10)
    assert vm.active and vm.msg_wait()


def test_stage_results_event() -> None:
    """STAGERESULTS: finished_stage 置 1 + 透出 MsgStageResults。"""
    vm = _vm((StageResults(0), Delete(1)))
    vm.read(0)
    vm.step()
    assert vm.finished_stage == 1
    assert vm.take_events() == [MsgStageResults()]
    assert vm.take_events() == []  # 取后即清


def test_next_level_event_and_gating() -> None:
    """NEXT_LEVEL: msg 置 -2(消息结束但门控保持, 时间轴放行) + 透出事件。"""
    vm = _vm((NextLevel(0), Delete(1)))
    vm.read(0)
    assert vm.step() is False
    assert vm.current_msg_idx == -2
    assert not vm.active
    assert vm.has_current_msg_idx()  # -2 仍算门控(世界保持冻结射击)
    assert not vm.msg_wait()  # 时间轴放行
    assert vm.take_events() == [MsgNextLevel()]
    assert vm.step() is False  # 非活动消息 step 直接 False


def test_music_events() -> None:
    """MUSIC/FADEOUT_MUSIC 透出切曲/淡出事件。"""
    vm = _vm((Music(0, 5), FadeoutMusic(1), Delete(2)))
    vm.read(0)
    vm.step()
    vm.step()
    assert vm.take_events() == [MsgMusicChange(5), MsgMusicFadeout()]


def test_text_introduce_lands_on_intro_lines() -> None:
    """TEXT_INTRODUCE 落介绍行(与对话行分槽)。"""
    vm = _vm((TextIntroduce(0, 2, 1, "一面"), Delete(1)))
    vm.read(0)
    vm.step()
    assert vm.intro_lines[1].text == "一面"
    assert not vm.dialogue_lines[1].visible


def test_read_resets_and_out_of_range_noop() -> None:
    """Read 越界无操作; 正常 read 把 VM 清零重来(立绘/行/计时/可跳过)。"""
    vm = _vm(
        (Dialogue(0, 0, 0, "a"), Delete(1)),
        (Dialogue(0, 0, 0, "b"), Delete(1)),
    )
    vm.read(0)
    vm.portraits[0].visible = True
    vm.dialogue_skippable = 0
    vm.read(99)  # 越界: 无操作
    assert vm.current_msg_idx == 0
    vm.step()
    assert vm.dialogue_lines[0].text == "a"
    vm.read(1)  # 清零重来
    assert vm.current_msg_idx == 1
    assert not vm.portraits[0].visible
    assert vm.dialogue_skippable == 1
    assert vm.timer == 0
    vm.step()
    assert vm.dialogue_lines[0].text == "b"


def test_inactive_step_is_noop() -> None:
    """未 read 的执行器 step 直接 False, 无事件。"""
    vm = _vm((Delete(0),))
    assert vm.step(_Z) is False
    assert vm.take_events() == []
