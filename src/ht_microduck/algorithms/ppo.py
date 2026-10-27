"""PPO loss and the per-iteration update.

The loss follows the standard clipped surrogate objective with a clipped value
loss and an entropy bonus. Two details matter for stability on this task:

- Advantages are normalised per minibatch, because the tracking reward is on a
  different scale from the penalty terms.
- The learning rate is adapted from the measured KL divergence, which is more
  robust than a fixed schedule when the task reward is mostly shaped terms.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn

from ht_microduck.algorithms.networks import ActorCritic
from ht_microduck.algorithms.storage import RolloutBatch, RolloutStorage


@dataclass(kw_only=True)
class PpoCfg:
    """Hyperparameters for PPO."""

    num_steps_per_env: int = 24
    num_learning_epochs: int = 5
    num_mini_batches: int = 4
    learning_rate: float = 1e-3
    gamma: float = 0.99
    lam: float = 0.95
    clip_param: float = 0.2
    value_loss_coef: float = 1.0
    entropy_coef: float = 0.01
    max_grad_norm: float = 1.0
    use_clipped_value_loss: bool = True
    schedule: str = "adaptive"
    desired_kl: float = 0.01


def compute_ppo_loss(
    *,
    model: ActorCritic,
    batch: RolloutBatch,
    clip_param: float,
    value_loss_coef: float,
    entropy_coef: float,
    use_clipped_value_loss: bool,
    normalize_advantages: bool = True,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Return the scalar loss and detached diagnostics for one minibatch."""
    log_prob, entropy, value, _ = model.evaluate(
        batch.obs, batch.critic_obs, batch.actions
    )

    # Normalise the advantages within the minibatch. The reward here is a sum of
    # a large tracking term and many small penalties, so raw advantages span a
    # wide range; without this the first update takes a huge step and the clip
    # fraction pins at ~1.
    advantages = batch.advantages
    if normalize_advantages:
        std = advantages.std()
        if float(std) > 1e-8:
            advantages = (advantages - advantages.mean()) / (std + 1e-8)

    # --- policy surrogate ---------------------------------------------------
    ratio = torch.exp(log_prob - batch.old_log_prob)
    surrogate_a = ratio * advantages
    surrogate_b = (
        torch.clamp(ratio, 1.0 - clip_param, 1.0 + clip_param) * advantages
    )
    policy_loss = -torch.min(surrogate_a, surrogate_b).mean()

    # --- value loss ---------------------------------------------------------
    if use_clipped_value_loss:
        clipped_value = batch.values + torch.clamp(
            value - batch.values, -clip_param, clip_param
        )
        value_loss_a = torch.square(value - batch.returns)
        value_loss_b = torch.square(clipped_value - batch.returns)
        value_loss = 0.5 * torch.max(value_loss_a, value_loss_b).mean()
    else:
        value_loss = 0.5 * torch.square(value - batch.returns).mean()

    entropy_bonus = entropy.mean()
    loss = policy_loss + value_loss_coef * value_loss - entropy_coef * entropy_bonus

    # The KL estimate uses the same samples as the update, so it is a slightly
    # biased but cheap proxy for how far this step moved the policy.
    with torch.no_grad():
        approx_kl = ((ratio - 1.0) - (log_prob - batch.old_log_prob)).mean()
        clip_fraction = (
            (ratio - 1.0).abs() > clip_param
        ).float().mean()

    diagnostics = {
        "policy_loss": float(policy_loss.detach()),
        "value_loss": float(value_loss.detach()),
        "entropy": float(entropy_bonus.detach()),
        "approx_kl": float(approx_kl.detach()),
        "clip_fraction": float(clip_fraction.detach()),
    }
    return loss, diagnostics


class PpoUpdater:
    """Owns the optimiser and runs one PPO iteration over a rolled-out buffer."""

    def __init__(self, model: ActorCritic, cfg: PpoCfg) -> None:
        self.model = model
        self.cfg = cfg
        self.optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)
        self.learning_rate = cfg.learning_rate

    def update(
        self,
        storage: RolloutStorage,
        *,
        generator: torch.Generator | None = None,
    ) -> dict[str, float]:
        """Run all epochs/minibatches over ``storage`` and return mean metrics."""
        totals: dict[str, float] = {}
        count = 0
        for _ in range(self.cfg.num_learning_epochs):
            batches = storage.minibatches(self.cfg.num_mini_batches, generator=generator)
            for batch in batches:
                loss, diagnostics = compute_ppo_loss(
                    model=self.model,
                    batch=batch,
                    clip_param=self.cfg.clip_param,
                    value_loss_coef=self.cfg.value_loss_coef,
                    entropy_coef=self.cfg.entropy_coef,
                    use_clipped_value_loss=self.cfg.use_clipped_value_loss,
                )
                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.cfg.max_grad_norm
                )
                self.optimizer.step()
                for key, value in diagnostics.items():
                    totals[key] = totals.get(key, 0.0) + value
                count += 1
        metrics = {key: value / max(count, 1) for key, value in totals.items()}
        self._adapt_learning_rate(metrics.get("approx_kl", 0.0))
        metrics["learning_rate"] = self.learning_rate
        return metrics

    def _adapt_learning_rate(self, approx_kl: float) -> None:
        """Scale the step size from the observed KL divergence.

        When the update moved further than intended, shrink; when it barely
        moved, grow. Bounded so one pathological batch cannot stall or explode
        training.
        """
        if self.cfg.schedule != "adaptive":
            return
        target = self.cfg.desired_kl
        if approx_kl > 2.0 * target:
            self.learning_rate = max(self.learning_rate / 1.5, 1e-5)
        elif approx_kl < 0.5 * target:
            self.learning_rate = min(self.learning_rate * 1.5, 1e-2)
        for group in self.optimizer.param_groups:
            group["lr"] = self.learning_rate
