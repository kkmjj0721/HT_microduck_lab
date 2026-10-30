# Copyright (c) 2026-2027 zh
"""统计物理关节目标越界、限幅以及控制帧上的执行器饱和。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.managers.metrics_manager import MetricsTermCfg


def requested_target_violation_fraction(
    env: ManagerBasedRlEnv, action_name: str = "joint_pos"
) -> torch.Tensor:
    """扣除编码器偏置后，请求目标超出硬关节范围的逐环境比例。"""
    term = env.action_manager.get_term(action_name)
    limits = env.scene[term.cfg.entity_name].data.joint_pos_limits[:, term.target_ids]
    targets = term.requested_targets
    outside = (targets < limits[..., 0]) | (targets > limits[..., 1])
    return outside.float().mean(dim=1)


def applied_target_violation_fraction(
    env: ManagerBasedRlEnv, action_name: str = "joint_pos"
) -> torch.Tensor:
    """最终下发目标超出硬关节范围的逐环境比例，正常启用约束时应为零。"""
    term = env.action_manager.get_term(action_name)
    limits = env.scene[term.cfg.entity_name].data.joint_pos_limits[:, term.target_ids]
    targets = term.applied_targets
    outside = (targets < limits[..., 0]) | (targets > limits[..., 1])
    return outside.float().mean(dim=1)


def target_clip_fraction(
    env: ManagerBasedRlEnv, action_name: str = "joint_pos"
) -> torch.Tensor:
    """当前请求中被物理目标约束改变的关节比例；原配方模式下为零。"""
    term = env.action_manager.get_term(action_name)
    return (term.requested_targets != term.applied_targets).float().mean(dim=1)


def _saturated_actuators(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg, ratio: float
) -> torch.Tensor:
    """按力矩符号匹配当前方向包络；每次读取最新桥接字段，不计零包络。"""
    robot = env.scene[asset_cfg.name]
    torque = robot.data.actuator_force[:, asset_cfg.actuator_ids]
    ctrl_ids = robot.indexing.ctrl_ids[asset_cfg.actuator_ids]
    bounds = env.sim.model.actuator_forcerange[:, ctrl_ids]
    capacity = torch.where(torque >= 0, bounds[..., 1], -bounds[..., 0])
    return (capacity > 0) & (torque.abs() >= ratio * capacity)


def actuator_saturation_fraction(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg, ratio: float = 0.95
) -> torch.Tensor:
    """实际力矩达到当前方向包络指定比例的执行器份额，仅作控制帧诊断。"""
    return _saturated_actuators(env, asset_cfg, ratio).float().mean(dim=1)


class ActuatorSaturationDuration:
    """记录控制帧连续饱和秒数；搭配reduce='max'获得回合最长持续时间。"""

    def __init__(self, cfg: MetricsTermCfg, env: ManagerBasedRlEnv):
        asset_cfg = cfg.params["asset_cfg"]
        shape = env.scene[asset_cfg.name].data.actuator_force[:, asset_cfg.actuator_ids].shape
        self._duration = torch.zeros(shape, dtype=torch.float32, device=env.device)

    def __call__(
        self, env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg, ratio: float = 0.95
    ) -> torch.Tensor:
        saturated = _saturated_actuators(env, asset_cfg, ratio)
        self._duration = torch.where(
            saturated, self._duration + env.step_dt, torch.zeros_like(self._duration)
        )
        return self._duration.max(dim=1).values

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        duration = self._duration.clone()
        duration[env_ids] = 0.0
        self._duration = duration
