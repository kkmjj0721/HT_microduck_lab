# HD1910-C001 执行器

本目录实现飞特 **HD1910-C001** 的仿真执行器，适配项目固定的 **mjlab 1.6.0**。
采用飞特公开的 **7.4 V BAM M6 参数**，在本项目内实现电气力矩、摩擦预算和摩擦域随机化，
不需要额外安装 BAM 包。

本项目有三个 HD1910 舵机关节：`head_yaw_joint`、`head_roll_joint`、`mouth_joint`。
名称以 [ht_microduck_constants.py](../../robot/ht_microduck_constants.py) 的
`SERVO_JOINT_NAMES` 为准；12 个无刷关节使用独立配置。
本目录提供已通过独立测试台验证的组件，完整机器人实体和场景的接入记录见
[开发文档](../../../../docs/development.md)。

## 目录结构

```text
HD_1910_C001/
├── README.md
├── __init__.py                   # 导出执行器类、配置类及 bam_init
├── model.py                      # 参数加载、电气力矩与 M6 干摩擦公式
├── bam_actuator.py               # mjlab 生命周期与 MuJoCo 摩擦字段接入
├── friction_dr_bam.py            # 摩擦域随机化的单次缩放
├── params/
│   ├── feetech_hd1910_7_4V_m6.json  # 厂家原始参数
│   └── README.md                   # 固定版本、校验值和参数来源
├── NOTICE                       # 上游归属和本地修改说明
└── THIRD_PARTY_LICENSE           # Apache-2.0 许可证
```

## 模型如何工作

策略给出目标关节角度。执行器根据位置误差计算 PWM 占空比和电机电压，
再根据反电动势计算输出侧电机力矩：

```text
error = q_target - q
duty = clip(0.163 * kp_fw * error, -0.97, 0.97)
voltage = vin * duty
motor_torque = kt * (voltage - kt * dq) / R
output_torque = clip(motor_torque, -effort_limit, effort_limit)
```

角度、角速度和力矩分别使用 `rad`、`rad/s`、`N·m`。
`kp_fw` 是厂家控制器模型的固件增益，不是单位为 `N·m/rad` 的关节刚度。
当前模型为 **P 电压控制加反电动势**，没有独立固件 D 项；
`velocity_target` 和 `effort_target` 不参与该控制律。

M6 根据上一物理步的实际电机力矩、外载荷及当前速度计算非负干摩擦预算，
包含基础摩擦、Stribeck 效应、方向相关的负载摩擦及二次项。
预算写入 MuJoCo 的 `dof_frictionloss`，粘性系数写入 `dof_damping`，由求解器处理摩擦。
返回的电机力矩不再手动减去同一份摩擦。

本地二次项遵循上游标量辨识公式，修正了其 GPU 实现中遗漏的符号及等幅条件。
实现细节见 [model.py](model.py)，参数工况及差异说明见 [params/README.md](params/README.md)。

## 配置三个舵机关节

所有示例均使用已安装的项目环境。配置入口可以从 `ht_microduck.actuator` 导入：

```python
from mjlab.managers.event_manager import EventTermCfg

from ht_microduck.actuator import FrictionDRBamActuatorCfg, bam_init
from ht_microduck.robot.ht_microduck_constants import SERVO_JOINT_NAMES

servo_actuator = FrictionDRBamActuatorCfg(
    target_names_expr=SERVO_JOINT_NAMES,
    vin=7.4,
    kp_fw=32.0,
    effort_limit=1.471,
    friction_scale_range=None,
    delay_min_lag=0,
    delay_max_lag=0,
)
bam_startup = EventTermCfg(func=bam_init, mode="startup")
```

将 `servo_actuator` 加入机器人实体的 `EntityArticulationInfoCfg.actuators` 元组，
并将 `bam_startup` 加入任务环境的 startup 事件。
同一个关节只能由一个执行器配置覆盖；当前实现只支持 `JOINT` 传动下的单轴 hinge 关节。

若只需要确定性基础模型，也可使用 `HD1910BamActuatorCfg`；
`FrictionDRBamActuatorCfg` 在 `friction_scale_range=None` 时默认摩擦系数为 1。

| 字段 | 默认值 | 含义 |
|---|---|---|
| `target_names_expr` | 必填 | 关节名称或匹配表达式，本项目使用 `SERVO_JOINT_NAMES` |
| `json_path` | `None` | 使用随包的厂家 M6 参数；非空时加载完整、有效的 HD1910 M6 JSON |
| `vin` | `7.4` | 仿真供电电压，当前配置允许 `0 < vin <= 8.4` V |
| `kp_fw` | `32.0` | 非负固件模型增益，尚非本机回读值 |
| `effort_limit` | `1.471` | 输出侧力矩上限，单位 N·m；默认取堵转规格近似，不是持续力矩 |
| `armature` | `None` | 使用拟合反射惯量；显式值覆盖该项，单位 kg·m² |
| `stiff_frictionloss` | `True` | 使用本适配器的较硬干摩擦约束参数 |
| `friction_scale_range` | `None` | DR 配置类专有；可设非负、有序的采样区间 |
| `delay_min_lag` / `delay_max_lag` | `0` / `0` | 最小/最大命令延迟，单位为物理步 |

首轮验证采用固定 7.4 V、关闭 DR、零额外延迟；这是明确的建模起点。
即使配置接受其他电压，随包参数仍来自 7.4 V 辨识工况，其他工况需重新验证。
厂家默认增益及控制律也需要与实机固件模式和回读值核对。

