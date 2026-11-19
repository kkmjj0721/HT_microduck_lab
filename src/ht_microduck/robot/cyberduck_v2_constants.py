# Copyright (c) 2026-2027 zh
"""
内容：
    CyberDuck V2 的源模型、关节映射、混合驱动与 mjlab 实体配置。

用法：
    uv run --no-sync python -B -m ht_microduck.robot.cyberduck_v2_constants
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import mujoco
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

from ht_microduck.actuator import HTDW3532ActuatorCfg

# ---------- 资源与关节 ----------
MJCF_PATH: Path = Path(__file__).resolve().parent / "cyberduck_v2" / "CyberDuck_V2.xml"

# 单轴关节按源 XML 声明顺序排列，包含四个从动滚轮关节。
JOINT_NAMES: tuple[str, ...] = (
    "r_hip_yaw_joint",
    "r_hip_roll_joint",
    "r_hip_pitch_joint",
    "r_calf_joint",
    "r_ankle_joint",
    "r_roller_back_joint",
    "r_roller_front_joint",
    "l_hip_yaw_joint",
    "l_hip_roll_joint",
    "l_hip_pitch_joint",
    "l_calf_joint",
    "l_ankle_joint",
    "l_roller_back_joint",
    "l_roller_front_joint",
    "neck_pitch_joint",
    "head_pitch_joint",
    "head_yaw_joint",
    "head_roll_joint",
    "mouth_joint",
)

# 源 URDF mimic 与 MJCF equality 一致；MuJoCo 以软等式约束实现跟随。
MIMIC_JOINT_MAP: dict[str, str] = {
    "r_roller_back_joint": "r_ankle_joint",
    "r_roller_front_joint": "r_ankle_joint",
    "l_roller_back_joint": "l_ankle_joint",
    "l_roller_front_joint": "l_ankle_joint",
}
MIMIC_JOINT_NAMES: tuple[str, ...] = tuple(MIMIC_JOINT_MAP)
MIMIC_MULTIPLIER = 1.210526
INDEPENDENT_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in JOINT_NAMES if name not in MIMIC_JOINT_MAP
)

# 原始 XML 的两个示例力矩电机仅由 get_spec() 保留，整机装配时移除。
SOURCE_ACTUATED_JOINT_NAMES: tuple[str, ...] = ("r_ankle_joint", "l_ankle_joint")
SOURCE_ACTUATOR_NAMES: tuple[str, ...] = ("r_ankle_motor", "l_ankle_motor")

# 全电机驱动：原 head_yaw/head_roll/mouth 三个舵机已改为无刷电机（2026-11-16）。
# 两踝仍控制速度、其余控制位置。分组名保留 SERVO_* 以免破坏既有导入，
# 但它们现在指向无刷电机，不再使用 HD1910 执行器。
BRUSHLESS_JOINT_NAMES: tuple[str, ...] = (
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
    "mouth_joint",
)
VELOCITY_JOINT_NAMES: tuple[str, ...] = ("r_ankle_joint", "l_ankle_joint")
BRUSHLESS_POSITION_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in BRUSHLESS_JOINT_NAMES if name not in VELOCITY_JOINT_NAMES
)
# 原舵机控制的 3 个关节。名字保留以兼容既有导入与测试，
# 但它们现在由 BRUSHLESS_ACTUATOR_CFG 驱动（见 SERVO_ACTUATOR_CFG 定义处）。
SERVO_JOINT_NAMES: tuple[str, ...] = (
    "head_yaw_joint",
    "head_roll_joint",
    "mouth_joint",
)
# 原舵机三名已并入 BRUSHLESS_POSITION_JOINT_NAMES，这里去重后保持 13 路位置控制。
POSITION_JOINT_NAMES: tuple[str, ...] = BRUSHLESS_POSITION_JOINT_NAMES

# 编译后的执行器顺序；全电机驱动后 15 个关节都由无刷配置驱动，不再追加舵机。
ACTUATED_JOINT_NAMES: tuple[str, ...] = BRUSHLESS_JOINT_NAMES
ACTUATOR_NAMES: tuple[str, ...] = ACTUATED_JOINT_NAMES
# 2026-11-16 全电机驱动：原 HD1910 舵机三名（head_yaw/head_roll/mouth）
# 统一改为 HTDW-3532-02-DNE，不再有 FEETECH HD1910。
JOINT_TO_MOTOR_MODEL: dict[str, str] = dict.fromkeys(
    BRUSHLESS_JOINT_NAMES, "HTDW-3532-02-DNE"
)

# ---------- 碰撞与源模型装配 ----------
_COLLISION_NAMES_BY_BODY: dict[str, tuple[str, ...]] = {
    "base_link": ("base_front_collision", "base_rear_collision"),
    "r_hip_roll_link": ("r_hip_roll_collision",),
    "r_hip_pitch_link": ("r_hip_pitch_collision",),
    "r_roller_back_link": ("r_roller_back_collision",),
    "r_roller_front_link": ("r_roller_front_collision",),
    "l_hip_roll_link": ("l_hip_roll_collision",),
    "l_hip_pitch_link": ("l_hip_pitch_collision",),
    "l_roller_back_link": ("l_roller_back_collision",),
    "l_roller_front_link": ("l_roller_front_collision",),
    "head_roll_link": ("head_collision",),
    "mouth_link": ("mouth_collision",),
}
COLLISION_GEOM_NAMES: tuple[str, ...] = tuple(
    name for names in _COLLISION_NAMES_BY_BODY.values() for name in names
)


def get_spec() -> mujoco.MjSpec:
    """读取机器人本体；场景地面与灯光由 mjlab Scene 提供。"""
    return mujoco.MjSpec.from_file(str(MJCF_PATH))


def get_robot_spec() -> mujoco.MjSpec:
    """移除源示例电机并命名碰撞体，保留本体与四个滚轮约束。"""
    spec = get_spec()
    for actuator_name in SOURCE_ACTUATOR_NAMES:
        spec.delete(spec.actuator(actuator_name))
    for body_name, names in _COLLISION_NAMES_BY_BODY.items():
        geoms = [
            geom
            for geom in spec.body(body_name).geoms
            if geom.contype or geom.conaffinity
        ]
        if len(geoms) != len(names):
            raise ValueError(
                f"{body_name}: expected {len(names)} collision geoms, "
                f"found {len(geoms)}; update the CyberDuck V2 collision mapping"
            )
        for geom, name in zip(geoms, names, strict=True):
            geom.name = name
    return spec


# ---------- 初态与混合驱动 ----------
# 保留源 XML 的零位供资源核对，实体默认使用下方用户选定的 HOME 初态。
SOURCE_JOINT_POS: dict[str, float] = dict.fromkeys(JOINT_NAMES, 0.0)
SOURCE_FRAME = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.252),
    rot=(1.0, 0.0, 0.0, 0.0),
    lin_vel=(0.0, 0.0, 0.0),
    ang_vel=(0.0, 0.0, 0.0),
    joint_pos=dict(SOURCE_JOINT_POS),
    joint_vel=dict.fromkeys(JOINT_NAMES, 0.0),
)

# 用户选定的对称弯腿与头颈后收姿态，单位 rad；其余位置和全部速度初值为零。
# 这是位置目标与重置初值，受载实际角度存在偏差；根高度与躯干初始朝向沿用源配置。
# 头部 pitch/roll 含当前增益下的静止受载补偿，使头部在世界坐标中接近水平。
HOME_JOINT_POS: dict[str, float] = {
    **SOURCE_JOINT_POS,
    "r_hip_pitch_joint": 0.490,
    "l_hip_pitch_joint": 0.490,
    "r_calf_joint": -0.444,
    "l_calf_joint": -0.444,
    "neck_pitch_joint": -0.360,
    "head_pitch_joint": 0.405,
    "head_roll_joint": 0.011,
}
HOME_FRAME = replace(
    SOURCE_FRAME,
    joint_pos=dict(HOME_JOINT_POS),
    joint_vel=dict.fromkeys(JOINT_NAMES, 0.0),
)

# 前滚翻任务的参考站立姿态（rad），与 HOME 分开维护。
#
# 2026-11-18 换用新模型（整机 3.703212→3.42329628 kg、头部五连杆降 25%、全部网格更新）
# 后复测：同一组 STAND_JOINT_POS 仍满足根高 0.241639 m、倾角 2.87°、双侧轮支撑 1.000、
# 自接触 0.000，因此姿态数值本身不需要改，只需更新 SUPPORT_HEIGHT（契约内）。
# 参考站姿的硬行程检查在下方按新限位复核：neck_pitch 上限 2.920→1.877、
# head_roll ±0.436→±0.208，当前参考值 -0.360 / 0.0 仍在内。
#
# 2026-11-13 用零动作保持（16 环境、4 秒、seed7）复测后更正了此前的一个错误结论：
# 之前的旧版本曾把“HOME 稳不住”当成改用策略站姿的理由，实测并非如此——
# 以 HOME 为默认姿态零动作站立：根高 0.2414 m、倾角 1.97°、双侧轮支撑 1.0、
# 自接触 0.0、无跌倒，与策略站姿完全同级。策略之所以漂到 hip_yaw ±0.43 的宽支撑姿态，
# 是因为姿态奖励太弱（pose 项只覆盖腿关节、取均值、std 0.4），不是 HOME 不可站。
#
# 因此这里回到**左右对称、yaw/roll 为 0** 的参考站姿：与 HOME 同族，但显式把
# head_roll 归零（HOME 的 0.011 是旧增益下的补偿量，不是姿态需求）。
# 零动作复测（旧模型）：根高 0.2414、倾角 1.97°、支撑 1.0、自接触 0.0、无跌倒。
STAND_JOINT_POS: dict[str, float] = {
    "r_hip_pitch_joint": 0.490,
    "l_hip_pitch_joint": 0.490,
    "r_calf_joint": -0.444,
    "l_calf_joint": -0.444,
    "neck_pitch_joint": -0.360,
    "head_pitch_joint": 0.405,
    "head_roll_joint": 0.0,
}
_stand_frame = dict(SOURCE_JOINT_POS, **STAND_JOINT_POS)
# 根高取新模型受载站姿实测值（32 环境 × 4 秒末秒均值 0.241639 m），不是源 XML 的 0.252。
STAND_FRAME = replace(
    SOURCE_FRAME,
    pos=(0.0, 0.0, 0.2416),
    joint_pos=_stand_frame,
    joint_vel=dict.fromkeys(JOINT_NAMES, 0.0),
)
_STAND_JOINT_LIMITS = {
    # 参考姿态必须落在硬关节行程内，否则动作映射的 HOME 逆映射不成立。
    # 2026-11-18 换用新模型后按新 XML 更新：neck_pitch 上限 1.877、head_roll ±0.208、
    # head_pitch 上限 1.571（旧版 2.920 / ±0.436 / 1.570）。
    "r_hip_pitch_joint": (-1.571, 1.571),
    "r_calf_joint": (-1.571, 1.571),
    "neck_pitch_joint": (-1.571, 1.877),
    "head_pitch_joint": (-1.571, 1.571),
    "head_roll_joint": (-0.208, 0.208),
}
for _name, (_lo, _hi) in _STAND_JOINT_LIMITS.items():
    _value = STAND_JOINT_POS[_name]
    if not _lo < _value < _hi:
        raise ValueError(f"STAND_JOINT_POS[{_name!r}]={_value} is outside ({_lo}, {_hi})")
del _name, _lo, _hi, _value, _stand_frame

# 13 个关节接位置目标（rad），两踝接速度目标（rad/s），滚轮没有独立输入。
# 独立动态运行须先按执行器约定展开逐环境模型字段，再写目标或 reset。
# 参数沿用项目现有 HTDW-3532 的仿真配置，不代表 CyberDuck 实机标定。
# 该值是原机器人用户提供的输出轴反射惯量；本次按同一电机模型复用。
BRUSHLESS_ARMATURE = 0.0069753532276
BRUSHLESS_ACTUATOR_CFG = HTDW3532ActuatorCfg(
    target_names_expr=BRUSHLESS_POSITION_JOINT_NAMES,
    stiffness=10.0,
    damping=0.4,
    effort_limit=2.0,
    armature=BRUSHLESS_ARMATURE,
    delay_min_lag=0,
    delay_max_lag=3,
    delay_hold_prob=0.4,
    delay_update_period=10,
)

# 沿用既有速度反馈增益，关闭踝部位置项；NT 包络与其他电机参数相同。
ANKLE_VELOCITY_ACTUATOR_CFG = replace(
    BRUSHLESS_ACTUATOR_CFG,
    target_names_expr=VELOCITY_JOINT_NAMES,
    stiffness=0.0,
)

# 2026-11-16 全电机驱动：原 head_yaw/head_roll/mouth 三个 HD1910 舵机改用
# 与腿部相同的 HTDW-3532 无刷位置电机（方案 A：只换执行器模型，沿用无刷的
# 控制参数 stiffness=10.0 / damping=0.4 / effort_limit=2.0 / armature）。
#
# 影响：头部偏航与横滚的力矩上限从舵机的 1.471 N·m 提升到 2.0 N·m，
# 且控制律由固件增益 kp_fw=32 改为 SI 关节 PD。此前训练的检查点因执行器
# 动力学改变而不再等价，需重新训练。
#
# 名字保留为 SERVO_ACTUATOR_CFG 以兼容既有导入；它不再产生 HD1910 执行器。
SERVO_ACTUATOR_CFG = replace(
    BRUSHLESS_ACTUATOR_CFG,
    target_names_expr=SERVO_JOINT_NAMES,
)

CYBERDUCK_V2_ROBOT_CFG = EntityCfg(
    spec_fn=get_robot_spec,
    init_state=HOME_FRAME,
    articulation=EntityArticulationInfoCfg(
        actuators=(
            BRUSHLESS_ACTUATOR_CFG,
            ANKLE_VELOCITY_ACTUATOR_CFG,
        ),
        soft_joint_pos_limit_factor=1.0,
    ),
    sort_actuators=True,
)


def get_cyberduck_v2_robot_cfg() -> EntityCfg:
    """返回 13 路位置控制、2 路踝部速度控制的独立配置副本。"""
    return deepcopy(CYBERDUCK_V2_ROBOT_CFG)


# ---------- 静态预览 ----------
def make_preview() -> tuple[mujoco.MjModel, mujoco.MjData]:
    """编译单环境平地场景并恢复默认 HOME 初态；仅用于静态形态检查。"""
    from mjlab.scene import Scene, SceneCfg
    from mjlab.sim import MujocoCfg
    from mjlab.terrains import TerrainEntityCfg

    scene = Scene(
        SceneCfg(
            num_envs=1,
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={"robot": get_cyberduck_v2_robot_cfg()},
        ),
        device="cpu",
    )
    model = scene.compile()
    MujocoCfg().apply(model)
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("init_state").id)
    mujoco.mj_forward(model, data)
    return model, data


if __name__ == "__main__":
    import time

    from mujoco import viewer as mj_viewer

    preview_model, preview_data = make_preview()
    with mj_viewer.launch_passive(preview_model, preview_data) as viewer:
        while viewer.is_running():
            viewer.sync()
            time.sleep(1.0 / 60.0)
