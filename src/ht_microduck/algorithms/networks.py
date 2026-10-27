"""Actor/critic networks and observation normalisation.

Deliberately small and dependency-free: plain ``torch.nn`` modules with an
explicit ``forward`` contract, so the same code can be exported to ONNX later
without stripping framework wrappers.

Shapes are fixed by ``contract.py``: the actor consumes a 39-D observation and
emits a 10-D action mean; the critic consumes 42-D and emits a scalar.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn


def _build_mlp(dims: tuple[int, ...], activation: str) -> nn.Sequential:
    layers: list[nn.Module] = []
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        if i < len(dims) - 2:
            layers.append(_ACTIVATIONS[activation]())
    return nn.Sequential(*layers)


_ACTIVATIONS: dict[str, type[nn.Module]] = {
    "elu": nn.ELU,
    "relu": nn.ReLU,
    "tanh": nn.Tanh,
    "selu": nn.SELU,
}


class RunningMeanStd(nn.Module):
    """Streaming mean/variance with a bias-corrected update.

    Used to normalise observations. It is an ``nn.Module`` so it moves with the
    policy and ends up in the checkpoint; the count is a buffer so a restored
    run keeps its statistics instead of restarting them.
    """

    def __init__(self, shape: int, epsilon: float = 1e-4, clip: float = 5.0) -> None:
        super().__init__()
        self.epsilon = epsilon
        self.clip = clip
        self.register_buffer("mean", torch.zeros(shape))
        self.register_buffer("var", torch.ones(shape))
        self.register_buffer("count", torch.tensor(0.0))

    @torch.no_grad()
    def update(self, batch: torch.Tensor) -> None:
        batch = batch.detach()
        batch_mean = batch.mean(dim=0)
        batch_var = batch.var(dim=0, unbiased=False)
        batch_count = batch.shape[0]
        # Parallel/Chanh-Lin style update via the pooled mean and variance.
        total = self.count + batch_count
        delta = batch_mean - self.mean
        new_mean = self.mean + delta * batch_count / total
        m2 = self.var * self.count + batch_var * batch_count
        m2 = m2 + delta.square() * self.count * batch_count / total
        self.mean.copy_(new_mean)
        self.var.copy_(m2 / total)
        self.count.copy_(total)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        normalized = (obs - self.mean) / torch.sqrt(self.var + self.epsilon)
        return torch.clamp(normalized, -self.clip, self.clip)


@dataclass(kw_only=True)
class NetworkCfg:
    """Shape and activation settings shared by both networks."""

    hidden_dims: tuple[int, ...] = (512, 256, 128)
    activation: str = "elu"
    obs_normalization: bool = True


class Actor(nn.Module):
    """Maps observations to the mean of a diagonal Gaussian action distribution."""

    def __init__(self, obs_dim: int, action_dim: int, cfg: NetworkCfg) -> None:
        super().__init__()
        self.obs_normalizer = (
            RunningMeanStd(obs_dim) if cfg.obs_normalization else nn.Identity()
        )
        self.mlp = _build_mlp(
            (obs_dim, *cfg.hidden_dims, action_dim), cfg.activation
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.mlp(self.obs_normalizer(obs))


class Critic(nn.Module):
    """Maps observations to a scalar state value."""

    def __init__(self, obs_dim: int, cfg: NetworkCfg) -> None:
        super().__init__()
        self.obs_normalizer = (
            RunningMeanStd(obs_dim) if cfg.obs_normalization else nn.Identity()
        )
        self.mlp = _build_mlp((obs_dim, *cfg.hidden_dims, 1), cfg.activation)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.mlp(self.obs_normalizer(obs)).squeeze(-1)


class GaussianDistribution:
    """Diagonal Gaussian with a state-independent ``log_std`` parameter.

    A scalar ``log_std`` (one value per action dimension) matches the upstream
    default and keeps the exported graph simple: sampling and the log-prob both
    stay purely algebraic.
    """

    def __init__(self, mean: torch.Tensor, log_std: torch.Tensor) -> None:
        self.mean = mean
        # Clamp the spread so an exploding update cannot produce a degenerate
        # distribution that yields inf log-probs. The clamp keeps the parameter's
        # own shape, so expand it to the batch shape here: otherwise every
        # reduction below loses the batch dimension.
        log_std = torch.clamp(log_std, -5.0, 1.0)
        self.log_std = log_std.expand_as(mean) if log_std.shape != mean.shape else log_std

    @property
    def std(self) -> torch.Tensor:
        return self.log_std.exp()

    def sample(self) -> torch.Tensor:
        return self.mean + self.std * torch.randn_like(self.mean)

    def log_prob(self, value: torch.Tensor) -> torch.Tensor:
        var = self.std**2
        log_scale = self.log_std
        return torch.sum(
            -((value - self.mean) ** 2) / (2 * var)
            - log_scale
            - 0.5 * torch.log(torch.tensor(2 * torch.pi, device=value.device)),
            dim=-1,
        )

    def entropy(self) -> torch.Tensor:
        # Differential entropy of a diagonal Gaussian, summed over dimensions.
        return torch.sum(
            self.log_std
            + 0.5 * torch.log(torch.tensor(2 * torch.pi * torch.e, device=self.mean.device)),
            dim=-1,
        )

    def mode(self) -> torch.Tensor:
        return self.mean


class ActorCritic(nn.Module):
    """Container pairing the actor, critic and the learnable action noise."""

    def __init__(
        self, actor_cfg: NetworkCfg, critic_cfg: NetworkCfg, obs_dim: int,
        critic_obs_dim: int, action_dim: int,
    ) -> None:
        super().__init__()
        self.actor = Actor(obs_dim, action_dim, actor_cfg)
        self.critic = Critic(critic_obs_dim, critic_cfg)
        self.log_std = nn.Parameter(torch.zeros(action_dim))

    def distribution(self, obs: torch.Tensor) -> GaussianDistribution:
        return GaussianDistribution(self.actor(obs), self.log_std)

    def act(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Sample an action and return it with its log-probability."""
        dist = self.distribution(obs)
        action = dist.sample()
        return action, dist.log_prob(action)

    def evaluate(
        self, obs: torch.Tensor, critic_obs: torch.Tensor, action: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return log-prob, entropy, value and the action mean for a rehearsal."""
        dist = self.distribution(obs)
        return dist.log_prob(action), dist.entropy(), self.critic(critic_obs), dist.mean
