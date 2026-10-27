"""Tests for the training runner.

These use a tiny stand-in environment rather than MuJoCo so they stay fast and
run inside ``make check``. The real environment is exercised separately by
``tools/check_velocity_env.py`` and the GPU smoke run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from ht_microduck.algorithms.networks import NetworkCfg
from ht_microduck.algorithms.ppo import PpoCfg
from ht_microduck.algorithms.runner import OnPolicyRunner, TrainCfg, write_metrics
from ht_microduck.tasks.common import contract as C


class _FakeEnv:
    """Minimal environment matching the mjlab step/reset interface."""

    def __init__(self, num_envs: int = 4) -> None:
        self.num_envs = num_envs
        self.step_count = 0

    def reset(self) -> tuple[dict[str, torch.Tensor], dict]:
        self.step_count = 0
        return self._obs(), {}

    def _obs(self) -> dict[str, torch.Tensor]:
        return {
            "actor": torch.randn(self.num_envs, C.ACTOR_OBSERVATION_DIM),
            "critic": torch.randn(self.num_envs, C.CRITIC_OBSERVATION_DIM),
        }

    def step(self, action: torch.Tensor):
        if action.shape != (self.num_envs, C.ACTION_DIM):
            raise AssertionError(f"Bad action shape {tuple(action.shape)}")
        self.step_count += 1
        reward = torch.randn(self.num_envs)
        terminated = torch.zeros(self.num_envs, dtype=torch.bool)
        # Force a timeout every 5 steps in the first world only.
        truncated = torch.zeros(self.num_envs, dtype=torch.bool)
        if self.step_count % 5 == 0:
            truncated[0] = True
        return self._obs(), reward, terminated, truncated, {}


def _cfg(**overrides) -> TrainCfg:
    base = dict(
        num_envs=4,
        num_iterations=2,
        seed=0,
        device="cpu",
        actor=NetworkCfg(hidden_dims=(16, 8)),
        critic=NetworkCfg(hidden_dims=(16, 8)),
        ppo=PpoCfg(num_steps_per_env=4, num_learning_epochs=1, num_mini_batches=2),
    )
    base.update(overrides)
    return TrainCfg(**base)


def test_runner_collects_the_configured_number_of_steps():
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    runner.collect()
    assert runner.storage.step == 4


def test_runner_iteration_produces_finite_metrics():
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    metrics = runner.train_step()
    assert runner.iteration == 1
    for key in ("rollout/mean_reward", "train/policy_loss", "train/value_loss"):
        assert torch.isfinite(torch.tensor(metrics[key])), key
    assert metrics["train/learning_rate"] > 0


def test_runner_updates_the_observation_normalizers():
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    before = float(runner.model.actor.obs_normalizer.count)
    runner.train_step()
    after = float(runner.model.actor.obs_normalizer.count)
    assert after > before, "Observation normaliser was never updated."
    assert float(runner.model.critic.obs_normalizer.count) > before


def test_runner_records_completed_episodes():
    runner = OnPolicyRunner(_FakeEnv(), _cfg(ppo=PpoCfg(num_steps_per_env=6)))
    runner.collect()
    # The fake env truncates world 0 every 5 steps, so one episode finished.
    assert runner.completed_returns, "No episode was recorded on truncation."


def test_checkpoint_roundtrip_restores_the_weights_and_iteration(tmp_path: Path):
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    runner.train_step()
    path = tmp_path / "ckpt.pt"
    runner.save(path)

    fresh = OnPolicyRunner(_FakeEnv(), _cfg())
    fresh.load(path)
    assert fresh.iteration == runner.iteration
    for (name, a), (_, b) in zip(
        runner.model.state_dict().items(), fresh.model.state_dict().items()
    ):
        assert torch.equal(a, b), name


def test_checkpoint_records_the_contract():
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    payload = runner.checkpoint()
    assert payload["contract"]["actor_obs_dim"] == C.ACTOR_OBSERVATION_DIM
    assert payload["contract"]["critic_obs_dim"] == C.CRITIC_OBSERVATION_DIM
    assert payload["contract"]["action_dim"] == C.ACTION_DIM
    assert payload["contract"]["action_terms"] == list(C.POLICY_JOINT_NAMES)
    assert payload["contract"]["control_hz"] == C.CONTROL_HZ
    assert payload["contract"]["action_scale"] == C.ACTION_SCALE


def test_loading_a_checkpoint_with_a_different_observation_size_fails(
    tmp_path: Path,
):
    """A stale checkpoint must be rejected, not silently reshaped."""
    runner = OnPolicyRunner(_FakeEnv(), _cfg())
    payload = runner.checkpoint()
    payload["contract"]["actor_obs_dim"] = 999
    path = tmp_path / "stale.pt"
    torch.save(payload, path)

    fresh = OnPolicyRunner(_FakeEnv(), _cfg())
    with pytest.raises(ValueError, match="does not match the current contract"):
        fresh.load(path)


def test_seed_makes_the_initial_weights_reproducible():
    a = OnPolicyRunner(_FakeEnv(), _cfg(seed=7))
    b = OnPolicyRunner(_FakeEnv(), _cfg(seed=7))
    for (name, pa), (_, pb) in zip(
        a.model.state_dict().items(), b.model.state_dict().items()
    ):
        assert torch.equal(pa, pb), name


def test_write_metrics_appends_one_json_line(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    write_metrics(path, {"a": 1.0, "b": 2.0})
    write_metrics(path, {"a": 3.0, "b": 4.0})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert '"a": 1.0' in lines[0]
    assert '"a": 3.0' in lines[1]
