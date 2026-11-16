# Copyright (c) 2026-2027 zh
"""HT 后空翻的行为验收指标，与训练奖励完全分开。

成功定义：空中累计后仰 ≥330°、双脚着地、倾角 ≤20°、根高误差 ≤0.025 m、
线速度 ≤0.2 m/s、角速度 ≤0.8 rad/s 连续 0.5 s。落地过程允许先接触再弹起，
计时器在条件不满足时清零。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import ht_microduck_backflip_contract as C
from ht_microduck.tasks.mdp.ht_backflip_state import (
    _feet_both_contact,
    _finite,
    _state,
    _update_accum,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_FEET_SENSOR = "feet_ground_contact"


def _metric_state(env: ManagerBasedRlEnv) -> None:
    if not hasattr(env, "_backflip_success_hold"):
        zeros = torch.zeros(env.num_envs, dtype=torch.float32, device=env.device)
        env._backflip_success_hold = zeros.clone()
        env._backflip_success = torch.zeros(
            env.num_envs, dtype=torch.bool, device=env.device
        )


def reset_backflip_metrics(
    env: ManagerBasedRlEnv, env_ids: torch.Tensor | None = None
) -> None:
    _metric_state(env)
    selected = slice(None) if env_ids is None else env_ids
    env._backflip_success_hold[selected] = 0.0
    env._backflip_success[selected] = False


def backflip_angle(env: ManagerBasedRlEnv) -> torch.Tensor:
    """当前历史最大离地后仰角 [rad]，仅用于日志；不依赖奖励是否启用。"""
    _state(env)
    _update_accum(env, env.scene["robot"])
    return env._backflip_max


def backflip_success(env: ManagerBasedRlEnv) -> torch.Tensor:
    """持续满足落地条件的 0/1 指标；不参与 reward。"""
    _state(env)
    _update_accum(env, env.scene["robot"])
    _metric_state(env)
    asset = env.scene["robot"]
    feet_f = _feet_both_contact(env, _FEET_SENSOR)
    quat = _finite(asset.data.root_link_quat_w, nan=0.0)
    cos_tilt = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    tilt = torch.rad2deg(torch.acos(cos_tilt.clamp(-1.0, 1.0)))
    height = asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    lin = torch.norm(
        _finite(asset.data.root_link_lin_vel_w, nan=0.0), dim=-1
    )
    ang = torch.norm(
        _finite(asset.data.root_link_ang_vel_b, nan=0.0), dim=-1
    )
    ok = (
        (env._backflip_max >= C.SUCCESS_ANGLE)
        & feet_f
        & (tilt <= C.SUCCESS_TILT_DEG)
        & ((height - C.STAND_Z).abs() <= C.SUCCESS_HEIGHT_TOL)
        & (lin <= C.SUCCESS_LIN_VEL)
        & (ang <= C.SUCCESS_ANG_VEL)
    )
    env._backflip_success_hold = torch.where(
        ok, env._backflip_success_hold + env.step_dt, torch.zeros_like(ok, dtype=torch.float32)
    )
    env._backflip_success |= env._backflip_success_hold >= C.SUCCESS_HOLD_S
    return env._backflip_success.float()
