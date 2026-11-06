# Copyright (c) 2026-2027 zh
"""HT前收脚坐站基础任务，使用独立的终点奖励与有效重置初态。

参考 microduck_rl@bae39f59 的坐站命令和姿态奖励；HT 的膝行程无法逐段复制官方腿形。
本地修复依据见设计T060；现有SitStand和官方移植MDP保持独立。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import RewardTermCfg
from mjlab.managers.metrics_manager import MetricsTermCfg

from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_sitstand_env_cfg import (
    make_sitstand_env_cfg,
)
from ht_microduck.tasks.mdp import forward_posture as forward

# HT 模型+X为前。对177个候选执行真实动作保持8秒；当前候选末2秒倾角约1.46°、根高约.05635m。
# 这是仿真固定目标保持结果，不是官方几何姿态、实机标定或策略收敛结论。
FORWARD_SITTING_JOINT_POS: dict[str, float] = {
    "r_hip_pitch_joint": -1.55,
    "l_hip_pitch_joint": -1.55,
    "r_calf_joint": -0.40,
    "l_calf_joint": -0.40,
    "r_ankle_joint": 0.0,
    "l_ankle_joint": 0.0,
    "r_hip_roll_joint": 0.0873,
    "l_hip_roll_joint": -0.0873,
}
FORWARD_SIT_Z: float = 0.0564


def make_sitstand_forward_env_cfg(
    num_envs: int = 4096,
    seed: int | None = None,
    play: bool = False,
    *,
    rough: bool = False,
    bound_targets: bool = True,
) -> ManagerBasedRlEnvCfg:
    """先学习基础坐站，保留原动作/观测接口与小范围头部指令。"""
    cfg = make_sitstand_env_cfg(num_envs, seed, play, rough=rough, bound_targets=bound_targets)
    overrides = {
        C.POLICY_JOINT_NAMES.index(name): value
        for name, value in FORWARD_SITTING_JOINT_POS.items()
    }
    # 移除可被部分完成或倒地减少误差代价利用的独立项，姿态和高度统一用非负跟踪。
    for name in ("posture_pose_l1", "posture_height_sharp", "posture_height_l1"):
        del cfg.rewards[name]
    for name in ("posture_pose_legs", "posture_composite"):
        cfg.rewards[name].params["sit_overrides"] = overrides.copy()
    for name in (
        "posture_height", "posture_stillness", "posture_composite",
    ):
        cfg.rewards[name].params["sit_z"] = FORWARD_SIT_Z
    cfg.commands["twist"].sit_z = FORWARD_SIT_Z
    reset = cfg.events["set_ground_state"].params
    reset["sitting_joint_overrides"] = overrides.copy()
    reset["sitting_z_min"] = FORWARD_SIT_Z
    reset["sitting_z_max"] = FORWARD_SIT_Z + 0.015
    # 保留官方坐/站高度区间中的相对门限，起立终点和1cm bootstrap余量仍使用HT站高。
    height_scale = (C.STAND_Z - FORWARD_SIT_Z) / (0.115 - 0.060)
    upright = cfg.rewards["upright_while_tall"].params
    upright["height_low"] = FORWARD_SIT_Z + (0.075 - 0.060) * height_scale
    upright["height_high"] = FORWARD_SIT_Z + (0.100 - 0.060) * height_scale
    cfg.rewards["posture_pose_legs"].func = forward.forward_pose_match
    cfg.rewards["posture_pose_legs"].weight = 8.0
    # 目标正分已有共同直立门控；适中的常驻项允许短暂倾斜后进入前坐。
    cfg.rewards["upright_linear"].weight = 2.5
    for name, func in (
        ("posture_height", forward.forward_height_match),
        ("posture_stillness", forward.forward_stillness),
    ):
        cfg.rewards[name].func = func
        cfg.rewards[name].params["sit_overrides"] = overrides.copy()
    cfg.rewards["posture_height"].weight = 4.0
    cfg.rewards["posture_height"].params["std"] = (C.STAND_Z - FORWARD_SIT_Z) / 2.0
    cfg.rewards["posture_composite"].func = forward.forward_composite
    cfg.rewards["upright_while_tall"].func = forward.forward_upright_while_tall
    cfg.rewards["upright_while_tall"].params["command_name"] = "twist"
    cfg.rewards["forward_action_limit_error"] = RewardTermCfg(
        func=forward.forward_action_limit_error, weight=-2.0,
    )
    cfg.events["set_ground_state"].func = forward.bounded_forward_ground_state
    reset["sitting_joint_noise_std"] = 0.02
    # 先验收基础坐站，再另开强化阶段；不由固定迭代号假定已经学会前坐。
    for name in ("push_robot", "seated_tip", "seated_head_jerk"):
        del cfg.events[name]
    cfg.curriculum = {}
    cfg.metrics["forward_sit_command_frames"] = MetricsTermCfg(func=forward.forward_sit_command_frames)
    cfg.metrics["forward_sit_success_frames"] = MetricsTermCfg(
        func=forward.forward_sit_success_frames,
        params={"command_name": "twist", "sit_overrides": overrides.copy(), "sit_z": FORWARD_SIT_Z},
    )
    return cfg
