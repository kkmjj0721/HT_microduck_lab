# Copyright (c) 2026-2027 zh
"""
内容：
    提供 CyberDuck 主动轮行的跟踪、停车、支撑容许带与分组目标变化代价。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.manager_base import ManagerTermBase
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def position_deviation_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg
) -> torch.Tensor:
    """计算所选位置关节相对 HOME 的平均平方误差，单位 rad²，不包含连续踝角。"""
    robot = env.scene[asset_cfg.name]
    deviation = (
        robot.data.joint_pos[:, asset_cfg.joint_ids]
        - robot.data.default_joint_pos[:, asset_cfg.joint_ids]
    )
    return torch.square(deviation).mean(dim=-1)


def nonwheel_ground_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """任何非滚轮碰撞体触地时返回 1，其余为 0。"""
    return (env.scene[sensor_name].data.found > 0).any(dim=-1).to(dtype=torch.float32)


def track_planar_velocity_exp(env: ManagerBasedRlEnv, command_name: str, std: float) -> torch.Tensor:
    """仅比较机体系水平线速度，垂直运动不混入主任务的速度误差。"""
    error = env.command_manager.get_command(command_name)[:, :2] - env.scene["robot"].data.root_link_lin_vel_b[:, :2]
    return torch.exp(-torch.square(error).sum(dim=-1) / std**2)


def track_yaw_velocity_exp(env: ManagerBasedRlEnv, command_name: str, std: float) -> torch.Tensor:
    """比较机体系偏航角速度，轮子空转不提供跟踪奖励。"""
    error = env.command_manager.get_command(command_name)[:, 2] - env.scene["robot"].data.root_link_ang_vel_b[:, 2]
    return torch.exp(-torch.square(error) / std**2)


def zero_command_motion(
    env: ManagerBasedRlEnv, command_name: str, linear_scale: float, angular_scale: float
) -> torch.Tensor:
    """零有效指令时对残余三轴平动/转动返回 [0,1] 平滑代价，避免大惩罚淹没跟踪。"""
    stopped = (env.command_manager.get_command(command_name).abs() <= 1.0e-6).all(dim=-1)
    data = env.scene["robot"].data
    motion = torch.square(data.root_link_lin_vel_b / linear_scale).sum(dim=-1)
    motion += torch.square(data.root_link_ang_vel_b / angular_scale).sum(dim=-1)
    return stopped * (1.0 - torch.exp(-motion))


def height_band_l2(
    env: ManagerBasedRlEnv, target_height: float, tolerance: float, scale: float
) -> torch.Tensor:
    """相对各环境平面原点的根高，在受载站姿容许带内不惩罚，带外归一化平方。"""
    height = env.scene["robot"].data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    error = (torch.abs(height - target_height) - tolerance).clamp_min(0.0)
    return torch.square(error / scale)


def tilt_band_l2(env: ManagerBasedRlEnv, tolerance: float, scale: float) -> torch.Tensor:
    """倾斜角容许带不约束偏航；单位 rad，严重倾倒由终止项处理。"""
    gravity = env.scene["robot"].data.projected_gravity_b
    tilt = torch.acos((-gravity[:, 2]).clamp(-1.0, 1.0))
    return torch.square((tilt - tolerance).clamp_min(0.0) / scale)


class JointTargetRateL2(ManagerTermBase):
    """按真实下发位置/速度目标的相邻控制帧增量计算代价，分别指定物理归一化尺度。"""

    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(env)
        asset = cfg.params["asset_cfg"]
        self.robot = env.scene[asset.name]
        self.joint_ids = asset.joint_ids
        self.target_type = cfg.params["target_type"]
        if self.target_type not in ("position", "velocity") or cfg.params["scale"] <= 0:
            raise ValueError("Target rate requires position/velocity targets and a positive scale")
        self._default = (
            self.robot.data.default_joint_pos if self.target_type == "position" else self.robot.data.default_joint_vel
        )[:, self.joint_ids]
        self.previous_targets = self._default.clone()

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        self.previous_targets[env_ids] = self._default[env_ids]

    def __call__(
        self, env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg, target_type: str, scale: float
    ) -> torch.Tensor:
        del env, asset_cfg, target_type
        targets = (
            self.robot.data.joint_pos_target if self.target_type == "position" else self.robot.data.joint_vel_target
        )[:, self.joint_ids]
        cost = torch.square((targets - self.previous_targets) / scale).mean(dim=-1)
        self.previous_targets.copy_(targets)
        return cost
