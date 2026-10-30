# 功能设计：目录结构与训练/回放入口对齐官方 microduck_rl

关联任务：[T046](../development.md)。本文件只记录接口与实施决策，任务状态在开发文档
统一维护。

## 目标与范围

用户判断当前仓库"很乱"，要求：

1. 分析官方 `pollen-robotics/microduck_rl` 的文件与目录设计；
2. 按官方风格重新设计本仓库的目录结构；
3. `log` 输出、`train`、`play` 贴合官方（mjlab + RSL-RL）口径；
4. **训练必须走本项目根目录的 `rsl_rl/`**，不切到 wheel 的 runner；
5. 给出无用文件与可合并清单——**本轮只报告，不修改**。

### 当前问题（已核对）

| 现象 | 事实位置 | 影响 |
|---|---|---|
| 任务目录两层且单文件 | `tasks/flat_velocity/velocity_env_cfg.py` 单文件 394 行 + `__init__.py` 只做转发 | 官方每个任务一个 `tasks/microduck_*_env_cfg.py` 平铺；新增任务要多建一层目录 |
| `tasks/__init__.py` 空壳 | 只有一行 docstring | 没有 `register_mjlab_task`，`mjlab` 的 `list_tasks()` 看不到本机任务 |
| 无 `mjlab.tasks` entry point | `pyproject.toml` 只有 `duck-train`/`duck-play` 两个 console script | `import mjlab` 不会导入 `ht_microduck.tasks`，任务不会自动注册 |
| 训练/回放自造 CLI | `cli/train.py` 247 行 argparse、`cli/play.py` 282 行 | 与官方 `--env.*`/`--agent.*` 覆盖、`log_root="logs/rsl_rl"`、`params/*.yaml` 布局不一致 |
| `algorithms/` 与 RSL-RL 重复 | `algorithms/{runner,logger,ppo,storage,networks}.py` | 训练入口一旦改用 RSL-RL，这套实现成为重复代码 |
| 空目录 | `src/ht_microduck/rl/` | 无任何文件 |

### 本轮范围

- 新增 `tasks/__init__.py` 注册表 + `mjlab.tasks` entry point；
- 任务模块平铺为 `tasks/flat_velocity_env_cfg.py`，共享件集中到 `tasks/mdp.py`、
  `tasks/contract.py`；
- 每个任务一个 `RslRlOnPolicyRunnerCfg` 实例（官方写法）；
- `train`/`play` 改为官方 `mjlab.scripts.train` / `mjlab.scripts.play` 的薄封装；
- 日志输出改用 RSL-RL 布局与面板；
- **不修改** `algorithms/`、`rsl_rl/`、`tests/test_{ppo,networks,runner}.py` 等本文
  "清理清单"内的文件。

## 依据与假设

| 判断 | 依据类型与位置 | 适用差异或缺口 | 最小验证与通过条件 |
|---|---|---|---|
| 官方任务平铺 + 单一注册表 | 上游 `.artifacts/research/upstream/src/mjlab_microduck/tasks/__init__.py`（commit `b02fdee`）：11 个 `register_mjlab_task` 调用，模块名 `microduck_*_env_cfg.py` | 官方 11 个任务；本机当前 1 个。平铺对 1 个任务略重，但新增任务时不需要再建目录 | 新结构下 `list_tasks()` 含本机 task id |
| entry point 自动发现 | 本地 `mjlab/__init__.py:46-62,75` 的 `_import_registered_packages()`，组名 `mjlab.tasks`；官方 `pyproject.toml`：`mjlab_microduck = "mjlab_microduck.tasks"` | 需要重装本包刷新 `dist-info/entry_points.txt` | `mjlab.tasks.list_tasks()` 在未显式 import 的情况下能看到任务 |
| 注册表语义 | 本地 `mjlab/tasks/registry.py`：`register_mjlab_task(task_id, env_cfg, play_env_cfg, rl_cfg, runner_cls)`；`load_env_cfg/load_rl_cfg` 都 `deepcopy` | 本机 `make_flat_velocity_env_cfg` 目前**没有 `play` 参数**，需要补 | `load_env_cfg(id, play=True)` 返回可跑的 play 配置 |
| 训练走官方入口 | 本地 `mjlab/scripts/train.py:49-179`：`ManagerBasedRlEnv` → `RslRlVecEnvWrapper` → `MjlabOnPolicyRunner`；`dump_yaml` 在 runner 之前调用 | 官方 mjlab 1.3.0，本机 1.6.0，`TrainConfig` 字段有差异（本机多 `gpu_ids`、`enable_nan_guard`） | 小规模 CPU 短跑产出 `params/*.yaml` 与 `model_N.pt` |
| **训练使用项目 `rsl_rl/`** | 本轮实测：`sys.path` 前插项目根后，`rsl_rl.__file__ == <repo>/rsl_rl/__init__.py`，`mjlab.scripts.train.main()` 全程跑通（1 迭代，写 `params/env.yaml`、`params/agent.yaml`、`git/*.diff`、console 面板） | 本机 `.venv/bin/train` 是 mjlab 的 shim，`sys.path[0]` 是 `.venv/bin`，**默认解析到 wheel**；必须由我们自己的入口先插入项目根 | `import rsl_rl` 指向项目目录，且 `PPO.__file__` 也在项目目录 |
| 日志布局 | `mjlab/scripts/train.py:186-190,163-165`；`rsl_rl/utils/logger.py:232-275`（5.4.2） | 本机安装版本与官方一致（都是 5.4.2），面板字段可直接对齐 | 产出目录形如 `{log_root}/{experiment_name}/{YYYY-MM-DD_HH-MM-SS}_{run_name}/` |

