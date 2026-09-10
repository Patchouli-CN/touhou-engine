"""th07 录像: 录制(输入帧序列+逐面快照) / msgspec JSON 存取 / 回放喂输入。

原理: 同 seed + 同输入序列 → 同模拟结果(engine/rng.py 种子化, compose_world(seed=))。
文件格式自定 JSON(不兼容原版 .rpy 二进制; 原版格式事实见 ReplayManager.hpp),
存 replays/ 目录(原版 ./replay/th7_udXXXX.rpy, ReplayManager.cpp:2000)。

逐面快照 = 原版 StageReplayData(ReplayManager.hpp:13-33 每面开局全局状态)的
扩展版: 补双 rng 状态/自机/子机/炸弹场, 使从任意面起播与原局逐帧一致。
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import msgspec

from ...engine import InputFrame
from ...engine.globals import GlobalsField
from ...engine.input import Button
from .bomb import Th07BombField
from .globals import Th07Globals
from .player import OptionMachine, Th07PlayerField
from .world import Th07World

FORMAT_VERSION = 1

#: 录像目录(仓根 replays/; 原版是 exe 旁 ./replay/)
DEFAULT_REPLAY_DIR = "replays"

# 输入码位布局(原版 u16 按键位掩码, ReplayManager.cpp:62 frameNum 字段)
_BUTTON_BITS = (
    Button.UP,
    Button.DOWN,
    Button.LEFT,
    Button.RIGHT,
    Button.SHOT,
    Button.BOMB,
    Button.FOCUS,
    Button.SKIP,
)

# 玩家名上限(ReplayManager.hpp:66 name[12])
_NAME_MAX = 12


def encode_input(inp: InputFrame) -> int:
    """Held 集 → int 码。PAUSE 不进带(暂停帧 sim 不走, 不录)。"""
    code = 0
    for i, b in enumerate(_BUTTON_BITS):
        if b in inp.held:
            code |= 1 << i
    return code


def decode_input(code: int, prev_held: frozenset[Button]) -> InputFrame:
    """Int 码 → InputFrame; pressed 沿由上帧 held 推导(原版 WAS_PRESSED 同构)。"""
    held = frozenset(b for i, b in enumerate(_BUTTON_BITS) if code >> i & 1)
    return InputFrame(held=held, pressed=held - prev_held)


def _rle(codes: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for c in codes:
        if out and out[-1][0] == c:
            out[-1][1] += 1
        else:
            out.append([c, 1])
    return out


def _unrle(pairs: list[list[int]]) -> list[int]:
    codes: list[int] = []
    for c, n in pairs:
        codes.extend([c] * n)
    return codes


def _copy_fields(
    dst: msgspec.Struct, src: msgspec.Struct, *, skip: frozenset[str] = frozenset()
) -> None:
    """同型 struct 逐字段拷贝(保对象身份, 管线持有的引用不失效)。"""
    for f in msgspec.structs.fields(type(dst)):
        if f.name not in skip:
            setattr(dst, f.name, getattr(src, f.name))


class StageSnapshot(msgspec.Struct):
    """一面开局的全部可携带状态(首帧 tick 后的世界快照; StageReplayData 扩展)。"""

    frame: int
    rng_main: tuple[int, int]  # world.rng.state()
    rng_ecl: tuple[int, int]  # host 与时间轴共享的 ECL rng
    th07: Th07Globals
    globals: GlobalsField
    options: OptionMachine
    bomb: Th07BombField
    player: dict  # Th07PlayerField asdict(去掉 on_border_break 回调)
    point_items_prev_stages: int
    rand_spawn_idx: int
    rand_table_idx: int
    spellcard_began_frame: int
    catk_idx: int | None

    @classmethod
    def capture(cls, w: Th07World) -> StageSnapshot:
        """抓当前世界状态(深拷贝, 之后世界继续走不影响快照)。"""
        player = msgspec.structs.asdict(w.player)
        player.pop("on_border_break")  # 回调不可序列化; 恢复时保留世界原接线
        return cls(
            frame=w.frame,
            rng_main=w.rng.state(),
            rng_ecl=w.host.rng.state() if w.host is not None else (0, 0),
            th07=copy.deepcopy(w.th07),
            globals=copy.deepcopy(w.globals),
            options=copy.deepcopy(w.options),
            bomb=copy.deepcopy(w.bomb),
            player=player,
            point_items_prev_stages=w.point_items_prev_stages,
            rand_spawn_idx=w.rand_spawn_idx,
            rand_table_idx=w.rand_table_idx,
            spellcard_began_frame=w.spellcard_began_frame,
            catk_idx=w.catk_idx,
        )

    def apply(self, w: Th07World) -> None:
        """把快照灌回(新组的)世界: 逐字段拷贝, 管线持有的 field 引用不动。"""
        w.frame = self.frame
        w.rng.restore((self.rng_main[0], self.rng_main[1]))
        if w.host is not None:
            w.host.rng.restore((self.rng_ecl[0], self.rng_ecl[1]))
        _copy_fields(w.th07, self.th07)
        _copy_fields(w.globals, self.globals)
        _copy_fields(w.options, self.options)
        _copy_fields(w.bomb, self.bomb)
        _copy_fields(
            w.player,
            msgspec.convert(self.player, Th07PlayerField),
            skip=frozenset({"on_border_break"}),
        )
        w.point_items_prev_stages = self.point_items_prev_stages
        w.rand_spawn_idx = self.rand_spawn_idx
        w.rand_table_idx = self.rand_table_idx
        w.spellcard_began_frame = self.spellcard_began_frame
        w.catk_idx = self.catk_idx


class StageMark(msgspec.Struct):
    """一面在输入序列里的锚点: 从这面起播 = 组该面世界 + 灌快照 + 从 start_frame 续喂。"""

    stage_no: int  # 1-based(Extra=7 Phantasm=8)
    start_frame: int  # 该面首个 tick 的输入下标(快照=该 tick 后的状态)
    snapshot: StageSnapshot
    score: int = 0  # 该面结束分(列表 LastScore 列; 过面/终局时回填)


class Th07Replay(msgspec.Struct):
    """一份录像文件的内容。"""

    version: int
    name: str  # 玩家名(录制时成绩库 last_name)
    date: str  # MM/DD(ResultScreen::GetDate 口径)
    character: int  # shotTypeAndCharacter 0..5
    difficulty: int
    stage_no: int  # 起始面
    practice: bool
    seed: int  # 主 rng 种子(ECL rng 由 compose_world 派生)
    score: int  # 终局分(ReplayManager.cpp:635 data.score=guiScore)
    slowdown: float  # 原版处理落ち率; 本引擎无此概念, 恒 0.0
    stages: list[StageMark]
    inputs: list[list[int]]  # RLE [码, 连续帧数]


class ReplayRecorder:
    """录制一局: 每个喂给 world.tick 的 InputFrame 录一码, 过面自动打锚点。"""

    def __init__(self, w: Th07World, *, name: str) -> None:
        self._name = name[:_NAME_MAX]
        self._character = w.character
        self._difficulty = w.difficulty
        self._stage_no = w.stage_no
        self._practice = w.practice
        self._seed = w.rng.seed  # compose_world 已把 seed 参数烘进主 rng
        self._codes: list[int] = []
        self._marks: list[StageMark] = []
        self._cur_stage = -1

    @property
    def frames(self) -> int:
        return len(self._codes)

    def record_tick(self, w: Th07World, inp: InputFrame) -> None:
        """world.tick(inp) 之后调: 录该帧输入; 检测到换面就打锚点。"""
        self._codes.append(encode_input(inp))
        if w.stage_no != self._cur_stage:
            if self._marks:
                # 上一面结束分(过面时 guiScore 携带, ReplayManager.cpp:189-193)
                self._marks[-1].score = w.globals.gui_score
            self._marks.append(
                StageMark(
                    stage_no=w.stage_no,
                    start_frame=len(self._codes) - 1,
                    snapshot=StageSnapshot.capture(w),
                )
            )
            self._cur_stage = w.stage_no

    def finish(self, w: Th07World) -> Th07Replay:
        """对局结算时收尾成录像数据(未结束也可调, 录到哪算哪)。"""
        if self._marks:
            self._marks[-1].score = w.globals.gui_score
        return Th07Replay(
            version=FORMAT_VERSION,
            name=self._name,
            date=datetime.now().strftime("%m/%d"),
            character=self._character,
            difficulty=self._difficulty,
            stage_no=self._stage_no,
            practice=self._practice,
            seed=self._seed,
            score=w.globals.gui_score,
            slowdown=0.0,
            stages=self._marks,
            inputs=_rle(self._codes),
        )


def load_inputs(replay: Th07Replay) -> list[int]:
    """展开 RLE 输入序列。"""
    return _unrle(replay.inputs)


def save_replay(replay: Th07Replay, path: str | Path) -> Path:
    """原子落盘(同 score_store 容错风格)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(msgspec.json.encode(replay))
    tmp.replace(path)
    return path


