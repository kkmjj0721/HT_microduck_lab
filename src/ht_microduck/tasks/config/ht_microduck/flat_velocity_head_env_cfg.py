# Copyright (c) 2026-2027 zh
"""将头颈任务 ID 保留为同一官方 Velocity 配方的独立入口。

官方 Velocity 本身已经训练随机头颈指令；两个入口采用同一环境配方，日志由注册项区分。
"""

from ht_microduck.tasks.config.ht_microduck.flat_velocity_env_cfg import (
    HEAD_POSE_RANGES_FULL,
    make_flat_velocity_env_cfg,
)

HEAD_ACTION_SCALE = 1.0
HEAD_POSE_RANGE_STAGES = (
    (0, ((-0.05, 0.05), (-0.05, 0.05), (-0.07, 0.07), (-0.015, 0.015))),
    (500, ((-0.17, 0.17), (-0.17, 0.17), (-0.21, 0.21), (-0.047, 0.047))),
    (1000, ((-0.39, 0.39), (-0.39, 0.39), (-0.49, 0.49), (-0.11, 0.11))),
    (1500, ((-0.72, 0.72), (-0.72, 0.72), (-0.91, 0.91), (-0.20, 0.20))),
    (2000, HEAD_POSE_RANGES_FULL),
)
BODY_POSE_RANGES = ((-0.005, 0.005),) * 3 + ((-0.05, 0.05),) * 3


def make_flat_velocity_head_env_cfg(
    num_envs: int = 4096, seed: int | None = None, play: bool = False
):
    """为独立任务注册创建新的官方配置实例。"""
    return make_flat_velocity_env_cfg(num_envs=num_envs, seed=seed, play=play)
