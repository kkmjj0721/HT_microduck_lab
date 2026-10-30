# 功能设计：包目录与官方 microduck_rl 完全对齐，rsl_rl 作为唯一训练算法来源

后续 T052 按用户指定的本机参考项目调整 `tasks/` 内部布局，见[任务目录整理](task_layout.md)。
本文保留 T047 当时的迁移依据与目标；顶层三个子包和唯一 `rsl_rl/` 算法来源保持不变。

关联任务：[T047](../development.md)。本文件记录接口、迁移映射与验收方式，任务状态在开发文档
统一维护。前置设计 [repo_layout_alignment.md](repo_layout_alignment.md)（T046）已把
`tasks/` 拍平、接入 `mjlab.tasks` entry point、并把 `duck-train`/`duck-play` 改成官方入口的
薄封装；本轮解决它遗留的两件事。

## 目标与范围

用户要求"文件架构像参考项目一样"，并明确"训练的 RL 算法使用本仓库根目录的 `rsl_rl/`"。
T046 只对齐了 `tasks/`，其余两处仍是官方结构之外的东西：

1. **包名与模型目录不对齐。** 官方是 `src/mjlab_microduck/{robot,actuator,tasks}/`，
   模型文件在 `robot/microduck/`（MJCF 与 `assets/` 同级）；本机是 `robots/ht_microduck/xmls/`，
   多一层 `xmls/`，且包名是复数。
2. **两套训练栈并存。** `src/ht_microduck/algorithms/`（6 文件，约 2.1k 行）与
   `src/ht_microduck/cli/`（3 文件，约 0.8k 行）是训练改用 RSL-RL 之前的自实现，
   入口已不经过它们，只剩 `tests/test_{ppo,networks,runner,logger_and_play}.py` 在用。
   官方没有本地 PPO/网络/Runner。
3. **`rsl_rl/` 不是完整实现。** 缺 `runners/`、`utils/logger.py`、`algorithms/distillation.py`，
   靠 `rsl_rl/_fallback.py` 把子包 `__path__` 扩展到 wheel。用户要求训练用这份代码，
   但实际跑起来的 `OnPolicyRunner` 与 `Logger`（训练循环与日志面板本身）来自 `.venv`。

### 本轮范围

- `robots/` → `robot/`、`actuators/` → `actuator/`，`robot/ht_microduck/xmls/` 拍平；
- 删除 `algorithms/` 与 `cli/`，删除只覆盖它们的 4 个测试文件；
- 把 `rsl_rl/` 补成 rsl-rl-lib 5.4.2 的完整副本，删除 `_fallback.py`；
- 新增覆盖**实际训练路径**的测试（本地 `rsl_rl` 解析、PPO/Runner/Logger 来源、
  短训练落盘布局）；
- 同步 README、`docs/development.md`、`AGENTS.md` 的模块归属与路径。

### 明确不做

- 不改 `mjlab` 版本、不改机器人 XML、执行器参数、任务奖励与观测契约；
- 不实现官方 `scripts/`（`export.py`、`infer_policy.py`、`publish`、HF Jobs），
  它们是 T028 的交付物；本机 `tools/` 是检查工具，不强行改名；
- 不提交 Git。

## 依据

