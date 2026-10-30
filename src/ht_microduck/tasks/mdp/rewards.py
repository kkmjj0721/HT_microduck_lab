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
from mjlab.tasks.velocity.mdp import feet_air_time as feet_air_time
from mjlab.tasks.velocity.mdp import feet_swing_height as MjlabFeetSwingHeight

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.managers.reward_manager import RewardTermCfg

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


def stand_still(
    env: ManagerBasedRlEnv,
    command_name: str,
    command_threshold: float,
    asset_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Return joint deviation from the default pose only for an idle twist."""
    asset = _asset(env, asset_cfg)
    default = asset.data.default_joint_pos
    assert default is not None
    ids = asset_cfg.joint_ids
    deviation = (asset.data.joint_pos[:, ids] - default[:, ids]).abs().sum(dim=1)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    idle = torch.norm(command[:, :2], dim=1) + command[:, 2].abs() <= command_threshold
    return deviation * idle.float()


class feet_swing_height(MjlabFeetSwingHeight):
    """Keep mjlab's landing-height formula and clear peaks on episode reset."""

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        if env_ids is None:
            self.peak_heights.zero_()
        else:
            self.peak_heights[env_ids] = 0.0


class head_pose_bias_penalty:
    """Price persistent head error with the official MicroDuck 1 s EMA.

    The per-joint signed error is averaged in time before taking its absolute
    value, so alternating gait motion can cancel while a steady droop cannot.
    This returns a non-negative mean over the selected head joints and therefore
    needs a negative reward weight. MicroDuck's function returns its negative;
    the weighted result is identical.

    Class-based reset replaces upstream's episode-length check so each world's
    bias is cleared through the reward manager's normal reset lifecycle.
    """

    def __init__(self, cfg: RewardTermCfg, env: ManagerBasedRlEnv):
        asset_cfg = cfg.params.get("asset_cfg", _DEFAULT_ASSET_CFG)
        asset = _asset(env, asset_cfg)
        self._ema = torch.zeros_like(asset.data.joint_pos[:, asset_cfg.joint_ids])

    def __call__(
        self,
        env: ManagerBasedRlEnv,
        command_name: str = "head_pose",
        tau_s: float = 1.0,
        asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    ) -> torch.Tensor:
        asset = _asset(env, asset_cfg)
        default = asset.data.default_joint_pos
        assert default is not None
        command = env.command_manager.get_command(command_name)
        assert command is not None
        ids = asset_cfg.joint_ids
        error = asset.data.joint_pos[:, ids] - default[:, ids] - command
        alpha = min(1.0, float(env.step_dt) / max(tau_s, 1e-6))
        self._ema = (1.0 - alpha) * self._ema + alpha * error
        return self._ema.abs().mean(dim=-1)

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        if env_ids is None:
            self._ema.zero_()
        else:
            self._ema[env_ids] = 0.0


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
