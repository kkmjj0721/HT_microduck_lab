# Copyright (c) 2026-2027 zh
"""v4前坐课程的阶段命令；训练阶段不进入策略观测。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import torch

from ht_microduck.tasks.mdp.official_posture_events import (
    SitStandCommand,
    SitStandCommandCfg,
)

DEFAULT_FORWARD_STATE_BANK = str(Path(__file__).resolve().parents[1] / "assets" / "forward_v4_states.npz")
FORWARD_STAGES = ("hold", "sit", "rise", "mixed")


class ForwardCurriculumCommand(SitStandCommand):
    """保持和过渡阶段固定终点命令，综合阶段沿用随机坐站切换。"""

    def __init__(self, cfg, env):
        if cfg.stage not in FORWARD_STAGES:
            raise ValueError(f"Unknown forward curriculum stage: {cfg.stage}")
        if not 0.0 <= cfg.difficulty <= 1.0 or (cfg.stage == "hold" and cfg.difficulty != 0.0) or (cfg.stage == "mixed" and cfg.difficulty != 1.0):
            raise ValueError("Forward difficulty must be in [0, 1]; hold requires zero and mixed requires one.")
        super().__init__(cfg, env)

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        if self.cfg.stage == "mixed":
            super()._resample_command(env_ids)
        else:
            self.vel_command_b[env_ids] = 0.0
            self.vel_command_b[env_ids, 0] = self._env_ref._forward_goal_sit[env_ids].float()
            self.time_left[env_ids] = 1.0e6


@dataclass(kw_only=True)
class ForwardCurriculumCommandCfg(SitStandCommandCfg):
    """阶段与真实状态库配置；升级报告由任务runner校验。"""

    class_type: type = ForwardCurriculumCommand
    stage: Literal["hold", "sit", "rise", "mixed"] = "hold"
    difficulty: float = 0.0
    state_bank: str = DEFAULT_FORWARD_STATE_BANK
    gate_reports: tuple[str, ...] = ()
    restore_stage_on_inference: bool = True

    def build(self, env):
        return ForwardCurriculumCommand(self, env)
