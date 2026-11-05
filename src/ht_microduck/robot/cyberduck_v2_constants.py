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

from ht_microduck.actuator import FrictionDRBamActuatorCfg, HTDW3532ActuatorCfg

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

# 12 个无刷中，两踝控制速度、其余控制位置；头部三个舵机控制位置。
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
)
VELOCITY_JOINT_NAMES: tuple[str, ...] = ("r_ankle_joint", "l_ankle_joint")
BRUSHLESS_POSITION_JOINT_NAMES: tuple[str, ...] = tuple(
    name for name in BRUSHLESS_JOINT_NAMES if name not in VELOCITY_JOINT_NAMES
)
SERVO_JOINT_NAMES: tuple[str, ...] = (
    "head_yaw_joint",
    "head_roll_joint",
    "mouth_joint",
)
POSITION_JOINT_NAMES: tuple[str, ...] = (
    BRUSHLESS_POSITION_JOINT_NAMES + SERVO_JOINT_NAMES
)

# 编译后的执行器仍按原 12＋3 顺序；配置分组不要求 ctrl 连续分块。
ACTUATED_JOINT_NAMES: tuple[str, ...] = BRUSHLESS_JOINT_NAMES + SERVO_JOINT_NAMES
ACTUATOR_NAMES: tuple[str, ...] = ACTUATED_JOINT_NAMES
JOINT_TO_MOTOR_MODEL: dict[str, str] = {
    **dict.fromkeys(BRUSHLESS_JOINT_NAMES, "HTDW-3532-02-DNE"),
    **dict.fromkeys(SERVO_JOINT_NAMES, "FEETECH HD1910"),
}

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
# 复用源 XML 的零位和根高度，未将此初态认定为稳定站姿。
SOURCE_JOINT_POS: dict[str, float] = dict.fromkeys(JOINT_NAMES, 0.0)
SOURCE_FRAME = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.252),
    rot=(1.0, 0.0, 0.0, 0.0),
    lin_vel=(0.0, 0.0, 0.0),
    ang_vel=(0.0, 0.0, 0.0),
    joint_pos=dict(SOURCE_JOINT_POS),
    joint_vel=dict.fromkeys(JOINT_NAMES, 0.0),
)

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

# 舵机采用项目既有 7.4 V HD1910 BAM M6；kp_fw 为固件模型增益。
# 供电、限幅和 0–3 个物理步延迟均为沿用的仿真假设，关闭摩擦随机化。
SERVO_ACTUATOR_CFG = FrictionDRBamActuatorCfg(
    target_names_expr=SERVO_JOINT_NAMES,
    vin=7.4,
    kp_fw=32.0,
    effort_limit=1.471,
    friction_scale_range=None,
    delay_min_lag=0,
    delay_max_lag=3,
    delay_hold_prob=0.4,
    delay_update_period=10,
)

CYBERDUCK_V2_ROBOT_CFG = EntityCfg(
    spec_fn=get_robot_spec,
    init_state=SOURCE_FRAME,
    articulation=EntityArticulationInfoCfg(
        actuators=(
            BRUSHLESS_ACTUATOR_CFG,
            ANKLE_VELOCITY_ACTUATOR_CFG,
            SERVO_ACTUATOR_CFG,
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
    """编译单环境平地场景并恢复源初态；仅用于静态形态检查。"""
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
