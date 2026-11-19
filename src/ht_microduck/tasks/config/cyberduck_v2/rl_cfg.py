# Copyright (c) 2026-2027 zh
"""
内容：
    配置 CyberDuck V2 独立任务的 RSL-RL 网络、PPO 与日志归属。

网络和 PPO 采用项目已有的配置类；下列数值为首版仿真训练默认值，未验证策略效果。
"""

from copy import deepcopy
from dataclasses import dataclass

from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg

from ht_microduck.tasks.cyberduck_v2_contract import ACTION_CONTRACT_VERSION

CyberDuckV2VelocityRlCfg = RslRlOnPolicyRunnerCfg(
    actor=RslRlModelCfg(
        hidden_dims=(512, 256, 128),
        activation="elu",
        obs_normalization=True,
        distribution_cfg={
            "class_name": "GaussianDistribution",
            "init_std": 0.5,
            "std_type": "scalar",
        },
    ),
    critic=RslRlModelCfg(
        hidden_dims=(512, 256, 128),
        activation="elu",
        obs_normalization=True,
    ),
    algorithm=RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    ),
    logger="tensorboard",
    experiment_name="cyberduck_v2_flat_velocity",
    run_name=f"{ACTION_CONTRACT_VERSION}_wz05_pose_go2_v1",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=10_000,
)


@dataclass
class CyberDuckRouladePpoCfg(RslRlPpoAlgorithmCfg):
    """沿用官方 Roulade 的镜像损失接口，通用 PPO 实现保持在 RSL-RL。"""

    symmetry_cfg: dict | None = None


# 来源：microduck_rl@bae39f59 的 MicroduckRouladeRlCfg；网络、PPO 数值及课程 rollout 均保留。
CyberDuckV2RouladeRlCfg = RslRlOnPolicyRunnerCfg(
    actor=RslRlModelCfg(
        hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True,
        distribution_cfg={"class_name": "GaussianDistribution", "init_std": 1.0, "std_type": "scalar"},
    ),
    critic=RslRlModelCfg(hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True),
    algorithm=CyberDuckRouladePpoCfg(
        value_loss_coef=1.0, use_clipped_value_loss=True, clip_param=0.2,
        entropy_coef=0.01, num_learning_epochs=5, num_mini_batches=4,
        learning_rate=1.0e-3, schedule="adaptive", gamma=0.99, lam=0.95,
        desired_kl=0.01, max_grad_norm=1.0,
        symmetry_cfg={
            "use_data_augmentation": False, "use_mirror_loss": True, "mirror_loss_coeff": 0.5,
            "data_augmentation_func": "ht_microduck.tasks.rl.cyberduck_roulade_symmetry:mirror_roulade",
        },
    ),
    logger="tensorboard", experiment_name="cyberduck_v2_roulade",
    run_name="roulade_p12_v2_obs46_v1", save_interval=250,
    num_steps_per_env=24, max_iterations=10_000,
)

# 仅隔离本机适配实验的产物；网络、PPO和镜像损失均沿用基线。
CyberDuckV2RouladeRecoveryRlCfg = deepcopy(CyberDuckV2RouladeRlCfg)
CyberDuckV2RouladeRecoveryRlCfg.experiment_name = "cyberduck_v2_roulade_recovery"
CyberDuckV2RouladeRecoveryRlCfg.run_name = "roulade_recovery_obs48_v4_standhome_v1"

# 2026-11-15：把最终验收版本的训练配方固化进任务，使 `duck-train` 一条命令即可复现。
#
# 基线用 `learning_rate=1e-3, schedule="adaptive"`。实际验收版本（§19 的五段链）
# 全程用 **3e-4 + fixed**：adaptive 在续训时会从优化器状态恢复到 2.25e-5，
# 探索严重不足，逐轮调奖励时无法继续改进。固定 3e-4 让每段都有足够探索，
# 也是最终 160 回合全通过的那组配置。此前这个值只通过训练测试的
# `--learning-rate` 参数传入，任务默认配置里没有，导致 `duck-train` 复现不出结果。
CyberDuckV2RouladeRecoveryRlCfg.algorithm.learning_rate = 3.0e-4
CyberDuckV2RouladeRecoveryRlCfg.algorithm.schedule = "fixed"
# 从零训练约需 5044 次更新（§19 五段链合计迭代数）。
# 以 1024 环境、24 steps/iter 计，1800 秒约 1070 次更新，故 5044 次约 2.4 小时。
CyberDuckV2RouladeRecoveryRlCfg.max_iterations = 6000

# 摔倒起立：起立比前滚翻需要更长探索，沿用 Recovery 的固定学习率配方
# （adaptive 在续训时会衰减到 2e-5 量级，探索不足；见上方 Recovery 说明）。
# 不启用镜像损失：镜像函数绑定前滚翻的观测布局与契约版本，起立任务只改初态与奖励。
CyberDuckV2StandUpRlCfg = RslRlOnPolicyRunnerCfg(
    actor=RslRlModelCfg(
        hidden_dims=(512, 256, 128),
        activation="elu",
        obs_normalization=True,
        distribution_cfg={
            "class_name": "GaussianDistribution",
            "init_std": 1.0,
            "std_type": "scalar",
        },
    ),
    critic=RslRlModelCfg(hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True),
    algorithm=RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=3.0e-4,
        schedule="fixed",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    ),
    logger="tensorboard",
    experiment_name="cyberduck_v2_standup",
    run_name="standup_obs46_v1",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=6000,
)
