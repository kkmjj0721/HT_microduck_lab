"""Exercise official walking costs, landing history and staged head-bias weights."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch
from mjlab.managers.reward_manager import RewardManager
from mjlab.sensor.terrain_height_sensor import TerrainHeightSensor
from mjlab.tasks.velocity.mdp import feet_swing_height as MjlabFeetSwingHeight

from ht_microduck.tasks.config.ht_microduck.flat_velocity_env_cfg import (
    FOOT_HEIGHT_SENSOR,
    make_flat_velocity_env_cfg,
)
from ht_microduck.tasks.config.ht_microduck.rl_cfg import FlatVelocityRlCfg
from ht_microduck.tasks.mdp.observations import FEET_SENSOR, FOOT_SITE_NAMES, ROBOT
from ht_microduck.tasks.mdp.rewards import feet_swing_height as LegacyFeetSwingHeight


def _make_env(commands):
    command = torch.tensor(commands, dtype=torch.float32)
    num_envs = len(commands)
    heights = torch.zeros(num_envs, 2)
    height_sensor = Mock(spec=TerrainHeightSensor)
    height_sensor.num_frames = 2
    height_sensor.data = SimpleNamespace(heights=heights)
    first_contact = torch.zeros(num_envs, 2, dtype=torch.bool)
    contact = SimpleNamespace(
        data=SimpleNamespace(found=torch.zeros(num_envs, 2)),
        compute_first_contact=lambda dt: first_contact,
    )
    default = torch.tensor([[0.7, -0.35, 0.2, 0.4, -0.1, 0.1, 0.15]]).repeat(num_envs, 1)
    data = SimpleNamespace(
        site_lin_vel_w=torch.zeros(num_envs, 3, 3),
        body_link_ang_vel_w=torch.zeros(num_envs, 2, 3),
        joint_pos=default.clone(),
        default_joint_pos=default,
    )
    momentum = SimpleNamespace(data=torch.zeros(num_envs, 3))
    env = SimpleNamespace(
        scene={
            ROBOT: SimpleNamespace(data=data),
            FEET_SENSOR: contact,
            FOOT_HEIGHT_SENSOR: height_sensor,
            f"{ROBOT}/root_angmom": momentum,
        },
        command_manager=SimpleNamespace(get_command=lambda name: command),
        extras={"log": {}},
        num_envs=num_envs,
        device="cpu",
        step_dt=0.02,
        max_episode_length_s=20.0,
        common_step_counter=0,
        episode_length_buf=torch.full((num_envs,), 2),
    )
    return env, data, heights, contact, first_contact


def _configured_term(name):
    term = make_flat_velocity_env_cfg(num_envs=1, seed=0).rewards[name]
    if "asset_cfg" in term.params:
        term.params["asset_cfg"] = SimpleNamespace(
            name=ROBOT, site_ids=[2, 0], body_ids=[1], joint_ids=[1, 3, 4, 5]
        )
    return term


def test_clearance_uses_absolute_height_error_times_speed_even_during_contact():
    env, data, heights, contact, _ = _make_env([[0.2, 0.0, 0.0]])
    heights[:] = torch.tensor([0.01, 0.04])
    data.site_lin_vel_w[:, [2, 0]] = torch.tensor([[0.3, 0.4, 90.0], [0.6, 0.8, 90.0]])
    data.site_lin_vel_w[:, 1] = 100.0
    term = _configured_term("foot_clearance")
    airborne = term.func(env, **term.params)
    contact.data.found[:] = 1.0
    grounded = term.func(env, **term.params)
    assert torch.allclose(airborne, torch.tensor([0.025]))
    assert torch.equal(grounded, airborne)
    assert torch.allclose(grounded * term.weight, torch.tensor([-0.05]))
    data.site_lin_vel_w.zero_()
    assert torch.equal(term.func(env, **term.params), torch.zeros(1))


def test_slip_squares_speed_and_pairs_each_contact_with_its_selected_foot():
    env, data, _, contact, _ = _make_env([[0.2, 0.0, 0.0], [0.2, 0.0, 0.0]])
    data.site_lin_vel_w[:, [2, 0]] = torch.tensor([[0.3, 0.4, 90.0], [0.6, 0.8, 90.0]])
    data.site_lin_vel_w[:, 1] = 100.0
    contact.data.found[:] = torch.tensor([[1.0, 0.0], [0.0, 2.0]])
    term = _configured_term("foot_slip")
    result = term.func(env, **term.params)
    assert torch.allclose(result, torch.tensor([0.25, 1.0]))
    assert torch.allclose(result * term.weight, torch.tensor([-0.025, -0.1]))


@pytest.mark.parametrize("name", ["foot_clearance", "foot_slip"])
def test_foot_motion_costs_include_turning_and_use_the_strict_command_threshold(name):
    env, data, heights, contact, _ = _make_env([
        [0.0, 0.0, 0.0],
        [0.01, 0.0, 0.0],
        [0.0101, 0.0, 0.0],
        [0.0, 0.0, 0.5],
        [0.006, 0.0, 0.005],
        [0.004, 0.0, 0.005],
    ])
    heights[:] = 0.01
    data.site_lin_vel_w[:, [2, 0], 0] = 0.5
    contact.data.found[:] = 1.0
    term = _configured_term(name)
    result = term.func(env, **term.params)
    assert torch.equal(result > 0.0, torch.tensor([False, False, True, True, True, False]))


def test_swing_peak_height_is_paid_at_each_foot_landing_and_then_cleared():
    env, _, heights, contact, first_contact = _make_env([[0.2, 0.0, 0.0], [0.0, 0.0, 0.5]])
    cfg = _configured_term("foot_swing_height")
    term = cfg.func(cfg, env)
    heights[:] = torch.tensor([[0.04, 0.01], [0.01, 0.03]])
    assert torch.equal(term(env, **cfg.params), torch.zeros(2))
    heights[:] = 0.005
    contact.data.found[:] = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    first_contact[:] = torch.tensor([[True, False], [False, True]])
    first_landing = term(env, **cfg.params)
    assert torch.allclose(first_landing, torch.tensor([1.0, 0.25]))
    assert torch.allclose(first_landing * cfg.weight, torch.tensor([-0.25, -0.0625]))
    contact.data.found[:] = 1.0
    first_contact[:] = ~first_contact
    assert torch.allclose(term(env, **cfg.params), torch.tensor([0.25, 0.25]))
    first_contact.zero_()
    assert torch.equal(term(env, **cfg.params), torch.zeros(2))
    assert torch.equal(term.peak_heights, torch.zeros(2, 2))


def test_swing_landing_cost_is_disabled_for_zero_and_threshold_commands():
    env, _, heights, contact, first_contact = _make_env([
        [0.0, 0.0, 0.0], [0.01, 0.0, 0.0], [0.0, 0.0, 0.5]
    ])
    cfg = _configured_term("foot_swing_height")
    term = cfg.func(cfg, env)
    heights[:] = 0.04
    term(env, **cfg.params)
    contact.data.found[:] = 1.0
    first_contact[:] = True
    assert torch.allclose(term(env, **cfg.params), torch.tensor([0.0, 0.0, 2.0]))


def test_legacy_reward_manager_reset_clears_swing_peaks_without_touching_other_worlds():
    env, _, heights, contact, first_contact = _make_env([[0.2, 0.0, 0.0], [0.2, 0.0, 0.0]])
    cfg = _configured_term("foot_swing_height")
    assert cfg.func is MjlabFeetSwingHeight
    # 旧实现的逐环境 reset 修复继续单独覆盖，官方任务保持其原生类。
    cfg.func = LegacyFeetSwingHeight
    manager = RewardManager({"foot_swing_height": cfg}, env)
    heights[:] = torch.tensor([[0.08, 0.02], [0.06, 0.01]])
    manager.compute(env.step_dt)
    manager.reset(torch.tensor([0]))
    term = manager.get_term_cfg("foot_swing_height").func
    assert torch.equal(term.peak_heights[0], torch.zeros(2))
    assert torch.equal(term.peak_heights[1], torch.tensor([0.06, 0.01]))
    heights[:] = 0.02
    manager.compute(env.step_dt)
    contact.data.found[:] = 1.0
    first_contact[:] = True
    assert torch.allclose(manager.compute(env.step_dt), torch.tensor([0.0, -0.02]))


def test_body_angular_cost_uses_only_selected_body_roll_and_pitch_rates():
    env, data, _, _, _ = _make_env([[0.2, 0.0, 0.0], [0.2, 0.0, 0.0]])
    data.body_link_ang_vel_w[:, 0] = 100.0
    data.body_link_ang_vel_w[:, 1] = torch.tensor([[3.0, -4.0, 12.0], [0.0, 0.0, 10.0]])
    term = _configured_term("body_ang_vel")
    cost = term.func(env, **term.params)
    assert torch.equal(cost, torch.tensor([25.0, 0.0]))
    assert torch.allclose(cost * term.weight, torch.tensor([-1.25, 0.0]))


def test_angular_momentum_cost_includes_all_three_axes():
    env, _, _, _, _ = _make_env([[0.2, 0.0, 0.0], [0.2, 0.0, 0.0]])
    env.scene[f"{ROBOT}/root_angmom"].data[:] = torch.tensor([[2.0, -3.0, 6.0], [-1.0, 2.0, 2.0]])
    term = _configured_term("angular_momentum")
    cost = term.func(env, **term.params)
    assert torch.equal(cost, torch.tensor([49.0, 9.0]))
    assert torch.allclose(cost * term.weight, torch.tensor([-0.98, -0.18]))


def test_head_bias_curriculum_changes_real_manager_weights_at_iteration_boundaries():
    cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    env, data, _, _, _ = _make_env([[0.0, 0.0, 0.0]])
    env.command_manager.get_command = lambda name: torch.zeros(1, 4)
    data.joint_pos[:, [1, 3, 4, 5]] += 0.2
    reward = deepcopy(cfg.rewards["head_pose_bias"])
    reward.params["asset_cfg"] = SimpleNamespace(name=ROBOT, joint_ids=[1, 3, 4, 5])
    robot = env.scene[ROBOT]
    robot.joint_names = [
        "other_0", "neck_pitch_joint", "other_2", "head_pitch_joint",
        "head_yaw_joint", "head_roll_joint", "other_6",
    ]
    robot.find_joints_by_actuator_names = lambda patterns: (
        [1, 3, 4, 5], [robot.joint_names[index] for index in [1, 3, 4, 5]]
    )
    env.reward_manager = RewardManager({"head_pose_bias": reward}, env)
    schedule_cfg = cfg.curriculum["head_pose_bias_weight"]
    assert FlatVelocityRlCfg.num_steps_per_env == 24
    for step, expected_weight in (
        (0, 0.0), (600 * 24, 0.0), (600 * 24 + 1, 1.0),
        (1000 * 24, 1.0), (1000 * 24 + 1, 2.0),
        (1500 * 24, 2.0), (1500 * 24 + 1, 3.0),
    ):
        env.common_step_counter = step
        logged = schedule_cfg.func(env, torch.tensor([0]), **schedule_cfg.params)
        assert logged.item() == expected_weight
        assert env.reward_manager.get_term_cfg("head_pose_bias").weight == expected_weight
        value = env.reward_manager.compute(env.step_dt)
        assert (value.item() < 0.0) if expected_weight > 0.0 else (value.item() == 0.0)


def test_official_walking_terms_keep_legacy_velstand_and_posture_sensor_boundaries():
    from ht_microduck.tasks.config.ht_microduck.flat_sitstand_env_cfg import (
        make_sitstand_env_cfg,
    )
    from ht_microduck.tasks.config.ht_microduck.flat_standup_env_cfg import (
        make_standup_env_cfg,
    )
    from ht_microduck.tasks.config.ht_microduck.flat_velstand_env_cfg import (
        make_velstand_env_cfg,
    )

    velocity = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    extra_terms = {"body_ang_vel", "angular_momentum", "foot_swing_height", "head_pose_bias"}
    assert extra_terms <= velocity.rewards.keys()
    sensors = {sensor.name: sensor for sensor in velocity.scene.sensors}
    assert tuple(frame.name for frame in sensors[FOOT_HEIGHT_SENSOR].frame) == FOOT_SITE_NAMES
    for name in ("foot_clearance", "foot_slip"):
        assert velocity.rewards[name].params["asset_cfg"].preserve_order
    legacy = make_velstand_env_cfg(num_envs=1, seed=0)
    assert not (extra_terms & legacy.rewards.keys())
    assert "head_pose_bias_weight" not in legacy.curriculum
    for factory in (make_velstand_env_cfg, make_standup_env_cfg, make_sitstand_env_cfg):
        posture = factory(num_envs=1, seed=0)
        assert FOOT_HEIGHT_SENSOR not in {sensor.name for sensor in posture.scene.sensors}
    standup = make_standup_env_cfg(num_envs=1, seed=0)
    assert {"body_ang_vel", "angular_momentum", "head_pose_bias"} <= standup.rewards.keys()
    sitstand = make_sitstand_env_cfg(num_envs=1, seed=0)
    assert {"body_ang_vel", "angular_momentum"} <= sitstand.rewards.keys()
