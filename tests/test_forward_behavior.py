# Copyright (c) 2026-2027 zh
"""验证前坐独立度量的目标腿形、坐标系、连续保持计时及四类帧归属。"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
import torch

from ht_microduck.robot.ht_microduck_constants import HOME_JOINT_POS
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
)
from ht_microduck.tasks.mdp.forward_behavior import (
    ForwardHoldDuration,
    forward_case_frames,
    forward_case_success_frames,
    forward_posture_valid,
)


class _Scene(dict):
    """提供实际度量使用的机器人和地形原点。"""


def _environment(sitting):
    """构造世界坐标中的两种终点，保留有命名和顺序的关节状态。"""
    sit = torch.tensor(sitting, dtype=torch.bool)
    count = len(sit)
    home = torch.tensor([[HOME_JOINT_POS[name] for name in C.POLICY_JOINT_NAMES]]).repeat(count, 1)
    seat = home.clone()
    for name, angle in FORWARD_SITTING_JOINT_POS.items():
        seat[:, C.POLICY_JOINT_NAMES.index(name)] = angle
    root = torch.zeros(count, 3)
    root[:, 2] = torch.where(sit, FORWARD_SIT_Z, C.STAND_Z)
    quat = torch.zeros(count, 4)
    quat[:, 0] = 1.0
    sites = root[:, None, :] + torch.tensor([[[0.1, -0.04, -0.04], [0.1, 0.04, -0.04]]])
    robot = SimpleNamespace(
        data=SimpleNamespace(
            default_joint_pos=home,
            joint_pos=torch.where(sit[:, None], seat, home),
            root_link_pos_w=root,
            root_link_quat_w=quat,
            site_pos_w=sites,
        ),
        find_joints=lambda names, preserve_order: (list(range(C.ACTION_DIM)), list(C.POLICY_JOINT_NAMES)),
        find_sites=lambda names, preserve_order: ([0, 1], ["r_foot", "l_foot"]),
    )
    scene = _Scene(robot=robot)
    scene.env_origins = torch.zeros(count, 3)
    commands = {"twist": torch.zeros(count, 3), "alternate": torch.zeros(count, 3)}
    commands["twist"][:, 0] = sit.float()
    env = SimpleNamespace(
        scene=scene, num_envs=count, device="cpu", step_dt=0.02,
        command_manager=SimpleNamespace(get_command=commands.__getitem__),
        _forward_initial_sit=sit.clone(),
    )
    return env, robot, commands


def _set_standing(robot, rows):
    """仅把所选环境切换到真实站立终点。"""
    robot.data.joint_pos[rows] = robot.data.default_joint_pos[rows]
    robot.data.root_link_pos_w[rows, 2] = C.STAND_Z


def test_endpoint_validity_tracks_the_live_command_and_explicit_target():
    env, _, commands = _environment([True, False])
    assert forward_posture_valid(env).tolist() == [True, True]
    commands["twist"][:, 0] = 1 - commands["twist"][:, 0]
    assert forward_posture_valid(env).tolist() == [False, False]
    assert forward_posture_valid(env, torch.tensor([True, False])).tolist() == [True, True]
    commands["alternate"][:, 0] = torch.tensor([1.0, 0.0])
    assert forward_posture_valid(env, command_name="alternate").tolist() == [True, True]


def test_low_rear_fold_is_invalid_even_at_the_correct_height_and_upright_angle():
    env, robot, _ = _environment([True, True])
    robot.data.site_pos_w[0, :, 0] = -0.098
    robot.data.joint_pos[1, [2, 7]] = 1.45
    assert forward_posture_valid(env).tolist() == [False, False]


def test_both_feet_must_pass_the_forward_distance_threshold():
    env, robot, _ = _environment([True, True])
    robot.data.site_pos_w[0, 0, 0] = 0.0149
    robot.data.site_pos_w[1, 0, 0] = 0.0151
    assert forward_posture_valid(env).tolist() == [False, True]


@pytest.mark.parametrize("joint", ["r_calf_joint", "l_calf_joint", "r_hip_pitch_joint", "l_hip_pitch_joint"])
def test_each_critical_joint_must_be_correct_even_when_mean_leg_error_is_small(joint):
    env, robot, _ = _environment([True, True])
    index = C.POLICY_JOINT_NAMES.index(joint)
    robot.data.joint_pos[0, index] += 0.349
    robot.data.joint_pos[1, index] += 0.351
    assert forward_posture_valid(env).tolist() == [True, False]


def test_mean_leg_error_is_checked_for_sitting_and_standing():
    env, robot, _ = _environment([True, False])
    robot.data.joint_pos[:, :10] += 0.26
    assert forward_posture_valid(env).tolist() == [False, False]


@pytest.mark.parametrize("sitting", [True, False])
def test_tilt_boundary_is_checked_for_both_postures(sitting):
    env, robot, _ = _environment([sitting, sitting])
    angles = torch.tensor([14.99, 15.01]) * math.pi / 180.0
    robot.data.root_link_quat_w[:, 0] = torch.cos(angles / 2)
    robot.data.root_link_quat_w[:, 2] = torch.sin(angles / 2)
    assert forward_posture_valid(env).tolist() == [True, False]


@pytest.mark.parametrize("sitting,tolerance", [(True, 0.015), (False, 0.02)])
def test_height_tolerance_uses_the_environment_origin(sitting, tolerance):
    env, robot, _ = _environment([sitting, sitting])
    env.scene.env_origins[:, 2] = torch.tensor([1.5, 2.0])
    robot.data.root_link_pos_w[:, 2] += env.scene.env_origins[:, 2] + torch.tensor([tolerance - 0.0001, tolerance + 0.0001])
    assert forward_posture_valid(env).tolist() == [True, False]


def test_forward_feet_are_measured_in_the_body_frame_after_world_yaw_and_translation():
    env, robot, _ = _environment([True, True])
    # 绕世界Z转180°后，世界坐标向负X的足点仍位于机体前方。
    robot.data.root_link_quat_w[:, 0] = 0.0
    robot.data.root_link_quat_w[:, 3] = 1.0
    robot.data.root_link_pos_w[:, :2] = torch.tensor([[3.0, 4.0], [5.0, 6.0]])
    robot.data.site_pos_w[:] = robot.data.root_link_pos_w[:, None, :]
    robot.data.site_pos_w[0, :, 0] -= 0.1
    robot.data.site_pos_w[1, :, 0] += 0.1
    assert forward_posture_valid(env).tolist() == [True, False]


def test_standing_does_not_require_forward_seated_feet_or_head_tracking():
    env, robot, _ = _environment([False, True])
    robot.data.site_pos_w[0, :, 0] = -0.1
    robot.data.joint_pos[:, 10:] += 1.0
    assert forward_posture_valid(env).tolist() == [True, True]


def test_continuous_hold_restarts_after_an_invalid_frame_and_preserves_prior_output():
    env, robot, _ = _environment([True, False])
    metric = ForwardHoldDuration(SimpleNamespace(), env)
    first = metric(env)
    for _ in range(4):
        metric(env)
    torch.testing.assert_close(first, torch.tensor([0.02, 0.02]))
    robot.data.site_pos_w[0, :, 0] = -0.1
    torch.testing.assert_close(metric(env), torch.tensor([0.0, 0.12]))
    robot.data.site_pos_w[0, :, 0] = 0.1
    torch.testing.assert_close(metric(env), torch.tensor([0.02, 0.14]))


def test_command_switch_clears_duration_even_if_the_new_posture_is_already_valid():
    env, robot, commands = _environment([True, False])
    metric = ForwardHoldDuration(SimpleNamespace(), env)
    for _ in range(3):
        metric(env)
    commands["twist"][0, 0] = 0.0
    _set_standing(robot, [0])
    torch.testing.assert_close(metric(env), torch.tensor([0.0, 0.08]))
    torch.testing.assert_close(metric(env), torch.tensor([0.02, 0.1]))


def test_five_seconds_of_continuous_hold_reaches_the_gate_without_accumulation_drift():
    env, _, _ = _environment([True, False])
    metric = ForwardHoldDuration(SimpleNamespace(), env)
    for _ in range(250):
        duration = metric(env)
    assert torch.equal(duration, torch.tensor([5.0, 5.0]))


def test_partial_reset_clears_only_selected_environment_duration_and_command_history():
    env, robot, commands = _environment([True, False])
    metric = ForwardHoldDuration(SimpleNamespace(), env)
    for _ in range(5):
        metric(env)
    metric.reset(torch.tensor([0]))
    commands["twist"][0, 0] = 0.0
    _set_standing(robot, [0])
    torch.testing.assert_close(metric(env), torch.tensor([0.02, 0.12]))
    metric.reset()
    torch.testing.assert_close(metric(env), torch.tensor([0.02, 0.02]))


@pytest.mark.parametrize("initial,target,index", [(False, False, 0), (False, True, 1), (True, False, 2), (True, True, 3)])
def test_four_cases_are_separated_by_initial_posture_and_live_target(initial, target, index):
    env, robot, commands = _environment([False, True, False, True])
    env._forward_initial_sit[:] = torch.tensor([False, False, True, True])
    expected = torch.zeros(4)
    expected[index] = 1.0
    torch.testing.assert_close(forward_case_frames(env, initial, target), expected)
    torch.testing.assert_close(forward_case_success_frames(env, initial, target), expected)
    robot.data.joint_pos[index, 0] += 3.0
    torch.testing.assert_close(forward_case_frames(env, initial, target), expected)
    torch.testing.assert_close(forward_case_success_frames(env, initial, target), torch.zeros(4))
    commands["twist"][:, 0] = 1 - commands["twist"][:, 0]
    assert forward_case_frames(env, initial, target).sum() == 1.0


def test_case_metrics_use_the_requested_command_without_writing_the_environment():
    env, robot, commands = _environment([True, False])
    commands["alternate"][:, 0] = torch.tensor([1.0, 0.0])
    joints = robot.data.joint_pos.clone()
    initial = env._forward_initial_sit.clone()
    before = {name: command.clone() for name, command in commands.items()}
    torch.testing.assert_close(forward_case_success_frames(env, True, True, "alternate"), torch.tensor([1.0, 0.0]))
    assert torch.equal(joints, robot.data.joint_pos)
    assert torch.equal(initial, env._forward_initial_sit)
    assert all(torch.equal(before[name], commands[name]) for name in commands)
