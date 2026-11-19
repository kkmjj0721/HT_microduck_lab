# Copyright (c) 2026-2027 zh
"""
内容：
    为 CyberDuck V2 摔倒起立提供高度、直立、参考站姿、起身进程与静止奖励。

奖励按新模型实测重标：受载根高 0.2416 m、整机 COM 高 0.1974 m、整机 3.4233 kg、
头部五连杆 0.8666 kg（25.3%）。**所有站立类奖励统一乘站立高度核或高度门控**，
否则躺平、坐姿不动都能满足“低速、低动作变化”并刷分（前滚翻 §16 的教训）。
坐标约定：根高与 COM 高均为相对本环境地面的世界竖直高度，单位 m。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ht_microduck.tasks import cyberduck_v2_standup_contract as C
from ht_microduck.tasks.mdp.cyberduck_standup_state import (
    STAND_HEIGHT_STD,
    _standup_state,
    standup_both_sides_supported,
    standup_head_action_delta,
    standup_head_axis_z,
    standup_height_gate,
    standup_pose_rms,
    standup_rise_potential_value,
    standup_root_height,
    standup_speed_terms,
    standup_stand_kernel,
    standup_tilt_squared,
)
from ht_microduck.tasks.mdp.cyberduck_standup_state import (
    standup_com_height as _com_height,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


# ---------- 站立目标 ----------
def standup_height(
    env: ManagerBasedRlEnv,
    std: float = 0.04,
    target_height: float = C.SUPPORT_HEIGHT,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """根高接近受载站姿的高斯奖励；在倒地到站立的整个行程上给出单调高度信号。"""
    asset = env.scene[asset_cfg.name]
    height = standup_root_height(env, asset)
    return torch.exp(-(((height - target_height) / std) ** 2))


def standup_upright(
    env: ManagerBasedRlEnv,
    upright_std: float = 0.4,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """躯干直立的门控奖励：按 1-cos(倾角) 度量，乘高度门控。

    只做直立而不加高度门控时，坐姿（根高约 0.10 m、躯干竖直）能拿到接近满分，
    而它离站姿还差整个起身行程，因此必须叠加高度门控。
    """
    asset = env.scene[asset_cfg.name]
    tilt_sq = standup_tilt_squared(asset)
    upright = torch.exp(-tilt_sq / (upright_std * upright_std))
    return upright * standup_height_gate(env, asset)


def standup_standing_composite(
    env: ManagerBasedRlEnv,
    height_std: float = 0.04,
    upright_std: float = 0.4,
    pose_std: float = 0.4,
    target_height: float = C.SUPPORT_HEIGHT,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """高度 × 直立 × 参考站姿三联乘积：任一条件不满足都拿不到分。

    结构与官方 StandUp 的 standing_composite 一致；本机把关节目标换成
    ``C.STAND_POSE``（12 路位置关节），高度目标换成新模型受载根高。
    """
    asset = env.scene[asset_cfg.name]
    height_score = standup_height(env, height_std, target_height, asset_cfg)
    upright_score = torch.exp(
        -standup_tilt_squared(asset) / (upright_std * upright_std)
    )
    rms = standup_pose_rms(env, asset)
    pose_score = torch.exp(-((rms / pose_std) ** 2))
    return height_score * upright_score * pose_score


def standup_stance_pose(
    env: ManagerBasedRlEnv,
    pose_std: float = 0.25,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """参考站姿的正向奖励，乘站立高度核；躺平或坐姿拿不到。

    用有理核 1/(1+(rms/σ)²) 而不是高斯：前滚翻实测策略站姿 RMS 约 0.25 rad 时
    高斯只剩 exp(-1)≈0.37，收紧到 0.12 会掉到 0.014，梯度消失。正向奖励不诱导
    “停在阈值前”（前滚翻 §16 的惩罚悬崖教训）。
    """
    asset = env.scene[asset_cfg.name]
    rms = standup_pose_rms(env, asset)
    pose = 1.0 / (1.0 + (rms / pose_std) ** 2)
    return pose * standup_stand_kernel(env, asset, target_height, height_std)


def standup_yaw_roll_pose(
    env: ManagerBasedRlEnv,
    pose_std: float = 0.10,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """只对 5 路宽行程关节（髋 yaw/roll、head_roll）收紧的站姿奖励。

    全局站姿项对 12 关节取均方，7 个本就接近参考的关节会把 0.43 rad 的偏移摊薄；
    前滚翻实测该偏移在全局项下仍值 0.26 分，压不住。
    """
    asset = env.scene[asset_cfg.name]
    error = asset.data.joint_pos[:, env._standup_yaw_roll_ids] - env._standup_yaw_roll_target
    cost = torch.nan_to_num(error, nan=0.0).square().mean(dim=-1)
    pose = 1.0 / (1.0 + cost / (pose_std * pose_std))
    return pose * standup_stand_kernel(env, asset, target_height, height_std)


def standup_com_height(
    env: ManagerBasedRlEnv,
    height_std: float = 0.03,
    target_height: float = C.COM_HEIGHT,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按整机质心高度奖励站立，避免“把头折下去换重心”被漏计。

    根体是 free joint，低头不改变根高，却能把整机 COM 压下去；本项直接看子树质心。
    新模型头部质量占比降到 25.3%，低头换重心的收益变小，但项本身仍防止
    “根高不变、COM 下沉”被高度项漏算。
    """
    asset = env.scene[asset_cfg.name]
    com_z = _com_height(env, asset)
    score = torch.exp(-(((com_z - target_height) / height_std) ** 2))
    return score * standup_stand_kernel(env, asset)


