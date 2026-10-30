# 功能设计：训练输出与回放对齐官方

关联任务：[T027](../development.md)（进行中）。本文件只记录接口与实施决策，
任务状态在开发文档统一维护。

> **已被 T046/T047 取代的部分。** 本文第 1 条与阶段表中的 `algorithms/logger.py`、
> `algorithms/runner.py`、`cli/train.py` 是"在自实现训练栈上改造"的方案。T046 改为直接复用
> 官方 `mjlab.scripts.train`/`play`，T047 删除了 `algorithms/` 与 `cli/`，训练算法只剩仓库根
> `rsl_rl/`。因此下文涉及这三个文件的实现步骤不再执行，其目标（RSL-RL 面板、`model_N.pt`、
> `params/*.yaml`、`metrics.jsonl`）由 mjlab 入口与本仓库 `rsl_rl/` 承担；`duck-play` 的三种
> 策略与两种 viewer 已在 T046 验收。设计其余部分（目录布局、checkpoint 命名、评估口径）仍有效。
> 见 [repo_structure_official_parity.md](repo_structure_official_parity.md)。

## 目标与范围

用户要求把训练输出、日志目录、checkpoint 命名和回放入口尽量对齐官方
`pollen-robotics/microduck_rl`（走 mjlab + RSL-RL）。当前本地 `duck-train` 输出是
自造的单行格式：

```
iter    10 reward +0.021 ep_return 1.16 value_loss 0.0142 kl +0.01163 lr 1.00e-03
```

官方 `rsl_rl/utils/logger.py` 输出 80 列块状面板，并写 TensorBoard。回放侧本地完全没有
入口，官方是 `mjlab/scripts/play.py`（`NativeMujocoViewer` / `ViserPlayViewer`）。

范围：

1. 新增 `ht_microduck.algorithms.logger`，复刻 RSL-RL 控制台块格式与指标字段，
   同时保留可机器读取的 `metrics.jsonl`。
2. `duck-train` 改用官方的日志目录布局与 `model_N.pt` 命名，写 `params/env.yaml`、
   `params/agent.yaml`。
3. 新增 `duck-play`，按官方 `play.py` 的口径加载 checkpoint、支持
   `zero`/`random`/`trained` 三种策略、native/viser 两种 viewer。
4. 不改观测/动作契约、奖励、终止和 PPO 超参。

## 依据与假设

| 判断 | 依据类型与位置 | 适用差异或缺口 | 最小验证与通过条件 |
|---|---|---|---|
| 控制台块格式 | 本地已安装 `rsl_rl/utils/logger.py:232-275`（rsl_rl_lib 5.4.2） | 官方 `microduck_rl` 锁定 mjlab 1.3.0，logger 版本可能更旧；字段名以本机安装版本为准 | 输出块与 `logger.py` 逐字段对照，测试断言关键字段存在 |
| 日志目录布局 | `mjlab/scripts/train.py:188-200`：`{log_root}/{experiment_name}/{YYYY-MM-DD_HH-MM-SS}_{run_name}` | 官方没有本项目已有的 `metrics.jsonl` | 实际跑短训练，检查目录与文件 |
| checkpoint 命名 `model_N.pt` | `rsl_rl/runners/on_policy_runner.py:133` | 本地已有 `checkpoint_N.pt`（正在跑的 2 万轮训练产物） | 新入口按 `model_*` 写，读取端同时兼容旧名 |
| 回放入口 | `mjlab/scripts/play.py`：`PlayConfig.agent`、`viewer="auto"`、`CheckpointManager` | 本机 `DISPLAY=:1` 存在，native 可用；viser 依赖已装 | `duck-play --checkpoint-file ...` 实际启动 |
| 官方 `run_name` / `experiment_name` | `mjlab/rl/config.py:97-105` | 本仓库没有这些字段 | 作为 CLI 参数提供 |

外部实现不等于本机已验证：本设计只对齐**输出格式与入口形态**，不引入 RSL-RL 的
算法实现。项目方向仍是本地 PPO/Runner，这一点不受本次影响。

## 模块、接口与兼容性

