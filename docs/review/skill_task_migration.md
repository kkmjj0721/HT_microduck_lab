# 审查记录：姿态技能任务迁移（T049）

## 审查范围与证据

- 任务与设计：关联 [任务表](../development.md) 中 T049（当前状态「进行中」）与
  [姿态技能迁移设计](../design/skill_task_migration.md)。审查目标为官方
  `pollen-robotics/microduck_rl` 三族姿态任务的迁移：14 执行器 / 61 维 actor / 64 维 critic
  契约，`HtDuck-Flat-Velocity`、`HtDuck-Flat-StandUp`、`HtDuck-Flat-SitStand`、
  `HtDuck-Flat-VelStand` 四个任务。
- 实现者与独立审查者：本记录由独立审查者按只读方式完成，实现者未参与结论。审查者未修改
  `src/`、`tools/`、`tests/`，唯一写入为本文件。
- 文件范围与基准：以 `git status --short --branch` 与 `git ls-files --others --exclude-standard`
  枚举，实际阅读以下最终内容（`HEAD` = `9840fa8` 之上的工作区状态）：
  - 重命名：`tasks/common/contract.py` → `tasks/contract.py`、`tasks/common/mdp.py` → `tasks/mdp.py`、
    `tasks/flat_velocity/velocity_env_cfg.py` → `tasks/flat_velocity_env_cfg.py`；
  - 新增未跟踪：`tasks/{shared,commands,curriculum,terrain,posture_mdp,posture_events}.py`、
    `tasks/flat_{standup,sitstand,velstand}_env_cfg.py`；
  - 修改：`tasks/__init__.py`；文档：`docs/design/skill_task_migration.md`、`docs/development.md`。
  - 对照上游：`mjlab` 1.6.0（`.venv/lib/python3.12/site-packages/mjlab`）、
    `rsl_rl` 5.4.2（仓库根 `rsl_rl/`）。逐行核对 `managers/reward_manager.py:116-133`（`raw * weight * dt`、
    `weight == 0.0` 跳过、`nan_to_num`）、`managers/manager_base.py:141-147`（`SceneEntityCfg.resolve`）、
    `managers/scene_entity_config.py:160-224`（名称→id 解析与 `preserve_order`）、
    `envs/manager_based_rl_env.py:439-471,580-608`（`common_step_counter` 每环境步加一；
    `_reset_idx` 中事件在 `command_manager.reset` 之前）、`envs/mdp/curriculums.py`
    （`reward_curriculum` / 阶段语义）、`envs/mdp/rewards.py` 与 `tasks/velocity/mdp/rewards.py:209-238`
    （官方 `feet_air_time` 参考实现）。
- 验证证据（实际执行，均在项目内 `.artifacts/review/` 进行，`TMPDIR` 与 `--basetemp` 已设为该目录；
  GPU 为 RTX 4060 且同卡另有他人训练任务，故环境数 1–64，**未运行训练**。第一轮探针见各 R 行「验证」栏；
  第二轮（复核）由审查者自建，逐条对应 R1–R9）：
  - 回归：四任务构建并读取真实形状，actor `(61,)`、critic `(64,)`、动作 14、`step_dt` 0.02，
    6 步运行奖励有限；61/64 的加和分解与第一轮一致；
  - R1：真实步进 4 环境 150 步，累计 112 次落足，正向 14 / 负向 **0** / 区间外 98，加权 +3.0；
    并以 `.artifacts/t049/probe_airtime2.py` 复现 0.13/0.20 s→2.0、0.02/0.06/0.10/0.40 s→0；
  - R2：128 次重置中出生姿态与 `pending_sit_flag` 不一致 0 次、`alpha` 与 flag 不一致 0 次；
  - R3：按 `num_steps_per_env` 折算后扫描计数器 599/600/1000/1200/1500/1600/2600，逐点读取
    `ground_state_mix`、`face_down`、`recovery_economy` 的实际参数值；
  - R6：`grep` 训练日志，确认 `Curriculum/ground_state_mix/mixture/0..3` 四个键存在；
  - R7：`src/` 内对 5 个已删符号 grep 0 命中；64 环境探针统计「行走中非零躯干指令」0 / 20817；
  - R8：向 body 槽注入 `zero_command_padding(4)`，复现导入期 `ValueError`（含槽位名与应有宽度）；
  - R9：32 环境 VelStand 逐步读 `_step_reward` 与 `_ht_*`，统计每个奖励项在「重置后首步」的支付额与
    它在整个回合回报中的占比；另做 standup 同种子基线/打补丁对照实验量化该泄漏的幅度。
  - 关节寻址（第一轮）：`robot.joint_names` 共 15 个（模型顺序以 `mouth_joint` 结尾），
    `POLICY/LEG/HEAD` 解析结果为 `slice(None)` / `[0..9]` / `[10..13]`，与名称逐一对齐；
    全部奖励/终止/事件/命令项的 `SceneEntityCfg` 共解析长度与名称一致（角标无错位）。
- 已执行与未执行项：审查者**独立执行**了 `pytest -q tests`（**222 passed, 8 subtests passed, 1 warning**）、
  文档检查（`19 files, 107 links, 50 task rows scanned`）、`tools/check_robot.py`、
  `ruff check src tools tests`（`All checks passed!`）、`uv lock --check`、`git diff --check`（无输出），
  故 R5 中的「222 个测试」说法成立。**未执行** `make check` 整包、`tools/check_velocity_env.py`
  与任何训练/回放（审查者只读且不得运行训练），这些项不由本记录背书。
  结论中所有「已验证」仅指上述只读探针与检查。
- 依据与差异：官方基于 mjlab 1.3.0 / rsl_rl 5.0.1，本机 1.6.0；`currculum` 与命令项 API 不同，
  迁移方自行实现 `curriculum.event_param_curriculum`。官方数值（坐姿关节、绝对高度门限）
  与本机实测不同属预期差异，本记录只审「是否自洽、是否与自身文档一致」，不要求数值与官方相同。

## 问题与修复复核

