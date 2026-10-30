# rsl_rl — 训练实际使用的 RSL-RL 代码

这是 **rsl-rl-lib 5.4.2 的完整副本**，放在项目根目录。训练、回放与导出导入的就是这份代码，
不是 `.venv` 里的 wheel。除本文件外，目录内所有文件都是上游原样内容，不在此改动风格。

## 为什么仓库内自带一份

官方 `pollen-robotics/microduck_rl` **没有自己实现 PPO 和网络**：

- 它的 `train_cli.py` 只有 1.4 KB，把 `main()` 转发给 `mjlab.scripts.train`；
- PPO 更新、ActorCritic 网络、RolloutStorage 全部来自 `rsl-rl-lib`；
- 官方自己写的唯一算法件是 `tasks/symmetry.py`。

本项目沿用同一分工，并把这份依赖放进版本控制，使"训练跑的是哪份代码"可审查、可追溯，
而不是由安装环境决定。上游 `mjlab==1.3.0` 与本地 `mjlab==1.6.0` 都用 `rsl-rl-lib==5.4.2`，
因此这份副本与本地 mjlab 的要求一致。

## 来源

| 项 | 值 |
|---|---|
| 包 | `rsl-rl-lib==5.4.2`（与 `.venv/lib/python3.12/site-packages/rsl_rl` 逐字节相同） |
| 许可证 | BSD-3-Clause，Copyright (c) 2021-2026 ETH Zurich and NVIDIA CORPORATION（见 `LICENSE`） |
| 规模 | 30 个 `.py` / 4711 行 / 312 KB |

`diff -rq rsl_rl .venv/lib/python3.12/site-packages/rsl_rl` 除 `__pycache__` 外只在仓库侧多
`LICENSE` 与 `README.md` 两个文件。

## 内容

| 文件 | 行数 | 作用 |
|---|---|---|
| `algorithms/ppo.py` | 488 | ★ PPO 主逻辑：GAE、clipped surrogate、value loss、entropy、adaptive KL、mini-batch |
| `algorithms/distillation.py` | 306 | 教师-学生蒸馏 |
| `models/mlp_model.py` | 256 | ★ ActorCritic 主体：obs 归一化 → MLP → 分布 / 标量 |
| `models/cnn_model.py` | 253 | 视觉输入的 CNN 变体 |
| `models/rnn_model.py` | 249 | RNN（GRU/LSTM）变体，带 hidden state |
| `modules/mlp.py` | 95 | ★ MLP 骨架与激活堆叠 |
| `modules/distribution.py` | 464 | Gaussian / Beta / HeteroscedasticGaussian |
| `modules/normalization.py` | 131 | EmpiricalNormalization 及折扣变体 |
| `storage/rollout_storage.py` | 357 | ★ Rollout 存储、mini-batch 生成、GAE 回填、recurrent 序列切分 |
| `runners/on_policy_runner.py` | 249 | ★ 训练循环：采样、更新、保存、恢复 |
| `runners/distillation_runner.py` | 25 | 蒸馏训练循环 |
| `utils/logger.py` | 332 | ★ 控制台面板、TensorBoard/W&B 写入、`git/` 快照 |
| `extensions/symmetry.py` | 137 | 左右对称增强与 mirror loss |
| `extensions/rnd.py` | 242 | 随机网络蒸馏 |
| `env/vec_env.py` | 93 | VecEnv 抽象接口（PPO 的依赖，非环境实现） |
| `utils/utils.py` | 389 | 激活/优化器/obs 分组解析、轨迹 padding、torch.compile 包装 |
| `utils/{log,wandb,neptune}_writer.py` | — | 日志写入器 |

## PPO 关键位置

| 机制 | 位置 |
|---|---|
| 采样并存 transition | `PPO.act()`（ppo.py:115） |
| 环境步与归一化更新 | `PPO.process_env_step()`（:128） |
| GAE + bootstrap | `PPO.compute_returns()`（:163） |
| 优化循环 | `PPO.update()`（:190） |
| 装配入口 | `PPO.construct_algorithm(obs, env, cfg, device)`（:416） |

实测 API 细节（与直觉不同）：

