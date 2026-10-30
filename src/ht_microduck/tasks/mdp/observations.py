"""Observation, command and sensor plumbing shared by every HT-Duck task.

All walking and posture tasks must present the same
actor vector, in the same order. Runtime policy selection must also apply the
task-specific action scale. Keeping term construction here enforces layout: a task
adds *values* to a slot, never a new slot.

The three command slots are ``twist`` (3), ``head_pose`` (4) and ``body_pose`` (6).
A task that does not use a slot still declares it and fills it with zeros, which
is why :func:`zero_command_padding` exists rather than the terms being omitted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.envs import mdp as envs_mdp
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ht_microduck.tasks import contract as C

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

ROBOT = "robot"
FEET_SENSOR = "feet_ground_contact"
BODY_CONTACT_SENSOR = "body_ground_contact"
SELF_COLLISION_SENSOR = "self_collision"

FOOT_GEOM_NAMES = ("r_foot_collision", "l_foot_collision")
FOOT_SITE_NAMES = ("r_foot", "l_foot")

# Joint subsets as resolved names, so reward terms never hard-code an index.
POLICY_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.POLICY_JOINT_NAMES)
LEG_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.LEG_JOINT_NAMES)
HEAD_JOINTS = SceneEntityCfg(ROBOT, joint_names=C.HEAD_JOINT_NAMES)

# Observation noise, matched to upstream microduck_rl. These are the ranges a real
# sensor suite shows; the previous numbers here were 7-11x wider, which trained a
# policy that distrusted its own encoders.
NOISE_ANG_VEL = Unoise(n_min=-0.03, n_max=0.03)
NOISE_GRAVITY = Unoise(n_min=-0.01, n_max=0.01)
NOISE_JOINT_POS = Unoise(n_min=-0.001, n_max=0.001)
NOISE_JOINT_VEL = Unoise(n_min=-0.25, n_max=0.25)


def zero_command_padding(dim: int) -> ObservationTermCfg:
    """A command slot a task does not drive: always zeros, never omitted.

    The declared width is recorded on the returned config so the import-time guard can
    check it against ``contract.ACTOR_OBSERVATION_DIMS``: a padded slot is exactly the
    place where a wrong width slips through silently, because nothing else reads it.
    """

    def _zeros(env: ManagerBasedRlEnv) -> torch.Tensor:
        return torch.zeros(env.num_envs, dim, device=env.device)

    _zeros.__name__ = f"zero_command_{dim}"
    term = ObservationTermCfg(func=_zeros)
    # Recorded on the term object, not in ``params``: params are forwarded to the
    # function as keyword arguments, so a bookkeeping key there would be passed through
    # and raise. The guard in ``tasks/__init__.py`` reads this attribute.
    term.padding_dim = dim
    return term


def actor_terms(
    head_command: str | ObservationTermCfg = "head_pose",
    body_command: str | ObservationTermCfg = "body_pose",
) -> dict[str, ObservationTermCfg]:
    """The actor observation group, in contract order.

    ``head_command`` and ``body_command`` accept either a command name (the slot is
    driven by that command term) or a pre-built term (a task passes
    :func:`zero_command_padding` when it does not use the slot).
    """
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
        "head_command": _resolve(head_command, dim=4),
        "body_command": _resolve(body_command, dim=6),
    }


def assert_actor_dim(env, group: str = "actor") -> None:
    """Fail loudly if a task's actor vector drifts from the frozen width.

    The width is not a style preference: an exported ONNX file has it baked into its
    first layer, and the runtime swaps policies by shape. A task that commands a
    narrower slot — easy to introduce by passing a 1-D ``ranges`` tuple to a command
    term — silently produces a shorter vector, which this catches at construction
    instead of at deployment. (It happened once: a 1-wide twist slot yielded 59-D.)
    """
    dims = env.observation_manager.group_obs_dim[group]
    width = dims[0] if isinstance(dims[0], int) else sum(dims[0])
    if width != C.ACTOR_OBSERVATION_DIM:
        raise ValueError(
            f"{group} observation is {width}-D but the contract fixes "
            f"{C.ACTOR_OBSERVATION_DIM}-D; check the command slot widths"
        )


def _resolve(slot: str | ObservationTermCfg, dim: int) -> ObservationTermCfg:
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
