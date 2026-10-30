# 开发流程与任务

本页维护项目已有阶段依赖、任务表、必要结果索引与历史记录；现行开发步骤、模块边界、
资料核查、复现、训练验证和交付规则统一见 [开发工作流设计](development_workflow.md)，
仓库约束见 [AGENTS.md](../AGENTS.md)，分工与独立审查见 [协作与审查规范](collaboration_review.md)。

## 每次开发怎么做

1. 阅读仓库规范与相关设计，检查工作区，保留用户已有改动、删除和实验产物。
2. 按改动影响明确目标、范围与验收。小修复、调参、局部重构和文档修改直接实施并验证，
   在交付回复说明结果；已有说明仍准确时不改文档，不默认新增任务、设计、审查或进度记录。
3. 大功能先补充同主题设计，明确模块、接口、分工和验收后继续实现；没有对应设计时才使用模板。
4. 按影响执行验证，大功能与跨模块接口变更完成独立审查及修复复核，再交付完整工作区。
   文档修改后先跑 `make docs`，验收前跑 `make check`；训练验证执行工作流中的训练测试与最低时长要求。
5. 已登记任务的目标、范围、依赖或验收发生变化时更新原条目，必要证据引用实际测试、配置快照和产物，
   不重复粘贴日志；不因完成普通小修改强制新增记录。Git 操作按当前会话授权执行。

## 记录与维护位置

通用规则以 `AGENTS.md` 为准；执行细则在 [开发工作流设计](development_workflow.md) 维护，
本页只维护已有任务及阶段信息，不另立一套流程。README 仅保留介绍、可用示例与必要链接，
环境与 TensorBoard 操作见 [安装文档](setup.md)。

已有任务状态只在下方任务表维护，使用“待办、进行中、阻塞、完成”，同时最多一个主任务进行中；
并发子工作属于同一主任务。登记任务必须有具体产物和可执行验收，全部验收通过才可完成。
阶段按依赖推进，不将前一阶段未通过的条件视为已满足。

已结束任务的正文与更早的完成记录分别按原措辞搬移到 [任务条目归档](archive/development_tasks.md)
和 [完成记录归档](archive/development_records.md)，保留当时结论，不重复维护状态。
本轮工作流变更不追溯改写历史训练证据；历史短跑不视为满足新增的 600 秒训练要求。

## 阶段顺序与验收

| 阶段 | 工作范围 | 通过条件 |
|---|---|---|
| M0 可复现基线 | 环境、MJCF、关节映射、基础检查与 Git 基线 | 安装和检查可重现，现有变更整理为可回溯提交；训练前另通过 GPU 检查 |
| M1 机器人仿真 | mjlab 实体、场景、无刷与舵机执行器 | 场景可创建和重置，两组关节响应符合控制约定；限幅和仿真假设有记录 |
| M2 最小训练 | 平地速度任务、RSL-RL 训练栈、训练入口 | 小规模采样和 PPO 更新可完成，关键张量有限、形状正确，检查点可保存；记录初始评估基线 |
| M3 可评估策略 | 检查点恢复、回放、评估、ONNX 导出 | 恢复可继续训练，固定配置和种子可评估，导出策略与原策略在约定误差内一致 |

