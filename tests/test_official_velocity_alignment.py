# Copyright (c) 2026-2027 zh
"""验证官方行走配方、独立配置与头颈误差计算的关键行为。"""

from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
import torch
from mjlab.entity import Entity
from mjlab.tasks.velocity import mdp as velocity_mdp

from ht_microduck.robot.ht_microduck_constants import (
    MJCF_PATH,
    get_ht_microduck_robot_cfg,
)
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_velocity_env_cfg import make_flat_velocity_env_cfg
from ht_microduck.tasks.config.flat_velocity_head_env_cfg import (
    make_flat_velocity_head_env_cfg,
)
from ht_microduck.tasks.mdp import official_rewards

FACTORIES = (make_flat_velocity_env_cfg, make_flat_velocity_head_env_cfg)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.parametrize("play", [False, True])
def test_official_velocity_preserves_command_distribution_and_exploration(
    factory, play
):
    cfg = factory(num_envs=3, seed=7, play=play)
    command = cfg.commands["twist"]
    assert command.resampling_time_range == (3.0, 8.0)
    assert command.rel_turn_in_place_envs == 0.15
    assert command.turn_in_place_min_frac == 0.4
    assert command.rel_standing_envs == 0.02
    assert command.rel_heading_envs == 0.0
    assert command.rel_forward_envs == 0.2
    assert cfg.actions["joint_pos"].scale == 1.0
    assert tuple(cfg.actions["joint_pos"].actuator_names) == C.POLICY_JOINT_NAMES
    assert cfg.commands["head_pose"].ranges == (
        (-0.05, 0.05),
        (-0.05, 0.05),
        (-0.07, 0.07),
        (-0.015, 0.015),
    )
    assert cfg.commands["head_pose"].zero_command_prob == 0.0
    assert (
        cfg.commands["body_pose"].ranges
        == ((-0.005, 0.005),) * 3 + ((-0.05, 0.05),) * 3
    )
    assert cfg.scene.num_envs == 3 and cfg.seed == 7


@pytest.mark.parametrize("factory", FACTORIES)
def test_official_critic_keeps_contact_state_and_observation_delay(factory):
    cfg = factory(num_envs=1)
    actor = cfg.observations["actor"].terms
    critic = cfg.observations["critic"].terms
    assert tuple(actor) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(critic) == (
        "base_lin_vel",
        "base_ang_vel",
        "projected_gravity",
        "joint_pos",
        "joint_vel",
        "actions",
        "command",
        "foot_height",
        "foot_air_time",
        "foot_contact",
        "foot_contact_forces",
        "head_command",
        "body_command",
    )
    widths = {
        **C.ACTOR_OBSERVATION_DIMS,
        "base_lin_vel": 3,
        "foot_height": 2,
        "foot_air_time": 2,
        "foot_contact": 2,
        "foot_contact_forces": 6,
    }
    assert sum(widths[name] for name in actor) == 61
    assert sum(widths[name] for name in critic) == 76
    for name in ("base_ang_vel", "projected_gravity"):
        assert (actor[name].delay_min_lag, actor[name].delay_max_lag) == (0, 1)
        assert actor[name].delay_update_period == 64
    assert (actor["joint_vel"].delay_min_lag, actor["joint_vel"].delay_max_lag) == (
        1,
        1,
    )
    assert critic["joint_pos"].params["biased"] is False
    assert actor["joint_pos"].params["biased"] is True


@pytest.mark.parametrize("factory", FACTORIES)
def test_official_velocity_reward_and_curriculum_stacks_are_complete(factory):
    cfg = factory(num_envs=1)
    assert set(cfg.rewards) == {
        "track_linear_velocity",
        "track_angular_velocity",
        "upright",
        "pose",
        "body_ang_vel",
        "angular_momentum",
        "dof_pos_limits",
        "action_rate_l2",
        "air_time",
        "foot_clearance",
        "foot_swing_height",
        "foot_slip",
        "self_collisions",
        "head_pose_tracking",
        "body_pose_tracking",
        "head_pose_bias",
    }
    assert (
        cfg.rewards["track_angular_velocity"].func
        is velocity_mdp.track_angular_velocity
    )
    assert cfg.rewards["pose"].func is velocity_mdp.variable_posture
    assert cfg.rewards["pose"].weight == 1.0
    assert cfg.rewards["body_pose_tracking"].weight == 0.0
    assert set(cfg.curriculum) == {
        "action_rate_weight",
        "standing_envs",
        "head_pose_range",
        "body_pose_range",
        "com_range",
        "head_com_range",
        "head_pose_bias_weight",
    }
    assert cfg.curriculum["action_rate_weight"].params["weight_stages"] == [
        {"step": 0, "weight": -0.1},
        {"step": 500 * 24, "weight": -0.2},
        {"step": 750 * 24, "weight": -0.4},
        {"step": 1000 * 24, "weight": -0.6},
        {"step": 1250 * 24, "weight": -0.8},
        {"step": 1500 * 24, "weight": -1.0},
    ]
    assert cfg.curriculum["standing_envs"].params["standing_stages"][-1] == {
        "step": 2000 * 24,
        "rel_standing_envs": 0.25,
    }
    assert cfg.curriculum["head_pose_bias_weight"].params["weight_stages"][-1] == {
        "step": 1500 * 24,
        "weight": 3.0,
    }
    assert set(cfg.terminations) == {
        "time_out",
        "fell_over",
        "out_of_terrain_bounds",
        "nan_state",
    }
    assert "illegal_contact" not in cfg.terminations


