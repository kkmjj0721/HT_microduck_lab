# Copyright (c) 2026-2027 zh
"""验证最终关节目标限幅、旧模式等价以及逐环境力矩饱和指标。"""

from dataclasses import asdict
from types import SimpleNamespace

import pytest
import torch
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.metrics_manager import MetricsManager, MetricsTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg

from ht_microduck.robot.ht_microduck_constants import HOME_JOINT_POS, get_robot_spec
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.mdp.action_metrics import (
    ActuatorSaturationDuration,
    actuator_saturation_fraction,
    applied_target_violation_fraction,
    requested_target_violation_fraction,
    target_clip_fraction,
)
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg

# ---------- 实体与动作测试台 ----------


@pytest.fixture(scope="module")
def robot_model():
    return get_robot_spec().compile()


class _ActionEntity:
    """用不同于策略的实体顺序保留真实模型关节范围与 HOME。"""

    def __init__(self, model, count):
        self.joint_names = ["mouth_joint", *reversed(C.POLICY_JOINT_NAMES)]
        home = torch.tensor([HOME_JOINT_POS[name] for name in self.joint_names])
        limits = torch.tensor([model.joint(name).range.tolist() for name in self.joint_names])
        self.data = SimpleNamespace(
            default_joint_pos=home.repeat(count, 1),
            joint_pos_limits=limits.repeat(count, 1, 1),
            soft_joint_pos_limits=limits.repeat(count, 1, 1),
            encoder_bias=torch.zeros(count, len(self.joint_names)),
            joint_pos_target=home.repeat(count, 1),
        )

    def find_joints_by_actuator_names(self, names):
        return [self.joint_names.index(name) for name in names], list(names)

    def set_joint_position_target(self, target, *, joint_ids):
        self.data.joint_pos_target[:, joint_ids] = target


def _action_env(model, count=3, **options):
    robot = _ActionEntity(model, count)
    env = SimpleNamespace(num_envs=count, device="cpu", scene={"robot": robot})
    cfg = BoundedJointPositionActionCfg(
        entity_name="robot", actuator_names=C.POLICY_JOINT_NAMES, **options
    )
    term = cfg.build(env)
    env.action_manager = SimpleNamespace(get_term=lambda _: term)
    return env, robot, term


# ---------- 物理目标与原配方对照 ----------


def test_extreme_actions_use_each_worlds_physical_joint_limits(robot_model):
    env, robot, term = _action_env(robot_model)
    ids = term.target_ids
    robot.data.joint_pos_limits[1, ids] *= 0.8
    robot.data.encoder_bias[0, ids] = -0.015
    robot.data.encoder_bias[1, ids] = 0.015
    actions = torch.stack((torch.full((14,), 20.0), torch.full((14,), -20.0), torch.zeros(14)))
    mouth_before = robot.data.joint_pos_target[:, 0].clone()
    term.process_actions(actions)
    term.apply_actions()
    targets = robot.data.joint_pos_target[:, ids]
    limits = robot.data.joint_pos_limits[:, ids]
    torch.testing.assert_close(targets[0], limits[0, :, 1])
    torch.testing.assert_close(targets[1], limits[1, :, 0])
    torch.testing.assert_close(targets[2], robot.data.default_joint_pos[2, ids])
    torch.testing.assert_close(term.raw_action, actions)
    torch.testing.assert_close(term.applied_targets, targets)
    assert tuple(term.target_names) == C.POLICY_JOINT_NAMES
    assert term.requested_targets.shape == term.applied_targets.shape == (env.num_envs, 14)
    assert term.applied_targets.dtype == torch.float32
    assert term.applied_targets.device.type == "cpu"
    assert torch.equal(robot.data.joint_pos_target[:, 0], mouth_before)
    assert torch.equal(applied_target_violation_fraction(env), torch.zeros(3))


