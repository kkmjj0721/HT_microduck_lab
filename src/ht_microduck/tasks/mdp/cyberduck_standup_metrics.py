# Copyright (c) 2026-2027 zh
"""
内容：
    统计 CyberDuck V2 摔倒起立的高度、倾角、站姿、双侧支撑与最终成功事件。

成功判据与验收一致：根高、倾角、四轮双侧支撑、12 关节相对参考站姿 RMS、
线速度、角速度六项同时满足并连续保持 0.5 s 才锁存成功。
本任务任何初态（俯卧、仰卧、侧卧、坐姿、站姿）都可以达成成功，不设“站姿起始”前置。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from ht_microduck.tasks import cyberduck_v2_standup_contract as C
from ht_microduck.tasks.mdp.cyberduck_standup_state import (
    _standup_state,
    standup_both_sides_supported,
    standup_pose_rms,
    standup_root_height,
    standup_speed_terms,
    standup_tilt_squared,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

# 倾角上限的 2(1-cos) 形式预计算：SUCCESS_TILT 为常量，避免每步反三角。
_TILT_SQUARED_LIMIT = 2.0 * (1.0 - math.cos(C.SUCCESS_TILT))


def standup_height_metric(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回当前根高相对参考站姿的绝对误差，单位 m。"""
    asset = env.scene["robot"]
    return (standup_root_height(env, asset) - C.SUPPORT_HEIGHT).abs()


def standup_tilt_metric(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回当前躯干倾角，单位 rad；直立为 0，倒置为 π。"""
    asset = env.scene["robot"]
    cosine = (1.0 - standup_tilt_squared(asset)).clamp(-1.0, 1.0)
    return torch.acos(cosine)


def standup_pose_metric(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回 12 个位置关节相对参考站姿的 RMS 误差，单位 rad。"""
    return standup_pose_rms(env, env.scene["robot"])


def standup_both_sides_metric(env: ManagerBasedRlEnv) -> torch.Tensor:
    """返回四轮双侧支撑标志，1.0 表示左右各至少一个滚轮接地。"""
    return standup_both_sides_supported(env).float()


def standup_success(env: ManagerBasedRlEnv) -> torch.Tensor:
    """六项判据同时满足并连续保持 0.5 s 才锁存成功，任意初态都可达成。"""
    _standup_state(env)
    asset = env.scene["robot"]
    height = standup_root_height(env, asset)
    pose_rms = standup_pose_rms(env, asset)
    linear, angular = standup_speed_terms(asset)
    # 倾角判据用 1-cos 形式，避免每步反三角；cos(SUCCESS_TILT) 在导入期算一次。
    stable = (
        ((height - C.SUPPORT_HEIGHT).abs() <= C.SUCCESS_HEIGHT_ERROR)
        & (standup_tilt_squared(asset) <= _TILT_SQUARED_LIMIT)
        & standup_both_sides_supported(env)
        & (pose_rms <= C.SUCCESS_POSE_RMS)
        & (linear <= C.SUCCESS_LINEAR_SPEED)
        & (angular <= C.SUCCESS_ANGULAR_SPEED)
    )
    step = int(env.common_step_counter)
    update = env._standup_metric_step != step
    hold = torch.where(
        stable,
        env._standup_success_hold + env.step_dt,
        torch.zeros_like(env._standup_success_hold),
    )
    env._standup_success_hold[update] = hold[update]
    # 用步数比较而不是浮点累加：25 次 0.02 s 相加在 float32 下可能差一个舍入单位。
    required_steps = round(C.SUCCESS_HOLD_S / env.step_dt)
    held_steps = torch.round(env._standup_success_hold / env.step_dt)
    env._standup_success |= update & (held_steps >= required_steps)
    env._standup_metric_step[update] = step
    return env._standup_success.float()


__all__ = [
    "standup_both_sides_metric",
    "standup_height_metric",
    "standup_pose_metric",
    "standup_success",
    "standup_tilt_metric",
]
