# 完成记录归档

本文件按时间顺序（最早在前）保存历史完成记录，包含当时执行的命令、关键结果、审查结论和遗留项。
搬移时保持原有顺序与措辞，不按新结论重排。
当前任务状态见 [开发流程与任务](../development.md)，最近的记录也保留在 `development.md` 末尾。

历史记录反映**当时**的事实与判断；后续任务已推翻的结论在被引用处注明「已被 Txxx 取代」，
不直接改写原文。

### 2026 年 10 月 22 日 T000

建立 `AGENTS.md`、本开发流程和 `Makefile` 检查入口，README 增加开发入口。
`make check` 通过：锁文件一致，Ruff 无问题，10 个测试及 8 个子测试通过，
MJCF 编译与 15 个关节的电机映射检查通过，模型 `nq=22`、`nv=21`、`nu=0`。
测试入口隔离了系统 ROS pytest 插件；这次验收覆盖基础开发检查，未运行 GPU 训练。
现有源码和文档重组的未提交改动保留，交由 T001 整理。

### 2026 年 10 月 23 日 模块命名与模型入口修复

发行包名统一为 `ht-microduck`，Python 包使用 `ht_microduck`。
`ht_microduck_constants.py` 集中定义模型路径、15 个关节的电机分组与 `get_spec()`，
模型检查脚本改为从该模块导入。XML 的网格路径修正为 `assets/`，加载函数使用包内绝对路径；
README 和安装文档同步更新。使用 `uv lock --python 3.12` 更新锁文件，
除项目名及对应的生成标识外，221 个依赖包的记录和版本均保留。

通过 `python3 tools/setup_env.py` 创建当前目录的开发环境，自动匹配 CUDA Toolkit 13.0 和 `cu130`。
`make check` 通过：锁文件一致，Ruff 无问题，10 个测试及 8 个子测试通过，
模型编译和关节映射通过，`nq=22`、`nv=21`、`nu=0`、16 个网格，总质量约 3.2893 kg。
`uv build --offline --out-dir /tmp/ht-microduck-review-a4bjyhep/dist` 成功构建源码包和 wheel，
两种产物均包含 XML 和全部 16 个 STL；从 `/tmp` 导入解包后的 wheel，
`get_spec().compile()` 和直接加载 XML 均通过，确认资源查找不依赖仓库工作目录。
README 与安装文档的本地链接检查通过。
本次未运行 GPU 仿真或训练，mjlab 实体与执行器接入仍待实现，T001、T002 状态不变。

### 2026 年 10 月 23 日 T003

`AGENTS.md` 增加多代理并发调研、实现与复核规则，明确同一任务内拆分、文件归属及主代理集成责任。
测试、验证脚本、辅助数据和构建解包产物限定在本项目内，禁止写入 `/tmp/` 等外部目录；
正式测试放在 `tests/`，临时验证产物放在项目内 `.artifacts/`。
交付前须等待全部子代理与检查进程结束，清理字节码缓存和本次临时验证产物，再扫描确认。
同步修正规则中旧包路径和关节定义模块的引用。独立子代理只读复核通过。

在项目内创建 `.artifacts/workflow-check-fajp89g4/`，将 `TMPDIR` 和 pytest `--basetemp` 指向该目录，
设置 `PYTHONDONTWRITEBYTECODE=1` 后运行 `make check`，锁文件、Ruff、10 个测试及 8 个子测试、模型检查均通过。
检查完成后删除 5 个 `__pycache__` 目录及本次临时验证目录，复查项目源码、工具与测试无字节码缓存残留；
第三方依赖环境和用户实验产物保留。本次仅调整开发约定及记录，未更改机器人行为，未运行 GPU 仿真或训练。

### 2026 年 10 月 23 日 T004

两个独立子代理只读复核了模型配置和本机 mjlab 1.6.0 接口，确认当前仅具备模型资源、加载和关节/电机映射。
在本页 T004 中记录实体工厂、显式初始状态、场景元素分离、混合执行器、碰撞命名及动态验收的缺项和依赖；
T002 仍只负责最小实体/场景，执行器后续单独验收。仅更新本页，未修改机器人源码或其他已有未提交改动。

在 `.artifacts/t004-robots-review-nI835kqe/` 下创建 `tmp/`，执行以下命令通过基础验收：

```bash
task_review_dir="$PWD/.artifacts/t004-robots-review-nI835kqe"
TMPDIR="$task_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_review_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_review_dir/pytest -o cache_dir=$task_review_dir/pytest-cache" \
  make check
```

结果：锁文件一致、Ruff 通过、10 个测试和 8 个子测试通过；15 个关节及电机映射检查通过，
模型 `nq=22`、`nv=21`、`nu=0`，16 个网格，模型总质量约 `3.2893 kg`。
本轮没有实现执行器或运行 GPU 场景、关节响应、站立或训练验证；实际控制参数和起始站姿仍待对应任务确认。
全部子代理及检查进程结束后，删除本次验证目录，并清理及复查项目字节码缓存，确认无残留；
排除 `.git/`、`.venv/` 及第三方依赖目录，保留用户实验产物。未提交 Git，T001 和 T002 状态不变。

### 2026 年 10 月 23 日 T005

根据用户反馈核对 mjlab 1.6.0 官方文档、固定 tag 的 Go1 源码及 MuJoCo 3.11.0 路径规则，
确认 `spec.meshdir = str(ASSETS_DIR)` 在当前模型布局下多余。删除该赋值和无其他引用的 `ASSETS_DIR`，
`get_spec()` 直接返回 `MjSpec.from_file(str(MJCF_PATH))`；README 同步解释 XML 的相对资源路径。
两个子代理分别只读核对官方接口和本地路径引用，均确认最小改动范围；历史记录保留。

在 `.artifacts/t005-mesh-loading-Xm39X9zy/` 创建 `tmp/` 和 `cwd/`，设置项目内 `TMPDIR`、
pytest `--basetemp`、Ruff/pytest 缓存目录和 `PYTHONDONTWRITEBYTECODE=1`。
通过 `uv run --no-sync python -B -` 执行内联专项检查：切换至 `cwd/` 后加载和编译成功，
`spec.meshdir` 保留为 `assets/`，多次加载返回独立 spec；与旧绝对 meshdir 加载器相比，
网格顶点/面、质量/惯性、关节和几何关键数组逐项完全一致。
再通过 `MjSpec.attach(..., prefix="robot/", frame=...)` 组合到父 spec 并成功编译，
16 个网格完整，15 个关节的前缀名称正确。

`make check` 通过：锁文件一致、Ruff 通过、10 个测试及 8 个子测试通过；
模型 `nq=22`、`nv=21`、`nu=0`，16 个网格，模型总质量约 `3.2893 kg`。
本次仅简化资源路径加载，未运行 GPU 仿真或训练；下一项仍为 T001，随后进入 T002。
全部子代理和检查进程结束后，删除本次验证目录并清理、复查项目字节码缓存，确认无残留；
排除第三方依赖环境，保留其他已有改动及用户实验产物。未提交 Git。

### 2026 年 10 月 23 日 T006

根据用户确认，无刷采用普通 PD，舵机型号为 HD1910-C001、供电方案为 7.4 V。
三路只读调研分别核对 mjlab v1.6.0 文档/源码、项目模型/动作接口和制造商资料；
将首版执行器类型、10 个建议参数组、参数含义、原 XML 交互和后续验收顺序记录在 T006，
同步 README 中已确认的舵机型号和供电，最终独立复核通过。
飞特公开资料未明确提供 7.4 V 条件的力矩/速度数据；高擎公开资料未找到确切 3532 型号的完整参数，
不将 XML 的 `3.7/1.47 N·m` 或经销商数值升格为已确认实机参数。

在 `.artifacts/t006-actuator-analysis-K1QaBt8X/` 下设置项目内临时与缓存目录，执行：

```bash
task_analysis_dir="$PWD/.artifacts/t006-actuator-analysis-K1QaBt8X"
TMPDIR="$task_analysis_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_analysis_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_analysis_dir/pytest -o cache_dir=$task_analysis_dir/pytest-cache" \
  make check
```

锁文件、Ruff、10 个测试及 8 个子测试、模型检查均通过；模型仍为 `nq=22`、`nv=21`、`nu=0`，
15 个关节、16 个网格。仅修改 README 和本页，未新增执行器或填入增益，未执行 GPU 仿真、阶跃或训练验证；
上述动态验证和参数标定留待对应实现任务，本轮调研完成不代表 M1 完成。
全部子代理及检查进程结束后删除本次验证目录，并清理和复查项目字节码缓存，无残留；
排除第三方依赖环境，保留其他已有改动与用户实验产物。未提交 Git，下一项仍为 T001，随后为 T002。

### 2026 年 10 月 23 日 T007

三路并行调研加主代理交叉核对，检查 mjlab 官方、Unitree RL Mjlab、Booster T1/K1、Menlo Asimov、
PAL Talos、Pollen Microduck、Wuji Hand2、AMP 等公开源码的执行器和实际任务引用，记录版本与可追溯链接；
另用 legged_gym、IsaacLab 和 Unitree RL Lab 作跨框架对照。未将框架类声明、注释或同源副本当成独立采用证据。
对可取得的分支以 `git ls-remote` 核对提交，固定 tag/提交链接；GitHub API 限流时改读 raw 源码和 Git 远程元数据，
没有 clone 或下载仓库到磁盘。源码存在只证明配置选择，不代表本次复现过其训练或实机效果。

结论更新：本项目的普通位置 PD 首版优先让无刷和舵机都使用 `BuiltinPositionActuatorCfg`，按负载分别配参；
需要已标定特殊动力学或明确显式控制时再扩展。T006 原始混合建议保留并注明由 T007 更新。
仅修改本页，机器人源码与硬件参数未变，M0/M1 状态不变，未提交 Git。

在 `.artifacts/t007-actuator-survey-Gmu1Ky8E/` 下设置项目内临时与缓存目录，执行：

```bash
task_survey_dir="$PWD/.artifacts/t007-actuator-survey-Gmu1Ky8E"
TMPDIR="$task_survey_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_survey_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_survey_dir/pytest -o cache_dir=$task_survey_dir/pytest-cache" \
  make check
```

锁文件、Ruff、10 个测试和 8 个子测试、模型检查均通过；模型仍为 `nq=22`、`nv=21`、`nu=0`，16 个网格。
未执行 GPU 仿真、跨执行器阶跃对照或训练。全部子代理、远程查询和检查进程结束后删除本次验证目录，
清理及复查项目字节码缓存，无残留；第三方依赖环境和用户实验产物保留。
下一项仍为 T001，随后按 T002 接入最小场景，再开展执行器动态验收。

### 2026 年 10 月 23 日 T008

三路并行只读调研分别核对 Pollen 实机/执行器接口、HD1910 厂家与社区资料、本机目录和依赖；
主代理交叉核对固定源码。确认 Pollen 原型使用 XL330，HD1910 是另有实现的社区替代；
发现飞特官方 7.4 V BAM 模型，以及社区托管的完整型号原始规格书，更新 T006 当时的资料缺项结论。
在 T008 中记录厂家模型的固件语义边界、三个接入问题、目标文件职责、参数来源和验证顺序，
将可执行实现拆为 T009；不因调研完成改变 M0/M1 状态。

在项目内 `.artifacts/t008-hd1910-research-zuJ6viZF/` 下载固定提交的五个厂家源文件/参数文件，
通过 `uv run --no-sync python -B -` 执行标准库专项检查：M6 JSON 数值有限、`R/kt` 为正、
惯量非负；AST 核对 JSON `hd1910` 与注册表 `HD1910` 不一致；
确认基类已有 `friction_scale_range`，解析 TOML 确认 mjlab extra 的旧版本限制。
厂家 M6 原始 JSON 的 SHA256 为
`81a441fb921130bcc9bcfbd9ee0c77e3c38d9ab758bc7e0559fb029c436355ba`。
专项检查是源码/数据静态验证，未执行完整 BAM 包，未把预测的加载错误当作实际运行日志。

基础验收命令：

```bash
task_hd1910_dir="$PWD/.artifacts/t008-hd1910-research-zuJ6viZF"
TMPDIR="$task_hd1910_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_hd1910_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_hd1910_dir/pytest -o cache_dir=$task_hd1910_dir/pytest-cache" \
  make check
```

结果：锁文件、Ruff、10 个测试及 8 个子测试、模型检查全部通过；
模型 `nq=22`、`nv=21`、`nu=0`，15 个关节、16 个网格，总质量约 `3.2893 kg`。
仅修改本页；用户新增的 `friction_dr_bam.py` 仍为空，未安装 BAM、修改依赖或编造实机参数。
未运行 BAM 动态模型、GPU 阶跃或训练，这些属于 T009 的后续验收。
全部子代理、网络查询和检查进程结束后删除本次临时验证目录；
清理并扫描项目字节码缓存，确认无残留，排除 `.git/`、`.venv/` 和第三方依赖目录。
保留其他已有改动和用户实验产物，未提交 Git。

### 2026 年 10 月 23 日 T009

根据用户明确要求实现，将 T009 调整为可独立验收的执行器组件和测试台，
完整机器人场景依赖仍交由 T002，不跳过阶段验收。
三路子代理分别实现纯模型/厂家参数、CPU 专项测试、GPU 检查工具；
主代理实现 mjlab 适配器、DR 薄封装、包导出与使用说明，并集成复核。

专项验证：

- 将固定上游 `bam/model.py` 的标量函数用 AST 提取为对照，检查 2054 组随机和边界输入；
  float64 最大绝对误差 `1.11e-16`。厂家 JSON 的 SHA256 与 T008 记录相同。
- CPU 专项 `tests/test_hd1910_actuator.py`：54 项通过，覆盖参数来源和校验、别名、
  电气饱和/反电动势、M6 手算参考、spec 覆盖、重复执行器及非 hinge 拒绝。
- 独立复核定位并修复两处生命周期/物理问题：把直接和身体外力纳入摩擦外载荷，
  以及仅在真实物理步后的 `update()` 恢复载荷有效性；GPU 增加针对性回归检查。
