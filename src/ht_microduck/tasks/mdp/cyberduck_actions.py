# Copyright (c) 2026-2027 zh
"""
内容：
    在缩放前分别裁剪 CyberDuck 腿位置与踝速度动作，保留原始策略采样。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch
from mjlab.envs.mdp.actions import JointVelocityAction, JointVelocityActionCfg

from ht_microduck.tasks.mdp.actions import (
    BoundedJointPositionAction,
    BoundedJointPositionActionCfg,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


@dataclass(kw_only=True)
class CyberDuckJointPositionActionCfg(BoundedJointPositionActionCfg):
    """腿位置动作的原始无量纲限幅，最终目标仍受实体硬关节范围约束。"""

    raw_action_limit: float

    def __post_init__(self) -> None:
        super().__post_init__()
        if not math.isfinite(self.raw_action_limit) or self.raw_action_limit <= 0:
            raise ValueError("Position raw_action_limit must be positive and finite")

    def build(self, env: ManagerBasedRlEnv) -> CyberDuckJointPositionAction:
        return CyberDuckJointPositionAction(self, env)


class CyberDuckJointPositionAction(BoundedJointPositionAction):
    """只裁剪本动作项接收的新张量，不改写策略输入或管理器原始动作。"""

    cfg: CyberDuckJointPositionActionCfg

    def process_actions(self, actions: torch.Tensor) -> None:
        limit = self.cfg.raw_action_limit
        super().process_actions(actions.clamp(min=-limit, max=limit))


@dataclass(kw_only=True)
class CyberDuckJointVelocityActionCfg(JointVelocityActionCfg):
    """踝速度动作的原始无量纲限幅，物理速度范围由上游 clip 指定。"""

    raw_action_limit: float

    def __post_init__(self) -> None:
        super().__post_init__()
        if not math.isfinite(self.raw_action_limit) or self.raw_action_limit <= 0:
            raise ValueError("Velocity raw_action_limit must be positive and finite")

    def build(self, env: ManagerBasedRlEnv) -> CyberDuckJointVelocityAction:
        return CyberDuckJointVelocityAction(self, env)


class CyberDuckJointVelocityAction(JointVelocityAction):
    """先裁剪踝动作，再沿用上游缩放、偏置与物理速度限幅。"""

    cfg: CyberDuckJointVelocityActionCfg

    def process_actions(self, actions: torch.Tensor) -> None:
        limit = self.cfg.raw_action_limit
        super().process_actions(actions.clamp(min=-limit, max=limit))