# ---------- 起身过程反馈 ----------
def standup_rise_velocity(
    env: ManagerBasedRlEnv,
    max_height: float = C.SUPPORT_HEIGHT,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """奖励“尚未站到目标高度时的向上根速度”，给探索期提供连续过程信号。

    与官方 com_upward_velocity 同构：只在根高低于目标且竖直速度为正时支付，
    避免“已经站好还往上弹”被重复奖励。
    """
    asset = env.scene[asset_cfg.name]
    height = standup_root_height(env, asset)
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    return torch.clamp(vz, min=0.0) * (height < max_height).float()


def standup_rise_potential(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """起身势能：只支付“比本回合历史最高势能更高”的增量，原地摇晃不能重复刷分。

    势能 = 归一化根高 ×（0.5 + 0.5 × 直立度），两项同时上升才单调增加。
    连续正向过程项若不设单调前沿，策略会在低位小幅起伏反复拿分。
    """
    asset = env.scene[asset_cfg.name]
    _standup_state(env)
    potential = standup_rise_potential_value(env, asset)
    step = int(env.common_step_counter)
    update = env._standup_rise_step != step
    frontier = torch.maximum(env._standup_rise_frontier, potential.detach())
    cost = (frontier - env._standup_rise_frontier).clamp(min=0.0)
    # 回合首步只建立前沿、不支付：否则“重置到站姿”会白送一次满势能。
    first = env._standup_rise_step < 0
    cost = torch.where(first, torch.zeros_like(cost), cost)
    env._standup_rise_cost[update] = cost[update]
    env._standup_rise_frontier[update] = frontier[update]
    env._standup_rise_step[update] = step
    return env._standup_rise_cost


def standup_flat_recovery(
    env: ManagerBasedRlEnv,
    tilt_full_deg: float = 100.0,
    tilt_zero_deg: float = 20.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """倒地但已在恢复面内的连续信号：倾角从 100° 收到 20° 时从 0 平滑升到 1。

    倒地初态倾角接近 90°，此时直立项几乎为 0；本项只依赖倾角、不依赖高度，
    填补“低位翻身”阶段的奖励真空，同时不会奖励躺平（躺平倾角仍接近 90°）。
    """
    asset = env.scene[asset_cfg.name]
    cosine = (1.0 - standup_tilt_squared(asset)).clamp(-1.0, 1.0)
    tilt = torch.rad2deg(torch.acos(cosine))
    blend = ((tilt_full_deg - tilt) / max(tilt_full_deg - tilt_zero_deg, 1e-6)).clamp(0.0, 1.0)
    return blend * blend * (3.0 - 2.0 * blend)


# ---------- 站立段静止与平滑 ----------
def standup_settle(
    env: ManagerBasedRlEnv,
    max_linear_speed: float = C.SUCCESS_LINEAR_SPEED,
    max_angular_speed: float = C.SUCCESS_ANGULAR_SPEED,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """奖励“真的站着且停住”，直接对齐验收的 0.2 m/s、0.8 rad/s 阈值。

    必须乘站立高度核：前滚翻实测躺平不动同样满足“速度小”，settle 曾给 12.01 分，
    比进度奖励还高。本任务倒地是合法初态，不乘高度核会直接奖励趴着不动。
    """
    asset = env.scene[asset_cfg.name]
    linear, angular = standup_speed_terms(asset)
    score = torch.exp(
        -(linear / max_linear_speed) ** 2 - (angular / max_angular_speed) ** 2
    )
    return score * standup_stand_kernel(env, asset, target_height, height_std)


def standup_stand_still(
    env: ManagerBasedRlEnv,
    speed_std: float = 0.5,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段奖励 12 路位置关节几乎不动，用有理核保持梯度；必须乘站立高度核。

    高斯核在头颈抖动 cost≈43 时得 exp(-43)≈1e-19，梯度完全消失；有理核在同样
    代价下仍给 0.085，能把速度真正压下去（前滚翻 §16.4）。
    """
    asset = env.scene[asset_cfg.name]
    velocity = torch.nan_to_num(
        asset.data.joint_vel[:, env._standup_position_ids], nan=0.0
    )
    cost = velocity.square().mean(dim=-1)
    score = 1.0 / (1.0 + cost / (speed_std * speed_std))
    return score * standup_stand_kernel(env, asset, target_height, height_std)


def standup_stand_action_rate(
    env: ManagerBasedRlEnv,
    joint_std: float = 0.3,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段奖励“头颈动作每帧不变”，直接压制 25 Hz bang-bang 抖动。

    前滚翻 §17：站立段关节角很稳，但策略目标值每帧剧烈跳变，joint_vel 已被
    PD 与惯性滤掉，看不见这个源头。只作用于头颈 4 路：腿与踝需要持续微调。
    """
    asset = env.scene[asset_cfg.name]
    delta = standup_head_action_delta(env)
    cost = delta.square().mean(dim=-1)
    score = 1.0 / (1.0 + cost / (joint_std * joint_std))
    return score * standup_stand_kernel(env, asset, target_height, height_std)


def standup_stand_angvel(
    env: ManagerBasedRlEnv,
    max_angular_speed: float = C.SUCCESS_ANGULAR_SPEED,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段惩罚超过验收角速度的尖峰，用 relu(|ω|-阈值)² 保持严格语义。

    前滚翻 §18：settle 的高斯核方向正确但对尖峰缺少即时信号，而打断 0.5 s
    保持的往往就是偶发角速度尖峰。本项低于阈值完全不计。配置须使用负权重。
    """
    asset = env.scene[asset_cfg.name]
    _, angular = standup_speed_terms(asset)
    excess = (angular - max_angular_speed).clamp(min=0.0)
    return excess.square() * standup_stand_kernel(env, asset, target_height, height_std)


# ---------- 姿态与自接触代价 ----------
def standup_neck_pose_l2(
    env: ManagerBasedRlEnv,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段惩罚头颈偏离参考站姿，防止用“低头换重心”维持平衡。

    旧模型头部占比 31.2%、低头能显著降低 COM，策略曾把 neck_pitch 顶到限位；
    新模型降到 25.3% 收益变小，但项本身仍防止头部姿态跑偏。配置须使用负权重。
    """
    asset = env.scene[asset_cfg.name]
    error = asset.data.joint_pos[:, env._standup_head_joint_ids] - env._standup_head_target
    cost = torch.nan_to_num(error, nan=0.0).square().sum(dim=-1)
    return cost * standup_stand_kernel(env, asset, target_height, height_std)


def standup_head_upright(
    env: ManagerBasedRlEnv,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段奖励头部朝上（头顶轴世界 z 为正），乘站立高度核。"""
    asset = env.scene[asset_cfg.name]
    score = standup_head_axis_z(env, asset).clamp(0.0, 1.0)
    return score * standup_stand_kernel(env, asset, target_height, height_std)


def standup_both_sides(
    env: ManagerBasedRlEnv,
    target_height: float = C.SUPPORT_HEIGHT,
    height_std: float = STAND_HEIGHT_STD,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """站立段奖励四轮双侧支撑，乘站立高度核；单侧支撑是起立末段常见失败模式。"""
    asset = env.scene[asset_cfg.name]
    supported = standup_both_sides_supported(env).float()
    return supported * standup_stand_kernel(env, asset, target_height, height_std)


# ---------- 通用平滑与安全代价 ----------
def standup_joint_torque_rate_l2(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回相邻控制步策略执行器力矩差的平方和，同一步重复读取保持原值。"""
    _standup_state(env)
    asset = env.scene[asset_cfg.name]
    current = asset.data.actuator_force[:, env._standup_actuator_ids]
    step = int(env.common_step_counter)
    update = env._standup_force_step != step
    cost = (current - env._standup_prev_forces).square().sum(dim=-1)
    cost = torch.where(env._standup_force_step < 0, torch.zeros_like(cost), cost)
    env._standup_force_cost[update] = cost[update]
    env._standup_prev_forces[update] = current[update].detach()
    env._standup_force_step[update] = step
    return env._standup_force_cost


def standup_trunk_vertical_accel(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """返回负的竖直有限差分加速度绝对值，重置首步消除跨回合冲击。"""
    _standup_state(env)
    asset = env.scene[asset_cfg.name]
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    step = int(env.common_step_counter)
    update = env._standup_accel_step != step
    accel = (vz - env._standup_prev_vz) / env.step_dt
    first = (env.episode_length_buf <= 1) | (env._standup_accel_step < 0)
    accel = torch.where(first, torch.zeros_like(accel), accel)
    env._standup_accel_cost[update] = -accel[update].abs()
    env._standup_prev_vz[update] = vz[update].detach()
    env._standup_accel_step[update] = step
    return env._standup_accel_cost


def standup_body_ang_vel_flat(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot", body_names=("base_link",)),
) -> torch.Tensor:
    """返回根体世界系横滚／俯仰角速度平方和，抑制起立过程中的甩动。"""
    asset = env.scene[asset_cfg.name]
    velocity = asset.data.body_link_ang_vel_w[:, asset_cfg.body_ids, :].squeeze(1)
    return torch.nan_to_num(velocity[:, :2], nan=0.0).square().sum(dim=-1)


def standup_self_contact(
    env: ManagerBasedRlEnv,
    sensor_name: str = C.SELF_SENSOR,
) -> torch.Tensor:
    """返回自接触 geom 对数量；配置须使用负权重。"""
    return env.scene.sensors[sensor_name].data.found.sum(dim=-1).float()


__all__ = [
    "standup_body_ang_vel_flat",
    "standup_both_sides",
    "standup_com_height",
    "standup_flat_recovery",
    "standup_head_upright",
    "standup_height",
    "standup_joint_torque_rate_l2",
    "standup_neck_pose_l2",
    "standup_rise_potential",
    "standup_rise_velocity",
    "standup_self_contact",
    "standup_settle",
    "standup_stance_pose",
    "standup_stand_action_rate",
    "standup_stand_angvel",
    "standup_stand_still",
    "standup_standing_composite",
    "standup_trunk_vertical_accel",
    "standup_upright",
    "standup_yaw_roll_pose",
]


def standup_rise_continuity(
    env: ManagerBasedRlEnv,
    tilt_full_deg: float = 100.0,
    tilt_zero_deg: float = 20.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """起身全过程的密集状态信号：只依赖当前姿态，严格随“越接近站立”单调增加。

    2026-11-18 新模型首次 1800 秒训练的实测失败模式与前滚翻的“奖励真空”同源：
    倒地初态下根高只有 0.09–0.13 m，而 `height`（std=0.04）在该高度只值 1e-6、
    `height_sharp`（std=0.015）为 0、全部站立类奖励因站立核同样为 0。
    于是策略的最优解是“躺平不动”：`flat_recovery` 与 `stand_*` 的站立核一起
    把整条从倒地到站立的路径让成零分，起身只剩 `rise_potential` 的稀疏增量。
    实测 32 回合中倒地类 0/24 成功，末秒根高 0.118 m。

    本项按「根高归一化」与「直立度」的几何平均给出 [0, 1] 连续值，
    倒地时接近 0、站立时接近 1，**不存在任何高度阈值**，因此不会像固定 std 的
    高斯核那样在低位形成悬崖。它反映当前状态值而不是新增量，与
    `roulade_roll_continuity`（前滚翻 §21 的直接修复）同构。
    """
    asset = env.scene[asset_cfg.name]
    normalized = (standup_root_height(env, asset) / C.SUPPORT_HEIGHT).clamp(0.0, 1.0)
    cosine = (1.0 - standup_tilt_squared(asset)).clamp(-1.0, 1.0)
    tilt = torch.rad2deg(torch.acos(cosine))
    blend = ((tilt_full_deg - tilt) / max(tilt_full_deg - tilt_zero_deg, 1e-6)).clamp(0.0, 1.0)
    upright = blend * blend * (3.0 - 2.0 * blend)
    # 几何平均：任一项为 0 时总分为 0，避免"高但躺"或"直但矮"拿到大部分分。
    return torch.sqrt((normalized * upright).clamp(min=0.0))
