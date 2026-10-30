# 任务条目归档

本文件保存已结束任务的目标、范围、验收条件和当时结论。
任务**当前状态**只在 [开发流程与任务](../development.md) 的任务表维护；
进行中任务的范围与下一步见 `development.md` 的「当前任务详情」。

搬移采用整段原文搬运：条目内的 `状态：…`、依赖说明与当时结论都是**当时记录的原文**，
保留不删，也不据此判断现状——判断现状只看任务表。顺序沿用原文档，
任务编号递增，`T022–T031` 合并块和 `T023–T026` 的排布照旧；
T027–T031 共用一个前瞻块，T042/T043 只有完成记录、没有单独条目。

改动任务结论时优先在本文件对应条目追加「追加（日期）」段落，保留原记录作为当时决策依据。

### T001 整理现有开发基线

目标：将已有的环境安装、模型加载和文档重组整理为可回溯的基线。

范围：审阅现有修改、新文件及删除项，确认旧文档与旧工具的替代关系，补齐必要的生成文件忽略规则，
按用途组织提交。当前工作区的已有改动需要逐项审阅，暂存时列出具体路径。

验收条件：

- `make check` 通过。
- README 中的安装、模型检查和文档链接与当前文件一致。
- 提交中包含所需源码、XML 和 mesh，排除虚拟环境、缓存及训练输出。
- 按当前会话授权完成基线提交后，`git status --short --branch` 中的剩余改动均有明确归属。

T021 复核补充：当前仅 README 被 Git 跟踪，已有代码、文档、依赖和测试尚未纳入基线，
且没有根 `.gitignore`；需审阅资源归属并补充环境、缓存和训练输出的忽略规则。
现有 constants 预览入口 `import` 排版触发 Ruff `I001`，须在基线验收时修复；T021 未修改该文件。
本次比较不包含 Git 提交授权。

T032 后续更新：忽略规则与统一检查入口已纳入本次工作流完善；具体结果见 T032 完成记录。
Git 基线的资源审阅与提交仍由本任务负责，不能仅因工作流和检查就绪关闭 T001。

T041 复核结论（完成）：Git 基线已经具备。提交 `21589d7`（2026-10-27 14:30，作者 KKMJJ0721）
以 60 个文件、11260 行新增把 `.gitignore`、`AGENTS.md`、`Makefile`、`README.md`、
`docs/`、`pyproject.toml`、`uv.lock`、`src/`、`tests/`、`tools/` 及 16 个 STL 一并纳入跟踪；
`git ls-files --others --exclude-standard` 为 0，工作区只有 T040/T041 的文档改动。
`.gitignore` 排除 `/.venv/`、`__pycache__/`、`/.artifacts/`、`/outputs/`、`/runs/` 等，
未跟踪任何环境、缓存或训练产物，也没有全局忽略 `*.pt`/`*.onnx`/`*.json`。
constants 的 Ruff `I001` 已在 T032 修复，本轮 `make check` 全程通过。
因此 T001 的四条验收条件均满足，状态改为完成；本任务未新增 Git 写操作。

### T002 接入 mjlab 机器人实体与最小场景

目标：复用现有 MJCF 加载器，将机器人放进由 mjlab 管理的最小场景。

当前实现更新：T016 按用户后续授权完成本任务的实体/场景功能，并一并接入混合执行器。
本任务仍待前置 T001 的 Git 基线验收，不重复实现已交付功能；T001 完成后依据 T016 证据复核并关闭。

范围：机器人实体配置、场景地面与灯光归属、一个可执行的场景检查入口。
混合执行器的控制和标定在后续任务中处理。

验收条件：

- 原有 `make check` 通过，独立模型检查继续可用。
- 在开发机 GPU 上创建并重置小规模场景，验证根状态和关节状态的维度及有限值。
- 场景中地面与灯光配置的归属明确，没有重复地面。
- 将实际执行的检查命令和结果写入完成记录。

M1 后续先拆分混合执行器任务，明确动作顺序、控制周期、增益、限幅和参数来源，再进入 M2。
M2 开始前将任务环境、网络与 Storage、PPO 更新、Runner 与入口分别拆成可验收任务。

T041 复核结论（完成）：T001 已关闭，本任务的前置条件满足，四条验收条件均有本轮证据。
本轮实际执行的整机场景检查为 `cuda:0`、4 环境、150 步、`dt=0.002 s`，退出码 0，
末根高 `0.166165–0.166172 m`、峰值力矩 `0.138278 N·m`、峰值关节速度 `0.184298 rad/s`；
双脚全程接地、`planes=1`（仅 mjlab terrain）、IMU 传感器 5 个、局部 reset 与目标映射通过。
地面与灯光的归属由 T039 的模型拆分固定：本体 XML 无 floor/light，场景提供 terrain 与太阳。
`make check` 通过（锁文件、Ruff、134 项测试与 8 项子测试、模型、Git 差异空白），
被动模型仍为 `nq=22`、`nv=21`、`nu=0`、15 关节、16 网格、质量 `3.2947 kg`。
状态改为完成；执行器标定与稳定站立仍分别属于 T030、T031，不在本任务范围。

### T003 补充并发与测试文件管理规则

目标：在 `AGENTS.md` 明确多代理并发、项目内测试与验证文件管理，以及交付前缓存清理规则。

范围：补充并发分工、文件归属、临时目录和清理要求，并同步规则中的现行包路径与关节定义模块。

验收条件：

- 并发规则经独立子代理只读复核，明确同一任务内拆分及同文件单写者。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过。
- 清理项目源码、工具和测试中的 `__pycache__`、`.pyc`、`.pyo` 及本次临时验证目录，复查无残留。

### T004 评审 robots 模块缺项

目标：依据当前机器人模型和已安装的 mjlab 1.6.0 接口，明确 `robots/` 的已有能力、缺项和实现顺序。

范围：只读检查模型加载、关节映射、MJCF、模型检查工具和 mjlab 实体配置；仅更新本任务记录，不实现机器人行为。

验收条件：

- 独立子代理复核模型配置与 mjlab 接入接口，建议提供源码依据并区分机器人配置与任务配置。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过。
- 记录按依赖排序的缺项、参数未知项与下一项最小可执行工作；清理本次临时验证目录及项目字节码缓存。

评审结论与后续顺序：

1. **T002 先接实体和最小场景。** 在现有 `ht_microduck_constants.py` 中补充返回新 `EntityCfg` 的
   `get_ht_microduck_robot_cfg()`，明确 `EntityCfg.InitialStateCfg` 中的基座位置、四元数、关节角和速度。
   已安装的 mjlab 在 `entity/entity.py` 的 `_add_initial_state_keyframe()` 中用该配置生成自由基座初始状态，
   默认位置是原点；不能只依赖原 XML 的基座高度 `0.167 m`，也不能假定全零关节角可以稳定站立。
2. **明确模型与场景归属。** 保留现有 `get_spec()` 的独立模型检查用途，为实体提供去除原始地面和灯光的
   加载入口，由 mjlab 场景统一管理地面和灯光，避免重复地面。
3. **随后单独接入混合执行器。** 依据已确认的 12 个无刷和 3 个舵机关节，分别配置控制响应，
   通过 `EntityArticulationInfoCfg.actuators` 接入。无刷按项目约定实现位置目标到 PD 力矩及限幅；
   舵机先建立等效位置伺服模型，必要时再补速度响应和延迟。执行器可以在 Python 配置中生成，
   无须预先手写到原 XML。增益、速度限制、供电、惯量及延迟须注明来源或仿真假设；
   原 XML 的 `±3.7`、`±1.47 N·m` 和统一 `damping=0.02` 不能视为已标定实机参数。
4. **按接触观测需要完善模型。** 当前机器人碰撞几何均未命名，建议为左右脚等关键几何命名，
   明确摩擦和自碰撞策略；足底 site 在任务需要足端位置等观测时再添加。
   当前没有显式 site 或 sensor，不构成被动实体接入的硬前置条件；现有 mesh 碰撞效果仍需动态验证。
5. **按阶段扩展验证。** T002 通过小规模 GPU 场景创建和重置验证状态；执行器任务再验证分组覆盖、
   目标映射、阶跃响应、力矩限幅及短跑有限值。现有 `check_robot.py` 只检查编译、关节名/顺序和映射覆盖，
   `nu=0` 仍正常退出，viewer 也只有 `mj_forward`，没有物理步进，不能代替动态验收。

机器人配置初期可继续集中在现有 constants 模块，随复杂度增长再拆分；公共 `__init__.py` 的导出按调用需要补充。
动作子集、动作顺序与缩放、观测、奖励、终止条件和控制周期由任务配置明确，PPO、Storage、Runner 保持在独立模块。
本轮评审不改变 M0/M1 状态，开发实施仍先完成 T001，再进入 T002。

### T005 核实并简化 MJCF 资源加载

目标：依据 mjlab 1.6.0 官方源码和文档，核实 `get_spec()` 的资源加载方式并去除不必要的路径覆盖。

范围：模型加载器、当前 README 的资源路径说明和本任务记录；保留历史验证记录，不更改 XML 或机器人行为。

验收条件：

- 核对官方固定版本的 `get_spec()` 示例和 MuJoCo 资源路径规则，记录来源。
- 删除不必要的 `spec.meshdir` 赋值后，从项目内其他工作目录加载并编译模型，验证网格和模型结构不变，
  并验证机器人 spec 组合进父 spec 后仍可编译。
- 设置项目内 `TMPDIR`、pytest `--basetemp` 和 `PYTHONDONTWRITEBYTECODE=1`，执行 `make check` 通过。
- 等待子代理与检查进程结束，清理本次临时验证目录和项目字节码缓存。

