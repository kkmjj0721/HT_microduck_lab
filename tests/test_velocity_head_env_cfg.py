"""Protect the walking/head task contract and independent head-pose objectives."""

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
import torch
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.utils.lab_api.string import resolve_matching_names

from ht_microduck.robot.ht_microduck_constants import (
    HOME_JOINT_POS,
    JOINT_NAMES,
    MJCF_PATH,
)
from ht_microduck.tasks import (
    FLAT_VELOCITY_HEAD_TASK_ID,
    FLAT_VELOCITY_TASK_ID,
    _assert_task_contract,
)
from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_velocity_env_cfg import (
    make_flat_velocity_env_cfg,
)
from ht_microduck.tasks.config.ht_microduck.flat_velocity_head_env_cfg import (
    HEAD_POSE_RANGE_STAGES,
    make_flat_velocity_head_env_cfg,
)
from ht_microduck.tasks.config.ht_microduck.rl_cfg import (
    FlatVelocityRlCfg,
    VelocityHeadRlCfg,
)
from ht_microduck.tasks.rl.runner import (
    OfficialTaskOnPolicyRunner,
    VelocityHeadOnPolicyRunner,
)


@pytest.mark.parametrize("play", [False, True])
def test_registered_walking_head_task_keeps_the_contract_and_drives_both_pose_slots(play):
    assert FLAT_VELOCITY_HEAD_TASK_ID in list_tasks()
    assert load_runner_cls(FLAT_VELOCITY_HEAD_TASK_ID) is VelocityHeadOnPolicyRunner
    assert load_runner_cls(FLAT_VELOCITY_TASK_ID) is OfficialTaskOnPolicyRunner
    cfg = load_env_cfg(FLAT_VELOCITY_HEAD_TASK_ID, play=play)
    _assert_task_contract(FLAT_VELOCITY_HEAD_TASK_ID, cfg)
    assert tuple(cfg.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(cfg.observations["critic"].terms) == C.critic_observation_terms(FLAT_VELOCITY_HEAD_TASK_ID)
    assert C.ACTOR_OBSERVATION_DIM == 61
    assert C.TASK_CRITIC_OBSERVATION_DIMS[FLAT_VELOCITY_HEAD_TASK_ID] == 76
    action = cfg.actions["joint_pos"]
    assert tuple(action.actuator_names) == C.POLICY_JOINT_NAMES
    assert len(action.actuator_names) == 14
    assert action.scale == 1.0
    values = {
        "head_pose": torch.tensor([[0.01, -0.02, 0.03, -0.01]]),
        "body_pose": torch.tensor([[0.001, -0.002, 0.003, -0.01, 0.02, -0.03]]),
    }
    env = SimpleNamespace(command_manager=SimpleNamespace(get_command=values.__getitem__))
    for group in ("actor", "critic"):
        for slot, command_name, dim in (("head_command", "head_pose", 4), ("body_command", "body_pose", 6)):
            term = cfg.observations[group].terms[slot]
            assert term.params["command_name"] == command_name
            assert cfg.commands[command_name].dim == dim
            assert torch.equal(term.func(env, **term.params), values[command_name])
    assert cfg.commands["head_pose"].zero_command_prob == 0.0
    assert cfg.commands["body_pose"].zero_command_prob == 0.0
    assert cfg.rewards["body_pose_tracking"].weight == 0.0


def test_train_and_play_use_the_same_step_based_head_curriculum():
    train = make_flat_velocity_head_env_cfg(num_envs=1, seed=0)
    play = make_flat_velocity_head_env_cfg(num_envs=1, seed=0, play=True)
    assert train.commands["head_pose"].ranges == play.commands["head_pose"].ranges
    assert train.commands["head_pose"].resampling_time_range == (2.0, 5.0)
    assert train.curriculum["head_pose_range"].params == play.curriculum["head_pose_range"].params
    assert [stage["step"] for stage in train.curriculum["head_pose_range"].params["range_stages"]] == (
        [iteration * 24 for iteration, _ in HEAD_POSE_RANGE_STAGES]
    )


def test_alias_factory_nested_changes_do_not_mutate_the_other_official_factory():
    baseline = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    variant = make_flat_velocity_head_env_cfg(num_envs=1, seed=0)
    assert variant.rewards["head_pose_tracking"].params is not baseline.rewards["head_pose_tracking"].params
    assert variant.scene.terrain is not baseline.scene.terrain
    for group in ("actor", "critic"):
        for name in ("joint_pos", "joint_vel"):
            original_selector = baseline.observations[group].terms[name].params["asset_cfg"]
            variant_selector = variant.observations[group].terms[name].params["asset_cfg"]
            assert variant_selector is not original_selector
            variant_selector.joint_names = ("neck_pitch_joint",)
    variant.rewards["head_pose_tracking"].params["std"] = 99.0
    variant.actions["joint_pos"].scale = 99.0
    variant.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    variant.rewards["pose"].params["std_standing"][r".*hip_roll.*"] = 99.0
    fresh = make_flat_velocity_head_env_cfg(num_envs=1, seed=0)
    assert baseline.rewards["head_pose_tracking"].params["std"] == 0.5
    assert baseline.actions["joint_pos"].scale == 1.0
    assert baseline.commands["head_pose"].ranges == HEAD_POSE_RANGE_STAGES[0][1]
    assert "stand_still" not in baseline.rewards and "pose" in baseline.rewards
    assert fresh.actions["joint_pos"].scale == 1.0
    assert fresh.commands["head_pose"].ranges == HEAD_POSE_RANGE_STAGES[0][1]
    assert fresh.rewards["pose"].params["std_standing"][r".*hip_roll.*"] == 0.05
    for group in ("actor", "critic"):
        for name in ("joint_pos", "joint_vel"):
            for cfg in (baseline, fresh):
                selector = cfg.observations[group].terms[name].params["asset_cfg"]
                assert tuple(selector.joint_names) == C.POLICY_JOINT_NAMES


def test_registry_loaded_configs_and_rl_settings_are_isolated():
    variant = load_env_cfg(FLAT_VELOCITY_HEAD_TASK_ID)
    variant.commands["head_pose"].ranges = ((99.0, 99.0),) * 4
    variant.curriculum["head_pose_range"].params["range_stages"].clear()
    variant.actions["joint_pos"].scale = 99.0
    fresh = load_env_cfg(FLAT_VELOCITY_HEAD_TASK_ID)
    original = load_env_cfg(FLAT_VELOCITY_TASK_ID)
    assert fresh.commands["head_pose"].ranges == HEAD_POSE_RANGE_STAGES[0][1]
    assert len(fresh.curriculum["head_pose_range"].params["range_stages"]) == 5
    assert fresh.actions["joint_pos"].scale == 1.0
    assert original.commands["head_pose"].ranges == HEAD_POSE_RANGE_STAGES[0][1]
    assert original.actions["joint_pos"].scale == 1.0
    runner = load_rl_cfg(FLAT_VELOCITY_HEAD_TASK_ID)
    assert runner.experiment_name == VelocityHeadRlCfg.experiment_name == "flat_velocity_head"
    assert runner.experiment_name != FlatVelocityRlCfg.experiment_name
    assert asdict(runner.actor) == asdict(FlatVelocityRlCfg.actor)
    assert asdict(runner.critic) == asdict(FlatVelocityRlCfg.critic)
    assert asdict(runner.algorithm) == asdict(FlatVelocityRlCfg.algorithm)
    runner.actor.hidden_dims = (1,)
    runner.algorithm.entropy_coef = 99.0
    assert load_rl_cfg(FLAT_VELOCITY_HEAD_TASK_ID).actor.hidden_dims == (512, 256, 128)
    assert FlatVelocityRlCfg.algorithm.entropy_coef == 0.01


def test_widest_head_commands_stay_inside_each_home_relative_model_limit():
    joints = {
        joint.attrib["name"]: tuple(float(value) for value in joint.attrib["range"].split())
        for joint in ElementTree.parse(MJCF_PATH).findall(".//joint[@range]")
    }
    for name, (low, high) in zip(C.HEAD_JOINT_NAMES, HEAD_POSE_RANGE_STAGES[-1][1], strict=True):
        model_low, model_high = joints[name]
        assert model_low <= HOME_JOINT_POS[name] + low
        assert HOME_JOINT_POS[name] + high <= model_high


class _Robot:
    def __init__(self):
        self.joint_names = list(JOINT_NAMES)
        self.num_joints = len(self.joint_names)
        default = torch.tensor([[HOME_JOINT_POS[name] for name in self.joint_names]])
        self.data = SimpleNamespace(default_joint_pos=default, joint_pos=default.clone())

    def find_joints(self, names, preserve_order=False):
        return resolve_matching_names(names, self.joint_names, preserve_order)

    def find_joints_by_actuator_names(self, patterns):
        return resolve_matching_names(patterns, self.joint_names, preserve_order=True)


def test_commanded_head_motion_does_not_compete_with_leg_pose_or_head_bias():
    cfg = make_flat_velocity_head_env_cfg(num_envs=1, seed=0)
    robot = _Robot()
    commands = {"twist": torch.zeros(1, 3), "head_pose": torch.zeros(1, 4)}
    env = SimpleNamespace(
        scene={"robot": robot}, command_manager=SimpleNamespace(get_command=commands.__getitem__),
        num_envs=1, device="cpu", step_dt=0.02, episode_length_buf=torch.full((1,), 2),
    )
    terms = {name: deepcopy(cfg.rewards[name]) for name in ("pose", "head_pose_tracking", "head_pose_bias")}
    terms["pose"].params["asset_cfg"].resolve(env.scene)
    pose_cfg = terms["pose"]
    pose = pose_cfg.func(pose_cfg, env)
    initial_pose = pose(env, **pose_cfg.params)
    commands["head_pose"][:] = torch.tensor([0.4, -0.25, 0.5, 0.1])
    head_ids = [robot.joint_names.index(name) for name in C.HEAD_JOINT_NAMES]
    robot.data.joint_pos[:, head_ids] += commands["head_pose"]
    assert torch.equal(pose(env, **pose_cfg.params), initial_pose)
    assert torch.equal(initial_pose, torch.ones(1))
    tracking = terms["head_pose_tracking"]
    assert torch.allclose(tracking.func(env, **tracking.params), torch.ones(1))
    bias_cfg = terms["head_pose_bias"]
    assert torch.equal(bias_cfg.func(env, **bias_cfg.params), torch.zeros(1))
    assert "stand_still" not in cfg.rewards
    robot.data.joint_pos[:, robot.joint_names.index("r_hip_pitch_joint")] += 0.1
    standing = pose(env, **pose_cfg.params)
    commands["twist"][:, 2] = 0.5
    turning = pose(env, **pose_cfg.params)
    assert 0.0 < standing.item() < turning.item() < 1.0
    assert torch.allclose(tracking.func(env, **tracking.params), torch.ones(1))
