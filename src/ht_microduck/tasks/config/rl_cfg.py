"""Network, PPO and training schedules for the five registered HT-Duck tasks.

The configurations retain their independent objects and task-specific limits.
Only the head variant copies the walking recipe, as it did before this split.
"""

from copy import deepcopy

from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg

from ht_microduck.tasks.config.flat_velocity_env_cfg import NUM_STEPS_PER_ENV
from ht_microduck.tasks.config.flat_velstand_env_cfg import assert_curriculum_units

# Network widths and PPO hyperparameters match the official microduck_rl task.
FlatVelocityRlCfg = RslRlOnPolicyRunnerCfg(
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
    # TensorBoard instead of wandb: this project has no wandb account wired up,
    # and the events file is the only writer the log layout requires.
    logger="tensorboard",
    experiment_name="flat_velocity",
    run_name="velocity",
    save_interval=250,
    num_steps_per_env=NUM_STEPS_PER_ENV,
    max_iterations=50_000,
)

# Same network and PPO schedule as the walking task, so a stand-up policy is
# comparable with the velocity one and can be distilled the same way.
StandUpRlCfg = RslRlOnPolicyRunnerCfg(
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
    critic=RslRlModelCfg(
        hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True
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
    experiment_name="flat_standup",
    run_name="standup",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=15_000,
)

# Same network and PPO schedule as the walking task.
SitStandRlCfg = RslRlOnPolicyRunnerCfg(
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
    critic=RslRlModelCfg(
        hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True
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
    experiment_name="flat_sitstand",
    run_name="sitstand",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=15_000,
)

# 前坐任务只改变任务目标与日志归属，网络和PPO沿用官方坐站配方，配置对象保持独立。
SitStandForwardRlCfg = deepcopy(SitStandRlCfg)
SitStandForwardRlCfg.experiment_name = "flat_sitstand_forward"
SitStandForwardRlCfg.run_name = "sitstand_forward_base_v3"

# v4使用相同网络与PPO，以独立任务和目录保留v3对照。
SitStandForwardV4RlCfg = deepcopy(SitStandForwardRlCfg)
SitStandForwardV4RlCfg.experiment_name = "flat_sitstand_forward_v4"
SitStandForwardV4RlCfg.run_name = "forward_v4_hold"

VelStandRlCfg = RslRlOnPolicyRunnerCfg(
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
    critic=RslRlModelCfg(
        hidden_dims=(512, 256, 128), activation="elu", obs_normalization=True
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
    experiment_name="flat_velstand",
    run_name="velstand",
    save_interval=250,
    num_steps_per_env=24,
    max_iterations=6_000,
)

VelocityHeadRlCfg = deepcopy(FlatVelocityRlCfg)
VelocityHeadRlCfg.experiment_name = "flat_velocity_head"
VelocityHeadRlCfg.run_name = "velocity_head"

# Keep curriculum environment steps aligned with the rollout length.
assert_curriculum_units(VelStandRlCfg)
