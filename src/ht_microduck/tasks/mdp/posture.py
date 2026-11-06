# Copyright (c) 2026-2027 zh
"""VelStand 使用的姿态、倒地恢复奖励与回合状态重置。

保留该任务的势函数进度、代价、终止和头部跟踪；其他姿态任务使用 official_* 模块。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity.mdp import feet_air_time

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _asset(env: ManagerBasedRlEnv, cfg: SceneEntityCfg) -> Entity:
    return env.scene[cfg.name]


def _trunk_height(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Trunk height above the terrain, not above the world origin.

    On rough terrain every environment sits at a different origin height, so an
    absolute world z would make the gates fire at the wrong time for most worlds.
    Upstream hit exactly that: with absolute z on rough terrain the robots spawned
    inside the ground and the value loss went from 0.6 to 42.
    """
    asset = _asset(env, asset_cfg)
    origins = env.scene.env_origins[:, 2]
    return asset.data.root_link_pos_w[:, 2] - origins


def _tilt_cos(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """``cos(tilt)``: 1 when the trunk is upright, -1 when inverted."""
    asset = _asset(env, asset_cfg)
    return -asset.data.projected_gravity_b[:, 2]


def _tilt_rad(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    return torch.acos(torch.clamp(_tilt_cos(env, asset_cfg), -1.0, 1.0))


def _smoothstep(x: torch.Tensor, low: float, high: float) -> torch.Tensor:
    """0 below ``low``, 1 above ``high``, smooth in between."""
    if high <= low:
        raise ValueError(f"smoothstep needs high > low, got {low} and {high}")
    t = torch.clamp((x - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------- per-episode reward state ----------
#
# Several terms here are potential-based or hysteretic, so they must remember a value
# from the previous control step: the previous potential, how long the robot has been
# fallen, whether the recovery bounty is armed. That state is kept per environment on
# the env object.
#
# **It must be cleared on reset, and by default it was not.** mjlab only calls
# ``RewardManager.reset(env_ids)`` on *class-based* terms (see
# ``reward_manager.py``: ``_class_term_cfgs``), and these were plain functions, so
# every new episode's first step compared against the *previous* episode's terminal
# state. Measured consequence on VelStand: ``upright_progress`` paid on 344 of 360
# resets, and in short episodes that first-step windfall was about two thirds of the
# mean return -- always positive, i.e. "fall over sooner and earn more", which is the
# exact opposite of what ``recovery_bounty`` and ``fallen_tax`` are for.
#
# ``RewardStateReset`` is a class-based term whose only job is to clear the buffers, so
# the manager's existing reset path does the right thing without patching mjlab.

_REWARD_STATE_KEYS: tuple[str, ...] = (
    "_ht_posture_prev",
    "_ht_fallen_timer",
    "_ht_fallen_timer_bounty",
    "_ht_bounty_armed",
    "_ht_fallen_tax_state",
    "_ht_air_time",
    "_ht_prev_contact",
)


def reset_reward_state(env: ManagerBasedRlEnv, env_ids: torch.Tensor) -> None:
    """只使指定环境的势函数历史失效，并清零对应计时/滞回状态。"""
    for key in _REWARD_STATE_KEYS:
        store = getattr(env, key, None)
        if store is None:
            continue
        if isinstance(store, dict):
            # 每项保存数值与逐环境有效位；邻居环境的历史不能随局部 reset 丢失。
            # 回放可在 inference_mode 内创建缓存，再由查看器在模式外手工重置。
            # 克隆后更新，避免原地修改 inference tensor，同时保留邻居历史。
            for name, (values, valid) in store.items():
                updated = valid.clone()
                updated[env_ids] = False
                store[name] = (values, updated)
            continue
        if isinstance(store, torch.Tensor) and store.ndim > 0:
            updated = store.clone()
            updated[env_ids] = 0
            setattr(env, key, updated)


class RewardStateReset:
    """Class-based term that clears the per-episode reward buffers on reset.

    Class-based rather than functional on purpose: mjlab's ``RewardManager`` invokes
    ``reset`` only for class-based terms, which is the supported hook for per-episode
    state. The term is registered with weight 0.0, so both mjlab and this code skip it
    during reward computation and it costs nothing.
    """

    def __init__(self, cfg: object, env: ManagerBasedRlEnv):
        del cfg
        self._env = env

    def __call__(self, env: ManagerBasedRlEnv, **kwargs) -> torch.Tensor:
        del kwargs
        return torch.zeros(env.num_envs, device=env.device)

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        if env_ids is None:
            env_ids = torch.arange(self._env.num_envs, device=self._env.device)
        elif isinstance(env_ids, slice):
            env_ids = torch.arange(self._env.num_envs, device=self._env.device)[env_ids]
        if len(env_ids) == 0:
            return
        reset_reward_state(self._env, env_ids)


def _prev(env: ManagerBasedRlEnv, key: str, current: torch.Tensor) -> torch.Tensor:
    """返回逐环境上一势函数值；初次调用或该环境刚 reset 时以当前值播种。"""
    store = getattr(env, "_ht_posture_prev", None)
    if store is None:
        store = {}
        env._ht_posture_prev = store
    history = store.get(key)
    if history is None or history[0].shape != current.shape:
        previous = current.clone()
    else:
        values, valid = history
        previous = torch.where(valid, values, current)
    store[key] = (current.clone(), torch.ones_like(current, dtype=torch.bool))
    return previous


def _joint_ids(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    return asset_cfg.joint_ids


# ---------- fall detection ----------


def upright_gaussian(
    env: ManagerBasedRlEnv,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``exp(-tilt**2 / std**2)``: sharp near vertical, where the linear form stalls."""
    return torch.exp(-torch.square(_tilt_rad(env, asset_cfg)) / std**2)


def upright_gaussian_at_height(
    env: ManagerBasedRlEnv,
    std: float,
    height_low: float,
    height_high: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    command_name: str | None = None,
) -> torch.Tensor:
    """保留本地角度 Gaussian 与高度门控，可显式改用身体指令的角度参考。

    这不是官方同名奖励：相对目标使用 gravity 夹角，使零指令在任意倾角下都还原
    原先的 acos(-g_z) 角度公式；不把本地额外项替换成官方 g_xy Gaussian。
    """
    if command_name is None:
        reward = upright_gaussian(env, std, asset_cfg)
    else:
        command = env.command_manager.get_command(command_name)
        roll, pitch = command[:, 3], command[:, 4]
        target = torch.stack(
            [
                torch.sin(pitch),
                -torch.sin(roll) * torch.cos(pitch),
                -torch.cos(roll) * torch.cos(pitch),
            ],
            dim=1,
        )
        gravity = _asset(env, asset_cfg).data.projected_gravity_b
        cosine = torch.sum(gravity * target, dim=1).clamp(-1.0, 1.0)
        angle = torch.acos(cosine)
        reward = torch.exp(-torch.square(angle) / std**2)
    return reward * _smoothstep(_trunk_height(env, asset_cfg), height_low, height_high)


def upright_body_cmd_relative(
    env: ManagerBasedRlEnv,
    std: float,
    command_name: str = "body_pose",
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方 g_xy Gaussian 跟随身体 roll/pitch，零指令等于原 upright。"""
    command = env.command_manager.get_command(command_name)
    roll, pitch = command[:, 3], command[:, 4]
    target = torch.stack(
        [torch.sin(pitch), -torch.sin(roll) * torch.cos(pitch)], dim=1
    )
    gravity = _asset(env, asset_cfg).data.projected_gravity_b
    error = torch.square(gravity[:, :2] - target).sum(dim=1)
    return torch.exp(-error / std**2)


def tilted_mask(
    env: ManagerBasedRlEnv,
    gate_tilt_above_deg: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Tilt-only gate: the safe gate for a positive recovery reward.

    Height must not be part of this condition. A reward that turns on when the
    robot is low is a reward for getting low, and a robot that can reach the gate
    by sitting has no reason to stand up again.
    """
    return _tilt_cos(env, asset_cfg) < math.cos(math.radians(gate_tilt_above_deg))


def fallen_too_long(
    env: ManagerBasedRlEnv,
    gate_z_below: float,
    gate_tilt_above_deg: float,
    max_duration_s: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按官方低高度或大倾角条件累计连续倒地时长，恢复后清零。"""
    fallen = (_trunk_height(env, asset_cfg) < gate_z_below) | (
        _tilt_cos(env, asset_cfg) < math.cos(math.radians(gate_tilt_above_deg))
    )
    timer = getattr(env, "_ht_fallen_timer", None)
    if timer is None or timer.shape != fallen.shape:
        timer = torch.zeros_like(fallen, dtype=torch.float)
        env._ht_fallen_timer = timer
    timer = torch.where(fallen, timer + env.step_dt, torch.zeros_like(timer))
    env._ht_fallen_timer = timer
    return timer >= max_duration_s


def feet_air_time_upright(
    env: ManagerBasedRlEnv,
    gate_tilt_above_deg: float = 40.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    **air_time_kwargs,
) -> torch.Tensor:
    """保留 mjlab 腾空奖励原式，仅在 tilt 严格超过官方门限时归零。"""
    reward = feet_air_time(env, **air_time_kwargs)
    upright = _tilt_cos(env, asset_cfg) >= math.cos(math.radians(gate_tilt_above_deg))
    return reward * upright.float()


# ---------- potential-based progress ----------


def upright_progress(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward the *increase* in ``cos(tilt)`` since the previous step.

    Prone -> standing swings ``cos(tilt)`` by about 2.0, so a get-up pays a fixed
    total however long it takes. A robot that stops moving earns zero, and because
    the term is a difference of a bounded quantity it cannot be farmed by holding
    any pose, including the target one.
    """
    current = _tilt_cos(env, asset_cfg)
    return current - _prev(env, "upright_progress", current)


def height_progress(
    env: ManagerBasedRlEnv,
    ceiling: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward the *increase* in trunk height, capped at ``ceiling``.

    The upright term alone runs out of gradient in the last stretch of a get-up:
    from a deep crouch to standing the trunk barely changes orientation but rises
    several centimetres. The cap bounds the total payout and keeps a walking robot
    from farming the term by bobbing through the ceiling.
    """
    current = torch.clamp(_trunk_height(env, asset_cfg), max=ceiling)
    return current - _prev(env, "height_progress", current)


def com_upward_velocity(
    env: ManagerBasedRlEnv,
    max_height: float,
    gate_tilt_above_deg: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Pay for upward trunk velocity while the robot is tilted.

    Gated on tilt for the same reason as :func:`tilted_mask`, and capped in height
    so a walking gait whose trunk passes the ceiling every step earns nothing.
    """
    asset = _asset(env, asset_cfg)
    vz = asset.data.root_link_lin_vel_w[:, 2]
    below = _trunk_height(env, asset_cfg) < max_height
    return torch.clamp(vz, min=0.0) * below.float() * tilted_mask(
        env, gate_tilt_above_deg, asset_cfg
    ).float()


def recovery_success(
    env: ManagerBasedRlEnv,
    fallen_tilt_deg: float,
    up_tilt_deg: float,
    up_z: float,
    min_fallen_s: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """One-shot bounty the frame a fallen robot becomes genuinely upright.

    Requires having been fallen for ``min_fallen_s`` and re-arms only on a new
    fall, so oscillating around the gate is not a way to collect it repeatedly.
    """
    fallen = tilted_mask(env, fallen_tilt_deg, asset_cfg)
    up = (_tilt_cos(env, asset_cfg) > math.cos(math.radians(up_tilt_deg))) & (
        _trunk_height(env, asset_cfg) > up_z
    )

    timer = getattr(env, "_ht_fallen_timer_bounty", None)
    if timer is None or timer.shape != fallen.shape:
        timer = torch.zeros_like(fallen, dtype=torch.float)
        env._ht_fallen_timer_bounty = timer
    armed = getattr(env, "_ht_bounty_armed", None)
    if armed is None or armed.shape != fallen.shape:
        armed = torch.zeros_like(fallen)
        env._ht_bounty_armed = armed

    timer = torch.where(fallen, timer + env.step_dt, torch.zeros_like(timer))
    armed = armed | (timer >= min_fallen_s)
    paid = armed & up
    armed = torch.where(paid, torch.zeros_like(armed), armed)
    env._ht_fallen_timer_bounty = timer
    env._ht_bounty_armed = armed
    return paid.float()


def fallen_tax(
    env: ManagerBasedRlEnv,
    gate_tilt_above_deg: float,
    release_tilt_deg: float,
    release_z: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Constant cost while fallen, with hysteresis on the way out.

    The hysteresis matters: with a single gate a deep crouch just past the
    threshold is a free resting pose, and the policy learns to stop there instead
    of finishing the stand.
    """
    fallen = tilted_mask(env, gate_tilt_above_deg, asset_cfg)
    released = (
        _tilt_cos(env, asset_cfg) > math.cos(math.radians(release_tilt_deg))
    ) & (_trunk_height(env, asset_cfg) > release_z)

    state = getattr(env, "_ht_fallen_tax_state", None)
    if state is None or state.shape != fallen.shape:
        state = torch.zeros_like(fallen)
        env._ht_fallen_tax_state = state
    state = torch.where(released, torch.zeros_like(state), state)
    state = state | fallen
    env._ht_fallen_tax_state = state
    return state.float()


# ---------- magnitude costs (negative weight in the config) ----------


def body_impact_cost(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    threshold_n: float,
) -> torch.Tensor:
    """Contact force above ``threshold_n`` on the given sensor, in newtons.

    The threshold is what makes the term useful. A constant force reading is not
    an impact: bracing on the ground to get up is a quasi-static push worth a
    fraction of body weight, while the spike that strips a gear is many times
    that. Pricing everything means paying the robot for the method that works.
    """
    sensor = env.scene[sensor_name]
    force = sensor.data.force
    if force.dim() == 3:
        magnitude = torch.norm(force, dim=-1).sum(dim=-1)
    else:
        magnitude = torch.norm(force, dim=-1)
    return torch.clamp(magnitude - threshold_n, min=0.0)


def trunk_vertical_accel_penalty(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``-|a_z|`` of the trunk: POSITIVE weight in the config.

    The function already returns a negative value. A negative weight double
    negates it into a reward for vertical shocks, which is how upstream produced a
    "butt-hopping, crash-sitting" policy whose three biggest positive reward terms
    were its three gentleness penalties.
    """
    asset = _asset(env, asset_cfg)
    vz = asset.data.root_link_lin_vel_w[:, 2]
    previous = _prev(env, "trunk_vz", vz)
    accel = (vz - previous) / env.step_dt
    return -torch.abs(accel)


def trunk_downward_velocity_penalty(
    env: ManagerBasedRlEnv,
    max_down_vel: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``-max(-vz - cap, 0)``: a per-step price on descending faster than the cap.

    Charging every step is what makes the cap bite. An acceleration-only penalty
    cannot see a constant-velocity drop (``a_z`` is zero the whole way), so a fast
    descent would cost the same as a slow one.
    """
    asset = _asset(env, asset_cfg)
    vz = asset.data.root_link_lin_vel_w[:, 2]
    return -torch.clamp(-vz - max_down_vel, min=0.0)


def action_rate_l2_fallen_scaled(
    env: ManagerBasedRlEnv,
    fallen_scale: float,
    gate_tilt_above_deg: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Action-rate cost, cheaper while fallen.

    At full weight the smoothness tax is the single largest cost in the stack, so
    a lying robot that does nothing is strictly better than one that tries to get
    up and fails. Scaling it down only while tilted keeps the walking gait's
    smoothness intact and makes an attempt affordable.
    """
    rate = torch.sum(
        torch.square(env.action_manager.action - env.action_manager.prev_action), dim=1
    )
    fallen = tilted_mask(env, gate_tilt_above_deg, asset_cfg)
    return rate * torch.where(
        fallen,
        torch.full_like(rate, fallen_scale),
        torch.ones_like(rate),
    )


def head_pose_tracking(
    env: ManagerBasedRlEnv,
    command_name: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Per-joint Gaussian on head pose error, averaged over the four head joints.

    The mean, not the sum or a product, so that a single joint that cannot reach
    its command still leaves a gradient for the other three.
    """
    command = env.command_manager.get_command(command_name)
    assert command is not None
    asset = _asset(env, asset_cfg)
    default = asset.data.default_joint_pos
    assert default is not None
    ids = _joint_ids(env, asset_cfg)
    target = default[:, ids] + command
    error = asset.data.joint_pos[:, ids] - target
    return torch.exp(-torch.square(error) / std**2).mean(dim=-1)
