# Copyright (c) 2026-2027 zh
"""
内容：
    固定 CyberDuck V2 摔倒起立任务的混合动作、单帧观测、初态与成功判据接口。

动作与前滚翻一致：十二路位置加两路踝速度，嘴保持 HOME，动作维度 14。
actor 为单帧 46 维（角速度、重力、12 路位置、14 路速度、14 路动作），critic 追加
base_lin_vel 与四轮接地共 53 维。观测为环境设备上的 float32，50 Hz、无历史。
任务从俯卧、仰卧、侧卧、坐姿、站姿五种倒地／低姿态出发，起立到参考站姿；
成功判据在任意初态下都成立，不要求“站姿起始”，因此与其他任务检查点不兼容。
"""

import math

from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    POSITION_JOINT_NAMES,
    STAND_JOINT_POS,
    VELOCITY_JOINT_NAMES,
)

# ---------- 任务标识与观测、动作 ----------
TASK_ID = "CyberDuckV2-Flat-StandUp"
CONTRACT_VERSION = "cyberduck_standup_obs46_v1"
POSITION_JOINTS = tuple(name for name in POSITION_JOINT_NAMES if name != "mouth_joint")
VELOCITY_JOINTS = VELOCITY_JOINT_NAMES
POLICY_JOINTS = POSITION_JOINTS + VELOCITY_JOINTS
HELD_JOINTS = ("mouth_joint",)
ACTION_DIM = len(POLICY_JOINTS)
POSITION_SCALE = 1.0
POSITION_ACTION_LIMIT = math.pi
VELOCITY_SCALE = 10.0
VELOCITY_ACTION_LIMIT = 2.0
VELOCITY_TARGET_LIMIT = 20.0
PHYSICS_TIMESTEP = 0.002
DECIMATION = 10
EPISODE_LENGTH_S = 6.0
# 观测沿用前滚翻的 46 / 53 维单帧布局，便于复用已有网络与镜像损失实现。
ACTOR_TERMS = ("base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "actions")
CRITIC_TERMS = ACTOR_TERMS + ("base_lin_vel", "wheel_contact")
ACTOR_DIM = 46
CRITIC_DIM = 53
OBSERVATION_POSITION_JOINT_NAMES = POSITION_JOINTS
OBSERVATION_VELOCITY_JOINT_NAMES = POSITION_JOINTS + VELOCITY_JOINTS

# ---------- 参考站姿与物理锚点 ----------
# 2026-11-18 新模型实测（32 环境、4 秒零动作、纯站立初态、末秒均值）：
# 整机质量 3.42329628 kg，头部五连杆 0.8665786 kg（25.3%）；
# 受载根高 0.241639 m、std 0.000929、倾角 2.87°、双侧轮支撑 1.000、自接触 0.000。
# 整机受载 COM 高 0.197381 m；旧模型（3.703212 kg / 头部 31.2%）的 0.223 m 不适用。
SUPPORT_HEIGHT = 0.2416
COM_HEIGHT = 0.1974
# 12 个位置关节的参考站姿；未在 STAND_JOINT_POS 中列出的关节取 0。
STAND_POSE: dict[str, float] = {
    name: float(STAND_JOINT_POS.get(name, 0.0)) for name in POSITION_JOINTS
}
HEAD_BODY_NAME = "head_roll_link"
# HOME 静态正运动学：世界竖直方向在 head_roll_link 局部坐标中的表达，非实机标定。
HEAD_TOP_AXIS = (-0.0449848140376603, 0.010988642771902007, 0.9989272327031775)
# 滚轮碰撞几何由机器人常量派生，独立于前滚翻契约；顺序为右后、右前、左后、左前。
WHEEL_GEOMS = tuple(name for name in COLLISION_GEOM_NAMES if "roller" in name)
WHEEL_COUNT = len(WHEEL_GEOMS)
WHEEL_SENSOR = "wheel_ground_contact"
SELF_SENSOR = "standup_self_contact"

# ---------- 初态课程 ----------
# 五种初态的根朝向（roll, pitch, yaw，单位 rad）；侧卧左右随机取符号。
# 触地由初态事件按缓存碰撞顶点求最低点后贴地 1 mm，这里只声明名义姿态。
SPAWN_POSTURES: tuple[str, ...] = ("standing", "sitting", "face_down", "face_up", "side")
SPAWN_ORIENTATION: dict[str, tuple[float, float, float]] = {
    "standing": (0.0, 0.0, 0.0),
    "sitting": (0.0, 0.0, 0.0),
    "face_down": (0.0, math.pi / 2, 0.0),
    "face_up": (0.0, -math.pi / 2, 0.0),
    "side": (math.pi / 2, 0.0, 0.0),
}
# 坐姿候选：双腿对称折叠，髋俯仰 1.5 / 膝 1.5 / 踝 0.3、髋横滚 ±0.0873 rad。
# 2026-11-18 静态几何探针：根高 0.1052 m，最低 geom 为 l/r_hip_pitch_collision，
# 无自接触；该姿态只作为初态锚点，不要求策略保持在坐姿。
SITTING_JOINT_POS: dict[str, float] = {
    "r_hip_pitch_joint": 1.5,
    "l_hip_pitch_joint": 1.5,
    "r_calf_joint": 1.5,
    "l_calf_joint": 1.5,
    "r_ankle_joint": 0.3,
    "l_ankle_joint": 0.3,
    "r_hip_roll_joint": 0.0873,
    "l_hip_roll_joint": -0.0873,
}
# 名义初态的静态几何根高（1 mm 离地放置、STAND 关节角、无额外噪声）。
# 2026-11-18 探针结果，仅用于测试核对量级，不作为奖励或控制目标。
SPAWN_GEOMETRY_HEIGHT: dict[str, float] = {
    "standing": 0.2454,
    "sitting": 0.1052,
    "face_down": 0.0919,
    "face_up": 0.0893,
    "side": 0.1078,
}
# 初态姿态噪声：倒地类额外俯仰／横滚扰动，站姿与坐姿只加小倾角。
SPAWN_ORIENTATION_NOISE: dict[str, float] = {
    "standing": math.radians(5.0),
    "sitting": math.radians(8.0),
    "face_down": math.radians(10.0),
    "face_up": math.radians(10.0),
    "side": math.radians(10.0),
}
SPAWN_JOINT_NOISE_STD = 0.08
GROUND_CLEARANCE = 0.001

# ---------- 成功判据 ----------
# 参考值取自新模型受载站姿（SUPPORT_HEIGHT / COM_HEIGHT），阈值与前滚翻一致。
SUCCESS_HOLD_S = 0.5
SUCCESS_TILT = math.radians(20.0)
SUCCESS_HEIGHT_ERROR = 0.025
SUCCESS_POSE_RMS = 0.12
SUCCESS_LINEAR_SPEED = 0.2
SUCCESS_ANGULAR_SPEED = 0.8


def validate_contract() -> None:
    """核对维度、关节顺序、滚轮几何与初态声明，防止接口漂移。"""
    if tuple(STAND_POSE) != POSITION_JOINTS:
        raise ValueError("StandUp STAND_POSE must follow the position joint order")
    if len(set(POLICY_JOINTS)) != ACTION_DIM or ACTION_DIM != 14:
        raise ValueError("StandUp requires 14 policy actions")
    if WHEEL_COUNT != 4:
        raise ValueError(f"StandUp requires four wheel geoms, got {WHEEL_GEOMS}")
    if set(SPAWN_POSTURES) != set(SPAWN_ORIENTATION):
        raise ValueError("StandUp spawn postures and orientations must match")
    if set(SPAWN_POSTURES) != set(SPAWN_GEOMETRY_HEIGHT):
        raise ValueError("StandUp spawn postures and geometry anchors must match")
    if set(SITTING_JOINT_POS) - set(POLICY_JOINTS):
        raise ValueError("StandUp sitting pose names a non-policy joint")
    if (ACTOR_DIM, CRITIC_DIM) != (46, 53):
        raise ValueError("StandUp actor/critic dimensions must remain 46/53")


validate_contract()
