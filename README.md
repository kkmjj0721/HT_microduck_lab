# HT_microduck_lab

基于 **mjlab 1.6.0** 搭建 HT Microduck 机器人的强化学习训练项目，面向无刷电机与舵机混合驱动。

项目采用独立 Python 包组织代码：mjlab 提供仿真、场景和环境管理；训练入口、PPO、网络、轨迹存储、Runner 和自定义执行器将在本仓库实现。
发行包名为 `ht-microduck`，Python 导入包名为 `ht_microduck`，源码位于 `src/ht_microduck/`。

## 开发流程

开发前先读 [开发流程与任务](docs/development.md) 和 [项目开发约定](AGENTS.md)。
按任务表一次推进一个任务，写清验收条件，通过检查后记录结果并按授权提交。
小修改直接在任务条目记录；大功能先明确设计、接口和验收，再按
[协作与审查规范](docs/collaboration_review.md) 完成集成与独立复核。
机器人配置与运行入口见下文；具体任务状态和阶段验收集中记录在开发文档中。

环境安装完成后，在仓库根目录运行统一检查：

```bash
make check
```

检查覆盖锁文件、代码、已有测试及模型编译；GPU 与训练效果按阶段另行验收。
检查自动隔离临时文件和缓存，每次运行会打印项目内 `.artifacts/checks/` 下的独立目录。
运行 `make` 可查看各检查入口。

## 安装

完整的环境要求、安装步骤、GPU 检查和依赖维护方法见 **[安装文档](docs/setup.md)**。

已安装 uv、满足项目要求的 CUDA Toolkit 和 NVIDIA 驱动时，在仓库根目录执行：

```bash
uv python install 3.12
python3 tools/setup_env.py
```

