# 功能设计：姿态技能迁移（起立 / 坐站 / 行走站立）

关联 [任务表](../development.md) 的 T049。本文不重复维护任务状态。

目录在 T052 按[任务目录整理设计](task_layout.md)迁移：环境/RL/地形配置位于 `tasks/config/`，
commands、curriculums、events、observations、rewards、posture 位于统一的 `tasks/mdp/`。
下文原路径保留当时设计与实验上下文，行为和训练参数不变。

## 目标与范围

### 当前问题

本仓库此前只有一个任务 `HtDuck-Flat-Velocity`：10 个腿部执行器、39 维 actor 观测、无姿态指令。
用户要求按官方 `pollen-robotics/microduck_rl` 的任务族补齐三个姿态技能任务：

- `Mjlab-VelStand-{Flat,Rough}-MicroDuck`：一条策略覆盖行走 + 零指令站立 + 保护性跌倒 + 自主起身 + 站立躯干姿态；
- `Mjlab-StandUp-{Flat,Rough}-MicroDuck`：坐姿 keyframe → 站立 + 躯干姿态指令；
- `Mjlab-SitStand-{Flat,Rough}-MicroDuck`：受令 sit↔stand，头部可指令。

### 完成后可观察的结果

- 四个任务都在 `duck-train`/`duck-play` 中可见、可训练、可回放，共享同一观测与动作契约。
- 三个新任务的奖励、终止、reset 与命令槽位按官方结构实现，数值换成本机实测。
- 现有 `HtDuck-Flat-Velocity` 在新契约下继续可用（需重训，见兼容性）。

### 本次范围

新增：`contract.py` 契约扩展、`posture_mdp.py`、`posture_events.py`、`commands.py`、
`curriculum.py`、`terrain.py`、`shared.py`，三个任务配置文件与注册。
修改：`flat_velocity_env_cfg.py`（适配新契约）、`__init__.py`（注册与契约守卫）。

### 不在本次范围

- Rough 变体的地形参数标定与训练验收（本次只提供地形配置与任务能否构建的验证）。
- 教师策略蒸馏（`distill.py`）：本机没有官方教师检查点，按用户决定从零训练。
- 实机部署、`duck-eval` 定量评估（属 T027/T028）。
- 三个姿态技能的完整训练；2026-10-29 用户要求修复行走后，Velocity 的有界训练验证纳入本轮。

## 依据与假设

| 判断 | 依据类型与位置 | 适用差异或缺口 | 最小验证与通过条件 |
|---|---|---|---|
| 官方任务族含 VelStand/StandUp/SitStand 三族，共享 61 维 actor 观测与 14 执行器动作 | 参考项目：`pollen-robotics/microduck_rl` `develop` 分支 commit `bae39f59`（2026-10-27），`tasks/*_env_cfg.py` 与 `microduck_constants.py` | 官方基于 mjlab 1.3.0 / rsl_rl 5.0.1；本机 mjlab 1.6.0。curriculum API 与命令项签名不同 | 三个任务在 1.6.0 下构建成功并跑通短训练：已通过 |
| 命令槽位固定宽度（twist 3 / head 4 / body 6），未使用的槽位补零而非删除，以支持统一运行时输入 | 参考项目：同上 `tasks/__init__.py` 与各 `*_env_cfg.py` 的 observation 定义 | 本机执行器数 14 与官方相同，但观测块宽度由 14 关节决定；切换策略还须同时选择任务的动作映射 | `ACTOR_OBSERVATION_DIM == 61` 且四任务实测一致：已通过 |
| 本机有 14 个可驱动关节（10 腿 + neck_pitch/head_pitch/head_yaw/head_roll），嘴保持 HOME | 本地事实：`robot/ht_microduck_constants.py` 的 `JOINT_NAMES`、`HELD_JOINT_NAMES`；`HT-DK_URDF.xml` 关节范围 | `mouth_joint` 行程仅 0.23 rad 且为最低带宽舵机，无平衡作用 | `contract.validate_contract()` 断言 14+1=15 关节覆盖：已通过 |
| 本机存在可保持的坐姿：膝盖**前折**（`calf=+0.40`）、机器人坐在髋部上、脚离地 | 本地实测（T049，`.artifacts/t049/verify_sit5.py`）：130 个限位内候选，唯一存活的低位族群；6 s 保持 `z=0.0563`（std 2.5e-4）、倾角 1.3°、峰值力矩 0.88 N·m（限 3.7）、零漂移 | 官方 sit keyframe 针对 800 g 双足；本机 `calf` 取正值才是折叠方向。先前的 167 组扫描只试 `calf<0` 并强加平脚约束，排除了整个可行方向（错误已更正） | 见下方“坐姿实现”说明与验收项 |
| 倾角可判定跌倒，倾角+高度可判定站起 | 本地实测：站姿倾角 4.3°、躯干 0.1502 m；坐姿 1.3°/0.0563 m；地面姿态 ≥79°、躯干 0.060–0.093 m | 官方门限同样是实测值，但绝对高度不可移植。代码实际取值：终止 40°（`TERM_GATE_TILT_DEG`）、倒地判定 60°（`C.FALLEN_TILT`）+ `C.FALLEN_Z=0.110`（两者取**与**）、站起 25°（`C.RECOVERED_TILT`）+ `C.RECOVERED_Z=0.130` | 短训练中奖励有限、无 NaN：已通过 |

### 坐姿实现（影响方案选择的假设）

用户指示“按官方的来”，机制全部保留、数值按本机实测：`SitStand` 是“受令在站立与低姿态之间切换”，
`StandUp` 是“从低姿态 keyframe 起立”，`VelStand` 是五族合一。

坐姿是通过**真实动作通道保持 6 s** 验证的（不是运动学推断，也不是瞬移）：

| 量 | 实测值 | 说明 |
|---|---|---|
| `hip_pitch` | +1.55 rad | 接近 ±1.571 限位 |
| `calf` | **+0.40 rad** | 正值：膝盖前折，这是关键方向 |
| `ankle` | +0.35 rad | 脚离地，不承担支撑 |
| `hip_roll` | ±0.0873 rad | 与 HOME 相同 |
| 躯干高度 | **0.0563 m** | std 2.5e-4，6 s 零漂移 |
| 倾角 | **1.3°** | 直立坐在髋部上 |
| 峰值力矩 | 0.879 N·m | 限值 3.7 N·m |

**一个必须记住的反直觉事实**：坐姿（0.0563 m）比任何躺姿（0.060–0.093 m）都**低**。
因此“低”不能判为“倒”，倒地判定必须由**倾角**主导（坐 1.3° / 站 4.3° / 所有实测倒地 ≥79°），
高度只作穿地保护。这条约束已写进 `contract.py` 与 `posture_mdp.fallen_mask`（两门限取**与**）。

**本机没有靠脚支撑的深蹲**：130 个候选里 0 个存活，脚底倾角实测 91–170°（脚底朝天）。
若后续需要脚支撑坐姿，需改执行器或腿长，而非重调参数。

## 模块、接口与兼容性

