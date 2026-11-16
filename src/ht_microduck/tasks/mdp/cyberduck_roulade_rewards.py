# Copyright (c) 2026-2027 zh
"""
内容：
    为 CyberDuck V2 提供前滚翻进度、头部支撑、翻后站立和冲击平滑奖励。

来源：microduck_rl@bae39f59，mdp.py:905–995、1743–1764、2609–2634、7436–7706，
Apache-2.0。沿用数学定义，关节及高度参考由本机配置传入，不依赖 HT 任务。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_state import (
    _head_top_down,
    _lateral_axis_z,
    _roulade_completion_gate,
    _roulade_state,
    _update_roulade_accum,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _stand_target(env, asset, joint_names=None, pattern=None):
    """返回目标姿态张量（参考站立姿态），缺失关节回落到实体默认姿态。

    2026-11-13 起 Roulade/Recovery 的“站好”判据不再用 HOME：`C.STAND_POSE`
    是策略实测稳定站姿（零动作 4 秒、16 环境验证），HOME 的 yaw/roll 全 0，
    物理上稳不住。未在 `C.STAND_POSE` 中列出的关节沿用实体默认值。
    """
    if joint_names is not None:
        joint_ids, _ = asset.find_joints(joint_names, preserve_order=True)
        names = list(joint_names)
    else:
        key = pattern or r"^(?!passive_).*"
        if not key.startswith(r"^(?!passive_)"):
            key = r"^(?!passive_)" + key.lstrip("^")
        joint_ids, names = asset.find_joints(key)
    target = asset.data.default_joint_pos.clone()
    values = [C.STAND_POSE.get(name) for name in names]
    index = torch.tensor(
        [i for i, value in enumerate(values) if value is not None],
        dtype=torch.long,
        device=env.device,
    )
    if len(index) > 0:
        joints = torch.tensor(joint_ids, dtype=torch.long, device=env.device)[index]
        target[:, joints] = torch.tensor(
            [values[i] for i in range(len(values)) if values[i] is not None],
            dtype=target.dtype,
            device=env.device,
        )
    return torch.tensor(joint_ids, dtype=torch.long, device=env.device), target


def roulade_progress(
    env: ManagerBasedRlEnv,
    target_angle: float = 2 * math.pi,
    max_paid_rate: float = 3.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """只支付新增最高进度，超速部分直接舍弃，摇摆或超过一圈不能重复刷分。"""
    _update_roulade_accum(env, env.scene[asset_cfg.name])
    _, frontier, paid = _roulade_state(env)
    new_paid = frontier.clamp(max=target_angle)
    delta = (new_paid - paid.clamp(max=target_angle)).clamp(
        0.0, max_paid_rate * env.step_dt
    )
    env._roulade_paid.copy_(torch.maximum(paid, new_paid))
    return delta / (env.step_dt * target_angle)


def roulade_head_pivot(
    env: ManagerBasedRlEnv,
    sensor_name: str = C.HEAD_SENSOR,
    angle_lo: float = math.radians(30.0),
    angle_hi: float = math.radians(240.0),
    rate_norm: float = 2.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """奖励滚动中的头部支撑，静态趴头没有收益，头顶朝下比脸部支撑得分高。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    found = env.scene.sensors[sensor_name].data.found
    contact = (found.reshape(env.num_envs, -1) > 0).any(dim=-1)
    accum, _, _ = _roulade_state(env)
    in_window = (accum > angle_lo) & (accum < angle_hi)
    rate = (
        torch.nan_to_num(asset.data.root_link_ang_vel_b[:, 1], nan=0.0) / rate_norm
    ).clamp(0.0, 1.0)
    return contact * in_window * rate * (0.3 + 0.7 * _head_top_down(env, asset))


