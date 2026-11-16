# Copyright (c) 2026-2027 zh
"""
内容：
    统计 CyberDuck V2 前滚翻角度、头顶接地及从站立完成并持续稳定落地的成功事件。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_state import (
    _roulade_state,
    _update_roulade_accum,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def roulade_angle(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回本回合受支撑前翻的历史最高角度，单位 rad。"""
    _update_roulade_accum(env, env.scene["robot"])
    return env._roulade_max


def roulade_head_contacted(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回头顶接地是否已锁存；课程中途初态的锁存不代表完整成功。"""
    _update_roulade_accum(env, env.scene["robot"])
    return env._roulade_head_latch.float()


def roulade_success(env: ManagerBasedRlEnv) -> torch.Tensor:
    """完整站立起始、经头顶前翻并双侧稳定支撑连续 0.5 秒才锁存成功。"""
    _roulade_state(env)
    asset = env.scene["robot"]
    _update_roulade_accum(env, asset)
    step = int(env.common_step_counter)
    update = env._roulade_metric_step != step
    found = env.scene.sensors[C.WHEEL_SENSOR].data.found
    wheel_contact = (found.reshape(env.num_envs, 4, -1) > 0).any(dim=-1)
    both_sides = wheel_contact[:, :2].any(dim=-1) & wheel_contact[:, 2:].any(dim=-1)
    quat = asset.data.root_link_quat_w
    cosine = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    height = asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
    # 站姿判据：相对参考站立姿态 C.STAND_POSE 的关节 RMS 误差。
    # 2026-11-13 起不再用 HOME：HOME 的 yaw/roll 全 0，物理上稳不住，
    # 而策略稳定站姿是另一套宽支撑姿态（零动作 4 秒验证通过）。
    joint_ids, _ = asset.find_joints(C.POSITION_JOINTS, preserve_order=True)
    joint_ids = torch.as_tensor(joint_ids, dtype=torch.long)
    target = torch.tensor(
        [C.STAND_POSE[name] for name in C.POSITION_JOINTS],
        dtype=asset.data.joint_pos.dtype,
        device=asset.data.joint_pos.device,
    )
    pose_rms = (
        (asset.data.joint_pos[:, joint_ids] - target).square().mean(dim=-1).sqrt()
    )
    stable = (
        env._roulade_standing_start
        & env._roulade_head_latch
        & (env._roulade_max >= C.COMPLETION_ANGLE)
        & both_sides
        & (cosine >= math.cos(C.SUCCESS_TILT))
        & ((height - C.SUPPORT_HEIGHT).abs() <= C.SUCCESS_HEIGHT_ERROR)
        & (pose_rms <= C.SUCCESS_POSE_RMS)
        & (asset.data.root_link_lin_vel_w.norm(dim=-1) <= C.SUCCESS_LINEAR_SPEED)
        & (asset.data.root_link_ang_vel_b.norm(dim=-1) <= C.SUCCESS_ANGULAR_SPEED)
    )
    hold = torch.where(stable, env._roulade_success_hold + env.step_dt, 0.0)
    env._roulade_success_hold[update] = hold[update]
    # 比较累计步数，避免 float32 的 25 次 0.02 秒加法低于 0.5 秒一个舍入单位。
    required_steps = math.ceil(C.SUCCESS_HOLD_S / env.step_dt)
    held_steps = torch.round(env._roulade_success_hold / env.step_dt)
    env._roulade_success |= update & (held_steps >= required_steps)
    env._roulade_metric_step[update] = step
    return env._roulade_success.float()
