# Copyright (c) 2026-2027 zh
"""HT 后空翻的板重置、发射参数采样和机器人上台初态。

来源：microduck_rl@d26322f ``tasks/mdp.py`` 的 launch/spawn/plate 事件。
本机板为独立静态实体（freejoint 但逐控制步重写位姿），机器人保持第一个
entity，reset/spawn 直接写 ``qpos[:, 2]``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import ht_microduck_backflip_contract as C
from ht_microduck.tasks.mdp.ht_backflip_state import (
    BACKFLIP_PHASE_GONE,
    _state,
    _time,
    backflip_plate_kinematics,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def _uniform(env: ManagerBasedRlEnv, env_ids: torch.Tensor, rng: tuple[float, float]) -> torch.Tensor:
    lo, hi = rng
    return torch.rand(len(env_ids), device=env.device) * (hi - lo) + lo


def reset_backflip_launch_params(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    hold_range: tuple[float, float] = C.HOLD_RANGE,
    launch_range: tuple[float, float] = C.LAUNCH_RANGE,
    z0_range: tuple[float, float] = C.Z0_RANGE,
    vz_range: tuple[float, float] = C.VZ_RANGE,
    w0_range: tuple[float, float] = C.W0_RANGE,
) -> None:
    """每回合采样一次发射参数，并清空进度/落地/发射门控状态。"""
    if env_ids is None or len(env_ids) == 0:
        return
    _state(env)
    env_ids = env_ids.to(env.device, dtype=torch.long)
    env._backflip_t_hold[env_ids] = _uniform(env, env_ids, hold_range)
    env._backflip_t_launch[env_ids] = _uniform(env, env_ids, launch_range)
    env._backflip_z0[env_ids] = _uniform(env, env_ids, z0_range)
    env._backflip_vz[env_ids] = _uniform(env, env_ids, vz_range)
    env._backflip_w0[env_ids] = _uniform(env, env_ids, w0_range)
    env._backflip_accum[env_ids] = 0.0
    env._backflip_max[env_ids] = 0.0
    env._backflip_paid[env_ids] = 0.0
    env._backflip_land_step[env_ids] = -1.0
    env._backflip_launch_gate[env_ids] = -1.0


def reset_backflip_robot_on_plate(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    stand_z: float = C.STAND_Z,
    plate_half_thickness: float = C.PLATE_HALF_THICKNESS,
) -> None:
    """把机器人放在本回合 ``z0`` 对应板顶，高度与 ``ready_stance`` 一致。"""
    if env_ids is None or len(env_ids) == 0:
        return
    _state(env)
    env_ids = env_ids.to(env.device, dtype=torch.long)
    origin_z = env.scene.env_origins[env_ids, 2]
    env.sim.data.qpos[env_ids, 2] = (
        origin_z + env._backflip_z0[env_ids] + plate_half_thickness + stand_z
    )
    env.sim.data.qvel[env_ids, :6] = 0.0


def backflip_plate_step(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None = None,
    asset_name: str = "plate",
    t_override: float | None = None,
) -> None:
    """逐控制步写入板的位姿和速度；模板 reset 时传 ``t_override=0``。"""
    t_hold, t_launch, z0, vz, w0, *_ = _state(env)
    t = _time(env) if t_override is None else torch.full_like(t_hold, float(t_override))
    z, pitch, vz_t, w_t, phase = backflip_plate_kinematics(
        t, t_hold, t_launch, z0, vz, w0
    )
    plate = env.scene[asset_name]
    n = env.num_envs
    all_ids = torch.arange(n, device=env.device)
    # reset 事件可能只重置一部分环境；只写这些环境，避免把邻居的板瞬移回 z0。
    ids = all_ids if env_ids is None else env_ids.to(env.device, dtype=torch.long)
    if len(ids) == 0:
        return
    gone = (phase == BACKFLIP_PHASE_GONE).to(z.dtype)
    origins = env.scene.env_origins
    pose = torch.zeros(n, 7, device=env.device)
    pose[:, 0] = origins[:, 0] + gone * C.PLATE_GONE_POS[0]
    pose[:, 1] = origins[:, 1] + gone * C.PLATE_GONE_POS[1]
    pose[:, 2] = origins[:, 2] + z
    pose[:, 3] = torch.cos(pitch * 0.5)
    pose[:, 5] = torch.sin(pitch * 0.5)
    vel = torch.zeros(n, 6, device=env.device)
    vel[:, 2] = vz_t
    vel[:, 4] = w_t
    plate.write_root_link_pose_to_sim(pose[ids], ids)
    plate.write_root_link_velocity_to_sim(vel[ids], ids)