`rsl_rl/` 缺 `runners/`、`utils/logger.py`、`algorithms/distillation.py`（wheel 独有）。
`_fallback.py` 用 `__path__` 扩展补齐，所以"本地优先、缺失回落 wheel"已成立；本轮不改
`rsl_rl/` 内部文件，只在入口处保证项目根在 `sys.path` 最前。

## 模块、接口与兼容性

### 目标目录结构

```
pyproject.toml                 # 新增 [project.entry-points."mjlab.tasks"]
src/ht_microduck/
  __init__.py
  train_cli.py                 # `train` console script → mjlab.scripts.train
  play_cli.py                  # `play` console script → mjlab.scripts.play
  tasks/
    __init__.py                # ★ 注册表：register_mjlab_task × N
    contract.py                # 冻结的控制/观测契约（原 tasks/common/contract.py）
    mdp.py                     # 共享 MDP 项（原 tasks/common/mdp.py）
    flat_velocity_env_cfg.py   # 任务配置 + FlatVelocityRlCfg（原 flat_velocity/velocity_env_cfg.py）
  robots/                      # 本轮保持；T047 改为 robot/
  actuators/                   # 本轮保持；T047 改为 actuator/
  algorithms/                  # 本轮保持不动，列入清理清单；T047 已删除
  cli/                         # 本轮保持不动，列入清理清单；T047 已删除
rsl_rl/                        # 本轮保持不动（只读参考 + 实际训练代码路径）
```

对照官方：官方是 `src/mjlab_microduck/{tasks,robot,actuator,sim,...}`，本机对应
`src/ht_microduck/{tasks,robots,actuators}`；官方 `tasks/mdp.py` 对应本机 `tasks/mdp.py`；
官方每个任务一个 `*_env_cfg.py`，本机当前一个 `flat_velocity_env_cfg.py`。

> **后续（T047）。** 本文只把 `tasks/` 与入口改成官方形状，并有意保留 `robots/`、
> `actuators/`、`algorithms/`、`cli/`。T047 已把前两者改为官方的 `robot/`、`actuator/`
> （MJCF 与 `assets/` 拍平到 `robot/ht_microduck/`），删除了后两者，并把 `rsl_rl/` 补成完整
> 副本、去掉 `_fallback.py`。当前结构以
> [repo_structure_official_parity.md](repo_structure_official_parity.md) 为准。

### 文件职责与接口

| 文件 | 职责与依赖 | 输入输出或配置 | 兼容性与异常 |
|---|---|---|---|
| `tasks/contract.py` | 冻结契约：`dt=0.002`、`decimation=10`、50 Hz、10 维动作、actor 39 / critic 42 | 常量 + `validate_contract()`，导入即自检 | 内容照搬原 `tasks/common/contract.py`，不改数值 |
| `tasks/mdp.py` | 共享 MDP 项（奖励/终止） | 函数集合，依赖 `mjlab` + `contract` | 内容照搬原 `tasks/common/mdp.py` |
| `tasks/flat_velocity_env_cfg.py` | 单任务环境配置 + RL 配置 | `make_flat_velocity_env_cfg(num_envs=4096, seed=None, play=False)` → `ManagerBasedRlEnvCfg`；`FlatVelocityRlCfg` → `RslRlOnPolicyRunnerCfg` | 新增 `play` 参数（默认 False，行为不变）；play 模式缩短 push 间隔 |
| `tasks/__init__.py` | 注册表 | 导入配置模块并调用 `register_mjlab_task` | 重复注册会抛 `ValueError`，故模块级只注册一次 |
| `train_cli.py` | 官方训练入口薄封装 | `main()` → 先 `import ht_microduck`（由包内插 `sys.path`），再调 `mjlab.scripts.train.main` | 不做运行时断言；保证由 `ht_microduck.__init__` 提供，见 [T047 设计](repo_structure_official_parity.md) |
| `play_cli.py` | 官方回放入口薄封装 | `main()` → 同上，调 `mjlab.scripts.play.main` | 同上 |