| 文件或模块 | 职责与依赖 | 输入输出或配置 | 兼容性与异常 |
|---|---|---|---|
| `algorithms/logger.py`（新） | 控制台块 + TensorBoard + JSONL；不依赖环境 | `Logger.log(it, start_it, total_it, collect_time, learn_time, loss_dict, learning_rate, action_std)` | 无 writer 时也能只打印；不改变已落盘的 metrics 字段 |
| `algorithms/runner.py` | 记录 episode reward/length 缓冲；产出 RSL-RL 口径的 loss_dict | 新增 `episode_reward_buffer`/`episode_length_buffer`（各 100 条） | `TrainCfg` 字段只增不改；旧 checkpoint 仍可加载 |
| `cli/train.py` | 装配日志目录、写 `params/*.yaml`、调用 logger | 新增 `--experiment-name`、`--run-name`、`--logger`；`--out-dir` 保留 | 显式 `--out-dir` 时沿用扁平布局，不套时间戳子目录 |
| `cli/play.py`（新） | 加载 checkpoint、构造策略、启动 viewer | `--checkpoint-file`、`--num-envs`、`--agent`、`--viewer`、`--video` | 缺 checkpoint 时报错退出；`zero`/`random` 不需要权重 |

指标口径对齐（重要）：

- `Total steps` = `num_steps_per_env × num_envs × iteration`，与官方一致。
- `Mean reward` / `Mean episode length` 取最近 100 个**完整 episode** 的均值，
  官方 `deque(maxlen=100)`。当前实现用「最近 100 条累计」但在 episode 未结束时为 NaN，
  行为需保持"没有完整 episode 时不打印该行"。
- `Mean action std` = `exp(log_std)` 的均值，单值（动作维共享 scalar log_std）。
- ETA 用已用时间 / 已完成迭代 × 剩余迭代。

## 实施与协作

| 子工作与负责人 | 允许修改的文件 | 依赖与接口 | 验证与交回 |
|---|---|---|---|
| 日志与指标（主代理） | `algorithms/logger.py`、`algorithms/runner.py`、`cli/train.py` | logger 接口先定 | `make check` + 6 迭代 GPU 短跑 |
| 回放（主代理） | `cli/play.py`、`pyproject.toml` | 依赖 runner 的 checkpoint 结构 | 加载真实 checkpoint 跑 100 步 |
| 测试（主代理） | `tests/test_logger.py`、`tests/test_play.py` | 用替身环境与假 checkpoint | `make check` |

本次为单代理串行实施；文件无并发修改者。共享工作区里已有的 2 万轮训练产物
（`runs/flat_velocity/`）**不删除、不覆盖**。

## 验收与结果

| 验证项 | 实际命令及前置条件 | 通过标准 | 结果 |
|---|---|---|---|
| 控制台格式 | `duck-train --num-envs 16 --iterations 3 --device cpu --num-steps-per-env 8` | 含官方字段 | 通过：`Learning iteration 2/3`、`Total steps: 256`、`Steps per second: 189`、`Mean policy/value/entropy loss`、`Mean action std`、`ETA` 全部出现 |
| 目录布局 | `--log-root .artifacts/t027/logs --run-name smoke` | `params/{env,agent}.yaml` 存在 | 通过：`…/2026-10-27_21-19-27_smoke/params/{env,agent}.yaml` |
| checkpoint 命名 | `--save-interval 1` | 生成 `model_N.pt` | 通过：`model_1.pt`、`model_2.pt`、`model_last.pt` |
| 回放 native | `duck-play --checkpoint-file runs/flat_velocity/checkpoint_1000.pt --viewer native --device cuda:0` | 加载并渲染 | 通过：窗口 `MuJoCo : mjlab scene` 1280×720 实际渲染，运行至 180 s 超时（exit 124），非崩溃退出 |
| 回放 viser | `duck-play --agent zero --viewer viser` | 起服务 | 通过：监听 `*:8080`，`http://localhost:8080` |
| 视频 | `duck-play --video --video-length 5` | 生成 mp4 | 通过：trained/zero/random 三种策略产出 8021/7733/9147 字节，内容不同 |
| 旧 checkpoint 兼容 | 读取 `runs/flat_velocity/checkpoint_1000.pt` | 能加载 | 通过：`[INFO] Loaded … at iteration 1000` |
| 恢复迭代号 | `duck-train --resume …/model_2.pt` | 表头不回到 1 | 通过：显示 `3/4`、`4/4` |
| 基础检查 | `pytest tests` + `ruff check src tests` | 全部通过 | 通过：192 passed；ruff `All checks passed!` |

未达成的验收项：T027 还要求 `duck-eval` 与固定种子定量评估（跟踪误差、跌倒率、限幅统计），
本轮未实现，任务状态因此保持“进行中”。

遗留：viser 的 GUI 观感需要浏览器人工确认，本机只验证了服务起来与端口监听；
native 窗口已用截图确认渲染出几何体（1107 种颜色），但步态质量未评估。
