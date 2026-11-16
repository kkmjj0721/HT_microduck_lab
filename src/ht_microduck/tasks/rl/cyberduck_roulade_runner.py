# Copyright (c) 2026-2027 zh
"""
内容：
    保存前滚翻独立接口契约，并在恢复后按训练步数重建课程和技能初态。
"""

from __future__ import annotations

import torch
from mjlab.rl import MjlabOnPolicyRunner

from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp.cyberduck_roulade_actions import RouladePositionAction
from ht_microduck.tasks.rl.cyberduck_runner import CyberDuckOnPolicyRunner


class CyberDuckRouladeOnPolicyRunner(CyberDuckOnPolicyRunner):
    """复用混合动作契约采集；仅接收同版本、同观测顺序和动作语义的检查点。"""

    def __init__(self, env, train_cfg: dict, log_dir=None, device="cpu"):
        super().__init__(env, train_cfg, log_dir, device)
        # RSL-RL 5.4.2 将 env 注入镜像配置；运行时扩展保留引用，日志配置去掉不可序列化对象。
        symmetry = train_cfg["algorithm"].get("symmetry_cfg")
        if symmetry is not None:
            train_cfg["algorithm"]["symmetry_cfg"] = {
                key: value for key, value in symmetry.items() if key != "env"
            }

    def action_contract(self) -> dict:
        contract = super().action_contract()
        contract.update(
            version=C.CONTRACT_VERSION,
            observation_terms={name: list(group.terms) for name, group in self.env.unwrapped.cfg.observations.items()},
        )
        position = self.env.unwrapped.action_manager.get_term("joint_pos")
        if isinstance(position, RouladePositionAction):
            contract["version"] = C.RECOVERY_CONTRACT_VERSION
            contract["terms"]["joint_pos"]["mapping"] = "joint_range_tanh_home_offset"
            contract["terms"]["joint_pos"]["latent_offset"] = position.latent_offset[0].cpu().tolist()
            contract["terms"]["joint_pos"]["encoder_bias_order"] = "map_then_subtract_then_bound"
        return contract

    def load(self, path: str, load_cfg: dict | None = None, strict: bool = True,
             map_location: str | None = None) -> dict:
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if (payload.get("infos") or {}).get("cyberduck_action_contract") != self.action_contract():
            raise ValueError(f"Incompatible roulade checkpoint; expected {self.action_contract()['version']}")
        infos = MjlabOnPolicyRunner.load(self, path, load_cfg, strict, map_location)
        self.env.reset()
        return infos
