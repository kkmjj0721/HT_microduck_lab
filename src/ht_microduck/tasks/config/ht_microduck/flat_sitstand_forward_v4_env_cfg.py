# Copyright (c) 2026-2027 zh
"""独立的v4前坐初态课程，保留v3工厂作为原配方对照。"""

from mjlab.managers import EventTermCfg
from mjlab.managers.metrics_manager import MetricsTermCfg

from ht_microduck.tasks.config.ht_microduck.flat_sitstand_forward_env_cfg import (
    make_sitstand_forward_env_cfg,
)
from ht_microduck.tasks.mdp.forward_behavior import (
    ForwardHoldDuration,
    forward_case_frames,
    forward_case_success_frames,
)
from ht_microduck.tasks.mdp.forward_commands import (
    ForwardCurriculumCommand,
    ForwardCurriculumCommandCfg,
)
from ht_microduck.tasks.mdp.forward_events import (
    forward_transition_reward,
    reset_forward_curriculum,
)
from ht_microduck.tasks.mdp.forward_initialization import (
    ForwardInitializedJointPositionActionCfg,
)


def make_sitstand_forward_v4_env_cfg(num_envs: int = 4096, seed: int | None = None, play: bool = False):
    """只更换初态/命令及度量，阶段通过twist配置显式选择。"""
    cfg = make_sitstand_forward_env_cfg(num_envs, seed, play)
    cfg.commands["twist"] = ForwardCurriculumCommandCfg(**{
        **vars(cfg.commands["twist"]), "class_type": ForwardCurriculumCommand,
    })
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.actions["joint_pos"] = ForwardInitializedJointPositionActionCfg(**vars(cfg.actions["joint_pos"]))
    cfg.events["set_ground_state"] = EventTermCfg(func=reset_forward_curriculum, mode="reset")
    for name in ("reset_base", "reset_robot_joints", "reset_action_history"):
        del cfg.events[name]
    for name in ("rise_bootstrap", "descent_speed", "rise_speed", "gentle_motion"):
        term = cfg.rewards[name]
        term.params = {"reward_func": term.func, **term.params}
        term.func = forward_transition_reward
    cfg.metrics["forward_hold_seconds"] = MetricsTermCfg(func=ForwardHoldDuration, reduce="max")
    for initial_sit, target_sit, label in ((False, False, "stand_hold"), (True, True, "sit_hold"), (False, True, "sit_transition"), (True, False, "rise_transition")):
        params = {"initial_sit": initial_sit, "target_sit": target_sit}
        cfg.metrics[f"forward_{label}_frames"] = MetricsTermCfg(func=forward_case_frames, params=params)
        cfg.metrics[f"forward_{label}_valid_frames"] = MetricsTermCfg(func=forward_case_success_frames, params=params)
    return cfg
