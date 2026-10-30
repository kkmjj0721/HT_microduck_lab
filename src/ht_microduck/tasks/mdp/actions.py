# Copyright (c) 2026-2027 zh
"""在编码器偏置补偿后，按实体硬关节范围约束策略的位置目标。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch
from mjlab.envs.mdp.actions import JointPositionAction, JointPositionActionCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


@dataclass(kw_only=True)
class BoundedJointPositionActionCfg(JointPositionActionCfg):
    """保留原始动作映射，可显式关闭物理目标约束以运行原配方对照。"""

    bound_targets: bool = True

    def build(self, env: ManagerBasedRlEnv) -> BoundedJointPositionAction:
        return BoundedJointPositionAction(self, env)


class BoundedJointPositionAction(JointPositionAction):
    """只约束最终物理目标，原始动作观测及动作变化奖励沿用上游行为。"""

    cfg: BoundedJointPositionActionCfg

    def __init__(self, cfg: BoundedJointPositionActionCfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._requested_targets = torch.zeros_like(self._raw_actions)
        self._applied_targets = torch.zeros_like(self._raw_actions)

    @property
    def requested_targets(self) -> torch.Tensor:
        """当前控制帧扣除编码器偏置后的请求目标，形状为环境数×动作数，单位rad。"""
        return self._requested_targets

    @property
    def applied_targets(self) -> torch.Tensor:
        """当前物理子步实际写入实体的目标，形状与请求目标一致，单位rad。"""
        return self._applied_targets

    def apply_actions(self) -> None:
        bias = self._entity.data.encoder_bias[:, self._target_ids]
        requested = self._processed_actions - bias
        self._requested_targets.copy_(requested)
        if self.cfg.bound_targets:
            limits = self._entity.data.joint_pos_limits[:, self._target_ids]
            applied = torch.clamp(requested, min=limits[..., 0], max=limits[..., 1])
        else:
            applied = requested
        self._applied_targets.copy_(applied)
        self._entity.set_joint_position_target(applied, joint_ids=self._target_ids)

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        super().reset(env_ids)
        self._requested_targets[env_ids] = 0.0
        self._applied_targets[env_ids] = 0.0
