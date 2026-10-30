"""HT-DK robot resources, mixed actuators, and the mjlab entity.

Task configurations choose their policy action subset and order explicitly.
"""

from copy import deepcopy
from pathlib import Path

import mujoco
import numpy as np
from mjlab.entity import Entity, EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

from ht_microduck.actuator import FrictionDRBamActuatorCfg, HTDW3532ActuatorCfg

# Robot body only: mjlab's Scene adds its own terrain plane and sun, so a floor,
# light or skybox in this XML would be a duplicate.
_ROBOT_DIR: Path = Path(__file__).resolve().parent / "ht_microduck"
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

# Crouched HOME stance with level soles and the centre of mass mid-foot.
#
# Measured with the T042 probes (.artifacts/t042-stance, RTX 4060): 5-6 s
# zero-action holds at 50 Hz (dt=0.002 s, decimation 10), 4 seeds x 16 envs, with
# each candidate spawned at its own geometric ground height.
#   - both soles parallel to the ground: 0.13 deg tilt (the earlier zero pose is
#     4.87 deg, i.e. both feet cant inward);
#   - centre of mass 40.0 mm behind the toes and 34.3 mm ahead of the heels, so it
#     is essentially centred instead of leaning forward or back;
#   - static holding torque <= 0.18 N*m per joint, far below the 2 N*m cap;
#   - 0/64 falls. The zero pose also survives (0/48) but stands on canted soles
#     with a 36 mm narrower stance.
#   - root height (0.1534 m) puts the lowest sole vertex 0.4 mm above the plane.
#     Height matters more than it looks: any real clearance turns the reset into a
#     drop, and the landing impact collapses this stance. At 0.1540 m 1/128 worlds
#     fell, at 0.1545-0.1548 m 0/128, at 0.1550 m 1/96 and at the previous default's
#     3.84 mm face clearance (0.1586 m) 2/64. 0.1534 m is 0/128 across 8 seeds.
#
# hip_roll is a mirrored pair (+0.0873 / -0.0873); 0.0873 is the value that makes
# the soles level. hip_pitch/calf/ankle are NOT mirrored: both legs share a sign.
#
# Rejected by the same measurement: hip_pitch = 1.57 rad (the joint limit) folds
# the leg until the feet pass behind the hips and the robot falls in 48/48 worlds;
# hip_roll = 0.38 rad cantilevers each sole by 16.9 deg onto its inner edge.
HOME_JOINT_POS: dict[str, float] = {
    **dict.fromkeys(JOINT_NAMES, 0.0),
    "r_hip_roll_joint": 0.0873,
    "l_hip_roll_joint": -0.0873,
    "r_hip_pitch_joint": 0.85,
    "l_hip_pitch_joint": 0.85,
    "r_calf_joint": -1.20,
    "l_calf_joint": -1.20,
    "r_ankle_joint": 0.35,
    "l_ankle_joint": 0.35,
}

HOME_FRAME = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.1534),
    rot=(1.0, 0.0, 0.0, 0.0),
    lin_vel=(0.0, 0.0, 0.0),
    ang_vel=(0.0, 0.0, 0.0),
    joint_pos=dict(HOME_JOINT_POS),
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

# Output-side reflected rotor inertia, J_motor * gear_ratio**2 [kg m^2].
#
# Why it is needed: without it the joint has almost no inertia, and the PD
# damping term is integrated against nearly nothing. Holding HOME makes the legs
# buzz at ~6 Hz instead of standing still. Over the standing preview, mean
# |joint velocity| and the visible frame-to-frame pixel change fall as armature
# rises (0.1055 -> 0.0257 -> 0.0044 rad/s, pixels 1.71 -> 0.29 -> 0.07 at
# 0 / 0.002 / 0.01). Halving dt also halves the buzz, the signature of a
# timestep-dependent numerical artefact rather than real motion.
#
# Provenance: user-supplied on 2026-10-27 as the HTDW-3532 joint-side armature.
# It is the only inertia figure available for this motor: the HTDW-3532 datasheet
# png has only the rpm/N·m curve, our params/README does not infer rotor inertia,
# the Hightorque product list and manual (book.hightorque.cn/Module20260917,
# 15 models) publish no inertia figure, the official STEP download carries no
# mass properties, and the model has been dropped from hightorque.cn.
#
# Sanity check, consistent with the number: at the 32:1 gearbox this reflects to
# 0.0069753532276 / 32**2 = 6.81e-6 kg m^2 = 68.1 g·cm^2 at the rotor, matching
# a ~60 g·cm^2 steel cylinder of this motor's size. An earlier placeholder of
# 0.002 (copied from the upstream duck MJCF, which hardcodes it for every joint)
# implied only 19.5 g·cm^2 and was a pure numerical prior; this replaces it.
BRUSHLESS_ARMATURE = 0.0069753532276

