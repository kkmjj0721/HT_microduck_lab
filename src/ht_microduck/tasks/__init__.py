"""通过 mjlab.tasks entry point 注册 HT 任务及动作约束对照，并校验接口。

配置位于 config/，全部 MDP 位于 mdp/，runner 适配位于 rl/。
四个官方配方使用 61 维 actor、14 维动作；Velocity critic 为76维，StandUp/SitStand为74维。
用户要求保留的 VelStand 使用旧61/64/14与原共享MDP，构造其他任务不能改变其配置。
"""

from __future__ import annotations

from copy import deepcopy

from mjlab.tasks.registry import register_mjlab_task

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_env_cfg import make_sitstand_env_cfg
from ht_microduck.tasks.config.flat_standup_env_cfg import make_standup_env_cfg
from ht_microduck.tasks.config.flat_velocity_env_cfg import make_flat_velocity_env_cfg
from ht_microduck.tasks.config.flat_velocity_head_env_cfg import (
    make_flat_velocity_head_env_cfg,
)
from ht_microduck.tasks.config.flat_velstand_env_cfg import make_velstand_env_cfg
from ht_microduck.tasks.config.rl_cfg import (
    FlatVelocityRlCfg,
    SitStandRlCfg,
    StandUpRlCfg,
    VelocityHeadRlCfg,
    VelStandRlCfg,
)
from ht_microduck.tasks.rl.runner import (
    OfficialTaskOnPolicyRunner,
    VelocityHeadOnPolicyRunner,
)

FLAT_VELOCITY_TASK_ID = "HtDuck-Flat-Velocity"
FLAT_VELOCITY_HEAD_TASK_ID = "HtDuck-Flat-Velocity-Head"
FLAT_STANDUP_TASK_ID = "HtDuck-Flat-StandUp"
FLAT_SITSTAND_TASK_ID = "HtDuck-Flat-SitStand"
FLAT_VELSTAND_TASK_ID = "HtDuck-Flat-VelStand"
FLAT_SITSTAND_UNBOUNDED_TASK_ID = "HtDuck-Flat-SitStand-Unbounded"
FLAT_VELSTAND_UNBOUNDED_TASK_ID = "HtDuck-Flat-VelStand-Unbounded"

register_mjlab_task(
    task_id=FLAT_VELOCITY_TASK_ID,
    env_cfg=make_flat_velocity_env_cfg(),
    play_env_cfg=make_flat_velocity_env_cfg(play=True),
    rl_cfg=FlatVelocityRlCfg,
    runner_cls=OfficialTaskOnPolicyRunner,
)

register_mjlab_task(
    task_id=FLAT_VELOCITY_HEAD_TASK_ID,
    env_cfg=make_flat_velocity_head_env_cfg(),
    play_env_cfg=make_flat_velocity_head_env_cfg(play=True),
    rl_cfg=VelocityHeadRlCfg,
    runner_cls=VelocityHeadOnPolicyRunner,
)

register_mjlab_task(
    task_id=FLAT_STANDUP_TASK_ID,
    env_cfg=make_standup_env_cfg(),
    play_env_cfg=make_standup_env_cfg(play=True),
    rl_cfg=StandUpRlCfg,
    runner_cls=OfficialTaskOnPolicyRunner,
)

register_mjlab_task(
    task_id=FLAT_SITSTAND_TASK_ID,
    env_cfg=make_sitstand_env_cfg(),
    play_env_cfg=make_sitstand_env_cfg(play=True),
    rl_cfg=SitStandRlCfg,
    runner_cls=OfficialTaskOnPolicyRunner,
)

register_mjlab_task(
    task_id=FLAT_VELSTAND_TASK_ID,
    env_cfg=make_velstand_env_cfg(),
    play_env_cfg=make_velstand_env_cfg(play=True),
    rl_cfg=VelStandRlCfg,
    runner_cls=OfficialTaskOnPolicyRunner,
)