- `update()` **无参**，返回 `dict[str, float]`（`value` / `surrogate` / `entropy` 等）；
- `compute_returns(obs)` **无返回值**；
- 必须走 `PPO.construct_algorithm(...)`，不能直接 `PPO(actor, critic, storage, ...)`；
- cfg 需含 `multi_gpu`、`obs_groups`、`num_steps_per_env` 等键。

## 为什么不会被 wheel 抢先

本目录位于项目根，而 mjlab 也依赖同名 wheel 包，谁生效取决于 `sys.path` 顺序。
控制台脚本启动时 `sys.path[0]` 是 `.venv/bin`，默认会解析到 wheel。因此
`src/ht_microduck/__init__.py` 在 `import mjlab` 之前把仓库根插到 `sys.path` 首位，
`train_cli.py`/`play_cli.py` 都先 `import ht_microduck`。实测：

```
rsl_rl        : <repo>/rsl_rl/__init__.py
__path__      : ['<repo>/rsl_rl']
OnPolicyRunner: <repo>/rsl_rl/runners/on_policy_runner.py
Logger        : <repo>/rsl_rl/utils/logger.py
```

边界要说清楚：这个保证只在 `ht_microduck` 先被导入时成立。若调用方自己先
`import rsl_rl` 且仓库根不在 `sys.path`（例如 `python -P -c "import rsl_rl"`），拿到的仍是
wheel —— Python 会缓存首次导入的模块，包内代码无法拦截。`tests/test_rsl_rl_vendoring.py`
把这两面都写成了断言。

## 修改约束

本目录是**逐字节 vendor drop**：不接受本地补丁、不重新格式化。
`pyproject.toml` 的 ruff 配置用 `extend-exclude` + `force-exclude` 排除它。
需要改变行为时改本仓库自己的配置（`tasks/*_env_cfg.py` 的 `RslRlOnPolicyRunnerCfg`），
或在 `src/ht_microduck/` 里包装，不要改这里。

升级方式：随 `rsl-rl-lib` 版本一起整体替换本目录，同步更新本文件的规模与来源表。
**不要删除本目录**：`runners/` 与 `utils/logger.py` 都在这里，删掉后训练会直接
`ModuleNotFoundError: No module named 'rsl_rl.runners'`，不会回落到 wheel。

## 官方 microduck 超参（对照）

```python
actor/critic: hidden_dims=(512,256,128), activation="elu", obs_normalization=True
GaussianDistribution: init_std=1.0, std_type="scalar"
PPO: clip_param=0.2, entropy_coef=0.01, num_learning_epochs=5, num_mini_batches=4,
     learning_rate=1e-3, schedule="adaptive", gamma=0.99, lam=0.95,
     desired_kl=0.01, max_grad_norm=1.0, value_loss_coef=1.0,
     use_clipped_value_loss=True
runner: num_steps_per_env=24, save_interval=250, max_iterations 8k–50k
symmetry: ENABLE_SYMMETRY=False（开启时 mirror_loss_coeff=0.5）
```

13 个任务共用同一套超参，只有 `max_iterations` 不同。本机 `FlatVelocityRlCfg` 与之逐项一致。

## 已验证

- 全量测试通过，覆盖见 `tests/test_rsl_rl_vendoring.py`（来源与完整性）、
  `tests/test_training_stack.py`（真实 `MjlabOnPolicyRunner` 的迭代、梯度、checkpoint 回读）。
- `rsl_rl.__path__` 单元素；`OnPolicyRunner`、`Logger`、`PPO`、`MLPModel` 均解析到本目录。
- 移除 `runners/` 后立即 `ModuleNotFoundError`，确认不会静默回落到 wheel。
- 端到端短跑：`duck-train HtDuck-Flat-Velocity --env.scene.num-envs 2 --agent.max-iterations 2`
  退出码 0，产出 `params/{env,agent}.yaml`、`git/<repo>.diff`、`model_{0,1}.pt`、TensorBoard 事件。

## 与本地约束的差异

- 本机 `mjlab==1.6.0`，官方 `1.3.0`；`rsl_rl` 两边都是 5.4.2，这部分无版本差。
- 官方 14 关节 / XL330；本机 15 关节 / 12 无刷 + 3 舵机。网络输入维度由本机契约决定
  （actor 39 / critic 42 / action 10）。