- GPU 实测：RTX 4060，`cuda:0`，4 环境 × 3 独立关节，300 个物理步，`dt=0.002 s`。
  精确两步命令延迟、局部 reset、重置后重复控制写入、直接外力 `0.1 N·m`、
  未展开模型字段的报错、初始化后再展开字段、环境间独立性、摩擦单次缩放与限幅均通过。
  最大目标误差 `0.000233 rad`，最大实际执行器力矩 `0.350000 N·m`；后者为测试台显式上限。
- `uv build --offline` 成功生成 sdist 和 wheel；检查 wheel 包含执行器代码、厂家 JSON、NOTICE 和许可证，
  在项目内解包并优先导入 wheel 内容，从其他工作目录加载参数成功。

验收命令（所有临时目录均在本项目内）：

```bash
task_hd1910_dir="$PWD/.artifacts/t009-hd1910"
TMPDIR="$task_hd1910_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_hd1910_dir/ruff-root" \
  PYTEST_ADDOPTS="--basetemp=$task_hd1910_dir/pytest-final -o cache_dir=$task_hd1910_dir/pytest-final-cache" \
  make check

TMPDIR="$task_hd1910_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_hd1910_dir/warp-cache" \
  TORCHINDUCTOR_CACHE_DIR="$task_hd1910_dir/torchinductor" \
  uv run --no-sync python -B tools/check_hd1910.py --device cuda:0 --num-envs 4 --steps 300

TMPDIR="$task_hd1910_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  uv build --offline --out-dir "$task_hd1910_dir/dist"
```

`make check` 通过：锁文件一致、Ruff 通过、64 个测试及 8 个子测试通过；
第三方依赖产生一条 `torch.jit.script` 弃用提示，不影响检查结果。
原始 MJCF 检查仍通过，`nq=22`、`nv=21`、`nu=0`，15 个关节、16 个网格，总质量约 `3.2893 kg`。
未运行实机硬件、完整机器人站立或训练；未修改 `pyproject.toml`、`uv.lock`、原始 MJCF 或已有电机映射。
全部子代理和 CPU/GPU/构建检查进程结束后，删除本次 `.artifacts/t009-hd1910/`、本次 Ruff 缓存项及
项目字节码缓存，最终扫描确认无残留；排除 `.git/`、`.venv/` 和第三方依赖，保留已有实验文件。
未提交 Git。下一项仍为 T001，随后按 T002 建立最小场景，再接入混合执行器；
实机模式/增益读回与 7.4 V 响应标定作为后续参数确认工作，不影响本次组件功能验收。

### 2026 年 10 月 23 日 T010

新增 `src/ht_microduck/actuators/HD_1910_C001/README.md`，说明目录结构、P 电压控制与 M6 摩擦预算、
配置字段和单位、三个舵机关节的配置示例、startup 事件/字段展开、XML 参数覆盖、DR/reset、
物理步延迟、CPU/GPU 验证命令与参数来源。独立子代理只读复核通过，说明与当前代码一致。
仅新增该 README 并更新本页，未修改执行器行为或依赖，没有新增测试文件。

在 `.artifacts/t010-hd1910-readme/` 下设置 `TMPDIR`、Ruff/pytest 缓存和 pytest `--basetemp`，
以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check`：锁文件、Ruff、64 个测试及 8 个子测试、模型检查均通过。
第三方依赖仍有一条 `torch.jit.script` 弃用提示。
通过 `uv run --no-sync python -B -` 检查全部本地链接、空白和三个 Python 示例的语法，
实际执行最小配置示例，确认三个舵机关节、7.4 V、默认关闭 DR 及 startup 事件；Bash 示例语法检查通过。
本轮为文档改动，未重复执行 GPU；GPU 证据与范围明确引用 T009。
子代理与检查进程结束后删除本次临时目录，清理并扫描项目字节码缓存，无残留；
排除 `.git/`、`.venv/` 及第三方依赖，保留已有实验文件和其他未提交改动，未提交 Git。
下一项仍为 T001，随后按 T002 接入最小场景。

### 2026 年 10 月 23 日 T011

`ht_microduck_constants.py` 新增 `get_actuator_cfgs()`，每次返回独立的两组配置：
12 个无刷使用 `BuiltinPositionActuatorCfg`，3 个舵机使用已有 `FrictionDRBamActuatorCfg`。
无刷 `stiffness`、`damping` 和 `effort_limit` 均需显式传入，并校验有限值、有效范围与 bool；
保留原 XML 的被动阻尼、摩擦和惯量假设。`BRUSHLESS_MJCF_EFFORT_LIMIT=3.7` 标为未标定模型上界，
工厂拒绝更大的无刷限幅，防止原 XML 关节总力矩限幅静默截断输出。
舵机明确采用厂家 7.4 V M6 模型、`kp_fw=32`、`1.471 N·m` 堵转近似上限和关闭 DR；
两组延迟暂设为零。调用方可调整独立配置，但修改力矩上限仍需协调关节总限幅。
README 补充调用、单位、startup/字段展开要求与专项命令；原始 MJCF、关节分组和依赖保持不变。

并行子工作分别只读复核 mjlab 1.6.0 接口/模型交互、实现 CPU 专项测试、实现 GPU 检查工具，
主代理集成并运行统一验收。最终独立复核通过；补充了未饱和、逐舵机不同目标的直接控制映射检查。

验收命令（临时目录均在项目内）：

```bash
task_actuator_dir="$PWD/.artifacts/t011-actuator-config"
TMPDIR="$task_actuator_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_actuator_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_actuator_dir/pytest -o cache_dir=$task_actuator_dir/pytest-cache" \
  make check

TMPDIR="$task_actuator_dir/gpu-agent/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_actuator_dir/gpu-agent/warp" \
  TORCHINDUCTOR_CACHE_DIR="$task_actuator_dir/gpu-agent/torch" \
  uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0 --num-envs 4 --steps 300
```

结果：

- `make check` 通过：锁文件一致、Ruff 通过、88 项测试和 8 项子测试通过。
  新增 `tests/test_robot_actuators.py` 的 24 项检查覆盖必填参数/边界、配置独立性、15 关节完整覆盖、
  真实机器人 Entity 编译 `nu=15`、无刷 PD 公式及双向限幅、被动阻尼独立计算、HD1910 参数覆盖。
  原始 `get_spec()` 仍为 `nq=22`、`nv=21`、`nu=0`，16 个网格，总质量约 `3.2893 kg`。
- GPU 实测：RTX 4060、`cuda:0`、4 环境 × 15 个独立关节、300 步、`dt=0.002 s`。
  两组测试台限幅均为 `0.35 N·m`，不是本机硬件额定值；无刷测试增益 `kp=2`、`kd=0.1`。
  实际力矩范围 `[-0.350000, 0.350000] N·m`，无刷最大保持误差 `0.000006 rad`，
  舵机 `0.000566 rad`，末速度 `0.000111 rad/s`；目标/控制映射、未饱和舵机通道、
  全部关节双向限幅、有限值、独立摩擦/阻尼字段和局部 reset 均通过。
  新增映射断言后的最终脚本再次通过 GPU 专项与 Ruff 检查。
- README 本地链接、Python 示例语法和混合配置示例实际执行通过。
  第三方依赖仍有现存的 `torch.jit.script` 弃用提示，不影响结果。

本轮未验证完整机器人站立、训练或实机响应；无刷增益/持续力矩、延迟与本机 HD1910 标定仍待确认。
全部子代理与检查进程结束后，删除本次 `.artifacts/t011-actuator-config/`，清理项目字节码缓存并复查无残留；
排除 `.git/`、`.venv/`、第三方依赖和符号链接，保留其他已有改动及实验产物，未提交 Git。
下一项仍为 T001 整理已有基线，随后按 T002 接入完整机器人实体与最小场景。


### 2026 年 10 月 23 日 T012

只读复核用户添加的两组随机命令延迟，未修改源码、测试、README 或用户参数；
两个子代理分别复核 mjlab 1.6.0 实现语义、旧验证与说明的适配情况。
当前文件使用英文逗号，语法合法；聊天粘贴的两处中文逗号若原样复制会产生语法错误。

结论：`delay_min_lag=0`、`delay_max_lag=3` 为合法的离散随机延迟范围；
`delay_update_period=10` 表示每 10 次控制缓冲计算有一次更新机会，届时 40% 保持 lag，
其余 60% 从 0、1、2、3 均匀采样。重采样也可能取到原值，所以更新机会前后保持原 lag 的概率为 55%。
默认 `delay_per_env_phase=True` 使各环境更新时点错开；每环境内 12 个无刷共享一个 lag，
3 个舵机共享另一个 lag，两组独立采样。命令目标被延迟，反馈位置/速度仍使用当前状态。
reset 清除选定行的 lag/历史并重采样相位，首个新目标回填历史。
正常一步一写控制时，`dt=0.002 s` 对应 0–6 ms 延迟和每 20 ms 一次更新机会。
实现按 `write_data_to_sim()` 调用计数，额外写控制也推进历史/采样计数；
ManagerBasedRlEnv 的 reset/autoreset 会额外写控制，因此不能把计数完全等同于绝对仿真时间。
两类硬件使用相同范围可作为统一随机化假设，尚无实机证据证明其延迟分布相同。

验收在项目内 `.artifacts/t012-delay-review/` 设置 TMPDIR、pytest basetemp、Ruff/Warp/Torch 缓存，
全部 Python 执行使用 `PYTHONDONTWRITEBYTECODE=1`。实际执行：

```bash
task_delay_dir="$PWD/.artifacts/t012-delay-review"
TMPDIR="$task_delay_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_delay_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_delay_dir/pytest -o cache_dir=$task_delay_dir/pytest-cache" \
  make check

TMPDIR="$task_delay_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_delay_dir/warp" TORCHINDUCTOR_CACHE_DIR="$task_delay_dir/torch" \
  uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0 --num-envs 4 --steps 300

TMPDIR="$task_delay_dir/tmp" PYTHONDONTWRITEBYTECODE=1 uv run --no-sync make model
```

结果：锁文件和 Ruff 通过；`make check` 在测试阶段失败，87 项测试、8 项子测试通过，1 项失败。
失败为 `tests/test_robot_actuators.py:66` 仍断言两组 `min=max=0`，与用户新配置冲突；
不据此否定合法的新配置，也未将当前统一验收写为通过。单独补跑模型检查通过，原始模型仍 `nu=0`。
RTX 4060 上 4 环境 × 15 关节 × 300 步 GPU 检查通过，测试台限幅 ±0.35 N·m，
无刷保持误差 0.000006 rad、舵机 0.000566 rad、末速度 0.000111 rad/s。
但现有探针在 reset 后首写目标，响应阶段目标恒定，不能单靠这些结果确认随机延迟生效。

另以相同项目内临时/缓存目录，通过 `uv run --no-sync python -B -` 执行内联 GPU 变化目标诊断：
seed=1910、4 环境、15 关节、60 个物理步、dt=0.002 s，逐通道目标为
`(step+1)*0.0002*(1+channel/30)`，奇数环境反号；使用原工厂延迟参数且不额外写控制。
逐步核对无刷控制来自 `history[max(0,t-lag)]`、BAM 由同一延迟目标和当前反馈计算力矩，
并检查 lag 仅在各自随机相位对应的 10 步更新机会变化。全部通过；
两组均观察到 lag 0/1/2/3，无刷非零 lag 为 94/240 个环境步，舵机为 145/240。
这些计数仅用于确认非零延迟确实发生，不用于估计厂家或硬件的延迟分布。

未解决项：constants docstring、README 仍声称默认零延迟；旧 CPU 断言需同步；
变化目标回归需固化到 GPU 工具。以上已记为待办 T013，未在只读评审中修改。
所有子代理和检查进程结束后删除本次临时产物，清理并复查项目字节码缓存无残留；
排除 .git、.venv、第三方依赖和符号链接，保留用户已有改动与实验文件，未提交 Git。
下一项可执行工作为 T013 同步随机延迟的验证与说明；完整场景仍按 T001、T002 推进。

### 2026 年 10 月 23 日 T014

按用户要求重新核对 `robots/`，两路子代理分别只读复核 mjlab 1.6.0 官方实体/配置接口与
本地模型/验证覆盖，主代理联网核对固定 v1.6.0 G1、Go1、Entity 与 action 源码并集成结论。
仅更新本页；未修改机器人源码、原始 XML、README、用户延迟参数、测试或依赖，未提交 Git。

验收命令：

```bash
task_robot_review_dir="$PWD/.artifacts/t014-robots-review-PKJ9GdzW"
TMPDIR="$task_robot_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_robot_review_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_robot_review_dir/pytest -o cache_dir=$task_robot_review_dir/pytest-cache" \
  make check

