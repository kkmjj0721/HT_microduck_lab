# 开发流程与任务

项目按“确定任务 → 最小实现 → 验证 → 记录结果 → 提交”的顺序开发。
一次只推进一个任务，每个任务都写清完成条件。接手工作时先读本页和根目录的
[AGENTS.md](../AGENTS.md)，再决定修改哪些文件。

## 每次开发怎么做

1. **查看现状。** 执行 `git status --short --branch`，阅读当前任务及相关代码，识别已有未提交改动。
2. **确定本次任务。** 写清目标、修改范围、前置依赖和验收命令。任务过大时先拆成能分别验证的小项。
3. **设计并实施。** 按下表选择流程，先打通最小结果；大功能先明确接口与模块边界。额外需求记入待办。
4. **验证并审查。** 执行 `make check` 和专项检查，按影响安排独立审查、修复和复核；未执行项说明原因。
5. **记录并交付。** 更新任务状态，记录命令、关键结果、审查结论和未解决项，默认保留工作区供审阅。

状态使用“待办、进行中、阻塞、完成”。同时最多一个任务进行中。
进入进行中前必须有明确验收条件；只有全部验收项通过才能完成。
已完成任务需要修改时创建后续任务，保留原来的验证记录。

## 规范职责与变更规模

| 维护位置 | 唯一职责 |
|---|---|
| [AGENTS.md](../AGENTS.md) | 仓库级约束、授权边界与开发入口 |
| 本页 | 执行流程、任务状态、阶段依赖和完成记录 |
| [协作与审查规范](collaboration_review.md) | 分工、文件归属、集成、独立审查和修复复核 |
| [设计模板](design/TEMPLATE.md)、[审查模板](review/TEMPLATE.md) | 大功能的具体接口、实施决策、审查问题与关闭证据 |
| [安装文档](setup.md) | 环境、安装、依赖同步与 GPU 基础检查 |
| [README](../README.md) | 项目概览、可用入口及必要链接 |

本项目参考 quadruped_lab 的流程设计，沿用自己的任务表、包目录和项目内产物约束。
规则只在上述归属处维护，其他位置使用链接；任务记录引用关键证据，不重复粘贴完整日志。

| 改动类型 | 执行方式 | 需要维护的记录 |
|---|---|---|
| 小修复、参数调整、局部重构 | 在任务条目明确范围，直接修改、验证并自审；有独立复核时如实记录 | 本页任务条目和完成记录；已有说明受影响时同步更新 |
| 用法、配置含义或安装变化 | 实现并验证真实入口，核对受影响示例 | 对应现有说明；跨模块接口变化同时按大功能处理 |
| 新环境、算法、训练/部署流程或跨模块接口 | 先设计模块、接口和验收，再实现、集成、验证与独立审查 | 复用同主题 `docs/design/<主题>.md` 和 `docs/review/<主题>.md`，没有时按模板创建 |
| 用户指定分析、文档或流程完善 | 按指定范围完成，不额外创建本次设计/审查专题文档 | 修改已有内容并记录任务结果 |

设计和内部审查不增加用户逐轮确认。实现请求持续推进至可验证交付；
只有缺失信息实质影响方案、资源超出授权或需要尚未授权的操作时才澄清，并继续处理独立工作。

## 模块归属与接口设计

| 目录 | 职责与边界 |
|---|---|
| `src/ht_microduck/robots/` | 机器人 MJCF、mesh、关节映射、实体初态和碰撞配置；不放奖励或训练循环 |
| `src/ht_microduck/actuators/` | 两类执行器模型、参数来源和 mjlab 生命周期适配；不决定策略动作子集 |
| `src/ht_microduck/tasks/`（待实现） | 任务配置、观测、动作、命令、奖励、终止和 reset |
| `src/ht_microduck/rl/`（建议，待实现） | 本地通用网络、Storage、PPO 与 Runner；通过明确接口消费环境，不混入机器人特定奖励 |
| `src/ht_microduck/cli/`（待实现） | 参数解析、配置装配和启动；不承载环境或算法的核心实现 |
| `tools/`、`tests/` | 独立检查工具与正式自动化验证；复用包接口，不复制训练核心逻辑 |
| `.artifacts/` | 任务临时验证、检查缓存、构建和解包产物；按所属任务清理 |
| `outputs/` 等运行目录 | 需保留的训练、评估、导出和实测产物；运行入口尚未实现，不视为已有默认输出路径 |

入口装配任务和算法，任务消费机器人/执行器配置，通用算法消费环境接口；
生产模块不反向导入 CLI、工具或测试。模块不应为复用少量代码而过早建立宽泛公共层。
已有层次没有合适职责时，在对应功能设计中说明新目录及依赖，再添加实现。

跨模块接口先明确输入输出的名称、形状、顺序、类型、设备、单位、坐标系和时序；
涉及学习时同时说明归一化、动作缩放/裁剪、上一动作含义、reset 历史和终止/超时的 bootstrap。
更改检查点或策略接口时写清兼容策略，同步核对训练、回放、评估和导出。

## 依据核查与验证选择

训练、控制或仿真问题先读取本地代码、配置、日志和已有运行结果，再核查相关上游源码、官方文档或论文。
记录版本、路径及直接支持判断的位置，比较硬件、依赖、接口和工况差异；
资料冲突或缺失时说明已检查范围、待核实内容和最小验证，不用反复猜测替代证据。

| 依据 | 结论边界 |
|---|---|
| 本地已验证事实 | 写明实际命令、配置与观察；编译、短跑、训练和性能评估分别说明覆盖范围 |
| 参考项目或论文 | 写明地址/路径、版本、代码位置或章节；外部实现与作者结果不等于本机已复现 |
| 推断或仿真假设 | 写明依据、尚缺证据、适用条件和判定方法；未验证前不写成确认参数或效果 |

所有任务都执行 `make check`；专项验证按变化选择，不因文档或格式修改新增测试。

| 变化 | 专项验证 |
|---|---|
| 文档、工作流、忽略规则 | 链接、实际示例、任务状态、规则一致性；用 `git check-ignore` 核对产物和保留文件 |
| 模型或执行器 | 模型加载、关节顺序、单位、目标映射、限幅、字段独立性及小规模 GPU 动态检查 |
| 观测、奖励、动作、终止和 reset | 形状、有限值、符号、边界、历史、真实终止/超时和局部 reset 隔离 |
| 算法或训练入口 | 有意义的数值验证，以及少量环境、有限迭代的采样/更新/检查点短跑 |
| 恢复、导出或部署 | 实际恢复更新、PyTorch/ONNX 一致性、闭环回放及受影响硬件/目标板验证 |
| 策略效果 | 固定评估配置、种子与基线，报告跟踪误差、跌倒率等指标和波动；短跑不代表收敛 |

训练验证复用正式测试或真实入口，不在辅助脚本复制训练实现。启动前确定设备、种子、
环境数、步数/迭代上限、超时及独立产物目录；完整训练须显式安排，不随 `make check` 执行。
确认启动正常后使用进程通知或有界等待，结束后统一核对退出码、日志、实际步数和检查点；
启动失败、异常退出或超时才提前排查，不频繁轮询训练指标。
已通过的验证只在后续改动、失败或明确未解决问题需要时重跑。

## 阶段顺序与验收

| 阶段 | 工作范围 | 通过条件 |
|---|---|---|
| M0 可复现基线 | 环境、MJCF、关节映射、基础检查与 Git 基线 | 安装和检查可重现，现有变更整理为可回溯提交；训练前另通过 GPU 检查 |
| M1 机器人仿真 | mjlab 实体、场景、无刷与舵机执行器 | 场景可创建和重置，两组关节响应符合控制约定；限幅和仿真假设有记录 |
| M2 最小训练 | 平地速度任务、本地算法组件、训练入口 | 小规模采样和 PPO 更新可完成，关键张量有限、形状正确，检查点可保存；记录初始评估基线 |
| M3 可评估策略 | 检查点恢复、回放、评估、ONNX 导出 | 恢复可继续训练，固定配置和种子可评估，导出策略与原策略在约定误差内一致 |

当前处于 **M0 收尾**：依赖、模型和关节映射已具备，本地基础检查已通过，Git 基线尚待整理。
原始检查模型保持 `nu=0`；T016 的整机工厂接入执行器后 `nu=15`，已有小规模场景运行证据。
Git 基线与阶段验收仍未完成；短场景检查不代表稳定站立或 M1 已完成。
M2 的短跑只验证训练链路；策略性能通过后续评估和实验确定。

## 当前任务

当前无进行中任务；T022–T026 已把任务契约、平地速度环境、本地网络/Storage、PPO 与
Runner/`duck-train` 依次接通，结论与实测见下方各条目。T038 已把 `HOME_FRAME` 定为
脚底水平的蹲姿并通过验收，未改动默认增益。T043 已把 PPO 与网络设计源码放到项目根
`rsl_rl/`（只读参考）。T042 只读核对了三处模型的碰撞体简化，未改变任何模型文件。
T044 修掉了自碰撞传感器把足底-地面接触计入 `self_collisions` 的问题；在此之前该奖励项
每步 `-0.109`，一个人盖过全部正奖励（约 `+0.054`），修复后奖励才反映任务本身。
T045 修掉了 `ht_microduck_constants.py` 独立预览的两个缺陷：预览跑的是 XML 默认的显式
Euler，无刷阻尼在该积分器下发散，机器人才"倒地后一直抽"；且 `init_state` 从未生效。
现在预览与训练用同一 `MujocoCfg`，并从 HOME 关键帧起算；入口也改成
`legged_wbc_mjlab` 的 `Entity` 直连写法，不再依赖 `Scene` 与 GPU。
随后用户报告"会抖动"，定位为 12 个无刷关节 `dof_armature` 全为 0、关节几乎没有惯性，
PD 阻尼按 6 Hz 空转；补上 armature 后站姿 `|qvel|` 降 29 倍、可见抖动降 24 倍、
训练环境零动作抖动降 30 倍，且零动作奖励不变差。取值由用户提供为
`0.0069753532276 kg·m²`（关节侧）；此前只能用官方 duck MJCF 的统一占位值 `0.002`，
因为官网、官方手册、官方 STEP 模型与参考项目均无 HTDW-3532 转子惯量。
按 32:1 折算该真实值相当于 68.1 g·cm² 转子，与该尺寸电机量级吻合。
T041 对照三个参考项目复核了下一步，结论见下方条目。
T040 已整理根目录 README 的概览、运行入口和文档导航。
T037 已按官方项目在 XML 中补 `imu` site 与 5 个内置传感器，统一检查与 GPU 场景检查通过。
T039 按用户意见让本体 XML 只保留机器人内容，并把 `ht_microduck_constants.py` 按官方
`microduck_constants.py` 的结构重写；地形与照明由 mjlab 的 `Scene` 提供，执行器沿用本地实现。
T001、T002 已按本轮核对证据关闭（见各自条目），原先"下一项仍是 Git 基线"的前提不再成立。
下一项为 T027（恢复、回放与定量评估）。T022–T026 的短跑只证明训练链路通、loss/梯度有限、
checkpoint 可读写可恢复，**不证明学会行走**；2026-10-27 复核在 CPU 上跑到 100 迭代，
episode 长度 24 → 156 步、return 由负转正，但仍在 3 s 左右跌倒。GPU 设备节点已在当日晚间
恢复可见，`duck-train` 可在 `cuda:0` 上实际运行；2048 环境需用 `--nconmax 64 --njmax 256`
规避 Warp 图捕获的 OOM（实测接触峰值 13、约束峰值 55），详见 T026 追加条目。
M0/M1 阶段验收仍按依赖推进，初始化姿态和短跑结果不代表稳定站立。

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
| T024 | 实现本地网络与轨迹 Storage | 完成 | T023 |
| T025 | 实现本地 PPO 更新 | 完成 | T024 |
| T026 | 接通 Runner、训练入口与短跑基线 | 完成 | T023、T025 |
| T027 | 实现恢复、回放与定量评估 | 进行中 | T026 |
| T028 | 导出策略包并通过 CPU MuJoCo 回放 | 待办 | T027 |
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

### T001 整理现有开发基线

目标：将已有的环境安装、模型加载和文档重组整理为可回溯的基线。

范围：审阅现有修改、新文件及删除项，确认旧文档与旧工具的替代关系，补齐必要的生成文件忽略规则，
按用途组织提交。当前工作区的已有改动需要逐项审阅，暂存时列出具体路径。

验收条件：

- `make check` 通过。
- README 中的安装、模型检查和文档链接与当前文件一致。
- 提交中包含所需源码、XML 和 mesh，排除虚拟环境、缓存及训练输出。
- 按当前会话授权完成基线提交后，`git status --short --branch` 中的剩余改动均有明确归属。

T021 复核补充：当前仅 README 被 Git 跟踪，已有代码、文档、依赖和测试尚未纳入基线，
且没有根 `.gitignore`；需审阅资源归属并补充环境、缓存和训练输出的忽略规则。
现有 constants 预览入口 `import` 排版触发 Ruff `I001`，须在基线验收时修复；T021 未修改该文件。
本次比较不包含 Git 提交授权。

T032 后续更新：忽略规则与统一检查入口已纳入本次工作流完善；具体结果见 T032 完成记录。
Git 基线的资源审阅与提交仍由本任务负责，不能仅因工作流和检查就绪关闭 T001。

T041 复核结论（完成）：Git 基线已经具备。提交 `21589d7`（2026-10-27 14:30，作者 KKMJJ0721）
以 60 个文件、11260 行新增把 `.gitignore`、`AGENTS.md`、`Makefile`、`README.md`、
`docs/`、`pyproject.toml`、`uv.lock`、`src/`、`tests/`、`tools/` 及 16 个 STL 一并纳入跟踪；
`git ls-files --others --exclude-standard` 为 0，工作区只有 T040/T041 的文档改动。
`.gitignore` 排除 `/.venv/`、`__pycache__/`、`/.artifacts/`、`/outputs/`、`/runs/` 等，
未跟踪任何环境、缓存或训练产物，也没有全局忽略 `*.pt`/`*.onnx`/`*.json`。
constants 的 Ruff `I001` 已在 T032 修复，本轮 `make check` 全程通过。
因此 T001 的四条验收条件均满足，状态改为完成；本任务未新增 Git 写操作。

### T002 接入 mjlab 机器人实体与最小场景

目标：复用现有 MJCF 加载器，将机器人放进由 mjlab 管理的最小场景。

当前实现更新：T016 按用户后续授权完成本任务的实体/场景功能，并一并接入混合执行器。
本任务仍待前置 T001 的 Git 基线验收，不重复实现已交付功能；T001 完成后依据 T016 证据复核并关闭。

范围：机器人实体配置、场景地面与灯光归属、一个可执行的场景检查入口。
混合执行器的控制和标定在后续任务中处理。

验收条件：

- 原有 `make check` 通过，独立模型检查继续可用。
- 在开发机 GPU 上创建并重置小规模场景，验证根状态和关节状态的维度及有限值。
- 场景中地面与灯光配置的归属明确，没有重复地面。
- 将实际执行的检查命令和结果写入完成记录。

M1 后续先拆分混合执行器任务，明确动作顺序、控制周期、增益、限幅和参数来源，再进入 M2。
M2 开始前将任务环境、网络与 Storage、PPO 更新、Runner 与入口分别拆成可验收任务。

T041 复核结论（完成）：T001 已关闭，本任务的前置条件满足，四条验收条件均有本轮证据。
本轮实际执行的整机场景检查为 `cuda:0`、4 环境、150 步、`dt=0.002 s`，退出码 0，
末根高 `0.166165–0.166172 m`、峰值力矩 `0.138278 N·m`、峰值关节速度 `0.184298 rad/s`；
双脚全程接地、`planes=1`（仅 mjlab terrain）、IMU 传感器 5 个、局部 reset 与目标映射通过。
地面与灯光的归属由 T039 的模型拆分固定：本体 XML 无 floor/light，场景提供 terrain 与太阳。
`make check` 通过（锁文件、Ruff、134 项测试与 8 项子测试、模型、Git 差异空白），
被动模型仍为 `nq=22`、`nv=21`、`nu=0`、15 关节、16 网格、质量 `3.2947 kg`。
状态改为完成；执行器标定与稳定站立仍分别属于 T030、T031，不在本任务范围。

### T003 补充并发与测试文件管理规则

目标：在 `AGENTS.md` 明确多代理并发、项目内测试与验证文件管理，以及交付前缓存清理规则。

范围：补充并发分工、文件归属、临时目录和清理要求，并同步规则中的现行包路径与关节定义模块。

验收条件：

- 并发规则经独立子代理只读复核，明确同一任务内拆分及同文件单写者。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过。
- 清理项目源码、工具和测试中的 `__pycache__`、`.pyc`、`.pyo` 及本次临时验证目录，复查无残留。

### T004 评审 robots 模块缺项

目标：依据当前机器人模型和已安装的 mjlab 1.6.0 接口，明确 `robots/` 的已有能力、缺项和实现顺序。

范围：只读检查模型加载、关节映射、MJCF、模型检查工具和 mjlab 实体配置；仅更新本任务记录，不实现机器人行为。

验收条件：

- 独立子代理复核模型配置与 mjlab 接入接口，建议提供源码依据并区分机器人配置与任务配置。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过。
- 记录按依赖排序的缺项、参数未知项与下一项最小可执行工作；清理本次临时验证目录及项目字节码缓存。

评审结论与后续顺序：

1. **T002 先接实体和最小场景。** 在现有 `ht_microduck_constants.py` 中补充返回新 `EntityCfg` 的
   `get_ht_microduck_robot_cfg()`，明确 `EntityCfg.InitialStateCfg` 中的基座位置、四元数、关节角和速度。
   已安装的 mjlab 在 `entity/entity.py` 的 `_add_initial_state_keyframe()` 中用该配置生成自由基座初始状态，
   默认位置是原点；不能只依赖原 XML 的基座高度 `0.167 m`，也不能假定全零关节角可以稳定站立。
2. **明确模型与场景归属。** 保留现有 `get_spec()` 的独立模型检查用途，为实体提供去除原始地面和灯光的
   加载入口，由 mjlab 场景统一管理地面和灯光，避免重复地面。
3. **随后单独接入混合执行器。** 依据已确认的 12 个无刷和 3 个舵机关节，分别配置控制响应，
   通过 `EntityArticulationInfoCfg.actuators` 接入。无刷按项目约定实现位置目标到 PD 力矩及限幅；
   舵机先建立等效位置伺服模型，必要时再补速度响应和延迟。执行器可以在 Python 配置中生成，
   无须预先手写到原 XML。增益、速度限制、供电、惯量及延迟须注明来源或仿真假设；
   原 XML 的 `±3.7`、`±1.47 N·m` 和统一 `damping=0.02` 不能视为已标定实机参数。
4. **按接触观测需要完善模型。** 当前机器人碰撞几何均未命名，建议为左右脚等关键几何命名，
   明确摩擦和自碰撞策略；足底 site 在任务需要足端位置等观测时再添加。
   当前没有显式 site 或 sensor，不构成被动实体接入的硬前置条件；现有 mesh 碰撞效果仍需动态验证。
5. **按阶段扩展验证。** T002 通过小规模 GPU 场景创建和重置验证状态；执行器任务再验证分组覆盖、
   目标映射、阶跃响应、力矩限幅及短跑有限值。现有 `check_robot.py` 只检查编译、关节名/顺序和映射覆盖，
   `nu=0` 仍正常退出，viewer 也只有 `mj_forward`，没有物理步进，不能代替动态验收。

机器人配置初期可继续集中在现有 constants 模块，随复杂度增长再拆分；公共 `__init__.py` 的导出按调用需要补充。
动作子集、动作顺序与缩放、观测、奖励、终止条件和控制周期由任务配置明确，PPO、Storage、Runner 保持在独立模块。
本轮评审不改变 M0/M1 状态，开发实施仍先完成 T001，再进入 T002。

### T005 核实并简化 MJCF 资源加载

目标：依据 mjlab 1.6.0 官方源码和文档，核实 `get_spec()` 的资源加载方式并去除不必要的路径覆盖。

范围：模型加载器、当前 README 的资源路径说明和本任务记录；保留历史验证记录，不更改 XML 或机器人行为。

验收条件：

- 核对官方固定版本的 `get_spec()` 示例和 MuJoCo 资源路径规则，记录来源。
- 删除不必要的 `spec.meshdir` 赋值后，从项目内其他工作目录加载并编译模型，验证网格和模型结构不变，
  并验证机器人 spec 组合进父 spec 后仍可编译。
- 设置项目内 `TMPDIR`、pytest `--basetemp` 和 `PYTHONDONTWRITEBYTECODE=1`，执行 `make check` 通过。
- 等待子代理与检查进程结束，清理本次临时验证目录和项目字节码缓存。

