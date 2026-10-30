# Copyright (c) 2026-2027 zh
"""官方头部跟踪、长期偏差与躯干六维奖励；旧 VelStand 保留原实现。

来源：pollen-robotics/microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb，
src/mjlab_microduck/tasks/mdp.py，对应函数保持官方公式，Apache-2.0。
"""

from __future__ import annotations

import math

import torch
from mjlab.entity import Entity
from mjlab.envs import ManagerBasedRlEnv
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import wrap_to_pi

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")
_NECK_JOINT_PATTERNS = [
    r".*neck_pitch.*",
    r".*head_pitch.*",
    r".*head_yaw.*",
    r".*head_roll.*",
]


def head_pose_tracking(
    env: ManagerBasedRlEnv,
    command_name: str = "head_pose",
    std: float = 0.5,
    fine_std: float | None = None,
    fine_weight: float = 0.5,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方基准实现head_pose_tracking，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)
    if not hasattr(env, "_head_pose_neck_ids"):
        ids, names = asset.find_joints_by_actuator_names(_NECK_JOINT_PATTERNS)
        env._head_pose_neck_ids = torch.tensor(ids, device=env.device, dtype=torch.long)
        name_to_id = {n: i for i, n in enumerate(asset.joint_names)}
        bl = [name_to_id.get(f"passive_{n}_backlash") for n in names]
        env._head_pose_bl_ids = torch.tensor(
            [0 if b is None else b for b in bl], device=env.device, dtype=torch.long
        )
        env._head_pose_bl_mask = torch.tensor(
            [0.0 if b is None else 1.0 for b in bl], device=env.device
        )
    neck_ids = env._head_pose_neck_ids
    joint_pos = asset.data.joint_pos
    measured = (
        joint_pos[:, neck_ids]
        + joint_pos[:, env._head_pose_bl_ids] * env._head_pose_bl_mask
    )
    actual = measured - asset.data.default_joint_pos[:, neck_ids]
    err = actual - cmd
    per_joint = torch.exp(-((err / std) ** 2))
    if fine_std is not None:
        per_joint = (1.0 - fine_weight) * per_joint + fine_weight * torch.exp(
            -((err / fine_std) ** 2)
        )
    return per_joint.mean(dim=-1)


def head_pose_bias_penalty(
    env: ManagerBasedRlEnv,
    command_name: str = "head_pose",
    tau_s: float = 1.0,
    gate_height_low: float | None = None,
    gate_height_high: float = 0.11,
    gate_tilt_full_deg: float = 20.0,
    gate_tilt_zero_deg: float = 45.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方基准实现head_pose_bias_penalty，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)
    if not hasattr(env, "_head_pose_neck_ids"):
        head_pose_tracking(env, command_name=command_name, asset_cfg=asset_cfg)
    neck_ids = env._head_pose_neck_ids
    joint_pos = asset.data.joint_pos
    measured = (
        joint_pos[:, neck_ids]
        + joint_pos[:, env._head_pose_bl_ids] * env._head_pose_bl_mask
    )
    err = measured - asset.data.default_joint_pos[:, neck_ids] - cmd
    if gate_height_low is not None:
        z = torch.nan_to_num(
            asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2],
            nan=0.0,
        )
        t = torch.clamp(
            (z - gate_height_low) / max(gate_height_high - gate_height_low, 1e-06),
            0.0,
            1.0,
        )
        gate = t * t * (3.0 - 2.0 * t)
        quat = asset.data.root_link_quat_w
        cos_tilt = 1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)
        tilt_deg = torch.rad2deg(torch.acos(cos_tilt.clamp(-1.0, 1.0)))
        st = torch.clamp(
            (gate_tilt_zero_deg - tilt_deg)
            / max(gate_tilt_zero_deg - gate_tilt_full_deg, 1e-06),
            0.0,
            1.0,
        )
        gate = gate * (st * st * (3.0 - 2.0 * st))
        err = err * gate.unsqueeze(-1)
    else:
        gate = None
    if not hasattr(env, "_head_bias_ema"):
        env._head_bias_ema = torch.zeros_like(err)
    fresh = env.episode_length_buf <= 1
    env._head_bias_ema[fresh] = 0.0
    alpha = min(1.0, float(env.step_dt) / max(tau_s, 1e-06))
    env._head_bias_ema = (1.0 - alpha) * env._head_bias_ema + alpha * err
    out = -env._head_bias_ema.abs().mean(dim=-1)
    if gate is not None:
        out = out * gate
    return out


def body_pose_tracking_6d(
    env: ManagerBasedRlEnv,
    command_name: str = "body_pose",
    nominal_height: float = 0.095,
    xy_std: float = 0.02,
    z_std: float = 0.01,
    angle_std: float = math.radians(8),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方基准实现body_pose_tracking_6d，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)
    dx, dy, dz = (cmd[:, 0], cmd[:, 1], cmd[:, 2])
    droll, dpitch, dyaw = (cmd[:, 3], cmd[:, 4], cmd[:, 5])
    pos_w = asset.data.root_link_pos_w
    origin = env.scene.terrain.env_origins
    rel = torch.nan_to_num(pos_w - origin, nan=0.0)
    x_err = rel[:, 0] - dx
    y_err = rel[:, 1] - dy
    z_err = rel[:, 2] - (nominal_height + dz)
    quat = asset.data.root_link_quat_w
    qw, qx, qy, qz = (quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3])
    roll = torch.atan2(2.0 * (qw * qx + qy * qz), 1.0 - 2.0 * (qx * qx + qy * qy))
    pitch = torch.asin(torch.clamp(2.0 * (qw * qy - qz * qx), -1.0, 1.0))
    yaw = torch.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
    roll_err = roll - droll
    pitch_err = pitch - dpitch
    yaw_err = wrap_to_pi(yaw - dyaw)
    r_x = torch.exp(-((x_err / xy_std) ** 2))
    r_y = torch.exp(-((y_err / xy_std) ** 2))
    r_z = torch.exp(-((z_err / z_std) ** 2))
    r_r = torch.exp(-((roll_err / angle_std) ** 2))
    r_p = torch.exp(-((pitch_err / angle_std) ** 2))
    r_w = torch.exp(-((yaw_err / angle_std) ** 2))
    return (r_x + r_y + r_z + r_r + r_p + r_w) / 6.0
