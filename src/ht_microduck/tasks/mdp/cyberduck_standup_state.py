# Copyright (c) 2026-2027 zh
"""
内容：
    管理 CyberDuck V2 摔倒起立任务的参考站姿、站立核与逐环境状态缓存。

依据：参考站姿取自 cyberduck_v2_constants.STAND_JOINT_POS，受载根高 0.2416 m、
整机 COM 高 0.1974 m 来自 2026-11-18 新模型实测。站立类奖励统一乘高度核，
防止躺平、坐姿不动等静态姿态刷分。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import cyberduck_v2_standup_contract as C

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.envs import ManagerBasedRlEnv

# 站立高度核的高斯尺度，单位 m；与受载根高 std 0.0009 m 相比留足加载后偏移余量。
STAND_HEIGHT_STD = 0.03
HEAD_JOINTS = ("neck_pitch_joint", "head_pitch_joint", "head_yaw_joint", "head_roll_joint")
# 髋 yaw/roll 与 head_roll 是宽行程、站立时最易漂移的关节。
YAW_ROLL_JOINTS = (
    "r_hip_yaw_joint",
    "l_hip_yaw_joint",
    "r_hip_roll_joint",
    "l_hip_roll_joint",
    "head_roll_joint",
)


def _standup_state(env: ManagerBasedRlEnv) -> None:
    """建立环境设备上的技能状态与关节、身体索引缓存，只解析模型一次。"""
    if hasattr(env, "_standup_success_hold"):
        return
    for name in (C.WHEEL_SENSOR, C.SELF_SENSOR):
        if name not in env.scene.sensors:
            raise ValueError(f"StandUp requires contact sensor: {name}")
    asset = env.scene["robot"]

    def ids_of(joint_names):
        ids, names = asset.find_joints(joint_names, preserve_order=True)
        values = torch.tensor(
            [C.STAND_POSE[name] for name in names],
            dtype=asset.data.joint_pos.dtype,
            device=env.device,
        )
        return torch.as_tensor(ids, dtype=torch.long, device=env.device), values

    position_ids, names = asset.find_joints(C.POSITION_JOINTS, preserve_order=True)
    policy_ids, _ = asset.find_joints(C.POLICY_JOINTS, preserve_order=True)
    actuator_ids, _ = asset.find_actuators(C.POLICY_JOINTS, preserve_order=True)
    head_body_ids, _ = asset.find_bodies(C.HEAD_BODY_NAME)
    if len(head_body_ids) != 1:
        raise ValueError(f"StandUp requires one head body: {C.HEAD_BODY_NAME}")
    env._standup_position_ids = torch.as_tensor(
        position_ids, dtype=torch.long, device=env.device
    )
    env._standup_policy_ids = torch.as_tensor(
        policy_ids, dtype=torch.long, device=env.device
    )
    env._standup_actuator_ids = torch.as_tensor(
        actuator_ids, dtype=torch.long, device=env.device
    )
    env._standup_pose_target = torch.tensor(
        [C.STAND_POSE[name] for name in names],
        dtype=asset.data.joint_pos.dtype,
        device=env.device,
    )
    env._standup_head_body_id = int(head_body_ids[0])
    env._standup_head_joint_ids, env._standup_head_target = ids_of(HEAD_JOINTS)
    env._standup_yaw_roll_ids, env._standup_yaw_roll_target = ids_of(YAW_ROLL_JOINTS)
    # 动作管理器整条策略输出的前 12 路是 joint_pos 动作，头颈在这 12 路中的位置需一次算好。
    manager = env.action_manager
    term = manager.get_term("joint_pos")
    names = list(term.target_names)
    offset = sum(manager.action_term_dim[: list(manager.active_terms).index("joint_pos")])
    env._standup_head_action_index = torch.tensor(
        [offset + names.index(name) for name in HEAD_JOINTS],
        dtype=torch.long,
        device=env.device,
    )
    zeros = torch.zeros(env.num_envs, dtype=torch.float32, device=env.device)
    false = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    steps = torch.full((env.num_envs,), -1, dtype=torch.long, device=env.device)
    env._standup_success_hold = zeros.clone()
    env._standup_success = false.clone()
    env._standup_metric_step = steps.clone()
    env._standup_spawn = torch.full(
        (env.num_envs,), -1, dtype=torch.long, device=env.device
    )
    env._standup_rise_frontier = zeros.clone()
    env._standup_rise_cost = zeros.clone()
    env._standup_rise_step = steps.clone()
    # 只缓存策略控制的 14 路执行器力矩，奖励项直接按此列索引，避免每次切片。
    env._standup_prev_forces = asset.data.actuator_force[:, env._standup_actuator_ids].detach().clone()
    env._standup_prev_vz = asset.data.root_link_lin_vel_w[:, 2].detach().clone()
    env._standup_force_step = steps.clone()
    env._standup_accel_step = steps.clone()
    env._standup_force_cost = zeros.clone()
    env._standup_accel_cost = zeros.clone()


def reset_standup_history(env: ManagerBasedRlEnv, env_ids: torch.Tensor | slice) -> None:
    """回填指定环境的差分历史、势能前沿与成功状态，不影响相邻环境。"""
    _standup_state(env)
    asset = env.scene["robot"]
    env._standup_prev_forces[env_ids] = asset.data.actuator_force[env_ids][
        :, env._standup_actuator_ids
    ].detach()
    env._standup_prev_vz[env_ids] = asset.data.root_link_lin_vel_w[env_ids, 2].detach()
    env._standup_force_step[env_ids] = -1
    env._standup_accel_step[env_ids] = -1
    env._standup_force_cost[env_ids] = 0.0
    env._standup_accel_cost[env_ids] = 0.0
    env._standup_success_hold[env_ids] = 0.0
    env._standup_success[env_ids] = False
    env._standup_metric_step[env_ids] = -1
    # 起身势能前沿按回合重置，否则新回合一开始就拿不到上升增量。
    env._standup_rise_frontier[env_ids] = 0.0
    env._standup_rise_cost[env_ids] = 0.0
    env._standup_rise_step[env_ids] = -1


def standup_root_height(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """返回根体相对本环境地面的高度，单位 m；NaN 按 0 处理。"""
    value = asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    return torch.nan_to_num(value, nan=0.0)


def standup_com_height(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """返回整机子树质心相对本环境地面的高度，单位 m。"""
    value = asset.data.root_com_pos_w[:, 2] - env.scene.env_origins[:, 2]
    return torch.nan_to_num(value, nan=0.0)


def standup_tilt_squared(asset: Entity) -> torch.Tensor:
    """返回 2*(qx²+qy²) = 1-cos(倾角)；水平站立为 0，倒置为 2。"""
    quat = asset.data.root_link_quat_w
    return torch.nan_to_num(2.0 * (quat[:, 1].square() + quat[:, 2].square()), nan=2.0)


def standup_stand_kernel(
    env: ManagerBasedRlEnv,
    asset: Entity,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
) -> torch.Tensor:
    """站立高度核：只有根高接近受载站姿时才支付站立类奖励。"""
    height = standup_root_height(env, asset)
    return torch.exp(-(((height - target_height) / height_std) ** 2))


def standup_height_gate(
    env: ManagerBasedRlEnv,
    asset: Entity,
    height_low: float = 0.55 * C.SUPPORT_HEIGHT,
    height_high: float = C.SUPPORT_HEIGHT,
) -> torch.Tensor:
    """高度平滑门控：低于 low 完全为 0，高于 high 为 1，中间三次平滑过渡。

    用于直立项：它不追求精确站高，但必须挡住“坐姿躯干直立、根高很低”的静态刷分。
    """
    height = standup_root_height(env, asset)
    t = ((height - height_low) / max(height_high - height_low, 1e-6)).clamp(0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def standup_pose_rms(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """返回 12 个位置关节相对参考站姿的 RMS 误差，单位 rad。"""
    joint_pos = asset.data.joint_pos[:, env._standup_position_ids]
    error = torch.nan_to_num(joint_pos - env._standup_pose_target, nan=0.0)
    return torch.sqrt(error.square().mean(dim=-1))


def standup_both_sides_supported(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回左右两侧各至少一个滚轮接地的布尔张量。"""
    found = env.scene.sensors[C.WHEEL_SENSOR].data.found
    contact = (found.reshape(env.num_envs, C.WHEEL_COUNT, -1) > 0).any(dim=-1)
    return contact[:, :2].any(dim=-1) & contact[:, 2:].any(dim=-1)


