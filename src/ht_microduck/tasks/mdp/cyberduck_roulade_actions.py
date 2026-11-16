# Copyright (c) 2026-2027 zh
"""
内容：
    按各关节实际行程平滑映射前滚翻位置动作，零动作对应 HOME。

网络输出为无量纲潜变量；目标为 mid + half * tanh(action + atanh((HOME-mid)/half))。
编码器偏置补偿和最终硬限位沿用项目位置动作，踝速度不在本模块处理。
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from mjlab.envs import ManagerBasedRlEnv

from ht_microduck.tasks.mdp.actions import (
    BoundedJointPositionAction,
    BoundedJointPositionActionCfg,
)


@dataclass(kw_only=True)
class RouladePositionActionCfg(BoundedJointPositionActionCfg):
    """位置动作不做原始硬裁剪，物理行程由实体关节范围决定。"""

    raw_action_limit: None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if (self.scale != 1.0 or self.offset != 0.0 or not self.use_default_offset
                or self.clip is not None or not self.bound_targets or self.raw_action_limit is not None):
            raise ValueError("Roulade tanh mapping requires its fixed HOME/range configuration")

    def build(self, env: ManagerBasedRlEnv) -> RouladePositionAction:
        return RouladePositionAction(self, env)


class RouladePositionAction(BoundedJointPositionAction):
    """保留网络原始动作，避免窄行程关节的大段输出映射到同一限位。"""

    cfg: RouladePositionActionCfg

    def __init__(self, cfg: RouladePositionActionCfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        limits = self._entity.data.joint_pos_limits[:, self._target_ids]
        self._midpoint = limits.mean(dim=-1)
        self._half_range = (limits[..., 1] - limits[..., 0]) * 0.5
        home = self._entity.data.default_joint_pos[:, self._target_ids]
        relative_home = (home - self._midpoint) / self._half_range
        if not torch.isfinite(limits).all() or not (relative_home.abs() < 1).all():
            raise ValueError("Roulade position mapping requires finite limits and an interior HOME")
        self.latent_offset = torch.atanh(relative_home)

    def process_actions(self, actions: torch.Tensor) -> None:
        self._raw_actions.copy_(actions)
        self._processed_actions.copy_(
            self._midpoint + self._half_range * torch.tanh(actions + self.latent_offset)
        )
