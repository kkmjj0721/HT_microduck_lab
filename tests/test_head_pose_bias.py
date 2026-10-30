"""Check persistent head bias separately from zero-mean gait oscillations."""

from types import SimpleNamespace

import torch
from mjlab.managers.reward_manager import RewardManager, RewardTermCfg

from ht_microduck.tasks.mdp.rewards import head_pose_bias_penalty

HEAD_IDS = [1, 3, 4, 5]


def _make_env(num_envs=2):
    default = torch.tensor([[0.7, -0.35, 0.2, 0.4, -0.1, 0.1, 0.15]]).repeat(num_envs, 1)
    data = SimpleNamespace(joint_pos=default.clone(), default_joint_pos=default)
    command = torch.zeros(num_envs, 4)
    env = SimpleNamespace(
        scene={"robot": SimpleNamespace(data=data)},
        command_manager=SimpleNamespace(get_command=lambda name: command),
        step_dt=0.02,
        num_envs=num_envs,
        device="cpu",
        max_episode_length_s=20.0,
    )
    asset = SimpleNamespace(name="robot", joint_ids=HEAD_IDS)
    params = {"command_name": "head_pose", "tau_s": 1.0, "asset_cfg": asset}
    cfg = RewardTermCfg(func=head_pose_bias_penalty, weight=-3.0, params=params)
    return env, data, command, cfg


def test_head_bias_uses_selected_joint_deltas_and_command_targets():
    env, data, command, cfg = _make_env()
    command[:] = torch.tensor([0.2, -0.3, 0.1, 0.05])
    data.joint_pos[:, HEAD_IDS] = data.default_joint_pos[:, HEAD_IDS] + command
    data.joint_pos[:, [0, 2, 6]] += 1.0
    term = head_pose_bias_penalty(cfg, env)
    result = term(env, **cfg.params)
    assert torch.allclose(result, torch.zeros(2), atol=1e-8)
    assert result.shape == (2,)
    assert result.dtype == torch.float32


def test_constant_head_bias_accumulates_over_one_second_from_zero():
    env, data, _, cfg = _make_env()
    data.joint_pos[:, HEAD_IDS] += torch.tensor([0.2, -0.1, 0.4, -0.3])
    term = head_pose_bias_penalty(cfg, env)
    assert torch.allclose(term(env, **cfg.params), torch.full((2,), 0.005))
    for _ in range(49):
        result = term(env, **cfg.params)
    expected = 0.25 * (1.0 - 0.98**50)
    assert torch.allclose(result, torch.full((2,), expected))
    assert torch.all(result >= 0.0)
    assert torch.all(result * cfg.weight < 0.0)


def test_alternating_head_motion_cancels_before_absolute_value():
    env, data, _, cfg = _make_env(num_envs=1)
    term = head_pose_bias_penalty(cfg, env)
    for index in range(500):
        displacement = 0.2 if index % 2 == 0 else -0.2
        data.joint_pos[:, HEAD_IDS] = data.default_joint_pos[:, HEAD_IDS] + displacement
        result = term(env, **cfg.params)
    assert 0.0 < result.item() < 0.003


def test_command_change_updates_the_signed_error_without_clearing_history():
    env, data, command, cfg = _make_env(num_envs=1)
    data.joint_pos[:, HEAD_IDS] += 0.2
    term = head_pose_bias_penalty(cfg, env)
    for _ in range(50):
        previous = term(env, **cfg.params)
    command[:] = 0.2
    matching = term(env, **cfg.params)
    assert torch.allclose(matching, previous * 0.98)
    command[:] = 0.4
    reversed_error = term(env, **cfg.params)
    assert torch.allclose(reversed_error, matching * 0.98 - 0.004)


def test_reward_manager_resets_only_selected_worlds_and_applies_negative_weight():
    env, data, _, cfg = _make_env()
    data.joint_pos[:, HEAD_IDS] += 0.2
    manager = RewardManager({"head_pose_bias": cfg}, env)
    for _ in range(50):
        before = manager.compute(env.step_dt).clone()
    assert torch.all(before < 0.0)
    manager.reset(torch.tensor([0]))
    after = manager.compute(env.step_dt)
    assert torch.allclose(after[0], torch.tensor(-0.00024))
    assert after[1] < before[1]
    manager.reset()
    reset_all = manager.compute(env.step_dt)
    assert torch.allclose(reset_all, torch.full((2,), -0.00024))


def test_zero_weight_phase_does_not_accumulate_hidden_head_bias():
    env, data, _, cfg = _make_env(num_envs=1)
    data.joint_pos[:, HEAD_IDS] += 0.2
    cfg.weight = 0.0
    manager = RewardManager({"head_pose_bias": cfg}, env)
    for _ in range(50):
        assert torch.equal(manager.compute(env.step_dt), torch.zeros(1))
    manager.get_term_cfg("head_pose_bias").weight = -1.0
    assert torch.allclose(manager.compute(env.step_dt), torch.tensor([-0.00008]))
