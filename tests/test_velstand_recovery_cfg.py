# Copyright (c) 2026-2027 zh
"""检查 VelStand 官方非热启动课程、恢复窗口与 HT 身体目标接口。"""

from __future__ import annotations

import math
from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

from ht_microduck.tasks import FLAT_VELSTAND_TASK_ID, _assert_task_contract
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config import flat_velstand_env_cfg as velstand
from ht_microduck.tasks.mdp.events import reset_to_ground_state
from ht_microduck.tasks.mdp.observations import FOOT_SITE_NAMES
from ht_microduck.tasks.mdp.official_posture_rewards import (
    body_pose_tracking_locomotion,
)
from ht_microduck.tasks.mdp.posture import (
    feet_air_time_upright,
    upright_gaussian_at_height,
)
from ht_microduck.tasks.mdp.rewards import upright as original_upright


def _curriculum_environment(cfg):
    return SimpleNamespace(
        common_step_counter=0,
        event_manager=SimpleNamespace(get_term_cfg=cfg.events.__getitem__),
        reward_manager=SimpleNamespace(get_term_cfg=cfg.rewards.__getitem__),
        termination_manager=SimpleNamespace(get_term_cfg=cfg.terminations.__getitem__),
    )


def _body_environment():
    command = torch.zeros(2, 6)
    standing = torch.tensor([True, False])
    data = SimpleNamespace(
        root_link_pos_w=torch.tensor([[0.0, 0.0, C.STAND_Z]]).repeat(2, 1),
        root_link_quat_w=torch.tensor([[1.0, 0.0, 0.0, 0.0]]).repeat(2, 1),
        projected_gravity_b=torch.tensor([[0.0, 0.0, -1.0]]).repeat(2, 1),
        site_pos_w=torch.zeros(2, 2, 3),
        site_quat_w=torch.tensor([[[1.0, 0.0, 0.0, 0.0]]]).repeat(2, 2, 1),
    )

    class Scene(dict):
        env_origins = torch.zeros(2, 3)
        terrain = SimpleNamespace(env_origins=env_origins)

    env = SimpleNamespace(
        scene=Scene(robot=SimpleNamespace(data=data)),
        command_manager=SimpleNamespace(
            get_command=lambda _: command,
            get_term=lambda _: SimpleNamespace(is_standing_env=standing),
        ),
    )
    return env, data, command, standing


@pytest.mark.parametrize("play", [False, True])
def test_recovery_configuration_preserves_ht_contract_and_timing(play):
    cfg = velstand.make_velstand_env_cfg(num_envs=2, seed=7, play=play)
    _assert_task_contract(FLAT_VELSTAND_TASK_ID, cfg)
    assert cfg.sim.mujoco.timestep == 0.002
    assert cfg.decimation == 10
    assert C.ACTOR_OBSERVATION_DIM == 61
    assert C.TASK_CRITIC_OBSERVATION_DIMS[FLAT_VELSTAND_TASK_ID] == 64
    assert tuple(cfg.actions["joint_pos"].actuator_names) == C.POLICY_JOINT_NAMES
    assert len(cfg.actions["joint_pos"].actuator_names) == 14
    assert cfg.actions["joint_pos"].scale == C.ACTION_SCALE
    assert {"htdw3532_init", "bam_init"} <= cfg.events.keys()
    assert cfg.terminations["fell_over_timeout"].params == {
        "gate_z_below": C.FALLEN_Z,
        "gate_tilt_above_deg": 40.0,
        "max_duration_s": 8.0,
    }


def test_ground_curriculum_keeps_absolute_standing_remainder_at_every_boundary():
    cfg = velstand.make_velstand_env_cfg(num_envs=1)
    reset = cfg.events["reset_ground_or_stand"]
    assert reset.func is reset_to_ground_state
    assert "mixture" not in reset.params
    term = cfg.curriculum["ground_state_mix"]
    env = _curriculum_environment(cfg)
    apply = term.func(term, env)
    expected = (
        (0, 0.0, 0.0, 1.0, 1.0),
        (800, 0.0, 0.2, 1.0, 0.8),
        (1500, 0.15, 0.2, 0.8, 0.65),
        (2000, 0.30, 0.2, 0.65, 0.50),
        (2500, 0.45, 0.2, 0.50, 0.35),
    )
    previous = None
    for iteration, prone, crouch, face_down, standing in expected:
        if iteration:
            env.common_step_counter = iteration * 24 - 1
            apply(env, None, **term.params)
            assert reset.params == previous
        env.common_step_counter = iteration * 24
        snapshot = apply(env, None, **term.params)
        assert reset.params["prone_prob"] == prone
        assert reset.params["crouch_prob"] == crouch
        assert reset.params["side_prob"] == 0.5
        assert reset.params["face_down_prob"] == face_down
        assert 1.0 - prone - crouch == pytest.approx(standing)
        assert snapshot["prone_prob"].item() == pytest.approx(prone)
        previous = deepcopy(reset.params)


