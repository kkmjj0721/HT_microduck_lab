# rsl_rl — PPO 与网络设计参考

这是 **RSL-RL 的 PPO 算法与网络设计** 的只读镜像，放在项目根目录，方便直接对照阅读。
**不含**环境、奖励、任务配置、导出、发布等训练框架代码。

## 为什么是 rsl_rl

官方 `pollen-robotics/microduck_rl` **没有自己实现 PPO 和网络**：

- 它的 `train_cli.py` 只有 1.4 KB，把 `main()` 转发给 `mjlab.scripts.train`；
- PPO 更新、ActorCritic 网络、RolloutStorage 全部来自 `rsl-rl-lib`；
- 官方自己写的唯一算法件是 `tasks/symmetry.py`。

所以"官方 PPO / 网络源码"就在 `rsl_rl` 里。本机 `.venv` 装的是 `rsl-rl-lib==5.4.2`
（`mjlab==1.6.0` 的依赖），与官方 `mjlab==1.3.0` 用的版本一致。

## 来源

| 项 | 值 |
|---|---|
| 包 | `rsl-rl-lib==5.4.2`（本机 `.venv/lib/python3.12/site-packages/rsl_rl`） |
| 许可证 | BSD-3-Clause，Copyright (c) 2021-2026 ETH Zurich and NVIDIA CORPORATION（见 `LICENSE`） |
| 规模 | 27 个文件 / 约 3900 行 / 256 KB |

## 内容

| 文件 | 行数 | 作用 |
|---|---|---|
| `algorithms/ppo.py` | 488 | ★ PPO 主逻辑：GAE、clipped surrogate、value loss、entropy、adaptive KL、mini-batch |
| `models/mlp_model.py` | 256 | ★ ActorCritic 主体：obs 归一化 → MLP → 分布 / 标量 |
| `models/cnn_model.py` | 253 | 视觉输入的 CNN 变体 |
| `models/rnn_model.py` | 249 | RNN（GRU/LSTM）变体，带 hidden state |
| `modules/mlp.py` | 95 | ★ MLP 骨架与激活堆叠 |
| `modules/distribution.py` | 464 | Gaussian / Beta / HeteroscedasticGaussian |
| `modules/normalization.py` | 131 | EmpiricalNormalization 及折扣变体 |
| `storage/rollout_storage.py` | 357 | ★ Rollout 存储、mini-batch 生成、GAE 回填、recurrent 序列切分 |
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

## 目录同名带来的遮蔽问题（重要）

这个目录位于项目根，而 Python 把当前目录排在 `sys.path` 最前，**它会遮蔽已安装的
`rsl_rl` wheel**。`mjlab.rl` 会 `from rsl_rl.runners import OnPolicyRunner`，
而 `runners/`、`utils/logger.py` 等不在本镜像里，因此会直接报：

```
ModuleNotFoundError: No module named 'rsl_rl.runners'
```

处理方式：`_fallback.py` 把已安装包的对应目录追加到各包的 `__path__` 之后。
本目录的文件优先，缺失的从 wheel 补。同时 `algorithms/__init__.py` 在可用时
重新导出 `Distillation`，因为 wheel 的 `runners` 依赖它。

结果是：`import mjlab.rl` 与本地 `from rsl_rl.algorithms.ppo import PPO` 可共存，
且本地文件确实优先（已验证 `PPO.__file__` 指向本目录）。
`_fallback.py` 是本项目新增的唯一辅助文件，其余为上游原样代码。

若不需要这份参考，**直接删除整个 `rsl_rl/` 目录**即可，项目会回落到已安装的 wheel。

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

13 个任务共用同一套超参，只有 `max_iterations` 不同。

## 已验证

- `make check` 通过：`134 passed, 1 warning, 8 subtests passed`，模型检查通过。
- `import mjlab.rl` 与 `MjlabOnPolicyRunner` 可正常导入。
- 本地 `PPO` / `MLPModel` / `RolloutStorage` 等全部可导入，且解析到本目录文件。
- 端到端冒烟：8 环境 / 12 维观测 / 4 维动作的合成 `VecEnv`，走
  `construct_algorithm → act → process_env_step → compute_returns → update`
  共 8 次迭代，entropy 单调下降 5.670 → 5.604，说明策略确实在更新。

## 与本地约束的差异

- 本机 `mjlab==1.6.0`，官方 `1.3.0`；`rsl_rl` 两边都是 5.4.2，这部分无版本差。
- 官方 14 关节 / XL330；本机 15 关节 / 12 无刷 + 3 舵机。网络输入维度需按本机观测维度定。
- 按项目约定，生产实现写在 `src/ht_microduck/`，本目录仅作只读参考。