TMPDIR="$task_robot_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1 uv run --no-sync make model
```

`make check` 的锁文件与 Ruff 通过，测试为 87 项通过、8 项子测试通过、1 项失败；
失败仍是 `tests/test_robot_actuators.py:66` 的零延迟旧断言，与 T012 已记录问题一致，
不是配置语法或模型编译错误。统一检查未通过，修复工作仍为 T013，不在本轮只读评审中改写用户配置。
模型阶段因测试失败未自动执行，单独补跑通过：15 个关节、16 个网格，
`nq=22`、`nv=21`、`nu=0`，总质量约 `3.2893 kg`。第三方 `torch.jit.script` 弃用提示仍存在。

另在相同项目内 TMPDIR 下以 `uv run --no-sync python -B -` 执行 CPU 内联组合检查，实际结果为：

- 当前安装版本 `mjlab=1.6.0`；调用现有工厂组装 `EntityArticulationInfoCfg` 后编译得到 `nu=15`。
  所用 `kp=2`、`kd=0.1`、限幅 `0.35 N·m` 只为编译探针参数，不代表整机增益或硬件额定值。
- 原模型 `qpos0` 根高度为 `0.167 m`，默认 Entity 的 `init_state` keyframe 根高度为 `0.0 m`。
- 机器人碰撞体 10 个均无名，两个 ankle 碰撞体使用默认摩擦 `(1, 0.005, 0.0001)`，
  模型没有 site 或 sensor。
- 原始 spec 与 plane terrain 组合后编译成功，但存在 `robot/floor` 和 `terrain` 两个 plane、两个灯光。

上述结果是静态 CPU 组合证据，没有运行 GPU、物理步进、完整机器人 reset、站立或训练；
本轮评审完成不表示 M1 或统一检查通过。剩余代码清单、参数边界与按依赖推进的顺序见 T014 正文。
所有子代理和检查进程结束后，删除本轮临时目录，清理并扫描项目字节码缓存；
排除 `.git/`、`.venv/`、第三方依赖和符号链接，保留用户已有改动与实验文件。
下一项为 T013，随后按 T001、T002 推进整机接入。

### 2026 年 10 月 23 日 T015

按用户明确指定的 MicroDuck 官方重做对照。两个子代理分别只读核对本地 robots/mjlab 1.6 接口、
Pollen 官方固定提交的机器人和任务配置，主代理联网交叉核对官方仓库与原始源码并汇总。
本次仅更新本页任务和评审记录；机器人源码、原始 XML、测试、README、用户延迟参数及依赖均保留，未提交 Git。

在项目内创建专用临时目录，以无字节码模式执行：

```bash
task_microduck_review_dir="$PWD/.artifacts/t015-microduck-review-cEXlFNf8"
TMPDIR="$task_microduck_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_microduck_review_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_microduck_review_dir/pytest -o cache_dir=$task_microduck_review_dir/pytest-cache" \
  make check

TMPDIR="$task_microduck_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1 uv run --no-sync make model
```

锁文件与 Ruff 通过；测试 87 项及 8 项子测试通过、1 项失败，仍为 `tests/test_robot_actuators.py:66`
要求零延迟的旧断言。统一检查未通过，已有问题继续由 T013 修复，不修改用户配置以迎合旧断言。
单独补跑模型检查通过：15 个关节、16 个网格，`nq=22`、`nv=21`、`nu=0`，质量约 `3.2893 kg`。
第三方 Torch 弃用提示仍存在。只读 CPU 内联组合复核得到装配实体 `nu=15`，
默认 Entity 初态根高从源模型 `0.167 m` 变为 `0.0 m`，确认需显式初态。
本轮未运行 GPU、完整机器人步进、站立或训练；评审完成不表示统一检查或 M1 已通过。

所有子代理和检查进程结束后，删除本轮 `.artifacts/t015-microduck-review-cEXlFNf8/`，
清理并扫描源码、工具、测试、文档及验证目录，未发现 `__pycache__/`、`.pyc` 或 `.pyo` 残留；
排除 `.git/`、`.venv/`、第三方目录和符号链接。下一项为 T013，随后按 T001/T002 推进整机集成。

### 2026 年 10 月 23 日 T016（含 T013）

用户明确要求实施上一轮官方对照清单。并发分工为实体工厂/CPU 模型测试、随机延迟回归、
场景接口只读复核；主代理负责真实场景工具、README/任务记录、集成审阅与 GPU/统一验收。
仅在既有工作区上增量修改：constants、两层 robots 导出、README、工具及相关测试；
原始 XML/mesh、关节分组、用户延迟值、依赖和锁文件保留，未提交 Git。

实际执行命令（临时及缓存目录均在本项目内）：

```bash
task_robot_dir="$PWD/.artifacts/t016-robot-integration-pcKfBb6n"
TMPDIR="$task_robot_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_robot_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_robot_dir/pytest -o cache_dir=$task_robot_dir/pytest-cache" \
  make check

TMPDIR="$task_robot_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_robot_dir/warp" TORCHINDUCTOR_CACHE_DIR="$task_robot_dir/torch" \
  uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0

TMPDIR="$task_robot_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_robot_dir/warp" TORCHINDUCTOR_CACHE_DIR="$task_robot_dir/torch" \
  uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150
```

结果：

- `make check` 全部通过：锁文件、Ruff、106 项测试及 8 项子测试、源模型编译与映射、Git 差异空白。
  源模型仍 `nq=22`、`nv=21`、`nu=0`，质量 `3.2893 kg`；实体/场景测试确认装配后 `nu=15`。
  新增实体 CPU 专项 18 项通过，另独立核对 README/开发文档的本地链接及未跟踪改动文件的空白。
  现有第三方 `torch.jit.script` 弃用警告仍存在，不影响检查。
- RTX 4060 上混合铰链检查通过：4 环境 × 15 关节、300 步响应，实际限幅 `±0.35 N·m`，
  无刷最大保持误差 `0.000006 rad`、舵机 `0.000566 rad`、末速度 `0.000111 rad/s`。
  额外 64 步变化目标检查中，两组均出现 lag `0/1/2/3`，观测到无刷 9 次、舵机 13 次 lag 变化；
  逐帧历史索引、BAM 当前反馈和每环境 10 步更新相位全部通过。这些计数仅证明随机延迟生效。
- 真实机器人场景 GPU 检查通过：4 环境、150 步、`dt=0.002 s`，正常重力与碰撞，唯一地面/灯光，
  所有环境左右足均出现有力接触，状态和传感器数值有限、接触/约束容量无溢出。
  显式状态/目标恢复、非零颈部测试初态、控制映射、BAM 字段独立性和局部 reset 隔离通过；
  末根高 `0.161931–0.161996 m`，本次最大执行器力矩 `0.132858 N·m`。
  工具使用无刷 `kp=10`、`kd=0.4`、限幅 `2 N·m` 及颈部 `0.03 rad` 的显式测试假设，
  不代表已标定参数或已通过稳定站立验收；主动触发两组限幅的证据来自上述独立铰链台架。

所有子代理及检查进程结束后，删除本次 `.artifacts/t016-robot-integration-pcKfBb6n/` 与检查缓存，
清理并复扫源码、工具、测试、文档及验证目录，无 `__pycache__/`、`.pyc`、`.pyo` 残留；
排除 `.git/`、`.venv/`、第三方目录和符号链接，保留用户已有源码与实验文件。
T013/T016 完成；T001 和阶段前置条件仍保留，T002 的功能证据由本轮提供。
下一项为 T001 整理 Git 基线，之后复核 T002 并单独验证全身保持、负载分组增益与短站立。

### 2026 年 10 月 23 日 T017

对照用户指定的 `legged_wbc_mjlab/src/assets/robots/ri_4438/ri_4438_constants.py`：
其无参工厂从 `Ri4438Cfg` 取参数；本机仍显式传参，仅在简短预览入口使用检查假设 `10/0.4/2`。
保留必要的场景/初态/passive viewer，去掉额外 CLI、打印、相机定制并压缩重复 docstring；
本轮修改限于 constants、README 和本页，原工厂行为、执行器参数、模型及依赖不变。

项目内 TMPDIR、pytest basetemp、Ruff 缓存及无字节码模式下 `make check` 通过：
106 项测试与 8 项子测试，模型和差异检查通过。最终 main 块核验为 15 执行器、单一地面、根高 `0.167 m`。
以用户原路径实际启动 GUI，在 `DISPLAY=:1` 检测到 MuJoCo 窗口，通过窗口管理器关闭后退出码为 0。
早期临时探针直接定时调用 `Handle.close()` 曾触发退出竞态（139），最终正常窗口关闭路径通过；
未改第三方 viewer，不将静态预览当作 BAM 动态验收。独立代理只读复核完成。
所有进程结束后删除本次 `.artifacts/t017-direct-preview-v6KBZY8o/`，清理并复扫项目字节码无残留。
未提交 Git，下一项仍为 T001。

### 2026 年 10 月 23 日 T018

增加模块级 `HOME_FRAME`、`BRUSHLESS_ACTUATOR_CFG`、`SERVO_ACTUATOR_CFG`、`FULL_COLLISION`、
`HT_MICRODUCK_ARTICULATION`、`HT_MICRODUCK_ROBOT_CFG`；预览直接使用整机配置。
工厂可无参深拷贝，并保留参数/初态覆盖；检查工具默认取模块参数。混合分组、延迟、源模型与依赖保留，
`10/0.4/2` 继续标明为仿真假设。两路代理分别更新测试/导出及只读复核，主代理集成验证。

在 `.artifacts/t018-module-config-7t8myJH0/` 内配置 TMPDIR、pytest basetemp 和缓存，Python 均禁用字节码。
`make check` 通过：107 项测试及 8 项子测试，锁文件/Ruff/模型/差异检查通过；实体专项 19 项通过。
`uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150` 通过，
末根高 `0.161931–0.161996 m`、峰值执行器力矩 `0.132858 N·m`，双脚接地、reset、有限值与限幅通过。
`uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0` 通过，300 步响应及 64 步延迟回归保留。
原 constants 路径实际打开 MuJoCo 窗口，经窗口管理器关闭退出码 0；README 本地链接和改动文件空白检查通过。
既有第三方 Torch 弃用提示保留；本轮不宣称稳定站立或实机标定通过。

全部代理和检查进程结束后删除本轮临时目录，清理并复扫源码、工具、测试、文档及验证目录的字节码无残留，
排除 `.git/`、`.venv/`、第三方目录及符号链接。未提交 Git，下一项仍为 T001。

### 2026 年 10 月 23 日 T019

仅整理 constants 与本页：按参考文件分为 MJCF、关节映射、执行器、初态、碰撞、最终配置和预览，
统一四空格缩进、规范空行和简短注释。两路只读复核确认结构及定义依赖正确。
项目内临时目录为 `.artifacts/t019-constants-style-oPHzHzn9/`；设置 TMPDIR、pytest basetemp 和缓存，
以无字节码模式执行 `ruff format --check`、`ruff check` 和 `make check`，全部通过：107 项测试及 8 项子测试。
整理前后逐条顶层 AST 多重集相同，函数体、参数、接口及共享引用保持不变；未新增测试或重跑 GPU/GUI。
所有代理和检查进程结束后删除临时目录，清理并复扫项目字节码无残留，保留既有改动及实验文件。
未提交 Git，下一项仍为 T001。

### 2026 年 10 月 23 日 T020

两路子代理分别只读核对 Pollen 官方配置和本地调用/参考风格，主代理修改常量模块、两项专项工具、
两项 CPU 测试文件、README 和本页，并集成验收。删除重复参数转传后 constants 从 306 行减至 233 行。
默认执行器、初态、碰撞及延迟数值未改；机器人入口只返回深拷贝，调用方直接编辑自己的配置。
独立复核未发现默认行为回归或调用遗漏，接口变动与校验边界见上方 T020 说明。

实际验收命令：

```bash
task_config_dir="$PWD/.artifacts/t020-config"
TMPDIR="$task_config_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  RUFF_CACHE_DIR="$task_config_dir/ruff" \
  PYTEST_ADDOPTS="--basetemp=$task_config_dir/pytest-final -o cache_dir=$task_config_dir/pytest-final-cache" \
  make check

TMPDIR="$task_config_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_config_dir/warp" TORCHINDUCTOR_CACHE_DIR="$task_config_dir/torch" \
  uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0 --num-envs 4 --steps 300

TMPDIR="$task_config_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_config_dir/warp" TORCHINDUCTOR_CACHE_DIR="$task_config_dir/torch" \
  uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150
