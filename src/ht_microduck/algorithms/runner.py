"""Training loop tying the environment, storage and PPO together.

The runner owns the environment, the model, the optimiser and the logging. It is
deliberately explicit: one iteration is "roll out N steps in every world, compute
GAE, update". Anything that needs to be reproducible (seed, checkpoint contents,
logged metrics) is recorded here rather than inferred later.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch

from ht_microduck.algorithms.networks import ActorCritic, NetworkCfg
from ht_microduck.algorithms.ppo import PpoCfg, PpoUpdater
from ht_microduck.algorithms.storage import RolloutStorage
from ht_microduck.tasks.common import contract as C


@dataclass(kw_only=True)
class TrainCfg:
    """Everything needed to reproduce one training run."""

    num_envs: int = 4096
    num_iterations: int = 100
    seed: int = 0
    device: str = "cuda:0"
    save_interval: int = 50
    log_interval: int = 1
    experiment_name: str = "flat_velocity"
    """Grouping directory under ``out_dir``; matches upstream ``experiment_name``."""
    run_name: str = ""
    """Optional suffix on the timestamped run directory."""
    actor: NetworkCfg = field(default_factory=NetworkCfg)
    critic: NetworkCfg = field(default_factory=NetworkCfg)
    ppo: PpoCfg = field(default_factory=PpoCfg)
    out_dir: str = "runs"


def _to_jsonable(value):
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


class OnPolicyRunner:
    """Rollout + PPO update loop for a single task."""

    def __init__(self, env, cfg: TrainCfg) -> None:
        self.env = env
        self.cfg = cfg
        self.device = torch.device(cfg.device)

        torch.manual_seed(cfg.seed)
        self.model = ActorCritic(
            cfg.actor,
            cfg.critic,
            C.ACTOR_OBSERVATION_DIM,
            C.CRITIC_OBSERVATION_DIM,
            C.ACTION_DIM,
        ).to(self.device)
        self.updater = PpoUpdater(self.model, cfg.ppo)
        self.storage = RolloutStorage(
            num_steps=cfg.ppo.num_steps_per_env,
            num_envs=env.num_envs,
            obs_dim=C.ACTOR_OBSERVATION_DIM,
            critic_obs_dim=C.CRITIC_OBSERVATION_DIM,
            action_dim=C.ACTION_DIM,
            device=self.device,
        )
        self.generator = torch.Generator(device=self.device)
        self.generator.manual_seed(cfg.seed)
        self.iteration = 0
        self.obs, _ = env.reset()
        self.episode_returns = torch.zeros(env.num_envs, device=self.device)
        self.episode_lengths = torch.zeros(env.num_envs, device=self.device)
        self.completed_returns: list[float] = []
        self.completed_lengths: list[float] = []
        # Episodes finished during the most recent ``collect()``.
        self.new_returns: list[float] = []
        self.new_lengths: list[float] = []
        # Last iteration's diagnostics, split so the console logger can print
        # RSL-RL style "Mean <name> loss" lines.
        self.last_update_metrics: dict[str, float] = {}

    # -- rollout -----------------------------------------------------------
    def collect(self) -> dict[str, float]:
        """Roll out ``num_steps_per_env`` steps in every world."""
        self.storage.clear()
        # Episodes that finished during *this* collection; the console logger
        # keeps its own 100-episode window from these, matching upstream.
        self.new_returns: list[float] = []
        self.new_lengths: list[float] = []
        for _ in range(self.cfg.ppo.num_steps_per_env):
            with torch.no_grad():
                action, log_prob = self.model.act(self.obs["actor"])
                value = self.model.critic(self.obs["critic"])
            env_obs, reward, terminated, truncated, _ = self.env.step(action)
            done = terminated | truncated
            self.storage.add(
                obs=self.obs["actor"],
                critic_obs=self.obs["critic"],
                actions=action,
                log_prob=log_prob,
                values=value,
                rewards=reward,
                dones=done,
                time_outs=truncated,
            )
            self.episode_returns += reward
            self.episode_lengths += 1
            for index in torch.nonzero(done).flatten().tolist():
                self.completed_returns.append(float(self.episode_returns[index]))
                self.completed_lengths.append(float(self.episode_lengths[index]))
                self.new_returns.append(float(self.episode_returns[index]))
                self.new_lengths.append(float(self.episode_lengths[index]))
                self.episode_returns[index] = 0.0
                self.episode_lengths[index] = 0.0
            self.obs = env_obs

        # Refresh the observation statistics from the rollout that was just
        # collected. Without this the normalisers stay at mean 0 / var 1 and the
        # scale of joint velocities and actions never adapts.
        self._update_normalizers()

        with torch.no_grad():
            last_values = self.model.critic(self.obs["critic"])
        self.storage.compute_returns(
            last_values=last_values,
            gamma=self.cfg.ppo.gamma,
            lam=self.cfg.ppo.lam,
        )
        return self._rollout_metrics()

    def _update_normalizers(self) -> None:
        """Feed the collected observations to the running statistics."""
        actor_norm = self.model.actor.obs_normalizer
        critic_norm = self.model.critic.obs_normalizer
        if hasattr(actor_norm, "update"):
            actor_norm.update(self.storage.obs.reshape(-1, C.ACTOR_OBSERVATION_DIM))
        if hasattr(critic_norm, "update"):
            critic_norm.update(
                self.storage.critic_obs.reshape(-1, C.CRITIC_OBSERVATION_DIM)
            )

    def _rollout_metrics(self) -> dict[str, float]:
        rewards = self.storage.rewards
        dones = self.storage.dones
        metrics = {
            "rollout/mean_reward": float(rewards.mean()),
            "rollout/mean_value": float(self.storage.values.mean()),
            "rollout/mean_advantage": float(self.storage.advantages.mean()),
            "rollout/advantage_std": float(self.storage.advantages.std()),
            "rollout/done_fraction": float(dones.float().mean()),
        }
        if self.completed_returns:
            recent = self.completed_returns[-100:]
            metrics["rollout/episode_return"] = float(sum(recent) / len(recent))
            recent_len = self.completed_lengths[-100:]
            metrics["rollout/episode_length"] = float(
                sum(recent_len) / len(recent_len)
            )
        else:
            metrics["rollout/episode_return"] = float("nan")
            metrics["rollout/episode_length"] = float("nan")
        return metrics

    # -- learning ----------------------------------------------------------
    def train_step(self) -> dict[str, float]:
        """Run one collect + update iteration."""
        start = time.perf_counter()
        metrics = self.collect()
        collect_time = time.perf_counter() - start
        update_start = time.perf_counter()
        update_metrics = self.updater.update(self.storage, generator=self.generator)
        learn_time = time.perf_counter() - update_start
        self.last_update_metrics = dict(update_metrics)
        metrics.update({f"train/{k}": v for k, v in update_metrics.items()})
        metrics["train/iteration"] = float(self.iteration)
        metrics["train/collect_s"] = collect_time
        metrics["train/learn_s"] = learn_time
        metrics["train/elapsed_s"] = time.perf_counter() - start
        self.iteration += 1
        return metrics

    # -- persistence -------------------------------------------------------
    def checkpoint(self) -> dict:
        """State dict plus everything needed to resume exactly."""
        return {
            "model": self.model.state_dict(),
            "optimizer": self.updater.optimizer.state_dict(),
            "iteration": self.iteration,
            "learning_rate": self.updater.learning_rate,
            "cfg": _to_jsonable(asdict(self.cfg)),
            "contract": {
                "actor_obs_dim": C.ACTOR_OBSERVATION_DIM,
                "critic_obs_dim": C.CRITIC_OBSERVATION_DIM,
                "action_dim": C.ACTION_DIM,
                "action_terms": list(C.POLICY_JOINT_NAMES),
                "actor_observation_terms": list(C.ACTOR_OBSERVATION_TERMS),
                "control_hz": C.CONTROL_HZ,
                "action_scale": C.ACTION_SCALE,
            },
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.checkpoint(), path)

    @property
    def action_std(self) -> torch.Tensor:
        """Current per-action standard deviation, for the ``Mean action std`` line."""
        with torch.no_grad():
            return self.model.log_std.detach().exp().clone()

    def load(self, path: Path) -> None:
        payload = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(payload["model"])
        self.updater.optimizer.load_state_dict(payload["optimizer"])
        self.iteration = int(payload["iteration"])
        self.updater.learning_rate = float(payload["learning_rate"])
        for group in self.updater.optimizer.param_groups:
            group["lr"] = self.updater.learning_rate
        saved = payload.get("contract", {})
        if saved.get("actor_obs_dim") != C.ACTOR_OBSERVATION_DIM:
            raise ValueError(
                "Checkpoint observation size does not match the current contract; "
                "retrain rather than silently reshaping the network."
            )


def write_metrics(path: Path, metrics: dict[str, float]) -> None:
    """Append one JSON line per iteration so a crash keeps earlier data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_to_jsonable(metrics)) + "\n")
