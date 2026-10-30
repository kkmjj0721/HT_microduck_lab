"""Exercise live pose-range curricula through real command resampling."""

from types import SimpleNamespace

import pytest
import torch
from mjlab.managers.command_manager import CommandManager
from mjlab.managers.curriculum_manager import CurriculumManager, CurriculumTermCfg

from ht_microduck.tasks.mdp.commands import UniformPoseCommandCfg
from ht_microduck.tasks.mdp.curriculums import pose_command_range_curriculum

HEAD_RANGE_STAGES = [
    {"step": 0, "ranges": ((-0.05, 0.05), (-0.05, 0.05), (-0.07, 0.07), (-0.015, 0.015))},
    {"step": 500 * 24, "ranges": ((-0.17, 0.17), (-0.17, 0.17), (-0.21, 0.21), (-0.047, 0.047))},
    {"step": 1000 * 24, "ranges": ((-0.39, 0.39), (-0.39, 0.39), (-0.49, 0.49), (-0.11, 0.11))},
    {"step": 1500 * 24, "ranges": ((-0.72, 0.72), (-0.72, 0.72), (-0.91, 0.91), (-0.20, 0.20))},
    {"step": 2000 * 24, "ranges": ((-1.10, 1.10), (-1.10, 1.10), (-1.40, 1.40), (-0.31, 0.31))},
]


def _make_env(dim=4, stages=None, zero_command_prob=0.0):
    if stages is None:
        stages = HEAD_RANGE_STAGES
    env = SimpleNamespace(num_envs=128, device="cpu", common_step_counter=0)
    command_cfg = UniformPoseCommandCfg(
        dim=dim,
        ranges=((-0.001, 0.001),) * dim,
        resampling_time_range=(2.0, 5.0),
        zero_command_prob=zero_command_prob,
    )
    env.command_manager = CommandManager({"pose": command_cfg}, env)
    curriculum_cfg = CurriculumTermCfg(
        func=pose_command_range_curriculum,
        params={"command_name": "pose", "range_stages": stages},
    )
    return env, command_cfg, curriculum_cfg


def _assert_in_ranges(command, ranges):
    assert command.shape[1] == len(ranges)
    for axis, (low, high) in enumerate(ranges):
        assert torch.all(command[:, axis] >= low)
        assert torch.all(command[:, axis] <= high)


def test_head_curriculum_updates_live_ranges_at_each_iteration_boundary():
    env, command_cfg, cfg = _make_env()
    manager = CurriculumManager({"head_pose_range": cfg}, env)
    term = env.command_manager.get_term("pose")
    all_ids = torch.arange(env.num_envs)
    boundaries = [(0, 0), (500 * 24 - 1, 0), (500 * 24, 1),
                  (1000 * 24 - 1, 1), (1000 * 24, 2),
                  (1500 * 24 - 1, 2), (1500 * 24, 3),
                  (2000 * 24 - 1, 3), (2000 * 24, 4)]
    for step, stage in boundaries:
        env.common_step_counter = step
        manager.compute(all_ids)
        assert term.cfg.ranges == HEAD_RANGE_STAGES[stage]["ranges"]
        assert command_cfg.dim == term.command.shape[1] == 4
        term.reset(all_ids)
        _assert_in_ranges(term.command, HEAD_RANGE_STAGES[stage]["ranges"])
    assert term.command[:, 2].abs().max() > 1.0
    logged = manager.reset(all_ids)
    assert logged["Curriculum/head_pose_range/axis_2/min"] == pytest.approx(-1.4)
    assert logged["Curriculum/head_pose_range/axis_3/max"] == pytest.approx(0.31)


def test_curriculum_only_changes_next_resample_and_local_reset_keeps_neighbours():
    env, _, cfg = _make_env()
    curriculum = pose_command_range_curriculum(cfg, env)
    term = env.command_manager.get_term("pose")
    all_ids = torch.arange(env.num_envs)
    curriculum(env, all_ids, **cfg.params)
    term.reset(all_ids)
    before_command = term.command.clone()
    before_timers = term.time_left.clone()
    before_counters = term.command_counter.clone()
    env.common_step_counter = 2000 * 24
    curriculum(env, torch.tensor([0]), **cfg.params)
    assert torch.equal(term.command, before_command)
    assert torch.equal(term.time_left, before_timers)
    assert torch.equal(term.command_counter, before_counters)
    term.reset(torch.tensor([0]))
    assert torch.equal(term.command[1:], before_command[1:])
    assert torch.equal(term.time_left[1:], before_timers[1:])
    assert torch.equal(term.command_counter[1:], before_counters[1:])
    _assert_in_ranges(term.command[:1], HEAD_RANGE_STAGES[-1]["ranges"])


def test_six_dimensional_body_command_keeps_width_and_reserves_zero_commands():
    torch.manual_seed(0)
    ranges = ((-0.005, 0.005),) * 3 + ((-0.05, 0.05),) * 3
    env, _, cfg = _make_env(
        dim=6, stages=[{"step": 0, "ranges": ranges}], zero_command_prob=0.25
    )
    curriculum = pose_command_range_curriculum(cfg, env)
    curriculum(env, torch.arange(env.num_envs), **cfg.params)
    command = env.command_manager.get_term("pose")
    command.reset(torch.arange(env.num_envs))
    _assert_in_ranges(command.command, ranges)
    zero = torch.all(command.command == 0.0, dim=1)
    assert zero.any() and (~zero).any()
    assert command.command.shape == (env.num_envs, 6)


def test_first_stage_applies_before_its_threshold_and_last_reached_stage_wins():
    stages = [
        {"step": 10, "ranges": ((-0.1, 0.1),) * 4},
        {"step": 10, "ranges": ((-0.2, 0.2),) * 4},
    ]
    env, _, cfg = _make_env(stages=stages)
    curriculum = pose_command_range_curriculum(cfg, env)
    curriculum(env, torch.arange(env.num_envs), **cfg.params)
    assert env.command_manager.get_term("pose").cfg.ranges == stages[0]["ranges"]
    env.common_step_counter = 10
    curriculum(env, torch.arange(env.num_envs), **cfg.params)
    assert env.command_manager.get_term("pose").cfg.ranges == stages[1]["ranges"]


@pytest.mark.parametrize("stages,match", [
    ([], "at least one stage"),
    ([{"step": 0, "ranges": ((-0.1, 0.1),)}], "expected 4"),
    ([{"step": 0, "ranges": ((0.1, -0.1),) * 4}], "reversed range"),
    ([{"step": 2, "ranges": ((-0.1, 0.1),) * 4},
      {"step": 1, "ranges": ((-0.2, 0.2),) * 4}], "nondecreasing"),
])
def test_invalid_pose_curriculum_cannot_change_the_fixed_command_contract(stages, match):
    env, command_cfg, cfg = _make_env(stages=stages)
    original = command_cfg.ranges
    with pytest.raises(ValueError, match=match):
        pose_command_range_curriculum(cfg, env)
    assert command_cfg.ranges == original
    assert command_cfg.dim == 4
