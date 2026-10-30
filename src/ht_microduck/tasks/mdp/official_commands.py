# Copyright (c) 2026-2027 zh
"""内容：
    迁入 MicroDuck 官方的命令采样规则，隔离保留现有 VelStand 行为。

参考：pollen-robotics/microduck_rl，提交 bae39f5900b318f7e87fc485c30a31213cfa14eb，
src/mjlab_microduck/tasks/mdp.py；摘录的上游实现与说明按原文保留，许可 Apache-2.0。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import torch
from mjlab.managers.command_manager import CommandTerm, CommandTermCfg
from mjlab.tasks.velocity.mdp.velocity_command import (
    UniformVelocityCommand,
    UniformVelocityCommandCfg,
)
from mjlab.utils.lab_api.math import matrix_from_quat

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.viewer.debug_visualizer import DebugVisualizer


class VelocityCommandCommandOnly(UniformVelocityCommand):
    """Like UniformVelocityCommand but only draws the command arrows (no actual velocity arrows)."""

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        super()._resample_command(env_ids)
        # mjlab 1.3 即使初始化速度概率为零，也抽取一次随机数；保留官方桶抽样序列。
        if self.cfg.init_velocity_prob == 0.0:
            torch.empty(len(env_ids), device=self.device).uniform_(0.0, 1.0)
        # Turn-in-place practice: for a fraction of envs, zero the linear velocity
        # and force a meaningful (away-from-zero) yaw command. Independent uniform
        # sampling almost never produces "lin≈0, |ang| large" (~2% of samples), so
        # spinning on the spot was effectively untrained → slow/unstable real-robot
        # turning. Mirrors the base rel_forward_envs mechanism.
        p = getattr(self.cfg, "rel_turn_in_place_envs", 0.0)
        if p <= 0.0:
            return
        r = torch.empty(len(env_ids), device=self.device)
        turn_ids = env_ids[r.uniform_(0.0, 1.0) < p]
        if len(turn_ids) == 0:
            return
        self.vel_command_b[turn_ids, 0] = 0.0
        self.vel_command_b[turn_ids, 1] = 0.0
        lo, hi = self.cfg.ranges.ang_vel_z
        maxr = max(abs(lo), abs(hi))
        rr = torch.empty(len(turn_ids), device=self.device)
        sign = torch.where(rr.uniform_(0.0, 1.0) < 0.5, -1.0, 1.0)
        lo_frac = getattr(self.cfg, "turn_in_place_min_frac", 0.4)
        mag = torch.empty(len(turn_ids), device=self.device).uniform_(lo_frac * maxr, maxr)
        self.vel_command_b[turn_ids, 2] = sign * mag
        # These envs must actually turn — un-mark them as standing (which would
        # zero the command) and refresh the world-frame reference copy.
        self.is_standing_env[turn_ids] = False
        self.vel_command_w[turn_ids] = self.vel_command_b[turn_ids]

    def _debug_vis_impl(self, visualizer: "DebugVisualizer") -> None:
        batch = visualizer.env_idx
        if batch >= self.num_envs:
            return

        cmds = self.command.cpu().numpy()
        base_pos_ws = self.robot.data.root_link_pos_w.cpu().numpy()
        base_quat_w = self.robot.data.root_link_quat_w
        base_mat_ws = matrix_from_quat(base_quat_w).cpu().numpy()

        base_pos_w = base_pos_ws[batch]
        base_mat_w = base_mat_ws[batch]
        cmd = cmds[batch]

        if np.linalg.norm(base_pos_w) < 1e-6:
            return

        def local_to_world(vec: np.ndarray) -> np.ndarray:
            return base_pos_w + base_mat_w @ vec

        scale = self.cfg.viz.scale * 2.0
        z_offset = self.cfg.viz.z_offset

        # Command linear velocity arrow (blue).
        cmd_lin_from = local_to_world(np.array([0, 0, z_offset]) * scale)
        cmd_lin_to = local_to_world(
            (np.array([0, 0, z_offset]) + np.array([cmd[0], cmd[1], 0])) * scale
        )
        visualizer.add_arrow(cmd_lin_from, cmd_lin_to, color=(0.2, 0.2, 0.6, 0.6), width=0.015)


@dataclass(kw_only=True)
class VelocityCommandCommandOnlyCfg(UniformVelocityCommandCfg):
    # Fraction of envs commanded to turn in place (lin=0, |ang| forced to
    # [0.4·max, max]) each resample. 0 = disabled (base uniform sampling only).
    rel_turn_in_place_envs: float = 0.0
    # Lower bound of the forced turn-in-place |wz|, as a fraction of the range max.
    # 0.4 (historical) means in-place yaw below 0.4 rad/s is never trained (standing
    # envs zero the whole command; uniform sampling never gives lin == 0).
    turn_in_place_min_frac: float = 0.4

    def build(self, env: ManagerBasedRlEnv) -> "VelocityCommandCommandOnly":
        return VelocityCommandCommandOnly(self, env)


class UniformPoseCommand(CommandTerm):
    """Generic N-dim uniform pose command.

    Samples each dim independently uniform in cfg.ranges[i] = (lo, hi) and holds
    the value between resamples. No metrics, no debug viz — keep it lightweight
    since we have many of these.
    """

    cfg: "UniformPoseCommandCfg"

    def __init__(self, cfg: "UniformPoseCommandCfg", env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self.dim = len(cfg.ranges)
        self._command = torch.zeros(self.num_envs, self.dim, device=self.device)

    @property
    def command(self) -> torch.Tensor:
        return self._command

    def _update_metrics(self) -> None:
        pass

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        del env_ids

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        r = torch.empty(n, device=self.device)
        for i, (lo, hi) in enumerate(self.cfg.ranges):
            self._command[env_ids, i] = r.uniform_(lo, hi)
        # Explicit zero-command bucket. Uniform sampling essentially never
        # produces the all-zero command, so the deployment idle case ("hold the
        # nominal pose") would otherwise be absent from training (velocity
        # body-control run-1 lesson: the policy only stood still when a command
        # was present).
        if self.cfg.zero_command_prob > 0.0:
            zero_mask = torch.rand(n, device=self.device) < self.cfg.zero_command_prob
            self._command[env_ids[zero_mask]] = 0.0


@dataclass(kw_only=True)
class UniformPoseCommandCfg(CommandTermCfg):
    """Per-dim uniform ranges; builds a UniformPoseCommand."""
    # Tuple of (lo, hi) per dim. Length defines the command dim.
    ranges: tuple[tuple[float, float], ...] = ()
    # Probability that a resample yields the exact all-zero command.
    zero_command_prob: float = 0.0

    @property
    def dim(self) -> int:
        """维度由官方 ranges 定义，不额外补零。"""
        return len(self.ranges)

    def build(self, env: ManagerBasedRlEnv) -> "UniformPoseCommand":
        return UniformPoseCommand(self, env)

