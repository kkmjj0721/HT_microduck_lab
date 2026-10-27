"""Flat-ground velocity task for the HT-Duck.

Mirrors the structure of mjlab's bundled velocity task (``mjlab.tasks.velocity``)
but is specialised for this robot: a 3.2947 kg quadruped with 12 brushless leg
motors, three servos in the head, and a measured crouched HOME stance.

Differences from the upstream recipe, each with a measured reason:

- Only 10 leg actuators are driven. The head/neck/mouth servos are held at HOME.
- Control runs at 50 Hz (dt 0.002 s, decimation 10) because the 3532 brushless
  motors model a 0-3 step command delay; a 200 Hz policy would fight it.
- No terrain scanner and no height scan: the task is flat ground only, and the
  HT-Duck has no depth sensor, so those terms could never run on hardware.
- The push velocity range is much smaller than upstream's +-0.5 m/s. This robot
  weighs 3.3 kg; the stock range launches it, which would teach the policy to
  brace against impulses it will never see.
- Velocity commands are reduced accordingly (see ``COMMAND_RANGES``).
"""

from __future__ import annotations

import math

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

from ht_microduck.actuators.HD_1910_C001 import bam_init
from ht_microduck.actuators.HTDW_3532_02_DNE import htdw3532_init
from ht_microduck.robots import get_ht_microduck_robot_cfg
from ht_microduck.tasks.common import contract as C
from ht_microduck.tasks.common.mdp import (
    feet_air_time,
    feet_clearance,
    feet_slip,
    illegal_contact,
    self_collision_cost,
    state_is_nan,
    track_angular_velocity,
    track_linear_velocity,
    upright,
)

ROBOT = "robot"
FEET_SENSOR = "feet_ground_contact"
BODY_CONTACT_SENSOR = "body_ground_contact"
SELF_COLLISION_SENSOR = "self_collision"

# Command sampling ranges. Kept conservative for a first policy: forward is the
# priority, lateral and yaw are limited because the stance is narrow (legs are
# 130 mm apart, feet span ~57 mm each).
# Command ranges mirror the official microduck_rl flat task. Forward and lateral
# limits are its values unchanged; yaw is kept inside the official +-1.0 rad/s
# because this robot's stance is narrower and a faster spin stalls the feet.
COMMAND_RANGES = dict(
    lin_vel_x=(-0.4, 0.4),
    lin_vel_y=(-0.3, 0.3),
    ang_vel_z=(-1.0, 1.0),
    heading=(-math.pi, math.pi),
)

# Domain randomisation ranges. These are simulation assumptions, not identified
# values; they bracket what the hardware may plausibly show.
FOOT_FRICTION_RANGE = (0.7, 1.3)
BODY_MASS_RANGE = (-0.1, 0.1)  # kg, added to the base
# Only horizontal linear kicks, as upstream: the stock template's z/roll/pitch/yaw
# pushes are removed because an angular kick on a 3.3 kg robot is unphysical.
PUSH_VELOCITY_RANGE = {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}
PUSH_INTERVAL_S = (3.0, 6.0)

FOOT_GEOM_NAMES = ("r_foot_collision", "l_foot_collision")
FOOT_SITE_NAMES = ("r_foot", "l_foot")

KNEE_JOINT_NAMES = ("r_calf_joint", "l_calf_joint")

# The observation layout covers only the driven joints; including the five held
# servos would add 10 dimensions that never change.
POLICY_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.POLICY_JOINT_NAMES)


def _feet_contact_sensor() -> ContactSensorCfg:
    return ContactSensorCfg(
        name=FEET_SENSOR,
        primary=ContactMatch(mode="geom", pattern=r"[rl]_foot_collision", entity=ROBOT),
        secondary=ContactMatch(mode="geom", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )


def _body_contact_sensor() -> ContactSensorCfg:
    """Torso/hip contacts with the ground. Any hit here is a fall."""
    return ContactSensorCfg(
        name=BODY_CONTACT_SENSOR,
        primary=ContactMatch(
            mode="geom",
            pattern=r"(base_.*|r_hip_yaw|r_hip_roll|l_hip_yaw|l_hip_roll|r_calf|l_calf)_collision",
            entity=ROBOT,
        ),
        secondary=ContactMatch(mode="geom", pattern="terrain"),
        fields=("found",),
        reduce="netforce",
        num_slots=1,
    )


def _self_collision_sensor() -> ContactSensorCfg:
    """Contacts between two parts of the robot itself.

    Both sides must be scoped to the same ``base_link`` subtree. Leaving
    ``secondary=None`` removes the reference filter, so the sensor also reports
    every foot/terrain contact: measured on the HOME stance that gave
    ``found=8`` while simply standing (and ``0`` once the robot was lifted off
    the ground). That silently turned ``self_collisions`` into a large constant
    penalty of about ``-0.109`` per step against roughly ``+0.054`` of tracking
    reward, i.e. it dominated the task reward. The mjlab reference task
    (``velocity/config/go1``) also pairs ``subtree`` with ``subtree``.
    """
    return ContactSensorCfg(
        name=SELF_COLLISION_SENSOR,
        primary=ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT),
        secondary=ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )


def _actor_terms() -> dict[str, ObservationTermCfg]:
    return {
        "base_ang_vel": ObservationTermCfg(
            func=envs_mdp.base_ang_vel,
            noise=Unoise(n_min=-0.2, n_max=0.2),
        ),
        "projected_gravity": ObservationTermCfg(
            func=envs_mdp.projected_gravity,
            noise=Unoise(n_min=-0.05, n_max=0.05),
        ),
        "command": ObservationTermCfg(
            func=envs_mdp.generated_commands,
            params={"command_name": "twist"},
        ),
        "joint_pos": ObservationTermCfg(
            func=envs_mdp.joint_pos_rel,
            params={"biased": True, "asset_cfg": POLICY_JOINTS},
            noise=Unoise(n_min=-0.01, n_max=0.01),
        ),
        "joint_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": POLICY_JOINTS},
            noise=Unoise(n_min=-1.5, n_max=1.5),
        ),
        "actions": ObservationTermCfg(func=envs_mdp.last_action),
    }


def _critic_terms() -> dict[str, ObservationTermCfg]:
    terms = _actor_terms()
    # Privileged: the real robot cannot measure this, the critic only needs it to
    # bootstrap values.
    terms["base_lin_vel"] = ObservationTermCfg(func=envs_mdp.base_lin_vel)
    # The critic also sees the unbiased joint positions and no noise.
    terms["joint_pos"] = ObservationTermCfg(
        func=envs_mdp.joint_pos_rel, params={"asset_cfg": POLICY_JOINTS}
    )
    for term in terms.values():
        term.noise = None
    return terms


