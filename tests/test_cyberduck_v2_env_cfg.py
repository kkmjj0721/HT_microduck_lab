# Copyright (c) 2026-2027 zh
"""
内容：
    验证 CyberDuck V2 独立任务的机器人归属、混合动作、观测契约和配置隔离。
"""

from copy import deepcopy

import pytest
from mjlab.envs.mdp.actions import JointVelocityActionCfg
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg

from ht_microduck.robot import cyberduck_v2_constants as robot
from ht_microduck.tasks import _assert_task_contract
from ht_microduck.tasks import cyberduck_v2_contract as C
from ht_microduck.tasks.config.cyberduck_v2.flat_velocity_env_cfg import (
    make_flat_velocity_env_cfg,
)
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg

TASK = "CyberDuckV2-Flat-Velocity"
POSITION_NAMES = (
    "r_hip_yaw_joint", "r_hip_roll_joint", "r_hip_pitch_joint", "r_calf_joint",
    "l_hip_yaw_joint", "l_hip_roll_joint", "l_hip_pitch_joint", "l_calf_joint",
    "neck_pitch_joint", "head_pitch_joint", "head_yaw_joint", "head_roll_joint",
)
VELOCITY_NAMES = ("r_ankle_joint", "l_ankle_joint")


def test_contract_separates_position_and_continuous_velocity_coordinates():
    C.validate_contract()
    assert C.POLICY_POSITION_JOINT_NAMES == POSITION_NAMES
    assert C.POLICY_VELOCITY_JOINT_NAMES == VELOCITY_NAMES
    assert C.POLICY_JOINT_NAMES == POSITION_NAMES + VELOCITY_NAMES
    assert C.HELD_JOINT_NAMES == ("mouth_joint",)
    assert (C.ACTOR_OBSERVATION_DIM, C.CRITIC_OBSERVATION_DIM, C.ACTION_DIM) == (49, 56, 14)
    assert set(C.POLICY_JOINT_NAMES).isdisjoint(robot.MIMIC_JOINT_NAMES)
    assert set(C.POLICY_JOINT_NAMES + C.HELD_JOINT_NAMES) == set(robot.INDEPENDENT_JOINT_NAMES)


@pytest.mark.parametrize("play", [False, True])
def test_registered_configuration_uses_cyberduck_and_mixed_control_units(play):
    cfg = load_env_cfg(TASK, play=play)
    _assert_task_contract(TASK, cfg)
    assert cfg.scene.entities["robot"].spec_fn is robot.get_robot_spec
    assert cfg.scene.entities["robot"].init_state == robot.HOME_FRAME
    assert tuple(cfg.actions) == ("joint_pos", "joint_vel")
    position, velocity = cfg.actions.values()
    assert isinstance(position, BoundedJointPositionActionCfg)
    assert position.bound_targets and position.use_default_offset
    assert tuple(position.actuator_names) == POSITION_NAMES
    assert position.scale == 0.25
    assert isinstance(velocity, JointVelocityActionCfg)
    assert tuple(velocity.actuator_names) == VELOCITY_NAMES
    assert velocity.scale == 4.0
    assert all(limits == (-8.0, 8.0) for limits in velocity.clip.values())
    assert cfg.sim.mujoco.timestep == 0.002 and cfg.decimation == 10
    assert cfg.episode_length_s == 20.0
    assert tuple(cfg.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(cfg.observations["critic"].terms) == C.CRITIC_OBSERVATION_TERMS
    for group in cfg.observations.values():
        assert tuple(group.terms["joint_pos"].params["asset_cfg"].joint_names) == POSITION_NAMES
        assert tuple(group.terms["joint_vel"].params["asset_cfg"].joint_names) == C.POLICY_JOINT_NAMES
    command = cfg.commands["twist"]
    assert command.ranges.lin_vel_x == (-0.1, 0.1)
    assert command.ranges.lin_vel_y == (0.0, 0.0)
    assert command.ranges.ang_vel_z == (-0.3, 0.3)
    assert not cfg.curriculum
    assert all(event.mode != "interval" for event in cfg.events.values())


def test_mutating_one_robot_configuration_cannot_change_another_robot_or_registry():
    original_ht = load_env_cfg("HtDuck-Flat-Velocity")
    original_new = load_env_cfg(TASK)
    modified = make_flat_velocity_env_cfg(num_envs=3, seed=3532)
    modified.scene.entities["robot"].init_state.joint_pos["neck_pitch_joint"] = 1.0
    modified.scene.entities["robot"].articulation.actuators[0].stiffness = 1.0
    modified.actions["joint_vel"].scale = 99.0
    modified.commands["twist"].ranges.lin_vel_x = (-9.0, 9.0)
    fresh = load_env_cfg(TASK)
    assert fresh.scene.entities["robot"].init_state == original_new.scene.entities["robot"].init_state
    assert fresh.actions["joint_vel"].scale == 4.0
    assert fresh.commands["twist"].ranges.lin_vel_x == (-0.1, 0.1)
    assert load_env_cfg("HtDuck-Flat-Velocity").scene.entities["robot"].init_state == original_ht.scene.entities["robot"].init_state
    assert robot.HOME_JOINT_POS["neck_pitch_joint"] == -0.360


def test_cyberduck_rl_configuration_has_independent_models_and_log_namespace():
    old = load_rl_cfg("HtDuck-Flat-Velocity")
    cfg = load_rl_cfg(TASK)
    assert cfg.experiment_name == "cyberduck_v2_flat_velocity"
    assert cfg.actor.obs_normalization and cfg.critic.obs_normalization
    assert cfg.num_steps_per_env == 24
    cfg.actor.hidden_dims = (1,)
    cfg.algorithm.learning_rate = 99.0
    assert load_rl_cfg(TASK).actor.hidden_dims != (1,)
    assert load_rl_cfg(TASK).algorithm.learning_rate != 99.0
    assert load_rl_cfg("HtDuck-Flat-Velocity") == old


@pytest.mark.parametrize("part", ["velocity_mode", "position_order", "observation_order", "control_period"])
def test_registry_guard_rejects_incompatible_new_task_configurations(part):
    cfg = deepcopy(load_env_cfg(TASK))
    if part == "velocity_mode":
        cfg.actions["joint_vel"] = deepcopy(cfg.actions["joint_pos"])
    elif part == "position_order":
        cfg.actions["joint_pos"].actuator_names = POSITION_NAMES[::-1]
    elif part == "observation_order":
        cfg.observations["actor"].terms = dict(reversed(tuple(cfg.observations["actor"].terms.items())))
    else:
        cfg.decimation = 1
    with pytest.raises(ValueError, match="CyberDuckV2"):
        _assert_task_contract(TASK, cfg)
