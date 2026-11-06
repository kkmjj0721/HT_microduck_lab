# Copyright (c) 2026-2027 zh
"""
内容：
    配置 CyberDuck V2 独立任务的 RSL-RL 网络、PPO 与日志归属。

网络和 PPO 采用项目已有的配置类；下列数值为首版仿真训练默认值，未验证策略效果。
"""

from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg

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
    run_name="rolling_h5_a10",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=10_000,
)
