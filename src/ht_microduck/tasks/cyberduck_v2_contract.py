# Copyright (c) 2026-2027 zh
"""
内容：
    固定 CyberDuck V2 平地任务的混合动作、观测顺序、单位和控制时序。

位置关节以相对 HOME 的 rad 表示，两踝只接收 rad/s 速度目标；机身速度与命令使用
机体系，线速度单位 m/s，角速度单位 rad/s。动作无量纲，张量为环境设备上的 float32。
actor 按项拼接五帧历史，项内从旧到新；critic 仅使用当前帧。重置以重置后首帧回填历史。
本契约与旧 HT 全位置任务、CyberDuck 首版 49/56/14 检查点及其归一化统计不兼容。
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

HELD_JOINT_NAMES: tuple[str, ...] = (
    "neck_pitch_joint", "head_pitch_joint", "head_yaw_joint", "head_roll_joint", "mouth_joint",
)
POLICY_POSITION_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in POSITION_JOINT_NAMES if name not in HELD_JOINT_NAMES
)
POLICY_VELOCITY_JOINT_NAMES: tuple[str, ...] = VELOCITY_JOINT_NAMES
POLICY_JOINT_NAMES: tuple[str, ...] = (
    POLICY_POSITION_JOINT_NAMES + POLICY_VELOCITY_JOINT_NAMES
)
ACTION_TERMS: tuple[str, ...] = ("joint_pos", "joint_vel")
ACTION_DIM: int = len(POLICY_JOINT_NAMES)

# 状态保留头颈实际响应；累计踝角和从动轮角不进入策略观测。
OBSERVATION_POSITION_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in POSITION_JOINT_NAMES if name != "mouth_joint"
)
OBSERVATION_VELOCITY_JOINT_NAMES: tuple[str, ...] = (
    OBSERVATION_POSITION_JOINT_NAMES + VELOCITY_JOINT_NAMES
)

# 贴地固定 HOME 探针支持本轮保守任务范围；不代表实机标定或策略最优参数。
POSITION_ACTION_SCALE: float = 0.25
VELOCITY_ACTION_SCALE: float = 2.0
VELOCITY_TARGET_LIMIT: float = 4.0
COMMAND_LINEAR_LIMIT: float = 0.1
COMMAND_YAW_LIMIT: float = 0.2
COMMAND_MAX_ACCELERATION: tuple[float, float, float] = (0.05, 0.05, 0.2)

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
    "joint_pos": len(OBSERVATION_POSITION_JOINT_NAMES),
    "joint_vel": len(OBSERVATION_VELOCITY_JOINT_NAMES),
    "actions": ACTION_DIM,
    "command": 3,
}
# mjlab 按观测项拼接；每项内部依次展开最旧至最新的五帧，并非五个完整帧顺次拼接。
ACTOR_FRAME_DIM: int = sum(ACTOR_OBSERVATION_DIMS.values())
ACTOR_HISTORY_LENGTH: int = 5
ACTOR_OBSERVATION_DIM: int = ACTOR_FRAME_DIM * ACTOR_HISTORY_LENGTH
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
WHEEL_ROLLING_SENSOR_NAME: str = "wheel_rolling_contact"
BODY_CONTACT_SENSOR_NAME: str = "body_ground_contact"
SELF_CONTACT_SENSOR_NAME: str = "self_contact"

# 本地受载 HOME 仿真参考，非源初始根高或实机测量值。
SUPPORT_HEIGHT: float = 0.238
HEIGHT_TOLERANCE: float = 0.015
TILT_TOLERANCE: float = 0.13962634015954636  # 8 度，单位 rad。


def validate_contract() -> None:
    """核对策略子集、两类目标和观测布局，防止关节或维度意外漂移。"""
    if (len(POLICY_POSITION_JOINT_NAMES), len(POLICY_VELOCITY_JOINT_NAMES)) != (8, 2):
        raise ValueError("CyberDuck V2 requires 8 position and 2 velocity actions")
    if len(set(POLICY_JOINT_NAMES)) != ACTION_DIM:
        raise ValueError("CyberDuck V2 policy joints must be unique")
    if set(POLICY_JOINT_NAMES) & set(HELD_JOINT_NAMES):
        raise ValueError("CyberDuck V2 policy and held joints must be disjoint")
    if set(POLICY_JOINT_NAMES + HELD_JOINT_NAMES) != set(ACTUATED_JOINT_NAMES):
        raise ValueError("CyberDuck V2 policy and held joints must cover its actuators")
    if not set(WHEEL_GEOM_NAMES) <= set(COLLISION_GEOM_NAMES):
        raise ValueError("CyberDuck V2 wheel contact geoms must exist in the robot")
    if (ACTOR_FRAME_DIM, ACTOR_OBSERVATION_DIM, CRITIC_OBSERVATION_DIM, ACTION_DIM) != (45, 225, 52, 10):
        raise ValueError("CyberDuck V2 frame/actor/critic/action dimensions must remain 45/225/52/10")
    if CONTROL_HZ != 50.0:
        raise ValueError("CyberDuck V2 policy frequency must remain 50 Hz")


validate_contract()
