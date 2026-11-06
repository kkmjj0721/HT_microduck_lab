# Copyright (c) 2026-2027 zh
"""
内容：
    根据实际启用的碰撞对，判定 CyberDuck 躯干触地和自碰撞失败。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch
    from mjlab.envs import ManagerBasedRlEnv


def contact_failure(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """任一匹配碰撞对发生接触即失败；地面由传感器 secondary 显式隔离。"""
    return (env.scene[sensor_name].data.found > 0).any(dim=-1)
