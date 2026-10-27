"""Single friction-budget scaling hook for the local HD1910 BAM actuator.

Dry/load/Stribeck friction is scaled once; viscous damping remains nominal.
With no range, reset restores 1.0. With a range, startup and each reset sample
one coefficient per selected environment, shared by the joints in this group.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch

from .bam_actuator import HD1910BamActuator, HD1910BamActuatorCfg


@dataclass(kw_only=True)
class FrictionDRBamActuatorCfg(HD1910BamActuatorCfg):
    """HD1910 M6 with optional per-episode, per-environment dry-friction DR."""

    friction_scale_range: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        limits = self.friction_scale_range
        if limits is not None and (
            len(limits) != 2
            or any(isinstance(x, bool) or not math.isfinite(x) for x in limits)
            or limits[0] < 0
            or limits[0] > limits[1]
        ):
            raise ValueError(
                "friction_scale_range must be finite, nonnegative, ordered"
            )

    def build(self, entity, target_ids, target_names) -> FrictionDRBamActuator:
        return FrictionDRBamActuator(self, entity, target_ids, target_names)


class FrictionDRBamActuator(HD1910BamActuator):
    cfg: FrictionDRBamActuatorCfg

    def initialize(self, mj_model, model, data, device: str) -> None:
        super().initialize(mj_model, model, data, device)
        self.friction_scale = torch.ones((data.nworld, 1), device=device)
        self.default_friction_scale = self.friction_scale.clone()
        self._sample_friction_scale()

    def _scale_friction_budget(self, budget: torch.Tensor) -> torch.Tensor:
        return budget * self.friction_scale

    def set_friction_scale(
        self,
        env_ids: torch.Tensor | slice | None,
        friction_scale: torch.Tensor | float,
    ) -> None:
        """Set a finite, nonnegative coefficient per selected environment.

        Accepts a scalar, shape (num_selected,), or (num_selected, 1).
        This setter validates at event time; it is not a per-step control call.
        """
        index = slice(None) if env_ids is None else env_ids
        values = torch.as_tensor(
            friction_scale,
            device=self.friction_scale.device,
            dtype=self.friction_scale.dtype,
        )
        if values.ndim == 1:
            values = values[:, None]
        target_shape = self.friction_scale[index].shape
        try:
            valid_shape = torch.broadcast_shapes(values.shape, target_shape) == (
                target_shape
            )
        except RuntimeError:
            valid_shape = False
        if values.ndim > 2 or not valid_shape:
            raise ValueError(
                "friction_scale must be scalar or one value per environment"
            )
        if not torch.isfinite(values).all() or (values < 0).any():
            raise ValueError("friction_scale must be finite and nonnegative")
        self.friction_scale[index] = values

    def reset_friction_scale(self, env_ids: torch.Tensor | slice | None = None) -> None:
        """Restore the selected coefficients to 1, without resampling."""
        index = slice(None) if env_ids is None else env_ids
        self.friction_scale[index] = self.default_friction_scale[index]

    def _sample_friction_scale(
        self, env_ids: torch.Tensor | slice | None = None
    ) -> None:
        index = slice(None) if env_ids is None else env_ids
        values = self.default_friction_scale[index].clone()
        if self.cfg.friction_scale_range is not None:
            values.uniform_(*self.cfg.friction_scale_range)
        self.friction_scale[index] = values

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        super().reset(env_ids)
        if hasattr(self, "friction_scale"):
            self._sample_friction_scale(env_ids)
