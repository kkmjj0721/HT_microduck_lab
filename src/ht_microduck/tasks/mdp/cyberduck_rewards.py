# Copyright (c) 2026-2027 zh
"""
内容：
    提供 CyberDuck V2 的位置关节姿态与非滚轮触地辅助代价。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
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
