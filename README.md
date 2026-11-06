# 🦆 HT Microduck Lab

基于 **mjlab 1.6.0** 的机器人仿真与强化学习项目，面向 **HT Microduck** 和 **CyberDuck V2**，提供混合执行器仿真、平地任务环境、PPO 训练和可视化回放。

两种机器人均接入 **12 个无刷电机＋3 个舵机**；HT 使用位置控制，CyberDuck V2 的两踝使用速度控制，其余独立关节使用位置控制。mjlab 负责仿真与环境管理，训练算法使用本仓库的 **RSL-RL 5.4.2**；`duck-train` 和 `duck-play` 是官方入口的薄封装。

HT 的训练、恢复与回放链路已有运行证据；前坐等技能尚未通过行为验收，CyberDuck V2 策略效果待验证。正式评估、策略导出与实机部署尚未提供。

| 任务 ID | 训练目标或用途 |
| --- | --- |
| `HtDuck-Flat-Velocity` | 平地速度与随机头颈姿态跟踪 |
| `HtDuck-Flat-Velocity-Head` | 同一速度跟踪配方，保留独立任务 ID 与日志 |
| `HtDuck-Flat-StandUp` | 从站、坐、前躺和后躺初态起立，跟踪躯干指令 |
| `HtDuck-Flat-SitStand` | 受令坐站切换，采用原有后收腿目标 |
| `HtDuck-Flat-SitStand-Forward` | 受令站立与前收腿坐下，保留 v3 配方作为对照 |
| `HtDuck-Flat-SitStand-Forward-V4` | 独立初态课程，默认先训练前坐与站立保持 |
| `HtDuck-Flat-VelStand` | 行走、站立与恢复技能组合 |
| `HtDuck-Flat-SitStand-Unbounded` | 坐站任务未约束关节目标的历史语义对照 |
| `HtDuck-Flat-VelStand-Unbounded` | 组合任务未约束关节目标的历史语义对照 |
| `CyberDuckV2-Flat-Velocity` | CyberDuck V2 平地速度跟踪，混合位置／速度动作 |

## 快速开始

环境要求：**Linux x86_64、Python 3.12**；GPU 训练需要 NVIDIA GPU 和兼容驱动。以下命令均在仓库根目录执行。

```bash
bash setup.sh
export PATH="$HOME/.local/bin:$PATH"

# 编译两种机器人，核对关节与执行器映射
make model
```

安装脚本会准备 uv、Python 和 `.venv/`，默认按本机 CUDA Toolkit 选择后端。CPU 安装、后端选项和训练前的 GPU 环境验证见[安装指南](docs/setup.md)。日常运行保留 `--no-sync`，沿用已安装的后端。

有图形桌面时，可静态预览模型：

```bash
make viewer
uv run --no-sync python -B tools/check_robot.py --robot cyberduck-v2 --viewer
```

## 训练与回放

### 训练

```bash
# HT Microduck：平地速度与头颈姿态跟踪
uv run --no-sync duck-train HtDuck-Flat-Velocity \
  --env.scene.num-envs 1024 --agent.max-iterations 3000 --agent.seed 0

# CyberDuck V2：平地速度跟踪
uv run --no-sync duck-train CyberDuckV2-Flat-Velocity \
  --env.scene.num-envs 1024 --agent.max-iterations 3000 --agent.seed 0
```

其他任务使用表中对应的 ID。环境数与训练轮数按资源和实验目标调整；训练支持 `--env.*` 和 `--agent.*` 覆盖配置，通过 `--gpu-ids 0` 选择 GPU。可用 `uv run --no-sync list-envs` 查看任务，命令后添加 `--help` 查看参数。

默认产物目录为 `logs/rsl_rl/<experiment_name>/<运行标识>/`，其中：

- **HT 速度任务**：`logs/rsl_rl/flat_velocity/<运行标识>/`。
- **CyberDuck V2 速度任务**：`logs/rsl_rl/cyberduck_v2_flat_velocity/<运行标识>/`。

