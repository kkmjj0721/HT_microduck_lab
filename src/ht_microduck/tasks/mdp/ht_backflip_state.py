# Copyright (c) 2026-2027 zh
"""HT 后空翻的发射参数、相位、空中进度与门控状态。

来源：microduck_rl@d26322f 的 ``tasks/mdp.py`` 后空翻段（Apache-2.0），保留
官方相位机、常加速度板运动学、只支付历史最大值的累计器、发射姿态门控和
完成度门控。本机差异：接触传感器名为 ``robot_ground_contact``，机器人根体为
``base_link``；HOLD 阶段和脚仍踩板时都禁止累计，避免板自身的俯仰扫角
被算成空中后仰；landing 窗口按双脚触地锁存。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import ht_microduck_backflip_contract as C

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.envs import ManagerBasedRlEnv

_GROUND_SENSOR = "robot_ground_contact"
_PLATE_SENSOR = "feet_plate_contact"
_REQUIRED_SENSORS = ("robot_ground_contact", "feet_ground_contact", "feet_plate_contact")
_FLAT_FULL = 0.5
_FLAT_ZERO = 0.866
_GATE_HEIGHT_STD = 0.04
_GATE_TILT_FULL_DEG = 10.0
_GATE_TILT_ZERO_DEG = 45.0

BACKFLIP_PHASE_HOLD = 0
BACKFLIP_PHASE_LAUNCH = 1
BACKFLIP_PHASE_GONE = 2


def backflip_plate_sweep_deg(w0: float, t_launch: float) -> float:
    """板在脚下扫过的俯仰角，官方 hand-like 门控用它限制发射。"""
    return math.degrees(0.5 * w0 * t_launch)


def backflip_plate_kinematics(
    t: torch.Tensor,
    t_hold: torch.Tensor,
    t_launch: torch.Tensor,
    z0: torch.Tensor,
    vz: torch.Tensor,
    w0: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """返回 ``(z, pitch, vz_t, w_t, phase)``。

    ``w0 > 0`` 是“向后翻”的公共约定；绕 +y 的后仰在官方坐标系中为负角速度，
    因此返回的 ``pitch``/``w_t`` 对正 ``w0`` 为负。这个符号由官方方向探针固定，
    不要按“角度为正”重写。
    """
    t_launch = torch.clamp(t_launch, min=1e-4)
    t_rel = t - t_hold
    in_hold = t_rel < 0.0
    in_launch = (~in_hold) & (t_rel < t_launch + 1e-6)
    gone = ~(in_hold | in_launch)

    tau = torch.minimum(torch.maximum(t_rel, torch.zeros_like(t_rel)), t_launch)
    a_lin = vz / t_launch
    a_ang = -w0 / t_launch
    z_ramp = z0 + 0.5 * a_lin * tau * tau
    pitch_ramp = 0.5 * a_ang * tau * tau
    vz_ramp = a_lin * tau
    w_ramp = a_ang * tau

    zero = torch.zeros_like(t)
    z = torch.where(in_hold, z0, z_ramp)
    pitch = torch.where(in_hold, zero, pitch_ramp)
    vz_t = torch.where(in_hold, zero, vz_ramp)
    w_t = torch.where(in_hold, zero, w_ramp)
    z = torch.where(gone, torch.full_like(z, C.PLATE_GONE_POS[2]), z)
    pitch = torch.where(gone, zero, pitch)
    vz_t = torch.where(gone, zero, vz_t)
    w_t = torch.where(gone, zero, w_t)

    phase = torch.where(
        in_hold,
        torch.full_like(t, BACKFLIP_PHASE_HOLD, dtype=torch.long),
        torch.where(
            in_launch,
            torch.full_like(t, BACKFLIP_PHASE_LAUNCH, dtype=torch.long),
            torch.full_like(t, BACKFLIP_PHASE_GONE, dtype=torch.long),
        ),
    )
    return z, pitch, vz_t, w_t, phase


def _state(env: ManagerBasedRlEnv) -> tuple[torch.Tensor, ...]:
    """惰性创建每环境发射参数与进度；``reset_backflip_launch_params`` 清空。"""
    if not hasattr(env, "_backflip_t_hold"):
        for name in _REQUIRED_SENSORS:
            if name not in env.scene.sensors:
                raise ValueError(f"Backflip requires contact sensor: {name}")
        zeros = torch.zeros(env.num_envs, dtype=torch.float32, device=env.device)
        env._backflip_t_hold = torch.full_like(zeros, 1.0)
        env._backflip_t_launch = torch.full_like(zeros, 0.24)
        env._backflip_z0 = torch.full_like(zeros, C.Z0_RANGE[0])
        env._backflip_vz = torch.full_like(zeros, 2.4)
        env._backflip_w0 = torch.full_like(zeros, 5.5)
        env._backflip_accum = zeros.clone()
        env._backflip_max = zeros.clone()
        env._backflip_paid = zeros.clone()
        env._backflip_land_step = torch.full_like(zeros, -1.0)
        env._backflip_launch_gate = torch.full_like(zeros, -1.0)
        env._backflip_last_update_step = -1
    return (
        env._backflip_t_hold,
        env._backflip_t_launch,
        env._backflip_z0,
        env._backflip_vz,
        env._backflip_w0,
        env._backflip_accum,
        env._backflip_max,
        env._backflip_paid,
    )


def _time(env: ManagerBasedRlEnv) -> torch.Tensor:
    return env.episode_length_buf.to(torch.float32) * env.step_dt


def backflip_phase(env: ManagerBasedRlEnv) -> torch.Tensor:
    """HOLD / LAUNCH / GONE 的逐环境相位。"""
    t_hold, t_launch, z0, vz, w0, *_ = _state(env)
    _, _, _, _, phase = backflip_plate_kinematics(
        _time(env), t_hold, t_launch, z0, vz, w0
    )
    return phase


def _finite(value: torch.Tensor, nan: float = 0.0) -> torch.Tensor:
    return torch.nan_to_num(value, nan=nan, posinf=0.0, neginf=0.0)


def _sensor_any_contact(env: ManagerBasedRlEnv, name: str) -> torch.Tensor | None:
    if name not in env.scene.sensors:
        return None
    found = env.scene.sensors[name].data.found
    return (found.reshape(env.num_envs, -1) > 0).any(dim=-1)


def _feet_both_contact(env: ManagerBasedRlEnv, name: str) -> torch.Tensor:
    """两只脚同时接触；传感器 found 的最后一维按脚排列。"""
    if name not in env.scene.sensors:
        raise ValueError(f"Backflip requires contact sensor: {name}")
    found = env.scene.sensors[name].data.found.reshape(env.num_envs, -1)
    if found.shape[-1] < 2:
        raise ValueError(f"Backflip feet sensor {name} must report both feet")
    return found[:, :2].all(dim=-1)


def _lateral_axis_z(quat: torch.Tensor) -> torch.Tensor:
    """机体横轴的世界 z 分量；纯矢状面翻转时接近 0。"""
    return 2.0 * (quat[:, 2] * quat[:, 3] + quat[:, 0] * quat[:, 1])


def _trunk_tilt_smoothstep(
    quat: torch.Tensor, tilt_full_deg: float, tilt_zero_deg: float
) -> torch.Tensor:
    cos_tilt = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    tilt_deg = torch.rad2deg(torch.acos(cos_tilt.clamp(-1.0, 1.0)))
    u = (
        (tilt_zero_deg - tilt_deg) / max(tilt_zero_deg - tilt_full_deg, 1e-6)
    ).clamp(0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _update_accum(env: ManagerBasedRlEnv, asset: Entity) -> None:
    """只累计一次连续离地弧内的后仰角；地面接触清零，HOLD 阶段不计。"""
    _state(env)
    step = int(env.common_step_counter)
    if step == env._backflip_last_update_step:
        return
    phase = backflip_phase(env)
    omega_bwd = -asset.data.root_link_ang_vel_b[:, 1]
    delta = _finite(omega_bwd, nan=0.0) * env.step_dt
    contact = _sensor_any_contact(env, _GROUND_SENSOR)
    airborne = (
        torch.ones_like(delta, dtype=torch.bool) if contact is None else ~contact
    )
    # 本机修正：HOLD 阶段和脚仍踩板时都不算“空中”；板不是 terrain，
    # 否则板自身的 32–45° 扫角会被计入后仰进度。
    airborne = airborne & (phase != BACKFLIP_PHASE_HOLD)
    plate_contact = _sensor_any_contact(env, _PLATE_SENSOR)
    airborne = airborne & ~plate_contact
    delta = delta * airborne
    y_z = _finite(
        _lateral_axis_z(asset.data.root_link_quat_w), nan=1.0
    ).abs()
    flat = ((_FLAT_ZERO - y_z) / (_FLAT_ZERO - _FLAT_FULL)).clamp(0.0, 1.0)
    delta = delta * flat.square() * (3.0 - 2.0 * flat)
    accum = torch.clamp(env._backflip_accum + delta, min=0.0) * airborne
    env._backflip_accum = accum
    env._backflip_max = torch.maximum(env._backflip_max, accum)
    env._backflip_last_update_step = step


def _launch_gate(
    env: ManagerBasedRlEnv,
    asset: Entity,
    hold_z: float,
    floor: float,
) -> torch.Tensor:
    """HOLD→LAUNCH 锁存的发射姿态门控，乘到 progress 和 landing。"""
    _state(env)
    phase = backflip_phase(env)
    fresh = (env._backflip_launch_gate < 0.0) & (phase != BACKFLIP_PHASE_HOLD)
    if bool(fresh.any()):
        z_err = asset.data.root_link_pos_w[:, 2] - (
            env.scene.env_origins[:, 2] + env._backflip_z0 + hold_z
        )
        height = torch.exp(
            -_finite(z_err, nan=1.0).square() / _GATE_HEIGHT_STD**2
        )
        upright = _trunk_tilt_smoothstep(
            _finite(asset.data.root_link_quat_w, nan=0.0),
            _GATE_TILT_FULL_DEG,
            _GATE_TILT_ZERO_DEG,
        )
        on_plate = _sensor_any_contact(env, _PLATE_SENSOR).float()
        env._backflip_launch_gate = torch.where(
            fresh, height * upright * on_plate, env._backflip_launch_gate
        )
    raw = torch.where(
        env._backflip_launch_gate < 0.0,
        torch.ones_like(env._backflip_launch_gate),
        env._backflip_launch_gate,
    )
    return floor + (1.0 - floor) * raw


def _completion_gate(env: ManagerBasedRlEnv) -> torch.Tensor:
    _, _, _, _, _, _, max_accum, _ = _state(env)
    t = (
        (max_accum - C.LANDING_GATE_LO)
        / max(C.LANDING_GATE_HI - C.LANDING_GATE_LO, 1e-6)
    ).clamp(0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _pay(env: ManagerBasedRlEnv, target_angle: float, max_paid_rate: float) -> torch.Tensor:
    *_, max_accum, paid = _state(env)
    new_paid = torch.clamp(max_accum, max=target_angle)
    delta = torch.clamp(new_paid - torch.clamp(paid, max=target_angle), min=0.0)
    delta = torch.clamp(delta, max=max_paid_rate * env.step_dt)
    env._backflip_paid = torch.maximum(paid, new_paid)
    return delta / (env.step_dt * target_angle)


def backflip_hold_window(env: ManagerBasedRlEnv) -> torch.Tensor:
    return (backflip_phase(env) == BACKFLIP_PHASE_HOLD).float()


def _landing_window(
    env: ManagerBasedRlEnv,
    window_s: float,
    sensor_name: str = "feet_ground_contact",
) -> torch.Tensor:
    """从第一次“双脚同时触地”开始锁存固定窗口，与 landing 的脚条件一致。"""
    _state(env)
    step = float(env.common_step_counter)
    contact = _feet_both_contact(env, sensor_name)
    fresh = (env._backflip_land_step < 0.0) & contact
    env._backflip_land_step = torch.where(
        fresh,
        torch.full_like(env._backflip_land_step, step),
        env._backflip_land_step,
    )
    landed = env._backflip_land_step >= 0.0
    elapsed = (step - env._backflip_land_step) * env.step_dt
    return (landed & (elapsed < window_s)).float()
