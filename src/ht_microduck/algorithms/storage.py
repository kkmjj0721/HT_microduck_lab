"""Rollout storage and generalised advantage estimation.

The layout is a fixed-capacity ring of ``num_steps_per_env`` transitions per
environment. ``compute_returns`` runs GAE-λ and, importantly, distinguishes a
*terminal* transition from a *timeout*: nothing exists after a real termination,
so its bootstrap value is zero, while a timeout keeps the value estimate because
the episode was only cut off by the horizon.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(kw_only=True)
class RolloutBatch:
    """One flattened minibatch ready for a PPO update."""

    obs: torch.Tensor
    critic_obs: torch.Tensor
    actions: torch.Tensor
    old_log_prob: torch.Tensor
    values: torch.Tensor
    advantages: torch.Tensor
    returns: torch.Tensor

    def __len__(self) -> int:
        return self.obs.shape[0]


class RolloutStorage:
    """Fixed-capacity storage for one PPO iteration.

    Args:
      num_steps: transitions collected per environment per iteration.
      num_envs: number of parallel environments.
      obs_dim: actor observation size.
      critic_obs_dim: critic observation size.
      action_dim: action size.
      device: torch device for the buffers.
    """

    def __init__(
        self,
        *,
        num_steps: int,
        num_envs: int,
        obs_dim: int,
        critic_obs_dim: int,
        action_dim: int,
        device: torch.device | str = "cpu",
    ) -> None:
        self.num_steps = int(num_steps)
        self.num_envs = int(num_envs)
        self.device = torch.device(device)
        shape = (self.num_steps, self.num_envs)
        self.obs = torch.zeros(*shape, obs_dim, device=self.device)
        self.critic_obs = torch.zeros(*shape, critic_obs_dim, device=self.device)
        self.actions = torch.zeros(*shape, action_dim, device=self.device)
        self.log_prob = torch.zeros(shape, device=self.device)
        self.values = torch.zeros(shape, device=self.device)
        self.rewards = torch.zeros(shape, device=self.device)
        self.dones = torch.zeros(shape, dtype=torch.bool, device=self.device)
        # True where the episode was cut by the horizon rather than failing.
        self.time_outs = torch.zeros(shape, dtype=torch.bool, device=self.device)
        self.advantages = torch.zeros(shape, device=self.device)
        self.returns = torch.zeros(shape, device=self.device)
        self.step = 0

    def add(
        self,
        *,
        obs: torch.Tensor,
        critic_obs: torch.Tensor,
        actions: torch.Tensor,
        log_prob: torch.Tensor,
        values: torch.Tensor,
        rewards: torch.Tensor,
        dones: torch.Tensor,
        time_outs: torch.Tensor | None = None,
    ) -> None:
        """Record one environment step for every world."""
        if self.step >= self.num_steps:
            raise RuntimeError(
                f"Storage is full ({self.num_steps} steps); call compute_returns()."
            )
        index = self.step
        self.obs[index] = obs
        self.critic_obs[index] = critic_obs
        self.actions[index] = actions
        self.log_prob[index] = log_prob
        self.values[index] = values
        self.rewards[index] = rewards
        self.dones[index] = dones
        if time_outs is not None:
            self.time_outs[index] = time_outs
        self.step += 1

    def compute_returns(
        self, *, last_values: torch.Tensor, gamma: float, lam: float
    ) -> None:
        """Fill ``advantages`` and ``returns`` with GAE-λ.

        ``last_values`` bootstraps the tail of the rollout. A transition marked
        done contributes no future value; a transition marked done *and*
        time_out keeps its bootstrap through ``last_values`` only if it is the
        final step, otherwise the horizon cut is handled by not zeroing.
        """
        advantage = torch.zeros(self.num_envs, device=self.device)
        for step in reversed(range(self.num_steps)):
            if step == self.num_steps - 1:
                next_value = last_values
            else:
                next_value = self.values[step + 1]
            # A real termination has no future; a timeout does.
            terminal = self.dones[step] & ~self.time_outs[step]
            not_terminal = ~terminal
            delta = (
                self.rewards[step]
                + gamma * next_value * not_terminal.float()
                - self.values[step]
            )
            advantage = delta + gamma * lam * not_terminal.float() * advantage
            self.advantages[step] = advantage
        self.returns[:] = self.advantages + self.values

    def flatten(self) -> tuple[torch.Tensor, ...]:
        """Return the full rollout as flat tensors, time-major."""
        return (
            self.obs.reshape(-1, self.obs.shape[-1]),
            self.critic_obs.reshape(-1, self.critic_obs.shape[-1]),
            self.actions.reshape(-1, self.actions.shape[-1]),
            self.log_prob.reshape(-1),
            self.values.reshape(-1),
            self.advantages.reshape(-1),
            self.returns.reshape(-1),
        )

    def minibatches(
        self, num_minibatches: int, generator: torch.Generator | None = None
    ) -> list[RolloutBatch]:
        """Shuffle the flattened rollout and split it into equal minibatches."""
        obs, critic_obs, actions, log_prob, values, advantages, returns = self.flatten()
        total = obs.shape[0]
        if total % num_minibatches != 0:
            # Trim to the largest divisible prefix so every minibatch has the same
            # shape; dropping a few samples beats ragged batches in the update.
            keep = (total // num_minibatches) * num_minibatches
            obs, critic_obs, actions, log_prob, values, advantages, returns = (
                tensor[:keep]
                for tensor in (obs, critic_obs, actions, log_prob, values, advantages, returns)
            )
            total = keep
        perm = torch.randperm(total, device=self.device, generator=generator)
        batches: list[RolloutBatch] = []
        size = total // num_minibatches
        for start in range(0, total, size):
            index = perm[start : start + size]
            batches.append(
                RolloutBatch(
                    obs=obs[index],
                    critic_obs=critic_obs[index],
                    actions=actions[index],
                    old_log_prob=log_prob[index],
                    values=values[index],
                    advantages=advantages[index],
                    returns=returns[index],
                )
            )
        return batches

    def clear(self) -> None:
        """Reset the write cursor; buffers are overwritten in place."""
        self.step = 0