## 摩擦字段与 XML 参数

每个并行环境都需要独立的 `dof_frictionloss` 和 `dof_damping` 存储。
上面的 `bam_init` startup 事件向 mjlab 声明这一要求。

独立使用 `Scene` / `Simulation` 时，在实体初始化后、第一次写控制前调用：

```python
# sim 是已创建并用于初始化 Scene 的 mjlab Simulation。
sim.expand_model_fields(("dof_frictionloss", "dof_damping"))
```

未正确展开字段时，执行器会明确报错。展开后会重新读取模型字段，避免继续写入旧数组。

执行器创建时会覆盖所控制关节的 XML 摩擦、粘性阻尼和反射惯量，
并使 motor 限幅与关节总执行器力矩范围都等于配置的 `effort_limit`。
因此不再叠加原 XML 的 `damping=0.02`。
配置中的 `frictionloss`、`viscous_damping` 必须保留为 `None`，这两项由 BAM 参数 JSON 管理；
`armature` 则允许显式覆盖。

## 摩擦随机化与重置

取得确定性基线后，可显式设置 `friction_scale_range`。
例如 `(0.8, 1.2)` 表示在标称干摩擦预算的 80%～120% 之间均匀采样，
这里只是仿真实验示例，不是本机测量所得的范围。

- 在初始化和每次 `reset(env_ids)` 时，为选中的每个环境采样一个系数。
- 同一执行器组内的关节共享该环境系数，干摩擦预算只缩放一次。
- 粘性阻尼保持标称值，不随该系数缩放。
- `set_friction_scale(env_ids, values)` 手动设置系数；支持标量、`(N,)` 或 `(N, 1)`，其中 N 为所选环境数。
- `reset_friction_scale(env_ids)` 恢复所选环境的系数为 1，不进行随机采样。
- `reset(env_ids)` 清理所选环境的延迟和历史，并按配置恢复或重采样摩擦；其他环境保持原状态。

执行器完成初始化后，可通过运行实例操作：

```python
# actuator 是初始化后的 FrictionDRBamActuator 实例。
actuator.set_friction_scale(None, 1.1)  # 所有环境设为标称干摩擦的 1.1 倍
actuator.reset_friction_scale()        # 所有环境恢复系数 1
```

重置后，旧物理解中的载荷不会立即重新参与摩擦估计。
只有新物理步完成并调用 `update()` 后，求解载荷才再次有效。
独立测试台需保持 `scene.write_data_to_sim()` → `sim.step()` → `scene.update(dt)` 的调用顺序。

## 命令延迟

`delay_min_lag` / `delay_max_lag` 使用物理步计数，由 mjlab Entity 在调用执行器前应用一次。
例如物理步长 `dt=0.002 s` 时，延迟 2 步对应 4 ms；不能用策略步长代替这里的物理步长。

厂家 JSON 中的 `command_delay` 与 `q_offset` 属于辨识工况元数据。
本项目保留它们以追溯来源，不自动将其作为整机总线延迟或机器人关节零位。

## 验证命令

从项目根目录 `/home/sunteng/projects/HT_microduck_lab` 运行。
按[项目安装说明](../../../../docs/setup.md)准备环境后，使用 `uv run --no-sync` 保留已选择的后端。
验证临时目录放在项目内：

```bash
check_hd1910_dir="$PWD/.artifacts/hd1910-check"
mkdir -p "$check_hd1910_dir/tmp"
export TMPDIR="$check_hd1910_dir/tmp"
export PYTHONDONTWRITEBYTECODE=1
export RUFF_CACHE_DIR="$check_hd1910_dir/ruff"
export PYTEST_ADDOPTS="--basetemp=$check_hd1910_dir/pytest -o cache_dir=$check_hd1910_dir/pytest-cache"
export WARP_CACHE_PATH="$check_hd1910_dir/warp-cache"
export TORCHINDUCTOR_CACHE_DIR="$check_hd1910_dir/torchinductor"
```

项目统一检查：

```bash
make check
```

只运行本模块的 CPU 检查：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync python -B -m pytest -q tests/test_hd1910_actuator.py
```

运行四环境、每环境三个关节的 GPU 检查：

```bash
uv run --no-sync python -B tools/check_hd1910.py --device cuda:0 --num-envs 4 --steps 300
```

CPU 检查覆盖参数加载、电气和摩擦公式、配置约束及 spec 修改。
GPU 检查覆盖字段展开、精确命令延迟、局部 reset、外载荷、旧载荷隔离、
摩擦单次缩放、力矩限幅和阶跃/保持响应。
测试台关闭重力和接触，使用显式的 `0.35 N·m` 测试力矩上限；
这些检查验证组件集成，完整机器人站立、训练和实机拟合效果另行验收。
已执行的命令、结果和阶段状态统一记录在[开发文档](../../../../docs/development.md)。

## 参数来源与许可

厂家参数固定于 `ftservo/ftservo-bam` 提交
`4f7c0b0de3debf9c1ab254fc9654676e8aab9317`。
具体来源、SHA256 和拟合条件见 [params/README.md](params/README.md)。
这些参数是公开模型起点，尚非本项目三只舵机的标定结果。
加载器仅接受当前 HD1910 M6 格式，并明确处理 `hd1910` / `HD1910` 别名。
更新本机标定结果时，使用新的参数文件并通过 `json_path` 指定，保留厂家原始文件以便对照。

上游归属与本地修改见 [NOTICE](NOTICE)，许可证见 [THIRD_PARTY_LICENSE](THIRD_PARTY_LICENSE)。
