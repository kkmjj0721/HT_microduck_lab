"""HTDW-3532 output-shaft motoring envelope sampled from a 24 V datasheet.

The piecewise curve is a simulation prior, not measured motor identification.
Opposing-speed torque keeps a separate fixed cap because the source does not
provide a braking or regeneration envelope. No thermal model is inferred.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from numbers import Real
from pathlib import Path

import torch

DEFAULT_PARAMETERS_PATH = Path(__file__).parent / "params" / "htdw_3532_24v.json"


def _finite_number(value: object, name: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    number = float(value)
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        domain = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {domain}")
    return number


@dataclass(frozen=True, kw_only=True)
class HTDW3532Parameters:
    """Validated output-shaft rpm/N·m points; gear ratio is metadata only."""

    voltage_v: float
    gear_ratio: float
    rpm: tuple[float, ...]
    motoring_torque_nm: tuple[float, ...]
    stall_torque_nm: float
    continuous_rated_torque_nm: float

    def __post_init__(self) -> None:
        for name in (
            "voltage_v",
            "gear_ratio",
            "stall_torque_nm",
            "continuous_rated_torque_nm",
        ):
            object.__setattr__(
                self,
                name,
                _finite_number(getattr(self, name), name, positive=True),
            )
        if self.continuous_rated_torque_nm > self.stall_torque_nm:
            raise ValueError("continuous_rated_torque_nm must not exceed stall torque")
        for name in ("rpm", "motoring_torque_nm"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)):
                raise ValueError(f"{name} must be a sequence of finite numbers")
            validated = tuple(
                _finite_number(value, f"{name}[{index}]", positive=False)
                for index, value in enumerate(values)
            )
            object.__setattr__(self, name, validated)
        if len(self.rpm) < 2 or len(self.rpm) != len(self.motoring_torque_nm):
            raise ValueError(
                "rpm and motoring_torque_nm need equal lengths of at least 2"
            )
        if self.rpm[0] != 0.0 or any(
            upper <= lower for lower, upper in zip(self.rpm, self.rpm[1:])
        ):
            raise ValueError("rpm must start at zero and be strictly increasing")
        if any(
            upper > lower
            for lower, upper in zip(
                self.motoring_torque_nm, self.motoring_torque_nm[1:]
            )
        ):
            raise ValueError("motoring_torque_nm must be monotonically nonincreasing")
        if self.motoring_torque_nm[0] != self.stall_torque_nm:
            raise ValueError("The zero-speed torque must equal stall_torque_nm")
        if self.motoring_torque_nm[-1] != 0.0:
            raise ValueError("The last motoring torque point must be zero")


def load_htdw3532_parameters(
    json_path: str | Path | None = None,
) -> HTDW3532Parameters:
    """Load the bundled prior or a complete fit with the same output-shaft schema.

    A different voltage requires its own explicitly supplied curve. This loader
    does not rescale torque or speed from supply voltage or reduction ratio.
    """
    path = DEFAULT_PARAMETERS_PATH if json_path is None else Path(json_path)
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected an HTDW3532 parameter object in {path}")
    expected = {field.name for field in fields(HTDW3532Parameters)}
    missing = expected - data.keys()
    unexpected = data.keys() - expected
    if missing or unexpected:
        raise ValueError(
            f"Invalid HTDW3532 parameter schema in {path}: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return HTDW3532Parameters(**data)


def motoring_torque_limit(
    velocity: torch.Tensor, parameters: HTDW3532Parameters
) -> torch.Tensor:
    """Interpolate the motoring cap from actual output-joint velocity [rad/s].

    Input is finite floating-point data. The result keeps its shape, dtype and
    device. Both rotation directions share the same curve; at and beyond the
    final rpm point the motoring cap is zero. No CPU transfer occurs here.
    """
    rpm = velocity.abs() * (60.0 / (2.0 * math.pi))
    result = torch.full_like(rpm, parameters.motoring_torque_nm[0])
    for lower, upper, lower_torque, upper_torque in zip(
        parameters.rpm,
        parameters.rpm[1:],
        parameters.motoring_torque_nm,
        parameters.motoring_torque_nm[1:],
    ):
        interpolated = lower_torque + (upper_torque - lower_torque) * (
            (rpm - lower) / (upper - lower)
        )
        result = torch.where((rpm >= lower) & (rpm < upper), interpolated, result)
    return torch.where(rpm >= parameters.rpm[-1], 0.0, result).clamp_min(0.0)


def clip_nt_torque(
    torque: torch.Tensor,
    velocity: torch.Tensor,
    effort_limit: float | torch.Tensor,
    parameters: HTDW3532Parameters,
) -> torch.Tensor:
    """Apply fixed and motoring limits to output-shaft torque [N·m].

    ``effort_limit`` is a nonnegative finite scalar or broadcastable tensor.
    Opposing-speed torque retains that fixed limit as an unmeasured braking
    assumption. A zero request remains zero, including at overspeed.
    """
    limited = torch.clamp(torque, min=-effort_limit, max=effort_limit)
    cap = motoring_torque_limit(velocity, parameters)
    driving = limited * velocity >= 0.0
    motoring = torch.clamp(limited, min=-cap, max=cap)
    return torch.where(driving, motoring, limited)
