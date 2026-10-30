# 审查记录：头颈联动平地速度任务

关联[任务与范围](../development.md)和[设计](../design/velocity_head_task.md)。
实现者为主代理与 `head_command_curriculum`，独立审查者为只读代理 `velocity_head_review`。

## 审查范围与证据

新环境与注册、姿态命令课程、正式测试、GPU 专项工具、README 入口和本轮设计/开发记录。
远端部署、依赖声明与锁文件等共享工作区已有改动不属于本轮修改范围。
基准为官方 `microduck_rl@bae39f59` 的 head/body 命令、head 范围课程及腿部姿态奖励。
新任务沿用本机腿部 `.25` 缩放，头部采用官方 `1.0`，该适配及导出/恢复边界已明确记录。

证据：15 个新增专项测试；`make check` 276 passed + 8 subtests；4 环境 GPU 指令/动作/实际运动
检查；正式入口 16 环境、5 迭代退出 0；真实 checkpoint 的 10 步推理及四个验证元数据阶段恢复。
日志与源码快照位于 `logs/velocity_head_20261029/`，详细命令见[开发记录](../development.md#2026-年-10-月-29-日-头颈联动平地速度任务)。

## 问题与修复复核

| 编号与程度 | 文件与触发 | 修复与验证 | 独立复核 |
|---|---|---|---|
| R1 一般 | 新工厂 deepcopy 后再调用共享 actor_terms/critic_terms，重新引入 POLICY_JOINTS；改新任务的 actor/critic joint_pos/joint_vel selector 会污染原任务 | 改为仅替换 deepcopy 后的 body_command 槽；既有测试补齐四个 selector 的对象及修改隔离 | 审查者 CPU 复现原问题，修复后独立复跑 15 个专项测试，确认关闭 |

额外集成核对：原生 mjlab play 在加载前已初始化环境，查看器启动不自动再 reset。
新任务注册 `VelocityHeadOnPolicyRunner`，只在 super.load 后 reset 刷新课程、命令和奖励历史，
保持 common_step_counter、PPO/优化器/迭代恢复与格式；旧任务仍用原 runner。
GPU 恢复专项在 load 后直接检查范围，没有用外部 reset 掩盖该集成路径。

## 最终结论

**独立审查通过。** 审查者 `velocity_head_review` 已核阅最终 GPU、正式短训、检查点有限值与
恢复日志，独立复跑 15 个专项测试，并核对 29 份留存源码/配置 SHA-256 与当前文件一致。
R1 已修复并复核关闭，无剩余阻塞或一般问题；审查者未修改文件或重复启动 GPU/训练。
完整训练与固定指令联合效果评估不在本轮短跑验收范围内；验证用后期元数据不代表训练到对应阶段。