def new_replay_path(replay_dir: str | Path = DEFAULT_REPLAY_DIR) -> Path:
    """按时间戳生成不重名路径 th7_udNNNN.json(原版 th7_udXXXX.rpy 命名风格)。"""
    replay_dir = Path(replay_dir)
    stamp = datetime.now().strftime("%y%m%d%H%M%S")
    for i in range(100):
        p = replay_dir / f"th7_ud{stamp}{i:02d}.json"
        if not p.exists():
            return p
    return replay_dir / f"th7_ud{stamp}x.json"


def load_replay(path: str | Path) -> Th07Replay:
    """读录像文件; 版本不符/内容缺损抛 ValueError。"""
    try:
        replay = msgspec.json.decode(Path(path).read_bytes(), type=Th07Replay)
    except (OSError, msgspec.DecodeError, msgspec.ValidationError) as e:
        raise ValueError(f"录像文件无法读取: {path}: {e}") from e
    if replay.version != FORMAT_VERSION:
        raise ValueError(f"录像版本不符: {path}")
    return replay


class ReplayEntry(msgspec.Struct):
    """列表画面的一行: 文件路径 + 内容 + 行首标签。"""

    path: str
    replay: Th07Replay
    label: str = "User "  # 原版 No.NN=编号槽/User=自由档(:1991/:2022), 本作只产自由档


def list_replays(replay_dir: str | Path = DEFAULT_REPLAY_DIR) -> list[ReplayEntry]:
    """扫录像目录, 按文件名序返回可读录像; 坏文件跳过(原版 ValidateReplayData 同构)。"""
    replay_dir = Path(replay_dir)
    out: list[ReplayEntry] = []
    if not replay_dir.is_dir():
        return out
    for p in sorted(replay_dir.glob("*.json")):
        try:
            out.append(ReplayEntry(str(p), load_replay(p)))
        except ValueError:
            continue
    return out
