# Copyright (c) 2026-2027 zh
"""
内容：
    管理 CyberDuck V2 前滚翻的接地进度、头顶锁存、逐环境去重和差分历史。

依据：microduck_rl@bae39f59 的 mdp.py:7165–7433；本机头部与传感器由独立契约声明。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import cyberduck_v2_roulade_contract as C

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.envs import ManagerBasedRlEnv


def _roulade_state(
    env: ManagerBasedRlEnv,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """一次建立环境设备上的技能状态，并校验任务所需的实体与接触传感器。"""
    if not hasattr(env, "_roulade_accum"):
        for name in (C.SUPPORT_SENSOR, C.HEAD_SENSOR, C.WHEEL_SENSOR):
            if name not in env.scene.sensors:
                raise ValueError(f"Roulade requires contact sensor: {name}")
        asset = env.scene["robot"]
        body_ids, _ = asset.find_bodies(C.HEAD_BODY_NAME)
        if len(body_ids) != 1:
            raise ValueError(f"Roulade requires one head body: {C.HEAD_BODY_NAME}")
        env._roulade_head_body_id = body_ids[0]
        zeros = torch.zeros(env.num_envs, dtype=torch.float32, device=env.device)
        false = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        steps = torch.full((env.num_envs,), -1, dtype=torch.long, device=env.device)
        env._roulade_accum = zeros.clone()
        env._roulade_max = zeros.clone()
        env._roulade_paid = zeros.clone()
        env._roulade_head_latch = false.clone()
        env._roulade_last_update_step = steps.clone()
        env._roulade_standing_start = false.clone()
        env._roulade_success_hold = zeros.clone()
        env._roulade_success = false.clone()
        env._roulade_metric_step = steps.clone()
        env._roulade_prev_forces = asset.data.actuator_force.detach().clone()
        env._roulade_prev_vz = asset.data.root_link_lin_vel_w[:, 2].detach().clone()
        env._roulade_force_step = steps.clone()
        env._roulade_accel_step = steps.clone()
        env._roulade_force_cost = zeros.clone()
        env._roulade_accel_cost = zeros.clone()
    return env._roulade_accum, env._roulade_max, env._roulade_paid


def _lateral_axis_z(quat: torch.Tensor) -> torch.Tensor:
    """返回机体横轴的世界 Z 分量，纯矢状面前翻始终为零。"""
    return 2.0 * (quat[:, 2] * quat[:, 3] + quat[:, 0] * quat[:, 1])


def _head_top_down(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """头顶参考轴朝地面时为真，排除脸部或头侧接地。"""
    _roulade_state(env)
    quat = asset.data.body_link_quat_w[:, env._roulade_head_body_id]
    w, x, y, z = quat.unbind(dim=-1)
    a, b, c = C.HEAD_TOP_AXIS
    axis_world_z = (
        2.0 * (x * z - w * y) * a
        + 2.0 * (y * z + w * x) * b
        + (1.0 - 2.0 * (x.square() + y.square())) * c
    )
    return axis_world_z < -0.3


def _update_roulade_accum(env: ManagerBasedRlEnv, asset: Entity) -> None:
    """每环境每控制步只积分一次，离地和侧滚不增加前滚翻进度。"""
    _roulade_state(env)
    step = int(env.common_step_counter)
    update = env._roulade_last_update_step != step
    found = env.scene.sensors[C.SUPPORT_SENSOR].data.found
    supported = (found.reshape(env.num_envs, -1) > 0).any(dim=-1)
    omega = torch.nan_to_num(asset.data.root_link_ang_vel_b[:, 1], nan=0.0)
    lateral_z = torch.nan_to_num(
        _lateral_axis_z(asset.data.root_link_quat_w), nan=1.0
    ).abs()
    flat = ((0.866 - lateral_z) / (0.866 - 0.5)).clamp(0.0, 1.0)
    delta = omega * env.step_dt * supported * flat.square() * (3.0 - 2.0 * flat)
    env._roulade_accum.copy_(
        torch.where(update, env._roulade_accum + delta, env._roulade_accum)
    )
    env._roulade_max.copy_(torch.maximum(env._roulade_max, env._roulade_accum))
    head_found = env.scene.sensors[C.HEAD_SENSOR].data.found
    head_contact = (head_found.reshape(env.num_envs, -1) > 0).any(dim=-1)
    in_window = (env._roulade_accum > math.radians(20.0)) & (
        env._roulade_accum < math.radians(170.0)
    )
    env._roulade_head_latch |= (
        update & head_contact & in_window & _head_top_down(env, asset)
    )
    env._roulade_last_update_step[update] = step


def _roulade_completion_gate(
    env: ManagerBasedRlEnv,
    gate_lo: float,
    gate_hi: float,
    require_head: bool = False,
) -> torch.Tensor:
    """按历史前翻进度平滑开放落地奖励，可额外要求真实头顶接地锁存。"""
    _, frontier, _ = _roulade_state(env)
    blend = ((frontier - gate_lo) / max(gate_hi - gate_lo, 1e-6)).clamp(0.0, 1.0)
    gate = blend.square() * (3.0 - 2.0 * blend)
    return gate * env._roulade_head_latch if require_head else gate


def reset_roulade_history(env: ManagerBasedRlEnv, env_ids: torch.Tensor | None) -> None:
    """回填指定环境的差分历史，不触碰邻居或前滚翻进度。"""
    _roulade_state(env)
    selected = slice(None) if env_ids is None else env_ids
    asset = env.scene["robot"]
    env._roulade_prev_forces[selected] = asset.data.actuator_force[selected].detach()
    env._roulade_prev_vz[selected] = asset.data.root_link_lin_vel_w[
        selected, 2
    ].detach()
    env._roulade_force_step[selected] = -1
    env._roulade_accel_step[selected] = -1
    env._roulade_force_cost[selected] = 0.0
    env._roulade_accel_cost[selected] = 0.0


def roulade_phase(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回前翻最高进度与头顶锁存两维观测，以区分翻前起动和翻后保持。"""
    _update_roulade_accum(env, env.scene["robot"])
    progress = (env._roulade_max / (2.0 * math.pi)).clamp(0.0, 1.0)
    return torch.stack((progress, env._roulade_head_latch.float()), dim=-1)
