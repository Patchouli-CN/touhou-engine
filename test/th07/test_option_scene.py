"""Option 设置画面状态机 + 配置存取的 headless 测试(无数据: VM 无脚本, 状态机照跑)。"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.games.th07.config import (
    MUSIC_MIDI,
    MUSIC_OFF,
    MUSIC_WAV,
    Th07Config,
    load_config,
    save_config,
)
from touhou.games.th07.view.menu_vms import MenuVmSet
from touhou.games.th07.view.option import OptionScene
from touhou.games.th07.view.scene import Scene

from .conftest import needs_data

_IDLE = InputFrame()


def _press(*btns: Button) -> InputFrame:
    s = frozenset(btns)
    return InputFrame(held=s, pressed=s)


def _hold(*btns: Button) -> InputFrame:
    return InputFrame(held=frozenset(btns))


class _Marker(Scene):
    """next_scene 落点标记。"""

    def step(self, inp: InputFrame) -> None:
        pass

    def snapshot(self):
        raise NotImplementedError

    def next_scene(self):
        return None


def _scene(
    config: Th07Config | None = None,
    vm_set: MenuVmSet | None = None,
    **kwargs,
) -> OptionScene:
    marker = _Marker()
    scene = OptionScene(
        config or Th07Config(),
        vm_set or MenuVmSet(None),
        on_exit=lambda: marker,
        **kwargs,
    )
    scene._marker = marker
    return scene


def _step(scene: OptionScene, inp: InputFrame = _IDLE, n: int = 1) -> None:
    for _ in range(n):
        scene.step(inp)


def _enter_options(scene: OptionScene) -> None:
    """30 帧转场 + INIT 帧 + 4 帧输入门(MainMenu.cpp:454/588)。"""
    _step(scene, _IDLE, 35)


# ---- 配置存取 ----
def test_config_roundtrip(tmp_path) -> None:
    """改几项存读回来一致; 未提到的字段保持默认。"""
    path = tmp_path / "config.json"
    cfg = Th07Config(life_count=4, music_mode=MUSIC_OFF, windowed=1, slow_mode=1)
    save_config(cfg, path)
    loaded = load_config(path)
    assert (loaded.life_count, loaded.music_mode) == (4, MUSIC_OFF)
    assert (loaded.windowed, loaded.slow_mode) == (1, 1)
    assert loaded.play_sounds == 1  # 默认
    assert loaded.bomb_count == 3


def test_config_missing_and_corrupt_fall_back(tmp_path) -> None:
    """文件缺失/坏 JSON/非对象 → 全默认(Supervisor.cpp:1167 init 分支)。"""
    assert load_config(tmp_path / "nope.json") == Th07Config()
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    assert load_config(bad) == Th07Config()
    bad.write_bytes(b"[1, 2]")
    assert load_config(bad) == Th07Config()


def test_config_out_of_range_resets_all(tmp_path) -> None:
    """任一字段越界/版本不对 → 整组回退默认(Supervisor.cpp:1221-1236)。"""
    path = tmp_path / "config.json"
    save_config(Th07Config(music_mode=MUSIC_MIDI), path)
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"life_count": 2', '"life_count": 9'), "utf-8")
    loaded = load_config(path)
    assert loaded == Th07Config()  # music_mode 也被带回默认
    path.write_text(raw.replace("458754", "1"), "utf-8")  # version 0x70002
    assert load_config(path) == Th07Config()


# ---- 转场与输入门 ----
def test_transition_takes_30_frames() -> None:
    """确认后 30 帧转场(PREINPUT_OPTIONS), 第 31 帧才进 option 态。"""
    scene = _scene()
    _step(scene, _IDLE, 30)
    assert scene._substate == 0
    scene.step(_IDLE)
    assert scene._substate == 1
    assert scene.cursor == 0


def test_input_gate_first_4_frames() -> None:
    """进 option 态前 4 帧(stateTimer<4)左右调档/确认/取消全无效。"""
    scene = _scene()
    _step(scene, _IDLE, 32)  # 转场 30 + 切换帧 + INIT(stateTimer 0→1)
    _step(scene, _press(Button.RIGHT), 3)  # stateTimer 1..3, 被门挡
    assert scene._config.life_count == 2
    scene.step(_press(Button.RIGHT))  # stateTimer=4, 生效
    assert scene._config.life_count == 3


# ---- 光标与调档 ----
def test_cursor_vertical_wrap() -> None:
    """9 项上下环绕 + 移动音(MainMenu.cpp:2407-2442)。"""
    scene = _scene()
    _enter_options(scene)
    scene.step(_press(Button.UP))
    assert scene.cursor == 8  # 0 → Exit(环绕)
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 0
    sounds = scene.drain_sounds()
    assert sounds.count(12) == 2  # SOUND_MOVE_MENU


def test_left_right_adjust_and_wrap() -> None:
    """残机档: 左 2→1→0→4(0 回顶档); 右 4→0(顶档回 0)(MainMenu.cpp:597-606/681-690)。"""
    scene = _scene()
    _enter_options(scene)
    for expect in (1, 0, 4):
        scene.step(_press(Button.LEFT))
        assert scene._config.life_count == expect
    scene.step(_press(Button.RIGHT))
    assert scene._config.life_count == 0
    assert 12 in scene.drain_sounds()


def test_adjust_only_on_value_items() -> None:
    """Reset/KeyConfig/Exit 项不吃左右(C++ default 分支跳音效)。"""
    scene = _scene()
    _enter_options(scene)
    before = scene._config
    for item in (6, 7, 8):
        scene.cursor = item
        scene.step(_press(Button.LEFT))
        scene.step(_press(Button.RIGHT))
    assert before == Th07Config()
    assert 12 not in scene.drain_sounds()


def test_eighth_repeat_adjust() -> None:
    """按住右键: 32 帧起每 8 帧重复调档(Supervisor.cpp:177-196)。"""
    scene = _scene()
    _enter_options(scene)
    scene.step(_press(Button.RIGHT))  # 沿: 2→3
    assert scene._config.life_count == 3
    _step(scene, _hold(Button.RIGHT), 32)
    assert scene._config.life_count == 3  # 还没到重复点
    scene.step(_hold(Button.RIGHT))
    assert scene._config.life_count == 4  # 第一次重复
    _step(scene, _hold(Button.RIGHT), 8)
    assert scene._config.life_count == 0  # 环绕回 0


def test_play_sounds_toggle_notifies() -> None:
    """効果音项调档触发 on_config_changed(SE 开关即时生效接缝)。"""
    seen: list[Th07Config] = []
    scene = _scene(on_config_changed=seen.append)
    _enter_options(scene)
    scene.cursor = 3  # PLAY_SFX
    scene.step(_press(Button.RIGHT))
    assert scene._config.play_sounds == 0
    assert seen == [scene._config]


# ---- 确认/取消/离场 ----
def test_reset_item_restores_defaults() -> None:
    """Reset: 残机/炸弹/BGM/効果音/低速回默认, 不动色数与窗口(MainMenu.cpp:766-774)。"""
    cfg = Th07Config(
        life_count=0,
        bomb_count=0,
        music_mode=MUSIC_OFF,
        play_sounds=0,
        slow_mode=1,
        color_mode16bit=1,
        windowed=1,
    )
    scene = _scene(config=cfg)
    _enter_options(scene)
    scene.cursor = 6
    scene.step(_press(Button.SHOT))
    assert (cfg.life_count, cfg.bomb_count) == (2, 3)
    assert (cfg.music_mode, cfg.play_sounds, cfg.slow_mode) == (MUSIC_WAV, 1, 0)
    assert (cfg.color_mode16bit, cfg.windowed) == (1, 1)  # 不在重置清单
    assert 10 in scene.drain_sounds()  # SOUND_SELECT
    assert not scene.done


def test_key_config_is_followup_noop() -> None:
    """KeyConfig: 确认只有选择音, 转场留待 KeyConfig 单(MainMenu.cpp:775-780)。"""
    scene = _scene()
    _enter_options(scene)
    scene.cursor = 7
    scene.step(_press(Button.SHOT))
    assert not scene.done
    assert 10 in scene.drain_sounds()


def test_exit_confirm_leaves_to_title() -> None:
    """Exit 确认: 返回音 + done, next_scene 落到装配的标题(MainMenu.cpp:781-792)。"""
    scene = _scene()
    _enter_options(scene)
    scene.cursor = 8
    scene.step(_press(Button.SHOT))
    assert scene.done
    assert 11 in scene.drain_sounds()  # SOUND_BACK
    assert scene.next_scene() is scene._marker


def test_cancel_jumps_to_exit_then_leaves() -> None:
    """取消: 光标不在 Exit 时跳 Exit; 在 Exit 上再取消直接回主菜单(:796-811)。"""
    scene = _scene()
    _enter_options(scene)
    scene.step(_press(Button.BOMB))
    assert scene.cursor == 8
    assert not scene.done
    scene.step(_press(Button.BOMB))
    assert scene.done


def test_idle_timeout_leaves() -> None:
    """无操作 3600 帧自动回主菜单(:757-760)。"""
    scene = _scene()
    _enter_options(scene)
    _step(scene, _IDLE, 3600)
    assert scene.done


def test_any_input_resets_idle() -> None:
    """有输入 idle 计数清零(:752-755)。"""
    scene = _scene()
    _enter_options(scene)
    _step(scene, _IDLE, 3000)
    scene.step(_press(Button.DOWN))
    _step(scene, _IDLE, 3000)
    assert not scene.done


# ---- 真数据: 标签/值指示贴图 ----
@needs_data
def test_real_data_labels_and_values() -> None:
    """真机: 标签 vms[9..17] 选中亮其余暗; 值指示 vms[18..33] 按 cfg 档位亮。"""
    from touhou.engine import open_archive
    from touhou.games.th07.compose import DATA_PATH

    archive = open_archive(DATA_PATH, format_name="pbg4")
    scene = _scene(vm_set=MenuVmSet(archive))
    _enter_options(scene)
    vms = scene._vm_set.vms
    # 标签: 光标项亮(base), 其余暗(base+1)(MainMenu.cpp:487-494)
    for i in range(9):
        w = vms[9 + i]
        assert w.vm.active_sprite_idx == w.base_sprite_idx + (0 if i == 0 else 1)
    # 残机值指示: life_count=2 → vms[20] 亮, 18/19/21/22 暗(:528-536)
    for i in range(5):
        w = vms[18 + i]
        assert w.vm.active_sprite_idx == w.base_sprite_idx + (0 if i == 2 else 1)
    # 调一档 → 值指示次帧刷新(C++ 指示在调档前刷新, 同序) → vms[21] 亮
    scene.step(_press(Button.RIGHT))
    scene.step(_IDLE)
    w = vms[21]
    assert w.vm.active_sprite_idx == w.base_sprite_idx
    # 快照: 标题背景垫底, option 标签/值贴图在画
    snap = scene.snapshot()
    assert snap.sprites[0].image == "title00.jpg"
    assert any(s.image.startswith("title01.anm:") for s in snap.sprites)
    assert snap.texts  # 说明文字(プレイヤーの初期数を…)
