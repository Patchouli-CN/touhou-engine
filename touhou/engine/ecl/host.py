"""EclHost: ECL 执行器的宿主接口(抽象基类), 作品专属语义全经此注入。

engine 只实现流派通用指令(控制流/数学/变量/等待/移动插值); 弹幕/激光/
敌人管理/符卡/音效等指令在 engine 侧注册为委托 handler, 原指令透传到本
接口的对应钩子。所有钩子有安全默认实现(无操作/C 默认语义), 作品在
games/thNN 侧子类化本类, 经组合根注入。

方法清单参照旧实现 engine/ecl.py EclHost + engine/ecl_base.py 的宿主调用
点; 与旧版的差异: 旧版弹幕/激光钩子吃烹好的 props 结构, 新版透传原始指令
(烹参数是作品语义, 属 games 侧),  operand 解析助手在 EclMachine 上
(ival/fval/store_int/store_float), 宿主可直接用。
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from ...schemas.ecl import EclInstr
from .state import EnemySpawn

if TYPE_CHECKING:
    from .machine import EclMachine  # 仅类型检查期(machine 运行时依赖本模块)


class EclHost(ABC):
    """ECL 宿主接口基类: 作品在 games 侧子类化, 组合根注入。"""

    #: 当前难度(0=E 1=N 2=H 3=L), 难度掩码过滤用; 作品侧每帧同步
    difficulty: int = 1

    # ---- 特殊变量透出(C GetVar/GetVarValue 的变量表 default 之外部分) ----

    def read_special_int(self, m: EclMachine, var_id: int) -> int:
        """读非局部槽的 int 变量; 默认原样返回 var_id(C default 分支)。"""
        return var_id

    def write_special_int(self, m: EclMachine, var_id: int, value: int) -> None:
        """写非局部槽的 int 变量; 默认丢弃(C 写进指令内存, 无意义)。"""

    def read_special_float(self, m: EclMachine, var_id: int) -> float:
        """读非局部槽的 float 变量; 默认按 f32 原值返回(C default 分支)。"""
        return float(var_id)

    def write_special_float(self, m: EclMachine, var_id: int, value: float) -> None:
        """写非局部槽的 float 变量; 默认丢弃。"""

    # ---- 帧流程 ----

    def skip_instr(self, m: EclMachine, instr: EclInstr) -> bool:
        """难度掩码过滤: 指令掩码不含当前难度位则跳过(掩码需扩展语义的作品覆写)。"""
        # th07 语义 EclManager.cpp RunEcl 主循环; th08 掩码需含 override 位,
        # 由作品宿主覆写(出处 old/touhou/engine/ecl_base.py _difficulty_skip)
        return (instr.skip_difficulty & (1 << self.difficulty)) == 0

    def player_position(self, m: EclMachine) -> tuple[float, float, float]:
        """自机位置(朝自机移动/逃角用); 默认场心底部。"""
        return (192.0, 400.0, 0.0)

    def on_sub_call(self, m: EclMachine) -> None:
        """SUB_CALL 进新 sub 后的交接钩子(如全局变量快照拷入上下文)。"""
        # 旧实现内联在 _op_sub_call: ctx.args.global_ints = list(world.global_ints)

    def on_auto_shoot(self, m: EclMachine) -> None:
        """自动射击计时到点(shoot_interval 走满一周期)。"""
        # 旧实现 th07 用持久 bullet_props 发射, th08 重新派发 pending 指令

    def run_ex_instr(self, m: EclMachine, idx: int, instr: EclInstr | None) -> bool:
        """Ex 指令(boss 特技)分发; 返回 True = 宿主已处理。"""
        return False

    # ---- 生敌(时间轴与 SPAWN_ENEMY_ABS/REL 指令共用) ----

    def spawn_enemy(self, spawn: EnemySpawn, m: EclMachine | None) -> object | None:
        """生成一个敌人脚本实例; 返回不透明句柄(失败 None)。m 是发起机(时间轴生敌为 None)。"""
        return None

    def spawn_familiar(self, m: EclMachine, instr: EclInstr) -> None:
        """使魔系生敌(SpawnFamiliar*, 参数面与普通生敌不同, 透传原指令)。"""

    def clear_enemies(self, m: EclMachine, instr: EclInstr) -> None:
        """清敌(REMOVE_ALL_ENEMIES, 透传原指令)。"""

    # ---- 弹幕/激光(原指令透传) ----

    def spawn_bullets(self, m: EclMachine, instr: EclInstr) -> None:
        """弹幕发射(SpawnBulletPattern/SpawnPrevBulletPattern)。"""

    def bullet_setup(self, m: EclMachine, instr: EclInstr) -> None:
        """弹幕参数配置(InitBulletCmd/SetShootInterval/SetBulletSound/SetShootOffset 等)。"""

    def clear_bullets(self, m: EclMachine, instr: EclInstr) -> None:
        """清弹(RemoveAllBullets/ClearBulletsForTransition/RemoveBulletsRadius)。"""

    def spawn_laser(self, m: EclMachine, instr: EclInstr) -> None:
        """激光发射(SpawnLaserPattern 系)。"""

    def laser_control(self, m: EclMachine, instr: EclInstr) -> None:
        """激光控制(SetLaserIdx/角度/位置/停止/测试等 12 种)。"""

    # ---- 敌人配置/道具/音效 ----

    def enemy_config(self, m: EclMachine, instr: EclInstr) -> None:
        """敌人状态配置(anm/判定盒/标志位/回调登记/掉落/特效等, 透传原指令)。"""

    def spawn_items(self, m: EclMachine, instr: EclInstr) -> None:
        """道具掉落(SpawnItem/SpawnItems/SpawnPointItems, 透传原指令)。"""

    def play_sound(self, m: EclMachine, sound_id: int) -> None:
        """播放音效(PlaySound, 已解析的操作数)。"""

    # ---- boss/符卡/作品机制 ----

    def boss_control(self, m: EclMachine, instr: EclInstr) -> None:
        """boss/符卡/作品机制指令(SetBoss/BeginSpellcard/时刻/樱点等, 透传原指令)。"""

    def get_boss_int(self, m: EclMachine, instr: EclInstr) -> int | None:
        """以 boss_idx 号 boss 为上下文读 int 变量(GetBossInt); None = 无该 boss。"""
        # C 语义是换上下文读 boss 机器的局部变量(EclManager.cpp:998-1002)
        return None

    def get_boss_float(self, m: EclMachine, instr: EclInstr) -> float | None:
        """GetBossInt 的 float 版; None = 无该 boss。"""
        return None

    def run_pending_sub(self, m: EclMachine, slot: int) -> bool:
        """Pending 槽位压栈调 sub(RunPendingSub, v800); 返回 True = 已进 sub。"""
        return False

    def call_sub_on_boss(self, m: EclMachine, boss_idx: int, sub_id: int) -> None:
        """让指定 boss 压栈调 sub(CallSubOnBoss, v800)。"""

    def set_child_context(self, m: EclMachine, slot: int, sub_id: int) -> None:
        """安装/释放 child 上下文块(SetChildContext, v800)。"""

    # ---- 时间轴 ----

    def boss_present(self) -> bool:
        """有 boss 在场(时间轴生敌门控)。"""
        return False

    def boss_active(self, idx: int) -> bool:
        """Idx 号 boss 仍在场(等 boss 退场用)。"""
        return False

    def timeline_spawns_suppressed(self) -> bool:
        """时间轴生敌被全局抑制(v800 的 SuppressTimelineSpawns 置位)。"""
        return False

    def set_boss_interrupt(self, boss_idx: int, interrupt: int) -> None:
        """设 boss 的 run_interrupt(v0 时间轴 op10 / SetBossRunInterrupt 指令)。"""

    def set_boss_pending_sub(self, boss_idx: int, sub_id: int) -> None:
        """设 boss 的 pendingEclSubroutineIndex(v800 时间轴 op8 / SetBossPendingSub 指令)。"""

    def msg_read(self, msg_id: int) -> None:
        """读 msg(C 还会加 character*10, 交给宿主)。"""

    def msg_wait(self) -> bool:
        """True = 消息仍在显示(时间轴停住)。"""
        return False

    def set_power(self, value: int) -> None:
        """设自机火力。"""

    def consume_event(self, value: int) -> bool:
        """事件槽消费(v800): True = 有匹配(时间轴继续), False = 停轴等。"""
        # 槽本体在宿主侧(跨时间轴/敌人共享, th08 EnemyManager.timeline_event_slots)
        return True

    def emit_event(self, value: int) -> None:
        """事件槽投放(v800): 填进所有空槽。"""

    def show_retry_menu(self) -> None:
        """出 Retry 菜单(v800)。"""
