"""Posture MDP terms shared by the stand-up, sit-stand and vel-stand tasks.

Each function here is a reward, termination, event or command term that the
posture tasks need and the walking task does not. Three families live side by
side:

- **Potential-based progress** (``upright_progress``, ``height_progress``). These
  return the *change* in a bounded quantity between consecutive steps, so a
  stationary robot earns exactly zero no matter which pose it holds. That is what
  makes them safe: an absolute reward for "be upright and tall" also pays a robot
  that is already upright, while a reward for *becoming* more upright cannot be
  farmed by holding still. Every upstream run that awarded a positive term gated
  on a bad state ended up farming that state (sitting, lying flat, or bracing on
  the head at 55 degrees).

- **Cost terms** (``body_impact_cost``, ``*_penalty``). These return a
  non-negative magnitude, so the task config must give them a **negative**
  weight. The exceptions whose function already returns a negative value are
  marked ``POSITIVE weight`` at the call site; writing a negative weight there
  flips a penalty into a reward for the exact behaviour it penalises. That sign
  bug shipped twice upstream (a violent "crash sit" policy and a bouncing
  get-up), so the convention is restated wherever it matters.

- **Command terms** (``SitStandCommand``). A posture flag in the twist command's
  first slot, with a slewed internal target: see the class docstring for why the
  slew is the anti-crash mechanism rather than a nicety.

All state reads go through ``Entity.data`` and every joint selection goes through
``SceneEntityCfg`` name resolution, so the terms stay valid when the joint set or
the actuator model changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity.mdp import (
    UniformVelocityCommand,
    UniformVelocityCommandCfg,
    feet_air_time,
)

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


def _slot_of(asset: Entity, ids: list[int], joint_name: str) -> int:
    """Position of ``joint_name`` inside a joint selection.

    Reward terms address joints by name rather than by position on purpose: the policy
    joint order and the model's joint order are different lists, and an index computed
    against one applied to the other silently drives the wrong joint.
    """
    global_index = asset.joint_names.index(joint_name)
    return ids.index(global_index)


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


def fallen_mask(
    env: ManagerBasedRlEnv,
    gate_z_below: float,
    gate_tilt_above_deg: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Environments that are both low **and** tilted: i.e. genuinely fallen.

    The two gates are ANDed, and that is not a detail. On this robot the seated keyframe
    (0.0563 m) is *lower* than every lying posture (0.060-0.093 m), so "low" cannot mean
    "fallen": the conjunction is what keeps the goal state of the sit task from being
    classified as a failure. Height alone would also let a seated robot open a recovery
    reward, which is how upstream taught a policy to sit down and bob instead of
    standing up.

    Tilt is the discriminating signal (1.3 deg seated, 4.3 deg standing, >=79 deg in
    every measured fall), so in practice this is a tilt test with a penetration guard.
    """
    low = _trunk_height(env, asset_cfg) < gate_z_below
    limit = torch.deg2rad(
        torch.tensor(gate_tilt_above_deg, device=env.device, dtype=torch.float)
    )
    return low & (_tilt_rad(env, asset_cfg) > limit)


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