| 文件或模块 | 职责与依赖 | 输入输出或配置 | 兼容性与异常 |
|---|---|---|---|
| `tasks/contract.py` | 唯一契约来源；被任务、导出与部署读取 | 关节顺序 14、动作 14、观测 61/64、命令槽位切片、姿态高度常量；纯行走缩放 .25、姿态技能 1.0 | **破坏性变更**：actor 由 39 维变 61 维、动作由 10 变 14。旧检查点不可加载，需重训；同维度策略切换仍需匹配动作缩放 |
| `tasks/shared.py` | 四任务共用的观测/传感器构造，防止槽位漂移 | `actor_terms`/`critic_terms` 按契约顺序返回 term 字典 | 命令名参数可选；未使用的槽位用 `zero_command_padding` 补零 |
| `tasks/commands.py` | `head_pose`/`body_pose` 命令项 | `dim` 字段固定槽位宽度；`UniformPoseCommand`、`StandingGatedPoseCommand` | 宽度与契约不符时构造即报错 |
| `tasks/posture_mdp.py` | 姿态奖励、终止、命令项 | 势函数型进度项、代价项、姿态跟踪项、`SitStandCommand` 斜坡 | 代价项约定：函数返回非负值配负权重；函数已返回负值的配**正**权重，调用点注明 |
| `tasks/posture_events.py` | 姿态 reset 事件 | `reset_to_sit`/`reset_to_stand`/`reset_to_ground_state`/`reset_to_stand_with_sit_blend` | 根高用实测常量，不做几何求解：碰撞体混合 box 与 mesh，无闭式最低点 |
| `tasks/curriculum.py` | mjlab 1.6.0 缺失的 event 参数 curriculum | `event_param_curriculum` | 只允许 staged `params`；只改参数不改 func/mode |
| `tasks/terrain.py` | 平地与粗糙地形预设 | `FLAT_TERRAIN`、`ROUGH_TERRAIN`、接触上限 | 粗糙地形按本机 1–2 cm 抬脚能力缩小，不用 mjlab 通用预设 |
| `tasks/flat_*_env_cfg.py` | 四个任务配置与 `rl_cfg` | `ManagerBasedRlEnvCfg` + `RslRlOnPolicyRunnerCfg` | 超参沿用官方（512/256/128、PPO 同参），迭代上限 standup/sitstand 15000、velstand 6000 |
| `tasks/__init__.py` | 注册与导入期契约守卫 | `register_mjlab_task` ×4 + `_assert_task_contract` | 槽位宽度或观测顺序漂移时**导入即失败**，不必等到部署 |

### 学习接口

- 观测：61 维 actor（`base_ang_vel` 3、`projected_gravity` 3、`joint_pos` 14、`joint_vel` 14、`actions` 14、
  `command` 3、`head_command` 4、`body_command` 6），critic 加 `base_lin_vel` 3 维 = 64 维。
  顺序由 `contract.ACTOR_OBSERVATION_TERMS` 固定，切片由 `ACTOR_OBSERVATION_SLICES` 提供。
- 动作：14 维关节位置目标，姿态任务为 `target = HOME + 1.0 * action`，
  纯行走恢复 `target = HOME + 0.25 * action`（2026-10-29 修复）。单位 rad/action，
  逐关节编码器偏置仍由 mjlab 动作项补偿。坐起技能保留较大的探索幅度。
- 奖励：行走项沿用原有配方；姿态类新增势函数进度项与代价项，正负号约定见上表。
- 终止：`time_out`、倾角跌倒、`fallen_too_long`（连续倒地超时）、NaN。
- 检查点：与旧 `HtDuck-Flat-Velocity` 不兼容（维度、顺序及自研 Runner 格式均不同）。
  四个任务维度相同，但行走与姿态任务的动作缩放不同，不能只凭形状直接热切换；
  后续导出/部署必须携带对应任务的缩放。当前 61/64/14 权重虽然可加载，修复改变了控制与奖励，
  应从零训练新策略，不能把恢复旧权重视作修复已生效。

### 2026-10-29 行走回归修复

用户观察为「能站住，但不迈步」。本机没有原行走 checkpoint 或训练日志；`9840fa8` 的标题是
「可以走路了」，这里只把其配置作为参考，不据此宣称已恢复相同行走效果。

| 来源/位置 | 本地确认差异或错误 | 修改与验证 |
|---|---|---|
| `9840fa8:src/ht_microduck/tasks/common/contract.py` 的 `ACTION_SCALE`；当前 `contract.py` | 10 腿动作 `.25` 被扩展为 14 动作 `1.0`，初始策略 std 仍为 1 | 仅 Velocity 采用 `WALKING_ACTION_SCALE=.25`；三个姿态任务保留 `ACTION_SCALE=1.0`。观测 61/64、动作 14、顺序、float32、运行设备和 50 Hz 均不变 |
| 同提交 `tasks/flat_velocity/velocity_env_cfg.py` 的 `commands` | 原行走无随机头部姿态，现在增加每 2–5 s 大范围头目标 | Velocity 的 4 维头指令保持零，头关节仍由策略控制并用宽高斯奖励保持 HOME；其余任务保留原范围。保留当前较小传感器噪声，未发现它导致静止的证据 |
| `.venv/lib/python3.12/site-packages/mjlab/tasks/velocity/mdp/rewards.py:209–238`，mjlab 1.6.0 | 上游在 `current_air_time` 落入区间时每步计数，并以线速度范数 + 角速度绝对值门控；本项目却只在落脚计分且漏掉纯转向 | 直接复用上游函数，脚接触传感器启用 `track_air_time=True`；移除手工 `_ht_air_time/_ht_prev_contact`，计时由传感器在物理子步更新并局部 reset |
| 原提交 `push_robot` 与当前 play 配置 | play 的推力间隔从训练的 3–6 s 缩短为 0.5–1 s | 恢复训练/回放一致的 3–6 s |

旧提交本身也有落足恒负的抬脚奖励错误，本轮不回退该错误。直接复用已安装上游源码，
无需增加新的 PPO、动作兼容层或训练流程；机器人模型、执行器及 HOME 参数没有行为差异，维持现值。
落脚稀疏奖励、四倍动作探索和随机头部目标是有代码依据的退化候选，是否足以解释本机策略静止
仍须固定种子/指令回放；不得把单元测试或短跑通过写成学会行走。

### 2026-10-29 零指令持续抬脚修复（已由下节简化方案取代）

用户进一步确认 `vx/vy/wz` 都为零时仍持续抬脚。现有腾空奖励在零指令下确实归零，
但足高/滑动代价也都归零，配置没有直接区分「静止站立」与「原地踏步」。
这是奖励约束缺项的本地代码事实，尚不能据此确认用户所用权重的全部成因。

- 新增 `mdp.idle_feet_cost`：以 `norm(vxy)+abs(wz) <= COMMAND_ACTIVITY_THRESHOLD (.01)`
  作为静止门控，与 mjlab 1.6.0 的腾空奖励互补。每只未接地脚计 1，另计
  `sum((foot_site_velocity / .1 m/s)^2)`，任务权重为 −1；两部分均无量纲。
  `.1 m/s` 和权重均是仿真调参值，不是硬件标定或已收敛结论。
- Velocity 直接启用；VelStand 使用 `posture_mdp.standing_idle_feet_cost`，
  复用现有 smoothstep，在高度 `SIT_Z→RECOVERED_Z`、直立程度 `cos(60°)→cos(25°)`
  之间逐渐生效。高度相对环境原点计算，坐姿/倒地免罚，恢复中连续渐入，避免硬门槛处突然免罚。
- 只约束实际足底接触和足底 site 三轴线速度，不惩罚关节偏离 HOME，不锁头部或躯干姿态指令，
  允许平衡修正。纯转向属于运动，站立代价为 0；足高/滑动代价同步采用含转向的活动门控。
