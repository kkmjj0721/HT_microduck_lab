"""姿态任务的重置事件与 HT 姿态参考。

VelStand 按官方绝对概率保留站立、低姿态和躺姿切片；前后躺绕 pitch，侧躺绕 roll。
站立和低姿态沿用本机已确认参考，前后躺保留官方均匀高度带并平移到 HT 的名义几何
支撑面，不把几何参考称为动态平衡实测值。其余姿态任务继续使用原有重置入口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.official_robot import (
    FACE_DOWN_SUPPORT_Z,
    FACE_UP_SUPPORT_Z,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _quat_from_axis_angle(axis: torch.Tensor, angle: torch.Tensor) -> torch.Tensor:
    """Unit quaternion ``(w, x, y, z)`` for a rotation of ``angle`` about ``axis``."""
    half = angle * 0.5
    return torch.cat(
        [torch.cos(half).unsqueeze(-1), axis * torch.sin(half).unsqueeze(-1)], dim=-1
    )


def quat_mul(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Hamilton product of ``(w, x, y, z)`` quaternions."""
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        dim=-1,
    )


def reset_to_posture(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    joint_overrides: dict[str, float],
    joint_noise_std: float,
    roll_deg: float | torch.Tensor,
    pitch_deg: tuple[float, float],
    yaw_range_deg: tuple[float, float],
    height: float | torch.Tensor,
    position_noise: float,
    velocity_noise: float = 0.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """按给定关节、朝向与地形相对高度重置；高度和 roll 可为逐环境张量。"""
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device)
    n = len(env_ids)
    if n == 0:
        return

    asset: Entity = env.scene[asset_cfg.name]

    # ---- joints: HOME, then the named overrides, then noise, then clamp --------
    default = asset.data.default_joint_pos
    assert default is not None
    joint_pos = default[env_ids].clone()
    if joint_overrides:
        index = {name: i for i, name in enumerate(asset.joint_names)}
        ids = torch.tensor(
            [index[name] for name in joint_overrides], device=env.device, dtype=torch.long
        )
        values = torch.tensor(
            list(joint_overrides.values()), device=env.device, dtype=joint_pos.dtype
        )
        joint_pos[:, ids] = values
    if joint_noise_std > 0.0:
        joint_pos = joint_pos + torch.randn_like(joint_pos) * joint_noise_std
    limits = asset.data.soft_joint_pos_limits[env_ids]
    joint_pos = joint_pos.clamp(limits[..., 0], limits[..., 1])
    asset.write_joint_position_to_sim(joint_pos, env_ids=env_ids)

    # ---- root orientation: R = Rz(yaw) * Ry(pitch) * Rx(roll) -----------------
    def _uniform(rng: tuple[float, float]) -> torch.Tensor:
        low = torch.deg2rad(torch.tensor(rng[0], device=env.device, dtype=torch.float))
        high = torch.deg2rad(torch.tensor(rng[1], device=env.device, dtype=torch.float))
        return torch.empty(n, device=env.device).uniform_(low, high)

    if isinstance(roll_deg, torch.Tensor):
        roll = roll_deg.to(device=env.device, dtype=torch.float).reshape(n)
    else:
        roll = torch.full((n,), float(roll_deg), device=env.device)
    roll = torch.deg2rad(roll)
    qx = _quat_from_axis_angle(
        torch.tensor([1.0, 0.0, 0.0], device=env.device).expand(n, 3), roll
    )
    qy = _quat_from_axis_angle(
        torch.tensor([0.0, 1.0, 0.0], device=env.device).expand(n, 3), _uniform(pitch_deg)
    )
    qz = _quat_from_axis_angle(
        torch.tensor([0.0, 0.0, 1.0], device=env.device).expand(n, 3),
        _uniform(yaw_range_deg),
    )
    quat = quat_mul(qz, quat_mul(qy, qx))

    # ---- root pose ------------------------------------------------------------
    origins = env.scene.env_origins[env_ids]
    root_xy = origins[:, :2]
    if position_noise > 0.0:
        root_xy = root_xy + torch.randn(n, 2, device=env.device) * position_noise
    z = origins[:, 2] + height
    asset.write_root_link_pose_to_sim(
        torch.cat([root_xy, z.unsqueeze(-1), quat], dim=-1), env_ids=env_ids
    )

    velocity = torch.zeros(n, 6, device=env.device)
    if velocity_noise > 0.0:
        velocity = velocity + torch.randn_like(velocity) * velocity_noise
    asset.write_root_link_velocity_to_sim(velocity, env_ids=env_ids)


