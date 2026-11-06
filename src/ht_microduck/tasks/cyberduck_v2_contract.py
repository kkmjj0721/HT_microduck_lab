# Copyright (c) 2026-2027 zh
"""
内容：
    固定 CyberDuck V2 平地任务的混合动作、观测顺序、单位和控制时序。

位置关节以相对 HOME 的 rad 表示，两踝只接收 rad/s 速度目标；机身速度与命令使用
机体系，线速度单位 m/s，角速度单位 rad/s。动作无量纲，张量为环境设备上的 float32。
本契约与旧 HT 任务的全位置控制及检查点不兼容。
"""

from ht_microduck.robot.cyberduck_v2_constants import (
    ACTUATED_JOINT_NAMES,
    COLLISION_GEOM_NAMES,
    POSITION_JOINT_NAMES,
    VELOCITY_JOINT_NAMES,
)

# ---------- 时序与动作 ----------
PHYSICS_TIMESTEP: float = 0.002
DECIMATION: int = 10
CONTROL_HZ: float = 1.0 / (PHYSICS_TIMESTEP * DECIMATION)
EPISODE_LENGTH_S: float = 20.0

HELD_JOINT_NAMES: tuple[str, ...] = ("mouth_joint",)
POLICY_POSITION_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in POSITION_JOINT_NAMES if name not in HELD_JOINT_NAMES
)
POLICY_VELOCITY_JOINT_NAMES: tuple[str, ...] = VELOCITY_JOINT_NAMES
POLICY_JOINT_NAMES: tuple[str, ...] = (
    POLICY_POSITION_JOINT_NAMES + POLICY_VELOCITY_JOINT_NAMES
)
ACTION_TERMS: tuple[str, ...] = ("joint_pos", "joint_vel")
ACTION_DIM: int = len(POLICY_JOINT_NAMES)

# 这是首版仿真探索尺度与目标范围，尚未进行实机或策略效果标定。
POSITION_ACTION_SCALE: float = 0.25
VELOCITY_ACTION_SCALE: float = 4.0
VELOCITY_TARGET_LIMIT: float = 8.0

# ---------- 观测与接触 ----------
ACTOR_OBSERVATION_TERMS: tuple[str, ...] = (
    "base_ang_vel",
    "projected_gravity",
    "joint_pos",
    "joint_vel",
    "actions",
    "command",
)
ACTOR_OBSERVATION_DIMS: dict[str, int] = {
    "base_ang_vel": 3,
    "projected_gravity": 3,
    "joint_pos": len(POLICY_POSITION_JOINT_NAMES),
    "joint_vel": len(POLICY_JOINT_NAMES),
    "actions": ACTION_DIM,
    "command": 3,
}
ACTOR_OBSERVATION_DIM: int = sum(ACTOR_OBSERVATION_DIMS.values())
CRITIC_OBSERVATION_TERMS: tuple[str, ...] = ACTOR_OBSERVATION_TERMS + (
    "base_lin_vel",
    "wheel_contact",
)
CRITIC_OBSERVATION_DIMS: dict[str, int] = {
    **ACTOR_OBSERVATION_DIMS,
    "base_lin_vel": 3,
    "wheel_contact": 4,
}
CRITIC_OBSERVATION_DIM: int = sum(CRITIC_OBSERVATION_DIMS.values())

WHEEL_GEOM_NAMES: tuple[str, ...] = (
    "r_roller_back_collision",
    "r_roller_front_collision",
    "l_roller_back_collision",
    "l_roller_front_collision",
)
WHEEL_CONTACT_SENSOR_NAME: str = "wheel_ground_contact"
NONWHEEL_CONTACT_SENSOR_NAME: str = "nonwheel_ground_contact"


def validate_contract() -> None:
    """核对策略子集、两类目标和观测布局，防止关节或维度意外漂移。"""
    if (len(POLICY_POSITION_JOINT_NAMES), len(POLICY_VELOCITY_JOINT_NAMES)) != (12, 2):
        raise ValueError("CyberDuck V2 requires 12 position and 2 velocity actions")
    if len(set(POLICY_JOINT_NAMES)) != ACTION_DIM:
        raise ValueError("CyberDuck V2 policy joints must be unique")
    if set(POLICY_JOINT_NAMES) & set(HELD_JOINT_NAMES):
        raise ValueError("CyberDuck V2 policy and held joints must be disjoint")
    if set(POLICY_JOINT_NAMES + HELD_JOINT_NAMES) != set(ACTUATED_JOINT_NAMES):
        raise ValueError("CyberDuck V2 policy and held joints must cover its actuators")
    if not set(WHEEL_GEOM_NAMES) <= set(COLLISION_GEOM_NAMES):
        raise ValueError("CyberDuck V2 wheel contact geoms must exist in the robot")
    if (ACTOR_OBSERVATION_DIM, CRITIC_OBSERVATION_DIM, ACTION_DIM) != (49, 56, 14):
        raise ValueError("CyberDuck V2 observation/action dimensions must remain 49/56/14")
    if CONTROL_HZ != 50.0:
        raise ValueError("CyberDuck V2 policy frequency must remain 50 Hz")


validate_contract()
