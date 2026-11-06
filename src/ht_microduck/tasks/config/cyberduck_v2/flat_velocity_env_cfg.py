# Copyright (c) 2026-2027 zh
"""
内容：
    定义 CyberDuck V2 的平地机身速度跟踪环境与混合位置、速度动作。

本配置只复用机器人、执行器及 mjlab 通用接口，不依赖旧 HT 任务的姿态或契约。
奖励、命令范围和终止阈值均为首版仿真假设，需另行训练与行为验收。
"""

import math
from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg, mdp
from mjlab.envs.mdp.actions import JointVelocityActionCfg
from mjlab.managers import (
    EventTermCfg,
    MetricsTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.terrains import TerrainEntityCfg
from mjlab.viewer import ViewerConfig

from ht_microduck.actuator import bam_init, htdw3532_init
from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    get_cyberduck_v2_robot_cfg,
)
from ht_microduck.tasks import cyberduck_v2_contract as C
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg
from ht_microduck.tasks.mdp.cyberduck_commands import RollingVelocityCommandCfg
from ht_microduck.tasks.mdp.cyberduck_events import reset_control_targets
from ht_microduck.tasks.mdp.cyberduck_metrics import WheelDriveMetric
from ht_microduck.tasks.mdp.cyberduck_observations import wheel_contact
from ht_microduck.tasks.mdp.cyberduck_rewards import (
    JointTargetRateL2,
    height_band_l2,
    nonwheel_ground_contact,
    position_deviation_l2,
    tilt_band_l2,
    track_planar_velocity_exp,
    track_yaw_velocity_exp,
    zero_command_motion,
)
from ht_microduck.tasks.mdp.cyberduck_terminations import contact_failure


