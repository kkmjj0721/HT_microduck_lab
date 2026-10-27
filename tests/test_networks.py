"""Tests for the local networks, observation normalisation and rollout storage."""

from __future__ import annotations

import math

import pytest
import torch

from ht_microduck.algorithms.networks import (
    ActorCritic,
    GaussianDistribution,
    NetworkCfg,
    RunningMeanStd,
)
from ht_microduck.algorithms.storage import RolloutStorage
from ht_microduck.tasks.common import contract as C

ACTOR_OBS = C.ACTOR_OBSERVATION_DIM
CRITIC_OBS = C.CRITIC_OBSERVATION_DIM
ACTION = C.ACTION_DIM


def _model(**overrides) -> ActorCritic:
    cfg = NetworkCfg(**overrides) if overrides else NetworkCfg()
    return ActorCritic(cfg, cfg, ACTOR_OBS, CRITIC_OBS, ACTION)


def test_contract_dimensions_are_consistent():
    assert ACTOR_OBS == 39
    assert CRITIC_OBS == 42
    assert ACTION == 10
    assert CRITIC_OBS - ACTOR_OBS == 3


def test_actor_and_critic_shapes():
    model = _model()
    obs = torch.randn(5, ACTOR_OBS)
    critic_obs = torch.randn(5, CRITIC_OBS)
    assert model.actor(obs).shape == (5, ACTION)
    assert model.critic(critic_obs).shape == (5,)


def test_sample_and_log_prob_shapes():
    model = _model()
    obs = torch.randn(7, ACTOR_OBS)
    action, log_prob = model.act(obs)
    assert action.shape == (7, ACTION)
    assert log_prob.shape == (7,)
    assert torch.isfinite(action).all()
    assert torch.isfinite(log_prob).all()


def test_log_prob_matches_manual_gaussian_value():
    """Check the log-prob against a hand-computed diagonal Gaussian."""
    mean = torch.zeros(1, 2)
    log_std = torch.zeros(1, 2)
    dist = GaussianDistribution(mean, log_std)
    value = torch.tensor([[1.0, -2.0]])

    expected = torch.sum(
        -0.5 * value**2 - 0.5 * math.log(2 * math.pi), dim=-1
    )
    assert torch.allclose(dist.log_prob(value), expected, atol=1e-6)


def test_log_prob_peaks_at_the_mean():
    mean = torch.zeros(1, 3)
    dist = GaussianDistribution(mean, torch.zeros(1, 3))
    at_mean = dist.log_prob(torch.zeros(1, 3))
    off_mean = dist.log_prob(torch.full((1, 3), 1.0))
    assert at_mean > off_mean


def test_entropy_matches_closed_form():
    """Entropy of a diagonal Gaussian is sum(0.5*log(2*pi*e*sigma^2))."""
    log_std = torch.full((1, 4), 0.3)
    dist = GaussianDistribution(torch.zeros(1, 4), log_std)
    expected = torch.sum(
        0.5 * math.log(2 * math.pi * math.e) + log_std, dim=-1
    )
    assert torch.allclose(dist.entropy(), expected, atol=1e-6)


def test_log_std_is_clamped_to_a_sane_range():
    """An exploding parameter must not produce an infinite-width distribution."""
    dist = GaussianDistribution(torch.zeros(1, 2), torch.full((1, 2), 50.0))
    assert torch.isfinite(dist.std).all()
    assert float(dist.log_std.max()) <= 1.0


def test_running_mean_std_converges_to_the_batch_moments():
    normalizer = RunningMeanStd(3, epsilon=0.0, clip=1e9)
    torch.manual_seed(0)
    data = torch.randn(4096, 3) * 2.0 + 5.0
    normalizer.update(data)
    assert torch.allclose(normalizer.mean, data.mean(dim=0), atol=1e-4)
    assert torch.allclose(normalizer.var, data.var(dim=0, unbiased=False), atol=1e-3)


