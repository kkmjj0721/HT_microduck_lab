# Copyright (c) 2026-2027 zh
"""检查官方姿态任务的初态覆盖、缓变目标、躯干轴与奖励公式。"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
import torch

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_env_cfg import make_sitstand_env_cfg
from ht_microduck.tasks.config.flat_standup_env_cfg import make_standup_env_cfg
from ht_microduck.tasks.config.official_robot import SIT_Z, STAND_Z
from ht_microduck.tasks.mdp.official_posture_events import (
    SitStandCommand,
    set_random_ground_state,
)
from ht_microduck.tasks.mdp.official_posture_rewards import (
    body_pose_tracking_locomotion,
    posture_composite,
    posture_height_gaussian,
    posture_pose_match,
    posture_rise_bootstrap,
    trunk_downward_velocity_penalty,
    trunk_upward_velocity_penalty,
)


class _Scene(dict):
    def __init__(self, robot, count):
        super().__init__(robot=robot)
        self.env_origins = torch.zeros(count, 3)
        self.terrain = SimpleNamespace(env_origins=self.env_origins)


def _environment(count=4):
    names = list(C.POLICY_JOINT_NAMES) + ["mouth_joint"]
    data = SimpleNamespace(
        root_link_pos_w=torch.zeros(count, 3),
        root_link_quat_w=torch.tensor([[1.0, 0.0, 0.0, 0.0]]).repeat(count, 1),
        root_link_lin_vel_w=torch.zeros(count, 3),
        joint_pos=torch.zeros(count, 15),
        default_joint_pos=torch.zeros(count, 15),
        site_pos_w=torch.zeros(count, 2, 3),
        site_quat_w=torch.tensor([[[1.0, 0.0, 0.0, 0.0]]]).repeat(count, 2, 1),
    )
    data.root_link_pos_w[:, 2] = STAND_Z

    def find_joints(keys, preserve_order=False):
        assert preserve_order
        return [names.index(name) for name in keys], list(keys)

    robot = SimpleNamespace(data=data, find_joints=find_joints)
    body = torch.zeros(count, 6)
    twist = torch.zeros(count, 3)
    head = torch.zeros(count, 4)
    posture = SimpleNamespace(alpha=torch.zeros(count))
    commands = {"body_pose": body, "twist": twist, "head_pose": head}
    env = SimpleNamespace(
        num_envs=count,
        device="cpu",
        scene=_Scene(robot, count),
        command_manager=SimpleNamespace(
            get_command=commands.__getitem__, get_term=lambda _: posture
        ),
        episode_length_buf=torch.full((count,), 5),
        step_dt=0.02,
        sim=SimpleNamespace(
            data=SimpleNamespace(
                qpos=torch.zeros(count, 22), qvel=torch.zeros(count, 21)
            )
        ),
    )
    return env, robot, commands, posture


def test_standup_restores_all_ground_buckets_and_official_curriculum():
    cfg = make_standup_env_cfg(num_envs=1, seed=0)
    reset = cfg.events["set_ground_state"]
    assert reset.func is set_random_ground_state
    assert tuple(
        reset.params[key]
        for key in ("standing_prob", "sitting_prob", "face_down_prob", "face_up_prob")
    ) == (0.4, 0.4, 0.2, 0.0)
    stages = cfg.curriculum["ground_state_mix"].params["param_stages"]
    assert [stage["step"] for stage in stages] == [0, 600 * 24, 1500 * 24, 2500 * 24]
    assert stages[-1]["params"] == {
        "standing_prob": 0.15,
        "sitting_prob": 0.2,
        "face_down_prob": 0.3,
        "face_up_prob": 0.35,
    }
    assert "fell_over" not in cfg.terminations
    assert cfg.episode_length_s == 6.0
    assert cfg.rewards["body_pose_tracking"].params["axis_weights"] == (
        0.0,
        0.0,
        1.0,
        1.0,
        1.0,
        0.0,
    )
    assert "foot_height" not in cfg.observations["critic"].terms
    assert {"foot_air_time", "foot_contact", "foot_contact_forces"} <= set(
        cfg.observations["critic"].terms
    )


def test_sitstand_restores_official_slew_gentleness_and_hardening():
    cfg = make_sitstand_env_cfg(num_envs=1, seed=0)
    command = cfg.commands["twist"]
    assert command.ramp_s == 2.0
    assert command.sit_prob == 0.5
    assert command.resampling_time_range == (3.5, 6.5)
    assert cfg.episode_length_s == 12.0
    assert cfg.rewards["descent_speed"].weight == 10.0
    assert cfg.rewards["descent_speed"].params["max_down_vel"] == 0.05
    assert cfg.rewards["rise_speed"].weight == 0.0
    assert cfg.rewards["rise_speed"].params["max_up_vel"] == 0.08
    assert {"seated_head_jerk", "seated_tip"} <= set(cfg.events)
    assert {"rise_speed_weight", "seated_tip_range", "torque_rate_weight"} <= set(
        cfg.curriculum
    )
    assert "fell_over" not in cfg.terminations


def test_sitstand_height_gates_keep_the_official_relative_positions():
    cfg = make_sitstand_env_cfg(num_envs=1, seed=0)
    params = cfg.rewards["upright_while_tall"].params
    for name, reference in (("height_low", 0.075), ("height_high", 0.100)):
        assert (params[name] - SIT_Z) / (STAND_Z - SIT_Z) == pytest.approx(
            (reference - 0.060) / (0.115 - 0.060)
        )
    ceiling = cfg.rewards["rise_bootstrap"].params["max_height"]
    assert ceiling == pytest.approx(STAND_Z + 0.01)
    assert SIT_Z < params["height_low"] < params["height_high"] < STAND_Z < ceiling


def test_sitstand_rise_bootstrap_covers_standing_and_stops_at_the_ceiling():
    env, robot, commands, _ = _environment()
    params = make_sitstand_env_cfg(num_envs=1).rewards["rise_bootstrap"].params
    ceiling = params["max_height"]
    robot.data.root_link_pos_w[:, 2] = torch.tensor(
        [0.130, STAND_Z, ceiling - 1e-5, ceiling + 1e-5]
    )
    robot.data.root_link_lin_vel_w[:, 2] = 0.04
    result = posture_rise_bootstrap(env, **params)
    assert torch.allclose(result, torch.tensor([0.04, 0.04, 0.04, 0.0]))
    commands["twist"][:, 0] = 1.0
    assert torch.equal(posture_rise_bootstrap(env, **params), torch.zeros(4))


def test_body_tracking_uses_z_roll_pitch_and_ignores_x_slot():
    env, robot, commands, _ = _environment()
    tracked = (0.0, 0.0, 1.0, 1.0, 1.0, 0.0)
    feet = SimpleNamespace(site_ids=[0, 1])
    baseline = body_pose_tracking_locomotion(
        env, nominal_height=STAND_Z, axis_weights=tracked, feet_cfg=feet
    )
    assert torch.equal(baseline, torch.ones(4))
    commands["body_pose"][:, 0] = 10.0
    assert torch.equal(
        body_pose_tracking_locomotion(
            env, nominal_height=STAND_Z, axis_weights=tracked, feet_cfg=feet
        ),
        baseline,
    )
    commands["body_pose"][:, 2] = 0.02
    commands["body_pose"][:, 3] = 0.12
    commands["body_pose"][:, 4] = -0.08
    mismatch = body_pose_tracking_locomotion(
        env, nominal_height=STAND_Z, axis_weights=tracked, feet_cfg=feet
    )
    assert torch.all(mismatch < baseline)
    roll = commands["body_pose"][:, 3]
    pitch = commands["body_pose"][:, 4]
    robot.data.root_link_pos_w[:, 2] += 0.02
    cr, sr = torch.cos(roll / 2), torch.sin(roll / 2)
    cp, sp = torch.cos(pitch / 2), torch.sin(pitch / 2)
    robot.data.root_link_quat_w[:] = torch.stack(
        (cr * cp, sr * cp, cr * sp, -sr * sp), -1
    )
    matched = body_pose_tracking_locomotion(
        env, nominal_height=STAND_Z, axis_weights=tracked, feet_cfg=feet
    )
    torch.testing.assert_close(matched, baseline)


def test_sitstand_reset_and_command_remain_independent():
    env, _, _, _ = _environment(count=4096)
    ids = torch.arange(env.num_envs)
    command = object.__new__(SitStandCommand)
    command._env = env
    command._sit_prob = 0.5
    command.vel_command_b = torch.zeros(env.num_envs, 3)
    torch.manual_seed(0)
    set_random_ground_state(
        env,
        ids,
        face_down_prob=0.0,
        face_up_prob=0.0,
        sitting_prob=0.5,
        standing_prob=0.5,
        sitting_z_min=SIT_Z,
        sitting_z_max=SIT_Z,
        standing_z_min=STAND_Z,
        standing_z_max=STAND_Z,
    )
    command._resample_command(ids)
    seated = env.sim.data.qpos[:, 2] == SIT_Z
    commanded = command.vel_command_b[:, 0] > 0.5
    for state in (False, True):
        for goal in (False, True):
            fraction = ((seated == state) & (commanded == goal)).float().mean().item()
            assert 0.2 < fraction < 0.3


@pytest.mark.parametrize("face_down", [False, True])
def test_prone_reset_uses_pitch_axis_and_preserves_unselected_worlds(face_down):
    env, _, _, _ = _environment()
    env.sim.data.qpos[1:] = 0.123
    env.sim.data.qvel[1:] = 0.456
    before_q = env.sim.data.qpos.clone()
    before_v = env.sim.data.qvel.clone()
    set_random_ground_state(
        env,
        torch.tensor([0]),
        face_down_prob=float(face_down),
        face_up_prob=float(not face_down),
        sitting_prob=0.0,
        standing_prob=0.0,
        prone_z_min=0.08,
        prone_z_max=0.08,
    )
    q = env.sim.data.qpos[0, 3:7]
    gravity_x = 2 * (q[0] * q[2] - q[1] * q[3])
    gravity_y = -2 * (q[0] * q[1] + q[2] * q[3])
    assert abs(gravity_x.item()) == pytest.approx(1.0, abs=1e-6)
    assert abs(gravity_y.item()) < 1e-6
    assert gravity_x.item() == pytest.approx(1.0 if face_down else -1.0, abs=1e-6)
    assert torch.equal(env.sim.data.qpos[1:], before_q[1:])
    assert torch.equal(env.sim.data.qvel[1:], before_v[1:])


def test_posture_reward_distinguishes_per_joint_gaussian_and_rms_composite():
    env, robot, _, posture = _environment()
    posture.alpha[:] = 0.5
    robot.data.root_link_pos_w[:, 2] = (SIT_Z + STAND_Z) / 2
    robot.data.joint_pos[:, 0] = 0.2
    overrides = {0: 0.2}
    indices = [0, 1]
    pose = posture_pose_match(
        env,
        command_name="twist",
        sit_overrides=overrides,
        std=0.2,
        joint_indices=indices,
    )
    expected = (math.exp(-((0.1 / 0.2) ** 2)) + 1.0) / 2
    torch.testing.assert_close(pose, torch.full((4,), expected))
    height = posture_height_gaussian(
        env, command_name="twist", sit_z=SIT_Z, stand_z=STAND_Z, std=0.02
    )
    composite = posture_composite(
        env,
        command_name="twist",
        sit_overrides=overrides,
        sit_z=SIT_Z,
        stand_z=STAND_Z,
        joint_indices=indices,
        height_std=0.02,
        upright_std=0.4,
        pose_std=0.2,
    )
    rms_score = math.exp(-((0.1**2 + 0.0) / 2) / 0.2**2)
    torch.testing.assert_close(composite, height * rms_score)
    assert torch.all(composite < height * pose)
    robot.data.root_link_pos_w[:, 2] += 0.2
    assert torch.all(
        posture_composite(
            env,
            command_name="twist",
            sit_overrides=overrides,
            sit_z=SIT_Z,
            stand_z=STAND_Z,
            joint_indices=indices,
            height_std=0.02,
            upright_std=0.4,
            pose_std=0.2,
        )
        < 1e-10
    )


def test_vertical_speed_caps_retain_official_linear_penalty():
    env, robot, _, _ = _environment()
    robot.data.root_link_lin_vel_w[:, 2] = torch.tensor([-0.10, -0.05, 0.08, 0.18])
    torch.testing.assert_close(
        trunk_downward_velocity_penalty(env, max_down_vel=0.05),
        torch.tensor([-0.05, 0.0, 0.0, 0.0]),
    )
    torch.testing.assert_close(
        trunk_upward_velocity_penalty(env, max_up_vel=0.08),
        torch.tensor([0.0, 0.0, 0.0, -0.10]),
    )


@pytest.mark.parametrize("factory", [make_standup_env_cfg, make_sitstand_env_cfg])
def test_posture_factories_return_independent_robot_and_reset_configs(factory):
    first = factory(num_envs=1, seed=0)
    second = factory(num_envs=1, seed=0, play=True)
    assert first.scene.entities["robot"] is not second.scene.entities["robot"]
    first_robot = first.scene.entities["robot"]
    second_robot = second.scene.entities["robot"]
    key = next(iter(first_robot.init_state.joint_pos))
    expected = second_robot.init_state.joint_pos[key]
    first_robot.init_state.joint_pos[key] = 123.0
    assert second_robot.init_state.joint_pos[key] == expected
    overrides = first.events["set_ground_state"].params["sitting_joint_overrides"]
    other = second.events["set_ground_state"].params["sitting_joint_overrides"]
    key = next(iter(overrides))
    expected = other[key]
    overrides[key] = 123.0
    assert other[key] == expected


def test_sitstand_slew_accepts_native_tensor_dt_and_scopes_partial_reset(monkeypatch):
    from mjlab.tasks.velocity.mdp.velocity_command import UniformVelocityCommand

    monkeypatch.setattr(
        UniformVelocityCommand, "compute", lambda self, dt, env_ids=None: None
    )
    env, robot, _, _ = _environment()
    command = object.__new__(SitStandCommand)
    command._env = env
    command._env_ref = env
    command.robot = robot
    command._sit_z = SIT_Z
    command._stand_z = STAND_Z
    command._ramp_s = 2.0
    command._alpha = torch.tensor([0.0, 0.5, 0.7, 1.0])
    command.vel_command_b = torch.zeros(4, 3)
    command.vel_command_b[:, 0] = 1.0
    before = command.alpha.clone()
    env.episode_length_buf[:] = 0
    command.compute(0.0, env_ids=torch.tensor([0]))
    assert torch.equal(command.alpha[1:], before[1:])
    env.episode_length_buf[:] = 5
    command.compute(torch.tensor([0.02, 0.0, 0.04, 0.02]))
    torch.testing.assert_close(command.alpha, torch.tensor([0.01, 0.5, 0.72, 1.0]))


def test_torque_rate_and_reset_follow_policy_actuators_and_ignore_mouth():
    from ht_microduck.tasks.mdp.official_events import reset_action_history
    from ht_microduck.tasks.mdp.official_posture_rewards import joint_torque_rate_l2

    env, robot, _, _ = _environment()
    actuator_names = list(reversed(C.POLICY_JOINT_NAMES))
    actuator_names.insert(3, "mouth_joint")
    robot.data.actuator_force = torch.zeros(4, 15)

    def find_actuators(names, preserve_order=False):
        assert preserve_order
        return [actuator_names.index(name) for name in names], list(names)

    robot.find_actuators = find_actuators
    policy_first = actuator_names.index(C.POLICY_JOINT_NAMES[0])
    mouth = actuator_names.index("mouth_joint")
    assert torch.equal(joint_torque_rate_l2(env), torch.zeros(4))
    robot.data.actuator_force[:, mouth] = 123.0
    assert torch.equal(joint_torque_rate_l2(env), torch.zeros(4))
    robot.data.actuator_force[:, policy_first] = torch.arange(1.0, 5.0)
    torch.testing.assert_close(
        joint_torque_rate_l2(env), torch.tensor([1.0, 4.0, 9.0, 16.0])
    )
    assert env._prev_actuator_forces.shape == (4, C.ACTION_DIM)
    torch.testing.assert_close(env._prev_actuator_forces[:, 0], torch.arange(1.0, 5.0))
    before = env._prev_actuator_forces.clone()
    robot.data.actuator_force[0, policy_first] = 7.0
    robot.data.actuator_force[:, mouth] = 555.0
    reset_action_history(env, torch.tensor([0]))
    assert env._prev_actuator_forces[0, 0].item() == 7.0
    assert torch.equal(env._prev_actuator_forces[1:], before[1:])
    assert torch.equal(joint_torque_rate_l2(env), torch.zeros(4))


def test_ground_height_offsets_preserve_draws_bandwidth_and_other_buckets():
    baseline, _, _, _ = _environment(count=4096)
    shifted, _, _, _ = _environment(count=4096)
    ids = torch.arange(4096)
    params = dict(
        face_down_prob=0.25,
        face_up_prob=0.25,
        sitting_prob=0.25,
        standing_prob=0.25,
        prone_z_min=0.05,
        prone_z_max=0.09,
        sitting_z_min=SIT_Z,
        sitting_z_max=SIT_Z,
        standing_z_min=STAND_Z,
        standing_z_max=STAND_Z,
    )
    torch.manual_seed(983)
    set_random_ground_state(baseline, ids, **params)
    baseline_rng = torch.get_rng_state()
    torch.manual_seed(983)
    set_random_ground_state(
        shifted,
        ids,
        face_down_z_offset=0.06938914768149877,
        face_up_z_offset=0.051,
        **params,
    )
    assert torch.equal(torch.get_rng_state(), baseline_rng)
    torch.testing.assert_close(
        shifted.sim.data.qpos[:, 3:], baseline.sim.data.qpos[:, 3:], rtol=0, atol=0
    )
    quat = baseline.sim.data.qpos[:, 3:7]
    pitch_indicator = 2 * (quat[:, 0] * quat[:, 2] - quat[:, 1] * quat[:, 3])
    face_down = pitch_indicator > 0.5
    face_up = pitch_indicator < -0.5
    upright = ~(face_down | face_up)
    delta = shifted.sim.data.qpos[:, 2] - baseline.sim.data.qpos[:, 2]
    torch.testing.assert_close(
        delta[face_down], torch.full_like(delta[face_down], 0.06938914768149877)
    )
    torch.testing.assert_close(delta[face_up], torch.full_like(delta[face_up], 0.051))
    assert torch.equal(delta[upright], torch.zeros_like(delta[upright]))
    for mask in (face_down, face_up):
        assert (
            baseline.sim.data.qpos[mask, 2].max()
            - baseline.sim.data.qpos[mask, 2].min()
            > 0.039
        )
        torch.testing.assert_close(
            shifted.sim.data.qpos[mask, 2].std(), baseline.sim.data.qpos[mask, 2].std()
        )