def roulade_landing_composite(
    env: ManagerBasedRlEnv,
    target_height: float,
    height_std: float,
    upright_std: float,
    pose_std: float,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """高度、直立和所选腿位置相对参考站姿匹配的乘积，仅在经头顶滚过后支付。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    height_score = torch.exp(-((z - target_height) / height_std).square())
    quat = asset.data.root_link_quat_w
    tilt_sq = 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright_score = torch.exp(-tilt_sq / (upright_std * upright_std))
    position = asset.data.joint_pos[:, asset_cfg.joint_ids]
    # 参考姿态用 C.STAND_POSE（策略实测稳定站姿），不是 HOME。
    names = tuple(asset_cfg.joint_names or ())
    _, stand = _stand_target(env, asset, joint_names=names or None)
    target = stand[:, asset_cfg.joint_ids]
    pose_score = torch.exp(
        -(position - target).square().mean(dim=-1) / (pose_std * pose_std)
    )
    return (
        height_score
        * upright_score
        * pose_score
        * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    )


def roulade_upright_after_roll(
    env: ManagerBasedRlEnv,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后使用正余弦直立反馈，翻转前不产生常驻直立收益。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    quat = asset.data.root_link_quat_w
    upright = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    return upright.clamp(min=0.0) * _roulade_completion_gate(
        env, gate_lo, gate_hi, require_head=True
    )


def roulade_height_after_roll(
    env: ManagerBasedRlEnv,
    target_height: float,
    std: float = 0.04,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后以宽高度高斯引导恢复支撑高度。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    return torch.exp(-((z - target_height) / std).square()) * _roulade_completion_gate(
        env, gate_lo, gate_hi, require_head=True
    )


def roulade_landing_sharp(
    env: ManagerBasedRlEnv,
    target_height: float,
    height_std: float = 0.015,
    upright_std: float = 0.3,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后以窄高斯改善停在低姿态或明显倾斜处的情况。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    quat = asset.data.root_link_quat_w
    tilt_sq = 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright = torch.exp(-tilt_sq / (upright_std * upright_std))
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    height = torch.exp(-((z - target_height) / height_std).square())
    return (
        upright
        * height
        * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    )


def roulade_stand_tax(
    env: ManagerBasedRlEnv,
    target_height: float,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回翻转后的负高度缺口，配置须使用正权重。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    return -(target_height - z).clamp(min=0.0) * _roulade_completion_gate(
        env, gate_lo, gate_hi, require_head=True
    )


def roulade_rise_velocity(
    env: ManagerBasedRlEnv,
    max_height: float = 0.125,
    gate_lo: float = math.radians(180.0),
    gate_hi: float = math.radians(260.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后半程奖励向上速度，达到目标高度后关闭，避免站立跳动刷分。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    return (
        vz.clamp(min=0.0)
        * (z < max_height)
        * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    )


def roulade_overspeed_penalty(
    env: ManagerBasedRlEnv,
    omega_max: float = 4.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回机身俯仰超速的正平方代价，配置须使用负权重。"""
    omega = torch.nan_to_num(
        env.scene[asset_cfg.name].data.root_link_ang_vel_b[:, 1], nan=0.0
    )
    return (omega.abs() - omega_max).clamp(min=0.0).square()


def roulade_flatness_penalty(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """返回横轴偏离水平的平方代价，纯俯仰翻转时为零。"""
    return torch.nan_to_num(
        _lateral_axis_z(env.scene[asset_cfg.name].data.root_link_quat_w), nan=0.0
    ).square()


def roulade_sagittal_penalty(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """返回机身横滚和偏航角速度的平方和，保留前翻俯仰自由度。"""
    omega = env.scene[asset_cfg.name].data.root_link_ang_vel_b
    return torch.nan_to_num(omega[:, 0].square() + omega[:, 2].square(), nan=0.0)


def roulade_lateral_velocity_penalty(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """返回机体系侧向线速度平方代价。"""
    return torch.nan_to_num(
        env.scene[asset_cfg.name].data.root_link_lin_vel_b[:, 1].square(), nan=0.0
    )


def body_ang_vel_at_height(
    env: ManagerBasedRlEnv,
    height_low: float,
    height_high: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    tilt_full_deg: float | None = None,
    tilt_zero_deg: float = 45.0,
) -> torch.Tensor:
    """按高度和可选倾角门控机身世界 XY 角速度平方代价。"""
    asset = env.scene[asset_cfg.name]
    velocity = asset.data.body_link_ang_vel_w[:, asset_cfg.body_ids, :].squeeze(1)
    cost = velocity[:, :2].square().sum(dim=-1)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    blend = ((z - height_low) / max(height_high - height_low, 1e-6)).clamp(0.0, 1.0)
    gate = blend.square() * (3.0 - 2.0 * blend)
    if tilt_full_deg is not None:
        quat = asset.data.root_link_quat_w
        cosine = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
        tilt = torch.rad2deg(torch.acos(cosine.clamp(-1.0, 1.0)))
        blend = (
            (tilt_zero_deg - tilt) / max(tilt_zero_deg - tilt_full_deg, 1e-6)
        ).clamp(0.0, 1.0)
        gate = gate * blend.square() * (3.0 - 2.0 * blend)
    return cost * gate


def joint_torque_rate_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """返回相邻控制步执行器力矩差平方和，同一步重复读取保持原值。"""
    _roulade_state(env)
    current = env.scene[asset_cfg.name].data.actuator_force
    step = int(env.common_step_counter)
    update = env._roulade_force_step != step
    cost = (current - env._roulade_prev_forces).square().sum(dim=-1)
    cost = torch.where(env._roulade_force_step < 0, torch.zeros_like(cost), cost)
    env._roulade_force_cost[update] = cost[update]
    env._roulade_prev_forces[update] = current[update].detach()
    env._roulade_force_step[update] = step
    return env._roulade_force_cost


def trunk_vertical_accel_penalty(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """返回负的竖直有限差分加速度绝对值，重置首步消除跨回合冲击。"""
    _roulade_state(env)
    vz = torch.nan_to_num(
        env.scene[asset_cfg.name].data.root_link_lin_vel_w[:, 2], nan=0.0
    )
    step = int(env.common_step_counter)
    update = env._roulade_accel_step != step
    accel = (vz - env._roulade_prev_vz) / env.step_dt
    first = (env.episode_length_buf <= 1) | (env._roulade_accel_step < 0)
    accel = torch.where(first, torch.zeros_like(accel), accel)
    env._roulade_accel_cost[update] = -accel[update].abs()
    env._roulade_prev_vz[update] = vz[update].detach()
    env._roulade_accel_step[update] = step
    return env._roulade_accel_cost


def roulade_recovery_deficit(
    env: ManagerBasedRlEnv,
    target_height: float = C.SUPPORT_HEIGHT,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回翻转后归一化高度亏损，使用负权重使低位停滞持续付出恢复代价。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    deficit = ((target_height - height) / target_height).clamp(0.0, 1.0)
    return deficit * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)


def roulade_supported_upright(
    env: ManagerBasedRlEnv,
    target_height: float,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后仅奖励双侧轮支撑下的直立，以高度平方抑制低位姿态收益。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    found = env.scene.sensors[C.WHEEL_SENSOR].data.found
    contact = (found.reshape(env.num_envs, 4, -1) > 0).any(dim=-1)
    bilateral = contact[:, :2].any(dim=-1) & contact[:, 2:].any(dim=-1)
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    height_gate = (height / target_height).clamp(0.0, 1.0).square()
    quat = asset.data.root_link_quat_w
    body_up_z = 1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright = torch.nan_to_num(body_up_z, nan=0.0).clamp(0.0, 1.0)
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return gate * bilateral * height_gate * upright


def roulade_supported_landing(
    env: ManagerBasedRlEnv,
    target_height: float,
    height_std: float = 0.08,
    upright_std: float = 0.4,
    gate_lo: float = math.radians(260.0),
    gate_hi: float = math.radians(330.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    linear_speed_std: float = C.SUCCESS_LINEAR_SPEED,
    angular_speed_std: float = C.SUCCESS_ANGULAR_SPEED,
) -> torch.Tensor:
    """翻转后奖励双侧轮支撑、适当高度、直立及停止，速度标准沿用行为验收接口。"""
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    found = env.scene.sensors[C.WHEEL_SENSOR].data.found
    contact = (found.reshape(env.num_envs, 4, -1) > 0).any(dim=-1)
    bilateral = contact[:, :2].any(dim=-1) & contact[:, 2:].any(dim=-1)
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    height_score = torch.exp(-((height - target_height) / height_std).square())
    quat = asset.data.root_link_quat_w
    tilt_sq = 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright_score = torch.nan_to_num(
        torch.exp(-tilt_sq / (upright_std * upright_std)), nan=0.0
    )
    linear_sq = asset.data.root_link_lin_vel_w.square().sum(dim=-1)
    angular_sq = asset.data.root_link_ang_vel_b.square().sum(dim=-1)
    speed_score = torch.nan_to_num(
        torch.exp(
            -linear_sq / (linear_speed_std * linear_speed_std)
            - angular_sq / (angular_speed_std * angular_speed_std)
        ),
        nan=0.0,
    )
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return gate * bilateral * height_score * upright_score * speed_score

def roulade_recovery_potential(
    env: ManagerBasedRlEnv,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = 0.06,
    upright_std: float = 0.5,
    gate_lo: float = math.radians(200.0),
    gate_hi: float = math.radians(300.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """连续恢复势能，缓解 260° 门控悬崖。

    原恢复项在 260° 前恒为 0，越过 260° 后低姿态立即按 4×高度亏损扣分，
    形成“翻到 259° 最优、越过 260° 反而净亏”的悬崖；策略因此停在约 259.6°。
    本项把门控放宽到 200–300° 且高度用高斯而非线性亏损，越接近站立越高，
    在低姿态也不产生“越扣越怕”的负梯度。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    height = torch.exp(-((z - target_height) / height_std).square())
    quat = asset.data.root_link_quat_w
    tilt_sq = 2.0 * (quat[:, 1].square() + quat[:, 2].square())
    upright = torch.nan_to_num(
        torch.exp(-tilt_sq / (upright_std * upright_std)), nan=0.0
    )
    return height * upright * _roulade_completion_gate(
        env, gate_lo, gate_hi, require_head=True
    )

def roulade_neck_pose_l2(
    env: ManagerBasedRlEnv,
    pattern: str = r"^(neck|head).*",
    gate_lo: float = math.radians(200.0),
    gate_hi: float = math.radians(300.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回头颈相对 HOME 的平方误差，配置须使用负权重。

    来源：microduck_rl@bae39f59 ``mdp.py`` 的 ``neck_joint_pos_l2``（Apache-2.0），
    该函数用于 spin/roller 系列；Roulade 本身没有头颈姿态项，这是本机修正。
    2026-11-12 观测到策略会把 neck_pitch 顶到 +2.92（上限）、head_pitch 压到 -1.53，
    把 31% 的头部质量压到躯干前方换取低重心；本项把头颈拉回参考姿态
    `C.STAND_POSE`（2026-11-13 起不再用 HOME，见契约说明），只作用于翻完后的站立段。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    if not pattern.startswith(r"^(?!passive_)"):
        pattern = r"^(?!passive_)" + pattern.lstrip("^")
    joint_ids, target = _stand_target(env, asset, joint_names=None, pattern=pattern)
    error = asset.data.joint_pos[:, joint_ids] - target[:, joint_ids]
    error_sq = torch.sum(torch.square(torch.nan_to_num(error, nan=0.0)), dim=1)
    # 只约束翻完后的站立段：滚动中必须收头（tuck 的 neck_pitch=1.0 / head_pitch=0.6），
    # 无门控的 L2 会与收头对抗。
    return error_sq * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)


def roulade_head_upright(
    env: ManagerBasedRlEnv,
    standing_std: float = 0.03,
    gate_lo: float = math.radians(200.0),
    gate_hi: float = math.radians(300.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后奖励头部世界竖直朝上，避免低头晃头但仍保持支撑。

    头部朝上用头部本体的 +z 轴世界分量表示；HOME 下约 1.0，低头姿态约 0.26 甚至为负。
    门控与恢复势能一致，只约束翻完后的站立段，不阻碍滚动过程中的收头。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    if not hasattr(env, "_roulade_head_body_id"):
        body_ids, _ = asset.find_bodies(C.HEAD_BODY_NAME)
        env._roulade_head_body_id = body_ids[0]
    quat = asset.data.body_link_quat_w[:, env._roulade_head_body_id]
    w, x, y, z = quat.unbind(dim=-1)
    up_z = 1.0 - 2.0 * (x.square() + y.square())
    # 同 settle：躺平时头部朝上也能拿满分（stage3 贡献 9.62），必须加站立前置。
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / standing_std).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(up_z, nan=0.0).clamp(0.0, 1.0) * standing * gate


def roulade_com_height(
    env: ManagerBasedRlEnv,
    target_height: float,
    height_std: float = 0.03,
    gate_lo: float = math.radians(200.0),
    gate_hi: float = math.radians(300.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按整机质心高度奖励站立，避免“把 31% 的头折下去”换重心。

    `recovery_potential` 与 `supported_landing` 都只看根体高度，根体是 free joint，
    把头折下去不会改变根高，却能把整机 COM 从 0.223 m 压到 0.186 m。
    本项用 `root_com_pos_w`（子树质心）作目标，低头换重心不再免费。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    com_z = asset.data.root_com_pos_w[:, 2] - env.scene.env_origins[:, 2]
    score = torch.exp(-((com_z - target_height) / height_std).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(score, nan=0.0) * gate


def roulade_settle(
    env: ManagerBasedRlEnv,
    max_linear_speed: float = C.SUCCESS_LINEAR_SPEED,
    max_angular_speed: float = C.SUCCESS_ANGULAR_SPEED,
    target_height: float = C.SUPPORT_HEIGHT,
    standing_std: float = 0.03,
    gate_lo: float = math.radians(200.0),
    gate_hi: float = math.radians(300.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转后奖励“真正停住”，直接对齐验收的 0.2 m/s、0.8 rad/s 阈值。

    2026-11-12 实测：头颈课程后站立段根高 0.2296 m、双侧支撑 0.991、角度 332–379°，
    六项判据里只有角速度不满足——|ω| 中位数 0.98 rad/s，仅 38.1% 的控制步低于 0.8，
    无法连续 0.5 s。原奖励里没有任何“站立段减小运动”的项（arrival_damping 只在
    0→-0.05 且门控高度更低），所以策略可以一直微调而拿满其他项。

    2026-11-14 记录：曾改为有理核 `1/(1+(x/σ)²)` 想让尖峰也保留梯度，但从
    `roulade_jitter_20261114/stage1b` 续训两轮都退化到 0/32（支撑掉到 0.65、
    角度判据 540 帧不达标）。原因是高斯在尖峰时给 ~0、区分度极强，
    换成有理核后尖峰仍有 0.038，站立类奖励（home_pose 33 + yaw_roll 28 +
    stand_action 21）相对主导，策略变得过度保守、不敢完成翻滚。
    **保持高斯核**；尖峰用下面的 `roulade_stand_angvel` 单独处理。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    linear = torch.nan_to_num(asset.data.root_link_lin_vel_w, nan=0.0).norm(dim=-1)
    angular = torch.nan_to_num(asset.data.root_link_ang_vel_b, nan=0.0).norm(dim=-1)
    score = torch.exp(
        -(linear / max_linear_speed).square() - (angular / max_angular_speed).square()
    )
    # 必须真的站着：2026-11-13 从零训练里策略学会翻完直接躺平（根高 0.116 m），
    # 躺着不动同样满足“速度小”，settle 给了 12.01 分，比 roulade_progress(6.5) 还高。
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - target_height) / standing_std).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(score * standing, nan=0.0) * gate


def roulade_posture_l2(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] | None = None,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转完成后全部策略关节相对 HOME 的平方误差，配置须使用负权重。

    2026-11-12 回放实测：策略能站住但站姿不是 HOME——hip_yaw 0.432 / -0.353
    （行程 ±0.436）、hip_roll 0.298 / 0.353、head_roll 0.424（行程 ±0.436），
    腿关节相对 HOME 的 RMS 偏差 0.284 rad。原 composite 的 pose 项只覆盖 8 个腿
    关节、取均值、`pose_std=0.4`，对这类偏差只值约 0.55 分，压不住。

    **门控设成 330–345°，与落地判据一致。** 早先放在 200–300° 的同款实验两轮都在
    600 秒内崩溃（0/32、角度掉到 56–139°）：那种窗口覆盖了整个翻转后半段，
    机器人必须大幅调姿时被扣分，直接压掉了 `roulade_progress` 的信号。
    现在只在翻完（≥330°）之后生效。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, target = _stand_target(env, asset, joint_names=joint_names)
    error = asset.data.joint_pos[:, joint_ids] - target[:, joint_ids]
    error_sq = torch.sum(torch.square(torch.nan_to_num(error, nan=0.0)), dim=1)
    return error_sq * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)


def roulade_stand_stillness(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] | None = None,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转完成后惩罚关节速度平方和，配置须使用负权重。

    站立段关节速度实测（零动作基线 0.000–0.001 rad/s）：腿 0.10–0.57，
    **头颈 3.73 / 4.93 / 4.19**；对应网络动作逐步变化量头颈 1.49–1.93、腿 0.02–0.23。
    即网络在站立段以 bang-bang 方式切换头颈动作，执行器低通后就是肉眼可见的抖动。

    这里用物理关节速度而不是动作变化，避免与滚动阶段的大幅必要动作对抗；
    门控同样设成 330–345°，只在翻完之后生效。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, _ = asset.find_joints(
        joint_names if joint_names is not None else r"^(?!passive_).*",
        preserve_order=joint_names is not None,
    )
    velocity = torch.nan_to_num(asset.data.joint_vel[:, joint_ids], nan=0.0)
    cost = torch.sum(torch.square(velocity), dim=1)
    return cost * _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)


def roulade_home_pose(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] | None = None,
    pose_std: float = 0.25,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转完成后奖励“站姿接近 HOME”，是正向奖励而不是惩罚。

    为什么不用惩罚项：实测姿态惩罚（`roulade_posture_l2`，门控 330–345°）会让策略
    学会“不翻过 330°”，因为一旦越过就开始扣分——600 秒实验里角度掉到 273–458°、
    成功率 0/32，正是“逃避惩罚”的悬崖，和 260° 那次同类。
    正向奖励没有这个结构：翻过去只会多一个机会拿分，不翻也扣不到分。

    形态与官方 `landing_composite` 的 pose 因子一致（关节误差均方的高斯），
    但覆盖全部 12 个位置关节（含头颈）、`pose_std` 收紧到 0.25：
    HOME 得 1.0，hip_yaw 0.43 这种偏差只值约 0.2，能形成明确梯度。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, target = _stand_target(env, asset, joint_names=joint_names)
    error = asset.data.joint_pos[:, joint_ids] - target[:, joint_ids]
    # 有理核 1/(1+(rms/σ)²) 而不是高斯：实测策略站姿 RMS 约 0.25 rad，
    # pose_std=0.25 的高斯给 exp(-1)≈0.37，再收紧到 0.12 会掉到 0.014（梯度消失）。
    # 有理核在 0.25 给 0.26、0.12 给 0.61、0.05 给 0.90，全程有梯度。
    rms_sq = torch.nan_to_num(error, nan=1.0).square().mean(dim=-1)
    pose = 1.0 / (1.0 + rms_sq / (pose_std * pose_std))
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / 0.03).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(pose * standing, nan=0.0) * gate


def roulade_stand_still(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] | None = None,
    speed_std: float = 1.0,
    height_std: float = 0.03,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """翻转完成后奖励“关节几乎不动的静止站立”，是正向奖励而不是惩罚。

    为什么必须是正向：任何在门控处才开始扣分的惩罚项，都会让“停在门控下方”
    变成最优。2026-11-13 的实测正是如此——加入 330–345° 门控的姿态/静止惩罚后，
    受支撑前翻从 334–383° 掉到 277.8–324.1°，四项目标奖励全部为 0，
    策略学会了“不翻过 330°”。正向奖励没有这个结构：翻过去只会多拿分。

    度量用 12 个位置关节速度的**均方**（不是求和），核函数用有理式
    `1 / (1 + cost/scale²)` 而不是高斯：高斯在 cost=43（头颈 2.7–4.3 rad/s）
    时得 exp(-43)≈1e-19，梯度完全消失，等于没加这项——2026-11-13 首轮
    `stand_still` 累计只有 0.07 就是这个原因。有理式在同样的 cost 下仍给 0.085，
    梯度持续存在，能把速度真正压下去。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, _ = _stand_target(env, asset, joint_names=joint_names)
    velocity = torch.nan_to_num(asset.data.joint_vel[:, joint_ids], nan=0.0)
    cost = torch.square(velocity).mean(dim=-1)
    score = 1.0 / (1.0 + cost / (speed_std * speed_std))
    # 必须真的站着才算“静止”：2026-11-13 的从零训练里，机器人翻完后直接躺平，
    # 照样拿到 stand_still=13.06、yaw_roll_pose=29.68，根高只有 0.103 m。
    # 躺着不动也满足“不动”，所以用根高做硬前置。
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / height_std).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(score * standing, nan=0.0) * gate


def roulade_head_crown_forward(
    env: ManagerBasedRlEnv,
    angle_lo: float = math.radians(0.0),
    angle_hi: float = math.radians(250.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """起翻到过顶阶段奖励“头顶朝前”，引导直接低头承重而不是先转 yaw。

    2026-11-13 观测：当前策略起翻时 `head_yaw` 会拧到 -1.32 rad、`head_pitch` 顶到
    +1.57，`neck_pitch` 顶到 -1.55；几何上原 tuck（neck +1.0 / head +0.6）让头顶轴
    指向身体后方（crown_up_x=-1.00），身体前俯 90° 时头顶朝上，实际是脸/下巴先着地。
    用户描述的“翻的时候头不转 yaw，直接低头头顶承地”正是这种姿态。
    本项用头顶轴（头部本体 +z）在世界系的 x 分量做正向奖励：正值为头顶朝前。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    if not hasattr(env, "_roulade_head_body_id"):
        body_ids, _ = asset.find_bodies(C.HEAD_BODY_NAME)
        env._roulade_head_body_id = body_ids[0]
    quat = asset.data.body_link_quat_w[:, env._roulade_head_body_id]
    w, x, y, z = quat.unbind(dim=-1)
    # R(q) @ (0,0,1) 的 x 分量
    crown_x = 2.0 * (x * z + w * y)
    blend = ((env._roulade_accum - angle_lo) / max(angle_hi - angle_lo, 1e-6)).clamp(0.0, 1.0)
    window = (blend > 0.0) & (env._roulade_accum <= angle_hi)
    return torch.nan_to_num(crown_x, nan=0.0).clamp(min=0.0) * window.float()


def roulade_head_yaw_penalty(
    env: ManagerBasedRlEnv,
    angle_hi: float = math.radians(250.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """起翻到过顶阶段惩罚 head_yaw，配置须使用负权重。

    实测策略在起翻前 12 个控制步内把 head_yaw 从 -0.08 拧到 -1.32 rad 再转回来，
    这正是用户看到的“先做 yaw 旋转”。前滚翻是矢状面动作，yaw 只会在头颈上产生
    侧向惯性力并让头部偏离承重点。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, _ = asset.find_joints(("head_yaw_joint",), preserve_order=True)
    yaw = asset.data.joint_pos[:, joint_ids]
    target = torch.tensor(
        [C.STAND_POSE.get("head_yaw_joint", 0.0)], dtype=yaw.dtype, device=yaw.device
    )
    blend = (env._roulade_accum / max(angle_hi, 1e-6)).clamp(0.0, 1.0)
    cost = torch.square(yaw - target).sum(dim=-1)
    return torch.nan_to_num(cost, nan=0.0) * blend


def roulade_yaw_roll_pose(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] = (
        "r_hip_yaw_joint", "l_hip_yaw_joint",
        "r_hip_roll_joint", "l_hip_roll_joint",
        "head_roll_joint",
    ),
    pose_std: float = 0.10,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """只约束 yaw/roll 类关节回到参考站姿，用有理核保证梯度。

    2026-11-13 诊断：参考站姿是全对称的（yaw/roll 均为 0），零动作 4 秒验证稳定
    （根高 0.2414、倾角 1.97°、0 跌倒）；把 hip_yaw 人为加到 ±0.43 同样能稳。
    但已训练的策略稳定停在 hip_yaw 0.426 / -0.360、hip_roll 0.084 / 0.385、
    head_roll 0.423，姿态 RMS 0.248；把这几路动作强制归零后 16/16 全倒
    （根高 0.118、倾角 54.8°），说明**偏置是策略学到的习惯，不是站立必需**。

    全局 `home_pose` 的均值会被 7 个本就接近参考的关节摊薄，对这几路只有约 0.43 分；
    这里单独对这 5 路取均方，`pose_std=0.10` 让 0.43 rad 只剩 0.05 分，
    形成足够陡的梯度。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    joint_ids, target = _stand_target(env, asset, joint_names=joint_names)
    error = asset.data.joint_pos[:, joint_ids] - target[:, joint_ids]
    rms_sq = torch.nan_to_num(error, nan=1.0).square().mean(dim=-1)
    score = 1.0 / (1.0 + rms_sq / (pose_std * pose_std))
    # 同 stand_still：只对真的站着的回合支付，否则躺平的 yaw/roll=0 也能拿满分。
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / 0.03).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(score * standing, nan=0.0) * gate


def roulade_stand_action_rate(
    env: ManagerBasedRlEnv,
    joint_names: tuple[str, ...] = (
        "neck_pitch_joint",
        "head_pitch_joint",
        "head_yaw_joint",
        "head_roll_joint",
    ),
    joint_std: float = 0.3,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段奖励“头颈动作每帧不变”，直接打击 25 Hz bang-bang 抖动。

    2026-11-14 诊断：stage7 站立段的**实际关节角度很稳**（neck 在 -0.35~-0.42 之间），
    但策略输出的**目标值每帧剧烈跳变**：-0.457 → -0.545 → -0.062 → -0.163 → -0.323 →
    -0.629 → …，逐步动作变化 head_yaw 均值 0.309、最大 0.636。关节不抖只是因为
    PD 和惯性把它滤掉了，代价是 neck 力矩 43.9% 的时间顶在 2.0 N·m 上限。

    `stand_still` 用关节速度，而关节速度已经被滤过；这里改用**动作差**，
    直接作用于产生跳变的源头。用有理核 `1/(1+cost/σ²)` 而不是平方惩罚：
    平方惩罚在抖动剧烈时梯度极大，会像 §14 的惩罚项一样诱导策略放弃该行为。

    只作用于头颈 4 路：腿和踝需要持续微调维持平衡，压它们的动作会掉支撑。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    # 动作管理器保存的是整条策略输出（14 路），位置项占前 12 路。
    term = env.action_manager.get_term("joint_pos")
    names = list(term.target_names)
    manager = env.action_manager
    offset = sum(manager.action_term_dim[: list(manager.active_terms).index("joint_pos")])
    index = torch.tensor(
        [offset + names.index(n) for n in joint_names], dtype=torch.long, device=env.device
    )
    delta = manager.action[:, index] - manager.prev_action[:, index]
    cost = torch.square(torch.nan_to_num(delta, nan=0.0)).mean(dim=-1)
    score = 1.0 / (1.0 + cost / (joint_std * joint_std))
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / 0.03).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(score * standing, nan=0.0) * gate


def roulade_stand_angvel(
    env: ManagerBasedRlEnv,
    max_angular_speed: float = C.SUCCESS_ANGULAR_SPEED,
    gate_lo: float = math.radians(330.0),
    gate_hi: float = math.radians(345.0),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段直接惩罚“角速度超过判定阈值”，压掉打断 0.5 s 保持的尖峰。

    2026-11-14 逐条统计（`probe_hold.py`）：8 条验收判据里，只有角速度打断
    连续 0.5 s 保持——833 帧不达标，其余 0–7 帧；站立段角速度 p95 = 1.97 rad/s，
    阈值 0.8。`settle` 的高斯核在尖峰时给 ~0（区分度强、方向正确，不能改成有理核：
    实测换成有理核两轮都退化到 0/32），但它只奖励“停住”，缺少对**超限本身**的即时信号。

    本项用 `relu(|ω| - 阈值)²`：低于阈值完全不计，超过后才线性增长，
    与判定语义严格一致，不会像高斯那样在远处梯度消失。配置须使用负权重。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    angular = torch.nan_to_num(asset.data.root_link_ang_vel_b, nan=0.0).norm(dim=-1)
    excess = (angular - max_angular_speed).clamp(min=0.0)
    height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2], nan=0.0
    )
    standing = torch.exp(-((height - C.SUPPORT_HEIGHT) / 0.03).square())
    gate = _roulade_completion_gate(env, gate_lo, gate_hi, require_head=True)
    return torch.nan_to_num(excess.square(), nan=0.0) * standing * gate


def roulade_roll_continuity(
    env: ManagerBasedRlEnv,
    angle_full: float = 2 * math.pi,
    gate_hi: float = math.radians(260.0),
    floor: float = 0.35,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按“已翻过多大比例”持续给分，填补 0–260° 之间的信号真空。

    2026-11-16 诊断：三次从零训练都卡在 127–149°。评估分项显示该状态下
    **只有 `roulade_progress` 为 3.1/8（翻了 140°/360°，本来就只值这么多），
    其余奖励全部为 0 或负数**——因为落地类奖励的门控是 260°/330°，
    `roulade_rise_velocity` 是 180–260°，在 140° 都还没打开。

    于是“继续翻”要冒着掉分风险穿过 120° 的零奖励区，“停下来”反而安全，
    形成梯度上的局部最优陷阱。

    本项把进度本身做成密集信号：`frontier / angle_full` 截断到 1，
    从第一度起就单调递增，260° 之后交给落地类奖励。
    不是 `roulade_progress` 的替代——后者只支付**新增**进度且有速率上限，
    防止摇摆刷分；本项反映当前状态值，用于消除平台。
    """
    asset = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    _, frontier, _ = _roulade_state(env)
    progress = (torch.nan_to_num(frontier, nan=0.0) / angle_full).clamp(0.0, 1.0)
    # 关键：翻过 330° 之后**仍保留 floor 比例**，绝不归零。
    # 三个版本实测的失败模式一致——策略停在门控阈值**前**：
    #   260° 后淡出 30° → 停在 241–261°；淡出到 330° → 停在 243–278°；
    #   330° 前不衰减 → 停在 322–328°，而此时落地类奖励（需真正站起：
    #   根高 0.24 + 双侧支撑）全部为 0.000，翻过去反而丢 18.8 分。
    # 保留 floor 使「越过阈值」永远严格优于「停在阈值前」，消除门控悬崖。
    # 注意 floor 不能低于阈值前的得分，否则仍是悬崖：一度用
    # 「360° 后 30° 内渐变到 0.35」，结果 325° 得 2.71 分、360° 只剩 1.05，
    # 单测直接抓到这个反例。现在 330° 之后**保持满值**，只随 progress 单调增。
    return progress
