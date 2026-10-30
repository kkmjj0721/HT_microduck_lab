# 功能设计：按职责整理任务目录

关联 [T052](../development.md)。用户要求参考本机
`/home/sunteng/projects/legged_wbc_mjlab/src/tasks`，全部 MDP 只建一个目录，并保持训练一致。

## 目标与依据

目前 `tasks/` 根目录混有五个环境配置、PPO 配置、Head runner、命令、奖励、重置和课程。
参考项目 `4eb8fcf71124b20ed4a1154b6c724ba962a424f8` 的
`locomotion/go2_ppo/config/{env_cfgs,rl_cfg}.py`、`mdp/` 和 `rl/runner.py`
分别组织配置、环境行为与 runner；本项目只有一个机器人和共享契约，直接采用这一层职责，
不引入任务族/机器人层级，也不复制各任务的 MDP。

本地依据为迁移前源码快照 `logs/task_layout_20261029/before/source/tasks/` 与上述参考源码。
参考只影响布局；机器人、执行器、mjlab 1.6.0、本地 rsl-rl-lib 5.4.2、算法与配方不变。

## 模块、接口与兼容性

| 位置 | 职责与迁移来源 |
|---|---|
| `tasks/__init__.py`、`contract.py` | 保留注册、五个任务 ID、导入期契约守卫和契约常量 |
| `tasks/config/flat_*_env_cfg.py` | 原五个环境工厂及常量，去除 PPO 配置和 runner |
| `tasks/config/rl_cfg.py` | 原五份 RL 配置原样集中；保留 Head 的 deepcopy 和 VelStand 课程单位断言 |
| `tasks/config/terrain.py` | 原地形配置，不改变对象共享关系 |
| `tasks/mdp/{commands,curriculums,events,observations,rewards,posture}.py` | 原 commands、curriculum、posture_events、shared、mdp、posture_mdp；仅改路径与导入 |
| `tasks/rl/runner.py` | 原 Head runner，继续仅在上游 load 后 reset |

五任务继续使用 61/64 维 actor/critic、14 维动作与原关节顺序、float32、原设备、50 Hz。
动作缩放、观测噪声、归一化、奖励顺序/权重、reset 历史、终止/timeout、课程和 PPO 参数全部不变。
训练/回放 CLI、任务 ID、日志目录、检查点键和张量形状不变。
Python 内部导入路径更新，所有源码/测试/工具同步；旧路径不另设重复模块或兼容壳。
上游检查点保存 state_dict 与计数器而非本地 Python 对象；已实际核对五任务旧权重加载。
旧 params YAML 中的函数路径是当时的配置记录，不回写历史实验；新配置记录采用新路径。
尚未实现的评估/导出沿用契约，当前没有可迁移的正式入口。

## 实施与协作

主代理是全部实现、文档和测试的唯一修改者；`task_layout_research` 子代理只读核对目录与依赖，
独立审查者在迁移后只读核对最终文件、迁移前快照及验证证据。所有子工作属于 T052。
先保存迁移前配置与正式训练证据，再机械移动/拆出配置和 runner，更新引用并比较，最后独立审查。
临时脚本与缓存只放项目 `.artifacts/task_layout_20261029/`，交付证据放 `logs/task_layout_20261029/`。

## 验收

| 验证 | 通过条件 |
|---|---|
| 五任务训练/回放配置快照 | 包括类型、字典顺序、函数名和全部配置值；仅规范化已声明的模块移动路径，前后完全一致 |
| 五任务真实训练 | 每任务前后各一次，cuda:0、种子 0、16 环境、24 步 rollout、2 迭代、单次 timeout 300s；保存日志、params 和 model_1.pt |
| 检查点比较 | 逐项比较模型、归一化、优化器和环境计数；差异必须查明，不用短跑成功替代等价判断 |
| 旧检查点恢复 | 迁移后的注册 runner 加载迁移前检查点；Head 课程立即恢复，继续推理结果有限 |
| 基础检查与审查 | `make docs`、`make check`、独立审查问题关闭 |

## 实测结果

证据根目录为 `logs/task_layout_20261029/`，保留迁移前/后源码、配置、训练日志和检查点，
用于核对本次行为等价。实际迁移前任务代码有大量未提交修改，比较以该源码快照为基准，
不以 Git HEAD 的旧任务配方为基准。

- `before/configs.json` 与 `after/configs.json` 字节相同；快照覆盖五任务 train/play/RL/runner、
  类型、全部属性、字典顺序、函数模块/qualname、默认参数和补零闭包维度，只规范化明确迁移的模块路径。
- `source_comparison.json`：13 个原模块的全部可执行定义/常量相同，拆出的 RL 赋值与 runner 类 AST 相同；
  仅规范化函数内 import 的移动路径，注册关系另由完整配置快照检查。
- 五任务前后各一次 GPU 正式短跑，再追加当前代码同配置重复短跑作为确定性对照，共 15 次，均退出 0。
  配置为 cuda:0、seed 0、16 环境、24 步 rollout、2 迭代，每次 768 个环境转换、上限 300s。
  命令、退出码在 `{before,after,after_repeat}/runs.json`，日志、params 和 `model_{0,1}.pt` 位于同阶段目录。
- `comparison.json`：GPU 前后权重存在差异，同版重复也有差异，不能声称 GPU 位级复现。
  本机 mjlab 1.6.0 的 `utils/random.py:9–14` 已说明 MuJoCo Warp 尚非完全确定性。
  为分离环境采样与算法变化，追加固定观测/奖励数据的 CPU 对照：独立 generator seed 713，
  torch seed 0、1 线程、确定性算法，每任务仍为 16 环境、2 次实际 Runner/PPO 更新。
  迁移前通过 import finder 仅载入源码快照的 tasks，机器人/执行器与仓库 `rsl_rl/` 来源相同。
  五任务各 76 个模型/归一化/优化器张量全部 `torch.equal`，48 步采样动作全部逐位相同，
  迭代号与环境计数相同；检查点与动作证据在 `{before,after}/fixed_batch/`。
- `restore.json`、`restore.log`：迁移后的注册 runner 全量加载五任务迁移前权重，恢复 optimizer、
  iter=1、common_step_counter=48；每任务 GPU 4 环境、10 步推理，动作/观测/奖励均有限。
  Head 另验证 0/500/1000/1500/2000 迭代元数据加载后立即选中相应课程；后期元数据仅用于验证，
  不代表策略已经训练到这些阶段，临时权重交付前删除。
- 新增 16 项 registry 测试保护五任务 train/play 契约、补零函数、独立 RL 配置、迭代上限、runner 选择与课程单位守卫。
  `make docs`、`make check` 通过（292 passed、8 subtests）；独立审查见[审查记录](../review/task_layout.md)。

验收结论为目录/配置/训练实现等价、固定数据 PPO 数值等价和旧权重兼容；
不承诺 GPU 逐位复现，也不把短跑作为完整训练收敛或实机效果的证据。
