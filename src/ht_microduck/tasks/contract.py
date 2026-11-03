"""HT 任务的关节、命令槽位、单位及各任务观测布局。

所有任务使用现有14个策略关节，嘴保持HOME；actor宽度61，命令依次为twist3、head4、body6。
官方Velocity critic为76维，StandUp/SitStand为74维，顺序由本文件末尾的逐任务契约定义。
上方原有时序和64维critic常量供受保护的VelStand及旧MDP使用，不改变其已有行为。

关节位置与头部命令为相对HOME的rad；关节速度和基座角速度为rad/s；重力为机体系单位向量。
速度命令为机体系vx/vy（m/s）和wz（rad/s）；body命令为x/y/z（m）及roll/pitch/yaw（rad）。
动作无量纲，由对应任务缩放为目标关节角；设备和float32批量张量沿用环境配置。
"""

from __future__ import annotations

import math

# Control period. dt * decimation must equal 0.02 s = 50 Hz.
PHYSICS_TIMESTEP: float = 0.002
DECIMATION: int = 10
CONTROL_HZ: float = 1.0 / (PHYSICS_TIMESTEP * DECIMATION)

# Per-task episode lengths. The velocity task keeps the original 20 s; the
# posture tasks are short episodic skills. Upstream uses 6 s for standup and 12 s
# for sitstand, and those two are adopted here because they follow from the
# manoeuvre duration rather than from the robot's size.
EPISODE_LENGTH_S: float = 20.0
STANDUP_EPISODE_LENGTH_S: float = 6.0
SITSTAND_EPISODE_LENGTH_S: float = 12.0

# The policy drives the legs and the four neck/head joints. The mouth is a
# display-only degree of freedom: 0.23 rad of range, the lowest-bandwidth servo
# and no balance function, so commanding it would spend an action dimension on
# nothing a task rewards.
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

LEG_JOINT_NAMES: tuple[str, ...] = POLICY_JOINT_NAMES[:10]
HEAD_JOINT_NAMES: tuple[str, ...] = POLICY_JOINT_NAMES[10:]

# Held at HOME by the action term; never part of the action vector.
HELD_JOINT_NAMES: tuple[str, ...] = ("mouth_joint",)

ACTION_DIM: int = len(POLICY_JOINT_NAMES)

# Raw actions are mapped to joint targets as
#     target = HOME + ACTION_SCALE * action
# 1.0 rad matches upstream, which uses ``scale=1.0`` for its servos: at the
# default Gaussian init the sampled offsets can reach the leg joint limits, which
# is what a fall or a rise needs in order to be explored at all. The previous
# 0.25 was chosen for a walking-only 10-actuator policy and would make a sit or a
# get-up unreachable from the policy's own output range.
ACTION_SCALE: float = 1.0

# SitStand/VelStand 在扣除编码器偏置后，将绝对位置目标限制在实际硬关节范围内。
# 动作维度、单位及上一动作观测保持原值；bound_targets=False显式恢复旧目标语义。
# 坐姿膝关节偏移约1.6 rad，不能用统一±1的原始动作裁剪替代逐关节目标约束。

# Walking uses the smaller exploration amplitude from 9840fa8; posture skills
# retain ACTION_SCALE so sitting and rising remain reachable. Same vector layout
# does not imply the same action-to-target mapping between these tasks.
WALKING_ACTION_SCALE: float = 0.25

# Observation layout. The order of this tuple is the observation vector order and
# must not be changed without retraining: the policy's first layer indexes it.
#
# The three command slots are always present, in this order, even when a task
# uses only one of them. Runtime policy selection must additionally load the
# matching task's action scale.
ACTOR_OBSERVATION_TERMS: tuple[str, ...] = (
    "base_ang_vel",       # 3  body-frame angular velocity, rad/s
    "projected_gravity",  # 3  unit gravity vector, body frame
    "joint_pos",          # 14 position relative to HOME, rad
    "joint_vel",          # 14 joint velocity, rad/s
    "actions",            # 14 previous action
    "command",            # 3  twist command (vx, vy, wz); vx carries the posture flag
    "head_command",       # 4  head pose delta from HOME, rad
    "body_command",       # 6  trunk pose delta from nominal standing, m and rad
)

ACTOR_OBSERVATION_DIMS: dict[str, int] = {
    "base_ang_vel": 3,
    "projected_gravity": 3,
    "joint_pos": ACTION_DIM,
    "joint_vel": ACTION_DIM,
    "actions": ACTION_DIM,
    "command": 3,
    "head_command": 4,
    "body_command": 6,
}

ACTOR_OBSERVATION_DIM: int = sum(
    ACTOR_OBSERVATION_DIMS[name] for name in ACTOR_OBSERVATION_TERMS
)

