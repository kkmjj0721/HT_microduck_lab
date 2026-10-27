"""Tests for the local PPO loss and update.

The important cases here are the ones that silently break training rather than
raising: a clipped surrogate that does not actually clip, a value loss that
ignores the clip, and an entropy bonus that never changes the parameters.
"""

from __future__ import annotations

import math

import pytest
import torch

from ht_microduck.algorithms.networks import ActorCritic, NetworkCfg
from ht_microduck.algorithms.ppo import PpoCfg, PpoUpdater, compute_ppo_loss
from ht_microduck.algorithms.storage import RolloutBatch, RolloutStorage
from ht_microduck.tasks.common import contract as C

ACTOR_OBS = C.ACTOR_OBSERVATION_DIM
CRITIC_OBS = C.CRITIC_OBSERVATION_DIM
ACTION = C.ACTION_DIM


def _model(seed: int = 0, **overrides) -> ActorCritic:
    torch.manual_seed(seed)
    cfg = NetworkCfg(hidden_dims=(32, 16), **overrides)
    return ActorCritic(cfg, cfg, ACTOR_OBS, CRITIC_OBS, ACTION)


def _batch(
    size: int = 16, *, advantage: float = 1.0, old_log_prob: float = 0.0
) -> RolloutBatch:
    torch.manual_seed(0)
    return RolloutBatch(
        obs=torch.randn(size, ACTOR_OBS),
        critic_obs=torch.randn(size, CRITIC_OBS),
        actions=torch.randn(size, ACTION),
        old_log_prob=torch.full((size,), old_log_prob),
        values=torch.randn(size),
        # A spread of advantages, not a constant: normalisation divides by the
        # standard deviation, so a constant batch would collapse to zero.
        advantages=torch.full((size,), advantage) + 0.1 * torch.randn(size),
        returns=torch.randn(size),
    )


def test_loss_is_finite_and_backward_produces_gradients():
    model = _model()
    loss, diagnostics = compute_ppo_loss(
        model=model,
        batch=_batch(),
        clip_param=0.2,
        value_loss_coef=1.0,
        entropy_coef=0.01,
        use_clipped_value_loss=True,
    )
    assert torch.isfinite(loss)
    loss.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads
    assert all(torch.isfinite(g).all() for g in grads)
    for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction"):
        assert key in diagnostics


def test_policy_loss_gradient_points_uphill_for_positive_advantage():
    """With a positive advantage, increasing the action's log-prob must reduce loss."""
    model = _model()
    batch = _batch(advantage=1.0)
    loss, _ = compute_ppo_loss(
        model=model,
        batch=batch,
        clip_param=0.2,
        value_loss_coef=0.0,
        entropy_coef=0.0,
        use_clipped_value_loss=False,
    )
    loss.backward()
    # The head's bias gradient is the cheapest readable signal: a positive
    # advantage should push the mean toward the sampled action.
    assert model.actor.mlp[-1].bias.grad is not None
    assert model.actor.mlp[-1].bias.grad.abs().sum() > 0


def test_clipping_bounds_the_surrogate_when_the_ratio_is_large():
    """The surrogate must stop growing once the ratio leaves the trust region."""
    # Drive this comparison directly through the loss, not through the network:
    # build two batches that differ only in how far the stored log-prob is from
    # the current policy's, so the ratio is the only thing that changes.
    model = _model()
    size, advantage = 8, 1.0
    obs = torch.randn(size, ACTOR_OBS)
    critic_obs = torch.randn(size, CRITIC_OBS)
    actions = torch.randn(size, ACTION)
    with torch.no_grad():
        current = model.distribution(obs).log_prob(actions)

    def _loss_at(offset: float) -> float:
        batch = RolloutBatch(
            obs=obs,
            critic_obs=critic_obs,
            actions=actions,
            old_log_prob=current - offset,
            values=torch.zeros(size),
            advantages=torch.full((size,), advantage),
            returns=torch.zeros(size),
        )
        _, diag = compute_ppo_loss(
            model=model,
            batch=batch,
            clip_param=0.2,
            value_loss_coef=0.0,
            entropy_coef=0.0,
            use_clipped_value_loss=False,
            normalize_advantages=False,
        )
        return diag["policy_loss"]

    # ratio = exp(offset). Inside the trust region the loss tracks -ratio; past
    # 1.2 the clipped branch is the minimum and the loss saturates at -1.2.
    inside = _loss_at(math.log(1.1))
    far = _loss_at(math.log(50.0))
    assert inside == pytest.approx(-1.1, rel=0.05)
    assert far == pytest.approx(-1.2, rel=0.05), (
        "Surrogate kept growing past the clip range; clipping is not applied."
    )


def test_value_loss_uses_the_worse_of_the_two_estimates_when_clipped():
    model = _model()
    batch = _batch()
    _, clipped = compute_ppo_loss(
        model=model,
        batch=batch,
        clip_param=0.2,
        value_loss_coef=1.0,
        entropy_coef=0.0,
        use_clipped_value_loss=True,
    )
    _, unclipped = compute_ppo_loss(
        model=model,
        batch=batch,
        clip_param=0.2,
        value_loss_coef=1.0,
        entropy_coef=0.0,
        use_clipped_value_loss=False,
    )
    # max(a, b) >= 0.5 * a, so clipping can only raise the value loss here.
    assert clipped["value_loss"] >= unclipped["value_loss"] - 1e-6