| 编号与程度 | 文件位置 | 触发、影响、依据及建议 | 修复与验证 | 复核者及状态 |
|---|---|---|---|---|
| R1 阻塞 | `src/ht_microduck/tasks/mdp.py:97-110`；调用处 `tasks/flat_velocity_env_cfg.py:196-205`、`tasks/flat_velstand_env_cfg.py:284-286`（`air_time`，weight +3.0） | `air_time` 先在第 102 行按 `where(contact, 0, air+dt)` 归零，第 108-110 行才用 `(air_time - threshold_min)` 乘 `first_contact` 支付；首次接地这一步 `contact=True`，因此 `air_time` 恰为 0，支付值恒为 `-threshold_min = -0.125`（双脚同时落地为 `-0.25`）。实测 87 次落足全部为负、无一次为正；训练日志 `Episode_Reward/air_time = -0.0012…-0.0031` 与 weight +3.0 同时出现即此现象。影响：本应奖励「摆动至少 0.125 s 后尽早落地」的步态整形项，实际等价于**每次落足固定扣分**，把策略推向不抬脚/拖步，与 `robo` 步态目标相反；VelStand（新任务）以 weight 3.0 复用同一项，因此该缺陷直接落在 T049 交付范围内。依据：官方 `tasks/velocity/mdp/rewards.py:209-238` 按 `current_air_time` 落在区间计数，为正向奖励。建议：在第 102 行归零前保留上一拍的 `air_time`（如 `closed = air_time.clone()` 后再 `where`），用 `closed` 参与支付；或在首次接地时用 `air_time + dt` 参与计算。修复后重跑同一探针，要求落足支付为正且随摆动时长单调。（该文件由 `tasks/common/mdp.py` 重命名而来，缺陷早于本次改动；但新任务新增了对它的依赖，故列为阻塞，由实现者决定「本轮修复」或「撤下 VelStand 的 weight 3.0 并为该缺陷单开阻塞任务」。） **验证**：`.artifacts/t049/probe_airtime2.py`：0.13 s→2.0、0.20 s→2.0（区间内计数），0.02/0.06/0.10/0.40 s→0.0（不在区间），**无负值**；旧算式复算证明恒为 −0.125。训练侧对照：修复前 6 迭代 `Episode_Reward/air_time` 恒为负（−0.0007/−0.0008），修复后为**正**（+0.0050/+0.0027）。 | `feet_air_time` 重写为与 mjlab 官方 `tasks/velocity/mdp/rewards.py::feet_air_time` 一致的**区间计数**形式：先用 `closed_air_time = air_time + dt` 保留刚结束的摆动时长，摆动落在 `(threshold_min, threshold_max)` 内计 1、否则计 0，因此永不为负，也不会被「久抬不放」或「碎步拖行」刷分。注释写明先前两种错法（付 `(air - min)` 会惩罚快速步伐；在归零后取值会得到恒定 `-threshold_min`）。 | 审查者：已复核关闭。独立复跑 `probe_airtime2.py` 得 0.02/0.06/0.10/0.40 s→0、0.13/0.20 s→2.0；自建真实步进探针（4 环境 150 步、112 次落足）得 14 次正向、**0 次负向**、98 次区间外为 0，加权 +3.0。注：本条原「要求随摆动时长单调」的验收写法已被区间计数取代（0.40 s 摆动同样支付 0），这是与官方一致的更严口径，非缺陷；但设计文档第 132 行的旧证据文字「随时长单调 / 0.40 s→+0.59」须一并改掉（见最终结论「建议级残余」）。 |
| R2 一般 | `src/ht_microduck/tasks/posture_events.py:311-358`（尤其 320-327 的 docstring、347/356 的赋值）；`mjlab` `envs/manager_based_rl_env.py:587` 与 `:608` | `reset_to_stand_with_sit_blend` 在 reset 事件里直接写 `term.vel_command_b[ids, 0]` 强制命令与出生姿态一致，但 `_reset_idx` 中事件（587 行）先于 `command_manager.reset`（608 行），后者调用 `SitStandCommand._resample_command`（`posture_mdp.py:509-516`）按 `sit_prob` 重新抽样，覆盖事件写入的 flag；`alpha` 因事件与 `compute` 都写而不受影响。实测 8 环境中 4 个 flag 被覆盖，6 次重置 48 例中 21 例出生姿态与命令相反。影响：恰好破坏了该函数 docstring 声明要避免的失败模式——「坐在座姿却收到 stand 命令，于是立刻起身、永不探索下坐」；约 44% 的重置把「保持座姿/保持站姿」退化为「从座姿起身/从站姿下坐」，SitStand 的任务分布与设计描述不一致，且该行为依赖两个 manager 的调用顺序，属隐性时序耦合。依据：`posture_mdp.py:535-537` 的注释已承认「命令管理器在事件传送机器人之前重置」，但只处理了 `alpha`，未处理 flag。建议：把姿态对齐改为「跟随已抽样命令」而非「反向强制命令」——在事件里读 `term.command[env_ids, 0]`，`== 1` 的播种座姿、`== 0` 的播站姿，从而消除跨 manager 写入与时序依赖；或保留现方案但把 flag 强制移到 `_resample_command` 之后执行的时机。修复后用同一探针断言「出生姿态与 flag 一致率 100%」。 **验证**：`.artifacts/t049/probe_spawn_consistency.py`：96 次重置（53 坐 / 43 站）**0 次**不匹配，此前为 21/48。 | 改为「事件自己抽签 + 交给命令项重放」：新增 `SitStandCommand.pending_sit_flag`，事件按 `sit_prob` 抽签并播种对应姿态，`_resample_command` 若遇到待重放标记则采用之而非重新抽样，消除对两个 manager 调用顺序的依赖（`posture_events.py`、`posture_mdp.py`）。 | 审查者：已复核关闭。自建探针 128 次重置：出生姿态与 `pending_sit_flag` 不一致 **0** 次、`alpha` 与 flag 不一致 **0** 次，重置后 flag 全部回到 `-1.0`（无跨回合残留）。 |
| R3 一般 | `src/ht_microduck/tasks/flat_velstand_env_cfg.py:168-179`（`GROUND_STATE_MIX`，0/600/1500/2600）、`:180`（`FACE_DOWN_PROB` 0/1000）、`:188-189`（`RECOVERY_ECON_KICKIN_ITER=1200`、`FALLEN_TAX_RAMP=400`）、`:249-253`；语义来源 `envs/manager_based_rl_env.py:447` | 阶段 `step` 与 `env.common_step_counter` 比较，而该计数器每**环境步**加一（一次迭代 = `num_steps_per_env=24` 步，四个任务均为 24），故 600/1500/2600 分别在第 25/63/109 次迭代生效、1200 在第 50 次迭代生效，而非常量名与注释暗示的「迭代」。mjlab 自身 `tasks/velocity/velocity_env_cfg.py:406-408` 明确写成 `5000 * 24`，可作为单位约定的旁证。影响：设计文档第 103 行「分段点按本机 6000 迭代上限等比压缩」不成立（偏差约 24 倍）；地面起始混合与「尝试税」几乎在训练一开始就全量生效，`velstand_curriculum` docstring 声称的三条「若在第 0 步启用就会失败」的保护实际只覆盖前 25–110 次迭代；`recovery_economy` 在第 50 次迭代即升到 -0.1、第 67 次到 -0.5，与本机 6000 迭代上限严重错配。建议：统一把常量改为「迭代 × `num_steps_per_env`」形式（如 `600 * 24`），或将常量重命名为 `*_STEPS` 并在注释中写明单位；同步修正设计文档第 103 行的说法。 **验证**：`.artifacts/t049/verify_curriculum.py`：按迭代设置计数器后，600/1500/2600 各自生效，末阶段 7/8 从地面起步、`fallen_tax` 0→−0.1→−0.5。 | 新增 `STEPS_PER_ITER = 24` 与 `_iter()`，全部阶段改为 `_iter(N)`；注释写明 mjlab 按环境步比较并以 `5000 * 24` 为旁证。 | 审查者：已复核关闭。自建探针按 `num_steps_per_env` 换算后逐点核对：计数器 599→(0,0,0,0)、600→(0.25,0.15,0.2,0.4)、1000→0.50、1200→−0.10、1500→(0.30,0.20,0.25,0.25)、1600→−0.50、2600→(0.35,0.25,0.25,0.15)；`face_down` 在 24000 前为 0、之后 0.25；`recovery_economy` 在 28800/38400 处 −0.10/−0.50，与设计文档第 103 行的「迭代」口径一致。遗留小项：`STEPS_PER_ITER = 24` 是 `num_steps_per_env=24` 的手抄副本，无测试断言二者耦合（见最终结论「建议级残余」）。 |
| R4 一般 | `docs/design/skill_task_migration.md:43`、`:103`；`src/ht_microduck/tasks/contract.py:200-208` | 设计文档第 43 行称「40° 倾角门可判定跌倒，25°/0.120 m 可判定站起」，但代码实际门限为：fall 终止 40°（`TERM_GATE_TILT_DEG`）、倒地判定 70°、站起 25°/`RECOVERED_Z=0.1300`；`contract.py` 另有 `FALLEN_TILT=1.05 rad(60°)`、`RECOVERED_TILT=0.44 rad(25°)`，且这两个常量在 `src/`、`tools/`、`tests/` 中**零引用**（grep 仅命中定义处）。同一行还写「HOME 站姿倾角 1.4°、躯干 0.1665 m」，与 `contract.STAND_Z=0.1502` 及其「0.1534 几何高度 PD 沉降到 0.1502」的实测注释矛盾。影响：读者按文档实现会得到 0.120 m 这一代码中不存在的门限；倒地方向的门限（40° vs 60° vs 70°）在文档、契约、cfg 三处各有一个值，属焦点 7「文档与代码一致」的实质不符；两个未引用常量是死配置，容易被后续误当作权威门限。建议：删除 `FALLEN_TILT`/`RECOVERED_TILT` 或让 cfg 真正引用它们；把设计文档第 43 行改成代码中的实际值（40° 终止 / 70° 倒地计时 / 25° 与 0.1300 m 站起），并统一 0.1502 m 口径。 **验证**：设计文档与 `contract.py` 已一致；四任务构建通过。 | `FALLEN_TILT`/`RECOVERED_TILT` 改为真正被引用（`RECOVERY_TILT_DEG`、`RECOVERY_UP_TILT_DEG`、`REWARD_GATE_TILT_DEG`、`STAND_UP_TILT_DEG` 均由契约换算）；设计文档第 43 行改为代码实际门限并统一 0.1502 m 口径；补充说明终止门限 40° 与倒地门限 60° 为何不同。 | 审查者：**部分复核**。死常量已复活并可核（velstand `:147,148,161`、standup `:128` 均引用 `C.FALLEN_TILT`/`C.RECOVERED_TILT`），设计文档第 43 行的 4.3°/0.1502 m、1.3°/0.0563 m、≥79° 与站起 25°/0.130 已与代码一致。**残留不一致**：同一行称「倒地判定 60° + 0.110 取与」，但 `fallen_too_long` 的定时终止在 `flat_velstand_env_cfg.py:467`、`flat_standup_env_cfg.py:243`、`flat_sitstand_env_cfg.py:255` 三处写死字面量 `70.0`，并非 `C.FALLEN_TILT`；60° 只用于奖励侧门（`REWARD_GATE_TILT_DEG`、`RECOVERY_TILT_DEG`）。影响限于文档准确性与可维护性（改 `FALLEN_TILT` 不会改到终止门），行为本身自洽（奖励门 60° 比终止门 70° 更早，方向正确），故降为建议级残余。建议：三处 `70.0` 改为 `math.degrees(C.FALLEN_TILT)`，或设计文档第 43 行分别写明「奖励侧 60°／终止侧 70°」。 |
| R5 一般 | `docs/development.md:221` 与 `docs/design/skill_task_migration.md:128-130` | 实现记录写「`make check` 全绿：锁文件、ruff、222 个测试、模型、文档检查均通过」，同一任务的设计文档验收表却把 `make check`、`make docs`、独立审查都列为「待执行/待指派」。两处对同一验收项给出互斥状态。影响：交付证据无法判定；审查者只读且不得运行检查，无法仲裁。建议：由实现者实际执行一次并只保留一处结论（设计文档验收表写结果、开发文档写命令与摘要），删除另一处的「待执行」。 **验证**：`make check` 退出码 0；19 文件/107 链接/50 任务行的文档检查通过。 | `make check` 已实际执行并只保留一处结论：设计文档验收表写结果，开发文档写命令与摘要。 | 审查者：已复核关闭（未跑 GPU 项）。审查者独立执行且全部通过：`pytest -q tests` → **222 passed, 8 subtests passed, 1 warning**；`tools/check_docs.py` → `docs check passed: 19 files, 107 links, 50 task rows scanned`；`tools/check_robot.py` 通过；`ruff check src tools tests` → `All checks passed!`；`uv lock --check` 解析 222 包；`git diff --check` 无输出。故「222 个测试」的说法成立，两处证据也已收敛为一处。仍未执行：`tools/check_velocity_env.py` 与任何 GPU 训练（审查者不得运行训练，且同卡另有他人训练任务占 6868 MiB）。 |
| R6 建议 | `src/ht_microduck/tasks/curriculum.py:87-88,104-108` | `event_param_curriculum` 的日志快照只接受 `int/float/bool`，`mixture` 是 4 元组，被静默丢弃；`Curriculum/ground_state_mix/mixture` 因此从不出现在训练日志中（`.artifacts/t049/train_HtDuck-Flat-VelStand.log` 只有 `recovery_economy/weight` 与 `face_down/face_down_prob` 两个键，可作旁证）。影响：与 R3 叠加后，地面起始混合的生效时机在日志里完全不可观测，只能靠读 `event_manager` 内部参数确认。建议：对不可标量的参数改为 `torch.tensor(value, dtype=...)` 时按元素展开为 `mixture/0..3`，或单独记录首元素与是否已越过阶段。 **验证**：实测日志键：`Curriculum/ground_state_mix/mixture/0..3` 与 `Curriculum/face_down/face_down_prob` 均出现。 | `event_param_curriculum` 对元组参数按分量展开为 `key/0..N`，日志侧由 `CurriculumManager.reset` 逐项展开。 | 审查者：已复核关闭。源码核对 `curriculum.py:99-118` 的展开分支；`grep -o "Curriculum/ground_state_mix/mixture/[0-3]"` 在 `.artifacts/t049/tr4_*.log` 中命中 0/1/2/3 四个键（与 `face_down/face_down_prob`、「recovery_economy/weight」同现）。 |
| R7 建议 | `src/ht_microduck/tasks/commands.py:96-147`；`src/ht_microduck/tasks/posture_mdp.py:117`、`:149`；`tasks/flat_velstand_env_cfg.py:184`；`tasks/flat_standup_env_cfg.py:126`、`:135`；`tasks/flat_sitstand_env_cfg.py:112`；`tasks/flat_velstand_env_cfg.py:163` | 死代码与未引用常量：`StandingGatedPoseCommand` 及其 `Cfg` 只在本文件内互相引用；`_joint_target_error`、`body_upright_linear` 无调用点；`FELL_OVER_DISABLE_ITER`、`STAND_DWELL_S`、三处 `SERVO_IMPACT_N` 均无引用（grep 只命中定义）。影响：`FELL_OVER_DISABLE_ITER=500` 与 `STAND_DWELL_S` 的注释描述了一个实际未实现的行为（「早期关闭跌倒终止」「站立驻留 0.4 s」），读者会误以为已生效。建议：删除；若 `FELL_OVER_DISABLE_ITER` 代表的意图（早期不终止跌倒）仍需要，改由 R3 校正后的 curriculum 显式实现。 **验证**：`ruff check src` 通过；64 环境探针实测「行走时非零躯干指令」0 次。 | 删除 `_joint_target_error`、`body_upright_linear`、三处 `SERVO_IMPACT_N`、`STAND_DWELL_S`、`FELL_OVER_DISABLE_ITER`；`StandingGatedPoseCommand` 未被删除而是**接入使用**——velstand 的 `body_pose` 改用该门控命令项，这正是「行走时躯干指令为零」的部署不变量。 | 审查者：已复核关闭（附一条口径说明）。"`_joint_target_error` / `body_upright_linear` / `SERVO_IMPACT_N` / `STAND_DWELL_S` / `FELL_OVER_DISABLE_ITER` 在 `src/` 内 grep" 在 `src/` 内 **0 命中**，删除干净；`StandingGatedPoseCommand` 确实被接线（velstand `:592` 的 `body_pose` 使用该 Cfg）。自建 64 环境探针：行走中「非零躯干指令」`max = 0.000000`、违规 **0 / 20817** 个行走环境步，站立占比 0.30、躯干指令非零占比 16%——门控真实生效。口径说明：本轮做的是「保留并接入」而非「删除」，功能上等价且更好，但与 R7 原文「建议删除」不同，记录在此以免读者误解。 |
| R8 建议 | `src/ht_microduck/tasks/shared.py:118-124`；`tasks/__init__.py:86-121` | `_resolve(slot, dim)` 声明了 `dim` 参数却从未使用，因此补零槽位的声明宽度（twist 3 / head 4 / body 6）不会被校验；导入期守卫 `_assert_task_contract` 也只对带 `params["command_name"]` 的槽位比对 `commands[name].dim`，补零槽位被跳过。实际宽度只由运行时 `shared.assert_actor_dim`（`:100-115`）在建环境时把关。影响：若有人把 `zero_command_padding(4)` 写进 body 槽，导入期不报错，只在建环境时以总宽不匹配的形式失败，错误信息不指向具体槽位。建议：在 `_resolve` 内对 `zero_command_padding` 的返回值断言其宽度等于 `dim`，或在导入期守卫里对补零槽位用 `ACTOR_OBSERVATION_DIMS` 逐槽校验。 **验证**：故意传入 `zero_command_padding(4)` 作为 body 槽时守卫报错：`padded slot 'body_command' is 4-wide but the contract needs 6`；正常配置通过。 | `zero_command_padding` 把宽度记录在 term 对象属性 `padding_dim`（不放 `params`，否则会被当关键字参数透传）；导入期守卫对补零槽也逐槽校验。 | 审查者：已复核关闭。自建注入探针把 body 槽改成 `zero_command_padding(4)`，导入期即复现 `ValueError: HtDuck-Flat-Velocity: padded slot 'body_command' is 4-wide but the contract needs 6`；未注入时四任务全部正常注册。守卫代码在 `tasks/__init__.py:106-116` 读 `getattr(term, "padding_dim", None)`。 |

