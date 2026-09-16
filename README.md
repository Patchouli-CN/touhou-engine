<div align="center">

# 東方エンジン ～ touhou-engine

**少女祈祷中……**

![python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)
![pygame](https://img.shields.io/badge/render-pygame-green)
![msgspec](https://img.shields.io/badge/data-msgspec-orange)

![gameplay](docs/assets/gameplay.png)

*通用东方弹幕游戏框架 —— TH07《东方妖妖梦 ～ Perfect Cherry Blossom》为参考实现*

</div>

---

## 「Story」这是什么

引擎逻辑对照原版反编译逐帧移植，架构全新：World + System 管线、sim 只产
事件流、SceneSnapshot 快照协议、组合根显式装配。作品经注册表接入框架，
框架代码零改动。不再是"只能玩"的游戏，而是**可以 import 的幻想乡**：

- **完整可玩**：标题菜单 / 选人 / 6 面 + Ex + Phantasm / 符卡宣言 /
  对话立绘 / 3D 背景 / BGM·SE / 结算入榜，pygame 渲染
- **事件流 API**：headless 逐帧驱动对局，符卡/死亡/Bomb/过关全是流式
  事件——给 AI 训练、自动化、工具链用
- **观战模式**：`headless=False + auto_input=policy`，窗口里看 AI 打游戏
- **确定性录像**：种子 + 逐帧输入即可完整复现一局，Replay 菜单可播
- **官方魔改口**：`ModApi`（无敌/资源直改/自定义弹幕/画面覆盖层），
  写操作走命令队列，不摸引擎内部
- **全能力开放**（apis 层）：写操作命令入队帧边界统一应用，重任务
  `submit(fn) -> Future` 上 worker 池，读走快照/副本拿不到 world 本体

## 「How to Play」安装与运行

```bash
uv sync                     # 或: pip install -e .

python -m touhou --game th07          # 开窗口进标题画面
python -m touhou --game th07 --direct # 跳过标题直进一局(调试入口)
touhou07                              # 安装后的脚本入口亦可
```

依赖：Python ≥ 3.12, numpy, pillow, pygame, loguru, msgspec。

**操作**：方向键移动 ／ `Z` 射击·确认 ／ `X` Bomb ／ `Shift` 低速（显判定点）／
`Ctrl` 快进对话 ／ `Esc` 暂停

**游戏资源**：各作品使用对应原版数据（th07 为 `th07.dat`，BGM 用同目录
`thbgm.dat` 自动推导），运行时解包，**仓库不分发任何二进制资源**。
资源包路径在作品注册处登记（th07 见 `touhou/games/th07/compose.py` 的
`DATA_PATH`）；要改路径，改登记值，或在 API 侧传 `data_path=` 覆盖。

## 「API」像调用库一样玩东方

公共门面从包根导出：`from touhou import Game, TouhouWorld, Input, ...`

**headless AI 循环**（`Game` 细粒度门面）：

```python
from touhou import Game, GamePhase, Input

game = Game(character="ReimuA", difficulty="Normal", seed=42)
while game.phase in (GamePhase.RUNNING, GamePhase.DIALOG):
    events = game.step(Input(shoot=True, advance=True))
    for ev in events:                       # spellcard_begin/player_death/...
        print(ev.kind, ev.name or "")
print(game.score, game.lives, game.result)  # 结算后 result 非 None
```

**事件流驱动**（`TouhouWorld`，迭代即驱动，终局自动收尾）：

```python
from touhou import TouhouWorld

tw = TouhouWorld(character="ReimuA", difficulty="Normal",
                 lives=3, headless=True, seed=42)
stream = tw.run()            # 返回 TouhouWorldEventStream
for event in stream:         # 迭代到总结算(RESULT)结束
    print(event.kind, event.name or "")
print(stream.result)         # 总结算 dict

stream2 = tw.stream(policy)  # 或直接带策略开流: game -> Input
```

**观战**（窗口里看 AI 打游戏）：窗口照开但跳过标题直进游戏，每帧输入来自
策略（观测面与 `Game` 门面一致）；Esc 随时中止，暂停/续关菜单仍走键盘：

```python
def my_policy(game) -> Input:
    return Input(shoot=True, advance=True, left=(game.frame // 90) % 2 == 0)

tw = TouhouWorld(headless=False, auto_input=my_policy, seed=42)
tw.run()   # 阻塞至关窗/终局
```

观测面细节：

- `game.snapshot()` 返回当前帧不可变实体快照（player/boss/bullets/enemies/
  items/lasers，子弹与自机带判定半径 hitbox）；每帧构造有开销，按需调用。
  逐帧热循环用 `game.bullets_array()`（numpy (N,6)：x/y/vx/vy/hitbox/sprite，
  速度向量为命令作用后的真值）+ `game.player_pos`。
- 属性 `frame/score/lives/bombs/power/graze/stage/phase/result` 只读；
  `game.scene` 是上一帧的 SceneSnapshot（绘制面），`game.last_events`
  是上一帧未映射的原始引擎事件（全量）。
- `game` 参数指定作品名（不传 = 框架默认作品，由作品包
  `register_default_game` 显式声明）；`data_path=` 覆盖资源包路径。

**§2.5 三件套**（apis 是全能力开放层，线程规矩从结构上保证）：

```python
# 写操作 → 命令入队, 下一帧边界统一应用, 返回 Future(结果/异常在里面)
fut = game.queue(lambda w, ctx: w.stats())   # fn(world, ctx)
game.step(Input(shoot=True))
fut.result()

# 重任务(AI 躲弹/图像处理/批量解析) → worker 池, 只碰传入的不可变快照
fut = game.submit(heavy_ai, game.snapshot(), game.bullets_array())

# 读 → 快照/标量副本, 拿不到 world 本体
```

**魔改**（`ModApi`，官方写入口；写操作全部走上面的命令队列，下一帧边界
生效，返回 `Future`）：

```python
from touhou.apis.modding import ModApi

mods = ModApi(tw.game)
mods.player.god_mode()                # 无敌(计时每帧递减, policy 里每帧调)
mods.player.set_power(mods.player.full_power)  # 满火力(上限取自作品数值表)
mods.bullets.fire_ring(x, y, arms=24)          # 自定义环形弹幕
mods.score.add(10000)                 # 分数直加(不走计分规则)
mods.gui.circle(*mods.player.pos, 32)          # 覆盖层画圈(叠进下一帧快照)
mods.gui.text(10, 10, "hello")                 # 覆盖层文字
mods.available()                      # 分层能力清单: 命名空间 → {能力: 说明}
```

五个通用核命名空间：`player`（无敌/火力/残机/Bomb/坐标）、`boss`
（exists/set_life/set_pos）、`bullets`（fire/fire_ring/clear/count）、
`score`（add）、`gui`（line/circle/polyline/text 覆盖层，坐标系 = 游戏区
像素 384x448、y 向下）。覆盖层叠进下一帧 SceneSnapshot 的
shapes/texts（快照每帧全量重建，故每帧都要重推；后端渲染 shapes 留待）。

完整示例见 `examples/`：`auto_play.py`（策略开车 + 事件流）、
`mod_fun.py`（魔改）、`dodge_ai.py`（势能场躲弹 baseline，直接运行 =
窗口观战，`DODGE_AI_HEADLESS=1` 跑数据）。

## 「Architecture」分层架构

```
touhou/
  apis/      # 对外门面: basic(Game/Input/事件/快照) + world(TouhouWorld)
             #   + modding(ModApi); 作品无关, 经注册表解析
  engine/    # 共用引擎: World/System 管线/事件流/InputFrame/SceneSnapshot/
             #   命令队列/注册表/ECL·ANM VM/弹幕/激光/敌人/渲染后端协议
  games/     # 作品实现(th07…): compose.py 组合根 import 即登记
  schemas/   # 纯数据层: 格式解析/指令 union/存档结构(零行为)
  utils/     # 工具(Vec2/日志…)
test/
  base/      # 引擎自身测试(禁 import games.*, CI 只跑这层)
  th07/      # 作品测试(含真数据 needs_data)
```

内部工作原理：sim 只产事件流（msgspec tagged union 的 Event），view/api/
replay 全是消费者；输入只走 InputFrame；渲染后端只拿 SceneSnapshot 快照，
拿不到 world 本体；每帧执行序 = 一屏可读的管线槽位清单（INPUT/LOGIC/
MOVEMENT/COLLISION/OUTPUT）。

## 「Extend」接入新作品

照 `games/th07/` 抄骨架，组件在定义处用装饰器登记（登记方向
games → engine 单向）：

- `@TouhouRegistry.world("thNN")` — 世界类（装配契约 `compose(assembly,
  **params)` + `tick(input) -> SceneSnapshot`）
- `@TouhouRegistry.ecl_host("thNN")` — ECL 宿主回调类
- `@TouhouRegistry.app("thNN")` — 窗口 App（`run_app`/`run_game` 契约见
  `engine/assembly.py` 的 `WindowApp`；缺了也能 headless）
- `@TouhouRegistry.renderer("后端名")` — 渲染后端（正交维度，默认 pygame）
- `TouhouRegistry.register(game, title=, data=, resources=, anm_version=,
  save=)` — 数值表/名单/资源命名规则等装配件
- `TouhouRegistry.register_default_game("thNN")` — 声明框架默认作品
  （显式决策，只能有一个）
- 在 `touhou/games/__init__.py` 的作品发现清单加一行 import（import 即登记）

apis 门面面向鸭子契约 `apis.basic.GameWorld` 编程（frame/tick/player/
bullets/enemies/…）；残机/火力等标量资源的位置由作品自定，经可选钩子
`stats()`（读）/`set_stat()`（写，ModApi 用）开放；终局收尾经
`finalize_game_over()`/`finish_ending()` 钩子。缺钩子的作品调用时报中文
NotImplementedError，不静默失败。

## 「Test」

```bash
# CI 同款(引擎层 + 守护测试, 无需游戏数据)
uv run pytest test/base -q
# 全量(含 th07 真数据 needs_data 用例, 本机数据路径见 compose.DATA_PATH)
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run pytest test -q
# 四件套其余: ruff check / ruff format --check / mypy(均见 pyproject 配置)
uv run ruff check touhou test && uv run ruff format --check touhou test
uv run python -m mypy touhou
```

---

<div align="center">

*原作《东方妖妖梦 ～ Perfect Cherry Blossom》© 上海アリス幻樂団（ZUN）*

*本仓库为爱好者再实现/二次创作，不含亦不分发任何原版游戏资源；*
*反编译参考来自 [some100/th07](https://github.com/some100/th07)（100% 实现 / 99.78% 精度）。*

**少女已祈祷完毕 —— 弹幕，就绪。**

</div>