def standup_speed_terms(asset: Entity) -> tuple[torch.Tensor, torch.Tensor]:
    """返回根体世界系线速度模长与机体系角速度模长。"""
    linear = torch.nan_to_num(asset.data.root_link_lin_vel_w, nan=0.0).norm(dim=-1)
    angular = torch.nan_to_num(asset.data.root_link_ang_vel_b, nan=0.0).norm(dim=-1)
    return linear, angular


def standup_head_axis_z(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """返回头顶参考轴（HEAD_TOP_AXIS）在世界 z 方向的分量，+1 为直立朝上。"""
    quat = asset.data.body_link_quat_w[:, env._standup_head_body_id]
    w, x, y, z = quat.unbind(dim=-1)
    a, b, c = C.HEAD_TOP_AXIS
    axis_z = (
        2.0 * (x * z - w * y) * a
        + 2.0 * (y * z + w * x) * b
        + (1.0 - 2.0 * (x.square() + y.square())) * c
    )
    return torch.nan_to_num(axis_z, nan=0.0)


def standup_head_action_delta(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回头颈 4 路位置动作的逐帧增量，用于直接压制策略输出跳变。"""
    manager = env.action_manager
    index = env._standup_head_action_index
    return torch.nan_to_num(
        manager.action[:, index] - manager.prev_action[:, index], nan=0.0
    )


def standup_rise_potential_value(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """起身势能：归一化根高 × 直立度，两项同时上升才单调增加。"""
    normalized = (standup_root_height(env, asset) / C.SUPPORT_HEIGHT).clamp(0.0, 1.0)
    upright = (1.0 - 0.5 * standup_tilt_squared(asset)).clamp(0.0, 1.0)
    return normalized * (0.5 + 0.5 * upright)


def standup_hold_steps(env: ManagerBasedRlEnv) -> int:
    """成功判据要求连续保持的控制步数。"""
    return math.ceil(C.SUCCESS_HOLD_S / env.step_dt)
