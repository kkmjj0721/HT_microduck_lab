# HT_microduck_lab

基于 **mjlab 1.6.0** 的 HT Microduck 机器人仿真与强化学习项目，采用 **12 个无刷电机 + 3 个舵机** 混合驱动。

mjlab 负责仿真、场景和环境管理；执行器模型、任务注册与训练入口放在独立 Python 包
`ht_microduck` 中，发行包名为 `ht-microduck`。
目前已提供机器人模型、混合执行器、IMU 仿真传感器和平地速度任务环境。训练与回放直接复用
官方 `mjlab` 入口，PPO、网络与 Runner 来自本仓库根目录的 `rsl_rl/`；`duck-train` 与
`duck-play` 是其薄封装。训练只验证到"链路通、可恢复、可回放"，
`duck-eval`/`duck-export` 属于后续任务。
另提供 **CyberDuck V2** 的独立模型、mjlab 实体、静态预览和平地速度任务配置；
新任务使用位置／速度混合动作，策略效果尚待训练验收。

## 目录结构

```
src/ht_microduck/
  tasks/                  # 任务注册、契约，以及按职责分层的配置与 MDP
    __init__.py           # register_mjlab_task（经 mjlab.tasks entry point 自动发现）
    ht_microduck_contract.py    # HT 任务时序/动作/观测契约
    cyberduck_v2_contract.py    # CyberDuck V2 独立混合动作契约
    config/
      ht_microduck/       # HT 环境、RL、地形与本体适配配置
      cyberduck_v2/       # CyberDuck V2 独立环境与 RL 配置
    mdp/                  # 官方 MDP 与独立保留的 VelStand 实现
    rl/                   # 任务检查点恢复与数值适配
  robot/
    ht_microduck_constants.py   # 关节/电机分组/初态/执行器装配
    ht_microduck/               # HT-DK_URDF.xml 与 16 个 STL（数据目录）
    cyberduck_v2_constants.py   # CyberDuck V2 关节、源电机与实体配置
    cyberduck_v2/               # CyberDuck_V2.xml、来源清单与 20 个 STL
  actuator/                     # 3532 NT-PD 与 HD1910 BAM 模型及参数来源
  train_cli.py                  # duck-train → mjlab.scripts.train
  play_cli.py                   # duck-play  → mjlab.scripts.play
rsl_rl/                         # rsl-rl-lib 5.4.2 完整副本，训练实际代码路径
```

包结构与官方 [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl)
保持相同的三个子包：`robot/`、`actuator/`、`tasks/`，机器人 MJCF 与 `assets/` 同级放在
`robot/ht_microduck/` 数据目录里，训练算法只保留 `rsl_rl/` 一套。
`tasks/` 内参考本机 `legged_wbc_mjlab` 按 `config/`、统一的 `mdp/` 和 `rl/` 分层，
新增任务在 `config/<机器人>/` 定义环境与 RL 配置，再在 `tasks/__init__.py` 注册。

## 快速开始

环境面向 **Linux x86_64、Python 3.12 和 NVIDIA GPU**。
首次使用在仓库根目录运行 `bash setup.sh`，自动准备 uv、Python 3.12 并安装到 `.venv/`。
脚本调用 `tools/setup_env.py` 安装或同步依赖；CPU 安装与选项见 [安装文档](docs/setup.md)。
安装后使用 `uv run --no-sync ...` 运行项目命令，保留已选定的 PyTorch 后端。

在仓库根目录运行：

```bash
# 编译两种机器人，核对关节、执行器映射与模型质量
make model

# 检查锁文件、代码、测试、模型、文档和 Git 差异空白
make check
```

有图形桌面时，可打开静态模型预览：

```bash
make viewer
```

`make` 可列出全部检查入口（`make docs` 单独检查文档链接、锚点和任务表）。
检查临时文件按次保存在 `.artifacts/checks/run-*`；
这些检查覆盖模型、代码与文档，GPU 动态运行需使用下方专项工具。
静态预览用于核对外观和姿态，稳定站立与训练效果另行验收。

## GPU 专项检查

