# Copyright (c) 2026-2027 zh
"""
内容：
    提供 CyberDuck V2 裁剪后的历史动作及四个滚轮接地状态观测。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def clipped_last_action(env: ManagerBasedRlEnv) -> torch.Tensor:
    """按腿位置、踝速度顺序返回上一控制帧的裁剪动作，形状为环境数×10。"""
    return torch.cat(
        (
            env.action_manager.get_term("joint_pos").raw_action,
            env.action_manager.get_term("joint_vel").raw_action,
        ),
        dim=-1,
    ).to(dtype=torch.float32)


def wheel_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """按右后、右前、左后、左前顺序返回环境数×4的 float32 接地标志。"""
    return (env.scene[sensor_name].data.found > 0).to(dtype=torch.float32)