| 判断 | 依据类型与位置 | 适用差异或缺口 | 最小验证与通过条件 |
|---|---|---|---|
| 官方包只有 `robot/`、`actuator/`、`tasks/` 三个子包 | 官方 tarball `pollen-robotics/microduck_rl@1e79c29`，`src/mjlab_microduck/` 目录列表（本轮解包于 `.artifacts/upstream_microduck_rl/`） | 官方没有 `algorithms/`、`cli/`、`robots/`、`actuators/` | 新树与官方逐目录对照一致 |
| 官方模型目录 `robot/microduck/` 无 `__init__.py` | 官方 `robot/microduck/` 文件列表：XML、json、`assets/`、`add_backlash.py` | 本机现有 `robots/ht_microduck/__init__.py` 做再导出，属包化而非数据目录 | `robot/ht_microduck/` 只放资源与常量，不再被 import |
| 官方 `robot/__init__.py` 为空，调用方直接 import 常量模块 | 官方 `robot/__init__.py` 为 0 字节；`tasks/microduck_velocity_env_cfg.py:120` `from mjlab_microduck.robot.microduck_constants import ...` | 本机测试/工具当前用 `from ht_microduck.robots import ...`，需改导入点 | grep 无 `ht_microduck.robots` |
| 官方 `train_cli.py` 只做转发 | 官方 `train_cli.py`（1.4 KB）→ `mjlab.scripts.train.main` | 本机多一个 `play_cli.py`，因为本地 `rsl_rl` 需要先修正 `sys.path`；官方用 wheel 不需要 | `duck-play` 冒烟通过 |
| `rsl_rl` 5.4.2 的完整文件集 | `.venv/.../rsl_rl` 与 `rsl_rl/` 逐文件 `diff -rq`：本地缺 `runners/{__init__,on_policy_runner,distillation_runner}.py`、`utils/logger.py`、`algorithms/distillation.py`；8 个 `__init__.py` 因 `_fallback` 而不同 | 补齐后本地副本与 wheel 内容一致（License 与 README 保留） | `diff -rq` 仅剩 `LICENSE`/`README.md`/`__pycache__` 差异 |
| 训练循环确实走本地副本 | 本机实测 `rsl_rl.__file__`、`OnPolicyRunner.__module__`、`Logger.__module__` | 补齐前 `rsl_rl.runners` 来自 wheel；补齐后应全部指向仓库 | 断言 `__file__` 前缀为仓库路径，且 `rsl_rl.__path__` 只有一项 |
| 迁移测试而不丢覆盖 | T046 记录"先让 tests 迁到 RSL-RL 等价断言，再删 `algorithms/`，最后删 `cli/`" | 旧测试断言的是被删实现；新测试要覆盖同一风险面（PPO 数值、网络形状、日志面板、checkpoint 恢复），但必须打在真正运行的代码上 | 新测试在 `make check` 通过并实际驱动 `rsl_rl.OnPolicyRunner` |

## 目标结构

```
src/ht_microduck/
  __init__.py                    # 保持：repo 根 rsl_rl 优先 + 先 import mjlab
  train_cli.py                   # duck-train  → mjlab.scripts.train
  play_cli.py                    # duck-play   → mjlab.scripts.play
  robot/
    __init__.py                  # 空（官方风格）
    ht_microduck_constants.py    # 原 robots/ht_microduck/ht_microduck_constants.py
    ht_microduck/                # 数据目录，不含 __init__.py
      HT-DK_URDF.xml
      assets/*.STL
  actuator/
    __init__.py                  # 原 actuators/__init__.py
    HD_1910_C001/
    HTDW_3532_02_DNE/
  tasks/
    __init__.py                  # 注册表（T046 已建）
    contract.py
    mdp.py
    flat_velocity_env_cfg.py
rsl_rl/                          # 完整 rsl-rl-lib 5.4.2 副本，训练实际代码路径
tools/ tests/ docs/              # 保持
```

对照官方：官方 `src/mjlab_microduck/{robot,actuator,tasks}` ↔ 本机
`src/ht_microduck/{robot,actuator,tasks}`；官方 `robot/microduck/` ↔ 本机
`robot/ht_microduck/`；官方 `tasks/microduck_*_env_cfg.py` ↔ 本机
`tasks/flat_velocity_env_cfg.py`。

## 迁移映射

| 旧路径 | 新路径 | 方式 |
|---|---|---|
| `src/ht_microduck/robots/__init__.py` | `src/ht_microduck/robot/__init__.py` | `git mv`，内容清空 |
| `src/ht_microduck/robots/ht_microduck/__init__.py` | — | 删除（数据目录不包化） |
| `src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py` | `src/ht_microduck/robot/ht_microduck_constants.py` | `git mv`，改 `_ROBOT_DIR` |
| `src/ht_microduck/robots/ht_microduck/xmls/HT-DK_URDF.xml` | `src/ht_microduck/robot/ht_microduck/HT-DK_URDF.xml` | `git mv`（`meshdir="assets/"` 不变） |
| `src/ht_microduck/robots/ht_microduck/xmls/assets/*.STL` | `src/ht_microduck/robot/ht_microduck/assets/*.STL` | `git mv` |
| `src/ht_microduck/actuators/` | `src/ht_microduck/actuator/` | `git mv` 整目录 |
| `src/ht_microduck/algorithms/`（6 文件） | — | 删除 |
| `src/ht_microduck/cli/`（3 文件） | — | 删除 |
| `tests/test_{ppo,networks,runner,logger_and_play}.py` | — | 删除，由新测试替代 |
| `rsl_rl/_fallback.py` | — | 删除，子包 `__init__.py` 恢复上游原文 |
| wheel 的 `runners/`、`utils/logger.py`、`algorithms/distillation.py` | `rsl_rl/` 同名路径 | 逐字节复制 |

导入点改写（`src/`、`tests/`、`tools/`）：

- `ht_microduck.robots.ht_microduck.ht_microduck_constants` → `ht_microduck.robot.ht_microduck_constants`
- `ht_microduck.robots` → `ht_microduck.robot.ht_microduck_constants`
- `ht_microduck.actuators` → `ht_microduck.actuator`

