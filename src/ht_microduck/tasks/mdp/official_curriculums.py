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


def reward_param_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    reward_name: str,
    param_stages: list[dict],
) -> torch.Tensor:
    """按训练步数更新奖励项的 params，使用 live RewardManager 配置。

    官方 backflip 用同一函数把 ``launch_gate_floor`` 从 0.30 收紧到 0.05；
    ``param_stages`` 为 ``{"step": int, "params": dict}``，浅合并到当前项。
    """
    del env_ids
    term_cfg = env.reward_manager.get_term_cfg(reward_name)
    current = param_stages[0]["params"]
    for stage in param_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["params"]
    term_cfg.params.update(current)
    value = next(iter(current.values()))
    return torch.tensor(float(value) if isinstance(value, (int, float)) else 0.0)


def reward_weight_ramp(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    reward_name: str,
    start_weight: float,
    end_weight: float,
    ramp_steps: int,
    delay_steps: int = 0,
    hold_weight: float | None = None,
) -> torch.Tensor:
    """从首次调用时的训练步开始线性加重奖励，适配续训。

    固定 ``step`` 阈值在续训时会被一次性跳过（本机从 model_9999 恢复时
    ``common_step_counter`` 已达 240000），这里把起点记在 env 上，使课程
    无论从零还是从检查点续训都从当前步开始，不会直接跳到末段。

    ``delay_steps`` 让权重先保持 ``hold_weight``（默认 ``start_weight``），
    经过该延迟后才开始 ramp。用于“必须等主任务先学会才能加”的辅助奖励：
    2026-11-15 实测当前配置单次从零训练时，``settle``/``stand_action_rate``/
    ``stand_angvel`` 三项从第一步就生效，把 ``roulade_progress`` 压住，
    6000 迭代后角度仍停在 127–148°（stage4 同期已达 334–383°）。
    """
    del env_ids
    key = f"_curriculum_ramp_start_{reward_name}"
    if not hasattr(env, key):
        setattr(env, key, int(env.common_step_counter))
    start = getattr(env, key)
    elapsed = int(env.common_step_counter) - start
    if elapsed < delay_steps:
        weight = start_weight if hold_weight is None else hold_weight
    else:
        blend = min(max((elapsed - delay_steps) / max(ramp_steps, 1), 0.0), 1.0)
        weight = start_weight + (end_weight - start_weight) * blend
    env.reward_manager.get_term_cfg(reward_name).weight = weight
    return torch.tensor([weight])
