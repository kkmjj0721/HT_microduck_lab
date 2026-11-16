# Copyright (c) 2026-2027 zh
"""HT MicroDuck 后空翻任务的独立接口与验收常量。

本任务按官方 ``microduck_rl@d26322f`` 的 hand-off 结构实现：机器人站在一块
由控制步事件驱动的发射板上，板先抬升后后仰，机器人负责保持站姿、空中收身/蹬板
和落地。官方包线来自约 0.74 kg 的 MicroDuck；HT 约 3.29 kg，因此本文件中的
发射范围是**未标定的临时基线**，必须由本机 CPU 包线探针替换后才能用于正式实验。
actor 仍为 61 维 plate-blind 布局，动作 14 维；critic 额外观察板状态和相位。
"""

from __future__ import annotations

import math

TASK_ID = "HtDuck-Flat-Backflip"
CONTRACT_VERSION = "ht_backflip_obs61_v2"
EXPERIMENT_NAME = "ht_backflip"
RUN_NAME = "ht_backflip_plate"

# ----- 控制周期与接口 -----
PHYSICS_TIMESTEP = 0.005
DECIMATION = 4
CONTROL_HZ = 1.0 / (PHYSICS_TIMESTEP * DECIMATION)
EPISODE_LENGTH_S = 7.6

POLICY_JOINT_NAMES: tuple[str, ...] = (
    "r_hip_yaw_joint",
    "r_hip_roll_joint",
    "r_hip_pitch_joint",
    "r_calf_joint",
    "r_ankle_joint",
    "l_hip_yaw_joint",
    "l_hip_roll_joint",
    "l_hip_pitch_joint",
    "l_calf_joint",
    "l_ankle_joint",
    "neck_pitch_joint",
    "head_pitch_joint",
    "head_yaw_joint",
    "head_roll_joint",
)
ACTION_DIM = len(POLICY_JOINT_NAMES)
ACTION_SCALE = 1.0

ACTOR_OBSERVATION_TERMS: tuple[str, ...] = (
    "base_ang_vel",
    "projected_gravity",
    "joint_pos",
    "joint_vel",
    "actions",
    "command",
    "head_command",
    "body_command",
)
ACTOR_OBSERVATION_DIM = 61

# 与官方 backflip 的 critic 对齐：删除 foot_height，追加板位姿/速度和相位。
CRITIC_OBSERVATION_TERMS: tuple[str, ...] = (
    "base_lin_vel",
    "base_ang_vel",
    "projected_gravity",
    "joint_pos",
    "joint_vel",
    "actions",
    "command",
    "foot_air_time",
    "foot_contact",
    "foot_contact_forces",
    "head_command",
    "body_command",
    "plate_position",
    "plate_velocity",
    "plate_phase",
    "hold_remaining",
)
CRITIC_OBSERVATION_DIM = 82

# ----- 机器人/板几何 -----
# T049 实测 HOME 站姿的躯干高度（地形以上米）。
STAND_Z = 0.1502
# 板中心 = 半厚，板正好落在地面上；板顶 = 2 * 半厚。
PLATE_HALF_THICKNESS = 0.01
Z0_RANGE = (0.010, 0.010)
# 0.30 m 见方，覆盖 HT 约 0.21 m 的外形宽并留出脚部余量。
PLATE_HALF_SIZE = 0.15
PLATE_MASS = 50.0
# 与官方一致的板消失位置：地面以上、机器人旁边，不能放到地面以下。
PLATE_GONE_POS = (5.0, 5.0, 5.0)

# ----- 官方临时代码的发射包线（未在 HT 上标定） -----
# 官方当前 box（d26322f）：z0=0.01, vz 2.20-2.60, w0 5-6, launch 0.22-0.26,
# sweep 32-45 deg，官方实测旋转 198-305 deg、落地 2.37-3.50 m/s、开环闭环 0%。
# 这些数值是为 0.74 kg 机器人测的，HT 质量约 4.47 倍；在本机包线探针完成前，
# 只作为可运行的基线，不得在文档或报告中称为 HT 已标定/已验证的包线。
HOLD_RANGE = (1.0, 5.0)
LAUNCH_RANGE = (0.22, 0.26)
VZ_RANGE = (2.20, 2.60)
W0_RANGE = (5.0, 6.0)

# ----- 奖励门控 -----
TARGET_ANGLE = 2.0 * math.pi
MAX_PAID_RATE = 25.0
LANDING_GATE_LO = math.radians(300.0)
LANDING_GATE_HI = math.radians(345.0)
LANDING_WINDOW_S = 1.4
READY_STANCE_WEIGHT = 3.0
LAUNCH_GATE_FLOOR = 0.30
LAUNCH_GATE_FLOOR_FINAL = 0.05
POSE_STD = 0.20

# ----- 行为验收 -----
SUCCESS_ANGLE = math.radians(330.0)
SUCCESS_TILT_DEG = 20.0
SUCCESS_HEIGHT_TOL = 0.025
SUCCESS_LIN_VEL = 0.2
SUCCESS_ANG_VEL = 0.8
SUCCESS_HOLD_S = 0.5
SUCCESS_RATE_TARGET = 0.80
EVAL_EPISODES = 32
EVAL_SECONDS = 7.4
TRAIN_SECONDS_MIN = 600.0
TRAIN_MAX_ITERATIONS = 10_000