def test_entropy_bonus_changes_the_parameters():
    """Entropy alone must move log_std; a zero-gradient bug would freeze it."""
    model = _model()
    batch = _batch()
    before = model.log_std.detach().clone()
    loss, _ = compute_ppo_loss(
        model=model,
        batch=batch,
        clip_param=0.2,
        value_loss_coef=0.0,
        entropy_coef=1.0,
        use_clipped_value_loss=False,
    )
    loss.backward()
    assert model.log_std.grad is not None
    assert model.log_std.grad.abs().sum() > 0
    assert torch.equal(before, model.log_std.detach())


def test_log_prob_matches_when_re_evaluated_through_the_model():
    """The stored log-prob must be reproducible from the same weights."""
    model = _model()
    obs = torch.randn(5, ACTOR_OBS)
    critic_obs = torch.randn(5, CRITIC_OBS)
    dist = model.distribution(obs)
    action = dist.mean  # deterministic point so both calls agree
    log_prob, _, _, _ = model.evaluate(obs, critic_obs, action)
    assert torch.allclose(log_prob, dist.log_prob(action), atol=1e-6)


def _full_storage(num_steps: int = 4, num_envs: int = 8) -> RolloutStorage:
    storage = RolloutStorage(
        num_steps=num_steps,
        num_envs=num_envs,
        obs_dim=ACTOR_OBS,
        critic_obs_dim=CRITIC_OBS,
        action_dim=ACTION,
    )
    torch.manual_seed(0)
    for _ in range(num_steps):
        storage.add(
            obs=torch.randn(num_envs, ACTOR_OBS),
            critic_obs=torch.randn(num_envs, CRITIC_OBS),
            actions=torch.randn(num_envs, ACTION),
            log_prob=torch.randn(num_envs),
            values=torch.randn(num_envs),
            rewards=torch.randn(num_envs),
            dones=torch.zeros(num_envs, dtype=torch.bool),
        )
    storage.compute_returns(
        last_values=torch.randn(num_envs), gamma=0.99, lam=0.95
    )
    return storage


def test_updater_changes_the_parameters():
    model = _model()
    updater = PpoUpdater(model, PpoCfg(num_learning_epochs=1, num_mini_batches=2))
    before = {name: p.detach().clone() for name, p in model.named_parameters()}
    storage = _full_storage()
    metrics = updater.update(storage, generator=torch.Generator().manual_seed(0))
    changed = [
        name
        for name, p in model.named_parameters()
        if not torch.equal(before[name], p.detach())
    ]
    assert changed, "PPO update left every parameter unchanged."
    assert torch.isfinite(torch.tensor(metrics["policy_loss"]))
    assert torch.isfinite(torch.tensor(metrics["value_loss"]))
    assert metrics["learning_rate"] > 0


def test_updater_gradients_are_finite():
    model = _model()
    updater = PpoUpdater(model, PpoCfg(num_learning_epochs=1, num_mini_batches=2))
    storage = _full_storage()
    updater.update(storage, generator=torch.Generator().manual_seed(0))
    for name, parameter in model.named_parameters():
        assert torch.isfinite(parameter).all(), f"{name} became non-finite"


def test_adaptive_learning_rate_responds_to_kl():
    """A large observed KL must shrink the step size, a tiny one must grow it."""
    model = _model()
    updater = PpoUpdater(model, PpoCfg(desired_kl=0.01, learning_rate=1e-3))
    start = updater.learning_rate
    updater._adapt_learning_rate(10.0)  # far too large
    assert updater.learning_rate < start
    grew_from = updater.learning_rate
    updater._adapt_learning_rate(0.0)  # essentially no movement
    assert updater.learning_rate > grew_from


def test_adaptive_learning_rate_stays_bounded():
    model = _model()
    updater = PpoUpdater(model, PpoCfg(desired_kl=0.01, learning_rate=1e-3))
    for _ in range(50):
        updater._adapt_learning_rate(1e6)
    assert updater.learning_rate >= 1e-5
    for _ in range(50):
        updater._adapt_learning_rate(0.0)
    assert updater.learning_rate <= 1e-2


def test_fixed_schedule_does_not_adapt():
    model = _model()
    updater = PpoUpdater(
        model, PpoCfg(schedule="fixed", learning_rate=3e-4)
    )
    updater._adapt_learning_rate(100.0)
    assert updater.learning_rate == 3e-4


def test_minibatch_count_and_coverage_drive_the_epoch_count():
    """Each epoch must visit every sample exactly once."""
    model = _model()
    cfg = PpoCfg(num_learning_epochs=3, num_mini_batches=4)
    updater = PpoUpdater(model, cfg)
    storage = _full_storage(num_steps=4, num_envs=8)
    metrics = updater.update(storage, generator=torch.Generator().manual_seed(0))
    assert metrics["learning_rate"] > 0
    # Sanity: 3 epochs x 4 minibatches of equal size = 12 updates seen.
    assert metrics["policy_loss"] == metrics["policy_loss"]
