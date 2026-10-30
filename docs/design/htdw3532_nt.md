# 功能设计：HTDW-3532 NT-PD 执行器

## 目标与范围

任务与状态见 [T035](../archive/development_tasks.md#t035-实现并接入-3532-nt-pd-执行器)。
现有无刷原生位置 PD 只限制固定力矩，新实现以输出轴实际速度计算分段 NT 驱动上限，
保持 12 个无刷、3 个 HD1910 BAM 的关节归属和顺序。源码、参数与来源资源都保存在独立 Python 包中。
执行器不导入机器人或任务模块；不增加奖励、训练框架或未标定的电气/热模型。

## 依据与假设

| 判断 | 依据 | 边界与验证 |
|---|---|---|
| 24 V 输出轴曲线 | T034 的参考 `duck_project/src/htdk/motor.py`、`actuator.py`、JSON 与原始资料 PNG；SHA256 见 T034 | 图像采样近似，不是本机实测；锚点与中点对照独立插值 |
| 正负驱动使用同一包络，超速驱动归零 | 参考 `actuator.py:23–44` | 制动仅沿用固定上限，缺少实测制动/再生曲线；覆盖四象限与零速度 |
| 保持本地增益与被动参数 | constants 的 `10/0.4/2`、XML 的 `0.02` 阻尼和 `3.7 N·m` 总限幅 | 仿真假设，未标定；检查编译模型与运行时控制 |
| 保留原生隐式 PD 积分 | mjlab 1.6.0 的 native PD 与 MuJoCo 3.11 affine bias；本轮正式场景诊断 | 直接显式 PD 在 dt0.002 下出现约53rad/s高频振荡和持续饱和；原生 affine 原型恢复旧根高/力矩，不修改增益、惯量或步长 |
| 参考类不能原样复制 | 本机 `IdealPdActuator` 没有参考代码调用的 `_clip_effort`，T034 已核对官方 v1.6.0 | 使用当前增益/`force_limit` 与原生 affine 接口，不修改上游包 |

默认曲线：rpm `(0,26,59,92,128,167,211,258,300)`，N·m `(3.7,3.5,3,2.5,2,1.5,1,0.5,0)`。
减速比 32 仅为元数据，不再作用于输出轴数值。额定 `0.6 N·m` 与堵转 `3.7 N·m` 分开记录；
固定限幅仍为 `2 N·m` 的仿真假设，不表示持续额定能力。曲线不按未知带载电压自动缩放。

## 模块、接口与兼容性

| 文件或模块 | 职责与接口 | 兼容性与异常 |
|---|---|---|
| `actuators/HTDW_3532_02_DNE/model.py` | 冻结参数 `HTDW3532Parameters`；`load_htdw3532_parameters(json_path=None)`；`motoring_torque_limit(velocity, parameters)`；`clip_nt_torque(torque, velocity, effort_limit, parameters)` | 参数验证有限、非负、rpm 严格递增、力矩单调不增、端点有效；无外部目录运行依赖 |
| 同目录 `nt_actuator.py` | `HTDW3532ActuatorCfg(IdealPdActuatorCfg)`，增加可选 `json_path`；`HTDW3532Actuator` 持有 `.parameters`，自定义原生 affine PD 与每环境 NT 范围；`htdw3532_init` 声明模型字段 | 仅 JOINT 单轴铰链；有限非负增益与正有限固定限幅，不超过参数堵转值；预先检查目标，不额外推定实机惯量/摩擦 |
| 同目录 `params/` | 有来源的 JSON、原始 PNG 和参数说明 | 仅移植电机参数，移除参考项目的关节分组和失效绝对路径；原图保留原字节与 SHA |
| `actuators/__init__.py` 与 constants | 导出配置和类；替换 `BRUSHLESS_ACTUATOR_CFG` 类型，保持现有数值/延迟 | 不改变策略位置目标、关节顺序、初态、XML 与舵机参数 |
| 正式工具与测试 | 核验 affine 控制项、实际力矩、新曲线和真实生命周期 | 原无刷 `ctrl` 是 rad 位置目标，现在是 N·m 的 PD 目标项；最终力矩还含原生 bias 与 NT 限幅，不直接等于 `ctrl` |

所有 `ActuatorCmd` 字段形状为 `(num_envs, num_targets)`；关节按 cfg 解析的目标顺序。
`position_target/pos` 为 rad，`velocity_target/vel` 为 rad/s，`effort_target` 为 N·m；
纯模型函数输出为同形状、同设备/浮点类型的输出轴 N·m；执行器 `compute` 返回同形状的 affine 目标项。
运行时参数张量遵循 mjlab 的设备和增益配置。
参数对象提供 `.voltage_v`、`.gear_ratio`、`.rpm`、`.motoring_torque_nm`、`.stall_torque_nm`、
`.continuous_rated_torque_nm`；JSON 的数据与原始出处分别记录。

每个物理步：

1. mjlab 对位置/速度/前馈目标统一延迟一次，位置与速度反馈读取当前状态。
2. 写 `ctrl = kp*q_target + kd*dq_target + tau_ff`；原生 unit gain、affine bias 为 `-kp*q-kd*dq`，
   因而未限幅力矩仍是完整 PD。禁用 ctrl 限幅，避免绝对位置较大时错误截断 PD 目标项。
3. 按当前速度更新原生 `actuator_forcerange`：正速度 `[-fixed, min(fixed,NT)]`，
   负速度 `[-min(fixed,NT), fixed]`，零速度为对称固定范围；由原生求解器限幅并处理 `-kd*dq` 导数。
4. `abs(dq) >= 300 rpm` 时同向驱动为零，反向制动仍允许固定限幅；零 PD 请求保持零，不强加反电动势制动。

这使瞬时静态力矩与纯函数 `clip_nt_torque` 等价，同时保留原生隐式速度积分。
自定义 `compute` 用一组 12 通道 Torch 运算，不继承 `BuiltinPositionActuator`，避免其组路由跳过自定义计算，
也不进入 IdealPd 自动融合。不新增自己的历史/延迟缓冲；reset 恢复所选环境的对称范围和当前增益，
局部 reset 不影响其他环境。所有曲线运算留在 Torch 原设备，不在计算路径使用 NumPy/CPU 同步。
运行时 `set_effort_limit` 只用于降额，控制范围额外受创建执行器时保存的固定上限约束，
不能通过字段写入解除初始上限或 XML 总限幅。不额外裁剪位置目标，沿用现有本机控制契约。

`actuator_forcerange` 和 `actuator_biasprm` 必须按环境独立分配，后者保证 `set_gains` 仍生效。
环境注册 `htdw3532_init` startup 事件；独立 Scene/Simulation 在控制/reset 前调用
`sim.expand_model_fields(("actuator_forcerange", "actuator_biasprm"))`，与现有 BAM 字段一起展开。
执行器每次从 ModelBridge 重读字段，禁止缓存展开前的视图；检测字段未展开时报出明确错误。
模型重分配通过 Simulation 的正式 API 完成，让 CUDA graph 重捕获指向新数组。
目前没有训练、回放、评估或策略导出模块；以后均复用实体配置，不能把仅位置目标的静态 viewer 当作动态执行器回放。

## 实施与协作

| 负责人 | 唯一允许修改的文件 | 交回与依赖 |
|---|---|---|
| 电机实现代理 | 新目录 `src/ht_microduck/actuators/HTDW_3532_02_DNE/` | 按上述 API 实现模型、类与有来源数据；不改根导出/机器人/测试 |
| 测试代理 | `tests/test_htdw3532_actuator.py`、`tests/test_robot_actuators.py`、`tests/test_robot_entity.py` | 对照上述 API 与独立期望值；编译属性改为 motor，GPU 由主代理统一运行 |
| 主代理 | 根导出、constants、两项正式工具、README、开发/设计/审查文档 | 集成、同步控制通道、专项 GPU 与打包验收；不覆盖两位代理负责文件 |
| 独立审查代理 | 默认只读全体交付 | 编码前检查本设计，最终覆盖代码/资源/测试/文档/运行证据，问题交作者修复并复核 |

基线位于 `.artifacts/t035-nt/before.json` 和 `before/`。共享 GPU 由主代理独占，两个正式入口顺序执行。
各代理临时文件限于本仓库 `.artifacts/` 的各自子目录，不写参考项目，不暂存/提交 Git。

## 验收与结果

| 验证 | 通过标准 | 当前结果 |
|---|---|---|
| `make check` 与 CPU 专项 | 锚点/中点/类型/四象限/三类目标/无效参数，原生 affine 力矩、ctrl不误限幅、模型字段独立与reset、15控制通道及被动属性通过 | 通过：131项测试+8子测试；3文件专项67项；最终字段异常分支4项 |
| 混合执行器正式工具 | `cuda:0`、seed1910、4 环境、300 步、dt0.002、每次超时180秒；延迟、局部 reset、阶跃保持，以及高速 NT 控制通过 | 通过：力矩±0.35 N·m；保持误差0.000006/0.000566rad；高速包络与64步延迟通过 |
| 真实模型正式工具 | 同设备/种子/环境数，150 步，dt0.002、超时180秒；接地、有限值、目标映射、限幅和 reset 通过；与原生PD中性短跑对照，增加速度界防止有限值掩盖高频振荡 | 通过：根高0.166165–0.166172m，峰值0.138278 N·m，峰速0.184298rad/s |
| 离线 wheel | 参数 JSON/PNG/代码均包含，脱离参考目录可加载 | 通过：37个包内代码/资源文件逐字节一致；解包后异cwd加载参数与整机编译通过 |
| 独立审查 | [审查记录](../review/htdw3532_nt.md) 的必要问题全部关闭 | 独立审查通过，R1/R2关闭，最终文档已复核 |

具体命令、实际指标、清理与限制补记至 T035 完成记录；不启动完整训练，不宣称站立或实机参数已验证。

## 积分方案的本地依据

同种子、4环境、150步、dt0.002 的正式场景对照：直接显式 PD 曾出现末根高
`0.124987–0.160429 m`、峰值 `2 N·m`；追加探针看到踝峰速约 `53 rad/s`、多通道持续饱和。
原生 PD 与 affine NT 原型均为末根高 `0.166165–0.166172 m`、峰值 `0.138278 N·m`，
关节峰速约 `0.1843 rad/s`。这些是短跑集成证据，不是稳定站立验收。
因此最终方案保留原生 PD 积分，由 Python 只更新包络和目标项。

核查位置：本机 `mujoco_warp/_src/forward.py:1015–1029` 的 affine/每环境力矩范围，
`derivative.py:106–143` 的 bias 速度导数与饱和处理；
[MuJoCo 3.11 积分说明](https://mujoco.readthedocs.io/en/3.11.0/computation/index.html#numerical-integration)
及 [general 执行器](https://mujoco.readthedocs.io/en/3.11.0/XMLreference.html#actuator-general)。
