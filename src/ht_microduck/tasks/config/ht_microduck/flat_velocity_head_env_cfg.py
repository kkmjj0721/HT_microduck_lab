# Copyright (c) 2026-2027 zh
"""保留随机头颈指令、单位动作缩放与官方课程的独立速度任务。"""

from ht_microduck.tasks.config.ht_microduck.flat_velocity_env_cfg import (
    HEAD_POSE_RANGES_FULL,
    _make_official_velocity_env_cfg,
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
    """从官方基础配方构造头颈任务，不继承普通速度入口的参数覆盖。"""
    from ht_microduck.tasks.config.ht_microduck.official_robot import adapt_official_cfg

    cfg = _make_official_velocity_env_cfg(play=play, rough=False)
    return adapt_official_cfg(cfg, num_envs, seed)
