# Copyright (c) 2026-2027 zh
"""提供平地速度任务与官方头颈变体共用的基础配方。

来源：pollen-robotics/microduck_rl@bae39f5900b318f7e87fc485c30a31213cfa14eb，
src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py（Apache-2.0）。
奖励、命令与课程逐项移植；普通速度入口采用较小动作、HOME 头颈目标和固定动作变化惩罚。
HT 名称、策略关节和执行器生命周期由 official_robot 装配。
"""

import math
from copy import deepcopy

import mjlab.terrains as terrain_gen
import mujoco as _mujoco
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
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.terrains.terrain_generator import TerrainGeneratorCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ht_microduck.robot.ht_microduck_constants import get_ht_microduck_robot_cfg
from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.official_common import (
    make_official_base_env_cfg as make_velocity_env_cfg,
)
from ht_microduck.tasks.mdp import official as microduck_mdp

# ---------- 官方训练参数 ----------

NUM_STEPS_PER_ENV = 24
TURN_IN_PLACE_FRACTION = 0.15
ENABLE_SYMMETRY = False
ENABLE_COM_RANDOMIZATION = True
ENABLE_HEAD_COM_RANDOMIZATION = True
ENABLE_KP_RANDOMIZATION = False
ENABLE_KD_RANDOMIZATION = False
ENABLE_MASS_INERTIA_RANDOMIZATION = True
ENABLE_JOINT_FRICTION_RANDOMIZATION = True
ENABLE_JOINT_DAMPING_RANDOMIZATION = False
ENABLE_ARMATURE_RANDOMIZATION = True
ENABLE_VELOCITY_PUSHES = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True
ENABLE_ENCODER_BIAS = True
ENABLE_BASE_ORIENTATION_RANDOMIZATION = False
HEAD_POSE_CMD_RESAMPLE_S = (2.0, 5.0)
BODY_POSE_CMD_RESAMPLE_S = (2.0, 5.0)
USE_PROJECTED_GRAVITY = True
COM_RANDOMIZATION_RANGE = 0.003
HEAD_COM_RANDOMIZATION_RANGE = 0.003
HEAD_BODY_NAMES = (
    "neck",
    "neck_pitch",
    "yaw_roll_motion",
    "(bottom_head_shell|jaw_soft)",
    "bearing_roll",
)
MASS_INERTIA_RANDOMIZATION_RANGE = (0.95, 1.05)
KP_RANDOMIZATION_RANGE = (0.85, 1.15)
KD_RANDOMIZATION_RANGE = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE = (0.9, 1.1)
JOINT_DAMPING_RANDOMIZATION_RANGE = (0.9, 1.1)
ARMATURE_RANDOMIZATION_RANGE = (0.9, 1.1)
VELOCITY_PUSH_INTERVAL_S = (3.0, 6.0)
VELOCITY_PUSH_RANGE = (-0.3, 0.3)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0
ENCODER_BIAS_RANGE = (-0.015, 0.015)
BASE_ORIENTATION_MAX_PITCH_DEG = 10.0
BASE_ORIENTATION_MAX_ROLL_DEG = 5.0
# ---------- 地形与接触 ----------

MICRODUCK_ROUGH_TERRAINS_CFG = TerrainGeneratorCfg(
    size=(8.0, 8.0),
    border_width=20.0,
    num_rows=10,
    num_cols=20,
    sub_terrains={
        "flat": terrain_gen.BoxFlatTerrainCfg(proportion=0.25),
        "pyramid_stairs": terrain_gen.BoxPyramidStairsTerrainCfg(
            proportion=0.25,
            step_height_range=(0.0, 0.015),
            step_width=0.15,
            platform_width=2.0,
            border_width=1.0,
        ),
        "random_grid": terrain_gen.BoxRandomGridTerrainCfg(
            proportion=0.3,
            grid_width=0.45,
            grid_height_range=(0.0, 0.01),
            platform_width=1.5,
        ),
        "pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.2,
            slope_range=(0.03, 0.1),
            platform_width=2.0,
            vertical_scale=0.001,
        ),
    },
    add_lights=False,
)


def _soften_terrain_contacts(spec: _mujoco.MjSpec) -> None:
    """按官方基准调整粗糙地形接触。"""
    body = spec.body("terrain")
    count = 0
    for geom in body.geoms:
        geom.solref = [0.04, 1.0]
        geom.solimp = [0.85, 0.95, 0.001, 0.5, 2.0]
        count += 1
    print(f"[rough terrain] spec_fn: softened {count} terrain geoms (solref=0.04)")