def test_encoder_bias_is_removed_before_the_final_limit(robot_model):
    _, robot, term = _action_env(robot_model)
    slot = C.POLICY_JOINT_NAMES.index("r_hip_yaw_joint")
    joint_id = term.target_ids[slot]
    lower, upper = robot.data.joint_pos_limits[0, joint_id]
    actions = torch.zeros(3, 14)
    actions[:, slot] = torch.tensor([upper, lower, upper - 0.02])
    robot.data.encoder_bias[:, joint_id] = torch.tensor([-0.015, 0.015, -0.015])
    term.process_actions(actions)
    term.apply_actions()
    torch.testing.assert_close(term.requested_targets[:, slot], torch.tensor([upper + 0.015, lower - 0.015, upper - 0.005]))
    torch.testing.assert_close(robot.data.joint_pos_target[:, joint_id], torch.tensor([upper, lower, upper - 0.005]))


def test_exact_boundaries_and_unlimited_joints_do_not_count_as_clipping(robot_model):
    env, robot, term = _action_env(robot_model, count=2, use_default_offset=False)
    ids = term.target_ids
    target = robot.data.joint_pos_limits[:, ids, 1].clone()
    target[1] = robot.data.joint_pos_limits[1, ids, 0]
    slot = C.POLICY_JOINT_NAMES.index("head_yaw_joint")
    robot.data.joint_pos_limits[:, ids[slot]] = torch.tensor([-float("inf"), float("inf")])
    target[:, slot] = torch.tensor([100.0, -100.0])
    term.process_actions(target)
    term.apply_actions()
    torch.testing.assert_close(robot.data.joint_pos_target[:, ids], target)
    torch.testing.assert_close(requested_target_violation_fraction(env), torch.zeros(2))
    torch.testing.assert_close(target_clip_fraction(env), torch.zeros(2))


def test_sit_pose_keeps_the_full_knee_travel_and_uses_hard_limits(robot_model):
    _, robot, term = _action_env(robot_model, count=1)
    ids = term.target_ids
    desired = robot.data.default_joint_pos[:, ids].clone()
    for name, value in C.LOW_POSTURE_JOINT_POS.items():
        desired[:, C.POLICY_JOINT_NAMES.index(name)] = value
    robot.data.encoder_bias[:, ids] = 0.01
    knee_slot = C.POLICY_JOINT_NAMES.index("r_calf_joint")
    robot.data.soft_joint_pos_limits[:, ids[knee_slot], 1] = 0.3
    actions = desired - robot.data.default_joint_pos[:, ids] + 0.01
    assert actions[0, knee_slot] > 1.6
    term.process_actions(actions)
    term.apply_actions()
    torch.testing.assert_close(robot.data.joint_pos_target[:, ids], desired)
    assert term.applied_targets[0, knee_slot] > robot.data.soft_joint_pos_limits[0, ids[knee_slot], 1]


@pytest.mark.parametrize("scale,offset,clip", [(1.0, 0.0, None), (0.5, 0.1, {"r_hip_yaw_joint": (-0.1, 0.1)})])
def test_unbounded_mode_matches_the_upstream_action_exactly(robot_model, scale, offset, clip):
    _, robot, term = _action_env(robot_model, bound_targets=False, use_default_offset=False, scale=scale, offset=offset, clip=clip)
    native_robot = _ActionEntity(robot_model, 3)
    native_env = SimpleNamespace(num_envs=3, device="cpu", scene={"robot": native_robot})
    native = JointPositionActionCfg(
        entity_name="robot", actuator_names=C.POLICY_JOINT_NAMES, use_default_offset=False,
        scale=scale, offset=offset, clip=clip,
    ).build(native_env)
    robot.data.encoder_bias[:] = native_robot.data.encoder_bias[:] = 0.015
    actions = torch.linspace(-20.0, 20.0, 42).reshape(3, 14)
    term.process_actions(actions)
    native.process_actions(actions)
    term.apply_actions()
    native.apply_actions()
    assert torch.equal(robot.data.joint_pos_target, native_robot.data.joint_pos_target)
    assert torch.equal(term.raw_action, native.raw_action)
    assert torch.equal(term.requested_targets, term.applied_targets)