def make_flat_velocity_env_cfg(
    *, num_envs: int = 512, seed: int | None = None, play: bool = False
) -> ManagerBasedRlEnvCfg:
    """构造独立配置；play 保持同一物理和动作语义，命令支持查看器交互。"""
    if num_envs < 1:
        raise ValueError("CyberDuck V2 num_envs must be positive")
    position_joints = SceneEntityCfg(
        "robot", joint_names=C.POLICY_POSITION_JOINT_NAMES, preserve_order=True
    )
    position_state_joints = SceneEntityCfg(
        "robot", joint_names=C.OBSERVATION_POSITION_JOINT_NAMES, preserve_order=True
    )
    velocity_state_joints = SceneEntityCfg(
        "robot", joint_names=C.OBSERVATION_VELOCITY_JOINT_NAMES, preserve_order=True
    )
    actor_terms = {
        "base_ang_vel": ObservationTermCfg(func=mdp.base_ang_vel),
        "projected_gravity": ObservationTermCfg(func=mdp.projected_gravity),
        "joint_pos": ObservationTermCfg(
            func=mdp.joint_pos_rel, params={"asset_cfg": position_state_joints}
        ),
        "joint_vel": ObservationTermCfg(
            func=mdp.joint_vel_rel, params={"asset_cfg": velocity_state_joints}
        ),
        "actions": ObservationTermCfg(func=mdp.last_action),
        "command": ObservationTermCfg(
            func=mdp.generated_commands, params={"command_name": "twist"}
        ),
    }
    critic_terms = {
        **deepcopy(actor_terms),
        "base_lin_vel": ObservationTermCfg(func=mdp.base_lin_vel),
        "wheel_contact": ObservationTermCfg(
            func=wheel_contact, params={"sensor_name": C.WHEEL_CONTACT_SENSOR_NAME}
        ),
    }

    # ---------- 场景、观测与动作 ----------
    sensors = (
        ContactSensorCfg(
            name=C.WHEEL_ROLLING_SENSOR_NAME,
            primary=ContactMatch(mode="geom", pattern=C.WHEEL_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found", "force", "pos", "normal", "tangent"),
            reduce="maxforce",
            num_slots=1,
            global_frame=True,
        ),
        ContactSensorCfg(
            name=C.WHEEL_CONTACT_SENSOR_NAME,
            primary=ContactMatch(mode="geom", pattern=C.WHEEL_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found", "force"),
            reduce="netforce",
            num_slots=1,
        ),
        ContactSensorCfg(
            name=C.BODY_CONTACT_SENSOR_NAME,
            primary=ContactMatch(mode="geom", pattern=("base_front_collision", "base_rear_collision"), entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found",),
            reduce="none",
            num_slots=1,
        ),
        ContactSensorCfg(
            name=C.SELF_CONTACT_SENSOR_NAME,
            primary=ContactMatch(mode="geom", pattern=COLLISION_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
            fields=("found",),
            reduce="none",
            num_slots=1,
        ),
        ContactSensorCfg(
            name=C.NONWHEEL_CONTACT_SENSOR_NAME,
            primary=ContactMatch(
                mode="geom",
                pattern=tuple(name for name in COLLISION_GEOM_NAMES if name not in C.WHEEL_GEOM_NAMES),
                entity="robot",
            ),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found",),
            reduce="none",
            num_slots=1,
        ),
    )
    cfg = ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            num_envs=num_envs,
            env_spacing=2.0,
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={"robot": get_cyberduck_v2_robot_cfg()},
            sensors=sensors,
        ),
        sim=SimulationCfg(
            mujoco=MujocoCfg(timestep=C.PHYSICS_TIMESTEP), nconmax=128, njmax=512
        ),
        decimation=C.DECIMATION,
        episode_length_s=C.EPISODE_LENGTH_S,
        seed=seed,
        viewer=ViewerConfig(entity_name="robot", body_name="base_link", distance=1.2),
        observations={
            "actor": ObservationGroupCfg(
                terms=actor_terms, enable_corruption=False,
                history_length=C.ACTOR_HISTORY_LENGTH, flatten_history_dim=True,
            ),
            "critic": ObservationGroupCfg(terms=critic_terms, enable_corruption=False),
        },
        actions={
            "joint_pos": BoundedJointPositionActionCfg(
                entity_name="robot",
                actuator_names=C.POLICY_POSITION_JOINT_NAMES,
                preserve_order=True,
                scale=C.POSITION_ACTION_SCALE,
                use_default_offset=True,
            ),
            "joint_vel": JointVelocityActionCfg(
                entity_name="robot",
                actuator_names=C.POLICY_VELOCITY_JOINT_NAMES,
                preserve_order=True,
                scale=C.VELOCITY_ACTION_SCALE,
                use_default_offset=True,
                clip={".*": (-C.VELOCITY_TARGET_LIMIT, C.VELOCITY_TARGET_LIMIT)},
            ),
        },
        # ---------- 初始化、重置与命令 ----------
        events={
            "htdw3532_init": EventTermCfg(func=htdw3532_init, mode="startup"),
            "bam_init": EventTermCfg(func=bam_init, mode="startup"),
            "reset_scene": EventTermCfg(func=mdp.reset_scene_to_default, mode="reset"),
            "reset_control_targets": EventTermCfg(func=reset_control_targets, mode="reset"),
        },
        commands={
            "twist": RollingVelocityCommandCfg(
                entity_name="robot",
                resampling_time_range=(3.0, 8.0),
                rel_standing_envs=0.2,
                rel_heading_envs=0.0,
                heading_command=False,
                debug_vis=play,
                max_acceleration=C.COMMAND_MAX_ACCELERATION,
                ranges=RollingVelocityCommandCfg.Ranges(
                    lin_vel_x=(-C.COMMAND_LINEAR_LIMIT, C.COMMAND_LINEAR_LIMIT),
                    lin_vel_y=(0.0, 0.0),
                    ang_vel_z=(-C.COMMAND_YAW_LIMIT, C.COMMAND_YAW_LIMIT),
                ),
            )
        },
        # ---------- 主动轮行奖励、诊断与终止 ----------
        # 速度跟踪为主任务，辅助项不对累计踝角或滚轮转速提供静止目标。
        rewards={
            "track_linear_velocity": RewardTermCfg(
                func=track_planar_velocity_exp, weight=2.0,
                params={"command_name": "twist", "std": 0.05},
            ),
            "track_angular_velocity": RewardTermCfg(
                func=track_yaw_velocity_exp, weight=1.0,
                params={"command_name": "twist", "std": 0.15},
            ),
            "stop_motion": RewardTermCfg(
                func=zero_command_motion, weight=-0.5,
                params={"command_name": "twist", "linear_scale": 0.1, "angular_scale": 0.3},
            ),
            "height": RewardTermCfg(
                func=height_band_l2, weight=-0.3,
                params={"target_height": C.SUPPORT_HEIGHT, "tolerance": C.HEIGHT_TOLERANCE, "scale": 0.05},
            ),
            "upright": RewardTermCfg(
                func=tilt_band_l2, weight=-0.3,
                params={"tolerance": C.TILT_TOLERANCE, "scale": math.radians(20.0)},
            ),
            "pose": RewardTermCfg(
                func=position_deviation_l2, weight=-0.2,
                params={"asset_cfg": deepcopy(position_joints)},
            ),
            "nonwheel_ground_contact": RewardTermCfg(
                func=nonwheel_ground_contact, weight=-1.0,
                params={"sensor_name": C.NONWHEEL_CONTACT_SENSOR_NAME},
            ),
            "joint_torques": RewardTermCfg(func=mdp.joint_torques_l2, weight=-1.0e-4),
            "position_target_rate": RewardTermCfg(
                func=JointTargetRateL2, weight=-0.02,
                params={"asset_cfg": deepcopy(position_joints), "target_type": "position", "scale": C.POSITION_ACTION_SCALE},
            ),
            "velocity_target_rate": RewardTermCfg(
                func=JointTargetRateL2, weight=-0.02,
                params={
                    "asset_cfg": SceneEntityCfg("robot", joint_names=C.POLICY_VELOCITY_JOINT_NAMES, preserve_order=True),
                    "target_type": "velocity", "scale": C.VELOCITY_ACTION_SCALE,
                },
            ),
            # RewardManager 会乘控制 dt；此权重使非超时失败实际扣除 2 分。
            "termination": RewardTermCfg(func=mdp.is_terminated, weight=-2.0 * C.CONTROL_HZ),
        },
        metrics={
            "wheel_slip_speed_m_s": MetricsTermCfg(func=WheelDriveMetric, params={"field": "wheel_slip_speed_m_s"}),
            "wheel_normal_load_n": MetricsTermCfg(func=WheelDriveMetric, params={"field": "wheel_normal_load_n"}),
            "actuator_saturation_fraction": MetricsTermCfg(func=WheelDriveMetric, params={"field": "actuator_saturation"}),
            "belt_velocity_error_rad_s": MetricsTermCfg(func=WheelDriveMetric, params={"field": "mimic_velocity_abs_error_rad_s"}),
        },
        terminations={
            "time_out": TerminationTermCfg(func=mdp.time_out, time_out=True),
            "bad_orientation": TerminationTermCfg(
                func=mdp.bad_orientation,
                params={"limit_angle": math.radians(60.0)},
            ),
            "root_height": TerminationTermCfg(
                func=mdp.root_height_below_minimum,
                params={"minimum_height": 0.15},
            ),
            "nan_state": TerminationTermCfg(func=mdp.nan_detection),
            "body_ground_contact": TerminationTermCfg(
                func=contact_failure, params={"sensor_name": C.BODY_CONTACT_SENSOR_NAME},
            ),
            "self_collision": TerminationTermCfg(
                func=contact_failure, params={"sensor_name": C.SELF_CONTACT_SENSOR_NAME},
            ),
        },
    )
    return cfg
