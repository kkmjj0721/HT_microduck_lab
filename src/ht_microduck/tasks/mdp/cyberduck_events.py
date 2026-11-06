# Copyright (c) 2026-2027 zh
"""
内容：
    在 CyberDuck V2 环境重置后恢复全部默认位置与速度控制目标。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def reset_control_targets(
    env: ManagerBasedRlEnv, env_ids: torch.Tensor | None
) -> None:
    """仅恢复被重置环境的 HOME 与零速目标；历史由 mjlab 的实体和动作管理器重置。"""
    robot = env.scene["robot"]
    selected = slice(None) if env_ids is None else env_ids
    robot.set_joint_position_target(robot.data.default_joint_pos[selected], env_ids=env_ids)
    robot.set_joint_velocity_target(robot.data.default_joint_vel[selected], env_ids=env_ids)