def test_upstream_processed_clip_still_precedes_encoder_compensation(robot_model):
    _, robot, term = _action_env(robot_model, count=1, use_default_offset=False, scale=0.5, offset=0.05, clip={"r_hip_yaw_joint": (-0.1, 0.1)})
    slot = C.POLICY_JOINT_NAMES.index("r_hip_yaw_joint")
    robot.data.encoder_bias[:, term.target_ids[slot]] = 0.02
    term.process_actions(torch.ones(1, 14))
    term.apply_actions()
    torch.testing.assert_close(term.requested_targets[0, slot], torch.tensor(0.08))
    torch.testing.assert_close(term.applied_targets[0, slot], torch.tensor(0.08))


def test_target_metrics_distinguish_requested_from_applied_positions(robot_model):
    env, _, term = _action_env(robot_model, count=2)
    actions = torch.zeros(2, 14)
    actions[0, 0] = 20
    actions[1, :2] = -20
    term.process_actions(actions)
    term.apply_actions()
    torch.testing.assert_close(requested_target_violation_fraction(env), torch.tensor([1 / 14, 2 / 14]))
    torch.testing.assert_close(target_clip_fraction(env), torch.tensor([1 / 14, 2 / 14]))
    torch.testing.assert_close(applied_target_violation_fraction(env), torch.zeros(2))


def test_partial_action_reset_preserves_neighbour_diagnostics(robot_model):
    _, _, term = _action_env(robot_model)
    term.process_actions(torch.full((3, 14), 20.0))
    term.apply_actions()
    before = (term.raw_action.clone(), term.requested_targets.clone(), term.applied_targets.clone())
    term.reset(torch.tensor([1]))
    for value, original in zip((term.raw_action, term.requested_targets, term.applied_targets), before, strict=True):
        assert torch.equal(value[[0, 2]], original[[0, 2]])
        assert torch.equal(value[1], torch.zeros(14))


@pytest.mark.parametrize("selector", [None, slice(None)])
def test_full_action_reset_accepts_the_manager_selectors(robot_model, selector):
    _, _, term = _action_env(robot_model)
    term.process_actions(torch.full((3, 14), -20.0))
    term.apply_actions()
    term.reset(selector)
    for value in (term.raw_action, term.requested_targets, term.applied_targets):
        assert torch.equal(value, torch.zeros(3, 14))


def test_limits_are_read_from_the_live_entity_data(robot_model):
    _, robot, term = _action_env(robot_model, count=1)
    term.process_actions(torch.full((1, 14), 20.0))
    term.apply_actions()
    first = term.applied_targets.clone()
    robot.data.joint_pos_limits[:, term.target_ids, 1] *= 0.5
    term.apply_actions()
    torch.testing.assert_close(term.applied_targets, first * 0.5)


# ---------- 任务配置边界 ----------


@pytest.mark.parametrize("play", [False, True])
@pytest.mark.parametrize("task", ["SitStand", "VelStand", "Velocity", "Velocity-Head", "StandUp"])
def test_only_the_two_selected_tasks_enable_target_bounds(task, play):
    cfg = load_env_cfg(f"HtDuck-Flat-{task}", play=play)
    term = cfg.actions["joint_pos"]
    if task in {"SitStand", "VelStand"}:
        assert isinstance(term, BoundedJointPositionActionCfg)
        assert term.bound_targets
        assert term.scale == 1.0
        assert tuple(term.actuator_names) == C.POLICY_JOINT_NAMES
    else:
        assert type(term) is JointPositionActionCfg


