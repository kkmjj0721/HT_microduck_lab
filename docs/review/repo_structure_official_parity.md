# 审查记录：包目录与官方对齐、收敛到唯一训练算法（T047）

## 审查范围与证据

- 任务与设计：[T047](../archive/development_tasks.md#t047-包目录与官方完全对齐并收敛到唯一训练算法)，
  设计 [repo_structure_official_parity.md](../design/repo_structure_official_parity.md)。
  前置设计 [repo_layout_alignment.md](../design/repo_layout_alignment.md)（T046）。
- 实现者与独立审查者：实现由主代理完成；独立审查由只读子代理执行，作者未自审。
- 文件范围与基准：`main` 分支工作区未提交改动，含未跟踪文件。审查覆盖
  `src/ht_microduck/{robot,actuator,tasks}/`、删除的 `algorithms/`、`cli/`、`rsl_rl/`
  全部 30 个 `.py`、`tests/`（含 3 个新文件）、`tools/` 导入点，以及
  `README.md`、`AGENTS.md`、`docs/development.md`、`docs/setup.md`、`pyproject.toml`、
  两份设计文档。基准为官方 tarball `pollen-robotics/microduck_rl@1e79c29`。
- 验证证据：审查者逐项执行 `uv lock --check --offline`、`ruff check src tools tests`、
  隔离 basetemp 的全量 pytest、`tools/check_robot.py`、`git diff [--cached] --check`
  （因只读约束未直接运行 `make check`；实现者另行运行，结果见下）。
  审查者额外用 `uv build --wheel` 验证打包后 XML 与 16 个 STL 仍在 wheel 内、`entry_points.txt`
  含 `duck-train`/`duck-play` 与 `[mjlab.tasks] ht_microduck`；用 `python -P` 模拟
  console script 验证路径顺序保证；用移除 `runners/` 的副本验证"残缺即失败、不回落 wheel"。
- 未执行项：GPU/多环境训练（本机 `CUDA unknown error`）、`viser`/`native` 画面与录屏、
  `duck-play` 真加载 checkpoint 的端到端（审查者只跑 `--help`；实现者用探针完成）、
  上游数值语义的独立复算。

## 问题与修复复核

| 编号与程度 | 文件位置 | 触发、影响、依据及建议 | 修复与验证 | 复核者及状态 |
|---|---|---|---|---|
| 1 阻塞性（文档） | `README.md:95-96` | 快速开始命令带 `--device cpu`，但 `TrainConfig` 无该字段（只有 `PlayConfig` 有）。实测退出码 2、`Unrecognized options: --device, cpu`。用户会第一个撞到 | 删除 `--device cpu`，改为 `--gpu-ids None` 并加一行说明"训练入口没有 `--device`"。实测 16 环境/5 迭代/退出码 0 | 实现者修复，已重跑验证 |
| 2 一般 | `src/ht_microduck/actuator/HD_1910_C001/README.md:8` | 改名后链接仍指 `../../robots/ht_microduck/ht_microduck_constants.py`，已不存在；`README.md:185` 直接链到该文件，读者会点到 404 | 改为 `../../robot/ht_microduck_constants.py`；全仓相对链接扫描全部可解析 | 实现者修复，已核对 |
| 3 一般 | `rsl_rl/README.md` 全文 | 仍在描述 `_fallback.py` 机制（`:62-78`）、称本目录"只读参考、不含训练框架代码"（`:3-4`）、建议"不需要时直接删除整个 `rsl_rl/`"（`:108`）、规模写 27 文件/3900 行、测试写 `134 passed`。与 `pyproject.toml`、`AGENTS.md`、`README.md` 及实际行为（删 `runners/` 即 `ModuleNotFoundError`）全面矛盾 | 按当前职责重写：完整副本、训练实际路径、来源与规模（30 文件/4711 行/312 KB）、路径顺序保证及其边界、修改与升级约束、明确"不要删除"。行数逐文件核对；`docs/development.md` 中过期的 `VENDOR_NOTES.md` 说明一并作废 | 实现者重写，已核对数字 |
| 4 轻微 | `docs/design/repo_layout_alignment.md:93` | 称 `train_cli.py` 会在 `rsl_rl` 解析到 wheel 时打印警告，实际无任何 `print`/`warn`。审查者另测：即使任务包加载失败，仓库根仍在 `sys.path[0]`，`rsl_rl` 仍解析到仓库副本；真正回退只在"调用方先 `import rsl_rl` 且仓库根不在 `sys.path`" | 改为"不做运行时断言；保证由 `ht_microduck.__init__` 提供"并链到 T047 设计 | 实现者修复，已核对 |
| 5 一般（准确性） | `docs/development.md:3680` 附近、parity 设计对照表 | 原称被删 4 个测试文件的风险"已等价替代"，实际 52 条断言里 GAE 手算、终止 vs timeout bootstrap、clipped value loss、`log_prob`/entropy 闭式解、adaptive KL 上下界、mini-batch 覆盖、归一化收敛、种子可复现、维度不匹配加载失败、`metrics.jsonl` 追加等语义在新测试中无对应 | 两步处理：(a) 措辞降级——删掉"等价迁移"，明确"不再覆盖的部分"及其替代保证（逐字节 vendor drop）；(b) 补两条可手算且真正驱动 vendored `PPO` 的数值测试：GAE 递推与手算轨迹逐位一致（含终止步切断 bootstrap）、clipped surrogate 上界。刻意不重建整套本地 PPO 断言 | 实现者修复，新测试通过 |
| 6 轻微 | `docs/design/repo_structure_official_parity.md:150` | 验收行称 grep"无匹配"，实测有 2 处命中（新测试文档字符串说明历史） | 改为"仅 `tests/test_training_stack.py` 的文档字符串提及被删模块，无实际导入" | 实现者修复 |
| 7 轻微 | `docs/development.md:3241/3274/3589/3618`、`repo_layout_alignment.md:50` | 仍把 `_fallback.py` 写成现存机制；`:3618` 的"除 `_fallback.py` 外 17 文件相同"在 T047 后完全反转 | 给 T043、T027 小节与 T046 清理清单加"已被 T047 取代"标记并指向 T047；保留原文作为当时决策记录 | 实现者修复 |
| 8 轻微 | `src/ht_microduck/robot/ht_microduck_constants.py:211` | 注释路径仍是 `actuators/...` | 改为 `actuator/...` | 实现者修复 |
| 9 轻微 | `pyproject.toml:22-23` | 注释"PPO/网络/Storage/Runner 将写在 ht_microduck 里"与现状相反 | 改为"mjlab 带来 `rsl-rl-lib==5.4.2`；本仓库 `rsl_rl/` 是逐字节副本，训练实际运行该副本" | 实现者修复 |
| 10 轻微（测试强度） | `tests/test_rsl_rl_vendoring.py:97` 原 `test_vendored_copy_covers_every_wheel_module` | 文档字符串称"必须是已安装发行版的超集"，实际只断言 `find_spec` 非空（必为仓库内包）加 5 个硬编码文件名，`try/except ModuleNotFoundError: skip` 是死分支——名不副实 | 改为用 `importlib.metadata.distribution("rsl-rl-lib").locate_file("rsl_rl")` 定位 wheel，做模块名集合差 `wheel - vendored == ∅`；删掉 skip 分支 | 实现者修复，通过 |
| 11 轻微 | `tests/test_rsl_rl_vendoring.py` 边界测试文档字符串 | 把"先 `import rsl_rl` 仍得 wheel"说成无条件成立；实际仅在仓库根不在 `sys.path` 时成立（从仓库根运行时 cwd 在 `sys.path` 上，同序也可） | 补限定："while the repository root is off `sys.path`, as in a console script or with `-P`"，并说明从仓库根运行时恰好可用、测试固定严格场景 | 实现者修复 |
| 12 轻微（可移植性） | `tests/test_training_stack.py` 日志布局测试 | 断言 `git/*.diff` 存在，但 vendored `rsl_rl/utils/logger.py` 里 `repo.git.status()` 在 `try` 之外；导出 tarball 或无 `git` 可执行文件时会抛异常而非跳过 | 加前置条件：`(REPO_ROOT/".git").exists() and shutil.which("git")` 才断言，否则 `pytest.skip` 并说明原因；`git/` 断言保留 | 实现者修复 |
| 13 nit | `tests/test_robot_layout.py:32` | `REMOVED_SUBPACKAGES` 含 `"rl"`，但设计文档从未提过（那是 T046 删的空目录） | 加注释说明来源："T046 删掉的空遗留目录，列在此处以捕获误重建" | 实现者修复 |
| 14 nit | `docs/design/repo_structure_official_parity.md:145` | 验收行 `find -maxdepth 2` 会输出 `robot/ht_microduck`、`actuator/HD_1910_C001`、`actuator/HTDW_3532_02_DNE`，照抄会误判失败 | 改为 `-maxdepth 1` | 实现者修复 |
| 15 nit | 全局 | `make check` 里没有真 MuJoCo 训练断言（用 `_FakeVecEnv` 替身） | 接受：测试文档字符串已声明，真环境由 `tools/check_velocity_env.py` 与短跑覆盖；不在 `make check` 里启动 MuJoCo 训练是有意的 | 接受，不修 |
| 16 nit | `pyproject.toml` 未直接声明 `GitPython` | vendored `rsl_rl/utils/logger.py:10` `import git` 是生产路径，但只经 `rsl-rl-lib==5.4.2` 间接提供 | **评估后不修**：`rsl-rl-lib` 的 `requires` 已含 `GitPython`（实测 `['GitPython']`），显式声明会强制 `uv.lock` 全量重新解析。实测清华镜像对 mjlab 返回 403、离线无法解析；用 pypi.org 解析则改写 723 条无关 URL 并改动 warp 索引主机。故只加注释记录该决定与理由，锁文件保持不变 | 实现者评估，已在 `pyproject.toml` 注明 |

## 最终结论

- 审查状态：**独立审查通过**。审查者原始结论为"机制正确、可合并，未发现 blocker"，
  16 条问题中 15 条已修复并复核，1 条（第 16 条）经评估后以注释说明理由不修。
- 问题关闭情况及最终集成验证（修复后由实现者重跑）：

| 验证项 | 命令 | 结果 |
|---|---|---|
| 基础检查 | `make check` | 通过：锁文件、ruff、pytest、模型检查、空白检查全绿 |
| 测试数量 | 隔离 basetemp 全量 pytest | 180 passed，8 subtests passed（较审查时的 177 增加 3 条：GAE 手算、终止步切断 bootstrap、vendored 超集比对替换后净增） |
| 模型不变 | `make model` | `robot/ht_microduck/HT-DK_URDF.xml`，15 关节、16 网格、`nq=22 nv=21 nu=0`、3.2947 kg |
| 训练短跑 | `duck-train HtDuck-Flat-Velocity --env.scene.num-envs 2 --agent.max-iterations 2 --agent.save-interval 1 --agent.seed 7 --gpu-ids None` | 退出码 0，产出 `params/{env,agent}.yaml`、`git/HT_microduck_lab.diff`、`model_{0,1}.pt`、`events.out.tfevents.*` |
| README 命令 | 修正后的 16 环境/5 迭代命令 | 退出码 0 |
| 回放 | `RslRlVecEnvWrapper` + `MjlabOnPolicyRunner.load(load_cfg={"actor": True})` | `PLAY PROBE OK (2, 10) torch.float32`，actor 39 / critic 42 / action 10 |
| 环境专项 | `tools/check_velocity_env.py --device cpu` | 通过：39D/42D/10D、11 个奖励项、命令范围、零动作 0/16 终止、跌倒检测 16/16 |
| 本地 rsl_rl | 打印 `rsl_rl.__file__`、`__path__`、`OnPolicyRunner`、`Logger`、`PPO`、`MLPModel` | 全部在仓库内，`__path__` 单元素 |
| 与 wheel 一致 | `diff -rq rsl_rl .venv/.../rsl_rl` | 仅仓库侧多 `LICENSE`、`README.md` |

- 限制与后续：GPU/多环境训练、`viser` 画面、`duck-eval`/`duck-export`（T027/T028）未做，
  与 T046 同口径记录。`GitPython` 未显式声明（第 16 条）属已知取舍，若后续迁移到可用的
  镜像或需要脱离 `rsl-rl-lib` 的传递依赖，应单独立项处理锁文件。上游数值语义未独立复算，
  由逐字节 vendor drop 与超集测试保证。

审查通过不授予 Git 提交或发布权限，任务状态只在开发文档统一维护。