# Byte offsets of each term inside the flat actor vector. Read this instead of
# recomputing slices: reward terms that inspect a command slot must not depend on
# the term order staying what it is today.
ACTOR_OBSERVATION_SLICES: dict[str, slice] = {}
_offset = 0
for _name in ACTOR_OBSERVATION_TERMS:
    ACTOR_OBSERVATION_SLICES[_name] = slice(
        _offset, _offset + ACTOR_OBSERVATION_DIMS[_name]
    )
    _offset += ACTOR_OBSERVATION_DIMS[_name]
del _name, _offset

# The critic may use privileged quantities the real robot cannot measure. Base
# linear velocity is the important one: an IMU plus leg odometry gives a poor
# estimate of it, but the critic only needs it for value bootstrapping.
CRITIC_EXTRA_TERMS: tuple[str, ...] = ("base_lin_vel",)  # 3, m/s
CRITIC_OBSERVATION_DIM: int = ACTOR_OBSERVATION_DIM + 3

_ACTOR_TERMS_SET = frozenset(ACTOR_OBSERVATION_TERMS)

# Terms available to the actor must be measurable on the HT-Duck: its IMU gives
# angular velocity and gravity direction, the encoders give joint state, and the
# command is supplied by the caller. Base linear velocity is deliberately
# excluded.
ACTOR_ALLOWED_TERMS: frozenset[str] = frozenset(
    {
        "base_ang_vel",
        "projected_gravity",
        "joint_pos",
        "joint_vel",
        "actions",
        "command",
        "head_command",
        "body_command",
    }
)

# Posture-task constants. Every number below is a measurement on this robot (T049).
#
# The load-bearing measured fact: **the only holdable low posture folds the knee
# forward.** A 130-candidate sweep inside the soft limits, driven through the real
# actuator path, found one surviving family of low poses and no foot-supported crouch
# at all: every candidate that kept its feet under the body toppled or saturated the
# 2 Nm actuator limit. The cause is travel, not tuning -- HOME already spends
# calf = -1.20 of the -1.571 knee travel, so there is no room left to fold the other
# way. The pose below is that surviving family's representative: knees folded forward
# onto the hips, feet off the ground.
#
# It plays the same role as the official biped's sit keyframe -- the low state the
# sit-stand command drives to -- and only the numbers differ, because they are measured
# on a different machine.
#
# Verified by holding it through the real actuator path for 6 s: trunk z = 0.0563 m
# (std 2.5e-4), tilt 1.3 deg, peak torque 0.88 Nm against a 3.7 Nm limit, zero drift.
# Note it is *lower* than every lying posture's trunk height (0.060-0.093 m), so height
# alone cannot tell a seat from a fall: tilt is the discriminator (1.3 deg seated,
# 4.3 deg standing, >=79 deg in every measured fall).
LOW_POSTURE_JOINT_POS: dict[str, float] = {
    "r_hip_pitch_joint": 1.55,
    "l_hip_pitch_joint": 1.55,
    "r_calf_joint": 0.40,
    "l_calf_joint": 0.40,
    "r_ankle_joint": 0.35,
    "l_ankle_joint": 0.35,
    "r_hip_roll_joint": 0.0873,
    "l_hip_roll_joint": -0.0873,
}

# Trunk heights above the terrain, all measured with zero command after settling.
STAND_Z: float = 0.1502     # HOME stance; the PD loop settles 3 mm below the 0.1534 m
                            # geometric height (T049)
SIT_Z: float = 0.0563       # seated keyframe above (T049)
PRONE_Z: float = 0.0929     # face-down (T049 PD settle)
SUPINE_Z: float = 0.0929    # face-up (the trunk rests on the same box faces)
SIDE_Z: float = 0.0601      # lying on one side (T049 PD settle)

# Roll of the seated keyframe, in degrees. Zero: the robot sits upright on its hips, so
# the pose is defined by the joints alone and the root stays level.
LOW_POSTURE_ROLL_DEG: float = 0.0

# Gates. **Fallen is decided by tilt, never by height.** A seated robot is lower than a
# fallen one (0.0563 m vs 0.060-0.093 m), so any "low means fallen" gate would classify
# the goal state of the sit task as a failure. Tilt separates the two cleanly: 1.3 deg
# seated, 4.3 deg standing, >=79 deg in every measured fall.
# FALLEN_Z must sit above every lying trunk height (highest measured: 0.0968 m) and
# below the standing one (0.1502 m), because it is the height half of an AND test: too
# low and no real fall would ever satisfy it, too high and a standing robot would.
FALLEN_Z: float = 0.1100
FALLEN_TILT_DEG: float = 60.0  # degrees is the authoritative form: the gates were
                               # measured in whole degrees, so round numbers here keep
                               # the radian values from looking spuriously precise
