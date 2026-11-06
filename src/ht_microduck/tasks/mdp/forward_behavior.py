# Copyright (c) 2026-2027 zh
"""独立度量前坐终点、连续保持时间和四种初态与命令组合，不参与奖励。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
)
from ht_microduck.tasks.mdp.forward_posture import _feet_forward_x
from ht_microduck.tasks.mdp.official_posture_events import _servo_joint_ids

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.managers.metrics_manager import MetricsTermCfg

_HIP_INDICES = tuple(C.POLICY_JOINT_NAMES.index(name) for name in ("r_hip_pitch_joint", "l_hip_pitch_joint"))
_KNEE_INDICES = tuple(C.POLICY_JOINT_NAMES.index(name) for name in ("r_calf_joint", "l_calf_joint"))


def forward_posture_valid(
    env: ManagerBasedRlEnv,
    target_sit: torch.Tensor | None = None,
    command_name: str = "twist",
) -> torch.Tensor:
    """联合检查目标腿形、地形相对高度、倾角及坐姿时的机体系前收脚位置。"""
    sit = env.command_manager.get_command(command_name)[:, 0] > 0.5 if target_sit is None else target_sit
    asset = env.scene["robot"]
    ids = _servo_joint_ids(env, asset)
    home = asset.data.default_joint_pos[:, ids]
    seat = home.clone()
    for name, angle in FORWARD_SITTING_JOINT_POS.items():
        seat[:, C.POLICY_JOINT_NAMES.index(name)] = angle
    target = torch.where(sit[:, None], seat, home)
    errors = (asset.data.joint_pos[:, ids] - target).abs()
    leg_valid = errors[:, :10].mean(dim=-1) < 0.25
    hip_valid = (errors[:, _HIP_INDICES] < 0.35).all(dim=-1)
    knee_valid = (errors[:, _KNEE_INDICES] < 0.35).all(dim=-1)
    feet_valid = (_feet_forward_x(env) > 0.015).all(dim=-1)
    height = asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    target_height = torch.where(sit, FORWARD_SIT_Z, C.STAND_Z)
    height_tolerance = torch.where(sit, 0.015, 0.02)
    height_valid = (height - target_height).abs() < height_tolerance
    quat = asset.data.root_link_quat_w
    cosine = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright = cosine > math.cos(math.radians(15.0))
    return leg_valid & height_valid & upright & (~sit | (hip_valid & knee_valid & feet_valid))


class ForwardHoldDuration:
    """累计当前命令下连续有效的秒数，命令切换或姿态失效时清零。"""

    def __init__(self, cfg: MetricsTermCfg, env: ManagerBasedRlEnv):
        del cfg
        self._steps = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)
        self._previous_sit = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        self._seen = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)

    def __call__(self, env: ManagerBasedRlEnv, command_name: str = "twist") -> torch.Tensor:
        sit = env.command_manager.get_command(command_name)[:, 0] > 0.5
        changed = self._seen & (sit != self._previous_sit)
        valid = forward_posture_valid(env, sit, command_name)
        self._steps = torch.where(valid & ~changed, self._steps + 1, 0)
        self._previous_sit = sit.clone()
        self._seen.fill_(True)
        return self._steps.to(torch.float32) * env.step_dt

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        steps = self._steps.clone()
        steps[env_ids] = 0
        self._steps = steps
        self._seen[env_ids] = False


def forward_case_frames(
    env: ManagerBasedRlEnv,
    initial_sit: bool,
    target_sit: bool,
    command_name: str = "twist",
) -> torch.Tensor:
    """按重置时姿态与当前命令标记四类帧，作为对应成功帧的独立分母。"""
    sit = env.command_manager.get_command(command_name)[:, 0] > 0.5
    return ((env._forward_initial_sit == initial_sit) & (sit == target_sit)).float()


def forward_case_success_frames(
    env: ManagerBasedRlEnv,
    initial_sit: bool,
    target_sit: bool,
    command_name: str = "twist",
) -> torch.Tensor:
    """仅标记所属初态与命令组合中同时满足当前目标姿态的帧。"""
    frames = forward_case_frames(env, initial_sit, target_sit, command_name)
    return frames * forward_posture_valid(env, command_name=command_name).float()