阶段结论：**M0、M1 已通过，M2 未通过。**
M0 的安装、模型与关节映射已具备，GPU 基础检查见[安装文档](setup.md#3-验证安装和-gpu-环境)，
Git 基线已建立在 `9840fa8`，此后改动尚未提交；
M1 的整机工厂接入执行器后 `nu=15`，已有场景、执行器与 IMU 的运行证据；
M2 的训练链路已接通（`duck-train` 可采样、更新、存取检查点），但**尚无固定种子的定量评估基线**，
因此 M2 未通过验收。T027 已做的恢复与回放属于 M3 的前期准备，**不作为 M3 已开始的依据**。
短场景检查与短跑不代表稳定站立或策略可用，证据见各任务条目与完成记录。

## 当前任务

当前任务状态以下表为准，本页其他位置不复述状态。
最近一次提交为 `9840fa8`（可走路了）；T047 已把包目录与官方对齐
（`robot/`、`actuator/`、`tasks/` 三个子包，MJCF 与 `assets/` 同级）并删除自实现训练栈，
训练算法只剩仓库根 `rsl_rl/` 一套。

下表是本页唯一的任务状态来源；已结束任务的目标、范围与实测结果在
[任务条目归档](archive/development_tasks.md)，历史记录在[完成记录归档](archive/development_records.md)。

| 编号 | 任务 | 状态 | 前置条件 |
|---|---|---|---|
| T000 | 建立开发规则和统一检查入口 | 完成 | 无 |
| T001 | 整理现有开发基线 | 完成 | T000 |
| T002 | 接入 mjlab 机器人实体与最小场景 | 完成 | T001 |
| T003 | 补充并发与测试文件管理规则 | 完成 | T000 |
| T004 | 评审 robots 模块缺项 | 完成 | T000；不依赖 T001 提交，仅只读评审代码 |
| T005 | 核实并简化 MJCF 资源加载 | 完成 | T004；用户提出的模型加载修正 |
| T006 | 分析混合执行器配置方案 | 完成 | T004、T005；只读调研，不依赖未知硬件参数 |
| T007 | 对照公开项目的执行器选型 | 完成 | T006；只读调研 |
| T008 | 核实 HD1910 与 Microduck 的 BAM 适配方案 | 完成 | T006、T007；用户新增空执行器文件 |
| T009 | 实现并验证 HD1910 的 mjlab 1.6 适配器 | 完成 | T008；独立组件和测试台不依赖 T002，完整机器人接入仍依赖 T002 |
| T010 | 补充 HD1910 执行器目录说明 | 完成 | T009；用户要求目录内 README |
| T011 | 编写机器人常量模块的混合驱动器配置 | 完成 | T009、T010；用户明确要求，独立配置与测试台不依赖 T002 |
| T012 | 复核用户新增的随机驱动器延迟 | 完成 | T011；用户已修改两组延迟参数，要求检查 |
| T013 | 同步随机延迟的测试、说明与运行期回归 | 完成 | T012；保持用户选定的延迟配置；由 T016 一并落实 |
| T014 | 对照官方复核 robots 模块剩余缺项 | 完成 | T011、T012；只读评审，不依赖 T001 提交 |
| T015 | 对照 MicroDuck 官方评审 robots 模块 | 完成 | T014；用户明确指定 MicroDuck 官方，只读调研不依赖 T001 提交 |
| T016 | 实现整机机器人配置与最小场景验证 | 完成 | T015；用户明确要求实施，含 T013 必要回归；不代替 T001 Git 基线验收 |
| T017 | 修复 constants 直接运行的整机预览入口 | 完成 | T016；用户新增 main 块并报告必填参数错误，临时修复 |
| T018 | 按官方风格集中定义机器人配置 | 完成 | T017；用户明确要求采用模块级配置，仿真假设继续标明 |
| T019 | 整理机器人常量模块的代码风格 | 完成 | T018；用户指定参考文件，保持行为不变 |
| T020 | 对照 Microduck 官方简化机器人参数配置 | 完成 | T019；用户要求重新核对参数与参考风格 |
| T021 | 对照 Microduck 梳理训练与实机部署缺项 | 完成 | T020；用户指定官方仓库，只读调研不依赖 T001 提交 |
| T022 | 固定首版任务控制与观测契约 | 完成 | T001、T002、T021 |
| T023 | 实现最小平地速度任务 | 完成 | T022；参考 pollen-robotics/microduck_rl 官方平地任务 |
| T024 | 实现本地网络与轨迹 Storage（实现已被 T047 删除，算法改用 RSL-RL） | 完成 | T023 |
| T025 | 实现本地 PPO 更新（实现已被 T047 删除，算法改用 RSL-RL） | 完成 | T024 |
| T026 | 接通 Runner、训练入口与短跑基线（入口形态已被 T046/T047 取代） | 完成 | T023、T025 |
| T027 | 实现恢复、回放与定量评估 | 阻塞 | T026；接续条件是 T049 的契约与任务稳定后再做定量评估 |
| T028 | 导出策略包并通过 CPU MuJoCo 回放 | 待办 | T049；导出需在新 61 维契约下进行 |
| T029 | 接入混合硬件 I/O、IMU 与故障处理 | 待办 | T022；需确认本机协议、IMU 与控制板，策略可先用替身 |
| T030 | 标定实机参数并验证域随机化 | 待办 | T029；需本机台架与测量数据 |
| T031 | 验收实机站立与低速速度跟踪 | 待办 | T028、T029、T030；需实机与目标板运行证据 |
| T032 | 参考 quadruped_lab 完善工作流与忽略规则 | 完成 | T021；用户明确要求，独立于 T001 的 Git 提交 |
| T033 | 替换为用户提供的 HT-DK_URDF 模型 | 完成 | T020、T032；用户指定本地资源，独立于 T001 的 Git 提交 |
| T034 | 对照 duck_project 评估无刷电机 NT 执行器 | 完成 | T033；用户指定参考项目，并确认型号为 HTDW-3532-02-DNE |
| T035 | 实现并接入 3532 NT-PD 执行器 | 完成 | T034；用户明确要求实施，独立于 T001 的 Git 提交 |
| T036 | 对照三个参考项目确定下一步 | 完成 | T035；用户指定 microduck、microduck_rl 与 duck_project，只读调研与只读实测 |
| T037 | 在 XML 中声明 IMU 参考点与内置传感器 | 完成 | T036；用户明确要求按官方项目补 IMU 数据 |
| T038 | 标定 HOME 站姿 | 完成 | T001、T002、T037；用户给出 `hip_roll 0.38`/`hip_pitch 1.57` 并要求重心居中、不前后倾 |
| T039 | 按官方结构重写机器人常量模块 | 完成 | T037；用户指出本体 XML 不应携带地形、常量应照官方写法 |
| T040 | 精简 README 并整理项目入口 | 完成 | T039；用户要求优化 README，独立于 T001 的 Git 提交 |
| T041 | 对照三个参考项目复核下一步 | 完成 | T040；用户指定 microduck、microduck_rl 与 duck_project，只读调研与项目内探针 |
| T042 | 核对三处模型的碰撞体简化 | 完成 | T041；用户要求比较本机、官方 microduck 与 duck_project 的碰撞体 |
| T043 | 拉取 PPO 与网络设计源码参考 | 完成 | T042；用户只要 PPO/网络设计，不要整个训练框架 |
| T044 | 修复自碰撞传感器误计地面接触 | 完成 | T023；用户报告"脚与地面的接触也算成自碰撞" |
| T045 | 修复独立预览的积分器与初态 | 完成 | T018；用户报告直接运行常量模块会倒地后一直抽、且看不到 `init_state` |
| T046 | 对齐官方目录设计与训练/回放入口 | 完成 | T045；用户要求按官方 `microduck_rl` 重设 |
| T047 | 包目录与官方完全对齐并收敛到唯一训练算法 | 完成 | T046；用户要求架构像官方且只用本项目 `rsl_rl/` |
| T048 | 完善开发工作流并归档历史记录 | 完成 | T047；用户要求参考 `AGENTS.md` 完善本仓库工作流 |
| T049 | 迁移官方姿态技能任务（起立 / 坐站 / 行走站立）与 14 执行器契约 | 待办 | T048；用户要求参考官方 microduck_rl 迁移三个技能任务；本轮先处理 T050，已有实现与实验保留 |
| T050 | 参考 quadruped_lab 增加一键安装 .venv 入口 | 完成 | T048；用户指定参考项目 setup.sh，复用现有 tools/setup_env.py |
| T051 | 远端环境部署与本地头颈联动速度任务 | 完成 | T050；远端上传与安装获明确授权，本地头颈任务为同任务下的独立并发子工作 |
| T052 | 参考 legged_wbc_mjlab 整理 tasks 并验证训练等价 | 完成 | T051；用户要求配置与 MDP 按职责归档，全部 MDP 共用一个目录，训练行为不变 |
| T053 | 将最新训练代码同步到 XN-4090-GPU1 | 完成 | T051、T052；用户要求更新既有远端项目，包含 Head 任务与新 tasks 目录 |
| T054 | 完整迁入 quadruped_lab 的开发工作流 | 完成 | T053；用户指定参考 AGENTS.md，完整迁入通用规则并适配本项目路径 |
| T055 | 除 VelStand 外逐项对齐官方任务 | 完成 | T052、T054；用户指定保留 flat_velstand_env_cfg.py，其余现有任务按官方 bae39f59 实现 |
| T056 | 再次同步最新训练代码到 XN-4090-GPU1 | 完成 | T053、T055；用户要求把当前更新后的训练代码传到原远端项目 |
| T057 | 按官方修复 VelStand 恢复机制与 SitStand 高度适配 | 完成 | T055、T056；用户确认分析后的环境修复方案，专家蒸馏另阶段 |
| T058 | 约束 SitStand 与 VelStand 的物理关节目标并增加饱和诊断 | 完成 | T057；用户确认训练诊断后的修改方案，原配方作为对照保留 |

## 当前任务详情

各任务的目标、范围、验收条件与实测结果见
[任务条目归档](archive/development_tasks.md)，按编号检索即可。

进行中任务与下一项的范围摘要如下，**状态以上方任务表为准**，避免再翻归档：

### T027 实现恢复、回放与定量评估

已完成：恢复训练（网络、优化器、统计与迭代号接续）与 `duck-play` 回放（trained/zero/random、
native/viser 查看器、mp4 录制），证据见[完成记录归档](archive/development_records.md)中
“2026 年 10 月 27 日 T027”条目。

未完成：`duck-eval` 与固定种子定量评估报告，要求覆盖零速、前后、侧移、转向，
报告跟踪误差、跌倒率、episode 长度与限幅统计，并在开工时冻结部署前的仿真性能门槛。
未达标时先记录并按授权训练/调参，不能进入 T031。

### T049 迁移官方姿态技能任务与 14 执行器契约

目标：按官方 `pollen-robotics/microduck_rl` 的任务族补齐三个姿态技能任务，并把动作/观测契约从
10 执行器扩展到 14（腿 10 + neck_pitch/head_pitch/head_yaw/head_roll，嘴保持 HOME）。
设计与依据见[姿态技能迁移设计](design/skill_task_migration.md)。

2026-10-29 用户补充「能站住，但不迈步」，本轮优先修复行走回归：
对照 `9840fa8` 恢复纯行走的 `0.25 rad/action` 和 HOME 头部目标，保留 61/64/14
向量布局与三个姿态任务的 `1.0 rad/action`；抬脚奖励改用 mjlab 1.6.0 自带的连续腾空区间计数，
同时覆盖原地转向，并使用传感器的逐环境 reset 生命周期管理计时。
验收：奖励边界/转向/静止单测、动作映射与局部计时 reset 的 GPU 检查、真实入口短训练和
固定前进指令回放、`make docs`、`make check` 及独立复核。短跑不作为收敛或稳定行走的证明。

本轮追加：用户确认三个速度均为 0 后仍持续抬脚。目标是零指令时明确约束足底离地和运动，
移动时继续允许迈步；VelStand 的坐姿、倒地与起身阶段不受双脚触地约束。
范围：`mdp.py` 与两个行走任务的奖励配置、相关测试及本条记录；不修改动作/观测/检查点格式。
验收：零指令/阈值/纯转向/非零速度与恢复门控单测、GPU 实际静止/离地奖励比较、
正式入口 64 环境 5 次迭代训练、`make docs`、`make check` 与独立复核。

用户现已收窄范围：撤除上述足底代价与恢复门控，只在 `HtDuck-Flat-Velocity` 增加
零指令下对 `default_joint_pos` 的 L1 偏差项 `stand_still`（权重 −0.5）。
其余行走奖励门控恢复到 11:12 训练基线；不再给 VelStand 添加额外站立项。
验收改为默认姿态/关节子集/零速与转向门控单测、4 环境 GPU 真实关节偏差检查、
`make docs`、`make check` 和独立复核；不启动额外训练、不改动用户正在运行的进程。

本轮新增需求：仅对 `HtDuck-Flat-Velocity` 补齐官方身体角速度、全身角动量、落足摆动峰高和
头部长期偏差项，足高与滑动改用官方公式（含纯转向门控）。接入仅供奖励使用的足端地形高度
传感器，并补齐峰高/头部 EMA 的逐环境 reset；头部偏差权重按官方延后渐增。
范围与对应关系见[设计追加说明](design/skill_task_migration.md#2026-10-29-平地行走奖励对齐官方)。
验收：公式/门控/峰高落足/局部 reset/课程边界测试，4 环境 GPU 传感器与奖励检查，
正式入口 16 环境、种子 0、5 迭代短跑，`make docs`、`make check` 和独立审查。
保留当前 61/64/14、动作缩放、HOME 头目标及 `stand_still`；不改动用户正在运行的训练。

产物（路径随 T052 整理）：`tasks/contract.py`、`tasks/mdp/`、
`tasks/config/flat_{standup,sitstand,velstand}_env_cfg.py`、`tasks/config/{terrain,rl_cfg}.py`、
注册与导入期契约守卫。

已完成：
- 契约扩展为 61 维 actor / 64 维 critic / 14 维动作，50 Hz 不变；四任务共享同一契约，
  观测/动作顺序由 `contract.py` 单一来源固定，导入期守卫防止槽位漂移。
- 三个新任务在 mjlab 1.6.0 下构建成功并通过短训练（64 环境）。
- 姿态实测（130 个限位内候选 + 7 个躺姿，真实动作通道）：**本机存在可保持坐姿**，
  `hip_pitch +1.55 / calf +0.40 / ankle +0.35 / hip_roll ±0.0873`，6 s 保持
  `z=0.0563 m`、倾角 1.3°、峰值力矩 0.879 N·m（限 3.7）、零漂移。
- 关键反直觉结论：坐姿比任何躺姿都低（0.0563 vs 0.060–0.093 m），
  因此倒地判定改由**倾角主导**，高度门限只作穿地保护并与倾角取合取。
- `make check` 全绿：锁文件、ruff、222 个测试、模型、文档检查均通过；
  `tools/check_task_contract.py` 与 `tools/check_velocity_env.py` 通过。
- 独立审查见[审查记录](review/skill_task_migration.md)：第二轮复核结论为**独立审查通过**，
  9 条问题（1 阻塞、5 一般、3 建议）全部修复：
  - R1 `feet_air_time` 奖励符号倒置（阻塞）：归零前取值使每次落足恒付 −0.125；
    重写为与 mjlab 官方一致的区间计数，实测 0.13/0.20 s 计 2.0、区间外计 0、无负值，
    训练日志由恒负转为正值。
    本轮进一步核对发现，该版本仍只在落脚瞬间计分，与 mjlab 的持续区间奖励不同；
    当前修复及证据以本轮完成记录和设计中的「行走回归修复」为准。
  - R2 出生姿态与命令不一致（21/48）：改为重置事件自行抽签并交给命令项重放，实测 0/96。
  - R3 课程阶段单位错 24 倍：新增 `STEPS_PER_ITER` 与 `_iter()`，并加导入期一致性断言。
  - R4 门限数字与死常量：度数形式进契约（`FALLEN_TILT_DEG`/`RECOVERED_TILT_DEG`/
    `DOWN_TILT_DEG`），三处 `70.0` 字面量与 velocity 任务统一到契约。
  - R5 `make check` 结论唯一化；R6 课程向量参数入日志（`mixture/0..3`）；
    R7 死代码清理（`StandingGatedPoseCommand` 改为接入使用）；R8 补零槽宽度纳入导入期校验。
  - R9 奖励状态跨回合泄漏（`env._ht_*` 无 reset）：新增类式项 `RewardStateReset` 与
    `reset_reward_state`，实测重置后首步 `upright_progress` 支付由 344/360 次降为 0。

未完成：三个任务的完整训练（本次只做短跑验证）；Rough 变体的地形标定与训练。
三个任务能否收敛需按官方迭代上限完整训练才能判断，不属本次交付结论。
R9 的修复方式经实现者自测，尚未经审查者第三轮复核。

### T028 导出策略包并通过 CPU MuJoCo 回放

产物：`duck-export`、策略元数据（观测/动作顺序、归一化统计、控制周期）、
ONNX 一致性工具和 CPU 回放工具。

验收：实际执行导出命令，同一观测集比较 PyTorch/ORT 并冻结误差容限；
在 CPU MuJoCo 用同样的执行器、时序、观测和缩放/滤波闭环运行，不换成理想 PD；
确认 CPU 对 BAM 执行器的适配。详见[任务条目归档](archive/development_tasks.md#t022t031-后续任务的产物与验收)。

## 后续任务的产物与验收

以下命令针对尚未实现的接口，当前不能直接运行；开工时确定最终参数并写入对应任务。
全部实现任务继续要求 `make check`，GPU 与硬件专项验证须另行保留实际运行证据。
T022–T031 的完整验收表保留在[任务条目归档](archive/development_tasks.md#t022t031-后续任务的产物与验收)。

T030 更新模型参数后须核对训练配置与实机契约；超出已训练、验证范围时，重做受影响的仿真、
训练、评估与导出。T031 只使用与最终标定配置匹配且通过仿真性能门槛的策略包，
不能沿用过时导出结果。

稳定行走之后再评估起身、头部联合控制、复杂地形和其他技能。
上游产品层的 Rust 多服务、蓝牙、相机与更新系统不要求在本仓库完整复刻。

## 新任务模板

需要登记的阶段任务或大功能加入上方任务表，并按需在本页添加以下内容；小修改不强制登记。只保留与任务有关的字段和检查。

```text
Txxx 任务名称
状态：待办
目标：完成后能观察到什么行为
范围：本次要改的模块
依赖：前置任务或所需参数
验收：可执行命令，以及期望看到的结果
结果：完成时填写命令、关键输出、剩余问题
```

## 统一检查命令

先按[安装文档](setup.md)准备环境，在仓库根目录运行：

```bash
make check
```

该命令依次检查锁文件、Python 代码、已有测试、机器人模型、文档一致性和差异空白。
锁文件检查使用本地缓存且不更新锁文件；其余项目命令使用 `uv run --no-sync`。
每次调用检查目标会建立独立的 `.artifacts/checks/run-XXXXXXXX/` 并打印实际路径，
自动设置 TMPDIR、无字节码模式、pytest basetemp 与 pytest/Ruff/Warp/Torch 编译缓存。
单独调用下表的目标也使用独立目录；`make`、`make help` 与 `make -n check` 不创建产物。
检查失败时保留该目录用于排查，任务交付前只清理本次实际创建的目录，不删除其他任务或用户实验文件。

直接运行 GPU 专项工具或其他命令不会经过 Makefile；仍按 `AGENTS.md` 显式设置项目内临时与缓存目录。
Git 差异检查只覆盖已跟踪文件，新文件还需用 `git ls-files --others --exclude-standard` 列出并按实际路径审阅。

| 命令 | 用途 |
|---|---|
| `make lint` | Ruff 代码检查 |
| `make test` | 运行 `tests/` 中的测试 |
| `make model` | 编译 MJCF 并核对关节顺序及电机映射 |
| `make docs` | 检查文档链接、锚点和任务表一致性 |
| `make lock-check` | 离线检查依赖声明与锁文件一致性 |
| `make viewer` | 在有图形桌面的终端中打开静态预览 |

测试入口设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，避免系统 ROS 等环境的 pytest 插件干扰测试启动。
以后确实需要第三方 pytest 插件时，在测试入口中用 `-p` 明确加载。
`make docs` 检查 `AGENTS.md`、`README.md` 与 `docs/` 下的本地链接和锚点，并校验本页任务表：
状态取值、编号唯一、最多一个进行中、前置依赖存在且无环、已完成或进行中任务不依赖待办/阻塞任务。
新增或移动文档后先跑 `make docs`；它不检查文字内容与规则合理性，那部分仍靠人工审阅。
GPU 验证按[安装文档](setup.md)执行；`duck-eval` 与 `duck-export` 实现后加入专项验收。

## Git 与实验记录

默认交付工作区，不自动提交、推送、合并或发布；已有明确授权持续有效，设计与审查通过不授予 Git 写操作权限。
共享工作区不并发切换分支或执行 Git 写操作。获授权后的提交格式与类型统一遵循
[Git 提交约定](development_workflow.md#7-git-提交约定)，暂存时列出具体文件并检查差异，避免混入已有改动。

`.gitignore` 排除环境、缓存、构建及根目录运行产物；正式测试、流程/设计/审查文档、
`pyproject.toml`、`uv.lock`、Python 源码、XML/STL 和厂家参数均保持可跟踪。
不使用全局 `*.pt`、`*.onnx`、`*.json` 等规则隐藏可能用于验证或随包发布的资源；
在开始写入新的运行目录前核对忽略规则。忽略不等于删除，已有被跟踪文件也不会自动退出索引。

训练实验从代码可回溯的状态开始。每次实验至少记录代码提交号及未提交差异、配置、随机种子、
环境与设备、启动命令、指标和检查点位置。对比实验一次只改变一个主要因素。
模型权重、视频和日志保留在输出目录，代码仓库保留复现实验所需的配置与结论。
入口尚未实现时不能声称某个示例目录是默认路径；实现后以真实入口为准。
需要交付的测量数据、策略或报告必须明确用途、项目内保留路径和分发方式；
`.artifacts/` 中的临时检查目录不得作为唯一长期结果位置。

## 完成记录

只保留最近的任务记录；更早的记录在[完成记录归档](archive/development_records.md)。
需要更新的已登记任务记录按时间顺序追加在末尾（与归档同一顺序），注明日期和任务编号，
引用实际命令、关键结果、审查结论和遗留项；小修改在交付回复说明即可。归档时把较早的记录整段搬过去，保留原文措辞。

### 2026 年 10 月 28 日 T048

用户要求参考 `AGENTS.md` 完善本仓库工作流。本轮把开发流程拆分为可执行步骤，
补齐语言与代码风格、论文复现、实现简洁性和异常处理约束，并把文档一致性检查接进
`make check`（新增 `tools/check_docs.py`、39 条单元测试和 `make docs`）。

结构上拆分了本页：`development.md` 从拆分前的 3751 行降到 321 行，任务条目与历史完成记录分别归档到
`docs/archive/development_tasks.md`（42 条条目；T027–T031 合并为前瞻块，T042/T043 只有完成记录）和
`docs/archive/development_records.md`（35 条历史记录），任务状态仍只在本页维护。
原文中误置于「完成记录」标题下的 T046/T047 任务条目一并移入任务归档。新增
`docs/development_workflow.md` 记录流程取舍、与 `quadruped_lab` 的差异及修改历史；
`docs/setup.md` 新增训练日志可视化一节，补上此前缺失的 TensorBoard 用法。

验收：`make check` 全部通过（219 passed + 8 subtests，含 `make docs` 的
`17 files, 100 links, 49 task rows scanned`）；归档用切片比对确认为搬移而非重写，
任务编号、前置依赖与完成记录全部保留；`make docs` 在人为构造的坏链接、坏锚点、
重复编号、依赖环和「进行中依赖待办」上均能报错，这 7 类行为已固化为端到端用例。
独立审查见[审查记录](review/development_workflow.md)：审查者提出 15 条问题，
其中 2 条阻塞（前置条件被压缩丢失依赖编号、审查记录仍是占位）与 9 条一般问题已修复，
3 条建议已落实或记录理由，第 15 条确认无需修改。
遗留：T027 的定量评估与 T028 的导出仍未做；本轮未执行 Git 暂存、提交或推送。

### 2026 年 10 月 29 日 T049 行走回归修复与有界验证

用户报告「能站住，但不迈步」，要求参考之前能走路的提交。本轮只读对照 `9840fa8`：
旧配方是 10 个腿动作、39/42 维观测、`0.25 rad/action`、头部保持 HOME；当前工作区扩展为
14 动作、61/64 维、`1.0 rad/action` 和随机头部目标。机器人 MJCF、HOME 与执行器物理参数
相对旧提交没有行为差异。仓库没有可用的旧行走策略或训练日志，因此提交标题不作为定量验收依据。

本轮保留 61/64/14，纯行走独用 `WALKING_ACTION_SCALE=.25`，头目标为 HOME，
三个姿态技能仍用 `1.0` 与原头部范围。抬脚奖励直接复用本机 mjlab 1.6.0 的连续腾空区间奖励，
修复只在落脚计分和漏掉原地转向；启用传感器 `track_air_time`，清除手工跨回合计时问题。
play 的推力间隔恢复为与训练一致的 3–6 s。已有未提交重构、用户删除与实验产物均保留。

验证：`make docs` 通过；`make check` 通过（225 passed + 8 subtests）。新增专项测试覆盖腾空
持续计分、静止/转向门控、区间边界和姿态任务配置隔离。GPU 契约检查（4 环境、种子 0、
150 控制步）与环境检查（16 环境、种子 0、150 随机步）通过；零动作 0/16 跌倒，
局部 reset 只清指定环境腾空计时，强制翻倒检出 16/16。

真实入口训练（cuda:0、种子 0、24 步/迭代，每次独立目录，TMPDIR/Warp/Torch 缓存在项目内）：

```bash
timeout 300s uv run --no-sync duck-train HtDuck-Flat-Velocity \
  --env.scene.num-envs 64 --agent.max-iterations 5 --agent.seed 0 \
  --agent.run-name gait_fix_smoke --log-root logs/walking_regression_20261029/smoke
timeout 600s uv run --no-sync duck-train HtDuck-Flat-Velocity \
  --env.scene.num-envs 256 --agent.max-iterations 300 --agent.seed 0 \
  --agent.run-name gait_fix --log-root logs/walking_regression_20261029/short
```

两次正常退出，分别保存 `model_4.pt`、`model_299.pt`，短训共 1,843,200 个环境转换、
约 258 s；最后一轮各 loss 有限，`nan_state=0`。权重与配置保留在
`logs/walking_regression_20261029/short/flat_velocity/2026-10-29_10-56-17_gait_fix/`。

固定指令回放：32 环境、种子 0、每种指令 6 s，前 1 s 预热；保留启动域随机化，关闭观测噪声
和外推力，头目标为 HOME，通过正式 `MjlabOnPolicyRunner.load` + inference policy 执行。
仅统计首跌前数据，以 `last_air_time > .1 s` 的再次触地计为完成一次摆动。
`vx=.2 m/s`、零速、`wz=.5 rad/s` 三种指令均 0/32 跌倒，但有效摆动均为 0；
前进均速约 `−0.00014 m/s`、转向均角速约 `0.00062 rad/s`，**仍未学会迈步**。
逐项数据与日志保留在 `logs/walking_regression_20261029/replay.json` 和同目录 `replay.log`。

为避免把短跑结果归因于修复，另用修改前的工作区配方作相同预算对照：通过官方
`mjlab.scripts.train.run_train`（未复制训练循环），恢复修改前动作缩放、随机头目标与落脚奖励，
同为 cuda:0、种子 0、256 环境、300 次迭代、600 s 上限。正常退出，共 1,843,200 转换、
约 261 s，`model_299.pt` 保存到
`logs/walking_regression_20261029/baseline/flat_velocity/before_fix_seed0/`。
两组检查点的 actor/critic 共 25 个状态张量均有限；在相同回放设置下（两组均固定 HOME 头目标、
使用各自训练的动作缩放），对照策略也为三种指令 0/32 跌倒、0 有效摆动、近零速度。
结果在 `baseline_replay.json`，源码行为差异另存 `repair.diff`，均位于上述实验根目录。
单种子 300 次迭代的结果**未验证出迈步改善，也不能确认静止的唯一原因**；
两组训练奖励定义已改变，不用总奖励高低比较策略质量。

独立代码审查及注释复核通过，见[本轮审查附录](review/skill_task_migration.md#2026-10-29-行走回归修复独立审查)。
本轮修复有代码与专项证据，但没有完成策略行走效果验收；300 次迭代不能证明收敛，
不能把本轮作为「已恢复稳定行走」的结论。下一步是按固定指令评估延长训练后的策略，
若仍无迈步，再针对头部动作与奖励竞争做单因素对照；完整姿态训练、Rough 与 R9 其他姿态项复核仍未完成。

### 2026 年 10 月 29 日 T049 零速度指令下持续抬脚

用户确认三个速度均为 0 后仍持续抬脚。检查发现，腾空正奖励已在零指令下关闭，
但原配置没有直接约束足底离地或足底运动，足高/滑动代价也随零指令关闭。
本轮新增 `idle_feet` 软代价，零指令下对每只未接地脚计 1，并计归一化足底速度平方
`sum((v / .1 m/s)^2)`，权重 −1；运动指令下归零。头部和腿部不被强制锁在 HOME，
保留平衡修正与躯干姿态控制。站立/运动的门控共用 `COMMAND_ACTIVITY_THRESHOLD=.01`，
活动值为 `norm(vxy)+abs(wz)`，包括纯转向；足高/滑动代价同步补上转向门控。

VelStand 对代价作平滑渐入：高度从坐姿到已恢复高度、倾角从 60° 到 25°，
复用现有 `_smoothstep`，避免硬门槛处突然免罚。高度按相对环境原点计算，
坐姿和倒地免罚，恢复过程逐渐生效。`.1 m/s` 与权重是仿真调参，不代表硬件标定或训练收敛。
动作/观测维度、顺序、缩放及 50 Hz 均不变；既有 checkpoint 的推理不会因奖励文件修改立即改变。

验证：

- 专项测试 14 passed；独立审查者复跑相同测试亦为 14 passed。
  覆盖零/微小输入、阈值边界、纯转向、倒退、接地/足速、头部不锁定、恢复渐入和环境原点不变性。
- `make check` 通过：230 passed + 8 subtests、Ruff、锁文件、模型、文档与差异空白检查通过。
- GPU：`timeout 600s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0 --num-envs 16 --steps 150`，
  种子 0、50 Hz、100 步零动作保持 0/16 终止；实际基座抬高 `.03 m` 后仿真更新，
  每个环境均由接触传感器报告 2 只脚离地。实际 twist 清零时，平均静止代价由 `0.0000`
  升至 `12.3223`；相同物理状态改为前进或纯转向时，代价严格为 0。
  原来的计时局部 reset、随机步有限值和强制翻倒检查亦通过。
- 正式入口分别对 `HtDuck-Flat-Velocity`、`HtDuck-Flat-VelStand` 执行
  `timeout 300s uv run --no-sync duck-train <task> --env.scene.num-envs 64 --agent.max-iterations 5 --agent.seed 0 --agent.run-name idle_feet_smoke --log-root logs/idle_feet_20261029/train`。
  cuda:0、每环境 24 步/迭代，分别完成 7,680 个转换；两项均正常退出，
  `idle_feet` 日志项真实出现，均保存 `model_4.pt`，各 25 个 actor/critic 状态张量全部有限。
  TMPDIR、Warp/Torch 缓存和 pytest basetemp 均显式放在本项目 `.artifacts/t049-idle/`。

独立代码审查通过，见[审查附录](review/skill_task_migration.md#2026-10-29-零指令持续抬脚修复审查)。
GPU 日志、训练配置、事件与两项检查点保留在 `logs/idle_feet_20261029/`，用于本轮验证追溯；
本次临时探针和缓存交付前清理。没有提交、推送或修改用户已有实验。

本轮验证的是零指令下奖励确实偏好双脚静止，**不是用户旧策略已停止抬脚的证明**。
下一步用新奖励训练或继续训练对应策略，按零速→行走→零速切换测量停步后的抬脚次数、
速度误差与跌倒率；完整训练、站立代价参数标定及整体行走效果仍待验收。

### 2026 年 10 月 29 日 T049 用户训练回归审计

用户报告新训练不会走路并询问改动，指定
`logs/rsl_rl/flat_velocity/2026-10-29_13-30-18_velocity/`。
本轮只审计实际训练证据并记录，不继续修改训练参数；该训练仍在运行，未停止、重启或覆盖产物。

对照前一次用户训练 `2026-10-29_11-12-58_velocity/`：

- `params/agent.yaml` 完全相同；网络、PPO、种子均未变，两次都是 `resume:false`，即从零训练。
- `params/env.yaml` 唯一差异是新增 `idle_feet`（权重 −1、`speed_scale=.1`、阈值 `.01`）。
  `.25` 动作缩放、HOME 头目标、上游连续腾空奖励均已在 11:12 的配置中存在。
- Git 源码快照还确认同名函数内部变化：足高/滑动代价由仅检查平移，改成包含纯转向的门控；
  这些函数体变化不会体现在 YAML 差异中。机器人、电机参数、时序与向量接口未变。
- 更早一轮本会话的改动还包括行走缩放 `1→.25`、随机头目标改为 HOME、
  落脚奖励改为连续腾空区间奖励、play 推力间隔恢复为 3–6 s；这些不能当作 13:30 相对 11:12 的新变化。

一次性读取两份 TensorBoard 事件中的历史数据，仅比较相同的第 450–500 轮，未反复轮询运行指标：

| 日志项的窗口均值 | 11:12 | 13:30 |
|---|---|---|
| `Episode_Reward/air_time` | 0.06053 | 0.00154 |
| `Episode_Reward/track_linear_velocity` | 1.40554 | 1.00198 |
| `Episode_Reward/upright` | 1.85666 | 1.85634 |
| `Episode_Reward/idle_feet` | 无 | −0.12721 |

这些是日志聚合奖励，不是固定指令下的速度误差或实际迈步次数，不能代替回放评估。
但抬脚激励明显减少而直立项几乎相同，与用户报告的不愿迈步相符。

源码风险：`sum((v/.1)^2)` 无上限，单只脚速度模长 `.3 m/s` 即为代价 9，
尚未计离地代价，已超过四项主要正奖励合计理论上限 8。虽然该项只在零指令时直接生效，
网络与每动作的状态无关探索标准差在各命令间共享，可能间接抑制行走探索。
这是有公式依据的风险机制，**尚未通过单因素对照证明唯一因果**。

独立只读审计者 `regression_audit` 确认了两个 YAML、Git 快照和实现差异，未运行 GPU 或训练。
本轮纠正先前交付判断：5 次迭代冒烟与通用测试只证明代码可运行，未验证新增站立代价不破坏行走，
不能据此把该奖励参数作为已验收默认配方。下一步优先对比用户策略在相同固定指令下的表现，
再只对新增站立惩罚做移除/弱化对照；不再把延长训练当成必然能解决问题的结论。

### 2026 年 10 月 29 日 T049 按用户要求简化为 default_pos 站立项

用户明确要求不再增加复杂机制，只加零指令保持 default_pos。本轮移除 `idle_feet_cost`、
足底速度/离地代价、VelStand 的恢复高度/倾角 wrapper 与相关全局门控辅助；
足高/滑动门控恢复到 11:12 基线。仅在 `HtDuck-Flat-Velocity` 新增 `stand_still`：
14 个策略关节相对实体 `default_joint_pos` 的 L1 偏差，权重 −0.5，
`norm(vxy)+abs(wz)<=.01` 时生效，移动或纯转向时为 0。不以零关节角代替默认站姿。
动作/观测维度、顺序、缩放、时序、机器人、电机及 PPO 配置不变；VelStand 不加 HOME 约束。

验收：专项测试及独立复跑均 11 passed；`make check` 227 passed + 8 subtests，
锁文件、Ruff、模型、文档与差异空白检查通过。
GPU 命令为 `timeout 300s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0 --num-envs 4 --steps 50`，
种子 0、50 Hz；实际写入默认关节位置后代价为 0，单个策略关节偏移 `.1 rad` 后代价为 `.1`，
相同状态下平移和纯转向指令均关闭该项；零动作 0/4 终止，其余既有检查通过。
独立只读复核通过，见[审查附录](review/skill_task_migration.md#default_pos-最小站立约束复核)。
日志保留在 `logs/default_stand_20261029/env.log`；临时缓存和探针交付前清理。

本轮没有启动额外训练或停止用户训练。`2026-10-29_13-30-18_velocity` 进程仍使用启动时的旧奖励，
重新启动才会加载这次简化配置；实际行走与停步效果待重新训练/继续训练后验收。

### 2026 年 10 月 29 日 T049 平地行走奖励对齐官方

按用户本轮要求，仅修改 `HtDuck-Flat-Velocity`：新增身体 xy 角速度平方代价（−0.05）、
全身角动量平方代价（−0.02）、落足摆动峰高代价（−0.25，目标 0.02 m），以及头部 1 s
有符号误差 EMA 的绝对值均值代价。头部偏差权重按官方在 0/600/1000/1500 迭代为
0/−1/−2/−3；本地采用非负原始代价配负权重，与官方负量配正权重数值等价。
足高改为对地高度绝对误差乘水平速度，滑动改为接触脚水平速度平方；二者及峰高均对纯转向启用，
零指令关闭。新增的足端地形 ray 只用于奖励，检查了机器人 geom 不混入地形 ray 分组。

原始公式直接复用 mjlab 1.6.0，与官方固定提交 `bae39f59` 继承的 mjlab 1.3.0 五项实现
逐项 AST 比较一致；只给有状态峰高补上局部 reset，并将头部 EMA 适配为 manager 管理的类式项。
姿态任务的足端公式、61/64/14 布局、`.25` 行走动作缩放、HOME 头目标、`stand_still`、
机器人、电机与 PPO 参数保持现值。来源、单位和文件分工见[设计说明](design/skill_task_migration.md#2026-10-29-平地行走奖励对齐官方)。

验证：

- 新增 17 个专项测试，覆盖平方/绝对值的区别、接触与左右脚对应、零速/阈值/纯转向、落足结算、
  恒定头偏差与零均值振荡、命令变化、真实 RewardManager 局部 reset、课程边界和姿态任务隔离。
- `make docs` 与 `make check` 通过：244 passed + 8 subtests，锁文件、Ruff、模型和差异空白检查通过。
- GPU：`timeout 300s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0 --num-envs 4 --steps 150`，
  种子 0、50 Hz、项目内 TMPDIR/Warp/Torch 缓存。61/64/14 不变，17 奖励项可调用；
  ray 全部命中地形，右脚抬高 `0.00505 m` 时左脚不变；身体角速度/角动量/足高/滑动在真实运动状态
  均有限且为正代价，静止足端代价为 0、纯转向启用。头部 `.1 rad` 恒定偏差经过 50 次采样得到
  `.063583 rad`，权重四阶段正确；峰高与 EMA 局部 reset 不影响邻居。2 s 零动作 0/4 终止，
  150 随机步数值有限，强制翻倒检出 4/4。滑动专项先让 HOME 接地再注入运动，避免把初态脚底
  `.4 mm` 余隙下的零接触误当公式失效。日志：`logs/official_walking_rewards_20261029/env.log`。

真实入口短跑：

```bash
timeout 300s uv run --no-sync duck-train HtDuck-Flat-Velocity \
  --env.scene.num-envs 16 --agent.max-iterations 5 --agent.seed 0 \
  --agent.run-name official_rewards_smoke --log-root logs/official_walking_rewards_20261029/train
```

cuda:0 正常退出，共 1,920 个环境转换，最后一轮 loss 有限、`nan_state=0`；
检查点 `train/flat_velocity/2026-10-29_14-47-59_official_rewards_smoke/model_4.pt`、
`params/{env,agent}.yaml`、源码快照与 `train.log` 保留在上述实验根目录。
CPU 加载检查点后，全部 76 个张量（其中 74 个浮点张量）有限，结果见同目录 `checkpoint_check.json`。
短训尚未到第 600 迭代，头部偏差非零阶段由 GPU 专项另行验证。

独立复核记录见[审查追加节](review/skill_task_migration.md#平地行走奖励对齐官方复核)。
只读审查者 `reward_reference_review` 结论为独立审查通过，本轮范围无阻塞或一般问题。
本轮短跑只验证训练与奖励路径，不作为稳定行走或跟踪改善的证据；固定指令定量评估仍待完成。
用户原有训练进程及实验产物均保留，后续新启动或恢复训练才会加载本轮配方。


### 2026 年 10 月 29 日 T050 一键安装 .venv

新增可执行的根目录 `setup.sh`，参考 `quadruped_lab/setup.sh` 的 uv/Python 准备、代理传递与
项目环境固定方式，复用本项目 `tools/setup_env.py` 执行锁定依赖同步。默认精确匹配 Toolkit，
支持 `--torch-backend`/`--backend`、`--cuda-home`、`--no-dev`、`--no-export` 与不安装任何工具的
`--dry-run`。uv 缺失时走官方安装器且不修改 shell 配置；无可用系统 Python 时通过 uv 准备 3.12。
即使从其他目录调用、设置了外部 `UV_PROJECT`/`UV_WORKING_DIR`/`UV_PROJECT_ENVIRONMENT`
或激活了其他环境，目标仍为本仓库 `.venv/`。非法参数在工具安装前拒绝，失败保留退出码。
README 与安装文档已更新；依赖声明和锁文件未因本任务改动。

验证：

- `bash -n setup.sh`、`bash setup.sh --help` 与 `bash setup.sh --dry-run` 通过；
  本机预览精确选中 Toolkit 13.0 对应的 `cu130`。
- `tests/test_setup_sh.py` 新增 17 项无网络隔离测试，通过真实 Python 安装器调用假 uv，覆盖
  工具引导安装、缺少工具时的预览、路径含空格/外部工作目录、环境固定、代理、CUDA 精确匹配与失败码。
- 真实执行 `timeout 300s bash setup.sh` 退出 0，使用项目内 TMPDIR 与无字节码模式；
  按锁文件解析 222 个包并更新本项目可编辑安装，保留既有 `.venv`。
  `uv run --no-sync python -B` 核实环境路径与 Python 3.12.14、mjlab 1.6.0、
  torch 2.14.1+cu130、MuJoCo 3.11.0、Warp 1.18.0，开发与导出依赖可导入；
  PyTorch/Warp 均在 RTX 4060 完成 GPU 分配与同步。
- `make docs`、`make check` 通过：261 passed + 8 subtests，锁文件、Ruff、模型与差异空白检查通过。
  最终归档后的文档链接与任务状态另用 `make docs` 复核。
- 只读独立审查者 `setup_review` 完整核对脚本、专项测试和使用说明，无阻塞或一般问题。
  首次下载 uv/Python 的错误与成功分支由隔离工具验证；本机实测为已有环境同步，未清空环境重装。

本任务无未解决项，不自动提交。T049 的已有实现、实验及用户运行进程保留，后续可继续任务验收与定量评估。
本次临时检查产物与字节码按项目约定清理；任务范围原文移入[任务归档](archive/development_tasks.md#t050-参考-quadruped_lab-增加一键安装-venv-入口)。

### 2026 年 10 月 29 日 头颈联动平地速度任务

用户要求另做一个按官方方法、上半身会动的 task。本轮新增本地
`HtDuck-Flat-Velocity-Head`，作为当前 T051 下的独立并发子工作；远端部署状态、依赖修订与
其他会话的产物保持原样，本轮验证不作为新增环境已上传远端的证据。

新任务采用官方 `microduck_rl@bae39f59` 的普通 head/body 指令，均每 2–5 s 重采样、
零指令概率 0。头部范围在 0/500/1000/1500/2000 迭代逐步扩大，最终 pitch ±1.1、yaw ±1.4、
roll ±.31 rad。躯干小范围指令填入原 6 维槽，不装配躯干跟踪奖励，数值等价官方 weight=0；
躯干维持自由基座与稳定性约束。以官方腿部 `variable_posture` 替代新任务的全关节 `stand_still`，
避免零速时头部被拉回 HOME；旧 Velocity 保留其原配方。

观测/动作保持 61/64/14、float32、50 Hz、原顺序；动作采用本机腿部 `.25`、头颈官方 `1.0`
的逐关节字典缩放。PPO 不变，日志独立写 `flat_velocity_head`。新工厂对基础配置做深拷贝，
仅替换 body 命令观测槽，避免重新引入共享关节选择器。新任务专用 runner 只在上游 load 后
reset 环境，立即按恢复的计数器刷新课程；不改 PPO 或检查点格式。
范围、上游对应和本机适配见[设计](design/velocity_head_task.md)。

验证：

- 新增课程与配置专项测试共 15 项，覆盖 live command 更新、阶段前后、4/6 维槽位、局部 reset、
  新旧配置/registry/RL 隔离、头部限位、腿部姿态不约束头部，以及实际注册 runner 的选择。
- `make docs` 与 `make check` 通过：276 passed + 8 subtests，锁文件、Ruff、模型及差异空白检查通过。
- GPU：`timeout 300s uv run --no-sync python -B tools/check_velocity_head_env.py --device cuda:0 --num-envs 4 --steps 150`，
  cuda:0、种子 0、项目内 TMPDIR/Warp/Torch 缓存。五阶段采样范围正确，非零 head/body 命令
  实际进入 actor/critic；14 个关节逐一验证缩放、路由和编码器偏置补偿。匹配非零头目标时，
  腿部 pose=1、head tracking=1、EMA=0。1 s 固定动作通道测试中四头颈峰值运动分别为
  `.1484/.1243/.1292/.1200 rad`、0/4 终止，嘴漂移 `.00027 rad`；150 随机步观测与奖励有限。
  这段是执行通道检查，不是学成策略的回放。最终日志为 `logs/velocity_head_20261029/env_final.log`。

正式短跑（300 s 上限，GPU 16 环境、种子 0、24 步 rollout）：

```bash
timeout 300s uv run --no-sync duck-train HtDuck-Flat-Velocity-Head \
  --env.scene.num-envs 16 --agent.max-iterations 5 --agent.seed 0 \
  --agent.run-name head_smoke_final --log-root logs/velocity_head_20261029/train
```

正常退出，共 1,920 个环境转换，最终 loss 有限、`nan_state=0`。
检查点为 `logs/velocity_head_20261029/train/flat_velocity_head/2026-10-29_15-56-39_head_smoke_final/model_4.pt`，
同目录保留 `params/{env,agent}.yaml` 与 Git 快照；实验根目录保留 `train_final.log`、
`checkpoint_check.json`、`source/` 的 29 份源码/配置副本与 SHA-256、实际安装版本清单。
CPU 加载后全部 76 个张量（74 个浮点张量）有限，保存的环境步为 120。

恢复检查：同一 GPU 工具加 `--checkpoint-file` 指定上述真实权重，经过注册 runner 的
actor-only load 后立即读取课程与观测，再运行 10 步推理，结果有限；无需外部手动 reset。
另通过仅用于验证的临时 checkpoint 元数据，覆盖 500/1000/1500/2000 迭代的 load 即时恢复；
这些不是训练到对应迭代的策略，临时文件交付前删除。日志为 `logs/velocity_head_20261029/restore.log`。

独立问题与复核见[审查记录](review/velocity_head_task.md)：审查者 `velocity_head_review` 判定独立审查通过，
1 项配置共享问题已修复并复核关闭；独立复跑 15 项专项测试，确认 29 份源码/配置快照哈希一致。
完整训练及固定指令下行走/头部联合
效果仍待验证；本轮只交付可训练、可恢复的新任务，不把短跑作为策略收敛或实机效果的证据。


### 2026 年 10 月 29 日 T051 远端环境部署子工作

已通过 JumpServer 将本轮冻结的工作区快照部署到资产 1：XN-4090-GPU1，
目录 `/data/hupeiyan/projects/HT_microduck_lab`，独立环境为该目录的 `.venv/`。
快照取自 `9840fa8` 上的当前未提交实现：129 个现存文件、16 个 STL、32 个 RSL-RL 文件，
未上传本机环境、缓存、Git 历史和训练产物，已删除的 `_fallback.py` 未回灌。
上传开始后另一会话新增的 Head 任务仅在本地交付，不属于此远端快照。
部署结果与本地 Head 子工作各自完成且分别通过独立审查后，汇总关闭 T051；未将 Head 发布远端。
原任务范围保持措辞移入[任务归档](archive/development_tasks.md#t051-上传项目到-xn-4090-gpu1-并安装环境)。

依赖适配：远端为 Toolkit 12.8.93、驱动 570.124.06。默认 Warp 1.18.0 wheel 使用 CUDA 13.4、
要求 R580，依据 NVIDIA 固定版本安装说明，为 `cu118/cu126/cu128/cu129` 选择官方同版本
`1.18.0+cu12` wheel；`cpu/cu130` 保留 NVIDIA 源。同步修改 `pyproject.toml` 和 `uv.lock`，
逐一导出六个后端确认来源选择，除 Warp 构建/来源外，锁定包的名称与版本集合不变；
本机 `cu130` 离线重新安装通过。来源与驱动要求见[安装说明](setup.md#2-依赖同步与后端选择)。

下载准备：服务器 GitHub 连接超时、清华镜像返回 403。将本机已有的 Python 3.12.14 与官方
Warp URL 对应的真实 uv wheel 缓存传入服务器；Python 单独装入受管目录，未复制本机 `.venv`。
其余依赖使用阿里云下载地址预热缓存，按锁文件保留 SHA256；临时下载覆盖仅允许
`package.wheels/sdist.url` 变化，恢复这些字段后整份 TOML 与原件全等，包来源、版本、标记和哈希均未改变。
缓存准备结束后恢复原始 `uv.lock`，再执行正式安装器，未把镜像覆盖保留到交付锁文件。

验证与产物：

- 正式命令：`UV_CACHE_DIR="$PWD/.cache/uv" UV_OFFLINE=1 timeout 180s bash setup.sh --cuda-home /usr/local/cuda-12.8`，
  精确选择 `cu128`、`uv sync --locked --python 3.12 --extra cu128 --extra export` 退出 0。
  锁文件 SHA256 为 `28f1e0178969022ad9f3e0697ed85107c792a689c08b9e9be1127158f525cfae`，与本机完全一致。
- Python 3.12.14、mjlab 1.6.0、PyTorch 2.11.0+cu128、MuJoCo/MuJoCo-Warp 3.11.0、
  Warp 1.18.0+cu12、开发和 ONNX 依赖导入通过。`rsl_rl.__file__` 来自远端仓库；
  Warp 的 `direct_url.json` 为官方 GitHub URL，4 个原有任务可用。
- `CUDA_VISIBLE_DEVICES=GPU-450c3470-1f63-9d53-43d4-366538571ecf` 选择物理 GPU 1。
  PyTorch GPU 矩阵乘与 Warp GPU 填充/回读通过；随后运行
  `timeout 600s uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0 --num-envs 4 --steps 20 --seed 0`，
  退出 0，完成真实 CUDA JIT。Warp 报 Toolkit 12.9 / Driver 12.8，61/64/14 布局正确，
  100 步保持 0/4 终止、20 随机步有限、强制翻倒 4/4 检出；地形射线、奖励与局部历史重置检查通过。
- 远端 `make lock-check lint test model docs` 退出 0：260 passed、1 skipped、8 subtests passed；
  跳过项为未上传 `.git` 时的 Git 快照用例。模型为 15 关节、16 网格；文档 19 文件、118 链接、52 任务。
  本地最后一次 `make check` 通过 276 tests + 8 subtests（含并发新增 Head 测试），文档 21 文件、129 链接。
- 远端 129 个源码文件逐一 SHA256 匹配，清理后复核仍通过；清单摘要为
  `c0eaa40d33c90a95bfdb0357a5e182b3f9aaee98ce027976a88f4e33ac79c4d8`。
  相对冻结快照恰好只有安装相关的 `pyproject.toml`、`uv.lock`、`docs/setup.md`、`docs/development.md` 四文件变化。
- 只读独立审查者 `remote_review` 核对包、清单、锁文件和回传运行日志，部署子工作独立复核通过，
  无阻塞或一般问题；本地 Head 子工作沿用其自身的 `velocity_head_review` 通过记录。

服务器保留 `logs/deployment_20261029/` 下的安装、版本/来源 JSON、GPU、检查、任务列表、
源码清单与部署元数据，作为运行证据；保留 `.cache/uv` 供离线同步，`.cache/warp` 与 `.cache/torch`
供后续仿真复用。临时传输包、专项临时目录、检查缓存与源码字节码清理；已有用户训练与实验未改动。
未执行远端训练、Git 提交或推送。下一步可在空闲 GPU 启动短训练；新 Head 任务若要远端运行需另行同步。


### 2026 年 10 月 29 日 T052 任务目录整理与训练等价

参考本机 `legged_wbc_mjlab@4eb8fcf71124b20ed4a1154b6c724ba962a424f8`，将 `tasks/` 根目录
收敛为注册与契约；五个环境、RL 与地形配置放 `config/`，全部任务共用一个 `mdp/`，
Head runner 放 `rl/runner.py`。MDP 包按 commands、curriculums、events、observations、
rewards、posture 分文件，原函数/常量、PPO 和课程参数原样迁移。更新 3 个工具与相关测试导入、
README 和设计说明，不改变 task ID、CLI、61/64/14、50 Hz、动作缩放或检查点格式。

验证与证据保留在 `logs/task_layout_20261029/`，用于复查目录调整前后的训练等价：

- 五任务 train/play/RL/runner 完整配置快照字节相同（只规范化声明的模块路径），
  包含字典顺序、所有属性、函数默认参数与补零闭包；13 个原模块定义/常量及拆出的 RL/runner AST 相同。
- 正式入口各任务迁移前、迁移后与同版重复对照共 15 次 GPU 短跑，均退出 0；
  cuda:0、seed 0、16 环境、24 步 rollout、2 迭代，每次 768 个环境转换、timeout 300s。
  命令模式为 `timeout 300s uv run --no-sync duck-train <task> --env.scene.num-envs 16 --agent.max-iterations 2 --agent.seed 0 --agent.run-name layout_parity --log-root logs/task_layout_20261029/<phase>/train`，
  各次精确命令与退出码见 `<phase>/runs.json`，环境/模型/优化器状态均有限。
- GPU 前后权重并非逐位相同，同版重复也有差异；本机 mjlab `utils/random.py:9–14` 已注明
  MuJoCo Warp 尚非完全确定。追加固定采样对照：CPU、torch seed 0、独立数据 seed 713、1 线程、
  确定性算法、每任务 2 次真实 Runner/PPO 更新；迁移前从源码快照加载任务，其余依赖来源相同。
  五任务各 76 个模型/归一化/优化器张量，以及 48 步动作，全部逐位相同，见 `comparison.json`。
- 五任务迁移前检查点在新目录下全量加载（含优化器、iter=1、环境计数48），GPU 4 环境各
  10 步推理的动作/观测/奖励有限。Head 的 0/500/1000/1500/2000 迭代元数据恢复后课程立即正确；
  后期元数据仅用于验证，临时权重删除，不将其描述为后期训练策略。
- 新增 16 项 registry 测试，`make docs`、`make check` 通过：292 passed、8 subtests，
  锁文件、Ruff、模型和差异空白检查均通过。
- 独立审查者 `task_layout_review` 对照原快照与最终代码，独立复跑 71 项专项测试并复核数值证据，
  结论为**独立审查通过**；1 项延迟注解保留建议已处理，无阻塞/一般问题。
  详见[设计结果](design/task_layout.md#实测结果)与[审查记录](review/task_layout.md)。

本轮无未解决项，固定数据下训练等价，不承诺 GPU 位级复现或完整训练效果。
旧 Python 内部 import 路径已迁移，旧 params YAML 作为历史记录保留；正式入口不从该 YAML 重建任务。
保留已有改动、删除和实验产物，默认交付工作区，不提交 Git。
下一步可接续 T049 的姿态技能任务验收，再按条件推进固定种子定量评估；本次不开展额外训练。
本轮临时检查脚本、缓存与字节码在所有代理/检查结束后清理；原任务范围归档到
[任务条目归档](archive/development_tasks.md#t052-整理-tasks-目录并验证训练等价)。


### 2026 年 10 月 29 日 T053 同步最新训练代码到远端

已将当前工作区训练代码更新到 XN-4090-GPU1 的
`/data/hupeiyan/projects/HT_microduck_lab`，包含 T051 的 Head 任务和 T052 的
`tasks/config`、`tasks/mdp`、`tasks/rl` 目录。五任务 ID 与训练 CLI 保持现有定义；
本轮不修改训练配方、依赖声明和锁文件，也不启动训练。

同步前实际枚举远端源码与 SHA256，确认项目目录只有交互 bash、没有活动 Python/uv 训练进程。
现有训练输出 `logs/rsl_rl` 保留；上次部署日志已由用户移除，本轮未恢复该目录。
当前快照 143 文件，上传 38 个新增/变化文件；按明确的迁移清单移除 11 个旧根模块，
包括 `tasks/mdp.py` 和原根目录的环境配置、commands/curriculum/shared/posture/terrain，
避免新包和旧路径并存。应用前逐项验证旧哈希与新增路径不存在，备份 24 个被替换/移除的原文件，
再替换源码；未对环境、缓存和用户实验目录使用删除同步。

验收与证据：

- 上传包 SHA256：`9c74f7d2244d4a1a4ba5155a4335f3250bee296298f76eef37a1792e411bf794`；
  初始 143 文件清单摘要 `f8491af3e646ceaa355b9992904b9ab468b3e933e7dccfebcaad9f402b62903d`，
  远端逐文件核对通过，11 个旧路径均已不存在。
- 原文件备份：远端 `logs/code_update_20261029_T053/backup.tar.gz`，24 个成员逐一与同步前哈希一致，
  包摘要 `1037578e158455ed8b40537fa0afccea0f81a7d7941163992b530555dd2fbe20`。
- `pyproject.toml` 与 `uv.lock` 的哈希和远端既有版本一致；正式离线
  `bash setup.sh --cuda-home /usr/local/cuda-12.8` 退出 0，复用原 `.venv`，
  PyTorch 2.11.0+cu128、Warp 1.18.0+cu12 保持现值。
- 五任务 train/play/RL 配置可加载，Head 注册 runner 来自 `ht_microduck.tasks.rl.runner`；
  `rsl_rl.__file__` 来自远端仓库。旧根模块 `find_spec` 均为空；
  `uv run --no-sync duck-train HtDuck-Flat-Velocity-Head --help` 退出 0。
- 物理 GPU 1（UUID `GPU-450c3470-1f63-9d53-43d4-366538571ecf`）执行
  `timeout 600s uv run --no-sync python -B tools/check_velocity_head_env.py --device cuda:0 --num-envs 4`，
  seed 0、默认 150 随机步，退出 0。61/64/14 与 50 Hz 正确，五阶段课程、局部 reset、
  十四关节隔离映射和非零头目标奖励通过；1 s 头部动作峰值约 `.148/.124/.129/.120 rad`，
  嘴漂移 `.00027 rad`、0/4 终止，随机步观测与奖励有限。
- 远端 `make lock-check lint test model docs` 退出 0：291 passed、1 skipped、8 subtests；
  跳过项为没有 `.git` 时的快照检查，模型为 15 关节/16 网格，文档 23 文件/145 链接/54 任务。
  本地 `make docs`、`make check` 通过：292 passed、8 subtests，Ruff、锁文件、模型和差异空白检查通过。
- 独立只读审查者 `code_sync_review` 核对上传内容、迁移清单、原备份及远端回传结果，
  独立复核通过，无阻塞或一般问题。
  任务归档后仅追加同步开发记录与任务归档两份文档，并重新核对最终清单；源码仍为已验证快照。

远端保留 `logs/code_update_20261029_T053/` 的原源码备份、更新清单、安装/注册/CLI/GPU/检查日志，
最终 143 文件清单为该目录的 `source.sha256`，原始上传清单另存 `source-upload.sha256`。
临时传输与检查文件、源码字节码在检查和代理结束后清理；原 `.venv`、`.cache`、用户日志与进程保留。
本轮无未解决项，无 Git 提交或推送。下一步可在选定空闲 GPU 运行最新 Head 任务的正式训练命令。
任务原范围见[任务归档](archive/development_tasks.md#t053-将最新训练代码同步到-xn-4090-gpu1)。


### 2026 年 10 月 29 日 T054 完整迁入参考开发工作流

按用户要求，将本机 `quadruped_lab/AGENTS.md` 的全部通用规则及配套流程、协作规范、
设计/审查模板迁入本仓库；统一中文代码注释与文件头、英文日志、按影响维护文档、
四类依据、完整复现基准及确认边界、训练测试先行、至少 600 秒实际本地训练和结束后统一分析。
目录、运行入口与 TensorBoard 指南映射本项目实际位置；保留单一 `rsl_rl/`、
正式测试纳管、项目内临时目录及已有任务历史，不迁入参考仓库忽略整个测试目录的策略。
README 仅更新导航，旧流程审查记录追加历史说明。

验证：`make docs` 与 `make check` 均退出 0；292 passed、8 subtests，
锁文件、Ruff、模型和差异空白检查通过。只读审查者 `workflow_audit` 逐节对照参考文件，
独立复核通过，无阻塞或一般问题；全部既有任务行、阶段内容、原任务详情和完成记录均保持原文。
任务结束时仅将 T054 的状态更新并搬移本条目标与验收，见 [任务归档](archive/development_tasks.md#t054-完整迁入-quadruped_lab-的开发工作流)。

本轮只修改文档，未新增测试或开展训练，不将旧短跑追记为达标训练；未执行 Git 暂存、提交或推送。
本次临时快照、检查缓存与字节码在代理和检查结束后清理。无未解决项。
下一步可接续 T049 的姿态技能任务验收，其后按条件推进固定种子定量评估。


### 2026 年 10 月 29 日 T055 对齐官方任务并保留 VelStand

按用户要求保留 `flat_velstand_env_cfg.py`，四个其余现有任务迁入官方
`microduck_rl@bae39f59` 的命令、观测、奖励、重置、终止、课程与动作映射；用户明确选择保留
HT仿真实测姿态和高度。两个Velocity任务为同一配方的独立ID/日志，critic76维；StandUp/SitStand
critic74维，actor61、动作14、scale1、50Hz。VelStand文件哈希、旧MDP及train/play/RL完整配置相同。
细节、来源和适配见[设计最终结果](design/skill_task_migration.md#t055-最终冻结配方验收)。

验证：make check通过340 tests和8 subtests；四任务GPU各4环境150步、实际DR列隔离、后期课程，
三个不同配方正式CLI短跑及最终各至少600秒实际采样/PPO更新通过，最终三次全流程退出0。
最终checkpoint、源码冻结与全部张量有限性、新环境全量恢复/10步推理、名义躺姿及Head别名工具检查通过。
首次同环境恢复失败和R4修正前产物保留为诊断；最终证据保留在
`logs/official_task_alignment_20261029/acceptance.json` 与同目录日志/配置/检查点，未读取运行中的指标。
只读审查者official_task_review复核四项问题及最终证据，结论为
[独立审查通过](review/skill_task_migration.md#t055-最终结论与冻结证据)。

本轮无未解决的实现项，不将有限训练当作技能收敛或实机验收；下一步可开展新配方的固定指令定量评估。
保留用户已有改动、删除和实验，未提交Git或同步远端；任务正文原措辞移入
[任务归档](archive/development_tasks.md#t055-除-velstand-外逐项对齐官方任务)。


### 2026 年 10 月 29 日 T056 再次同步当前训练代码

已将 T054/T055 后的工作区快照同步到 XN-4090-GPU1 原目录
`/data/hupeiyan/projects/HT_microduck_lab`。160 个源文件逐项哈希通过；更新 44 文件
（27 个既有文件、17 个新增文件），无旧文件删除。官方 MDP 的 NOTICE/LICENSE 一并上传，
VelStand 配置、六个旧 MDP、RSL-RL、依赖声明和锁文件与远端前态哈希一致。
更新前确认无项目 Python/uv 进程，核对旧哈希和新增路径，并备份原 27 文件；
保留 `.venv`、`.cache`、`logs/rsl_rl` 和 T053 的已有备份。

运行证据保留在远端 `logs/code_update_20261029_T056/`：`backup.tar.gz` 为原源码备份，
`plan.json` 与 `source.sha256` 为部署清单，注册、CLI、四任务 GPU 和完整检查日志同目录保存。
原备份 27 成员已独立逐项核对，清单记录原始与更新后哈希。正式离线
`bash setup.sh --cuda-home /usr/local/cuda-12.8` 退出 0，仍为 Torch 2.11.0+cu128、Warp 1.18.0+cu12；
五任务 train/play/RL 和 runner 加载通过，训练入口 `duck-train HtDuck-Flat-Velocity --help` 退出 0。

- 本地 `make docs`、`make check` 通过：340 passed、8 subtests，锁文件、Ruff、模型与差异检查通过。
- 远端 `make lock-check lint test model docs` 退出 0：339 passed、1 个 Git 快照跳过、8 subtests；
  模型 15 关节/16 网格，文档 23 文件/160 链接/57 任务。更新完成记录后另复核文档和最终清单。
- 物理 GPU 1 用 UUID 选择，每任务执行
  `timeout 600s uv run --no-sync python -B tests/test_official_task_training.py env --task <task> --device cuda:0 --num-envs 4 --steps 150 --seed 0`。
  Velocity、Velocity-Head、StandUp、SitStand 四次均退出 0；actor61/action14，critic 分别76/76/74/74，
  dt=.02，动作映射、实际 DR 列隔离、局部 reset、射线与后期课程有限值通过。
- 只读独立审查者 `code_sync_review` 核对来源快照、备份、上传清单及真实远端结果，
  独立复核通过，无阻塞或一般问题；最终仅补同步开发记录和任务归档两文档，源码不再变化。

本轮仅验证部署和仿真，未启动训练，不将这些环境检查称为至少 600 秒的训练验收。
四个新配方不能用上一版 64 维 critic 权重完整恢复；保留的 VelStand 不受该配方变更影响。
临时传输、检查目录及源码字节码在所有检查和审查结束后清理，保留上述备份与日志。
无未解决部署项，未提交或推送 Git。下一步可用新配方启动独立训练。
任务原范围见[任务归档](archive/development_tasks.md#t056-再次同步最新训练代码到-xn-4090-gpu1)。


### 2026 年 10 月 30 日 T057 恢复机制与 HT 高度适配

完成官方非热启动恢复窗口、绝对初态与站立余量、局部势函数reset、身体相对目标与腾空门控，
以及SitStand的HT高度映射。基础检查380项/8子测试、两个GPU环境与控制状态机专项通过，
独立审查及运行证据复核通过。两个16环境seed0实验各完成超过600秒采样与PPO更新，
检查点在新环境全量加载并推理10步通过；原日志和检查点保留。

证据与具体限制见[同主题设计结果](design/skill_task_migration.md#t057-实施与验收结果)和
[审查记录](review/skill_task_migration.md#t057-最终复核结论)，产物在
`logs/posture_recovery_20261030/`。VelStand仅483更新，未实训500后的恢复课程，
后期逻辑由专项检查覆盖；本阶段不代表策略收敛或完成专家蒸馏。
