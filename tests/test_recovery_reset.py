# Copyright (c) 2026-2027 zh
"""验证恢复初态的绝对分布、姿态轴、局部状态和倒地奖励边界。"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch
from mjlab.utils.lab_api.math import quat_apply_inverse

from ht_microduck.robot.ht_microduck_constants import HOME_FRAME
from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.official_robot import (
    FACE_DOWN_SUPPORT_Z,
    FACE_UP_SUPPORT_Z,
)
from ht_microduck.tasks.mdp import posture
from ht_microduck.tasks.mdp.events import reset_to_ground_state
from ht_microduck.tasks.mdp.rewards import upright


class _Scene(dict):
    def __init__(self, robot, count):
        super().__init__(robot=robot)
        self.env_origins = torch.zeros(count, 3)
        self.env_origins[:, 2] = torch.arange(count) % 7 * 0.25


class _Robot:
    def __init__(self, count):
        self.joint_names = [*C.POLICY_JOINT_NAMES, "mouth_joint"]
        default = torch.tensor(
            [HOME_FRAME.joint_pos[name] for name in self.joint_names]
        ).repeat(count, 1)
        pose = torch.zeros(count, 7)
        pose[:, 3] = 1.0
        self.data = SimpleNamespace(
            default_joint_pos=default,
            joint_pos=default.clone(),
            soft_joint_pos_limits=torch.tensor([-2.0, 2.0]).repeat(count, 15, 1),
            root_link_pose_w=pose,
            root_link_pos_w=pose[:, :3],
            root_link_quat_w=pose[:, 3:],
            projected_gravity_b=torch.tensor([0.0, 0.0, -1.0]).repeat(count, 1),
            root_link_vel_w=torch.zeros(count, 6),
        )

    def write_joint_position_to_sim(self, values, *, env_ids):
        self.data.joint_pos[env_ids] = values

    def write_root_link_pose_to_sim(self, values, *, env_ids):
        self.data.root_link_pose_w[env_ids] = values
        self.data.projected_gravity_b[env_ids] = quat_apply_inverse(
            values[:, 3:], torch.tensor([0.0, 0.0, -1.0]).repeat(len(env_ids), 1)
        )

    def write_root_link_velocity_to_sim(self, values, *, env_ids):
        self.data.root_link_vel_w[env_ids] = values


def _environment(count=4):
    robot = _Robot(count)
    body_command = torch.zeros(count, 6)
    env = SimpleNamespace(
        num_envs=count,
        device="cpu",
        step_dt=0.02,
        scene=_Scene(robot, count),
        command_manager=SimpleNamespace(get_command=lambda _: body_command),
    )
    robot.data.root_link_pos_w[:, 2] = env.scene.env_origins[:, 2] + C.STAND_Z
    return env, robot, body_command


def _reset(env, **overrides):
    params = {
        "prone_prob": 0.45,
        "crouch_prob": 0.20,
        "side_prob": 0.5,
        "face_down_prob": 0.5,
        "position_noise": 0.0,
    }
    params.update(overrides)
    reset_to_ground_state(env, None, **params)


def _height(env, robot):
    return robot.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]


def test_absolute_ground_probabilities_preserve_standing_remainder():
    torch.manual_seed(0)
    env, robot, _ = _environment(20_000)
    _reset(env, face_down_prob=0.8)
    gravity = robot.data.projected_gravity_b
    height = _height(env, robot)
    face_down = gravity[:, 0] > 0.99
    face_up = gravity[:, 0] < -0.99
    side = gravity[:, 1].abs() > 0.99
    seated = torch.isclose(height, torch.tensor(C.SIT_Z), atol=1e-6)
    standing = (gravity[:, 2] < -0.99) & torch.isclose(
        height, torch.tensor(C.STAND_Z), atol=1e-6
    )
    groups = (face_down, face_up, side, seated, standing)
    assert torch.stack(groups).sum(dim=0).eq(1).all()
    expected = (0.45 * 0.5 * 0.8, 0.45 * 0.5 * 0.2, 0.45 * 0.5, 0.20, 0.35)
    for mask, probability in zip(groups, expected, strict=True):
        assert abs(mask.float().mean().item() - probability) < 0.015
    assert torch.allclose(
        robot.data.root_link_quat_w.square().sum(dim=1), torch.ones(env.num_envs)
    )
    assert torch.count_nonzero(robot.data.root_link_vel_w) == 0


@pytest.mark.parametrize("face_down_prob, sign", [(1.0, 1.0), (0.0, -1.0)])
def test_front_and_back_use_pitch_and_keep_mapped_uniform_height_band(
    face_down_prob, sign
):
    torch.manual_seed(10)
    env, robot, _ = _environment(1024)
    _reset(
        env,
        prone_prob=1.0,
        crouch_prob=0.0,
        side_prob=0.0,
        face_down_prob=face_down_prob,
    )
    gravity = robot.data.projected_gravity_b
    torch.testing.assert_close(
        gravity[:, 0], torch.full((1024,), sign), atol=1e-6, rtol=0
    )
    assert gravity[:, 1:].abs().max() < 1e-6
    support = FACE_DOWN_SUPPORT_Z if sign > 0 else FACE_UP_SUPPORT_Z
    excess = _height(env, robot) - support
    assert excess.min() >= 0.006 - 1e-6
    assert excess.max() <= 0.046 + 1e-6
    assert 0.024 < excess.mean() < 0.028
    assert excess.max() - excess.min() > 0.039
    torch.testing.assert_close(robot.data.joint_pos, robot.data.default_joint_pos)
    assert robot.data.root_link_quat_w[:, 3].abs().max() > 0.5


def test_side_probability_is_inside_prone_and_rolls_both_directions():
    torch.manual_seed(3)
    env, robot, _ = _environment(1024)
    _reset(env, prone_prob=1.0, crouch_prob=0.0, side_prob=1.0)
    gravity = robot.data.projected_gravity_b
    assert gravity[:, [0, 2]].abs().max() < 1e-6
    torch.testing.assert_close(gravity[:, 1].abs(), torch.ones(1024), atol=1e-6, rtol=0)
    assert 0.4 < (gravity[:, 1] > 0).float().mean() < 0.6
    torch.testing.assert_close(_height(env, robot), torch.full((1024,), C.SIDE_Z))


@pytest.mark.parametrize(
    "prone_prob,crouch_prob,height", [(0.0, 0.0, C.STAND_Z), (0.0, 1.0, C.SIT_Z)]
)
def test_zero_prone_and_absolute_low_slice_keep_confirmed_ht_references(
    prone_prob, crouch_prob, height
):
    torch.manual_seed(8)
    env, robot, _ = _environment(512)
    _reset(env, prone_prob=prone_prob, crouch_prob=crouch_prob)
    torch.testing.assert_close(_height(env, robot), torch.full((512,), height))
    torch.testing.assert_close(
        robot.data.projected_gravity_b, torch.tensor([0.0, 0.0, -1.0]).repeat(512, 1)
    )
    if crouch_prob:
        for name, target in C.LOW_POSTURE_JOINT_POS.items():
            values = robot.data.joint_pos[:, robot.joint_names.index(name)]
            assert abs(values.mean().item() - target) < 0.01
            assert values.std() > 0
    else:
        torch.testing.assert_close(robot.data.joint_pos, robot.data.default_joint_pos)


def test_ground_reset_does_not_change_unselected_environments():
    env, robot, _ = _environment()
    before_pose = robot.data.root_link_pose_w.clone()
    before_joints = robot.data.joint_pos.clone()
    reset_to_ground_state(env, torch.tensor([1, 3]), 1.0, 0.0, 0.0, 1.0, 0.0)
    torch.testing.assert_close(robot.data.root_link_pose_w[[0, 2]], before_pose[[0, 2]])
    torch.testing.assert_close(robot.data.joint_pos[[0, 2]], before_joints[[0, 2]])
    assert robot.data.projected_gravity_b[[1, 3], 0].min() > 0.99


def test_potential_reset_keeps_neighbour_progress_and_reseeds_only_reset_rows():
    env, robot, _ = _environment(3)
    reset = posture.RewardStateReset(None, env)
    assert posture.height_progress(env, 1.0).eq(0).all()
    assert posture.upright_progress(env).eq(0).all()
    reset.reset(torch.tensor([0]))
    robot.data.root_link_pos_w[:, 2] += torch.tensor([-0.04, 0.02, 0.03])
    robot.data.projected_gravity_b[:, 2] += torch.tensor([0.5, 0.2, 0.1])
    torch.testing.assert_close(
        posture.height_progress(env, 1.0), torch.tensor([0.0, 0.02, 0.03])
    )
    torch.testing.assert_close(
        posture.upright_progress(env), torch.tensor([0.0, -0.2, -0.1])
    )
    reset.reset(torch.tensor([1]))
    reset.reset(torch.tensor([1]))
    robot.data.root_link_pos_w[:, 2] += 0.01
    torch.testing.assert_close(
        posture.height_progress(env, 1.0), torch.tensor([0.01, 0.0, 0.01])
    )


def test_potential_slice_and_full_reset_keep_history_and_timers_local():
    env, robot, _ = _environment()
    reset = posture.RewardStateReset(None, env)
    posture.height_progress(env, 1.0)
    env._ht_fallen_timer = torch.tensor([0.1, 0.2, 0.3, 0.4])
    env._ht_bounty_armed = torch.ones(4, dtype=torch.bool)
    reset.reset(slice(1, 2))
    robot.data.root_link_pos_w[:, 2] += 0.01
    torch.testing.assert_close(
        posture.height_progress(env, 1.0), torch.tensor([0.01, 0.0, 0.01, 0.01])
    )
    torch.testing.assert_close(env._ht_fallen_timer, torch.tensor([0.1, 0.0, 0.3, 0.4]))
    assert env._ht_bounty_armed.tolist() == [True, False, True, True]
    reset.reset(None)
    robot.data.root_link_pos_w[:, 2] += 0.05
    assert posture.height_progress(env, 1.0).eq(0).all()
    assert env._ht_fallen_timer.eq(0).all()


def test_inference_created_state_can_be_reset_outside_inference_mode():
    env, robot, _ = _environment(2)
    with torch.inference_mode():
        posture.height_progress(env, 1.0)
        posture.upright_progress(env)
        env._ht_fallen_timer = torch.tensor([0.3, 0.4])
        env._ht_bounty_armed = torch.tensor([True, True])
    previous_values, previous_valid = env._ht_posture_prev["height_progress"]
    previous_timer = env._ht_fallen_timer
    previous_armed = env._ht_bounty_armed
    assert previous_valid.is_inference()
    assert previous_timer.is_inference()
    assert previous_armed.is_inference()

    posture.RewardStateReset(None, env).reset(torch.tensor([0]))
    torch.testing.assert_close(env._ht_fallen_timer, torch.tensor([0.0, 0.4]))
    assert env._ht_bounty_armed.tolist() == [False, True]
    assert env._ht_posture_prev["height_progress"][0] is previous_values
    assert env._ht_posture_prev["height_progress"][1].tolist() == [False, True]
    # 重置只替换状态对象，不在模式外改写原有 inference tensor。
    assert previous_valid.tolist() == [True, True]
    torch.testing.assert_close(previous_timer, torch.tensor([0.3, 0.4]))
    assert previous_armed.tolist() == [True, True]

    robot.data.root_link_pos_w[:, 2] += torch.tensor([0.01, 0.02])
    robot.data.projected_gravity_b[:, 2] += torch.tensor([0.2, 0.1])
    with torch.inference_mode():
        torch.testing.assert_close(
            posture.height_progress(env, 1.0), torch.tensor([0.0, 0.02])
        )
        torch.testing.assert_close(
            posture.upright_progress(env), torch.tensor([0.0, -0.1])
        )


def test_fallen_timeout_uses_or_and_inclusive_duration_boundary():
    env, robot, _ = _environment()
    robot.data.root_link_pos_w[:, 2] = env.scene.env_origins[:, 2] + torch.tensor(
        [0.05, 0.15, 0.15, 0.11]
    )
    robot.data.projected_gravity_b[:, 2] = -torch.tensor(
        [
            1.0,
            math.cos(math.radians(50)),
            1.0,
            math.cos(math.radians(40)),
        ]
    )
    params = {"gate_z_below": 0.11, "gate_tilt_above_deg": 40.0, "max_duration_s": 0.04}
    assert not posture.fallen_too_long(env, **params).any()
    assert posture.fallen_too_long(env, **params).tolist() == [True, True, False, False]
    posture.RewardStateReset(None, env).reset(torch.tensor([0]))
    assert posture.fallen_too_long(env, **params).tolist() == [
        False,
        True,
        False,
        False,
    ]
    robot.data.root_link_pos_w[:, 2] = env.scene.env_origins[:, 2] + C.STAND_Z
    robot.data.projected_gravity_b[:, 2] = -1.0
    assert not posture.fallen_too_long(env, **params).any()
    assert env._ht_fallen_timer.eq(0).all()


def test_fallen_timeout_fires_at_exactly_eight_seconds():
    env, robot, _ = _environment(1)
    env.step_dt = 0.25
    robot.data.root_link_pos_w[:, 2] = 0.05
    params = {
        "gate_z_below": C.FALLEN_Z,
        "gate_tilt_above_deg": 40.0,
        "max_duration_s": 8.0,
    }
    for _ in range(31):
        assert not posture.fallen_too_long(env, **params).any()
    assert env._ht_fallen_timer.item() == 7.75
    assert posture.fallen_too_long(env, **params).item()
    assert env._ht_fallen_timer.item() == 8.0


def test_recovery_bounty_arms_at_half_second_but_not_before():
    env, robot, _ = _environment(2)
    env.step_dt = 0.25
    robot.data.projected_gravity_b[:, 2] = -math.cos(math.radians(80.0))
    params = {
        "fallen_tilt_deg": 40.0,
        "up_tilt_deg": 25.0,
        "up_z": C.RECOVERED_Z,
        "min_fallen_s": 0.5,
    }
    assert posture.recovery_success(env, **params).eq(0).all()
    assert env._ht_fallen_timer_bounty.eq(0.25).all()
    assert not env._ht_bounty_armed.any()
    # world1 提前恢复，不足半秒；world0 继续倒地到恰好半秒。
    robot.data.projected_gravity_b[1, 2] = -1.0
    assert posture.recovery_success(env, **params).eq(0).all()
    assert env._ht_fallen_timer_bounty.tolist() == [0.5, 0.0]
    assert env._ht_bounty_armed.tolist() == [True, False]
    robot.data.projected_gravity_b[:, 2] = -1.0
    assert posture.recovery_success(env, **params).tolist() == [1.0, 0.0]
    assert posture.recovery_success(env, **params).eq(0).all()


def test_recovery_angle_and_height_equalities_match_official_strict_gates():
    env, robot, _ = _environment()
    threshold = math.cos(math.radians(40.0))
    robot.data.projected_gravity_b[:, 2] = -torch.tensor(
        [threshold, threshold + 1e-4, threshold - 1e-4, 1.0]
    )
    assert posture.tilted_mask(env, 40.0).tolist() == [False, False, True, False]

    threshold = math.cos(math.radians(25.0))
    robot.data.projected_gravity_b[:, 2] = -torch.tensor(
        [threshold, threshold + 1e-4, threshold - 1e-4, 1.0]
    )
    env.scene.env_origins[:, 2] = 0.0
    robot.data.root_link_pos_w[:, 2] = torch.tensor(
        [C.STAND_Z, C.STAND_Z, C.STAND_Z, C.RECOVERED_Z]
    )
    env._ht_bounty_armed = torch.ones(4, dtype=torch.bool)
    params = {
        "fallen_tilt_deg": 40.0,
        "up_tilt_deg": 25.0,
        "up_z": C.RECOVERED_Z,
        "min_fallen_s": 0.5,
    }
    assert posture.recovery_success(env, **params).tolist() == [0.0, 1.0, 0.0, 0.0]
    env._ht_fallen_tax_state = torch.ones(4, dtype=torch.bool)
    assert posture.fallen_tax(env, 40.0, 25.0, C.RECOVERED_Z).tolist() == [
        1.0,
        0.0,
        1.0,
        1.0,
    ]


def test_air_time_forwards_original_parameters_and_preserves_angle_equality():
    env, robot, _ = _environment()
    angles = torch.tensor([0.0, 39.0, 40.0, 41.0])
    robot.data.projected_gravity_b[:, 2] = -torch.cos(torch.deg2rad(angles))
    params = {
        "sensor_name": "feet",
        "threshold_min": 0.125,
        "threshold_max": 0.3,
        "command_name": "twist",
        "command_threshold": 0.01,
    }
    with patch.object(
        posture, "feet_air_time", return_value=torch.tensor([1.0, 2.0, 3.0, 4.0])
    ) as base:
        result = posture.feet_air_time_upright(env, gate_tilt_above_deg=40.0, **params)
    base.assert_called_once_with(env, **params)
    torch.testing.assert_close(result, torch.tensor([1.0, 2.0, 3.0, 0.0]))


def test_relative_upright_zero_command_keeps_both_baseline_formulas():
    env, robot, _ = _environment(257)
    pitch = torch.linspace(-math.pi, math.pi, 257)
    robot.data.projected_gravity_b[:, 0] = torch.sin(pitch)
    robot.data.projected_gravity_b[:, 2] = -torch.cos(pitch)
    params = {"std": math.sqrt(0.05), "height_low": C.SIT_Z, "height_high": C.STAND_Z}
    torch.testing.assert_close(
        posture.upright_body_cmd_relative(env, params["std"]),
        upright(env, params["std"]),
    )
    # 本地额外高度项仍用角度 Gaussian，不把它当作官方 g_xy 原式。
    torch.testing.assert_close(
        posture.upright_gaussian_at_height(env, **params, command_name="body_pose"),
        posture.upright_gaussian_at_height(env, **params),
    )


def test_relative_upright_accepts_commanded_roll_pitch_and_ignores_other_axes():
    env, robot, command = _environment()
    command[:, 3] = torch.tensor([0.14, -0.14, 0.1, -0.1])
    command[:, 4] = torch.tensor([-0.14, 0.14, 0.1, -0.1])
    roll, pitch = command[:, 3], command[:, 4]
    robot.data.projected_gravity_b[:] = torch.stack(
        [
            torch.sin(pitch),
            -torch.sin(roll) * torch.cos(pitch),
            -torch.cos(roll) * torch.cos(pitch),
        ],
        dim=1,
    )
    params = {
        "std": math.sqrt(0.05),
        "height_low": C.SIT_Z,
        "height_high": C.STAND_Z,
        "command_name": "body_pose",
    }
    expected = torch.ones(4)
    torch.testing.assert_close(
        posture.upright_body_cmd_relative(env, params["std"]), expected
    )
    torch.testing.assert_close(
        posture.upright_gaussian_at_height(env, **params),
        expected,
        atol=1e-5,
        rtol=1e-5,
    )
    command[:, [0, 1, 2, 5]] = 0.5
    torch.testing.assert_close(
        posture.upright_body_cmd_relative(env, params["std"]), expected
    )
    torch.testing.assert_close(
        posture.upright_gaussian_at_height(env, **params),
        expected,
        atol=1e-5,
        rtol=1e-5,
    )