# 显式对照任务让官方训练与回放入口使用同一原目标语义，避免回放额外解析配置。
for _baseline_id, _factory, _rl in (
    (FLAT_SITSTAND_UNBOUNDED_TASK_ID, make_sitstand_env_cfg, SitStandRlCfg),
    (FLAT_VELSTAND_UNBOUNDED_TASK_ID, make_velstand_env_cfg, VelStandRlCfg),
):
    _baseline_rl = deepcopy(_rl)
    _baseline_rl.experiment_name += "_unbounded"
    _baseline_rl.run_name += "_unbounded"
    register_mjlab_task(
        task_id=_baseline_id,
        env_cfg=_factory(bound_targets=False),
        play_env_cfg=_factory(play=True, bound_targets=False),
        rl_cfg=_baseline_rl,
        runner_cls=OfficialTaskOnPolicyRunner,
    )
del _baseline_id, _factory, _rl, _baseline_rl


def _assert_task_contract(task_id: str, env_cfg) -> None:
    """Check one registry entry against the frozen contract, statically.

    This runs at import time, before any environment exists, so it can only inspect the
    configuration: the action width, the observation term order and the declared widths
    of the command slots. That is enough to catch the mistakes that actually happen — a
    task narrowing a command slot (which silently shortens the actor vector) or dropping
    an observation term.
    """
    action = env_cfg.actions["joint_pos"]
    if tuple(action.actuator_names) != C.POLICY_JOINT_NAMES:
        raise ValueError(
            f"{task_id}: action joint order does not match the contract"
        )
    terms = tuple(env_cfg.observations["actor"].terms)
    if terms != C.ACTOR_OBSERVATION_TERMS:
        raise ValueError(
            f"{task_id}: actor terms {terms} do not match the contract order "
            f"{C.ACTOR_OBSERVATION_TERMS}"
        )
    if tuple(env_cfg.observations["critic"].terms) != C.critic_observation_terms(task_id):
        raise ValueError(f"{task_id}: critic observation order does not match its contract")
    # A command-driven slot must resolve to a command term of the declared width.
    for slot, width in (
        ("command", 3),
        ("head_command", 4),
        ("body_command", 6),
    ):
        term = env_cfg.observations["actor"].terms[
            C.ACTOR_OBSERVATION_TERMS[C.ACTOR_OBSERVATION_TERMS.index(slot)]
        ]
        params = getattr(term, "params", {}) or {}
        name = params.get("command_name")
        if name is None:
            # A padded slot: it must declare exactly the width the contract fixes,
            # since nothing else ever reads it.
            declared_padding = params.get("dim", getattr(term, "padding_dim", None))
            if declared_padding != width:
                raise ValueError(
                    f"{task_id}: padded slot {slot!r} is {declared_padding}-wide but "
                    f"the contract needs {width}"
                )
            continue
        command = env_cfg.commands[name]
        declared = getattr(command, "dim", None)
        if declared is not None and declared != width:
            raise ValueError(
                f"{task_id}: command {name!r} is {declared}-wide but slot {slot!r} needs "
                f"{width}"
            )


for _task_id, _env_cfg in (
    (FLAT_VELOCITY_TASK_ID, make_flat_velocity_env_cfg(num_envs=1)),
    (FLAT_VELOCITY_HEAD_TASK_ID, make_flat_velocity_head_env_cfg(num_envs=1)),
    (FLAT_STANDUP_TASK_ID, make_standup_env_cfg(num_envs=1)),
    (FLAT_SITSTAND_TASK_ID, make_sitstand_env_cfg(num_envs=1)),
    (FLAT_VELSTAND_TASK_ID, make_velstand_env_cfg(num_envs=1)),
    (FLAT_SITSTAND_UNBOUNDED_TASK_ID, make_sitstand_env_cfg(num_envs=1, bound_targets=False)),
    (FLAT_VELSTAND_UNBOUNDED_TASK_ID, make_velstand_env_cfg(num_envs=1, bound_targets=False)),
):
    _assert_task_contract(_task_id, _env_cfg)
del _task_id, _env_cfg

__all__ = [
    "FLAT_SITSTAND_TASK_ID",
    "FLAT_STANDUP_TASK_ID",
    "FLAT_VELOCITY_HEAD_TASK_ID",
    "FLAT_VELOCITY_TASK_ID",
    "FLAT_VELSTAND_TASK_ID",
    "FLAT_SITSTAND_UNBOUNDED_TASK_ID",
    "FLAT_VELSTAND_UNBOUNDED_TASK_ID",
]
