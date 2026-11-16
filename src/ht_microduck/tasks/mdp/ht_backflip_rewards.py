# Copyright (c) 2026-2027 zh
"""HT 后空翻的进度、保持、落地奖励。

来源：microduck_rl@d26322f ``tasks/mdp.py`` 的 backflip 奖励（Apache-2.0）。
公式保持官方：进度只支付历史新高、落地为乘性门控、保持只付 HOLD。
常量由 HT 契约传入；其中发射范围仍是官方 0.74 kg 的临时基线，未在 HT 标定。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ht_microduck.tasks import ht_microduck_backflip_contract as C
from ht_microduck.tasks.mdp.ht_backflip_state import (
    _PLATE_SENSOR,
    _completion_gate,
    _feet_both_contact,
    _finite,
    _landing_window,
    _launch_gate,
    _pay,
    _sensor_any_contact,
    _state,
    _trunk_tilt_smoothstep,
    _update_accum,
    backflip_hold_window,
)

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _joint_ids(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    ids = getattr(env, "_backflip_joint_ids", None)
    if ids is None:
        ids, _ = asset.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
        env._backflip_joint_ids = ids
    return torch.as_tensor(ids, dtype=torch.long, device=env.device)


def backflip_progress(
    env: ManagerBasedRlEnv,
    target_angle: float = C.TARGET_ANGLE,
    max_paid_rate: float = C.MAX_PAID_RATE,
    launch_gate_floor: float = C.LAUNCH_GATE_FLOOR,
    hold_z: float = C.STAND_Z + C.PLATE_HALF_THICKNESS,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """离地后仰历史新高的 potential 支付，乘以发射姿态门控。"""
    asset = env.scene[asset_cfg.name]
    _update_accum(env, asset)
    gate = _launch_gate(env, asset, hold_z, launch_gate_floor)
    return _pay(env, target_angle, max_paid_rate) * gate


def backflip_ready_stance(
    env: ManagerBasedRlEnv,
    stand_z: float = C.STAND_Z + C.PLATE_HALF_THICKNESS,
    height_std: float = 0.03,
    tilt_full_deg: float = 10.0,
    tilt_zero_deg: float = 45.0,
    pose_std: float = C.POSE_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """HOLD 阶段站在板上：高度×直立×关节姿态，窗口由预设时间关闭。"""
    asset = env.scene[asset_cfg.name]
    _state(env)
    z_err = asset.data.root_link_pos_w[:, 2] - (
        env.scene.env_origins[:, 2] + env._backflip_z0 + stand_z
    )
    height = torch.exp(-_finite(z_err, nan=1.0).square() / height_std**2)
    upright = _trunk_tilt_smoothstep(
        _finite(asset.data.root_link_quat_w, nan=0.0),
        tilt_full_deg,
        tilt_zero_deg,
    )
    ids = _joint_ids(env, asset)
    joint_err = asset.data.joint_pos[:, ids] - asset.data.default_joint_pos[:, ids]
    pose = torch.exp(
        -_finite(joint_err, nan=1.0).square().mean(dim=-1) / pose_std**2
    )
    on_plate = _sensor_any_contact(env, _PLATE_SENSOR).float()
    return backflip_hold_window(env) * on_plate * height * upright * pose


def backflip_landing(
    env: ManagerBasedRlEnv,
    stand_z: float = C.STAND_Z,
    height_std: float = 0.04,
    omega_std: float = 3.0,
    lin_vel_std: float = 0.5,
    window_s: float = C.LANDING_WINDOW_S,
    launch_gate_floor: float = C.LAUNCH_GATE_FLOOR,
    hold_z: float = C.STAND_Z + C.PLATE_HALF_THICKNESS,
    sensor_name: str = "feet_ground_contact",
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """完成后仰门控后的落地年金：双脚、直立、高度、角速度、线速度、固定窗口。"""
    asset = env.scene[asset_cfg.name]
    gate = _completion_gate(env)
    feet_f = _feet_both_contact(env, sensor_name).float()
    quat = _finite(asset.data.root_link_quat_w, nan=0.0)
    up = (1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())).clamp(min=0.0)
    z_err = asset.data.root_link_pos_w[:, 2] - (
        env.scene.env_origins[:, 2] + stand_z
    )
    height = torch.exp(-_finite(z_err, nan=1.0).square() / height_std**2)
    omega = torch.norm(_finite(asset.data.root_link_ang_vel_b, nan=0.0), dim=-1)
    calm = torch.exp(-omega.square() / omega_std**2)
    lin = torch.norm(
        _finite(asset.data.root_link_lin_vel_w, nan=0.0), dim=-1
    )
    settle = torch.exp(-lin.square() / lin_vel_std**2)
    window = _landing_window(env, window_s, sensor_name)
    launch = _launch_gate(env, asset, hold_z, launch_gate_floor)
    return gate * feet_f * up * height * calm * settle * window * launch
