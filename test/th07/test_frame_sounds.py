"""frame_sounds SE 透出测试: 敌击坠/自机撞弹/暂停音 (settle 订阅 + world 直出)。

SE 号出处: 敌爆 i%2+2 (EnemyManager.cpp:1015), 撞弹 SOUND_PICHUN=4
(Player.cpp:1237 Player::Die), 暂停 SOUND_PAUSED=37 (GameManager.cpp:144);
槽位 → wav 映射见 schemas/sound.py (g_SFXList, SoundPlayer.cpp:14-77)。
"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.engine.player import PlayerState
from touhou.schemas.sound import SOUND_EFFECTS

from .conftest import needs_data


def test_se_table_mapping() -> None:
    """本单用到的 SE 槽位映射到正确 wav(映射错=无声)。"""
    assert SOUND_EFFECTS[2].file_name == "se_enep00.wav"  # 敌爆 A
    assert SOUND_EFFECTS[3].file_name == "se_enep00.wav"  # 敌爆 B(低声压档)
    assert SOUND_EFFECTS[4].file_name == "se_pldead00.wav"  # 撞弹
    assert SOUND_EFFECTS[37].file_name == "se_pause.wav"  # 暂停
    assert SOUND_EFFECTS[7].file_name == "se_tan00.wav"  # 结界破 A(既有)
    assert SOUND_EFFECTS[33].file_name == "se_bonus.wav"  # 结界破 B(既有)
    assert SOUND_EFFECTS[32].file_name == "se_border.wav"  # 结界激活 A
    assert SOUND_EFFECTS[36].file_name == "se_bonus2.wav"  # 结界激活 B


@needs_data
def test_border_activate_se_on_real_stage() -> None:
    """灌满樱点 → 结界激活帧 frame_sounds 含 32+36 (Player.cpp:2138-2139)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.player import BorderState
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=1)
    for _ in range(600):  # 开局 SPAWNING 无敌, 先跑到 ALIVE
        w.tick(InputFrame())
        if w.player.state == PlayerState.ALIVE:
            break
    w.add_cherry_plus(50000)  # 樱点灌满 → READY
    assert w.player.border.has_border == BorderState.READY
    w.tick(InputFrame())
    assert w.player.border.active
    assert 32 in w.frame_sounds and 36 in w.frame_sounds


@needs_data
def test_enemy_death_se_on_real_stage() -> None:
    """真一面自动射击: 击落杂鱼的帧 frame_sounds 含敌爆音 2/3。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=1)
    w.th07.lives = 99
    heard: set[int] = set()
    for _ in range(3600):
        w.tick(InputFrame(held=frozenset({Button.SHOT})))
        heard.update(w.frame_sounds)
        if heard & {2, 3}:
            break
    assert heard & {2, 3}, "击落杂鱼必须有敌爆音"


@needs_data
def test_player_death_se_on_real_stage() -> None:
    """真一面站着挨打: 撞弹死亡帧 frame_sounds 含 4 (se_pldead00)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42, difficulty=3)
    heard: set[int] = set()
    for _ in range(3600):
        w.tick(InputFrame())
        heard.update(w.frame_sounds)
        if 4 in heard:
            break
    assert 4 in heard, "自机撞弹必须有 SOUND_PICHUN"
