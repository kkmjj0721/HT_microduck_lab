# Copyright (c) 2026-2027 zh
"""
内容：
    保存摔倒起立任务的独立动作契约，并拒绝其他任务或旧动作语义的检查点。

起立任务与前滚翻共享「关节行程 tanh 映射的位置动作 + 踝速度动作」实现，
但观测、初态课程与奖励不同，检查点必须按独立契约版本隔离。
"""

from __future__ import annotations

import torch
from mjlab.rl import MjlabOnPolicyRunner

from ht_microduck.tasks import cyberduck_v2_standup_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_actions import RouladePositionAction
from ht_microduck.tasks.rl.cyberduck_runner import CyberDuckOnPolicyRunner


class CyberDuckStandUpOnPolicyRunner(CyberDuckOnPolicyRunner):
    """复用混合动作契约采集；只接收同版本、同观测顺序与同初态语义的检查点。"""

    def action_contract(self) -> dict:
        contract = super().action_contract()
        contract.update(
            version=C.CONTRACT_VERSION,
            observation_terms={
                name: list(group.terms)
                for name, group in self.env.unwrapped.cfg.observations.items()
            },
            task_id=C.TASK_ID,
        )
        position = self.env.unwrapped.action_manager.get_term("joint_pos")
        if isinstance(position, RouladePositionAction):
            contract["terms"]["joint_pos"]["mapping"] = "joint_range_tanh_home_offset"
            contract["terms"]["joint_pos"]["latent_offset"] = (
                position.latent_offset[0].cpu().tolist()
            )
            contract["terms"]["joint_pos"]["encoder_bias_order"] = (
                "map_then_subtract_then_bound"
            )
        return contract

    def load(
        self,
        path: str,
        load_cfg: dict | None = None,
        strict: bool = True,
        map_location: str | None = None,
    ) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if (payload.get("infos") or {}).get("cyberduck_action_contract") != self.action_contract():
            raise ValueError(
                f"Incompatible standup checkpoint; expected {self.action_contract()['version']}"
            )
        infos = MjlabOnPolicyRunner.load(self, path, load_cfg, strict, map_location)
        self.env.reset()
        return infos
