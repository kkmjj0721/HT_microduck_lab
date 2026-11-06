# Copyright (c) 2026-2027 zh
"""HT 任务共用的关节选择、观测噪声与接触传感器配置。

actor_terms 和 critic_terms 构造 VelStand 的观测；官方任务独立构造其观测项。
"""

from __future__ import annotations

from mjlab.envs import mdp as envs_mdp
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ht_microduck.tasks import ht_microduck_contract as C

ROBOT = "robot"
FEET_SENSOR = "feet_ground_contact"
BODY_CONTACT_SENSOR = "body_ground_contact"
SELF_COLLISION_SENSOR = "self_collision"

FOOT_GEOM_NAMES = ("r_foot_collision", "l_foot_collision")
FOOT_SITE_NAMES = ("r_foot", "l_foot")

# Joint subsets as resolved names, so reward terms never hard-code an index.
POLICY_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.POLICY_JOINT_NAMES)
HEAD_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.HEAD_JOINT_NAMES)

# Observation noise, matched to upstream microduck_rl. These are the ranges a real
# sensor suite shows; the previous numbers here were 7-11x wider, which trained a
# policy that distrusted its own encoders.
NOISE_ANG_VEL = Unoise(n_min=-0.03, n_max=0.03)
NOISE_GRAVITY = Unoise(n_min=-0.01, n_max=0.01)
NOISE_JOINT_POS = Unoise(n_min=-0.001, n_max=0.001)
NOISE_JOINT_VEL = Unoise(n_min=-0.25, n_max=0.25)


def actor_terms(
    head_command: str | ObservationTermCfg = "head_pose",
    body_command: str | ObservationTermCfg = "body_pose",
) -> dict[str, ObservationTermCfg]:
    """按冻结契约构造 actor 观测，命令槽位接受命令名或已构造的观测项。"""
    return {
        "base_ang_vel": ObservationTermCfg(
            func=envs_mdp.base_ang_vel,
            noise=NOISE_ANG_VEL,
        ),
        "projected_gravity": ObservationTermCfg(
            func=envs_mdp.projected_gravity,
            noise=NOISE_GRAVITY,
        ),
        "joint_pos": ObservationTermCfg(
            func=envs_mdp.joint_pos_rel,
            params={"biased": True, "asset_cfg": POLICY_JOINTS},
            noise=NOISE_JOINT_POS,
        ),
        "joint_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": POLICY_JOINTS},
            noise=NOISE_JOINT_VEL,
        ),
        "actions": ObservationTermCfg(func=envs_mdp.last_action),
        "command": ObservationTermCfg(
            func=envs_mdp.generated_commands,
            params={"command_name": "twist"},
        ),
        "head_command": _resolve(head_command),
        "body_command": _resolve(body_command),
    }


def _resolve(slot: str | ObservationTermCfg) -> ObservationTermCfg:
    if isinstance(slot, ObservationTermCfg):
        return slot
    return ObservationTermCfg(
        func=envs_mdp.generated_commands,
        params={"command_name": slot},
    )


def critic_terms(
    head_command: str | ObservationTermCfg = "head_pose",
    body_command: str | ObservationTermCfg = "body_pose",
) -> dict[str, ObservationTermCfg]:
    """The critic group: the actor terms plus privileged quantities, noise-free."""
    terms = actor_terms(head_command, body_command)
    terms["base_lin_vel"] = ObservationTermCfg(func=envs_mdp.base_lin_vel)
    # The critic also sees unbiased joint positions.
    terms["joint_pos"] = ObservationTermCfg(
        func=envs_mdp.joint_pos_rel, params={"asset_cfg": POLICY_JOINTS}
    )
    for term in terms.values():
        term.noise = None
    return terms


def feet_contact_sensor() -> ContactSensorCfg:
    return ContactSensorCfg(
        name=FEET_SENSOR,
        primary=ContactMatch(mode="geom", pattern=r"[rl]_foot_collision", entity=ROBOT),
        secondary=ContactMatch(mode="geom", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )


def body_contact_sensor() -> ContactSensorCfg:
    """Torso and hip contacts with the ground; any hit here is a fall.

    Used for the impact costs, not as a termination: a robot that is getting up
    from its side has to be allowed to touch the ground with its body, otherwise
    the recovery can never happen.
    """
    return ContactSensorCfg(
        name=BODY_CONTACT_SENSOR,
        primary=ContactMatch(
            mode="geom",
            pattern=(
                r"(base_.*|r_hip_yaw|r_hip_roll|l_hip_yaw|l_hip_roll|r_calf|l_calf)"
                r"_collision"
            ),
            entity=ROBOT,
        ),
        secondary=ContactMatch(mode="geom", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )


def head_contact_sensor() -> ContactSensorCfg:
    """Head contacts with the ground, for the head impact cost."""
    return ContactSensorCfg(
        name="head_ground_contact",
        primary=ContactMatch(
            mode="geom",
            pattern=r"(head_collision|mouth_collision)",
            entity=ROBOT,
        ),
        secondary=ContactMatch(mode="geom", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )


def self_collision_sensor() -> ContactSensorCfg:
    """Contacts between two parts of the robot itself.

    Both sides must be scoped to the same ``base_link`` subtree. Leaving
    ``secondary=None`` removes the reference filter, so the sensor also reports
    every foot/terrain contact: measured on the HOME stance that gave
    ``found=8`` while simply standing (and ``0`` once the robot was lifted off the
    ground). That silently turned ``self_collisions`` into a large constant
    penalty of about ``-0.109`` per step against roughly ``+0.054`` of tracking
    reward, i.e. it dominated the task reward.
    """
    return ContactSensorCfg(
        name=SELF_COLLISION_SENSOR,
        primary=ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT),
        secondary=ContactMatch(mode="subtree", pattern="base_link", entity=ROBOT),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )
