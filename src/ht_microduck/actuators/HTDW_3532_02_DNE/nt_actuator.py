"""Native affine HTDW-3532 joint PD with the sampled output-shaft NT envelope."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import TYPE_CHECKING

import mujoco
import torch
from mjlab.actuator.actuator import ActuatorCmd, TransmissionType
from mjlab.actuator.pd_actuator import (
    IdealPdActuator,
    IdealPdActuatorCfg,
)
from mjlab.managers.event_manager import requires_model_fields

from .model import load_htdw3532_parameters, motoring_torque_limit

if TYPE_CHECKING:
    from mjlab.entity import Entity
    from mjlab.sim.sim import ModelBridge


@requires_model_fields("actuator_forcerange", "actuator_biasprm")
def htdw3532_init(env, env_ids=None) -> None:
    """Declare independent native-PD fields as a startup event.

    Standalone Scene/Simulation users can instead call
    ``sim.expand_model_fields(('actuator_forcerange', 'actuator_biasprm'))``
    before writing controls or resetting the initialized entity.
    """
    del env, env_ids


@dataclass(kw_only=True)
class HTDW3532ActuatorCfg(IdealPdActuatorCfg):
    """HTDW-3532 output-joint controller using the bundled 24 V prior.

    Gains are SI joint PD gains, not firmware values. Set a finite positive
    ``effort_limit`` explicitly; the stall rating is not a continuous rating.
    Delay/reset and passive joint overrides use mjlab's normal lifecycle.
    """

    json_path: str | Path | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.transmission_type != TransmissionType.JOINT:
            raise ValueError(
                "HTDW3532 supports JOINT transmission and hinge joints only"
            )
        if not self.target_names_expr:
            raise ValueError("HTDW3532 needs at least one target joint expression")
        for name in (
            "stiffness",
            "damping",
            "effort_limit",
            "armature",
            "frictionloss",
            "viscous_damping",
        ):
            value = getattr(self, name)
            if value is None and name in (
                "armature",
                "frictionloss",
                "viscous_damping",
            ):
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"{name} must be finite and nonnegative")
        parameters = load_htdw3532_parameters(self.json_path)
        if not 0.0 < self.effort_limit <= parameters.stall_torque_nm:
            raise ValueError(
                "effort_limit must be positive and not exceed stall torque"
            )

    def build(
        self, entity: Entity, target_ids: list[int], target_names: list[str]
    ) -> HTDW3532Actuator:
        return HTDW3532Actuator(self, entity, target_ids, target_names)


class HTDW3532Actuator(IdealPdActuator[HTDW3532ActuatorCfg]):
    """Native affine PD with per-world NT limits and mjlab command delay.

    ``compute`` writes the native bias and signed force range, then returns
    ``kp*q_target + kd*dq_target + tau_ff``. MuJoCo adds ``-kp*q-kd*dq`` and
    clips the result, retaining implicit damping integration. The control
    has units of N·m but is not the final applied torque. The custom method
    bypasses IdealPd fusion and the builtin identity-control batch path.

    Targets were delayed once by Entity; range feedback uses current velocity.
    There is no extra history buffer or thermal/braking dynamics.
    """

    def __init__(self, cfg, entity, target_ids, target_names) -> None:
        super().__init__(cfg, entity, target_ids, target_names)
        self.parameters = load_htdw3532_parameters(cfg.json_path)
        self._model: ModelBridge | None = None
        self._compiled_force_limit: torch.Tensor | None = None
        self._model_actuator_count: int | None = None

    def edit_spec(self, spec: mujoco.MjSpec, target_names: list[str]) -> None:
        # Check the entire group before creating any actuators.
        if len(target_names) != len(set(target_names)):
            raise ValueError("HTDW3532 target joint names must be unique")
        for name in target_names:
            joint = spec.joint(name)
            if joint is None or joint.type != mujoco.mjtJoint.mjJNT_HINGE:
                raise ValueError(f"HTDW3532 target {name!r} must be a hinge joint")
            for actuator in spec.actuators:
                if (
                    actuator.trntype == mujoco.mjtTrn.mjTRN_JOINT
                    and actuator.target == name
                ):
                    raise ValueError(
                        f"HTDW3532 target {name!r} already has an actuator"
                    )
        super().edit_spec(spec, target_names)
        for actuator in self._mjs_actuators:
            # Unit control gain supports kp=0 and all three command targets.
            actuator.gainprm[0] = 1.0
            actuator.biastype = mujoco.mjtBias.mjBIAS_AFFINE
            actuator.biasprm[1] = -self.cfg.stiffness
            actuator.biasprm[2] = -self.cfg.damping
            # The drive term can exceed the actual torque limit at a nonzero
            # position; only the final force must be clamped.
            actuator.ctrllimited = False
            actuator.inheritrange = 0.0

    def initialize(self, mj_model, model, data, device: str) -> None:
        super().initialize(mj_model, model, data, device)
        self._model = model
        self._model_actuator_count = mj_model.nu
        # Dynamic field writes replace forcerange. Keep the original compiled
        # bounds independently so set_effort_limit cannot erase that ceiling.
        ceilings = [
            min(
                -mj_model.actuator_forcerange[actuator.id, 0],
                mj_model.actuator_forcerange[actuator.id, 1],
            )
            for actuator in self._mjs_actuators
        ]
        self._compiled_force_limit = torch.tensor(
            ceilings, dtype=self.force_limit.dtype, device=device
        )[None, :]

    def _native_fields(self):
        if self._model is None or self.force_limit is None:
            raise RuntimeError("HTDW3532 must be initialized before compute or reset")
        expected = self.force_limit.shape[0], self._model_actuator_count
        fields = []
        for name, width in (
            ("actuator_forcerange", 2),
            ("actuator_biasprm", 10),
        ):
            field = getattr(self._model, name, None)
            try:
                independent = (
                    field is not None
                    and tuple(field.shape) == (*expected, width)
                    and (expected[0] <= 1 or field.stride(0) != 0)
                )
            except AttributeError:
                independent = False
            if not independent:
                raise RuntimeError(
                    "HTDW3532 needs independent per-world native PD fields. "
                    "Register the htdw3532_init startup event or call "
                    "sim.expand_model_fields(('actuator_forcerange', "
                    f"'actuator_biasprm')) before control/reset; invalid {name}."
                )
            fields.append(field)
        return fields[0], fields[1]

    def _fixed_limit(self) -> torch.Tensor:
        assert self.force_limit is not None and self._compiled_force_limit is not None
        return torch.minimum(
            self.force_limit.clamp_min(0.0), self._compiled_force_limit
        )

    def _write_native_parameters(self, ranges, bias, lower, upper, env_ids=None):
        assert self.stiffness is not None and self.damping is not None
        bounds = torch.stack((lower, upper), dim=-1).to(dtype=ranges.dtype)
        position_bias = -self.stiffness.to(dtype=bias.dtype)
        velocity_bias = -self.damping.to(dtype=bias.dtype)
        ids = self.global_ctrl_ids
        if env_ids is None:
            ranges[:, ids] = bounds
            bias[:, ids, 1] = position_bias
            bias[:, ids, 2] = velocity_bias
        else:
            rows = torch.arange(bounds.shape[0], device=bounds.device)[env_ids]
            index = rows[:, None], ids[None, :]
            ranges[index] = bounds[rows]
            bias[*index, 1] = position_bias[rows]
            bias[*index, 2] = velocity_bias[rows]

    def compute(self, cmd: ActuatorCmd) -> torch.Tensor:
        if self.stiffness is None or self.damping is None or self.force_limit is None:
            raise RuntimeError("HTDW3532 must be initialized before compute")
        # Re-read bridge arrays after any expand_model_fields reallocation.
        ranges, bias = self._native_fields()
        fixed = self._fixed_limit()
        cap = torch.minimum(fixed, motoring_torque_limit(cmd.vel, self.parameters))
        lower = torch.where(cmd.vel < 0.0, -cap, -fixed)
        upper = torch.where(cmd.vel > 0.0, cap, fixed)
        self._write_native_parameters(ranges, bias, lower, upper)
        return (
            self.stiffness * cmd.position_target
            + self.damping * cmd.velocity_target
            + cmd.effort_target
        )

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        if self._model is None:
            super().reset(env_ids)
            return
        ranges, bias = self._native_fields()
        super().reset(env_ids)
        fixed = self._fixed_limit()
        self._write_native_parameters(ranges, bias, -fixed, fixed, env_ids)
