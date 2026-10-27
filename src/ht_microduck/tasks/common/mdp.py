"""MDP terms for the HT-Duck flat velocity task.

Each function is either a thin robot-specific wrapper over mjlab's bundled
implementation or a reimplementation where upstream assumes a robot shape this
one does not have. Differences are noted per function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _asset(env: ManagerBasedRlEnv, cfg: SceneEntityCfg) -> Entity:
    return env.scene[cfg.name]


def track_linear_velocity(
    env: ManagerBasedRlEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward tracking of commanded base linear velocity.

    The commanded z velocity is assumed zero, matching the upstream task.
    """
    asset = _asset(env, asset_cfg)
    command = env.command_manager.get_command(command_name)
    assert command is not None, f"Command '{command_name}' not found."
    actual = asset.data.root_link_lin_vel_b
    xy_error = torch.sum(torch.square(command[:, :2] - actual[:, :2]), dim=1)
    z_error = torch.square(actual[:, 2])
    return torch.exp(-(xy_error + z_error) / std**2)


def upright(
    env: ManagerBasedRlEnv,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward keeping the torso level.

    ``exp(-sum(g_xy**2) / std**2)`` on the projected-gravity xy components, which
    is the form upstream uses. A plain L2 penalty (as in ``flat_orientation_l2``)
    grows without bound and competes badly with the tracking terms.
    """
    asset = _asset(env, asset_cfg)
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    return torch.exp(-torch.sum(torch.square(gravity_xy), dim=1) / std**2)


def track_angular_velocity(
    env: ManagerBasedRlEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward tracking of commanded yaw rate."""
    asset = _asset(env, asset_cfg)
    command = env.command_manager.get_command(command_name)
    assert command is not None, f"Command '{command_name}' not found."
    actual = asset.data.root_link_ang_vel_b
    error = torch.square(command[:, 2] - actual[:, 2])
    return torch.exp(-error / std**2)


def _foot_contact_state(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    sensor = env.scene[sensor_name]
    return sensor.data.found > 0


def feet_air_time(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    threshold_min: float,
    threshold_max: float,
    command_name: str,
    command_threshold: float,
) -> torch.Tensor:
    """Reward long swing phases, but only while walking is commanded.

    Rewards the *earliest* landing after a swing of at least ``threshold_min`` so
    the policy is pushed toward a stepping gait rather than a shuffle. Capped at
    ``threshold_max`` to stop it farming infinite air time.
    """
    sensor = env.scene[sensor_name]
    contact = sensor.data.found > 0
    first_contact = contact & ~getattr(env, "_ht_prev_contact", contact)
    env._ht_prev_contact = contact.clone()

    air_time = getattr(env, "_ht_air_time", torch.zeros_like(contact, dtype=torch.float))
    dt = env.step_dt
    air_time = torch.where(contact, torch.zeros_like(air_time), air_time + dt)
    env._ht_air_time = air_time

    command = env.command_manager.get_command(command_name)
    assert command is not None
    moving = torch.norm(command[:, :2], dim=1) > command_threshold
    reward = torch.sum(
        (air_time - threshold_min).clamp(max=threshold_max) * first_contact, dim=1
    )
    return reward * moving.float()


def feet_clearance(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    target_height: float,
    command_name: str,
    command_threshold: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Penalise swing feet that are not lifted to ``target_height``.

    Uses the foot site heights relative to their HOME height, which is a constant
    offset, so no ground sensor is needed on flat terrain.
    """
    asset = _asset(env, asset_cfg)
    contact = _foot_contact_state(env, sensor_name)
    sites = asset.data.site_pos_w[:, asset_cfg.site_ids, 2]
    # HOME site height is a fixed offset on flat ground; subtract it so the
    # penalty is zero when a foot sits on the ground at its nominal height.
    home_z = getattr(asset.data, "default_site_pos_w", None)
    if home_z is not None:
        sites = sites - home_z[:, asset_cfg.site_ids, 2]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    moving = torch.norm(command[:, :2], dim=1) > command_threshold
    swing = ~contact
    error = torch.square(sites - target_height)
    return torch.sum(error * swing, dim=1) * moving.float()


def feet_slip(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    command_name: str,
    command_threshold: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Penalise horizontal foot velocity while the foot is on the ground."""
    asset = _asset(env, asset_cfg)
    contact = _foot_contact_state(env, sensor_name)
    vel = asset.data.site_lin_vel_w[:, asset_cfg.site_ids, :2]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    moving = torch.norm(command[:, :2], dim=1) > command_threshold
    speed = torch.norm(vel, dim=-1)
    return torch.sum(speed * contact, dim=1) * moving.float()


def illegal_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """Terminate when a body other than the feet touches the ground.

    mjlab's bundled ``illegal_contact`` treats *any* contact on the sensor as
    illegal, which is the right semantics for a sensor built from the torso geoms
    but wrong for a foot sensor. This robot needs both: feet may touch, nothing
    else may.
    """
    sensor = env.scene[sensor_name]
    return torch.any(sensor.data.found > 0, dim=-1)


def state_is_nan(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG) -> torch.Tensor:
    """Terminate on non-finite robot state.

    Without this a single blown-up world keeps contributing NaN rewards and
    poisons the whole PPO batch through the advantage normalisation.
    """
    asset = _asset(env, asset_cfg)
    data = asset.data
    fields = (
        data.joint_pos,
        data.joint_vel,
        data.root_link_pose_w,
        data.root_link_vel_w,
    )
    bad = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    for field in fields:
        bad |= ~torch.isfinite(field).all(dim=-1)
    return bad


def self_collision_cost(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
    """Penalise robot bodies touching each other.

    ``reduce="none"`` with a subtree primary reports every pair, so the count is
    summed across slots rather than any()-ed.
    """
    sensor = env.scene[sensor_name]
    found = sensor.data.found
    if found.dim() == 1:
        return found.float()
    return torch.sum(found, dim=-1).float()
