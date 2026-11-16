# Copyright (c) 2026-2027 zh
"""HT 后空翻检查点契约：拒绝不同观测/动作语义的权重。

沿用现有 PPO runner；只在保存时写入接口指纹，加载时先核对再调用基类。
"""

from __future__ import annotations

import torch

from ht_microduck.tasks import ht_microduck_backflip_contract as C
from ht_microduck.tasks.rl.runner import OfficialTaskOnPolicyRunner


class HtBackflipOnPolicyRunner(OfficialTaskOnPolicyRunner):
    def action_contract(self) -> dict:
        env = self.env.unwrapped
        term = env.action_manager.get_term("joint_pos")
        group_dims = {
            group: [int(value) for value in dims]
            for group, dims in env.observation_manager.group_obs_dim.items()
        }
        history = {
            group: {
                "length": int(getattr(cfg, "history_length", 0) or 0),
                "flatten": bool(getattr(cfg, "flatten_history_dim", False)),
            }
            for group, cfg in env.cfg.observations.items()
        }
        return {
            "version": C.CONTRACT_VERSION,
            "task": C.TASK_ID,
            "actor_terms": list(env.cfg.observations["actor"].terms),
            "critic_terms": list(env.cfg.observations["critic"].terms),
            "actor_dim": C.ACTOR_OBSERVATION_DIM,
            "critic_dim": C.CRITIC_OBSERVATION_DIM,
            "obs_dims": group_dims,
            "obs_history": history,
            "action_joints": list(C.POLICY_JOINT_NAMES),
            "action_target_names": list(term.target_names),
            "action_scale": float(term.scale),
            "use_default_offset": bool(term.cfg.use_default_offset),
            "action_dim": int(env.action_manager.total_action_dim),
        }

    def save(self, path: str, infos=None) -> None:
        super().save(
            path,
            {**(infos or {}), "ht_backflip_contract": self.action_contract()},
        )

    def load(
        self,
        path: str,
        load_cfg: dict | None = None,
        strict: bool = True,
        map_location: str | None = None,
    ) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        saved = (payload.get("infos") or {}).get("ht_backflip_contract")
        if saved != self.action_contract():
            raise ValueError(
                "Incompatible backflip checkpoint: expected "
                f"{C.CONTRACT_VERSION}, got {None if saved is None else saved.get('version')}"
            )
        return super().load(path, load_cfg, strict, map_location)
