# Copyright (c) 2026-2027 zh
"""
内容：
    保存并核对 CyberDuck 执行动作契约，沿用 mjlab 与 RSL-RL 的训练和恢复实现。
"""

from __future__ import annotations

import torch
from mjlab.rl import MjlabOnPolicyRunner

from ht_microduck.tasks import cyberduck_v2_contract as C


class CyberDuckOnPolicyRunner(MjlabOnPolicyRunner):
    """在恢复参数前拒绝动作语义不同的权重，包括旧版同维度检查点。"""

    def action_contract(self) -> dict:
        """记录实际动作项参数；环境数与计算设备不影响检查点兼容性。"""
        env = self.env.unwrapped
        terms = {}
        for name in ("joint_pos", "joint_vel"):
            term = env.action_manager.get_term(name)
            values = {}
            for field in ("scale", "offset"):
                value = getattr(term, field)
                values[field] = value[0].detach().cpu().tolist() if isinstance(value, torch.Tensor) else [float(value)] * term.action_dim
            terms[name] = {
                "joint_names": list(term.target_names),
                "raw_action_limit": term.cfg.raw_action_limit,
                **values,
                "clip": dict(term.cfg.clip) if term.cfg.clip is not None else None,
            }
            if name == "joint_pos":
                terms[name]["bound_targets"] = term.cfg.bound_targets
                ids, _ = env.scene["robot"].find_joints(term.target_names, preserve_order=True)
                terms[name]["joint_pos_limits"] = env.scene["robot"].data.joint_pos_limits[0, ids].cpu().tolist()
        return {
            "version": C.ACTION_CONTRACT_VERSION,
            "actor_observation_dim": self.alg.actor.obs_dim,
            "critic_observation_dim": self.alg.critic.obs_dim,
            "actor_history_length": env.cfg.observations["actor"].history_length,
            "wrapper_clip_actions": self.env.clip_actions,
            "action_term_order": list(env.action_manager.active_terms),
            "action_observation": {
                group: env.cfg.observations[group].terms["actions"].func.__name__
                for group in ("actor", "critic")
            },
            "control_dt": env.step_dt,
            "terms": terms,
        }

    def save(self, path: str, infos: dict | None = None) -> None:
        super().save(path, {**(infos or {}), "cyberduck_action_contract": self.action_contract()})

    def load(
        self,
        path: str,
        load_cfg: dict | None = None,
        strict: bool = True,
        map_location: str | None = None,
    ) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        previous = (payload.get("infos") or {}).get("cyberduck_action_contract")
        if previous != self.action_contract():
            raise ValueError(
                "CyberDuck checkpoint action contract is missing or incompatible; "
                f"start a new run with {C.ACTION_CONTRACT_VERSION}."
            )
        return super().load(path, load_cfg, strict, map_location)