| R9 一般 | `src/ht_microduck/tasks/posture_mdp.py:84-97`（`_prev`）、`:220-243`（进度项）、`:283-297`（`_ht_bounty_armed`）、`mdp.py:107-117`（`_ht_prev_contact`/`_ht_air_time`）；对照 `mjlab/managers/reward_manager.py:100-114,174`、`sensor/contact_sensor.py:350-358,462-468` | **本轮新发现（非本轮修复引入）。** 奖励项把回合内状态存在 `env._ht_*` 上，但没有任何项注册类式 `reset(env_ids)`，`RewardManager._class_term_cfgs` 因此为空（`reward_manager.py:174` 只收 `hasattr(term_cfg.func, "reset")` 的可调用对象），`_reset_idx` 从不清理这些缓冲；而 mjlab 自身的 `ContactSensor.last_air_time` 是逐环境 reset 安全的。后果：新回合第一步的差分/支付对比的是**上一回合的终止状态**。实测（32 环境 VelStand）：`upright_progress` 在 344/360 次重置支付，原始均值 +0.251（加权 +0.0251/步，最大 +0.0327）；`height_progress` 2421/2706 次支付；`air_time` 385/2706 次把重置前未结算的摆动付掉（最长 0.280 s → 加权 +0.06），在 `episode_length_buf==1` 的 173 次支付里 **173 次**都用到了跨越重置的旧摆动、合法者为 0。聚合看：短回合探针中平均回合回报 +0.049，其中首步贡献 **+0.042（约 66%）**；且所有非零重置支付**均为正**——等于「越早摔倒越赚」，与 `recovery_bounty`/`fallen_tax` 的反刷分设计方向相反。单独对照实验（standup，同种子 8 环境）：基线 `upright_progress` 回合均值 −0.0298（最大 +0.0294），把首步差分按 0 处理后为 −0.0828（最大 −0.0632），即该泄漏把一项本应恒为负的差分量抬到了可正可负。依据：`reward_manager.py:100-114` 的 `reset` 会逐项调用 `func.reset(env_ids=...)`，本项目无一项使用该协议。建议：把 `upright_progress`/`height_progress`/`air_time`/`recovery_bounty` 改为类式奖励项并实现 `reset(self, env_ids)` 清空 `_ht_*` 对应行；成本更低的替代是在各函数内用 `env.episode_length_buf <= 1` 把首步差分/支付置零（重置后第一步无历史可言）。修复后应断言「重置后首步 `upright_progress`/`height_progress`/`air_time` 支付恒为 0」。**范围判定**：该缺陷早于 T049（`_ht_*` 方案来自既有 `mdp.py`），三个新任务因新增了依赖它的进度/奖励项而继承了它；它不是 R1–R8 任一修复引入的回归，本轮 8 项修复的复核结论不受影响。 已修复：`posture_mdp.py` 新增 `_REWARD_STATE_KEYS` + `reset_reward_state(env, env_ids)` 与类式项
`RewardStateReset`（weight 0.0），四个任务均注册；`RewardManager` 的既有 reset 路径即会清空
`_ht_posture_prev`/`_ht_fallen_timer`/`_ht_fallen_timer_bounty`/`_ht_bounty_armed`/
`_ht_fallen_tax_state`/`_ht_air_time`/`_ht_prev_contact`，未改动 mjlab。**验证**：
`.artifacts/t049/probe_reward_leak.py`（32 环境、12 轮、384 次重置）重置后首步
`upright_progress` 支付 **0/12 轮**、合计 0.0000（修复前为 344/360 次支付）；直接读缓冲确认
`_ht_posture_prev` 由 dict(3) 变 dict(0)、`_ht_prev_contact` 由 sum16 归零。 | 已复核待确认（实现者自查） |

