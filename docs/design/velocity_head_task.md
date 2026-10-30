# 功能设计：头颈联动平地速度任务

> T055 已将 Velocity 与 Head 对齐为同一官方配方；本文保留此前 Head 变体的设计上下文。当前接口、差异和验收见[任务对齐追加节](skill_task_migration.md#t055-除-velstand-外逐项对齐官方任务)。

关联[当前任务](../development.md)中 T051 的本地并发子工作；任务状态只在开发文档维护。
远端安装与依赖适配由原工作继续，本轮保留其改动，只交付本地新增训练任务。

目录在 T052 按[任务目录整理设计](task_layout.md)迁移：环境/RL 配置位于 `tasks/config/`，
Head runner 位于 `tasks/rl/runner.py`，共享行为位于统一的 `tasks/mdp/`。
下文原路径记录当时实现，历史实验与检查点不回写。

## 目标与范围

用户要求另做一个按官方方法、上半身也会动的 task。新增 `HtDuck-Flat-Velocity-Head`，
同时训练平地速度跟踪与四个头颈关节的随机姿态跟踪；原 `HtDuck-Flat-Velocity` 保持 HOME 头目标。
躯干仍为自由基座，通过直立、角速度和角动量代价保持稳定；按官方 Velocity 保留小范围
`body_pose` 输入但不给躯干姿态跟踪奖励，不把弯腰/蹲起作为本任务目标。

新增环境文件、注册、范围课程、正式测试、GPU 专项工具和 README 入口。
不修改机器人/执行器、依赖、PPO、其他技能或原 Velocity 的行为，不执行完整训练或远端发布。

## 依据与对应关系

基准为官方 `microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb`：
[`microduck_velocity_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)
与 [`mdp.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/mdp.py)。

| 官方位置 | 本地实现约定 | 适配与验收 |
|---|---|---|
| velocity:656–674，head 命令 | 4 维、每 2–5 s 重采样，`zero_command_prob=0` | 相对本机 HOME，顺序 neck_pitch/head_pitch/head_yaw/head_roll；全程采样有非零目标 |
| velocity:812–829，head 范围课程 | 0/500/1000/1500/2000 迭代，乘默认 rollout 24 为环境步 | 五组范围按官方数值；宽度校验防止 61 维槽位漂移 |
| mdp:5904–5932，范围课程机制 | 修改 live command term 的 cfg，下一次重采样生效 | 首阶段为默认、最后到达阶段覆盖；只改范围，不提前覆盖其他环境的当前命令 |
| velocity:679–689，body 命令 | 位移各 ±0.005 m、姿态各 ±0.05 rad，6 维、每 2–5 s 重采样 | 不使用站立门控，零指令概率为官方默认 0 |
| velocity:715–727，body tracking=0 | 不装配此奖励，与官方零权重数值等价 | 本地没有该 6D 函数，不为永远不执行的项新增实现 |
| velocity:199–215、275–289，腿部 pose | 直接复用 mjlab `variable_posture`，仅选择十个腿关节，权重 1 | knee 名称映射为本机 calf；取代新任务的全 14 关节 `stand_still`，避免与头目标冲突 |
| velocity:710–714、892–907，head 奖励 | 沿用当前 tracking（权重 2、std=.5）和 1 s EMA 偏差及延后权重课程 | 奖励始终读当前 head 命令，匹配非零目标时不被 HOME 代价反向拉扯 |

头部五阶段范围（单位 rad）：

| 迭代 | neck_pitch / head_pitch | head_yaw | head_roll |
|---|---|---|---|
| 0 | ±0.05 | ±0.07 | ±0.015 |
| 500 | ±0.17 | ±0.21 | ±0.047 |
| 1000 | ±0.39 | ±0.49 | ±0.11 |
| 1500 | ±0.72 | ±0.91 | ±0.20 |
| 2000 | ±1.10 | ±1.40 | ±0.31 |

这些范围是官方参考值，本机关节 HOME 与限位可容纳；仍属于仿真训练配置，不代表实机标定或
联合行走已收敛。最小验证是逐阶段采样范围、目标可达性、真实动作映射和短训练数值检查。

## 模块与接口

- `tasks/flat_velocity_head_env_cfg.py`：复用原 Velocity 工厂得到独立配置，再替换 head/body 命令、
  相应观测槽、腿部 pose、头部范围课程及动作缩放。训练和 play 都保留课程。
- `tasks/curriculum.py`：新增 `pose_command_range_curriculum`，只负责姿态命令范围更新；
  不改变已有 event curriculum。
- `tasks/__init__.py`：注册新任务的 train/play/rl 配置，并纳入已有导入期契约守卫。
- 新任务的 `VelocityHeadOnPolicyRunner` 只在上游 load 完成后调用环境 reset，立即按恢复的
  计数器刷新命令课程；不改变 PPO 或检查点格式。mjlab 原生 play 在 load 前已初始化环境，
  查看器启动时不会再次 reset，因此需要此任务级装配，避免先用初始小范围直到首个回合结束。
- `tools/check_velocity_head_env.py`：通过真实环境检查范围阶段、命令槽、动作映射、局部 reset，
  支持读取短训 checkpoint 并验证 `MjlabOnPolicyRunner.load → reset → 课程恢复`。

保持 actor 61 / critic 64 / action 14，float32、设备、关节与命令顺序沿用 `contract.py`。
头、躯干命令分别填入原有 4/6 维槽；actor 不增加真实线速度或足端特权信息。
原始动作无量纲，目标为 HOME 加缩放后的动作，再由 mjlab 扣除编码器偏置：
腿部沿用本机 `.25 rad/action`，四头颈关节采用官方 `1.0 rad/action`，嘴保持 HOME。
这是对官方所有关节 scale=1 的局部适配，避免改变当前腿部探索幅度；新任务的逐关节字典缩放
必须随检查点/后续导出元数据一起使用，不能把旧任务的统一 `.25` 映射直接用于新策略。

`VelocityHeadRlCfg` 独立复制原 PPO 配置，experiment_name=`flat_velocity_head`、run_name=`velocity_head`；
架构/优化器参数与 24 步 rollout 不变。检查点形状可相同，但命令分布和动作映射不同，默认从零训练。
恢复时使用对应任务及完整的 env/agent 配置。mjlab 1.6 的 runner 会恢复 `common_step_counter`，
新任务的注册 runner 在 load 后立即 reset，按检查点训练阶段采样，不默认强制最终头部范围，
以免早期策略接收超范围指令。

## 实施与验收

主代理负责配置、注册、GPU 工具、入口说明及记录；`head_command_curriculum` 只修改课程及其
专项测试；`velocity_head_review` 只读核对官方基准、最终文件和验证证据，承担独立审查。
与远端部署相关的依赖/锁文件及其他已有改动保留，本轮不覆盖或同步它们。

验收依次为课程/采样/奖励隔离/旧任务不变的正式测试，GPU 4 环境、种子 0 的有限步验证，
正式入口 GPU 16 环境、种子 0、5 次迭代、300 s 上限，检查点与课程恢复，
`make docs`、`make check` 及[独立审查](../review/velocity_head_task.md)。
专项与短训证据保留在 `logs/velocity_head_20261029/`；临时文件仅用项目内
`.artifacts/t052-velocity-head/`，交付前清理。短跑不代表行走与头部跟踪效果已经验收。

实际结果：15 个新增专项测试通过；GPU 验证了五阶段范围、命令槽、十四关节映射和四头颈实际运动。
正式短训为 16 环境、种子 0、5 迭代，正常退出；检查点及立即恢复课程的路径通过。
完整命令、数值与限制见[开发完成记录](../development.md#2026-年-10-月-29-日-头颈联动平地速度任务)，
问题关闭与独立结论见[审查记录](../review/velocity_head_task.md)。