普通依赖使用清华 PyPI 镜像；PyTorch 和 Warp 使用各自的官方源。
下载超时后可保留现有环境和缓存，重新运行安装命令；排查方法见[安装文档](docs/setup.md#下载缓慢或出现-operation-timed-out)。

安装脚本读取本机选用 Toolkit 的 `nvcc --version`，精确匹配相同 CUDA 主、次版本的
PyTorch wheel。可用 `--dry-run` 预览；多版本共存时用
`--cuda-home /usr/local/cuda-12.6` 选择已安装目录。没有兼容组合时会报告原因。
当前开发机使用 CUDA Toolkit 13.0，已完成 `cu130` 环境安装；
PyTorch 和 Warp 均通过 RTX 4060 上的 GPU 内存分配与同步检查。

当前依赖面向 Linux x86_64，使用 Python 3.12、mjlab 1.6.0 和 `torch>=2.7,<3`。
具体依赖声明见 [pyproject.toml](pyproject.toml)，各后端解析版本由 [uv.lock](uv.lock) 固定。
安装后使用 `uv run --no-sync ...` 运行命令，保留所选后端；依赖同步继续使用安装脚本。

## 电机与关节

| 电机 | 数量 | 对应关节 |
|---|---|---|
| 高擎 HTDW-3532-02-DNE 无刷电机 | 12 | 双腿 10 个关节、`neck_pitch_joint`、`head_pitch_joint` |
| 飞特 HD1910-C001 舵机 | 3 | `head_yaw_joint`、`head_roll_joint`、`mouth_joint` |

已确认的对应关系定义在 [ht_microduck_constants.py](src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py)，
其中关节顺序与当前 MJCF 一致；策略使用哪些关节、按什么顺序输出动作由任务配置明确指定。
两组执行器分别配置控制响应、力矩限幅、摩擦和延迟；无刷已接入有来源的 24 V 输出轴 NT 曲线近似。

高擎无刷的控制约定为：策略输出目标关节角度，PD 控制器根据位置误差和关节速度计算力矩，
再进行固定力矩限幅，并按实际关节速度限制同向驱动力矩。默认目标速度与前馈力矩取零：

```text
tau_pd = kp * (q_target - q) + kd * (dq_target - dq) + tau_ff
tau = clip(tau_pd, -torque_limit, torque_limit)
# 力矩与速度同向时，再按 NT 曲线限制力矩；反向制动保留固定上限。
```

飞特 HD1910-C001 使用位置伺服控制；仿真中的等效控制增益、速度响应、摩擦及延迟单独配置，
后续根据实际舵机响应标定。

供电方案暂按 24 V 母线加舵机降压支路讨论；用户已确认舵机供电方案为 **7.4 V**，尚未记录带载端电压实测值。
HD1910-C001 的建模条件以这一供电方案为起点，后续结合舵机端实测电压与响应标定；
[飞特型号资料](https://ftservo.github.io/ftservo-wiki/products/models/hd-1910-c001/main/)
给出的 HD-1910-C001 输入电压上限为 8.4 V，不能直接接入 24 V 母线。
`ht_microduck_constants.py` 集中定义两组执行器与整机配置；默认无刷 `kp=10`、`kd=0.4`、
限幅 `2 N·m` 沿用场景检查的仿真假设，尚未经实机标定。

## 混合驱动器配置

`BRUSHLESS_ACTUATOR_CFG` 配置 12 个无刷的 `HTDW3532ActuatorCfg`，`SERVO_ACTUATOR_CFG` 配置
3 个舵机的 HD1910 BAM；两组由 `HT_MICRODUCK_ARTICULATION` 汇总。
参数在常量模块里修改；独立测试台需要自己的配置时，直接复制：

```python
from copy import deepcopy

from ht_microduck.robots.ht_microduck.ht_microduck_constants import (
    HT_MICRODUCK_ARTICULATION,
)

articulation = deepcopy(HT_MICRODUCK_ARTICULATION)
```

无刷保留 XML 的被动阻尼 `0.02`、零干摩擦和零反射惯量，均为待标定模型假设；
主动 PD 的 `damping` 与被动阻尼分别计算。无刷执行器限幅应不超过原 XML 的关节上界 `3.7 N·m`，
提高上界时需同步修改模型，避免被关节总限幅截断。
舵机默认采用厂家 7.4 V M6 参数、`kp_fw=32` 和 `1.471 N·m` 堵转近似上限，关闭摩擦随机化。
两组命令延迟均采用 `0–3` 个物理步、保持概率 `0.4`、每 `10` 步一次重采样机会，
各环境更新相位错开。这些是待标定的仿真假设，单位按每物理步写一次控制计算；
NT 曲线的 `300 rpm` 是来源数据的空载端点，用于禁止超速同向驱动；允许反向制动，不强行裁剪状态速度。
任务仍需明确动作子集、顺序和控制周期。
独立副本可直接调整；BAM 的 startup 事件或字段展开要求见下节。

运行全部 15 个独立关节的混合驱动器 GPU 专项检查：

```bash
uv run --no-sync python tools/check_robot_actuators.py --device cuda:0
```

该测试台检查配置接入、力矩控制映射、三类目标的随机延迟历史、限幅和短阶跃响应，
另在真实 Entity 控制路径验证高速 NT 限幅、超速制动与零请求；整机检查使用下一节的入口。

## 3532 无刷 NT 执行器

实现位于 [actuators/HTDW_3532_02_DNE](src/ht_microduck/actuators/HTDW_3532_02_DNE/)，
复用 mjlab 1.6.0 的 `IdealPdActuator` 参数与生命周期，通过 MuJoCo 原生 affine PD 保留隐式阻尼积分。
Python 每步按当前速度更新有方向的力矩范围；增益、惯量和物理步长沿用本项目配置。
策略仍传关节位置目标；实体的无刷 `ctrl` 是 `kp*q_target + kd*dq_target + tau_ff`（N·m），
实际力矩由原生 `-kp*q-kd*dq` 和 NT 范围共同确定，应读取 `actuator_force` / `qfrc_actuator`。
两项正式工具已同步；命令目标由 mjlab 延迟一次，反馈使用当前状态。

[参数与原始资料](src/ht_microduck/actuators/HTDW_3532_02_DNE/params/README.md)
来自用户指定的 duck_project，已复制入包内，运行时不依赖参考目录。
曲线是 24 V 输出轴资料图的分段近似：`167/211 rpm` 对应 `1.5/1.0 N·m`，
`300 rpm` 及以上同向驱动为零；转速从 rad/s 转换一次，不再叠加减速比 32。
反向制动保持配置的固定力矩上限，是尚未实测的仿真假设。
额定 `0.6 N·m` 与堵转 `3.7 N·m` 分开记录；默认 `2 N·m` 不表示连续额定能力，
未推定热模型、峰值持续时间或其他电压下的曲线。

需要显式提供其他已取得的输出轴曲线时，可设置配置副本的 `json_path`；JSON 格式见参数说明。
`set_effort_limit` 可在运行时降低限幅，不能解除编译后的 MuJoCo 执行器/XML 上限。

在环境中把导出的 `htdw3532_init` 注册为 startup 事件，以声明需要独立的
`actuator_forcerange` / `actuator_biasprm` 字段。独立 Scene/Simulation 在控制与 reset 前调用：

```python
sim.expand_model_fields(
    ("dof_frictionloss", "dof_damping", "actuator_forcerange", "actuator_biasprm")
)
```

前两项供 HD1910 BAM 使用，后两项供 3532 的 NT 范围和动态增益使用；正式工具已包含这一步。

## 整机配置与最小场景

配置参照 [Microduck 官方常量模块](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)，
直接定义 `HOME_FRAME`、两组 `ACTUATOR_CFG`、`FULL_COLLISION`、`HT_MICRODUCK_ARTICULATION`
和 `HT_MICRODUCK_ROBOT_CFG`。官方使用 XL330 M6，`kp_fw=200`、延迟 `3–6` 步；
本机采用不同硬件，保留 HD1910 的 `kp_fw=32` 和用户选定的 `0–3` 步延迟，不照搬这些数值。
场景通过无参入口获取整机配置副本：

```python
from mjlab.scene import SceneCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.robots import get_ht_microduck_robot_cfg

scene_cfg = SceneCfg(
    num_envs=4,
    terrain=TerrainEntityCfg(terrain_type="plane"),
    entities={"robot": get_ht_microduck_robot_cfg()},
)
```

`get_ht_microduck_robot_cfg()` 只返回深拷贝，不接收参数。任务需要不同增益或初态时，
直接修改副本，例如 `cfg.articulation.actuators[0].stiffness = 2.0` 或
`cfg.init_state.joint_pos["neck_pitch_joint"] = 0.03`，不会影响模块默认值。

`ht_microduck_constants.py` 与官方 `microduck_constants.py` 同构：路径常量加存在性断言、
一行式 `get_spec()`、`HOME_FRAME`、单套 `FULL_COLLISION`、执行器配置与整机实体，末尾用 mjlab
`Scene` 做可视化预览；执行器沿用本地 `ht_microduck.actuators` 的实现。
`HT-DK_URDF.xml` 只含机器人本体（compiler、asset、worldbody、sensor）。mjlab 的 `Scene` 自带
terrain 平面与灯光，因此本体 XML 不含 `floor`、`light` 或 `skybox`，也不再另设预览场景文件；
`get_robot_spec()` 只负责碰撞体命名与足底 site。
默认 `HOME_FRAME` 为根高 `0.171 m`、单位四元数、15 个关节零位和零速度；
新模型双足底左右镜像倾斜约 `5°`，初态下最低足边离地约 `3.840 mm`，没有初始碰撞，并非已验证的实机站姿。
初态字典随整机配置一起深拷贝，任务可直接修改，避免多场景间共享修改。

现有 10 个机器人碰撞体均被命名，足部为 `r_foot_collision` / `l_foot_collision`；
单套规则保留身体与足部的碰撞资格及 MuJoCo 的标准自碰撞过滤。
摩擦 `(1.0, 0.005, 0.0001)`、`condim=3` 沿用源模型默认值，均为未标定仿真假设。
左右足底中心 site 为 `r_foot` / `l_foot`，位置按新 STL 倾斜足底面的包围盒中心确定，方向沿用踝坐标系；
接触、足高观测按任务需要另行配置。

XML 另含 IMU：挂在 `base_link` 原点处、单位姿态的 `imu` site 及 5 个内置传感器
`imu_ang_vel` / `imu_lin_vel` / `imu_accel` / `imu_upvector` / `root_angmom`，
场景中对应 `robot/imu_ang_vel` 等名称，可直接用 `mdp.builtin_sensor` 或
`mdp.projected_gravity_from_sensor` 取用。读数为理想值，不含噪声、延迟与安装误差；
`imu_accel` 为比力语义（自由落体为 0，有支撑静止时约 `+9.81·imu_upvector`），
重力方向请用 `imu_upvector`/投影重力；`imu_lin_vel` 与 `root_angmom` 在本机无对应实机传感器，
只适合 critic 或奖励，不能进 actor 观测；
安装载体（`base_link`）、传感器组合与名称沿用官方做法（官方 `imu` site 同样挂在 `trunk_base`）；
但官方 site 在基座上带有 `(-0.021, 0.0001, -0.0147) m` 的偏移，本机该偏移尚未测量，
故 `pos="0 0 0"` 是仿真占位，噪声与延迟属任务观测配置。
软关节限位系数默认 `1.0`，保留嘴部零位闭合姿态；任务可显式调整。

运行真实机器人四环境 GPU 场景检查：

```bash
uv run --no-sync python tools/check_robot_scene.py --device cuda:0
```

工具检查单一地面、15 个执行器、双脚接地、目标映射、状态有限值、力矩上限和局部 reset 隔离；
另核对 5 个 IMU/根传感器在场景中的名称、维度与有限值，并比对陀螺与根角速度、up 向量与投影重力。
默认运行 `150` 个 `0.002 s` 物理步，另用颈部 `0.03 rad` 测试初态验证非零保持目标；
所有增益、限幅和时序均是显式检查假设。`scene.reset()` 仅清理控制状态，工具另行恢复根状态、
关节状态和全部保持目标，并在首次控制写入前展开 BAM 模型字段。
该检查验证整机接线与短步进；稳定站立、任务控制周期和训练效果仍需后续验收。

在有图形桌面的终端中，也可直接运行常量模块，查看整机模型：

```bash
uv run --no-sync python src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py
```

预览直接使用 `HT_MICRODUCK_ROBOT_CFG`，参数统一在模块中修改，默认值仍为仿真假设。
该入口只编译实体模型供预览；完整动态控制使用 mjlab 场景检查，运行 Python NT-PD 与 BAM。

## HD1910 自定义执行器

已实现适配 mjlab 1.6.0 的 HD1910 M6 执行器和摩擦随机化封装，代码位于
[actuators/HD_1910_C001](src/ht_microduck/actuators/HD_1910_C001/)。
使用[飞特公开的 7.4 V 参数](src/ht_microduck/actuators/HD_1910_C001/params/README.md)，
电气力矩由 Python 计算，干摩擦预算和粘性阻尼由 MuJoCo 求解器处理；不需要安装 BAM 包。
原始 MJCF 和 `get_spec()` 保持用于模型检查；整机工厂通过 articulation 接入这些执行器。

需要单独配置三个舵机关节时，可以使用：

```python
from mjlab.managers.event_manager import EventTermCfg

from ht_microduck.actuators import FrictionDRBamActuatorCfg, bam_init
from ht_microduck.robots.ht_microduck.ht_microduck_constants import SERVO_JOINT_NAMES

servo_actuator = FrictionDRBamActuatorCfg(
    target_names_expr=SERVO_JOINT_NAMES,
    vin=7.4,
    kp_fw=32.0,                 # 厂家控制器模型假设，尚非本机读回值
    effort_limit=1.471,          # 7.4 V 堵转规格近似，不是持续力矩
    friction_scale_range=None,  # 首先关闭随机化，取得确定性响应
    delay_min_lag=0,            # 与机器人工厂一致，仍为未测的仿真假设
    delay_max_lag=3,
    delay_hold_prob=0.4,
    delay_update_period=10,
)
bam_startup = EventTermCfg(func=bam_init, mode="startup")
```

将 `servo_actuator` 加入实体的 `EntityArticulationInfoCfg.actuators`，无刷另用自己的 PD 配置；
将 `bam_startup` 加入环境的 startup 事件，使摩擦和阻尼字段按环境独立分配。
独立使用 `Scene` / `Simulation` 时，在写入控制前调用
`sim.expand_model_fields(("dof_frictionloss", "dof_damping"))`。
延迟单位为物理步，由 mjlab 在调用执行器前处理；厂家 JSON 的台架延迟和零位偏差不自动施加。

`kp_fw` 不是 SI 制的关节刚度；当前模型是厂家 P 电压控制加反电动势，不包含独立固件 D 项。
模型覆盖其所控制关节的原 XML 被动阻尼、摩擦、反射惯量和执行器力矩范围，避免重复计入。
可显式用 `armature` 覆盖拟合惯量；干摩擦和粘性阻尼通过参数 JSON 管理。
需要摩擦随机化时再设置 `friction_scale_range`，启动及每次 reset 按环境采样一次，
同组关节共享系数；只缩放干摩擦预算，粘性阻尼保持标称值。
`reset_friction_scale()` 恢复系数为 1，`reset()` 按配置重采样选定环境。

在开发机上运行三关节、四环境的短 GPU 检查：

```bash
uv run --no-sync python tools/check_hd1910.py --device cuda:0
```

该检查覆盖延迟、局部重置、摩擦字段独立性、单次摩擦缩放、力矩限幅及阶跃/保持响应。
它验证执行器集成，不代表完整机器人已能站立或厂家模型已与本机实测一致。

## 第一步：模型加载与检查

`ht_microduck_constants.py` 中的 `get_spec()` 加载 `xmls/HT-DK_URDF.xml`，
XML 通过 `meshdir="assets/"` 声明网格目录，由 MuJoCo 相对模型 XML 所在目录解析，
不需要在 Python 中覆盖 `spec.meshdir`，也不依赖命令执行时的工作目录。
模型与全部 16 个 STL 来自用户提供的 `/home/sunteng/Downloads/HT-DK_URDF`，已复制到包内；
随包 MJCF 仅调整 mesh 路径及预览根高（`0.167 → 0.171 m`），避免新足底穿地，运行时不依赖原目录。
检查模型编译、关节顺序、电机分组、关节范围及模型总质量：

```bash
uv run --no-sync python tools/check_robot.py
```

在本机有图形桌面的终端中打开静态预览：

```bash
uv run --no-sync python tools/check_robot.py --viewer
```

当前模型包含 15 个单轴关节和 1 个自由基座，`nq=22`、`nv=21`、`nu=0`，
模型总质量约 3.2947 kg。这里 `nu=0` 表示检查的是被动源模型，预览窗口仅用于核对形状和姿态。
`tools/check_robot.py` 会断言本体 XML 中没有平面和灯光；`--viewer` 用 mjlab `Scene` 预览，
地面和灯光由场景提供。整机工厂只加载本体，并接入无刷 PD 与舵机 BAM，编译后 `nu=15`。

## 当前状态

- 已配置项目依赖和锁文件，验证锁文件一致性及 Python wheel 构建，并完成开发机 GPU 基础检查。
- 已切换至机器人模型 `HT-DK_URDF.xml` 和配套 mesh 资源，关节顺序及 12+3 电机分组保持兼容。
- `ht_microduck_constants.py` 已提供整机实体工厂、显式中性初态、碰撞规则及足底参考点，另有最小平地场景检查。
- 已实现 3532 NT-PD、HD1910 M6 执行器、摩擦随机化和 12+3 混合配置，保留独立与整机检查入口；实机标定仍待完成。
- 本地训练入口、任务环境、PPO、网络和 Runner 待实现；`duck-train` 等入口已在配置文件中注释预留。
- 模型已声明 `imu` site 与 5 个内置传感器（T037），最先缺的观测来源已就位；读数为理想值。
- 已知缺口（T036 记录）：HOME 全零站姿脚底外倾 `5°`、
  单脚支撑仅 `1.59 cm²`，`hip_roll` 内收 `0.0873 rad` 的候选站姿几何与保持都更好，取向待用户确认。
  下一步顺序为 Git 基线（T001）→ 站姿标定（T038）→ 控制/观测契约（T022）。

## 当前目录

```text
HT_microduck_lab/
├── pyproject.toml              # 项目元数据、依赖和包源
├── uv.lock                     # uv 生成的依赖锁文件
├── README.md
├── AGENTS.md                   # AI 与开发者遵循的开发约定
├── Makefile                    # 统一检查入口
├── docs/
│   ├── setup.md                # 安装与环境验证
│   └── development.md          # 工作流、任务状态和阶段验收
├── tools/
│   ├── setup_env.py            # 检测本机 CUDA Toolkit 并安装对应 PyTorch
│   ├── check_robot.py          # 模型编译、关节检查及静态预览
│   ├── check_hd1910.py         # HD1910 执行器 GPU 专项检查
│   ├── check_robot_actuators.py # 15 关节混合驱动器 GPU 检查
│   └── check_robot_scene.py     # 真实机器人 GPU 场景、接触与 reset 检查
├── tests/
│   ├── test_setup_env.py       # 安装脚本测试
│   ├── test_hd1910_actuator.py # HD1910 参数、公式和模型配置检查
│   ├── test_htdw3532_actuator.py # 3532 曲线、原生 PD、模型字段与 reset 检查
│   ├── test_robot_actuators.py # 混合驱动器配置与 PD 力矩检查
│   └── test_robot_entity.py    # 整机初态、碰撞、足底及场景组合检查
└── src/ht_microduck/
    ├── __init__.py
    ├── actuators/
    │   ├── HTDW_3532_02_DNE/
    │   │   ├── model.py              # 输出轴 NT 插值与驱动/制动限幅
    │   │   ├── nt_actuator.py        # mjlab 1.6 原生 affine PD + NT 范围
    │   │   └── params/              # 24 V 曲线、原始资料图与来源
    │   └── HD_1910_C001/
    │       ├── model.py              # 参数加载、电气与 M6 摩擦公式
    │       ├── bam_actuator.py       # mjlab 1.6 适配
    │       ├── friction_dr_bam.py    # 摩擦随机化
    │       └── params/              # 厂家原始参数与来源
    └── robots/
        ├── __init__.py
        └── ht_microduck/
            ├── __init__.py
            ├── ht_microduck_constants.py  # 模型、整机实体、关节与混合驱动器配置
            └── xmls/
                ├── HT-DK_URDF.xml
                └── assets/
```

## 构建顺序

1. 安装并验证 Python、PyTorch 和 Warp 的 GPU 环境。
2. 接入机器人模型、关节映射、无刷与舵机执行器。
3. 实现平地速度任务和本地训练链路：入口 → Runner → PPO → Storage → 环境。
4. 完成检查点恢复、回放、定量评估和 ONNX 导出验证。