- 上游依据：本机 mjlab 1.6.0 `tasks/velocity/mdp/rewards.py:209–238,385–470`，
  连续腾空奖励和 variable_posture 都根据线速范数与角速绝对值区分站立/运动。
  新足底代价是本项目的适配，不冒称官方已有同一公式。

61/64/14、动作顺序/缩放、float32、设备与 50 Hz 均不变；奖励项改变了训练目标，
必须在新奖励下训练或继续训练，既有 checkpoint 的推理不会因修改奖励立刻停止抬脚。
验证覆盖静止/阈值/微小输入/纯转向、实际足底运动代价、恢复渐入与环境高度不变性，
GPU 实际静止/离地状态的分项比较，以及正式训练入口的有限更新；这不等同于用户策略效果已验收。

### 零指令保持 default_pos（当前方案）

按用户「只加一个静止站立在 default_pos」的要求，移除 `idle_feet_cost`、
足底速度尺度、恢复高度/倾角门控及相关配置。仅在 `HtDuck-Flat-Velocity` 添加
`stand_still`：`sum(abs(q - default_joint_pos))`，只计算 14 个策略关节，权重 −0.5。
当 `norm(vxy)+abs(wz) <= .01` 时生效，平移或纯转向指令时为 0。
默认位置直接读实体数据，不把 `q=0` 当站姿，不增加额外接触或运动条件。
VelStand 撤掉本轮额外站立代价，其他奖励门控恢复到 11:12 基线。
动作/观测接口与其余参数不变；用户运行中的训练进程仍使用启动时已加载的奖励，
重新启动训练才会采用此项。本轮仅做测试和小规模 GPU 检查，不启动新训练。

### 2026-10-29 平地行走奖励对齐官方

用户在只读对比后要求补齐四个奖励项，并对齐滑动与足高公式。本轮只修改纯行走任务；
VelStand 等姿态任务继续使用原来的足端项。机器人、执行器、61/64/14 向量顺序、float32、
设备、50 Hz、`.25 rad/action`、HOME 头指令、`stand_still` 和 PPO 配置保持现值。
检查点形状可兼容，但奖励目标已经改变，旧策略的行为不会因修改源码立即改变；
用户已有训练保持运行，后续新启动或恢复的训练才采用本轮配方。

