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
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity.mdp import (
    UniformVelocityCommandCfg,
    track_angular_velocity,
    track_linear_velocity,
)
from mjlab.terrains import TerrainEntityCfg
from mjlab.viewer import ViewerConfig

from ht_microduck.actuator import bam_init, htdw3532_init
from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    get_cyberduck_v2_robot_cfg,
)
from ht_microduck.tasks import cyberduck_v2_contract as C
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg
from ht_microduck.tasks.mdp.cyberduck_events import reset_control_targets
from ht_microduck.tasks.mdp.cyberduck_observations import wheel_contact
from ht_microduck.tasks.mdp.cyberduck_rewards import (
    nonwheel_ground_contact,
    position_deviation_l2,
)


def make_flat_velocity_env_cfg(
    *, num_envs: int = 512, seed: int | None = None, play: bool = False
) -> ManagerBasedRlEnvCfg:
    """构造独立配置；play 保持同一物理和动作语义，命令支持查看器交互。"""
    if num_envs < 1:
        raise ValueError("CyberDuck V2 num_envs must be positive")
    position_joints = SceneEntityCfg(
        "robot", joint_names=C.POLICY_POSITION_JOINT_NAMES, preserve_order=True
    )
    policy_joints = SceneEntityCfg(
        "robot", joint_names=C.POLICY_JOINT_NAMES, preserve_order=True
    )
    actor_terms = {
        "base_ang_vel": ObservationTermCfg(func=mdp.base_ang_vel),
        "projected_gravity": ObservationTermCfg(func=mdp.projected_gravity),
        "joint_pos": ObservationTermCfg(
            func=mdp.joint_pos_rel, params={"asset_cfg": position_joints}
        ),
        "joint_vel": ObservationTermCfg(
            func=mdp.joint_vel_rel, params={"asset_cfg": policy_joints}
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
            name=C.WHEEL_CONTACT_SENSOR_NAME,
            primary=ContactMatch(mode="geom", pattern=C.WHEEL_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found", "force"),
            reduce="netforce",
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
            "actor": ObservationGroupCfg(terms=actor_terms, enable_corruption=False),
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
            "twist": UniformVelocityCommandCfg(
                entity_name="robot",
                resampling_time_range=(3.0, 8.0),
                rel_standing_envs=0.2,
                rel_heading_envs=0.0,
                heading_command=False,
                debug_vis=play,
                ranges=UniformVelocityCommandCfg.Ranges(
                    lin_vel_x=(-0.1, 0.1),
                    lin_vel_y=(0.0, 0.0),
                    ang_vel_z=(-0.3, 0.3),
                ),
            )
        },
        # ---------- 初版奖励与终止 ----------
        # 速度跟踪为主任务，辅助项不对累计踝角或滚轮转速提供静止目标。
        rewards={
            "track_linear_velocity": RewardTermCfg(
                func=track_linear_velocity, weight=2.0,
                params={"command_name": "twist", "std": 0.1},
            ),
            "track_angular_velocity": RewardTermCfg(
                func=track_angular_velocity, weight=1.0,
                params={"command_name": "twist", "std": 0.3},
            ),
            "upright": RewardTermCfg(func=mdp.flat_orientation_l2, weight=-0.5),
            "pose": RewardTermCfg(
                func=position_deviation_l2, weight=-0.2,
                params={"asset_cfg": deepcopy(position_joints)},
            ),
            "nonwheel_ground_contact": RewardTermCfg(
                func=nonwheel_ground_contact, weight=-1.0,
                params={"sensor_name": C.NONWHEEL_CONTACT_SENSOR_NAME},
            ),
            "joint_torques": RewardTermCfg(func=mdp.joint_torques_l2, weight=-1.0e-4),
            "action_rate": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01),
            "termination": RewardTermCfg(func=mdp.is_terminated, weight=-2.0),
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
        },
    )
    return cfg