无问题项（逐焦点结论，均有上述探针或源码核对支持）：

1. **契约一致性与导入期守卫**：`contract.ACTOR_OBSERVATION_SLICES` 由 `ACTOR_OBSERVATION_DIMS` 与
   `ACTOR_OBSERVATION_TERMS` 同一次循环生成，三者按构造一致；61 = 3+3+14+14+14+3+4+6，
   critic 64 = 61+3；四任务实测 `(61,)`/`(64,)`、动作 14、`step_dt` 0.02（50 Hz）全部吻合；
   `validate_contract()` 覆盖关节覆盖数 15、策略/持住不重叠、`LOW_POSTURE_JOINT_POS` 子集等断言。
2. **奖励项 weight 符号**：四个 cfg 的 12/15/17/24 个奖励项逐项比对，凡函数返回非负量者权重为负
   （`dof_pos_limits`、`action_rate_*`、`joint_torques_l2`、`joint_vel_l2`、`self_collisions`、
   `head_impact`、`body_impact`、`fallen_tax`、`foot_slip`、`foot_clearance`），凡函数已返回负值者
   权重为正（`rise_speed_cap`、`descent_speed_cap`、`trunk_accel`、`posture_error`、
   `posture_error_joints`），凡返回正收益者权重为正（`upright_progress`、`height_progress`、
   `recovery_*`、`track_*`、`posture_*`、`head_pose_tracking` 等）。唯一的符号倒置是 R1 的
   `air_time`，且其根源在函数而非权重。
3. **门控逻辑**：`posture_mdp.fallen_mask` 用 `low & (tilt > limit)` 的合取，与 `contract.py:194-205`
   记录的「坐姿 0.0563 m 低于所有躺姿 0.060–0.093 m，故高度不能单独判跌倒」一致；
   `recovery_success(:302-335)` 需先累计 `timer > min_fallen_s` 才置位，支付后立即解除，
   振荡重获奖励必须重新越过 `fallen_tilt_deg`，不存在逐帧刷分；探针确认站立态
   `recovery_bounty`/`fallen_tax` 恒为 0；`upright_progress`/`height_progress` 的 `_prev` 在
   **同一回合内**单调比较、不产生跨帧跳变。
   **但跨回合不成立**：`_prev` 缓冲不被 `_reset_idx` 清理，新回合首步差分对比的是上一回合终止态，
   会正向支付（见 R9）——此处为对第一轮「reset 后不复位」正/负结论的修正。
4. **关节寻址**：所有姿态项按名称经 `_slot_of` / `SceneEntityCfg` 解析，无裸下标；模型 15 关节以
   `mouth_joint` 结尾而策略 14 关节以 `head_roll_joint` 结尾，实测解析 `[0..9]`（腿）与
   `[10..13]`（头）正确；`mouth_joint` 只在 `HELD_JOINT_NAMES` 中出现，未被任何奖励/事件按名或按下标触及；
   传感器的 `primary_names` 顺序（`r_foot_collision`, `l_foot_collision`）与 `FOOT_SITE_NAMES`
   顺序一致，脚部两项奖励不会左右脚错位。
5. **mjlab 1.6.0 API**：`reward_curriculum`、`event_param_curriculum`、`bad_orientation`、
   `SceneEntityCfg.resolve`、`ContactSensorCfg(reduce="netforce"/"none")`、`EventManager.get_term_cfg`
   （与 `apply` 同一对象）均在 1.6.0 中存在且语义与调用方式一致；四任务构建与 6 步运行无异常。
6. **风格约束**：`src/ht_microduck/tasks/` 无中文字符；代码/注释英文、文档中文的约定未被破坏。

## 最终结论

- 审查状态：**第二轮复核完成 —— 独立审查通过（附 R9，已由实现者修复，待第三轮复核确认）**。R1–R8 八项由审查者
  用自建探针逐条独立复核，全部确认为真实修复（非表面修补），无一回归；复核中发现并记录 1 项
  **先前不在清单上的既有缺陷 R9**（`env._ht_*` 奖励状态跨回合泄漏），另有 3 项建议级残余
  （倒地判定 `70.0` 字面量、设计文档第 132 行的旧 air_time 证据文字、`STEPS_PER_ITER` 手工同步）。T049 在
  [任务表](../development.md) 中仍为「进行中」，本记录不改变该状态。
- 问题关闭情况：
  - R1（阻塞）**已复核关闭**：区间计数形式，112 次落足中 14 正 / **0 负** / 98 零，0.13–0.20 s 支付 2.0，
    <0.125 s 与 >0.300 s 支付 0。注：第一轮要求的「随时长单调」已被区间计数取代，属与官方一致的更严口径。
  - R2（一般）**已复核关闭**：128 次重置，姿态/flag 不一致 0 次、alpha/flag 不一致 0 次，flag 无残留。
  - R3（一般）**已复核关闭**：阶段点 600/1500/2600 与 1200 均按 `_iter()` 折算为环境步，逐点实测生效。
  - R4（一般）**部分复核**：死常量已复活并被引用、设计文档主表已对齐；残留 `fallen_too_long` 三处
    `70.0` 字面量（建议级，见上表）。
  - R5（一般）**已复核关闭（GPU 项除外）**：审查者独立跑出 222 passed / 8 subtests、文档检查
    19 文件 107 链接、`ruff` 全通过、`uv lock --check` 正常；`tools/check_velocity_env.py` 与训练未跑。
  - R6–R8（建议）**已复核关闭**：`mixture/0..3` 日志键真实出现；死代码 grep 0 命中且门控命令项确有接线
    （行走中违规 0/20817）；补零槽注入探针复现出精确的槽位错误信息。
  - R9（一般，**本轮新提出**）**已修复待复核**：细节与实测见上表；修复方式为类式项
    `RewardStateReset` + 集中的 `reset_reward_state`，未改动 mjlab 本体。
- 回归检查（审查者自测）：四任务仍为 `actor=(61,)`、`critic=(64,)`、动作 14、`step_dt=0.02`（50 Hz）、
  6 步运行奖励有限且无 NaN；61 = 3+3+14+14+14+3+4+6、64 = 61+3 未变。
