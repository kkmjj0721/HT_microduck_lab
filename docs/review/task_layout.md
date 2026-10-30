# 审查记录：任务目录整理与训练等价

## 审查范围与证据

- 关联 [T052](../development.md) 与[设计](../design/task_layout.md)。主代理实施；
  `task_layout_review` 独立只读审查，`task_layout_research` 负责前期只读调研。
- 审查基准为 `logs/task_layout_20261029/before/source/tasks/` 的工作区快照，
  包含开始时已有未提交修改与新增文件；最终覆盖 `tasks/**`、3 个检查工具、8 个相关测试文件、
  README、开发任务和设计说明，核对 Git 状态及未跟踪清单，不只依赖 Git diff。
- 参考本机 `legged_wbc_mjlab@4eb8fcf71124b20ed4a1154b6c724ba962a424f8` 的 config/mdp/rl 分层。
  审查者独立比较：六个 MDP 模块、terrain、contract 内容相同；五环境函数/常量、五份 RL 赋值、
  runner 类在声明的路径归一化后 AST 相同；registry 仅改 import/docstring。
- `before/configs.json` 与 `after/configs.json` 完全一致，旧 import 搜索无残留。
  mjlab 1.6.0 的 `rl/runner.py:67–143` 保存/加载 state_dict 与计数器，
  `scripts/train.py` 和 `scripts/play.py` 从 registry 重建配置，目录移动不更改权重格式。
- 审查者独立运行 8 个相关测试文件，71 passed（4.05s），使用 `uv run --no-sync python -B -m pytest`、
  项目内 `.artifacts/task_layout_review/` TMPDIR/basetemp/缓存；未占用 GPU。
- 审查者复核 `comparison.json`、源码比较与旧检查点证据：五任务固定数据各 76 个张量和
  48 步动作逐位一致，GPU 前后短训及同版对照均通过但不逐位一致；五任务全量旧权重加载/推理通过，
  Head 五课程阶段立即恢复通过。主代理 `make check` 为 292 passed、8 subtests，模型/文档/锁文件/Ruff 通过。

## 问题与修复复核

| 编号与程度 | 文件位置 | 触发、影响、依据及建议 | 修复与验证 | 复核者及状态 |
|---|---|---|---|---|
| R1 建议 | `src/ht_microduck/tasks/rl/runner.py` | runner 从含 future annotations 的模块拆出后，注解由延迟字符串变为立即求值；不影响已知训练，但建议保留原 introspection 语义 | 补回 `from __future__ import annotations` | `task_layout_review` 已复核关闭 |

## 最终结论

- **独立审查通过**，无阻塞或一般问题，R1 建议已处理。
- 目录迁移保持五任务配置、训练逻辑与共享对象语义，固定数据下模型、优化器与动作逐位一致，旧权重兼容。
- GPU 实际采样不保证位级确定性，同版重复对照确认存在差异，结论未将短训成功等同策略收敛。
- 审查进程已结束；审查后只补充结果文档、归档任务条目和清理临时产物，最终文档/检查由主代理复核。
  本轮无未解决事项，不授予 Git 提交或发布权限。