在已通过 [GPU 环境验证](docs/setup.md#3-验证安装和-gpu-环境) 的终端中，先创建项目内临时目录并设置缓存：

```bash
mkdir -p .artifacts/manual-checks
check_dir="$(mktemp -d "$PWD/.artifacts/manual-checks/run-XXXXXXXX")"
export TMPDIR="$check_dir/tmp" PYTHONDONTWRITEBYTECODE=1
export WARP_CACHE_PATH="$check_dir/warp" TORCHINDUCTOR_CACHE_DIR="$check_dir/torch"
mkdir -p "$TMPDIR"
```

在同一终端按需选择检查；以下命令均默认使用 4 个环境：

```bash
# 整机平地场景：150 步，检查接触、IMU、目标映射、限幅和局部 reset
timeout 180s uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0

# 15 关节混合执行器测试台：300 步，检查延迟、NT 限幅和短阶跃响应
timeout 180s uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0

# 3 关节 HD1910 测试台：300 步，检查摩擦、延迟、限幅和重置
timeout 180s uv run --no-sync python -B tools/check_hd1910.py --device cuda:0
```

任务环境与训练链路的专项检查：

```bash
# 冻结契约：时序、动作子集/顺序/缩放、观测维度、逐关节映射、保持关节
timeout 300s uv run --no-sync python -B tools/check_task_contract.py --device cuda:0

# 官方平地速度任务：维度、逐关节动作映射、足端射线、局部重置与后期课程有限值
timeout 600s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0

# 短训练：采样 + PPO 更新，检查 loss/梯度有限、checkpoint 可写可恢复
# 训练入口没有 --device；用 --gpu-ids None 走 CPU，或省略后由可见 GPU 决定
uv run --no-sync duck-train HtDuck-Flat-Velocity --env.scene.num-envs 16 \
  --agent.max-iterations 5 --agent.seed 0 --gpu-ids None
```

上述工具验证仿真接入与短时响应；实机参数和稳定站立仍需标定与验收。失败现场保留至排查
结束，完成后仅清理本次生成的产物目录。

## 训练与回放

两个入口都是 mjlab 官方 `train`/`play` 的薄封装，命令行、日志布局、控制台面板和查看器
与官方一致；第一个位置参数是任务 id。训练支持`--env.*` / `--agent.*`覆盖任务的
`ManagerBasedRlEnvCfg` / `RslRlOnPolicyRunnerCfg`字段，回放使用官方`PlayConfig`选项。
任务列表可用
`uv run --no-sync list-envs` 查看：

| 任务 id | 训练目标 |
|---|---|
| `HtDuck-Flat-Velocity` | 官方平地速度与随机头颈姿态跟踪 |
| `HtDuck-Flat-Velocity-Head` | 与 Velocity 使用同一官方配方，保留独立任务 ID 与日志 |
| `HtDuck-Flat-StandUp` | 从站、坐、前躺与后躺初态起立，并学习躯干指令 |
| `HtDuck-Flat-SitStand` | 受令坐站切换（原有后收腿目标） |
| `HtDuck-Flat-SitStand-Forward` | 受令站立／前收腿坐下，独立姿态目标与日志 |
| `HtDuck-Flat-SitStand-Forward-V4` | 独立初态课程，默认先学习前坐与站立保持；原Forward保留v3对照 |
| `HtDuck-Flat-VelStand` | 行走、站立与恢复技能组合 |
| `HtDuck-Flat-SitStand-Unbounded` | 坐站原始动作目标语义的对照 |
| `HtDuck-Flat-VelStand-Unbounded` | 组合任务原始动作目标语义的对照 |
| `CyberDuckV2-Flat-Velocity` | CyberDuck V2 平地速度配置，混合位置／速度控制，策略效果待验收 |

```bash
# 训练：默认写到 logs/rsl_rl/<experiment_name>/<时间戳>_<run_name>/
uv run --no-sync duck-train HtDuck-Flat-Velocity --agent.max-iterations 3000

# 头颈联动：每 2–5 s 改变目标，范围在 0/500/1000/1500/2000 迭代逐步扩大
uv run --no-sync duck-train HtDuck-Flat-Velocity-Head

# 回放：--agent zero|random|trained，--checkpoint-file 指定权重，--video 录 mp4
uv run --no-sync duck-play HtDuck-Flat-Velocity --agent trained --checkpoint-file .../model_250.pt
uv run --no-sync duck-play HtDuck-Flat-Velocity --agent zero --num-envs 1 --viewer viser

# 使用 Head 任务对应的检查点；回放按检查点保存的课程阶段采样头部目标
uv run --no-sync duck-play HtDuck-Flat-Velocity-Head --agent trained --checkpoint-file .../model_250.pt
```

前坐任务沿用官方坐站命令接口，采用HT前收脚姿态及独立的基础奖励、限位重置和验收。
基础阶段保留小范围头部指令与初态域随机化，关闭interval推扰和逐迭代强化课程；
先学会完整坐站，再加入大幅头部/推扰强化。受HT膝行程限制，并非精确复制官方腿形。
训练目录为`logs/rsl_rl/flat_sitstand_forward/`，默认新运行名`sitstand_forward_base_v3`；
采用联合最差关节与全腿误差的非负姿态奖励、稠密高度信号及适中的直立奖励。
完整策略坐站尚未通过行为验收。
奖励语义已改变，应从零训练，不续训旧前坐或SitStand优化器。修复依据与验证边界见
[前坐修复设计](docs/design/skill_task_migration.md#t060-前坐失败后的任务修复)。

```bash
uv run --no-sync duck-train HtDuck-Flat-SitStand-Forward --agent.seed 0
uv run --no-sync duck-play HtDuck-Flat-SitStand-Forward --agent trained --checkpoint-file .../model_250.pt

# 验收实际策略的站立→前坐→站立，失败退出非零；输出必须为新的项目内目录
uv run --no-sync python -B tests/test_sitstand_forward_behavior.py --checkpoint-file .../model_250.pt --output logs/forward_behavior/new_run
```

v4从零训练，默认`hold`阶段匹配初态与命令；头部为零指令，全部动作仍由策略输出。
训练目录为`logs/rsl_rl/flat_sitstand_forward_v4/`，默认运行名`forward_v4_hold`。
阶段、初态库指纹和归一化/优化器随检查点保存；升级需要对应检查点的三种子独立报告。
初态库随包提供经真实执行器采集并复验的坐/站端点；后续`sit/rise`须补充相同语义下复验的真实过渡样本，
缺少样本时会明确报错。阶段接口、验收门槛和参考依据见
[v4课程设计](docs/design/skill_task_migration.md#2026-11-03-v4-初态课程与独立保持验收)。

```bash
uv run --no-sync duck-train HtDuck-Flat-SitStand-Forward-V4 --agent.seed 0

# 显式有界训练：至少600秒实际采样和PPO，随后完整恢复；不等于策略行为通过
uv run --no-sync python -B tests/test_forward_v4_training.py train --num-envs 512 --seed 0 --output logs/forward_v4/new_hold

# 每个种子分别检查前坐和站立是否连续保持5秒；输出必须为新目录
uv run --no-sync python -B tests/test_forward_v4_behavior.py --checkpoint-file .../model_1000.pt --seed 0 --output logs/forward_v4/hold_seed0
```

除 VelStand 和前坐基础变体外，现有任务的奖励、重置与课程采用官方 `microduck_rl@bae39f59` 的配方，机器人相关姿态与高度
使用 HT 仿真实测值。两个 Velocity 任务都训练随机头颈指令，躯干槽位保留小范围随机输入且
跟踪奖励为零；StandUp 逐步加入前后躺初态与躯干 z/roll/pitch 跟踪；SitStand 按官方节奏
训练受令坐站。对应关系和必要适配见[任务对齐设计](docs/design/skill_task_migration.md#t055-除-velstand-外逐项对齐官方任务)。

上述 HT 任务（含前坐基础变体）的接口都是 61 维 actor、14 维动作、`1.0 rad/action`、50 Hz（物理步 `.005 s`，
decimation=4）；Velocity critic 为 76 维，StandUp/SitStand 为 74 维。VelStand 保留原有
61/64/14与`.002 s × 10`；恢复窗口、初态概率和身体跟踪已按[恢复修复设计](docs/design/skill_task_migration.md#t057-官方恢复机制与-ht-坐站高度修复)修正，专家蒸馏另阶段实施。旧 64 维 critic 检查点、旧动作缩放和旧观测顺序不能用于
新配方的完整恢复，须使用对应配置重新训练。短跑只验证运行链路，不代表已经学会各项技能。

SitStand、VelStand 默认在扣除编码器偏置后，将绝对关节目标限制在模型的逐关节硬范围内；
14维动作仍为`HOME + 1.0 × action`，上一动作观测和动作变化奖励仍使用策略原值。
原SitStand膝关节坐姿需要约1.6 rad偏移，前坐任务髋关节需要约2.4 rad偏移，因此没有统一裁剪原始动作至±1。新增的
`Episode_Metrics/requested_target_outside_limits`、`applied_target_outside_limits`、
`target_clip_fraction`、`actuator_saturation_fraction`和`actuator_saturation_duration`
分别记录请求越界、实际下发越界、限幅比例、控制帧饱和比例和回合最长连续饱和秒数；指标不参与奖励。
对应设计与验证范围见[目标约束设计](docs/design/skill_task_migration.md#t058-坐站与组合任务的关节目标约束)。

目标约束改变了旧策略的控制语义，新配方使用新实验从零训练。回放旧权重作原行为对照时，
使用显式`-Unbounded`任务；对照日志实验名带`_unbounded`，原训练目录保留：

```bash
uv run --no-sync duck-train HtDuck-Flat-SitStand --agent.run-name sitstand_bounded
uv run --no-sync duck-play HtDuck-Flat-SitStand-Unbounded --agent trained --checkpoint-file .../model_5500.pt
```

训练也可用`--env.actions.joint-pos.bound-targets False`关闭约束；官方回放入口不支持
`--env.*`覆盖，使用上述对照任务ID选择旧语义。部署时需要同步实现最终目标限幅；
现阶段尚未提供对应的正式评估、部署导出及专家蒸馏入口。

一次训练产出 `params/env.yaml`、`params/agent.yaml`、`git/<repo>.diff`、
`model_<iteration>.pt` 和 TensorBoard `events.*`；控制台面板沿用 RSL-RL 字段
（`Learning iteration`、`Total steps`、`Collection time`、`Mean reward`、`ETA` 等）。
短跑只证明训练链路与数值有限，不代表策略已学会行走。

训练走本仓库根目录的 `rsl_rl/`——它是 rsl-rl-lib 5.4.2 的完整副本，PPO、
ActorCritic、Storage、Runner 和 Logger 全部来自这里，不依赖 `.venv` 里的 wheel。
包初始化时把仓库根置于 `sys.path` 首位，让这份代码稳定地先于 wheel 被导入。

## 机器人与执行器

模型 [HT-DK_URDF.xml](src/ht_microduck/robot/ht_microduck/HT-DK_URDF.xml)
及 16 个 STL 随包保存，包含自由基座和 15 个单轴关节，模型总质量约 **3.2947 kg**。
本体 XML 只定义机器人和传感器，地形与灯光由 mjlab `Scene` 提供。
被动源模型为 `nq=22`、`nv=21`、`nu=0`；场景装配执行器后为 `nu=15`。

| 电机 | 数量 | 对应关节 | 仿真模型 |
|---|---|---|---|
| 高擎 HTDW-3532-02-DNE | 12 | 双腿 10 关节、`neck_pitch_joint`、`head_pitch_joint` | 原生 PD + 24 V 输出轴 NT 曲线近似 |
| 飞特 HD1910-C001 | 3 | `head_yaw_joint`、`head_roll_joint`、`mouth_joint` | 7.4 V BAM M6 + 摩擦模型 |

关节名称、顺序、初态、碰撞与两组执行器配置统一在
[ht_microduck_constants.py](src/ht_microduck/robot/ht_microduck_constants.py)
中定义。策略的动作子集、输出顺序和控制周期由任务配置明确声明。

当前无刷默认 `kp=10`、`kd=0.4`、力矩上限 `2 N·m`；舵机默认 `kp_fw=32`、
力矩上限 `1.471 N·m`，关闭摩擦随机化。两组命令延迟均为 `0–3` 个物理步。
这些属于仿真配置，增益、限幅、延迟和带载供电尚未完成实机标定；堵转力矩不代表持续输出能力。

`HOME_FRAME` 现在是蹲姿：`hip_pitch 0.85`、`calf −1.20`、`ankle 0.35`，
`hip_roll` 镜像内收 `+0.0873/−0.0873`，根高 `0.1534 m`。脚底与地面平行（倾角 `0.13°`，
旧零位是 `4.87°`），重心在脚掌前后各约 `35–40 mm` 之间基本居中。
实测（[T038](docs/archive/development_tasks.md#t038-标定-home-站姿)）：5 s 零动作保持 0/128 跌倒，
根高稳定在 `0.150 m`；协调脉冲 `0.10–0.26 rad` 为 0/24，同幅度下旧零位在 `0.26 rad` 跌 2/24。
根高对站姿影响很大：任何可见离地间隙都会让复位变成落体冲击并撞散蹲姿，
所以 HOME 只留 `0.4 mm` 顶点余隙，不要为了"更保险"把 `pos` 调高。

用户提出的 `hip_roll 0.38` / `hip_pitch 1.57` 无法采用：`1.57` 正是关节限位，
腿会折到脚过髋而 48/48 全倒；`0.38` 超出平地所需，会把脚底翘起约 `17°` 而只靠内缘着地。
当前站姿与增益仍是仿真假设，不含实机标定（实机标定归 T030，验收条件见
[T022–T031 验收表](docs/archive/development_tasks.md#t022t031-后续任务的产物与验收)）。

XML 提供 `imu_ang_vel`、`imu_lin_vel`、`imu_accel`、`imu_upvector` 和 `root_angmom`，
场景注册名带 `robot/` 前缀。读数为理想值，IMU 安装位姿为占位配置；
`imu_lin_vel` 和 `root_angmom` 在本机无对应实机传感器，只用于 critic 或奖励。
传感器语义与观测边界见 [IMU 说明](docs/archive/development_tasks.md#t037-在-xml-中声明-imu-参考点与内置传感器)。

### CyberDuck V2

[CyberDuck_V2.xml](src/ht_microduck/robot/cyberduck_v2/CyberDuck_V2.xml)
及 20 个 STL 随包提供，源文件与导入差异记录在
[来源清单](src/ht_microduck/robot/cyberduck_v2/source_manifest.json)。
模型包含自由基座、19 个单轴关节，总质量约 **3.7032 kg**；
其中 4 个滚轮通过软等式约束跟随踝关节，比例为 `1.210526`。
机器人实体接入 **12 个无刷电机＋3 个舵机**，两踝控制速度，其余 13 个独立关节控制位置：

| 执行器 | 关节 | 当前仿真配置 |
|---|---|---|
| HTDW-3532 NT-PD，10 路位置控制 | 双腿除踝部外 8 关节，以及 `neck_pitch_joint`、`head_pitch_joint` | `kp=10`、`kd=0.4`、限幅 `2 N·m`，沿用既有输出轴 NT 曲线与反射惯量 |
| HTDW-3532，2 路速度控制 | `r_ankle_joint`、`l_ankle_joint` | `kp=0`、速度反馈增益 `0.4`、限幅 `2 N·m`，保留同一 NT 包络 |
| HD1910 BAM，3 路 | `head_yaw_joint`、`head_roll_joint`、`mouth_joint` | `7.4 V`、`kp_fw=32`、限幅 `1.471 N·m`，关闭摩擦随机化 |

三组均沿用 `0–3` 个物理步命令延迟。这些参数是复用的仿真默认值，尚非 CyberDuck 实机标定。
两踝通过 `set_joint_velocity_target(..., joint_ids=踝关节索引)` 下发 rad/s 目标，局部轴正方向沿用模型；
其余关节使用 `set_joint_position_target`。速度组关闭位置反馈，不主动回到初始踝角度。
左右各两个滚轮保留从动，不单独配置执行器；滚轮仍参与运动、碰撞和约束受力。
默认初态采用对称弯腿与头颈后收：左右 `hip_pitch=0.490`、`calf=-0.444`，
`neck_pitch=-0.360`、`head_pitch=0.405`、`head_roll=0.011`（rad），其余关节位置和全部关节速度为零。
头部角度包含当前仿真增益下的静止受载补偿，使头部接近世界水平面。
姿态由 `HOME_FRAME` 定义，并用于实体的 `default_joint_pos` 与静态预览；根高度仍为 `0.252 m`。
源零位保留在 `SOURCE_FRAME`。静止承重已做仿真检查，尚非实机标定或策略效果验收。
源 XML 原有两个踝部示例 motor 保持原样，实体装配时在内存中替换为上述混合驱动。

```bash
uv run --no-sync python -B tools/check_robot.py --robot cyberduck-v2

# 有图形桌面时打开静态预览
uv run --no-sync python -B tools/check_robot.py --robot cyberduck-v2 --viewer
```

场景通过
[get_cyberduck_v2_robot_cfg()](src/ht_microduck/robot/cyberduck_v2_constants.py)
获取独立配置；两种机器人可同时装入同一个 Scene。
[运行时专项检查](tests/test_cyberduck_v2.py)使用 3 个环境、100 个物理步核对 13 路位置及 2 路速度目标、NT/BAM 限幅与局部重置，
不启动训练；设置上方项目内临时与缓存路径后运行：

```bash
uv run --no-sync python -B tests/test_cyberduck_v2.py --device cuda:0
```

独立任务 `CyberDuckV2-Flat-Velocity` 使用 49 维 actor、56 维 critic 和 14 维混合动作：
前 12 维依次控制右腿 yaw/roll/pitch/calf、左腿同序及 neck_pitch/head_pitch/head_yaw/head_roll，
目标为 `HOME + 0.25 × action` rad，并按模型硬限位约束；最后两维依次控制右踝、左踝，
目标为 `4.0 × action` rad/s，范围 ±8 rad/s。嘴保持 HOME，四个滚轮没有独立动作。
连续踝角不进入 actor；四轮接地与机身线速度只供 critic。控制频率 50 Hz（`.002 s × 10`）。
这些是首版仿真配置，不能加载旧 HT 策略或归一化统计。

设置上方项目内临时与缓存路径后，可检查实际任务的动作映射、观测、步进和局部重置：

```bash
uv run --no-sync python -B tests/test_cyberduck_v2_motion.py --device cuda:0 --steps 300 --output "$check_dir/cyberduck-task"
uv run --no-sync duck-play CyberDuckV2-Flat-Velocity --agent zero --num-envs 1 --viewer viser
```

训练配置使用独立日志实验名 `cyberduck_v2_flat_velocity`；专项检查不启动训练，也不代表策略运动性能通过。

## 在场景中使用

通过工厂获取独立配置副本，再按任务需要调整初态和执行器参数：

```python
from mjlab.scene import SceneCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.robot.ht_microduck_constants import get_ht_microduck_robot_cfg

robot_cfg = get_ht_microduck_robot_cfg()
scene_cfg = SceneCfg(
    num_envs=4,
    terrain=TerrainEntityCfg(terrain_type="plane"),
    entities={"robot": robot_cfg},
)
```

该示例只创建配置。运行动态控制前，需要通过执行器的 startup 事件或
`sim.expand_model_fields(...)` 为各环境分配独立模型字段；正式检查工具已处理。
接入方法见 [3532 NT-PD 说明](src/ht_microduck/actuator/HTDW_3532_02_DNE/params/README.md)
和 [HD1910 执行器说明](src/ht_microduck/actuator/HD_1910_C001/README.md)。

## 目录与文档

```text
HT_microduck_lab/
├── src/ht_microduck/
│   ├── robot/                 # 整机配置、MJCF 与 mesh
│   ├── actuator/              # 3532 NT-PD、HD1910 BAM 与参数来源
│   └── tasks/                 # 任务注册表、契约与速度任务配置
├── rsl_rl/                    # rsl-rl-lib 5.4.2 完整副本（训练实际代码）
├── tools/                     # 环境安装、模型与 GPU 专项检查
├── tests/                     # 正式自动化测试
├── docs/                      # 安装、流程、设计、审查与历史归档
├── Makefile                   # 统一检查入口
├── setup.sh                   # 一键准备 uv、Python 与 .venv
├── pyproject.toml             # 包元数据与依赖声明
└── uv.lock                    # 依赖锁文件
```

| 文档 | 内容 |
|---|---|
| [安装与环境验证](docs/setup.md) | 环境要求、CUDA 后端选择、依赖同步和排错 |
| [阶段与任务记录](docs/development.md) | 既有任务、阶段依赖和必要结果索引 |
| [项目开发约定](AGENTS.md) | 仓库约束、语言与代码风格、产物管理和交付要求 |
| [开发工作流设计](docs/development_workflow.md) | 开发步骤、模块边界、复现、训练验证与交付规则 |
| [协作与审查规范](docs/collaboration_review.md) | 并发分工、集成和独立复核 |
| [任务条目归档](docs/archive/development_tasks.md) / [完成记录归档](docs/archive/development_records.md) | 已结束任务的目标、验收与当时结论 |
| [3532 执行器设计](docs/design/htdw3532_nt.md) | NT 曲线、原生 PD、接口及验证依据 |

参与开发前请先阅读开发工作流与项目约定；小修改直接实施，已登记任务按原条目维护。
**当前任务状态与下一步安排只以[开发文档的任务表](docs/development.md)为准**，本页不复述。
T022–T026 已把任务契约、平地速度任务与 RSL-RL 训练链路依次接通；短跑只证明链路可用，
不代表策略已学会行走。
