# HT_microduck_lab

基于 **mjlab 1.6.0** 的 HT Microduck 机器人仿真与强化学习项目，采用 **12 个无刷电机 + 3 个舵机** 混合驱动。

mjlab 负责仿真、场景和环境管理；执行器模型与训练代码放在独立 Python 包
`ht_microduck` 中，发行包名为 `ht-microduck`。
目前已提供机器人模型、混合执行器、IMU 仿真传感器、平地速度任务环境，以及本仓库自带的
网络、轨迹 Storage、PPO 与 Runner；`duck-train` 与 `duck-play` 可用。训练输出格式、日志目录
和回放入口对齐官方 mjlab + RSL-RL 约定；训练只验证到"链路通、可恢复、可回放"，
`duck-eval`/`duck-export` 属于后续任务。

## 快速开始

环境面向 **Linux x86_64、Python 3.12 和 NVIDIA GPU**。
首次使用请按 [安装文档](docs/setup.md) 配置环境，通过 `tools/setup_env.py` 安装或同步依赖。
安装后使用 `uv run --no-sync ...` 运行项目命令，保留已选定的 PyTorch 后端。

在仓库根目录运行：

```bash
# 编译模型，核对关节、电机分组与模型质量
make model

# 检查锁文件、代码、测试、模型和 Git 差异空白
make check
```

有图形桌面时，可打开静态模型预览：

```bash
make viewer
```

`make` 可列出全部检查入口。检查临时文件按次保存在 `.artifacts/checks/run-*`；
这些检查覆盖模型与代码，GPU 动态运行需使用下方专项工具。
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

# 平地速度任务：形状、有限值、命令范围、零动作保持、超时与真实终止的区分
timeout 600s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0

# 短训练：采样 + PPO 更新，检查 loss/梯度有限、checkpoint 可写可恢复
uv run --no-sync duck-train --num-envs 16 --iterations 5 --seed 0
```

可用 `--num-envs`、`--steps` 调整规模。上述工具验证仿真接入与短时响应；
实机参数和稳定站立仍需标定与验收。失败现场保留至排查结束，完成后仅清理本次生成的产物目录。
`duck-train` 默认按官方布局写到 `runs/<experiment_name>/<时间戳>_<run_name>/`，内含
`params/env.yaml`、`params/agent.yaml`、`metrics.jsonl`、`model_<iteration>.pt` 和
`model_last.pt`，控制台面板同样沿用 RSL-RL 的字段（`Total steps`、`Collection time`、
`Mean reward`、`ETA` 等）。`--out-dir` 可固定一个扁平目录。短跑只证明训练链路与数值有限，
不代表策略已学会行走。

回放已训练的策略（`--viewer native` 开 MuJoCo 窗口，`--viewer viser` 开浏览器视图，
`--video` 录 mp4；省略 `--checkpoint-file` 时取最新 `model_*.pt`）：

```bash
uv run --no-sync duck-play --checkpoint-file runs/flat_velocity/model_last.pt
uv run --no-sync duck-play --agent zero --num-envs 1          # 零动作基线
uv run --no-sync duck-play --checkpoint-file ... --video       # 录到 <checkpoint 目录>/videos/play
```

## 机器人与执行器

模型 [HT-DK_URDF.xml](src/ht_microduck/robots/ht_microduck/xmls/HT-DK_URDF.xml)
及 16 个 STL 随包保存，包含自由基座和 15 个单轴关节，模型总质量约 **3.2947 kg**。
本体 XML 只定义机器人和传感器，地形与灯光由 mjlab `Scene` 提供。
被动源模型为 `nq=22`、`nv=21`、`nu=0`；场景装配执行器后为 `nu=15`。

| 电机 | 数量 | 对应关节 | 仿真模型 |
|---|---|---|---|
| 高擎 HTDW-3532-02-DNE | 12 | 双腿 10 关节、`neck_pitch_joint`、`head_pitch_joint` | 原生 PD + 24 V 输出轴 NT 曲线近似 |
| 飞特 HD1910-C001 | 3 | `head_yaw_joint`、`head_roll_joint`、`mouth_joint` | 7.4 V BAM M6 + 摩擦模型 |

关节名称、顺序、初态、碰撞与两组执行器配置统一在
[ht_microduck_constants.py](src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py)
中定义。策略的动作子集、输出顺序和控制周期由任务配置明确声明。

当前无刷默认 `kp=10`、`kd=0.4`、力矩上限 `2 N·m`；舵机默认 `kp_fw=32`、
力矩上限 `1.471 N·m`，关闭摩擦随机化。两组命令延迟均为 `0–3` 个物理步。
这些属于仿真配置，增益、限幅、延迟和带载供电尚未完成实机标定；堵转力矩不代表持续输出能力。

`HOME_FRAME` 现在是蹲姿：`hip_pitch 0.85`、`calf −1.20`、`ankle 0.35`，
`hip_roll` 镜像内收 `+0.0873/−0.0873`，根高 `0.1534 m`。脚底与地面平行（倾角 `0.13°`，
旧零位是 `4.87°`），重心在脚掌前后各约 `35–40 mm` 之间基本居中。
实测（[T038](docs/development.md#t038-标定-home-站姿)）：5 s 零动作保持 0/128 跌倒，
根高稳定在 `0.150 m`；协调脉冲 `0.10–0.26 rad` 为 0/24，同幅度下旧零位在 `0.26 rad` 跌 2/24。
根高对站姿影响很大：任何可见离地间隙都会让复位变成落体冲击并撞散蹲姿，
所以 HOME 只留 `0.4 mm` 顶点余隙，不要为了"更保险"把 `pos` 调高。

用户提出的 `hip_roll 0.38` / `hip_pitch 1.57` 无法采用：`1.57` 正是关节限位，
腿会折到脚过髋而 48/48 全倒；`0.38` 超出平地所需，会把脚底翘起约 `17°` 而只靠内缘着地。
当前站姿与增益仍是仿真假设，不含实机标定（见 [T030](docs/development.md#t030-两类执行器imu-标定配置原始轨迹对比报告和-dr-事件)）。

XML 提供 `imu_ang_vel`、`imu_lin_vel`、`imu_accel`、`imu_upvector` 和 `root_angmom`，
场景注册名带 `robot/` 前缀。读数为理想值，IMU 安装位姿为占位配置；
`imu_lin_vel` 和 `root_angmom` 在本机无对应实机传感器，只用于 critic 或奖励。
传感器语义与观测边界见 [IMU 说明](docs/development.md#t037-在-xml-中声明-imu-参考点与内置传感器)。

## 在场景中使用

通过工厂获取独立配置副本，再按任务需要调整初态和执行器参数：

```python
from mjlab.scene import SceneCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.robots import get_ht_microduck_robot_cfg

