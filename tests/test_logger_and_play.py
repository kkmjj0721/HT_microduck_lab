"""Tests for the RSL-RL style training logger and the play helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from ht_microduck.algorithms.logger import (
    EpisodeBuffers,
    TrainingLogger,
    format_console_block,
)
from ht_microduck.algorithms.networks import ActorCritic, NetworkCfg
from ht_microduck.cli.play import Policy, _filter_network_cfg, find_latest_checkpoint
from ht_microduck.tasks.common import contract as C


def _block(**overrides) -> str:
    kwargs = dict(
        iteration=3,
        total_iterations=10,
        total_steps=384,
        steps_per_second=190.0,
        collect_time=0.63,
        learn_time=0.04,
        loss_dict={"policy": -0.0775, "value": 0.0057, "entropy": 14.17},
        learning_rate=1e-3,
        action_std=1.0,
        mean_reward=12.5,
        mean_episode_length=200.0,
        elapsed=2.0,
        eta=8.0,
    )
    kwargs.update(overrides)
    return format_console_block(**kwargs)


def test_console_block_has_the_official_fields():
    block = _block()
    for field in (
        "Learning iteration 3/10",
        "Total steps:",
        "Steps per second:",
        "Collection time:",
        "Learning time:",
        "Mean policy loss:",
        "Mean value loss:",
        "Mean reward:",
        "Mean episode length:",
        "Mean action std:",
        "Iteration time:",
        "Time elapsed:",
        "ETA:",
    ):
        assert field in block


def test_console_block_banner_is_eighty_columns():
    first_line = _block().splitlines()[0]
    assert first_line == "#" * 80


def test_console_block_omits_episode_lines_before_any_episode_finishes():
    block = _block(mean_reward=None, mean_episode_length=None)
    assert "Mean reward:" not in block
    assert "Mean episode length:" not in block
    assert "Mean action std:" in block


def test_episode_buffers_keep_only_the_last_hundred():
    buffers = EpisodeBuffers()
    buffers.extend(list(range(150)), list(range(150)))
    assert len(buffers.rewards) == 100
    assert buffers.rewards[0] == 50.0
    assert buffers.lengths[-1] == 149.0


def test_episode_buffers_ignore_empty_updates():
    buffers = EpisodeBuffers()
    buffers.extend([], [])
    assert buffers.rewards == []


def _logger(tmp_path: Path, log_interval: int = 1) -> TrainingLogger:
    return TrainingLogger(
        log_dir=tmp_path,
        enable_tensorboard=False,
        log_interval=log_interval,
    )


def test_logger_writes_one_json_line_per_iteration(tmp_path: Path):
    logger = _logger(tmp_path)
    for iteration in range(2):
        logger.log(
            iteration=iteration,
            total_iterations=2,
            collect_time=0.1,
            learn_time=0.05,
            loss_dict={"policy": 0.1},
            learning_rate=1e-3,
            action_std=torch.ones(2),
            metrics={"train/iteration": float(iteration)},
            num_steps_per_env=4,
            num_envs=2,
        )
    lines = (tmp_path / "metrics.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["train/iteration"] == 1.0


def test_logger_accumulates_total_steps(tmp_path: Path):
    logger = _logger(tmp_path)
    for iteration in range(3):
        logger.log(
            iteration=iteration,
            total_iterations=3,
            collect_time=0.1,
            learn_time=0.05,
            loss_dict={"policy": 0.1},
            learning_rate=1e-3,
            action_std=torch.ones(2),
            num_steps_per_env=4,
            num_envs=2,
        )
    # 4 steps x 2 envs x 3 iterations.
    assert logger.total_steps == 24


def test_logger_respects_log_interval(tmp_path: Path, capsys):
    logger = _logger(tmp_path, log_interval=2)
    printed = [
        logger.log(
            iteration=iteration,
            total_iterations=4,
            collect_time=0.1,
            learn_time=0.05,
            loss_dict={"policy": 0.1},
            learning_rate=1e-3,
            action_std=torch.ones(2),
            num_steps_per_env=4,
            num_envs=2,
        )
        for iteration in range(1, 4)
    ]
    assert [block is not None for block in printed] == [False, True, False]


def _checkpoint(tmp_path: Path, actor: NetworkCfg | None = None) -> Path:
    model = ActorCritic(
        actor or NetworkCfg(hidden_dims=(8, 4)),
        NetworkCfg(hidden_dims=(8, 4)),
        C.ACTOR_OBSERVATION_DIM,
        C.CRITIC_OBSERVATION_DIM,
        C.ACTION_DIM,
    )
    path = tmp_path / "model_1.pt"
    torch.save(
        {
            "model": model.state_dict(),
            "optimizer": {},
            "iteration": 1,
            "learning_rate": 1e-3,
            "cfg": {
                "actor": {"hidden_dims": (8, 4)},
                "critic": {"hidden_dims": (8, 4)},
            },
            "contract": {"actor_obs_dim": C.ACTOR_OBSERVATION_DIM},
        },
        path,
    )
    return path


def test_network_cfg_filter_keeps_only_known_fields():
    filtered = _filter_network_cfg(
        {"hidden_dims": [8, 4], "activation": "elu", "unknown": 1}
    )
    assert "unknown" not in filtered
    assert filtered["hidden_dims"] == (8, 4)


def test_play_policy_returns_zero_and_random_actions():
    zero = Policy("zero", None, C.ACTION_DIM)
    obs = torch.randn(3, C.ACTOR_OBSERVATION_DIM)
    assert torch.all(zero(obs) == 0)

    random = Policy("random", None, C.ACTION_DIM)
    actions = random(obs)
    assert actions.shape == (3, C.ACTION_DIM)
    assert not torch.all(actions == 0)


def test_play_policy_trained_is_deterministic(tmp_path: Path):
    from ht_microduck.cli.play import load_model

    checkpoint = _checkpoint(tmp_path)
    model = load_model(checkpoint, "cpu")
    policy = Policy("trained", model, C.ACTION_DIM).to(torch.device("cpu"))
    obs = torch.randn(2, C.ACTOR_OBSERVATION_DIM)
    assert torch.allclose(policy(obs), policy(obs))


def test_find_latest_checkpoint_prefers_the_newest_run(tmp_path: Path):
    experiment = tmp_path / "flat_velocity"
    old = experiment / "2026-01-01_00-00-00"
    new = experiment / "2026-01-02_00-00-00"
    for run, iteration in ((old, 1), (new, 7)):
        run.mkdir(parents=True)
        (run / f"model_{iteration}.pt").write_bytes(b"")
    assert find_latest_checkpoint(tmp_path, "flat_velocity") == new / "model_7.pt"


def test_find_latest_checkpoint_errors_without_runs(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        find_latest_checkpoint(tmp_path, "flat_velocity")


def test_logger_eta_counts_from_the_resume_iteration(tmp_path: Path):
    """A resumed run's ETA must cover only the remaining iterations."""
    logger = _logger(tmp_path)
    blocks = []
    for iteration in (11, 12):
        blocks.append(
            logger.log(
                iteration=iteration,
                total_iterations=12,
                collect_time=1.0,
                learn_time=0.0,
                loss_dict={"policy": 0.1},
                learning_rate=1e-3,
                action_std=torch.ones(2),
                num_steps_per_env=4,
                num_envs=2,
                start_iteration=10,
            )
        )
    # Two iterations ran, two of two were done, so nothing is left.
    assert "ETA: 0:00:00" in blocks[-1]
    assert "Learning iteration 12/12" in blocks[-1]