def test_velocity_aliases_have_independent_nested_configuration():
    first = make_flat_velocity_env_cfg(num_envs=1)
    second = make_flat_velocity_head_env_cfg(num_envs=1)
    first.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    first.rewards["head_pose_tracking"].weight = 99
    first.curriculum["action_rate_weight"].params["weight_stages"][0]["weight"] = 99
    assert second.commands["head_pose"].ranges[0] == (-0.05, 0.05)
    assert second.rewards["head_pose_tracking"].weight == 2.0
    assert (
        second.curriculum["action_rate_weight"].params["weight_stages"][0]["weight"]
        == -0.1
    )


def _head_environment(errors):
    errors = torch.tensor(errors, dtype=torch.float32)
    n = len(errors)
    positions = torch.zeros(n, 14)
    positions[:, 10:] = errors
    names = list(C.POLICY_JOINT_NAMES)
    asset = SimpleNamespace(
        data=SimpleNamespace(
            joint_pos=positions, default_joint_pos=torch.zeros_like(positions)
        ),
        joint_names=names,
        find_joints_by_actuator_names=lambda patterns: (
            list(range(10, 14)),
            names[10:],
        ),
    )
    return SimpleNamespace(
        device="cpu",
        scene={"robot": asset},
        command_manager=SimpleNamespace(get_command=lambda name: torch.zeros(n, 4)),
        episode_length_buf=torch.full((n,), 2),
        step_dt=0.02,
    )


def test_official_head_tracking_pays_partial_tracking_per_joint():
    env = _head_environment([[0.5, 0, 0, 0], [0.5, 0.5, 0.5, 0.5]])
    value = official_rewards.head_pose_tracking(env, std=0.5)
    assert value.tolist() == pytest.approx(
        [
            (3 + torch.exp(torch.tensor(-1)).item()) / 4,
            torch.exp(torch.tensor(-1)).item(),
        ]
    )


def test_official_head_bias_uses_signed_ema_and_resets_only_fresh_environments():
    env = _head_environment([[0.1] * 4, [0.2] * 4])
    for _ in range(50):
        value = official_rewards.head_pose_bias_penalty(env, tau_s=1.0)
    assert value.tolist() == pytest.approx(
        [-0.1 * (1 - 0.98**50), -0.2 * (1 - 0.98**50)]
    )
    previous = value[1].item()
    env.episode_length_buf[0] = 0
    reset_value = official_rewards.head_pose_bias_penalty(env, tau_s=1.0)
    assert reset_value[0].item() == pytest.approx(-0.002)
    assert reset_value[1].item() < previous


def test_official_head_joint_cache_matches_ht_command_order():
    asset = Entity(get_ht_microduck_robot_cfg())
    ids, names = asset.find_joints_by_actuator_names(
        official_rewards._NECK_JOINT_PATTERNS
    )
    assert tuple(names) == C.HEAD_JOINT_NAMES
    assert [asset.joint_names[index] for index in ids] == list(C.HEAD_JOINT_NAMES)


@pytest.mark.parametrize("task", ("Velocity", "Velocity-Head", "StandUp", "SitStand"))
def test_head_com_targets_match_the_source_bodies_joint_roles(task):
    """上游 bearing_roll 直属关节是髋yaw，不能按名称误选髋roll。"""
    from mjlab.tasks.registry import load_env_cfg

    cfg = load_env_cfg("HtDuck-Flat-" + task)
    selector = cfg.events["randomize_head_com"].params["asset_cfg"]
    asset = Entity(cfg.scene.entities["robot"])
    _, names = asset.find_bodies(selector.body_names, preserve_order=True)
    bodies = {body.attrib["name"]: body for body in ElementTree.parse(MJCF_PATH).iter("body")}
    joints = {bodies[name].find("joint").attrib["name"] for name in names}
    assert joints == set(C.HEAD_JOINT_NAMES) | {"r_hip_yaw_joint"}
    assert "r_hip_roll_joint" not in joints
    yaw = bodies[names[-1]].find("joint")
    assert tuple(map(float, yaw.attrib["axis"].split())) == (0.0, 0.0, 1.0)
