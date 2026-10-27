"""Frozen control and observation contract for the HT-Duck flat-ground task.

This module is the single place that defines what the policy sees and what it
controls. Training, evaluation, export and hardware deployment all read these
values instead of restating them, so the ordering cannot drift between them.

Everything here was fixed by measurement (T022/T038), not by copying upstream:
the 10-actuator split, the 50 Hz control period and the observation layout are
recorded in ``docs/development.md``.

Units and conventions:

- Joint positions: radians, relative to ``HOME_JOINT_POS``.
- Joint velocities: radians per second.
- Base angular velocity: radians per second, in the body frame.
- Projected gravity: unit vector, body frame, pointing along gravity.
- Velocity commands: metres per second (x, y) and radians per second (yaw).
- Actions: dimensionless, scaled by ``ACTION_SCALE`` onto joint targets.
"""

from __future__ import annotations

# Control period. dt * decimation must equal 0.02 s = 50 Hz.
PHYSICS_TIMESTEP: float = 0.002
DECIMATION: int = 10
CONTROL_HZ: float = 1.0 / (PHYSICS_TIMESTEP * DECIMATION)

EPISODE_LENGTH_S: float = 20.0

# Only the leg actuators are driven by the policy. The neck, head and mouth are
# held at HOME: they are not needed for balancing, and two of them are servos
# with much lower bandwidth than the leg motors.
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
)

# Held at HOME by the action term; never part of the action vector.
HELD_JOINT_NAMES: tuple[str, ...] = (
    "neck_pitch_joint",
    "head_pitch_joint",
    "head_yaw_joint",
    "head_roll_joint",
    "mouth_joint",
)

ACTION_DIM: int = len(POLICY_JOINT_NAMES)

# Raw actions are mapped to joint targets as
#     target = HOME + ACTION_SCALE * action
# 0.25 rad keeps a full-scale action inside the leg range without saturating the
# position limits, and leaves the policy headroom for recovery.
ACTION_SCALE: float = 0.25

# Observation layout. The order of this tuple is the observation vector order and
# must not be changed without retraining: the policy's first layer indexes it.
ACTOR_OBSERVATION_TERMS: tuple[str, ...] = (
    "base_ang_vel",       # 3  body-frame angular velocity, rad/s
    "projected_gravity",  # 3  unit gravity vector, body frame
    "command",            # 3  commanded (vx, vy, wz)
    "joint_pos",          # 10 position relative to HOME, rad
    "joint_vel",          # 10 joint velocity, rad/s
    "actions",            # 10 previous action
)

ACTOR_OBSERVATION_DIMS: dict[str, int] = {
    "base_ang_vel": 3,
    "projected_gravity": 3,
    "command": 3,
    "joint_pos": ACTION_DIM,
    "joint_vel": ACTION_DIM,
    "actions": ACTION_DIM,
}

ACTOR_OBSERVATION_DIM: int = sum(
    ACTOR_OBSERVATION_DIMS[name] for name in ACTOR_OBSERVATION_TERMS
)

# The critic may use privileged quantities the real robot cannot measure. Base
# linear velocity is the important one: an IMU plus leg odometry gives a poor
# estimate of it, but the critic only needs it for value bootstrapping.
CRITIC_EXTRA_TERMS: tuple[str, ...] = ("base_lin_vel",)  # 3, m/s
CRITIC_OBSERVATION_DIM: int = ACTOR_OBSERVATION_DIM + 3

_ACTOR_TERMS_SET = frozenset(ACTOR_OBSERVATION_TERMS)

# Terms available to the actor must be measurable on the HT-Duck: its IMU gives
# angular velocity and gravity direction, the leg encoders give joint state, and
# the command is supplied by the caller. Base linear velocity is deliberately
# excluded.
ACTOR_ALLOWED_TERMS: frozenset[str] = frozenset(
    {
        "base_ang_vel",
        "projected_gravity",
        "command",
        "joint_pos",
        "joint_vel",
        "actions",
    }
)


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


validate_contract()
