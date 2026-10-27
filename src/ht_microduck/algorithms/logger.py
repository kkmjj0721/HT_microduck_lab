"""Training console output aligned with RSL-RL's logger.

The project's own PPO/Runner stay in place: this module only reproduces the
*reporting* shape the official ``microduck_rl`` stack produces, so a run here
looks like a run there. Format and field names follow
``rsl_rl/utils/logger.py`` (rsl_rl_lib 5.4.2) as installed in this environment:

- an 80-column ``#`` header with ``Learning iteration i/total``
- ``Total steps``, ``Steps per second``, ``Collection time``, ``Learning time``
- ``Mean <name> loss`` lines
- ``Mean reward``, ``Mean episode length``, ``Mean action std``
- a footer with ``Iteration time``, ``Time elapsed`` and ``ETA``

The JSONL metrics file is kept as well: the console block is for humans, the
JSONL is what later evaluation and plotting read.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import torch

# One block is 80 columns wide upstream; keep it identical so side-by-side
# comparisons with official logs line up.
WIDTH = 80
PAD = 40


@dataclass
class EpisodeBuffers:
    """Rolling windows of the last 100 completed episodes, as upstream."""

    maxlen: int = 100

    def __post_init__(self) -> None:
        # A plain list is used instead of ``deque`` so the truncation rule is
        # explicit and easy to test.
        self.rewards: list[float] = []
        self.lengths: list[float] = []

    def extend(self, rewards: list[float], lengths: list[float]) -> None:
        if not rewards:
            return
        self.rewards.extend(rewards)
        self.lengths.extend(lengths)
        if len(self.rewards) > self.maxlen:
            self.rewards = self.rewards[-self.maxlen :]
        if len(self.lengths) > self.maxlen:
            self.lengths = self.lengths[-self.maxlen :]


def format_console_block(
    *,
    iteration: int,
    total_iterations: int,
    total_steps: int,
    steps_per_second: float,
    collect_time: float,
    learn_time: float,
    loss_dict: dict[str, float],
    learning_rate: float,
    action_std: float,
    mean_reward: float | None,
    mean_episode_length: float | None,
    elapsed: float,
    eta: float,
    run_name: str | None = None,
    width: int = WIDTH,
    pad: int = PAD,
) -> str:
    """Render one iteration report in the official RSL-RL layout.

    ``mean_reward``/``mean_episode_length`` are ``None`` until at least one
    episode has finished; upstream omits those two lines in that case and so do
    we, rather than printing ``nan``.
    """
    lines = [f"{'#' * width}"]
    lines.append(f"\033[1m{f' Learning iteration {iteration}/{total_iterations} '.center(width)}\033[0m ")
    lines.append("")

    if run_name:
        lines.append(f"{'Run name:':>{pad}} {run_name}")

    lines.append(f"{'Total steps:':>{pad}} {total_steps}")
    lines.append(f"{'Steps per second:':>{pad}} {steps_per_second:.0f}")
    lines.append(f"{'Collection time:':>{pad}} {collect_time:.3f}s")
    lines.append(f"{'Learning time:':>{pad}} {learn_time:.3f}s")

    for key, value in loss_dict.items():
        lines.append(f"{f'Mean {key} loss:':>{pad}} {value:.4f}")

    if mean_reward is not None:
        lines.append(f"{'Mean reward:':>{pad}} {mean_reward:.2f}")
    if mean_episode_length is not None:
        lines.append(f"{'Mean episode length:':>{pad}} {mean_episode_length:.2f}")

    lines.append(f"{'Mean action std:':>{pad}} {action_std:.2f}")
    lines.append(f"{'Learning rate:':>{pad}} {learning_rate:.2e}")

    lines.append(f"{'-' * width}")
    lines.append(f"{'Iteration time:':>{pad}} {collect_time + learn_time:.2f}s")
    lines.append(f"{'Time elapsed:':>{pad}} {timedelta(seconds=int(elapsed))}")
    lines.append(f"{'ETA:':>{pad}} {timedelta(seconds=int(eta))}")
    return "\n".join(lines) + "\n"


class TrainingLogger:
    """Owns the console block, the TensorBoard writer and the JSONL file."""

    def __init__(
        self,
        *,
        log_dir: Path | None,
        metrics_path: Path | None = None,
        enable_tensorboard: bool = True,
        log_interval: int = 1,
        run_name: str | None = None,
    ) -> None:
        self.log_dir = Path(log_dir) if log_dir is not None else None
        self.metrics_path = (
            Path(metrics_path) if metrics_path is not None else (
                self.log_dir / "metrics.jsonl" if self.log_dir is not None else None
            )
        )
        self.log_interval = int(log_interval)
        self.run_name = run_name
        self.episodes = EpisodeBuffers()
        self.total_steps = 0
        self.total_time = 0.0
        self.writer = None

        if enable_tensorboard and self.log_dir is not None:
            try:
                from torch.utils.tensorboard import SummaryWriter
            except ImportError:  # pragma: no cover - optional dependency
                SummaryWriter = None  # type: ignore[assignment]
            if SummaryWriter is not None:
                self.writer = SummaryWriter(log_dir=str(self.log_dir), flush_secs=10)

    # -- episode bookkeeping -------------------------------------------------
    def record_episodes(self, rewards: list[float], lengths: list[float]) -> None:
        self.episodes.extend(rewards, lengths)

    # -- per-iteration report ------------------------------------------------
    def log(
        self,
        *,
        iteration: int,
        total_iterations: int,
        collect_time: float,
        learn_time: float,
        loss_dict: dict[str, float],
        learning_rate: float,
        action_std: torch.Tensor | float,
        metrics: dict[str, float] | None = None,
        num_steps_per_env: int,
        num_envs: int,
        start_iteration: int = 0,
    ) -> str | None:
        """Record one iteration; return the console block when it was printed."""
        collection_size = num_steps_per_env * num_envs
        iteration_time = collect_time + learn_time
        self.total_steps += collection_size
        self.total_time += iteration_time

        std_value = (
            float(action_std.mean())
            if isinstance(action_std, torch.Tensor)
            else float(action_std)
        )
        mean_reward = (
            float(statistics.mean(self.episodes.rewards)) if self.episodes.rewards else None
        )
        mean_length = (
            float(statistics.mean(self.episodes.lengths)) if self.episodes.lengths else None
        )

        if self.writer is not None:
            for key, value in loss_dict.items():
                self.writer.add_scalar(f"Loss/{key}", value, iteration)
            self.writer.add_scalar("Loss/learning_rate", learning_rate, iteration)
            self.writer.add_scalar("Policy/mean_std", std_value, iteration)
            if iteration_time > 0:
                self.writer.add_scalar(
                    "Perf/total_fps", collection_size / iteration_time, iteration
                )
            self.writer.add_scalar("Perf/collection_time", collect_time, iteration)
            self.writer.add_scalar("Perf/learning_time", learn_time, iteration)
            if mean_reward is not None:
                self.writer.add_scalar("Train/mean_reward", mean_reward, iteration)
                self.writer.add_scalar("Train/mean_episode_length", mean_length, iteration)

        if self.metrics_path is not None and metrics is not None:
            self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with self.metrics_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_jsonable(metrics), sort_keys=True) + "\n")

        done = iteration + 1 - start_iteration
        remaining = max(total_iterations - start_iteration - done, 0)
        eta = (self.total_time / done * remaining) if done > 0 else float("nan")

        if self.log_interval and (iteration % self.log_interval == 0):
            block = format_console_block(
                iteration=iteration,
                total_iterations=total_iterations,
                total_steps=self.total_steps,
                steps_per_second=(
                    collection_size / iteration_time if iteration_time > 0 else 0.0
                ),
                collect_time=collect_time,
                learn_time=learn_time,
                loss_dict=loss_dict,
                learning_rate=learning_rate,
                action_std=std_value,
                mean_reward=mean_reward,
                mean_episode_length=mean_length,
                elapsed=self.total_time,
                eta=eta,
                run_name=self.run_name,
            )
            print(block)
            return block
        return None

    def close(self) -> None:
        if self.writer is not None:
            self.writer.flush()
            self.writer.close()
            self.writer = None


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)
