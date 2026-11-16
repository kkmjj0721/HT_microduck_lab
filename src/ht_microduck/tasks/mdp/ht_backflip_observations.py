# Copyright (c) 2026-2027 zh
"""HT 后空翻的 critic-only 板状态与相位观测。

actor 刻意保持 plate-blind；这些量只给 critic，实机没有发射板传感器。
板的观测在 GONE 后置零，避免归一化器被远距离停靠值压扁。
"""

from __future__ import annotations

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import quat_apply_inverse

from ht_microduck.tasks.mdp.ht_backflip_state import (
    BACKFLIP_PHASE_GONE,
    _finite,
    _state,
    _time,
    backflip_phase,
)

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _present_mask(env) -> torch.Tensor:
    return (backflip_phase(env) != BACKFLIP_PHASE_GONE).float().unsqueeze(-1)


def backflip_plate_pos_obs(
    env, asset_name: str = "plate", asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """板相对机器人根体的位置，GONE 后置零；NaN 在 mask 前清理。"""
    robot = env.scene[asset_cfg.name]
    plate = env.scene[asset_name]
    rel = plate.data.root_link_pos_w - robot.data.root_link_pos_w
    rel_b = quat_apply_inverse(
        _finite(robot.data.root_link_quat_w, nan=0.0), rel
    )
    return _finite(rel_b, nan=0.0) * _present_mask(env)


def backflip_plate_vel_obs(
    env, asset_name: str = "plate", asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """板相对机器人根体的线速度，GONE 后置零。"""
    robot = env.scene[asset_cfg.name]
    plate = env.scene[asset_name]
    rel = plate.data.root_link_lin_vel_w - robot.data.root_link_lin_vel_w
    rel_b = quat_apply_inverse(
        _finite(robot.data.root_link_quat_w, nan=0.0), rel
    )
    return _finite(rel_b, nan=0.0) * _present_mask(env)


def backflip_phase_obs(env) -> torch.Tensor:
    """critic-only 相位标量 HOLD/LAUNCH/GONE，形状 (N,1)。"""
    return _finite(backflip_phase(env).float(), nan=0.0).unsqueeze(-1)


def backflip_hold_remaining_obs(env) -> torch.Tensor:
    """critic-only 距离发射的剩余秒数，发射后为 0。"""
    _state(env)
    remaining = (env._backflip_t_hold - _time(env)).clamp(min=0.0)
    return _finite(remaining, nan=0.0).unsqueeze(-1)
