# Copyright (c) 2026-2027 zh
"""
内容：
    为 CyberDuck 主动轮行采样目标速度，并限制策略可见机身指令的变化率。
    观测、奖励和查看器箭头读取同一有效指令，重置从零开始。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch
from mjlab.managers.command_manager import CommandTerm
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


@dataclass(kw_only=True)
class RollingVelocityCommandCfg(UniformVelocityCommandCfg):
    """仅支持机体系速度；变化率依次为 m/s²、m/s²、rad/s²。"""

    max_acceleration: tuple[float, float, float]

    def __post_init__(self):
        super().__post_init__()
        if self.heading_command or self.rel_world_envs or self.rel_forward_envs or self.init_velocity_prob:
            raise ValueError("Rolling velocity commands require body-frame targets without initial velocity overrides")
        if len(self.max_acceleration) != 3 or any(value <= 0 for value in self.max_acceleration):
            raise ValueError("Rolling command acceleration must contain three positive values")

    def build(self, env: ManagerBasedRlEnv) -> RollingVelocityCommand:
        return RollingVelocityCommand(self, env)


class RollingVelocityCommand(UniformVelocityCommand):
    """保留上游采样、计时与查看器，目标重采样不使有效速度发生跳变。"""

    cfg: RollingVelocityCommandCfg

    def __init__(self, cfg: RollingVelocityCommandCfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self.target_velocity_b = torch.zeros_like(self.vel_command_b)
        self._acceleration = torch.tensor(cfg.max_acceleration, device=self.device)
        self._command_dt: float | torch.Tensor = 0.0
        self._update_env_ids: torch.Tensor | None = None

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        effective = self.vel_command_b[env_ids].clone()
        super()._resample_command(env_ids)
        self.target_velocity_b[env_ids] = self.vel_command_b[env_ids]
        self.target_velocity_b[env_ids[self.is_standing_env[env_ids]]] = 0.0
        self.vel_command_b[env_ids] = effective

    def reset(self, env_ids: torch.Tensor | slice | None) -> dict[str, float]:
        self.vel_command_b[env_ids] = 0.0
        self.target_velocity_b[env_ids] = 0.0
        return super().reset(env_ids)

    def compute(self, dt: float | torch.Tensor, env_ids: torch.Tensor | None = None) -> None:
        self._command_dt = dt
        self._update_env_ids = env_ids
        # 避免上游在 compute 末尾将 GUI 值直接写入有效指令，交互目标也必须经过限速。
        CommandTerm.compute(self, dt, env_ids)

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        selected = slice(None) if env_ids is None else env_ids
        if self._joystick_enabled is not None and self._joystick_enabled.value:
            index = self._joystick_get_env_idx()
            if env_ids is None or (env_ids == index).any():
                self.target_velocity_b[index] = torch.tensor(
                    [slider.value for slider in self._joystick_sliders], device=self.device
                )
                ranges = self.cfg.ranges
                for axis, limits in enumerate((ranges.lin_vel_x, ranges.lin_vel_y, ranges.ang_vel_z)):
                    self.target_velocity_b[index, axis].clamp_(*limits)
        dt = self._command_dt
        if isinstance(dt, torch.Tensor):
            dt = dt[selected, None]
        maximum_delta = self._acceleration * dt
        delta = self.target_velocity_b[selected] - self.vel_command_b[selected]
        self.vel_command_b[selected] += torch.clamp(delta, min=-maximum_delta, max=maximum_delta)

    def _update_metrics(self) -> None:
        # reset 的 dt=0 路径不重复累计指标，自动重置的零 dt 环境同样不计。
        fraction = self._command_dt / self.cfg.resampling_time_range[1]
        if self._update_env_ids is not None:
            scoped_fraction = torch.zeros_like(self.time_left)
            scoped_fraction[self._update_env_ids] = fraction
            fraction = scoped_fraction
        self.metrics["error_vel_xy"] += torch.linalg.vector_norm(
            self.vel_command_b[:, :2] - self.robot.data.root_link_lin_vel_b[:, :2], dim=-1
        ) * fraction
        self.metrics["error_vel_yaw"] += (
            self.vel_command_b[:, 2] - self.robot.data.root_link_ang_vel_b[:, 2]
        ).abs() * fraction