FALLEN_TILT: float = math.radians(FALLEN_TILT_DEG)
RECOVERED_Z: float = 0.1300  # 0.1502 - 0.020: clear of the highest lying posture (0.0968)
RECOVERED_TILT_DEG: float = 25.0  # stand is 4.3 deg, every fall >= 79 deg
RECOVERED_TILT: float = math.radians(RECOVERED_TILT_DEG)
# The `fallen_too_long` timeout fires on a *sustained* dwell, so its gate is looser than
# the reward-side "is fallen" gate: 70 deg only triggers once the robot is unambiguously
# down and staying down, while 60 deg is where the reward starts treating it as fallen.
DOWN_TILT_DEG: float = 70.0

# Spawn noise for the low posture. Small enough that the pose stays in the posture and
# large enough that the policy cannot memorise one exact configuration.
SIT_JOINT_NOISE_STD: float = 0.08


def validate_contract() -> None:
    """Fail fast if the declared layout is internally inconsistent."""
    missing = _ACTOR_TERMS_SET - ACTOR_ALLOWED_TERMS
    if missing:
        raise ValueError(f"Actor observation uses unavailable terms: {sorted(missing)}")
    if "base_lin_vel" in _ACTOR_TERMS_SET:
        raise ValueError("base_lin_vel is privileged and must stay critic-only.")
    unknown = set(ACTOR_OBSERVATION_TERMS) - set(ACTOR_OBSERVATION_DIMS)
    if unknown:
        raise ValueError(f"Observation terms without a declared size: {sorted(unknown)}")
    if abs(PHYSICS_TIMESTEP * DECIMATION - 0.02) > 1e-12:
        raise ValueError("Control period must stay at 50 Hz.")
    if ACTOR_OBSERVATION_DIM != CRITIC_OBSERVATION_DIM - 3:
        raise ValueError("Critic must add exactly the 3 base linear velocity terms.")
    if set(LOW_POSTURE_JOINT_POS) - set(POLICY_JOINT_NAMES):
        raise ValueError("LOW_POSTURE_JOINT_POS names a joint the policy cannot command.")
    if set(POLICY_JOINT_NAMES) & set(HELD_JOINT_NAMES):
        raise ValueError("A joint is both commanded and held at HOME.")
    if len(set(POLICY_JOINT_NAMES) | set(HELD_JOINT_NAMES)) != 15:
        raise ValueError("Policy + held joints must cover the robot's 15 joints.")
    if not RECOVERED_Z > FALLEN_Z:
        raise ValueError("RECOVERED_Z must be above FALLEN_Z.")


validate_contract()

# 官方任务保留基准的 critic 布局；上方旧常量仍是受保护 VelStand 的契约。
OFFICIAL_CRITIC_TERMS: tuple[str, ...] = (
    "base_lin_vel",
    "base_ang_vel",
    "projected_gravity",
    "joint_pos",
    "joint_vel",
    "actions",
    "command",
    "foot_height",
    "foot_air_time",
    "foot_contact",
    "foot_contact_forces",
    "head_command",
    "body_command",
)
TASK_CRITIC_OBSERVATION_DIMS: dict[str, int] = {
    "HtDuck-Flat-Velocity": 76,
    "HtDuck-Flat-Velocity-Head": 76,
    "HtDuck-Flat-StandUp": 74,
    "HtDuck-Flat-SitStand": 74,
    "HtDuck-Flat-SitStand-Forward": 74,
    "HtDuck-Flat-SitStand-Forward-V4": 74,
    "HtDuck-Flat-VelStand": CRITIC_OBSERVATION_DIM,
    "HtDuck-Flat-SitStand-Unbounded": 74,
    "HtDuck-Flat-VelStand-Unbounded": CRITIC_OBSERVATION_DIM,
}


def critic_observation_terms(task_id: str) -> tuple[str, ...]:
    """返回各任务有序的 critic 项，包括任务对应的足端特权输入。"""
    if task_id in ("HtDuck-Flat-VelStand", "HtDuck-Flat-VelStand-Unbounded"):
        return ACTOR_OBSERVATION_TERMS + CRITIC_EXTRA_TERMS
    if task_id in ("HtDuck-Flat-StandUp", "HtDuck-Flat-SitStand", "HtDuck-Flat-SitStand-Unbounded", "HtDuck-Flat-SitStand-Forward", "HtDuck-Flat-SitStand-Forward-V4"):
        return tuple(name for name in OFFICIAL_CRITIC_TERMS if name != "foot_height")
    if task_id in TASK_CRITIC_OBSERVATION_DIMS:
        return OFFICIAL_CRITIC_TERMS
    raise KeyError(task_id)