# ---------- 官方任务装配 ----------

def _make_official_velocity_env_cfg(
    play: bool = False, rough: bool = False
) -> ManagerBasedRlEnvCfg:
    """按官方基准构造任务配置，机器人名字由最终装配适配。"""
    std_standing = {
        ".*hip_yaw.*": 0.1,
        ".*hip_roll.*": 0.05,
        ".*hip_pitch.*": 0.15,
        ".*knee.*": 0.15,
        ".*ankle.*": 0.1,
    }
    std_walking = {
        ".*hip_yaw.*": 0.3,
        ".*hip_roll.*": 0.05,
        ".*hip_pitch.*": 0.4,
        ".*knee.*": 0.4,
        ".*ankle.*": 0.25,
    }
    site_names = ["left_foot", "right_foot"]
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
    foot_height_scan_cfg = TerrainHeightSensorCfg(
        name="foot_height_scan",
        frame=tuple((ObjRef(type="site", name=s, entity="robot") for s in site_names)),
        pattern=RingPatternCfg.single_ring(radius=0.04, num_samples=2),
        ray_alignment="yaw",
        max_distance=1.0,
        exclude_parent_body=True,
        include_geom_groups=(0,),
        debug_vis=False,
    )
    foot_frictions_geom_names = ("left_foot_collision", "right_foot_collision")
    cfg = make_velocity_env_cfg()
    cfg.scene.entities = {"robot": get_ht_microduck_robot_cfg()}
    cfg.scene.sensors = (feet_ground_cfg, self_collision_cfg, foot_height_scan_cfg)
    cfg.viewer.body_name = "trunk_base"
    # ---------- 动作与奖励 ----------
    joint_pos_action = cfg.actions["joint_pos"]
    assert isinstance(joint_pos_action, JointPositionActionCfg)
    joint_pos_action.scale = 1.0
    cfg.rewards["pose"].params["std_standing"] = std_standing
    cfg.rewards["pose"].params["std_walking"] = std_walking
    cfg.rewards["pose"].params["std_running"] = std_walking
    cfg.rewards["pose"].params["asset_cfg"] = SceneEntityCfg(
        "robot", joint_names=("^(?!passive_|.*neck.*|.*head.*).*",)
    )
    cfg.rewards["pose"].params["walking_threshold"] = 0.01
    cfg.rewards["pose"].weight = 1.0
    cfg.rewards["upright"].params["asset_cfg"].body_names = ("trunk_base",)
    cfg.rewards["upright"].weight = 2.0
    cfg.rewards["upright"].params["std"] = math.sqrt(0.05)
    for reward_name in ["foot_clearance", "foot_slip"]:
        cfg.rewards[reward_name].params["asset_cfg"].site_names = site_names
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = ("trunk_base",)
    cfg.rewards["foot_slip"].weight = -0.1
    cfg.rewards["foot_slip"].params["command_threshold"] = 0.01
    cfg.rewards.pop("soft_landing", None)
    cfg.rewards["self_collisions"] = RewardTermCfg(
        func=mdp.self_collision_cost,
        weight=-1.0,
        params={"sensor_name": self_collision_cfg.name},
    )
    cfg.rewards["air_time"].weight = 3.0
    cfg.rewards["air_time"].params["command_threshold"] = 0.01
    cfg.rewards["air_time"].params["threshold_min"] = 0.125
    cfg.rewards["air_time"].params["threshold_max"] = 0.3
    cfg.rewards["body_ang_vel"].weight = -0.05
    cfg.rewards["angular_momentum"].weight = -0.02
    cfg.rewards["track_linear_velocity"].weight = 2.0
    cfg.rewards["track_linear_velocity"].params["std"] = math.sqrt(0.1)
    cfg.rewards["track_angular_velocity"].weight = 2.0
    cfg.rewards["track_angular_velocity"].params["std"] = math.sqrt(0.5)
    cfg.rewards["action_rate_l2"].weight = -0.1
    cfg.rewards["foot_clearance"].params["command_threshold"] = 0.01
    cfg.rewards["foot_clearance"].params["target_height"] = 0.02
    cfg.rewards["foot_swing_height"].params["command_threshold"] = 0.01
    cfg.rewards["foot_swing_height"].params["target_height"] = 0.02
    # ---------- 重置、扰动与域随机化 ----------
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
    cfg.terminations["nan_state"] = TerminationTermCfg(
        func=microduck_mdp.robot_state_is_nan,
        time_out=False,
        params={"sensor_names": (feet_ground_cfg.name,)},
    )
    cfg.events["reset_base"].params["pose_range"]["z"] = (0.12, 0.13)
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
    if ENABLE_JOINT_DAMPING_RANDOMIZATION:
        cfg.events["randomize_joint_damping"] = EventTermCfg(
            func=microduck_mdp.randomize_dof_field_scaled,
            mode="reset",
            domain_randomization=True,
            params={
                "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",)),
                "field": "dof_damping",
                "scale_range": JOINT_DAMPING_RANDOMIZATION_RANGE,
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
    if ENABLE_BASE_ORIENTATION_RANDOMIZATION:
        cfg.events["randomize_base_orientation"] = EventTermCfg(
            func=microduck_mdp.randomize_base_orientation,
            mode="reset",
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "max_pitch_deg": BASE_ORIENTATION_MAX_PITCH_DEG,
                "max_roll_deg": BASE_ORIENTATION_MAX_ROLL_DEG,
            },
        )
    # ---------- 观测、延迟与传感器误差 ----------
    del cfg.observations["actor"].terms["base_lin_vel"]
    del cfg.observations["actor"].terms["height_scan"]
    del cfg.observations["critic"].terms["height_scan"]
    cfg.observations["critic"].terms["base_lin_vel"] = ObservationTermCfg(
        func=mdp.base_lin_vel, scale=1.0
    )
    gravity_term_name = (
        "projected_gravity" if USE_PROJECTED_GRAVITY else "raw_accelerometer"
    )
    if not USE_PROJECTED_GRAVITY:
        del cfg.observations["actor"].terms["projected_gravity"]
        cfg.observations["actor"].terms["raw_accelerometer"] = ObservationTermCfg(
            func=microduck_mdp.raw_accelerometer, scale=1.0
        )
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
    for _term, _safe in (
        ("foot_contact_forces", microduck_mdp.foot_contact_forces_safe),
        ("foot_height", microduck_mdp.foot_height_safe),
        ("foot_air_time", microduck_mdp.foot_air_time_safe),
    ):
        if _term in cfg.observations["critic"].terms:
            cfg.observations["critic"].terms[_term].func = _safe
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
        if USE_PROJECTED_GRAVITY:
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
    # ---------- 速度、头部和躯干命令 ----------
    command: UniformVelocityCommandCfg = deepcopy(cfg.commands["twist"])
    cfg.commands["twist"] = command
    command.rel_standing_envs = 0.02
    command.rel_heading_envs = 0.0
    command.ranges.lin_vel_x = (-0.4, 0.4)
    command.ranges.lin_vel_y = (-0.3, 0.3)
    command.ranges.ang_vel_z = (-1.0, 1.0)
    command.viz.z_offset = 0.5
    cfg.commands["twist"] = microduck_mdp.VelocityCommandCommandOnlyCfg(**vars(command))
    cfg.commands["twist"].rel_turn_in_place_envs = TURN_IN_PLACE_FRACTION
    cfg.commands["head_pose"] = microduck_mdp.UniformPoseCommandCfg(
        resampling_time_range=HEAD_POSE_CMD_RESAMPLE_S,
        ranges=((-0.05, 0.05), (-0.05, 0.05), (-0.07, 0.07), (-0.015, 0.015)),
    )
    cfg.commands["body_pose"] = microduck_mdp.UniformPoseCommandCfg(
        resampling_time_range=BODY_POSE_CMD_RESAMPLE_S,
        ranges=(
            (-0.005, 0.005),
            (-0.005, 0.005),
            (-0.005, 0.005),
            (-0.05, 0.05),
            (-0.05, 0.05),
            (-0.05, 0.05),
        ),
    )
    for group in ("actor", "critic"):
        cfg.observations[group].terms["head_command"] = ObservationTermCfg(
            func=mdp.generated_commands, params={"command_name": "head_pose"}
        )
        cfg.observations[group].terms["body_command"] = ObservationTermCfg(
            func=mdp.generated_commands, params={"command_name": "body_pose"}
        )
    cfg.rewards["head_pose_tracking"] = RewardTermCfg(
        func=microduck_mdp.head_pose_tracking,
        weight=2.0,
        params={"command_name": "head_pose", "std": 0.5},
    )
    cfg.rewards["body_pose_tracking"] = RewardTermCfg(
        func=microduck_mdp.body_pose_tracking_6d,
        weight=0.0,
        params={
            "command_name": "body_pose",
            "nominal_height": 0.095,
            "xy_std": 0.05,
            "z_std": 0.02,
            "angle_std": math.radians(15),
        },
    )
    cfg.rewards["head_pose_bias"] = RewardTermCfg(
        func=microduck_mdp.head_pose_bias_penalty,
        weight=0.0,
        params={"command_name": "head_pose", "tau_s": 1.0},
    )
    if not rough:
        cfg.scene.terrain.terrain_type = "plane"
        cfg.scene.terrain.terrain_generator = None
    else:
        cfg.scene.terrain.terrain_type = "generator"
        cfg.scene.terrain.terrain_generator = MICRODUCK_ROUGH_TERRAINS_CFG
        cfg.scene.spec_fn = _soften_terrain_contacts
        cfg.sim.nconmax = 200
        cfg.sim.mujoco.iterations = 30
        cfg.sim.mujoco.ls_iterations = 50
        if play:
            cfg.scene.terrain.terrain_generator.curriculum = False
            cfg.scene.terrain.terrain_generator.num_cols = 5
            cfg.scene.terrain.terrain_generator.num_rows = 5
    # ---------- 官方课程 ----------
    cfg.curriculum["action_rate_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "action_rate_l2",
            "weight_stages": [
                {"step": 0, "weight": -0.1},
                {"step": 500 * NUM_STEPS_PER_ENV, "weight": -0.2},
                {"step": 750 * NUM_STEPS_PER_ENV, "weight": -0.4},
                {"step": 1000 * NUM_STEPS_PER_ENV, "weight": -0.6},
                {"step": 1250 * NUM_STEPS_PER_ENV, "weight": -0.8},
                {"step": 1500 * NUM_STEPS_PER_ENV, "weight": -1.0},
            ],
        },
    )
    cfg.curriculum["standing_envs"] = CurriculumTermCfg(
        func=microduck_mdp.standing_envs_curriculum,
        params={
            "command_name": "twist",
            "standing_stages": [
                {"step": 0, "rel_standing_envs": 0.02},
                {"step": 500 * 24, "rel_standing_envs": 0.05},
                {"step": 750 * 24, "rel_standing_envs": 0.1},
                {"step": 1000 * 24, "rel_standing_envs": 0.15},
                {"step": 1500 * 24, "rel_standing_envs": 0.2},
                {"step": 2000 * 24, "rel_standing_envs": 0.25},
            ],
        },
    )
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
    cfg.curriculum["body_pose_range"] = CurriculumTermCfg(
        func=microduck_mdp.pose_command_range_curriculum,
        params={
            "command_name": "body_pose",
            "range_stages": [
                {
                    "step": 0,
                    "ranges": (
                        (-0.005, 0.005),
                        (-0.005, 0.005),
                        (-0.005, 0.005),
                        (-0.05, 0.05),
                        (-0.05, 0.05),
                        (-0.05, 0.05),
                    ),
                }
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
    if not rough:
        del cfg.curriculum["terrain_levels"]
    del cfg.curriculum["command_vel"]
    cfg.curriculum["head_pose_bias_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "head_pose_bias",
            "weight_stages": [
                {"step": 0, "weight": 0.0},
                {"step": 600 * NUM_STEPS_PER_ENV, "weight": 1.0},
                {"step": 1000 * NUM_STEPS_PER_ENV, "weight": 2.0},
                {"step": 1500 * NUM_STEPS_PER_ENV, "weight": 3.0},
            ],
        },
    )
    return cfg


# ---------- 本项目入口与受保护任务的常量接口 ----------

COMMAND_RANGES = dict(
    lin_vel_x=(-0.4, 0.4),
    lin_vel_y=(-0.3, 0.3),
    ang_vel_z=(-1.0, 1.0),
    heading=(-math.pi, math.pi),
)
FOOT_HEIGHT_SENSOR = "foot_height_scan"
HEAD_POSE_RANGES_FULL = ((-1.1, 1.1), (-1.1, 1.1), (-1.4, 1.4), (-0.31, 0.31))


def make_flat_velocity_env_cfg(
    num_envs: int = 4096, seed: int | None = None, play: bool = False
):
    """装配 HT 平地速度任务，保留当前观测、物理时序与执行器延迟。"""
    from ht_microduck.tasks.config.ht_microduck.official_robot import adapt_official_cfg

    cfg = _make_official_velocity_env_cfg(play=play, rough=False)
    cfg.actions["joint_pos"].scale = C.WALKING_ACTION_SCALE
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.rewards["action_rate_l2"].weight = -0.1
    # 保留四维头颈观测槽位；移除课程，避免后期重置重新扩大目标或加重动作惩罚。
    del cfg.curriculum["head_pose_range"]
    del cfg.curriculum["action_rate_weight"]
    return adapt_official_cfg(cfg, num_envs, seed)
