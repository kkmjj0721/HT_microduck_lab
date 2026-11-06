# Copyright (c) 2026-2027 zh
"""
内容：
    将 CyberDuck V2 四个滚轮的接地状态转换为 critic 特权观测。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def wheel_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """按右后、右前、左后、左前顺序返回环境数×4的 float32 接地标志。"""
    return (env.scene[sensor_name].data.found > 0).to(dtype=torch.float32)
