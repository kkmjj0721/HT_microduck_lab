# Copyright (c) 2026-2027 zh
"""官方任务的 IMU 安装误差与足端特权观测；旧 VelStand 不使用本模块。

来源：pollen-robotics/microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb，
src/mjlab_microduck/tasks/mdp.py，对应函数保持官方计算与缓存规则，Apache-2.0。
"""

from __future__ import annotations

import math

import torch
from mjlab.entity import Entity
from mjlab.envs import ManagerBasedRlEnv
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity.mdp import observations as _velocity_obs
from mjlab.utils.lab_api.math import quat_apply, quat_from_angle_axis

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _imu_misalignment_quat(
    env: ManagerBasedRlEnv, max_angle_rad: float
) -> torch.Tensor:
    """按官方基准实现_imu_misalignment_quat，仅适配本项目的模块与命名。"""
    q = getattr(env, "_imu_misalign_quat", None)
    if q is None:
        n = env.num_envs
        axis = torch.randn(n, 3, device=env.device)
        axis = axis / (torch.norm(axis, dim=-1, keepdim=True) + 1e-08)
        angle = torch.rand(n, device=env.device) * max_angle_rad
        q = quat_from_angle_axis(angle, axis)
        env._imu_misalign_quat = q
    return q


def projected_gravity_imu_misaligned(
    env: ManagerBasedRlEnv,
    max_angle_deg: float = 1.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方基准实现projected_gravity_imu_misaligned，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    q = _imu_misalignment_quat(env, math.radians(max_angle_deg))
    return quat_apply(q, asset.data.projected_gravity_b)


def base_ang_vel_imu_misaligned(
    env: ManagerBasedRlEnv,
    max_angle_deg: float = 1.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方基准实现base_ang_vel_imu_misaligned，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    q = _imu_misalignment_quat(env, math.radians(max_angle_deg))
    return quat_apply(q, asset.data.root_link_ang_vel_b)


def raw_accelerometer(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """按官方基准实现raw_accelerometer，仅适配本项目的模块与命名。"""
    asset: Entity = env.scene[asset_cfg.name]
    mj_model = asset.data.model
    sensor_adr_array = mj_model.sensor_adr
    sensor_id = 4
    sensor_adr = int(sensor_adr_array[sensor_id].item())
    accel_raw = asset.data.data.sensordata[:, sensor_adr : sensor_adr + 3]
    accel_negated = -accel_raw
    accel_norm = torch.norm(accel_negated, dim=-1, keepdim=True)
    accel_normalized = torch.where(
        accel_norm > 0.1, accel_negated / accel_norm, asset.data.projected_gravity_b
    )
    return accel_normalized


def zero_command_padding(env: ManagerBasedRlEnv, dim: int) -> torch.Tensor:
    """按官方基准实现zero_command_padding，仅适配本项目的模块与命名。"""
    return torch.zeros(env.num_envs, dim, device=env.device)


def _finite(x: torch.Tensor) -> torch.Tensor:
    return torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)


def foot_contact_forces_safe(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """按官方基准实现foot_contact_forces_safe，仅适配本项目的模块与命名。"""
    return _finite(_velocity_obs.foot_contact_forces(env, sensor_name))


def foot_height_safe(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """按官方基准实现foot_height_safe，仅适配本项目的模块与命名。"""
    return _finite(_velocity_obs.foot_height(env, sensor_name))


def foot_air_time_safe(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """按官方基准实现foot_air_time_safe，仅适配本项目的模块与命名。"""
    return _finite(_velocity_obs.foot_air_time(env, sensor_name))
