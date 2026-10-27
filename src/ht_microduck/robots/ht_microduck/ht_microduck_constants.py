"""HT-DK robot resources, mixed actuators, and the mjlab entity.

Task configurations choose their policy action subset and order explicitly.
"""

from copy import deepcopy
from pathlib import Path

import mujoco
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

from ht_microduck.actuators import FrictionDRBamActuatorCfg, HTDW3532ActuatorCfg

# Robot body only: mjlab's Scene adds its own terrain plane and sun, so a floor,
# light or skybox in this XML would be a duplicate.
_ROBOT_DIR: Path = Path(__file__).resolve().parent / "xmls"
MJCF_PATH: Path = _ROBOT_DIR / "HT-DK_URDF.xml"

assert MJCF_PATH.exists(), f"XML not found: {MJCF_PATH}"

# Collision geoms the URDF export leaves unnamed, in body declaration order.
_COLLISION_NAMES_BY_BODY: dict[str, tuple[str, ...]] = {
    "base_link": ("base_front_collision", "base_rear_collision"),
    "r_hip_roll_link": ("r_hip_roll_collision",),
    "r_hip_pitch_link": ("r_hip_pitch_collision",),
    "r_ankle_link": ("r_foot_collision",),
    "l_hip_roll_link": ("l_hip_roll_collision",),
    "l_hip_pitch_link": ("l_hip_pitch_collision",),
    "l_ankle_link": ("l_foot_collision",),
    "head_roll_link": ("head_collision",),
    "mouth_link": ("mouth_collision",),
}

COLLISION_GEOM_NAMES: tuple[str, ...] = tuple(
    name for names in _COLLISION_NAMES_BY_BODY.values() for name in names
)

FOOT_SITE_NAMES: tuple[str, ...] = ("r_foot", "l_foot")

# Ankle-frame AABB centers of the STL sole faces [m], rounded to 1e-8 m.
# The soles tilt by mirrored 5 degrees; sites keep ankle-frame orientations.
# Model reference points, not measured hardware sensor locations.
FOOT_SITE_POSITIONS: dict[str, tuple[float, float, float]] = {
    "r_foot": (0.01, -0.00061009, -0.03923883),
    "l_foot": (0.00999891, 0.00061009, -0.03923992),
}


def get_spec() -> mujoco.MjSpec:
    """Load the robot-only model: IMU site and sensors, no ground or lights."""
    return mujoco.MjSpec.from_file(str(MJCF_PATH))


def get_robot_spec() -> mujoco.MjSpec:
    """Name the source collision geoms and add the sole reference sites."""
    spec = get_spec()
    for body_name, names in _COLLISION_NAMES_BY_BODY.items():
        geoms = [
            geom
            for geom in spec.body(body_name).geoms
            if geom.contype or geom.conaffinity
        ]
        if len(geoms) != len(names):
            raise ValueError(
                f"{body_name}: expected {len(names)} collision geoms, "
                f"found {len(geoms)}; update the robot collision mapping"
            )
        for geom, name in zip(geoms, names, strict=True):
            geom.name = name

    for side, site_name in zip(("r", "l"), FOOT_SITE_NAMES, strict=True):
        spec.body(f"{side}_ankle_link").add_site(
            name=site_name,
            pos=FOOT_SITE_POSITIONS[site_name],
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            size=(0.002, 0.0, 0.0),
            rgba=(0.1, 0.8, 0.2, 1.0),
            group=3,
        )
    return spec


# 12 brushless HTDW-3532 (10 leg, neck and head pitch) + 3 FEETECH HD1910.
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

SERVO_JOINT_NAMES: tuple[str, ...] = (
    "head_yaw_joint",
    "head_roll_joint",
    "mouth_joint",
)

JOINT_NAMES: tuple[str, ...] = BRUSHLESS_JOINT_NAMES + SERVO_JOINT_NAMES

JOINT_TO_MOTOR_MODEL: dict[str, str] = {
    **dict.fromkeys(BRUSHLESS_JOINT_NAMES, "HTDW-3532-02-DNE"),
    **dict.fromkeys(SERVO_JOINT_NAMES, "FEETECH HD1910"),
}

# Neutral pose: lowest sole edges about 3.84 mm above a z=0 plane.
HOME_FRAME = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.171),
    rot=(1.0, 0.0, 0.0, 0.0),
    lin_vel=(0.0, 0.0, 0.0),
    ang_vel=(0.0, 0.0, 0.0),
    joint_pos=dict.fromkeys(JOINT_NAMES, 0.0),
    joint_vel=dict.fromkeys(JOINT_NAMES, 0.0),
)

FULL_COLLISION = CollisionCfg(
    geom_names_expr=COLLISION_GEOM_NAMES,
    contype=1,
    conaffinity=1,
    condim=3,
    priority=0,
    friction=(1.0, 0.005, 0.0001),
    disable_other_geoms=True,
)

# Source MJCF joint-side force ceiling; not a confirmed hardware rating.
BRUSHLESS_MJCF_EFFORT_LIMIT = 3.7

# Joint-side simulation defaults, not hardware calibration.
# Keep effort_limit <= the source MJCF ceiling above.
BRUSHLESS_ACTUATOR_CFG = HTDW3532ActuatorCfg(
    target_names_expr=BRUSHLESS_JOINT_NAMES,
    stiffness=10.0,
    damping=0.4,
    effort_limit=2.0,
    delay_min_lag=0,
    delay_max_lag=3,
    delay_hold_prob=0.4,
    delay_update_period=10,
)

# Feetech's HD1910 7.4 V M6 model; kp_fw is a firmware gain, not SI stiffness.
# Source and hardware assumptions: actuators/HD_1910_C001/params/README.md.
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

HT_MICRODUCK_ROBOT_CFG = EntityCfg(
    spec_fn=get_robot_spec,
    init_state=HOME_FRAME,
    collisions=(FULL_COLLISION,),
    articulation=EntityArticulationInfoCfg(
        actuators=(BRUSHLESS_ACTUATOR_CFG, SERVO_ACTUATOR_CFG),
        soft_joint_pos_limit_factor=1.0,  # Keeps the closed mouth at its bound.
    ),
)


def get_ht_microduck_robot_cfg() -> EntityCfg:
    """Return an independent config for task-specific edits."""
    return deepcopy(HT_MICRODUCK_ROBOT_CFG)


if __name__ == "__main__":
    import mujoco.viewer as viewer
    from mjlab.scene import Scene, SceneCfg
    from mjlab.terrains import TerrainEntityCfg

    SCENE_CFG = SceneCfg(
        terrain=TerrainEntityCfg(terrain_type="plane"),
        entities={"robot": HT_MICRODUCK_ROBOT_CFG},
    )
    scene = Scene(SCENE_CFG, device="cuda:0")
    viewer.launch(scene.compile())
