# Copyright (c) 2026-2027 zh
"""内容：
    迁入 MicroDuck 官方的课程参数更新，隔离保留现有 VelStand 行为。

参考：pollen-robotics/microduck_rl，提交 bae39f5900b318f7e87fc485c30a31213cfa14eb，
src/mjlab_microduck/tasks/mdp.py；摘录的上游实现与说明按原文保留，许可 Apache-2.0。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def standing_envs_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    standing_stages: list[dict],
) -> torch.Tensor:
    """Update the relative number of standing environments based on training progress.

    Args:
        env: The RL environment
        env_ids: Environment IDs (unused, but required by curriculum interface)
        command_name: Name of the velocity command term
        standing_stages: List of dicts with 'step' and 'rel_standing_envs' keys
            Example: [
                {"step": 0, "rel_standing_envs": 0.02},
                {"step": 1000, "rel_standing_envs": 0.1},
                {"step": 2000, "rel_standing_envs": 0.2},
            ]

    Returns:
        Current rel_standing_envs value as a tensor
    """
    del env_ids  # Unused

    from typing import cast

    from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

    command_term = env.command_manager.get_term(command_name)
    assert command_term is not None, f"Command term '{command_name}' not found"

    cfg = cast(UniformVelocityCommandCfg, command_term.cfg)

    # Update rel_standing_envs based on current step
    for stage in standing_stages:
        if env.common_step_counter > stage["step"]:
            cfg.rel_standing_envs = stage["rel_standing_envs"]

    return torch.tensor([cfg.rel_standing_envs])


def push_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    event_name: str,
    push_stages: list[dict],
) -> torch.Tensor:
    """Update push velocity range based on training progress.

    Starts with no/small pushes to learn clean walking, then gradually increases
    to build robustness without disrupting early learning.

    Args:
        env: The RL environment
        env_ids: Environment IDs (unused, but required by curriculum interface)
        event_name: Name of the push event term (e.g., "push_robot")
        push_stages: List of dicts with 'step' and 'velocity_range' keys
            Example: [
                {"step": 0, "velocity_range": {"x": (0.0, 0.0), "y": (0.0, 0.0)}},
                {"step": 250, "velocity_range": {"x": (-0.15, 0.15), "y": (-0.15, 0.15)}},
                {"step": 500, "velocity_range": {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}},
            ]

    Returns:
        Current max push magnitude as a tensor
    """
    del env_ids  # Unused

    # NOTE: must update the live EventManager term_cfg, not env.cfg.events —
    # EventManager.__init__ does deepcopy(cfg), so mutating env.cfg.events is a no-op.
    event_cfg = env.event_manager.get_term_cfg(event_name)

    # Update velocity_range based on current step
    current_range = push_stages[0]["velocity_range"]  # Default to first stage

    for stage in push_stages:
        if env.common_step_counter > stage["step"]:
            current_range = stage["velocity_range"]

    # Update the event configuration's velocity_range parameter
    event_cfg.params["velocity_range"] = current_range

    # Return max magnitude for logging
    max_push = max(abs(current_range["x"][0]), abs(current_range["x"][1]))
    return torch.tensor([max_push])


def reward_weight(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    reward_name: str,
    weight_stages: list[dict],
) -> torch.Tensor:
    """Step-staged reward weight curriculum.

    mjlab 1.3.0 dropped the built-in ``mdp.reward_weight`` helper, so microduck
    provides its own. ``weight_stages`` is a list of ``{"step": int, "weight":
    float}`` dicts; the weight of the latest stage whose step has elapsed is
    applied. Mutates the live RewardManager term cfg (not env.cfg, which is a
    deepcopy at manager init).
    """
    del env_ids
    term_cfg = env.reward_manager.get_term_cfg(reward_name)
    for stage in weight_stages:
        if env.common_step_counter > stage["step"]:
            term_cfg.weight = stage["weight"]
    return torch.tensor([term_cfg.weight])


def com_range_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    event_name: str,
    range_stages: list[dict],
) -> torch.Tensor:
    """Update CoM randomization range based on training progress.

    Gradually increases the CoM offset range so the robot first learns to walk
    with a small CoM uncertainty, then progressively larger.

    Args:
        env: The RL environment
        env_ids: Environment IDs (unused)
        event_name: Name of the CoM randomization event (e.g., "randomize_com")
        range_stages: List of dicts with 'step' and 'range' keys (range in meters)
            Example: [
                {"step": 0,          "range": 0.003},
                {"step": 1000 * 24,  "range": 0.005},
                {"step": 2000 * 24,  "range": 0.008},
            ]

    Returns:
        Current range value as a tensor (for logging)
    """
    del env_ids

    # NOTE: must update the live EventManager term_cfg, not env.cfg.events —
    # EventManager.__init__ does deepcopy(cfg), so mutating env.cfg.events is a no-op.
    event_cfg = env.event_manager.get_term_cfg(event_name)

    current_range = range_stages[0]["range"]
    for stage in range_stages:
        if env.common_step_counter > stage["step"]:
            current_range = stage["range"]

    event_cfg.params["ranges"] = (-current_range, current_range)
    return torch.tensor([current_range])


def event_param_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    event_name: str,
    param_stages: list[dict],
) -> torch.Tensor:
    """Mutate an event term's params at scheduled steps.

    Mirror of termination_param_curriculum but for events. Uses the live
    EventManager term cfg via get_term_cfg, since env.cfg.events is a deepcopy.
    param_stages: list of {step: int, params: dict}. Shallow-merged into the
    live event term's params at the latest matching stage.
    """
    del env_ids
    event_cfg = env.event_manager.get_term_cfg(event_name)
    current = param_stages[0]["params"]
    for stage in param_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["params"]
    event_cfg.params.update(current)
    first_val = next(iter(current.values()))
    return torch.tensor(float(first_val) if isinstance(first_val, (int, float)) else 0.0)


def termination_param_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    term_name: str,
    param_stages: list[dict],
) -> torch.Tensor:
    """Mutate a termination term's params at scheduled steps.

    TerminationManager keeps its own deepcopy of the cfg dict, so the live
    term_cfgs list must be edited directly — env.cfg.terminations is a no-op.
    Useful for disabling a termination later in training (e.g. set
    bad_orientation's limit_angle to pi at iter N so the robot can fall over
    without ending the episode and learn to recover).

    param_stages: list of {step: int, params: dict}. The dict is shallow-merged
    into the live term_cfg.params at the latest matching stage.
    """
    del env_ids
    tm = env.termination_manager
    if term_name not in tm._term_names:
        # Term was removed (e.g. play mode disables fell_over entirely).
        return torch.tensor(0.0)
    idx = tm._term_names.index(term_name)
    term_cfg = tm._term_cfgs[idx]

    current = param_stages[0]["params"]
    for stage in param_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["params"]
    term_cfg.params.update(current)

    first_val = next(iter(current.values()))
    return torch.tensor(float(first_val) if isinstance(first_val, (int, float)) else 0.0)


def pose_command_range_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    command_name: str,
    range_stages: list[dict],
) -> torch.Tensor:
    """Ramp a UniformPoseCommand's per-dim ranges over training.

    range_stages: list of {step: int, ranges: tuple[(lo, hi), ...]}.
    The first stage applies before its step; latest passed stage wins.
    Always uses the live CommandManager term cfg (NOT env.cfg.commands) so
    updates take effect — CommandManager keeps its own term refs and reads
    `term.cfg.ranges` each resample.
    """
    del env_ids

    term = env.command_manager.get_term(command_name)
    assert term is not None, f"Command term '{command_name}' not found"
    cfg = term.cfg  # type: ignore[assignment]

    current = range_stages[0]["ranges"]
    for stage in range_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["ranges"]

    cfg.ranges = tuple(current)
    # Return the max abs range as a scalar for wandb visibility.
    max_abs = max((max(abs(lo), abs(hi)) for lo, hi in current), default=0.0)
    return torch.tensor(max_abs)