# Joint-side simulation defaults, not hardware calibration.
# Keep effort_limit <= the source MJCF ceiling above.
BRUSHLESS_ACTUATOR_CFG = HTDW3532ActuatorCfg(
    target_names_expr=BRUSHLESS_JOINT_NAMES,
    stiffness=10.0,
    damping=0.4,
    effort_limit=2.0,
    armature=BRUSHLESS_ARMATURE,
    delay_min_lag=0,
    delay_max_lag=3,
    delay_hold_prob=0.4,
    delay_update_period=10,
)

# Feetech's HD1910 7.4 V M6 model; kp_fw is a firmware gain, not SI stiffness.
# Source and hardware assumptions: actuator/HD_1910_C001/params/README.md.
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


def make_preview() -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Compile the standalone preview and wind it to the HOME stance.

    Built the way the reference ``go2``/``ri_4438`` constants files are: one
    ``Entity``, compile its spec, hand the model to the viewer. Two differences
    are deliberate, because both bugs were measured on this robot:

    - ``MujocoCfg().apply`` first. The spec carries no ``<option>``, so a plain
      compile gives MuJoCo's default explicit Euler. Training compiles the same
      actuators through ``MujocoCfg`` (implicitfast), so the preview uses the
      same physics. This used to be the whole fix: with the joints at armature
      0 the explicit damping was unstable and the robot juddered at ~25 rad/s
      forever. Now that ``BRUSHLESS_ARMATURE`` gives them real inertia, plain
      euler survives too (0.032 vs 0.025 rad/s), but the config is still applied
      to keep preview and training bit-for-bit on the same integrator.
    - Return an ``MjData`` wound to ``init_state``. ``viewer.launch(model)``
      would build its own ``MjData`` at the XML default pose (root 0.171 m,
      every joint straight), so ``init_state`` would never be visible and that
      pose is not a stance this robot can hold.

    The stance is held with each actuator's own compiled gain, because this
    model's ``ctrl`` is an affine-PD input (``ctrl = kp * q_target``), not a
    torque: ``ctrl = 0`` drives every leg joint towards zero rather than
    switching the drive off. The keyframe stores plain joint targets, so they
    are scaled by ``-biasprm[:, 1]`` to get the runtime command. HD1910
    compiles to a plain torque motor with no position bias, so its gain reads 0
    and the head droops by <= 0.1 rad instead of being servo-driven; the
    preview does not model BAM.

    This uses no ``Scene``, so it needs no torch tensors and takes no device:
    the preview opens while the GPU is busy training.
    """
    from mjlab.sim import MujocoCfg

    entity = Entity(get_ht_microduck_robot_cfg())
    spec = entity.spec
    _add_preview_ground(spec)
    model = spec.compile()
    MujocoCfg().apply(model)

    key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "init_state")
    if key_id < 0:
        raise RuntimeError("compiled entity has no init_state keyframe")
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, key_id)
    data.ctrl[:] = -model.actuator_biasprm[:, 1] * np.asarray(model.key(key_id).ctrl)
    mujoco.mj_forward(model, data)
    return model, data


def _add_preview_ground(spec: mujoco.MjSpec) -> None:
    """Add the plane, checker texture and sun that ``Scene`` would supply.

    Mirrors mjlab's ``TerrainEntityCfg(terrain_type="plane")`` defaults and its
    ``_DEFAULT_SUN_LIGHT`` so the standalone preview looks like the training
    scene. The robot XML itself keeps no floor or light (T016/T039); this only
    touches the throwaway spec built for the viewer.
    """
    spec.add_texture(
        name="groundplane",
        type=mujoco.mjtTexture.mjTEXTURE_2D,
        builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
        mark=mujoco.mjtMark.mjMARK_EDGE,
        rgb1=[0.2, 0.3, 0.4],
        rgb2=[0.1, 0.2, 0.3],
        markrgb=[0.8, 0.8, 0.8],
        width=300,
        height=300,
    )
    spec.add_material(
        name="groundplane",
        textures=["groundplane"],
        texuniform=True,
        texrepeat=[4.0, 4.0],
        reflectance=0.2,
    )
    spec.worldbody.add_light(
        name="sun",
        pos=[0.0, 0.0, 1.5],
        dir=[0.0, 0.0, -1.0],
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL,
    )
    spec.worldbody.add_body(name="terrain").add_geom(
        name="terrain",
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[0.0, 0.0, 0.01],
        material="groundplane",
        friction=[1.0, 0.005, 0.0001],
        condim=3,
    )


if __name__ == "__main__":
    from mujoco import viewer

    preview_model, preview_data = make_preview()
    viewer.launch(preview_model, preview_data)
