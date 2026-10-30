# Copyright 2025 Marc Duclusaud & Grégoire Passault
# Copyright 2026 ftservo
# SPDX-License-Identifier: Apache-2.0
#
# Adapted for ht_microduck from ftservo/ftservo-bam at commit
# 4f7c0b0de3debf9c1ab254fc9654676e8aab9317. See NOTICE and
# THIRD_PARTY_LICENSE in this directory for attribution and modifications.

"""HD1910 M6 electrical and dry-friction equations, independent of mjlab.

The bundled parameters are the manufacturer's public 7.4 V fit, not a
calibration of this robot. The fitted ``q_offset`` and ``command_delay`` are
retained as identification metadata and are deliberately not applied here.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from numbers import Real
from pathlib import Path

import torch

DEFAULT_PARAMETERS_PATH = (
    Path(__file__).parent / "params" / "feetech_hd1910_7_4V_m6.json"
)


@dataclass(frozen=True, kw_only=True)
class HD1910BamParameters:
    """Validated manufacturer M6 parameters in SI units.

    ``kt`` and ``R`` are identified effective motor constants at the output
    joint, not independent measurements of the bare motor or gearbox.
    """

    kt: float
    R: float
    armature: float
    q_offset: float
    command_delay: float
    friction_base: float
    friction_stribeck: float
    load_friction_motor: float
    load_friction_external: float
    load_friction_motor_stribeck: float
    load_friction_external_stribeck: float
    load_friction_motor_quad: float
    load_friction_external_quad: float
    dtheta_stribeck: float
    alpha: float
    friction_viscous: float
    model: str = "m6"
    actuator: str = "hd1910"

    def __post_init__(self) -> None:
        if self.model != "m6":
            raise ValueError(f"Only the HD1910 M6 model is supported: {self.model!r}")
        if self.actuator not in ("hd1910", "HD1910"):
            raise ValueError(f"Unsupported actuator identity: {self.actuator!r}")
        # Upstream JSON uses lowercase; the upstream registry uses uppercase.
        # Normalize this known alias explicitly, without a registry dependency.
        object.__setattr__(self, "actuator", "hd1910")
        positive_fields = {"kt", "R", "dtheta_stribeck", "alpha"}
        for field in fields(self):
            if field.name in ("model", "actuator"):
                continue
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{field.name} must be a finite real number")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{field.name} must be finite")
            if field.name in positive_fields and value <= 0.0:
                raise ValueError(f"{field.name} must be positive")
            if field.name != "q_offset" and value < 0.0:
                raise ValueError(f"{field.name} must be nonnegative")
            object.__setattr__(self, field.name, value)


def load_hd1910_parameters(
    json_path: str | Path | None = None,
) -> HD1910BamParameters:
    """Load a complete HD1910 M6 fit, retaining the fitted values unchanged.

    A custom fit must use the same schema and identify this actuator and model
    explicitly. Missing, extra, nonfinite or nonphysical fields fail early.
    No model initialization is run after loading the identified parameters.
    """
    path = DEFAULT_PARAMETERS_PATH if json_path is None else Path(json_path)
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a parameter object in {path}")
    expected = {field.name for field in fields(HD1910BamParameters)}
    missing = expected - data.keys()
    unexpected = data.keys() - expected
    if missing or unexpected:
        raise ValueError(
            f"Invalid HD1910 M6 schema in {path}: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return HD1910BamParameters(**data)


def compute_motor_torque(
    parameters: HD1910BamParameters,
    position_error: torch.Tensor,
    velocity: torch.Tensor,
    voltage: torch.Tensor,
    kp_fw: float = 32.0,
) -> torch.Tensor:
    """Compute P-controlled DC torque, including back EMF, in N m.

    ``kp_fw`` is the manufacturer's dimensionless firmware gain, not a joint
    stiffness in N m/rad. ``voltage`` is the actual supply voltage in V.
    Inputs follow PyTorch broadcasting and must contain finite values, with
    positive voltage. Limits, delays and additional damping belong to the
    integrating actuator, and are not silently added to this equation.
    """
    if not math.isfinite(kp_fw) or kp_fw < 0.0:
        raise ValueError("kp_fw must be finite and nonnegative")
    duty_cycle = torch.clamp(position_error * kp_fw * 0.163, -0.97, 0.97)
    return (
        parameters.kt * voltage * duty_cycle / parameters.R
        - parameters.kt**2 * velocity / parameters.R
    )


def compute_friction_budget(
    parameters: HD1910BamParameters,
    motor_torque: torch.Tensor,
    external_torque: torch.Tensor,
    velocity: torch.Tensor,
) -> torch.Tensor:
    """Compute the manufacturer's canonical M6 dry-friction budget in N m.

    This is a nonnegative constraint budget, not a signed torque to subtract.
    MuJoCo applies it through ``dof_frictionloss``. Viscous damping is separate
    (``parameters.friction_viscous``); neither it nor domain randomization is
    applied here. The caller supplies motor/external loads from the same solve.

    The quadratic term follows the pinned scalar ``bam/model.py`` used for
    identification: it contributes only for opposite torque signs and unequal
    load magnitudes. This corrects the missing gates in upstream's mjlab port.
    """
    p = parameters
    stribeck = torch.exp(-torch.pow(torch.abs(velocity) / p.dtheta_stribeck, p.alpha))
    gearbox = torch.abs(
        external_torque * p.load_friction_external
        - motor_torque * p.load_friction_motor
    )
    gearbox_stribeck = torch.abs(
        external_torque * p.load_friction_external_stribeck
        - motor_torque * p.load_friction_motor_stribeck
    )
    abs_motor = torch.abs(motor_torque)
    abs_external = torch.abs(external_torque)
    motor_driven_quadratic = (
        p.load_friction_external_quad * abs_external**2 * (abs_motor > abs_external)
    )
    backdriven_quadratic = (
        p.load_friction_motor_quad * abs_motor**2 * (abs_motor < abs_external)
    )
    opposite_sign = torch.sign(external_torque) != torch.sign(motor_torque)
    quadratic = (motor_driven_quadratic + backdriven_quadratic) * opposite_sign
    return (
        p.friction_base
        + gearbox
        + stribeck * (p.friction_stribeck + gearbox_stribeck + quadratic)
    )