def reset_to_sit(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    joint_noise_std: float = C.SIT_JOINT_NOISE_STD,
    yaw_range_deg: tuple[float, float] = (-180.0, 180.0),
    position_noise: float = 0.03,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Seated start for the stand-up task: every episode begins from the same sit."""
    reset_to_posture(
        env,
        env_ids,
        joint_overrides=C.LOW_POSTURE_JOINT_POS,
        joint_noise_std=joint_noise_std,
        # The trunk stays level: this robot sits on its hips with its feet off the
        # ground, so the pose comes from the joints alone (contract.py).
        roll_deg=C.LOW_POSTURE_ROLL_DEG,
        pitch_deg=(0.0, 0.0),
        yaw_range_deg=yaw_range_deg,
        height=C.SIT_Z,
        position_noise=position_noise,
        asset_cfg=asset_cfg,
    )


def reset_to_ground_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    prone_prob: float,
    crouch_prob: float,
    side_prob: float,
    face_down_prob: float,
    position_noise: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """按官方互斥切片抽样，保留 ``1-prone_prob-crouch_prob`` 的站立份额。

    ``side_prob`` 是 prone 内部的侧躺概率，其余按 ``face_down_prob`` 分前后躺。
    概率由配置入口校验；官方 crouch 切片映射到已确认的 HT 低姿态。
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device)
    n = len(env_ids)
    if n == 0:
        return

    draw = torch.rand(n, device=env.device)
    prone = env_ids[draw < prone_prob]
    low = env_ids[(draw >= prone_prob) & (draw < prone_prob + crouch_prob)]
    standing = env_ids[draw >= prone_prob + crouch_prob]

    if len(standing) > 0:
        reset_to_stand(env, standing, position_noise=position_noise, asset_cfg=asset_cfg)
    if len(low) > 0:
        reset_to_sit(env, low, position_noise=position_noise, asset_cfg=asset_cfg)
    if len(prone) == 0:
        return

    # 官方先抽侧躺，再对非侧躺切片独立抽前后躺；两种侧躺等概率。
    on_side = torch.rand(len(prone), device=env.device) < side_prob
    face_down = torch.rand(len(prone), device=env.device) < face_down_prob
    for mask, pitch, support_z in (
        (~on_side & face_down, 90.0, FACE_DOWN_SUPPORT_Z),
        (~on_side & ~face_down, -90.0, FACE_UP_SUPPORT_Z),
    ):
        selected = prone[mask]
        if len(selected) == 0:
            continue
        # 保留官方 U(.05,.09) 的余隙及带宽，仅改变机器人支撑参考。
        height = torch.empty(len(selected), device=env.device).uniform_(0.05, 0.09)
        height += support_z - 0.044
        reset_to_posture(
            env,
            selected,
            joint_overrides={},
            joint_noise_std=0.0,
            roll_deg=0.0,
            pitch_deg=(pitch, pitch),
            yaw_range_deg=(-180.0, 180.0),
            height=height,
            position_noise=position_noise,
            asset_cfg=asset_cfg,
        )
    selected = prone[on_side]
    if len(selected) > 0:
        sign = torch.where(torch.rand(len(selected), device=env.device) < 0.5, 1.0, -1.0)
        reset_to_posture(
            env,
            selected,
            joint_overrides={},
            joint_noise_std=0.0,
            roll_deg=sign * 90.0,
            pitch_deg=(0.0, 0.0),
            yaw_range_deg=(-180.0, 180.0),
            height=C.SIDE_Z,
            position_noise=position_noise,
            asset_cfg=asset_cfg,
        )


def reset_to_stand(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    position_noise: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Upright start at the measured stance height (no drop-in transient)."""
    reset_to_posture(
        env,
        env_ids,
        joint_overrides={},
        joint_noise_std=0.0,
        roll_deg=0.0,
        pitch_deg=(0.0, 0.0),
        yaw_range_deg=(-180.0, 180.0),
        height=C.STAND_Z,
        position_noise=position_noise,
        asset_cfg=asset_cfg,
    )


def reset_to_stand_with_sit_blend(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    joint_noise_std: float,
    position_noise: float,
    command_name: str,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Start a sit-stand episode from a pose matching the command it will be given.

    The sit-stand task must not start every episode standing: if it does, the seated
    half of the command distribution is only ever reached by descending, and the policy
    learns to fall into it.

    **Ordering constraint.** mjlab runs reset *events* before ``command_manager.reset``,
    so at this point the flag belongs to the *previous* episode and cannot be followed.
    Writing the flag here is equally wrong the other way: the command manager re-samples
    it immediately afterwards, discarding the write (measured: 21 of 48 resets spawned a
    pose opposite to the command).

    So this event draws the flag itself, spawns the matching pose, and records the draw
    on the command term. ``SitStandCommand`` replays that recorded draw on the reset
    that follows, which makes the spawn and the command consistent regardless of the
    managers' order, instead of depending on it.
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device)
    n = len(env_ids)
    if n == 0:
        return

    term = env.command_manager.get_term(command_name)
    seated = torch.rand(n, device=env.device) < getattr(term.cfg, "sit_prob", 0.5)

    # Hand the draw to the command term; its reset() applies it instead of resampling.
    term.pending_sit_flag[env_ids] = seated.to(term.pending_sit_flag.dtype)
    if hasattr(term, "alpha"):
        term.alpha[env_ids] = seated.to(term.alpha.dtype)

    seated_ids = env_ids[seated]
    if len(seated_ids) > 0:
        reset_to_sit(
            env,
            seated_ids,
            joint_noise_std=joint_noise_std,
            position_noise=position_noise,
            asset_cfg=asset_cfg,
        )

    standing_ids = env_ids[~seated]
    if len(standing_ids) > 0:
        reset_to_stand(
            env, standing_ids, position_noise=position_noise, asset_cfg=asset_cfg
        )