```

结果：

- `make check` 全部通过：锁文件、Ruff、83 项测试与 8 项子测试、源模型及差异检查。
  随旧接口移除 27 项旧参数入口测试，去掉重复的标准库复制测试；4 项现有物理回归增加
  零主动阻尼、`3.7 N·m` 总限幅的边界配置。真实 PD 公式/双向饱和、独立副本和任务修改后编译仍验证。
- 五个改动 Python 文件的 `ruff format --check` 通过；README 两个修改后的示例实际执行通过，
  修改文件空白与本地文档链接检查通过。
- 用项目内修改前快照和当前模块分别创建整机，482 个编译模型数组逐项完全一致，
  均为 `nq=22`、`nv=21`、`nu=15`。源 XML 与 mesh 未修改，原始模型仍 `nu=0`。
- RTX 4060 上混合执行器四环境、300 步通过，实际力矩 `±0.35 N·m`，
  无刷/舵机保持误差 `0.000006/0.000566 rad`；64 步随机延迟回归通过，
  两组均出现 `0/1/2/3` 步 lag，lag 变化次数仍为无刷 9、舵机 13。
- 真实机器人四环境、150 步场景通过，双脚接地、控制映射、BAM 字段独立性和局部 reset 正常；
  根高 `0.161931–0.161996 m`、峰值执行器力矩 `0.132858 N·m`，与修改前记录一致。

现有第三方 Torch 弃用提示保留。未运行 GUI、实机标定或训练，短检查不构成稳定站立验收。
所有子代理与检查进程结束后删除本次 `.artifacts/t020-config/`，清理并复扫项目字节码无残留，
排除 `.git/`、`.venv/`、第三方目录及符号链接，保留已有修改和实验产物。
未提交 Git；无本次遗留阻塞，未知实机增益、力矩/速度和延迟仍需后续标定。
下一项为 T001 整理 Git 基线，随后依 T002 复核场景阶段验收。

### 2026 年 10 月 27 日 T021

两路子代理分别只读核对官方实机与训练仓库，主代理核对本地代码并更新本页。
固定核对版本、差异矩阵、后续任务及源码链接见 T021；独立复核后补充了标定变更后的重验证要求、
硬件工作的依赖关系及部署前仿真性能门槛。未修改 Python、XML、依赖或 README，未安装依赖或提交 Git。

实际验收命令（目录使用前已在项目内创建，结束时已删除）：

```bash
task_review_dir="$PWD/.artifacts/t021-review"
export TMPDIR="$task_review_dir/tmp" PYTHONDONTWRITEBYTECODE=1
export RUFF_CACHE_DIR="$task_review_dir/ruff"
export PYTEST_ADDOPTS="--basetemp=$task_review_dir/pytest -o cache_dir=$task_review_dir/pytest-cache"
make check
make test
make model
git diff --check
git diff --cached --check
```

结果：

- `make check` 的离线锁文件检查通过；Ruff 在现有 constants 的预览入口第 212 行报 `I001`，
  因而统一检查整体未通过。本任务未改该文件，问题补记至 T001，不回写历史通过记录。
- 单独运行后续检查：83 项测试及 8 项子测试通过；源模型编译、15 关节及电机映射检查通过，
  `nq=22`、`nv=21`、`nu=0`，模型质量 `3.2893 kg`。第三方 Torch 弃用提示仍在。
- 文档专项检查通过：32 个任务编号唯一、声明的前置依赖无环、本地链接存在、10 个新增上游链接固定至核对 SHA，
  无尾随空白；Git 暂存/未暂存差异空白检查通过。未新增测试文件。
- 本次未运行 GPU、训练、导出或实机；沿用旧专项记录只说明已有集成能力，不声明新运行结果。
- 所有子代理及检查进程结束后，删除本次临时目录，清理并复扫项目字节码为零残留；
  排除 `.git/`、`.venv/`、第三方目录和符号链接，保留已有改动与实验文件。

T021 的比较与任务规划已交付，不代表 M0/M1 或新增实现任务通过验收。
剩余问题为 T001 的 Git 基线与 Ruff 错误，以及后续任务明确列出的实机参数/协议和运行证据。
下一项为 T001，随后复核 T002，再实施 T022 的控制契约与 T023 的最小平地速度任务。

### 2026 年 10 月 27 日 T032

参考 `/home/sunteng/projects/quadruped_lab` 的 `AGENTS.md`、`.gitignore`、
`docs/DEVELOPMENT_WORKFLOW.md`、`docs/COLLABORATION_REVIEW.md` 和设计/审查模板。
读取的是当日未提交工作区，不能只用参考仓库 HEAD 代表这些文件的版本；关键内容 SHA256：

- `docs/DEVELOPMENT_WORKFLOW.md`：`8add6d4adbeccc864f135d91780020066643fd08a1f3d7b59ef24cd5c6d2b142`。
- `.gitignore`：`6fb02713e45600251ad52065b31ad4ea35772b0da7dd528642c3441191288018`。

实际交付：

- 本页保留工作流、任务与阶段的统一入口，补充变更规模、模块依赖、技术依据和专项验收选择。
  AGENTS 与 README 链接对应规范，新增协作审查说明及设计/审查模板；小修改不额外建立专题文档。
- `.gitignore` 排除环境、缓存、构建和根运行产物，保留正式测试、流程文档、源码、锁文件和模型资源可跟踪。
  未照搬参考项目的目录布局、测试/流程文档忽略规则、作者版权或缺失的工具指南。
- Makefile 自动为每次检查分配项目内独立目录，设置 TMPDIR、pytest basetemp 和缓存，保留失败现场。
  `make`/help/dry-run 不产生检查目录；并行目标不共享临时目录，基目录为符号链接时拒绝写入。
- 仅删除 constants 预览入口两条 import 之间的空行，修复已有 Ruff I001。
  改前后 AST 完全一致；其他 39 个源码/资源/测试文件的哈希保持不变，依赖声明与锁文件未修改。

实际验证：

- 在仓库根直接运行 `make check` 全部通过：离线锁文件、Ruff、83 项测试、8 项子测试、源模型和 Git 差异空白。
  模型仍为 `nq=22`、`nv=21`、`nu=0`、15 个关节、16 个网格、质量 `3.2893 kg`。
  第三方 Torch 弃用提示保留；未运行 GUI、GPU、训练或实机，格式修复不改变控制行为。
- 使用项目内临时 uv 替身验证 Makefile 编排：`make test` 的 basetemp/cache 路径、
  `make -j2 lint model` 的独立目录、`make check` 遇锁文件失败立即停止，以及保留 `uv run --no-sync`。
  替身只验证编排，不代替前述真实检查。串行检查 help/dry-run 无副作用，符号链接路径拒写检查通过。
- 用 `git check-ignore --no-index` 及未跟踪文件清单核对产物被忽略、测试/文档/资源可见；
  主代理复核 16 个产物路径和 17 个保留路径，全部符合预期。
- 文档专项检查通过：29 个本地链接存在、33 个任务编号唯一、声明的前置依赖无环；
  9 个交付文件无尾随空白，新建未跟踪文件已按实际内容审阅。
- 独立审查者只读复核全部交付文件、Makefile 和源码快照，结论为独立审查通过，无验收相关遗留问题。
  另一子代理只负责 `.gitignore`，没有共享文件同时修改。

所有代理和检查进程结束后，删除本次 `.artifacts/t032-workflow/` 及 5 个实际创建的检查目录，
清理并复扫项目字节码为零残留；排除 `.git/`、`.venv/`、第三方依赖和符号链接，保留用户既有修改与实验产物。
未在参考仓库写文件，未执行 Git 暂存、提交、推送或合并。T001/T002 和阶段状态保持原状；
下一项为 T001 的资源归属审阅及基线整理，获对应提交授权后再完成其 Git 验收。

### 2026 年 10 月 27 日 T033

默认模型从 `HT-DK_V2.xml` 替换为来源包的 `HT-DK_URDF.xml`，全部 16 个 STL 复制入包内。
来源为 `/home/sunteng/Downloads/HT-DK_URDF`，其 XML SHA256 为
`7c453442a34a79a1fc08262829ef8b076d3a40c1bbc9656f98988f5656a91a1f`；
项目 XML 与来源仅有 `meshdir="assets/"` 和预览根高 `0.171 m` 两处适配，网格逐字节一致。
运行时不再依赖来源目录；旧 XML 已移除，用户已有常量模块预览入口及其他无关修改保留。

新模型质量为 `3.2946797 kg`；颈俯仰、头俯仰、头滚转、嘴部限位分别为
`[-1.21, 2.3]`、`[-1.571, 1.88]`、`[-0.36, 0.36]`、`[0, 0.23] rad`。
关节名称、顺序、轴和 12+3 分组兼容，执行器参数与依赖未改。
基座碰撞盒命名按新模型前后顺序调整，足底 site 更新至左右镜像倾斜约 `5°` 的底面中心，
site 方向仍沿用踝坐标系。`HOME_FRAME` 根高同步为 `0.171 m`，最低足边离地
`3.840389/3.840301 mm`，预览与实体初态均无接触；旧根高会轻微穿地，不能继续使用。

实际验收：

```bash
make check
task_model_dir="$PWD/.artifacts/t033-model"
mkdir -p "$task_model_dir/tmp" "$task_model_dir/gpu/tmp"
TMPDIR="$task_model_dir/gpu/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_model_dir/gpu/warp" TORCHINDUCTOR_CACHE_DIR="$task_model_dir/gpu/torch" \
  timeout 180s uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150
TMPDIR="$task_model_dir/tmp" PYTHONDONTWRITEBYTECODE=1 \
  uv build --wheel --offline --out-dir "$task_model_dir/dist"
```

- `make check` 通过：锁文件、Ruff、85 项测试与 8 项子测试、模型和 Git 差异空白检查。
  被动模型为 `nq=22`、`nv=21`、`nu=0`，整机为 `nu=15`；更新的实体测试核验新质量、限位、
  基座碰撞命名和倾斜足底，修改后的测试文件另通过 `ruff format --check`。
- RTX 4060 / `cuda:0` 上正式场景检查退出码 0：种子 `1910`、4 环境、150 步、`dt=0.002 s`，
  末根高 `0.166165–0.166172 m`、峰值力矩 `0.138278 N·m`；双足接地、目标映射、有限值、
  力矩限幅、BAM 字段独立性和局部 reset 通过。未运行训练、GUI 或实机，不构成稳定站立验收。
- 改换工作目录后，被动模型和整机均编译通过；离线 wheel 构建成功，包内新 XML 和 16 个 STL
  与项目资源逐字节一致，没有旧 XML。原始下载目录未修改。
- 来源对比与最终独立审查由两路只读代理完成；独立审查者另从二进制 STL 核验底面中心和离地高度，
  确认初态无接触、控制顺序兼容，无验收相关遗留问题。第三方 Torch 弃用提示仍保留。

所有代理与检查进程结束后，删除本轮 `.artifacts/t033-model/` 和 `.artifacts/checks/run-QHPe9zZm/`，
清理并复扫项目字节码为零残留，排除 `.git/`、`.venv/`、第三方依赖与符号链接，保留已有实验产物。
未提交 Git；T033 完成，下一项仍为 T001，M0/M1 阶段状态保持不变。

### 2026 年 10 月 27 日 T034

核对本地固定限幅的无刷 PD、参考项目的运行时 NT 插值/驱动象限限幅、参数 JSON 和原始资料图片，
再核对安装的 mjlab `1.6.0` 与官方 `v1.6.0` 固定版本源码。
用户确认“3530”指 HTDW-3532-02-DNE，本地原名称已正确，因此未改型号映射。
建议新增对应的轻量 NT-PD 执行器；曲线、接入边界、与通用 DC 模型的差异、
型号/工况假设及后续实现验收见上方 T034，当前没有实现新的执行器或修改默认控制行为。

实际验证：

- `make check` 退出码 0：锁文件、Ruff、85 项测试与 8 项子测试、源模型和 Git 差异空白检查通过。
  模型仍为 15 个关节、16 个网格，`nq=22`、`nv=21`、`nu=0`、质量 `3.2947 kg`。
- 用内存中的参考 `motoring_limit` 函数执行 CPU 数值探针，全部锚点和正负速度与独立 NumPy 插值一致；
  与本机 `dc_motor_clip` 对比，`167/211 rpm` 的曲线/直线输出分别为
  `1.5/1.640333`、`1.0/1.097667 N·m`（同向请求 `2 N·m`），
  `400 rpm` 时分别为零驱动能力与 `-1.233333 N·m` 输出，证实两种模型不能互换。
  该探针仅核对数学行为，不代表新执行器已集成或电机已实测。
- 文档本地链接、空白、35 个任务编号唯一性检查通过；来源文件 SHA256 与记录一致。
  哈希对照本次基线确认仅 `docs/development.md` 改动，没有修改源码、XML、网格、参数或依赖。
- 两路只读子代理分别核对参考资料和独立审查结论；复核后补充了本机父类没有参考代码
  `_clip_effort` 的兼容性差异，明确不能原样复制参考类。第三方 Torch 弃用提示保留。
  本轮为分析与文档，未新增测试、未运行 GPU、训练或实机。

所有代理与检查进程结束后，删除 `.artifacts/t034-nt-review/` 与 `.artifacts/checks/run-7PhTgiMI/`，
清理并复扫项目字节码为零残留，排除 `.git/`、`.venv/`、第三方依赖和符号链接，保留已有修改与实验产物。
T034 分析完成，尚未交付 NT 执行器；下一项相关工作为完善设计并实施该执行器及专项短跑，
M0/M1 验收与 T001 的 Git 基线要求保持不变，未提交 Git。

### 2026 年 10 月 27 日 T035

新增 `actuators/HTDW_3532_02_DNE/`：六字段冻结参数与严格加载校验、分段NT纯函数、
`HTDW3532ActuatorCfg` / `HTDW3532Actuator`、startup字段声明，以及有来源的JSON、原始PNG和说明。
常量模块将12个无刷接入新执行器，保留型号/关节顺序、10/0.4/2、0–3步延迟及XML被动参数；
3个HD1910 BAM、初态、机器人资源与依赖保持原状，用户已有main入口保留。
正式工具和测试同步新的原生 affine 控制项与实际力矩，README说明了模型字段、ctrl含义和预览边界。

最终执行器由 Python 更新输出轴NT范围，MuJoCo原生 affine PD 计算实际力矩并保留隐式阻尼积分。
初版直接显式PD曾使整机踝峰速约53rad/s、持续饱和；此问题已修复，最终相同配置的结果恢复原生PD基线。
未降低增益、增加未知惯量或缩短物理步长。设计/修复依据见
[设计](../design/htdw3532_nt.md)，问题与独立复核见 [审查记录](../review/htdw3532_nt.md)。

最终实际验收命令：

```bash
make check
task_nt_dir="$PWD/.artifacts/t035-nt"
mkdir -p "$task_nt_dir/tmp" "$task_nt_dir/gpu/tmp"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$task_nt_dir/gpu/tmp"
export WARP_CACHE_PATH="$task_nt_dir/gpu/warp"
export TORCHINDUCTOR_CACHE_DIR="$task_nt_dir/gpu/torch"
timeout 180s uv run --no-sync python -B tools/check_robot_actuators.py --device cuda:0 --num-envs 4 --steps 300
timeout 180s uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150
TMPDIR="$task_nt_dir/tmp" uv build --wheel --offline --out-dir "$task_nt_dir/dist-final"
```

- `make check` 退出码0：锁文件、Ruff、131项测试和8项子测试、模型及Git差异检查通过。
  新旧三个执行器/实体测试文件的CPU专项67项通过；最终字段诊断分支另以正式测试筛选运行4项通过。
  无刷完整PD、四象限/超速/零请求、锚点/中点与一次单位换算、较大绝对位置、kp=0、
  字段独立性/重分配、三目标延迟/局部reset和编译力矩上限均覆盖。修改Python文件的Ruff/格式检查通过。
- RTX4060 / `cuda:0`、种子1910，4环境、dt0.002：混合执行器300步通过，实际力矩±0.35 N·m，
  无刷/舵机保持误差 `0.000006/0.000566 rad`，末保持速度 `0.000111 rad/s`。
  实际Entity→MuJoCo路径在0/258/280/299/300/360rpm验证正负驱动、制动与零请求；
  64步随机延迟记录为无刷lag `[0,1,2,3]`、变化10次，舵机lag `[0,1,2]`、变化10次，
  两组配置上界仍为3，三类目标历史、每环境相位与局部reset隔离通过。
- 真实模型150步通过：双足接地，末根高 `0.166165–0.166172 m`、峰值力矩 `0.138278 N·m`、
  峰值关节速度 `0.184298 rad/s`，与原生PD对照一致；新增短中性保持检查界避免有限值掩盖数值振荡。
  所有控制映射、模型字段、限幅与reset检查通过，不将这段结果称作稳定站立或训练验收。
- 离线wheel构建通过，37个包内源码/资源文件与工作区逐字节一致；在项目内解包并切换工作目录后，
  确认从解包副本导入，默认参数加载和整机编译通过，`nq=22`、`nv=21`、`nu=15`、16网格。
  被动源模型仍为 `nu=0`、质量 `3.2947 kg`；原始资料图与参考字节一致，不依赖参考目录运行。
- 两路代理分别负责新电机目录与三份正式测试，主代理集成工具/装配/文档并独占GPU；
  第三路独立审查已复核产品、运行证据与最终文档，独立审查通过，R1/R2已关闭。
  原型与失败现场保留至审查完成后，随本轮临时产物统一清理。

没有运行完整训练、GUI或实机；来源曲线为24V资料图采样近似，制动/连续温升/峰值持续时间和本机带载供电仍待标定。
第三方Torch弃用提示保留。所有代理与检查进程结束后，已删除本轮 `.artifacts/t035-nt/`、
`.artifacts/t035-tests/`、`.artifacts/checks/run-YigExA63/` 和 `.artifacts/checks/run-7rIbxcFq/`，
清理并复扫项目字节码为零残留，排除Git/venv/第三方依赖及符号链接，保留已有修改和实验产物。
T035完成；未执行Git暂存、提交或推送，下一项仍为T001的Git基线整理，再按依赖复核T002。

### 2026 年 10 月 27 日 T036

用户指定三个参考项目（microduck、microduck_rl、duck_project），要求给出下一步方向。
两路只读子代理分别核对上游仓库与 duck_project，主代理只读检查本仓库代码、模型几何与
GPU 短时保持行为，并汇总为 T037 与后续顺序。本轮未修改机器人源码、参数、XML、依赖或测试。

核对中发现一个需要长期注意的版本问题：microduck_rl 的默认分支是 `develop`（`b02fdea`），
T021 与 README 引用的 `1e79c29` 实际在 `main` 上，落后 76 个提交。
本轮新增引用统一写 `develop` 的固定提交。

实际执行的验证命令：

```bash
cd /home/sunteng/projects/HT_microduck_lab
make check
task_t036="$PWD/.artifacts/t036-next-step"
mkdir -p "$task_t036/tmp"
TMPDIR="$task_t036/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_t036/warp" TORCHINDUCTOR_CACHE_DIR="$task_t036/torch" \
  timeout 300 uv run --no-sync python -B .artifacts/t036-next-step/home_hold.py \
  --device cuda:0 --steps 1500
