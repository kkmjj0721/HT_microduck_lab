# Copyright (c) 2026-2027 zh
"""验证官方命令分桶、课程边界、逐环境状态与混合执行器随机化。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

from ht_microduck.actuator.HD_1910_C001.friction_dr_bam import FrictionDRBamActuator
from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.mdp.official_commands import (
    UniformPoseCommandCfg,
    VelocityCommandCommandOnlyCfg,
)
from ht_microduck.tasks.mdp.official_curriculums import (
    com_range_curriculum,
    event_param_curriculum,
    pose_command_range_curriculum,
    push_curriculum,
    reward_weight,
    standing_envs_curriculum,
    termination_param_curriculum,
)
from ht_microduck.tasks.mdp.official_events import (
    expand_bam_friction_fields,
    randomize_bam_friction,
    reset_action_history,
    robot_state_is_nan,
)


class _Scene(dict):
    def __init__(self, robot, sensors=None):
        super().__init__(robot=robot)
        self.sensors = {} if sensors is None else sensors


def _env(num_envs=4096):
    data = SimpleNamespace(
        heading_w=torch.zeros(num_envs),
        joint_pos=torch.zeros(num_envs, 15),
        joint_vel=torch.zeros(num_envs, 15),
        root_link_pos_w=torch.zeros(num_envs, 3),
        root_link_quat_w=torch.zeros(num_envs, 4),
        root_link_lin_vel_b=torch.zeros(num_envs, 3),
        root_link_ang_vel_b=torch.zeros(num_envs, 3),
        root_link_lin_vel_w=torch.zeros(num_envs, 3),
        root_link_ang_vel_w=torch.zeros(num_envs, 3),
    )
    return SimpleNamespace(
        num_envs=num_envs,
        device="cpu",
        step_dt=0.02,
        scene=_Scene(SimpleNamespace(data=data)),
    )


def test_official_turn_bucket_is_sampled_and_survives_standing_update():
    torch.manual_seed(13)
    env = _env(10_000)
    cfg = VelocityCommandCommandOnlyCfg(
        entity_name="robot",
        resampling_time_range=(3.0, 8.0),
        heading_command=True,
        rel_heading_envs=0.0,
        rel_standing_envs=0.25,
        rel_forward_envs=0.2,
        rel_turn_in_place_envs=0.15,
        ranges=VelocityCommandCommandOnlyCfg.Ranges(
            lin_vel_x=(-0.4, 0.4),
            lin_vel_y=(-0.3, 0.3),
            ang_vel_z=(-1.0, 1.0),
            heading=(-3.14, 3.14),
        ),
    )
    term = cfg.build(env)
    term._resample_command(torch.arange(env.num_envs))
    turns = (term.command[:, :2] == 0).all(dim=-1) & (term.command[:, 2] != 0)
    assert 0.13 < turns.float().mean() < 0.17
    assert not term.is_standing_env[turns].any()
    assert (term.command[turns, 2].abs() >= 0.4).all()
    assert (term.command[turns, 2].abs() <= 1.0).all()
    original = term.command[turns].clone()
    term._update_command()
    torch.testing.assert_close(term.command[turns], original)
    assert not term.is_heading_env.any()


def test_official_pose_command_uses_ranges_dimension_and_exact_zero_bucket():
    torch.manual_seed(71)
    env = _env()
    cfg = UniformPoseCommandCfg(
        resampling_time_range=(2.0, 5.0),
        ranges=((0.1, 0.2),) * 4,
        zero_command_prob=0.3,
    )
    term = cfg.build(env)
    term._resample_command(torch.arange(env.num_envs))
    assert cfg.dim == term.dim == 4
    assert term.command.shape == (env.num_envs, 4)
    zeros = (term.command == 0).all(dim=-1)
    assert 0.27 < zeros.float().mean() < 0.33
    assert ((term.command[~zeros] >= 0.1) & (term.command[~zeros] <= 0.2)).all()
    before = term.command.clone()
    term._resample_command(torch.tensor([1, 3]))
    keep = torch.ones(env.num_envs, dtype=torch.bool)
    keep[[1, 3]] = False
    torch.testing.assert_close(term.command[keep], before[keep])


def _curriculum_env(step):
    event = SimpleNamespace(params={"preserved": 17})
    reward = SimpleNamespace(weight=-0.1)
    command = SimpleNamespace(cfg=SimpleNamespace(rel_standing_envs=0.02, ranges=()))
    termination = SimpleNamespace(params={"preserved": 23})
    env = SimpleNamespace(
        common_step_counter=step,
        event_manager=SimpleNamespace(get_term_cfg=lambda name: event),
        reward_manager=SimpleNamespace(get_term_cfg=lambda name: reward),
        command_manager=SimpleNamespace(get_term=lambda name: command),
        termination_manager=SimpleNamespace(
            _term_names=["fell_over"], _term_cfgs=[termination]
        ),
        cfg=SimpleNamespace(events={"event": deepcopy(event)}),
    )
    return env, event, reward, command, termination


@pytest.mark.parametrize("step,expected", [(99, -0.1), (100, -0.1), (101, -1.0)])
def test_reward_weight_keeps_official_strict_stage_boundary(step, expected):
    env, _, live, _, _ = _curriculum_env(step)
    value = reward_weight(
        env, None, "action_rate_l2", [{"step": 0, "weight": -0.1}, {"step": 100, "weight": -1.0}]
    )
    assert live.weight == expected
    assert value.item() == pytest.approx(expected)


@pytest.mark.parametrize("step,expected", [(99, 0.02), (100, 0.02), (101, 0.25)])
def test_standing_fraction_keeps_official_strict_stage_boundary(step, expected):
    env, _, _, live, _ = _curriculum_env(step)
    standing_envs_curriculum(
        env,
        None,
        "twist",
        [{"step": 0, "rel_standing_envs": 0.02}, {"step": 100, "rel_standing_envs": 0.25}],
    )
    assert live.cfg.rel_standing_envs == expected


@pytest.mark.parametrize("step,expected", [(99, 0.1), (100, 0.9), (101, 0.9)])
def test_pose_range_keeps_official_inclusive_stage_boundary(step, expected):
    env, _, _, live, _ = _curriculum_env(step)
    pose_command_range_curriculum(
        env, None, "head_pose", [{"step": 0, "ranges": ((-0.1, 0.1),)}, {"step": 100, "ranges": ((-0.9, 0.9),)}]
    )
    assert live.cfg.ranges == ((-expected, expected),)


@pytest.mark.parametrize("step,expected", [(100, 0.003), (101, 0.015)])
def test_com_and_push_curricula_mutate_live_manager_only(step, expected):
    env, live, _, _, _ = _curriculum_env(step)
    com_range_curriculum(
        env, None, "event", [{"step": 0, "range": 0.003}, {"step": 100, "range": 0.015}]
    )
    assert live.params["ranges"] == (-expected, expected)
    push_curriculum(
        env,
        None,
        "event",
        [
            {"step": 0, "velocity_range": {"x": (-0.1, 0.1)}},
            {"step": 100, "velocity_range": {"x": (-0.3, 0.3)}},
        ],
    )
    magnitude = 0.1 if step == 100 else 0.3
    assert live.params["velocity_range"] == {"x": (-magnitude, magnitude)}
    assert env.cfg.events["event"].params == {"preserved": 17}


def test_event_and_termination_curricula_shallow_merge_at_inclusive_boundary():
    env, event, _, _, termination = _curriculum_env(100)
    stages = [{"step": 0, "params": {"value": 0}}, {"step": 100, "params": {"value": 4}}]
    event_param_curriculum(env, None, "event", stages)
    termination_param_curriculum(env, None, "fell_over", stages)
    assert event.params == {"preserved": 17, "value": 4}
    assert termination.params == {"preserved": 23, "value": 4}
    assert termination_param_curriculum(env, None, "removed", stages).item() == 0


def test_action_cache_reset_uses_ht_joint_order_and_leaves_neighbours():
    env = _env(3)
    env.action_manager = SimpleNamespace(action=torch.arange(42).reshape(3, 14).float())
    env._prev_leg_actions = torch.full((3, 10), -1.0)
    env._prev_neck_actions = torch.full((3, 4), -1.0)
    reset_action_history(env, torch.tensor([1]))
    torch.testing.assert_close(env._prev_leg_actions[1], env.action_manager.action[1, :10])
    torch.testing.assert_close(env._prev_neck_actions[1], env.action_manager.action[1, 10:])
    assert (env._prev_leg_actions[[0, 2]] == -1).all()
    assert (env._prev_neck_actions[[0, 2]] == -1).all()
    assert C.ACTION_DIM == 14


def test_bam_friction_randomization_is_local_and_does_not_accumulate():
    env = _env(3)
    bam = object.__new__(FrictionDRBamActuator)
    bam.friction_scale = torch.ones(3, 1)
    bam.default_friction_scale = torch.ones(3, 1)
    brushless = SimpleNamespace(untouched=17)
    env.scene["robot"].actuators = [brushless, bam]
    randomize_bam_friction(env, torch.tensor([1]), (1.2, 1.2))
    torch.testing.assert_close(bam.friction_scale[:, 0], torch.tensor([1.0, 1.2, 1.0]))
    randomize_bam_friction(env, torch.tensor([1]), (0.9, 0.9))
    torch.testing.assert_close(bam.friction_scale[:, 0], torch.tensor([1.0, 0.9, 1.0]))
    assert brushless.untouched == 17
    assert set(expand_bam_friction_fields.model_fields) == {"dof_frictionloss", "dof_damping"}


def test_nan_guard_catches_root_and_contact_failures_with_finite_joints():
    env = _env(3)
    env.scene["robot"].data.root_link_lin_vel_w[1, 0] = float("inf")
    force = torch.zeros(3, 2, 3)
    force[2, 0, 0] = float("nan")
    env.scene.sensors["feet"] = SimpleNamespace(data=SimpleNamespace(force=force))
    result = robot_state_is_nan(env, sensor_names=("feet",))
    assert result.tolist() == [False, True, True]
