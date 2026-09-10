"""ECL 时间轴执行器: 每帧 step 一次, 生敌/msg/boss 等待全走宿主回调。

handler 按 {时间轴指令类: handler} 查表分派(与指令 VM 同形态); handler
返回 True = 停轴等(msg 未完/boss 未退场/事件无匹配)。时间轴指令类与
handler 语义是作品数据(v0/v800 布局全分叉), 由 games/thNN 侧组装
TL_HANDLERS 注入; 本模块只有推进框架。语义出处
EnemyManager::RunEclTimeline / EnemyTimeline.cpp:134-283。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...schemas.ecl import TlInstr
from ..rng import Rng
from .host import EclHost

#: 时间轴指令类 → handler(返回 True = 停轴等一帧); 指令参数按 Any 收(同指令 VM)
TlHandler = Callable[["TimelineRunner", Any], "bool | None"]


class TimelineRunner:
    """一条时间轴的执行器; 生敌门控/坐标随机在本层, 敌人本体归宿主。"""

    def __init__(
        self,
        timeline: tuple[TlInstr, ...],
        host: EclHost,
        rng: Rng,
        handlers: Mapping[type[TlInstr], TlHandler],
    ) -> None:
        self.timeline = timeline
        self.host = host
        self.rng = rng
        self.handlers = handlers
        self.time = 0
        self.idx = 0  # 当前指令下标(模拟 timelineInstr 指针)

    @property
    def done(self) -> bool:
        """时间轴跑完(越界或遇到 time<0 的终止记录)。"""
        return self.idx >= len(self.timeline) or self.timeline[self.idx].time < 0

    def _spawn_gated(self) -> bool:
        """生敌门控: boss 在场或全局抑制时跳过。"""
        if self.host.timeline_spawns_suppressed():
            return False
        return not self.host.boss_present()

    def step(self) -> None:
        """推进一帧: 执行所有到点指令, 停轴指令冻结 time。"""
        while not self.done:
            ins = self.timeline[self.idx]
            if self.time == ins.time:
                # 难度掩码过滤(v800 时间轴指令带掩码, EnemyTimeline.cpp:131-132)
                dm = getattr(ins, "difficulty_mask", None)
                if dm is not None and (dm & (1 << self.host.difficulty)) == 0:
                    self.idx += 1
                    continue
                if self.handlers[type(ins)](self, ins):
                    self.time -= 1  # 底部 time++ 抵消, 时间轴停住
                    break
            elif self.time < ins.time:
                break
            self.idx += 1
        self.time += 1


__all__ = ["TimelineRunner", "TlHandler"]