def test_general_fall_termination_opens_recovery_window_at_iteration_500():
    cfg = velstand.make_velstand_env_cfg(num_envs=1)
    term = cfg.curriculum["fell_over_disable"]
    env = _curriculum_environment(cfg)
    env.scene = {
        "robot": SimpleNamespace(
            data=SimpleNamespace(projected_gravity_b=torch.tensor([[0.0, 1.0, 0.0]]))
        )
    }
    apply = term.func(term, env)
    fall = cfg.terminations["fell_over"]
    for step in (0, 500 * 24 - 1):
        env.common_step_counter = step
        apply(env, None, **term.params)
        assert fall.params["limit_angle"] == pytest.approx(math.radians(70.0))
        assert fall.func(env, **fall.params).item()
    env.common_step_counter = 500 * 24
    apply(env, None, **term.params)
    assert fall.params["limit_angle"] == math.pi
    assert not fall.func(env, **fall.params).item()
    play = velstand.make_velstand_env_cfg(num_envs=1, play=True)
    assert "fell_over" not in play.terminations
    assert "fell_over_disable" not in play.curriculum
    assert "fell_over_timeout" in play.terminations


@pytest.mark.parametrize("curriculum_name,reward_name,weight", [
    ("recovery_economy", "fallen_tax", -0.5),
    ("recovery_bounty_weight", "recovery_bounty", 10.0),
    ("com_upward_weight", "com_upward_velocity", 2.0),
])
def test_recovery_rewards_start_together_at_iteration_1200(curriculum_name, reward_name, weight):
    cfg = velstand.make_velstand_env_cfg(num_envs=1)
    reward = cfg.rewards[reward_name]
    assert reward.weight == 0.0
    term = cfg.curriculum[curriculum_name]
    env = _curriculum_environment(cfg)
    apply = term.func(term, env)
    for step, expected in ((0, 0.0), (1200 * 24 - 1, 0.0), (1200 * 24, weight)):
        env.common_step_counter = step
        apply(env, None, **term.params)
        assert reward.weight == expected


def test_upward_reward_height_cutoff_covers_ht_standing_height():
    cfg = velstand.make_velstand_env_cfg(num_envs=2)
    term = cfg.rewards["com_upward_velocity"]
    cutoff = term.params["max_height"]
    assert cutoff == C.STAND_Z + 0.01
    env, data, _, _ = _body_environment()
    env.device = "cpu"
    data.projected_gravity_b[:] = torch.tensor([0.0, 1.0, 0.0])
    data.root_link_lin_vel_w = torch.tensor([[0.0, 0.0, 0.2]]).repeat(2, 1)
    data.root_link_pos_w[:, 2] = torch.tensor([C.STAND_Z, cutoff])
    assert torch.equal(term.func(env, **term.params), torch.tensor([0.2, 0.0]))


def test_body_tracking_declares_official_axes_and_ht_foot_order():
    cfg = velstand.make_velstand_env_cfg(num_envs=1)
    term = cfg.rewards["body_pose_tracking"]
    assert term.func is body_pose_tracking_locomotion
    assert term.weight == 2.0
    assert term.params["nominal_height"] == C.STAND_Z
    assert term.params["z_std"] == 0.01
    assert term.params["angle_std"] == math.radians(5.0)
    assert term.params["axis_weights"] == (0.0, 0.0, 1.0, 1.0, 1.0, 0.0)
    assert term.params["standing_gate_command_name"] == "twist"
    assert tuple(term.params["feet_cfg"].site_names) == FOOT_SITE_NAMES
    assert term.params["feet_cfg"].preserve_order
    assert {"body_pose_height", "body_pose_joints"}.isdisjoint(cfg.rewards)
    air_time = cfg.rewards["air_time"]
    assert air_time.func is feet_air_time_upright
    assert air_time.params["gate_tilt_above_deg"] == 40.0
    assert air_time.params["threshold_min"] == 0.125
    assert air_time.params["threshold_max"] == 0.300


def test_configured_body_reward_tracks_z_roll_pitch_only_while_standing():
    cfg = velstand.make_velstand_env_cfg(num_envs=2)
    term = cfg.rewards["body_pose_tracking"]
    params = dict(term.params)
    params["feet_cfg"] = SimpleNamespace(site_ids=[0, 1])
    env, data, command, standing = _body_environment()
    baseline = term.func(env, **params)
    assert torch.equal(baseline, torch.tensor([1.0, 0.0]))
    command[:, [0, 1, 5]] = torch.tensor([0.02, -0.02, 0.1])
    assert torch.equal(term.func(env, **params), baseline)
    for axis in (2, 3, 4):
        command.zero_()
        command[:, axis] = 0.01 if axis == 2 else math.radians(5.0)
        changed = term.func(env, **params)
        assert changed[0] < baseline[0]
        assert changed[1] == 0.0
        if axis == 2:
            data.root_link_pos_w[:, 2] = C.STAND_Z + 0.01
        else:
            angle = float(command[0, axis])
            data.root_link_quat_w.zero_()
            data.root_link_quat_w[:, 0] = math.cos(angle / 2)
            data.root_link_quat_w[:, axis - 2] = math.sin(angle / 2)
        assert torch.allclose(term.func(env, **params), baseline)
        data.root_link_pos_w[:, 2] = C.STAND_Z
        data.root_link_quat_w[:] = torch.tensor([1.0, 0.0, 0.0, 0.0])


