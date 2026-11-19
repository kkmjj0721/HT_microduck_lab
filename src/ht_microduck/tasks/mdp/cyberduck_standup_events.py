# Copyright (c) 2026-2027 zh
"""
内容：
    采样 CyberDuck V2 摔倒起立的五种初态，并按实际碰撞几何把它们贴到地面。

初态课程参照 microduck_rl@bae39f59 官方 StandUp 的倒地课程思路；本机改为
俯卧、仰卧、侧卧、坐姿、站姿五类，姿态锚点与几何支撑高度按新模型实测。
本模块只负责静态几何摆放，不代表这些姿态在动力学上可保持。
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import mujoco
import numpy as np
import torch
from mjlab.utils.lab_api.math import quat_from_euler_xyz

from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    MIMIC_JOINT_MAP,
    MIMIC_MULTIPLIER,
)
from ht_microduck.tasks import cyberduck_v2_standup_contract as C
from ht_microduck.tasks.mdp.cyberduck_standup_state import (
    _standup_state,
    reset_standup_history,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def init_standup_geometry(env: ManagerBasedRlEnv, env_ids=None) -> None:
    """一次缓存模型碰撞顶点、关节映射与坐姿锚点，重置时不重新解析模型。"""
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
            # 编译后的 mesh 顶点与 geom_xmat 配套，最低顶点与凸包支撑极值一致。
            points = model.mesh_vert[start : start + count].copy()
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            points = np.array(list(itertools.product((-1.0, 1.0), repeat=3))) * geom.size
        else:
            raise ValueError(f"Unsupported CyberDuck collision geometry: {name} ({kind})")
        geometry.append((geom.id, torch.as_tensor(points, dtype=torch.float32, device=env.device)))
    follower_ids, _ = robot.find_joints(tuple(MIMIC_JOINT_MAP), preserve_order=True)
    driver_ids = [robot.joint_names.index(name) for name in MIMIC_JOINT_MAP.values()]
    sitting = robot.data.default_joint_pos[0].clone()
    for name, value in C.SITTING_JOINT_POS.items():
        joint_ids, _ = robot.find_joints((name,), preserve_order=True)
        sitting[joint_ids[0]] = value
    env._standup_collision_geometry = tuple(geometry)
    env._standup_follower_ids = torch.as_tensor(follower_ids, device=env.device)
    env._standup_driver_ids = torch.as_tensor(driver_ids, device=env.device)
    env._standup_sitting_target = sitting
    # 仅在 startup 分配原生延迟存储；后续局部 backfill 不推进邻居的时间指针。
    for actuator in robot.actuators:
        buffer = actuator._delay_buffer
        if buffer is not None and not buffer.is_initialized:
            ids = actuator.target_ids
            buffer.append(torch.stack((
                robot.data.joint_pos_target[:, ids],
                robot.data.joint_vel_target[:, ids],
                robot.data.joint_effort_target[:, ids],
            ), dim=-1))


def _spawn_orientation(env: ManagerBasedRlEnv, spawn: torch.Tensor) -> torch.Tensor:
    """按初态类别生成世界系根姿态：固定名义角加噪声，侧卧左右随机。"""
    count = len(spawn)
    roll_noise = torch.randn(count, device=env.device)
    pitch_noise = torch.randn(count, device=env.device)
    side_sign = torch.where(torch.rand(count, device=env.device) < 0.5, -1.0, 1.0)
    nominal_roll = torch.zeros(count, device=env.device)
    nominal_pitch = torch.zeros(count, device=env.device)
    scale = torch.zeros(count, device=env.device)
    for slot, posture in enumerate(C.SPAWN_POSTURES):
        selected = spawn == slot
        base_roll, base_pitch, _ = C.SPAWN_ORIENTATION[posture]
        if posture == "side":
            nominal_roll = torch.where(selected, side_sign * abs(base_roll), nominal_roll)
        else:
            nominal_roll = torch.where(selected, torch.full_like(nominal_roll, base_roll), nominal_roll)
        nominal_pitch = torch.where(selected, torch.full_like(nominal_pitch, base_pitch), nominal_pitch)
        scale = torch.where(
            selected,
            torch.full_like(scale, C.SPAWN_ORIENTATION_NOISE[posture]),
            scale,
        )
    yaw = torch.rand(count, device=env.device) * (2.0 * torch.pi) - torch.pi
    roll = nominal_roll + scale * roll_noise
    pitch = nominal_pitch + scale * pitch_noise
    return quat_from_euler_xyz(roll, pitch, yaw)


def reset_standup_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    spawn_weights: tuple[float, ...] = (0.2, 0.2, 0.2, 0.2, 0.2),
    joint_noise_std: float = C.SPAWN_JOINT_NOISE_STD,
) -> None:
    """按课程权重采样五类初态，写入根位姿与关节角后按几何最低点贴地。

    在 ``reset_scene_to_default`` 之后调用。``spawn_weights`` 顺序固定为
    ``C.SPAWN_POSTURES``（standing / sitting / face_down / face_up / side）。
    贴地先在高处做正运动学，取缓存碰撞顶点的全局最低点，再把根高抬到地面以上
    ``C.GROUND_CLEARANCE``，避免重置瞬间深埋地面。
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device)
    else:
        env_ids = env_ids.to(device=env.device, dtype=torch.long)
    if len(env_ids) == 0:
        return
    _standup_state(env)
    weights = torch.tensor(spawn_weights, dtype=torch.float32, device=env.device)
    if len(weights) != len(C.SPAWN_POSTURES) or not torch.isfinite(weights).all() or weights.sum() <= 0:
        raise ValueError("StandUp spawn weights must be finite, nonnegative and match the postures")
    robot = env.scene["robot"]
    count = len(env_ids)

    # ---------- 初态类别与根姿态 ----------
    cumulative = torch.cumsum(weights / weights.sum(), dim=0)
    sample = torch.rand(count, device=env.device)
    # 最后一段用 cumsum 兜底，浮点累加可能略小于 1，越界项夹到末段。
    spawn = torch.searchsorted(cumulative, sample).clamp(max=len(C.SPAWN_POSTURES) - 1)
    env._standup_spawn[env_ids] = spawn
    quaternion = _spawn_orientation(env, spawn)

    # ---------- 关节初值 ----------
    # 站姿、俯卧、仰卧、侧卧都围绕参考站姿加噪声；坐姿换成折叠腿锚点。
    position = robot.data.default_joint_pos[env_ids].clone()
    stand_ids = [robot.joint_names.index(name) for name in C.STAND_POSE]
    position[:, stand_ids] = torch.tensor(
        [C.STAND_POSE[robot.joint_names[i]] for i in stand_ids],
        dtype=position.dtype,
        device=position.device,
    )
    sitting = env._standup_sitting_target[None, :].expand(count, -1)
    is_sitting = (spawn == C.SPAWN_POSTURES.index("sitting")).unsqueeze(-1)
    position = torch.where(is_sitting, sitting, position)
    position_ids = env._standup_position_ids
    position[:, position_ids] += torch.randn(
        count, len(position_ids), device=env.device
    ) * joint_noise_std
    limits = robot.data.joint_pos_limits[env_ids]
    position = torch.clamp(position, min=limits[..., 0], max=limits[..., 1])
    followers, drivers = env._standup_follower_ids, env._standup_driver_ids
    position[:, followers] = MIMIC_MULTIPLIER * position[:, drivers]
    velocity = torch.zeros_like(position)
    robot.write_joint_state_to_sim(position, velocity, env_ids=env_ids)

    # ---------- 根位姿与几何贴地 ----------
    root_pose = torch.cat((env.scene.env_origins[env_ids].clone(), quaternion), dim=-1)
    root_pose[:, 2] += 1.0
    robot.write_root_link_pose_to_sim(root_pose, env_ids=env_ids)
    robot.write_root_link_velocity_to_sim(
        torch.zeros(count, 6, device=env.device), env_ids=env_ids
    )
    # 在高处刷新正运动学，避免临时深埋地面产生无意义的接触求解。
    env.sim.forward()
    minimum = torch.full((count,), float("inf"), device=env.device)
    for geom_id, points in env._standup_collision_geometry:
        rotation_z = env.sim.data.geom_xmat[env_ids, geom_id].reshape(count, 3, 3)[:, 2]
        world_z = env.sim.data.geom_xpos[env_ids, geom_id, 2]
        lowest = world_z + (rotation_z @ points.T).amin(dim=1)
        minimum = torch.minimum(minimum, lowest)
    root_pose[:, 2] += env.scene.env_origins[env_ids, 2] + C.GROUND_CLEARANCE - minimum
    robot.write_root_link_pose_to_sim(root_pose, env_ids=env_ids)

    # ---------- 控制目标、延迟与历史 ----------
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
    reset_standup_history(env, env_ids)


def standup_spawn_names(env: ManagerBasedRlEnv) -> list[str]:
    """返回当前回合各环境初态类别名，供诊断与测试读取。"""
    return [C.SPAWN_POSTURES[int(index)] for index in env._standup_spawn.tolist()]