核查结论：用户指出的路径覆盖确实多余。[mjlab 1.6.0 Entity 文档的 `spec_fn` 示例](https://mujocolab.github.io/mjlab/v1.6.0/source/entity/index.html#spec-fn)
和[官方 v1.6.0 Go1 加载器](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py)
均直接返回 `mujoco.MjSpec.from_file(...)`。根据 [MuJoCo 3.11.0 的 `meshdir` 规则](https://mujoco.readthedocs.io/en/3.11.0/XMLreference.html#compiler-meshdir)，
本项目绝对路径 MJCF 配合 XML 中已有的 `meshdir="assets/"`，即可相对 XML 所在目录解析全部 STL。
这是 MuJoCo 的资源路径机制，不将其表述为 mjlab 1.6.0 才新增的功能。

`get_spec()` 改为直接返回新 spec，删除冗余 `spec.meshdir` 覆盖和不再使用的 `ASSETS_DIR` 常量；
README 改为说明资源路径由 XML 声明、由 MuJoCo 解析。XML 和历史完成记录保留。

### T006 分析混合执行器配置方案

目标：结合 mjlab 1.6.0 官方接口、本项目关节映射及硬件官方资料，给出无刷和舵机的分组、参数来源与验证顺序。

范围：只读调研、本页记录和 README 中用户已确认的硬件信息，不实现执行器或填入未经确认的实机参数，
不推进 M1 验收状态。

验收条件：

- 并行核对官方执行器 API、项目 XML/关节映射和制造商资料，区分首版仿真近似与后续标定模型。
- 说明两类执行器的控制方式、增益/限幅/惯量/摩擦/延迟归属，以及原 XML 参数与 Python 配置的交互。
- 给出可执行的后续验证步骤，明确尚缺的硬件信息；未运行的动态验证如实记录。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过；
  全部子代理和检查进程结束后清理本次临时产物及项目字节码缓存。

用户确认的设计输入：无刷使用普通 PD 控制；三个舵机为飞特 **HD1910-C001，供电 7.4 V**。
这里的供电是用户确定的方案，不代表已测量负载下的端电压；kp/kd、持续/短时力矩和响应数据仍未确认。

建议的首版方案：

后续选型更新见 T007：多项目对照后，默认建议调整为两类硬件都先使用原生位置 PD；
以下保留 T006 当时提出的显式/原生混合方案，供比较，不作为当前首选。

- 无刷用 `IdealPdActuatorCfg`，明确 `velocity_target=0`、`effort_target=0`，对应当前 README 的显式 PD
  力矩公式及限幅。舵机用 `BuiltinPositionActuatorCfg` 作为等效位置伺服模型，不声称等同实机内部 PID。
  这不是由“无刷/舵机”名称强制决定的：无刷也可使用 native position PD，后者与显式 PD 的离散积分不同，
  官方推荐它作为稳定的入门方案；若调整选择，应记录控制周期、积分器和阶跃对比，不反复改动架构。
- 物理参数按型号/电压区分，控制增益按负载区分。建议先分为双侧 hip_yaw、hip_roll、hip_pitch、calf、ankle
  五对，另列 neck_pitch、head_pitch，再分别列 head_yaw、head_roll、mouth，共 10 个互不重叠的参数组、15 个关节。
  左右同类关节初期可共享增益假设，实测不对称时再拆；同型号并不要求所有关节共用 kp/kd。
  mjlab 1.6.0 的这些执行器增益是标量，按组创建多个 cfg，再汇总到 `EntityArticulationInfoCfg.actuators`。
- 每组显式提供 `stiffness`（kp，N·m/rad）、`damping`（kd，N·m·s/rad）与有限的 `effort_limit`（N·m）。
  `IdealPdActuatorCfg` / `BuiltinPositionActuatorCfg` 没有供电电压字段，7.4 V 是选取和标定参数的工况记录，
  不能添加不存在的 `voltage=7.4` 参数。
  无刷优先映射驱动中已有增益，先核实驱动的单位和减速器输入/输出侧定义；舵机 kp/kd 是需拟合的等效值，
  不能直接照搬内置 PID 寄存器数值或官方大机器人示例。已知有效关节惯量时，可用
  `kp = J_eff * omega_n**2`、`kd = 2*zeta*J_eff*omega_n` 作调参起点，再用带载阶跃验证；
  `J_eff` 包含连杆负载，不等于仅有转子反射惯量，公式不代替标定。
- `armature` 是输出侧反射惯量，不是连杆质量；单级近似为 `J_motor * reduction_ratio**2`。
  力矩、速度和惯量都统一到模型关节输出侧，避免将已换算的参数再次乘减速比。
  没有可靠数据时，明确沿用 XML 默认值的仿真假设，不从电机质量或整机质量臆造转子惯量。
- XML 的统一 `damping=0.02` 是被动粘性阻尼；cfg 的 `damping` 是主动 PD kd，二者都会影响响应。
  `viscous_damping=None` 保留 XML，非空值则覆盖。后续训练 spec 应统一管理/记录该阻尼，避免把它当成 kd。
  当前 XML 的 joint `actuatorfrcrange` 仍会限制总执行器力矩；普通 `IdealPd` / `BuiltinPosition` 的 Python
  `effort_limit` 不会自动覆盖它，实际范围受两者共同约束。后续实现应让训练 spec 与 cfg 来自同一组限幅值；
  保留当前原始 XML 供检查。总执行器限幅不包含被动阻尼、摩擦或接触产生的关节力。
- `BuiltinPositionActuatorCfg` 没有 `velocity_limit` 字段；它不会自动复现舵机速度/加速度限制。
  若需模拟舵机目标速度，可在发送位置目标前增加按时间步限制增量的轨迹模块，但这只是目标轨迹限速，
  不保证受外力推动时实际关节速度不超限。需要真实响应时再拟合负载相关的执行器模型。
  待确认扭矩—速度曲线后，可为无刷使用 `DcMotorActuatorCfg`；其中 `saturation_effort` 表示堵转端峰值，
  `velocity_limit` 表示空载速度，`effort_limit` 是每步输出上限，不自带温升/峰值持续时长模型。
  `velocity_limit` 控制力矩—速度饱和曲线，也不是实际关节速度的硬限幅。
  该类也可用于无刷输出侧的简化曲线，不能仅凭名称或将额定速度当空载速度直接选参。
- 延迟用 cfg 自带的 `delay_min_lag` / `delay_max_lag`，单位为物理步，不是策略步；分别记录 CAN 与 TTL
  链路响应，未测时可显式以零延迟作初版假设。控制环、物理 dt 与策略 decimation 分别记录，舵机命令
  更新慢也不意味着仿真跳过其物理步。未知通信延迟不能从串口波特率直接推定。

硬件资料核查：

- [飞特型号资料](https://raw.githubusercontent.com/ftservo/ftservo-wiki/main/docs/products/models/hd-1910-c001/main.md)
  支持位置伺服、TTL 总线与内部 PID；7.4 V 在其所列电压范围内。但摘要和官网详细表的条件/数据不同，
  详细表的力矩及速度只明确标注 4.8 V；不能将其换作 7.4 V 的额定数据，也不线性外推。
  当前没有充分依据确认 XML 的 `1.47 N·m` 是本型号在 7.4 V 的持续力矩；堵转值也不能作为长期出力。
- 无刷 `3.7 N·m` 目前仍只有模型预设，未取得确切型号的一手规格以确认持续力矩、峰值时长和速度等条件。
  不把经销商表格替代为制造商确认结果；后续取得型号说明或实测数据后再填正式参数。

任务侧与后续验收：

1. 实现时检查 10 个参数组恰好覆盖 12+3 个关节且无重复，并导出最终编译的 actuator 与 joint 限幅和阻尼。
2. 平地行走首版建议动作仅覆盖双腿 10 关节，其余 5 个颈/头/嘴关节保留执行器并显式发送默认保持目标，
   这只是建议的任务选择；策略动作数不由执行器数量决定。`init_state.joint_pos` 不会自动为未选动作关节
   设置持续保持目标，reset 后也需要初始化 command target。
3. 首版动作顺序沿当前 MJCF 的右腿到左腿顺序明确声明，并断言实际 `target_names`；
   mjlab 1.6.0 关节 action 查询按自然关节顺序匹配，不能只用 `preserve_order=True` 声称任意顺序成立。
   每关节单独设置动作 scale/目标角范围，尤其 mouth 范围为 `[0, 0.33] rad`、head_roll 仅 `±0.28 rad`，
   不使用全身统一幅度；位置目标限幅与力矩限幅分别处理。
4. 完成 T002 后，单独开展小规模 GPU 执行器验收：先隔离/固定基座测试单关节小幅阶跃，再验证带载响应、
   目标映射、饱和、延迟和 reset；记录力矩/速度/超调/稳态误差及数值有限性，再做全身保持姿态和短跑。
   避免用自由基座未支撑时的倒地现象判断 PD 性能；不以静态编译或 `nu` 数值代替响应证据。

接口依据：[mjlab v1.6.0 执行器文档](https://mujocolab.github.io/mjlab/v1.6.0/source/actuators.html)、
[IdealPd 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/pd_actuator.py)、
[Builtin 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/builtin_actuator.py)、
[参数与延迟定义](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/actuator.py)、
[DcMotor 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/dc_actuator.py)。

### T007 对照公开项目的执行器选型

目标：从真实机器人训练项目的配置和任务引用核对位置 PD 的常见建模方式，并据此评估本项目首版选型。

范围：公开项目源码与本页记录，不实现执行器或调整硬件参数。

验收条件：

- 核对多个独立项目的实际执行器实例化和任务使用，记录可追溯源码链接及 mjlab 版本条件；
  不用 import 数量、同仓库多个机器人或复制 fork 代替独立采用证据。
- 区分普通原生位置 PD、显式理想 PD 和带速度曲线/自定义动力学的执行器；
  其他框架只作为机制对照，不混入 mjlab 类使用频次统计。
- 说明样本局限与本项目建议变化，保留 T006 原始记录并明确后续结论。
- 项目内设置临时目录和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check`；
  全部子代理及检查进程结束后清理本次临时产物和项目字节码缓存。

本次调研日期：2026-10-23。逐项检查执行器实例化、机器人 articulation 和任务引用；
同源机器人配置、同一仓库多个机器人和框架机制对照均不重复统计为独立采用证据。

当前核对到的项目：

| 项目与版本条件 | 实际任务中的执行器路径 | 源码依据 |
|---|---|---|
| mjlab 官方 v1.6.0 | G1、Go1、YAM 按关节组创建 `BuiltinPositionActuatorCfg` | [G1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py)、[速度任务引用](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/tasks/velocity/config/g1/env_cfgs.py)、[YAM 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/i2rt_yam/yam_constants.py) |
| Unitree `unitree_rl_mjlab`，提交 `1425b15f`；setup.py 声明 mjlab==1.2.0 | G1 的手臂、髋、膝、踝等组均为 `BuiltinPositionActuatorCfg`，速度任务实际调用；与 mjlab 官方配置同源 | [配置](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/src/assets/robots/unitree_g1/g1_constants.py)、[任务](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/src/tasks/velocity/config/g1/env_cfgs.py)、[版本](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/setup.py) |
| KaydenKnapik `BoosterT1mjlab`，提交 `f0480bff`；uv.lock 为 mjlab 1.3.0 | T1 六组增益/力矩/惯量/延迟均通过 `BuiltinPositionActuatorCfg` 表达，速度任务引用机器人配置 | [配置](https://github.com/KaydenKnapik/BoosterT1mjlab/blob/f0480bffb456456aa01bda75b4dcd3655659614c/src/booster_t1_mjlab/robots/boostert1/t1_constants.py)、[任务](https://github.com/KaydenKnapik/BoosterT1mjlab/blob/f0480bffb456456aa01bda75b4dcd3655659614c/src/booster_t1_mjlab/tasks/velocity/config/t1/env_cfgs.py) |
| IntelligentRoboticsLab `booster_mjlab`，提交 `d92e1139`；uv.lock 为 mjlab 1.6.0，源码 rev 为 `b517e0c4` | 普通 K1 速度任务使用 `MotorPositionActuatorCfg`，该类仅扩展元数据并继承 `BuiltinPosition` 的 build；不能因另有 torque_speed.py 就认定默认启用自定义限幅 | [继承关系](https://github.com/IntelligentRoboticsLab/booster_mjlab/blob/d92e11395d961096d639446c0a8a176f12bb51da/src/booster_mjlab/robots/booster_k1/actuators.py)、[任务](https://github.com/IntelligentRoboticsLab/booster_mjlab/blob/d92e11395d961096d639446c0a8a176f12bb51da/src/booster_mjlab/tasks/velocity/config/k1/env_cfgs.py) |
| Menlo `asimov-mjlab`，提交 `98870d12`；旧版 mjlab 源码 fork，自报包版本 0.1.0，不能视作当前 1.6.0 | 自有 Asimov 双足配置按髋/膝/踝组使用 `BuiltinPositionActuatorCfg`，速度任务实际引用；仍使用旧 `joint_names_expr` API | [配置](https://github.com/menloresearch/asimov-mjlab/blob/98870d12f079c0b6313bb0fe459aa591a5e7f251/src/mjlab/asset_zoo/robots/asimov/asimov_constants.py)、[任务](https://github.com/menloresearch/asimov-mjlab/blob/98870d12f079c0b6313bb0fe459aa591a5e7f251/src/mjlab/tasks/velocity/config/asimov/env_cfgs.py) |
| ccrpRepo `AMP_mjlab`，提交 `6c7a2947`；setup.py 固定 mjlab==1.2.0 | 使用自定义 `UnitreeActuator`：PD、速度相关限幅和摩擦计算后反解位置输入；虽 cfg 继承 `BuiltinPosition`，其 build 已返回自定义实现，不能记作标准类型 | [执行器](https://github.com/ccrpRepo/AMP_mjlab/blob/6c7a2947fccc973e4af8e6d90e550400f1b6fcfc/src/assets/robots/unitree_g1/unitree_actuators.py)、[AMP 任务](https://github.com/ccrpRepo/AMP_mjlab/blob/6c7a2947fccc973e4af8e6d90e550400f1b6fcfc/src/tasks/amp_loco/config/g1/env_cfgs.py) |

补充核对了以下三个组织的项目：

| 项目与版本条件 | 实际任务中的执行器路径 | 源码依据 |
|---|---|---|
| PAL Robotics `pal_mjlab`，提交 `952abb83`；uv.lock 为 mjlab 1.6.0 | Talos 按手臂、腿、头等关节组创建 `BuiltinPositionActuatorCfg`，Flat/Rough 速度任务实际使用 | [配置](https://github.com/pal-robotics/pal_mjlab/blob/952abb83a590d0e771cfd8e570517ba054182196/src/pal_mjlab/robots/pal_talos/talos_constants.py)、[任务](https://github.com/pal-robotics/pal_mjlab/blob/952abb83a590d0e771cfd8e570517ba054182196/src/pal_mjlab/tasks/velocity/talos/env_cfgs.py) |
| Pollen Robotics `microduck_rl`，develop 提交 `b02fdea4`；依赖 mjlab==1.3.0 | 默认 Walk Flat/Rough 使用自定义 `FrictionDRBamActuatorCfg`，建模固件位置控制、电压与摩擦；不属于直接标准 IdealPd 或 BuiltinPosition | [配置](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)、[任务](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)、[BAM 实现](https://github.com/Rhoban/bam/blob/62bd8ce12154340be97e06f7f41a0ca8f116d967/bam/mjlab.py) |
| Wuji Technology `wuji-mjlab`，提交 `b2b98d70`；pixi.toml 固定 mjlab==1.6.0 | Hand2 Reorient 用 `XmlActuatorCfg` 包装 XML，任务 spec 编辑调用 `set_to_position(kp, kv)`；属于原生位置 PD 路线，但不能算直接实例化 BuiltinPosition | [XML wrapper](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/assets/robots/wuji_hand2/wuji_hand2_cfg.py)、[控制与编辑链](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/tasks/reorient/config/wuji_hand2/hand2_constants.py)、[任务](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/tasks/reorient/config/wuji_hand2/env_cfgs.py) |

Pollen 的经验提示：接近本项目形态的机器人也会在取得硬件辨识数据后使用自定义电气/摩擦模型，
选型不总是标准 IdealPd 与 BuiltinPosition 二选一。其电机与本项目的高擎/飞特混合方案不同，不能复用其参数。

跨框架对照仅用于说明两条路线都存在：

- [legged_gym A1](https://github.com/leggedrobotics/legged_gym/blob/8fa29acc6fd1910c3d9659eef6310bdd301cde0a/legged_gym/envs/base/legged_robot.py)
  每个物理步显式计算 PD 力矩并裁剪，再写入力矩；其路径类似 mjlab 的显式 PD，但不是使用 mjlab 类。
- [IsaacLab v2.3.0 H1](https://github.com/isaac-sim/IsaacLab/blob/v2.3.0/source/isaaclab_assets/isaaclab_assets/robots/unitree.py)
  使用 `ImplicitActuatorCfg`；它是 PhysX 原生驱动机制，不能当成同名 mjlab API 或保证相同离散动力学。
- [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab/blob/4960b84732b0c2ec593dccbfe963fda1bcd7b1e3/source/unitree_rl_lab/unitree_rl_lab/assets/robots/unitree.py)
  同一提交 H1 用显式 `IdealPDActuatorCfg`、G1 用 `ImplicitActuatorCfg`，说明选择还与项目建模目标和已有配置有关。

本项目建议：普通位置目标、零目标速度的首版，两类硬件都优先采用 `BuiltinPositionActuatorCfg`，
仍按 T006 的关节负载分组分别配置增益、力矩、惯量和延迟，配合 `implicitfast`。
这与现有 PD 公式一致，不要求因为无刷而先选显式实现；T006 的混合方案保留为可选对照。
需要显式控制律、可验证的力矩—速度曲线或更复杂已标定动力学时，再按需求使用 `IdealPd`、`DcMotor` 或自定义模型。
单纯加命令延迟也不要求换成显式类型，因为两者均支持 inline delay。

这些源码样本支持原生位置 PD 是 mjlab 常规配置的常见起点，但包含同源复用，不能推广为全生态占比，
也不能据此判断它在本机实机上必然更准确。尚未运行跨执行器动态对照或任何 GPU 训练；
实机型号、7.4 V 工况、未知增益和标定要求均沿用 T006，不照搬他人的数值。

### T008 核实 HD1910 与 Microduck 的 BAM 适配方案

目标：核实 Pollen 官方与 HD1910 社区鸭子的硬件和模型来源，明确用户新增
`actuators/HD_1910_C001/friction_dr_bam.py` 的职责、数据要求及 mjlab 1.6.0 接入方式。

范围：联网核查官方/社区源码、厂家资料，检查新增目录及依赖，形成有来源的实现方案；
不将其他型号参数或未经验证的社区借用参数标为本机标定结果，不推进 M1 验收状态。

验收条件：

- 交叉核对 Pollen 实机硬件/通信与 RL 模型；区分官方原型、社区 HD1910 改版及本项目混合驱动。
- 核对 HD1910-C001 的 7.4 V 规格、公开 BAM 参数来源与版本，明确电气模型、拟合数据、摩擦随机化封装的边界。
- 给出该文件可落实的类/API/参数方案和专项验证步骤，说明当前缺项；只有证据足够时才进一步确定代码改动范围。
- 项目内设置临时目录和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check`；
  全部子代理与检查进程结束后清理本次临时产物和项目字节码缓存。

调研结论（2026-10-23）：

**硬件与参数来源。** Pollen 官方 Microduck 的[实机总线](https://github.com/pollen-robotics/microduck/blob/main/duck-control/src/bus.rs#L1-L30)
使用 `Xl330Controller`；[RL 配置，固定提交 b02fdea](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)
使用 XL330 / M6。HD1910 是另有公开实现的社区改版，不能将其参数称为 Pollen 原型的标定值。
本机为 12 个无刷加 3 个 HD1910，更不能整体复制纯舵机鸭子的配置。

| 来源 | 核对到的实现/工况 | 本项目如何使用 |
|---|---|---|
| Pollen Microduck | XL330，BAM 加摩擦随机化扩展 | 参考配置分层、事件和状态生命周期；不用其电机参数 |
| [飞特 ftservo-bam，固定提交 4f7c0b0](https://github.com/ftservo/ftservo-bam/tree/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/params/feetech_hd1910_7_4V) | HD1910，7.4 V，提供 M1–M6 JSON 和专用控制器 | 首选的公开模型候选；不是本机实测标定 |
| [JoyandAI 的 HD1910 摆锤报告](https://github.com/JoyandAI/microduck_rl/blob/22916b9d82f250caa563ed9a56976eb33243fb91/docs/feetech_hd1910_pendulum_results.md)及[训练配置](https://github.com/JoyandAI/microduck_rl/blob/22916b9d82f250caa563ed9a56976eb33243fb91/src/mjlab_microduck/robot/microduck_constants.py#L150-L198) | 实测约 5.1 V，报告默认 M1、备选 M4；同提交训练配置另用 M5 | 参考采集和独立验证方法，注意报告与运行配置的差异，不当作 7.4 V 参数 |
| [Luwu xgoduck 的 1910_m6.json](https://github.com/LuwuDynamics/xgoduck_rl/blob/326d77a1122870bdefa2c36403937502c958e69c/src/mjlab_microduck/robot/xgoduck/params/1910_m6.json) | JSON 选择 `sts3215` 控制器，原始采集条件本轮未核实 | 不直接采用；该字段只证明所选控制律，不能据此断定被测硬件型号 |

**新增的确切型号规格。** [社区托管的飞特 HD1910-C001 原始规格书](https://raw.githubusercontent.com/JoyandAI/OpenMicroDuck/b8c7d6945e5ceda9ceb9706b53c372adb9ae4128/hardware_spec/servo/HD-1910-C001%E4%B8%B2%E5%9E%8B%E8%A7%84%E6%A0%BC%E4%B9%A6-20260907.pdf)
为 A/0、2026-09-07，带制造商抬头及完整型号；托管方是社区，非厂家官网。
7.4 V 条件下给出堵转力矩 `15 kgf·cm ≈ 1.471 N·m`、额定负载 `3.7 kgf·cm ≈ 0.363 N·m`，
空载速度 `0.088 s/60°`（同时列 `113 rpm`，约 `11.9 rad/s`）；堵转力矩和空载速度均有 ±10% 公差。
XML 的 `±1.47` 因而有对应的规格书堵转依据，但仍不代表持续力矩或本机已测限值；
额定负载也不自动构成瞬时硬限幅，峰值持续时间、温升和保护仍需单独处理。
这份版本的规格书说明模式 4 为出厂默认纯位置 PD / Sim2Real 模式；实机仍应读回模式和增益确认。
这些新增来源更新 T006 当时“未找到明确 7.4 V 数据”的结论，历史记录保留。

**厂家模型的适用边界。** [HD1910 控制器源码](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/feetech/actuator.py)
采用位置误差到 PWM/电压的 P 控制，再由电气模型计算含反电动势的电机力矩；默认 `vin=7.4`、`kp=32`。
`kp_fw=32` 是该控制模型的固件增益，不是 `32 N·m/rad`，也不是已经读回的本机设置；
该类没有独立 D 项，不能声称完整复现上述模式 4 的 PD 固件。
M6 中的 `kt≈0.5645`、`R≈2.9665`、`armature≈0.001827` 是拟合模型参数；
`q_offset` 属于台架零位，`command_delay≈0.000978 s` 属于该辨识链路，不直接当作机器人关节零位或整机总线延迟。
普通 `BamActuator.compute()` 不会自动施加 JSON 的 `command_delay`；
另行启用时须与 mjlab 以物理步计的 inline delay 分清，避免重复施加。

**三个已定位的接入问题。**

1. 厂家 [JSON](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/params/feetech_hd1910_7_4V/m6.json)
   写 `actuator="hd1910"`，[注册表](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/actuators.py)
   只有 `HD1910`；[加载器](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/model.py)
   直接用字符串索引。静态核对确认不一致，按这条路径直接加载会查不到键；本轮未执行完整上游包。
   适配层应明确处理别名，保留原始厂家 JSON 和提交/哈希记录，不能只改文件名冒充适配完成。
2. 飞特 [BAM 适配器](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/mjlab.py)
   已有 `friction_scale_range` 和一次摩擦预算缩放。
   Pollen [同名薄封装](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/actuator/friction_dr_bam.py)
   是针对其基类写的；原样套到飞特分支会覆盖 startup 抽样，并可能将同一系数乘两次，得到 `scale²`。
   项目应选择唯一的缩放位置，仅按需补 setter/reset 或每回合重采样。
3. 飞特与 Rhoban 所核对版本的 [mjlab extra 依赖](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/pyproject.toml)
   仍为 `mjlab>=1.3,<1.4`、MuJoCo/Warp 3.7 系列和 `warp-lang>=1.12,<1.13`，
   与本项目 1.6.0 / 3.11 系列冲突。不能直接安装该 extra、降级项目或靠 lazy import 宣称兼容。
   候选路线是固定 BAM core 来源，在本项目适配 mjlab 1.6 生命周期，再经 CPU/GPU 实测确认。

**目标文件应承担的职责。** 当前 `friction_dr_bam.py` 为用户新增空文件，仓库未声明 BAM 依赖。
建议将模型本体与 DR 薄封装分开：

| 位置 | 计划职责 |
|---|---|
| `actuators/HD_1910_C001/bam_actuator.py` | `HD1910BamActuatorCfg` / `HD1910BamActuator`：经过验证的模型加载、别名处理和 mjlab 1.6 适配 |
| `actuators/HD_1910_C001/friction_dr_bam.py` | 在基类确有不足时定义 DR Cfg/Actuator；`build()` 返回运行实例，提供摩擦系数 setter/reset，明确重采样时机，保证只缩放一次 |
| 型号目录内的参数与来源记录 | 原始厂家 JSON、固定提交与哈希、模型版本/电压/固件假设；本机标定结果另存，不能覆盖来源 |
| 机器人配置与任务事件 | 精确绑定 `head_yaw_joint`、`head_roll_joint`、`mouth_joint`，注册字段展开和随机化；无刷仍用自己的 PD 配置 |

若兼容后的基类已有所需 DR 功能，此文件可只导出配置入口，不为了沿用 Pollen 文件名再加一层缩放。
底层适配需实现/核验 `ActuatorCfg.build()`、`Actuator.edit_spec/initialize/compute/reset`：
加载后不重复执行会重建参数的 BAM 内部模型初始化；只重置指定环境的历史力矩和延迟状态。
BAM 计算电机力矩并将干摩擦预算、粘性阻尼写入 MuJoCo `dof_frictionloss` / `dof_damping`，
由求解器处理摩擦，不在普通 PD 后随意减一项摩擦力矩。
初始化必须通过 `requires_model_fields` / startup 事件展开这些字段，验证每个环境有独立存储。
训练 spec 还应统一 XML 的 `damping=0.02`、关节力矩范围与 BAM 的参数归属，避免重复阻尼或隐藏限幅。

验证顺序：先固定 7.4 V、关闭 DR/延迟，以厂家参数作有来源的候选，核对 JSON 加载、
控制器公式、参数范围与张量形状、子环境 reset；然后在小规模 GPU 多环境上检验阶跃/保持、
近零速摩擦、力矩范围、字段互不影响及有限值，再增加一次摩擦缩放和明确的延迟。
模型准确度最终用本机 7.4 V、实际固件模式/增益和带载电压的独立实机日志验证；
M6 不因参数更多就自动优于 M1/M4，需要比较留出轨迹。
本轮交付为调研与适配设计，保留空文件及现有依赖，不将未执行的动态验证写为通过。

### T009 实现并验证 HD1910 的 mjlab 1.6 适配器

目标：在 mjlab 1.6.0 上以可追溯的 HD1910 模型驱动三个舵机关节，并提供可复现的短响应证据。

范围：落实 T008 的模型加载/别名修正、兼容适配和必要的 DR 薄封装；采用外部依赖时固定来源，
按安装工具更新并验证 `pyproject.toml` 和 `uv.lock`。实现前记录实机模式和增益；
未读回的值只可作为明确的仿真假设，不能标为实机配置。

用户于本轮明确要求实施，范围调整为自包含的 HD1910 M6 模型、mjlab 1.6 执行器及可重复的
CPU/GPU 测试台，不安装旧版 BAM extra，不以未完成的 T001/T002 阻塞独立组件实现。
电压 7.4 V 是用户方案；`kp_fw=32` 和厂家控制器为初版仿真假设，实机模式/增益尚未读回。
本次不更改原始 MJCF 或添加未经验证的全机器人控制参数。

验收条件：`make check` 通过；CPU 参考计算/参数加载与局部 reset 检查通过；
小规模 GPU 多环境阶跃与保持、字段独立性、限幅和 reset 检查通过；
关闭 DR 的确定性基线先通过，再验证摩擦仅缩放一次；实机准确度与仿真功能验收分别记录。

实现结果：

- `actuators/HD_1910_C001/model.py` 提供冻结、校验后的 M6 参数和独立 Torch 公式。
  接受明确的 `hd1910` / `HD1910` 别名；仅支持 HD1910 M6，其他模型不静默回退。
  参数 JSON 按原始字节随包保存，附固定来源、SHA256、NOTICE 和 Apache-2.0 许可证。
  不引入 BAM 依赖或旧 mjlab extra，依赖声明与锁文件保持不变。
- `bam_actuator.py` 实现 mjlab 1.6 的配置工厂、spec 修改、初始化、compute、post-step update 和 reset，
  通过原生 `dof_frictionloss` / `dof_damping` 处理摩擦，提供 `bam_init` 字段展开事件。
  仅支持 hinge 关节，拒绝重复执行器，统一主动执行器与关节总力矩限幅，覆盖 XML 中被动参数。
  外载荷从上一解平滑力中移除主动/被动力，再合入排除自身干摩擦的约束力，纳入直接外力和映射后的身体外力。
  reset 后旧求解载荷保持无效，直到 `update()` 确认新物理步完成；单纯重复写控制不会令旧载荷重新有效。
- `friction_dr_bam.py` 实现 `FrictionDRBamActuatorCfg` / `FrictionDRBamActuator`。
  默认关闭 DR；配置范围后启动与每回合仅对选定环境重采样，同组关节共享系数，干摩擦只缩放一次。
  `set_friction_scale()` 支持标量或每环境系数；`reset_friction_scale()` 恢复 1，
  `reset()` 则按配置重采样并清理相应历史；粘性阻尼不参与该缩放。
- M6 二次摩擦项按上游 `bam/model.py` 的辨识公式实现，补上厂家 GPU 适配器遗漏的符号/等幅条件，
  不是未经说明地复制存在差异的 GPU 公式。厂家 JSON 的零位和台架延迟保留为元数据，未自动施加；
  mjlab Entity 自带的物理步延迟仅使用一次。
- README 提供用 `SERVO_JOINT_NAMES` 配置三个舵机及 startup 事件的示例。
  `tests/test_hd1910_actuator.py` 为 CPU 专项测试，`tools/check_hd1910.py` 为可重复的三关节多环境测试台。

边界：7.4 V 为用户方案；`kp_fw=32`、P 电压控制加反电动势及默认约 `1.471 N·m` 峰值限幅是有来源的
仿真假设，尚未读回实机固件设置；不包含独立固件 D 项或持续力矩/温升模型。
模型在实机 7.4 V 的阶跃与负载数据上是否准确仍待标定。
原始全机器人 MJCF 仍 `nu=0`，未把独立组件验收写成全机器人集成、站立或训练验收。

### T010 补充 HD1910 执行器目录说明

目标：在 `src/ht_microduck/actuators/HD_1910_C001/README.md` 提供就近可读的模块说明与使用指南。

范围：说明目录结构、控制与摩擦模型、配置字段、实体/事件接入、DR 与 reset、验证命令和参数来源；
仅新增目录文档并更新本任务记录，不改变执行器行为或依赖。

验收：独立只读核对文档与实现；检查本地链接、Python 示例和命令入口；
在项目内设置临时目录及 pytest `--basetemp` 后执行 `make check`，不新增文档专用测试；
检查进程及子代理结束后清理临时产物和项目字节码缓存。

### T011 编写机器人常量模块的混合驱动器配置

目标：在 `ht_microduck_constants.py` 返回可交给 mjlab articulation 的两组独立配置，
12 个无刷关节使用原生位置 PD，3 个 HD1910 使用现有 7.4 V BAM 模型。

范围：驱动器配置工厂、必要的使用说明、CPU 专项测试和小规模 GPU 检查入口；
不修改原始 MJCF、既有关节分组、依赖或完整机器人实体/场景。
无刷增益和力矩上限由调用方显式提供，区分模型假设、公开厂家拟合与本机标定。

验收：独立子代理只读核对 mjlab 1.6.0 接口及 XML 限幅/阻尼交互；
CPU 检查分组覆盖、配置独立性、参数校验、模型编译和 PD 力矩；
GPU 独立测试台验证 15 个关节的目标映射、两组限幅、阶跃/保持响应及有限值。
设置项目内临时目录和 pytest `--basetemp` 后执行 `make check`；
全部子代理与检查进程结束后清理本次临时产物和项目字节码缓存。

### T012 复核用户新增的随机驱动器延迟

目标：核对两组 `delay_min_lag=0`、`delay_max_lag=3`、`delay_hold_prob=0.4`、
`delay_update_period=10` 在 mjlab 1.6.0 中的实际行为，区分配置合法性与硬件建模依据。

范围：只读检查用户源码改动、已安装 mjlab 延迟实现、相关文档和测试；仅更新本任务记录，
不修改用户参数、源码、测试或 README。并行独立复核延迟语义及既有验收假设。

验收：记录随机延迟的单位、重采样/保持、分组共享和 reset 语义；
设置项目内临时目录后执行 `make check` 和已有 15 关节 GPU 专项，说明实际通过项或失败原因，
列出与新默认值不一致的说明和测试；全部子代理与检查进程结束后清理临时产物和字节码缓存。

### T013 同步随机延迟的测试、说明与运行期回归

目标：让当前 `(min=0, max=3, hold_prob=0.4, period=10)` 默认值与说明及验收一致。

范围：更新 `tests/test_robot_actuators.py` 的零延迟断言、constants docstring 和 README 的默认值描述；
在混合 GPU 检查中固化变化目标序列，覆盖无刷和 BAM 的历史目标映射及周期采样。

验收：`make check` 通过；固定种子下对两组配置检查 lag 范围、非零延迟、每环境更新周期，
逐步核对无刷 `ctrl=history[t-lag]` 和 BAM 对延迟位置目标计算的力矩；
保留 reset/限幅/静态响应检查，明确所有延迟参数仍为待标定的仿真假设。

完成情况：本任务的源码说明、README、CPU 断言和 64 步 GPU 变化目标回归已由 T016 一并落实；
统一检查及两组随机延迟映射通过，结果与命令见 T016 完成记录。

### T014 对照官方复核 robots 模块剩余缺项

目标：依据已实现的混合驱动器配置，对照 mjlab 1.6.0 官方机器人与实体接口，给出剩余代码清单和实现顺序。

范围：并行只读核对 `robots/`、官方 G1/Go1 配置、EntityCfg 和现有验证；仅修改本页记录，
不修改机器人行为、用户延迟参数、测试或 README，不跳过 T001/T002 的阶段依赖。

验收：结论附当前代码与固定版本官方源码依据，区分必需配置、按需扩展和任务层职责；
执行 `make check` 并如实记录现存失败，单独补跑未执行的模型检查；
使用项目内临时/缓存目录、pytest basetemp 和无字节码模式，全部子代理及检查结束后清理。

对照结论（2026-10-23）：

本次“官方”按项目固定版本的 mjlab v1.6.0 理解，对照
[G1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py)、
[Go1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py)
和 [Entity 文档](https://mujocolab.github.io/mjlab/v1.6.0/source/entity/index.html)。
当前 `get_spec()` 的直接 XML 加载、12+3 关节分组、返回独立执行器配置均已具备；
T004 原结论中“混合执行器待实现”的部分已由 T009/T011 完成，剩余主要是整机装配与接触配置。

| 内容 | 当前情况 | 还需编写或明确的内容 |
|---|---|---|
| 机器人配置工厂 | 无 `EntityCfg` 公共入口；只有测试临时组装 | 在 constants 模块增加 `get_ht_microduck_robot_cfg()`，每次组装新的 `EntityCfg`、初态与 articulation；沿用调用方显式传入无刷参数的约定 |
| 初始状态 | XML 基座高 `0.167 m`，没有 Python 初态或 XML keyframe | 显式 `EntityCfg.InitialStateCfg`：根位置/四元数、根速度、15 关节默认角度和速度；初态要经过足底接触与关节范围检查，不能声称全零即可站稳 |
| articulation | 已有 `get_actuator_cfgs()`，尚未在机器人公共配置中接入 | 工厂内调用 `EntityArticulationInfoCfg(actuators=...)`，验证 15 个执行器和既有顺序；软限位系数可以显式配置，非必填 |
| 模型与场景归属 | 原始 MJCF 同时含机器人、地面和灯光 | 保留独立检查入口，为实体增加只返回机器人内容的 spec 加载入口，或拆出预览场景 XML；地形和环境照明交给场景管理（T039 已移除本体中的地面与灯光） |
| 碰撞与摩擦 | 机器人 10 个碰撞 geom 均无名，脚部采用 MuJoCo 默认摩擦 | 为脚部及其他关键碰撞体命名，明确完整碰撞/自碰撞策略和摩擦假设；再使用 `CollisionCfg` 等配置。现有 XML 碰撞可用于最小加载，但尚未验证整机接触响应 |
| 足端参考点 | 当时 `nsite=0`，`nsensor=0` | 已在 T037 补齐：足底 `r_foot`/`l_foot` site、`imu` site 与 5 个内置传感器；接触/足高传感器仍按任务在场景配置 |
| 包导出与预览 | robots 顶层空，型号 `__init__.py` 只有说明；工具仍检查被动源模型 | 公共工厂落实后按需导出；另提供装配后 `nu=15` 的场景创建/reset 检查，保留原始 `nu=0` 检查用途 |

灯光统一管理是本项目的场景约定，并非 mjlab 硬性限制；官方机器人 XML 也可以携带灯光。
`CollisionCfg` 默认关闭未匹配 geom 的碰撞，因此命名和策略要一起落地，
不能把官方脚部正则直接套到当前无名 geom，或将多套互相覆盖的碰撞策略一起注册。

两项已有风险通过 CPU 静态组合实际复现：

- 原始模型的 `qpos0` 根高度为 `0.167`，直接用默认 `EntityCfg(spec_fn=get_spec, ...)`
  生成的 `init_state` keyframe 根高度为 `0.0`；后续 reset 使用该初态会放错高度。
  依据为 [EntityCfg 默认值及 keyframe 实现](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/entity/entity.py)。
- 将原始 spec 放入含平地 terrain 的 `Scene`，编译得到两个 plane：`robot/floor` 和 `terrain`，
  共两个灯光。原始 XML 中的地面随机器人组合进入场景，不能直接复用为训练机器人资源。
  （T039 已解决：地面、灯光与天空盒从本体移除，改由 mjlab `Scene` 提供。）

不能照搬的官方参数和模块边界：

- 官方 G1/Go1 用 `soft_joint_pos_limit_factor=0.9`，接口默认为 `1.0`；这是软限位信息，
  不会更改 MJCF 硬限位，也不自动裁剪动作。`mouth_joint` 的硬范围为 `[0, 0.33]`，
  若全局取 `0.9`，软范围成为 `[0.0165, 0.3135]`，全关节软限位奖励可能惩罚正常闭嘴姿态；
  应在任务中明确奖惩关节子集与目标范围，而非机械复制数值。
- 官方 `ACTION_SCALE = 0.25 * effort_limit / stiffness` 适用于其原生位置 PD 配置；
  HD1910 的 `kp_fw` 是固件模型增益，不能代入 SI 刚度公式。动作子集、最终顺序、
  每关节角度缩放、偏置/裁剪、物理步长与控制降采样由任务配置落实，robots 可提供有依据的参考值。
  本版本 JOINT action 走自然关节顺序，不能仅靠声明 tuple 或 `preserve_order=True` 推定任意自定义顺序；
  接入时应验证实际解析目标和策略通道映射，依据为
  [action 实现](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/envs/mdp/actions/actions.py)
  与 `Entity.find_joints_by_actuator_names()`。
- BAM 的 `bam_init` startup 事件或独立 Simulation 的字段展开仍需由环境/检查入口配置；
  返回 `EntityCfg` 不等于已经执行初始化。观测、奖励、终止、事件和控制周期放任务层，
  PPO、Storage、Runner 放本项目对应模块，不塞进 robots，也不改用官方 RSL-RL 训练链路。
- 当前无刷统一标量增益可作首版显式仿真假设；后续按腿部、颈部、头部负载分组扩展。
  反射惯量、速度/持续力矩和延迟分布需硬件依据或标定，不从 G1/Go1 复制未知数值。

当前已知说明/测试不一致仍由 T013 处理：`constants.py:74` 和 README 声称默认零延迟，
`tests/test_robot_actuators.py:66` 断言两组 `min=max=0`，实际两组均为 `(0, 3, 0.4, 10)`。
现有 GPU 工具主要使用 reset 后首个目标和恒定阶跃；首写会回填延迟历史，因此映射探针能通过，
但不能据此验收稳定历史下的随机延迟，需要固化 T012 已验证的变化目标检查。
另将 `tools/check_robot.py:49` 的“下一步添加两组 PD 执行器”提示记为 T002 接入时同步项：
应说明源 MJCF 保持被动，混合执行器已由配置提供，避免误称三只 BAM 舵机为普通 PD。

建议执行顺序：先 T013 同步已有验证与说明，再 T001 整理基线，按 T002 落实初态、
机器人 spec 与实体工厂及小规模 GPU 场景 reset；在后续 M1 任务接入现有混合驱动器，
验证整机接触、保持响应和限幅，再建立动作/观测/奖励等任务配置。
本次仅完成缺项评审，不将 CPU 组合编译、独立执行器测试台或官方配置对照视为整机 M1 验收。

### T015 对照 MicroDuck 官方评审 robots 模块

目标：以 `pollen-robotics/microduck_rl` 的固定提交对照本地 `robots/`，明确已实现、必需补充及按需扩展的内容。

范围：并发只读核对本地机器人、官方机器人配置与其任务层引用；仅更新本页，保留源码、测试、README、
用户延迟参数和依赖。不将官方舵机参数、默认姿态、动作顺序或训练链路直接移植到本机混合驱动机器人。

验收：报告附官方固定提交链接和本地代码位置，区分机器人配置与任务层职责；
在项目内临时目录和无字节码模式下执行 `make check`，如实记录现存失败，单独补跑被跳过的模型检查；
所有子代理及检查进程结束后清理本次临时产物与项目字节码缓存。

对照结论（2026-10-23）：

本次按用户指定，以 Pollen 官方 `microduck_rl` 默认 `develop` 分支固定提交
`b02fdea4902c2b93b7d34a83a6f05da4ececb7d3` 为参照，区别于 T014 的 mjlab 官方示例对照。
主要来源为[机器人配置](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py#L116-L210)、
[行走模型](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/robot_walk.xml)、
[独立预览场景](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/scene_walk.xml)
和[速度任务](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)。
行号采用原始文件物理行，网页正文抽取后的行号可能不同。

当前 `robots/` 已具备模型加载、关节/电机映射及混合执行器工厂；核心缺项是可直接用于场景的整机配置。
不需要重新编写已经完成的 HD1910 模型，也不要求把执行器手写进原 XML。

| 优先级与内容 | MicroDuck 官方实现 | 本地还需要写什么 |
|---|---|---|
| 必需：整机实体入口 | constants:202 的 `MICRODUCK_WALK_ROBOT_CFG` 组装 spec、初态、碰撞和 articulation | 在现有 constants 中增加 `get_ht_microduck_robot_cfg()`，调用已有 `get_actuator_cfgs()`；每次返回新配置，继续要求调用方显式提供无刷增益和限幅。当前测试里的临时 `EntityCfg` 不代替公共入口 |
| 必需：显式初态 | constants:116 的 `HOME_FRAME` 声明关节默认姿态；任务:388 另设 reset 根高度 | 定义本机根位置/四元数、关节角及速度。CPU 实测源模型根高 `0.167 m`，默认 Entity 的 `init_state` 根高却为 `0.0 m`；需验证足底位置、关节范围及接触，不复制官方角度或高度 |
| 必需：机器人与场景分离 | `robot_walk.xml` 不带地面，`scene_walk.xml:20` 起另配地面、灯光 | 保留 `get_spec()` 的原模型预览用途，新增去除预览地面的机器人 spec 入口。当前 XML:129 带 `floor`，直接组合 terrain 会重复；灯光按本项目场景约定统一管理 |
| 整机接触前明确：碰撞规则 | constants:142 的 `FULL_COLLISION` 依赖命名的脚部碰撞体，配置摩擦和接触维度 | 本机 10 个机器人碰撞 geom 均无名，双足位于 XML:52、80，采用默认摩擦。先为关键 geom 命名，定义摩擦、自碰撞和接触策略，再配置 `CollisionCfg`；不能直接套官方正则，否则未匹配 geom 默认会被禁用 |
| 行走任务按需：足底参考点与传感器 | XML 有 `left_foot/right_foot`、`imu` site 和 IMU sensor；任务:217 起配置接触和足高传感器 | 本机已按 T037 补足底 site、`imu` site 与 5 个内置传感器，命名对齐官方；接触与足高传感器仍在任务场景配置 |
| 验收：完整机器人场景 | constants:320 起提供场景预览入口，任务层实际使用整机配置 | 为本机新增真实机器人小规模创建/reset/短步进检查，验证根状态、关节状态、15 个执行器和接触。当前 `check_robot.py` 只静态编译；混合执行器工具使用独立铰链台架，不能证明整机已能站立 |

适配边界和按需扩展：

- 官方所选 walk 模型有 14 个主动关节、XL330 BAM；本机有 15 个主动关节，采用 12 无刷加 3 HD1910。
  官方主动关节数、关节名称/正负方向、姿态和电机参数不能直接采用。
  官方[依赖声明](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/pyproject.toml#L15-L19)
  固定 `mjlab==1.3.0`、`warp-lang==1.12.0`；本机继续使用 mjlab 1.6.0，按其实际接口适配，不降级依赖。
- 官方动作 `scale` 在速度任务:273 配置，不在 robots 常量中定义通用公式。动作子集、实际通道顺序、
  偏置/裁剪、物理步长和降采样仍放本项目任务层；`kp_fw` 不能当作 SI 刚度代入 PD 缩放公式。
  未纳入策略动作的头/嘴关节如需保持，仍应初始化并持续提供目标，初态不等于保持控制。
- 官方任务:364 配置 BAM 字段展开 startup 事件；本机已有 `bam_init`，完整环境仍需注册，
  单独返回实体配置不代替运行期初始化。观测、奖励、终止、随机化和训练模块继续按本项目分层实现。
- 官方另有 groundcontact、allcollisions、backlash、rollers 等模型变体；首个平地任务不需要全部补齐。
  后续只有确需倒地接触、已测间隙或轮式任务时再增加。无刷分负载增益、反射惯量、速度曲线和延迟分布
  依据本机参数或标定扩展，不为对齐官方文件数量而填写未知值。

现存同步问题仍由 T013 处理：constants:74 和 README 的默认零延迟说明、tests/test_robot_actuators.py:66
的零延迟断言，与实际 `(0, 3, 0.4, 10)` 不一致；本轮不更改用户参数。
建议先完成 T013，再按 T001/T002 补整机工厂、显式初态和机器人专用 spec，随后验证接触与任务所需足底参考点。

### T016 实现整机机器人配置与最小场景验证

目标：提供可复用的整机 `EntityCfg` 工厂，在 mjlab 1.6.0 小规模 GPU 场景中创建、重置并短步进。

范围：机器人专用 spec、显式模型初态、关键碰撞命名及完整碰撞规则、按几何确定的足底 site、
公共导出、真实机器人场景检查；同步 T013 的延迟断言/说明和变化目标回归。保留原始 XML/mesh、
现有 12+3 分组及用户选定的延迟参数。无刷参数继续显式传入，新增数值均标明仿真假设及几何依据。
不安装依赖，不改用外部训练链路，不提交 Git，不将未知实机姿态或 IMU 安装参数写成确认值。

验收：`make check` 通过；CPU 验证源模型独立、实体初态/关节限位/碰撞/site 和单一地面；
GPU 小规模真实场景验证状态、目标映射、局部 reset、接触及短步进有限值；混合铰链 GPU 检查保留
限幅/响应并覆盖变化目标下的两组随机延迟。全部验证使用项目内临时目录和无字节码模式，
所有代理与检查进程结束后清理本次临时产物及项目字节码缓存。

实现结果：

- `get_robot_spec()` 在新 spec 上移除地面/灯光、命名全部 10 个现有碰撞体并添加 `r_foot/l_foot`
  足底 site；原 XML/mesh 和 `get_spec()` 保留。足底坐标依据本机编译网格的最低水平面中心确定，
  不是实机压力中心或传感器安装位置。
- `get_ht_microduck_robot_cfg()` 组装每次独立的 `EntityCfg`、初态、articulation 和单套完整碰撞规则，
  两层包导出公共工厂。保留无刷显式参数和原有 12+3 顺序、用户延迟配置；支持深拷贝的 `init_state`
  及 `(0, 1]` 的软限位系数，默认 `1.0` 兼容闭嘴边界。
- `NEUTRAL_FRAME` 显式根高 `0.167 m`、单位四元数、15 关节零位和零速度。
  CPU 独立几何查询证明双足离地约 `3.759 mm`、初态无接触、投影 COM 位于足底支承条带；
  这些是模型几何条件，不是稳定站立证据。碰撞参数显式沿用源默认值，视觉 geom 保持不碰撞。
- `tests/test_robot_entity.py` 新增实体/场景、初态深拷贝、限位、源模型保留、碰撞资格、足底真实网格
  和接地查询测试。`tools/check_robot_scene.py` 使用真实自由基座机器人、平地和双足接触传感器，
  首次控制前展开 BAM 字段，显式恢复物理状态和全部目标；验证非零颈部初态及局部 reset 隔离。
- T013 的旧断言和说明已同步；混合铰链工具新增 64 步变化目标，验证两组真实延迟历史、当前反馈、
  每环境更新相位和非零延迟的可见效果。README 添加实际用法，源模型工具提示改为无刷 PD / 舵机 BAM。

边界：本轮未填未知实机 IMU 位姿、按负载标定的无刷增益、速度/持续力矩曲线或电气延迟分布。
动作/观测/奖励/控制降采样与训练组件仍留在任务层。下一项为 T001 整理基线；其后复核 T002，
再以本机参数单独验证全身保持与更长的短站立，而非直接进行长时间训练。

### T017 修复 constants 直接运行的整机预览入口

目标：用户原命令可以打开带地面的静态整机场景，无刷参数来源和预览职责明确。

范围：修正新增 main 块的漏参，预览入口以明确的仿真检查参数调用工厂，保留工厂必填参数；
组装单一平地及初始化状态，以 passive viewer 显示，不绕过 Python BAM 使用原生自动步进。
按用户指定的 `ri_4438_constants.py` 简化，仅留简短 main 块，去除 CLI、打印、相机定制和重复说明。
不修改用户延迟、机器人参数、源 XML 或依赖。

验收：`make check` 通过；用户同一路径的 main 块编译得到 `nu=15`、单一地面，
有图形显示时实际启动并关闭预览验证 GUI 可用；如图形环境受限则如实记录。
所有临时内容和 TMPDIR 均在项目 `.artifacts/` 内，代理与检查进程结束后清理缓存及本次临时产物。

### T018 按官方风格集中定义机器人配置

范围：模块级两组执行器、初态、碰撞和整机配置；简化预览使用方式、同步公共导出/调用说明，
保留工厂返回独立副本和参数覆盖，保留用户延迟与模型。默认无刷 `10/0.4/2` 仍为仿真假设。
验收：`make check`；默认配置/副本隔离检查；4 环境 GPU 场景短跑；原路径 GUI 打开和关闭。
本轮不修改依赖或提交 Git，全部验证临时内容置于项目 `.artifacts/`，结束后清理。

### T019 整理机器人常量模块的代码风格

范围：参照用户指定文件，按 MJCF、关节映射、执行器、初态、碰撞、最终配置和预览分区，统一排版与简洁注释。
仅修改常量模块和任务记录；不新增功能、参数或测试。验收为 Ruff 格式/检查、AST 语义与定义依赖复核、
`make check`；纯代码整理不重复 GPU/GUI 运行，沿用 T018 运行证据。验证临时内容均在项目内并于结束时清理。

### T020 对照 Microduck 官方简化机器人参数配置

目标：参数在模块级执行器/初态/碰撞配置中直接可见，使用整机配置无需逐层传入同一批关键字参数。

范围：并发只读核对 Pollen Microduck 官方参数及 ri_4438 参考风格，简化常量模块、迁移内部调用与测试，
同步 README 和来源记录；保留 12+3 分组、用户延迟、原始模型及 mjlab 1.6.0，不引入未知硬件参数。

验收：记录官方配置的准确来源及与本机硬件的差异；`make check`、Ruff 格式检查、
配置副本隔离/模型编译/PD 行为检查通过；在 GPU 上运行混合执行器和真实机器人小规模短检查。
本次不安装依赖、不提交 Git；临时目录和缓存仅在项目 `.artifacts/`，所有代理及进程结束后统一清理。

官方参数核对：以 [Pollen 官方固定提交 b02fdea 的常量模块](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)
为依据，直接定义初态、碰撞、BAM 执行器和 `EntityCfg`；没有本项目原先的两层参数覆盖工厂。
用户给出的 `legged_wbc_mjlab/src/assets/robots/ri_4438/ri_4438_constants.py`
也采用模块级配置和无参整机入口，其增益来自独立 `Ri4438Cfg.control`。
本项目当前直接保留 mjlab 配置对象，不再另建一套参数类。

| 项目 | 官方 Microduck 的配置 | 本机继续采用的配置与依据 |
|---|---|---|
| 执行器 | XL330 M6，`kp_fw=200` | 12 个 HTDW 原生 PD 加 3 个 HD1910 M6；无刷 `10/0.4/2` 为检查假设，舵机 `kp_fw=32` 来自飞特控制模型假设 |
| 供电 | `vin_range=(6.5, 8.2)`、压降系数范围 `(0, 0.2)`、最低 `6 V` | 舵机 `7.4 V` 为用户方案，未新增无刷供电模型或电压随机化 |
| 延迟 | `3–6` 个物理步 | 用户选定的 `0–3`、保持概率 `0.4`、更新周期 `10` 保留，待实机标定 |
| 初态/接触 | 官方关节角、脚部 `condim=3`、其他碰撞体 `condim=1`、软限位 `0.9` | 保留本机模型零位、高度、碰撞配置和软限位 `1.0`，不照搬不同结构的姿态和参数 |

兼容性变化：删除 `get_actuator_cfgs()`、`get_ht_microduck_robot_cfg()` 的关键字覆盖参数、
场景检查的 `--brushless-*` 选项和 `NEUTRAL_FRAME` 别名。整机入口只深拷贝，初态统一叫 `HOME_FRAME`；
任务在独立副本上直接改字段，台架用 `dataclasses.replace()` 设置测试专用值。
旧标量入口的数值域校验随接口移除，不再承诺覆盖参数会自动校验；直接配置需保持有限合法增益和限幅、
软限位系数 `(0, 1]` 及无刷执行器限幅不超过原模型 `3.7 N·m` 的约束。
XML 的总力矩限幅保留，CPU 检查验证默认值与编译后的双向限幅及零主动阻尼边界。

### T021 对照 Microduck 梳理训练与实机部署缺项

目标：对照用户指定的 `pollen-robotics/microduck` 及其关联的 `microduck_rl`，
区分已有能力、训练链路缺项、sim2real 标定和实机运行缺项，给出按依赖排列的可执行后续任务。

范围：并行只读核对上游实机运行和训练代码，主代理核对本地代码并更新本页；
保留独立包、mjlab 1.6.0 与本地 PPO/网络/Storage/Runner 的既定方向，不实现新行为。

验收条件：

- 记录上游核对版本及源码链接，区分上游配置事实与本机硬件假设。
- 每项缺口给出本地现状、优先级、依赖及可执行验收方式；避免重复实现已交付的整机工厂和执行器。
- 执行项目内临时目录隔离的 `make check`；不将静态检查写成训练或实机运行证据。
- 所有子代理与检查进程结束后，删除本次临时产物和项目字节码缓存并复查。

核对版本（2026 年 10 月 27 日）：

- 实机仓库 [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)。
- 关联训练仓库 [microduck_rl@1e79c29](https://github.com/pollen-robotics/microduck_rl/tree/1e79c29c97d8b38aee9eefde77a545860ba7658e)。

**已有基础可以继续使用。** 模型加载、15 关节映射、12 无刷 PD 加 3 个 HD1910 M6、
整机实体、碰撞/足底参考点及短 GPU 场景检查已经实现，不再重复列为缺项。
本次重新验证的源模型质量为 `3.2893 kg`，不是实机称重结果；上游约 `0.8 kg`。
当前 `150 × 0.002 s = 0.3 s` 场景检查只验证接线、有限值、接触、限幅与 reset，
不能作为稳定站立、可训练环境或已学会行走的证据。

| 能力 | 官方参考与本地现状 | 后续工作 |
|---|---|---|
| 任务控制与观测 | 官方策略为 61 维输入、14 维输出；本机只有 15 关节实体，没有任务契约 | T022 固定动作子集/顺序、HOME、缩放、坐标系、上一动作含义、归一化及控制时序 |
| 平地环境 | 官方有 commands、actor/critic 观测、奖励、终止与课程；本机尚无 `tasks/` | T023 先实现站立命令和平地速度跟踪，验证多次 reset/step |
| 训练算法与入口 | 官方使用 mjlab/RSL-RL；本机入口仍为 pyproject 注释，网络、Storage、PPO、Runner 均未实现 | T024–T026 按既定架构在本仓库实现，先小规模短跑 |
| 评估与部署策略 | 官方有恢复、导出、CPU ONNX 回放；本机只有 export 可选依赖声明 | T027–T028 提供固定种子评估、完整恢复、带归一化的策略包与闭环回放 |
| sim2real 参数 | 官方按其 XL330 建模并做 DR；本机已有厂家 HD1910 参数和延迟/摩擦接口，未做本机标定 | T030 按两类执行器和 IMU 分别采集、拟合并验证 DR |
| 实机运行 | 官方有总线 I/O、IMU、状态机、故障处理、推理和日志；本仓库尚无对应模块 | T029、T031 接入本机硬件并分级验收 |
| 高级技能与产品服务 | 官方还有起身、蹲站、叼取、踢球、翻滚、轮滑及蓝牙/相机/OTA | 基础行走与部署通过后按需求另立任务，不作为当前训练前置 |

关键差异与源码依据：

1. [官方观测实现](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/obs.rs)
   使用角速度 3、重力 3、相对关节位置 14、速度 14、原始上一动作 14、命令 13，共 61 维；
   嘴独立控制，不进入策略动作。官方顺序为左腿、颈头、右腿；本机 constants 为右腿、左腿、颈头、嘴，
   不能复制索引、维度或权重。首版建议双腿 10 动作，其他 5 关节显式保持，这是待 T022 确定的任务选择。
2. [官方训练依赖](https://github.com/pollen-robotics/microduck_rl/blob/1e79c29c97d8b38aee9eefde77a545860ba7658e/pyproject.toml)
   固定 mjlab `1.3.0` 和 Warp `1.12.0`；本机继续 mjlab `1.6.0` 与本地算法，参考任务设计而不照搬依赖/API。
3. [官方控制器](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/control.rs)
   按 `HOME + scale × action` 生成目标，另有滤波与模式处理。训练、回放、部署的裁剪和滤波顺序必须一致。
   官方策略 50 Hz 只是参考；若本机最终选择 `dt=0.002 s` 和 50 Hz，则 decimation 为 10，尚非已定控制参数。
4. [官方导出](https://github.com/pollen-robotics/microduck_rl/blob/1e79c29c97d8b38aee9eefde77a545860ba7658e/scripts/export.py)
   将观测归一化嵌入 ONNX，并附元数据；本机也应导出完整推理处理，不能只转换裸 actor 权重。
5. 官方 [I/O](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/io.rs)
   面向 Dynamixel 总线；[IMU](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/imu.rs)
   和[故障处理](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/safety.rs)
   可参考接口和测试方法。本机实际无刷协议、飞特总线、IMU 安装和控制板尚需确认，不能将官方总线、
   安装旋转、增益或故障阈值作为本机已确认数据。源码允许短暂沿用旧传感样本，部分旧设计文字要求当步新鲜样本，
   以[当前主循环](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/main.rs)
   为核查依据，不复制其容忍时长。

推荐顺序：T001 → 依据 T016 证据关闭 T002 → T022 → T023 → T024 → T025 → T026 → T027 → T028。
硬件路径为 T022 → T029 → T030，最终由 T031 汇合训练导出与实机证据。
新增待办不改变 M0/M1 当前验收状态；T029–T030 是可在契约确定后开展的独立硬件工作，
不代表训练阶段已通过。T031 在 M3、仿真性能门槛和硬件标定均通过后验收；这些任务尚未启动。

### T022–T031 后续任务的产物与验收

以下命令为待实现接口建议，当前不能直接运行；开工时确定最终参数并写入对应任务。
全部实现任务继续要求 `make check`，GPU 与硬件专项验证须另行保留实际运行证据。

| 任务 | 具体产物 | 专项验收方式 |
|---|---|---|
| T022 | 首版控制/观测配置及 `tools/check_task_contract.py` | `uv run --no-sync python -B tools/check_task_contract.py --device cuda:0`；逐关节脉冲验证映射，4 环境按任务周期运行数秒，检查非策略关节保持、限幅、历史与局部 reset；冻结单位、时序、偏置/缩放和处理顺序 |
| T023 | `tasks/` 中的平地速度环境及 `tools/check_velocity_env.py` | `uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0`；4–16 环境反复 reset/step，验证观测/动作/奖励有限值及形状、跌倒/超时区分；actor 只用实机可得量，真值线速度/接触可供 critic 或奖励使用 |
| T024 | 本地 actor/critic、观测统计、Storage 和 GAE | `uv run --no-sync python -B -m pytest -q tests/test_networks.py`（Storage 与 GAE 测试同文件）；用可手算轨迹检查 return/advantage、真实终止与 timeout bootstrap，验证 log-prob/value 形状和批次覆盖 |
| T025 | 本地 PPO 损失与更新模块 | `uv run --no-sync python -B -m pytest -q tests/test_ppo.py`；验证 clipping、熵、value loss、梯度裁剪与更新前后参数变化，有限梯度和 log-prob 一致性 |
| T026 | Runner、`duck-train`、配置/种子/指标记录和 checkpoint | `uv run --no-sync duck-train --num-envs 16 --iterations 5 --seed 0`；完成采样及数次 PPO 更新，loss/梯度有限、检查点可读且可恢复；记录零动作/初始策略基线，不以短跑宣称学会行走 |
| T027 | 恢复入口、`duck-play`、`duck-eval` 和评估报告 | 用同一 checkpoint 实际执行恢复训练、回放及固定种子评估；恢复网络、优化器、统计与迭代号，区分重启环境与精确轨迹续接；覆盖零速、前后、侧移、转向，报告跟踪误差、跌倒率、episode 长度与限幅统计；开工时冻结部署前的仿真性能门槛，未达标时先记录并按授权训练/调参，不能进入 T031 |
| T028 | `duck-export`、策略元数据、ONNX 一致性工具和 CPU 回放工具 | 实际执行 `duck-export`、`tools/check_onnx.py`、`tools/play_onnx.py`；同一观测集比较 PyTorch/ORT 并冻结误差容限，在 CPU MuJoCo 用同样的执行器、时序、观测、缩放/滤波闭环运行，避免换成理想 PD；确认 CPU 对 BAM 的适配 |
| T029 | 混合硬件后端、IMU 转换、状态机、FakeIo 和带时间戳日志 | `uv run --no-sync python -B -m pytest -q tests/test_runtime.py` 加目标板只读/单关节低幅度检查；验证零位、符号、单位、两类链路时序、IMU 坐标；注入断流、旧样本、NaN、推理失败和超期，检查启停、渐变与故障行为 |
| T030 | 两类执行器/IMU 标定配置、原始轨迹、对比报告和 DR 事件 | 用项目内保留的实测数据运行拟合/回放命令并交付该命令；对比延迟、超调、稳态误差、速度与饱和，核查质量/质心/惯量及摩擦；DR 范围注明测量或假设，验证 reset 不累积且环境独立；无数据时记录阻塞，先关闭相关 DR |
| T031 | 目标板时序报告及实机站立/低速跟踪记录 | 按空载/支撑、站立、低速命令分级运行，逐步记录命令与状态、跌倒/限幅、温升/供电和故障；完整环路 p50/p95/p99、超期次数满足 T022 控制周期；具体幅度、时长和阈值由本机标定及实机条件确定 |

T030 更新模型参数后须核对训练配置与实机契约；超出已训练、验证范围时，重做受影响的仿真、
训练、评估与导出。T031 只使用与最终标定配置匹配且通过仿真性能门槛的策略包，不能沿用过时导出结果。

稳定行走之后再评估起身、头部联合控制、复杂地形和其他技能。
上游产品层的 Rust 多服务、蓝牙、相机与更新系统不要求在本仓库完整复刻。

### T032 参考 quadruped_lab 完善工作流与忽略规则

目标：借鉴 `/home/sunteng/projects/quadruped_lab` 的按变更规模选择流程、模块边界、依据核查、
并发分工和独立审查规则，完善本项目可执行的开发工作流与 `.gitignore`。

范围：根开发约定、开发文档、必要的设计/审查模板、忽略规则、Makefile 和 README 入口说明。
保留现有架构、任务历史、用户已有修改和模型资源；不照搬参考仓库对 `tests/` 和流程文档的忽略规则。
检查入口统一使用项目内临时目录；如需恢复统一检查，仅修复已知的预览入口 import 排版，不改变行为。

验收条件：

- 工作流职责与链接一致，区分小修改与大功能、事实与假设、自审与独立审查，避免额外的常规审批。
- 用 `git check-ignore` 验证环境/缓存/构建/实验输出被忽略，源码、测试、流程文档、模型和锁文件可纳入版本控制。
- `make check` 通过，检查产物限定在项目 `.artifacts/`；审阅新增文件与已有未提交改动。
- 独立复核最终文件，所有代理和检查进程结束后清理本次临时产物及项目字节码并复查。

### T033 替换为用户提供的 HT-DK_URDF 模型

目标：将默认机器人模型替换为 `/home/sunteng/Downloads/HT-DK_URDF` 的模型与配套网格，
项目独立保存资源，不依赖 Downloads 路径。

范围：复用来源包已提供的 `xml/HT-DK_URDF.xml`，调整包内 mesh 路径与预览根高；替换配套 STL，
同步常量中的默认入口、碰撞名称、足底参考点和无穿地中性初态，更新已有测试与 README。
关节顺序及 12+3 电机分组不变，执行器增益、限幅和延迟继续沿用现有仿真假设。
属于机器人资源和几何参数调整，不新增训练或跨模块接口；由主代理实施、子代理只读核对来源与最终结果。

验收条件：

- 项目资源与来源 XML/STL 一致，仅 mesh 路径和预览根高作本地适配；从其他工作目录亦能编译。
- `make check` 通过；关节限位、足底 site、初态无穿地、碰撞体语义与来源模型一致。
- 使用正式 `check_robot_scene.py` 在 `cuda:0`、种子 `1910`、4 环境、150 个 `0.002 s` 步内验证
  目标映射、双脚接地、有限值、限幅、字段独立性及局部 reset；超时上限 180 秒。
- 所有检查临时目录限于 `.artifacts/`，独立复核后清理本次临时产物与项目字节码，保留已有修改。

### T034 对照 duck_project 评估无刷电机 NT 执行器

目标：根据 `/home/sunteng/projects/duck_project` 的实际电机曲线与实现，判断本项目是否需要
无刷执行器，以及可复用的逻辑、数据边界和最小实现范围。

范围：先读本地无刷 PD、关节与 XML 限幅，再核对参考项目电机数据、源图、运行时执行器，
并核对 mjlab 1.6.0 的现有执行器能力。用户已澄清“3530”指参考项目中的 HTDW-3532-02-DNE，
与本地已有电机名称一致，无需改名。此次先分析并记录结论，不提前实现新执行器。
由只读子代理核对参考曲线，主代理核对本地与上游接口，最后独立复核结论。

验收条件：

- 结论有源码/数据的版本、路径和具体位置，区分已验证事实、外部参考与仿真假设。
- 明确 NT 曲线的电压、轴端、单位、插值、四象限处理及与现有 PD、延迟、XML 限幅的关系。
- 给出是否新增执行器、模块边界、最小实现及专项验收建议，记录型号/实测参数缺口。
- `make check` 通过；分析与文档不新增测试、不重跑 GPU；结束后清理本次临时产物与项目字节码。

核对结论与后续最小实现：

1. **建议增加对应的 NT 限幅 PD 执行器。** 本地 constants 第 90–114 行已经声明 12 个 3532，
   但使用 `BuiltinPositionActuatorCfg`，只限制固定 `2 N·m`，没有速度相关包络。
   保留当前固定上限时，参考曲线在超过 `128 rpm` 后成为更严格约束；`167/211 rpm` 的驱动上限
   分别为 `1.5/1.0 N·m`，`300 rpm` 为零。低速行为可以保持，较高速驱动不再使用恒定力矩能力。
2. **迁移运行时曲线逻辑及有来源的数据。** 参考 `src/htdk/motor.py:6–17`、
   `src/htdk/actuator.py:23–44` 和 `src/assets/motors/htdw_3532_24v.json`；原始图片为
   `src/assets/motors/HTDW-3532-02-DNE_user_datasheet.png`。
   源图标示 24 V、减速比 32、额定 `0.6 N·m`、堵转 `3.7 N·m`、空载 `300 rpm`。
   锚点是图像采样后取整的近似，不是本机实测。单位已经是减速器输出轴 `rpm / N·m`，不能再乘减速比。

   ```text
   rpm:   0    26   59   92   128  167  211  258  300
   N·m:   3.7  3.5  3.0  2.5  2.0  1.5  1.0  0.5  0
   ```

   运行时用实际输出轴速度 `abs(dq) * 60 / (2*pi)`，在相邻点间线性插值，
   先用固定力矩上限限制 PD，再仅对 `tau_pd * dq >= 0` 的驱动象限应用 NT 包络。
   两个旋转方向镜像使用同一曲线；达到/超过 `300 rpm` 时同向驱动力矩为零，仍允许反向制动。
   制动上限暂沿用配置的固定力矩限幅，是参考实现的明确假设，源图没有再生/制动曲线。
   `0.6 N·m` 是连续额定值，不能把 `3.7 N·m` 堵转值称为可持续力矩；没有热参数就不新增热模型。
3. **通用 DC 模型不能原样保留这条曲线。** 已核对安装的 mjlab `1.6.0` 和官方固定版本：
   [dc_actuator.py:25–50](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/dc_actuator.py#L25-L50)
   使用直线包络。以 `3.7 N·m` 和 `300 rpm` 为端点、固定上限 `2 N·m` 时，
   其 `167/211 rpm` 上限约 `1.6403/1.0977 N·m`，不同于参考曲线的 `1.5/1.0`。
   超速时该电压包络还可能产生反向力矩，与参考实现的驱动归零规则不同。
   本地 `builtin_actuator.py:260–325` 的原生 DC 模型可用数据表三元组或 `Kt/Ke/R` 参数化，
   但它改变了电压/PID语义，也不能仅靠两个端点复现上述分段曲线，当前不选用。
4. **保持本机模块边界与硬件分组。** 建议在 `src/ht_microduck/actuators/HTDW_3532_02_DNE/`
   保存参数、来源说明和轻量 NT-PD 实现，基于 `IdealPdActuator` 复用控制与生命周期；
   在 constants 中装配 12 个无刷，3 个 HD1910 BAM 保持现有归属。
   参考项目只对双腿 10 个关节应用曲线，颈/头俯仰归入舵机且嘴固定，不能复制其关节分组。
   参考 `src/htdk/tasks.py:146–149` 的 `armature=0.002`、零延迟、`dt=0.004 s` 和控制降采样 5
   都不是本机标定数据；不照搬增益、惯量、延迟或任务参数。
5. **接入时需要同时核对数值与控制通道。** 第一版保留本地 `kp=10`、`kd=0.4`、
   固定上限 `2 N·m`、XML 总上限 `3.7 N·m`、被动阻尼 `0.02` 及 `0–3` 步命令延迟，
   继续注明仿真假设；不默认为堵转上限可持续输出，不重复加入摩擦。
   曲线计算留在 Torch 的原设备/类型，每物理步读取当前速度，目标延迟由 mjlab 处理一次。
   参考诊断 `analysis/nt_curve.py:59–85` 使用 CPU/NumPy，不用于逐步控制路径。
   mjlab 1.6 的 `IdealPdActuator` 通过 `control_law` 计算，参见
   [pd_actuator.py:55–68](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/pd_actuator.py#L55-L68)；
   本机 `IdealPdActuator`/`Actuator` 没有参考 `compute` 所调用的 `_clip_effort`，
   因而参考类不能原样复制，也不能只覆盖该方法；需使用当前的 `force_limit` / `control_law` 接口。
   可显式覆盖 `compute`，或遵循
   [fused_group.py:61–73](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/fused_group.py#L61-L73)
   的共享计算约定；按所选路径验证真实 Entity 调用，走融合路径时另核验参数与延迟一致性，
   不能仅直接调用函数算作集成通过。
   从原生隐式 PD 改为显式力矩输入后，需要重新跑短动态检查，旧场景结果不能代替。

参考目录没有 `.git`（根与 `src/` 均已检查）；2026-10-27 读取的内容 SHA256 为：

| 参考文件 | SHA256 |
|---|---|
| `src/htdk/motor.py` | `8225cbbf25383d65b08e08e8574ec971d13842e5a080a34d01f61384e77a651f` |
| `src/htdk/actuator.py` | `022fcd00d91907237a4e8659fc4c813ce755edf255f6174b79d0914971c9bbea` |
| `src/assets/motors/htdw_3532_24v.json` | `a0f102775e78a1a95a3c5d97bbd69c0a4c132f1d692d248fa310bbfd596f9447` |
| 原始资料 PNG | `56c8ac1a17ccbbf840591fefeec254b939477ff1cd8a9cb31220004cf11b9770` |

下一项可执行实现：先完善本主题设计，再增加上述小执行器与参数资源，替换无刷配置并同步专项工具/测试。
验收至少包括全部锚点与中点、一次单位换算、正负驱动/制动/超速、固定与 XML 限幅、
12+3 控制顺序、目标延迟和局部 reset，以及正式混合执行器和整机的有界小规模 GPU 短跑。
源图电压是 24 V 条件，实际带载电压、制动能力、摩擦/惯量和峰值持续时间仍需本机验证；
不凭源图推定其他电压下的完整曲线。

### T035 实现并接入 3532 NT-PD 执行器

目标：将 T034 的有来源输出轴曲线接入本项目 12 个无刷关节，在 PD 固定限幅后增加驱动象限 NT 限幅。
范围：新电机模块及参数资源、机器人装配、已有专项工具与相关测试、README；执行器和训练职责不混用。
详细接口、实施分工及验收见 [设计](../design/htdw3532_nt.md)，独立审查见 [审查记录](../review/htdw3532_nt.md)。

验收条件：

- `make check` 通过；曲线锚点/中点/单位与类型、正负驱动与制动、空载及超速、PD 三类目标和限幅有数值验证。
- 全部 15 个关节及 12+3 映射正确，XML 被动属性保留；实际 Entity 每物理步使用一次目标延迟和当前反馈。
- 种子 `1910`、`cuda:0`、4 环境：正式混合执行器工具 300 步加延迟回归，整机场景 150 步；
  每个入口超时 180 秒，另验证高速 NT 实际控制与局部 reset；不将完整训练作为默认验收。
- 独立审查通过，参数与原始来源随 wheel 打包；所有代理/检查结束后清理本轮临时产物和项目字节码。

### T036 对照三个参考项目确定下一步

目标：对照 pollen-robotics/microduck、pollen-robotics/microduck_rl 和本地 duck_project，
判断本仓库当前最该做的工作，并把结论落成有验收条件的后续任务。

范围：只读核对三个参考项目与本仓库现状；本轮只更新本页和 README 的下一步说明，
不修改机器人源码、参数、XML、依赖或测试，不执行训练与实机操作。

核对版本（2026 年 10 月 27 日）：

- [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)，默认分支 `main`，与 T021 记录一致。
- [microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3)，**默认分支是 `develop`**；
  T021 记录的 `1e79c29` 是 `main` 上的提交，比 `develop` 落后 76 个提交。以后引用该仓库必须注明分支。
- `/home/sunteng/projects/duck_project`：无 `.git` 的归档（代码 + 参数 + 报告，不含权重）。

**本机复核（只读探针，非验收）**

- `make check` 退出码 0：锁文件、Ruff、131 项测试与 8 项子测试、模型与差异检查通过；
  被动模型 `nq=22`、`nv=21`、`nu=0`、15 关节、16 网格、质量 `3.2947 kg`。
- 原模型不含任何 sensor：`nsensor=0`，只有 `r_foot`/`l_foot` 两个 site（由整机工厂添加）。
  官方 61 维观测的前三组依赖陀螺与重力方向，本仓库当时没有 IMU 声明（T037 已补）。
- HOME 零位几何：躯干高 `0.171 m` 时两足最低点各 `+3.84 mm`，脚底支撑面与水平面成 **5.00°**
  （左右各向外倾，`r` 法向 `y=-0.0872`、`l` 法向 `y=+0.0872`），单脚接地面积仅 `1.59 cm²`，
  接触多边形在 y 方向只有 `2.3 mm` 宽；重心投影距单脚支撑边界仅 `0.88/0.66 mm`，
  距双足联合支撑边界 `24.55 mm`。左右腿关节轴不镜像（左右同为正 `hip_pitch=knee=ankle` 轴），
  与 duck_project 的"右腿取负"约定不同。
- 把左右 `hip_roll` 各向内收 `0.0873 rad` 后，两侧脚底同时水平：支撑面倾角 `0.00°`、
  单脚接地面积 `30.02 cm²`、脚宽 `42.9 mm`、单脚重心余量 `5.19/4.97 mm`、站宽由
  `0.1556 m` 变为 `0.1355 m`，且不产生自碰撞。该姿态是几何解，不是已确认站姿。
- GPU（RTX 4060、`cuda:0`、种子 `1910`、4 环境、`dt=0.002 s`）零位保持 3 s：
  根高由 `0.1710` 沉到 `0.1655–0.1657 m`，倾角 `<1.5°`，两足全程有载，无跌倒。
  加 `hip_roll ±0.0873` 后根高 `0.1682 m`、倾角 `<1.3°`、两足全程有载，左右法向力 `17.0/15.3 N`。
- 同一保持测试的水平速度脉冲：`0.10 m/s` 后最大倾角 `2.02°`；`0.20 m/s` 时 `6.29°`；
  `0.35 m/s` 时倾角 `82–93°`、根高掉到 `0.06–0.09 m`，判定跌倒。零位站姿的稳定边界很窄。
- 全部测试增益仍为源码中的仿真假设（`kp=10`、`kd=0.4`、限幅 `2 N·m`），未做任何标定。

**参考项目的可取之处与不可照搬项**

| 参考 | 可取做法 | 不能照搬 |
|---|---|---|
| microduck_rl@develop | 观测/动作契约单点定义；导出把归一化烘进 ONNX；HF 上的策略 manifest 做 `[1,61]→[1,14]` 校验 | `mjlab==1.3.0`、`warp 1.12`、RSL-RL `5.0.1`；XL330 `kp_fw=200`、延迟 `3–6` 步；61/14 维与关节顺序 |
| microduck@main | 部署侧 `targets = HOME + scale × action`，并有 `legs_lowpass`、安全层（NaN 拒绝、超程 clamp、deadman 500 ms、跌倒判据） | Dynamixel 总线与 ID 布局、`scale=0.9/1.0`、`gain=200`、IMU 安装旋转 |
| duck_project | 量化口径（抬脚/前扫/打滑/单脚悬空 + 红线诊断）；N-T 软约束与验收统计；"改 default_joint_pos 会平移观测、破坏热启动"的经验 | 旧机 14 维动作、`scale=0.5/1.0`、`stand_z=0.163`、`sit_q`、8 mm 抬脚等全部旧几何阈值；其 v44 的 48 集评估 `success_rate=0.0`，不能当作成功基线 |

duck_project 归档中另有一处文档与数据冲突：`reports/README.md` 称 sitstand "达成率 96%"，
而 `sitstand_v46.md` 的实际统计是 `96/192 = 50%`，且该 run 目录下没有 `evaluation.json`。
引用它的结论时应以具体 JSON/数值为准，不引用概述性百分比。

**结论：下一步做什么**

1. **先收 Git 基线（T001）。** 当前只有 `README.md` 被跟踪，59 个未跟踪文件
   （含 16 个 STL、`uv.lock`、全部源码与测试）不在版本控制内，任何后续实验都无法回溯。
   这是 T022 及之后所有任务的前置，也是 T021 已记录的同一个阻塞点。
2. **补 IMU 声明（T037，已完成）。** 原模型没有任何 sensor，官方 61 维观测的前三组
   （陀螺、投影重力、线速度）在本仓库没有对应来源；没有它们，T022 的 actor 观测只能拿
   仿真真值，违反 T021 记录的"actor 只用实机可得量"。
3. **标定 HOME 站姿（T038，待办）。** 现有"全零关节"只满足"不穿地"，但脚底外倾 5°、
   单脚支撑 `1.59 cm²`、重心余量不到 1 mm，属于"能站但不该作为训练起点"的姿态；
   引脚外收 `0.0873 rad` 的候选站姿在几何与 3 s 保持上都明显更好，取向待用户确认。
4. **然后按 T022 → T023 推进契约与最小平地速度任务。** 契约需要冻结的内容比 T021 时更明确：
   动作是 10 维（双腿）还是 14 维（含颈头俯仰）、`HOME`、`scale`、上一动作含义、
   归一化、控制周期（`dt=0.002 s` 时 decimation 取 10 → 50 Hz 或 5 → 100 Hz）、
   以及"右腿不取负"对本机观测与奖励符号的影响。
5. **训练链路按 T024–T026 本地实现，不引入 RSL-RL**：架构方向仍是自研 PPO/Storage/Runner，
   但可以把 microduck_rl 的导出配方、duck_project 的量化验收脚本结构作为验收模板。
6. **T029–T031 的硬件工作继续等待本机协议/IMU/控制板信息**，T030 也不具备测量条件；
   在 T036 的调研范围内不调整这部分依赖关系。

### T037 在 XML 中声明 IMU 参考点与内置传感器

状态：完成。

目标：让被动模型与整机工厂都具备训练所需的姿态与角速度观测来源，命名与官方项目一致，
不把噪声、延迟和安装误差写进模型。

范围：`xmls/HT-DK_URDF.xml`（新增 `imu` site 与 `<sensor>` 块）、
`ht_microduck_constants.py`（`get_spec()` 说明；IMU 名称由工具与测试直接从模型读取）、
`tools/check_robot.py`、`tools/check_robot_scene.py`、`tests/test_robot_entity.py`；README。

依据（外部参考，2026 年 10 月 27 日核对）：

- [microduck_rl@b02fdea `sensors.xml`](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/sensors.xml)：
  `imu` site 上的 `framequat`、`gyro`、`gyro`、`velocimeter`、`accelerometer`，加 `subtreeangmom`。
  同目录 `robot_groundcontact.xml` 的 `imu` site 在 `trunk_base` 上，`quat="1 0 0 0"`。
- 同一提交的 `microduck_velocity_env_cfg.py` 用 `mdp.builtin_sensor` 读
  `robot/imu_ang_vel`、`robot/imu_lin_vel`，并用 `projected_gravity`；`raw_accelerometer`
  按固定的 sensor 下标读第 5 个传感器，属于绑定该 XML 的写法，未照搬到本仓库。
- mjlab 1.6.0 资产库（`unitree_go1`、`unitree_g1`）用同样的 `gyro` / `velocimeter` /
  `accelerometer` / `framezaxis` 组合，`Scene._add_sensors` 会把实体 XML 里已有的 sensor
  以 `<entity>/<name>` 注册，因此本仓库不需要在场景配置里重复声明。

实施内容：

- 新增 `imu` site：挂在 `base_link` 原点、单位姿态、`group=3`、半径 `0.004 m`。
  这是仿真占位，不是测得的板载位置；XML 注释与 README 均标明。
- 新增 5 个 sensor：`imu_ang_vel`（gyro）、`imu_lin_vel`（velocimeter）、`imu_accel`
  （accelerometer）、`imu_upvector`（framezaxis，world +Z 在 IMU 系中的方向，
  即投影重力的反向量，配 mjlab 的 `mdp.projected_gravity_from_sensor`）、
  `root_angmom`（subtreeangmom，`base_link` 子树）。
- 未采用官方 `framequat`（冗余于 `imu_upvector`）与官方第二个 `gyro`（带 `noise` 的近似重复项）；
  传感器噪声、延迟与安装误差按 mjlab 约定留在任务观测配置。

验收条件与结果：

- `get_spec().compile()` 后 `nsite=1`、`nsensor=5`，名称与顺序为 `imu_ang_vel`、`imu_lin_vel`、
  `imu_accel`、`imu_upvector`、`root_angmom`；
  整机工厂 `nsite=3`（`imu` + 两足底）、`nsensor=5`、`nu=0` 保持被动。
- 数值语义有断言：静止直立时 `imu_upvector=[0,0,1]`、陀螺/线速度/角动量为零；
  绕 z 轴偏航 30° 后 up 向量不变；绕 y 轴俯仰 −30° 后 up 向量为 `[0.5, 0, 0.866]`；
  给定根角速度 `[0.3,−0.2,0.5]` 时陀螺读数一致。
- 场景检查：`robot/imu_*` 与 `robot/root_angmom` 全部注册为 `BuiltinSensor`，
  形状 `(num_envs, 3)`、有限值，陀螺与 `root_link_ang_vel_b` 一致、`-up` 与
  `projected_gravity_b` 一致；`make check` 与 GPU 150 步场景检查通过。
  陀螺比较在步进 12 步之后执行（`|root ang vel|` 峰值 `0.165 rad/s`），并先要求
  `|root ang vel| ≥ 1e-3`，避免 reset 后两边同为 0 的恒真断言；负向对照（把 `imu` site
  转 20°）会产生 `0.127 rad/s` 的偏差，确认该断言能发现接错的 site。
- `root_angmom` 语义（实测）：世界系、绕子树质心，`base_link` 子树覆盖全部 16 个非 world body；
  与"绕基座原点"版本差 `0.2675`、与体系版本差 `0.1033`，不要当体坐标系或基座原点量使用。
- `imu_accel` 的语义（实测，2026 年 10 月 27 日）：MuJoCo accelerometer 输出比力，
  **自由落体时精确为 0**（`qpos0` 下 `ncon=0`、无支撑，读数 `[0,0,0]`），
  **有支撑静止时约为 `+9.81·imu_upvector`**（站立 `imu_accel=[9.810, 0.005, −0.032]`，
  与 `R^T·(+g)` 差 `3.8e-2`，残差来自接触振动）。所以加速度计并不排除重力；
  需要无噪声的重力方向时仍用 `imu_upvector`，不要假设 `imu_accel` 在支撑状态下为 0。
- 实机可得性分级（供 T022 定 actor 观测）：`imu_ang_vel`、`imu_upvector`（等价于姿态）
  是实机 IMU 可得的；`imu_lin_vel`、`root_angmom` 在本机没有对应传感器，
  只能给 critic 或奖励，不能进 actor —— 官方 `microduck_velocity_env_cfg.py` 同样把
  `base_lin_vel` 从 actor 删除后只加到 critic。`imu_accel` 实机可得但其含义依赖
  加速度计标定，本次未启用。

### T038 标定 HOME 站姿

状态：完成。用户给出 `r_hip_roll=0.38`、`r_hip_pitch=1.57` 的大致取向，要求左腿镜像、
重心居中且不前后倾，并授权自行补齐其余关节。

目标：给出一个可复核、脚底平贴、支撑余量足够的 HOME 站姿。

范围：`ht_microduck_constants.py` 的 `HOME_FRAME`（含初态根高），以及 `tools/check_robot_scene.py`、
`tests/test_robot_entity.py` 的对应断言；README 同步。

结果：

用户给的两个角度都不能直接落地，实测依据如下（`.artifacts/t042-stance`，RTX 4060）。

1. `hip_pitch=1.57` 正好是关节限位（`range="-1.571 1.571"`），且会把腿折到脚过髋：
   `roll 0.38 / pitch 1.57 / calf 0 / ankle 0` 的脚底法线倾角 **88.15°**，
   补 `calf=−1.57` 后仍有 16.90°；两者在 5–6 s 零动作保持中都是 **48/48 全倒**
   （根高掉到 0.043 m，倾角 74–76°）。所以 pitch 必须降到 0.85。
2. `hip_roll=0.38` 只在 (−0.384, 0.384) 内留 0.004 rad 余量，且把脚底翘起约 16.9°，
   只靠内缘着地；同时横向支撑余量从 92 mm 收到 57 mm。平地姿态需要的镜像内收是
   **`+0.0873 / −0.0873`**（T041 结论），脚底倾角 `0.13°`，与全零姿态的 `4.87°` 相比才是真正水平。

最终 HOME（`HOME_JOINT_POS`）：

| 关节 | 右 | 左 |
| --- | --- | --- |
| `hip_roll` | `+0.0873` | `−0.0873`（镜像） |
| `hip_pitch` | `0.85` | `0.85`（同号） |
| `calf` | `−1.20` | `−1.20`（同号） |
| `ankle` | `0.35` | `0.35`（同号） |

`hip_yaw`/`neck_pitch`/`head_pitch`/`head_yaw`/`head_roll`/`mouth` 保持 0。
根高 `0.1534 m`。支撑面比最低顶点低约 0.5 mm，最低顶点（脚跟圆弧）离地 `0.4 mm`，
复位时 `ncon=0`。

依据（CPU 几何 + GPU 保持，各自独立测得）：

- 脚底平面倾角 `0.13°`（两侧相同），全零姿态是 `4.87°`。
- 重心到支撑边界：前 `40.0 mm`、后 `34.3 mm`、左 `92.5 mm`、右 `91.9 mm`；
  前后差 `5.7 mm`，即重心在脚掌前后基本居中，不向前也不向后倾。
- 静态保持力矩最大 `0.176 N*m`（`hip_roll`），远低于 `2 N*m` 上限。
- 5 s 零动作保持：**0/128 跌倒**（8 种子 × 16 环境，关节目标加 `0.01 rad` 噪声），
  根高稳定在 `0.150 m`，末端倾角 7.8–9.4°。

根高比姿势本身更敏感，这是本轮最重要的实测结论：

| 根高 | 最低顶点离地 | 零动作保持 |
| --- | --- | --- |
| `0.1530` | `0.00 mm` | 0/64（与地面接触） |
| `0.1534` | `0.40 mm` | **0/128** |
| `0.1540` | `1.00 mm` | 1/128 |
| `0.1545`/`0.1548` | `1.5`/`1.8 mm` | 0/128 |
| `0.1550` | `2.00 mm` | 1/96 |
| `0.1586` | `4.80 mm` | 2/64（旧零位的 3.84 mm 支撑面余隙） |

原因是任何可见离地间隙都让复位变成落体，落地冲击会把蹲姿撞散。因此不沿用旧零位
3.84 mm 的支撑面余隙，取 `0.1534 m`。这一条对后续所有复位/课程设计都成立。

早期版本的保持测试把所有候选都从 `root_z=0.171` 放下，让深蹲姿势从 3–8 cm 高空自由落体，
把落地冲击记成了姿势不稳；改成每个姿势按自身几何高度复位后结论才稳定。
平面拟合也不能用来判脚底倾角：脚部碰撞网格是整只脚（约 3.9e4 顶点）且带曲面，
在倾斜姿态下拟合会给出 33–90° 的假值；改为在真正水平的姿态标定一次脚底法线，
再用踝链旋转它。

守卫与断言同步：

- `tools/check_robot_scene.py` 的根高守卫原为绝对值 `0.15 m`，对更低的蹲姿等于失效且会误报；
  改为相对 HOME 的 `0.9 × HOME`（`0.138 m`），实测 `0.1498 m` 通过，腿塌时仍能拦住。
- `tests/test_robot_entity.py` 的三处 HOME 断言与脚底余隙区间（改为 `−1.5 mm ~ 0`）同步；
  “下压 5 mm 触地”改为 `8 mm`，因为最低网格点是脚跟圆弧而不是支撑面。

验收：

- `make check` 通过：`All checks passed!`、`134 passed, 1 warning, 8 subtests passed`。
- 整机场景 GPU 检查 150 步通过：`root_height=[0.149827, 0.149834] m`、
  `peak_effort=0.532 Nm`、`peak_joint_speed=0.841 rad/s`、双足接地、无溢出。
- 速度脉冲（协调的前倾+屈膝开环目标，1 s 保持）：

  | 幅度 | 旧零位 | 新 HOME |
  | --- | --- | --- |
  | `0.10 rad` | 0/24 | 0/24 |
  | `0.14 rad` | 0/24 | 0/24 |
  | `0.18 rad` | 0/24 | 0/24 |
  | `0.22 rad` | 0/24 | 0/24 |
  | `0.26 rad` | 2/24 | **0/24** |

  只前倾不动膝的非协调脉冲会让蹲姿在 0.35 m/s 档 23/24 跌倒，但那是不可执行的指令
  （膝关节不动时髋前倾等于把脚往后蹬），不作为站姿证据；执行器层面的跟踪能力归 T023。

未完成、需如实记录的部分：

- 默认增益未改，仍是 `kp=10`/`kd=0.4`。本轮只证明该增益下蹲姿可以 0/128 保持，
  没有证明它是最优增益；T041 曾测出 `kp=20`/`kd=0.8` 能把旧零位从 7/96 降到 2/96。
  增益与 HOME 的联合整定仍未做，属 T023 及 M1 的范围。
- 单脚/双脚接触面积没有直接测量。mjlab 1.6 的 `sim.data.contact` 是 `WarpBridge`，
  只有 `dist`/`pos`/`frame` 等扁平张量，没有 `geom1`/`geom2`，无法在设备侧按 geom 归并接触点；
  本轮改用 CPU 顶点与支撑面几何替代，并明确它不等于接触面积。
- 增益、限幅、延迟与供电仍是仿真假设；实机参数归 T030。不宣称完成实机标定。

### T039 按官方结构重写机器人常量模块

状态：完成。依赖 T037。用户指出本体 XML 不该带地形，并要求常量模块照官方写法、执行器用本地实现。

目标：机器人 XML 只包含本体；`ht_microduck_constants.py` 的结构与官方
`microduck_constants.py` 一致，同时保留本仓库自己的执行器实现。

依据（外部参考，[microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck)）：

- 官方 `robot_walk.xml` 顶层只有 `compiler`、`default`、`asset`、`worldbody`、`sensor`、
  `actuator`、`equality`，不含地面与灯光；`scene_walk.xml` 用 `<include>` 引入本体后再加地面。
- 官方 `microduck_constants.py`（331 行）只有：`_ROBOT_DIR` 与各 XML 路径常量加
  `assert XML.exists()`、一行式 `get_*_spec()`、`HOME_FRAME`、单套 `FULL_COLLISION`、
  `_BAM_ACTUATOR_KWARGS` 与执行器对象、若干 `EntityCfg`，末尾用 `SceneCfg` + `Scene` 做预览。
  没有 IMU 名称常量，没有电机映射表，没有分节横幅。官方在 env cfg 里直接写 `"robot/imu_ang_vel"`。
- mjlab 的 `Scene` 自带 terrain 平地与太阳，机器人 XML 带地面必然出现两个 plane。

实施：

- `HT-DK_URDF.xml` 只保留 `compiler`、`asset`（网格）、`worldbody`（机器人）、`sensor`。
- `ht_microduck_constants.py`（189 行）按官方结构重写：路径常量加存在性断言、一行式
  `get_spec()`、`get_robot_spec()` 只做碰撞体命名与足底 site、`HOME_FRAME`、单套
  `FULL_COLLISION`、无刷与舵机执行器配置、一个 `HT_MICRODUCK_ROBOT_CFG`、
  `get_ht_microduck_robot_cfg()` 深拷贝，末尾 mjlab `Scene` 预览。
  执行器沿用本地 `FrictionDRBamActuatorCfg` 与 `HTDW3532ActuatorCfg`。
- 删除本地自造的 `SCENE_XML_PATH`、`get_scene_spec()`、`IMU_SITE_NAME`、`IMU_SENSOR_NAMES`、
  `##` 分节横幅；工具与测试改为直接从编译后的模型读取 sensor 名称。

验收结果（本机实测）：

- 本体 `get_spec().compile()`：`nq=22 nv=21 nu=0 nsite=1 nsensor=5 nlight=0`，plane 数 0。
- `tools/check_robot.py` 输出“本体检查：无平面、无灯光；地面与灯光由 mjlab 场景提供”。
- `make check`：`All checks passed!`，`134 passed, 1 warning, 8 subtests passed`。
- GPU 场景检查（`cuda:0`、4 环境、150 步）：`planes=1`（仅 mjlab 的 `terrain`）、
  双足接地、`IMU sensors=5`、`peak_effort=0.138278Nm`、`root_height=[0.166165, 0.166172]m`。

剩余问题：

- `imu` site 仍在本体原点、单位姿态。官方 site 挂在 `trunk_base` 上但带 `(-0.021, 0.0001, -0.0147) m`
  偏移；本机该偏移未测量，属 T030 硬件标定。
- 站姿标定（T038）未做。

### T040 精简 README 并整理项目入口

状态：完成。依赖 T039，按用户要求进行文档整理，不改变实现和阶段验收状态。

目标：让首次阅读者快速了解项目用途、已有功能、检查入口和详细文档位置。

范围：根目录 `README.md` 和本页任务记录。安装流程引用 `setup.md`，
执行器公式、参数来源及接入细节引用已有模块说明与设计，任务进度仍在本页维护。

验收条件：

- README 中的目录、符号、命令与当前代码和 Makefile 一致，本地链接可解析。
- 保留 12+3 电机分组、机器人与场景的边界、仿真假设与实机标定的区别，以及训练入口尚未实现的说明。
- 直接运行的 GPU 检查示例先创建项目内临时目录，并隔离相关缓存。
- `make check` 通过；不新增测试，不因文档整理启动 GPU 短跑或训练。

### T041 对照三个参考项目复核下一步

状态：完成。依赖 T040；用户指定 pollen-robotics/microduck、pollen-robotics/microduck_rl 与
`/home/sunteng/projects/duck_project`，要求判断下一步做什么。

目标：把"已经有模型、混合执行器和场景检查，但还没有任务环境与训练链路"这一现状，
对照三个参考项目落到一个可执行的任务顺序上，并纠正上一轮遗留的错误前提。

范围：只读核对上游固定提交、`duck_project` 归档与本仓库代码；在项目内
`.artifacts/t040-next-step/` 写一次性探针做可行性实测。不修改机器人源码、参数、XML、
依赖或测试，不执行训练与实机操作。探针在交付前删除，结论与数值落回本页。

核对版本（2026 年 10 月 27 日，均用 GitHub API 核对默认分支）：

- [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)，
  默认分支 `main`，2026-10-26 "Prepare release 0.17.9"。
- [microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3)，
  默认分支 `develop`，2026-10-12；与 T036 记录的提交一致，`develop` 本身未再前进。
  仓库 `pushed_at` 更新是因为其它分支在动，引用时仍须写明 `develop`。
- `/home/sunteng/projects/duck_project`：78 个 run 的归档，无 `.git`、无权重。

**上游事实（附固定链接）**

- 训练侧主任务是平地速度跟踪 `Mjlab-Velocity-Flat/Rough-MicroDuck`；另有 `StandUp`、
  `VelStand`、`SitStand`、`RollerStandUp` 等站立/起身任务，注册表见
  [tasks/\_\_init\_\_.py](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/__init__.py)。
- 观测固定 61 维：`base_ang_vel`(3)、`projected_gravity`(3)、`joint_pos`(14)、`joint_vel`(14)、
  `last_action`(14)、命令块 13（twist 3 + head_pose 4 + body_pose 6）。actor **删除**
  `base_lin_vel` 与 `height_scan`，只给 critic；即刻意只用实机可得量。
- 动作 `JointPositionActionCfg`、`scale=1.0`、14 维（15 关节去掉嘴）；控制 50 Hz
  （`timestep=0.005`、`decimation=4`）；`episode_length_s=20`。
- 命令固定 `lin_vel_x ±0.4`、`lin_vel_y ±0.3`、`ang_vel_z ±1.0`，不再做扩张课程；
  15% 环境专训原地转；站立环境占比 0.02→0.25 走课程。
- 奖励骨架：`track_linear_velocity +2.0`、`track_angular_velocity +2.0`、`upright +2.0`、
  `pose +1.0`、`air_time +3.0`、`head_pose_tracking +2.0`、`self_collisions −1.0`、
  `action_rate_l2 −0.1→−1.0`（课程）、`foot_slip −0.1`（刻意弱）、`body_ang_vel −0.05`、
  `angular_momentum −0.02`。
- 上游 `AGENTS.md` 给出可迁移的工程经验：每个罚项在 wandb 中必须 ≤ 0（符号写反会变成奖励）、
  不要用二值 mask 门控奖励、命令槽即使权重为 0 也要保留小范围采样、零命令必须显式训练、
  课程阶段要与策略实际进度对齐、`warm start ≠ resume`（步数计数器会被恢复）。
- 部署侧 [control.rs](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/control.rs)
  的目标为 `HOME + scale × action`；[safety.rs](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/safety.rs)
  对 NaN 是**拒绝**而非夹取，deadman 500 ms 只清速度，跌倒判定只上报。
- 上游存在一处自相矛盾：训练侧 `AGENTS.md` 写策略训练中不加动作低通，
  部署侧 `control.rs` 写滤波系数"训练时就是 0.5/0.7"。二者不能同时成立，不能作为本机依据。

**duck_project 事实（以 JSON 为准，不引用概述性百分比）**

- 48 集行走评估（seed 2043）：v21 37/48、v29 25/48、v37 36/48、v38b 0/48、v43 0/48、v44 0/48。
- v44 的 0/48 全部由 `velocity` 判死（48/48，其中 `|vy|≥0.04` 有 45 集），
  且该 run 的 `selection.json` 选中的权重是 v29 的 checkpoint——0/48 指新训 final，
  0.625 是回退基线，两者不能混用。
- 文档里的"前扫 15.3 mm / 抬脚 17.0 mm"在 `params/`、`reports/` 中没有任何原始 JSON 支撑，
  仅出现在 md 与脚本内硬编码表；`sitstand` 的"96%"是把分子 96/192 误当百分比，
  `sitstand_v46.md` 自述为 50%。
- 归档代码里 `gait.py` 的 excursion 仍用机体系，正是 v43 认定为致命 bug 的算法；
  评估口径应以 v43 之后的世界系版本为准。

**本机实测（一次性探针，非验收）**

探针位于 `.artifacts/t040-next-step/`，全部使用项目内 `TMPDIR`/Warp/Torch 缓存、
`PYTHONDONTWRITEBYTECODE=1`，RTX 4060、`cuda:0`。

1. **mjlab 1.6 自带的平地速度任务可以直接套在本机器人上**，但必须显式改六处，
   否则第一次 `reset` 就报错。实测的失败顺序与修法：
   - `feet_ground_contact`、`self_collision` 两个接触传感器在通用模板里不存在，
     需按本机 `r_foot_collision`/`l_foot_collision` 与 `base_link` 子树自行声明，
     否则 `KeyError: Scene element 'feet_ground_contact' not found`。
   - `pose` 奖励的 `std_standing/walking/running` 默认是空字典，必须给正则映射，
     否则 `tensor a (15) must match tensor b (0)`。
   - `terrain_scan` 与 `height_scan` 在平地上应删除；`foot_height_scan` 改为
     `r_foot`/`l_foot` 两个 site。
   - `actions["joint_pos"].actuator_names` 需显式给 10 个腿部关节，才能得到 10 维动作
     并让其余 5 个关节保持默认位置。
   - `htdw3532_init`、`bam_init` 两个 startup 事件必须注册，
     否则 `HTDW3532 needs independent per-world native PD fields`。
   - `foot_friction`、`base_com`、`upright`、`body_ang_vel`、`foot_clearance`、`foot_slip`
     的 asset 选择器默认是空元组，需按本机命名填写。

   按上述改动后，2 环境 `obs[actor]=(2,52)`、`obs[critic]=(2,64)`、动作 `(2,10)`，
   20 步零动作奖励有限，根高 `0.1658–0.1664 m`，未触发跌倒终止。
   52 维的构成是 3+3+15+15+10+3（角速度、投影重力、全部 15 关节位置与速度、上一步动作、命令）；
   joint_pos/joint_vel 含被保持的 5 个关节，因此比动作维度大。
2. **吞吐**：同配置下 256 环境约 `1.47e4` env-step/s、1024 环境约 `1.29e4`、
   4096 环境约 `4.20e4`（60 步均值，含少量首次编译摊薄）。
   RTX 4060 8 GB 在 4096 环境时显存占用未见压力。这说明以 256–1024 环境先跑
   短训练是可行的，训练规模不是当前瓶颈。
3. **HOME 站姿比 T036 记录的更脆弱**。固定初态、移除 `push_robot`、50 Hz 控制、
   32 环境 × 3 种子、5 s 零动作保持：

   | 站姿 | 增益 | 跌倒 | 末根高 |
   |---|---|---|---|
   | 全零 | `kp=10`/`kd=0.4` | 7/96 | `0.1570–0.1710 m` |
   | 全零 | `kp=20`/`kd=0.8` | 2/96 | `0.1655–0.1669 m` |
   | 水平（±0.0873） | `kp=10`/`kd=0.4` | 5/96 | `0.1606–0.1686 m` |
   | 水平（±0.0873） | `kp=20`/`kd=0.8` | 1/96 | `0.1666–0.1688 m` |

   把根高下调到 `0.1695 m` 没有改善（4/96 与 1/96）。
4. **跌倒来源已定位到 `push_robot` 而不是 DR 组合**：同一保持测试保留全部默认 DR
   但去掉 `push_robot` 后，全零站姿 `worst_tilt` 从 70.30° 降到 19.25°、跌倒 0/8；
   水平站姿从 68.34° 降到 10.74°、跌倒 0/8。单独去掉 `base_com`、`encoder_bias`
   或 `foot_friction` 都不能消除跌倒。上游默认推扰为每 1–3 s、±0.5 m/s，
   对 3.3 kg 的本机明显过强。
5. **脚底平面只能用镜像内收拉平**：CPU 顶点拟合给出全零时两侧均为 `4.55°`、
   `+0.0873/−0.0873` 时两侧均为 `0.11°`；同号 `+0.0873/+0.0873` 则一侧 `0.11°`、
   另一侧 `7.65°`。这与 T036 的措辞一致，但 T036 没写出符号，落地时容易写错。
6. **控制周期与物理步长不能独立选**：`dt=0.005`、decimation 4（50 Hz）在默认 DR 下
   跌倒 3–4/4；`dt=0.002`、decimation 10（50 Hz）在同条件下 0–1/4。
   即上游"50 Hz"这个结论在本机成立的前提是物理步长为 2 ms，不能把 `dt=0.005` 直接搬来。

**为什么顺序是 T038 → T022 → T023，而不是直接写环境**

- 任务契约（动作子集、`scale`、观测项、控制周期）一旦冻结，观测维度与默认关节角就固定了。
  `duck_project` 的教训是：改 `default_joint_pos` 等于整体平移 `joint_pos_rel`，
  是"换任务"，会让热启动失配；`action scale` 被全局值覆盖曾直接导致坐下 100% 摔倒。
  所以必须先把 HOME 与增益定下来，再冻结契约。
- HOME 现在连"零动作保持"都做不到全种子无跌倒，而这个姿态会被写进观测基线
  （`joint_pos` 相对 HOME）、奖励（`pose`）与部署侧的 `DEFAULT_POSITION`。
  在它稳定之前写任务，等于把一个已知不稳的参考点固化进三层接口。
- 反过来，T022 不需要训练链路，也不该等 T029 的硬件协议，因此它可以紧跟 T038。

**下一步（按依赖排序）**

1. **T038**：按本页新增的验收条件确定 `hip_roll` 符号、`hip_pitch`/`knee`/`ankle`
   的站姿值与默认增益，并把"多种子零动作保持"写入断言。这是唯一阻塞 T022 的事项。
2. **T022**：冻结契约。建议首版取 10 维双腿动作（颈头 5 关节显式保持）、
   `scale` 按本机单独定（不沿用上游 1.0 也不再沿用全局 0.5）、
   `dt=0.002 s` + decimation 10（50 Hz，见实测第 6 条）、观测只用
   `imu_ang_vel`/`imu_upvector`/关节位置/关节速度/上一步动作/命令，
   不用 `imu_lin_vel` 与 `root_angmom`。
3. **T023**：在 `tasks/` 实现平地速度任务。可直接以 mjlab 1.6 的
   `make_velocity_env_cfg()` 为底，按上面第 1 条列的六处改动落地；
   推扰强度必须按本机质量重标（实测第 4 条），不能沿用上游 ±0.5 m/s。
4. **T024–T026**：本地网络、Storage、PPO、Runner 按既定方向实现，不引入 RSL-RL。
   上游 `AGENTS.md` 的奖励符号检查、零命令显式训练、课程阶段对齐三条应直接写进验收。
5. **T027–T028**：评估与导出。评估口径参考 `duck_project` 的世界系前扫与真实足端高度，
   但不要复用其机体系 excursion 与 `contact.found` 判离地。
6. **T029–T031** 仍等待本机协议、IMU 安装与控制板信息，本轮不调整其依赖。

**结论一句话**：三个参考项目里，`microduck_rl` 提供可直接套用的任务骨架与工程不变量，
`duck_project` 提供"哪些指标能信、哪些坑会重演"的负面清单，`microduck` 提供部署侧契约；
本仓库现在已经具备把它们接起来的前提，最该做的是先把 HOME/增益定死（T038），
再用 mjlab 1.6 通用速度模板改出本机任务（T022 → T023），而不是继续攒检查工具。

**本轮实际推进（2026-10-27）**：T038 → T022 → T023 → T024 → T025 → T026 已依次完成，
上面的"下一步"清单第 1–4 条已落地，详见下方各任务的完成记录。T027 起仍按原依赖等待。

### T022 固定首版任务控制与观测契约

状态：完成。依赖 T001、T002、T021；承接 T038 定下的 HOME 与增益。

目标：把"动作子集、缩放、观测项与顺序、控制频率、episode 长度"冻结成一份运行时校验的
契约，让任务环境、PPO、回放与导出都从同一处取维度，避免 T041 记录的
"改 `default_joint_pos` 或全局 `action_scale` 直接换掉任务"。

产物：`src/ht_microduck/tasks/common/contract.py` 与 `tools/check_task_contract.py`。

契约取值与依据：

| 项 | 取值 | 依据 |
|---|---|---|
| 物理步长 | `0.002 s` | T041 实测第 6 条：`dt=0.005` 在默认 DR 下 3–4/4 跌倒 |
| decimation | `10` | 与上一条共同给出 50 Hz，且 3532 有 0–3 步指令延迟 |
| 控制频率 | `50 Hz` | 与 `microduck_rl` 一致 |
| episode 长度 | `20.0 s` | 与 `microduck_rl` 一致 |
| 动作维度 | `10`（仅双腿） | 颈头 5 关节由 HOME 显式保持，见下 |
| 动作顺序 | `r_hip_yaw/roll/pitch/calf/ankle` → `l_…` | 与 `joint_pos` 观测同一顺序 |
| 动作缩放 | `0.25 rad` | 本机单独定；不沿用上游 `1.0` 或 mjlab 全局 `0.5` |
| actor 观测 | `39` 维 | 见下表 |
| critic 观测 | `42` 维 | actor 39 + `base_lin_vel(3)` |
| 保持关节 | `neck_pitch`、`head_pitch`、`head_yaw`、`head_roll`、`mouth` | 实机无对应策略输出 |

actor 观测顺序（`ACTOR_OBSERVATION_TERMS`）：`base_ang_vel`(3)、`projected_gravity`(3)、
`command`(3)、`joint_pos`(10)、`joint_vel`(10)、`actions`(10)。critic 在其后追加
`base_lin_vel`(3)。`base_lin_vel` 只出现在 critic，`validate_contract()` 在导入时强制这一点，
避免真值线速度漏进实机可部署的 actor。

与官方 `microduck_rl` 的**有意差异**（每条都在配置里就地注明理由）：

1. 动作 10 维而非 14 维：本机颈头是 FEETECH/3532 混合且不做视觉追踪，头部命令会让
   `joint_pos` 基线随命令漂移。上游 14 维里有 4 维是颈头。
2. 动作缩放 `0.25` 而非 `1.0`：整机 3.29 kg、腿长更短，`1.0` 的单步目标变化会直接掀翻机身。
3. 无 `height_scan` / 地形扫描：本机是平地，硬件也没有深度传感器。
4. 推扰收到 `±0.3 m/s` 水平分量，且无角速度分量：上游 `±0.5 m/s` 对 3.3 kg 机体过强
   （T041 实测第 4 条）。
5. 命令范围收窄为 `vx(-0.4,0.4)`、`vy(-0.3,0.3)`、`wz(-1.0,1.0)`：与上游一致，
   但删掉上游的 `head_pose`/`body_pose` 命令块（对应第 1 条）。

验收命令与结果：

```
uv run --no-sync python -B tools/check_task_contract.py --device cuda:0
```

```
timing: dt=0.002s decimation=10 control=50.0Hz
action: dim=10 scale=0.25 names ok
observations: actor=39 critic=42, order ok, no privileged actor terms
privileged: critic tail == root_link_lin_vel_b; actor has 6 terms and none is base_lin_vel
mapping: 10 per-joint pulses each command only their own joint
held joints: 5 servos/neck stayed within 46.5 mrad of HOME under random actions
reset: per-env reset isolated to the requested worlds
run: 150 control steps finite obs/reward
Contract check passed: device=cuda:0, envs=4, actor=39D, action=10D, control=50Hz.
```

检查过程中暴露并修正的三个真实问题（不是测试写法问题）：

- **动作映射的判据从"位置"改为"指令目标"**：`apply_actions()` 写入的
  `joint_pos_target` 与 `processed_actions` 之间还隔着编码器偏置
  （`target = processed - encoder_bias`），启动事件给的 `±0.015 rad` 偏置会让
  实测位置慢速收敛。比较 `processed_actions` 才能把"索引路由"和"PD 收敛"分开测。
- **编码器偏置必须进期望值**：修正后仍差 `0.0096 rad`，正是 `encoder_bias` 在该关节上的取值。
  现在期望值显式减去 `robot.data.encoder_bias`。
- **特权项用结构断言而不是数值扰动**：最初的写法"只改线速度、断言 actor 不变"不成立，
  因为重推一步物理会让 `base_ang_vel` 与 `projected_gravity` 一起变。改为直接断言
  critic 末 3 维等于 `root_link_lin_vel_b`，且 actor 的 term 列表里没有 `base_lin_vel`。

### T023 实现最小平地速度任务

状态：完成。依赖 T022；参考 pollen-robotics/microduck_rl 官方平地任务 `Mjlab-Velocity-Flat-MicroDuck`。

目标：在 `tasks/` 里做出可直接训练、也可被回放复用的平地速度环境。

产物：`src/ht_microduck/tasks/flat_velocity/`（`velocity_env_cfg.py`、`__init__.py`）、
`src/ht_microduck/tasks/common/mdp.py`、`tools/check_velocity_env.py`。

结构：`make_flat_velocity_env_cfg(num_envs, seed)` 组合 mjlab 1.6 的场景、命令、动作与观测，
奖励和终止按官方平地任务对齐，另加本机专用项。

奖励（11 项，权重取官方 `microduck_rl` 平地任务的数值）：

| 项 | 权重 | 说明 |
|---|---|---|
| `track_linear_velocity` | `2.0` | `std=sqrt(0.1)`，与官方一致 |
| `track_angular_velocity` | `2.0` | `std=sqrt(0.5)` |
| `upright` | `2.0` | `exp(-g_xy²/std²)`、`std=sqrt(0.05)` |
| `dof_pos_limits` | `-1.0` | |
| `action_rate_l2` | `-0.1` | 官方由课程从 `-0.1` 加到 `-1.0`；首版取起步值 |
| `joint_torques_l2` | `-2e-4` | 本机专用（3.29 kg，力矩量级小） |
| `joint_vel_l2` | `-2e-4` | 同上 |
| `air_time` | `3.0` | 阈值 `0.125/0.300 s`，`command_threshold=0.01` |
| `foot_clearance` | `-2.0` | 目标高 `0.02 m` |
| `foot_slip` | `-0.1` | |
| `self_collisions` | `-1.0` | 官方新增项；`primary`/`secondary` 两侧都是 `subtree=base_link` 的接触传感器（T044 修正） |

终止（4 项）：`time_out`（超时，`time_out=True`）、`fell_over`（`bad_orientation`，70°，
与 T038 的跌倒判据一致）、`illegal_contact`（机体触地，本机专用）、`nan_state`
（非有限状态；不加它会让一个炸掉的环境通过优势归一化污染整个 batch）。

事件：启动阶段必须有 `htdw3532_init` 与 `bam_init`（否则 3532 无法拿到逐世界的原生 PD 字段）；
另有 `reset_base`、`reset_robot_joints`、`push_robot`（每 3–6 s，`±0.3 m/s` 水平）、
`foot_friction`（`0.7–1.3`）、`encoder_bias`（`±0.015 rad`）、`base_com`（`±0.02 m`）。

验收命令与结果：

```
uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0
```

```
spaces: actor=39D critic=42D action=10D dt=0.02s
rewards: 11 terms -> track_linear_velocity, track_angular_velocity, upright, dof_pos_limits, action_rate_l2, joint_torques_l2, joint_vel_l2, air_time, foot_clearance, foot_slip, self_collisions
commands: dim=3 ranges vx=(-0.4, 0.4) vy=(-0.3, 0.3) wz=(-1.0, 1.0)
zero-action hold: 100 steps, 2/16 terminations (domain randomisation on; T038 measured 0/128 without it)
random run: 300 steps, mean reward -20.375, terminations 16, truncations 0
terminations: time_out is truncation, fell_over is terminal
fall detection: flipped worlds terminated = 16/16
Velocity env check passed: device=cuda:0, envs=16, steps=300, dt=0.02s.
```

**零动作保持 2/16 的定性**：这不是回归。T038 的 0/128 是在无 DR 的干净保持下测的；
本任务同时开编码器偏置 `±0.015 rad`、足底摩擦 `0.7–1.3`、逐环境 CoM 偏移，
多次重复（6×16）累计 1/96 终止，属偶发。检查据此改为"不超过 1/4 环境"而不是断言为 0，
并把实测值打印出来，避免把 DR 的正常代价误读成站姿失败。

**待办（不阻塞 T023 验收）**：`feet_clearance` 与 `foot_slip` 依赖足端 site 的世界系高度与速度，
当前实现读 `asset.data.site_pos_w`；导出与回放前需与 `duck_project` 的世界系前扫口径对齐一次。

### T024 实现本地网络与轨迹 Storage

状态：完成。依赖 T023。

目标：不引入 RSL-RL，自己实现 actor/critic、观测归一化、rollout 存储与 GAE。

产物：`src/ht_microduck/algorithms/networks.py`、`storage.py`、`tests/test_networks.py`。

- `Actor`/`Critic`：`(512,256,128)` ELU MLP，输入分别为 39/42 维，输出 10 维均值/标量。
  与官方同构，便于日后再对照超参。
- `RunningMeanStd`：`nn.Module`，带 `count` 缓冲，随 checkpoint 存取；用合并均值/方差的
  增量公式，使"两个半批"与"一整批"得到相同统计（有测试守住）。
- `GaussianDistribution`：状态无关的 `log_std`，`log_std` 截断到 `[-5,1]`。
- `RolloutStorage`：`(num_steps, num_envs, dim)` 固定容量，`compute_returns()` 跑 GAE-λ，
  并把 **真实终止** 与 **超时** 分开：真实终止不 bootstrap，超时保留价值估计。
  理由是不区分时，20 s 的超时会被当成"死亡"，价值函数学到的就是"时间到了等于失败"。

验收命令与结果：

```
uv run --no-sync python -B -m pytest -q tests/test_networks.py
```

`17 passed`。其中三条用手算值守住关键公式：`log_prob` 对标准对角高斯、
熵对 `0.5·log(2πeσ²)`、GAE 对两步行进的手推递推（含真实终止与超时两种分支）。

**实现中发现的真实 bug**：`GaussianDistribution` 的 `log_std` 是形状 `(10,)` 的参数，
与 `(N,10)` 的均值广播后，`torch.clamp` 保留的是参数自身形状，导致 `entropy()` 和
`log_prob()` 的 `sum(dim=-1)` 把 batch 维也压掉了（返回标量）。已改为在构造时
`expand_as(mean)`；这条正是被"形状断言 + 手算熵"测试抓到的，不是靠肉眼。

### T025 实现本地 PPO 更新

状态：完成。依赖 T024。

产物：`src/ht_microduck/algorithms/ppo.py`、`tests/test_ppo.py`。

- 裁剪代理目标 + 裁剪价值损失 + 熵奖励，梯度按 `max_grad_norm=1.0` 裁剪。
- 超参取官方值：`gamma=0.99`、`lam=0.95`、`clip=0.2`、`entropy_coef=0.01`、
  `5` epochs / `4` minibatches、`lr=1e-3`、`desired_kl=0.01` 的自适应步长。
- **小批量内优势归一化**：本任务的奖励是"一个大跟踪项 + 一堆小惩罚项"，原始优势跨度大；
  不归一化时首个 iteration 的 `approx_kl` 达 `2.99`、`clip_fraction` 达 `0.90`。
  归一化后首轮 `kl=1.02`、第三轮 `0.068`。同时对零方差 batch 加保护，避免除零后梯度全零。

验收命令与结果：

```
uv run --no-sync python -B -m pytest -q tests/test_ppo.py
```

`12 passed`。裁剪性质不是"看损失变小"，而是构造两批只差 `old_log_prob` 的数据，
直接断言 `ratio=1.1` 时损失约 `-1.1`、`ratio=50` 时仍约 `-1.2`（即停在信任域边界）。

**写测试时被自己纠正的一处判断**：最初想断言"ratio 很大时损失有界"，但标准 PPO 里
负优势对应的目标本来就没有下界；正确可测的命题是"正优势 + 超出信任域时饱和在
`-clip·A`"。测试改为显式关掉归一化、只用正优势，避免用一个错命题掩盖真实行为。

### T026 接通 Runner、训练入口与短跑基线

状态：完成。依赖 T023、T025。

产物：`src/ht_microduck/algorithms/runner.py`、`src/ht_microduck/cli/train.py`、
`pyproject.toml` 的 `[project.scripts]`、`tests/test_runner.py`。

- `OnPolicyRunner` 负责"采样 N 步 → 更新 GAE → PPO 更新"，并把归一化器统计的更新、
  指标记录、checkpoint 存取集中在一处。
- checkpoint 里同时存 `model`、`optimizer`、`iteration`、`learning_rate`、完整 `cfg`
  和**契约快照**；加载时若契约的观测维度不符直接报错，而不是把权重硬塞进改过的网络。
- 指标每个 iteration 追加一行 JSONL，崩溃也保留已有数据。

验收命令与结果：

```
uv run --no-sync duck-train --num-envs 16 --iterations 2 --seed 0 --device cpu
```

```
training: envs=16 iterations=2 seed=0 actor_obs=39 action=10 control=50Hz
iter     1 reward -0.063 ep_return -1.27 value_loss 0.1169 kl +0.39855 lr 6.67e-04
iter     2 reward -0.067 ep_return -1.81 value_loss 0.0544 kl +0.10128 lr 4.44e-04
saved final checkpoint and metrics to .artifacts/t023/entry
```

恢复验证（同一 checkpoint 续训，迭代号与优化器状态都接上）：

```
resumed from .../checkpoint_last.pt at iteration 4
iter     5 reward -0.069 ep_return -1.92 value_loss 0.0369 kl +0.02501 lr 1.32e-04
iter     6 reward -0.070 ep_return -2.14 value_loss 0.0662 kl +0.02236 lr 8.78e-05
```

`tests/test_runner.py` 用替身环境跑通 9 条测试（含种子可复现、契约不符时报错、
指标追加），`make check` 通过。

**未完成的一处**：本轮三次 GPU 短跑曾被并发进程占满显存（`Go2-Chase-Flat` 训练常驻
7.1/8.0 GiB），最终训练验证在 `--device cpu` 上完成；GPU 上只跑通了环境的
`check_task_contract.py` 与 `check_velocity_env.py`。GPU 训练证据留到 T027 一并补，
届时需要显存空闲窗口。

**明确不宣称的事**：以上短跑只证明"链路通、loss 有限、checkpoint 可读写可恢复"，
不证明学会行走。奖励均值在 `-0.07` 附近、episode 长度 20–30 步，都是初始策略的表现。
该 `-0.07` 的绝对值在 T044 修复自碰撞误计后不再适用（修复后同类短跑为 `-0.003` 到 `+0.007`），
但"没学会行走"这个结论不受影响。

#### 追加（2026-10-27）：训练可用性复核

用户问"现在能不能训练"。本轮只做只读复核加短跑，不新增任务、不改代码、不改超参。

环境限制先说明：本沙箱**没有 GPU 设备节点**（`/dev/nvidia*` 不存在，`nvidia-smi` 报
`couldn't communicate with the NVIDIA driver`），`torch 2.14.1+cu130` 报
`cuda_available=False`、`device_count=0`；宿主内核模块已加载但未透传到本进程。
因此默认的 `duck-train`（`--device cuda:0`）在环境构造阶段就失败：
`RuntimeError: No CUDA GPUs are available`。这不是代码缺陷，但说明**默认入口在本机跑不起来，
必须显式 `--device cpu`**。

CPU 路径实测（`UV_CACHE_DIR`、`TMPDIR`、`WARP_CACHE_PATH`、`TORCHINDUCTOR_CACHE_DIR`
均指向项目内 `.artifacts/`；`~/.cache/uv` 与 `~/.cache/warp` 在本机只读，首次没设会
`OSError: [Errno 30] Read-only file system`）：

```
uv run --no-sync duck-train --num-envs 64 --iterations 100 --seed 0 --device cpu \
  --save-interval 25 --out-dir .artifacts/status-check/learn
```

| 迭代 | mean_reward | episode_return | episode_length | done_fraction |
|---|---|---|---|---|
| 1 | `+0.0136` | `-0.12` | 24.0 | 0.0007 |
| 25 | `+0.0094` | `+0.38` | 54.2 | 0.0156 |
| 50 | `+0.0185` | `+0.84` | 60.6 | 0.0150 |
| 75 | `+0.0223` | `+2.21` | 104.3 | 0.0091 |
| 100 | `+0.0251` | `+3.63` | 156.3 | 0.0033 |

100 个迭代共 421 s（约 4.2 s/iter），`approx_kl` 从 `0.163` 收敛到 `0.013`，
学习率自适应降到 `1.32e-04`。恢复验证：`--resume .../checkpoint_100.pt --seed 7`
从 iteration 100 接着跑到 102，优化器与迭代号都接上。

另一条短跑（64 环境 4 迭代、256 环境 3 迭代）同样通过；`make check` 全绿
（179 项测试 + 8 subtests、Ruff、模型编译、锁文件），锁文件检查同样要项目内 `UV_CACHE_DIR`。

结论与边界：

1. **训练链路是通的**，CPU 上能采样、更新、写指标、存 checkpoint、恢复续训。
   从 episode 长度 24 → 156 步和 return 由负转正看，策略确实在学（不是随机基线）。
2. **还远没学会走**。episode 上限是 20 s / 1000 步（`EPISODE_LENGTH_S` × 50 Hz），
   156 步约 3.1 s，绝大多数 episode 仍以跌倒终止。
3. **CPU 不适合正式训练**。256 环境 12.13 s/iter（24 步）= 约 506 env-step/s；
   T036 探针在 RTX 4060 上的量级是 `1.3e4` env-step/s（不同探针，非同一路径的对照）。
   按此估算，CPU 上跑 1000–4000 迭代的正式训练要数天。
4. **GPU 证据仍缺**，与 T026 原文的欠账一致；`docs/development.md` 里"RTX 4060 8 GB"
   的运行数据本轮无法复现或反驳，需要用户在有 GPU 设备节点（可见 `/dev/nvidia*`、
   `nvidia-smi` 正常）的机器上跑 `duck-train` 默认参数补测。

本轮临时产物（`.artifacts/status-check/`、`.artifacts/checks/run-DAze415b/`、
`.artifacts/checks/run-qzGsgrXt/`）在复核结束后删除，未保留训练出的策略。

#### 追加（2026-10-27 晚）：GPU 恢复可见，2048 环境需下调接触缓冲区

上一条说"无 GPU 设备节点"只在当时成立。用户随后放开了设备节点，现在
`/dev/nvidia0`、`/dev/nvidiactl`、`/dev/nvidia-uvm` 都可见，`nvidia-smi` 正常，
`torch.cuda.is_available()` 为 `True`。**GPU 训练现在可以实际运行。**

但 `--num-envs 2048` 用任务默认的 `nconmax=128`、`njmax=512` 会失败：

```
RuntimeError: Graph creation error: Warp CUDA error 2: out of memory
  (in function wp_cuda_graph_create_exec)
```

失败点不是普通的张量分配，而是 Warp 在捕获 CUDA graph 时分配执行实例。默认缓冲把
2048 世界的图捕获推过了 8 GB。实测各规模占用（`num_steps_per_env=24`，含 mjlab/Warp
常驻部分约 3.6 GB，其中外部 `Go2-SuperMimic-Flat` 进程占 3.1 GB）：

| 环境数 | 缓冲区 | 结果 | 占用 |
|---|---|---|---|
| 1024 | 128 / 512 | 通过，graph 生效 | — |
| 1536 | 128 / 512 | 通过 | 6987 MiB |
| 2048 | 128 / 512 | **OOM（graph 捕获）** | — |
| 2048 | 64 / 512 | 通过 | 6166 MiB |
| 2048 | 96 / 384 | 通过 | 6985 MiB |
| 2048 | 64 / 256 | 通过 | 6298 MiB |

因为缓冲区是每世界上限、不是实际用量，先测了这台机器人真实的接触/约束峰值
（512 环境、随机大幅动作 500 步、故意跌倒并自碰撞）：

```
max_contacts_per_world = 13
max_nefc              = 55
```

即 `nconmax=64`、`njmax=256` 仍是实测峰值的 4.9 倍 / 4.7 倍余量。为保留默认行为、
不把临时实验值写死进任务配置，`duck-train` 新增两个可选覆盖参数
`--nconmax`、`--njmax`；不传时仍用任务默认的 `128 / 512`。

**追加（2026-10-28）：改为任务默认 `64 / 256`。** 用户要求启动时不再每次追加参数，
`flat_velocity_env_cfg.py` 的 `SimulationCfg` 默认值由 `128 / 512` 改为 `64 / 256`，
`--env.sim.nconmax` / `--env.sim.njmax` 仍可覆盖。这样原命令
`duck-train HtDuck-Flat-Velocity --env.scene.num-envs 4096` 无需额外参数即可启动
（此前 4096 用默认值必现 graph capture OOM）。验证：4096 环境、1 迭代、无额外参数
退出码 0，2.11 s/iter；`--env.sim.nconmax 96 --env.sim.njmax 384` 覆盖仍生效；
`make check` 通过（当时 180 项测试 + 8 subtests）。

**吞吐很差，原因是外部争抢而非代码**。2048 环境实测 5.93 s/iter（12 次迭代，
5.08–7.32 s），约 8290 env-step/s；同样条件下 1024 环境是 4.5 s/iter。
单步拆解开销（2048 环境、24 次采样）：

```
env.step 本身            94.1 ms/步
env.step + nonzero.tolist 95.3 ms/步
torch.nonzero(...).tolist() 0.5 ms/步
```

即 95% 时间在 `env.step`，`runner.py` 里每步的 host 同步只占 0.5 ms，不是瓶颈。
`nvidia-smi` 显示另一个 `Go2-SuperMimic-Flat`（pid 499718，占 3.1 GB、利用率约 90%）
同时在跑，这是耗时随规模不降反升的原因。

按 5.93 s/iter 估算，20000 迭代约 **33 小时**（1.4 天）；若外部进程退出应明显加快。
checkpoint 每个约 4.5 MB，1000 轮存一次共 20 个，约 90 MB。

本轮临时产物（`.artifacts/gpu-probe/`、`.artifacts/checks/run-8e9FD43X/`、
`.artifacts/checks/run-jSndYcPu/`）在复核结束后删除。`make check` 通过
（179 项测试 + 8 subtests）；改动仅新增两个 CLI 参数。

### T044 修复自碰撞传感器误计地面接触

状态：完成。依赖 T023；用户报告"脚与地面的接触也算成自碰撞"。

目标：让 `self_collisions` 只统计机器人自身两处之间的接触，不再把站立时
的足底-地面接触算进去。

问题定位：`_self_collision_sensor()` 原本是 `primary=subtree:base_link`、
`secondary=None`。`secondary=None` 在 mjlab 里表示**不加参考过滤**，因此该传感器会
命中机器人与任意物体的接触。实测（`num_envs=2`，零动作）：

| 状态 | `found`（旧） | `found`（修复后） |
|---|---|---|
| HOME 站立（贴地） | `8.0` | `0.0` |
| 整体抬高 1 m | `0.0` | `0.0` |
| 腿折到极限（真实自碰撞） | `2.0` | `2.0` |

按 `reward_manager._step_reward` 拆开单步期望值（32 环境、噪声 0.3、100 步）：

```
track_linear_velocity   +0.01782
track_angular_velocity  +0.01530
upright                 +0.02087
其余惩罚项合计           -0.00526
self_collisions         -0.10885   ← 旧值，一个人顶掉全部正奖励
```

即站立本身每步被扣 `-0.109`，而正奖励合计只有约 `+0.054`，`self_collisions`
一项就主导了任务奖励，且方向与"学会走路"无关。

修复：`secondary` 改为 `ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT)`，
与 mjlab 参考任务 `tasks/velocity/config/go1/env_cfgs.py` 的 `subtree` 对 `subtree`
写法一致。改动前 `docs/development.md` 已写"用 `subtree=base_link` 的接触传感器"，
与实现不符，本次一并纠正。

A/B 短跑（32 环境、100 迭代、CPU、种子 0、同配置）：

| | iter 1 | iter 100 | episode 长度 |
|---|---|---|---|
| 修复前 | `-0.0611` | `-0.0561`（ep_return `-1.06`） | 22.0 → 18.8 |
| 修复后 | `-0.0027` | `+0.0074`（ep_return `+0.23`） | 22.0 → 29.6 |

修复后奖励转正、episode 变长；修复前奖励几乎不动且 episode 变短。这仍然只说明
奖励信号恢复正常，**不证明学会行走**。

验证：

```
uv run --no-sync python -B tools/check_velocity_env.py --device cpu
uv run --no-sync python -B -m pytest -q tests/test_velocity_env_cfg.py
```

```
zero-action hold: 100 steps, 2/16 terminations (domain randomisation on; T038 measured 0/128 without it)
self-collision while standing: raw term max 0.000 (expected 0)
random run: 300 steps, mean reward 12.982, terminations 16, truncations 0
Velocity env check passed: device=cpu, envs=16, steps=300, dt=0.02s.
```

`tests/test_velocity_env_cfg.py` 3 条通过；把 `secondary` 改回 `None` 后
有 2 条失败，说明这组测试确实能拦住该回归。`check_velocity_env.py` 新增
"站立时 `self_collisions` 必须为 0"的断言，随机跑 300 步的奖励也从 `-19.892`
变为 `+12.982`。

本节只改 `self_collisions` 口径；`feet_air_time` 在落地步为负、`feet_clearance`
读不到 `default_site_pos_w`、`BODY_MASS_RANGE` 未接入，这三项作为待办另行处理。

### T045 修复独立预览的积分器与初态

用户报告：直接运行 `python src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py`，
机器人倒地后一直抽动（而不是倒地不动），并且看不到 `init_state`。两个现象是**两个独立缺陷**，
都用 A/B 定位到具体原因，不是观感问题。

范围：只改预览入口 `__main__` 块和 `tools/check_robot.py --viewer` 的重复实现；不动训练
环境、执行器参数、源 XML 和默认增益。

**缺陷一：预览用的积分器和训练不一致。** 旧预览 `scene.compile()` 后直接交给
`viewer.launch`，拿到的是 XML 默认的显式 Euler（`mjINT_EULER`，实测编译结果
`model.opt.integrator == 0`）。训练侧 `velocity_env_cfg.py` 经 `MujocoCfg` 改用
`implicitfast`（`== 3`）。无刷关节当时 armature 为 **0**（本轮才补上 0.002，见下文
"站姿抖动"一节；此处 `0.0018` 是早期误记，实测 12 个无刷关节当时全为 0），`kd 0.4`、
`dt 0.002 s`，显式阻尼在该组合下发散：

| 积分器 | 末态根高 | 收敛后 max\|qvel\| |
|---|---|---|
| euler（旧预览） | 0.0954 m | 32.0 rad/s |
| implicitfast（训练） | 0.1655 m | 0.20 rad/s |

即"一直抽"就是显式阻尼的数值不稳定，数值上每步都在抖。同一组对照还排除了"求解器迭代
不够"这一猜测：`iterations/ls_iterations` 调成训练的 10/20 对 euler 完全没有改善
（两次都是 24.35 rad/s），换积分器是唯一有效的变量。把 `kd` 单独设为 0 时抖动降到
5.96 rad/s、只留阻尼项时为 23.75 rad/s，确认主因是速度阻尼项。

**缺陷二：`init_state` 从未生效。** mjlab 把初态写成 `init_state` 关键帧（`nkey=1`），
但要显式 `mj_resetDataKeyframe` 才会用上。旧代码只传 model 让 `viewer.launch` 自己建
`MjData`，起点是 XML 默认位姿（根高 0.171 m、全部关节为 0），关键帧里的 HOME 蹲姿
（根高 0.1534 m）根本没出现——这正是用户"看不到 init_state"的直接原因。

顺带修正一个会让预览完全无法站立的问题：本模型的 `ctrl` 是仿射 PD 输入
（`ctrl = kp·q_target`），不是力矩。若把 `ctrl` 置 0，等于命令所有腿关节回零，机器人只会
塌下去。新代码用每个执行器编译后的 `biasprm[1]` 反推 `kp`，再写 `kp·HOME_JOINT_POS`。
HD1910 编译成纯力矩电机、无位置偏置，`kp` 读作 0，头部因此最多下垂 0.1 rad（预览不建模
BAM），不影响腿部站立。

实现：常量模块新增 `make_preview()`，负责编译实体、套用 `MujocoCfg`、复位到
`init_state`、写入 HOME 保持命令；`__main__` 与 `tools/check_robot.py --viewer` 都改用它，
消掉了原先那份会静默预览不同物理的重复实现。

**按 `legged_wbc_mjlab` 参考重写入口。** 用户之后要求参考
`/home/sunteng/projects/legged_wbc_mjlab/src/assets` 与官方 microduck 的写法。该目录下
`go2/go2_constants.py`、`ri_4438/ri_4438_constants.py`、`ri_5036/`、`go2_piper/` 的入口统一是：

```python
robot = Entity(get_*_robot_cfg())
viewer.launch(robot.spec.compile())
```

它的优点是不经过 `Scene`，因此不分配 torch 张量、不需要 `device`，预览在 GPU 被训练占满时
照样能开。本轮把 `make_preview()` 改成同样的结构（`Entity` 直连 + 自己的 `_add_preview_ground`），
去掉了 `Scene` 依赖，函数签名从 `make_preview(device)` 变成 `make_preview()`。

但参考写法**不能照抄**，实测对比（2500 步）：

| 写法 | 根高轨迹 | 末态 max\|qvel\| |
|---|---|---|
| 参考式单行（无地面、无 `MujocoCfg`、不应用关键帧） | 0.171 → -4.76 → -19.50 → -44.05 → -78.41 | 49.06 rad/s |
| 本轮 `make_preview()` | 0.1534 → 0.1501 → 0.1498 → 0.1498 → 0.1497 | 0.55 rad/s |

参考式单行在本机连地面都没有（`robot.spec` 只有机器人本体），直接自由落体到 `z=-78`。所以
本轮只借用它的**结构**，保留已验证的两处差别：套用 `MujocoCfg`、显式 `mj_resetDataKeyframe`。
地面、棋盘纹理和定向光按 mjlab `TerrainEntityCfg(terrain_type="plane")` 的默认值补在预览 spec 上
（`friction=(1.0, 0.005, 0.0001)`、`texrepeat=(4,4)`、`sun` 0.0/0.0/1.5 定向），机器人 XML 仍然
不含地面和灯光（T016/T039），预览不会出现两个地面。

关键帧里存的 `ctrl` 是**关节目标角**（如 `0.85`），不是运行时命令（`kp·q_target = 8.5`）。
这一点在参考写法里看不出来，因为参考项目用的是 plain `motor`。本轮据此把 `ctrl` 的推导
改成 `-biasprm[:, 1] * key.ctrl`，和原先按名字查 `HOME_JOINT_POS` 的结果逐元素一致
（实测 `allclose` 为真），但少了一层名字匹配、也不会在两处定义之间漂移。

验收：

```
make check
  → 178 passed, 8 subtests passed（新增 3 条，原 175）

uv run --no-sync python -B src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py
  → GLX: Failed to create context（本沙箱无 /dev/nvidia*，仅图形受限，CUDA 报错已消失）
```

无头 A/B（2500 步，同一场景）：

| | 根高轨迹 | 末态 max\|qvel\| |
|---|---|---|
| 旧预览 | 0.171 → 0.1033 → 0.0952 → 0.0964 → 0.0982 | 29.57 rad/s |
| 新预览 | 0.1534 → 0.1501 → 0.1498 → 0.1498 → 0.1497 | 0.55 rad/s |

新增 3 条测试（`tests/test_robot_entity.py`）：`test_preview_starts_from_the_init_state_keyframe`
断言 `qpos` 等于关键帧、根高等于 `HOME_FRAME.pos[2]`、关节不全为 0、且 `ctrl == kp·key.ctrl`
（同时仍逐项对照 `kp·HOME_JOINT_POS`）；`test_preview_uses_the_training_integrator_and_holds_the_stance`
断言积分器与 `MujocoCfg` 一致且不是 euler，并跑 1000 步后要求 `max|qvel| < 2.0`、根高 `> 0.1`；
`test_preview_adds_one_ground_and_light_without_touching_the_robot_xml` 断言预览只有一个
`terrain` 平面、摩擦 `1.0`、1 个灯光/纹理/材质，且源 XML 仍无灯光与平面。把两处修复同时
回退验证：前 2 条都失败，其余照常通过，说明这组测试能拦住该回归。

未解决/未验证：本沙箱没有 GPU 设备节点，`nvidia-smi` 显示 RTX 4060 被外部
`Go2-Chase-Flat` 训练占用，且 GLX 无法创建上下文，因此**无法实际打开窗口验证 GUI 观感**，
只能验证其编译、初态、积分器、地面装配与无头物理行为。需要用户在有图形和空闲 GPU 的机器上
跑一次确认。参考目录 `legged_wbc_mjlab` 与官方 microduck 仓库本轮**只读**，未修改，也不受
GitHub 网络受限影响（本地已存在该目录）。

#### 追加：站姿抖动来自缺失的转子惯量（armature）

用户反馈“会抖动”。无头定位后确认：站姿高度稳定（`root z` 均值 0.14975、峰峰值 0.00012 m），
但关节持续高频嗡嗡（末 5 s 平均 `|qvel|`：`l_ankle 0.2665`、`l_hip_pitch 0.2241`、
`l_calf 0.1970`），FFT 主频 **6.0 Hz**，ankle `qvel` 每 100 步换向约 7 次。

排除项（同一场景 2500 步，均值 `|qvel|`）：求解器迭代 `10/20`、`50/25`、`100/50`、`200/100`
结果**完全相同**（0.0961）；`implicit` 0.0959、`rk4` 反而 7.6299；接触稳定不抖（`ncon`
恒为 6，左右足 `fz` 均值 16.704/15.590 N，总重 32.321 N）；**去掉重力抖动直接归零**；
`dt` 减半抖动也减半（0.1055→0.0626→0.0341→0.0173）——这是显式/隐式 PD 环路“欠惯性”的特征，
不是求解器或接触问题。逐执行器审计发现 12 个无刷关节的 `dof_armature` **全为 0**
（只有 3 个 HD1910 舵机有 `0.001827`，来自 BAM 厂家辨识值），即关节几乎没有惯性。

修复：`BRUSHLESS_ACTUATOR_CFG` 显式传 `armature=BRUSHLESS_ARMATURE`，取值由用户提供为
`0.0069753532276 kg·m²`（关节输出侧）。armature 扫描（同一站姿、同一场景）：

| armature | 均值 \|qvel\| | root z 峰峰值 | 渲染帧间像素差 |
|---|---|---|---|
| 无（0） | 0.10518 | 0.000115 | 1.706 |
| 0.001 | 0.0363 | — | — |
| 0.002（早期占位） | 0.02494 | 0.000124 | 0.285 |
| **0.0069753532276（采用）** | **0.00366** | **0.000006** | **0.071** |
| 0.01 | 0.00264 | 0.000004 | 0.068 |

渲染帧间像素差用 EGL 离屏渲染客观量化“肉眼可见的抖”（本沙箱无法查看渲染图）：无 armature
1.706、占位 0.002 时 0.285、真实值 0.0069753532276 时 **0.071**，即真实值把可见抖动降
**24 倍**（占位值只有 6 倍）。训练环境同样受益：零动作 200 步平均 `|qvel|` 从 **0.193 降到
0.00649**（30 倍），`root z` 0.1503 不变。

奖励用**同一协议**（8 环境、种子 0、150 步零动作）对照，避免换协议造成的假象：

| armature | 全程 150 步均值 | 后 100 步均值 |
|---|---|---|
| 0（无） | 0.0983 | 0.1001 |
| 0.002（占位） | 0.1034 | 0.1033 |
| **0.0069753532276** | **0.1034** | **0.1033** |

即真实值与占位值奖励相同、比无 armature 略好，**没有变差**。（期间出现过一次
0.0811，是本轮把环境数从 8 改成 4、并只统计后 50 步造成的协议差异，非真实退化，已用上表
同协议复测排除。）

**取值来源：** 用户于 2026-10-27 提供，为 HTDW-3532 的关节侧 armature。在此之前本轮已查证
全部可得公开来源均无该参数——用户提供的 `HTDW-3532-02-DNE_user_datasheet.png` 只有转速–力矩
曲线；本地 `params/README.md` 明确“不推定转子惯量”；高擎官网产品页 15 个型号**已不含 3532**
（已下架），官方手册 `book.hightorque.cn/Module20260917`（15 个型号）**完全没有惯量字段**；
官方“模型”下载 `HTDW-3532-02-DNE.zip` 只有一个 SolidWorks `STEP` 几何体（无质量属性）；
`store.hightorque.cn` 该型号页已 404；参考项目 `legged_wbc_mjlab` 对 RI-5036 同样写
“没有推断…转子惯量”（其 `docs/development.md:2314`）。因此该值此前只能用占位值
`0.002`（沿用官方 duck MJCF 对每个关节的统一硬编码，见 `src/htdk/model.py:64`），本轮已用
用户提供的真实值替换。

**合理性核对（仅佐证，不是来源）：** 按 32:1 折算回转子侧
`0.0069753532276 / 32² = 6.81e-6 kg·m² = 68.1 g·cm²`，与该尺寸电机约 60 g·cm² 的钢质转子
量级一致；而占位值 `0.002` 只相当于 19.5 g·cm²。数值带 11 位有效数字，应按用户给定保留，
不做多余修约。舵机 `0.001827` 不同，它是飞特 BAM 厂家辨识值
（`bam/params/feetech_hd1910_7_4V/m6.json`，固定到 commit、SHA256 记录在
`actuators/HD_1910_C001/params/README.md`），属厂家模型参数而非本机实测；用户明确表示
舵机的值不清楚，本轮不臆测替换。

另：头部 `head_yaw` 站姿仍缓慢漂移 5.4°、`mouth` 7.4°（`ptp` 3.96°），原因是预览里 3 个
舵机的 BAM 模型不参与编译（`biastype=NONE`、位置增益为 0），属无驱动自由下垂，不是高频抖动。
实测把头部按 `kp=7.345/kd=0.1074` 固定后帧间像素差仅 0.285→0.277（占位值下的测试），
对观感无影响，本轮不为预览引入 BAM 建模。

验收：`make check` → **179 passed**（新增
`test_brushless_joints_carry_reflected_rotor_inertia_and_stop_buzzing`，断言 12 个无刷关节
`dof_armature == BRUSHLESS_ARMATURE`、站姿 3 s 平均 `|qvel| < 0.06`、根高 `> 0.14`）；
`tests/test_robot_actuators.py` 里原先断言 `armature is None` / `dof_armature == 0.0` 的两处
改为断言 `BRUSHLESS_ARMATURE`（源 XML 仍断言 `armature == 0.0`，因为改动只经 cfg，不动 XML）。
把 `armature=BRUSHLESS_ARMATURE` 摘掉后这 4 条测试全部失败，恢复后通过，确认能拦住回归。

### T046 对齐官方目录设计与训练/回放入口

用户要求按官方 `pollen-robotics/microduck_rl` 重设目录与日志输出，把 `train`/`play` 贴合
官方口径，且**训练必须使用本项目根目录的 `rsl_rl/`**；无用/可合并文件本轮只报告不修改。

设计：[repo_layout_alignment.md](../design/repo_layout_alignment.md)。依据来自上游
`.artifacts/research/upstream/`（commit `b02fdee`）与本地 mjlab 1.6.0 源码。

**目录重构。** 原 `tasks/flat_velocity/velocity_env_cfg.py` 是单文件任务却占一个包目录，
`tasks/common/` 又把契约和 MDP 藏在第二层。改为官方平铺：

| 旧路径 | 新路径 |
|---|---|
| `tasks/common/contract.py` | `tasks/contract.py` |
| `tasks/common/mdp.py` | `tasks/mdp.py` |
| `tasks/flat_velocity/velocity_env_cfg.py` | `tasks/flat_velocity_env_cfg.py` |

`tasks/__init__.py` 从一行 docstring 改为注册表，按官方写法调用一次
`register_mjlab_task(task_id="HtDuck-Flat-Velocity", env_cfg=..., play_env_cfg=..., rl_cfg=...)`。
新增 `FlatVelocityRlCfg`（`RslRlOnPolicyRunnerCfg`）：网络 `(512,256,128)`、`elu`、
`obs_normalization=True`、高斯 `init_std=1.0`，PPO `clip 0.2`、`entropy 0.01`、`lr 1e-3`、
`adaptive`、`gamma 0.99`、`lam 0.95`、`desired_kl 0.01`，与官方 microduck 一致；`logger`
用 `tensorboard`（本机无 wandb）。

**注册自动发现。** `pyproject.toml` 新增 `[project.entry-points."mjlab.tasks"]
ht_microduck = "ht_microduck.tasks"`。`mjlab/__init__.py` 在 import 时加载该组，所以
`list_tasks()`/`list-envs` 无需显式 import 即可看到本机任务。实测：

```
$ .venv/bin/list-envs
| 1 | HtDuck-Flat-Velocity |
```

**入口改为官方薄封装。** `duck-train`/`duck-play` 从 `cli.train`/`cli.play`（自写 argparse）
改为 `train_cli.py`/`play_cli.py`，各自只做 import 再调 `mjlab.scripts.train.main()` /
`mjlab.scripts.play.main()`。命令行因此变成官方两段式：位置参数是任务 id，
`--env.*`/`--agent.*` 覆盖配置，`--log-root` 默认 `logs/rsl_rl`。旧参数
`--num-envs`/`--iterations`/`--out-dir` 不再支持（有意的破坏性变更，README 已同步）。

**训练确实走项目 `rsl_rl/`。** 初版实现把 `sys.path` 修正放在 `train_cli.py`，实测
`rsl_rl.__file__` 仍指向 wheel——因为 `ht_microduck.tasks` 在 entry point 加载时已经先
`import mjlab`，而 `mjlab.scripts.train` 内部的 `import rsl_rl` 早于 shim 生效。改为在
`src/ht_microduck/__init__.py` 里先修正 `sys.path` 再 `import mjlab`，两个入口都只
`import ht_microduck`。实测：

```
rsl_rl   : <repo>/rsl_rl/__init__.py
runners  : .venv/.../rsl_rl/runners/__init__.py     # wheel 补齐，符合 _fallback 设计
PPO      : <repo>/rsl_rl/algorithms/ppo.py
MLPModel : <repo>/rsl_rl/models/mlp_model.py
```

**同时修掉一个真实缺陷：循环导入。** 加上 entry point 后，`import ht_microduck.actuators`
会先触发 `import mjlab` → loader 回头 import `ht_microduck.tasks` → 又要
`ht_microduck.actuators.bam_init`，而 `actuators/__init__.py` 正执行到一半，报
`cannot import name 'bam_init' ... (most likely due to a circular import)`。修复同一处：
在包 `__init__` 里先把 `mjlab` 导入完成，任何子包都还没开始，顺序就确定了。

**验收（本机 CPU，GPU 驱动当前不可用）。**

| 检查 | 命令 | 结果 |
|---|---|---|
| 基础检查 | `make check` | 通过：193 passed，8 subtests |
| 注册可见 | `list-envs` | `HtDuck-Flat-Velocity` 在列 |
| 训练短跑 | `duck-train HtDuck-Flat-Velocity --env.scene.num-envs 2 --agent.max-iterations 2 --agent.save-interval 1 --agent.seed 7 --gpu-ids None` | 输出官方 80 列面板（`Learning iteration 0/2`、`Total steps: 16`、`Steps per second: 30`、`Collection time: 0.455s`、`Mean value/surrogate/entropy loss`、`Mean action std: 1.00`、`ETA`），退出码 0 |
| 日志布局 | 同上产物 | `flat_velocity/<时间戳>_velocity/{params/env.yaml,params/agent.yaml,git/HT_microduck_lab.diff,model_0.pt,model_1.pt,events.out.tfevents.*}`，与官方一致 |
| play 配置差异 | `load_env_cfg(id)` vs `load_env_cfg(id, play=True)` | push 间隔 `(3.0,6.0)` → `(0.5,1.0)`；奖励/终止集合相同；两份 cfg 已 deepcopy 隔离 |
| 回放加载 | 直接跑官方 play 路径加载 `model_1.pt` | `PLAY PROBE OK`，动作 `(2,10)` float32，actor 39 维入 / 10 维出，critic 42 维，契约未变 |
| viser 查看器 | `duck-play ... --viewer viser` | 服务启动后长期驻留（设计如此），本轮按有界探针替代，未做画面验收 |

**无用文件与可合并清单（T046 只报告，未修改）。**

> 下表是 T046 当时的判断，**已由 T047 执行**：`algorithms/`、`cli/`、4 个测试已删除；
> `rsl_rl/` 已补成完整副本并删除 `_fallback.py`（因此「17 个文件与 wheel 相同、可精简」
> 已反转为「30 个文件、不可删除、不可本地修改」）；`rsl_rl/README.md` 已重写，不再涉及
> `VENDOR_NOTES.md`。保留本表作为决策依据记录，现状见
> [T047](development_tasks.md#t047-包目录与官方完全对齐并收敛到唯一训练算法)。

| 对象 | 判断 | 依据 |
|---|---|---|
| `src/ht_microduck/algorithms/`（6 文件） | 已被 RSL-RL 取代 | `runner.py` 复刻 `runners/on_policy_runner.py` 的循环/存取；`logger.py` 复刻 `utils/logger.py` 面板；`ppo.py`/`storage.py`/`networks.py` 复刻同名实现。训练已不经它，仅 `tests/test_{ppo,networks,runner,logger_and_play}.py` 和 `cli/` 在用 |
| `src/ht_microduck/cli/train.py`、`cli/play.py` | 同上，且与官方入口重复 | `play.py` 重新实现了 `PlayConfig`、`get_checkpoint_path`、`CheckpointManager`、`VideoRecorder`；入口已改指向 `*_cli.py` |
| `rsl_rl/` 镜像 | **不能删**，但可精简 | 除 `_fallback.py` 外 17 个文件与 wheel 逐字节相同；`LICENSE`/`README.md` 为镜像自带。保留理由：本轮约束要求训练走此路径 |
| `rsl_rl/README.md` 的 `VENDOR_NOTES.md` 引用 | 死链 | 两个 `VENDOR_NOTES.md`（根目录与 `rsl_rl/`）均不存在 |
| `src/ht_microduck/rl/` | 空目录 | 无任何文件，本轮已删除 |
| `MUJOCO_LOG.TXT` | 运行产物 | 仓库根目录误留，应在 `.gitignore` 中排除 |

合并顺序建议：先让 `tests/test_{ppo,networks,runner,logger_and_play}` 迁到 RSL-RL 等价断言，
再删 `algorithms/`，最后删 `cli/`；已有的 `runs/` 实验产物不动。

**遗留。** GPU 驱动当前不可用（`nvidia-smi` 通信失败、`torch.cuda.is_available()==False`），
所以多环境与 `cuda:0` 训练未在本轮复测；viser 查看器只验证了能起服务，未做画面验收。
本轮未执行 Git 暂存、提交或推送。

### T047 包目录与官方完全对齐并收敛到唯一训练算法

用户要求"文件架构像参考项目一样"，并明确"训练的 RL 算法使用本仓库根目录的 `rsl_rl/`"。
T046 只对齐了 `tasks/`，本轮收掉它留下的两件事：包名与模型目录仍和官方不同形，
以及自实现训练栈与 RSL-RL 两套算法并存。

设计：[repo_structure_official_parity.md](../design/repo_structure_official_parity.md)。
依据来自官方 tarball `pollen-robotics/microduck_rl@1e79c29`（本轮解包于
`.artifacts/upstream_microduck_rl/`，任务结束后删除）与本地 mjlab 1.6.0 源码。

**目录改为官方三子包。** 官方 `src/mjlab_microduck/` 只有 `robot/`、`actuator/`、`tasks/`
三个子包，机器人资源放在 `robot/microduck/` 数据目录（无 `__init__.py`），常量单独一个
`robot/microduck_constants.py`，调用方直接 import 常量模块而不走包再导出。本机按同一形状改：

| 旧路径 | 新路径 |
|---|---|
| `robots/` | `robot/` |
| `robots/ht_microduck/ht_microduck_constants.py` | `robot/ht_microduck_constants.py` |
| `robots/ht_microduck/xmls/HT-DK_URDF.xml` | `robot/ht_microduck/HT-DK_URDF.xml` |
| `robots/ht_microduck/xmls/assets/*.STL` | `robot/ht_microduck/assets/*.STL` |
| `robots/ht_microduck/__init__.py` | 删除（官方资源目录不包化） |
| `actuators/` | `actuator/` |

`_ROBOT_DIR` 随之从 `parent/"xmls"` 改为 `parent/"ht_microduck"`；XML 内的
`meshdir="assets/"` 未动，XML 与 `assets/` 仍是同级，模型编译结果不变。
`robot/__init__.py` 不再再导出常量（官方为空文件），保留一段说明文档字符串。

**删除自实现训练栈。** `src/ht_microduck/algorithms/`（6 文件，PPO、网络、Storage、Runner、
Logger）与 `src/ht_microduck/cli/`（3 文件）是训练改用 RSL-RL 之前的实现，入口早已不经它们。
官方根本没有这两层：PPO 与网络来自 `rsl-rl-lib`，上游自己写的算法文件只有
`tasks/symmetry.py`。所以删除是与官方对齐，不是能力回退——`import ht_microduck.algorithms`
现在会 `ImportError`，这是有意的，避免再出现两套算法。

**`rsl_rl/` 从"部分镜像"补成完整副本。** 原来缺 `runners/`、`utils/logger.py`、
`algorithms/distillation.py`，靠 `_fallback.py` 把 8 个子包的 `__path__` 扩展到 wheel。
也就是说训练循环 `OnPolicyRunner` 和日志面板 `Logger` 实际来自 `.venv`，与"训练使用本项目
`rsl_rl/`"不符。本轮从 wheel 逐字节补齐这 5 个文件、把 8 个 `__init__.py` 恢复为上游原文、
删除 `_fallback.py`。现在 `diff -rq` 与 wheel 无差异（仅 `LICENSE`/`README.md`/`__pycache__`）。

实测解析结果（训练入口与直接 import 两条路径一致）：

```
rsl_rl        : <repo>/rsl_rl/__init__.py
__path__      : ['<repo>/rsl_rl']                    # 单元素，无 site-packages 回落
OnPolicyRunner: <repo>/rsl_rl/runners/on_policy_runner.py
Logger        : <repo>/rsl_rl/utils/logger.py
PPO           : <repo>/rsl_rl/algorithms/ppo.py
MLPModel      : <repo>/rsl_rl/models/mlp_model.py
```

**测试覆盖的迁移边界（重要）。** 被删的 4 个测试文件（`test_ppo`、`test_networks`、
`test_runner`、`test_logger_and_play`）断言的是已删除的实现，共 52 条。新测试不追求逐条等价：

| 新文件 | 覆盖 | 做法 |
|---|---|---|
| `tests/test_rsl_rl_vendoring.py` | 训练代码来源与完整性 | `rsl_rl.__path__` 单元素；`OnPolicyRunner`/`Logger`/`PPO`/`MLPModel` 均在仓库内；`_fallback.py` 不存在且不可导入；仓库副本是 wheel 的**超集**（用 `importlib.metadata` 定位 wheel 后做模块名集合差）；两个子进程用例分别验证 `-P` 下的路径顺序保证与"先 import `rsl_rl` 仍得 wheel"这条边界 |
| `tests/test_training_stack.py` | PPO 数值语义 + 端到端 | 用 stand-in `VecEnv` 驱动真实 `MjlabOnPolicyRunner`：GAE 递推与手算轨迹逐位一致（含终止步切断 bootstrap）、clipped surrogate 上界、1 次迭代无 NaN、梯度有限非全零、`model_0.pt` 落盘并可被新 runner 回读且参数逐位相等、网络输出宽度 10/1 |
| `tests/test_robot_layout.py` | 目录结构与模型不变 | 子包恰为 `{robot, actuator, tasks}`、已删包不再出现、MJCF 与 `assets/` 同级且 `meshdir` 未变、资源目录无 `__init__.py`、编译模型仍 15 关节/16 网格/3.2947 kg |

**不再覆盖的部分**（因此上文不写"等价迁移"）：被删测试里针对自实现 PPO 的细节断言——
clipped value loss 取两次估计较大者、`log_prob`/`entropy` 闭式解、adaptive KL 的学习率上下界与
`fixed` schedule、mini-batch 恰好覆盖每样本一次、归一化收敛到批矩与离群裁剪、种子可复现初始
权重、观测维度不匹配时加载失败、`metrics.jsonl` 追加格式。这些语义现在由"逐字节 vendor drop"
保证（`rsl_rl/` 与 `rsl-rl-lib==5.4.2` 无差异，改动会在 `diff` 与超集测试中暴露），
而不是由本地重新推导一遍公式保证。若后续要独立复核上游数值，应单独立任务，避免重新长出一套
本地 PPO 断言。

stand-in 环境只提供 `get_observations`/`step`/`unwrapped.common_step_counter`，形状取契约
的 39/42/10，因此 `make check` 不需要 MuJoCo 也不启动长时间训练。

**验收（本机，CPU）。**

| 检查 | 命令 | 结果 |
|---|---|---|
| 基础检查 | `make check` | 通过：锁文件、ruff、pytest、模型检查、空白检查全绿 |
| 模型不变 | `make model` | `robot/ht_microduck/HT-DK_URDF.xml`，15 关节、16 网格、`nq=22 nv=21 nu=0`、3.2947 kg，与迁移前逐项相同 |
| 残留引用 | `grep -rn "ht_microduck\.\(robots\|actuators\|algorithms\|cli\)" src tests tools` | 仅 `tests/test_training_stack.py` 文档串中说明"旧测试覆盖的是被删模块" |
| 训练短跑 | `duck-train HtDuck-Flat-Velocity --env.scene.num-envs 2 --agent.max-iterations 2 --agent.save-interval 1 --agent.seed 7 --gpu-ids None --log-root .artifacts/smoke_t047/final/logs` | 退出码 0，输出 RSL-RL 面板（`Mean value/surrogate/entropy loss`、`Mean reward`、`Mean episode length`、各 `Episode_Reward/*`、`Episode_Termination/*`） |
| 日志布局 | 同上产物 | `flat_velocity/<时间戳>_velocity/{params/env.yaml,params/agent.yaml,git/HT_microduck_lab.diff,model_0.pt,model_1.pt,events.out.tfevents.*}`，与官方一致 |
| 回放 | 用 `RslRlVecEnvWrapper` + `MjlabOnPolicyRunner.load(load_cfg={"actor": True})` 加载 `model_1.pt` | `PLAY PROBE OK (2, 10) torch.float32`，actor 39 维、critic 42 维、10 维动作，契约未变 |

**`rsl_rl/README.md` 已重写。** 原文把 `_fallback.py` 描述为现存机制、称本目录"只读参考、
不含训练框架代码"、并建议"不需要时直接删除整个 `rsl_rl/`"。这些在补齐副本后都与事实相反
（删掉 `runners/` 会直接 `ModuleNotFoundError`，不会回落 wheel），已按当前职责重写：
完整副本、训练实际路径、修改与升级约束、路径顺序保证及其边界。T046 记录的 `VENDOR_NOTES.md`
死链说明一并作废——该 README 现在不引用它（原文其实也不引用，是更早版本遗留）。

**遗留。** 本轮短跑只证明链路与数值有限，不代表策略性能；多环境 GPU 训练、`viser` 画面与
`duck-eval`/`duck-export`（T027/T028）仍未做。本轮未执行 Git 暂存、提交或推送。

**独立审查。** 由只读子代理执行，见
[审查记录](../review/repo_structure_official_parity.md)。结论"机制正确、可合并，未发现 blocker"；
提出 16 条问题，其中 README 快速开始命令实测失败、`HD_1910_C001/README.md` 死链、
`rsl_rl/README.md` 全面过期、测试"等价迁移"结论过强属需修项，已全部处理；`GitPython`
显式声明一条经评估后以注释说明不修（会强制全量重解析锁文件，而清华镜像对 mjlab 返回 403、
离线无法解析）。修复后重跑：`make check` 通过（180 passed + 8 subtests）、模型不变、
训练短跑与回放探针均通过。审查记录同时说明未验证项与取舍理由。

### T048 完善开发工作流并归档历史记录

目标：把 `AGENTS.md` 中的开发约定落成可执行的阶段步骤，补齐语言与代码风格、论文复现、
实现简洁性与异常处理等缺失条目；把文档一致性检查纳入统一检查；拆分过长的开发文档，
使任务状态单一来源、历史记录可检索。

范围：`AGENTS.md`、`docs/development.md`、`docs/collaboration_review.md`、新建
`docs/development_workflow.md`、`docs/archive/`、`docs/design/TEMPLATE.md`、
`docs/review/TEMPLATE.md`、`docs/review/development_workflow.md`、`docs/setup.md`、
`tools/check_docs.py`、`tests/test_check_docs.py`、`Makefile`、`README.md`。
不改变机器人模型、任务配置、执行器与训练算法。

依赖：T047；用户要求参考 `AGENTS.md` 完善本仓库工作流。

验收条件：

- `AGENTS.md` 与流程文档职责不重叠，链接与锚点有效；`make docs` 通过。
- 归档前后任务编号、前置依赖、完成记录条数逐项一致；任务状态只在 `development.md` 任务表维护。
  前置条件单元格原样搬移，不压缩、不改写。
- 新增的文档检查能在人为构造的坏链接、坏锚点、重复任务编号和依赖环上报错。
- `make check` 全部通过；独立审查覆盖全部交付文件，问题关闭或如实记录。
- 所有代理与检查进程结束后清理本次临时产物与字节码，保留用户已有改动。

结果：见 [开发流程与任务](../development.md)的 T048 完成记录与
[审查记录](../review/development_workflow.md)。

### T050 参考 quadruped_lab 增加一键安装 .venv 入口

目标：运行根目录 `bash setup.sh` 即可准备 uv、Python 3.12，并按锁文件安装到本项目 `.venv/`。
范围：新增 `setup.sh`，复用 `tools/setup_env.py` 的 Toolkit 精确匹配与依赖同步；
更新 README、安装文档并增加入口行为测试。不修改依赖声明、锁文件和用户已有训练进程。
参考：`/home/sunteng/projects/quadruped_lab/setup.sh` 的工具准备、根目录定位、环境固定及代理传递；
保留本项目严格 CUDA 匹配规则，显式支持 CPU，不引入参考项目专用的下载通道测速模块。
验收：`bash -n setup.sh`、帮助/预览、隔离测试覆盖工具缺失/引导安装/路径与代理/失败退出码，
本机真实同步与 Python/依赖导入检查、`make docs`、`make check` 和只读独立复核。

结果：见 [开发流程与任务](../development.md#2026-年-10-月-29-日-t050-一键安装-venv)的 T050 完成记录。

### T051 上传项目到 XN-4090-GPU1 并安装环境

用户本轮另要求新增按官方方式联动头颈的平地速度任务。本地实现作为同一进行中任务下的
独立并发子工作记录，保留远端部署的既有状态、依赖适配和产物；本轮只验收新增环境，
不代表远端安装已经完成。目标为 `HtDuck-Flat-Velocity-Head`，保留原 Velocity，
采用官方随机头部指令/范围课程、腿部姿态奖励及独立日志目录。设计见
[头颈联动速度任务](../design/velocity_head_task.md)。
验收：命令采样/课程/腿部奖励隔离与旧配置不变的单测，GPU 4 环境实际指令/动作/重置与
检查点课程恢复检查，正式入口 16 环境、种子 0、5 迭代短跑，`make docs`、`make check` 和独立审查。

目标：通过 `hupeiyan@j4.tx.ppp.clicki.cn` 登录用户示例中的资产 1（XN-4090-GPU1），
上传当前工作区源码、资源和锁文件，在远端项目目录安装独立 `.venv/`。
范围：先检查远端用户、目录、磁盘、CUDA 与 GPU；上传包含未提交修改的当前文件，
排除本机环境、缓存及训练产物；调用 `setup.sh` 安装，不覆盖远端已有项目或干扰现有训练。
这是本次部署操作，不新增通用部署框架；训练代码沿用现状，依赖调整仅限下述 Warp 构建来源。
远端核查：驱动 570.124.06、Toolkit 12.8.93，默认 Warp 1.18.0 wheel 使用 CUDA 13.4，
要求 R580；本轮补充按 CUDA 后端选择官方同版本 `+cu12` 构建，并同步 `pyproject.toml`、
`uv.lock` 与安装说明，避免重复安装恢复不兼容 wheel。依据为 NVIDIA Warp v1.18.0 安装说明；
CUDA 12 构建要求 R525 及以上，仍需远端实际 GPU/JIT 验证。
验收：源码文件清单与哈希核对、安装退出码、Python 3.12/依赖/任务注册/本地 RSL-RL 路径、
远端 PyTorch 与 Warp GPU 检查及模型检查；本地 `make docs`、`make check` 与独立复核。

结果：见 [开发流程与任务](../development.md#2026-年-10-月-29-日-t051-远端环境部署子工作)的部署记录与同日 Head 子工作记录；两者汇总验收，Head 未发布到远端。

### T052 整理 tasks 目录并验证训练等价

目标：参考本机 `legged_wbc_mjlab/src/tasks` 的配置、MDP 与 RL 分层，整理本项目任务目录，
全部任务复用一个 `mdp/`。范围为五任务配置、RL 配置和 runner 的原样迁移、导入调用方及说明，
保留原有未提交改动、删除与实验产物。设计见[任务目录整理](../design/task_layout.md)。
验收：五任务 train/play 的全部配置逐项等价，固定种子、GPU 16 环境、2 迭代的正式入口前后
短跑及检查点数值对比，旧检查点加载/Head 课程恢复，`make docs`、`make check` 与独立审查。
短跑只验证重构等价，不作为策略收敛证明；本轮不开展远端部署。

结果：见[任务目录整理设计](../design/task_layout.md#实测结果)及[独立审查](../review/task_layout.md)。

### T053 将最新训练代码同步到 XN-4090-GPU1

目标：把当前工作区训练源码、五任务配置及配套文件同步到
`/data/hupeiyan/projects/HT_microduck_lab`，让已安装环境可运行最新五任务与新目录。
范围：上传当前现存源码/配置/资源/测试与文档，核对远端状态并备份需替换的旧源码，
只处理项目拥有的旧模块；保留远端环境、缓存、训练输出及用户进程。
验收：本地 `make docs`、`make check`；同步文件哈希与旧模块清单；远端离线环境同步、
五任务注册与 CLI 导入、本地 RSL-RL 路径、CPU 检查和四环境 GPU 专项；独立只读复核。
本轮不开展完整训练，训练配方与依赖版本沿用当前工作区。

结果：见 [开发流程与任务](../development.md#2026-年-10-月-29-日-t053-同步最新训练代码到远端)的完成记录。

### T054 完整迁入 quadruped_lab 的开发工作流

目标：完整迁入参考 `AGENTS.md` 的通用规则和配套执行细则，统一现行流程与模板。
范围：`AGENTS.md`、流程/协作文档、设计/审查模板及受影响的文档导航；保留本项目技术方向、
正式测试纳管、项目内临时产物约束和全部历史记录，不修改训练代码或开展训练。
验收：逐节对照参考文件，核对实际路径和规则一致性，执行 `make docs`、`make check`，
由只读代理核对迁移完整性；检查结束后清理本次临时产物和字节码。

结果：见 [T054 完成记录](../development.md#2026-年-10-月-29-日-t054-完整迁入参考开发工作流)。


### T055 除 VelStand 外逐项对齐官方任务

目标：将现有 Velocity、Velocity-Head、StandUp、SitStand 的命令、观测、动作、奖励、重置、
终止与课程逐项迁入官方 `microduck_rl@bae39f59`；保留任务 ID、HT 机器人与混合执行器。
用户指定 `flat_velstand_env_cfg.py` 不改；同时冻结其既有共享 MDP、61/64/14、50 Hz 和奖励行为。
设计与迁移对应见[姿态技能迁移设计追加节](../design/skill_task_migration.md#t055-除-velstand-外逐项对齐官方任务)。
验收：基准配置/公式/课程边界与恢复测试、VelStand 文件与完整配置隔离检查、GPU 动态检查、
正式入口短跑及按当前规范运行的有界训练验证、`make docs`、`make check` 与独立审查。
不复制官方机器人或更换 mjlab/RSL-RL，不自动同步远端或执行 Git 写操作。

结果：见[开发完成记录](../development.md#2026-年-10-月-29-日-t055-对齐官方任务并保留-velstand)与[设计最终验收](../design/skill_task_migration.md#t055-最终冻结配方验收)。

### T056 再次同步最新训练代码到 XN-4090-GPU1

目标：把当前工作区的官方配方更新同步到原远端目录，保留现有环境、训练日志和检查点。
范围：核对差异，先备份被替换源码，再上传当前源文件及配套测试/文档；依赖与训练参数不另作修改。
验收：本地 `make check`，远端文件哈希、五任务配置与入口、离线环境同步、CPU 检查和小规模 GPU 环境检查。
本轮仅验证代码部署与环境运行，不启动训练；新配方的检查点兼容边界按 T055 的既定说明交付。

结果：见 [开发流程与任务](../development.md#2026-年-10-月-29-日-t056-再次同步当前训练代码)的完成记录。

### T057 按官方修复 VelStand 恢复机制与 SitStand 高度适配

范围：按已确认分阶段方案，恢复官方非热启动的倒地训练窗口、绝对初态概率和恢复奖励课程；
修正局部势函数重置及身体指令目标，补齐 SitStand 相对坐站参考的高度门限。
保留 HT 混合执行器、任务张量布局和当前物理时序，专家蒸馏/热启动另阶段实施。
设计与分工见[恢复修复设计](../design/skill_task_migration.md#t057-官方恢复机制与-ht-坐站高度修复)。

验收：专项 CPU/GPU 检查；两个任务各至少600秒实际训练与新环境恢复；`make docs`、
`make check`、独立审查和复核。新实验在 `logs/posture_recovery_20261030/`，
本轮旧源码归档在 `logs/posture_recovery_20261030/validation/baseline-code.tar.gz`，既有日志、检查点和视频保留。

### T058 约束坐站与组合任务的物理关节目标

目标：在编码器偏置补偿后按逐环境硬关节范围约束SitStand/VelStand目标，保留原目标语义对照，
使真实下发目标越界率为零，并记录请求越界、限幅、方向相关力矩饱和与连续饱和时长。
模块与接口见[目标约束设计](../design/skill_task_migration.md#t058-坐站与组合任务的关节目标约束)。
验收：CPU边界与配置隔离、官方CLI对照入口、真实GPU与旧检查点对照、两个各至少600秒的
采样/PPO更新及新环境恢复、文档/完整检查和独立审查。技能收敛、教师蒸馏和部署导出另行验收。
修改前源码与Git状态保存在`logs/action_bounds_20261030/validation/`，原训练产物保留。