def test_running_mean_std_is_stable_across_updates():
    """Two half-batches must give the same statistics as one whole batch."""
    torch.manual_seed(1)
    data = torch.randn(512, 2)
    whole = RunningMeanStd(2, epsilon=0.0)
    whole.update(data)

    split = RunningMeanStd(2, epsilon=0.0)
    split.update(data[:256])
    split.update(data[256:])

    assert torch.allclose(whole.mean, split.mean, atol=1e-5)
    assert torch.allclose(whole.var, split.var, atol=1e-4)


def test_running_mean_std_clips_outliers():
    normalizer = RunningMeanStd(2, epsilon=1e-8, clip=1.0)
    normalizer.update(torch.zeros(100, 2))
    out = normalizer(torch.full((1, 2), 1000.0))
    assert torch.all(out.abs() <= 1.0)


def _filled_storage(num_steps: int = 4, num_envs: int = 2) -> RolloutStorage:
    storage = RolloutStorage(
        num_steps=num_steps,
        num_envs=num_envs,
        obs_dim=ACTOR_OBS,
        critic_obs_dim=CRITIC_OBS,
        action_dim=ACTION,
    )
    return storage


def test_storage_records_steps_and_reports_full():
    storage = _filled_storage(num_steps=2)
    for _ in range(2):
        storage.add(
            obs=torch.zeros(2, ACTOR_OBS),
            critic_obs=torch.zeros(2, CRITIC_OBS),
            actions=torch.zeros(2, ACTION),
            log_prob=torch.zeros(2),
            values=torch.zeros(2),
            rewards=torch.zeros(2),
            dones=torch.zeros(2, dtype=torch.bool),
        )
    with pytest.raises(RuntimeError, match="full"):
        storage.add(
            obs=torch.zeros(2, ACTOR_OBS),
            critic_obs=torch.zeros(2, CRITIC_OBS),
            actions=torch.zeros(2, ACTION),
            log_prob=torch.zeros(2),
            values=torch.zeros(2),
            rewards=torch.zeros(2),
            dones=torch.zeros(2, dtype=torch.bool),
        )


def test_gae_matches_a_hand_computed_trajectory():
    """Two steps, no termination: verify the recursion by hand."""
    storage = _filled_storage(num_steps=2, num_envs=1)
    gamma, lam = 0.9, 0.8
    rewards = [1.0, 2.0]
    values = [0.5, 1.5]
    for step in range(2):
        storage.add(
            obs=torch.zeros(1, ACTOR_OBS),
            critic_obs=torch.zeros(1, CRITIC_OBS),
            actions=torch.zeros(1, ACTION),
            log_prob=torch.zeros(1),
            values=torch.tensor([values[step]]),
            rewards=torch.tensor([rewards[step]]),
            dones=torch.zeros(1, dtype=torch.bool),
        )
    last_value = torch.tensor([2.5])
    storage.compute_returns(last_values=last_value, gamma=gamma, lam=lam)

    # delta_1 = r1 + gamma * V_last - V_1
    delta_1 = rewards[1] + gamma * float(last_value) - values[1]
    adv_1 = delta_1
    # delta_0 = r0 + gamma * V_1 - V_0
    delta_0 = rewards[0] + gamma * values[1] - values[0]
    adv_0 = delta_0 + gamma * lam * adv_1

    assert storage.advantages[0, 0].item() == pytest.approx(adv_0, abs=1e-6)
    assert storage.advantages[1, 0].item() == pytest.approx(adv_1, abs=1e-6)
    assert storage.returns[0, 0].item() == pytest.approx(adv_0 + values[0], abs=1e-6)
    assert storage.returns[1, 0].item() == pytest.approx(adv_1 + values[1], abs=1e-6)


