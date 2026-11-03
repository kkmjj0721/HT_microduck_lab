# Copyright (c) 2026-2027 zh
"""前坐任务的有效初态、终点姿态奖励与机体系前收脚度量。

本地HT适配，不修改官方移植MDP。姿态与高度由任务配置传入，命令0站立、1前坐；
所有奖励和度量返回与环境同设备的逐环境张量，不规定中间关节运动轨迹。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import quat_apply_inverse

from ht_microduck.tasks.mdp.official_posture_events import (
    _servo_joint_ids,
    set_random_ground_state,
)
from ht_microduck.tasks.mdp.official_posture_rewards import (
    posture_composite,
    posture_stillness,
    upright_while_tall,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


# ---------- 初态边界与姿态读取 ----------
def bounded_forward_ground_state(
    env: ManagerBasedRlEnv, env_ids: torch.Tensor, **params
) -> None:
    """沿用原初态采样，仅将本次重置的策略关节限制在真实硬范围内。"""
    set_random_ground_state(env, env_ids, **params)
    asset = env.scene[params.get("asset_cfg", _DEFAULT_ASSET_CFG).name]
    ids = _servo_joint_ids(env, asset)
    q_adr = asset.indexing.joint_q_adr[ids]
    rows = env_ids[:, None]
    limits = asset.data.joint_pos_limits[env_ids][:, ids]
    sampled = env.sim.data.qpos[rows, q_adr]
    env.sim.data.qpos[rows, q_adr] = sampled.clamp(
        min=limits[..., 0] + 0.005, max=limits[..., 1] - 0.005
    )


def _joint_state(env, command_name, sit_overrides, asset_cfg=_DEFAULT_ASSET_CFG):
    """按策略关节顺序读取实测角、HOME、前坐终点和二值姿态命令。"""
    asset = env.scene[asset_cfg.name]
    ids = _servo_joint_ids(env, asset)
    actual = asset.data.joint_pos[:, ids]
    home = asset.data.default_joint_pos[:, ids]
    seat = home.clone()
    for index, value in sit_overrides.items():
        seat[:, index] = value
    sit = env.command_manager.get_command(command_name)[:, 0]
    return actual, home, seat, sit


def _goal_pose(env, command_name, sit_overrides, asset_cfg=_DEFAULT_ASSET_CFG):
    actual, home, seat, sit = _joint_state(env, command_name, sit_overrides, asset_cfg)
    return actual, home + sit[:, None] * (seat - home)


def _feet_forward_x(env):
    """返回两个足端在躯干机体系中的前向位置，单位米。"""
    asset = env.scene["robot"]
    ids = env.__dict__.get("_forward_foot_site_ids")
    if ids is None:
        ids, _ = asset.find_sites(("r_foot", "l_foot"), preserve_order=True)
        env._forward_foot_site_ids = ids
    offset = asset.data.site_pos_w[:, ids] - asset.data.root_link_pos_w[:, None, :]
    quat = asset.data.root_link_quat_w[:, None, :].expand(-1, 2, -1)
    return quat_apply_inverse(quat.reshape(-1, 4), offset.reshape(-1, 3)).reshape(-1, 2, 3)[..., 0]


def _sit_pose_gate(env, command_name, sit_overrides, hip_indices):
    sit = env.command_manager.get_command(command_name)[:, 0] > 0.5
    actual, target = _goal_pose(env, command_name, sit_overrides)
    hip_error = (actual[:, hip_indices] - target[:, hip_indices]).abs().amax(dim=-1)
    front = (_feet_forward_x(env) > 0.015).all(dim=-1)
    return (~sit | ((hip_error < 0.35) & front)).float()


def _upright_gate(env, asset_cfg=_DEFAULT_ASSET_CFG):
    """正向目标奖励须联合直立程度，避免倒地后凭关节/低位单项拿分。"""
    quat = env.scene[asset_cfg.name].data.root_link_quat_w
    cosine = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    full = math.cos(math.radians(15.0))
    zero = math.cos(math.radians(60.0))
    return ((cosine - zero) / (full - zero)).clamp(0.0, 1.0)


# ---------- 终点姿态与坐高奖励 ----------
def forward_pose_match(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict,
    joint_indices: tuple[int, ...],
    std: float = 0.5,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """最差关节与全腿平均各占一半，约束错误膝角并保留其他关节改善的信号。"""
    actual, target = _goal_pose(env, command_name, sit_overrides, asset_cfg)
    errors = (actual[:, joint_indices] - target[:, joint_indices]).abs()
    error = 0.5 * (errors.amax(dim=-1) + errors.mean(dim=-1))
    return _upright_gate(env, asset_cfg) / (1.0 + error / std)


def forward_action_limit_error(
    env: ManagerBasedRlEnv, action_name: str = "joint_pos"
) -> torch.Tensor:
    """扣除编码器偏置后的请求目标越界L1；避免策略长期请求限位外的无效目标。"""
    term = env.action_manager.get_term(action_name)
    asset = env.scene[term.cfg.entity_name]
    limits = asset.data.joint_pos_limits[:, term.target_ids]
    requested = term.requested_targets
    feasible = requested.clamp(min=limits[..., 0], max=limits[..., 1])
    return (requested - feasible).abs().mean(dim=-1)


def _height_target_and_gate(
    env, command_name, sit_z, stand_z, sit_overrides, hip_indices, asset_cfg
):
    actual, home, seat, sit = _joint_state(env, command_name, sit_overrides, asset_cfg)
    # 配置提供与HOME不同的髋终点；按实际髋进度开启坐高奖励，避免强迫提前下降。
    error = (actual[:, hip_indices] - seat[:, hip_indices]).abs()
    distance = (home[:, hip_indices] - seat[:, hip_indices]).abs()
    progress = (1.0 - (error / distance).mean(dim=-1)).clamp(0.0, 1.0)
    gate = torch.where(sit > 0.5, progress, torch.ones_like(progress))
    target = stand_z + sit * (sit_z - stand_z)
    z = env.scene[asset_cfg.name].data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    return z, target, gate


def forward_height_match(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
    std: float,
    sit_overrides: dict,
    hip_indices: tuple[int, ...] = (2, 7),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """用有理分数区分远离终点的高度，坐下时随真实髋进度开启。"""
    z, target, gate = _height_target_and_gate(
        env, command_name, sit_z, stand_z, sit_overrides, hip_indices, asset_cfg
    )
    return gate * _upright_gate(env, asset_cfg) / (1.0 + (z - target).abs() / std)


def forward_upright_while_tall(
    env: ManagerBasedRlEnv, command_name: str = "twist", **params
) -> torch.Tensor:
    """仅站立命令取得高位直立奖励，基础姿态稳定项由任务单独保留。"""
    sit = env.command_manager.get_command(command_name)[:, 0]
    return upright_while_tall(env, **params) * (1.0 - sit)


def forward_stillness(
    env: ManagerBasedRlEnv,
    sit_overrides: dict,
    hip_indices: tuple[int, ...] = (2, 7),
    **params,
) -> torch.Tensor:
    """坐姿静止奖励须同时满足前收脚和关键髋角，站立沿用原判定。"""
    gate = _sit_pose_gate(env, params["command_name"], sit_overrides, hip_indices)
    return posture_stillness(env, **params) * gate


def forward_composite(
    env: ManagerBasedRlEnv, hip_indices: tuple[int, ...] = (2, 7), **params
) -> torch.Tensor:
    """仅缓变完成后启用原综合奖励，并拒绝后收腿低位替代前坐。"""
    command_name = params["command_name"]
    gate = _sit_pose_gate(env, command_name, params["sit_overrides"], hip_indices)
    sit = env.command_manager.get_command(command_name)[:, 0]
    alpha = env.command_manager.get_term(command_name).alpha
    ramp_done = (sit - alpha).abs() < 0.02
    return posture_composite(env, **params) * gate * ramp_done.float()


# ---------- 独立于奖励的成功度量 ----------
def forward_sit_command_frames(
    env: ManagerBasedRlEnv, command_name: str = "twist"
) -> torch.Tensor:
    """稳定坐下命令帧；与成功帧之比用于计算条件成功率。"""
    command = env.command_manager.get_command(command_name)[:, 0]
    alpha = env.command_manager.get_term(command_name).alpha
    return ((command > 0.5) & (alpha >= 0.98)).float()


def forward_sit_success_frames(
    env: ManagerBasedRlEnv,
    sit_overrides: dict,
    sit_z: float,
    command_name: str = "twist",
    hip_indices: tuple[int, ...] = (2, 7),
) -> torch.Tensor:
    """联合检查稳定命令、双脚前向、髋姿态、低位和躯干倾角。"""
    asset = env.scene["robot"]
    z = asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    quat = asset.data.root_link_quat_w
    cos_tilt = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    stable = forward_sit_command_frames(env, command_name) > 0.5
    pose = _sit_pose_gate(env, command_name, sit_overrides, hip_indices) > 0.5
    height = (z - sit_z).abs() < 0.015
    upright = cos_tilt > math.cos(math.radians(15.0))
    return (stable & pose & height & upright).float()