def make_flat_velocity_env_cfg(num_envs: int = 4096, seed: int | None = None):
    """Build the flat-ground velocity task configuration."""
    robot_cfg = get_ht_microduck_robot_cfg()
    # The action term drives only the leg actuators; the head stays at HOME.
    robot_cfg.articulation.actuators  # noqa: B018  (documents the object touched)

    rewards = {
        "track_linear_velocity": RewardTermCfg(
            func=track_linear_velocity,
            weight=2.0,
            params={"command_name": "twist", "std": math.sqrt(0.1)},
        ),
        "track_angular_velocity": RewardTermCfg(
            func=track_angular_velocity,
            weight=2.0,
            params={"command_name": "twist", "std": math.sqrt(0.5)},
        ),
        "upright": RewardTermCfg(
            func=upright,
            weight=2.0,
            params={"std": math.sqrt(0.05), "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",))},
        ),
        "dof_pos_limits": RewardTermCfg(func=envs_mdp.joint_pos_limits, weight=-1.0),
        "action_rate_l2": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.1),
        "joint_torques_l2": RewardTermCfg(
            func=envs_mdp.joint_torques_l2, weight=-2e-4
        ),
        "joint_vel_l2": RewardTermCfg(func=envs_mdp.joint_vel_l2, weight=-2e-4),
        "air_time": RewardTermCfg(
            func=feet_air_time,
            weight=3.0,
            params={
                "sensor_name": FEET_SENSOR,
                "threshold_min": 0.125,
                "threshold_max": 0.300,
                "command_name": "twist",
                "command_threshold": 0.01,
            },
        ),
        "foot_clearance": RewardTermCfg(
            func=feet_clearance,
            weight=-2.0,
            params={
                "sensor_name": FEET_SENSOR,
                "target_height": 0.02,
                "command_name": "twist",
                "command_threshold": 0.01,
                "asset_cfg": SceneEntityCfg(ROBOT, site_names=FOOT_SITE_NAMES),
            },
        ),
        "foot_slip": RewardTermCfg(
            func=feet_slip,
            weight=-0.1,
            params={
                "sensor_name": FEET_SENSOR,
                "command_name": "twist",
                "command_threshold": 0.01,
                "asset_cfg": SceneEntityCfg(ROBOT, site_names=FOOT_SITE_NAMES),
            },
        ),
        "self_collisions": RewardTermCfg(
            func=self_collision_cost,
            weight=-1.0,
            params={"sensor_name": SELF_COLLISION_SENSOR},
        ),
    }

    events = {
        # Both actuator families declare per-world native fields; without these
        # startup events the model fields alias across environments and the
        # first control write raises.
        "htdw3532_init": EventTermCfg(func=htdw3532_init, mode="startup"),
        "bam_init": EventTermCfg(func=bam_init, mode="startup"),
        "reset_base": EventTermCfg(
            func=envs_mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-3.14, 3.14)},
                "velocity_range": {},
            },
        ),
        "reset_robot_joints": EventTermCfg(
            func=envs_mdp.reset_joints_by_offset,
            mode="reset",
            params={
                "position_range": (0.0, 0.0),
                "velocity_range": (0.0, 0.0),
                "asset_cfg": SceneEntityCfg(ROBOT, joint_names=(".*",)),
            },
        ),
        "push_robot": EventTermCfg(
            func=envs_mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=PUSH_INTERVAL_S,
            params={"velocity_range": PUSH_VELOCITY_RANGE},
        ),
        "foot_friction": EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg(ROBOT, geom_names=FOOT_GEOM_NAMES),
                "operation": "abs",
                "ranges": FOOT_FRICTION_RANGE,
                "shared_random": True,
            },
        ),
        "encoder_bias": EventTermCfg(
            mode="startup",
            func=dr.encoder_bias,
            params={
                "asset_cfg": SceneEntityCfg(ROBOT),
                "bias_range": (-0.015, 0.015),
            },
        ),
        "base_com": EventTermCfg(
            mode="startup",
            func=dr.body_com_offset,
            params={
                "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",)),
                "operation": "add",
                "ranges": {0: (-0.02, 0.02), 1: (-0.02, 0.02), 2: (-0.02, 0.02)},
            },
        ),
    }

    terminations = {
        "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
        "fell_over": TerminationTermCfg(
            func=envs_mdp.bad_orientation,
            params={"limit_angle": math.radians(70.0)},
        ),
        "illegal_contact": TerminationTermCfg(
            func=illegal_contact,
            params={"sensor_name": BODY_CONTACT_SENSOR},
        ),
        "nan_state": TerminationTermCfg(func=state_is_nan, time_out=False),
    }

    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            num_envs=num_envs,
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={ROBOT: robot_cfg},
            sensors=(
                _feet_contact_sensor(),
                _body_contact_sensor(),
                _self_collision_sensor(),
            ),
            extent=2.0,
        ),
        observations={
            "actor": ObservationGroupCfg(
                terms=_actor_terms(),
                concatenate_terms=True,
                enable_corruption=True,
            ),
            "critic": ObservationGroupCfg(
                terms=_critic_terms(),
                concatenate_terms=True,
                enable_corruption=False,
            ),
        },
        actions={
            "joint_pos": JointPositionActionCfg(
                entity_name=ROBOT,
                actuator_names=tuple(C.POLICY_JOINT_NAMES),
                scale=C.ACTION_SCALE,
                use_default_offset=True,
                preserve_order=True,
            )
        },
        commands={
            "twist": UniformVelocityCommandCfg(
                entity_name=ROBOT,
                resampling_time_range=(4.0, 8.0),
                rel_standing_envs=0.15,
                rel_heading_envs=0.3,
                rel_forward_envs=0.3,
                heading_command=True,
                heading_control_stiffness=0.5,
                debug_vis=False,
                ranges=UniformVelocityCommandCfg.Ranges(**COMMAND_RANGES),
            )
        },
        rewards=rewards,
        terminations=terminations,
        events=events,
        curriculum={},
        metrics={},
        viewer=ViewerConfig(
            origin_type=ViewerConfig.OriginType.ASSET_BODY,
            entity_name=ROBOT,
            body_name="base_link",
            distance=1.5,
            elevation=-5.0,
            azimuth=90.0,
        ),
        sim=SimulationCfg(
            nconmax=128,
            njmax=512,
            mujoco=MujocoCfg(
                timestep=C.PHYSICS_TIMESTEP,
                iterations=10,
                ls_iterations=20,
            ),
        ),
        decimation=C.DECIMATION,
        episode_length_s=C.EPISODE_LENGTH_S,
        seed=seed,
    )
