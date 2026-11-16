# Copyright (c) 2026-2027 zh
"""
内容：
    采样 CyberDuck 前滚翻的站立和翻转中途初态，并按本机碰撞几何放置到地面。

课程分布参照 microduck_rl@bae39f59 的 mdp.py:7303–7433；关节锚点、几何支撑高度和
滚轮传动按 CyberDuck 模型适配。收身锚点仅通过静态几何检查，不代表动态恢复能力。
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING

import mujoco
import numpy as np
import torch
from mjlab.utils.lab_api.math import quat_apply, quat_from_euler_xyz

from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    MIMIC_JOINT_MAP,
    MIMIC_MULTIPLIER,
)
from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_state import (
    _roulade_state,
    reset_roulade_history,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


# 两腿同号。25组静态候选中此组下半身半径0.17934m，且无超过1mm的自穿透。
# 证据在 .artifacts/roulade-20261109/reset/tuck_candidates.json，不是训练结果。
#
# 头颈在 2026-11-13 更正：原值 neck +1.0 / head +0.6 让头顶轴在世界系指向**身体后方**
# （crown_up_x=-1.00），身体前俯 90° 时头顶朝上，等于用脸/下巴滚过去；实测策略
# 起翻阶段还会把 head_yaw 拧到 -1.32 rad，典型表现就是用户看到的“先转 yaw 再翻”。
# 新值 neck -0.6 / head -0.6 使 crown_up_x=+0.93，身体前俯 90° 时头顶世界 z≈-0.93
# （正面朝下承重），且静态自穿插 0.0（扫描 324 组、53 组满足无穿插且头顶朝前）。
TUCK_JOINT_POS = {
    "r_hip_pitch_joint": 1.4,
    "l_hip_pitch_joint": 1.4,
    "r_calf_joint": 1.4,
    "l_calf_joint": 1.4,
    "neck_pitch_joint": -0.6,
    "head_pitch_joint": -0.6,
}


def init_roulade_geometry(env: ManagerBasedRlEnv, env_ids=None) -> None:
    """一次缓存模型碰撞顶点、关节映射与延迟存储，重置时不重新解析模型。"""
    del env_ids
    model = env.sim.mj_model
    robot = env.scene["robot"]
    geometry = []
    for name in COLLISION_GEOM_NAMES:
        geom = model.geom("robot/" + name)
        kind = int(geom.type[0])
        if kind == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = int(geom.dataid[0])
            start = int(model.mesh_vertadr[mesh])
            count = int(model.mesh_vertnum[mesh])
            # 编译后的mesh坐标与geom_xmat配套；取全部顶点与凸包的支撑极值相同。
            points = model.mesh_vert[start : start + count].copy()
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            points = np.array(list(itertools.product((-1.0, 1.0), repeat=3))) * geom.size
        else:
            raise ValueError(f"Unsupported CyberDuck collision geometry: {name} ({kind})")
        geometry.append((geom.id, torch.as_tensor(points, dtype=torch.float32, device=env.device)))
    position_ids, _ = robot.find_joints(C.POSITION_JOINTS, preserve_order=True)
    follower_ids, _ = robot.find_joints(tuple(MIMIC_JOINT_MAP), preserve_order=True)
    driver_ids = [robot.joint_names.index(name) for name in MIMIC_JOINT_MAP.values()]
    tuck = robot.data.default_joint_pos[0].clone()
    for name, value in TUCK_JOINT_POS.items():
        joint_ids, _ = robot.find_joints((name,), preserve_order=True)
        tuck[joint_ids[0]] = value
    env._roulade_collision_geometry = tuple(geometry)
    env._roulade_position_ids = torch.as_tensor(position_ids, device=env.device)
    env._roulade_follower_ids = torch.as_tensor(follower_ids, device=env.device)
    env._roulade_driver_ids = torch.as_tensor(driver_ids, device=env.device)
    env._roulade_tuck_target = tuck
    # 仅在startup分配原生延迟存储；后续局部backfill不推进邻居的时间指针。
    for actuator in robot.actuators:
        buffer = actuator._delay_buffer
        if buffer is not None and not buffer.is_initialized:
            ids = actuator.target_ids
            buffer.append(torch.stack((
                robot.data.joint_pos_target[:, ids],
                robot.data.joint_vel_target[:, ids],
                robot.data.joint_effort_target[:, ids],
            ), dim=-1))


def reset_roulade_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    standing_prob: float = 0.5,
    midroll_prob: float = 0.5,
    standing_tilt_max: float = math.radians(5.0),
    midroll_pitch_min: float = math.radians(50.0),
    midroll_pitch_max: float = math.radians(340.0),
    midroll_omega_range: tuple[float, float] = (0.0, 3.0),
    tuck_factor_range: tuple[float, float] = (0.3, 1.0),
    joint_noise_std: float = 0.08,
    forward_vel_range: tuple[float, float] = (0.0, 0.0),
) -> None:
    """只重置指定环境，使用世界系位姿和机体系正向俯仰角速度。

    在reset_scene_to_default之后调用。中途初态预付出生角度并开放头部锁存，只用于
    学习剩余过程；standing_start=False保证其不会被统计成完整前滚翻。
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device)
    else:
        env_ids = env_ids.to(device=env.device, dtype=torch.long)
    if len(env_ids) == 0:
        return
    total = standing_prob + midroll_prob
    if standing_prob < 0 or midroll_prob < 0 or total <= 0:
        raise ValueError("Roulade spawn probabilities must be nonnegative with positive total")
    robot = env.scene["robot"]
    accum, frontier, paid = _roulade_state(env)
    count = len(env_ids)
    is_mid = torch.rand(count, device=env.device) < midroll_prob / total
    yaw = torch.rand(count, device=env.device) * (2.0 * math.pi) - math.pi
    roll = (torch.rand(count, device=env.device) * 2.0 - 1.0) * max(standing_tilt_max, math.radians(5.0))
    standing_pitch = (torch.rand(count, device=env.device) * 2.0 - 1.0) * standing_tilt_max
    mid_pitch = torch.rand(count, device=env.device) * (midroll_pitch_max - midroll_pitch_min) + midroll_pitch_min
    pitch = torch.where(is_mid, mid_pitch, standing_pitch)
    quaternion = quat_from_euler_xyz(roll, pitch, yaw)

    # ---------- 关节与传动 ----------
    # 站立/中途初态围绕参考站姿，而不是 HOME（HOME 的 yaw/roll 全 0，稳不住）。
    position = robot.data.default_joint_pos[env_ids].clone()
    stand_ids = [robot.joint_names.index(name) for name in C.STAND_POSE]
    position[:, stand_ids] = torch.tensor(
        [C.STAND_POSE[robot.joint_names[i]] for i in stand_ids],
        dtype=position.dtype,
        device=position.device,
    )
    velocity = robot.data.default_joint_vel[env_ids].clone()
    factor = torch.rand(count, 1, device=env.device) * (tuck_factor_range[1] - tuck_factor_range[0]) + tuck_factor_range[0]
    position += is_mid[:, None] * factor * (env._roulade_tuck_target - position)
    position_ids = env._roulade_position_ids
    noise = torch.randn(count, len(position_ids), device=env.device) * joint_noise_std
    position[:, position_ids] += is_mid[:, None] * noise
    limits = robot.data.joint_pos_limits[env_ids]
    position = torch.clamp(position, min=limits[..., 0], max=limits[..., 1])
    followers, drivers = env._roulade_follower_ids, env._roulade_driver_ids
    position[:, followers] = MIMIC_MULTIPLIER * position[:, drivers]
    velocity[:, followers] = MIMIC_MULTIPLIER * velocity[:, drivers]
    robot.write_joint_state_to_sim(position, velocity, env_ids=env_ids)

    # ---------- 根状态与几何支撑 ----------
    root_pose = torch.cat((env.scene.env_origins[env_ids].clone(), quaternion), dim=-1)
    root_pose[:, 2] += 1.0
    robot.write_root_link_pose_to_sim(root_pose, env_ids=env_ids)
    root_velocity = torch.zeros(count, 6, device=env.device)
    omega = torch.rand(count, device=env.device) * (midroll_omega_range[1] - midroll_omega_range[0]) + midroll_omega_range[0]
    angular_b = torch.zeros(count, 3, device=env.device)
    angular_b[:, 1] = omega * is_mid
    root_velocity[:, 3:] = quat_apply(quaternion, angular_b)
    forward = torch.rand(count, device=env.device) * (forward_vel_range[1] - forward_vel_range[0]) + forward_vel_range[0]
    root_velocity[:, 0] = forward * (~is_mid) * torch.cos(yaw)
    root_velocity[:, 1] = forward * (~is_mid) * torch.sin(yaw)
    robot.write_root_link_velocity_to_sim(root_velocity, env_ids=env_ids)
    # 在高处刷新正运动学，避免临时深埋地面产生无意义的接触求解。
    env.sim.forward()
    minimum = torch.full((count,), float("inf"), device=env.device)
    for geom_id, points in env._roulade_collision_geometry:
        rotation_z = env.sim.data.geom_xmat[env_ids, geom_id].reshape(count, 3, 3)[:, 2]
        world_z = env.sim.data.geom_xpos[env_ids, geom_id, 2]
        lowest = world_z + (rotation_z @ points.T).amin(dim=1)
        minimum = torch.minimum(minimum, lowest)
    root_pose[:, 2] += env.scene.env_origins[env_ids, 2] + 0.001 - minimum
    robot.write_root_link_pose_to_sim(root_pose, env_ids=env_ids)

    # ---------- 控制目标、延迟与回合状态 ----------
    robot.set_joint_position_target(position, env_ids=env_ids)
    robot.set_joint_velocity_target(velocity, env_ids=env_ids)
    robot.set_joint_effort_target(torch.zeros_like(position), env_ids=env_ids)
    for actuator in robot.actuators:
        buffer = actuator._delay_buffer
        if buffer is not None:
            ids = actuator.target_ids
            buffer.backfill(torch.stack((
                robot.data.joint_pos_target[:, ids],
                robot.data.joint_vel_target[:, ids],
                robot.data.joint_effort_target[:, ids],
            ), dim=-1), env_ids)
    spawn_angle = torch.where(is_mid, mid_pitch, torch.zeros_like(mid_pitch))
    accum[env_ids] = spawn_angle
    frontier[env_ids] = spawn_angle
    paid[env_ids] = spawn_angle
    env._roulade_head_latch[env_ids] = is_mid
    env._roulade_standing_start[env_ids] = ~is_mid
    env._roulade_success_hold[env_ids] = 0.0
    env._roulade_success[env_ids] = False
    env._roulade_last_update_step[env_ids] = env.common_step_counter
    env._roulade_metric_step[env_ids] = env.common_step_counter
    reset_roulade_history(env, env_ids)