robot_cfg = get_ht_microduck_robot_cfg()
scene_cfg = SceneCfg(
    num_envs=4,
    terrain=TerrainEntityCfg(terrain_type="plane"),
    entities={"robot": robot_cfg},
)
```

该示例只创建配置。运行动态控制前，需要通过执行器的 startup 事件或
`sim.expand_model_fields(...)` 为各环境分配独立模型字段；正式检查工具已处理。
接入方法见 [3532 NT-PD 说明](src/ht_microduck/actuators/HTDW_3532_02_DNE/params/README.md)
和 [HD1910 执行器说明](src/ht_microduck/actuators/HD_1910_C001/README.md)。

## 目录与文档

```text
HT_microduck_lab/
├── src/ht_microduck/
│   ├── robots/ht_microduck/    # 整机配置、MJCF 与 mesh
│   └── actuators/             # 3532 NT-PD、HD1910 BAM 与参数来源
├── tools/                     # 环境安装、模型与 GPU 专项检查
├── tests/                     # 正式自动化测试
├── docs/                      # 安装、开发任务、设计与审查记录
├── Makefile                   # 统一检查入口
├── pyproject.toml             # 包元数据与依赖声明
└── uv.lock                    # 依赖锁文件
```

| 文档 | 内容 |
|---|---|
| [安装与环境验证](docs/setup.md) | 环境要求、CUDA 后端选择、依赖同步和排错 |
| [开发流程与任务](docs/development.md) | 当前任务、阶段依赖、验收条件和运行证据 |
| [项目开发约定](AGENTS.md) | 仓库约束、模块边界、产物管理和交付要求 |
| [协作与审查规范](docs/collaboration_review.md) | 并发分工、集成和独立复核 |
| [3532 执行器设计](docs/design/htdw3532_nt.md) | NT 曲线、原生 PD、接口及验证依据 |

参与开发前请先阅读开发流程与项目约定，按任务表推进；具体状态与下一步安排以开发文档为准。
当前下一项是 T038（HOME 站姿与默认增益），之后是 T022（控制/观测契约）与 T023（平地速度任务），
依据是 [T041 的复核结论](docs/development.md#t041-对照三个参考项目复核下一步)。
Git 基线与最小场景已按 T001、T002 关闭，不再是后续任务的前置。