## 接口与兼容性

- **常量模块路径变化**是刻意的破坏性变更：`MJCF_PATH`、`JOINT_NAMES`、
  `get_ht_microduck_robot_cfg()` 等符号名与取值全部不变，只改导入路径。
- `MJCF_PATH` 由 `<pkg>/robot/ht_microduck/xmls/HT-DK_URDF.xml` 变为
  `<pkg>/robot/ht_microduck/HT-DK_URDF.xml`；XML 内 `meshdir="assets/"` 与
  `assets/` 的相对关系保持不变，模型编译结果必须逐项相同（关节数、质量、网格数）。
- `rsl_rl` 变为完整副本后，`rsl_rl.runners`/`rsl_rl.utils.logger` 不再回落 wheel；
  `rsl_rl.__path__` 只含仓库内目录。checkpoint 格式不变（仍是 5.4.2）。
- 训练/回放命令行、日志布局、任务 id 不变。
- 删除 `algorithms/`、`cli/` 后，`import ht_microduck.algorithms` / `ht_microduck.cli` 会
  `ImportError`；这是有意的，避免再次出现两套算法。

## 新测试（替代被删的 4 个文件）

| 文件 | 覆盖 | 断言要点 |
|---|---|---|
| `tests/test_rsl_rl_vendoring.py` | 本地副本完整性 | `rsl_rl.__path__` 只有仓库一项；`OnPolicyRunner`/`Logger`/`PPO`/`MLPModel` 的 `__file__` 在仓库内；未解析到 site-packages |
| `tests/test_training_stack.py` | 训练入口真正可用 | 用 stand-in `VecEnv` 驱动 `rsl_rl` 的 `OnPolicyRunner`：1 次迭代、loss 有限、`model_0.pt` 可写可回读；`RslRlOnPolicyRunnerCfg` 字段与契约维度一致 |
| `tests/test_robot_layout.py` | 新目录结构 | `MJCF_PATH` 存在且模型可编译、关节顺序不变、`assets/` 与 XML 同级、无 `robots/`/`actuators/` 残留 |

## 实施与协作

主代理实施机械迁移与测试；独立子代理做只读审查（文件归属不重叠）。

| 步骤 | 允许修改的文件 | 依赖 | 验证 |
|---|---|---|---|
| 1. 设计 | 本文件 | 无 | — |
| 2. 包改名与拍平 | `src/ht_microduck/{robot,actuator}/**`、删除 `algorithms/`、`cli/` | 步骤 1 | `make model` |
| 3. 补齐 rsl_rl | `rsl_rl/**` | 步骤 1 | `diff -rq` 与 wheel 对齐 |
| 4. 导入点与测试 | `src/`、`tests/`、`tools/` | 步骤 2、3 | `make check` |
| 5. 运行验证 | 无源码改动 | 步骤 4 | 训练短跑 + 回放探针 |
| 6. 文档 | `README.md`、`docs/development.md`、`AGENTS.md`、`docs/design/repo_layout_alignment.md` | 步骤 4、5 | 链接与示例核对 |
| 7. 独立审查 | `docs/review/repo_structure_official_parity.md` | 步骤 4–6 | 审查问题关闭 |

## 验收

| 验证项 | 命令/前置 | 通过标准 |
|---|---|---|
| 基础检查 | `make check` | 全部通过 |
| 结构对照 | `find src/ht_microduck -maxdepth 1 -type d` | 只有 `robot/ actuator/ tasks/`，与官方三子包一致 |
| 模型不变 | `make model` | 15 关节、16 网格、3.2947 kg，与迁移前一致 |
| 本地 rsl_rl | 打印 `rsl_rl.__file__`、`OnPolicyRunner`、`Logger`、`PPO`、`MLPModel` | 全部在仓库内，`rsl_rl.__path__` 单元素 |
| 训练短跑 | `duck-train HtDuck-Flat-Velocity --env.scene.num-envs 2 --agent.max-iterations 2 --agent.save-interval 1 --gpu-ids None` | 退出码 0，产出 `params/{env,agent}.yaml`、`model_*.pt`，面板为 RSL-RL 字段 |
| 回放 | `duck-play` 加载该 checkpoint 的探针 | 动作形状 `(2,10)`，actor 39 / critic 42 |
| 无残留 | `grep -rn "ht_microduck\.\(robots\|actuators\|algorithms\|cli\)" src tests tools` | 仅 `tests/test_training_stack.py` 的文档字符串提及被删模块（说明历史），无实际导入 |

未执行项（GPU 多环境、viser 画面）按 T046 同样口径如实记录。
