# Copyright (c) 2026-2027 zh
"""前坐任务的关节方向、姿态目标一致性和独立注册回归测试。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest
import torch
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

from ht_microduck.robot.ht_microduck_constants import (
    HOME_JOINT_POS,
    get_robot_spec,
)
from ht_microduck.tasks import _assert_task_contract
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_env_cfg import make_sitstand_env_cfg
from ht_microduck.tasks.config.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
    make_sitstand_forward_env_cfg,
)
from ht_microduck.tasks.mdp import forward_posture
from ht_microduck.tasks.rl.runner import OfficialTaskOnPolicyRunner

TASK = "HtDuck-Flat-SitStand-Forward"


def test_forward_seat_places_both_feet_in_front_within_real_joint_limits():
    model = get_robot_spec().compile()
    data = mujoco.MjData(model)
    assert set(FORWARD_SITTING_JOINT_POS) <= set(C.LEG_JOINT_NAMES)
    for name, value in {**HOME_JOINT_POS, **FORWARD_SITTING_JOINT_POS}.items():
        joint = model.joint(name)
        assert joint.range[0] <= value <= joint.range[1], name
        data.joint(name).qpos[0] = value
    mujoco.mj_forward(model, data)
    body = data.body("base_link")
    feet_b = np.stack([
        (data.site(name).xpos - body.xpos) @ body.xmat.reshape(3, 3)
        for name in ("r_foot", "l_foot")
    ])
    assert np.all(feet_b[:, 0] > 0.015), feet_b
    assert 0.0 < FORWARD_SIT_Z < C.STAND_Z - 0.015


@pytest.mark.parametrize("play", [False, True])
def test_forward_reset_and_pose_rewards_share_the_new_seated_target(play):
    cfg = make_sitstand_forward_env_cfg(num_envs=2, seed=17, play=play)
    expected = {
        C.POLICY_JOINT_NAMES.index(name): angle
        for name, angle in FORWARD_SITTING_JOINT_POS.items()
    }
    reset = cfg.events["set_ground_state"].params
    assert reset["sitting_joint_overrides"] == expected
    for name in ("posture_pose_legs", "posture_composite"):
        assert cfg.rewards[name].params["sit_overrides"] == expected, name
    assert cfg.scene.num_envs == 2 and cfg.seed == 17


@pytest.mark.parametrize("play", [False, True])
def test_forward_seated_height_reaches_every_dependent_configuration(play):
    cfg = make_sitstand_forward_env_cfg(num_envs=1, play=play)
    command = cfg.commands["twist"]
    assert command.sit_z == FORWARD_SIT_Z
    assert command.stand_z == C.STAND_Z
    for name in (
        "posture_height", "posture_stillness", "posture_composite",
    ):
        assert cfg.rewards[name].params["sit_z"] == FORWARD_SIT_Z, name
        assert cfg.rewards[name].params["stand_z"] == C.STAND_Z, name
    reset = cfg.events["set_ground_state"].params
    assert reset["sitting_z_min"] == pytest.approx(FORWARD_SIT_Z)
    assert reset["sitting_z_max"] == pytest.approx(FORWARD_SIT_Z + 0.015)
    upright = cfg.rewards["upright_while_tall"].params
    for key, official_height in (("height_low", 0.075), ("height_high", 0.100)):
        fraction = (upright[key] - FORWARD_SIT_Z) / (C.STAND_Z - FORWARD_SIT_Z)
        assert fraction == pytest.approx((official_height - 0.060) / 0.055)
    assert cfg.rewards["rise_bootstrap"].params["max_height"] == pytest.approx(C.STAND_Z + 0.01)


@pytest.mark.parametrize("play", [False, True])
def test_forward_base_recipe_keeps_policy_interface_without_hardening_curricula(play):
    cfg = make_sitstand_forward_env_cfg(num_envs=1, seed=0, play=play)
    baseline = make_sitstand_env_cfg(num_envs=1, seed=0, play=play)
    assert cfg.commands["twist"].ramp_s == 2.0
    assert cfg.commands["twist"].sit_prob == 0.5
    assert cfg.commands["twist"].resampling_time_range == (3.5, 6.5)
    assert asdict(cfg.commands["head_pose"]) == asdict(baseline.commands["head_pose"])
    assert not cfg.curriculum
    assert all(term.mode != "interval" for term in cfg.events.values())
    assert cfg.events["set_ground_state"].func is forward_posture.bounded_forward_ground_state
    assert cfg.events["set_ground_state"].params["sitting_joint_noise_std"] == 0.02
    assert cfg.rewards["posture_pose_legs"].func is forward_posture.forward_pose_match
    assert cfg.rewards["posture_height"].func is forward_posture.forward_height_match
    limit_costs = [term for term in cfg.rewards.values() if term.func is forward_posture.forward_action_limit_error]
    assert len(limit_costs) == 1 and limit_costs[0].weight == -2.0
    assert tuple(cfg.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS
    assert cfg.actions["joint_pos"].bound_targets
    assert cfg.actions["joint_pos"].scale == 1.0
    assert cfg.sim.mujoco.timestep * cfg.decimation == 0.02


def test_forward_factory_does_not_mutate_legacy_pose_or_other_instances():
    legacy_pose = deepcopy(C.LOW_POSTURE_JOINT_POS)
    forward_pose = deepcopy(FORWARD_SITTING_JOINT_POS)
    baseline = make_sitstand_env_cfg(num_envs=1)
    before = repr(asdict(baseline))
    first = make_sitstand_forward_env_cfg(num_envs=1)
    key = next(iter(first.rewards["posture_pose_legs"].params["sit_overrides"]))
    first.rewards["posture_pose_legs"].params["sit_overrides"][key] = 99.0
    first.events["set_ground_state"].params["sitting_z_min"] = 99.0
    first.commands["head_pose"].ranges = ((99.0, 99.0),) * 4
    fresh = make_sitstand_forward_env_cfg(num_envs=1, play=True)
    assert fresh.rewards["posture_pose_legs"].params["sit_overrides"][key] != 99.0
    assert fresh.events["set_ground_state"].params["sitting_z_min"] == pytest.approx(FORWARD_SIT_Z)
    assert FORWARD_SITTING_JOINT_POS == forward_pose
    assert C.LOW_POSTURE_JOINT_POS == legacy_pose
    assert repr(asdict(baseline)) == before
    legacy = make_sitstand_env_cfg(num_envs=1)
    assert legacy.commands["twist"].sit_z == C.SIT_Z
    assert legacy.events["set_ground_state"].params["sitting_joint_overrides"] == {
        C.POLICY_JOINT_NAMES.index(name): angle for name, angle in legacy_pose.items()
    }


@pytest.mark.parametrize("play", [False, True])
def test_forward_registration_keeps_tensor_contract_and_independent_training(play):
    cfg = load_env_cfg(TASK, play=play)
    _assert_task_contract(TASK, cfg)
    assert C.TASK_CRITIC_OBSERVATION_DIMS[TASK] == 74
    assert C.ACTOR_OBSERVATION_DIM == 61 and C.ACTION_DIM == 14
    agent = load_rl_cfg(TASK)
    assert agent.experiment_name == "flat_sitstand_forward"
    assert agent.run_name == "sitstand_forward_base_v3"
    assert load_runner_cls(TASK) is OfficialTaskOnPolicyRunner
    baseline = load_rl_cfg("HtDuck-Flat-SitStand")
    for field in ("actor", "critic", "algorithm"):
        assert asdict(getattr(agent, field)) == asdict(getattr(baseline, field))
    assert agent.num_steps_per_env == baseline.num_steps_per_env == 24
    agent.algorithm.learning_rate = 99.0
    assert load_rl_cfg(TASK).algorithm.learning_rate == baseline.algorithm.learning_rate
    assert load_rl_cfg("HtDuck-Flat-SitStand").experiment_name == "flat_sitstand"


@pytest.mark.parametrize("task_id", [
    "HtDuck-Flat-Velocity", "HtDuck-Flat-Velocity-Head", "HtDuck-Flat-StandUp",
    "HtDuck-Flat-SitStand", "HtDuck-Flat-VelStand",
    "HtDuck-Flat-SitStand-Unbounded", "HtDuck-Flat-VelStand-Unbounded",
])
def test_forward_registration_preserves_all_original_tasks(task_id):
    _assert_task_contract(task_id, load_env_cfg(task_id))
    load_rl_cfg(task_id)
    for cfg in (load_env_cfg(task_id), load_env_cfg(task_id, play=True)):
        assert "forward_action_limit_error" not in cfg.rewards
        assert all(term.func is not forward_posture.forward_action_limit_error for term in cfg.rewards.values())
    before = repr((asdict(load_env_cfg(task_id)), asdict(load_env_cfg(task_id, play=True)), asdict(load_rl_cfg(task_id))))
    forward = make_sitstand_forward_env_cfg(num_envs=2, seed=7)
    forward.commands["twist"].sit_z = 99.0
    forward.actions["joint_pos"].scale = 99.0
    forward.events["set_ground_state"].params["sitting_prob"] = 0.0
    assert repr((asdict(load_env_cfg(task_id)), asdict(load_env_cfg(task_id, play=True)), asdict(load_rl_cfg(task_id)))) == before


class _Scene(dict):
    """只提供被测MDP实际消费的场景数据。"""


def _reward_env(num_envs=1):
    """构造有命名关节和世界坐标足点的CPU状态，不复刻奖励计算。"""
    home = torch.tensor([[HOME_JOINT_POS[name] for name in C.POLICY_JOINT_NAMES]], dtype=torch.float32).repeat(num_envs, 1)
    seat = home.clone()
    for name, angle in FORWARD_SITTING_JOINT_POS.items():
        seat[:, C.POLICY_JOINT_NAMES.index(name)] = angle
    root = torch.zeros(num_envs, 3)
    root[:, 2] = FORWARD_SIT_Z
    quat = torch.zeros(num_envs, 4)
    quat[:, 0] = 1.0
    sites = root[:, None, :] + torch.tensor([[[0.1, -0.04, -0.04], [0.1, 0.04, -0.04]]])
    robot = SimpleNamespace(
        data=SimpleNamespace(
            default_joint_pos=home, joint_pos=seat.clone(), root_link_pos_w=root, root_link_quat_w=quat,
            root_link_lin_vel_w=torch.zeros(num_envs, 3), site_pos_w=sites,
        ),
        find_joints=lambda names, preserve_order: (list(range(C.ACTION_DIM)), list(C.POLICY_JOINT_NAMES)),
        find_sites=lambda names, preserve_order: ([0, 1], ["r_foot", "l_foot"]),
    )
    scene = _Scene(robot=robot)
    scene.env_origins = torch.zeros(num_envs, 3)
    scene.terrain = SimpleNamespace(env_origins=scene.env_origins)
    command = torch.zeros(num_envs, 3)
    command[:, 0] = 1.0
    term = SimpleNamespace(alpha=torch.ones(num_envs))
    env = SimpleNamespace(
        scene=scene, num_envs=num_envs, device="cpu",
        command_manager=SimpleNamespace(get_command=lambda name: command, get_term=lambda name: term),
    )
    overrides = {C.POLICY_JOINT_NAMES.index(name): angle for name, angle in FORWARD_SITTING_JOINT_POS.items()}
    return env, robot, command, term, overrides


@pytest.mark.parametrize("sit", [False, True])
def test_forward_endpoint_rewards_follow_flag_instead_of_intermediate_alpha(sit):
    env, robot, command, term, overrides = _reward_env()
    command[:, 0] = float(sit)
    if not sit:
        robot.data.joint_pos[:] = robot.data.default_joint_pos
        robot.data.root_link_pos_w[:, 2] = C.STAND_Z
    args = dict(command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10)))
    term.alpha.zero_()
    initial = forward_posture.forward_pose_match(env, **args)
    initial_height = forward_posture.forward_height_match(
        env, command_name="twist", sit_overrides=overrides, sit_z=FORWARD_SIT_Z, stand_z=C.STAND_Z, std=0.015
    )
    term.alpha.fill_(1.0)
    torch.testing.assert_close(forward_posture.forward_pose_match(env, **args), initial)
    torch.testing.assert_close(initial, torch.ones(1))
    torch.testing.assert_close(
        forward_posture.forward_height_match(
            env, command_name="twist", sit_overrides=overrides, sit_z=FORWARD_SIT_Z, stand_z=C.STAND_Z, std=0.015
        ), initial_height
    )
    assert initial_height.item() > 0.99


def test_forward_pose_reward_distinguishes_movement_toward_goal():
    env, robot, _, _, overrides = _reward_env(4)
    robot.data.joint_pos[:] = robot.data.default_joint_pos
    for name in ("r_hip_pitch_joint", "l_hip_pitch_joint"):
        index = C.POLICY_JOINT_NAMES.index(name)
        start = robot.data.default_joint_pos[:, index]
        delta = FORWARD_SITTING_JOINT_POS[name] - start
        robot.data.joint_pos[:, index] = start + torch.tensor([-0.1, 0.0, 0.1, 0.2]) * delta
    score = forward_posture.forward_pose_match(
        env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10))
    )
    assert torch.all(score[1:] > score[:-1])


@pytest.mark.parametrize("knee_name", ["r_calf_joint", "l_calf_joint"])
def test_forward_one_incorrect_knee_cannot_hide_among_nine_correct_joints(knee_name):
    env, robot, _, _, overrides = _reward_env(4)
    knee = C.POLICY_JOINT_NAMES.index(knee_name)
    robot.data.joint_pos[1, knee] += 1.6
    robot.data.joint_pos[2, knee] += 0.8
    robot.data.joint_pos[3, (3, 8)] += 1.6
    score = forward_posture.forward_pose_match(
        env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10))
    )
    # 一侧膝方向严重错误也须损失过半姿态分；另一侧正确不能稀释该错误。
    assert score[0] > score[2] > score[1] > score[3] > 0
    assert score[1] < 0.5 * score[0]


def test_forward_pose_reward_still_improves_when_a_non_worst_joint_approaches_goal():
    env, robot, _, _, overrides = _reward_env(2)
    robot.data.joint_pos[:] = robot.data.default_joint_pos
    # HOME中髋误差最大；先改善膝也必须有信号，不能只优化当前最差关节。
    for name in ("r_calf_joint", "l_calf_joint"):
        robot.data.joint_pos[1, C.POLICY_JOINT_NAMES.index(name)] = FORWARD_SITTING_JOINT_POS[name]
    score = forward_posture.forward_pose_match(
        env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10))
    )
    assert score[1] > score[0] > 0


def test_forward_foot_geometry_uses_body_coordinates_after_rotation_and_translation():
    env, robot, _, _, _ = _reward_env()
    reference = forward_posture._feet_forward_x(env).clone()
    robot.data.root_link_pos_w[:] = torch.tensor([[3.0, -2.0, FORWARD_SIT_Z]])
    angle = torch.tensor(np.pi / 4)
    robot.data.root_link_quat_w[:] = torch.tensor([[torch.cos(angle), 0.0, 0.0, torch.sin(angle)]])
    # 整个场景绕Z旋转90度并平移，脚在机体系中的相对位置不变。
    robot.data.site_pos_w[:] = robot.data.root_link_pos_w[:, None, :] + torch.tensor([[[0.04, 0.1, -0.04], [-0.04, 0.1, -0.04]]])
    torch.testing.assert_close(forward_posture._feet_forward_x(env), reference)
    robot.data.root_link_quat_w[:] = torch.tensor([[1.0, 0.0, 0.0, 0.0]])
    robot.data.site_pos_w[:] = robot.data.root_link_pos_w[:, None, :] + torch.tensor([[[-0.02, -0.04, -0.04], [0.22, 0.04, -0.04]]])
    feet = forward_posture._feet_forward_x(env)
    assert feet[0, 0] < 0 < feet[0, 1]


@pytest.mark.parametrize("sit", [False, True])
def test_forward_height_reward_distinguishes_faraway_heights_and_matches_endpoint(sit):
    cfg = make_sitstand_forward_env_cfg(num_envs=5)
    env, robot, command, _, _ = _reward_env(5)
    command[:, 0] = float(sit)
    target = FORWARD_SIT_Z if sit else C.STAND_Z
    if not sit:
        robot.data.joint_pos[:] = robot.data.default_joint_pos
    distance = C.STAND_Z - FORWARD_SIT_Z
    offsets = torch.tensor([2.0, 1.5, 1.0, 0.5, 0.0]) * distance
    robot.data.root_link_pos_w[:, 2] = target + offsets
    term = cfg.rewards["posture_height"]
    score = term.func(env, **term.params)
    assert torch.isfinite(score).all() and torch.all(score > 0)
    assert torch.all(score[1:] > score[:-1])
    assert score[0] > 0.1 * score[-1]
    torch.testing.assert_close(score[-1], torch.tensor(1.0))


def test_forward_sitting_height_reward_opens_with_actual_hip_progress():
    cfg = make_sitstand_forward_env_cfg(num_envs=3)
    env, robot, _, _, _ = _reward_env(3)
    for name in ("r_hip_pitch_joint", "l_hip_pitch_joint"):
        slot = C.POLICY_JOINT_NAMES.index(name)
        home = robot.data.default_joint_pos[:, slot]
        robot.data.joint_pos[:, slot] = home + torch.tensor([0.0, 0.5, 1.0]) * (FORWARD_SITTING_JOINT_POS[name] - home)
    term = cfg.rewards["posture_height"]
    score = term.func(env, **term.params)
    torch.testing.assert_close(score[0], torch.tensor(0.0))
    assert 0 < score[1] < score[2]


def test_forward_sit_success_requires_all_geometry_pose_and_command_conditions():
    env, robot, command, term, overrides = _reward_env(7)
    robot.data.site_pos_w[1, 0, 0] = -0.04
    robot.data.root_link_pos_w[2, 2] = C.STAND_Z
    angle = torch.tensor(np.deg2rad(30.0) / 2)
    robot.data.root_link_quat_w[3] = torch.tensor([torch.cos(angle), torch.sin(angle), 0.0, 0.0])
    robot.data.joint_pos[4, C.POLICY_JOINT_NAMES.index("r_hip_pitch_joint")] += 0.6
    term.alpha[5] = 0.5
    command[6, 0] = 0.0
    success = forward_posture.forward_sit_success_frames(env, sit_overrides=overrides, sit_z=FORWARD_SIT_Z)
    torch.testing.assert_close(success, torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))


def test_forward_command_frame_denominator_excludes_transition_and_stand_frames():
    env, _, command, term, _ = _reward_env(4)
    command[:, 0] = torch.tensor([1.0, 1.0, 0.0, 0.0])
    term.alpha[:] = torch.tensor([1.0, 0.5, 1.0, 0.5])
    torch.testing.assert_close(forward_posture.forward_sit_command_frames(env), torch.tensor([1.0, 0.0, 0.0, 0.0]))


@pytest.mark.parametrize("reward_name", ["composite", "stillness"])
def test_forward_rest_rewards_reject_incomplete_ramp_and_one_incorrect_hip(reward_name):
    env, robot, _, term, overrides = _reward_env()
    common = dict(command_name="twist", sit_overrides=overrides, sit_z=FORWARD_SIT_Z, stand_z=C.STAND_Z)
    if reward_name == "composite":
        reward = forward_posture.forward_composite
        params = {**common, "joint_indices": tuple(range(10)), "height_std": 0.03, "upright_std": 0.4, "pose_std": 0.4}
    else:
        reward = forward_posture.forward_stillness
        params = {**common, "band_full": 0.012, "band_zero": 0.03, "vel_std": 0.05, "tilt_full_deg": 25.0, "tilt_zero_deg": 60.0}
    assert reward(env, **params).item() > 0.99
    term.alpha[:] = 0.5
    torch.testing.assert_close(reward(env, **params), torch.zeros(1))
    term.alpha[:] = 1.0
    robot.data.joint_pos[:, C.POLICY_JOINT_NAMES.index("r_hip_pitch_joint")] += 0.6
    torch.testing.assert_close(reward(env, **params), torch.zeros(1))


@pytest.mark.parametrize("env_id", [0, 1])
def test_forward_reset_clips_with_margin_without_changing_neighbor(monkeypatch, env_id):
    env, robot, _, _, _ = _reward_env(2)
    width = C.ACTION_DIM
    # 策略顺序、qpos地址与被保持的嘴均不同，避免把7+策略索引误当作物理地址。
    q_adr = torch.tensor([11, 7, 18, 9, 15, 8, 17, 10, 20, 12, 16, 14, 13, 19, 21])
    robot.indexing = SimpleNamespace(joint_q_adr=q_adr)
    limits = torch.empty(2, width + 1, 2)
    limits[..., 0] = -0.75
    limits[..., 1] = 0.75
    limits[:, 0, :] = torch.tensor([-1.0, 1.0])
    limits[:, 1, :] = torch.tensor([-0.5, 0.5])
    robot.data.joint_pos_limits = limits
    qpos = torch.zeros(2, 8 + width)
    qpos[env_id, -1] = 0.4
    neighbor_id = 1 - env_id
    qpos[neighbor_id] = 0.123
    env.sim = SimpleNamespace(data=SimpleNamespace(qpos=qpos))
    calls = []

    def sample(current_env, env_ids, **params):
        calls.append((env_ids.clone(), params))
        current_env.sim.data.qpos[env_ids, q_adr[0]] = -2.0
        current_env.sim.data.qpos[env_ids, q_adr[1]] = 2.0

    monkeypatch.setattr(forward_posture, "set_random_ground_state", sample)
    neighbor = qpos[neighbor_id].clone()
    forward_posture.bounded_forward_ground_state(env, torch.tensor([env_id]), sitting_prob=1.0)
    assert len(calls) == 1 and calls[0][1]["sitting_prob"] == 1.0
    torch.testing.assert_close(calls[0][0], torch.tensor([env_id]))
    assert qpos[env_id, q_adr[0]] == pytest.approx(-0.995)
    assert qpos[env_id, q_adr[1]] == pytest.approx(0.495)
    assert qpos[env_id, -1] == pytest.approx(0.4)
    assert torch.equal(qpos[neighbor_id], neighbor)
    assert torch.equal(qpos[env_id, :7], torch.zeros(7))


def test_forward_request_limit_cost_is_zero_inside_and_at_exact_physical_bounds():
    from test_bounded_actions import _action_env

    env, robot, term = _action_env(get_robot_spec().compile(), count=3, use_default_offset=False)
    limits = robot.data.joint_pos_limits[:, term.target_ids]
    targets = torch.stack((torch.zeros(C.ACTION_DIM), limits[1, :, 0], limits[2, :, 1]))
    term.process_actions(targets)
    term.apply_actions()
    torch.testing.assert_close(forward_posture.forward_action_limit_error(env), torch.zeros(3))


@pytest.mark.parametrize("bound_targets", [False, True])
def test_forward_request_limit_cost_reads_mapped_limits_and_preserves_all_state(bound_targets):
    from test_bounded_actions import _action_env

    env, robot, term = _action_env(get_robot_spec().compile(), count=3, use_default_offset=False, bound_targets=bound_targets)
    assert tuple(term.target_ids) != tuple(range(C.ACTION_DIM))
    limits = robot.data.joint_pos_limits[:, term.target_ids]
    targets = torch.zeros(3, C.ACTION_DIM)
    targets[0, 0] = limits[0, 0, 1] + 0.28
    targets[0, 1] = limits[0, 1, 0] - 0.14
    targets[1, 2] = limits[1, 2, 0] - 0.42
    term.process_actions(targets)
    term.apply_actions()
    tensors = (
        term.raw_action, term.requested_targets, term.applied_targets,
        robot.data.joint_pos_limits, robot.data.joint_pos_target, robot.data.encoder_bias,
    )
    before = tuple(value.clone() for value in tensors)
    score = forward_posture.forward_action_limit_error(env)
    # 单位为rad，按14个策略关节取平均；未越界的第三个环境不得受到其他环境影响。
    torch.testing.assert_close(score, torch.tensor([0.42 / C.ACTION_DIM, 0.42 / C.ACTION_DIM, 0.0]))
    for value, original in zip(tensors, before, strict=True):
        assert torch.equal(value, original)
    if not bound_targets:
        assert torch.equal(term.requested_targets, term.applied_targets)
        assert score[0] > 0


def test_forward_request_limit_cost_uses_post_encoder_bias_targets_instead_of_raw_action():
    from test_bounded_actions import _action_env

    env, robot, term = _action_env(get_robot_spec().compile(), count=3)
    slot = C.POLICY_JOINT_NAMES.index("r_hip_yaw_joint")
    physical_id = term.target_ids[slot]
    upper = robot.data.joint_pos_limits[0, physical_id, 1]
    actions = torch.zeros(3, C.ACTION_DIM)
    actions[0, slot] = upper + 0.03
    actions[1, slot] = upper - 0.02
    robot.data.encoder_bias[:, physical_id] = torch.tensor([0.05, -0.05, 0.0])
    term.process_actions(actions)
    term.apply_actions()
    torch.testing.assert_close(term.requested_targets[:, slot], torch.stack((upper - 0.02, upper + 0.03, torch.tensor(0.0))))
    torch.testing.assert_close(forward_posture.forward_action_limit_error(env), torch.tensor([0.0, 0.03 / C.ACTION_DIM, 0.0]))


def _apply_fk_states(robot, cases):
    """用真实MuJoCo模型更新测试状态的世界位姿与足端，返回机体系足点。"""
    model = get_robot_spec().compile()
    data = mujoco.MjData(model)
    feet_b = []
    for index, (position, quaternion) in enumerate(cases):
        data.qpos[:] = model.qpos0
        data.qpos[:3] = position
        data.qpos[3:7] = quaternion
        for slot, name in enumerate(C.POLICY_JOINT_NAMES):
            data.joint(name).qpos[0] = float(robot.data.joint_pos[index, slot])
        mujoco.mj_forward(model, data)
        robot.data.root_link_pos_w[index] = torch.tensor(data.body("base_link").xpos.copy(), dtype=torch.float32)
        robot.data.root_link_quat_w[index] = torch.tensor(data.body("base_link").xquat.copy(), dtype=torch.float32)
        robot.data.site_pos_w[index] = torch.tensor(
            np.stack([data.site(name).xpos.copy() for name in ("r_foot", "l_foot")]), dtype=torch.float32
        )
        body = data.body("base_link")
        feet_b.append(np.stack([
            (data.site(name).xpos - body.xpos) @ body.xmat.reshape(3, 3)
            for name in ("r_foot", "l_foot")
        ]))
    return np.stack(feet_b)


def test_forward_static_core_rewards_prefer_front_seat_then_upright_home_over_fallen_seat():
    """用真实FK与生产奖励检查静止反例排序，不把它当作动态成功证明。"""
    fallen_angles = (60.0, 90.0, 112.0, 180.0)
    count = 2 + len(fallen_angles)
    cfg = make_sitstand_forward_env_cfg(num_envs=count)
    env, robot, _, _, overrides = _reward_env(count)
    robot.data.joint_pos[1] = robot.data.default_joint_pos[1]
    cases = [
        ((3.0, -2.0, FORWARD_SIT_Z), (1.0, 0.0, 0.0, 0.0)),
        ((-1.0, 0.5, C.STAND_Z), (1.0, 0.0, 0.0, 0.0)),
    ]
    for index, angle in enumerate(fallen_angles):
        pitch = np.deg2rad(angle)
        cases.append(((4.0 + index, 3.0, FORWARD_SIT_Z), (np.cos(pitch / 2), 0.0, np.sin(pitch / 2), 0.0)))
    feet_b = _apply_fk_states(robot, cases)
    # 腿形相同的倒地样例随躯干真实旋转；HOME也必须使用自己的FK脚位置。
    np.testing.assert_allclose(feet_b[2:], np.broadcast_to(feet_b[0], (len(fallen_angles), 2, 3)), atol=1e-7)
    torch.testing.assert_close(
        forward_posture.forward_sit_success_frames(env, sit_overrides=overrides, sit_z=FORWARD_SIT_Z),
        torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    )
    core = ("posture_pose_legs", "posture_height", "upright_linear")
    scores = torch.stack([
        cfg.rewards[name].func(env, **cfg.rewards[name].params) * cfg.rewards[name].weight
        for name in core
    ]).sum(dim=0)
    print(f"Static core reward totals (front seat, HOME, fallen {fallen_angles}): {scores.tolist()}")
    print(f"Actual HOME body-frame foot X: {feet_b[1, :, 0].tolist()}")
    correct, home = scores[:2]
    assert correct > home
    assert torch.all(home > scores[2:])


def test_forward_v2_high_body_counterexample_improves_with_knee_and_height_correction():
    """用第二版实测关节/根高和真实FK比较局部修正，不声称这些静态样例是可行过渡。"""
    count = 4
    cfg = make_sitstand_forward_env_cfg(num_envs=count)
    env, robot, _, _, overrides = _reward_env(count)
    # 第二版model_29999，8环境14–16秒均值；水平躯干给予高位反例最大的直立分。
    measured = torch.tensor([
        -0.1486, 0.3677, -1.5703, 1.2777, 0.0650,
        0.1697, -0.3659, -1.5696, 1.2746, 0.0590,
        1.3008, 0.1184, 0.0166, 0.0258,
    ])
    robot.data.joint_pos[1:] = measured
    for name in ("r_calf_joint", "l_calf_joint"):
        slot = C.POLICY_JOINT_NAMES.index(name)
        robot.data.joint_pos[2:, slot] = 0.5 * (measured[slot] + FORWARD_SITTING_JOINT_POS[name])
    high_z = 0.14987
    cases = [
        ((0.0, 0.0, FORWARD_SIT_Z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, high_z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, high_z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.5 * (high_z + FORWARD_SIT_Z)), (1.0, 0.0, 0.0, 0.0)),
    ]
    feet_b = _apply_fk_states(robot, cases)
    assert np.all(feet_b[1, :, 0] > 0.015)
    success = forward_posture.forward_sit_success_frames(env, sit_overrides=overrides, sit_z=FORWARD_SIT_Z)
    torch.testing.assert_close(success, torch.tensor([1.0, 0.0, 0.0, 0.0]))
    scores = torch.stack([
        cfg.rewards[name].func(env, **cfg.rewards[name].params) * cfg.rewards[name].weight
        for name in ("posture_pose_legs", "posture_height", "upright_linear")
    ]).sum(dim=0)
    assert scores[0] > scores[3] > scores[2] > scores[1]


@pytest.mark.parametrize("reward_name", ["pose", "height"])
def test_forward_positive_rewards_have_continuous_upright_gate_boundaries(reward_name):
    angles = (0.0, 15.0, 30.0, 45.0, 60.0, 90.0)
    env, robot, _, _, overrides = _reward_env(len(angles))
    cases = []
    for angle in angles:
        half_pitch = np.deg2rad(angle) / 2
        cases.append(((0.0, 0.0, FORWARD_SIT_Z), (np.cos(half_pitch), 0.0, np.sin(half_pitch), 0.0)))
    _apply_fk_states(robot, cases)
    if reward_name == "pose":
        score = forward_posture.forward_pose_match(env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10)))
    else:
        score = forward_posture.forward_height_match(env, command_name="twist", sit_overrides=overrides, sit_z=FORWARD_SIT_Z, stand_z=C.STAND_Z, std=0.015)
    assert score[0] > 0
    torch.testing.assert_close(score[0], score[1])
    assert score[1] > score[2] > score[3] > 0
    torch.testing.assert_close(score[4:], torch.zeros(2), rtol=0, atol=1e-6)


def test_forward_rewards_and_success_reject_real_legacy_rear_seat():
    env, robot, _, _, overrides = _reward_env(3)
    for name, value in C.LOW_POSTURE_JOINT_POS.items():
        robot.data.joint_pos[1:, C.POLICY_JOINT_NAMES.index(name)] = value
    feet_b = _apply_fk_states(robot, [
        ((0.0, 0.0, FORWARD_SIT_Z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, FORWARD_SIT_Z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, FORWARD_SIT_Z), (np.sqrt(0.5), 0.0, np.sqrt(0.5), 0.0)),
    ])
    assert np.all(feet_b[0, :, 0] > 0) and np.all(feet_b[1:, :, 0] < 0)
    pose = forward_posture.forward_pose_match(env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10)))
    assert pose[0] > pose[1] > 0
    torch.testing.assert_close(pose[2], torch.tensor(0.0), rtol=0, atol=1e-6)
    torch.testing.assert_close(
        forward_posture.forward_sit_success_frames(env, sit_overrides=overrides, sit_z=FORWARD_SIT_Z),
        torch.tensor([1.0, 0.0, 0.0]),
    )


@pytest.mark.parametrize("reward_name", ["pose", "height"])
def test_forward_standing_positive_rewards_also_reject_fallen_orientation(reward_name):
    env, robot, command, _, overrides = _reward_env(2)
    command[:, 0] = 0
    robot.data.joint_pos[:] = robot.data.default_joint_pos
    _apply_fk_states(robot, [
        ((0.0, 0.0, C.STAND_Z), (1.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, C.STAND_Z), (np.sqrt(0.5), 0.0, np.sqrt(0.5), 0.0)),
    ])
    if reward_name == "pose":
        score = forward_posture.forward_pose_match(env, command_name="twist", sit_overrides=overrides, joint_indices=tuple(range(10)))
    else:
        score = forward_posture.forward_height_match(env, command_name="twist", sit_overrides=overrides, sit_z=FORWARD_SIT_Z, stand_z=C.STAND_Z, std=0.015)
    assert score[0] > 0.99
    torch.testing.assert_close(score[1], torch.tensor(0.0), rtol=0, atol=1e-6)