def test_body_posture_stack_tracks_nonzero_tilt_without_changing_zero_command_values():
    cfg = velstand.make_velstand_env_cfg(num_envs=2)
    env, data, command, standing = _body_environment()
    standing[:] = True
    terms = {name: deepcopy(cfg.rewards[name]) for name in (
        "upright", "upright_when_tall", "body_pose_tracking",
    )}
    terms["body_pose_tracking"].params["feet_cfg"] = SimpleNamespace(site_ids=[0, 1])

    def posture_reward():
        return sum(term.weight * term.func(env, **term.params) for term in terms.values())

    for axis in (3, 4):
        command.zero_()
        command[:, axis] = 0.14
        data.root_link_quat_w[:] = torch.tensor([1.0, 0.0, 0.0, 0.0])
        data.projected_gravity_b[:] = torch.tensor([0.0, 0.0, -1.0])
        ignored = posture_reward()
        data.root_link_quat_w.zero_()
        data.root_link_quat_w[:, 0] = math.cos(0.14 / 2)
        data.root_link_quat_w[:, axis - 2] = math.sin(0.14 / 2)
        data.projected_gravity_b[:, 2] = -math.cos(0.14)
        if axis == 3:
            data.projected_gravity_b[:, 1] = -math.sin(0.14)
        else:
            data.projected_gravity_b[:, 0] = math.sin(0.14)
        assert torch.all(posture_reward() > ignored)

        # 零指令下，原直立项及本地额外角度项的每个倾角值都必须保持。
        command.zero_()
        for angle in (0.0, 0.14, 0.6):
            data.projected_gravity_b.zero_()
            data.projected_gravity_b[:, 2] = -math.cos(angle)
            data.projected_gravity_b[:, 0 if axis == 4 else 1] = (
                math.sin(angle) if axis == 4 else -math.sin(angle)
            )
            ordinary = terms["upright"]
            assert torch.equal(
                ordinary.func(env, **ordinary.params),
                original_upright(env, ordinary.params["std"], ordinary.params["asset_cfg"]),
            )
            height_term = terms["upright_when_tall"]
            original_params = height_term.params | {"command_name": None}
            assert torch.equal(
                height_term.func(env, **height_term.params),
                upright_gaussian_at_height(env, **original_params),
            )


@pytest.mark.parametrize("stages", [
    (),
    ((1, (0.0, 0.0, 0.5, 1.0)),),
    ((0, (0.0, 0.0, 0.5, 1.0)), (0, (0.0, 0.2, 0.5, 1.0))),
    ((0, (0.0, 0.0, 0.5, 1.0)), (-1, (0.0, 0.2, 0.5, 1.0))),
    ((0, (0.8, 0.3, 0.5, 1.0)),),
    ((0, (0.0, -0.2, 0.5, 1.0)),),
    ((0, (0.0, 0.0, 1.1, 1.0)),),
    ((0, (0.0, 0.0, 0.5, float("nan"))),),
    ((0, (0.0, 0.0, 0.5)),),
])
def test_configuration_rejects_invalid_ground_distribution_before_mdp(stages, monkeypatch):
    monkeypatch.setattr(velstand, "GROUND_STATE_MIX", stages)
    with pytest.raises(ValueError):
        velstand.make_velstand_env_cfg(num_envs=1)


def test_configuration_instances_do_not_share_ground_curriculum_or_selectors():
    changed = velstand.make_velstand_env_cfg(num_envs=1)
    changed.curriculum["ground_state_mix"].params["stages"][1]["params"]["prone_prob"] = 0.99
    changed.events["reset_ground_or_stand"].params["crouch_prob"] = 0.99
    changed.rewards["body_pose_tracking"].params["feet_cfg"].site_names = ("head",)
    fresh = velstand.make_velstand_env_cfg(num_envs=1)
    assert fresh.curriculum["ground_state_mix"].params["stages"][1]["params"]["prone_prob"] == 0.0
    assert fresh.events["reset_ground_or_stand"].params["crouch_prob"] == 0.0
    assert tuple(fresh.rewards["body_pose_tracking"].params["feet_cfg"].site_names) == FOOT_SITE_NAMES