def trunk_upward_velocity_penalty(
    env: ManagerBasedRlEnv,
    max_up_vel: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``-max(vz - cap, 0)``: the rising counterpart, deliberately looser."""
    asset = _asset(env, asset_cfg)
    vz = asset.data.root_link_lin_vel_w[:, 2]
    return -torch.clamp(vz - max_up_vel, min=0.0)


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


# ---------- posture commands ----------


@dataclass(kw_only=True)
class SitStandCommandCfg(UniformVelocityCommandCfg):
    """Command term config for a posture flag rather than a velocity.

    ``ranges`` is inherited but unused: the flag is sampled from ``sit_prob`` and the
    other two components are held at zero, so the twist slot keeps its 3-wide shape.
    """

    sit_prob: float = 0.5
    ramp_s: float = 2.0
    sit_z: float = 0.075
    stand_z: float = 0.1534

    def build(self, env: ManagerBasedRlEnv) -> "SitStandCommand":
        return SitStandCommand(self, env)


class SitStandCommand(UniformVelocityCommand):
    """Posture command: ``cmd = [sit_flag, 0, 0]`` with a slewed internal target.

    ``sit_flag`` is binary (0 = stand, 1 = sit) and is what the observation
    carries, so the deployed runtime writes a plain 0 or 1. ``alpha`` is the
    internal target blend and slews towards the flag at a constant rate, taking
    ``ramp_s`` for a full transition; the posture rewards track ``alpha``, not the
    flag.

    The slew is the anti-crash mechanism, not a smoothing nicety. With a binary
    target, arriving early collects the whole goal-state payout for every step
    saved, while a speed-cap penalty only integrates a bounded excess-distance
    cost — measured upstream, dropping instantly beat a one-second descent by
    about seven times, and the policy learned to slam down. With a moving target,
    being *ahead* of the ramp scores near zero on the height and composite terms,
    so following the slow setpoint is the best available strategy.
    """

    cfg: SitStandCommandCfg

    def __init__(self, cfg: SitStandCommandCfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._alpha = torch.zeros(self.num_envs, device=self.device)
        # Draws handed over by the reset event. The reset event runs *before*
        # ``command_manager.reset``, so it cannot write the flag directly (it would be
        # discarded) and cannot read it either (it would still hold the previous
        # episode's value). Instead it draws the flag and invites this term to replay
        # that draw, which keeps the spawn pose and the command consistent without
        # depending on manager ordering. ``-1`` means "no draw pending".
        self.pending_sit_flag = torch.full(
            (self.num_envs,), -1.0, device=self.device
        )

    @property
    def command(self) -> torch.Tensor:
        return self.vel_command_b

    @property
    def alpha(self) -> torch.Tensor:
        """Slewed target blend: 0 = stand target, 1 = sit target."""
        return self._alpha

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        if len(env_ids) == 0:
            return
        pending = self.pending_sit_flag[env_ids]
        drawn = torch.rand(len(env_ids), device=self.device) < self.cfg.sit_prob
        # Replay a hand-off where the reset event supplied one; draw otherwise.
        sit = torch.where(pending >= 0.0, pending, drawn.float())
        self.pending_sit_flag[env_ids] = -1.0
        self.vel_command_b[env_ids] = 0.0
        self.vel_command_b[env_ids, 0] = sit

    def _alpha_from_height(self) -> torch.Tensor:
        """Target blend that matches the trunk's actual height right now.

        A seated spawn must not be dragged upward by a stand-initialised ramp, so
        the blend starts where the robot really is.
        """
        asset = self.robot
        origins = self._env.scene.env_origins[:, 2]
        z = torch.nan_to_num(
            asset.data.root_link_pos_w[:, 2] - origins, nan=self.cfg.stand_z
        )
        span = max(self.cfg.stand_z - self.cfg.sit_z, 1e-6)
        return torch.clamp((self.cfg.stand_z - z) / span, 0.0, 1.0)

    def compute(self, dt: float, env_ids: torch.Tensor | None = None) -> None:
        super().compute(dt, env_ids)
        # The spawn state is only in place on the first compute of an episode:
        # the command manager resets before the ground-state event teleports the
        # robot, so reading the height at reset time reads the pre-teleport pose.
        fresh = self._env.episode_length_buf <= 1
        if fresh.any():
            self._alpha = torch.where(fresh, self._alpha_from_height(), self._alpha)
        step = dt / max(self.cfg.ramp_s, 1e-6)
        delta = self.vel_command_b[:, 0] - self._alpha
        self._alpha += torch.clamp(delta, -step, step)

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        """No heading controller and no standing-env machinery: the flag is it."""
        del env_ids

    def _update_metrics(self) -> None:
        """No velocity tracking metrics for a posture flag."""


def posture_blend(env: ManagerBasedRlEnv, command_name: str) -> torch.Tensor:
    """Target blend in ``[0, 1]`` (0 = stand, 1 = sit) for the posture rewards."""
    term = env.command_manager.get_term(command_name)
    alpha = getattr(term, "alpha", None)
    if alpha is not None:
        return alpha
    return env.command_manager.get_command(command_name)[:, 0]


def posture_targets(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict[str, float],
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> tuple[torch.Tensor, torch.Tensor]:
    """``(blend, per-env joint target)`` for the commanded posture.

    The stand target is HOME and the sit target is HOME with the overrides
    applied; the slewed blend interpolates between them, so mid-ramp the rewarded
    pose folds in step with the descending height.
    """
    blend = posture_blend(env, command_name)
    asset = _asset(env, asset_cfg)
    default = asset.data.default_joint_pos
    assert default is not None
    ids = _joint_ids(env, asset_cfg)
    stand = default[:, ids]
    sit = stand.clone()
    # sit_overrides is keyed by joint *name* (see contract.LOW_POSTURE_JOINT_POS): the
    # policy joint order is a task-level decision, so index-based keys would silently
    # apply a knee angle to a hip if the order ever changed.
    for name, value in sit_overrides.items():
        sit[:, _slot_of(asset, ids, name)] = value
    target = stand + blend.unsqueeze(-1) * (sit - stand)
    return blend, target


def posture_height_target(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
) -> torch.Tensor:
    """Trunk height target that moves with the blend."""
    blend = posture_blend(env, command_name)
    return stand_z + blend * (sit_z - stand_z)


def posture_height_gaussian(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Gaussian around the *commanded* trunk height."""
    target = posture_height_target(env, command_name, sit_z, stand_z)
    error = _trunk_height(env, asset_cfg) - target
    return torch.exp(-torch.square(error) / std**2)


def posture_height_l1(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``-|z - z*|`` against the commanded height: POSITIVE weight in the config.

    With a small weight the static error of ignoring the command is cheap enough
    to live with, and "stay seated" becomes a local optimum that never rises. The
    per-step cost has to be larger than the whole posture reward stack.
    """
    target = posture_height_target(env, command_name, sit_z, stand_z)
    return -torch.abs(_trunk_height(env, asset_cfg) - target)


def posture_pose_match(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict[str, float],
    std: float,
    joint_indices: tuple[int, ...] | None = None,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Per-joint Gaussian on the error against the commanded joint target."""
    _, target = posture_targets(env, command_name, sit_overrides, asset_cfg)
    asset = _asset(env, asset_cfg)
    ids = _joint_ids(env, asset_cfg)
    error = asset.data.joint_pos[:, ids] - target
    if joint_indices is not None:
        index = torch.as_tensor(joint_indices, device=env.device, dtype=torch.long)
        error = error.index_select(-1, index)
    return torch.exp(-torch.square(error) / std**2).mean(dim=-1)


def posture_pose_l1(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict[str, float],
    joint_indices: tuple[int, ...] | None = None,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """``-mean|q - q*|``: POSITIVE weight in the config."""
    _, target = posture_targets(env, command_name, sit_overrides, asset_cfg)
    asset = _asset(env, asset_cfg)
    ids = _joint_ids(env, asset_cfg)
    error = asset.data.joint_pos[:, ids] - target
    if joint_indices is not None:
        index = torch.as_tensor(joint_indices, device=env.device, dtype=torch.long)
        error = error.index_select(-1, index)
    return -error.abs().mean(dim=-1)


def posture_stillness(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
    band_full: float,
    band_zero: float,
    vel_std: float,
    tilt_full_deg: float,
    tilt_zero_deg: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward resting *quietly, upright, at the commanded height, after the ramp*.

    Four gates, each closing a specific exploit:

    - height band: otherwise a robot lying inside the seated height band scores,
    - tilt gate: the same, for a robot on its back,
    - speed term: "still" has to mean still,
    - ramp completion: during the transition this pays nothing, so it cannot
      compete with the transition it is supposed to reward the end of.
    """
    blend = posture_blend(env, command_name)
    target = posture_height_target(env, command_name, sit_z, stand_z)
    z_error = (_trunk_height(env, asset_cfg) - target).abs()
    z_gate = 1.0 - _smoothstep(z_error, band_full, band_zero)

    asset = _asset(env, asset_cfg)
    speed = torch.norm(asset.data.root_link_lin_vel_w, dim=-1)
    still = torch.exp(-torch.square(speed / vel_std))

    cos_full = torch.cos(torch.deg2rad(
        torch.tensor(tilt_full_deg, device=env.device, dtype=torch.float)
    ))
    cos_zero = torch.cos(torch.deg2rad(
        torch.tensor(tilt_zero_deg, device=env.device, dtype=torch.float)
    ))
    tilt_gate = _smoothstep(_tilt_cos(env, asset_cfg), float(cos_zero), float(cos_full))

    flag = env.command_manager.get_command(command_name)[:, 0]
    ramp_done = ((flag - blend).abs() < 0.02).float()
    return still * z_gate * tilt_gate * ramp_done


def posture_composite(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict[str, float],
    sit_z: float,
    stand_z: float,
    height_std: float,
    upright_std: float,
    pose_std: float,
    joint_indices: tuple[int, ...] | None = None,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Multiplicative goal score: every factor must hold for the product to pay.

    A product rather than a sum is what removes the partial-credit exploits: a
    sum lets a robot collect the height and pose terms while braced on its head at
    55 degrees, because each term is satisfied on its own.
    """
    target = posture_height_target(env, command_name, sit_z, stand_z)
    height = torch.exp(
        -torch.square(_trunk_height(env, asset_cfg) - target) / height_std**2
    )
    tilt_sq = 2.0 * (1.0 - _tilt_cos(env, asset_cfg))
    upright = torch.exp(-tilt_sq / upright_std**2)
    _, pose_target = posture_targets(env, command_name, sit_overrides, asset_cfg)
    asset = _asset(env, asset_cfg)
    ids = _joint_ids(env, asset_cfg)
    error = asset.data.joint_pos[:, ids] - pose_target
    if joint_indices is not None:
        index = torch.as_tensor(joint_indices, device=env.device, dtype=torch.long)
        error = error.index_select(-1, index)
    pose = torch.exp(-torch.square(error).mean(dim=-1) / pose_std**2)
    return height * upright * pose


def posture_rise_bootstrap(
    env: ManagerBasedRlEnv,
    command_name: str,
    max_height: float,
    max_vz: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Pay for the *motion* of rising, not just for the destination.

    A goal-only reward has zero gradient at zero motion, so "stay seated and eat
    the L1" is a local optimum the policy can sit in forever. This term makes any
    rise attempt immediately positive. ``max_vz`` caps the payout so an explosive
    launch cannot out-earn a gentle one, and the term is zero under a sit command
    so it never fights the descent.
    """
    asset = _asset(env, asset_cfg)
    vz = asset.data.root_link_lin_vel_w[:, 2]
    below = _trunk_height(env, asset_cfg) < max_height
    sit = env.command_manager.get_command(command_name)[:, 0]
    return torch.clamp(vz, min=0.0, max=max_vz) * below.float() * (1.0 - sit)


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
