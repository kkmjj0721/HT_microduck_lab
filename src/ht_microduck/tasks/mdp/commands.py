"""Command terms for the pose slots shared by every HT-Duck task.

Two slots beyond ``twist`` are part of the frozen 61-D-style observation contract:
``head_pose`` (4 joint deltas from HOME) and ``body_pose`` (6 trunk deltas). Tasks
that do not drive a slot still declare it and fill it with zeros, so these terms
only need to exist for the tasks that do.

The sampling rule both terms share is the one upstream learned the hard way: a
uniform sample of an N-dimensional box essentially never produces the all-zero
command, so a policy trained only on uniform samples never sees the deployment
idle case ("hold the nominal pose"). ``zero_command_prob`` reserves a share of
resamples for exactly zero, and ``axis_zero_prob`` does the same per axis for the
body pose, where holding one axis still while moving another is a distinct skill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import torch
from mjlab.managers.command_manager import CommandTerm, CommandTermCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


# Fixed width of every command slot in the actor observation. The widths are part of
# the frozen contract (``contract.ACTOR_OBSERVATION_DIMS``): a slot that a task does
# not drive is *padded with zeros*, never narrowed, because a narrower vector would
# change the observation dimension and break policy hot-swapping at runtime.
TWIST_DIM = 3
HEAD_POSE_DIM = 4
BODY_POSE_DIM = 6


class UniformPoseCommand(CommandTerm):
    """N-dimensional pose command, each axis uniform within its own range.

    The command width is pinned by the contract, not by the number of ranges: a task
    that commands fewer axes still publishes a full-width vector with the unused axes
    held at zero. Widths below are enforced against ``time_out``-free slots only; the
    caller must pass a matching ``dim``.
    """

    cfg: "UniformPoseCommandCfg"

    def __init__(self, cfg: "UniformPoseCommandCfg", env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self.dim = cfg.dim
        if cfg.ranges and len(cfg.ranges) > self.dim:
            raise ValueError(
                f"command declares {len(cfg.ranges)} ranges but its slot is only "
                f"{self.dim} wide"
            )
        self._command = torch.zeros(self.num_envs, self.dim, device=self.device)

    @property
    def command(self) -> torch.Tensor:
        return self._command

    def _update_metrics(self) -> None:
        """A pose command has no tracking metric worth logging."""

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        """The command only changes on resample."""
        del env_ids

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        for axis, (low, high) in enumerate(self.cfg.ranges):
            sample = torch.empty(n, device=self.device).uniform_(low, high)
            self._command[env_ids, axis] = sample
        if self.cfg.zero_command_prob > 0.0:
            zero = torch.rand(n, device=self.device) < self.cfg.zero_command_prob
            self._command[env_ids[zero]] = 0.0


@dataclass(kw_only=True)
class UniformPoseCommandCfg(CommandTermCfg):
    """Per-axis uniform ranges; the tuple length defines the command dimension."""

    ranges: tuple[tuple[float, float], ...] = ()
    dim: int = 3
    """Width of this command's slot in the observation, padded with zeros."""
    resampling_time_range: tuple[float, float] = (4.0, 8.0)
    zero_command_prob: float = 0.0
    """Probability that a resample yields the exact all-zero command."""

    def build(self, env: ManagerBasedRlEnv) -> UniformPoseCommand:
        return UniformPoseCommand(self, env)


class StandingGatedPoseCommand(UniformPoseCommand):
    """A pose command that is only active while the twist command is standing.

    Body-pose control is a standing feature at deployment: while walking, the
    runtime sends a zero body command. Sampled values live in ``_raw``; the exposed
    command is ``_raw`` masked by the twist term's ``is_standing_env`` and
    re-applied every step, because the twist term can flip an environment between
    standing and walking at its own resample. The twist command must be registered
    before this one — the command manager updates in insertion order.
    """

    cfg: "StandingGatedPoseCommandCfg"

    def __init__(self, cfg: "StandingGatedPoseCommandCfg", env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._raw = torch.zeros_like(self._command)

    def _gate(self) -> None:
        twist = self._env.command_manager.get_term(self.cfg.twist_command_name)
        standing = getattr(twist, "is_standing_env", None)
        if standing is None:
            self._command[:] = 0.0
        else:
            self._command[:] = self._raw * standing.float().unsqueeze(1)

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        del env_ids
        self._gate()

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        super()._resample_command(env_ids)
        raw = self._command[env_ids].clone()
        for axis, probability in enumerate(self.cfg.axis_zero_prob):
            if probability > 0.0:
                zero = torch.rand(n, device=self.device) < probability
                raw[zero, axis] = 0.0
        self._raw[env_ids] = raw
        # Resets do not run _update_command, so re-gate here to keep the
        # walking-zero invariant through a reset.
        self._gate()


@dataclass(kw_only=True)
class StandingGatedPoseCommandCfg(UniformPoseCommandCfg):
    twist_command_name: str = "twist"
    axis_zero_prob: tuple[float, ...] = field(default_factory=tuple)

    def build(self, env: ManagerBasedRlEnv) -> StandingGatedPoseCommand:
        return StandingGatedPoseCommand(self, env)