TMPDIR="$task_t036/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_t036/warp" TORCHINDUCTOR_CACHE_DIR="$task_t036/torch" \
  timeout 400 uv run --no-sync python -B .artifacts/t036-next-step/push_hold.py \
  --device cuda:0 --steps 1000
TMPDIR="$task_t036/tmp" PYTHONDONTWRITEBYTECODE=1 \
  WARP_CACHE_PATH="$task_t036/warp" TORCHINDUCTOR_CACHE_DIR="$task_t036/torch" \
  timeout 400 uv run --no-sync python -B .artifacts/t036-next-step/home_hold2.py \
  --device cuda:0 --steps 1000
```

`home_hold.py`/`push_hold.py`/`home_hold2.py` 是本轮一次性探针，只用于比较 HOME 候选站姿，
不是正式工具，已在收尾时删除；结论与数值写入 T036 与 T038，不把探针当作验收入口。

结果：

- `make check` 通过：锁文件、Ruff、131 项测试、8 项子测试、模型与差异检查；质量 `3.2947 kg`。
- 几何：HOME 脚底外倾 `5.00°`，单脚接地 `1.59 cm²`（y 向仅 `2.3 mm`），
  重心到单脚边界 `0.88/0.66 mm`、到双脚联合边界 `24.55 mm`；
  `hip_roll` 内收 `0.0873 rad` 后脚底水平、单脚 `30.02 cm²`、单脚余量 `5.19/4.97 mm`、站宽 `0.1355 m`。
- GPU 保持 3 s：零位根高 `0.1655–0.1657 m`、倾角 `<1.5°`、双足全程有载；
  内收站姿根高 `0.1682 m`、倾角 `<1.3°`、左右法向力 `17.0/15.3 N`。
- GPU 速度脉冲：`0.10 m/s → 2.02°`、`0.20 m/s → 6.29°`、`0.35 m/s → 82–93°` 并跌倒。
- 原模型 `nsensor=0`，没有 IMU；官方 61 维观测的三组输入在本仓库尚无对应传感器（T037 已补 `imu` site 与 5 个传感器）。

遗留问题与下一步：站姿取向需要用户确认（原 T037，现 T038）；Git 基线（T001）仍是所有后续任务的硬前置。
本轮未运行训练、GUI 或实机，未提交 Git。

### 2026 年 10 月 27 日 T037

用户要求把 IMU 数据加进 XML，并参考官方项目。只新增传感器声明与检查，不改站姿、增益或训练代码。

实际执行的验证命令：

```bash
cd /home/sunteng/projects/HT_microduck_lab
make check
task_t037="$PWD/.artifacts/t037-imu"
mkdir -p "$task_t037/tmp"
TMPDIR="$task_t037/tmp" PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync python -B -m pytest -q \
  tests/test_robot_entity.py --basetemp="$task_t037/pytest" -o cache_dir="$task_t037/pytest-cache"
TMPDIR="$task_t037/tmp" uv run --no-sync python -B tools/check_robot.py
TMPDIR="$task_t037/tmp" PYTHONDONTWRITEBYTECODE=1 WARP_CACHE_PATH="$task_t037/warp" \
  TORCHINDUCTOR_CACHE_DIR="$task_t037/torch" timeout 400 \
  uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --steps 150
```

结果：

- `get_spec()`：`nsite=1`（`imu`）、`nsensor=5`，名称顺序 `imu_ang_vel`、`imu_lin_vel`、
  `imu_accel`、`imu_upvector`、`root_angmom`；整机工厂 `nsite=3`、`nsensor=5`、`nu=0`。
- 场景侧注册名带实体前缀：`robot/imu_ang_vel` 等，均由 `Scene._add_sensors` 自动包装，
  不需要在 `SceneCfg.sensors` 重复声明。
- 语义断言：水平 `imu_upvector=[0,0,1]`；偏航 30° 不变；俯仰 −30° 为 `[0.5,0,0.866]`；
  根角速度 `[0.3,−0.2,0.5]` 时陀螺一致；陀螺与 `root_link_ang_vel_b`、`-up` 与
  `projected_gravity_b` 在 GPU 场景中逐元素一致。
- 场景检查 `root_height=[0.166165,0.166172] m`、`peak_effort=0.138 Nm`、
  `peak_joint_speed=0.184 rad/s`，双足全程接地、无溢出与非有限值。
- `tests/test_robot_entity.py` 14 项通过；`make check` 通过（其后又跑一次，仍 133 项通过）。
- 独立只读审查（另一个代理）复核了 XML 结构、随机 200 组位姿的 `-up`/投影重力一致性、
  `subtreeangmom` 参考系与场景注册，判定模型与代码无功能缺陷；其指出的 4 处加速度计语义
  描述错误与 1 处近恒真断言已按实测修正（见上），`root_angmom` 参考系与陀螺负向对照已补记。

遗留问题：

- `imu` site 位置/姿态是占位（基座原点、单位姿态）；实机安装位姿未测量，属 T030。
- `imu_accel` 为 MuJoCo 比力语义：自由落体为 0，有支撑静止时约 `+9.81·imu_upvector`；
  观测方案仍用 `imu_upvector` 取重力方向，但不要把"支撑时读数为 0"当作前提。
- 传感器噪声、延迟、安装误差随机化未在 XML 中启用，留给任务观测配置。
- 本轮未改 `HOME_FRAME`，站姿标定顺延为 T038；未执行 Git 暂存/提交/推送。

### 2026 年 10 月 27 日 T039

用户要求 `ht_microduck_constants.py` 照官方 `microduck_constants.py` 的写法重写、不要多写，
执行器仍用本地实现；此前已指出本体 XML 不该带地形。

核对官方后确认：官方常量模块没有 IMU 名称常量、没有电机映射表、没有分节横幅；
预览用 mjlab `SceneCfg` + `Scene`，不是另设场景 XML；地形与照明由场景提供。

改动文件：

- `xmls/HT-DK_URDF.xml`：删除 `statistic`、`visual`、天空盒 `asset`、`light`、`floor`（146 → 130 行）。
- `xmls/HT-DK_scene.xml`：删除（官方不设该文件，地形由 mjlab `Scene` 提供）。
- `ht_microduck_constants.py`：按官方结构重写（252 → 189 行）；删除 `SCENE_XML_PATH`、
  `get_scene_spec()`、`IMU_SITE_NAME`、`IMU_SENSOR_NAMES`、`##` 横幅；保留本地执行器。
- `robots/ht_microduck/__init__.py`：移除 `get_scene_spec` 导出。
- `tools/check_robot.py`：本体检查改为“无平面、无灯光”；`--viewer` 改用 mjlab `Scene`。
- `tools/check_robot_scene.py`、`tests/test_robot_entity.py`：sensor 名称改由模型读取。
- `README.md`、`docs/development.md`：同步结构与文件归属。

命令与结果：

```bash
uv run --no-sync python tools/check_robot.py
# 本体检查：无平面、无灯光；地面与灯光由 mjlab 场景提供
make check
# All checks passed! / 134 passed, 1 warning, 8 subtests passed
uv run --no-sync python tools/check_robot_scene.py --device cuda:0 --steps 150
# planes=1（仅 terrain）、双足接地、IMU sensors=5
```

排查记录：GPU 场景检查一度在 `warp` 的 `tile_cholesky_inplace` LTO 处失败，
最小复现脚本同样失败，确认与改动无关 —— 原因是 `TMPDIR` 指向了不存在的目录，
创建目录后通过。后续运行 GPU 检查前应先确认 `TMPDIR` 存在。

剩余问题：`imu` 安装偏移未标定（T030）；站姿标定（T038）未做；未执行 Git 写操作。

### 2026 年 10 月 27 日 T040

根目录 README 从 360 行整理为 136 行，突出项目用途、模型检查与预览、GPU 专项检查、
机器人配置示例和文档导航。安装流程与参数细节引用已有说明，任务进度统一指向本页；
移除已不存在的 `HT_MICRODUCK_ARTICULATION` 示例，保留 12+3 分组、传感器观测边界、
未标定参数与训练入口尚未实现的说明。GPU 示例补齐项目内临时目录和缓存设置。
仅修改 `README.md` 与本页，未改变代码、模型、依赖或测试。

实际验证：

- `make check` 退出码 0：锁文件、Ruff、134 项测试与 8 项子测试、模型编译与差异空白检查通过。
  模型仍为 15 关节、16 网格，`nq=22`、`nv=21`、`nu=0`、质量 `3.2947 kg`。
  保留第三方 Torch 的既有弃用提示。
- 使用 `uv run --no-sync python -B -` 执行内存中的文档核查：12 个本地链接及锚点通过，
  Bash 示例通过 `bash -n`，Python 示例实际创建 4 环境的 `SceneCfg` 配置并核对平地与两组执行器，
  没有创建仿真或启动 GPU 动态检查。专项临时目录为 `.artifacts/t040-readme/run-Pnbu2FVf/`。
- 使用 `python3 -B -` 单独核对当前任务表，41 个编号唯一；完成时没有进行中任务。
  自审确认命令参数、默认规模、目录和配置符号与代码一致；未新增测试，未运行 GUI、训练或实机。

所有检查进程结束后清理本轮专项目录与 `.artifacts/checks/run-9OoUDOQA/`，
清理并复扫项目字节码，排除 Git、虚拟环境、第三方依赖及符号链接，保留已有实验产物。
T040 完成，无本次未解决项；后续仍按 T001 → T002 复核 → T038 → T022 的依赖推进，
M0/M1 阶段状态不变。未执行 Git 暂存、提交或推送。

### 2026 年 10 月 27 日 T041

对照用户指定的三个参考项目复核下一步。两路子代理分别只读分析
`pollen-robotics/microduck` + `pollen-robotics/microduck_rl`（固定 `develop@b02fdea`）与
`/home/sunteng/projects/duck_project`；主代理核对本机代码、用 GitHub API 确认默认分支，
并在项目内写一次性探针做可行性实测。未修改机器人源码、参数、XML、依赖或测试，未提交 Git。

实际执行的命令（临时与缓存目录均在本项目内，Python 全部禁用字节码）：

```bash
cd /home/sunteng/projects/HT_microduck_lab
make check
task_t041="$PWD/.artifacts/t040-next-step"
mkdir -p "$task_t041/tmp" "$task_t041/gpu/tmp"
export TMPDIR="$task_t041/gpu/tmp" PYTHONDONTWRITEBYTECODE=1
export WARP_CACHE_PATH="$task_t041/gpu/warp" TORCHINDUCTOR_CACHE_DIR="$task_t041/gpu/torch"
timeout 400 uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0 --num-envs 4 --steps 150
timeout 500 uv run --no-sync python -B .artifacts/t040-next-step/probe_velocity.py cuda:0
timeout 500 uv run --no-sync python -B .artifacts/t040-next-step/probe_throughput.py cuda:0 4096 60
timeout 1500 uv run --no-sync python -B .artifacts/t040-next-step/probe_home_final.py cuda:0
```

结果：

- `make check` 退出码 0：锁文件、Ruff、134 项测试与 8 项子测试、模型与 Git 差异空白检查通过；
  被动模型 `nq=22`、`nv=21`、`nu=0`、15 关节、16 网格、质量 `3.2947 kg`。
- 整机场景检查退出码 0：`cuda:0`、4 环境、150 步、`dt=0.002 s`，末根高
  `0.166165–0.166172 m`、峰值力矩 `0.138278 N·m`、峰值关节速度 `0.184298 rad/s`，
  `planes=1`、双脚接地、IMU 传感器 5 个、局部 reset 与目标映射通过。
