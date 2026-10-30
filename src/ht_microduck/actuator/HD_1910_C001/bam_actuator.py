# Portions adapted from BAM, Copyright 2025 Marc Duclusaud & Grégoire Passault.
# Licensed under Apache-2.0; see NOTICE and THIRD_PARTY_LICENSE in this directory.
"""HD1910 M6 actuator for mjlab 1.6, with native solver friction.

This implements the manufacturer's voltage/P-position model, not a measured
replica of every HD1910 firmware mode. Velocity and effort targets are unused.
The fitted rig offset and delay are metadata; command delay is configured in
physics steps through ActuatorCfg and applied once by mjlab's Entity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import mujoco
import torch
from mjlab.actuator.actuator import (
    Actuator,
    ActuatorCfg,
    ActuatorCmd,
    TransmissionType,
)
from mjlab.managers.event_manager import requires_model_fields
from mjlab.utils.spec import create_motor_actuator

from .model import (
    compute_friction_budget,
    compute_motor_torque,
    load_hd1910_parameters,
)

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.sim.sim import DataBridge, ModelBridge


@requires_model_fields("dof_frictionloss", "dof_damping")
def bam_init(env, env_ids=None) -> None:
    """Register as a startup event to allocate independent friction per world.

    A standalone Scene/Simulation may instead call
    ``sim.expand_model_fields(("dof_frictionloss", "dof_damping"))`` before
    writing controls. This no-op event declares the fields to mjlab's manager.
    """
    del env, env_ids


@dataclass(kw_only=True)
class HD1910BamActuatorCfg(ActuatorCfg):
    """Position-controlled HD1910, using the bundled factory 7.4 V M6 fit.

    ``kp_fw=32`` is the manufacturer's firmware-model assumption, not an SI PD
    stiffness or a value read from this robot. ``effort_limit`` defaults to the
    rounded 7.4 V stall specification, not a continuous thermal rating.
    BAM owns dry and viscous friction; XML values are replaced, not added.
    ``armature=None`` selects the fitted output-side inertia.
    """

    json_path: str | Path | None = None
    vin: float = 7.4
    kp_fw: float = 32.0
    effort_limit: float = 1.471
    stiff_frictionloss: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.transmission_type != TransmissionType.JOINT:
            raise ValueError("HD1910 supports JOINT transmission and hinge joints only")
        if not self.target_names_expr:
            raise ValueError("HD1910 needs at least one target joint expression")
        for name in ("vin", "kp_fw", "effort_limit", "armature"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value < 0
            ):
                raise ValueError(f"{name} must be finite and nonnegative")
        if not 0 < self.vin <= 8.4:
            raise ValueError("vin must be positive and at most 8.4 V for HD1910")
        if self.effort_limit <= 0:
            raise ValueError("effort_limit must be positive")
        if self.frictionloss is not None or self.viscous_damping is not None:
            raise ValueError("BAM owns frictionloss and viscous_damping; use its JSON")

    def build(
        self, entity: Entity, target_ids: list[int], target_names: list[str]
    ) -> HD1910BamActuator:
        return HD1910BamActuator(self, entity, target_ids, target_names)


class HD1910BamActuator(Actuator[HD1910BamActuatorCfg]):
    """Explicit motor voltage/torque, with M6 friction handled by MuJoCo.

    Load-dependent friction uses the preceding solve's actual motor torque.
    The dry-friction contribution is removed from the external-load estimate
    to avoid feeding the model's own friction back into itself. On reset the
    first compute ignores old solve loads until new physics has run.
    """

    def __init__(self, cfg, entity, target_ids, target_names) -> None:
        super().__init__(cfg, entity, target_ids, target_names)
        self.parameters = load_hd1910_parameters(cfg.json_path)
        self._model: ModelBridge | None = None
        self._data: DataBridge | None = None
        self._dof_ids: torch.Tensor | None = None
        self._load_valid: torch.Tensor | None = None
        self.last_motor_torque: torch.Tensor | None = None
        self.last_friction_budget: torch.Tensor | None = None

    def edit_spec(self, spec: mujoco.MjSpec, target_names: list[str]) -> None:
        # Validate the whole group before mutating the source spec.
        for name in target_names:
            joint = spec.joint(name)
            if joint is None or joint.type != mujoco.mjtJoint.mjJNT_HINGE:
                raise ValueError(f"HD1910 target {name!r} must be a hinge joint")
            for actuator in spec.actuators:
                if (
                    actuator.trntype == mujoco.mjtTrn.mjTRN_JOINT
                    and actuator.target == name
                ):
                    raise ValueError(f"HD1910 target {name!r} already has an actuator")

        armature = self.cfg.armature
        if armature is None:
            armature = self.parameters.armature
        for name in target_names:
            actuator = create_motor_actuator(
                spec,
                name,
                effort_limit=self.cfg.effort_limit,
                armature=armature,
                # Seed native friction constraints before the first compute.
                frictionloss=(
                    self.parameters.friction_base + self.parameters.friction_stribeck
                ),
                viscous_damping=self.parameters.friction_viscous,
            )
            self._mjs_actuators.append(actuator)
            joint = spec.joint(name)
            # Make the joint total-force limit agree with our actuator limit,
            # rather than silently retaining a different limit from the XML.
            joint.actfrclimited = True
            joint.actfrcrange = (-self.cfg.effort_limit, self.cfg.effort_limit)
            if self.cfg.stiff_frictionloss:
                joint.solref_friction = (-5.0e4, -2.0e2)
                joint.solimp_friction = (0.99, 0.9999, 0.001, 0.5, 2.0)

    def initialize(self, mj_model, model, data, device: str) -> None:
        super().initialize(mj_model, model, data, device)
        self._model, self._data = model, data
        joint_ids = self.entity.indexing.joint_ids
        self._dof_ids = torch.tensor(
            [mj_model.jnt_dofadr[joint_ids[i].item()] for i in self._target_ids_list],
            device=device,
            dtype=torch.long,
        )
        shape = (data.nworld, len(self._target_ids_list))
        self._load_valid = torch.zeros(
            (data.nworld, 1), device=device, dtype=torch.bool
        )
        self.last_motor_torque = torch.zeros(shape, device=device)
        self.last_friction_budget = torch.zeros(shape, device=device)

    def _friction_constraint_force(self) -> torch.Tensor:
        """Recover DOF dry-friction forces from valid previous constraint rows."""
        assert self._data is not None and self._dof_ids is not None
        efc = self._data.efc
        types, ids, forces = efc.type[...], efc.id[...], efc.force[...]
        valid = torch.arange(types.shape[1], device=types.device)[None, :]
        valid = valid < self._data.nefc[...][:, None]
        mask = valid & (types == int(mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF))
        indices = torch.where(mask, ids, 0).long()
        contributions = torch.where(mask, forces, 0.0)
        per_dof = torch.zeros_like(self._data.qfrc_actuator[...])
        per_dof.scatter_add_(1, indices, contributions)
        return per_dof[:, self._dof_ids]

    def _scale_friction_budget(self, budget: torch.Tensor) -> torch.Tensor:
        return budget

    def _write_frictions(self, budget: torch.Tensor) -> None:
        assert self._model is not None and self._dof_ids is not None
        assert self._load_valid is not None
        # Re-read bridge fields after any expand_model_fields reallocation.
        for name in ("dof_frictionloss", "dof_damping"):
            field = getattr(self._model, name)
            if field.shape[0] != self._load_valid.shape[0] or (
                field.shape[0] > 1 and field.stride(0) == 0
            ):
                raise RuntimeError(
                    "HD1910 needs independent per-world friction fields. Add the "
                    "bam_init startup event or call sim.expand_model_fields("
                    "('dof_frictionloss', 'dof_damping')) before writing controls."
                )
        self._model.dof_frictionloss[:, self._dof_ids] = budget
        self._model.dof_damping[:, self._dof_ids] = self.parameters.friction_viscous

    def compute(self, cmd: ActuatorCmd) -> torch.Tensor:
        if self._data is None or self._dof_ids is None or self._load_valid is None:
            raise RuntimeError("HD1910 must be initialized before compute")
        assert self.last_motor_torque is not None
        assert self.last_friction_budget is not None
        # mjlab Entity already applied the inline delay. Feedback is current.
        voltage = torch.full_like(cmd.pos[:, :1], self.cfg.vin)
        torque = compute_motor_torque(
            self.parameters,
            cmd.position_target - cmd.pos,
            cmd.vel,
            voltage,
            self.cfg.kp_fw,
        ).clamp(-self.cfg.effort_limit, self.cfg.effort_limit)
        motor_load = self._data.qfrc_actuator[:, self._dof_ids]
        external_load = (
            # Smooth forces include bias, actuation, passive forces, direct
            # generalized loads and projected Cartesian body wrenches.
            self._data.qfrc_smooth[:, self._dof_ids]
            - motor_load
            - self._data.qfrc_passive[:, self._dof_ids]
            + self._data.qfrc_constraint[:, self._dof_ids]
            - self._friction_constraint_force()
        )
        motor_load = torch.where(self._load_valid, motor_load, 0.0)
        external_load = torch.where(self._load_valid, external_load, 0.0)
        budget = compute_friction_budget(
            self.parameters, motor_load, external_load, cmd.vel
        )
        budget = self._scale_friction_budget(budget)
        self._write_frictions(budget)
        self.last_motor_torque.copy_(torque)
        self.last_friction_budget.copy_(budget)
        return torque

    def update(self, dt: float) -> None:
        """A completed physics step makes the new solve loads valid again."""
        del dt
        if self._load_valid is not None:
            self._load_valid.fill_(True)

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        super().reset(env_ids)
        index = slice(None) if env_ids is None else env_ids
        if self._load_valid is not None:
            self._load_valid[index] = False
        if self.last_motor_torque is not None:
            self.last_motor_torque[index] = 0.0
        if self.last_friction_budget is not None:
            self.last_friction_budget[index] = 0.0