- 最终集成验证：本次结论对应工作区 `HEAD` + 未提交改动（含 `tasks/` 下 9 个新增未跟踪文件）的最终内容；
  审查者只读，除本文件外未产生任何写入（临时探针仅在 `.artifacts/review/` 内，已删除）。
  审查后若实现者继续修改 `posture_events.py`、`posture_mdp.py`、`mdp.py`、`flat_velstand_env_cfg.py`
  或两份文档，需重新复核对应条目。
- 建议级残余（均不阻塞，建议随 R9 一并处理）：
  - 设计文档第 132 行的 air_time 证据仍写「随时长单调 / 0.13 s→+0.05，0.40 s→+0.59」，
    与现行为区间计数不符（0.40 s 现在支付 0）。该表行应改为「摆动落在 0.125–0.300 s 内计 1」。
  - `fallen_too_long` 的 `gate_tilt_above_deg` 在三个 cfg 中写死 `70.0`，未走 `C.FALLEN_TILT`；
    设计文档第 43 行只写「倒地判定 60°」，读者会以为改常量即可改终止门。
  - `flat_velstand_env_cfg.py` 的 `STEPS_PER_ITER = 24` 与 `num_steps_per_env=24` 靠手工同步，
    无测试断言二者相等；`num_steps_per_env` 一旦改变，R3 的阶段点会静默失准。
- 限制与后续：
  - 审查者**未运行任何训练**，`tools/check_velocity_env.py` 也未执行；设计文档验收表中依赖 GPU 的
    行仍属实现者自证，不由本审查背书。
  - 本次只审静态契约、奖励/门控/课程语义与重置时序，**未评估**策略收敛质量、Rough 变体地形参数、
    ONNX 导出与实机时序；三个新任务能否收敛需要按官方迭代上限完整训练才能判断，不属本审查结论。
  - 范围外的既有问题：仓库工作区存在与本任务无关的大量未提交改动（`docs/design/repo_layout_alignment.md`、
    `actuators/`→`actuator/`、删除 `src/ht_microduck/algorithms/*` 等），未纳入本次审查。
  - R9 与 R1 同属「早于本次改动、但新任务新增了依赖」的情形：建议随 T049 一并修掉，理由是三个新任务
    的进度项正是靠首步正支付把「摔倒」变成正收益，会与 `recovery_bounty`/`fallen_tax` 的反刷分意图直接抵消。

审查通过不授予 Git 提交或发布权限，任务状态只在开发文档统一维护。

## 2026-10-29 行走回归修复独立审查

范围：本轮以 `9840fa8` 和修改前工作区为参考，修复用户报告的「能站住，但不迈步」。
独立只读审查者为子代理 `walk_review`，实现者为主代理。文件覆盖
`tasks/{mdp,shared,contract,flat_velocity_env_cfg,__init__}.py`、
`tools/{check_task_contract,check_velocity_env}.py`、`tests/test_velocity_env_cfg.py`、
新增 `tests/test_walking_rewards.py`，以及任务与设计中的本轮差异。
保留已有未提交重构、删除和姿态技能实现；该审查不追认上方 R9 其他姿态进度项的全部行为。

审查者核对了本机 mjlab 1.6.0 的 `tasks/velocity/mdp/rewards.py:209–238`、
`sensor/contact_sensor.py:350–371,441–485` 与 `ManagerBasedRlEnv` 的子步更新及 reset 时序：
连续腾空区间计数包括纯 yaw，传感器计时随物理子步推进，局部 reset 只清指定环境。
三个姿态任务的动作缩放 `1.0`、随机头部范围均保留，Velocity 独用 `.25` 与 HOME 头目标；
61/64/14 和 50 Hz 未变。相同向量维度不保证动作语义相同，修复后的行走策略须重新训练。

审查者独立执行奖励及配置专项测试：`9 passed`，只有既有 `torch.jit` 弃用警告。
未发现代码正确性阻塞。提出的三处注释建议（形状相同不等于直接热切换、VelStand 并非原样继承、
设计中的统一运行时说明）已由实现者同步。代码审查结论为**独立审查通过**；
GPU 和短训练由主代理运行，其结果及策略效果限制见任务完成记录，审查通过不代表策略已收敛。

完成 300 次迭代后，审查者再次核对了任务记录、`model_299.pt` 和 `replay.json`：
1,843,200 转换、约 258 s、32 环境三种固定指令均无跌倒但也无有效摆动，
与「仍未学会迈步、效果验收未完成」的记录一致。本轮只可称为
「已修正已确认的奖励实现错误，并恢复旧版部分行走配置」，不能称为「已解决静止」。
修改前配方的同预算对照结果由实现者补记，不作为已恢复行走的证据。

## 2026-10-29 零指令持续抬脚修复审查

独立只读审查者 `idle_review`，实现者为主代理。本轮范围是
`tasks/{mdp,posture_mdp,contract,flat_velocity_env_cfg,flat_velstand_env_cfg}.py`、
两项奖励/配置测试、`tools/check_velocity_env.py` 和本轮任务/设计说明。
对照修改前工作区快照，保留此前未提交改动；本次不重新审查原姿态任务的全部奖励状态。

审查者确认：零指令门控 `<=.01` 与上游腾空奖励 `>.01` 互补，纯转向保持运动激励；
足速归一化后成本无量纲，头部与 HOME 关节位置不作为惩罚输入；
`posture_mdp→mdp` 的依赖没有循环，恢复高度减去了环境原点，
`smoothstep(cos tilt, cos60°, cos25°)` 的方向与高度渐入正确。
不再使用跨过 `.13 m` 或 `25°` 即完全免罚的硬门控；慢蹲/慢倾仍可能降低代价，
其与姿态奖励的平衡需要训练评估，不能由静态审查排除。

审查者独立运行专项测试：14 passed（2.79 s，仅有既有 `torch.jit` 弃用警告），
未发现阻塞或一般问题，**独立代码审查通过**。
GPU 工具只读复核通过：实际 twist 张量被直接置零/写入，真实基座抬高后仿真和接触状态更新，
之后 reset 隔离后续检查。审查建议补充接触传感器的双脚离地断言，主代理已落实并重跑 GPU。
GPU 和 5 次迭代训练由主代理执行，其数据见任务记录；审查者没有独立运行 GPU 或训练。

审查结论只覆盖新训练目标和运行链路，旧 checkpoint 不会因新增奖励自动改变行为，
未验证零速停步策略收敛，也未宣称解决整体行走效果。

## default_pos 最小站立约束复核

按用户新要求撤除前述足底惩罚与恢复门控，本节为当前实现的审查结论。
独立只读审查者 `regression_audit` 确认：`stand_still` 直接读取 `default_joint_pos`，
按配置的 14 个策略关节计算 L1，负权重 −0.5，零指令生效而移动/纯转向关闭；
VelStand 不增加 HOME 约束，旧 `idle_feet`、速度尺度、恢复高度/倾角链路已撤除。
61/64/14、`.25` 行走缩放和 50 Hz 不变。

独立 CPU 专项 11 passed（2.84 s），无阻塞或一般问题，代码审查通过；
默认值非零、关节子集、阈值与纯转向均有覆盖。GPU 工具以真实关节写入验证
默认姿态 cost=0、单关节 `.1 rad` 偏差 cost=.1，符合最小需求。
GPU 由主代理执行；本轮没有新增训练，不能声称正在运行的旧进程已自动采用新奖励或策略已收敛。
## 平地行走奖励对齐官方复核

关联 [T049](../development.md) 与[本轮设计](../design/skill_task_migration.md#2026-10-29-平地行走奖励对齐官方)。
实现者为主代理及 `head_bias`；独立审查者为只读代理 `reward_reference_review`。
审查范围：`flat_velocity_env_cfg.py`、`mdp.py`、`test_head_pose_bias.py`、
`test_official_walking_rewards.py`、`tools/check_velocity_env.py` 与本轮设计/开发记录。
现有重构、用户删除及其他实验文件不属于本轮修改范围。

基准为 `microduck_rl@bae39f59` 的平地 Velocity 与其 mjlab 1.3.0 依赖；审查者对身体角速度、
角动量、足高、滑动和峰高五项做 AST 比较，确认与本机 mjlab 1.6.0 相同。头部偏差以
`mdp.py:5614–5702` 的 1 s 有符号 EMA 为基准，负量/正权重改成正量/负权重，结果等价。

| 关注点 | 实现与验证证据 | 复核结论 |
|---|---|---|
| 公式与符号 | 五项复用 mjlab；EMA、平方滑动、足高速度加权、落足结算有固定数值测试 | 通过 |
| 足端传感器与顺序 | right/left frames 与 site、contact 顺序一致；任务级 ray 分组排除机器人；GPU 只命中地形 | 通过 |
| 回合状态隔离 | 峰高最薄子类补 reset，头部 EMA 类式 reset；单测真实 RewardManager 与 GPU 局部 reset | 通过 |
| 课程与影响范围 | 0/600/1000/1500×24 环境步对应 0/−1/−2/−3；三个姿态任务保持原配方 | 通过 |
| 运行证据 | `make check` 244 passed + 8 subtests；4 环境 GPU 专项通过；16 环境 5 迭代退出 0，检查点张量全有限 | 通过 |

审查状态：**独立审查通过**。`reward_reference_review` 已只读核对最终实现、专项测试、GPU 日志、
正式短训配置/日志及检查点检查 JSON，本轮范围内未发现阻塞或一般问题；确认专项工具先接地再验证
滑动正值的前提修正合理。审查者没有重复启动 GPU 或训练。限制：GPU/短训证明路径与数值正确，不证明策略收敛、稳定行走、
跟踪改善或实机效果。完整实验与固定指令评估未在本轮执行。


## T055 除 VelStand 外对齐官方任务复核

### 范围与基准

用户要求保留 `tasks/config/flat_velstand_env_cfg.py`，其余现有任务按官方；后续明确选择
「使用已测量的 HT 姿态与高度，其余任务逻辑和参数按官方」。设计见
[对应追加节](../design/skill_task_migration.md#t055-除-velstand-外逐项对齐官方任务)。
基准为 `microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb` 三个任务工厂、实际引用的
MDP 和 mjlab v1.3.0 基础 Velocity 配置。本机运行 mjlab1.6.0、仓库 RSL-RL5.4.2、HT 混合执行器。

实现者为 walking_alignment、posture_alignment、official_mdp_alignment 与主代理；
独立只读审查者为 official_task_review。审查包含新增未跟踪文件、四工厂、official_* MDP、
registry/contract/runner、测试/工具、授权硬件适配和保护快照；原有 VelStand 问题不在本次修复范围。

### 问题与复核

| 编号 | 严重程度 | 问题与影响 | 实际处理 | 独立复核 |
| --- | --- | --- | --- | --- |
| T055-R1 | 一般 | StandUp保留官方0.05–0.09 m躺姿高度，对HT真实pitch±90°会产生名义几何穿地；旧PRONE_Z来自旧roll轴姿态 | 独立计算真实HT碰撞最低顶点，前/后躺分别加入硬件参考偏移；保留抽样次数、概率、带宽和额外侧滚角 | 已核对几何值、默认零偏移、同种子RNG及最终名义躺姿GPU专项，已关闭 |
| T055-R2 | 一般 | 初版adapter删除Velocity reset z维度，改变官方均匀高度分布 | 改为官方绝对高度减官方站高，加HT站高，再扣HT默认根高；保留原1cm带宽 | 代码与宽度复核通过 |
| T055-R3 | 一般 | 力矩变化代价与reset缓存包含HT额外的嘴执行器，偏离官方14策略执行器 | 按策略名称和preserve_order选择执行器列，reset使用同一选择 | 打乱列序且mouth置中测试通过，嘴单独变化不影响代价、局部reset不改邻居 |
| T055-R4 | 一般 | bearing_roll字面包含roll，但官方真MJCF的直属关节是right_hip_yaw；初版映射错了DR身体 | 改为HT r_hip_yaw_link，保留原上游头部DR含髋yaw身体的选择；增加真实直属关节与body_ipos列测试 | 源MJCF直属关节、四任务实际DR列及最终冻结三配方训练均复核通过，已关闭 |

本地新增说明语言建议已处理；不因格式偏好改变上游移植公式。

### 已执行核查与运行证据

- 独立核对三工厂顶层常量：Velocity无差异；StandUp/SitStand仅HT姿态/高度、坐姿字典、腿头索引
  存在已授权适配，其他开关、权重、时序与课程同源。PPO/网络数值及迭代上限逐项一致。
- 工厂与观测/奖励共14项AST对应证据保留在
  `logs/official_task_alignment_20261029/walking_formula_parity.json`；姿态28函数公式独立核对。
  不把API选择器适配或明确列出的硬件参考变换写成字节相同。
- 独立专项复跑42项通过，覆盖三项修复；主代理新增runner实例隔离与load顺序2项通过。
- 保护文件、全部旧MDP源码与train/play/RL完整配置独立对照一致；主代理保存
  `logs/official_task_alignment_20261029/velstand_protection.json` 及前后快照。
- 主代理 `make check` 通过336项和8个subtests，四任务GPU动态/后期课程检查与三配方正式CLI短跑通过。
- 最终三个不同配方的至少600秒实际采样/PPO更新、检查点全量恢复和推理均已完成，实际退出码、
  时间、检查点与最终结论见下节。GPU/短跑及有界训练不作为策略收敛或硬件效果证据。

首轮三组600秒训练与fresh-env独立恢复已通过，但最终拓扑复核发现R4，故上一轮结论不沿用；
R4后的最终结论以下节冻结证据为准。首次恢复失败退出码1和原产物保留。


### T055 最终结论与冻结证据

独立只读审查者official_task_review最终结论：**独立审查通过**。R1–R4全部关闭，无剩余阻塞或一般问题。

- R4后独立读取两种官方机器人XML的直属关节并与HT模型对应；四任务真实body_ipos写入列及
  局部环境隔离已检查。此前72项独立测试和新增4项拓扑测试通过，R4后的velocity专项16项独立复跑通过。
- 从最终三组TensorBoard事件独立重算collection+update为600.190533/600.579648/600.072179秒，
  对应595/654/701次更新，四类Loss所有样本有限；最终全流程退出码均0。
- 直接CPU加载最终model_594/653/700.pt，各76个张量有限；iter、环境计数与updates×24一致。
  新环境全量恢复和十步推理、Head别名加载最终Velocity权重均通过。
- 每组29份生产源码与当前文件、manifest及冻结副本逐一SHA-256相同；保护文件、旧MDP与完整
  train/play/RL配置再次独立一致。最终依据为training_final、*_env_final与acceptance_final.json。
- 名义躺姿专项的原始数据和成功退出已读取；该测试没有额外侧滚，不扩展为所有随机姿态无穿透或
  稳定保持的结论。首次训练后同环境恢复失败的退出码1及修正前产物完整保留，未冒充最终证据。
- 主代理最终make check通过340 tests和8 subtests；最终归档后另执行make docs。

源码、运行命令、检查点、来源与复核范围见对应设计追加节以及
`logs/official_task_alignment_20261029/`。没有未解决的实现问题；策略收敛、固定指令效果、
实机效果和远端同步属于范围外后续工作。所有独立检查进程已结束，审查者未修改文件。


## T057 恢复机制与 HT 高度适配

### 审查范围与基准

- 设计：[T057恢复修复设计](../design/skill_task_migration.md#t057-官方恢复机制与-ht-坐站高度修复)。
- 作者：velstand_config负责VelStand配置与相应测试；recovery_mdp负责events/posture和reset测试；统筹者负责SitStand、注册、GPU/训练验收与文档。
- 独立审查者：code_sync_review，默认只读，未编写上述实现。
- 官方基准：microduck_rl固定提交`bae39f5900b318f7e87fc485c30a31213cfa14eb`；本轮仅已批准的环境修复阶段，专家/热启动与完整v8硬件防护后续。
- 旧工作区快照：`logs/posture_recovery_20261030/validation/baseline_manifest.json`及`baseline-code.tar.gz`，包含54份源码/测试/文档；保留用户所有既有Git改动和训练产物。
- 当前审查：设计、实际代码、GPU、训练及恢复结果的独立复核全部通过，以下记录与最终交付范围一致。

### 问题与修复记录

| 编号 | 严重程度 | 位置与触发条件、影响、依据 | 处理与复核 |
| --- | --- | --- | --- |
| T057-R1 | 一般 | 只迁入身体跟踪而保留绝对直立奖励时，完整姿态奖励可能更偏好忽略倾角目标；官方同组body安装函数还改用相对目标upright | 配套修复两个直立项角度参考，完整奖励栈与零指令恒等测试通过；独立复核关闭 |
| T057-R2 | 一般 | reset在推理张量上下文外原位更新有效位/计时会抛异常 | clone后局部更新与跨模式局部reset测试通过；独立复核关闭 |
| T057-R3 | 一般 | 本地成功武装/恢复超时使用严格大于，官方为大于等于，会多延迟一控制步 | 按官方>=计时和严格cos/高度门限修正，17项恢复专项通过；独立复核关闭 |

### 验证与结论

首轮 `make check` 为377 passed、8 subtests；R3修复后重跑为380 passed、8 subtests。
首轮GPU验收的阶段/状态/身体目标检查完成，但测试在inference_mode创建上游延迟缓存后，
又在该上下文外调用完整env.reset，触发mjlab circular_buffer原位更新限制。
核对官方ViewerBase实际使用no_grad后，将GPU回放验收改为相同张量模式；保留失败日志，
不修改上游框架。单独的本地势函数跨模式重置已由正式CPU测试覆盖。
最终训练预算、GPU与恢复证据已完成独立复核，结论见下一节；本阶段仍不宣称技能效果已复现。


### T057 最终复核结论

code_sync_review独立复跑69项相关CPU测试，并复核最终380 passed/8 subtests基础检查、
两个GPU环境检查与控制姿态状态机检查，R1–R3全部关闭。
独立CPU解析两个已结束的原始TensorBoard记录，确认实际采样+更新时间分别为
SitStand600.436701536 s/998更新、VelStand600.370447636 s/483更新，与`result.json`一致；
两个检查点各76张量有限、iter与env_steps一致，新环境完整恢复后10步推理通过。
29份任务源码snapshot和93份运行源码/资源的current/frozen/code_state哈希全部相符。

验证与配置证据长期保留在 `logs/posture_recovery_20261030/validation/`，
训练产物在相邻`sitstand/`和`velstand/`。GPU测试曾因验证代码混用上游inference延迟缓存模式
失败，按官方ViewerBase的no_grad生命周期修正后复跑通过，失败日志保留。
最终GPU新增状态注入检查不修改生产源码，不要求重复600秒训练。

独立审查通过仅覆盖本阶段环境修复和链路验收：VelStand483次更新未进入500后的恢复阶段，
后期课程只有专项检查覆盖；不宣称技能已学会或官方v8完整复现。保留HT特定低姿态、61/64/14
与物理时序等已确认差异，专家BC与跨任务热启动仍是下一阶段。

## T058 物理目标约束与饱和诊断

### 审查范围与基准

- 需求与设计：[T058目标约束](../design/skill_task_migration.md#t058-坐站与组合任务的关节目标约束)。
- 实现者：`action_impl`负责动作与指标模块，`action_tests`负责CPU边界测试；统筹者负责配置、
  对照注册、CLI/GPU/训练验收及文档。
- 独立审查者：`action_review`，默认只读，未参与实现。
- 审查基准：`logs/action_bounds_20261030/validation/baseline-code.tar.gz`及对应SHA256清单，
  包含修改前161份文件，另保留原Git状态、已暂存/未暂存差异与未跟踪列表。
- 范围包含新增未跟踪文件`mdp/actions.py`、`action_metrics.py`、三个`test_bounded_action*`测试文件，
  两任务配置、注册与契约、README、设计和任务记录；不将工作区其他已有改动算入本轮作者范围。
- 编码前设计审查及生产代码、真实GPU和训练/恢复证据的最终独立审查均通过。

### 问题与复核

设计审查要求已落实：偏置后限幅、方向相关动态力矩包络、零包络、逐控制帧计时和局部reset，
以及实际CLI对照入口。上游PlayConfig没有env字段，因此新增两个显式`-Unbounded`对照任务，
而非向CLI薄封装加入独立配置逻辑；CPU测试实际调用官方Tyro入口并拦截环境构造。
后续实际缺陷与修复复核在本节继续记录。

| 编号 | 严重程度 | 位置、触发条件与影响 | 修正与复核 |
| --- | --- | --- | --- |
| T058-R1 | 一般 | T058设计结果把76个检查点张量称为模型张量；实际actor13、critic12、优化器51，统计范围表述错误 | 仅修正本轮为“76个检查点张量（含模型、归一化与优化器）”，历史原措辞保留；独立复核关闭 |

### 验证与当前结论

CPU边界专项33 passed；配置、CLI与注册集成57 passed，完整检查421 passed和8 subtests。
两任务各8环境的GPU专项退出0，极端动作、正负偏置、坐姿可达及局部reset通过。
旧检查点对照4组进程退出0，启用约束后全部工况下发目标越界为零；旧SitStand起身饱和
约49.6%降至0.7%，但姿态仍未达标，不将控制约束改善描述为技能已学会。

两次32环境seed0的真实采样/PPO更新分别600.937100410 s和602.368088722 s，
更新459/246次；首轮更新凭据写出后仅阻塞等待，结束后统一分析。两个检查点新环境全量恢复
并完成10步推理，另各20步直接核对实际目标范围与嘴保持。
原始事件重算、95份运行代码资源冻结、31份任务源码快照核对及结果在
`logs/action_bounds_20261030/validation/`。两个训练均未进入500之后课程，
不验收坐站/行走/恢复效果，倒置奖励与教师BC保持后续独立验证。
最终独立审查通过，T058-R1关闭。审查者直接从原始事件重算训练预算与更新数，
核对各76个检查点张量、31份任务源码、95份运行文件及归档字节；55/56类全部标量有限、
实际目标越界日志为零，20步恢复目标与嘴保持、旧策略20工况对照及串行时间记录均一致。
独立审计数据保存于`validation/review_audit.json`。仅文档措辞在训练后修正，生产代码保持冻结；
旧策略差值不是严格配对因果效应，不将本次链路验收扩大为技能效果或部署验收。


## T059 独立前坐任务

### 审查范围与基准

- 需求：参考官方新增向前收腿的独立任务，现有任务保留。
- 设计：[T059前坐设计](../design/skill_task_migration.md#t059-独立的-ht-前收腿坐站任务)。
- 基准：`microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb`坐站命令、奖励和课程；HT姿态独立适配，不声明官方精确几何复现。
- 改动：新前坐配置、注册/RL/契约、两份测试及必要使用/设计文档。
- 独立审查者：`forward_review`；只读生产、测试、文档与证据。`forward_reference`另行只读核查关节轴/零位/行程，`forward_tests`实现测试，两者不替代最终审查。
- 保留用户已有`docs/archive/development_records.md`修改，不纳入本轮代码改动。

### 问题与复核

设计初审无阻塞缺口；任务表行前多余空行按建议移除。实现阶段未发现可确认的阻塞或一般问题。
正式GPU工具中的批量高度参数在运行前已按实际`reset_to_posture`接口修正；未放宽验收容差。
独立CPU检查首次受到系统ROS自动pytest插件缺失`lark`影响，按项目Makefile的
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`运行后通过，保留首次输出，不修改项目依赖。

### 已执行实现检查

- 两个种子各16环境、8秒真实固定动作保持，末1秒最大倾角1.585°/1.564°，双脚最小前向X为0.1192/0.1193m；有限值、物理目标约束、局部reset隔离通过。此检查不证明策略已学会前坐。
- `make check`实际438 passed、8 subtests；独立复跑81项CPU专项通过。
- 审查者独立重算旧七任务21份训练/回放/RL配置，全部与改动前字节一致。
- 98份冻结源码、资源和测试与实际文件逐项匹配。
- 最终运行证据由同一独立审查者复核通过：原始事件重算采样+PPO为600.070596秒、1685次更新；
  55类标量、actor13/critic12/优化器51共76个检查点张量有限；模型与优化器全量恢复、新环境10步推理一致。
- step60001后期课程真实GPU检查通过；741条实际下发目标越界记录全零。请求限幅均值63.28%、执行器饱和37.59%，明确不作为技能收敛依据。
- 32份训练任务源码与98份冻结输入逐项哈希一致，最终检查点SHA256与设计结果一致。

### T059 最终结论

实现、环境、至少600秒训练与完整恢复的独立审查通过，无阻塞或一般问题。
新增任务复用官方机制并保留原任务，HT前收脚姿态是硬件行程内的适配；
固定动作保持与训练链路验收均不能替代完整策略前坐/起立效果及实机验收。
原始独立审计、CPU检查、配置对比和训练复算脚本保留于`validation/forward_review/`。

原始记录交付时保留于`logs/sitstand_forward_20261031/`。

## T060 前坐任务修复

### 审查范围与状态

- 需求：解释model_26000没有前坐并修正任务；[设计T060](../design/skill_task_migration.md#t060-前坐失败后的任务修复)。
- root负责Forward配置、RL运行名、显式训练/重置检查、文档与集成；forward_fix_mdp负责本地MDP；
  forward_fix_tests负责CPU回归和显式策略行为工具。独立审查者forward_fix_review只读，未参与实现。
- 基准为本轮修改前工作区，全部任务源码及八任务配置冻结在`logs/sitstand_forward_fix_20261101/baseline/`。
  用户既有文档改动、T059实现和实验保持原状态；不以Git HEAD替代工作区基准。
- 当前状态：独立审查完成；代码与边界检查未发现确认缺陷，训练链路证据核对通过；
  **整体验收未通过**，`T060-BEHAVIOR`保持未解决。训练链路与技能效果分别判定。

### 已处理问题

| 问题 | 处理与验证 | 状态 |
| --- | --- | --- |
| 完成门限用平均髋误差会接受单侧错误 | 本地完成gate改为两髋分别误差小于0.35rad，与行为工具一致；CPU先失败后通过的证据由测试作者保留 | 已复核关闭 |
| 综合奖励仍委托官方alpha中间目标 | 增加缓变完成门限，中间帧不计综合奖励；主姿态与高度独立追踪终点 | 已复核关闭 |
| README仍称前坐完全复用官方配方 | 明确Forward基础阶段、独立奖励、small head范围及新运行名称，保留旧记录措辞 | 已复核关闭 |

### 实际验证与效果状态

CPU专项42项、全量463项/8子测试通过；真实1024个旧噪声压力reset、固定前坐保持、两次4环境运行检查通过。
三轮独立预算实验实际训练均超过600秒，检查点完整恢复、有限值和下发目标限位通过。
第二轮发现只强化髋/部分关节目标仍可能以翻倒取得局部分数，最终增加联合直立门控；
单独权重12仍在真实HOME与60°反例排序中失败，保留失败输出后改13并通过多角度与门控边界回归。

三轮严格行为验收**全部未通过**，均有再次站起0/8，联合成功0；不将训练链路审查扩大为效果通过。
任务T060保持进行中，最终审查须分别给出代码/证据核查与行为未解决项。

### 最终独立复核

forward_fix_review独立复跑42项CPU检查，并核对其余七任务21份配置、最终交付文件和第三轮33份训练源码。
三轮原始事件重算实际训练为600.3861878/600.0954642/600.7956238秒，更新1017/995/997次，
各76个检查点张量有限、恢复证据及下发目标越界全零一致。
扩大静态排序包含静止/综合项后仍满足正确前坐25.9749 > HOME6.9585 > 60°6.6318 >
70°4.4954 > 90°0.00579 > 112°−4.8693 > 180°−13；只支持对应静态反例，不证明动态策略收敛。

最终策略严格轨迹独立重算为1/8前坐、0/8站起、联合0/8，确认行为缺口。
已修代码问题关闭；`T060-BEHAVIOR`仍需后续完整训练与动态过渡验证，不给可用策略或整体验收通过结论。
总审计及三轮原始复算保留于`logs/sitstand_forward_fix_20261101/validation/forward_fix_review_20261101/`。
本轮后续目标门控、越界代价和权重修正由root实现，初版MDP由forward_fix_mdp实现；独立审查者未参与修改。

### 2026-11-02 两版完整训练后的复核

本轮继续T060：[对应设计](../design/skill_task_migration.md#2026-11-02-两版完整训练后的奖励修正)。
root负责Forward配置、MDP、RL名称与结果文档，forward_logs_analysis仅修改前坐CPU测试；
独立审查者forward_reward_analysis只读源码、配置、测试及实际证据，未参与实现或GPU运行。
修改前40份相关文件与完整工作区差异保存在`logs/forward_revision_20261102/baseline/`，
原先未跟踪的Forward文件也纳入审查，其余已有修改和旧训练保留。

| 问题 | 严重程度、触发与影响 | 处理及复核 |
| --- | --- | --- |
| 论文适用性表述超出证据 | 一般；设计原称躯干接地终止不适用于合法坐姿，而本项目主要是髋碰撞体支撑，不能由论文推断必然误杀 | 已改为需要区分合法髋支撑与非法接触，并明确不引入未经验证的新终止；独立审查原文第6.1–6.2节后复核关闭 |
| T060-BEHAVIOR | 阻塞整体技能验收；本轮严格坐/站均0/8，仍未学会完整前坐起立 | 保留未解决；未修改验收门限，不将代码与训练链路通过写成技能完成 |

独立复核确认：

- 本轮正向奖励在60°及以上被门控，取消裸负姿态L1后常驻直立权重2.5可排除已列倒地反例；
  最差与平均误差混合保留非最差膝关节改善的信号。仅支持已测静态排序，不证明动态探索成功。
- 七个旧任务的训练、回放和RL配置与修改前一致，行为/训练工具本轮没有修改；CPU专项49项及全量470项/8子测试证据真实。
- 四环境150步、八环境512次限位压力reset与八秒固定目标保持证据一致，均未被当作策略成功。
- 原始事件逐项累加实际采样/PPO为600.4096763134003秒，856条更新记录；33份训练源码逐项哈希匹配当前代码。
  检查点含actor、critic、优化器与环境状态，76个张量均有限；恢复实现与完成记录支持新环境全量加载后10步推理。
  实际下发越界和NaN终止均为零；请求裁剪与饱和仍高，不能据链路通过推断可部署。
- 新策略原始轨迹1200步/24秒/8环境有限、无自动reset；检查点哈希、关节顺序、髋误差和HOME腿误差重算一致。
  坐下时双脚前向/髋姿态条件全部失败，最后站立的高度/倾角/腿形条件全部失败；联合成功0，确认原门限下真实失败。

本轮代码与训练链路独立审查通过，**整体验收未通过**，T060-BEHAVIOR保留未解决；
本轮512环境短预算与旧版4096环境完整训练不能作等预算比较，也未证明行为改善。
独立复核产物保留于`logs/forward_revision_20261102/analysis/review/`；同一审查者已复核最终文档、三版原始轨迹与汇总、对照图、源码哈希及最终470项/8子测试证据，未发现新增确认缺陷。

### 2026-11-03 v4 初态课程独立审查

实现者为root、forward_state_audit（初始化与正式行为入口）及forward_metrics（度量与CPU边界测试）；
独立审查者为forward_v4_review，未参与被审内容实现，未运行GPU。
范围包括新增v4配置、命令、状态库/回填、度量、runner、三份共享注册/契约文件、采集工具、
可安装初态资源及正式测试；对应[v4设计](../design/skill_task_migration.md#2026-11-03-v4-初态课程与独立保持验收)。

| 编号 | 严重程度 | 触发与影响 | 修复及复核状态 |
| --- | --- | --- | --- |
| V4-R01 | 一般 | 动态样本只有布尔标签，未绑定逐样本复验；易样本可冒充完整难度 | 样本ID、类别、协议、有效帧和剩余时长逐项对应；动态池须包含请求难度边界；独立复核关闭 |
| V4-R02 | 一般 | 正式验收及官方回放不能选择非默认动态状态库 | 检查点携带库原始字节与指纹；回放恢复匹配快照；行为入口支持显式库或在新输出目录恢复快照；独立复核关闭 |
| V4-R03 | 一般 | 整数2的validated列绕过按位证据校验，再转bool被当作有效 | 外部数据边界强制bool；复现样例及拒绝回归通过；独立复核关闭 |

独立审查还推动补齐了保持分组各90%、实际完整难度后的跨阶段门槛、
CLI最终阶段控制过程奖励、缺少姿态case拒绝及不完整检查点恢复拒绝等边界。
初始化/度量33项与课程/行为135项独立CPU复核通过；最终wheel构建、提取后从非editable包加载16端点成功，
库指纹、采集工具和初始化源码哈希与来源记录一致。

独立复算训练事件为600.0149729251862秒实际采样/PPO、810条更新；
原`model_809.pt`与带库快照的检查点76个训练张量全部有限且逐项相同，GPU新环境完整恢复10步通过。
六份初次原始轨迹按几何、髋膝、全腿、倾角和连续有效段重算，
三种子前坐保持均0/16、站立保持分别2/16、0/16、1/16，确认阶段未达标。
该门槛是8秒窗口内连续5秒，不是从首步开始保持；峰值倾角单独保留，未隐藏初段失稳。
最终冻结入口及带库快照检查点的三种子复核保留在`logs/forward_v4_20261103/hold_final_seed*/`，
汇总见`hold_final_comparison.json`，失败均实际退出1。

本轮**代码与训练链路独立审查通过，策略保持及T060整体验收未通过**。
状态库仅有端点，sit/rise/mixed未解锁；未交付完整过渡采集流程或可用前坐策略。
训练后的代码变更限于状态库与检查点外部边界，不改变已测奖励、观测、动作和PPO。
详细独立证据位于`.artifacts/forward_v4_20261103/review/`，最终检查结果由root补充到交付证据。