def test_gae_zeroes_bootstrap_after_a_real_termination():
    """A terminal transition must not use the next value."""
    storage = _filled_storage(num_steps=2, num_envs=1)
    gamma, lam = 0.9, 0.8
    storage.add(
        obs=torch.zeros(1, ACTOR_OBS),
        critic_obs=torch.zeros(1, CRITIC_OBS),
        actions=torch.zeros(1, ACTION),
        log_prob=torch.zeros(1),
        values=torch.tensor([0.5]),
        rewards=torch.tensor([1.0]),
        dones=torch.zeros(1, dtype=torch.bool),
    )
    storage.add(
        obs=torch.zeros(1, ACTOR_OBS),
        critic_obs=torch.zeros(1, CRITIC_OBS),
        actions=torch.zeros(1, ACTION),
        log_prob=torch.zeros(1),
        values=torch.tensor([1.5]),
        rewards=torch.tensor([2.0]),
        dones=torch.ones(1, dtype=torch.bool),
        time_outs=torch.zeros(1, dtype=torch.bool),
    )
    storage.compute_returns(
        last_values=torch.tensor([2.5]), gamma=gamma, lam=lam
    )
    # Terminal: delta_1 = r1 - V_1 (no gamma * V_next term).
    assert storage.advantages[1, 0].item() == pytest.approx(2.0 - 1.5, abs=1e-6)


def test_gae_bootstraps_through_a_timeout():
    """A timeout keeps the value bootstrap so training does not treat it as death."""
    storage = _filled_storage(num_steps=2, num_envs=1)
    gamma, lam = 0.9, 0.8
    storage.add(
        obs=torch.zeros(1, ACTOR_OBS),
        critic_obs=torch.zeros(1, CRITIC_OBS),
        actions=torch.zeros(1, ACTION),
        log_prob=torch.zeros(1),
        values=torch.tensor([0.5]),
        rewards=torch.tensor([1.0]),
        dones=torch.zeros(1, dtype=torch.bool),
    )
    storage.add(
        obs=torch.zeros(1, ACTOR_OBS),
        critic_obs=torch.zeros(1, CRITIC_OBS),
        actions=torch.zeros(1, ACTION),
        log_prob=torch.zeros(1),
        values=torch.tensor([1.5]),
        rewards=torch.tensor([2.0]),
        dones=torch.ones(1, dtype=torch.bool),
        time_outs=torch.ones(1, dtype=torch.bool),
    )
    last_value = 2.5
    storage.compute_returns(
        last_values=torch.tensor([last_value]), gamma=gamma, lam=lam
    )
    # Timeout: delta_1 = r1 + gamma * V_last - V_1.
    expected = 2.0 + gamma * last_value - 1.5
    assert storage.advantages[1, 0].item() == pytest.approx(expected, abs=1e-6)


def test_minibatches_cover_every_sample_exactly_once():
    storage = _filled_storage(num_steps=8, num_envs=4)
    for step in range(8):
        storage.add(
            obs=torch.full((4, ACTOR_OBS), float(step)),
            critic_obs=torch.zeros(4, CRITIC_OBS),
            actions=torch.zeros(4, ACTION),
            log_prob=torch.zeros(4),
            values=torch.zeros(4),
            rewards=torch.zeros(4),
            dones=torch.zeros(4, dtype=torch.bool),
        )
    storage.compute_returns(
        last_values=torch.zeros(4), gamma=0.99, lam=0.95
    )
    generator = torch.Generator().manual_seed(0)
    batches = storage.minibatches(4, generator=generator)
    assert len(batches) == 4
    seen = torch.cat([batch.obs[:, 0] for batch in batches])
    # 8 steps x 4 envs, each step value appears exactly num_envs times.
    for step in range(8):
        assert int((seen == float(step)).sum()) == 4


def test_storage_clear_resets_the_cursor():
    storage = _filled_storage(num_steps=2)
    storage.add(
        obs=torch.zeros(2, ACTOR_OBS),
        critic_obs=torch.zeros(2, CRITIC_OBS),
        actions=torch.zeros(2, ACTION),
        log_prob=torch.zeros(2),
        values=torch.zeros(2),
        rewards=torch.zeros(2),
        dones=torch.zeros(2, dtype=torch.bool),
    )
    assert storage.step == 1
    storage.clear()
    assert storage.step == 0


def test_actor_critic_evaluate_shapes():
    model = _model()
    obs = torch.randn(6, ACTOR_OBS)
    critic_obs = torch.randn(6, CRITIC_OBS)
    action = torch.randn(6, ACTION)
    log_prob, entropy, value, mean = model.evaluate(obs, critic_obs, action)
    assert log_prob.shape == (6,)
    assert entropy.shape == (6,)
    assert value.shape == (6,)
    assert mean.shape == (6, ACTION)