- 本机已具备把 mjlab 1.6 平地速度模板套到本机器人的条件，但需显式改六处
  （接触传感器、`pose` 的 std 字典、地形扫描、动作关节子集、两个 startup 事件、DR asset 选择器）；
  改完后 `obs[actor]=(2,52)`、`obs[critic]=(2,64)`、动作 `(2,10)`，20 步零动作奖励有限。
  探针只用于判断可行性，不作为任务环境已实现的证据。
- 吞吐：256 / 1024 / 4096 环境分别为 `1.47e4` / `1.29e4` / `4.20e4` env-step/s。
- HOME 保持（固定初态、无推扰、50 Hz、32 环境 × 3 种子 × 5 s）：
  全零站姿 `kp=10` 跌 7/96、`kp=20` 跌 2/96；水平站姿（`r=+0.0873`、`l=−0.0873`）
  分别为 5/96、1/96；下调根高无改善。
- 跌倒来源定位：保留全部 DR、仅去掉 `push_robot`，`worst_tilt` 由 70.30° 降到 19.25°、
  跌倒 0/8；单独去掉 `base_com`/`encoder_bias`/`foot_friction` 都无效。
- 脚底平面：CPU 顶点拟合确认镜像内收 `+0.0873/−0.0873` 才使两侧同时水平（0.11°/0.11°），
  同号组合会得到 0.11°/7.65°。
- 控制周期：同为 50 Hz，`dt=0.005`+dec4 跌倒 3–4/4，`dt=0.002`+dec10 为 0–1/4，
  说明上游 50 Hz 的结论依赖 2 ms 物理步长。

据此关闭 T001（Git 基线已由 `21589d7` 满足四条验收条件）与 T002（T016 证据 + 本轮场景检查），
并修正 T038 的前提：站姿必须与默认增益一起定，且符号为镜像内收。
T041 未运行训练、GUI 或实机。所有探针与子代理结束后删除 `.artifacts/t040-next-step/`
及本轮 `.artifacts/checks/run-*`，清理并复扫项目字节码，排除 Git、虚拟环境、
第三方依赖与符号链接，保留已有实验产物。T041 完成，无遗留阻塞；
下一项为 T038，随后 T022 → T023。M0/M1 阶段状态不变，未执行 Git 暂存、提交或推送。

### 2026 年 10 月 27 日 T042

用户要求核对三处模型是否对碰撞体（collision geom）做了简化：本机
`src/ht_microduck/robots/ht_microduck/xmls/HT-DK_URDF.xml`、官方
`pollen-robotics/microduck_rl`（固定 `develop@b02fdea`）以及 `/home/sunteng/projects/duck_project`。
只读核对 XML/URDF/配置，并在项目内一次性探针里编译三份模型量测碰撞凸包规模；
未修改任何模型、源码、参数或测试，未提交 Git。

实际执行的命令（临时与缓存目录均在本项目内，Python 全部禁用字节码）：

```bash
cd /home/sunteng/projects/HT_microduck_lab
export UV_CACHE_DIR="$PWD/.artifacts/manual-checks/uv-cache"
export TMPDIR="$PWD/.artifacts/manual-checks/tmp"
mkdir -p "$UV_CACHE_DIR" "$TMPDIR"
make check
# 探针：编译三份模型，读 mjModel.mesh_graph 取 MuJoCo 实际凸包顶点/面数，
# 在随机关节姿态下计时 mj_collision 的窄相开销；同时解析官方 config_mjcf_*.json
```

结果：

- **本机：没有做碰撞体简化。** 9 个碰撞 geom（2 个 base box + 7 个 mesh）直接引用原始高精度
  STL，XML 未设置 `maxhullvert`，因此 MuJoCo 用全部顶点构建碰撞凸包。
  实测单网格原始顶点 906–55348，凸包 124–1113 顶点；7 个碰撞 mesh 合计
  凸包 2475 顶点 / 4918 面。碰撞凸包形状与 CAD 差异明显：`head_roll_link` 的
  1113 顶点凸包会把头部凹结构填实，`l/r_ankle_link` 的 300+ 顶点凸包把整个脚踝外壳
  （沿 z 向 81 mm）当作碰撞体，而不是脚底平面。凸包是 MuJoCo 对 mesh geom 的固有语义，
  不是本机额外做的简化，但本机确实缺少“抽面/参数化代替原网格”这一层处理。
- **官方 microduck：做了网格抽面简化，但没有多凸块凸分解。**
  `config_mjcf_{walk,groundcontact,allcollisions}.json` 均为
  `"simplify_stls": true, "max_stl_size": 1.0`，即 onshape-to-robot 用 pymeshlab 二次误差
  边坍缩把每个 STL 抽到 ≤1 MB；旁证是 `assets/*.stl` 尺寸都压在 1 MB 阈值下
  （`foot_left.stl` 996,184 B、`sole_left.stl` 789,484 B、`leg.stl` 738,884 B）。
  没有独立 collision 网格（无 `collision/` 目录、无 `*_collision.STL`、无 `.obj` 凸块），
  碰撞 geom 与可视 geom 引用同一份已简化 STL，也未设置 `maxhullvert`。
  每个 part 仍是一个 mesh geom，没有拆成多个凸块，也没有 box/cylinder/sphere 原语。
  官方真正做的是“抽面 + 按任务的碰撞 part 白名单”：`robot_walk.xml` 只有
  2 个 `class="collision"`（左/右脚底 `sole_left`/`sole_right`）和 3 个
  `class="self_collision_only"`（`leg`/`leg_2`/`power_support`，`contype=conaffinity=2`），
  头壳、躯干壳、舵机、PCB 全部无碰撞体；`robot_allcollisions.xml` 则有 69 个碰撞 geom。
  实测官方脚底碰撞网格 `sole_left` 抽面后仍有 7896 顶点、凸包 4964 顶点，是本机
  7 个碰撞 mesh 凸包总量（2475）的两倍，说明“抽面”并不等于“小凸包”。
- **duck_project：做了凸分解，且按 profile 分级。** `src/htdk/collision.py` 定义三代 profile：
  `urdf_partial_v1`（原始、部分 link 无碰撞）、`convex_full_links_v2`（补齐 7 个缺碰撞的
  link 并加脚部 shell）、`decomposed_links_v3`（CoACD 凸分解）。
  `src/assets/collision_parts_v3/manifest.json` 记录生成器 CoACD 1.0.14、
  `max_convex_hull=12`、`max_ch_vertex=64`、`threshold=0.001`，只覆盖 5 个 link
  （l/r_hip_roll、l/r_calf 各 12 块启用，`head_roll_link` 12 块因“粗分解被否决”而
  `enabled=false`，保留原保守凸包）。v2/v3 都把 16 个 mesh 的 `maxhullvert` 显式设为 48，
  脚部用 box（`size 0.04 0.0262 0.003`）代替脚踝网格。实测 v2：19 个碰撞 geom、
  凸包 720 顶点 / 1380 面；v3：63 个碰撞 geom、凸包 2832 顶点 / 5428 面。
  即 v3 用更多凸块换取更贴合的凹形，代价是几何数翻三倍。
- 窄相计时（随机关节姿态，200 次平均）：本机现状 42.7 µs、本机加 `maxhullvert=48` 为
  36.4 µs、duck v2 为 56.1 µs、duck v3 为 69.1 µs（配置数量不同，仅作量级参考）。
  编译期 `npoly`：本机现状 3235、加 `maxhullvert=48` 为 604。
- 本机 200 组随机关节姿态下没有出现父子（相邻）link 自碰撞，但如果后续给
  `l/r_calf_link`、`l/r_hip_yaw_link` 等 link 补碰撞体，需要同时补 duck_project 那样的
  15 条相邻 link `exclude`（本机 XML 当前 0 条），否则相邻件会持续自碰撞并触发终止。
- `make check` 退出码 0：`134 passed, 1 warning, 8 subtests passed`，13 项模型检查通过
  （`nq=22, nv=21, nu=0`、15 关节、16 网格、3.2947 kg）。

结论与后续：

三处差异是**三个不同层次**，不能笼统说“做了/没做”：
本机=原始网格+无限顶点凸包；官方=抽面 + 任务白名单 + 单一网格凸包；
duck_project=显式 `maxhullvert=48` + CoACD 多凸块 + box 脚底。
本机若要对齐，最小改动是给碰撞 mesh 加 `maxhullvert`（`make check` 与凸包顶点数可验证），
更贴近 duck_project 的做法需要 CoACD 资产与相邻 link 排除表，属于新增任务范围，本轮不做。

本轮未改模型、未训练、未开 GUI；探针文件已删除，`.artifacts/t042-stance/` 属 T038 的既有
实验产物，保留不动。T042 完成，无遗留阻塞；未执行 Git 暂存、提交或推送。

### 2026 年 10 月 27 日 T043

> **已被 T047 取代。** 本节的 `rsl_rl/_fallback.py` 机制、以及「本目录仅作只读参考、不直接作为
> 依赖」的定位都已撤销：T047 把 `rsl_rl/` 补成 rsl-rl-lib 5.4.2 的完整副本、删除 `_fallback.py`，
> 它现在是训练/回放/导出实际运行的代码。保留本节作为当时的决策与验证记录。

用户要求把官方 microduck 训练算法中的 **PPO 与网络设计** 拉取过来，明确不要整个训练框架；
随后要求目录名直接叫 `rsl_rl`，不要 `vendor/` 这类前缀。

**关键事实：官方仓库没有 PPO 与网络的实现。** 所以源码不在
`pollen-robotics/microduck_rl` 里，而在它依赖的 `rsl-rl-lib` 里：

- 官方 `train_cli.py` 仅 1456 B，把 `main()` 转发给 `mjlab.scripts.train`；
- PPO、ActorCritic 网络、RolloutStorage 全部来自 `rsl-rl-lib`，经 mjlab 的
  `RslRlOnPolicyRunnerCfg` / `RslRlModelCfg` / `RslRlPpoAlgorithmCfg` 装配；
- 官方自己写的唯一算法件是 `tasks/symmetry.py`（算法 cfg 加字段 + 镜像函数）。

本机 `.venv` 装的是 `rsl-rl-lib==5.4.2`（`mjlab==1.6.0` 的依赖），与官方
`mjlab==1.3.0` 所用 `rsl_rl` 版本一致，故直接从本地抽取，无需联网。

**范围两次修正**：第一次把官方 `microduck_rl` 的 41 个框架文件（1.2 MB）整包拉进
`vendor/microduck_rl/`，范围过宽，已删除；第二次收敛为算法闭包放到
`vendor/rsl_rl_algorithm/`，用户要求改名；最终落在项目根 **`rsl_rl/`**，
`vendor/` 目录已整体删除。

落点：`rsl_rl/`，27 个文件 / 约 3900 行 / 256 KB，BSD-3-Clause（含 `LICENSE`），
保留上游目录结构。核心：

| 文件 | 行数 | 作用 |
|---|---|---|
| `algorithms/ppo.py` | 488 | PPO 主逻辑：GAE、clipped surrogate、value loss、entropy、adaptive KL、mini-batch |
| `models/mlp_model.py` | 256 | ActorCritic 主体：obs 归一化 → MLP → 分布 / 标量 |
| `storage/rollout_storage.py` | 357 | Rollout 存储、mini-batch 生成、GAE 回填、recurrent 序列切分 |
| `modules/distribution.py` | 464 | Gaussian / Beta / HeteroscedasticGaussian |
| `modules/mlp.py` | 95 | MLP 骨架与激活堆叠 |
| `modules/normalization.py` | 131 | EmpiricalNormalization 及折扣变体 |
| `extensions/symmetry.py` | 137 | 左右对称增强与 mirror loss |
| `extensions/rnd.py` | 242 | 随机网络蒸馏 |
| `env/vec_env.py` | 93 | VecEnv 抽象（PPO 的接口依赖，非环境实现） |
| `utils/utils.py` | 389 | 激活/优化器/obs 分组解析、轨迹 padding、torch.compile 包装 |

另含 `models/{cnn,rnn}_model.py`、`modules/{cnn,rnn}.py`、三个日志 writer 与各目录 `__init__.py`。
说明写在 `rsl_rl/README.md`。上游 `algorithms/__init__.py` 原本还导出 `distillation`；
蒸馏不在参考集内，未复制该文件。

**目录同名遮蔽问题（本轮新增处理）**：`rsl_rl/` 位于项目根，Python 把当前目录排在
`sys.path` 最前，会遮蔽已安装的 `rsl_rl` wheel；而 `mjlab.rl` 需要
`from rsl_rl.runners import OnPolicyRunner`，本镜像不含 `runners/`，实测直接报
`ModuleNotFoundError: No module named 'rsl_rl.runners'`。

处理：新增 `rsl_rl/_fallback.py`，把已安装包的对应目录追加到各包 `__path__` 之后，
本目录文件优先、缺失的从 wheel 补；并让 `algorithms/__init__.py` 在可用时再导出
`Distillation`（wheel 的 `runners` 依赖它）。实现细节：
`_installed_root()` 不能用 `startswith(项目路径)` 排除，因为 `.venv` 就在项目内，
会把已安装包一并排除；改为只跳过本目录自身，并优先选择含 `runners/` 的候选。

验证结果：

- `make check` 通过（退出码 0）：`134 passed, 1 warning, 8 subtests passed`，
  模型编译与关节映射检查通过。
- `import mjlab.rl` 与 `mjlab.rl.runner.MjlabOnPolicyRunner` 均可正常导入
  （遮蔽问题已解除）。
- 本地 `PPO` / `MLPModel` / `RolloutStorage` / `GaussianDistribution` /
  `EmpiricalNormalization` 全部可导入，且 `PPO.__file__` 确认指向 `rsl_rl/algorithms/ppo.py`，
  即本目录优先而非 wheel。
- 端到端冒烟：8 环境 / 12 维观测 / 4 维动作的合成 `VecEnv`，按真实 API
  `PPO.construct_algorithm(obs, env, cfg, device)` → `act` → `process_env_step` →
  `compute_returns` → `update()` 跑 8 次迭代，entropy 单调下降 5.670 → 5.604，
  证明策略在真实更新而非死代码。