### 训练/回放接口（对齐官方）

```
duck-train <TASK_ID> [--env.*] [--agent.*] [--log-root ...]
duck-play  <TASK_ID> [--agent zero|random|trained] [--viewer auto|native|viser] ...
```

- 第一位置参数是任务 id（官方 `tyro.extras.literal_type_from_choices(list_tasks())`）；
- `--env.*` / `--agent.*` 直接覆盖 `ManagerBasedRlEnvCfg` / `RslRlOnPolicyRunnerCfg` 字段；
- `--log-root` 默认 `logs/rsl_rl`（官方默认），不再用本机私有的 `runs`；
- 保留 `duck-train` / `duck-play` 两个名字，避免与 mjlab 的 `train`/`play` console script
  抢名字（官方也为同一原因保留声明）。

### 日志输出（对齐官方）

```
{log_root}/{experiment_name}/{YYYY-MM-DD_HH-MM-SS}_{run_name}/
  params/env.yaml      # dump_yaml，runner 创建之前写
  params/agent.yaml    # 同上（runner 会原地修改 agent_cfg）
  git/<repo>.diff
  model_<it>.pt        # it % save_interval == 0，外加最后一次
  events.out.tfevents.*
```

控制台 80 列面板来自 `rsl_rl/utils/logger.py`，字段：`Learning iteration`、`Run name`、
`Total steps`、`Steps per second`、`Collection time`、`Learning time`、`Mean * loss`、
`Mean reward`、`Mean episode length`、`Mean action std`、`Iteration time`、`Time elapsed`、`ETA`。

### 兼容性

- `make_flat_velocity_env_cfg` 只新增带默认值的关键字参数，旧调用不受影响。
- 旧 `duck-train --num-envs ... --iterations ...` 参数**不再支持**：这是刻意的破坏性变更，
  改为官方 `--env.scene.num-envs` / `--agent.max-iterations`。README 与开发文档同步更新。
- 旧 `runs/` 下的实验产物不删除、不覆盖。

## 实施与协作

单代理串行实施，文件无并发修改者。

| 步骤 | 允许修改的文件 | 依赖 | 验证 |
|---|---|---|---|
| 1. 设计文档 | `docs/design/repo_layout_alignment.md` | 无 | 本文件 |
| 2. 任务目录重构 | `tasks/{contract,mdp,flat_velocity_env_cfg,__init__}.py`、删除 `tasks/common/`、`tasks/flat_velocity/` | 步骤 1 | `make check` |
| 3. 入口重写 | `train_cli.py`、`play_cli.py`、`pyproject.toml` | 步骤 2 | console script 冒烟 |
| 4. 引用更新 | `tests/`、`tools/` 的 import | 步骤 2 | `make check` |
| 5. 验证与文档 | `docs/development.md`、`README.md` | 步骤 3、4 | 见验收表 |

`algorithms/`、`cli/`、`rsl_rl/` 及清理清单内文件本轮不动。

## 验收与结果

| 验证项 | 实际命令及前置条件 | 通过标准 | 结果 |
|---|---|---|---|
| 注册表可见 | `list-envs`（需重装本包刷新 entry point） | 含本机 task id | 通过：`HtDuck-Flat-Velocity` 在列 |
| 训练走项目 rsl_rl | 打印 `rsl_rl.__file__` 与 PPO/Model 位置 | 指向 `<repo>/rsl_rl/` | 通过；`runners/` 按设计由 wheel 补齐 |
| 训练冒烟 | `duck-train <TASK> --env.scene.num-envs 2 --agent.max-iterations 2 --gpu-ids None` | 产出 `params/{env,agent}.yaml`、`model_*.pt`、console 面板 | 通过：6 个文件齐备，官方面板完整 |
| 回放冒烟 | 官方 play 路径加载 `model_1.pt` | 动作形状与契约一致 | 通过：`(2,10)`，actor 39→10、critic 42 |
| 基础检查 | `make check` | 全部通过 | 通过：193 passed |

viser 查看器只验证到"能起服务"：它启动后长期驻留是设计行为，本轮以有界探针替代画面验收。
GPU 驱动当前不可用，多环境与 `cuda:0` 未复测。
