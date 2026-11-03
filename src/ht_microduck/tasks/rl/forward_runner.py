# Copyright (c) 2026-2027 zh
"""保存v4课程边界，并以对应检查点的独立行为报告校验阶段升级。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import torch

from ht_microduck.tasks.mdp.forward_commands import FORWARD_STAGES
from ht_microduck.tasks.mdp.forward_events import ForwardStateBank
from ht_microduck.tasks.rl.runner import OfficialTaskOnPolicyRunner


def validate_forward_promotion(previous: dict, current: dict, reports: list[dict], checkpoint_sha256: str) -> None:
    """完整续训只允许同配置恢复，扩展课程必须先通过来源阶段的三种子验收。"""
    old_stage, new_stage = previous["stage"], current["stage"]
    old_level, new_level = previous["difficulty"], current["difficulty"]
    if old_stage == new_stage and old_level == new_level and previous["bank_sha256"] == current["bank_sha256"]:
        return
    old_index, new_index = FORWARD_STAGES.index(old_stage), FORWARD_STAGES.index(new_stage)
    if new_index == old_index:
        if not old_level < new_level <= min(1.0, old_level + 0.25) + 1e-6:
            raise ValueError("Forward difficulty can increase by at most 0.25 after evaluation.")
    elif new_index == old_index + 1:
        if (old_stage != "hold" and old_level < 1.0) or (new_stage != "mixed" and new_level > 0.25):
            raise ValueError("Forward stage promotion requires full source difficulty and a gradual next stage.")
    else:
        raise ValueError("Forward curriculum stages cannot be skipped or reversed during full resume.")
    if len(reports) != 3 or len({report["seed"] for report in reports}) != 3:
        raise ValueError("Forward promotion requires three independent evaluation seeds.")
    cases = {"stand_hold", "sit_hold"}
    if old_stage in ("sit", "mixed"):
        cases.add("sit_transition")
    if old_stage in ("rise", "mixed"):
        cases.add("rise_transition")
    for report in reports:
        matches = (
            report["schema_version"] == 1 and report["passed"] is True
            and report["checkpoint_sha256"] == checkpoint_sha256
            and report["bank_sha256"] == previous["bank_sha256"]
            and report["stage"] == old_stage and report["difficulty"] == old_level
            and report["policy_actions_unmodified"] is True
            and report["num_envs_per_case"] >= 16
            and type(report["seed"]) is int
            and report["continuous_hold_seconds"] >= 5.0
            and report["thresholds"] == {"tilt_deg": 15.0, "sit_height_m": 0.015, "stand_height_m": 0.02, "foot_x_m": 0.015, "hip_knee_rad": 0.35, "mean_leg_rad": 0.25}
        )
        rates = report["case_success_rates"]
        if not matches or set(rates) != cases or any(not math.isfinite(value) or not 0.9 <= value <= 1.0 for value in rates.values()):
            raise ValueError("Forward gate report does not certify the source checkpoint and each posture case.")


class ForwardCurriculumOnPolicyRunner(OfficialTaskOnPolicyRunner):
    """通用PPO保持不变，任务适配只管理课程元数据和显式升级。"""

    def __init__(self, env, train_cfg, log_dir=None, device="cpu"):
        super().__init__(env, train_cfg, log_dir, device)
        self._forward_complete_resume = False
        self._forward_inference_only = False

    def curriculum_state(self) -> dict:
        env = self.env.unwrapped
        cfg = env.command_manager.get_term("twist").cfg
        return {"schema_version": 1, "stage": cfg.stage, "difficulty": cfg.difficulty, "bank_sha256": env._forward_state_bank.sha256}

    def save(self, path: str, infos=None) -> None:
        if self._forward_inference_only:
            raise ValueError("Inference-only loads cannot be saved as complete v4 training checkpoints.")
        bank = self.env.unwrapped._forward_state_bank
        state = {**self.curriculum_state(), "bank_snapshot": bank.content, "bank_source": str(bank.path)}
        super().save(path, {**(infos or {}), "forward_curriculum": state})

    def load(self, path, load_cfg=None, strict=True, map_location=None):
        inference_only = load_cfg is not None and load_cfg.get("actor", False) and not any(load_cfg.get(key, False) for key in ("critic", "optimizer", "iteration"))
        if load_cfg is not None and not inference_only and not all(load_cfg.get(key, False) is True for key in ("actor", "critic", "optimizer", "iteration")):
            raise ValueError("Partial v4 resume is not supported; load actor-only for inference or restore all training state.")
        payload = torch.load(path, map_location="cpu", weights_only=False)
        previous = (payload.get("infos") or {}).get("forward_curriculum")
        cfg = self.env.unwrapped.command_manager.get_term("twist").cfg
        if inference_only and previous is not None and cfg.restore_stage_on_inference:
            if previous["bank_sha256"] != self.curriculum_state()["bank_sha256"]:
                if "bank_snapshot" not in previous:
                    raise ValueError("Playback requires the checkpoint's matching forward state bank snapshot.")
                bank = ForwardStateBank(previous["bank_snapshot"], self.env.unwrapped.device)
                if bank.sha256 != previous["bank_sha256"]:
                    raise ValueError("Checkpoint state-bank snapshot does not match its fingerprint.")
                self.env.unwrapped._forward_state_bank = bank
                cfg.state_bank = "checkpoint:" + bank.sha256
            cfg.stage, cfg.difficulty = previous["stage"], previous["difficulty"]
        if not inference_only:
            if previous is None or previous.get("schema_version") != 1:
                raise ValueError("Full v4 resume requires matching forward curriculum metadata; v3 is inference-only.")
            reports = [json.loads(Path(value).read_text()) for value in cfg.gate_reports]
            validate_forward_promotion(previous, self.curriculum_state(), reports, hashlib.sha256(Path(path).read_bytes()).hexdigest())
        infos = super().load(path, load_cfg, strict, map_location)
        self._forward_complete_resume = not inference_only
        self._forward_inference_only = inference_only
        return infos

    def learn(self, num_learning_iterations: int, init_at_random_ep_len: bool = False):
        state = self.curriculum_state()
        if self._forward_inference_only or (not self._forward_complete_resume and (state["stage"] != "hold" or state["difficulty"] != 0.0)):
            raise ValueError("Training must start from v4 hold or a fully restored, validated curriculum checkpoint.")
        return super().learn(num_learning_iterations, init_at_random_ep_len)