核查结论：用户指出的路径覆盖确实多余。[mjlab 1.6.0 Entity 文档的 `spec_fn` 示例](https://mujocolab.github.io/mjlab/v1.6.0/source/entity/index.html#spec-fn)
和[官方 v1.6.0 Go1 加载器](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py)
均直接返回 `mujoco.MjSpec.from_file(...)`。根据 [MuJoCo 3.11.0 的 `meshdir` 规则](https://mujoco.readthedocs.io/en/3.11.0/XMLreference.html#compiler-meshdir)，
本项目绝对路径 MJCF 配合 XML 中已有的 `meshdir="assets/"`，即可相对 XML 所在目录解析全部 STL。
这是 MuJoCo 的资源路径机制，不将其表述为 mjlab 1.6.0 才新增的功能。

`get_spec()` 改为直接返回新 spec，删除冗余 `spec.meshdir` 覆盖和不再使用的 `ASSETS_DIR` 常量；
README 改为说明资源路径由 XML 声明、由 MuJoCo 解析。XML 和历史完成记录保留。

### T006 分析混合执行器配置方案

目标：结合 mjlab 1.6.0 官方接口、本项目关节映射及硬件官方资料，给出无刷和舵机的分组、参数来源与验证顺序。

范围：只读调研、本页记录和 README 中用户已确认的硬件信息，不实现执行器或填入未经确认的实机参数，
不推进 M1 验收状态。

验收条件：

- 并行核对官方执行器 API、项目 XML/关节映射和制造商资料，区分首版仿真近似与后续标定模型。
- 说明两类执行器的控制方式、增益/限幅/惯量/摩擦/延迟归属，以及原 XML 参数与 Python 配置的交互。
- 给出可执行的后续验证步骤，明确尚缺的硬件信息；未运行的动态验证如实记录。
- 在项目内设置 `TMPDIR` 和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check` 通过；
  全部子代理和检查进程结束后清理本次临时产物及项目字节码缓存。

用户确认的设计输入：无刷使用普通 PD 控制；三个舵机为飞特 **HD1910-C001，供电 7.4 V**。
这里的供电是用户确定的方案，不代表已测量负载下的端电压；kp/kd、持续/短时力矩和响应数据仍未确认。

建议的首版方案：

后续选型更新见 T007：多项目对照后，默认建议调整为两类硬件都先使用原生位置 PD；
以下保留 T006 当时提出的显式/原生混合方案，供比较，不作为当前首选。

- 无刷用 `IdealPdActuatorCfg`，明确 `velocity_target=0`、`effort_target=0`，对应当前 README 的显式 PD
  力矩公式及限幅。舵机用 `BuiltinPositionActuatorCfg` 作为等效位置伺服模型，不声称等同实机内部 PID。
  这不是由“无刷/舵机”名称强制决定的：无刷也可使用 native position PD，后者与显式 PD 的离散积分不同，
  官方推荐它作为稳定的入门方案；若调整选择，应记录控制周期、积分器和阶跃对比，不反复改动架构。
- 物理参数按型号/电压区分，控制增益按负载区分。建议先分为双侧 hip_yaw、hip_roll、hip_pitch、calf、ankle
  五对，另列 neck_pitch、head_pitch，再分别列 head_yaw、head_roll、mouth，共 10 个互不重叠的参数组、15 个关节。
  左右同类关节初期可共享增益假设，实测不对称时再拆；同型号并不要求所有关节共用 kp/kd。
  mjlab 1.6.0 的这些执行器增益是标量，按组创建多个 cfg，再汇总到 `EntityArticulationInfoCfg.actuators`。
- 每组显式提供 `stiffness`（kp，N·m/rad）、`damping`（kd，N·m·s/rad）与有限的 `effort_limit`（N·m）。
  `IdealPdActuatorCfg` / `BuiltinPositionActuatorCfg` 没有供电电压字段，7.4 V 是选取和标定参数的工况记录，
  不能添加不存在的 `voltage=7.4` 参数。
  无刷优先映射驱动中已有增益，先核实驱动的单位和减速器输入/输出侧定义；舵机 kp/kd 是需拟合的等效值，
  不能直接照搬内置 PID 寄存器数值或官方大机器人示例。已知有效关节惯量时，可用
  `kp = J_eff * omega_n**2`、`kd = 2*zeta*J_eff*omega_n` 作调参起点，再用带载阶跃验证；
  `J_eff` 包含连杆负载，不等于仅有转子反射惯量，公式不代替标定。
- `armature` 是输出侧反射惯量，不是连杆质量；单级近似为 `J_motor * reduction_ratio**2`。
  力矩、速度和惯量都统一到模型关节输出侧，避免将已换算的参数再次乘减速比。
  没有可靠数据时，明确沿用 XML 默认值的仿真假设，不从电机质量或整机质量臆造转子惯量。
- XML 的统一 `damping=0.02` 是被动粘性阻尼；cfg 的 `damping` 是主动 PD kd，二者都会影响响应。
  `viscous_damping=None` 保留 XML，非空值则覆盖。后续训练 spec 应统一管理/记录该阻尼，避免把它当成 kd。
  当前 XML 的 joint `actuatorfrcrange` 仍会限制总执行器力矩；普通 `IdealPd` / `BuiltinPosition` 的 Python
  `effort_limit` 不会自动覆盖它，实际范围受两者共同约束。后续实现应让训练 spec 与 cfg 来自同一组限幅值；
  保留当前原始 XML 供检查。总执行器限幅不包含被动阻尼、摩擦或接触产生的关节力。
- `BuiltinPositionActuatorCfg` 没有 `velocity_limit` 字段；它不会自动复现舵机速度/加速度限制。
  若需模拟舵机目标速度，可在发送位置目标前增加按时间步限制增量的轨迹模块，但这只是目标轨迹限速，
  不保证受外力推动时实际关节速度不超限。需要真实响应时再拟合负载相关的执行器模型。
  待确认扭矩—速度曲线后，可为无刷使用 `DcMotorActuatorCfg`；其中 `saturation_effort` 表示堵转端峰值，
  `velocity_limit` 表示空载速度，`effort_limit` 是每步输出上限，不自带温升/峰值持续时长模型。
  `velocity_limit` 控制力矩—速度饱和曲线，也不是实际关节速度的硬限幅。
  该类也可用于无刷输出侧的简化曲线，不能仅凭名称或将额定速度当空载速度直接选参。
- 延迟用 cfg 自带的 `delay_min_lag` / `delay_max_lag`，单位为物理步，不是策略步；分别记录 CAN 与 TTL
  链路响应，未测时可显式以零延迟作初版假设。控制环、物理 dt 与策略 decimation 分别记录，舵机命令
  更新慢也不意味着仿真跳过其物理步。未知通信延迟不能从串口波特率直接推定。

硬件资料核查：

- [飞特型号资料](https://raw.githubusercontent.com/ftservo/ftservo-wiki/main/docs/products/models/hd-1910-c001/main.md)
  支持位置伺服、TTL 总线与内部 PID；7.4 V 在其所列电压范围内。但摘要和官网详细表的条件/数据不同，
  详细表的力矩及速度只明确标注 4.8 V；不能将其换作 7.4 V 的额定数据，也不线性外推。
  当前没有充分依据确认 XML 的 `1.47 N·m` 是本型号在 7.4 V 的持续力矩；堵转值也不能作为长期出力。
- 无刷 `3.7 N·m` 目前仍只有模型预设，未取得确切型号的一手规格以确认持续力矩、峰值时长和速度等条件。
  不把经销商表格替代为制造商确认结果；后续取得型号说明或实测数据后再填正式参数。

任务侧与后续验收：

1. 实现时检查 10 个参数组恰好覆盖 12+3 个关节且无重复，并导出最终编译的 actuator 与 joint 限幅和阻尼。
2. 平地行走首版建议动作仅覆盖双腿 10 关节，其余 5 个颈/头/嘴关节保留执行器并显式发送默认保持目标，
   这只是建议的任务选择；策略动作数不由执行器数量决定。`init_state.joint_pos` 不会自动为未选动作关节
   设置持续保持目标，reset 后也需要初始化 command target。
3. 首版动作顺序沿当前 MJCF 的右腿到左腿顺序明确声明，并断言实际 `target_names`；
   mjlab 1.6.0 关节 action 查询按自然关节顺序匹配，不能只用 `preserve_order=True` 声称任意顺序成立。
   每关节单独设置动作 scale/目标角范围，尤其 mouth 范围为 `[0, 0.33] rad`、head_roll 仅 `±0.28 rad`，
   不使用全身统一幅度；位置目标限幅与力矩限幅分别处理。
4. 完成 T002 后，单独开展小规模 GPU 执行器验收：先隔离/固定基座测试单关节小幅阶跃，再验证带载响应、
   目标映射、饱和、延迟和 reset；记录力矩/速度/超调/稳态误差及数值有限性，再做全身保持姿态和短跑。
   避免用自由基座未支撑时的倒地现象判断 PD 性能；不以静态编译或 `nu` 数值代替响应证据。

接口依据：[mjlab v1.6.0 执行器文档](https://mujocolab.github.io/mjlab/v1.6.0/source/actuators.html)、
[IdealPd 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/pd_actuator.py)、
[Builtin 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/builtin_actuator.py)、
[参数与延迟定义](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/actuator.py)、
[DcMotor 源码](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/dc_actuator.py)。

### T007 对照公开项目的执行器选型

目标：从真实机器人训练项目的配置和任务引用核对位置 PD 的常见建模方式，并据此评估本项目首版选型。

范围：公开项目源码与本页记录，不实现执行器或调整硬件参数。

验收条件：

- 核对多个独立项目的实际执行器实例化和任务使用，记录可追溯源码链接及 mjlab 版本条件；
  不用 import 数量、同仓库多个机器人或复制 fork 代替独立采用证据。
- 区分普通原生位置 PD、显式理想 PD 和带速度曲线/自定义动力学的执行器；
  其他框架只作为机制对照，不混入 mjlab 类使用频次统计。
- 说明样本局限与本项目建议变化，保留 T006 原始记录并明确后续结论。
- 项目内设置临时目录和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check`；
  全部子代理及检查进程结束后清理本次临时产物和项目字节码缓存。

本次调研日期：2026-10-23。逐项检查执行器实例化、机器人 articulation 和任务引用；
同源机器人配置、同一仓库多个机器人和框架机制对照均不重复统计为独立采用证据。

当前核对到的项目：

| 项目与版本条件 | 实际任务中的执行器路径 | 源码依据 |
|---|---|---|
| mjlab 官方 v1.6.0 | G1、Go1、YAM 按关节组创建 `BuiltinPositionActuatorCfg` | [G1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py)、[速度任务引用](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/tasks/velocity/config/g1/env_cfgs.py)、[YAM 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/i2rt_yam/yam_constants.py) |
| Unitree `unitree_rl_mjlab`，提交 `1425b15f`；setup.py 声明 mjlab==1.2.0 | G1 的手臂、髋、膝、踝等组均为 `BuiltinPositionActuatorCfg`，速度任务实际调用；与 mjlab 官方配置同源 | [配置](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/src/assets/robots/unitree_g1/g1_constants.py)、[任务](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/src/tasks/velocity/config/g1/env_cfgs.py)、[版本](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/setup.py) |
| KaydenKnapik `BoosterT1mjlab`，提交 `f0480bff`；uv.lock 为 mjlab 1.3.0 | T1 六组增益/力矩/惯量/延迟均通过 `BuiltinPositionActuatorCfg` 表达，速度任务引用机器人配置 | [配置](https://github.com/KaydenKnapik/BoosterT1mjlab/blob/f0480bffb456456aa01bda75b4dcd3655659614c/src/booster_t1_mjlab/robots/boostert1/t1_constants.py)、[任务](https://github.com/KaydenKnapik/BoosterT1mjlab/blob/f0480bffb456456aa01bda75b4dcd3655659614c/src/booster_t1_mjlab/tasks/velocity/config/t1/env_cfgs.py) |
| IntelligentRoboticsLab `booster_mjlab`，提交 `d92e1139`；uv.lock 为 mjlab 1.6.0，源码 rev 为 `b517e0c4` | 普通 K1 速度任务使用 `MotorPositionActuatorCfg`，该类仅扩展元数据并继承 `BuiltinPosition` 的 build；不能因另有 torque_speed.py 就认定默认启用自定义限幅 | [继承关系](https://github.com/IntelligentRoboticsLab/booster_mjlab/blob/d92e11395d961096d639446c0a8a176f12bb51da/src/booster_mjlab/robots/booster_k1/actuators.py)、[任务](https://github.com/IntelligentRoboticsLab/booster_mjlab/blob/d92e11395d961096d639446c0a8a176f12bb51da/src/booster_mjlab/tasks/velocity/config/k1/env_cfgs.py) |
| Menlo `asimov-mjlab`，提交 `98870d12`；旧版 mjlab 源码 fork，自报包版本 0.1.0，不能视作当前 1.6.0 | 自有 Asimov 双足配置按髋/膝/踝组使用 `BuiltinPositionActuatorCfg`，速度任务实际引用；仍使用旧 `joint_names_expr` API | [配置](https://github.com/menloresearch/asimov-mjlab/blob/98870d12f079c0b6313bb0fe459aa591a5e7f251/src/mjlab/asset_zoo/robots/asimov/asimov_constants.py)、[任务](https://github.com/menloresearch/asimov-mjlab/blob/98870d12f079c0b6313bb0fe459aa591a5e7f251/src/mjlab/tasks/velocity/config/asimov/env_cfgs.py) |
| ccrpRepo `AMP_mjlab`，提交 `6c7a2947`；setup.py 固定 mjlab==1.2.0 | 使用自定义 `UnitreeActuator`：PD、速度相关限幅和摩擦计算后反解位置输入；虽 cfg 继承 `BuiltinPosition`，其 build 已返回自定义实现，不能记作标准类型 | [执行器](https://github.com/ccrpRepo/AMP_mjlab/blob/6c7a2947fccc973e4af8e6d90e550400f1b6fcfc/src/assets/robots/unitree_g1/unitree_actuators.py)、[AMP 任务](https://github.com/ccrpRepo/AMP_mjlab/blob/6c7a2947fccc973e4af8e6d90e550400f1b6fcfc/src/tasks/amp_loco/config/g1/env_cfgs.py) |

补充核对了以下三个组织的项目：

| 项目与版本条件 | 实际任务中的执行器路径 | 源码依据 |
|---|---|---|
| PAL Robotics `pal_mjlab`，提交 `952abb83`；uv.lock 为 mjlab 1.6.0 | Talos 按手臂、腿、头等关节组创建 `BuiltinPositionActuatorCfg`，Flat/Rough 速度任务实际使用 | [配置](https://github.com/pal-robotics/pal_mjlab/blob/952abb83a590d0e771cfd8e570517ba054182196/src/pal_mjlab/robots/pal_talos/talos_constants.py)、[任务](https://github.com/pal-robotics/pal_mjlab/blob/952abb83a590d0e771cfd8e570517ba054182196/src/pal_mjlab/tasks/velocity/talos/env_cfgs.py) |
| Pollen Robotics `microduck_rl`，develop 提交 `b02fdea4`；依赖 mjlab==1.3.0 | 默认 Walk Flat/Rough 使用自定义 `FrictionDRBamActuatorCfg`，建模固件位置控制、电压与摩擦；不属于直接标准 IdealPd 或 BuiltinPosition | [配置](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)、[任务](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)、[BAM 实现](https://github.com/Rhoban/bam/blob/62bd8ce12154340be97e06f7f41a0ca8f116d967/bam/mjlab.py) |
| Wuji Technology `wuji-mjlab`，提交 `b2b98d70`；pixi.toml 固定 mjlab==1.6.0 | Hand2 Reorient 用 `XmlActuatorCfg` 包装 XML，任务 spec 编辑调用 `set_to_position(kp, kv)`；属于原生位置 PD 路线，但不能算直接实例化 BuiltinPosition | [XML wrapper](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/assets/robots/wuji_hand2/wuji_hand2_cfg.py)、[控制与编辑链](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/tasks/reorient/config/wuji_hand2/hand2_constants.py)、[任务](https://github.com/wuji-technology/wuji-mjlab/blob/b2b98d7054a8d1b0f5cf295d5acaebc4358bc6a9/src/wuji_mjlab/tasks/reorient/config/wuji_hand2/env_cfgs.py) |

Pollen 的经验提示：接近本项目形态的机器人也会在取得硬件辨识数据后使用自定义电气/摩擦模型，
选型不总是标准 IdealPd 与 BuiltinPosition 二选一。其电机与本项目的高擎/飞特混合方案不同，不能复用其参数。

跨框架对照仅用于说明两条路线都存在：

- [legged_gym A1](https://github.com/leggedrobotics/legged_gym/blob/8fa29acc6fd1910c3d9659eef6310bdd301cde0a/legged_gym/envs/base/legged_robot.py)
  每个物理步显式计算 PD 力矩并裁剪，再写入力矩；其路径类似 mjlab 的显式 PD，但不是使用 mjlab 类。
- [IsaacLab v2.3.0 H1](https://github.com/isaac-sim/IsaacLab/blob/v2.3.0/source/isaaclab_assets/isaaclab_assets/robots/unitree.py)
  使用 `ImplicitActuatorCfg`；它是 PhysX 原生驱动机制，不能当成同名 mjlab API 或保证相同离散动力学。
- [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab/blob/4960b84732b0c2ec593dccbfe963fda1bcd7b1e3/source/unitree_rl_lab/unitree_rl_lab/assets/robots/unitree.py)
  同一提交 H1 用显式 `IdealPDActuatorCfg`、G1 用 `ImplicitActuatorCfg`，说明选择还与项目建模目标和已有配置有关。

本项目建议：普通位置目标、零目标速度的首版，两类硬件都优先采用 `BuiltinPositionActuatorCfg`，
仍按 T006 的关节负载分组分别配置增益、力矩、惯量和延迟，配合 `implicitfast`。
这与现有 PD 公式一致，不要求因为无刷而先选显式实现；T006 的混合方案保留为可选对照。
需要显式控制律、可验证的力矩—速度曲线或更复杂已标定动力学时，再按需求使用 `IdealPd`、`DcMotor` 或自定义模型。
单纯加命令延迟也不要求换成显式类型，因为两者均支持 inline delay。

这些源码样本支持原生位置 PD 是 mjlab 常规配置的常见起点，但包含同源复用，不能推广为全生态占比，
也不能据此判断它在本机实机上必然更准确。尚未运行跨执行器动态对照或任何 GPU 训练；
实机型号、7.4 V 工况、未知增益和标定要求均沿用 T006，不照搬他人的数值。

### T008 核实 HD1910 与 Microduck 的 BAM 适配方案

目标：核实 Pollen 官方与 HD1910 社区鸭子的硬件和模型来源，明确用户新增
`actuators/HD_1910_C001/friction_dr_bam.py` 的职责、数据要求及 mjlab 1.6.0 接入方式。

范围：联网核查官方/社区源码、厂家资料，检查新增目录及依赖，形成有来源的实现方案；
不将其他型号参数或未经验证的社区借用参数标为本机标定结果，不推进 M1 验收状态。

验收条件：

- 交叉核对 Pollen 实机硬件/通信与 RL 模型；区分官方原型、社区 HD1910 改版及本项目混合驱动。
- 核对 HD1910-C001 的 7.4 V 规格、公开 BAM 参数来源与版本，明确电气模型、拟合数据、摩擦随机化封装的边界。
- 给出该文件可落实的类/API/参数方案和专项验证步骤，说明当前缺项；只有证据足够时才进一步确定代码改动范围。
- 项目内设置临时目录和 pytest `--basetemp`，以 `PYTHONDONTWRITEBYTECODE=1` 执行 `make check`；
  全部子代理与检查进程结束后清理本次临时产物和项目字节码缓存。

调研结论（2026-10-23）：

**硬件与参数来源。** Pollen 官方 Microduck 的[实机总线](https://github.com/pollen-robotics/microduck/blob/main/duck-control/src/bus.rs#L1-L30)
使用 `Xl330Controller`；[RL 配置，固定提交 b02fdea](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)
使用 XL330 / M6。HD1910 是另有公开实现的社区改版，不能将其参数称为 Pollen 原型的标定值。
本机为 12 个无刷加 3 个 HD1910，更不能整体复制纯舵机鸭子的配置。

| 来源 | 核对到的实现/工况 | 本项目如何使用 |
|---|---|---|
| Pollen Microduck | XL330，BAM 加摩擦随机化扩展 | 参考配置分层、事件和状态生命周期；不用其电机参数 |
| [飞特 ftservo-bam，固定提交 4f7c0b0](https://github.com/ftservo/ftservo-bam/tree/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/params/feetech_hd1910_7_4V) | HD1910，7.4 V，提供 M1–M6 JSON 和专用控制器 | 首选的公开模型候选；不是本机实测标定 |
| [JoyandAI 的 HD1910 摆锤报告](https://github.com/JoyandAI/microduck_rl/blob/22916b9d82f250caa563ed9a56976eb33243fb91/docs/feetech_hd1910_pendulum_results.md)及[训练配置](https://github.com/JoyandAI/microduck_rl/blob/22916b9d82f250caa563ed9a56976eb33243fb91/src/mjlab_microduck/robot/microduck_constants.py#L150-L198) | 实测约 5.1 V，报告默认 M1、备选 M4；同提交训练配置另用 M5 | 参考采集和独立验证方法，注意报告与运行配置的差异，不当作 7.4 V 参数 |
| [Luwu xgoduck 的 1910_m6.json](https://github.com/LuwuDynamics/xgoduck_rl/blob/326d77a1122870bdefa2c36403937502c958e69c/src/mjlab_microduck/robot/xgoduck/params/1910_m6.json) | JSON 选择 `sts3215` 控制器，原始采集条件本轮未核实 | 不直接采用；该字段只证明所选控制律，不能据此断定被测硬件型号 |

**新增的确切型号规格。** [社区托管的飞特 HD1910-C001 原始规格书](https://raw.githubusercontent.com/JoyandAI/OpenMicroDuck/b8c7d6945e5ceda9ceb9706b53c372adb9ae4128/hardware_spec/servo/HD-1910-C001%E4%B8%B2%E5%9E%8B%E8%A7%84%E6%A0%BC%E4%B9%A6-20260907.pdf)
为 A/0、2026-09-07，带制造商抬头及完整型号；托管方是社区，非厂家官网。
7.4 V 条件下给出堵转力矩 `15 kgf·cm ≈ 1.471 N·m`、额定负载 `3.7 kgf·cm ≈ 0.363 N·m`，
空载速度 `0.088 s/60°`（同时列 `113 rpm`，约 `11.9 rad/s`）；堵转力矩和空载速度均有 ±10% 公差。
XML 的 `±1.47` 因而有对应的规格书堵转依据，但仍不代表持续力矩或本机已测限值；
额定负载也不自动构成瞬时硬限幅，峰值持续时间、温升和保护仍需单独处理。
这份版本的规格书说明模式 4 为出厂默认纯位置 PD / Sim2Real 模式；实机仍应读回模式和增益确认。
这些新增来源更新 T006 当时“未找到明确 7.4 V 数据”的结论，历史记录保留。

**厂家模型的适用边界。** [HD1910 控制器源码](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/feetech/actuator.py)
采用位置误差到 PWM/电压的 P 控制，再由电气模型计算含反电动势的电机力矩；默认 `vin=7.4`、`kp=32`。
`kp_fw=32` 是该控制模型的固件增益，不是 `32 N·m/rad`，也不是已经读回的本机设置；
该类没有独立 D 项，不能声称完整复现上述模式 4 的 PD 固件。
M6 中的 `kt≈0.5645`、`R≈2.9665`、`armature≈0.001827` 是拟合模型参数；
`q_offset` 属于台架零位，`command_delay≈0.000978 s` 属于该辨识链路，不直接当作机器人关节零位或整机总线延迟。
普通 `BamActuator.compute()` 不会自动施加 JSON 的 `command_delay`；
另行启用时须与 mjlab 以物理步计的 inline delay 分清，避免重复施加。

**三个已定位的接入问题。**

1. 厂家 [JSON](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/params/feetech_hd1910_7_4V/m6.json)
   写 `actuator="hd1910"`，[注册表](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/actuators.py)
   只有 `HD1910`；[加载器](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/model.py)
   直接用字符串索引。静态核对确认不一致，按这条路径直接加载会查不到键；本轮未执行完整上游包。
   适配层应明确处理别名，保留原始厂家 JSON 和提交/哈希记录，不能只改文件名冒充适配完成。
2. 飞特 [BAM 适配器](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/bam/mjlab.py)
   已有 `friction_scale_range` 和一次摩擦预算缩放。
   Pollen [同名薄封装](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/actuator/friction_dr_bam.py)
   是针对其基类写的；原样套到飞特分支会覆盖 startup 抽样，并可能将同一系数乘两次，得到 `scale²`。
   项目应选择唯一的缩放位置，仅按需补 setter/reset 或每回合重采样。
3. 飞特与 Rhoban 所核对版本的 [mjlab extra 依赖](https://github.com/ftservo/ftservo-bam/blob/4f7c0b0de3debf9c1ab254fc9654676e8aab9317/pyproject.toml)
   仍为 `mjlab>=1.3,<1.4`、MuJoCo/Warp 3.7 系列和 `warp-lang>=1.12,<1.13`，
   与本项目 1.6.0 / 3.11 系列冲突。不能直接安装该 extra、降级项目或靠 lazy import 宣称兼容。
   候选路线是固定 BAM core 来源，在本项目适配 mjlab 1.6 生命周期，再经 CPU/GPU 实测确认。

**目标文件应承担的职责。** 当前 `friction_dr_bam.py` 为用户新增空文件，仓库未声明 BAM 依赖。
建议将模型本体与 DR 薄封装分开：

| 位置 | 计划职责 |
|---|---|
| `actuators/HD_1910_C001/bam_actuator.py` | `HD1910BamActuatorCfg` / `HD1910BamActuator`：经过验证的模型加载、别名处理和 mjlab 1.6 适配 |
| `actuators/HD_1910_C001/friction_dr_bam.py` | 在基类确有不足时定义 DR Cfg/Actuator；`build()` 返回运行实例，提供摩擦系数 setter/reset，明确重采样时机，保证只缩放一次 |
| 型号目录内的参数与来源记录 | 原始厂家 JSON、固定提交与哈希、模型版本/电压/固件假设；本机标定结果另存，不能覆盖来源 |
| 机器人配置与任务事件 | 精确绑定 `head_yaw_joint`、`head_roll_joint`、`mouth_joint`，注册字段展开和随机化；无刷仍用自己的 PD 配置 |

若兼容后的基类已有所需 DR 功能，此文件可只导出配置入口，不为了沿用 Pollen 文件名再加一层缩放。
底层适配需实现/核验 `ActuatorCfg.build()`、`Actuator.edit_spec/initialize/compute/reset`：
加载后不重复执行会重建参数的 BAM 内部模型初始化；只重置指定环境的历史力矩和延迟状态。
BAM 计算电机力矩并将干摩擦预算、粘性阻尼写入 MuJoCo `dof_frictionloss` / `dof_damping`，
由求解器处理摩擦，不在普通 PD 后随意减一项摩擦力矩。
初始化必须通过 `requires_model_fields` / startup 事件展开这些字段，验证每个环境有独立存储。
训练 spec 还应统一 XML 的 `damping=0.02`、关节力矩范围与 BAM 的参数归属，避免重复阻尼或隐藏限幅。

验证顺序：先固定 7.4 V、关闭 DR/延迟，以厂家参数作有来源的候选，核对 JSON 加载、
控制器公式、参数范围与张量形状、子环境 reset；然后在小规模 GPU 多环境上检验阶跃/保持、
近零速摩擦、力矩范围、字段互不影响及有限值，再增加一次摩擦缩放和明确的延迟。
模型准确度最终用本机 7.4 V、实际固件模式/增益和带载电压的独立实机日志验证；
M6 不因参数更多就自动优于 M1/M4，需要比较留出轨迹。
本轮交付为调研与适配设计，保留空文件及现有依赖，不将未执行的动态验证写为通过。

### T009 实现并验证 HD1910 的 mjlab 1.6 适配器

目标：在 mjlab 1.6.0 上以可追溯的 HD1910 模型驱动三个舵机关节，并提供可复现的短响应证据。

范围：落实 T008 的模型加载/别名修正、兼容适配和必要的 DR 薄封装；采用外部依赖时固定来源，
按安装工具更新并验证 `pyproject.toml` 和 `uv.lock`。实现前记录实机模式和增益；
未读回的值只可作为明确的仿真假设，不能标为实机配置。

用户于本轮明确要求实施，范围调整为自包含的 HD1910 M6 模型、mjlab 1.6 执行器及可重复的
CPU/GPU 测试台，不安装旧版 BAM extra，不以未完成的 T001/T002 阻塞独立组件实现。
电压 7.4 V 是用户方案；`kp_fw=32` 和厂家控制器为初版仿真假设，实机模式/增益尚未读回。
本次不更改原始 MJCF 或添加未经验证的全机器人控制参数。

验收条件：`make check` 通过；CPU 参考计算/参数加载与局部 reset 检查通过；
小规模 GPU 多环境阶跃与保持、字段独立性、限幅和 reset 检查通过；
关闭 DR 的确定性基线先通过，再验证摩擦仅缩放一次；实机准确度与仿真功能验收分别记录。

实现结果：

- `actuators/HD_1910_C001/model.py` 提供冻结、校验后的 M6 参数和独立 Torch 公式。
  接受明确的 `hd1910` / `HD1910` 别名；仅支持 HD1910 M6，其他模型不静默回退。
  参数 JSON 按原始字节随包保存，附固定来源、SHA256、NOTICE 和 Apache-2.0 许可证。
  不引入 BAM 依赖或旧 mjlab extra，依赖声明与锁文件保持不变。
- `bam_actuator.py` 实现 mjlab 1.6 的配置工厂、spec 修改、初始化、compute、post-step update 和 reset，
  通过原生 `dof_frictionloss` / `dof_damping` 处理摩擦，提供 `bam_init` 字段展开事件。
  仅支持 hinge 关节，拒绝重复执行器，统一主动执行器与关节总力矩限幅，覆盖 XML 中被动参数。
  外载荷从上一解平滑力中移除主动/被动力，再合入排除自身干摩擦的约束力，纳入直接外力和映射后的身体外力。
  reset 后旧求解载荷保持无效，直到 `update()` 确认新物理步完成；单纯重复写控制不会令旧载荷重新有效。
- `friction_dr_bam.py` 实现 `FrictionDRBamActuatorCfg` / `FrictionDRBamActuator`。
  默认关闭 DR；配置范围后启动与每回合仅对选定环境重采样，同组关节共享系数，干摩擦只缩放一次。
  `set_friction_scale()` 支持标量或每环境系数；`reset_friction_scale()` 恢复 1，
  `reset()` 则按配置重采样并清理相应历史；粘性阻尼不参与该缩放。
- M6 二次摩擦项按上游 `bam/model.py` 的辨识公式实现，补上厂家 GPU 适配器遗漏的符号/等幅条件，
  不是未经说明地复制存在差异的 GPU 公式。厂家 JSON 的零位和台架延迟保留为元数据，未自动施加；
  mjlab Entity 自带的物理步延迟仅使用一次。
- README 提供用 `SERVO_JOINT_NAMES` 配置三个舵机及 startup 事件的示例。
  `tests/test_hd1910_actuator.py` 为 CPU 专项测试，`tools/check_hd1910.py` 为可重复的三关节多环境测试台。

边界：7.4 V 为用户方案；`kp_fw=32`、P 电压控制加反电动势及默认约 `1.471 N·m` 峰值限幅是有来源的
仿真假设，尚未读回实机固件设置；不包含独立固件 D 项或持续力矩/温升模型。
模型在实机 7.4 V 的阶跃与负载数据上是否准确仍待标定。
原始全机器人 MJCF 仍 `nu=0`，未把独立组件验收写成全机器人集成、站立或训练验收。

### T010 补充 HD1910 执行器目录说明

目标：在 `src/ht_microduck/actuators/HD_1910_C001/README.md` 提供就近可读的模块说明与使用指南。

范围：说明目录结构、控制与摩擦模型、配置字段、实体/事件接入、DR 与 reset、验证命令和参数来源；
仅新增目录文档并更新本任务记录，不改变执行器行为或依赖。

验收：独立只读核对文档与实现；检查本地链接、Python 示例和命令入口；
在项目内设置临时目录及 pytest `--basetemp` 后执行 `make check`，不新增文档专用测试；
检查进程及子代理结束后清理临时产物和项目字节码缓存。

### T011 编写机器人常量模块的混合驱动器配置

目标：在 `ht_microduck_constants.py` 返回可交给 mjlab articulation 的两组独立配置，
12 个无刷关节使用原生位置 PD，3 个 HD1910 使用现有 7.4 V BAM 模型。

范围：驱动器配置工厂、必要的使用说明、CPU 专项测试和小规模 GPU 检查入口；
不修改原始 MJCF、既有关节分组、依赖或完整机器人实体/场景。
无刷增益和力矩上限由调用方显式提供，区分模型假设、公开厂家拟合与本机标定。

验收：独立子代理只读核对 mjlab 1.6.0 接口及 XML 限幅/阻尼交互；
CPU 检查分组覆盖、配置独立性、参数校验、模型编译和 PD 力矩；
GPU 独立测试台验证 15 个关节的目标映射、两组限幅、阶跃/保持响应及有限值。
设置项目内临时目录和 pytest `--basetemp` 后执行 `make check`；
全部子代理与检查进程结束后清理本次临时产物和项目字节码缓存。

### T012 复核用户新增的随机驱动器延迟

目标：核对两组 `delay_min_lag=0`、`delay_max_lag=3`、`delay_hold_prob=0.4`、
`delay_update_period=10` 在 mjlab 1.6.0 中的实际行为，区分配置合法性与硬件建模依据。

范围：只读检查用户源码改动、已安装 mjlab 延迟实现、相关文档和测试；仅更新本任务记录，
不修改用户参数、源码、测试或 README。并行独立复核延迟语义及既有验收假设。

验收：记录随机延迟的单位、重采样/保持、分组共享和 reset 语义；
设置项目内临时目录后执行 `make check` 和已有 15 关节 GPU 专项，说明实际通过项或失败原因，
列出与新默认值不一致的说明和测试；全部子代理与检查进程结束后清理临时产物和字节码缓存。

### T013 同步随机延迟的测试、说明与运行期回归

目标：让当前 `(min=0, max=3, hold_prob=0.4, period=10)` 默认值与说明及验收一致。

范围：更新 `tests/test_robot_actuators.py` 的零延迟断言、constants docstring 和 README 的默认值描述；
在混合 GPU 检查中固化变化目标序列，覆盖无刷和 BAM 的历史目标映射及周期采样。

验收：`make check` 通过；固定种子下对两组配置检查 lag 范围、非零延迟、每环境更新周期，
逐步核对无刷 `ctrl=history[t-lag]` 和 BAM 对延迟位置目标计算的力矩；
保留 reset/限幅/静态响应检查，明确所有延迟参数仍为待标定的仿真假设。

完成情况：本任务的源码说明、README、CPU 断言和 64 步 GPU 变化目标回归已由 T016 一并落实；
统一检查及两组随机延迟映射通过，结果与命令见 T016 完成记录。

### T014 对照官方复核 robots 模块剩余缺项

目标：依据已实现的混合驱动器配置，对照 mjlab 1.6.0 官方机器人与实体接口，给出剩余代码清单和实现顺序。

范围：并行只读核对 `robots/`、官方 G1/Go1 配置、EntityCfg 和现有验证；仅修改本页记录，
不修改机器人行为、用户延迟参数、测试或 README，不跳过 T001/T002 的阶段依赖。

验收：结论附当前代码与固定版本官方源码依据，区分必需配置、按需扩展和任务层职责；
执行 `make check` 并如实记录现存失败，单独补跑未执行的模型检查；
使用项目内临时/缓存目录、pytest basetemp 和无字节码模式，全部子代理及检查结束后清理。

对照结论（2026-10-23）：

本次“官方”按项目固定版本的 mjlab v1.6.0 理解，对照
[G1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_g1/g1_constants.py)、
[Go1 配置](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py)
和 [Entity 文档](https://mujocolab.github.io/mjlab/v1.6.0/source/entity/index.html)。
当前 `get_spec()` 的直接 XML 加载、12+3 关节分组、返回独立执行器配置均已具备；
T004 原结论中“混合执行器待实现”的部分已由 T009/T011 完成，剩余主要是整机装配与接触配置。

| 内容 | 当前情况 | 还需编写或明确的内容 |
|---|---|---|
| 机器人配置工厂 | 无 `EntityCfg` 公共入口；只有测试临时组装 | 在 constants 模块增加 `get_ht_microduck_robot_cfg()`，每次组装新的 `EntityCfg`、初态与 articulation；沿用调用方显式传入无刷参数的约定 |
| 初始状态 | XML 基座高 `0.167 m`，没有 Python 初态或 XML keyframe | 显式 `EntityCfg.InitialStateCfg`：根位置/四元数、根速度、15 关节默认角度和速度；初态要经过足底接触与关节范围检查，不能声称全零即可站稳 |
| articulation | 已有 `get_actuator_cfgs()`，尚未在机器人公共配置中接入 | 工厂内调用 `EntityArticulationInfoCfg(actuators=...)`，验证 15 个执行器和既有顺序；软限位系数可以显式配置，非必填 |
| 模型与场景归属 | 原始 MJCF 同时含机器人、地面和灯光 | 保留独立检查入口，为实体增加只返回机器人内容的 spec 加载入口，或拆出预览场景 XML；地形和环境照明交给场景管理（T039 已移除本体中的地面与灯光） |
| 碰撞与摩擦 | 机器人 10 个碰撞 geom 均无名，脚部采用 MuJoCo 默认摩擦 | 为脚部及其他关键碰撞体命名，明确完整碰撞/自碰撞策略和摩擦假设；再使用 `CollisionCfg` 等配置。现有 XML 碰撞可用于最小加载，但尚未验证整机接触响应 |
| 足端参考点 | 当时 `nsite=0`，`nsensor=0` | 已在 T037 补齐：足底 `r_foot`/`l_foot` site、`imu` site 与 5 个内置传感器；接触/足高传感器仍按任务在场景配置 |
| 包导出与预览 | robots 顶层空，型号 `__init__.py` 只有说明；工具仍检查被动源模型 | 公共工厂落实后按需导出；另提供装配后 `nu=15` 的场景创建/reset 检查，保留原始 `nu=0` 检查用途 |

灯光统一管理是本项目的场景约定，并非 mjlab 硬性限制；官方机器人 XML 也可以携带灯光。
`CollisionCfg` 默认关闭未匹配 geom 的碰撞，因此命名和策略要一起落地，
不能把官方脚部正则直接套到当前无名 geom，或将多套互相覆盖的碰撞策略一起注册。

两项已有风险通过 CPU 静态组合实际复现：

- 原始模型的 `qpos0` 根高度为 `0.167`，直接用默认 `EntityCfg(spec_fn=get_spec, ...)`
  生成的 `init_state` keyframe 根高度为 `0.0`；后续 reset 使用该初态会放错高度。
  依据为 [EntityCfg 默认值及 keyframe 实现](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/entity/entity.py)。
- 将原始 spec 放入含平地 terrain 的 `Scene`，编译得到两个 plane：`robot/floor` 和 `terrain`，
  共两个灯光。原始 XML 中的地面随机器人组合进入场景，不能直接复用为训练机器人资源。
  （T039 已解决：地面、灯光与天空盒从本体移除，改由 mjlab `Scene` 提供。）

不能照搬的官方参数和模块边界：

- 官方 G1/Go1 用 `soft_joint_pos_limit_factor=0.9`，接口默认为 `1.0`；这是软限位信息，
  不会更改 MJCF 硬限位，也不自动裁剪动作。`mouth_joint` 的硬范围为 `[0, 0.33]`，
  若全局取 `0.9`，软范围成为 `[0.0165, 0.3135]`，全关节软限位奖励可能惩罚正常闭嘴姿态；
  应在任务中明确奖惩关节子集与目标范围，而非机械复制数值。
- 官方 `ACTION_SCALE = 0.25 * effort_limit / stiffness` 适用于其原生位置 PD 配置；
  HD1910 的 `kp_fw` 是固件模型增益，不能代入 SI 刚度公式。动作子集、最终顺序、
  每关节角度缩放、偏置/裁剪、物理步长与控制降采样由任务配置落实，robots 可提供有依据的参考值。
  本版本 JOINT action 走自然关节顺序，不能仅靠声明 tuple 或 `preserve_order=True` 推定任意自定义顺序；
  接入时应验证实际解析目标和策略通道映射，依据为
  [action 实现](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/envs/mdp/actions/actions.py)
  与 `Entity.find_joints_by_actuator_names()`。
- BAM 的 `bam_init` startup 事件或独立 Simulation 的字段展开仍需由环境/检查入口配置；
  返回 `EntityCfg` 不等于已经执行初始化。观测、奖励、终止、事件和控制周期放任务层，
  PPO、Storage、Runner 放本项目对应模块，不塞进 robots，也不改用官方 RSL-RL 训练链路。
- 当前无刷统一标量增益可作首版显式仿真假设；后续按腿部、颈部、头部负载分组扩展。
  反射惯量、速度/持续力矩和延迟分布需硬件依据或标定，不从 G1/Go1 复制未知数值。

当前已知说明/测试不一致仍由 T013 处理：`constants.py:74` 和 README 声称默认零延迟，
`tests/test_robot_actuators.py:66` 断言两组 `min=max=0`，实际两组均为 `(0, 3, 0.4, 10)`。
现有 GPU 工具主要使用 reset 后首个目标和恒定阶跃；首写会回填延迟历史，因此映射探针能通过，
但不能据此验收稳定历史下的随机延迟，需要固化 T012 已验证的变化目标检查。
另将 `tools/check_robot.py:49` 的“下一步添加两组 PD 执行器”提示记为 T002 接入时同步项：
应说明源 MJCF 保持被动，混合执行器已由配置提供，避免误称三只 BAM 舵机为普通 PD。

建议执行顺序：先 T013 同步已有验证与说明，再 T001 整理基线，按 T002 落实初态、
机器人 spec 与实体工厂及小规模 GPU 场景 reset；在后续 M1 任务接入现有混合驱动器，
验证整机接触、保持响应和限幅，再建立动作/观测/奖励等任务配置。
本次仅完成缺项评审，不将 CPU 组合编译、独立执行器测试台或官方配置对照视为整机 M1 验收。

### T015 对照 MicroDuck 官方评审 robots 模块

目标：以 `pollen-robotics/microduck_rl` 的固定提交对照本地 `robots/`，明确已实现、必需补充及按需扩展的内容。

范围：并发只读核对本地机器人、官方机器人配置与其任务层引用；仅更新本页，保留源码、测试、README、
用户延迟参数和依赖。不将官方舵机参数、默认姿态、动作顺序或训练链路直接移植到本机混合驱动机器人。

验收：报告附官方固定提交链接和本地代码位置，区分机器人配置与任务层职责；
在项目内临时目录和无字节码模式下执行 `make check`，如实记录现存失败，单独补跑被跳过的模型检查；
所有子代理及检查进程结束后清理本次临时产物与项目字节码缓存。

对照结论（2026-10-23）：

本次按用户指定，以 Pollen 官方 `microduck_rl` 默认 `develop` 分支固定提交
`b02fdea4902c2b93b7d34a83a6f05da4ececb7d3` 为参照，区别于 T014 的 mjlab 官方示例对照。
主要来源为[机器人配置](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py#L116-L210)、
[行走模型](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/robot_walk.xml)、
[独立预览场景](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/scene_walk.xml)
和[速度任务](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)。
行号采用原始文件物理行，网页正文抽取后的行号可能不同。

当前 `robots/` 已具备模型加载、关节/电机映射及混合执行器工厂；核心缺项是可直接用于场景的整机配置。
不需要重新编写已经完成的 HD1910 模型，也不要求把执行器手写进原 XML。

| 优先级与内容 | MicroDuck 官方实现 | 本地还需要写什么 |
|---|---|---|
| 必需：整机实体入口 | constants:202 的 `MICRODUCK_WALK_ROBOT_CFG` 组装 spec、初态、碰撞和 articulation | 在现有 constants 中增加 `get_ht_microduck_robot_cfg()`，调用已有 `get_actuator_cfgs()`；每次返回新配置，继续要求调用方显式提供无刷增益和限幅。当前测试里的临时 `EntityCfg` 不代替公共入口 |
| 必需：显式初态 | constants:116 的 `HOME_FRAME` 声明关节默认姿态；任务:388 另设 reset 根高度 | 定义本机根位置/四元数、关节角及速度。CPU 实测源模型根高 `0.167 m`，默认 Entity 的 `init_state` 根高却为 `0.0 m`；需验证足底位置、关节范围及接触，不复制官方角度或高度 |
| 必需：机器人与场景分离 | `robot_walk.xml` 不带地面，`scene_walk.xml:20` 起另配地面、灯光 | 保留 `get_spec()` 的原模型预览用途，新增去除预览地面的机器人 spec 入口。当前 XML:129 带 `floor`，直接组合 terrain 会重复；灯光按本项目场景约定统一管理 |
| 整机接触前明确：碰撞规则 | constants:142 的 `FULL_COLLISION` 依赖命名的脚部碰撞体，配置摩擦和接触维度 | 本机 10 个机器人碰撞 geom 均无名，双足位于 XML:52、80，采用默认摩擦。先为关键 geom 命名，定义摩擦、自碰撞和接触策略，再配置 `CollisionCfg`；不能直接套官方正则，否则未匹配 geom 默认会被禁用 |
| 行走任务按需：足底参考点与传感器 | XML 有 `left_foot/right_foot`、`imu` site 和 IMU sensor；任务:217 起配置接触和足高传感器 | 本机已按 T037 补足底 site、`imu` site 与 5 个内置传感器，命名对齐官方；接触与足高传感器仍在任务场景配置 |
| 验收：完整机器人场景 | constants:320 起提供场景预览入口，任务层实际使用整机配置 | 为本机新增真实机器人小规模创建/reset/短步进检查，验证根状态、关节状态、15 个执行器和接触。当前 `check_robot.py` 只静态编译；混合执行器工具使用独立铰链台架，不能证明整机已能站立 |

适配边界和按需扩展：

- 官方所选 walk 模型有 14 个主动关节、XL330 BAM；本机有 15 个主动关节，采用 12 无刷加 3 HD1910。
  官方主动关节数、关节名称/正负方向、姿态和电机参数不能直接采用。
  官方[依赖声明](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/pyproject.toml#L15-L19)
  固定 `mjlab==1.3.0`、`warp-lang==1.12.0`；本机继续使用 mjlab 1.6.0，按其实际接口适配，不降级依赖。
- 官方动作 `scale` 在速度任务:273 配置，不在 robots 常量中定义通用公式。动作子集、实际通道顺序、
  偏置/裁剪、物理步长和降采样仍放本项目任务层；`kp_fw` 不能当作 SI 刚度代入 PD 缩放公式。
  未纳入策略动作的头/嘴关节如需保持，仍应初始化并持续提供目标，初态不等于保持控制。
- 官方任务:364 配置 BAM 字段展开 startup 事件；本机已有 `bam_init`，完整环境仍需注册，
  单独返回实体配置不代替运行期初始化。观测、奖励、终止、随机化和训练模块继续按本项目分层实现。
- 官方另有 groundcontact、allcollisions、backlash、rollers 等模型变体；首个平地任务不需要全部补齐。
  后续只有确需倒地接触、已测间隙或轮式任务时再增加。无刷分负载增益、反射惯量、速度曲线和延迟分布
  依据本机参数或标定扩展，不为对齐官方文件数量而填写未知值。

现存同步问题仍由 T013 处理：constants:74 和 README 的默认零延迟说明、tests/test_robot_actuators.py:66
的零延迟断言，与实际 `(0, 3, 0.4, 10)` 不一致；本轮不更改用户参数。
建议先完成 T013，再按 T001/T002 补整机工厂、显式初态和机器人专用 spec，随后验证接触与任务所需足底参考点。

### T016 实现整机机器人配置与最小场景验证

目标：提供可复用的整机 `EntityCfg` 工厂，在 mjlab 1.6.0 小规模 GPU 场景中创建、重置并短步进。

范围：机器人专用 spec、显式模型初态、关键碰撞命名及完整碰撞规则、按几何确定的足底 site、
公共导出、真实机器人场景检查；同步 T013 的延迟断言/说明和变化目标回归。保留原始 XML/mesh、
现有 12+3 分组及用户选定的延迟参数。无刷参数继续显式传入，新增数值均标明仿真假设及几何依据。
不安装依赖，不改用外部训练链路，不提交 Git，不将未知实机姿态或 IMU 安装参数写成确认值。

验收：`make check` 通过；CPU 验证源模型独立、实体初态/关节限位/碰撞/site 和单一地面；
GPU 小规模真实场景验证状态、目标映射、局部 reset、接触及短步进有限值；混合铰链 GPU 检查保留
限幅/响应并覆盖变化目标下的两组随机延迟。全部验证使用项目内临时目录和无字节码模式，
所有代理与检查进程结束后清理本次临时产物及项目字节码缓存。

实现结果：

- `get_robot_spec()` 在新 spec 上移除地面/灯光、命名全部 10 个现有碰撞体并添加 `r_foot/l_foot`
  足底 site；原 XML/mesh 和 `get_spec()` 保留。足底坐标依据本机编译网格的最低水平面中心确定，
  不是实机压力中心或传感器安装位置。
- `get_ht_microduck_robot_cfg()` 组装每次独立的 `EntityCfg`、初态、articulation 和单套完整碰撞规则，
  两层包导出公共工厂。保留无刷显式参数和原有 12+3 顺序、用户延迟配置；支持深拷贝的 `init_state`
  及 `(0, 1]` 的软限位系数，默认 `1.0` 兼容闭嘴边界。
- `NEUTRAL_FRAME` 显式根高 `0.167 m`、单位四元数、15 关节零位和零速度。
  CPU 独立几何查询证明双足离地约 `3.759 mm`、初态无接触、投影 COM 位于足底支承条带；
  这些是模型几何条件，不是稳定站立证据。碰撞参数显式沿用源默认值，视觉 geom 保持不碰撞。
- `tests/test_robot_entity.py` 新增实体/场景、初态深拷贝、限位、源模型保留、碰撞资格、足底真实网格
  和接地查询测试。`tools/check_robot_scene.py` 使用真实自由基座机器人、平地和双足接触传感器，
  首次控制前展开 BAM 字段，显式恢复物理状态和全部目标；验证非零颈部初态及局部 reset 隔离。
- T013 的旧断言和说明已同步；混合铰链工具新增 64 步变化目标，验证两组真实延迟历史、当前反馈、
  每环境更新相位和非零延迟的可见效果。README 添加实际用法，源模型工具提示改为无刷 PD / 舵机 BAM。

边界：本轮未填未知实机 IMU 位姿、按负载标定的无刷增益、速度/持续力矩曲线或电气延迟分布。
动作/观测/奖励/控制降采样与训练组件仍留在任务层。下一项为 T001 整理基线；其后复核 T002，
再以本机参数单独验证全身保持与更长的短站立，而非直接进行长时间训练。

### T017 修复 constants 直接运行的整机预览入口

目标：用户原命令可以打开带地面的静态整机场景，无刷参数来源和预览职责明确。

范围：修正新增 main 块的漏参，预览入口以明确的仿真检查参数调用工厂，保留工厂必填参数；
组装单一平地及初始化状态，以 passive viewer 显示，不绕过 Python BAM 使用原生自动步进。
按用户指定的 `ri_4438_constants.py` 简化，仅留简短 main 块，去除 CLI、打印、相机定制和重复说明。
不修改用户延迟、机器人参数、源 XML 或依赖。

验收：`make check` 通过；用户同一路径的 main 块编译得到 `nu=15`、单一地面，
有图形显示时实际启动并关闭预览验证 GUI 可用；如图形环境受限则如实记录。
所有临时内容和 TMPDIR 均在项目 `.artifacts/` 内，代理与检查进程结束后清理缓存及本次临时产物。

### T018 按官方风格集中定义机器人配置

范围：模块级两组执行器、初态、碰撞和整机配置；简化预览使用方式、同步公共导出/调用说明，
保留工厂返回独立副本和参数覆盖，保留用户延迟与模型。默认无刷 `10/0.4/2` 仍为仿真假设。
验收：`make check`；默认配置/副本隔离检查；4 环境 GPU 场景短跑；原路径 GUI 打开和关闭。
本轮不修改依赖或提交 Git，全部验证临时内容置于项目 `.artifacts/`，结束后清理。

### T019 整理机器人常量模块的代码风格

范围：参照用户指定文件，按 MJCF、关节映射、执行器、初态、碰撞、最终配置和预览分区，统一排版与简洁注释。
仅修改常量模块和任务记录；不新增功能、参数或测试。验收为 Ruff 格式/检查、AST 语义与定义依赖复核、
`make check`；纯代码整理不重复 GPU/GUI 运行，沿用 T018 运行证据。验证临时内容均在项目内并于结束时清理。

### T020 对照 Microduck 官方简化机器人参数配置

目标：参数在模块级执行器/初态/碰撞配置中直接可见，使用整机配置无需逐层传入同一批关键字参数。

范围：并发只读核对 Pollen Microduck 官方参数及 ri_4438 参考风格，简化常量模块、迁移内部调用与测试，
同步 README 和来源记录；保留 12+3 分组、用户延迟、原始模型及 mjlab 1.6.0，不引入未知硬件参数。

验收：记录官方配置的准确来源及与本机硬件的差异；`make check`、Ruff 格式检查、
配置副本隔离/模型编译/PD 行为检查通过；在 GPU 上运行混合执行器和真实机器人小规模短检查。
本次不安装依赖、不提交 Git；临时目录和缓存仅在项目 `.artifacts/`，所有代理及进程结束后统一清理。

官方参数核对：以 [Pollen 官方固定提交 b02fdea 的常量模块](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck_constants.py)
为依据，直接定义初态、碰撞、BAM 执行器和 `EntityCfg`；没有本项目原先的两层参数覆盖工厂。
用户给出的 `legged_wbc_mjlab/src/assets/robots/ri_4438/ri_4438_constants.py`
也采用模块级配置和无参整机入口，其增益来自独立 `Ri4438Cfg.control`。
本项目当前直接保留 mjlab 配置对象，不再另建一套参数类。

| 项目 | 官方 Microduck 的配置 | 本机继续采用的配置与依据 |
|---|---|---|
| 执行器 | XL330 M6，`kp_fw=200` | 12 个 HTDW 原生 PD 加 3 个 HD1910 M6；无刷 `10/0.4/2` 为检查假设，舵机 `kp_fw=32` 来自飞特控制模型假设 |
| 供电 | `vin_range=(6.5, 8.2)`、压降系数范围 `(0, 0.2)`、最低 `6 V` | 舵机 `7.4 V` 为用户方案，未新增无刷供电模型或电压随机化 |
| 延迟 | `3–6` 个物理步 | 用户选定的 `0–3`、保持概率 `0.4`、更新周期 `10` 保留，待实机标定 |
| 初态/接触 | 官方关节角、脚部 `condim=3`、其他碰撞体 `condim=1`、软限位 `0.9` | 保留本机模型零位、高度、碰撞配置和软限位 `1.0`，不照搬不同结构的姿态和参数 |

兼容性变化：删除 `get_actuator_cfgs()`、`get_ht_microduck_robot_cfg()` 的关键字覆盖参数、
场景检查的 `--brushless-*` 选项和 `NEUTRAL_FRAME` 别名。整机入口只深拷贝，初态统一叫 `HOME_FRAME`；
任务在独立副本上直接改字段，台架用 `dataclasses.replace()` 设置测试专用值。
旧标量入口的数值域校验随接口移除，不再承诺覆盖参数会自动校验；直接配置需保持有限合法增益和限幅、
软限位系数 `(0, 1]` 及无刷执行器限幅不超过原模型 `3.7 N·m` 的约束。
XML 的总力矩限幅保留，CPU 检查验证默认值与编译后的双向限幅及零主动阻尼边界。

### T021 对照 Microduck 梳理训练与实机部署缺项

目标：对照用户指定的 `pollen-robotics/microduck` 及其关联的 `microduck_rl`，
区分已有能力、训练链路缺项、sim2real 标定和实机运行缺项，给出按依赖排列的可执行后续任务。

范围：并行只读核对上游实机运行和训练代码，主代理核对本地代码并更新本页；
保留独立包、mjlab 1.6.0 与本地 PPO/网络/Storage/Runner 的既定方向，不实现新行为。

验收条件：

- 记录上游核对版本及源码链接，区分上游配置事实与本机硬件假设。
- 每项缺口给出本地现状、优先级、依赖及可执行验收方式；避免重复实现已交付的整机工厂和执行器。
- 执行项目内临时目录隔离的 `make check`；不将静态检查写成训练或实机运行证据。
- 所有子代理与检查进程结束后，删除本次临时产物和项目字节码缓存并复查。

核对版本（2026 年 10 月 27 日）：

- 实机仓库 [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)。
- 关联训练仓库 [microduck_rl@1e79c29](https://github.com/pollen-robotics/microduck_rl/tree/1e79c29c97d8b38aee9eefde77a545860ba7658e)。

**已有基础可以继续使用。** 模型加载、15 关节映射、12 无刷 PD 加 3 个 HD1910 M6、
整机实体、碰撞/足底参考点及短 GPU 场景检查已经实现，不再重复列为缺项。
本次重新验证的源模型质量为 `3.2893 kg`，不是实机称重结果；上游约 `0.8 kg`。
当前 `150 × 0.002 s = 0.3 s` 场景检查只验证接线、有限值、接触、限幅与 reset，
不能作为稳定站立、可训练环境或已学会行走的证据。

| 能力 | 官方参考与本地现状 | 后续工作 |
|---|---|---|
| 任务控制与观测 | 官方策略为 61 维输入、14 维输出；本机只有 15 关节实体，没有任务契约 | T022 固定动作子集/顺序、HOME、缩放、坐标系、上一动作含义、归一化及控制时序 |
| 平地环境 | 官方有 commands、actor/critic 观测、奖励、终止与课程；本机尚无 `tasks/` | T023 先实现站立命令和平地速度跟踪，验证多次 reset/step |
| 训练算法与入口 | 官方使用 mjlab/RSL-RL；本机入口仍为 pyproject 注释，网络、Storage、PPO、Runner 均未实现 | T024–T026 按既定架构在本仓库实现，先小规模短跑 |
| 评估与部署策略 | 官方有恢复、导出、CPU ONNX 回放；本机只有 export 可选依赖声明 | T027–T028 提供固定种子评估、完整恢复、带归一化的策略包与闭环回放 |
| sim2real 参数 | 官方按其 XL330 建模并做 DR；本机已有厂家 HD1910 参数和延迟/摩擦接口，未做本机标定 | T030 按两类执行器和 IMU 分别采集、拟合并验证 DR |
| 实机运行 | 官方有总线 I/O、IMU、状态机、故障处理、推理和日志；本仓库尚无对应模块 | T029、T031 接入本机硬件并分级验收 |
| 高级技能与产品服务 | 官方还有起身、蹲站、叼取、踢球、翻滚、轮滑及蓝牙/相机/OTA | 基础行走与部署通过后按需求另立任务，不作为当前训练前置 |

关键差异与源码依据：

1. [官方观测实现](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/obs.rs)
   使用角速度 3、重力 3、相对关节位置 14、速度 14、原始上一动作 14、命令 13，共 61 维；
   嘴独立控制，不进入策略动作。官方顺序为左腿、颈头、右腿；本机 constants 为右腿、左腿、颈头、嘴，
   不能复制索引、维度或权重。首版建议双腿 10 动作，其他 5 关节显式保持，这是待 T022 确定的任务选择。
2. [官方训练依赖](https://github.com/pollen-robotics/microduck_rl/blob/1e79c29c97d8b38aee9eefde77a545860ba7658e/pyproject.toml)
   固定 mjlab `1.3.0` 和 Warp `1.12.0`；本机继续 mjlab `1.6.0` 与本地算法，参考任务设计而不照搬依赖/API。
3. [官方控制器](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/control.rs)
   按 `HOME + scale × action` 生成目标，另有滤波与模式处理。训练、回放、部署的裁剪和滤波顺序必须一致。
   官方策略 50 Hz 只是参考；若本机最终选择 `dt=0.002 s` 和 50 Hz，则 decimation 为 10，尚非已定控制参数。
4. [官方导出](https://github.com/pollen-robotics/microduck_rl/blob/1e79c29c97d8b38aee9eefde77a545860ba7658e/scripts/export.py)
   将观测归一化嵌入 ONNX，并附元数据；本机也应导出完整推理处理，不能只转换裸 actor 权重。
5. 官方 [I/O](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/io.rs)
   面向 Dynamixel 总线；[IMU](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/imu.rs)
   和[故障处理](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/safety.rs)
   可参考接口和测试方法。本机实际无刷协议、飞特总线、IMU 安装和控制板尚需确认，不能将官方总线、
   安装旋转、增益或故障阈值作为本机已确认数据。源码允许短暂沿用旧传感样本，部分旧设计文字要求当步新鲜样本，
   以[当前主循环](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/main.rs)
   为核查依据，不复制其容忍时长。

推荐顺序：T001 → 依据 T016 证据关闭 T002 → T022 → T023 → T024 → T025 → T026 → T027 → T028。
硬件路径为 T022 → T029 → T030，最终由 T031 汇合训练导出与实机证据。
新增待办不改变 M0/M1 当前验收状态；T029–T030 是可在契约确定后开展的独立硬件工作，
不代表训练阶段已通过。T031 在 M3、仿真性能门槛和硬件标定均通过后验收；这些任务尚未启动。

### T022–T031 后续任务的产物与验收

以下命令为待实现接口建议，当前不能直接运行；开工时确定最终参数并写入对应任务。
全部实现任务继续要求 `make check`，GPU 与硬件专项验证须另行保留实际运行证据。

| 任务 | 具体产物 | 专项验收方式 |
|---|---|---|
| T022 | 首版控制/观测配置及 `tools/check_task_contract.py` | `uv run --no-sync python -B tools/check_task_contract.py --device cuda:0`；逐关节脉冲验证映射，4 环境按任务周期运行数秒，检查非策略关节保持、限幅、历史与局部 reset；冻结单位、时序、偏置/缩放和处理顺序 |
| T023 | `tasks/` 中的平地速度环境及 `tools/check_velocity_env.py` | `uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0`；4–16 环境反复 reset/step，验证观测/动作/奖励有限值及形状、跌倒/超时区分；actor 只用实机可得量，真值线速度/接触可供 critic 或奖励使用 |
| T024 | 本地 actor/critic、观测统计、Storage 和 GAE | `uv run --no-sync python -B -m pytest -q tests/test_networks.py`（Storage 与 GAE 测试同文件）；用可手算轨迹检查 return/advantage、真实终止与 timeout bootstrap，验证 log-prob/value 形状和批次覆盖 |
| T025 | 本地 PPO 损失与更新模块 | `uv run --no-sync python -B -m pytest -q tests/test_ppo.py`；验证 clipping、熵、value loss、梯度裁剪与更新前后参数变化，有限梯度和 log-prob 一致性 |
| T026 | Runner、`duck-train`、配置/种子/指标记录和 checkpoint | `uv run --no-sync duck-train --num-envs 16 --iterations 5 --seed 0`；完成采样及数次 PPO 更新，loss/梯度有限、检查点可读且可恢复；记录零动作/初始策略基线，不以短跑宣称学会行走 |
| T027 | 恢复入口、`duck-play`、`duck-eval` 和评估报告 | 用同一 checkpoint 实际执行恢复训练、回放及固定种子评估；恢复网络、优化器、统计与迭代号，区分重启环境与精确轨迹续接；覆盖零速、前后、侧移、转向，报告跟踪误差、跌倒率、episode 长度与限幅统计；开工时冻结部署前的仿真性能门槛，未达标时先记录并按授权训练/调参，不能进入 T031 |
| T028 | `duck-export`、策略元数据、ONNX 一致性工具和 CPU 回放工具 | 实际执行 `duck-export`、`tools/check_onnx.py`、`tools/play_onnx.py`；同一观测集比较 PyTorch/ORT 并冻结误差容限，在 CPU MuJoCo 用同样的执行器、时序、观测、缩放/滤波闭环运行，避免换成理想 PD；确认 CPU 对 BAM 的适配 |
| T029 | 混合硬件后端、IMU 转换、状态机、FakeIo 和带时间戳日志 | `uv run --no-sync python -B -m pytest -q tests/test_runtime.py` 加目标板只读/单关节低幅度检查；验证零位、符号、单位、两类链路时序、IMU 坐标；注入断流、旧样本、NaN、推理失败和超期，检查启停、渐变与故障行为 |
| T030 | 两类执行器/IMU 标定配置、原始轨迹、对比报告和 DR 事件 | 用项目内保留的实测数据运行拟合/回放命令并交付该命令；对比延迟、超调、稳态误差、速度与饱和，核查质量/质心/惯量及摩擦；DR 范围注明测量或假设，验证 reset 不累积且环境独立；无数据时记录阻塞，先关闭相关 DR |
| T031 | 目标板时序报告及实机站立/低速跟踪记录 | 按空载/支撑、站立、低速命令分级运行，逐步记录命令与状态、跌倒/限幅、温升/供电和故障；完整环路 p50/p95/p99、超期次数满足 T022 控制周期；具体幅度、时长和阈值由本机标定及实机条件确定 |

T030 更新模型参数后须核对训练配置与实机契约；超出已训练、验证范围时，重做受影响的仿真、
训练、评估与导出。T031 只使用与最终标定配置匹配且通过仿真性能门槛的策略包，不能沿用过时导出结果。

稳定行走之后再评估起身、头部联合控制、复杂地形和其他技能。
上游产品层的 Rust 多服务、蓝牙、相机与更新系统不要求在本仓库完整复刻。

### T032 参考 quadruped_lab 完善工作流与忽略规则

目标：借鉴 `/home/sunteng/projects/quadruped_lab` 的按变更规模选择流程、模块边界、依据核查、
并发分工和独立审查规则，完善本项目可执行的开发工作流与 `.gitignore`。

范围：根开发约定、开发文档、必要的设计/审查模板、忽略规则、Makefile 和 README 入口说明。
保留现有架构、任务历史、用户已有修改和模型资源；不照搬参考仓库对 `tests/` 和流程文档的忽略规则。
检查入口统一使用项目内临时目录；如需恢复统一检查，仅修复已知的预览入口 import 排版，不改变行为。

验收条件：

- 工作流职责与链接一致，区分小修改与大功能、事实与假设、自审与独立审查，避免额外的常规审批。
- 用 `git check-ignore` 验证环境/缓存/构建/实验输出被忽略，源码、测试、流程文档、模型和锁文件可纳入版本控制。
- `make check` 通过，检查产物限定在项目 `.artifacts/`；审阅新增文件与已有未提交改动。
- 独立复核最终文件，所有代理和检查进程结束后清理本次临时产物及项目字节码并复查。

### T033 替换为用户提供的 HT-DK_URDF 模型

目标：将默认机器人模型替换为 `/home/sunteng/Downloads/HT-DK_URDF` 的模型与配套网格，
项目独立保存资源，不依赖 Downloads 路径。

范围：复用来源包已提供的 `xml/HT-DK_URDF.xml`，调整包内 mesh 路径与预览根高；替换配套 STL，
同步常量中的默认入口、碰撞名称、足底参考点和无穿地中性初态，更新已有测试与 README。
关节顺序及 12+3 电机分组不变，执行器增益、限幅和延迟继续沿用现有仿真假设。
属于机器人资源和几何参数调整，不新增训练或跨模块接口；由主代理实施、子代理只读核对来源与最终结果。

验收条件：

- 项目资源与来源 XML/STL 一致，仅 mesh 路径和预览根高作本地适配；从其他工作目录亦能编译。
- `make check` 通过；关节限位、足底 site、初态无穿地、碰撞体语义与来源模型一致。
- 使用正式 `check_robot_scene.py` 在 `cuda:0`、种子 `1910`、4 环境、150 个 `0.002 s` 步内验证
  目标映射、双脚接地、有限值、限幅、字段独立性及局部 reset；超时上限 180 秒。
- 所有检查临时目录限于 `.artifacts/`，独立复核后清理本次临时产物与项目字节码，保留已有修改。

### T034 对照 duck_project 评估无刷电机 NT 执行器

目标：根据 `/home/sunteng/projects/duck_project` 的实际电机曲线与实现，判断本项目是否需要
无刷执行器，以及可复用的逻辑、数据边界和最小实现范围。

范围：先读本地无刷 PD、关节与 XML 限幅，再核对参考项目电机数据、源图、运行时执行器，
并核对 mjlab 1.6.0 的现有执行器能力。用户已澄清“3530”指参考项目中的 HTDW-3532-02-DNE，
与本地已有电机名称一致，无需改名。此次先分析并记录结论，不提前实现新执行器。
由只读子代理核对参考曲线，主代理核对本地与上游接口，最后独立复核结论。

验收条件：

- 结论有源码/数据的版本、路径和具体位置，区分已验证事实、外部参考与仿真假设。
- 明确 NT 曲线的电压、轴端、单位、插值、四象限处理及与现有 PD、延迟、XML 限幅的关系。
- 给出是否新增执行器、模块边界、最小实现及专项验收建议，记录型号/实测参数缺口。
- `make check` 通过；分析与文档不新增测试、不重跑 GPU；结束后清理本次临时产物与项目字节码。

核对结论与后续最小实现：

1. **建议增加对应的 NT 限幅 PD 执行器。** 本地 constants 第 90–114 行已经声明 12 个 3532，
   但使用 `BuiltinPositionActuatorCfg`，只限制固定 `2 N·m`，没有速度相关包络。
   保留当前固定上限时，参考曲线在超过 `128 rpm` 后成为更严格约束；`167/211 rpm` 的驱动上限
   分别为 `1.5/1.0 N·m`，`300 rpm` 为零。低速行为可以保持，较高速驱动不再使用恒定力矩能力。
2. **迁移运行时曲线逻辑及有来源的数据。** 参考 `src/htdk/motor.py:6–17`、
   `src/htdk/actuator.py:23–44` 和 `src/assets/motors/htdw_3532_24v.json`；原始图片为
   `src/assets/motors/HTDW-3532-02-DNE_user_datasheet.png`。
   源图标示 24 V、减速比 32、额定 `0.6 N·m`、堵转 `3.7 N·m`、空载 `300 rpm`。
   锚点是图像采样后取整的近似，不是本机实测。单位已经是减速器输出轴 `rpm / N·m`，不能再乘减速比。

   ```text
   rpm:   0    26   59   92   128  167  211  258  300
   N·m:   3.7  3.5  3.0  2.5  2.0  1.5  1.0  0.5  0
   ```

   运行时用实际输出轴速度 `abs(dq) * 60 / (2*pi)`，在相邻点间线性插值，
   先用固定力矩上限限制 PD，再仅对 `tau_pd * dq >= 0` 的驱动象限应用 NT 包络。
   两个旋转方向镜像使用同一曲线；达到/超过 `300 rpm` 时同向驱动力矩为零，仍允许反向制动。
   制动上限暂沿用配置的固定力矩限幅，是参考实现的明确假设，源图没有再生/制动曲线。
   `0.6 N·m` 是连续额定值，不能把 `3.7 N·m` 堵转值称为可持续力矩；没有热参数就不新增热模型。
3. **通用 DC 模型不能原样保留这条曲线。** 已核对安装的 mjlab `1.6.0` 和官方固定版本：
   [dc_actuator.py:25–50](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/dc_actuator.py#L25-L50)
   使用直线包络。以 `3.7 N·m` 和 `300 rpm` 为端点、固定上限 `2 N·m` 时，
   其 `167/211 rpm` 上限约 `1.6403/1.0977 N·m`，不同于参考曲线的 `1.5/1.0`。
   超速时该电压包络还可能产生反向力矩，与参考实现的驱动归零规则不同。
   本地 `builtin_actuator.py:260–325` 的原生 DC 模型可用数据表三元组或 `Kt/Ke/R` 参数化，
   但它改变了电压/PID语义，也不能仅靠两个端点复现上述分段曲线，当前不选用。
4. **保持本机模块边界与硬件分组。** 建议在 `src/ht_microduck/actuators/HTDW_3532_02_DNE/`
   保存参数、来源说明和轻量 NT-PD 实现，基于 `IdealPdActuator` 复用控制与生命周期；
   在 constants 中装配 12 个无刷，3 个 HD1910 BAM 保持现有归属。
   参考项目只对双腿 10 个关节应用曲线，颈/头俯仰归入舵机且嘴固定，不能复制其关节分组。
   参考 `src/htdk/tasks.py:146–149` 的 `armature=0.002`、零延迟、`dt=0.004 s` 和控制降采样 5
   都不是本机标定数据；不照搬增益、惯量、延迟或任务参数。
5. **接入时需要同时核对数值与控制通道。** 第一版保留本地 `kp=10`、`kd=0.4`、
   固定上限 `2 N·m`、XML 总上限 `3.7 N·m`、被动阻尼 `0.02` 及 `0–3` 步命令延迟，
   继续注明仿真假设；不默认为堵转上限可持续输出，不重复加入摩擦。
   曲线计算留在 Torch 的原设备/类型，每物理步读取当前速度，目标延迟由 mjlab 处理一次。
   参考诊断 `analysis/nt_curve.py:59–85` 使用 CPU/NumPy，不用于逐步控制路径。
   mjlab 1.6 的 `IdealPdActuator` 通过 `control_law` 计算，参见
   [pd_actuator.py:55–68](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/pd_actuator.py#L55-L68)；
   本机 `IdealPdActuator`/`Actuator` 没有参考 `compute` 所调用的 `_clip_effort`，
   因而参考类不能原样复制，也不能只覆盖该方法；需使用当前的 `force_limit` / `control_law` 接口。
   可显式覆盖 `compute`，或遵循
   [fused_group.py:61–73](https://github.com/mujocolab/mjlab/blob/v1.6.0/src/mjlab/actuator/fused_group.py#L61-L73)
   的共享计算约定；按所选路径验证真实 Entity 调用，走融合路径时另核验参数与延迟一致性，
   不能仅直接调用函数算作集成通过。
   从原生隐式 PD 改为显式力矩输入后，需要重新跑短动态检查，旧场景结果不能代替。

参考目录没有 `.git`（根与 `src/` 均已检查）；2026-10-27 读取的内容 SHA256 为：

| 参考文件 | SHA256 |
|---|---|
| `src/htdk/motor.py` | `8225cbbf25383d65b08e08e8574ec971d13842e5a080a34d01f61384e77a651f` |
| `src/htdk/actuator.py` | `022fcd00d91907237a4e8659fc4c813ce755edf255f6174b79d0914971c9bbea` |
| `src/assets/motors/htdw_3532_24v.json` | `a0f102775e78a1a95a3c5d97bbd69c0a4c132f1d692d248fa310bbfd596f9447` |
| 原始资料 PNG | `56c8ac1a17ccbbf840591fefeec254b939477ff1cd8a9cb31220004cf11b9770` |

下一项可执行实现：先完善本主题设计，再增加上述小执行器与参数资源，替换无刷配置并同步专项工具/测试。
验收至少包括全部锚点与中点、一次单位换算、正负驱动/制动/超速、固定与 XML 限幅、
12+3 控制顺序、目标延迟和局部 reset，以及正式混合执行器和整机的有界小规模 GPU 短跑。
源图电压是 24 V 条件，实际带载电压、制动能力、摩擦/惯量和峰值持续时间仍需本机验证；
不凭源图推定其他电压下的完整曲线。

### T035 实现并接入 3532 NT-PD 执行器

目标：将 T034 的有来源输出轴曲线接入本项目 12 个无刷关节，在 PD 固定限幅后增加驱动象限 NT 限幅。
范围：新电机模块及参数资源、机器人装配、已有专项工具与相关测试、README；执行器和训练职责不混用。
详细接口、实施分工及验收见 [设计](design/htdw3532_nt.md)，独立审查见 [审查记录](review/htdw3532_nt.md)。

验收条件：

- `make check` 通过；曲线锚点/中点/单位与类型、正负驱动与制动、空载及超速、PD 三类目标和限幅有数值验证。
- 全部 15 个关节及 12+3 映射正确，XML 被动属性保留；实际 Entity 每物理步使用一次目标延迟和当前反馈。
- 种子 `1910`、`cuda:0`、4 环境：正式混合执行器工具 300 步加延迟回归，整机场景 150 步；
  每个入口超时 180 秒，另验证高速 NT 实际控制与局部 reset；不将完整训练作为默认验收。
- 独立审查通过，参数与原始来源随 wheel 打包；所有代理/检查结束后清理本轮临时产物和项目字节码。

### T036 对照三个参考项目确定下一步

目标：对照 pollen-robotics/microduck、pollen-robotics/microduck_rl 和本地 duck_project，
判断本仓库当前最该做的工作，并把结论落成有验收条件的后续任务。

范围：只读核对三个参考项目与本仓库现状；本轮只更新本页和 README 的下一步说明，
不修改机器人源码、参数、XML、依赖或测试，不执行训练与实机操作。

核对版本（2026 年 10 月 27 日）：

- [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)，默认分支 `main`，与 T021 记录一致。
- [microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3)，**默认分支是 `develop`**；
  T021 记录的 `1e79c29` 是 `main` 上的提交，比 `develop` 落后 76 个提交。以后引用该仓库必须注明分支。
- `/home/sunteng/projects/duck_project`：无 `.git` 的归档（代码 + 参数 + 报告，不含权重）。

**本机复核（只读探针，非验收）**

- `make check` 退出码 0：锁文件、Ruff、131 项测试与 8 项子测试、模型与差异检查通过；
  被动模型 `nq=22`、`nv=21`、`nu=0`、15 关节、16 网格、质量 `3.2947 kg`。
- 原模型不含任何 sensor：`nsensor=0`，只有 `r_foot`/`l_foot` 两个 site（由整机工厂添加）。
  官方 61 维观测的前三组依赖陀螺与重力方向，本仓库当时没有 IMU 声明（T037 已补）。
- HOME 零位几何：躯干高 `0.171 m` 时两足最低点各 `+3.84 mm`，脚底支撑面与水平面成 **5.00°**
  （左右各向外倾，`r` 法向 `y=-0.0872`、`l` 法向 `y=+0.0872`），单脚接地面积仅 `1.59 cm²`，
  接触多边形在 y 方向只有 `2.3 mm` 宽；重心投影距单脚支撑边界仅 `0.88/0.66 mm`，
  距双足联合支撑边界 `24.55 mm`。左右腿关节轴不镜像（左右同为正 `hip_pitch=knee=ankle` 轴），
  与 duck_project 的"右腿取负"约定不同。
- 把左右 `hip_roll` 各向内收 `0.0873 rad` 后，两侧脚底同时水平：支撑面倾角 `0.00°`、
  单脚接地面积 `30.02 cm²`、脚宽 `42.9 mm`、单脚重心余量 `5.19/4.97 mm`、站宽由
  `0.1556 m` 变为 `0.1355 m`，且不产生自碰撞。该姿态是几何解，不是已确认站姿。
- GPU（RTX 4060、`cuda:0`、种子 `1910`、4 环境、`dt=0.002 s`）零位保持 3 s：
  根高由 `0.1710` 沉到 `0.1655–0.1657 m`，倾角 `<1.5°`，两足全程有载，无跌倒。
  加 `hip_roll ±0.0873` 后根高 `0.1682 m`、倾角 `<1.3°`、两足全程有载，左右法向力 `17.0/15.3 N`。
- 同一保持测试的水平速度脉冲：`0.10 m/s` 后最大倾角 `2.02°`；`0.20 m/s` 时 `6.29°`；
  `0.35 m/s` 时倾角 `82–93°`、根高掉到 `0.06–0.09 m`，判定跌倒。零位站姿的稳定边界很窄。
- 全部测试增益仍为源码中的仿真假设（`kp=10`、`kd=0.4`、限幅 `2 N·m`），未做任何标定。

**参考项目的可取之处与不可照搬项**

| 参考 | 可取做法 | 不能照搬 |
|---|---|---|
| microduck_rl@develop | 观测/动作契约单点定义；导出把归一化烘进 ONNX；HF 上的策略 manifest 做 `[1,61]→[1,14]` 校验 | `mjlab==1.3.0`、`warp 1.12`、RSL-RL `5.0.1`；XL330 `kp_fw=200`、延迟 `3–6` 步；61/14 维与关节顺序 |
| microduck@main | 部署侧 `targets = HOME + scale × action`，并有 `legs_lowpass`、安全层（NaN 拒绝、超程 clamp、deadman 500 ms、跌倒判据） | Dynamixel 总线与 ID 布局、`scale=0.9/1.0`、`gain=200`、IMU 安装旋转 |
| duck_project | 量化口径（抬脚/前扫/打滑/单脚悬空 + 红线诊断）；N-T 软约束与验收统计；"改 default_joint_pos 会平移观测、破坏热启动"的经验 | 旧机 14 维动作、`scale=0.5/1.0`、`stand_z=0.163`、`sit_q`、8 mm 抬脚等全部旧几何阈值；其 v44 的 48 集评估 `success_rate=0.0`，不能当作成功基线 |

duck_project 归档中另有一处文档与数据冲突：`reports/README.md` 称 sitstand "达成率 96%"，
而 `sitstand_v46.md` 的实际统计是 `96/192 = 50%`，且该 run 目录下没有 `evaluation.json`。
引用它的结论时应以具体 JSON/数值为准，不引用概述性百分比。

**结论：下一步做什么**

1. **先收 Git 基线（T001）。** 当前只有 `README.md` 被跟踪，59 个未跟踪文件
   （含 16 个 STL、`uv.lock`、全部源码与测试）不在版本控制内，任何后续实验都无法回溯。
   这是 T022 及之后所有任务的前置，也是 T021 已记录的同一个阻塞点。
2. **补 IMU 声明（T037，已完成）。** 原模型没有任何 sensor，官方 61 维观测的前三组
   （陀螺、投影重力、线速度）在本仓库没有对应来源；没有它们，T022 的 actor 观测只能拿
   仿真真值，违反 T021 记录的"actor 只用实机可得量"。
3. **标定 HOME 站姿（T038，待办）。** 现有"全零关节"只满足"不穿地"，但脚底外倾 5°、
   单脚支撑 `1.59 cm²`、重心余量不到 1 mm，属于"能站但不该作为训练起点"的姿态；
   引脚外收 `0.0873 rad` 的候选站姿在几何与 3 s 保持上都明显更好，取向待用户确认。
4. **然后按 T022 → T023 推进契约与最小平地速度任务。** 契约需要冻结的内容比 T021 时更明确：
   动作是 10 维（双腿）还是 14 维（含颈头俯仰）、`HOME`、`scale`、上一动作含义、
   归一化、控制周期（`dt=0.002 s` 时 decimation 取 10 → 50 Hz 或 5 → 100 Hz）、
   以及"右腿不取负"对本机观测与奖励符号的影响。
5. **训练链路按 T024–T026 本地实现，不引入 RSL-RL**：架构方向仍是自研 PPO/Storage/Runner，
   但可以把 microduck_rl 的导出配方、duck_project 的量化验收脚本结构作为验收模板。
6. **T029–T031 的硬件工作继续等待本机协议/IMU/控制板信息**，T030 也不具备测量条件；
   在 T036 的调研范围内不调整这部分依赖关系。

### T037 在 XML 中声明 IMU 参考点与内置传感器

状态：完成。

目标：让被动模型与整机工厂都具备训练所需的姿态与角速度观测来源，命名与官方项目一致，
不把噪声、延迟和安装误差写进模型。

范围：`xmls/HT-DK_URDF.xml`（新增 `imu` site 与 `<sensor>` 块）、
`ht_microduck_constants.py`（`get_spec()` 说明；IMU 名称由工具与测试直接从模型读取）、
`tools/check_robot.py`、`tools/check_robot_scene.py`、`tests/test_robot_entity.py`；README。

依据（外部参考，2026 年 10 月 27 日核对）：

- [microduck_rl@b02fdea `sensors.xml`](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/sensors.xml)：
  `imu` site 上的 `framequat`、`gyro`、`gyro`、`velocimeter`、`accelerometer`，加 `subtreeangmom`。
  同目录 `robot_groundcontact.xml` 的 `imu` site 在 `trunk_base` 上，`quat="1 0 0 0"`。
- 同一提交的 `microduck_velocity_env_cfg.py` 用 `mdp.builtin_sensor` 读
  `robot/imu_ang_vel`、`robot/imu_lin_vel`，并用 `projected_gravity`；`raw_accelerometer`
  按固定的 sensor 下标读第 5 个传感器，属于绑定该 XML 的写法，未照搬到本仓库。
- mjlab 1.6.0 资产库（`unitree_go1`、`unitree_g1`）用同样的 `gyro` / `velocimeter` /
  `accelerometer` / `framezaxis` 组合，`Scene._add_sensors` 会把实体 XML 里已有的 sensor
  以 `<entity>/<name>` 注册，因此本仓库不需要在场景配置里重复声明。

实施内容：

- 新增 `imu` site：挂在 `base_link` 原点、单位姿态、`group=3`、半径 `0.004 m`。
  这是仿真占位，不是测得的板载位置；XML 注释与 README 均标明。
- 新增 5 个 sensor：`imu_ang_vel`（gyro）、`imu_lin_vel`（velocimeter）、`imu_accel`
  （accelerometer）、`imu_upvector`（framezaxis，world +Z 在 IMU 系中的方向，
  即投影重力的反向量，配 mjlab 的 `mdp.projected_gravity_from_sensor`）、
  `root_angmom`（subtreeangmom，`base_link` 子树）。
- 未采用官方 `framequat`（冗余于 `imu_upvector`）与官方第二个 `gyro`（带 `noise` 的近似重复项）；
  传感器噪声、延迟与安装误差按 mjlab 约定留在任务观测配置。

验收条件与结果：

- `get_spec().compile()` 后 `nsite=1`、`nsensor=5`，名称与顺序为 `imu_ang_vel`、`imu_lin_vel`、
  `imu_accel`、`imu_upvector`、`root_angmom`；
  整机工厂 `nsite=3`（`imu` + 两足底）、`nsensor=5`、`nu=0` 保持被动。
- 数值语义有断言：静止直立时 `imu_upvector=[0,0,1]`、陀螺/线速度/角动量为零；
  绕 z 轴偏航 30° 后 up 向量不变；绕 y 轴俯仰 −30° 后 up 向量为 `[0.5, 0, 0.866]`；
  给定根角速度 `[0.3,−0.2,0.5]` 时陀螺读数一致。
- 场景检查：`robot/imu_*` 与 `robot/root_angmom` 全部注册为 `BuiltinSensor`，
  形状 `(num_envs, 3)`、有限值，陀螺与 `root_link_ang_vel_b` 一致、`-up` 与
  `projected_gravity_b` 一致；`make check` 与 GPU 150 步场景检查通过。
  陀螺比较在步进 12 步之后执行（`|root ang vel|` 峰值 `0.165 rad/s`），并先要求
  `|root ang vel| ≥ 1e-3`，避免 reset 后两边同为 0 的恒真断言；负向对照（把 `imu` site
  转 20°）会产生 `0.127 rad/s` 的偏差，确认该断言能发现接错的 site。
- `root_angmom` 语义（实测）：世界系、绕子树质心，`base_link` 子树覆盖全部 16 个非 world body；
  与"绕基座原点"版本差 `0.2675`、与体系版本差 `0.1033`，不要当体坐标系或基座原点量使用。
- `imu_accel` 的语义（实测，2026 年 10 月 27 日）：MuJoCo accelerometer 输出比力，
  **自由落体时精确为 0**（`qpos0` 下 `ncon=0`、无支撑，读数 `[0,0,0]`），
  **有支撑静止时约为 `+9.81·imu_upvector`**（站立 `imu_accel=[9.810, 0.005, −0.032]`，
  与 `R^T·(+g)` 差 `3.8e-2`，残差来自接触振动）。所以加速度计并不排除重力；
  需要无噪声的重力方向时仍用 `imu_upvector`，不要假设 `imu_accel` 在支撑状态下为 0。
- 实机可得性分级（供 T022 定 actor 观测）：`imu_ang_vel`、`imu_upvector`（等价于姿态）
  是实机 IMU 可得的；`imu_lin_vel`、`root_angmom` 在本机没有对应传感器，
  只能给 critic 或奖励，不能进 actor —— 官方 `microduck_velocity_env_cfg.py` 同样把
  `base_lin_vel` 从 actor 删除后只加到 critic。`imu_accel` 实机可得但其含义依赖
  加速度计标定，本次未启用。

### T038 标定 HOME 站姿

状态：完成。用户给出 `r_hip_roll=0.38`、`r_hip_pitch=1.57` 的大致取向，要求左腿镜像、
重心居中且不前后倾，并授权自行补齐其余关节。

目标：给出一个可复核、脚底平贴、支撑余量足够的 HOME 站姿。

范围：`ht_microduck_constants.py` 的 `HOME_FRAME`（含初态根高），以及 `tools/check_robot_scene.py`、
`tests/test_robot_entity.py` 的对应断言；README 同步。

结果：

用户给的两个角度都不能直接落地，实测依据如下（`.artifacts/t042-stance`，RTX 4060）。

1. `hip_pitch=1.57` 正好是关节限位（`range="-1.571 1.571"`），且会把腿折到脚过髋：
   `roll 0.38 / pitch 1.57 / calf 0 / ankle 0` 的脚底法线倾角 **88.15°**，
   补 `calf=−1.57` 后仍有 16.90°；两者在 5–6 s 零动作保持中都是 **48/48 全倒**
   （根高掉到 0.043 m，倾角 74–76°）。所以 pitch 必须降到 0.85。
2. `hip_roll=0.38` 只在 (−0.384, 0.384) 内留 0.004 rad 余量，且把脚底翘起约 16.9°，
   只靠内缘着地；同时横向支撑余量从 92 mm 收到 57 mm。平地姿态需要的镜像内收是
   **`+0.0873 / −0.0873`**（T041 结论），脚底倾角 `0.13°`，与全零姿态的 `4.87°` 相比才是真正水平。

最终 HOME（`HOME_JOINT_POS`）：

| 关节 | 右 | 左 |
| --- | --- | --- |
| `hip_roll` | `+0.0873` | `−0.0873`（镜像） |
| `hip_pitch` | `0.85` | `0.85`（同号） |
| `calf` | `−1.20` | `−1.20`（同号） |
| `ankle` | `0.35` | `0.35`（同号） |

`hip_yaw`/`neck_pitch`/`head_pitch`/`head_yaw`/`head_roll`/`mouth` 保持 0。
根高 `0.1534 m`。支撑面比最低顶点低约 0.5 mm，最低顶点（脚跟圆弧）离地 `0.4 mm`，
复位时 `ncon=0`。

依据（CPU 几何 + GPU 保持，各自独立测得）：

- 脚底平面倾角 `0.13°`（两侧相同），全零姿态是 `4.87°`。
- 重心到支撑边界：前 `40.0 mm`、后 `34.3 mm`、左 `92.5 mm`、右 `91.9 mm`；
  前后差 `5.7 mm`，即重心在脚掌前后基本居中，不向前也不向后倾。
- 静态保持力矩最大 `0.176 N*m`（`hip_roll`），远低于 `2 N*m` 上限。
- 5 s 零动作保持：**0/128 跌倒**（8 种子 × 16 环境，关节目标加 `0.01 rad` 噪声），
  根高稳定在 `0.150 m`，末端倾角 7.8–9.4°。

根高比姿势本身更敏感，这是本轮最重要的实测结论：

| 根高 | 最低顶点离地 | 零动作保持 |
| --- | --- | --- |
| `0.1530` | `0.00 mm` | 0/64（与地面接触） |
| `0.1534` | `0.40 mm` | **0/128** |
| `0.1540` | `1.00 mm` | 1/128 |
| `0.1545`/`0.1548` | `1.5`/`1.8 mm` | 0/128 |
| `0.1550` | `2.00 mm` | 1/96 |
| `0.1586` | `4.80 mm` | 2/64（旧零位的 3.84 mm 支撑面余隙） |

原因是任何可见离地间隙都让复位变成落体，落地冲击会把蹲姿撞散。因此不沿用旧零位
3.84 mm 的支撑面余隙，取 `0.1534 m`。这一条对后续所有复位/课程设计都成立。

早期版本的保持测试把所有候选都从 `root_z=0.171` 放下，让深蹲姿势从 3–8 cm 高空自由落体，
把落地冲击记成了姿势不稳；改成每个姿势按自身几何高度复位后结论才稳定。
平面拟合也不能用来判脚底倾角：脚部碰撞网格是整只脚（约 3.9e4 顶点）且带曲面，
在倾斜姿态下拟合会给出 33–90° 的假值；改为在真正水平的姿态标定一次脚底法线，
再用踝链旋转它。

守卫与断言同步：

- `tools/check_robot_scene.py` 的根高守卫原为绝对值 `0.15 m`，对更低的蹲姿等于失效且会误报；
  改为相对 HOME 的 `0.9 × HOME`（`0.138 m`），实测 `0.1498 m` 通过，腿塌时仍能拦住。
- `tests/test_robot_entity.py` 的三处 HOME 断言与脚底余隙区间（改为 `−1.5 mm ~ 0`）同步；
  “下压 5 mm 触地”改为 `8 mm`，因为最低网格点是脚跟圆弧而不是支撑面。

验收：

- `make check` 通过：`All checks passed!`、`134 passed, 1 warning, 8 subtests passed`。
- 整机场景 GPU 检查 150 步通过：`root_height=[0.149827, 0.149834] m`、
  `peak_effort=0.532 Nm`、`peak_joint_speed=0.841 rad/s`、双足接地、无溢出。
- 速度脉冲（协调的前倾+屈膝开环目标，1 s 保持）：

  | 幅度 | 旧零位 | 新 HOME |
  | --- | --- | --- |
  | `0.10 rad` | 0/24 | 0/24 |
  | `0.14 rad` | 0/24 | 0/24 |
  | `0.18 rad` | 0/24 | 0/24 |
  | `0.22 rad` | 0/24 | 0/24 |
  | `0.26 rad` | 2/24 | **0/24** |

  只前倾不动膝的非协调脉冲会让蹲姿在 0.35 m/s 档 23/24 跌倒，但那是不可执行的指令
  （膝关节不动时髋前倾等于把脚往后蹬），不作为站姿证据；执行器层面的跟踪能力归 T023。

未完成、需如实记录的部分：

- 默认增益未改，仍是 `kp=10`/`kd=0.4`。本轮只证明该增益下蹲姿可以 0/128 保持，
  没有证明它是最优增益；T041 曾测出 `kp=20`/`kd=0.8` 能把旧零位从 7/96 降到 2/96。
  增益与 HOME 的联合整定仍未做，属 T023 及 M1 的范围。
- 单脚/双脚接触面积没有直接测量。mjlab 1.6 的 `sim.data.contact` 是 `WarpBridge`，
  只有 `dist`/`pos`/`frame` 等扁平张量，没有 `geom1`/`geom2`，无法在设备侧按 geom 归并接触点；
  本轮改用 CPU 顶点与支撑面几何替代，并明确它不等于接触面积。
- 增益、限幅、延迟与供电仍是仿真假设；实机参数归 T030。不宣称完成实机标定。

### T039 按官方结构重写机器人常量模块

状态：完成。依赖 T037。用户指出本体 XML 不该带地形，并要求常量模块照官方写法、执行器用本地实现。

目标：机器人 XML 只包含本体；`ht_microduck_constants.py` 的结构与官方
`microduck_constants.py` 一致，同时保留本仓库自己的执行器实现。

依据（外部参考，[microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck)）：

- 官方 `robot_walk.xml` 顶层只有 `compiler`、`default`、`asset`、`worldbody`、`sensor`、
  `actuator`、`equality`，不含地面与灯光；`scene_walk.xml` 用 `<include>` 引入本体后再加地面。
- 官方 `microduck_constants.py`（331 行）只有：`_ROBOT_DIR` 与各 XML 路径常量加
  `assert XML.exists()`、一行式 `get_*_spec()`、`HOME_FRAME`、单套 `FULL_COLLISION`、
  `_BAM_ACTUATOR_KWARGS` 与执行器对象、若干 `EntityCfg`，末尾用 `SceneCfg` + `Scene` 做预览。
  没有 IMU 名称常量，没有电机映射表，没有分节横幅。官方在 env cfg 里直接写 `"robot/imu_ang_vel"`。
- mjlab 的 `Scene` 自带 terrain 平地与太阳，机器人 XML 带地面必然出现两个 plane。

实施：

- `HT-DK_URDF.xml` 只保留 `compiler`、`asset`（网格）、`worldbody`（机器人）、`sensor`。
- `ht_microduck_constants.py`（189 行）按官方结构重写：路径常量加存在性断言、一行式
  `get_spec()`、`get_robot_spec()` 只做碰撞体命名与足底 site、`HOME_FRAME`、单套
  `FULL_COLLISION`、无刷与舵机执行器配置、一个 `HT_MICRODUCK_ROBOT_CFG`、
  `get_ht_microduck_robot_cfg()` 深拷贝，末尾 mjlab `Scene` 预览。
  执行器沿用本地 `FrictionDRBamActuatorCfg` 与 `HTDW3532ActuatorCfg`。
- 删除本地自造的 `SCENE_XML_PATH`、`get_scene_spec()`、`IMU_SITE_NAME`、`IMU_SENSOR_NAMES`、
  `##` 分节横幅；工具与测试改为直接从编译后的模型读取 sensor 名称。

验收结果（本机实测）：

- 本体 `get_spec().compile()`：`nq=22 nv=21 nu=0 nsite=1 nsensor=5 nlight=0`，plane 数 0。
- `tools/check_robot.py` 输出“本体检查：无平面、无灯光；地面与灯光由 mjlab 场景提供”。
- `make check`：`All checks passed!`，`134 passed, 1 warning, 8 subtests passed`。
- GPU 场景检查（`cuda:0`、4 环境、150 步）：`planes=1`（仅 mjlab 的 `terrain`）、
  双足接地、`IMU sensors=5`、`peak_effort=0.138278Nm`、`root_height=[0.166165, 0.166172]m`。

剩余问题：

- `imu` site 仍在本体原点、单位姿态。官方 site 挂在 `trunk_base` 上但带 `(-0.021, 0.0001, -0.0147) m`
  偏移；本机该偏移未测量，属 T030 硬件标定。
- 站姿标定（T038）未做。

### T040 精简 README 并整理项目入口

状态：完成。依赖 T039，按用户要求进行文档整理，不改变实现和阶段验收状态。

目标：让首次阅读者快速了解项目用途、已有功能、检查入口和详细文档位置。

范围：根目录 `README.md` 和本页任务记录。安装流程引用 `setup.md`，
执行器公式、参数来源及接入细节引用已有模块说明与设计，任务进度仍在本页维护。

验收条件：

- README 中的目录、符号、命令与当前代码和 Makefile 一致，本地链接可解析。
- 保留 12+3 电机分组、机器人与场景的边界、仿真假设与实机标定的区别，以及训练入口尚未实现的说明。
- 直接运行的 GPU 检查示例先创建项目内临时目录，并隔离相关缓存。
- `make check` 通过；不新增测试，不因文档整理启动 GPU 短跑或训练。

### T041 对照三个参考项目复核下一步

状态：完成。依赖 T040；用户指定 pollen-robotics/microduck、pollen-robotics/microduck_rl 与
`/home/sunteng/projects/duck_project`，要求判断下一步做什么。

目标：把"已经有模型、混合执行器和场景检查，但还没有任务环境与训练链路"这一现状，
对照三个参考项目落到一个可执行的任务顺序上，并纠正上一轮遗留的错误前提。

范围：只读核对上游固定提交、`duck_project` 归档与本仓库代码；在项目内
`.artifacts/t040-next-step/` 写一次性探针做可行性实测。不修改机器人源码、参数、XML、
依赖或测试，不执行训练与实机操作。探针在交付前删除，结论与数值落回本页。

核对版本（2026 年 10 月 27 日，均用 GitHub API 核对默认分支）：

- [microduck@96b89d8](https://github.com/pollen-robotics/microduck/tree/96b89d8613f06722c1d64ce75ab0d7124fed9d8f)，
  默认分支 `main`，2026-10-26 "Prepare release 0.17.9"。
- [microduck_rl@b02fdea](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3)，
  默认分支 `develop`，2026-10-12；与 T036 记录的提交一致，`develop` 本身未再前进。
  仓库 `pushed_at` 更新是因为其它分支在动，引用时仍须写明 `develop`。
- `/home/sunteng/projects/duck_project`：78 个 run 的归档，无 `.git`、无权重。

**上游事实（附固定链接）**

- 训练侧主任务是平地速度跟踪 `Mjlab-Velocity-Flat/Rough-MicroDuck`；另有 `StandUp`、
  `VelStand`、`SitStand`、`RollerStandUp` 等站立/起身任务，注册表见
  [tasks/\_\_init\_\_.py](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/__init__.py)。
- 观测固定 61 维：`base_ang_vel`(3)、`projected_gravity`(3)、`joint_pos`(14)、`joint_vel`(14)、
  `last_action`(14)、命令块 13（twist 3 + head_pose 4 + body_pose 6）。actor **删除**
  `base_lin_vel` 与 `height_scan`，只给 critic；即刻意只用实机可得量。
- 动作 `JointPositionActionCfg`、`scale=1.0`、14 维（15 关节去掉嘴）；控制 50 Hz
  （`timestep=0.005`、`decimation=4`）；`episode_length_s=20`。
- 命令固定 `lin_vel_x ±0.4`、`lin_vel_y ±0.3`、`ang_vel_z ±1.0`，不再做扩张课程；
  15% 环境专训原地转；站立环境占比 0.02→0.25 走课程。
- 奖励骨架：`track_linear_velocity +2.0`、`track_angular_velocity +2.0`、`upright +2.0`、
  `pose +1.0`、`air_time +3.0`、`head_pose_tracking +2.0`、`self_collisions −1.0`、
  `action_rate_l2 −0.1→−1.0`（课程）、`foot_slip −0.1`（刻意弱）、`body_ang_vel −0.05`、
  `angular_momentum −0.02`。
- 上游 `AGENTS.md` 给出可迁移的工程经验：每个罚项在 wandb 中必须 ≤ 0（符号写反会变成奖励）、
  不要用二值 mask 门控奖励、命令槽即使权重为 0 也要保留小范围采样、零命令必须显式训练、
  课程阶段要与策略实际进度对齐、`warm start ≠ resume`（步数计数器会被恢复）。
- 部署侧 [control.rs](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/robotd/src/control.rs)
  的目标为 `HOME + scale × action`；[safety.rs](https://github.com/pollen-robotics/microduck/blob/96b89d8613f06722c1d64ce75ab0d7124fed9d8f/duck-control/src/safety.rs)
  对 NaN 是**拒绝**而非夹取，deadman 500 ms 只清速度，跌倒判定只上报。
- 上游存在一处自相矛盾：训练侧 `AGENTS.md` 写策略训练中不加动作低通，
  部署侧 `control.rs` 写滤波系数"训练时就是 0.5/0.7"。二者不能同时成立，不能作为本机依据。

**duck_project 事实（以 JSON 为准，不引用概述性百分比）**

- 48 集行走评估（seed 2043）：v21 37/48、v29 25/48、v37 36/48、v38b 0/48、v43 0/48、v44 0/48。
- v44 的 0/48 全部由 `velocity` 判死（48/48，其中 `|vy|≥0.04` 有 45 集），
  且该 run 的 `selection.json` 选中的权重是 v29 的 checkpoint——0/48 指新训 final，
  0.625 是回退基线，两者不能混用。
- 文档里的"前扫 15.3 mm / 抬脚 17.0 mm"在 `params/`、`reports/` 中没有任何原始 JSON 支撑，
  仅出现在 md 与脚本内硬编码表；`sitstand` 的"96%"是把分子 96/192 误当百分比，
  `sitstand_v46.md` 自述为 50%。
- 归档代码里 `gait.py` 的 excursion 仍用机体系，正是 v43 认定为致命 bug 的算法；
  评估口径应以 v43 之后的世界系版本为准。

**本机实测（一次性探针，非验收）**

探针位于 `.artifacts/t040-next-step/`，全部使用项目内 `TMPDIR`/Warp/Torch 缓存、
`PYTHONDONTWRITEBYTECODE=1`，RTX 4060、`cuda:0`。

1. **mjlab 1.6 自带的平地速度任务可以直接套在本机器人上**，但必须显式改六处，
   否则第一次 `reset` 就报错。实测的失败顺序与修法：
   - `feet_ground_contact`、`self_collision` 两个接触传感器在通用模板里不存在，
     需按本机 `r_foot_collision`/`l_foot_collision` 与 `base_link` 子树自行声明，
     否则 `KeyError: Scene element 'feet_ground_contact' not found`。
   - `pose` 奖励的 `std_standing/walking/running` 默认是空字典，必须给正则映射，
     否则 `tensor a (15) must match tensor b (0)`。
   - `terrain_scan` 与 `height_scan` 在平地上应删除；`foot_height_scan` 改为
     `r_foot`/`l_foot` 两个 site。
   - `actions["joint_pos"].actuator_names` 需显式给 10 个腿部关节，才能得到 10 维动作
     并让其余 5 个关节保持默认位置。
   - `htdw3532_init`、`bam_init` 两个 startup 事件必须注册，
     否则 `HTDW3532 needs independent per-world native PD fields`。
   - `foot_friction`、`base_com`、`upright`、`body_ang_vel`、`foot_clearance`、`foot_slip`
     的 asset 选择器默认是空元组，需按本机命名填写。

   按上述改动后，2 环境 `obs[actor]=(2,52)`、`obs[critic]=(2,64)`、动作 `(2,10)`，
   20 步零动作奖励有限，根高 `0.1658–0.1664 m`，未触发跌倒终止。
   52 维的构成是 3+3+15+15+10+3（角速度、投影重力、全部 15 关节位置与速度、上一步动作、命令）；
   joint_pos/joint_vel 含被保持的 5 个关节，因此比动作维度大。
2. **吞吐**：同配置下 256 环境约 `1.47e4` env-step/s、1024 环境约 `1.29e4`、
   4096 环境约 `4.20e4`（60 步均值，含少量首次编译摊薄）。
   RTX 4060 8 GB 在 4096 环境时显存占用未见压力。这说明以 256–1024 环境先跑
   短训练是可行的，训练规模不是当前瓶颈。
3. **HOME 站姿比 T036 记录的更脆弱**。固定初态、移除 `push_robot`、50 Hz 控制、
   32 环境 × 3 种子、5 s 零动作保持：

   | 站姿 | 增益 | 跌倒 | 末根高 |
   |---|---|---|---|
   | 全零 | `kp=10`/`kd=0.4` | 7/96 | `0.1570–0.1710 m` |
   | 全零 | `kp=20`/`kd=0.8` | 2/96 | `0.1655–0.1669 m` |
   | 水平（±0.0873） | `kp=10`/`kd=0.4` | 5/96 | `0.1606–0.1686 m` |
   | 水平（±0.0873） | `kp=20`/`kd=0.8` | 1/96 | `0.1666–0.1688 m` |

   把根高下调到 `0.1695 m` 没有改善（4/96 与 1/96）。
4. **跌倒来源已定位到 `push_robot` 而不是 DR 组合**：同一保持测试保留全部默认 DR
   但去掉 `push_robot` 后，全零站姿 `worst_tilt` 从 70.30° 降到 19.25°、跌倒 0/8；
   水平站姿从 68.34° 降到 10.74°、跌倒 0/8。单独去掉 `base_com`、`encoder_bias`
   或 `foot_friction` 都不能消除跌倒。上游默认推扰为每 1–3 s、±0.5 m/s，
   对 3.3 kg 的本机明显过强。
5. **脚底平面只能用镜像内收拉平**：CPU 顶点拟合给出全零时两侧均为 `4.55°`、
   `+0.0873/−0.0873` 时两侧均为 `0.11°`；同号 `+0.0873/+0.0873` 则一侧 `0.11°`、
   另一侧 `7.65°`。这与 T036 的措辞一致，但 T036 没写出符号，落地时容易写错。
6. **控制周期与物理步长不能独立选**：`dt=0.005`、decimation 4（50 Hz）在默认 DR 下
   跌倒 3–4/4；`dt=0.002`、decimation 10（50 Hz）在同条件下 0–1/4。
   即上游"50 Hz"这个结论在本机成立的前提是物理步长为 2 ms，不能把 `dt=0.005` 直接搬来。

**为什么顺序是 T038 → T022 → T023，而不是直接写环境**

- 任务契约（动作子集、`scale`、观测项、控制周期）一旦冻结，观测维度与默认关节角就固定了。
  `duck_project` 的教训是：改 `default_joint_pos` 等于整体平移 `joint_pos_rel`，
  是"换任务"，会让热启动失配；`action scale` 被全局值覆盖曾直接导致坐下 100% 摔倒。
  所以必须先把 HOME 与增益定下来，再冻结契约。
- HOME 现在连"零动作保持"都做不到全种子无跌倒，而这个姿态会被写进观测基线
  （`joint_pos` 相对 HOME）、奖励（`pose`）与部署侧的 `DEFAULT_POSITION`。
  在它稳定之前写任务，等于把一个已知不稳的参考点固化进三层接口。
- 反过来，T022 不需要训练链路，也不该等 T029 的硬件协议，因此它可以紧跟 T038。

**下一步（按依赖排序）**

1. **T038**：按本页新增的验收条件确定 `hip_roll` 符号、`hip_pitch`/`knee`/`ankle`
   的站姿值与默认增益，并把"多种子零动作保持"写入断言。这是唯一阻塞 T022 的事项。
2. **T022**：冻结契约。建议首版取 10 维双腿动作（颈头 5 关节显式保持）、
   `scale` 按本机单独定（不沿用上游 1.0 也不再沿用全局 0.5）、
   `dt=0.002 s` + decimation 10（50 Hz，见实测第 6 条）、观测只用
   `imu_ang_vel`/`imu_upvector`/关节位置/关节速度/上一步动作/命令，
   不用 `imu_lin_vel` 与 `root_angmom`。
3. **T023**：在 `tasks/` 实现平地速度任务。可直接以 mjlab 1.6 的
   `make_velocity_env_cfg()` 为底，按上面第 1 条列的六处改动落地；
   推扰强度必须按本机质量重标（实测第 4 条），不能沿用上游 ±0.5 m/s。
4. **T024–T026**：本地网络、Storage、PPO、Runner 按既定方向实现，不引入 RSL-RL。
   上游 `AGENTS.md` 的奖励符号检查、零命令显式训练、课程阶段对齐三条应直接写进验收。
5. **T027–T028**：评估与导出。评估口径参考 `duck_project` 的世界系前扫与真实足端高度，
   但不要复用其机体系 excursion 与 `contact.found` 判离地。
6. **T029–T031** 仍等待本机协议、IMU 安装与控制板信息，本轮不调整其依赖。

**结论一句话**：三个参考项目里，`microduck_rl` 提供可直接套用的任务骨架与工程不变量，
`duck_project` 提供"哪些指标能信、哪些坑会重演"的负面清单，`microduck` 提供部署侧契约；
本仓库现在已经具备把它们接起来的前提，最该做的是先把 HOME/增益定死（T038），
再用 mjlab 1.6 通用速度模板改出本机任务（T022 → T023），而不是继续攒检查工具。

**本轮实际推进（2026-10-27）**：T038 → T022 → T023 → T024 → T025 → T026 已依次完成，
上面的"下一步"清单第 1–4 条已落地，详见下方各任务的完成记录。T027 起仍按原依赖等待。

### T022 固定首版任务控制与观测契约

状态：完成。依赖 T001、T002、T021；承接 T038 定下的 HOME 与增益。

目标：把"动作子集、缩放、观测项与顺序、控制频率、episode 长度"冻结成一份运行时校验的
契约，让任务环境、PPO、回放与导出都从同一处取维度，避免 T041 记录的
"改 `default_joint_pos` 或全局 `action_scale` 直接换掉任务"。

产物：`src/ht_microduck/tasks/common/contract.py` 与 `tools/check_task_contract.py`。

契约取值与依据：

| 项 | 取值 | 依据 |
|---|---|---|
| 物理步长 | `0.002 s` | T041 实测第 6 条：`dt=0.005` 在默认 DR 下 3–4/4 跌倒 |
| decimation | `10` | 与上一条共同给出 50 Hz，且 3532 有 0–3 步指令延迟 |
| 控制频率 | `50 Hz` | 与 `microduck_rl` 一致 |
| episode 长度 | `20.0 s` | 与 `microduck_rl` 一致 |
| 动作维度 | `10`（仅双腿） | 颈头 5 关节由 HOME 显式保持，见下 |
| 动作顺序 | `r_hip_yaw/roll/pitch/calf/ankle` → `l_…` | 与 `joint_pos` 观测同一顺序 |
| 动作缩放 | `0.25 rad` | 本机单独定；不沿用上游 `1.0` 或 mjlab 全局 `0.5` |
| actor 观测 | `39` 维 | 见下表 |
| critic 观测 | `42` 维 | actor 39 + `base_lin_vel(3)` |
| 保持关节 | `neck_pitch`、`head_pitch`、`head_yaw`、`head_roll`、`mouth` | 实机无对应策略输出 |

actor 观测顺序（`ACTOR_OBSERVATION_TERMS`）：`base_ang_vel`(3)、`projected_gravity`(3)、
`command`(3)、`joint_pos`(10)、`joint_vel`(10)、`actions`(10)。critic 在其后追加
`base_lin_vel`(3)。`base_lin_vel` 只出现在 critic，`validate_contract()` 在导入时强制这一点，
避免真值线速度漏进实机可部署的 actor。

与官方 `microduck_rl` 的**有意差异**（每条都在配置里就地注明理由）：

1. 动作 10 维而非 14 维：本机颈头是 FEETECH/3532 混合且不做视觉追踪，头部命令会让
   `joint_pos` 基线随命令漂移。上游 14 维里有 4 维是颈头。
2. 动作缩放 `0.25` 而非 `1.0`：整机 3.29 kg、腿长更短，`1.0` 的单步目标变化会直接掀翻机身。
3. 无 `height_scan` / 地形扫描：本机是平地，硬件也没有深度传感器。
4. 推扰收到 `±0.3 m/s` 水平分量，且无角速度分量：上游 `±0.5 m/s` 对 3.3 kg 机体过强
   （T041 实测第 4 条）。
5. 命令范围收窄为 `vx(-0.4,0.4)`、`vy(-0.3,0.3)`、`wz(-1.0,1.0)`：与上游一致，
   但删掉上游的 `head_pose`/`body_pose` 命令块（对应第 1 条）。

验收命令与结果：

```
uv run --no-sync python -B tools/check_task_contract.py --device cuda:0
```

```
timing: dt=0.002s decimation=10 control=50.0Hz
action: dim=10 scale=0.25 names ok
observations: actor=39 critic=42, order ok, no privileged actor terms
privileged: critic tail == root_link_lin_vel_b; actor has 6 terms and none is base_lin_vel
mapping: 10 per-joint pulses each command only their own joint
held joints: 5 servos/neck stayed within 46.5 mrad of HOME under random actions
reset: per-env reset isolated to the requested worlds
run: 150 control steps finite obs/reward
Contract check passed: device=cuda:0, envs=4, actor=39D, action=10D, control=50Hz.
```

检查过程中暴露并修正的三个真实问题（不是测试写法问题）：

- **动作映射的判据从"位置"改为"指令目标"**：`apply_actions()` 写入的
  `joint_pos_target` 与 `processed_actions` 之间还隔着编码器偏置
  （`target = processed - encoder_bias`），启动事件给的 `±0.015 rad` 偏置会让
  实测位置慢速收敛。比较 `processed_actions` 才能把"索引路由"和"PD 收敛"分开测。
- **编码器偏置必须进期望值**：修正后仍差 `0.0096 rad`，正是 `encoder_bias` 在该关节上的取值。
  现在期望值显式减去 `robot.data.encoder_bias`。
- **特权项用结构断言而不是数值扰动**：最初的写法"只改线速度、断言 actor 不变"不成立，
  因为重推一步物理会让 `base_ang_vel` 与 `projected_gravity` 一起变。改为直接断言
  critic 末 3 维等于 `root_link_lin_vel_b`，且 actor 的 term 列表里没有 `base_lin_vel`。

### T023 实现最小平地速度任务

状态：完成。依赖 T022；参考 pollen-robotics/microduck_rl 官方平地任务 `Mjlab-Velocity-Flat-MicroDuck`。

目标：在 `tasks/` 里做出可直接训练、也可被回放复用的平地速度环境。

产物：`src/ht_microduck/tasks/flat_velocity/`（`velocity_env_cfg.py`、`__init__.py`）、
`src/ht_microduck/tasks/common/mdp.py`、`tools/check_velocity_env.py`。

结构：`make_flat_velocity_env_cfg(num_envs, seed)` 组合 mjlab 1.6 的场景、命令、动作与观测，
奖励和终止按官方平地任务对齐，另加本机专用项。

奖励（11 项，权重取官方 `microduck_rl` 平地任务的数值）：

| 项 | 权重 | 说明 |
|---|---|---|
| `track_linear_velocity` | `2.0` | `std=sqrt(0.1)`，与官方一致 |
| `track_angular_velocity` | `2.0` | `std=sqrt(0.5)` |
| `upright` | `2.0` | `exp(-g_xy²/std²)`、`std=sqrt(0.05)` |
| `dof_pos_limits` | `-1.0` | |
| `action_rate_l2` | `-0.1` | 官方由课程从 `-0.1` 加到 `-1.0`；首版取起步值 |
| `joint_torques_l2` | `-2e-4` | 本机专用（3.29 kg，力矩量级小） |
| `joint_vel_l2` | `-2e-4` | 同上 |
| `air_time` | `3.0` | 阈值 `0.125/0.300 s`，`command_threshold=0.01` |
| `foot_clearance` | `-2.0` | 目标高 `0.02 m` |
| `foot_slip` | `-0.1` | |
| `self_collisions` | `-1.0` | 官方新增项；`primary`/`secondary` 两侧都是 `subtree=base_link` 的接触传感器（T044 修正） |

终止（4 项）：`time_out`（超时，`time_out=True`）、`fell_over`（`bad_orientation`，70°，
与 T038 的跌倒判据一致）、`illegal_contact`（机体触地，本机专用）、`nan_state`
（非有限状态；不加它会让一个炸掉的环境通过优势归一化污染整个 batch）。

事件：启动阶段必须有 `htdw3532_init` 与 `bam_init`（否则 3532 无法拿到逐世界的原生 PD 字段）；
另有 `reset_base`、`reset_robot_joints`、`push_robot`（每 3–6 s，`±0.3 m/s` 水平）、
`foot_friction`（`0.7–1.3`）、`encoder_bias`（`±0.015 rad`）、`base_com`（`±0.02 m`）。

验收命令与结果：

```
uv run --no-sync python -B tools/check_velocity_env.py --device cuda:0
```

```
spaces: actor=39D critic=42D action=10D dt=0.02s
rewards: 11 terms -> track_linear_velocity, track_angular_velocity, upright, dof_pos_limits, action_rate_l2, joint_torques_l2, joint_vel_l2, air_time, foot_clearance, foot_slip, self_collisions
commands: dim=3 ranges vx=(-0.4, 0.4) vy=(-0.3, 0.3) wz=(-1.0, 1.0)
zero-action hold: 100 steps, 2/16 terminations (domain randomisation on; T038 measured 0/128 without it)
random run: 300 steps, mean reward -20.375, terminations 16, truncations 0
terminations: time_out is truncation, fell_over is terminal
fall detection: flipped worlds terminated = 16/16
Velocity env check passed: device=cuda:0, envs=16, steps=300, dt=0.02s.
```

**零动作保持 2/16 的定性**：这不是回归。T038 的 0/128 是在无 DR 的干净保持下测的；
本任务同时开编码器偏置 `±0.015 rad`、足底摩擦 `0.7–1.3`、逐环境 CoM 偏移，
多次重复（6×16）累计 1/96 终止，属偶发。检查据此改为"不超过 1/4 环境"而不是断言为 0，
并把实测值打印出来，避免把 DR 的正常代价误读成站姿失败。

**待办（不阻塞 T023 验收）**：`feet_clearance` 与 `foot_slip` 依赖足端 site 的世界系高度与速度，
当前实现读 `asset.data.site_pos_w`；导出与回放前需与 `duck_project` 的世界系前扫口径对齐一次。

### T024 实现本地网络与轨迹 Storage

状态：完成。依赖 T023。

目标：不引入 RSL-RL，自己实现 actor/critic、观测归一化、rollout 存储与 GAE。

产物：`src/ht_microduck/algorithms/networks.py`、`storage.py`、`tests/test_networks.py`。

- `Actor`/`Critic`：`(512,256,128)` ELU MLP，输入分别为 39/42 维，输出 10 维均值/标量。
  与官方同构，便于日后再对照超参。
- `RunningMeanStd`：`nn.Module`，带 `count` 缓冲，随 checkpoint 存取；用合并均值/方差的
  增量公式，使"两个半批"与"一整批"得到相同统计（有测试守住）。
- `GaussianDistribution`：状态无关的 `log_std`，`log_std` 截断到 `[-5,1]`。
- `RolloutStorage`：`(num_steps, num_envs, dim)` 固定容量，`compute_returns()` 跑 GAE-λ，
  并把 **真实终止** 与 **超时** 分开：真实终止不 bootstrap，超时保留价值估计。
  理由是不区分时，20 s 的超时会被当成"死亡"，价值函数学到的就是"时间到了等于失败"。

验收命令与结果：

```
uv run --no-sync python -B -m pytest -q tests/test_networks.py
```

`17 passed`。其中三条用手算值守住关键公式：`log_prob` 对标准对角高斯、
熵对 `0.5·log(2πeσ²)`、GAE 对两步行进的手推递推（含真实终止与超时两种分支）。

**实现中发现的真实 bug**：`GaussianDistribution` 的 `log_std` 是形状 `(10,)` 的参数，
与 `(N,10)` 的均值广播后，`torch.clamp` 保留的是参数自身形状，导致 `entropy()` 和
`log_prob()` 的 `sum(dim=-1)` 把 batch 维也压掉了（返回标量）。已改为在构造时
`expand_as(mean)`；这条正是被"形状断言 + 手算熵"测试抓到的，不是靠肉眼。

### T025 实现本地 PPO 更新

状态：完成。依赖 T024。

产物：`src/ht_microduck/algorithms/ppo.py`、`tests/test_ppo.py`。

- 裁剪代理目标 + 裁剪价值损失 + 熵奖励，梯度按 `max_grad_norm=1.0` 裁剪。
- 超参取官方值：`gamma=0.99`、`lam=0.95`、`clip=0.2`、`entropy_coef=0.01`、
  `5` epochs / `4` minibatches、`lr=1e-3`、`desired_kl=0.01` 的自适应步长。
- **小批量内优势归一化**：本任务的奖励是"一个大跟踪项 + 一堆小惩罚项"，原始优势跨度大；
  不归一化时首个 iteration 的 `approx_kl` 达 `2.99`、`clip_fraction` 达 `0.90`。
  归一化后首轮 `kl=1.02`、第三轮 `0.068`。同时对零方差 batch 加保护，避免除零后梯度全零。

验收命令与结果：

```
uv run --no-sync python -B -m pytest -q tests/test_ppo.py
```

`12 passed`。裁剪性质不是"看损失变小"，而是构造两批只差 `old_log_prob` 的数据，
直接断言 `ratio=1.1` 时损失约 `-1.1`、`ratio=50` 时仍约 `-1.2`（即停在信任域边界）。

**写测试时被自己纠正的一处判断**：最初想断言"ratio 很大时损失有界"，但标准 PPO 里
负优势对应的目标本来就没有下界；正确可测的命题是"正优势 + 超出信任域时饱和在
`-clip·A`"。测试改为显式关掉归一化、只用正优势，避免用一个错命题掩盖真实行为。

### T026 接通 Runner、训练入口与短跑基线

状态：完成。依赖 T023、T025。

产物：`src/ht_microduck/algorithms/runner.py`、`src/ht_microduck/cli/train.py`、
`pyproject.toml` 的 `[project.scripts]`、`tests/test_runner.py`。

- `OnPolicyRunner` 负责"采样 N 步 → 更新 GAE → PPO 更新"，并把归一化器统计的更新、
  指标记录、checkpoint 存取集中在一处。
- checkpoint 里同时存 `model`、`optimizer`、`iteration`、`learning_rate`、完整 `cfg`
  和**契约快照**；加载时若契约的观测维度不符直接报错，而不是把权重硬塞进改过的网络。
- 指标每个 iteration 追加一行 JSONL，崩溃也保留已有数据。

验收命令与结果：

```
uv run --no-sync duck-train --num-envs 16 --iterations 2 --seed 0 --device cpu
```

```
training: envs=16 iterations=2 seed=0 actor_obs=39 action=10 control=50Hz
iter     1 reward -0.063 ep_return -1.27 value_loss 0.1169 kl +0.39855 lr 6.67e-04
iter     2 reward -0.067 ep_return -1.81 value_loss 0.0544 kl +0.10128 lr 4.44e-04
saved final checkpoint and metrics to .artifacts/t023/entry
```

恢复验证（同一 checkpoint 续训，迭代号与优化器状态都接上）：

```
resumed from .../checkpoint_last.pt at iteration 4
iter     5 reward -0.069 ep_return -1.92 value_loss 0.0369 kl +0.02501 lr 1.32e-04
iter     6 reward -0.070 ep_return -2.14 value_loss 0.0662 kl +0.02236 lr 8.78e-05
```

`tests/test_runner.py` 用替身环境跑通 9 条测试（含种子可复现、契约不符时报错、
指标追加），`make check` 通过。

**未完成的一处**：本轮三次 GPU 短跑曾被并发进程占满显存（`Go2-Chase-Flat` 训练常驻
7.1/8.0 GiB），最终训练验证在 `--device cpu` 上完成；GPU 上只跑通了环境的
`check_task_contract.py` 与 `check_velocity_env.py`。GPU 训练证据留到 T027 一并补，
届时需要显存空闲窗口。

**明确不宣称的事**：以上短跑只证明"链路通、loss 有限、checkpoint 可读写可恢复"，
不证明学会行走。奖励均值在 `-0.07` 附近、episode 长度 20–30 步，都是初始策略的表现。
该 `-0.07` 的绝对值在 T044 修复自碰撞误计后不再适用（修复后同类短跑为 `-0.003` 到 `+0.007`），
但"没学会行走"这个结论不受影响。

#### 追加（2026-10-27）：训练可用性复核

用户问"现在能不能训练"。本轮只做只读复核加短跑，不新增任务、不改代码、不改超参。

环境限制先说明：本沙箱**没有 GPU 设备节点**（`/dev/nvidia*` 不存在，`nvidia-smi` 报
`couldn't communicate with the NVIDIA driver`），`torch 2.14.1+cu130` 报
`cuda_available=False`、`device_count=0`；宿主内核模块已加载但未透传到本进程。
因此默认的 `duck-train`（`--device cuda:0`）在环境构造阶段就失败：
`RuntimeError: No CUDA GPUs are available`。这不是代码缺陷，但说明**默认入口在本机跑不起来，
必须显式 `--device cpu`**。

CPU 路径实测（`UV_CACHE_DIR`、`TMPDIR`、`WARP_CACHE_PATH`、`TORCHINDUCTOR_CACHE_DIR`
均指向项目内 `.artifacts/`；`~/.cache/uv` 与 `~/.cache/warp` 在本机只读，首次没设会
`OSError: [Errno 30] Read-only file system`）：

```
uv run --no-sync duck-train --num-envs 64 --iterations 100 --seed 0 --device cpu \
  --save-interval 25 --out-dir .artifacts/status-check/learn
```

| 迭代 | mean_reward | episode_return | episode_length | done_fraction |
|---|---|---|---|---|
| 1 | `+0.0136` | `-0.12` | 24.0 | 0.0007 |
| 25 | `+0.0094` | `+0.38` | 54.2 | 0.0156 |
| 50 | `+0.0185` | `+0.84` | 60.6 | 0.0150 |
| 75 | `+0.0223` | `+2.21` | 104.3 | 0.0091 |
| 100 | `+0.0251` | `+3.63` | 156.3 | 0.0033 |

100 个迭代共 421 s（约 4.2 s/iter），`approx_kl` 从 `0.163` 收敛到 `0.013`，
学习率自适应降到 `1.32e-04`。恢复验证：`--resume .../checkpoint_100.pt --seed 7`
从 iteration 100 接着跑到 102，优化器与迭代号都接上。

另一条短跑（64 环境 4 迭代、256 环境 3 迭代）同样通过；`make check` 全绿
（179 项测试 + 8 subtests、Ruff、模型编译、锁文件），锁文件检查同样要项目内 `UV_CACHE_DIR`。

结论与边界：

1. **训练链路是通的**，CPU 上能采样、更新、写指标、存 checkpoint、恢复续训。
   从 episode 长度 24 → 156 步和 return 由负转正看，策略确实在学（不是随机基线）。
2. **还远没学会走**。episode 上限是 20 s / 1000 步（`EPISODE_LENGTH_S` × 50 Hz），
   156 步约 3.1 s，绝大多数 episode 仍以跌倒终止。
3. **CPU 不适合正式训练**。256 环境 12.13 s/iter（24 步）= 约 506 env-step/s；
   T036 探针在 RTX 4060 上的量级是 `1.3e4` env-step/s（不同探针，非同一路径的对照）。
   按此估算，CPU 上跑 1000–4000 迭代的正式训练要数天。
4. **GPU 证据仍缺**，与 T026 原文的欠账一致；`docs/development.md` 里"RTX 4060 8 GB"
   的运行数据本轮无法复现或反驳，需要用户在有 GPU 设备节点（可见 `/dev/nvidia*`、
   `nvidia-smi` 正常）的机器上跑 `duck-train` 默认参数补测。

本轮临时产物（`.artifacts/status-check/`、`.artifacts/checks/run-DAze415b/`、
`.artifacts/checks/run-qzGsgrXt/`）在复核结束后删除，未保留训练出的策略。

#### 追加（2026-10-27 晚）：GPU 恢复可见，2048 环境需下调接触缓冲区

上一条说"无 GPU 设备节点"只在当时成立。用户随后放开了设备节点，现在
`/dev/nvidia0`、`/dev/nvidiactl`、`/dev/nvidia-uvm` 都可见，`nvidia-smi` 正常，
`torch.cuda.is_available()` 为 `True`。**GPU 训练现在可以实际运行。**

但 `--num-envs 2048` 用任务默认的 `nconmax=128`、`njmax=512` 会失败：

```
RuntimeError: Graph creation error: Warp CUDA error 2: out of memory
  (in function wp_cuda_graph_create_exec)
```

失败点不是普通的张量分配，而是 Warp 在捕获 CUDA graph 时分配执行实例。默认缓冲把
2048 世界的图捕获推过了 8 GB。实测各规模占用（`num_steps_per_env=24`，含 mjlab/Warp
常驻部分约 3.6 GB，其中外部 `Go2-SuperMimic-Flat` 进程占 3.1 GB）：

| 环境数 | 缓冲区 | 结果 | 占用 |
|---|---|---|---|
| 1024 | 128 / 512 | 通过，graph 生效 | — |
| 1536 | 128 / 512 | 通过 | 6987 MiB |
| 2048 | 128 / 512 | **OOM（graph 捕获）** | — |
| 2048 | 64 / 512 | 通过 | 6166 MiB |
| 2048 | 96 / 384 | 通过 | 6985 MiB |
| 2048 | 64 / 256 | 通过 | 6298 MiB |

因为缓冲区是每世界上限、不是实际用量，先测了这台机器人真实的接触/约束峰值
（512 环境、随机大幅动作 500 步、故意跌倒并自碰撞）：

```
max_contacts_per_world = 13
max_nefc              = 55
```

即 `nconmax=64`、`njmax=256` 仍是实测峰值的 4.9 倍 / 4.7 倍余量。为保留默认行为、
不把临时实验值写死进任务配置，`duck-train` 新增两个可选覆盖参数
`--nconmax`、`--njmax`；不传时仍用任务默认的 `128 / 512`。

**吞吐很差，原因是外部争抢而非代码**。2048 环境实测 5.93 s/iter（12 次迭代，
5.08–7.32 s），约 8290 env-step/s；同样条件下 1024 环境是 4.5 s/iter。
单步拆解开销（2048 环境、24 次采样）：

```
env.step 本身            94.1 ms/步
env.step + nonzero.tolist 95.3 ms/步
torch.nonzero(...).tolist() 0.5 ms/步
```

即 95% 时间在 `env.step`，`runner.py` 里每步的 host 同步只占 0.5 ms，不是瓶颈。
`nvidia-smi` 显示另一个 `Go2-SuperMimic-Flat`（pid 499718，占 3.1 GB、利用率约 90%）
同时在跑，这是耗时随规模不降反升的原因。

按 5.93 s/iter 估算，20000 迭代约 **33 小时**（1.4 天）；若外部进程退出应明显加快。
checkpoint 每个约 4.5 MB，1000 轮存一次共 20 个，约 90 MB。

本轮临时产物（`.artifacts/gpu-probe/`、`.artifacts/checks/run-8e9FD43X/`、
`.artifacts/checks/run-jSndYcPu/`）在复核结束后删除。`make check` 通过
（179 项测试 + 8 subtests）；改动仅新增两个 CLI 参数。

### T044 修复自碰撞传感器误计地面接触

状态：完成。依赖 T023；用户报告"脚与地面的接触也算成自碰撞"。

目标：让 `self_collisions` 只统计机器人自身两处之间的接触，不再把站立时
的足底-地面接触算进去。

问题定位：`_self_collision_sensor()` 原本是 `primary=subtree:base_link`、
`secondary=None`。`secondary=None` 在 mjlab 里表示**不加参考过滤**，因此该传感器会
命中机器人与任意物体的接触。实测（`num_envs=2`，零动作）：

| 状态 | `found`（旧） | `found`（修复后） |
|---|---|---|
| HOME 站立（贴地） | `8.0` | `0.0` |
| 整体抬高 1 m | `0.0` | `0.0` |
| 腿折到极限（真实自碰撞） | `2.0` | `2.0` |

按 `reward_manager._step_reward` 拆开单步期望值（32 环境、噪声 0.3、100 步）：

```
track_linear_velocity   +0.01782
track_angular_velocity  +0.01530
upright                 +0.02087
其余惩罚项合计           -0.00526
self_collisions         -0.10885   ← 旧值，一个人顶掉全部正奖励
```

即站立本身每步被扣 `-0.109`，而正奖励合计只有约 `+0.054`，`self_collisions`
一项就主导了任务奖励，且方向与"学会走路"无关。

修复：`secondary` 改为 `ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT)`，
与 mjlab 参考任务 `tasks/velocity/config/go1/env_cfgs.py` 的 `subtree` 对 `subtree`
写法一致。改动前 `docs/development.md` 已写"用 `subtree=base_link` 的接触传感器"，
与实现不符，本次一并纠正。

A/B 短跑（32 环境、100 迭代、CPU、种子 0、同配置）：

| | iter 1 | iter 100 | episode 长度 |
|---|---|---|---|
| 修复前 | `-0.0611` | `-0.0561`（ep_return `-1.06`） | 22.0 → 18.8 |
| 修复后 | `-0.0027` | `+0.0074`（ep_return `+0.23`） | 22.0 → 29.6 |

修复后奖励转正、episode 变长；修复前奖励几乎不动且 episode 变短。这仍然只说明
奖励信号恢复正常，**不证明学会行走**。

验证：

```
uv run --no-sync python -B tools/check_velocity_env.py --device cpu
uv run --no-sync python -B -m pytest -q tests/test_velocity_env_cfg.py
```

```
zero-action hold: 100 steps, 2/16 terminations (domain randomisation on; T038 measured 0/128 without it)
self-collision while standing: raw term max 0.000 (expected 0)
random run: 300 steps, mean reward 12.982, terminations 16, truncations 0
Velocity env check passed: device=cpu, envs=16, steps=300, dt=0.02s.
```

`tests/test_velocity_env_cfg.py` 3 条通过；把 `secondary` 改回 `None` 后
有 2 条失败，说明这组测试确实能拦住该回归。`check_velocity_env.py` 新增
"站立时 `self_collisions` 必须为 0"的断言，随机跑 300 步的奖励也从 `-19.892`
变为 `+12.982`。

本节只改 `self_collisions` 口径；`feet_air_time` 在落地步为负、`feet_clearance`
读不到 `default_site_pos_w`、`BODY_MASS_RANGE` 未接入，这三项作为待办另行处理。

### T045 修复独立预览的积分器与初态

用户报告：直接运行 `python src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py`，
机器人倒地后一直抽动（而不是倒地不动），并且看不到 `init_state`。两个现象是**两个独立缺陷**，
都用 A/B 定位到具体原因，不是观感问题。

范围：只改预览入口 `__main__` 块和 `tools/check_robot.py --viewer` 的重复实现；不动训练
环境、执行器参数、源 XML 和默认增益。

**缺陷一：预览用的积分器和训练不一致。** 旧预览 `scene.compile()` 后直接交给
`viewer.launch`，拿到的是 XML 默认的显式 Euler（`mjINT_EULER`，实测编译结果
`model.opt.integrator == 0`）。训练侧 `velocity_env_cfg.py` 经 `MujocoCfg` 改用
`implicitfast`（`== 3`）。无刷关节当时 armature 为 **0**（本轮才补上 0.002，见下文
"站姿抖动"一节；此处 `0.0018` 是早期误记，实测 12 个无刷关节当时全为 0），`kd 0.4`、
`dt 0.002 s`，显式阻尼在该组合下发散：

| 积分器 | 末态根高 | 收敛后 max\|qvel\| |
|---|---|---|
| euler（旧预览） | 0.0954 m | 32.0 rad/s |
| implicitfast（训练） | 0.1655 m | 0.20 rad/s |

即"一直抽"就是显式阻尼的数值不稳定，数值上每步都在抖。同一组对照还排除了"求解器迭代
不够"这一猜测：`iterations/ls_iterations` 调成训练的 10/20 对 euler 完全没有改善
（两次都是 24.35 rad/s），换积分器是唯一有效的变量。把 `kd` 单独设为 0 时抖动降到
5.96 rad/s、只留阻尼项时为 23.75 rad/s，确认主因是速度阻尼项。

**缺陷二：`init_state` 从未生效。** mjlab 把初态写成 `init_state` 关键帧（`nkey=1`），
但要显式 `mj_resetDataKeyframe` 才会用上。旧代码只传 model 让 `viewer.launch` 自己建
`MjData`，起点是 XML 默认位姿（根高 0.171 m、全部关节为 0），关键帧里的 HOME 蹲姿
（根高 0.1534 m）根本没出现——这正是用户"看不到 init_state"的直接原因。

顺带修正一个会让预览完全无法站立的问题：本模型的 `ctrl` 是仿射 PD 输入
（`ctrl = kp·q_target`），不是力矩。若把 `ctrl` 置 0，等于命令所有腿关节回零，机器人只会
塌下去。新代码用每个执行器编译后的 `biasprm[1]` 反推 `kp`，再写 `kp·HOME_JOINT_POS`。
HD1910 编译成纯力矩电机、无位置偏置，`kp` 读作 0，头部因此最多下垂 0.1 rad（预览不建模
BAM），不影响腿部站立。

实现：常量模块新增 `make_preview()`，负责编译实体、套用 `MujocoCfg`、复位到
`init_state`、写入 HOME 保持命令；`__main__` 与 `tools/check_robot.py --viewer` 都改用它，
消掉了原先那份会静默预览不同物理的重复实现。

**按 `legged_wbc_mjlab` 参考重写入口。** 用户之后要求参考
`/home/sunteng/projects/legged_wbc_mjlab/src/assets` 与官方 microduck 的写法。该目录下
`go2/go2_constants.py`、`ri_4438/ri_4438_constants.py`、`ri_5036/`、`go2_piper/` 的入口统一是：

```python
robot = Entity(get_*_robot_cfg())
viewer.launch(robot.spec.compile())
```

它的优点是不经过 `Scene`，因此不分配 torch 张量、不需要 `device`，预览在 GPU 被训练占满时
照样能开。本轮把 `make_preview()` 改成同样的结构（`Entity` 直连 + 自己的 `_add_preview_ground`），
去掉了 `Scene` 依赖，函数签名从 `make_preview(device)` 变成 `make_preview()`。

但参考写法**不能照抄**，实测对比（2500 步）：

| 写法 | 根高轨迹 | 末态 max\|qvel\| |
|---|---|---|
| 参考式单行（无地面、无 `MujocoCfg`、不应用关键帧） | 0.171 → -4.76 → -19.50 → -44.05 → -78.41 | 49.06 rad/s |
| 本轮 `make_preview()` | 0.1534 → 0.1501 → 0.1498 → 0.1498 → 0.1497 | 0.55 rad/s |

参考式单行在本机连地面都没有（`robot.spec` 只有机器人本体），直接自由落体到 `z=-78`。所以
本轮只借用它的**结构**，保留已验证的两处差别：套用 `MujocoCfg`、显式 `mj_resetDataKeyframe`。
地面、棋盘纹理和定向光按 mjlab `TerrainEntityCfg(terrain_type="plane")` 的默认值补在预览 spec 上
（`friction=(1.0, 0.005, 0.0001)`、`texrepeat=(4,4)`、`sun` 0.0/0.0/1.5 定向），机器人 XML 仍然
不含地面和灯光（T016/T039），预览不会出现两个地面。

关键帧里存的 `ctrl` 是**关节目标角**（如 `0.85`），不是运行时命令（`kp·q_target = 8.5`）。
这一点在参考写法里看不出来，因为参考项目用的是 plain `motor`。本轮据此把 `ctrl` 的推导
改成 `-biasprm[:, 1] * key.ctrl`，和原先按名字查 `HOME_JOINT_POS` 的结果逐元素一致
（实测 `allclose` 为真），但少了一层名字匹配、也不会在两处定义之间漂移。

验收：

```
make check
  → 178 passed, 8 subtests passed（新增 3 条，原 175）

uv run --no-sync python -B src/ht_microduck/robots/ht_microduck/ht_microduck_constants.py
  → GLX: Failed to create context（本沙箱无 /dev/nvidia*，仅图形受限，CUDA 报错已消失）
```

无头 A/B（2500 步，同一场景）：

| | 根高轨迹 | 末态 max\|qvel\| |
|---|---|---|
| 旧预览 | 0.171 → 0.1033 → 0.0952 → 0.0964 → 0.0982 | 29.57 rad/s |
| 新预览 | 0.1534 → 0.1501 → 0.1498 → 0.1498 → 0.1497 | 0.55 rad/s |

新增 3 条测试（`tests/test_robot_entity.py`）：`test_preview_starts_from_the_init_state_keyframe`
断言 `qpos` 等于关键帧、根高等于 `HOME_FRAME.pos[2]`、关节不全为 0、且 `ctrl == kp·key.ctrl`
（同时仍逐项对照 `kp·HOME_JOINT_POS`）；`test_preview_uses_the_training_integrator_and_holds_the_stance`
断言积分器与 `MujocoCfg` 一致且不是 euler，并跑 1000 步后要求 `max|qvel| < 2.0`、根高 `> 0.1`；
`test_preview_adds_one_ground_and_light_without_touching_the_robot_xml` 断言预览只有一个
`terrain` 平面、摩擦 `1.0`、1 个灯光/纹理/材质，且源 XML 仍无灯光与平面。把两处修复同时
回退验证：前 2 条都失败，其余照常通过，说明这组测试能拦住该回归。

未解决/未验证：本沙箱没有 GPU 设备节点，`nvidia-smi` 显示 RTX 4060 被外部
`Go2-Chase-Flat` 训练占用，且 GLX 无法创建上下文，因此**无法实际打开窗口验证 GUI 观感**，
只能验证其编译、初态、积分器、地面装配与无头物理行为。需要用户在有图形和空闲 GPU 的机器上
跑一次确认。参考目录 `legged_wbc_mjlab` 与官方 microduck 仓库本轮**只读**，未修改，也不受
GitHub 网络受限影响（本地已存在该目录）。

#### 追加：站姿抖动来自缺失的转子惯量（armature）

用户反馈“会抖动”。无头定位后确认：站姿高度稳定（`root z` 均值 0.14975、峰峰值 0.00012 m），
但关节持续高频嗡嗡（末 5 s 平均 `|qvel|`：`l_ankle 0.2665`、`l_hip_pitch 0.2241`、
`l_calf 0.1970`），FFT 主频 **6.0 Hz**，ankle `qvel` 每 100 步换向约 7 次。

排除项（同一场景 2500 步，均值 `|qvel|`）：求解器迭代 `10/20`、`50/25`、`100/50`、`200/100`
结果**完全相同**（0.0961）；`implicit` 0.0959、`rk4` 反而 7.6299；接触稳定不抖（`ncon`
恒为 6，左右足 `fz` 均值 16.704/15.590 N，总重 32.321 N）；**去掉重力抖动直接归零**；
`dt` 减半抖动也减半（0.1055→0.0626→0.0341→0.0173）——这是显式/隐式 PD 环路“欠惯性”的特征，
不是求解器或接触问题。逐执行器审计发现 12 个无刷关节的 `dof_armature` **全为 0**
（只有 3 个 HD1910 舵机有 `0.001827`，来自 BAM 厂家辨识值），即关节几乎没有惯性。

修复：`BRUSHLESS_ACTUATOR_CFG` 显式传 `armature=BRUSHLESS_ARMATURE`，取值由用户提供为
`0.0069753532276 kg·m²`（关节输出侧）。armature 扫描（同一站姿、同一场景）：

| armature | 均值 \|qvel\| | root z 峰峰值 | 渲染帧间像素差 |
|---|---|---|---|
| 无（0） | 0.10518 | 0.000115 | 1.706 |
| 0.001 | 0.0363 | — | — |
| 0.002（早期占位） | 0.02494 | 0.000124 | 0.285 |
| **0.0069753532276（采用）** | **0.00366** | **0.000006** | **0.071** |
| 0.01 | 0.00264 | 0.000004 | 0.068 |

渲染帧间像素差用 EGL 离屏渲染客观量化“肉眼可见的抖”（本沙箱无法查看渲染图）：无 armature
1.706、占位 0.002 时 0.285、真实值 0.0069753532276 时 **0.071**，即真实值把可见抖动降
**24 倍**（占位值只有 6 倍）。训练环境同样受益：零动作 200 步平均 `|qvel|` 从 **0.193 降到
0.00649**（30 倍），`root z` 0.1503 不变。

奖励用**同一协议**（8 环境、种子 0、150 步零动作）对照，避免换协议造成的假象：

| armature | 全程 150 步均值 | 后 100 步均值 |
|---|---|---|
| 0（无） | 0.0983 | 0.1001 |
| 0.002（占位） | 0.1034 | 0.1033 |
| **0.0069753532276** | **0.1034** | **0.1033** |

即真实值与占位值奖励相同、比无 armature 略好，**没有变差**。（期间出现过一次
0.0811，是本轮把环境数从 8 改成 4、并只统计后 50 步造成的协议差异，非真实退化，已用上表
同协议复测排除。）

**取值来源：** 用户于 2026-10-27 提供，为 HTDW-3532 的关节侧 armature。在此之前本轮已查证
全部可得公开来源均无该参数——用户提供的 `HTDW-3532-02-DNE_user_datasheet.png` 只有转速–力矩
曲线；本地 `params/README.md` 明确“不推定转子惯量”；高擎官网产品页 15 个型号**已不含 3532**
（已下架），官方手册 `book.hightorque.cn/Module20260917`（15 个型号）**完全没有惯量字段**；
官方“模型”下载 `HTDW-3532-02-DNE.zip` 只有一个 SolidWorks `STEP` 几何体（无质量属性）；
`store.hightorque.cn` 该型号页已 404；参考项目 `legged_wbc_mjlab` 对 RI-5036 同样写
“没有推断…转子惯量”（其 `docs/development.md:2314`）。因此该值此前只能用占位值
`0.002`（沿用官方 duck MJCF 对每个关节的统一硬编码，见 `src/htdk/model.py:64`），本轮已用
用户提供的真实值替换。

**合理性核对（仅佐证，不是来源）：** 按 32:1 折算回转子侧
`0.0069753532276 / 32² = 6.81e-6 kg·m² = 68.1 g·cm²`，与该尺寸电机约 60 g·cm² 的钢质转子
量级一致；而占位值 `0.002` 只相当于 19.5 g·cm²。数值带 11 位有效数字，应按用户给定保留，
不做多余修约。舵机 `0.001827` 不同，它是飞特 BAM 厂家辨识值
（`bam/params/feetech_hd1910_7_4V/m6.json`，固定到 commit、SHA256 记录在
`actuators/HD_1910_C001/params/README.md`），属厂家模型参数而非本机实测；用户明确表示
舵机的值不清楚，本轮不臆测替换。

另：头部 `head_yaw` 站姿仍缓慢漂移 5.4°、`mouth` 7.4°（`ptp` 3.96°），原因是预览里 3 个
舵机的 BAM 模型不参与编译（`biastype=NONE`、位置增益为 0），属无驱动自由下垂，不是高频抖动。
实测把头部按 `kp=7.345/kd=0.1074` 固定后帧间像素差仅 0.285→0.277（占位值下的测试），
对观感无影响，本轮不为预览引入 BAM 建模。

验收：`make check` → **179 passed**（新增
`test_brushless_joints_carry_reflected_rotor_inertia_and_stop_buzzing`，断言 12 个无刷关节
`dof_armature == BRUSHLESS_ARMATURE`、站姿 3 s 平均 `|qvel| < 0.06`、根高 `> 0.14`）；
`tests/test_robot_actuators.py` 里原先断言 `armature is None` / `dof_armature == 0.0` 的两处
改为断言 `BRUSHLESS_ARMATURE`（源 XML 仍断言 `armature == 0.0`，因为改动只经 cfg，不动 XML）。
把 `armature=BRUSHLESS_ARMATURE` 摘掉后这 4 条测试全部失败，恢复后通过，确认能拦住回归。

## 新任务模板

将新任务加入上方任务表，并在本页添加以下内容。只保留与任务有关的字段和检查。

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

该命令依次检查锁文件、Python 代码、已有测试、机器人模型，以及已跟踪文件暂存和未暂存的差异空白。
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
| `make lock-check` | 离线检查依赖声明与锁文件一致性 |
| `make viewer` | 在有图形桌面的终端中打开静态预览 |

测试入口设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，避免系统 ROS 等环境的 pytest 插件干扰测试启动。
以后确实需要第三方 pytest 插件时，在测试入口中用 `-p` 明确加载。
GPU 验证按安装文档执行；训练和导出命令在对应模块实现后加入专项验收。

## Git 与实验记录

基线整理完成后，在 `task/Txxx-short-name` 分支开发任务，再将通过验收的变更合入 `main`。
已有未提交改动时先识别归属，避免分支切换或暂存操作混入其他任务。
一个提交围绕一个目的，提交信息可使用 `feat:`、`fix:`、`test:`、`docs:` 或 `chore:`。
是否提交、合并或推送按当前会话授权执行。

默认交付工作区，任务完成、设计或审查通过不授予 Git 写操作权限；已有明确授权持续有效。
获授权后使用 `<type>(<scope>): <简短中文描述>`，按实际目的选择类型和稳定模块名称，
暂存时列出具体文件，再检查暂存差异，避免混入既有改动。

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
[设计](design/htdw3532_nt.md)，问题与独立复核见 [审查记录](review/htdw3532_nt.md)。

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