@pytest.mark.parametrize("play", [False, True])
@pytest.mark.parametrize("task,critic_dim", [("SitStand", 74), ("VelStand", 64)])
def test_unbounded_registry_entries_preserve_observation_and_action_contracts(task, critic_dim, play):
    original_id = f"HtDuck-Flat-{task}"
    baseline_id = original_id + "-Unbounded"
    original = load_env_cfg(original_id, play=play)
    baseline = load_env_cfg(baseline_id, play=play)
    action = baseline.actions["joint_pos"]
    assert isinstance(action, BoundedJointPositionActionCfg)
    assert not action.bound_targets
    assert action.scale == 1.0
    assert tuple(action.actuator_names) == C.POLICY_JOINT_NAMES
    assert C.ACTOR_OBSERVATION_DIM == 61
    assert C.TASK_CRITIC_OBSERVATION_DIMS[baseline_id] == critic_dim
    assert C.TASK_CRITIC_OBSERVATION_DIMS[original_id] == critic_dim
    assert tuple(baseline.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(baseline.observations["critic"].terms) == C.critic_observation_terms(original_id)
    assert C.critic_observation_terms(baseline_id) == C.critic_observation_terms(original_id)
    assert asdict(baseline.observations["actor"]) == asdict(original.observations["actor"])
    assert asdict(baseline.observations["critic"]) == asdict(original.observations["critic"])
    assert baseline.sim.mujoco.timestep == original.sim.mujoco.timestep
    assert baseline.decimation == original.decimation
    action.bound_targets = True
    baseline.observations["actor"].enable_corruption = False
    assert not load_env_cfg(baseline_id, play=play).actions["joint_pos"].bound_targets
    assert load_env_cfg(original_id, play=play).observations["actor"].enable_corruption


@pytest.mark.parametrize("task", ["SitStand", "VelStand"])
def test_unbounded_rl_configuration_is_independent_and_has_separate_log_names(task):
    original_id = f"HtDuck-Flat-{task}"
    baseline_id = original_id + "-Unbounded"
    original = load_rl_cfg(original_id)
    baseline = load_rl_cfg(baseline_id)
    assert baseline.experiment_name == original.experiment_name + "_unbounded"
    assert baseline.run_name == original.run_name + "_unbounded"
    original_values, baseline_values = asdict(original), asdict(baseline)
    for key in ("experiment_name", "run_name"):
        original_values.pop(key)
        baseline_values.pop(key)
    assert baseline_values == original_values
    baseline.actor.hidden_dims = (1,)
    baseline.actor.distribution_cfg["init_std"] = 0.05
    baseline.algorithm.learning_rate = 12.0
    for task_id in (original_id, baseline_id):
        fresh = load_rl_cfg(task_id)
        assert fresh.actor.hidden_dims == (512, 256, 128)
        assert fresh.actor.distribution_cfg["init_std"] == 1.0
        assert fresh.algorithm.learning_rate == 0.001


# ---------- 饱和指标与逐环境生命周期 ----------


def _force_env():
    """选区顺序、实体执行器顺序与仿真全局控制索引互不相同。"""
    robot = SimpleNamespace(
        actuator_names=["selected_a", "unselected", "selected_b"],
        num_actuators=3,
        indexing=SimpleNamespace(ctrl_ids=torch.tensor([5, 2, 4])),
        data=SimpleNamespace(actuator_force=torch.tensor([[2.9, 999.0, -1.8], [-0.24, 999.0, 0.4]])),
    )

    def find_actuators(names, preserve_order=False):
        assert preserve_order
        return [robot.actuator_names.index(name) for name in names], list(names)

    robot.find_actuators = find_actuators
    ranges = torch.tensor([-1.0, 1.0]).repeat(2, 7, 1)
    ranges[0, 4] = torch.tensor([-2.0, 1.0])
    ranges[0, 5] = torch.tensor([-1.0, 3.0])
    ranges[1, 4] = torch.tensor([-0.5, 4.0])
    ranges[1, 5] = torch.tensor([-5.0, 0.25])
    env = SimpleNamespace(
        num_envs=2, device="cpu", step_dt=0.02, scene={"robot": robot},
        sim=SimpleNamespace(model=SimpleNamespace(actuator_forcerange=ranges)),
    )
    asset = SceneEntityCfg("robot", actuator_ids=[2, 0], preserve_order=True)
    return env, robot, asset


def test_saturation_uses_selected_actuators_and_directional_global_ranges():
    env, robot, asset = _force_env()
    torch.testing.assert_close(actuator_saturation_fraction(env, asset), torch.tensor([0.5, 0.0]))
    robot.data.actuator_force[1, [0, 2]] = torch.tensor([0.24, -0.48])
    torch.testing.assert_close(actuator_saturation_fraction(env, asset), torch.tensor([0.5, 1.0]))


def test_saturation_reloads_replaced_bridge_and_ignores_zero_capacity():
    env, robot, asset = _force_env()
    first = actuator_saturation_fraction(env, asset)
    replacement = env.sim.model.actuator_forcerange.clone()
    replacement[:, [4, 5]] *= 100
    env.sim.model.actuator_forcerange = replacement
    torch.testing.assert_close(actuator_saturation_fraction(env, asset), torch.zeros(2))
    assert first[0] > 0
    replacement[:, [4, 5]] = 0
    robot.data.actuator_force[:, [0, 2]] = 0
    assert torch.equal(actuator_saturation_fraction(env, asset), torch.zeros(2))


def test_saturation_threshold_includes_its_exact_boundary():
    env, robot, asset = _force_env()
    env.sim.model.actuator_forcerange[:, [4, 5]] = torch.tensor([-2.0, 2.0])
    robot.data.actuator_force[:, [0, 2]] = torch.tensor([[1.9, -1.9], [1.899, -1.899]])
    torch.testing.assert_close(actuator_saturation_fraction(env, asset), torch.tensor([1.0, 0.0]))


def test_saturation_duration_tracks_each_actuator_and_resets_only_selected_worlds():
    env, robot, asset = _force_env()
    env.sim.model.actuator_forcerange[:, [4, 5]] = torch.tensor([-2.0, 2.0])
    robot.data.actuator_force[:, [0, 2]] = torch.tensor([[2.0, -2.0], [0.0, 0.0]])
    cfg = MetricsTermCfg(func=ActuatorSaturationDuration, params={"asset_cfg": asset})
    duration = ActuatorSaturationDuration(cfg, env)
    with torch.inference_mode():
        torch.testing.assert_close(duration(env, asset), torch.tensor([0.02, 0.0]))
        torch.testing.assert_close(duration(env, asset), torch.tensor([0.04, 0.0]))
        robot.data.actuator_force[:, 0] = torch.tensor([0.0, 2.0])
        torch.testing.assert_close(duration(env, asset), torch.tensor([0.06, 0.02]))
    duration.reset(torch.tensor([0]))
    robot.data.actuator_force[:, 0] = 2.0
    torch.testing.assert_close(duration(env, asset), torch.tensor([0.02, 0.04]))
    duration.reset()
    torch.testing.assert_close(duration(env, asset), torch.tensor([0.02, 0.02]))


def test_metrics_manager_reports_episode_maximum_and_preserves_neighbours():
    env, robot, asset = _force_env()
    env.sim.model.actuator_forcerange[:, [4, 5]] = torch.tensor([-2.0, 2.0])
    robot.data.actuator_force[:, [0, 2]] = torch.tensor([2.0, -2.0])
    manager = MetricsManager({
        "saturation_duration": MetricsTermCfg(
            func=ActuatorSaturationDuration, params={"asset_cfg": asset}, reduce="max"
        )
    }, env)
    manager.compute()
    manager.compute()
    first = manager.reset(torch.tensor([0]))
    torch.testing.assert_close(first["Episode_Metrics/saturation_duration"], torch.tensor(0.04))
    manager.compute()
    second = manager.reset(torch.tensor([1]))
    torch.testing.assert_close(second["Episode_Metrics/saturation_duration"], torch.tensor(0.06))