训练目录保存 `params/env.yaml`、`params/agent.yaml`、代码差异、`model_<iteration>.pt` 和 TensorBoard 事件。日志查看方式见[安装指南](docs/setup.md#6-训练日志可视化)。

前坐 v3 与 V4 使用独立实验并从零训练，不续训旧前坐或 SitStand 优化器。V4 默认处于 `hold` 阶段，后续阶段需要匹配检查点的验收报告及经复验的过渡样本；当前保持与完整坐站能力仍待验收。

### 策略播放

将检查点路径替换为实际文件，并选择与训练一致的任务：

```bash
uv run --no-sync duck-play HtDuck-Flat-Velocity \
  --agent trained --checkpoint-file '<实验目录>/model_1000.pt' --num-envs 1
```

查看器默认按图形环境选择 MuJoCo 窗口或 Viser 浏览器界面，可通过 `--viewer native` / `--viewer viser` 指定；添加 `--video True` 可将录像保存到实验目录的 `videos/play/`。

没有检查点时，可用 `--agent zero` 或 `--agent random` 查看环境，例如：

```bash
uv run --no-sync duck-play CyberDuckV2-Flat-Velocity \
  --agent zero --num-envs 1 --viewer viser
```

恢复与回放须匹配机器人、任务接口和动作语义；HT 与 CyberDuck V2 的检查点及归一化统计不能混用。旧版未约束关节目标的 SitStand / VelStand 权重使用表中的 `-Unbounded` 对照任务。仿真参数尚未完成实机标定，短时检查也不代表策略能力达标。

## 项目结构

```text
src/ht_microduck/
  robot/       # 两种机器人的 MJCF、mesh、关节映射与实体配置
  actuator/    # 3532 NT-PD、HD1910 BAM 与参数来源
  tasks/       # 任务注册、独立契约、分机器人配置、共享 MDP 与 runner 适配
  train_cli.py # duck-train 入口
  play_cli.py  # duck-play 入口
rsl_rl/        # rsl-rl-lib 5.4.2 完整副本，训练与回放实际使用
tools/         # 环境安装、模型、契约与运行检查
tests/         # 正式测试与显式启动的训练、行为验收入口
docs/          # 安装与使用说明
```

## 检查与文档

```bash
make check  # 检查锁文件、代码、测试、两种模型、文档与差异空白
make docs   # 单独检查文档链接、锚点与任务表
```

`make` 可列出全部检查入口。检查缓存按次写入 `.artifacts/checks/run-*`；`make check` 不覆盖 GPU 动态运行或策略训练效果，专项入口见 `tools/` 与 `tests/`。

- [安装指南](docs/setup.md)：依赖、后端选择、GPU 环境验证与日志可视化。
- [HT 任务配置](src/ht_microduck/tasks/config/ht_microduck/) / [CyberDuck V2 任务配置](src/ht_microduck/tasks/config/cyberduck_v2/)：环境、奖励、课程与 PPO 参数。
- [HT 接口契约](src/ht_microduck/tasks/ht_microduck_contract.py) / [CyberDuck V2 接口契约](src/ht_microduck/tasks/cyberduck_v2_contract.py)：观测、动作、单位与控制周期。
- [3532 参数说明](src/ht_microduck/actuator/HTDW_3532_02_DNE/params/README.md) / [HD1910 执行器说明](src/ht_microduck/actuator/HD_1910_C001/README.md)：模型、参数来源与接入方式。
- [项目开发约定](AGENTS.md)：开发流程、验证与产物管理；本地阶段与任务安排见[任务记录](docs/development.md)。

引入的算法、任务实现和机器人资产遵循各自的许可及来源说明，见 [RSL-RL 许可](rsl_rl/LICENSE)、[BAM 来源声明](src/ht_microduck/actuator/HD_1910_C001/NOTICE)、[任务实现来源](src/ht_microduck/tasks/mdp/OFFICIAL_NOTICE)及 [CyberDuck V2 来源清单](src/ht_microduck/robot/cyberduck_v2/source_manifest.json)。
