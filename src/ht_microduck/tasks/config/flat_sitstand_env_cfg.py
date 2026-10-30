# Copyright (c) 2026-2027 zh
"""官方 sitstand 任务配方的 HT 适配；奖励、重置和课程对应 bae39f59。

来源：pollen-robotics/microduck_rl，Apache-2.0。
只替换机器人命名、实体关节索引、已确认的姿态常量和 mjlab 1.6 接口。
"""

from __future__ import annotations

import math
from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import (
    CurriculumTermCfg,
    EventTermCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.metrics_manager import MetricsTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ht_microduck.robot.ht_microduck_constants import get_ht_microduck_robot_cfg
from ht_microduck.tasks.config.flat_velocity_env_cfg import (
    HEAD_BODY_NAMES,
    HEAD_POSE_CMD_RESAMPLE_S,
    MICRODUCK_ROUGH_TERRAINS_CFG,
)
from ht_microduck.tasks.config.official_common import make_official_base_env_cfg
from ht_microduck.tasks.config.official_robot import (
    HEAD_JOINT_INDICES as _HT_HEAD_INDICES,
)
from ht_microduck.tasks.config.official_robot import (
    LEG_JOINT_INDICES as _HT_LEG_INDICES,
)
from ht_microduck.tasks.config.official_robot import (
    SIT_Z as _HT_SIT_Z,
)
from ht_microduck.tasks.config.official_robot import (
    SITTING_JOINT_OVERRIDES as _HT_SITTING_OVERRIDES,
)
from ht_microduck.tasks.config.official_robot import (
    STAND_Z as _HT_STAND_Z,
)
from ht_microduck.tasks.config.official_robot import (
    adapt_official_cfg,
)
from ht_microduck.tasks.mdp import official as microduck_mdp
from ht_microduck.tasks.mdp.action_metrics import (
    ActuatorSaturationDuration,
    actuator_saturation_fraction,
    applied_target_violation_fraction,
    requested_target_violation_fraction,
    target_clip_fraction,
)
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg

ENABLE_SYMMETRY = False
ENABLE_COM_RANDOMIZATION = True
ENABLE_HEAD_COM_RANDOMIZATION = True
ENABLE_KP_RANDOMIZATION = False
ENABLE_KD_RANDOMIZATION = False
ENABLE_MASS_INERTIA_RANDOMIZATION = True
ENABLE_JOINT_FRICTION_RANDOMIZATION = True
ENABLE_ARMATURE_RANDOMIZATION = True
ENABLE_VELOCITY_PUSHES = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True
ENABLE_ENCODER_BIAS = True
COM_RANDOMIZATION_RANGE = 0.003
HEAD_COM_RANDOMIZATION_RANGE = 0.003
MASS_INERTIA_RANDOMIZATION_RANGE = (0.95, 1.05)
ARMATURE_RANDOMIZATION_RANGE = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE = (0.9, 1.1)
ENCODER_BIAS_RANGE = (-0.015, 0.015)
KP_RANDOMIZATION_RANGE = (0.85, 1.15)
KD_RANDOMIZATION_RANGE = (0.9, 1.1)
VELOCITY_PUSH_INTERVAL_S = (3.0, 6.0)
VELOCITY_PUSH_RANGE = (-0.3, 0.3)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0
EPISODE_LENGTH_S = 12.0
POSTURE_DWELL_S = (3.5, 6.5)
SIT_PROB = 0.5
SITTING_TARGET_OVERRIDES = _HT_SITTING_OVERRIDES
_LEG_JOINTS = _HT_LEG_INDICES
_NECK_JOINTS = _HT_HEAD_INDICES
STAND_Z = _HT_STAND_Z
SIT_Z = _HT_SIT_Z
# 区间内门限保持官方坐高 .060、站高 .115 之间的相对位置。
_HEIGHT_RANGE_SCALE = (STAND_Z - SIT_Z) / (0.115 - 0.060)
STAND_UPRIGHT_Z = SIT_Z + (0.100 - 0.060) * _HEIGHT_RANGE_SCALE
SIT_UPRIGHT_Z = SIT_Z + (0.075 - 0.060) * _HEIGHT_RANGE_SCALE
# 起身末端的 1 cm 余量保持物理距离，不随坐站行程缩放。
RISE_BOOTSTRAP_MAX_HEIGHT = STAND_Z + (0.125 - 0.115)
POSTURE_RAMP_S = 2.0
MAX_DESCENT_SPEED = 0.05
MAX_RISE_SPEED = 0.08
ENABLE_SEATED_FALLBACK_HARDENING = True
SEATED_HEAD_JERK_INTERVAL_S = (0.3, 0.8)
SEATED_TIP_INTERVAL_S = (3.0, 6.0)


def make_sitstand_env_cfg(
    num_envs: int = 4096,
    seed: int | None = None,
    play: bool = False,
    *,
    rough: bool = False,
    bound_targets: bool = True,
) -> ManagerBasedRlEnvCfg:
    feet_ground_cfg = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="geom",
            pattern="^(left_foot_collision|right_foot_collision)$",
            entity="robot",
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    self_collision_cfg = ContactSensorCfg(
        name="self_collision",
        primary=ContactMatch(mode="subtree", pattern="trunk_base", entity="robot"),
        secondary=ContactMatch(mode="subtree", pattern="trunk_base", entity="robot"),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )
    foot_frictions_geom_names = ("left_foot_collision", "right_foot_collision")
    cfg = make_official_base_env_cfg()
    cfg.scene.entities = {"robot": get_ht_microduck_robot_cfg()}
    cfg.scene.sensors = (feet_ground_cfg, self_collision_cfg)
    cfg.viewer.body_name = "trunk_base"
    cfg.episode_length_s = EPISODE_LENGTH_S
    joint_pos_action = cfg.actions["joint_pos"]
    assert isinstance(joint_pos_action, JointPositionActionCfg)
    joint_pos_action.scale = 1.0
    for name in [
        "track_linear_velocity",
        "track_angular_velocity",
        "air_time",
        "foot_clearance",
        "foot_swing_height",
        "foot_slip",
        "pose",
    ]:
        if name in cfg.rewards:
            del cfg.rewards[name]
    cfg.rewards["posture_pose_legs"] = RewardTermCfg(
        func=microduck_mdp.posture_pose_match,
        weight=4.0,
        params={
            "command_name": "twist",
            "std": 0.5,
            "joint_indices": _LEG_JOINTS,
            "sit_overrides": SITTING_TARGET_OVERRIDES,
        },
    )
    cfg.rewards["head_pose_tracking"] = RewardTermCfg(
        func=microduck_mdp.head_pose_tracking,
        weight=0.75,
        params={"command_name": "head_pose", "std": 0.5},
    )
    cfg.rewards["posture_pose_l1"] = RewardTermCfg(
        func=microduck_mdp.posture_pose_l1,
        weight=1.0,
        params={
            "command_name": "twist",
            "joint_indices": _LEG_JOINTS,
            "sit_overrides": SITTING_TARGET_OVERRIDES,
        },
    )
    cfg.rewards["posture_height"] = RewardTermCfg(
        func=microduck_mdp.posture_height_gaussian,
        weight=1.0,
        params={
            "command_name": "twist",
            "sit_z": SIT_Z,
            "stand_z": STAND_Z,
            "std": 0.04,
        },
    )
    cfg.rewards["posture_height_sharp"] = RewardTermCfg(
        func=microduck_mdp.posture_height_gaussian,
        weight=1.0,
        params={
            "command_name": "twist",
            "sit_z": SIT_Z,
            "stand_z": STAND_Z,
            "std": 0.015,
        },
    )
    cfg.rewards["posture_height_l1"] = RewardTermCfg(
        func=microduck_mdp.posture_height_l1,
        weight=6.0,
        params={"command_name": "twist", "sit_z": SIT_Z, "stand_z": STAND_Z},
    )
    cfg.rewards["rise_bootstrap"] = RewardTermCfg(
        func=microduck_mdp.posture_rise_bootstrap,
        weight=0.75,
        params={"command_name": "twist", "max_height": RISE_BOOTSTRAP_MAX_HEIGHT, "max_vz": MAX_RISE_SPEED},
    )
    cfg.rewards["descent_speed"] = RewardTermCfg(
        func=microduck_mdp.trunk_downward_velocity_penalty,
        weight=10.0,
        params={
            "max_down_vel": MAX_DESCENT_SPEED,
            "asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",)),
        },
    )
    cfg.rewards["rise_speed"] = RewardTermCfg(
        func=microduck_mdp.trunk_upward_velocity_penalty,
        weight=0.0,
        params={
            "max_up_vel": MAX_RISE_SPEED,
            "asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",)),
        },
    )
    cfg.rewards["gentle_motion"] = RewardTermCfg(
        func=microduck_mdp.trunk_vertical_accel_penalty,
        weight=0.05,
        params={"asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",))},
    )
    cfg.rewards["upright_linear"] = RewardTermCfg(
        func=microduck_mdp.body_upright_linear,
        weight=2.5,
        params={"asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",))},
    )
    cfg.rewards["upright_while_tall"] = RewardTermCfg(
        func=microduck_mdp.upright_while_tall,
        weight=1.5,
        params={
            "height_low": SIT_UPRIGHT_Z,
            "height_high": STAND_UPRIGHT_Z,
            "asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",)),
        },
    )
    cfg.rewards["posture_stillness"] = RewardTermCfg(
        func=microduck_mdp.posture_stillness,
        weight=2.0,
        params={
            "command_name": "twist",
            "sit_z": SIT_Z,
            "stand_z": STAND_Z,
            "band_full": 0.012,
            "band_zero": 0.03,
            "vel_std": 0.05,
            "tilt_full_deg": 25.0,
            "tilt_zero_deg": 60.0,
        },
    )
    cfg.rewards["posture_composite"] = RewardTermCfg(
        func=microduck_mdp.posture_composite,
        weight=3.0,
        params={
            "command_name": "twist",
            "sit_overrides": SITTING_TARGET_OVERRIDES,
            "joint_indices": _LEG_JOINTS,
            "sit_z": SIT_Z,
            "stand_z": STAND_Z,
            "height_std": 0.03,
            "upright_std": 0.4,
            "pose_std": 0.4,
            "head_std": 0.4,
        },
    )
    cfg.rewards["action_rate_l2"] = RewardTermCfg(func=mdp.action_rate_l2, weight=-0.1)
    cfg.rewards["joint_torque_rate_l2"] = RewardTermCfg(
        func=microduck_mdp.joint_torque_rate_l2, weight=0.0
    )
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = ("trunk_base",)
    cfg.rewards["body_ang_vel"].weight = -0.05
    cfg.rewards["angular_momentum"].weight = -0.02
    cfg.rewards.pop("soft_landing", None)
    if ENABLE_SEATED_FALLBACK_HARDENING:
        cfg.rewards["neck_strain_leaned"] = RewardTermCfg(
            func=microduck_mdp.neck_torque_when_tilted,
            weight=-0.5,
            params={
                "command_name": "twist",
                "tilt_start_deg": 12.0,
                "tilt_full_deg": 25.0,
                "torque_scale": 0.1,
            },
        )
    cfg.rewards["self_collisions"] = RewardTermCfg(
        func=mdp.self_collision_cost,
        weight=-1.0,
        params={"sensor_name": self_collision_cfg.name},
    )
    if "upright" in cfg.rewards:
        del cfg.rewards["upright"]
    del cfg.observations["actor"].terms["base_lin_vel"]
    cfg.observations["critic"].terms["base_lin_vel"] = ObservationTermCfg(
        func=mdp.base_lin_vel, scale=1.0
    )
    del cfg.observations["critic"].terms["foot_height"]
    del cfg.observations["actor"].terms["height_scan"]
    del cfg.observations["critic"].terms["height_scan"]
    gravity_term_name = "projected_gravity"
    cfg.observations["actor"].terms[gravity_term_name] = deepcopy(
        cfg.observations["actor"].terms[gravity_term_name]
    )
    cfg.observations["actor"].terms["base_ang_vel"] = deepcopy(
        cfg.observations["actor"].terms["base_ang_vel"]
    )
    cfg.observations["actor"].terms["base_ang_vel"].delay_min_lag = 0
    cfg.observations["actor"].terms["base_ang_vel"].delay_max_lag = 1
    cfg.observations["actor"].terms["base_ang_vel"].delay_update_period = 64
    cfg.observations["actor"].terms[gravity_term_name].delay_min_lag = 0
    cfg.observations["actor"].terms[gravity_term_name].delay_max_lag = 1
    cfg.observations["actor"].terms[gravity_term_name].delay_update_period = 64
    cfg.observations["actor"].terms["base_ang_vel"].noise = Unoise(
        n_min=-0.03, n_max=0.03
    )
    cfg.observations["actor"].terms[gravity_term_name].noise = Unoise(
        n_min=-0.01, n_max=0.01
    )
    cfg.observations["actor"].terms["joint_pos"].noise = Unoise(
        n_min=-0.001, n_max=0.001
    )
    cfg.observations["actor"].terms["joint_vel"].noise = Unoise(n_min=-0.25, n_max=0.25)
    if ENABLE_IMU_ORIENTATION_RANDOMIZATION:
        av = cfg.observations["actor"].terms["base_ang_vel"]
        av.func = microduck_mdp.base_ang_vel_imu_misaligned
        av.params = {"max_angle_deg": IMU_ORIENTATION_RANDOMIZATION_ANGLE}
        g = cfg.observations["actor"].terms[gravity_term_name]
        g.func = microduck_mdp.projected_gravity_imu_misaligned
        g.params = {"max_angle_deg": IMU_ORIENTATION_RANDOMIZATION_ANGLE}
    cfg.observations["actor"].terms["joint_vel"] = deepcopy(
        cfg.observations["actor"].terms["joint_vel"]
    )
    cfg.observations["actor"].terms["joint_vel"].delay_min_lag = 1
    cfg.observations["actor"].terms["joint_vel"].delay_max_lag = 1
    cfg.observations["actor"].terms["joint_vel"].delay_update_period = 0
    passive_excluded = SceneEntityCfg("robot", joint_names=("^(?!passive_).*",))
    for grp in ("actor", "critic"):
        for term in ("joint_pos", "joint_vel"):
            cfg.observations[grp].terms[term] = deepcopy(
                cfg.observations[grp].terms[term]
            )
            cfg.observations[grp].terms[term].params["asset_cfg"] = deepcopy(
                passive_excluded
            )
    if ENABLE_ENCODER_BIAS:
        cfg.events["encoder_bias"].params["bias_range"] = ENCODER_BIAS_RANGE
        cfg.observations["actor"].terms["joint_pos"].params["biased"] = True
        cfg.observations["critic"].terms["joint_pos"].params["biased"] = False
    else:
        cfg.events.pop("encoder_bias", None)
    cfg.commands["head_pose"] = microduck_mdp.UniformPoseCommandCfg(
        resampling_time_range=HEAD_POSE_CMD_RESAMPLE_S,
        ranges=((-0.05, 0.05), (-0.05, 0.05), (-0.07, 0.07), (-0.015, 0.015)),
    )
    for group in ("actor", "critic"):
        cfg.observations[group].terms["head_command"] = ObservationTermCfg(
            func=mdp.generated_commands, params={"command_name": "head_pose"}
        )
        cfg.observations[group].terms["body_command"] = ObservationTermCfg(
            func=microduck_mdp.zero_command_padding, params={"dim": 6}
        )
    command = cfg.commands["twist"]
    command.rel_standing_envs = 0.0
    command.rel_heading_envs = 0.0
    command.heading_command = False
    command.ranges.heading = None
    command.resampling_time_range = POSTURE_DWELL_S
    command.debug_vis = False
    cfg.commands["twist"] = microduck_mdp.SitStandCommandCfg(
        **{
            **vars(command),
            "sit_prob": SIT_PROB,
            "ramp_s": POSTURE_RAMP_S,
            "sit_z": SIT_Z,
            "stand_z": STAND_Z,
        }
    )
    if "fell_over" in cfg.terminations:
        del cfg.terminations["fell_over"]
    cfg.terminations["nan_state"] = TerminationTermCfg(
        func=microduck_mdp.robot_state_is_nan, time_out=False
    )
    cfg.events["expand_bam_friction_fields"] = EventTermCfg(
        func=microduck_mdp.expand_bam_friction_fields, mode="startup"
    )
    cfg.events["reset_action_history"] = EventTermCfg(
        func=microduck_mdp.reset_action_history, mode="reset"
    )
    cfg.events["foot_friction"].params[
        "asset_cfg"
    ].geom_names = foot_frictions_geom_names
    cfg.events["foot_friction"].params["ranges"] = (0.7, 1.3)
    cfg.events["reset_base"].params["pose_range"]["z"] = (0.11, 0.12)
    cfg.events["set_ground_state"] = EventTermCfg(
        func=microduck_mdp.set_random_ground_state,
        mode="reset",
        params={
            "face_down_prob": 0.0,
            "face_up_prob": 0.0,
            "sitting_prob": 0.5,
            "standing_prob": 0.5,
            "sitting_joint_overrides": SITTING_TARGET_OVERRIDES,
            "sitting_joint_noise_std": 0.1,
            "sitting_tilt_max": math.radians(8),
            "sitting_z_min": 0.06,
            "sitting_z_max": 0.075,
            "standing_z_min": 0.11,
            "standing_z_max": 0.12,
        },
    )
    cfg.sim.nconmax = 200
    cfg.sim.mujoco.iterations = 30
    cfg.sim.mujoco.ls_iterations = 50
    if ENABLE_VELOCITY_PUSHES:
        interval = (0.5, 1.0) if play else VELOCITY_PUSH_INTERVAL_S
        cfg.events["push_robot"] = EventTermCfg(
            func=mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=interval,
            params={
                "velocity_range": {"x": VELOCITY_PUSH_RANGE, "y": VELOCITY_PUSH_RANGE},
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
    if ENABLE_SEATED_FALLBACK_HARDENING:
        cfg.events["seated_head_jerk"] = EventTermCfg(
            func=microduck_mdp.seated_head_command_jerk,
            mode="interval",
            interval_range_s=SEATED_HEAD_JERK_INTERVAL_S,
            params={"prob": 0.0, "flip_frac": 0.5},
        )
        cfg.events["seated_tip"] = EventTermCfg(
            func=microduck_mdp.seated_backward_tip,
            mode="interval",
            interval_range_s=SEATED_TIP_INTERVAL_S,
            params={"ang_vel_range": (0.0, 0.0), "prob": 0.5, "lateral_frac": 0.3},
        )
    if ENABLE_COM_RANDOMIZATION:
        cfg.events["randomize_com"] = EventTermCfg(
            func=dr.body_ipos,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",)),
                "operation": "add",
                "ranges": (-COM_RANDOMIZATION_RANGE, COM_RANDOMIZATION_RANGE),
            },
        )
    if ENABLE_HEAD_COM_RANDOMIZATION:
        cfg.events["randomize_head_com"] = EventTermCfg(
            func=dr.body_ipos,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=HEAD_BODY_NAMES),
                "operation": "add",
                "ranges": (-HEAD_COM_RANDOMIZATION_RANGE, HEAD_COM_RANDOMIZATION_RANGE),
            },
        )
    if ENABLE_ARMATURE_RANDOMIZATION:
        cfg.events["randomize_armature"] = EventTermCfg(
            func=dr.joint_armature,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",)),
                "operation": "scale",
                "ranges": ARMATURE_RANDOMIZATION_RANGE,
            },
        )
    if ENABLE_KP_RANDOMIZATION or ENABLE_KD_RANDOMIZATION:
        kp_range = KP_RANDOMIZATION_RANGE if ENABLE_KP_RANDOMIZATION else (1.0, 1.0)
        kd_range = KD_RANDOMIZATION_RANGE if ENABLE_KD_RANDOMIZATION else (1.0, 1.0)
        cfg.events["randomize_motor_gains"] = EventTermCfg(
            func=microduck_mdp.randomize_delayed_actuator_gains,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "operation": "scale",
                "kp_range": kp_range,
                "kd_range": kd_range,
            },
        )
    if ENABLE_MASS_INERTIA_RANDOMIZATION:
        _mi_lo, _mi_hi = MASS_INERTIA_RANDOMIZATION_RANGE
        cfg.events["randomize_mass_inertia"] = EventTermCfg(
            func=dr.pseudo_inertia,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=("trunk_base",)),
                "alpha_range": (math.log(_mi_lo) / 2.0, math.log(_mi_hi) / 2.0),
            },
        )
    if ENABLE_JOINT_FRICTION_RANDOMIZATION:
        cfg.events["randomize_joint_friction"] = EventTermCfg(
            func=microduck_mdp.randomize_bam_friction,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "scale_range": JOINT_FRICTION_RANDOMIZATION_RANGE,
            },
        )
    if not rough:
        cfg.scene.terrain.terrain_type = "plane"
        cfg.scene.terrain.terrain_generator = None
    else:
        cfg.scene.terrain.terrain_type = "generator"
        cfg.scene.terrain.terrain_generator = MICRODUCK_ROUGH_TERRAINS_CFG
        if play:
            cfg.scene.terrain.terrain_generator.curriculum = False
            cfg.scene.terrain.terrain_generator.num_cols = 5
            cfg.scene.terrain.terrain_generator.num_rows = 5
    if not rough:
        del cfg.curriculum["terrain_levels"]
    del cfg.curriculum["command_vel"]
    cfg.curriculum["head_pose_range"] = CurriculumTermCfg(
        func=microduck_mdp.pose_command_range_curriculum,
        params={
            "command_name": "head_pose",
            "range_stages": [
                {
                    "step": 0,
                    "ranges": (
                        (-0.05, 0.05),
                        (-0.05, 0.05),
                        (-0.07, 0.07),
                        (-0.015, 0.015),
                    ),
                },
                {
                    "step": 500 * 24,
                    "ranges": (
                        (-0.17, 0.17),
                        (-0.17, 0.17),
                        (-0.21, 0.21),
                        (-0.047, 0.047),
                    ),
                },
                {
                    "step": 1000 * 24,
                    "ranges": (
                        (-0.39, 0.39),
                        (-0.39, 0.39),
                        (-0.49, 0.49),
                        (-0.11, 0.11),
                    ),
                },
                {
                    "step": 1500 * 24,
                    "ranges": (
                        (-0.72, 0.72),
                        (-0.72, 0.72),
                        (-0.91, 0.91),
                        (-0.2, 0.2),
                    ),
                },
                {
                    "step": 2000 * 24,
                    "ranges": ((-1.1, 1.1), (-1.1, 1.1), (-1.4, 1.4), (-0.31, 0.31)),
                },
            ],
        },
    )
    if ENABLE_COM_RANDOMIZATION:
        cfg.curriculum["com_range"] = CurriculumTermCfg(
            func=microduck_mdp.com_range_curriculum,
            params={
                "event_name": "randomize_com",
                "range_stages": [
                    {"step": 0, "range": 0.003},
                    {"step": 500 * 24, "range": 0.005},
                    {"step": 1000 * 24, "range": 0.01},
                    {"step": 1500 * 24, "range": 0.015},
                ],
            },
        )
    if ENABLE_HEAD_COM_RANDOMIZATION:
        cfg.curriculum["head_com_range"] = CurriculumTermCfg(
            func=microduck_mdp.com_range_curriculum,
            params={
                "event_name": "randomize_head_com",
                "range_stages": [
                    {"step": 0, "range": 0.003},
                    {"step": 500 * 24, "range": 0.005},
                    {"step": 1000 * 24, "range": 0.01},
                ],
            },
        )
    if ENABLE_VELOCITY_PUSHES:
        cfg.curriculum["push_magnitude"] = CurriculumTermCfg(
            func=microduck_mdp.push_curriculum,
            params={
                "event_name": "push_robot",
                "push_stages": [
                    {"step": 0, "velocity_range": {"x": (0.0, 0.0), "y": (0.0, 0.0)}},
                    {
                        "step": 1000 * 24,
                        "velocity_range": {"x": (-0.05, 0.05), "y": (-0.05, 0.05)},
                    },
                    {
                        "step": 1500 * 24,
                        "velocity_range": {"x": (-0.1, 0.1), "y": (-0.1, 0.1)},
                    },
                    {
                        "step": 2000 * 24,
                        "velocity_range": {"x": (-0.2, 0.2), "y": (-0.2, 0.2)},
                    },
                    {
                        "step": 2500 * 24,
                        "velocity_range": {
                            "x": VELOCITY_PUSH_RANGE,
                            "y": VELOCITY_PUSH_RANGE,
                        },
                    },
                ],
            },
        )
    cfg.curriculum["action_rate_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "action_rate_l2",
            "weight_stages": [
                {"step": 0, "weight": -0.1},
                {"step": 500 * 24, "weight": -0.2},
                {"step": 750 * 24, "weight": -0.4},
                {"step": 1000 * 24, "weight": -0.6},
                {"step": 1250 * 24, "weight": -0.8},
                {"step": 1500 * 24, "weight": -1.0},
            ],
        },
    )
    cfg.curriculum["descent_speed_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "descent_speed",
            "weight_stages": [
                {"step": 0, "weight": 10.0},
                {"step": 500 * 24, "weight": 20.0},
            ],
        },
    )
    cfg.curriculum["rise_speed_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "rise_speed",
            "weight_stages": [
                {"step": 0, "weight": 0.0},
                {"step": 1500 * 24, "weight": 5.0},
                {"step": 2500 * 24, "weight": 10.0},
            ],
        },
    )
    if ENABLE_SEATED_FALLBACK_HARDENING:
        cfg.curriculum["seated_head_jerk_prob"] = CurriculumTermCfg(
            func=microduck_mdp.event_param_curriculum,
            params={
                "event_name": "seated_head_jerk",
                "param_stages": [
                    {"step": 0, "params": {"prob": 0.0}},
                    {"step": 1500 * 24, "params": {"prob": 0.2}},
                    {"step": 2000 * 24, "params": {"prob": 0.4}},
                ],
            },
        )
        cfg.curriculum["seated_tip_range"] = CurriculumTermCfg(
            func=microduck_mdp.event_param_curriculum,
            params={
                "event_name": "seated_tip",
                "param_stages": [
                    {"step": 0, "params": {"ang_vel_range": (0.0, 0.0)}},
                    {"step": 1500 * 24, "params": {"ang_vel_range": (1.0, 2.5)}},
                    {"step": 2000 * 24, "params": {"ang_vel_range": (1.5, 3.25)}},
                    {"step": 2500 * 24, "params": {"ang_vel_range": (2.0, 4.0)}},
                ],
            },
        )
    cfg.curriculum["torque_rate_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "joint_torque_rate_l2",
            "weight_stages": [
                {"step": 0, "weight": 0.0},
                {"step": 750 * 24, "weight": -0.0005},
                {"step": 1250 * 24, "weight": -0.001},
            ],
        },
    )
    cfg = adapt_official_cfg(cfg, num_envs, seed)
    cfg.actions["joint_pos"] = BoundedJointPositionActionCfg(
        **vars(cfg.actions["joint_pos"]), bound_targets=bound_targets
    )
    cfg.metrics.update({
        "requested_target_outside_limits": MetricsTermCfg(func=requested_target_violation_fraction),
        "applied_target_outside_limits": MetricsTermCfg(func=applied_target_violation_fraction),
        "target_clip_fraction": MetricsTermCfg(func=target_clip_fraction),
    })
    for name, func, reduce in (
        ("actuator_saturation_fraction", actuator_saturation_fraction, "mean"),
        ("actuator_saturation_duration", ActuatorSaturationDuration, "max"),
    ):
        cfg.metrics[name] = MetricsTermCfg(
            func=func,
            params={
                "asset_cfg": SceneEntityCfg(
                    "robot", actuator_names=list(cfg.actions["joint_pos"].actuator_names), preserve_order=True
                ),
                "ratio": 0.95,
            },
            reduce=reduce,
        )
    return cfg


__all__ = ["make_sitstand_env_cfg"]
