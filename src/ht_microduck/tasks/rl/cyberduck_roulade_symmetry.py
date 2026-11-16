# Copyright (c) 2026-2027 zh
"""
内容：
    按 CyberDuck V2 的关节轴和 HOME 偏置构造前滚翻策略的左右镜像。

来源：microduck_rl@bae39f59/tasks/symmetry.py，Apache-2.0。
仅用于官方的镜像损失，不启用 critic 数据增强；本体细小几何不对称仍属于仿真适配假设。
"""

from __future__ import annotations

import torch
from tensordict import TensorDict

from ht_microduck.robot.cyberduck_v2_constants import HOME_JOINT_POS
from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_actions import RouladePositionAction

_PERM = (4, 5, 6, 7, 0, 1, 2, 3, 8, 9, 10, 11, 13, 12)
_SIGN = (-1, -1, 1, 1, -1, -1, 1, 1, 1, 1, -1, -1, 1, 1)


def mirror_roulade(env, obs: TensorDict | None, actions: torch.Tensor | None):
    """返回原样本与镜像样本；相对 HOME 的位置和动作先恢复绝对目标再反射。"""
    reference = obs["actor"] if obs is not None else actions
    if reference is None:
        return None, None
    perm = torch.tensor(_PERM, device=reference.device)
    sign = reference.new_tensor(_SIGN)
    home = reference.new_tensor([HOME_JOINT_POS[name] for name in C.POSITION_JOINTS])
    shift = home[perm[:12]] * sign[:12] - home
    action_shift = torch.cat((shift / C.POSITION_SCALE, reference.new_zeros(2)))
    if env is not None:
        position = env.unwrapped.action_manager.get_term("joint_pos")
        if isinstance(position, RouladePositionAction):
            bias = position.latent_offset[0].to(device=reference.device, dtype=reference.dtype)
            action_shift[:12] = bias[perm[:12]] * sign[:12] - bias
    augmented_obs = None
    if obs is not None:
        actor = obs["actor"]
        mirrored = actor.clone()
        mirrored[:, :3] *= actor.new_tensor((-1, 1, -1))
        mirrored[:, 3:6] *= actor.new_tensor((1, -1, 1))
        mirrored[:, 6:18] = actor[:, 6:18][:, perm[:12]] * sign[:12] + shift
        mirrored[:, 18:32] = actor[:, 18:32][:, perm] * sign
        mirrored[:, 32:46] = actor[:, 32:46][:, perm] * sign + action_shift
        augmented_obs = TensorDict(
            {name: torch.cat((value, mirrored if name == "actor" else value), dim=0)
             for name, value in obs.items()},
            batch_size=[actor.shape[0] * 2],
            device=actor.device,
        )
    augmented_actions = None
    if actions is not None:
        augmented_actions = torch.cat((actions, actions[:, perm] * sign + action_shift), dim=0)
    return augmented_obs, augmented_actions
