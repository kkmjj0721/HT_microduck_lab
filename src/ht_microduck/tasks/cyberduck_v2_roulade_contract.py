# Copyright (c) 2026-2027 zh
"""
内容：
    固定 CyberDuck V2 前滚翻任务的混合动作、单帧观测和行为验收接口。

动作依次为十二路位置和两路踝速度，嘴保持 HOME。位置状态不含累计踝角及从动轮角，
速度状态含十二路位置关节与两踝。角速度和重力在机体系，位置为相对 HOME 的 rad，
速度为 rad/s；张量为环境设备上的 float32，50 Hz、无观测历史。
本接口与轮行任务不兼容，必须使用独立检查点。
Recovery 适配任务追加两维翻转进度和头部记录，位置动作改为各关节行程内的 HOME 偏置 tanh 潜变量，
历史位置动作保留网络原始输出；零动作对应 HOME 编码器目标，物理目标再扣除编码器偏置。
原任务与 Recovery 的动作语义和训练配方不同，检查点不能互用。
"""

import math

from ht_microduck.robot.cyberduck_v2_constants import (
    POSITION_JOINT_NAMES,
    STAND_JOINT_POS,
    VELOCITY_JOINT_NAMES,
)

TASK_ID = "CyberDuckV2-Flat-Roulade"
CONTRACT_VERSION = "cyberduck_roulade_p12_v2_obs46_v1"
RECOVERY_TASK_ID = "CyberDuckV2-Flat-Roulade-Recovery"
RECOVERY_CONTRACT_VERSION = "cyberduck_roulade_recovery_obs48_v4"
POSITION_JOINTS = tuple(name for name in POSITION_JOINT_NAMES if name != "mouth_joint")
VELOCITY_JOINTS = VELOCITY_JOINT_NAMES
POLICY_JOINTS = POSITION_JOINTS + VELOCITY_JOINTS
LEG_POSITION_JOINTS = POSITION_JOINTS[:8]
HELD_JOINTS = ("mouth_joint",)
ACTION_DIM = len(POLICY_JOINTS)
POSITION_SCALE = 1.0
POSITION_ACTION_LIMIT = math.pi
VELOCITY_SCALE = 10.0
VELOCITY_ACTION_LIMIT = 2.0
VELOCITY_TARGET_LIMIT = 20.0
PHYSICS_TIMESTEP = 0.002
DECIMATION = 10
EPISODE_LENGTH_S = 5.0
ACTOR_TERMS = ("base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "actions")
CRITIC_TERMS = ACTOR_TERMS + ("base_lin_vel", "wheel_contact")
ACTOR_DIM = 46
CRITIC_DIM = 53
RECOVERY_ACTOR_TERMS = ACTOR_TERMS + ("roulade_phase",)
RECOVERY_CRITIC_TERMS = CRITIC_TERMS + ("roulade_phase",)
RECOVERY_ACTOR_DIM = 48
RECOVERY_CRITIC_DIM = 55
# 前滚翻的参考站立姿态与高度。
#
# 2026-11-13 起不再用 HOME 当落地判据：HOME 的 hip_yaw/hip_roll/head_roll 全为 0，
# 策略五轮实验都无法把站姿拉回它，零动作也稳不住；改用策略实测的稳定站姿
# （见 cyberduck_v2_constants.STAND_JOINT_POS，零动作 4 秒验证通过）。
# 补全 12 个位置关节：未在 STAND_JOINT_POS 中列出的关节取 0（参考站姿的其余轴为中立）。
STAND_POSE: dict[str, float] = {
    name: float(STAND_JOINT_POS.get(name, 0.0)) for name in POSITION_JOINTS
}
# 2026-11-18 换用新模型后重测：32 环境、4 秒零动作、纯站立初态，
# 末秒根高均值 0.241639 m、std 0.000929、倾角 2.87°、双侧轮支撑 1.000、自接触 0.000，
# 整机 COM 高 0.197381 m。旧值 0.2414 恰好接近，但它是旧几何的受载结果，不能当作同一模型沿用。
SUPPORT_HEIGHT = 0.2416
HEAD_BODY_NAME = "head_roll_link"
# HOME 静态正运动学：世界竖直表达在头部局部坐标中，非实机标定。
# 2026-11-18 换用新模型后重算；新几何下 head_roll_link 本体系与旧版不同，数值必须更新。
HEAD_TOP_AXIS = (-0.0449848140376603, 0.010988642771902007, 0.9989272327031775)
WHEEL_GEOMS = (
    "r_roller_back_collision", "r_roller_front_collision",
    "l_roller_back_collision", "l_roller_front_collision",
)
SUPPORT_SENSOR = "robot_ground_contact"
HEAD_SENSOR = "head_ground_contact"
WHEEL_SENSOR = "wheel_ground_contact"
COMPLETION_ANGLE = math.radians(330.0)
SUCCESS_HOLD_S = 0.5
SUCCESS_TILT = math.radians(20.0)
SUCCESS_HEIGHT_ERROR = 0.025
# 站姿验收阈值：12 个位置关节相对 C.STAND_POSE 的 RMS 误差。
# 0.12 rad 约为当前最佳策略（腿 RMS 0.233 相对 HOME）在参考姿态下的实测值
# 量级再留余量；低于它会逼出更接近参考姿态的站姿。
SUCCESS_POSE_RMS = 0.12
SUCCESS_LINEAR_SPEED = 0.2
SUCCESS_ANGULAR_SPEED = 0.8
