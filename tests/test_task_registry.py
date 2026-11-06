"""Protect task registration, padded observations and independent RL schedules."""

from types import SimpleNamespace

import pytest
import torch
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

from ht_microduck.tasks import _assert_task_contract
from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_velstand_env_cfg import (
    assert_curriculum_units,
)
from ht_microduck.tasks.rl.runner import (
    OfficialTaskOnPolicyRunner,
    VelocityHeadOnPolicyRunner,
)

TASKS = (
    ("HtDuck-Flat-Velocity", "flat_velocity", 50_000),
    ("HtDuck-Flat-Velocity-Head", "flat_velocity_head", 50_000),
    ("HtDuck-Flat-StandUp", "flat_standup", 15_000),
    ("HtDuck-Flat-SitStand", "flat_sitstand", 15_000),
    ("HtDuck-Flat-VelStand", "flat_velstand", 6_000),
)


@pytest.mark.parametrize("task_id,experiment,max_iterations", TASKS)
@pytest.mark.parametrize("play", [False, True])
def test_registered_task_keeps_contract_and_unused_command_slots(
    task_id, experiment, max_iterations, play
):
    cfg = load_env_cfg(task_id, play=play)
    _assert_task_contract(task_id, cfg)
    assert tuple(cfg.observations["critic"].terms) == C.critic_observation_terms(task_id)
    expected_dims = {
        "HtDuck-Flat-Velocity": 76,
        "HtDuck-Flat-Velocity-Head": 76,
        "HtDuck-Flat-StandUp": 74,
        "HtDuck-Flat-SitStand": 74,
        "HtDuck-Flat-VelStand": 64,
    }
    assert C.TASK_CRITIC_OBSERVATION_DIMS[task_id] == expected_dims[task_id]
    if task_id.endswith("-VelStand"):
        assert (cfg.sim.mujoco.timestep, cfg.decimation) == (0.002, 10)
    else:
        assert (cfg.sim.mujoco.timestep, cfg.decimation) == (0.005, 4)
    assert cfg.sim.mujoco.timestep * cfg.decimation == 0.02
    env = SimpleNamespace(num_envs=2, device="cpu")
    for group in ("actor", "critic"):
        for slot, dim in (("command", 3), ("head_command", 4), ("body_command", 6)):
            term = cfg.observations[group].terms[slot]
            if "command_name" not in term.params:
                padding = term.func(env, **term.params)
                assert padding.shape == (2, dim)
                assert padding.dtype == torch.float32
                assert torch.equal(padding, torch.zeros_like(padding))


@pytest.mark.parametrize("task_id,experiment,max_iterations", TASKS)
def test_registered_rl_schedule_and_runner_are_preserved_and_isolated(
    task_id, experiment, max_iterations
):
    cfg = load_rl_cfg(task_id)
    assert cfg.experiment_name == experiment
    assert cfg.max_iterations == max_iterations
    assert cfg.num_steps_per_env == 24
    assert cfg.actor.hidden_dims == cfg.critic.hidden_dims == (512, 256, 128)
    assert cfg.actor.obs_normalization and cfg.critic.obs_normalization
    expected = (
        VelocityHeadOnPolicyRunner if task_id.endswith("-Head")
        else OfficialTaskOnPolicyRunner
    )
    assert load_runner_cls(task_id) is expected
    cfg.actor.hidden_dims = (1,)
    cfg.algorithm.learning_rate = 99.0
    cfg.actor.distribution_cfg["init_std"] = 99.0
    for other_id, _, _ in TASKS:
        fresh = load_rl_cfg(other_id)
        assert fresh.actor.hidden_dims == (512, 256, 128)
        assert fresh.algorithm.learning_rate == 1.0e-3
        assert fresh.actor.distribution_cfg["init_std"] == 1.0


def test_velstand_curriculum_rejects_a_mismatched_rollout_length():
    cfg = load_rl_cfg("HtDuck-Flat-VelStand")
    assert_curriculum_units(cfg)
    cfg.num_steps_per_env = 1
    with pytest.raises(ValueError, match="every curriculum stage would fire"):
        assert_curriculum_units(cfg)


def test_both_robot_families_are_registered_with_distinct_action_modes():
    from mjlab.envs.mdp.actions import JointVelocityActionCfg
    from mjlab.tasks.registry import list_tasks

    from ht_microduck.tasks import CYBERDUCK_V2_VELOCITY_TASK_ID

    assert CYBERDUCK_V2_VELOCITY_TASK_ID in list_tasks()
    for task_id, _, _ in TASKS:
        assert tuple(load_env_cfg(task_id).actions) == ("joint_pos",)
    for play in (False, True):
        cfg = load_env_cfg(CYBERDUCK_V2_VELOCITY_TASK_ID, play=play)
        _assert_task_contract(CYBERDUCK_V2_VELOCITY_TASK_ID, cfg)
        assert isinstance(cfg.actions["joint_vel"], JointVelocityActionCfg)
    assert load_runner_cls(CYBERDUCK_V2_VELOCITY_TASK_ID) is None
