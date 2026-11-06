# Copyright (c) 2026-2027 zh
"""从官方 bae39f59 移植姿态事件与坐站命令，适配 HT 关节、高度参考和 mjlab 1.6。

来源：pollen-robotics/microduck_rl，Apache-2.0，tasks/mdp.py。
公式与状态更新顺序保留官方实现，旧 VelStand 不引用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass as _dataclass
from typing import Optional

import numpy as np
import torch
from mjlab.entity import Entity
from mjlab.envs import ManagerBasedRlEnv
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity.mdp.velocity_command import (
    UniformVelocityCommand,
    UniformVelocityCommandCfg,
)
from mjlab.utils.lab_api.math import quat_apply

from ht_microduck.tasks import ht_microduck_contract as C

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _servo_joint_ids(env: "ManagerBasedRlEnv", asset: Entity) -> list:
    cache = env.__dict__.setdefault("_servo_joint_ids_cache", {})
    key = id(asset)
    ids = cache.get(key)
    if ids is None:
        ids, _ = asset.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
        cache[key] = ids
    return ids


def _env_origin_z(env: "ManagerBasedRlEnv", env_ids: torch.Tensor) -> torch.Tensor:
    return env.scene.env_origins[env_ids.long(), 2]


def set_random_ground_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    face_down_prob: float = 0.4,
    face_up_prob: float = 0.4,
    sitting_prob: float = 0.2,
    standing_prob: float = 0.0,
    prone_z_min: float = 0.2,
    prone_z_max: float = 0.25,
    sitting_z_min: float = 0.07,
    sitting_z_max: float = 0.09,
    standing_z_min: float = 0.11,
    standing_z_max: float = 0.12,
    sitting_joint_overrides: Optional[dict] = None,
    sitting_joint_noise_std: float = 0.0,
    sitting_tilt_max: float = 0.0,
    face_up_roll_max: float = 0.0,
    face_down_z_offset: float = 0.0,
    face_up_z_offset: float = 0.0,
):
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.int)
    num = len(env_ids)
    total = face_down_prob + face_up_prob + sitting_prob + standing_prob
    p_fd = face_down_prob / total
    p_fu = (face_down_prob + face_up_prob) / total
    p_sit = (face_down_prob + face_up_prob + sitting_prob) / total
    yaw = torch.rand(num, device=env.device) * 2 * np.pi - np.pi
    cy = torch.cos(yaw * 0.5)
    sy = torch.sin(yaw * 0.5)
    s = 2.0 ** (-0.5)
    face_down = torch.stack([s * cy, -s * sy, s * cy, s * sy], dim=1)
    face_up = torch.stack([s * cy, s * sy, -s * cy, s * sy], dim=1)
    if sitting_tilt_max > 0.0:
        pitch = (torch.rand(num, device=env.device) * 2 - 1) * sitting_tilt_max
        roll = (torch.rand(num, device=env.device) * 2 - 1) * sitting_tilt_max
        cp = torch.cos(pitch * 0.5)
        sp = torch.sin(pitch * 0.5)
        cr = torch.cos(roll * 0.5)
        sr = torch.sin(roll * 0.5)
        sit_w = cr * cp * cy + sr * sp * sy
        sit_x = sr * cp * cy - cr * sp * sy
        sit_y = cr * sp * cy + sr * cp * sy
        sit_z = cr * cp * sy - sr * sp * cy
        sitting = torch.stack([sit_w, sit_x, sit_y, sit_z], dim=1)
    else:
        sitting = torch.stack(
            [cy, torch.zeros_like(cy), torch.zeros_like(cy), sy], dim=1
        )
    u = torch.rand(num, device=env.device)
    _is_fd = u < p_fd
    is_fu = (u >= p_fd) & (u < p_fu)
    is_sit = (u >= p_fu) & (u < p_sit)
    is_stand = u >= p_sit
    if face_up_roll_max > 0.0:
        theta = (torch.rand(num, device=env.device) * 2 - 1) * face_up_roll_max
        ct = torch.cos(theta * 0.5)
        st = torch.sin(theta * 0.5)
        w, x, y, z = (face_up[:, 0], face_up[:, 1], face_up[:, 2], face_up[:, 3])
        face_up = torch.stack(
            [w * ct - z * st, x * ct + y * st, y * ct - x * st, w * st + z * ct], dim=1
        )
    new_quat = face_down.clone()
    new_quat[is_fu] = face_up[is_fu]
    new_quat[is_sit] = sitting[is_sit]
    new_quat[is_stand] = sitting[is_stand]
    z_prone = (
        torch.rand(num, device=env.device) * (prone_z_max - prone_z_min) + prone_z_min
    )
    z_sit = (
        torch.rand(num, device=env.device) * (sitting_z_max - sitting_z_min)
        + sitting_z_min
    )
    z_stand = (
        torch.rand(num, device=env.device) * (standing_z_max - standing_z_min)
        + standing_z_min
    )
    # 保留官方均匀高度带，只平移前后躺的硬件支撑参考。
    new_z = z_prone + torch.where(is_fu, face_up_z_offset, face_down_z_offset)
    new_z = torch.where(is_sit, z_sit, new_z)
    new_z = torch.where(is_stand, z_stand, new_z)
    env.sim.data.qpos[env_ids, 2] = new_z + _env_origin_z(env, env_ids)
    env.sim.data.qpos[env_ids, 3:7] = new_quat
    env.sim.data.qvel[env_ids, :6] = 0.0
    asset: Entity = env.scene[asset_cfg.name]
    servo_ids = _servo_joint_ids(env, asset)
    if sitting_joint_overrides:
        sit_env_ids = env_ids[is_sit]
        if len(sit_env_ids) > 0:
            for jnt_idx, angle in sitting_joint_overrides.items():
                env.sim.data.qpos[sit_env_ids, 7 + servo_ids[jnt_idx]] = angle
    if sitting_joint_noise_std > 0.0:
        sit_env_ids = env_ids[is_sit]
        if len(sit_env_ids) > 0:
            n_sit = len(sit_env_ids)
            cols = torch.tensor(
                [7 + j for j in servo_ids], device=env.device, dtype=torch.long
            )
            noise = (
                torch.randn(n_sit, len(cols), device=env.device)
                * sitting_joint_noise_std
            )
            env.sim.data.qpos[sit_env_ids.unsqueeze(1).long(), cols.unsqueeze(0)] += (
                noise
            )


class SitStandCommand(UniformVelocityCommand):
    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._sit_prob = float(getattr(cfg, "sit_prob", 0.5))
        self._ramp_s = float(getattr(cfg, "ramp_s", 2.0))
        self._sit_z = float(getattr(cfg, "sit_z", 0.06))
        self._stand_z = float(getattr(cfg, "stand_z", 0.115))
        self._env_ref = env
        self._alpha = torch.zeros(self.num_envs, device=self.device)

    @property
    def command(self) -> torch.Tensor:
        return self.vel_command_b

    @property
    def alpha(self) -> torch.Tensor:
        return self._alpha

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        sit = (torch.rand(n, device=self.device) < self._sit_prob).float()
        self.vel_command_b[env_ids] = 0.0
        self.vel_command_b[env_ids, 0] = sit

    def _alpha_from_height(self) -> torch.Tensor:
        z = torch.nan_to_num(
            self.robot.data.root_link_pos_w[:, 2]
            - self._env_ref.scene.terrain.env_origins[:, 2],
            nan=self._stand_z,
        )
        return torch.clamp(
            (self._stand_z - z) / max(self._stand_z - self._sit_z, 1e-06), 0.0, 1.0
        )

    def compute(
        self, dt: float | torch.Tensor, env_ids: torch.Tensor | None = None
    ) -> None:
        super().compute(dt, env_ids)
        fresh = self._env_ref.episode_length_buf <= 1
        if env_ids is not None:
            selected = torch.zeros_like(fresh)
            selected[env_ids] = True
            fresh = fresh & selected
        if fresh.any():
            self._alpha = torch.where(fresh, self._alpha_from_height(), self._alpha)
        step = dt / max(self._ramp_s, 1e-06)
        delta = self.vel_command_b[:, 0] - self._alpha
        increment = torch.clamp(delta, -step, step)
        if env_ids is None:
            self._alpha += increment
        else:
            self._alpha[env_ids] += increment[env_ids]

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        pass

    def _update_metrics(self) -> None:
        pass


@_dataclass(kw_only=True)
class SitStandCommandCfg(UniformVelocityCommandCfg):
    class_type: type = SitStandCommand
    sit_prob: float = 0.5
    ramp_s: float = 2.0
    sit_z: float = 0.06
    stand_z: float = 0.115

    def build(self, env: ManagerBasedRlEnv) -> "SitStandCommand":
        return SitStandCommand(self, env)


def _posture_blend(env: ManagerBasedRlEnv, command_name: str) -> torch.Tensor:
    term = env.command_manager.get_term(command_name)
    alpha = getattr(term, "alpha", None)
    if alpha is not None:
        return alpha
    return env.command_manager.get_command(command_name)[:, 0]


def _seated_mask(
    env: ManagerBasedRlEnv, command_name: str, min_alpha: float
) -> torch.Tensor:
    sit = env.command_manager.get_command(command_name)[:, 0] > 0.5
    return sit & (_posture_blend(env, command_name) >= min_alpha)


def seated_head_command_jerk(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    prob: float,
    flip_frac: float = 0.5,
    posture_command_name: str = "twist",
    head_command_name: str = "head_pose",
    min_alpha: float = 0.98,
) -> None:
    if prob <= 0.0 or env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.long)
    seated = _seated_mask(env, posture_command_name, min_alpha)[env_ids]
    pick = seated & (torch.rand(len(env_ids), device=env.device) < prob)
    ids = env_ids[pick]
    if len(ids) == 0:
        return
    term = env.command_manager.get_term(head_command_name)
    flip = torch.rand(len(ids), device=env.device) < flip_frac
    fresh = torch.empty(len(ids), term.dim, device=env.device)
    for i, (lo, hi) in enumerate(term.cfg.ranges):
        fresh[:, i].uniform_(lo, hi)
    cur = term._command[ids]
    term._command[ids] = torch.where(flip.unsqueeze(1), -cur, fresh)


def seated_backward_tip(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    ang_vel_range: tuple[float, float],
    prob: float = 1.0,
    lateral_frac: float = 0.3,
    posture_command_name: str = "twist",
    min_alpha: float = 0.98,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.long)
    seated = _seated_mask(env, posture_command_name, min_alpha)[env_ids]
    pick = seated & (torch.rand(len(env_ids), device=env.device) < prob)
    ids = env_ids[pick]
    if len(ids) == 0 or ang_vel_range[1] <= 0.0:
        return
    asset: Entity = env.scene[asset_cfg.name]
    n = len(ids)
    mag = torch.empty(n, device=env.device).uniform_(*ang_vel_range)
    roll = (torch.rand(n, device=env.device) * 2 - 1) * lateral_frac
    omega_b = torch.stack([roll * mag, -mag, torch.zeros_like(mag)], dim=1)
    omega_w = quat_apply(asset.data.root_link_quat_w[ids], omega_b)
    vel = asset.data.root_link_vel_w[ids].clone()
    vel[:, 3:6] += omega_w
    asset.write_root_link_velocity_to_sim(vel, env_ids=ids)


__all__ = [
    "SitStandCommand",
    "SitStandCommandCfg",
    "seated_backward_tip",
    "seated_head_command_jerk",
    "set_random_ground_state",
]