复现基准为官方 `microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb` 的
[`microduck_velocity_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)、
[`mdp.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/mdp.py)，
以及其继承的 [mjlab 1.3.0 奖励](https://github.com/mujocolab/mjlab/blob/v1.3.0/src/mjlab/tasks/velocity/mdp/rewards.py)。
本机 mjlab 1.6.0 对应公式相同，优先直接复用。

| 官方位置与项 | 本地装配与原始量 | 权重 / 参数 | 差异及验证 |
|---|---|---|---|
| velocity:338，`body_ang_vel` | mjlab `body_angular_velocity_penalty`，`base_link` 世界系角速度 xy 的平方和，`[B]` | −0.05 | 本机躯干名称替换；验证 yaw 不受罚、xy 非零受罚 |
| velocity:339，`angular_momentum` | mjlab `angular_momentum_penalty`，`robot/root_angmom` 三轴平方和，`[B]` | −0.02 | XML 内置传感器由 Scene 自动注册；验证真实数据可读且有限 |
| velocity:351–355，足高/落足峰高 | mjlab `feet_clearance` / `feet_swing_height`，足端对地高度 `[B,2]`，单位 m | −2 / −0.25，目标 0.02 m | 足高为 `sum(abs(h-.02)*norm(vxy))`；峰高在落足时计算 `sum((h_peak/.02-1)^2)`；补上游缺失的局部 reset |
| velocity:312–315，滑动 | mjlab `feet_slip`，接触脚水平速度平方和，`[B]` | −0.1 | 与足高/峰高一起采用 `norm(vxy_cmd)+abs(wz_cmd)>.01` 门控；验证静止、边界、平移和纯转向 |
| mdp:5614–5702，头部长期偏差 | 类式 `head_pose_bias_penalty`，四头关节相对 HOME 与命令的有符号误差，1 s EMA 后取绝对值均值，`[B]`，单位 rad | 原始非负量配 0 / −1 / −2 / −3 | 官方返回负量配正权重，本地符号等价；`alpha=min(1,dt/max(tau_s,1e-6))`，不在命令变化时清空历史，按逐环境 reset 清空 |
| velocity:892–907，头部偏差课程 | mjlab 1.6 `reward_curriculum` | 0/600/1000/1500 迭代，乘 24 转为环境步 | 只新增此项课程；验证阶段前后与 reset 计数，不迁移其他课程 |

`foot_height_scan` 采用官方每脚半径 0.04 m、2 条竖直 ray、yaw 对齐、最大距离 1 m 的配置。
frames 按本机 `r_foot/l_foot` 排列，与接触传感器和奖励 site 选择一致。传感器不进入 actor 或
critic，观测形状不变。官方碰撞体在 group 3，本机碰撞体原为 group 0；因此仅在 Velocity 场景
装配时将机器人 group 0 geom 移到 group 3，ray 只看 group 0 地形，避免误击另一只脚或躯干。
这只改变 ray/显示分组，不改变接触参数；GPU 要检查实际命中 geom 和单脚高度变化。

实施分工：主代理负责 Velocity 配置、专项工具、足端测试及文档；`head_bias` 负责 `mdp.py`
两个有状态奖励类和头部测试；`reward_reference_review` 只读核对来源并独立审查最终内容。
验收包含公式、纯转向/静止门控、落足结算、EMA 零均值振荡与恒定偏差、局部 reset 隔离和课程边界。
GPU 用 4 环境、种子 0 和有界步数，随后通过正式入口做 16 环境、种子 0、5 迭代短跑（300 s 上限），
训练与专项日志保留在 `logs/official_walking_rewards_20261029/`，缓存和临时验证只放
`.artifacts/t049-official-rewards/`。短跑验证代码与数值路径，不代表已学会行走。

## 论文或上游复现

| 原文位置（章节、公式、表格） | 本仓库实现位置 | 是否按原文 | 差异与理由 |
|---|---|---|---|
| 官方 `velstand_policy.md`：势函数进度奖励 | `posture_mdp.upright_progress` / `height_progress` | 是 | 无 |
| 官方 `sitstand_policy.md`：命令斜坡防“砸坐” | `posture_mdp.SitStandCommand` | 是 | 斜坡时长 1.5 s（官方 2.0 s），按本机更低的重心调整 |
| 官方 `sitstand_policy.md`：乘积式目标分 | `posture_mdp.posture_composite` | 是 | 无 |
| 官方 sit keyframe（knee ±1.35、hip_pitch HOME∓0.05、ankle 0、hip_roll 0） | `contract.LOW_POSTURE_JOINT_POS` | 否（数值）／是（机制） | 官方双足值不可移植；本机实测坐姿为 `hip_pitch +1.55 / calf +0.40 / ankle +0.35 / hip_roll ±0.0873`，6 s 保持验证 |
| 官方高度门限（SIT_Z 0.060 / STAND_Z 0.115 / TERM_GATE_Z 0.08） | `contract.SIT_Z`/`STAND_Z`/`FALLEN_Z` | 否 | 绝对高度与机器人尺寸绑定；本机实测 SIT_Z 0.0563、STAND_Z 0.1502、FALLEN_Z 0.110（与倾角取合取） |
| 官方 `ground_state_mix` 分段 | `flat_velstand_env_cfg.GROUND_STATE_MIX` + `curriculum.event_param_curriculum` | 是（机制） | 分段点按本机 6000 迭代上限等比压缩为 600/1500/2600 **迭代**；注意 mjlab 按环境步比较，故代码用 `_iter()` 乘 `num_steps_per_env`。mjlab 1.6.0 无 event curriculum，自行实现 |
| 官方“尝试税后置”（`RECOVERY_ECON_KICKIN_ITER`） | `velstand_curriculum` 的 `recovery_economy` 阶段 | 是 | 起效点 1200（从零训练口径），与官方一致 |

## 实施与协作

| 子工作与负责人 | 允许修改的文件 | 依赖与接口 | 验证与交回 |
|---|---|---|---|
| 契约与共用层（主代理） | `contract.py`、`shared.py`、`commands.py`、`curriculum.py`、`terrain.py` | 四任务共同依赖，须先完成 | 契约自检 + 四任务构建 |
| 姿态 MDP 与事件（主代理） | `posture_mdp.py`、`posture_events.py` | 依赖契约常量 | 奖励有限、姿态 reset 正确 |
| 三个任务配置（主代理） | `flat_standup/ sitstand/ velstand_env_cfg.py` | 依赖上述两层 | 构建 + 短训练 |
| 姿态实测（子代理 `ceba1e55`） | `.artifacts/t049-stance/` 只读探针 | 无 | 130 候选扫描与 7 个躺姿实测 |
| 坐姿独立复核（主代理） | `.artifacts/t049/verify_sit5.py` | 6 s 保持、零漂移、力矩余量 | 通过：z=0.0563、倾角 1.3°、0.88 N·m |
| 独立审查（待指派） | 只读 | 全部改动 | 按[审查模板](../review/TEMPLATE.md) |

串行依赖：契约 → 共用层 → 姿态 MDP/事件 → 任务配置 → 注册守卫。实测与文档可并行。

## 验收与结果

| 验证项 | 实际命令及前置条件 | 通过标准 | 结果 |
|---|---|---|---|
| 契约自检 | `uv run --no-sync python -c "import ht_microduck.tasks.contract"` | 维度 61/64/14、50 Hz、关节覆盖 15 | 通过（61/64/14） |
| 四任务注册 | `python -c "from mjlab.tasks.registry import list_tasks"` | 四个 `HtDuck-*` 可见且导入期守卫不报错 | 通过 |
| 四任务构建与形状 | `.artifacts/t049/smoke.py` | actor 61、critic 64、动作 14、dt 0.02、20 步奖励有限 | 通过 |
| 短训练（三新任务） | `.artifacts/t049/train_smoke.py <task> 3`，64 环境、3 迭代 | 迭代正常推进、奖励有限、无异常 | 见下方结果 |
| 姿态实测 | `.artifacts/t049/verify_sit5.py`、`.artifacts/t049-stance/` | 坐姿可保持、地面姿态高度与倾角 | 通过，见“坐姿实现” |
| `make check` | `make check` | 锁文件、ruff、测试、模型、文档、差异空白全部通过 | 通过（222 测试） |
| `tools/check_task_contract.py` | `uv run --no-sync python -B tools/check_task_contract.py --device cuda:0` | 61D/14D/50 Hz、关节映射、保持关节、reset 隔离 | 通过 |
| `tools/check_velocity_env.py` | `uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0` | 空间、命令范围、零动作稳定、跌倒检测 | 通过 |
| 独立审查 | `docs/review/skill_task_migration.md` | 阻塞项与一般项修复并复核 | R1–R8 复核通过；R9（本记录追加）见下行 |
| 奖励符号探针 | `.artifacts/t049/probe_airtime2.py` | `air_time` 为**区间计数**：摆动落在 `(0.125, 0.300)` s 内计 1、否则计 0，永不为负 | 通过（0.13 s→2.0，0.20 s→2.0，0.02/0.06/0.10/0.40 s→0.0） |
| 出生姿态一致性 | `.artifacts/t049/probe_spawn_consistency.py` | 出生姿态与命令 100% 一致 | 通过（96 次重置 0 不匹配） |
| 课程推进 | `.artifacts/t049/verify_curriculum.py` | 600/1500/2600 迭代分别生效，末阶段 7/8 从地面起步 | 通过 |
| 回合奖励状态隔离 | `.artifacts/t049/probe_reward_leak.py` | 重置后首步不支付跨回合差分 | 通过（384 次重置 0/12 轮支付；修复前 344/360 支付） |

- 短训练不代表策略可用；三个任务的实际收敛需要按官方迭代上限完整训练，不在本次交付内。
- Rough 变体本次只验证可构建，未做地形参数标定与训练。


## T055 除 VelStand 外逐项对齐官方任务

### 范围、基准与隔离

用户在只读比较后要求保留 `tasks/config/flat_velstand_env_cfg.py`，其他现有任务完全按官方。
基准固定为 `pollen-robotics/microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb`，
包括三个环境工厂、所调用的 MDP 以及其 mjlab 1.3.0 基础配置；在本机 mjlab 1.6.0 上适配 API。
本次不新增 Rough/Backlash/其他技能，不替换 HT 机器人或执行器，不修改根目录 RSL-RL 算法。

只读核对发现，当前 VelStand 与其他任务共用旧 MDP；因此官方实现使用统一 `mdp/` 中的
`official_*` 模块，旧函数保持原行为。受保护配置文件先记录 SHA-256，再比较最终文件与配置。
官方任务 actor 61 维，Velocity critic 76 维、StandUp/SitStand critic 74 维，HT 关节顺序保持现有 10 腿+4 头颈，动作 scale=1；
VelStand 继续原 61/64/14 和旧时序。维度与缩放变化意味着原任务检查点不再视为兼容策略。
头颈专用任务保留 ID，作为同一官方 Velocity 配方的独立日志别名。

用户已明确选择「使用已测量的 HT 姿态与高度，其余任务逻辑和参数按官方」。站高/坐高/坐姿
关节角采用 HT 常量，复位高度带仅变换机器人参考并保留均匀采样、带宽及抽样次数；任务奖励/课程
权重与时间不自行调整。前后躺采用 pitch 轴，以真实碰撞网格名义支撑高度作本机高度参考。

### 模块、接口与并发分工

| 工作 | 负责人 | 文件归属 | 交付 |
| --- | --- | --- | --- |
| 官方行走与基础观测 | walking_alignment | config/flat_velocity_env_cfg.py、flat_velocity_head_env_cfg.py、official_common.py；mdp/official_observations.py、official_rewards.py | 官方基础模板、任务对应的 61/76 或 61/74 观测、scale=1、命令桶、全部行走课程与奖励；专项测试 |
| 官方姿态技能 | posture_alignment | config/flat_standup_env_cfg.py、flat_sitstand_env_cfg.py；mdp/official_posture_rewards.py、official_posture_events.py | 两工厂及相应公式、坐站命令和初态逻辑；专项测试 |
| 命令、课程与随机化 | official_mdp_alignment | mdp/official_commands.py、official_curriculums.py、official_events.py | 官方命令采样、live manager 课程和 DR；专项测试 |
| 集成与验证 | 主代理 | config/official_robot.py、mdp/official.py、contract.py、registry、RL、工具、集成测试和文档 | 硬件名字映射、注册与兼容说明、GPU/训练证据、make check |
| 独立审查 | official_task_review | 只读所有最终修改及证据 | 使用原同主题 review/skill_task_migration.md 记录问题与复核 |

新模块通过 `mdp/official.py` 汇总；旧 MDP 不反向依赖新实现。前置接口为
`config/official_common.make_official_base_env_cfg()`、
`config/official_robot.adapt_official_cfg(cfg, num_envs, seed)`；机器人名称和硬件常量在后者集中。
数据仍为 float32、环境设备上的批量张量，头命令4维、躯干命令6维、twist3维；原始官方顺序
映射到本机命名关节后使用，不能将官方关节索引直接应用到 HT 关节。

### 验收安排

- 静态逐项对照官方已启用的配置、公式、随机化开关及课程，保留许可与来源；不把未启用分支
  当成运行能力。复用和新增正式测试验证命令概率桶、观测维度/延迟、课程边界、姿态指令轴、
  独立初态/目标组合和逐环境 reset。
- 保护 VelStand 文件 SHA-256、旧模块源码以及 train/play/RL 完整配置；GPU 复核其输出布局。
- GPU 专项按种子0、4环境、有界150步检查四个对齐任务；检查恢复到后期课程后立即生效。
- tests/ 中提供显式训练验证入口，调用正式 duck-train/Runner，固定种子0和独立 logs 目录；
  先少量迭代冒烟，再按仓库当前规则运行至少600秒实际训练的有界验证。启动正常后只阻塞等待，
  不轮询训练指标，结束后统一检查退出码、日志、检查点和有限值。该验证不代表策略收敛。
- 所有临时脚本与参考源码位于 `.artifacts/official-task-alignment/`，运行缓存显式放项目内；
  需要交付的训练证据保留 logs/，最终清理本次临时文件和字节码。
- `make docs`、`make check`、独立审查通过后记录实际结果和未验证范围。


### T055 官方对应与已授权的硬件适配

| 基准位置 | 本机实现 | 一致性或必要适配 |
| --- | --- | --- |
| 官方 microduck_velocity_env_cfg.py 全工厂 | config/flat_velocity_env_cfg.py；Head 工厂为相同配方别名 | 所有启用开关、权重、时序、命令桶与课程按固定提交；两个 ID 保留独立 RL/日志对象 |
| 官方 microduck_standup_env_cfg.py 全工厂 | config/flat_standup_env_cfg.py | 包含完整混合初态、课程、姿态/高度奖励与 z/roll/pitch 跟踪，使用 HT 姿态参考 |
| 官方 microduck_sitstand_env_cfg.py 全工厂 | config/flat_sitstand_env_cfg.py | 保留独立初态与指令、2 s 斜坡、轻柔约束、头部扰动与全部课程 |
| mjlab v1.3.0 velocity_env_cfg.py | config/official_common.py | 保留原观测顺序；Velocity critic76，姿态任务按官方删除足高后为74 |
| 官方 mdp.py 任务实际引用函数 | mdp/official_commands.py、official_curriculums.py、official_events.py、official_observations.py、official_rewards.py、official_posture_events.py、official_posture_rewards.py | 按职责摘录，公式/课程边界不调参；许可原文与来源在 OFFICIAL_LICENSE/OFFICIAL_NOTICE |
| 官方全局 RewardManager/PPO 数值修复 | rl/runner.py 的 OfficialTaskOnPolicyRunner | 同一运算绑定到任务实例，避免改变受保护 VelStand；无新算法实现 |
| 官方根实体默认 z=0、reset_base 的绝对高度带 | config/official_robot.py | 新偏移=官方绝对高度−0.115+HT站高−HT HOME根高，保留原带宽；不是删除高度随机化 |
| 官方坐/站 reset 高度带 | config/official_robot.py | 分别按官方坐高0.060/站高0.115变换到HT仿真实测0.0563/0.1502 m，宽度不变 |
| 官方前后躺 reset 高度带0.05–0.09 | official_robot.py 与 official_posture_events.py | 以官方文档前躺参考0.044 m保留余隙与4 cm均匀带宽，分别平移至HT前后躺名义支撑参考；不改变分组概率或姿态抽样 |
| 官方14执行器与两脚/头部命名 | official_robot.py 与各 MDP 选择器 | 按HT策略关节14维排除保持HOME的嘴；脚接触/射线/site统一右左顺序，头关节保持neck_pitch/head_pitch/head_yaw/head_roll |
| 官方全舵机BAM随机化 | official_events.py，HT执行器初始化 | 保留本机12无刷+3舵机模型，BAM摩擦事件只作用本机BAM；未启用的官方增益随机化分支仍关闭 |

几何核对：真实 HT 碰撞 mesh/box、HOME 关节、根平移为零，`mujoco.mj_forward` 后计算全部
碰撞顶点最低点。HOME 支撑根高0.1530019321 m，pitch+90°为0.1133891477 m（head_collision），
pitch−90°为0.095 m（base_rear_collision）。记录在 `logs/official_task_alignment_20261029/geometry.json`。
这些是名义几何支撑参考，不是动态平衡高度；官方后躺的额外侧滚角会改变实际支撑形状，运行验证
覆盖其随机初态，不能宣称每个扰动姿态都无初始接触穿透。

官方原生 `feet_swing_height` 没有此前本地类额外提供的局部峰值 reset，本次按用户要求保留
基准原行为；旧类及其局部 reset 测试仍为 VelStand 隔离保留。Logger继续使用已配置的本地
TensorBoard，PPO与网络数值超参及迭代上限逐项同源，不连接外部账号。


### T055 首轮诊断与恢复流程修正

四个既有任务完成官方配方迁入，Velocity-Head是同一Velocity配方的独立ID/日志对象；
VelStand文件SHA-256前后均为 `8522e485699d50f0c754dbf094b8a4955c53801b8d3d9c853bc0cc6cc0aecca8`。
全部旧MDP源码以及train/play/RL完整配置逐项相同，证据保留在
`logs/official_task_alignment_20261029/velstand_protection.json` 与前后JSON快照。

已执行：

- `make check`：336 passed、8 subtests，锁文件、Ruff、模型与文档检查通过；
  后续仅测试恢复流程与文档调整，最终检查结果在任务完成记录维护。
- GPU：四任务各seed0、4环境、150步，真实逐关节动作路由、61/76或61/74、接触/射线顺序、
  局部reset及全部课程末阶段后10步有限。三种不同配方的正式duck-train入口各16环境、2迭代短跑通过。
- 名义前后躺专项：真实HT任务/执行器，强制pitch±90°、不额外侧滚，各4环境、100步（2秒）零动作。
  初始根高均落在映射高度带，观测/奖励有限，各0终止。前躺末20步根高均值0.05330 m、
  后躺0.09487 m，说明几何支撑参考不是动态姿态保持或平衡高度。此专项不覆盖全部随机侧滚姿态。
- 显式训练：`tests/test_official_task_training.py train`，cuda:0、seed0、16环境、24步rollout，
  三任务同GPU并发，测试回调在累计至少600秒实际collection+update后、完整PPO更新边界结束。
  启动确认后阻塞等待，结束前不读训练指标或设备状态；每轮loss有限。

| 配方 | 实际collection+update时长 | 更新数 | 最后检查点 | 恢复结果 |
| --- | --- | --- | --- | --- |
| Velocity | 600.359737 s | 279 | training/velocity/model_278.pt | fresh env全量加载，10步推理有限 |
| StandUp | 600.007316 s | 373 | training/standup/model_372.pt | fresh env全量加载，10步推理有限 |
| SitStand | 600.641745 s | 404 | training/sitstand/model_403.pt | fresh env全量加载，10步推理有限 |

上述检查点相对实验根目录 `logs/official_task_alignment_20261029/`。三次各76个检查点张量
（包含优化器状态）有限，各自29份任务源码副本/manifest与当时生产源码SHA-256一致；后续R4
修正了一个DR身体映射，因此本轮只保留为修正前诊断，不再作为最终配方的冻结证据。

初次训练测试的进程退出码均为1：训练已达到预算并保存检查点，但随后复用训练环境调用load/reset，
触发推理张量在inference_mode之外原位写的限制。保留原失败日志和training_runs.json；
未将其改写成正常退出。测试恢复段现与正式恢复入口一样新建环境，并使用no_grad推理；
对三个已保存权重分别执行restore模式，退出码均0，不重复无变化的600秒训练。
时长由全部进程结束后读取的TensorBoard采样/更新时间核对，字段见training_evidence.json；
组合验收结果见acceptance.json，恢复证据见restore_runs.json及各restore JSON。

这些运行证明配置、采样/PPO更新、保存和恢复路径可运行，不代表策略收敛、稳定行走/坐站/起立
或实机效果。没有执行远端同步或Git提交。独立审查及最终检查见对应审查追加节和任务完成记录。


### T055-R4 随机化身体拓扑复核

独立读取固定提交的 `robot_walk.xml` 与 `robot_groundcontact.xml`，`bearing_roll` 实际是
`trunk_base` 下、直属 `right_hip_yaw`（轴Z）的身体；其子级 `hip_l_2` 才对应髋roll。
HT相同角色为 `base_link → r_hip_yaw_link → r_hip_roll_link`。初版按名字把前者映射到
r_hip_roll_link，改变了启用的头部CoM随机化对象，故更正为r_hip_yaw_link，并保留官方已存在的
「head DR包含一个髋yaw身体」行为，不擅自修正该上游选择。

新增四任务真MJCF直属关节角色测试，以及GPU实际body_ipos目标列/局部环境隔离检查。
其他四个头部身体由独立审查按直属关节逐一核对一致。本次修正改变真实DR对象，三配方最终
训练证据重新冻结到 `logs/official_task_alignment_20261029/training_final/`；原training目录、
首次恢复失败与修正前诊断全部保留，不覆盖或冒充最终配方结果。


### T055 最终冻结配方验收

R4修正后的四任务真实GPU DR探针均通过：直属关节角色与官方真实MJCF对应，单独调用head CoM
事件只改变world0预期的五个body_ipos列，邻居环境保持原值。四任务各4环境、150步及后期课程
检查均正常退出；运行命令与输出见 `gpu_env_final_runs.json` 和各 `*_env_final.log`。

最终三配方训练使用cuda:0、seed0、16环境、24步rollout，同GPU并发；启动确认后只阻塞等待。
预算不包含初始化、日志写入与结束等待，只累计runner的collection+update，三次全流程退出码均0：

| 最终配方 | 实际collection+update | 更新数 | 检查点（相对实验根目录） | 全量恢复 |
| --- | --- | --- | --- | --- |
| Velocity | 600.190533 s | 595 | training_final/velocity/model_594.pt | fresh env，10步推理有限 |
| StandUp | 600.579648 s | 654 | training_final/standup/model_653.pt | fresh env，10步推理有限 |
| SitStand | 600.072179 s | 701 | training_final/sitstand/model_700.pt | fresh env，10步推理有限 |

实验根目录为 `logs/official_task_alignment_20261029/`；完整命令和退出码保存在
`training_final_runs.json`。三次各76个模型/归一化/优化器张量有限，全部loss逐次有限；
各29份生产源码与当前文件、冻结副本及manifest逐一SHA-256相同。
`training_final/<任务>/result.json` 保存精确时间，独立审查从TensorBoard事件重算一致；
`acceptance_final.json` 与 `acceptance.json` 汇总最终证据。

R4后再次执行名义pitch±90°、无额外侧滚的两秒躺姿专项，初态高度带正确、观测/奖励有限，
每组4环境0终止；前躺后期根高0.05304 m、后躺0.09487 m，不将几何参考称为动态姿态保持。
`ground_heights_final.json` 保留数据。Head别名通过原工具入口完整加载最终Velocity检查点，
证据为 `final_inference_checks.json` 和 `head_alias_restore_final.log`。

最终 `make check` 通过340项测试与8个subtests，锁文件、Ruff、模型、文档和差异空白检查通过。
只读审查者official_task_review复核R1–R4、最终源码/模型/运行证据，结论为独立审查通过。
本轮没有未解决的实现项，未验收策略收敛、固定指令技能表现或实机效果；这些属于后续实验。
源模型、混合执行器和用户既有实验保留，不修改VelStand文件或其原有共享MDP，不执行Git提交或远端同步。


## T057 官方恢复机制与 HT 坐站高度修复

### 范围与依据

用户在比较两段训练回放后确认前述分阶段方案，并要求按官方实施。本轮撤销 T055 对 VelStand
实现不作修改的限制，先交付环境修复与有界训练；专家蒸馏和热启动仍按已确认方案另阶段实施，
本轮不宣称复现官方部署策略或完成技能收敛。

基准继续固定为 `pollen-robotics/microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb`。
参考源码、作者训练记录和本地诊断保留于 `.artifacts/posture_analysis_20261030/`；
其中 `summary.json` 区分源码事实、单种子 GPU 推理证据与尚需训练消融的假设。
官方展示视频不可访问，本轮没有将作者报告等同于本机实测。

| 项目 | 采用依据与本地决策 | 验收 |
| --- | --- | --- |
| VelStand 恢复窗口 | 官方 `microduck_velstand_env_cfg.py` 的非热启动分支：初期一般倾角终止70°，500迭代后设π；恢复/超时倾角40°、完成25°，超时按低高度OR倾角持续8秒；恢复税与成功奖励在1200迭代启动 | 后期前后躺、侧躺不再首步因一般倾角终止；恢复计时与成功奖励可触发 |
| VelStand 初态 | 官方非热启动阶段 0/800/1500/2000/2500，prone份额0/0/.15/.30/.45，低姿态份额0/.20/.20/.20/.20；保留余下站立份额，prone内部side=.5、前后躺概率1/1/.8/.65/.5 | 绝对概率与互斥分组、站立余量、pitch前后躺与roll侧躺、阶段边界 |
| HT 低姿态与高度 | 沿用已确认的HT实测坐姿、坐站高度及恢复高度门限；角度和超时OR逻辑按官方；官方 crouch 切片映射到已确认的 HT 低姿态，不将其称为官方机器人的同一运动学姿态 | 支撑高度与实际关节/朝向通过 GPU 检查；差异在结果中记录 |
| 倒地腾空门控 | 采用官方feet_air_time_upright，tilt超过40°时将原腾空奖励归零；保留本机原足端参数 | 倾角等号边界、参数透传、倒地不会刷腾空奖励 |
| 势函数局部重置 | 修复本地 `_ht_posture_prev` 被整批清空的问题；仅重置指定环境，未重置环境保持连续 | 双环境及多次局部重置验证 |
| 身体指令 | 采用现有官方 `body_pose_tracking_locomotion` 的 z/roll/pitch 跟踪和站立门控；保留6维米/弧度指令接口，避免把x位置当坐站blend；普通直立项采用官方相对目标g_xy公式；本地额外高度直立项保留角度Gaussian，只把角度参考改为目标gravity，零指令任意倾角恒等；保留权重与高度门控 | x/y/yaw不改变已声明未跟踪目标，z/roll/pitch产生正确响应 |
| SitStand 高度 | 官方起身辅助截止值 `.125` 比其站高 `.115` 高1cm；HT改为 `STAND_Z+.01`；VelStand的同源COM上升辅助上限同样改为站高+1cm，其余绝对高度门限按坐站参考区间核对映射，奖励公式与权重/2秒斜坡不自行调整 | 高度映射与截止边界测试；推理与有界训练 |

本轮保留 VelStand 的61/64/14顺序、float32、原`.002s×10`执行器时序与HT混合执行器，
保留SitStand的61/74/14和`.005s×4`；它是已确认的环境修复阶段，不是官方完整VelStand
环境/硬件防护模型的逐项迁入。旧VelStand、SitStand检查点在张量布局上可加载，但奖励与初态
分布已经变化；本轮用新实验目录建立训练基线，原训练产物保留。后续接入热启动/蒸馏前须重新
核对教师策略的动作缩放、关节/观测顺序、归一化和物理时序，不直接套用旧Velocity的`.25`策略。

### 模块、接口与并发归属

| 负责人 | 允许修改 | 接口与验证 |
| --- | --- | --- |
| velstand_config | `config/flat_velstand_env_cfg.py`、`tests/test_velstand_recovery_cfg.py` | 调用下述明确的初态API与已有官方身体跟踪；复制官方非热启动阶段，配置独立与边界测试 |
| recovery_mdp | `mdp/events.py`、`mdp/posture.py`、`tests/test_recovery_reset.py` | `reset_to_ground_state`以prone_prob/crouch_prob/side_prob/face_down_prob表达绝对分布；局部势函数状态保持独立；保留其他既有调用 |
| 统筹者 | SitStand配置与高度适配、任务注册、既有受影响测试/训练验收、README、任务/设计/审查记录 | 集成、GPU串行检查、单GPU预算内两个各至少600秒的训练验证、独立审查和清理 |
| 独立审查者 | 默认只读全体最终改动及新文件 | 官方对应、HT适配、实际验证、检查点与调用兼容性；缺陷修复后复核 |

`reset_to_ground_state`将当前prone_prob切成side_prob侧躺份额，其余按face_down_prob分前后躺；
另分配crouch_prob给HT已确认低姿态，剩余为站立。任务加载统一使用已有OfficialTaskOnPolicyRunner，恢复计数后reset以刷新课程，并沿用官方实例级有限值处理；无需另写训练算法。配置入口统一验证概率和阶段；MDP内部沿用
已确认约定。现有日志与工作期旧源码快照存于 `.artifacts/t057/baseline/`，交付时归档为 `logs/posture_recovery_20261030/validation/baseline-code.tar.gz`；原训练日志不覆盖。

### 验证与交付门槛

先执行局部单测与配置对照，再进行真实 GPU 初态、局部 reset、指令响应和恢复终止检查。
训练复用或扩展 `tests/` 正式验收文件，固定seed0与明确环境/预算，累计至少600秒采样和更新，
实际结束后再统一分析日志、有限值及新环境恢复结果；期间仅阻塞等待或确认进程结束，不读取
训练指标、检查点或设备状态。此验证仅覆盖训练链路和恢复，不代表已学会技能。
文档修改后执行 `make docs`，交付前执行 `make check`；本轮大范围恢复接口修改须独立审查。


### T057 实施与验收结果

本轮完成非热启动恢复课程、绝对初态/朝向、局部势函数历史、恢复时间与角度边界、
身体目标相对直立及腾空门控；SitStand两项区间门限分别为0.08190909/0.12459091 m，
两任务对应的起身上升辅助截止均为HT站高+1 cm=0.1602 m。注册复用已有OfficialTask runner，
恢复检查点计数后刷新课程；PPO、依赖、执行器、任务张量布局和物理时序保持已声明范围。

- 基础检查：380 passed、8 subtests；独立审查者复跑69项相关CPU测试。
- GPU：VelStand32环境检查0/499/500/800/1200/1500/2000/2500阶段，后期一般倾角首步终止均0，
  配置站立份额最终为0.35；实体与势函数局部reset保持邻居，身体轴/站立门控通过。
- GPU控制状态注入：实际Entity写入已知躺/站姿，直接调用恢复函数，武装、单次付奖、不重复、
  8秒超时及恢复清零均通过；这不代表策略自主起身。
- SitStand4环境150步，61/74/14、动作映射、局部重置、DR与后期课程有限值通过。

| 任务 | 固定条件 | 实际collection+learning时间 | PPO更新数 | 检查点与新环境恢复 |
| --- | --- | --- | --- | --- |
| SitStand | seed0、cuda:0、16环境、24步rollout | 600.436701536 s | 998 | `sitstand/model_997.pt`，76张量有限，完整加载后10步推理 |
| VelStand | seed0、cuda:0、16环境、24步rollout | 600.370447636 s | 483 | `velstand/model_482.pt`，76张量有限，完整加载后10步推理 |

表中路径相对 `logs/posture_recovery_20261030/`。每次首个真实PPO更新写入启动凭据后，
统筹仅阻塞等待退出，没有读取运行中的指标/检查点或查询设备。独立审查者在结束后从原始
TensorBoard事件重算时间和更新数，与结果完全一致；29份任务源码快照与93份运行源码/资源
哈希保持冻结。长期配置、源码状态、GPU结果、旧基线归档与审查所用证据在该目录的
`validation/`；同主题独立审查记录见[姿态迁移审查](../review/skill_task_migration.md)。

范围限制：VelStand483次更新尚未达到第500次的一般终止关闭点，800/1200/1500以后阶段
只由专项GPU状态检查与CPU边界测试覆盖，没有把这次训练算作后期恢复学习实验。
两个600秒实验只验证学习/保存/恢复链路，不证明坐站、起身或行走收敛。
后续可执行工作是按相同动作/观测契约验证HT自己的行走与起立教师，再接热启动/专家蒸馏。

## T058 坐站与组合任务的关节目标约束

### 范围、依据与假设

用户在两次训练诊断及修改方案说明后要求实施。先交付 SitStand、VelStand 的逐关节位置目标
约束、越界与力矩饱和观测，以及有界训练链路验证。独立保存原配方；倒置直立奖励的修改、
奖励成本调参、教师训练与专家蒸馏属于随后可独立验证的步骤，本轮不混入。

| 判断 | 依据类型及位置 | 适用范围与验证 |
| --- | --- | --- |
| 旧策略产生远超关节行程的目标，并长期以2 N·m顶住多个关节 | 本项目已验证：`.artifacts/training_diagnosis_20261030_1145/diagnosis.json`、两个`*_controlled.json` | seed0、固定初态；不将该测量当作全部种子的收敛结论 |
| 上游位置动作在编码器偏置扣除后写入目标；可选clip在扣偏置之前 | 参考项目：本机mjlab1.6.0 `envs/mdp/actions/actions.py:154,221`；官方固定v1.6.0同文件 | 新任务动作继承上游处理，仅在最终物理目标处按实体`joint_pos_limits`限幅 |
| 统一裁原始动作至±1会使膝关节坐姿偏移1.6 rad不可达 | 本项目代码：`contract.py` HOME与`LOW_POSTURE_JOINT_POS` | 对逐关节有效范围、坐姿目标、正负编码器偏置进行边界验证 |
| 位置目标约束可阻止超行程目标持续驱动，但不保证策略姿态或恢复收敛 | 推断／待验证假设 | 注入极端动作与旧检查点推理；记录满力矩持续时间；新训练另行评价技能 |
| 主upright对完全倒置同样满分源于官方公式 | 参考项目：microduck_rl@bae39f59 `mdp.py:5477`；本地`posture.py:243`及诊断边界JSON | 本轮保留，后续独立消融，不宣称其因果影响已验证 |

### 接口与模块

- 新动作位于`tasks/mdp/actions.py`：`BoundedJointPositionActionCfg`继承官方配置，新增
  `bound_targets: bool = True`；对应动作先沿用上游scale/offset/clip，再逐物理子步执行
  `requested = processed - encoder_bias`、`applied = clamp(requested, joint_pos_limits)`。
  使用实际模型逐环境硬关节范围，包含上下界；不缩小至软限位，不修改PD、NT、BAM、延迟或力矩上限。
- `bound_targets=False`明确启用原始目标语义，作为同一任务的旧配方对照入口；不作静默回退。
  仅SitStand、VelStand默认启用，其他三个任务保持原动作类与行为。
  上游`duck-play`的PlayConfig不支持`--env.*`覆盖，因此注册`HtDuck-Flat-SitStand-Unbounded`
  和`HtDuck-Flat-VelStand-Unbounded`两个显式对照ID，训练/回放均关闭目标约束，日志实验名
  加`_unbounded`；训练原ID另可用`--env.actions.joint-pos.bound-targets False`。
- 保留14维动作及关节顺序、1 rad/action、float32、环境设备、50 Hz；上一动作观测与
  原有动作变化奖励仍读策略原始动作。新模式增加最后一道物理目标限幅，属于控制语义变更。
  旧权重张量可以加载做对照，但不视为新配方的完整等价恢复；正式新基线从零训练。
  训练、回放使用同一配置开关；评估通过注册任务和相同开关；未实现的部署导出仍须后续实现该映射。
- 新指标位于`tasks/mdp/action_metrics.py`：请求目标越界比例、实际目标越界比例、限幅比例，
  以及当前方向力矩达到实际仿真force range的95%比例和最长连续饱和秒数。均按14个策略执行器
  控制帧采样，零力矩包络不计饱和；持续计时由MetricsManager局部reset清除，仅用于诊断而非硬件安全评级。
- 指标只用于日志，不加入奖励；持续用力是否需要额外代价由新基线测量决定。

### 并发归属与验收

| 负责人 | 允许修改 | 前置与验证 |
| --- | --- | --- |
| action_impl | `mdp/actions.py`、`mdp/action_metrics.py` | 按上述接口实现；只读配置、实体和上游API；CPU专项，不启动GPU或训练，不继续分派 |
| action_tests | `tests/test_bounded_actions.py` | 极端/边界/偏置/坐姿可达、原模式、局部reset和饱和计时；只读实现；独立CPU产物目录，不启动GPU |
| 统筹者 | 两任务配置、注册与契约说明、README、正式GPU/训练验收文件与设计/任务/审查文档 | 配置集成、CLI对照入口、真实GPU目标与局部reset检查、旧检查点对照、各任务至少600秒训练及新环境恢复 |
| 独立审查者 | 默认只读上述最终实现、测试、文档与证据 | 编码前审查设计，交付前复核接口和基线范围；问题关闭后方可完成 |

修改前源码、未跟踪文件与Git状态保存于`logs/action_bounds_20261030/validation/`，原日志不覆盖。
基础验收要求：实际目标越界为零、坐姿行程可达、原模式与上游等价、局部reset不影响邻居，
观测/动作顺序维度及嘴保持HOME不变。GPU验证分别使用两任务，固定种子0；有界训练复用已有
正式训练接口，串行、每次至少600秒实际采样/PPO更新，确认启动后只阻塞等待，结束后统一检查。
短训练仅验链路、指标有限和检查点恢复，不作为坐站、行走或恢复效果达标证据。
文档修改后`make docs`，最终`make check`和独立审查；需要新修改时复核其影响。

### T058 实施与验证结果

动作、五个日志指标和两个显式`-Unbounded`对照任务已实现；其余三任务仍使用原动作类。
正式专项见`tests/test_bounded_actions.py`、`test_bounded_action_cli.py`和
`test_bounded_action_training.py`；训练测试委托既有训练接口，没有复制PPO或训练循环。

- 基础检查：421 passed、8 subtests；CPU动作/配置专项33 passed，独立预审93 passed。
- 两任务各8环境GPU专项通过极端动作、正负编码器偏置、坐姿目标与局部reset。
- 旧检查点对照：seed0、16环境、每种固定初态500控制步，使用原权重，头身指令为零，
  移除间隔扰动、保留startup DR；只评价首回合有效帧的姿态，目标与饱和指标按全部控制帧采样。
  新旧回合终止时序可改变后续随机数，不能把差值当作严格配对的学习因果结论。
  SitStand起身工况下发目标越界0.56097→0，力矩饱和0.49561→0.00701，
  但倾角仍为21.76°；限幅保证控制目标有效，不代表旧策略姿态已修复。
  VelStand全部6组工况启用约束后的下发目标越界也为零。

| 任务 | 固定条件 | 实际采样+PPO更新时间 | 更新数 | 检查点与恢复 |
| --- | --- | --- | --- | --- |
| SitStand | seed0、cuda:0、32环境、24步rollout | 600.937100410 s | 459 | `sitstand/model_458.pt`；全量加载到新环境，10步推理，另20步实际目标/嘴保持复核 |
| VelStand | 同上 | 602.368088722 s | 246 | `velstand/model_245.pt`；全量加载到新环境，10步推理，另20步实际目标/嘴保持复核 |

表中路径相对`logs/action_bounds_20261030/`。确认首个真实PPO更新完成后，主代理仅阻塞等待进程
结束，没有中途读取指标、检查点或设备状态。结束后从原始事件重算的时间与更新数一致，
全部事件标量有限，`applied_target_outside_limits`全程为零，两个检查点各76个检查点张量
（含模型、归一化与优化器）有限。
每次训练保存31份任务源码快照，与冻结的95份运行源码/资源清单一致。
完整证据位于该实验根目录的`validation/acceptance.json`、`restored_targets.json`、
`old_policy_comparison.json`、`runtime_manifest.json`和`runtime-code.tar.gz`。

范围限制：这两次训练均未到第500次更新，不能作为后期头部/扰动课程或恢复学习效果验收。
探索阶段的力矩饱和仍然较多；尚未据此增加成本或重判其必要权重。
倒置upright、专家BC、热启动与正式部署导出不在本轮交付内。下一项可执行工作是使用新目录
进行SitStand完整训练，并按站姿倾角、头部误差、双向切换与持续饱和指标选择检查点；
VelStand组合训练前先验收HT自己的行走与起立教师。