实测 API 细节（与直觉不同，供后续实现参考）：`update()` 无参且返回
`dict[str, float]`；`compute_returns(obs)` 无返回值；构造必须走 `construct_algorithm`；
cfg 需含 `multi_gpu`、`obs_groups`、`num_steps_per_env` 等键。

`rsl_rl/` 已在 `pyproject.toml` 的 `[tool.ruff]` 中以 `extend-exclude` + `force-exclude`
排除（`make lint` 本来就只检查 `src tools tests`，此举显式固化边界）；已验证
`src tools tests` 仍正常检查、`rsl_rl/` 被跳过。

未解决项与边界：

- 官方 14 关节 / XL330，本机 15 关节 / 12 无刷 + 3 舵机；网络输入维度与对称性索引表
  需按本机观测维度重定，不能照抄。
- 官方 `mjlab==1.3.0` 与本机 `1.6.0` 的 `RslRl*` 配置接口未做行为等价性验证。
- 目录同名遮蔽虽已用 `_fallback.py` 处理，但属项目根放第三方同名包的固有风险；
  后续若在项目内引入 `rsl_rl` 其他子模块，需确认优先级仍符合预期。
- 按项目约定，生产实现写在 `src/ht_microduck/`，本目录仅作只读参考，不直接作为依赖。

本轮未改模型、未训练、未开 GUI、未安装依赖。`rsl_rl/` 与 `pyproject.toml` 的改动
待用户确认后再决定是否提交；未执行 Git 暂存、提交或推送。

### 2026 年 10 月 27 日 T038

完成 HOME 站姿标定，`HOME_FRAME` 由全零改为脚底水平的蹲姿。

改动文件：

- `src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py`：新增 `HOME_JOINT_POS`
  （`hip_roll ±0.0873` 镜像、`hip_pitch 0.85`、`calf −1.20`、`ankle 0.35` 双腿同号），
  `HOME_FRAME.pos` 由 `0.171` 改为 `0.1534`，并记录否定用户两个给定角度的实测依据。
- `tests/test_robot_entity.py`：三处 HOME 断言同步；脚底余隙区间由 `3.8–3.9 mm`
  改为 `−1.5–0 mm`（蹲姿的最低点是脚跟圆弧，不是支撑面）；触地下压量由 `5 mm` 改为 `8 mm`。
- `tools/check_robot_scene.py`：根高守卫由绝对 `0.15 m` 改为 `0.9 × HOME`，
  否则更低的蹲姿会让守卫恒通过或误报。
- `README.md`：HOME 段改为蹲姿说明，并写清两个用户给定角度不能采用的原因。

验证命令与结果：

- `make check`：`All checks passed!`、`134 passed, 1 warning, 8 subtests passed`。
- `uv run --no-sync python -B tools/check_robot_scene.py --device cuda:0`：
  `root_height=[0.149827, 0.149834] m`、`peak_effort=0.532 Nm`、`peak_joint_speed=0.841 rad/s`，双足接地。
- 5 s 零动作保持 8 种子 × 16 环境：`falls=0/128`，末端倾角 7.8–9.4°。
- 协调速度脉冲 `0.10–0.26 rad`：新 HOME 全 `0/24`，旧零位在 `0.26 rad` 为 `2/24`。

用户提出的 `hip_roll 0.38` / `hip_pitch 1.57` 未采用，理由已写入常量和 README：
`1.57` 是关节限位且使脚底法线倾角达 88°，48/48 全倒；`0.38` 把脚底翘起约 17°，
横向余量从 92 mm 降到 57 mm，平地只需镜像内收 `0.0873`。

本轮还纠正了两个方法论错误，后续探针必须沿用：
每个候选姿势要按自身几何高度复位，不能统一从 `0.171 m` 放下（否则把落地冲击记成不稳）；
脚底倾角要在真正水平的姿态标定一次法线再随踝链旋转，不能对带曲面的整脚网格直接做平面拟合。

未解决项：

- 默认增益未改（`kp=10`/`kd=0.4`），增益与 HOME 的联合整定未做，归 T023/M1。
- 接触面积未直接测量：mjlab 1.6 的 `sim.data.contact` 无 `geom1`/`geom2`，设备侧无法按 geom 归并；
  本轮用 CPU 顶点几何替代并注明不等价。
- 实机增益、限幅、延迟与供电仍是仿真假设，归 T030。

下一项为 T022（固定首版任务控制与观测契约），随后 T023（最小平地速度任务）。
本轮未训练、未开 GUI、未安装依赖；未执行 Git 暂存、提交或推送，`vendor/` 与 `pyproject.toml`
的既有改动保持原样。

### 2026 年 10 月 27 日 VS Code Codex 面板无法打开修复

现象：VS Code 内 Codex 侧栏显示 `Codex could not start its user interface.`，
扩展日志 `~/.config/Code/logs/<会话>/window<N>/exthost/openai.chatgpt/Codex.log` 记录
`Webview renderer did not become ready ... reason=renderer_ready_timeout
receivedWebviewMessage=false timeoutMs=30000`，且没有任何 `React root render` 行。

定位结论（本地已验证）：两个独立缺陷叠加，只修任一个都不够。

1. GPU 进程崩溃是主因。`~/.config/Code/Crashpad/` 的 dump 记录
   `FATAL:content/browser/gpu/gpu_data_manager_impl_private.cc:417] GPU process isn't usable. Goodbye.`，
   同会话 `main.log` 出现 `CodeWindow: detected unresponsive` 与 `Extension host ... exited`。
   该机 Xorg 只有 `swrast`（`AIGLX: Screen 0 is not DRI2 capable`、
   `Initialized DRISWRAST GL provider`），Electron 拿不到可用的 GL 后端，GPU 进程反复失败，
   Codex 侧栏的 webview 渲染进程因此根本没被创建——表现为日志里连 `React root render` 都没有。
   同期 Claude Code 的 webview 在同一 VS Code 里正常收发消息，说明 webview 基础设施本身没坏。
2. 30 s 超时预算过紧。扩展 `out/extension.js` 把等待 webview 上报 `renderer_ready` 的定时器
   硬编码为 30 s（`setTimeout(..., 3e4)`），超时后替换 `webview.html` 并弹错误。
   实测 `[startup][renderer] app routes mounted after` 为
   `15584/19471/32636/38603/42988/50090 ms`，正常挂载也常超过 30 s。
   30 s 无设置项可调，也无法靠重装规避：市场最新 linux-x64 为 `26.51021.22027`，
   本机已装 `26.1021.22027`，市场无更新版本。

修改：
- `~/.vscode/argv.json`：打开 `"disable-hardware-acceleration": true`（原为注释），
  让 Electron 走软件渲染，绕开本机不可用的 GL；备份为 `argv.json.dsh-backup`。
- `~/.vscode/extensions/openai.chatgpt-<版本>-linux-x64/out/extension.js`：把该定时器
  由 `3e4` 改为 `18e4`（30 s → 180 s），原文备份为 `extension.js.dsh-backup`。
  `~/.local/share/codex-webview-fix/reapply.sh` 保存可重复执行的补丁脚本（幂等，
  带 `node --check` 校验），扩展升级后可重跑。

验证：
- 只打超时补丁时仍打不开：新会话 `165600` 的三个窗口都没有任何 `React root render` 行，
  证实超时预算不是充分条件。
- 补上软件渲染并完整重启后，真实会话 `20261027T170157/window1` 出现
  `React root render requested windowType=extension`、`authenticatedAccountPresent=true`、
  `app routes mounted after 50090ms`、`[git-repo-watcher] Starting`、`result=succeeded`，
  `detected unresponsive` 为 0，17:00 后无新 crash dump。
  该 50090 ms 挂载时间也说明 30 s 预算必然失败，两项修改互补。
- 隔离实例加 `--disable-gpu` 复核：`app routes mounted after 15584ms`。
- `node --check extension.js` 通过，`argv.json` 去注释后仍是合法 JSON；不改动仓库代码，
  未运行 `make check`。

遗留：
- 两处补丁都在用户级配置/扩展目录，不随仓库版本管理；扩展更新后需再次执行
  `bash ~/.local/share/codex-webview-fix/reapply.sh`，`argv.json` 一般仍保留。
- 软件渲染只是绕开 GPU 缺陷，没修好显卡驱动本身：该机 `nvidia-smi` 可用但 Xorg 未绑定
  NVIDIA（`/dev/dri` 存在却仍走 `fbdev`/`swrast`）。若要恢复硬件加速，需另查 Xorg 驱动加载。
- 本次为临时修复，`make check` 与仓库产物均未变更；未执行 Git 暂存、提交或推送。

2026 年 10 月 30 日复发与补充结论：上述两处补丁仍在（`--use-gl=disabled` 已生效、
超时已是 180 s），但面板再次打不开，且日志中没有 `renderer_ready_timeout`，
连 `React root render` 都没有。原因是第三个独立故障：

- `~/.vscode/extensions/` 中 `ms-vscode-remote.remote-ssh-0.128.0` 与
  `github.remotehub-0.65.0` 与 Code 1.124.2 不兼容（分别要求 `^1.133.0`、`^1.141.0`），
  而 `extensions.json` 里同时保留了兼容的旧版（`0.124.0`、`0.64.0`）。
  自动更新装上新版后加载失败，`main.log` 记录扩展宿主两次
  `Extension host with pid ... exited`，Codex 的 webview 尚未渲染完即被连带终止。
- 处理：在 `settings.json` 关闭 `extensions.autoUpdate` 与 `extensions.autoCheckUpdates`；
  两个不兼容版本目录被 VS Code 清理后，`extensions.json` 残留 2 条指向已删目录的条目，
  一并删除（备份 `extensions.json.dsh-backup2`）。
- 验证：重启后会话 `20261030T154502` 中 window1 `app routes mounted after 54110ms`、
  window4 `after 23366ms`，扩展宿主启动 1 次不再反复重启，15:48 后无新的不兼容报错。
  对照：同一补丁下隔离实例 13–42 s 即可渲染，说明补丁本身有效，故障出在真实配置的扩展注册表。

后续同类问题的排查顺序：先查 `main.log` 有无 `Extension host ... exited` 与
`detected unresponsive`，再查 `extensions.json` 是否有指向已删目录或版本不兼容的条目，
最后才怀疑扩展自身。这些改动均属用户级配置，不随仓库管理。

2026 年 10 月 31 日再次复发：前三处修复（软件渲染、180 s 超时、清理扩展注册表）都仍在，
但面板又打不开。这次 `extensions.json` 已无失效条目，`main.log` 显示窗口
`CodeWindow: detected unresponsive` 卡住约 26 s，并伴随 3 次
`Extension host with pid ... exited`，Codex 扩展在 10:51:08 随宿主一起被终止。

卡顿样本指向 `manasxx.background-cover-3.7.2`：`unresponsive samples` 中出现
`.../out/vs/workbench/js-background-cover.js?t=...`，与 xterm 同时占用主线程。
该扩展在 `settings.json` 中 `background.enabled: true`，会在主线程持续重绘背景。

处理：`settings.json` 设 `background.enabled: false`（备份 `settings.json.dsh-backup2`）。
验证：重启后会话 `20261031T105609` 中 window1 `app routes mounted after 53560ms`，
`detected unresponsive` 为 0，扩展宿主只启动 1 次。

结论补充：本机是"多个独立故障叠加"的典型场景，每修好一层都会露出下一层，
排查必须同时看三处——`main.log` 的未响应/宿主重启、`unresponsive samples` 里的具体栈、
以及 `exthost/openai.chatgpt/Codex.log` 是否出现过 `React root render`。
只看到"没有超时日志"就下结论会漏掉真实原因；没有 `React root render` 说明
webview 从未被创建，应优先查宿主与主线程，而不是继续调超时预算。

2026 年 10 月 31 日第二轮（按用户要求彻底删除背景扩展）：

- 背景扩展 `manasxx.background-cover-3.7.2` 不只是普通插件，它会改写 VS Code 安装目录的
  `.../out/vs/workbench/workbench.desktop.main.js`，注入一段
  `/*ext-backgroundCover-start*/` … `/*ext-backgroundCover-end*/` 引导代码，
  用于加载 `js-background-cover.js` 与 182 个 `css-background-cover.*.css`。
  只删扩展目录而不清注入，启动时仍会去找已删文件。
- 实际清理范围：扩展目录、`CachedExtensionVSIXs/manasxx.background-cover-3.7.2`、
  `.obsolete` 条目、`workbench.desktop.main.js` 中 6196 字符注入块（备份
  `workbench.desktop.main.js.dsh-backup`）、182 个 css 与 1 个 js 缓存、
  `settings.json` 的 `background.enabled`、`state.vscdb` 中 4 条相关记录
  （备份 `state.vscdb.dsh-backup`，188→184 行，`pragma integrity_check` 为 ok）。
- 清理后仍未渲染，继续定位到真正的阻塞点：`settings.json` 里
  `http.proxySupport` 默认为 `override`，VS Code 走系统代理
  （GNOME `manual`，`127.0.0.1:7897`）。当时代理节点已失效，HTTPS 全部 TLS 失败
  （`SSL routines::unexpected eof while reading`，`https://www.google.com` 经代理也是 000，
  `chatgpt.com` 被解析到 Facebook 的 IP），主线程在卡住的请求上出现
  `CodeWindow: detected unresponsive`，webview 因此始终没有创建。
- 处理：`settings.json` 设 `http.proxySupport: "off"`（备份 `settings.json.dsh-backup3`）。
  验证：干净重启后会话 `20261031T120313` 中 window1
  `app routes mounted after 53330ms`，`detected unresponsive` 为 0。
- 隔离对照（两次都用同一份 `workbench.desktop.main.js` 与同一扩展目录）：
  带 `http.proxySupport:"off"` 的隔离实例 53996 ms 正常挂载，
  不带该项的隔离实例卡在 `detected unresponsive` 且无 `React root render`。
  据此确认 workbench 注入的移除本身没有破坏 VS Code。

