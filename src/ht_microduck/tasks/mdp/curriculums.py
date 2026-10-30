"""Curriculum helpers that mjlab 1.6.0 does not provide.

mjlab 1.6.0 ships exactly two staging helpers, ``reward_curriculum`` and
``termination_curriculum``; both mutate a *reward* or *termination* term. The posture
tasks also need to stage **event** parameters — how often an episode starts on the
ground, and what share of those starts is face-down — because those are reset-event
parameters, not rewards.

Upstream ``microduck_rl`` does this with an ``event_param_curriculum`` helper built on
the mjlab 1.3.0 curriculum API. That helper does not exist here, so this module
reimplements the same behaviour against the 1.6.0 API: it resolves the event term's
config through ``EventManager.get_term_cfg`` and mutates it in place, returning the
staged values so the manager can log them.

The staging rule is copied from mjlab's own ``_apply_stages`` on purpose, including
the "last reached stage wins" precedence and its non-decreasing-step validation, so a
curriculum written with these helpers behaves exactly like the built-in ones.

The walking/head variant also stages live pose-command ranges, following
MicroDuck's first-stage default and next-resample semantics. It validates the
fixed command width so a range change cannot shrink an observation slot.

Pose-command ranges are staged on the live command term config, so they affect
the next resample without rewriting another world's current command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

import torch
from mjlab.managers.curriculum_manager import CurriculumTermCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def _validate(stages: Sequence[dict[str, Any]], term_name: str) -> None:
    for index in range(1, len(stages)):
        if stages[index]["step"] < stages[index - 1]["step"]:
            raise ValueError(
                f"Curriculum stages for {term_name!r} must be in nondecreasing step "
                f"order, but stage {index} has step {stages[index]['step']} < "
                f"{stages[index - 1]['step']}."
            )
    for stage in stages:
        for key in stage:
            if key not in {"step", "params"}:
                raise ValueError(
                    f"Event curriculum stage for {term_name!r} may only set 'step' and "
                    f"'params', but got {key!r}."
                )


class event_param_curriculum:
    """Stage an event term's ``params`` by training step.

    The event config object is mutated in place, which is the same mechanism mjlab's
    own helpers use: the manager keeps a reference to the same ``EventTermCfg`` the
    environment calls, so the next invocation sees the new values.

    Example::

        CurriculumTermCfg(
            func=event_param_curriculum,
            params={
                "event_name": "reset_ground_or_stand",
                "stages": [
                    {"step": 0, "params": {"mixture": (0.0, 0.0, 0.0, 0.0)}},
                    {"step": 600, "params": {"mixture": (0.25, 0.15, 0.20, 0.40)}},
                ],
            },
        )

    Only ``params`` may be staged: an event term's ``func``, ``mode`` and
    ``interval_range_s`` define what the event *is*, and changing them mid-training
    would silently swap the task.
    """

    def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
        event_name: str = cfg.params["event_name"]
        stages: list[dict[str, Any]] = cfg.params["stages"]
        _validate(stages, event_name)
        self._term_cfg = env.event_manager.get_term_cfg(event_name)
        known = set(self._term_cfg.params)
        for stage in stages:
            unknown = set(stage.get("params", {})) - known
            if unknown:
                raise KeyError(
                    f"Stage at step {stage['step']} sets unknown param(s) {sorted(unknown)} "
                    f"on event {event_name!r}; it has {sorted(known)}."
                )
        self._stages = stages
        self._logged = sorted(
            {key for stage in stages for key in stage.get("params", {})}
        )

    def __call__(
        self,
        env: ManagerBasedRlEnv,
        env_ids: torch.Tensor,
        event_name: str,
        stages: list[dict[str, Any]],
    ) -> dict[str, torch.Tensor]:
        del env_ids, event_name, stages
        step = env.common_step_counter
        for stage in self._stages:
            if step >= stage["step"]:
                self._term_cfg.params.update(stage.get("params", {}))
        snapshot: dict[str, torch.Tensor] = {}
        for key in self._logged:
            value = self._term_cfg.params[key]
            if isinstance(value, (int, float, bool)):
                snapshot[key] = torch.tensor(float(value))
            elif isinstance(value, (tuple, list)) and all(
                isinstance(item, (int, float)) for item in value
            ):
                # A vector param such as the ground-start mixture. The log machinery
                # stores scalars, so expand it to one entry per component ("mixture/0"
                # ... "mixture/3") rather than dropping it: *when* the mixture advances
                # is the one thing that matters about this curriculum, and it is
                # otherwise unobservable in training.
                for index, item in enumerate(value):
                    snapshot[f"{key}/{index}"] = torch.tensor(float(item))
        return snapshot


class pose_command_range_curriculum:
    """Stage pose-command ranges without changing their fixed observation width.

    This follows MicroDuck's live-command update: the first stage is the default
    even before its threshold, and the last reached stage wins. Only ranges are
    changed; existing command values and per-world resampling timers are kept.
    """

    def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
        command_name: str = cfg.params["command_name"]
        stages: list[dict[str, Any]] = cfg.params["range_stages"]
        self._command_cfg = env.command_manager.get_term(command_name).cfg
        if not stages:
            raise ValueError(f"Pose curriculum for {command_name!r} needs at least one stage.")
        for index, stage in enumerate(stages):
            if index > 0 and stage["step"] < stages[index - 1]["step"]:
                raise ValueError(
                    f"Pose curriculum stages for {command_name!r} must be in "
                    "nondecreasing step order."
                )
            ranges = stage["ranges"]
            if len(ranges) != self._command_cfg.dim:
                raise ValueError(
                    f"Pose curriculum for {command_name!r} has {len(ranges)} ranges "
                    f"at step {stage['step']}, expected {self._command_cfg.dim}."
                )
            if any(low > high for low, high in ranges):
                raise ValueError(
                    f"Pose curriculum for {command_name!r} has a reversed range "
                    f"at step {stage['step']}."
                )
        self._stages = stages

    def __call__(
        self,
        env: ManagerBasedRlEnv,
        env_ids: torch.Tensor,
        command_name: str,
        range_stages: list[dict[str, Any]],
    ) -> dict[str, torch.Tensor]:
        del env_ids, command_name, range_stages
        current = self._stages[0]["ranges"]
        for stage in self._stages:
            if env.common_step_counter >= stage["step"]:
                current = stage["ranges"]
        self._command_cfg.ranges = tuple(current)
        snapshot = {}
        for index, (low, high) in enumerate(current):
            snapshot[f"axis_{index}/min"] = torch.tensor(float(low))
            snapshot[f"axis_{index}/max"] = torch.tensor(float(high))
        return snapshot