注意事项：`http.proxySupport: "off"` 会让 VS Code 自身及扩展不再使用系统代理，
若之后依赖代理访问外网，需要重新打开该项或改用能正常工作的代理节点。
该机当前代理节点失效是独立问题，本次未修复，仅绕开。

2026 年 11 月 1 日复发：这次的直接原因是代理进程没起来，与 Codex 和扩展都无关。

- 现象：Codex 面板又打不开，`main.log` 有 `detected unresponsive` 与 2 次
  `Extension host with pid ... exited`，各窗口 `Codex.log` 均无 `React root render`。
- 定位：`ss -tln` 显示 7897/7890/9090 全部无监听，`gsettings get
  org.gnome.system.proxy mode` 已是 `'none'`，只有 `clash-verge-service` 守护进程在跑，
  图形端 `clash-verge` 未启动。国内站点（`https://www.baidu.com`）200，
  `api.github.com` 直连与经代理均 000，即外网出口整体不可用。
  渲染层报 `[DefaultAccount] request: error TypeError: Failed to fetch
  https://api.github.com/copilot_int...` 与连串"出现未知错误"，都是外网不通的派生现象。
- 处理：启动 `/usr/bin/clash-verge`（7897 恢复监听，`api.github.com` 200、
  `chatgpt.com/backend-api/me` 401 为正常的未登录响应），
  把 `http.proxySupport` 由上一轮临时值 `"off"` 改回 `"override"`
  （备份 `settings.json.dsh-backup4`），并把 GNOME 系统代理恢复为
  `manual` + `127.0.0.1:7897`（上一轮排查时被置成了 `none`）。
- 验证：会话 `20261101T115425` 中 window1 `app routes mounted after 9484ms`，
  同时出现 `result=succeeded` 与 `authenticatedAccountPresent=true`，
  `detected unresponsive` 为 0。

结论：前四层（软件渲染、180 s 超时、扩展注册表、背景扩展及其 workbench 注入）
属本地配置缺陷，已修净；但"外网出口是否可用"是独立变量，代理进程未启动或
系统代理被置为 `none` 时，Codex 同样表现为面板打不开且无 `React root render`。
以后遇到同一症状，先花十秒做这两项检查再动配置：
`ss -tln | grep 789` 与 `gsettings get org.gnome.system.proxy mode`。

### 2026 年 10 月 27 日 T022–T026 任务环境与本地训练链路

按用户要求"参考官方的项目做任务环境（任务/行动/奖励），无 PPO、网络、存储、Runner"落地首版：
先冻结契约，再做平地速度环境，最后接上本地的网络、Storage、PPO 与 Runner。
参考 pollen-robotics/microduck_rl 的 `Mjlab-Velocity-Flat-MicroDuck`
（`develop@b02fdea`，Apache-2.0 代码 / 网格为 CC BY-NC-SA 4.0），
用 `curl` 读取固定提交的原始文件与 PyPI 上 `mjlab==1.3.0` 的基类配置；
上游与本机 `mjlab==1.6.0` 的差异逐条核对后再改，不整体搬运。

新增文件：

- `src/ht_microduck/tasks/common/contract.py`：冻结的时序、动作子集/顺序/缩放、
  actor 39 维与 critic 42 维观测，导入时 `validate_contract()` 强制 `base_lin_vel` 只在 critic。
- `src/ht_microduck/tasks/common/mdp.py`：速度跟踪、腾空时间、足端间隙/滑移、
  机体触地、自碰撞、`upright`、`state_is_nan`。
- `src/ht_microduck/tasks/flat_velocity/`：`make_flat_velocity_env_cfg()`，11 项奖励、4 项终止、
  7 个事件（含必需的 `htdw3532_init`/`bam_init`）。
- `src/ht_microduck/algorithms/`：`networks.py`、`storage.py`、`ppo.py`、`runner.py`。
- `src/ht_microduck/cli/train.py` 与 `pyproject.toml` 的 `[project.scripts]`（`duck-train`）。
- `tools/check_task_contract.py`、`tools/check_velocity_env.py`。
- `tests/test_networks.py`（17）、`tests/test_ppo.py`（12）、`tests/test_runner.py`（9）。

实测结果：

```
uv run --no-sync python -B tools/check_task_contract.py --device cuda:0
  Contract check passed: device=cuda:0, envs=4, actor=39D, action=10D, control=50Hz.

uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0
  Velocity env check passed: device=cuda:0, envs=16, steps=300, dt=0.02s.

uv run --no-sync duck-train --num-envs 16 --iterations 2 --seed 0 --device cpu
  iter 1 reward -0.063 value_loss 0.1169 kl +0.39855 lr 6.67e-04
  iter 2 reward -0.067 value_loss 0.0544 kl +0.10128 lr 4.44e-04
  恢复同一 checkpoint 后 iter 5/6 继续，迭代号、优化器与归一化统计均接上。

make check
  All checks passed!  172 passed, 1 warning, 8 subtests passed
```

本轮修掉的真实缺陷（都由检查或测试发现，不是推测）：

1. `GaussianDistribution` 的 `log_std` 形状为 `(A,)`，与 `(N,A)` 均值广播后
   `clamp` 保留参数形状，导致 `entropy()`/`log_prob()` 的 `sum(-1)` 连 batch 维一起压掉。
   已在构造时 `expand_as(mean)`。
2. PPO 缺少小批量优势归一化，首个 iteration `approx_kl=2.99`、`clip_fraction=0.90`；
   加入归一化并对零方差批次加保护后降到 `1.02` 且逐轮收敛。
3. Runner 从未调用 `RunningMeanStd.update()`，归一化器一直停在均值 0/方差 1；
   现在每个 rollout 后更新，统计随 checkpoint 持久化（`count=768` 可复查）。
4. 契约检查里"只改线速度、断言 actor 不变"不成立（重推物理会扰动其它项），
   改为结构断言；动作脉冲判据从"位置"改为"指令目标"，并把编码器偏置计入期望值。

遗留与边界：

- 零动作保持 2/16 终止是 DR 的预期代价，T038 的 0/128 是无 DR 的干净保持；
  6×16 重复累计 1/96，检查据此改为"不超过 1/4"并把实测值打印出来。
- 三次 GPU 短跑撞上并发进程常驻 7.1/8.0 GiB 显存，训练验证最终在 CPU 上完成；
  GPU 上只跑通了两个环境检查工具，GPU 训练证据留到 T027 补。
- `feet_clearance`/`foot_slip` 的足端世界系高度与速度口径需在导出前与 `duck_project` 对齐一次。
- 短跑只证明链路通与数值有限，**不证明学会行走**；奖励均值仍为负、episode 长度 20–30 步。
- 本轮未执行 Git 暂存、提交或推送；`rsl_rl/` 与 `pyproject.toml` 的并发改动保持原样。

### 2026 年 10 月 27 日 T027 训练输出与回放对齐官方

> **部分已被 T046/T047 取代。** 本节"算法仍是本仓库自己的 PPO/Runner"的前提不再成立：
> T046 改为复用官方 `mjlab.scripts.train`/`play`，T047 删除了 `algorithms/` 与 `cli/`，
> 训练算法只剩仓库根 `rsl_rl/`。保留本节作为当时输出格式对齐的记录。

用户要求"把训练输出、回放之类的尽量都对齐官方"。官方指 pollen-robotics/microduck_rl 所用的
mjlab + RSL-RL 栈；本机该栈的控制台格式在 `rsl_rl/utils/logger.py`（rsl_rl_lib 5.4.2，
`232–275` 行），日志布局在 `mjlab/scripts/train.py:188–200`，回放在 `mjlab/scripts/play.py`。
本轮只对齐**输出格式与入口形态**，算法仍是本仓库自己的 PPO/Runner（见 AGENTS.md 的技术方向）。

新增与修改：

- `src/ht_microduck/algorithms/logger.py`：`TrainingLogger` 复刻官方 80 列面板
  （`#` 横幅、居中 `Learning iteration i/total`、`Total steps`、`Steps per second`、
  `Collection time`、`Learning time`、`Mean <key> loss`、`Mean reward`、
  `Mean episode length`、`Mean action std`、`Iteration time`、`Time elapsed`、`ETA`），
  同时写 TensorBoard 事件与原有 `metrics.jsonl`；episode 统计用官方口径的最近 100 条窗口。
- `src/ht_microduck/algorithms/runner.py`：`train_step()` 分别记录 `collect_s` 与 `learn_s`
  （官方 `Collection time`/`Learning time` 是两个独立字段），新增 `action_std` 属性，
  `collect()` 额外暴露本轮完成的 episode；`TrainCfg` 增加 `experiment_name`/`run_name`。
  `TrainCfg` 只增字段，旧 checkpoint 仍可加载。
- `src/ht_microduck/cli/train.py`：默认写到
  `runs/<experiment_name>/<YYYY-mm-dd_HH-MM-SS>_<run_name>/`，内含 `params/env.yaml`、
  `params/agent.yaml`、`metrics.jsonl`、`model_<iteration>.pt`、`model_last.pt`；
  新增 `--log-root`、`--experiment-name`、`--run-name`、`--logger {tensorboard,none}`；
  `--out-dir` 仍表示扁平目录，供既有记录复现。
- `src/ht_microduck/cli/play.py`（新）与 `pyproject.toml` 的 `duck-play` 入口：按 `PlayConfig`
  提供 `--checkpoint-file`、`--agent {trained,zero,random}`、`--num-envs`、`--device`、
  `--viewer {auto,native,viser}`、`--no-terminations`、`--video`、`--video-length`，
  缺参数时按官方口径回退到最新 `model_*.pt`。
- `tests/test_logger_and_play.py`（14 条）、`docs/design/training_output_and_play.md`。

实测结果：

```
uv run --no-sync duck-train --num-envs 16 --iterations 3 --device cpu --num-steps-per-env 8 \
  --out-dir .artifacts/t027/fmt --log-interval 1
  ################################################################################
                               Learning iteration 2/3
                              Total steps: 256
                         Steps per second: 189
                          Collection time: 0.632s
                            Learning time: 0.044s
                         Mean policy loss: -0.0775
                          Mean value loss: 0.0057
                        Mean entropy loss: 14.1783
                          Mean action std: 1.00
                            Learning rate: 4.44e-04
  --------------------------------------------------------------------------------
                           Iteration time: 0.68s
                             Time elapsed: 0:00:02
                                      ETA: 0:00:00
```

（终端里横幅与迭代标题为彩色加粗，此处去掉了 ANSI 转义。）

```
uv run --no-sync duck-train --num-envs 8 --iterations 2 --device cpu --num-steps-per-env 4 \
  --log-root .artifacts/t027/logs --run-name smoke --save-interval 1
  [INFO] Training with: device=cpu, seed=0
  [INFO] Logging experiment in directory: .artifacts/t027/logs/flat_velocity/2026-10-27_21-19-27_smoke
  → params/{env,agent}.yaml、metrics.jsonl、model_1.pt、model_2.pt、model_last.pt

uv run --no-sync duck-play --checkpoint-file runs/flat_velocity/checkpoint_1000.pt \
  --num-envs 1 --device cuda:0 --viewer native --nconmax 64 --njmax 256
  [INFO] Loaded runs/flat_velocity/checkpoint_1000.pt at iteration 1000
  → 窗口 "MuJoCo : mjlab scene" 1280x720 实际渲染，持续运行至 180 s 超时退出（exit 124）

uv run --no-sync duck-play --agent zero --num-envs 1 --device cuda:0 --viewer viser
  ╭────── viser (listening *:8080) ───────╮  HTTP http://localhost:8080

uv run --no-sync duck-play --checkpoint-file ... --video --video-length 5
  [INFO] Saved video to .artifacts/t027/vid/duck-play-step-0.mp4   （8021 字节）
  trained/zero/random 三种策略分别产出 8021 / 7733 / 9147 字节，内容不同

uv run --no-sync duck-train --resume .../model_2.pt
  [INFO] Resumed from .../model_2.pt at iteration 2
  Learning iteration 3/4 … 4/4      （迭代号与 ETA 均接上，不回到 1/2）

make check / pytest tests
  All checks passed!   192 passed, 1 warning, 8 subtests passed
```

本轮修掉的问题：

1. `--video` 起初只打印 "Video written"，实际没有 mp4：`VideoRecorder` 只在
   `render_mode == "rgb_array"` 时取帧，而 `build_env` 没有传该参数。现在显式传入，
   并实测生成文件。
2. 视频默认位置一度写到 `runs/flat_velocity/videos`（用户的实验目录）。按官方 `play.py`
   改为 `<checkpoint 目录>/videos/play`，并加 `--videos-dir` 覆盖；误建的空目录已删除。
3. `--resume` 后表头显示 `3/2`：`total_iterations` 没有加起始迭代号，ETA 也按 0 起算。
   改为 `start_iteration + num_iterations` 并在 logger 里扣减，实测恢复后显示 `3/4`、`4/4`。

与官方的已知差异（有意保留）：

- 官方 `log_interval` 概念不存在，每轮都打印；这里保留 `--log-interval`（默认 1，即每轮打印）。
- 官方用 wandb/tensorboard 二选一，默认 wandb；这里默认 tensorboard（本机无 wandb 登录），
  且始终写 `metrics.jsonl` 供后续评估与绘图读取。
- 官方 `params/agent.yaml` 记录 RSL-RL 的完整 `train_cfg`；这里记录本仓库的
  `actor`/`critic`/`ppo` 数据类，字段名不同但同样是"恢复所需的最小集合"。

遗留与边界（T027 仍为进行中，未全部验收）：

- 本轮完成的是 T027 中的**恢复与回放**两项；T027 的验收还要求
  `duck-eval` 与固定种子评估报告（覆盖零速、前后、侧移、转向，报告跟踪误差、跌倒率、
  episode 长度与限幅统计），这部分本轮未做，任务状态保持"进行中"。
- 回放只做了"能加载、能跑、能出画面/视频"，**未评估步态质量**；所用 checkpoint 取自仍在
  进行的 2 万轮训练（第 1000 轮），当时 episode 长度已满 1000 步但尚未验证速度跟踪误差。
- 本轮未执行 Git 暂存、提交或推送。
