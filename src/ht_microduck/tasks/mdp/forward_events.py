# Copyright (c) 2026-2027 zh
"""加载经真实执行器采集和重新初始化复验的v4课程初态。"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import torch

from ht_microduck.robot.ht_microduck_constants import JOINT_NAMES
from ht_microduck.tasks.mdp.forward_initialization import set_forward_initial_state

STATE_FIELDS = {"root_pose": 7, "root_velocity": 6, "joint_pos": 15, "joint_vel": 15, "position_target": 15}


def forward_model_fingerprint() -> dict[str, str]:
    """记录影响初态物理含义的机器人和执行器源码/参数/资源。"""
    package = Path(__file__).resolve().parents[2]
    files = sorted((package / "robot").rglob("*.xml")) + sorted((package / "robot").rglob("*.STL"))
    files += sorted((package / "robot").rglob("*.stl"))
    files += [package / "robot" / "ht_microduck_constants.py"]
    files += sorted((package / "actuator").rglob("*.py")) + sorted((package / "actuator").rglob("*.json"))
    return {str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


class ForwardStateBank:
    """只在外部数据边界校验一次，内部沿用有序机器人状态约定。"""

    def __init__(self, path: str | bytes, device):
        self.path = None if isinstance(path, bytes) else Path(path).resolve()
        self.content = path if isinstance(path, bytes) else self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.content).hexdigest()
        with np.load(io.BytesIO(self.content), allow_pickle=False) as data:
            self.metadata = json.loads(str(data["metadata"].item()))
            values = {name: data[name].copy() for name in (*STATE_FIELDS, "kind", "difficulty", "validated")}
        meta = self.metadata
        if meta["schema_version"] != 1 or meta["mjlab_version"] != "1.6.0":
            raise ValueError("Unsupported forward state-bank schema or simulator version.")
        if meta["joint_names"] != list(JOINT_NAMES) or meta["model_fingerprint"] != forward_model_fingerprint():
            raise ValueError("Forward state-bank joint order or model fingerprint does not match.")
        if meta["initialization"] != "physical_state_current_targets_native_reset" or not meta["revalidation"]:
            raise ValueError("Forward states require revalidation under native-reset initialization.")
        count = len(values["kind"])
        if not count:
            raise ValueError("Forward state bank must contain samples.")
        for name, width in STATE_FIELDS.items():
            array = values[name]
            if array.shape != (count, width) or not np.isfinite(array).all():
                raise ValueError(f"Invalid forward state field: {name}")
        for name in ("kind", "difficulty", "validated"):
            if values[name].shape != (count,):
                raise ValueError(f"Invalid forward sample labels: {name}")
        if values["validated"].dtype != np.dtype(bool):
            raise ValueError("Forward validated labels must have boolean dtype.")
        if not np.isin(values["kind"], (0, 1, 2, 3)).all():
            raise ValueError("Unknown forward state kind.")
        if not np.isfinite(values["difficulty"]).all() or not ((values["difficulty"] >= 0) & (values["difficulty"] <= 1)).all():
            raise ValueError("Forward state difficulty must be in [0, 1].")
        if not np.allclose(np.linalg.norm(values["root_pose"][:, 3:7], axis=1), 1.0, atol=1e-4):
            raise ValueError("Forward root quaternions must have unit norm.")
        proven = np.zeros(count, dtype=bool)
        for record in meta["revalidation"]:
            ids = np.asarray(record.get("sample_ids", []), dtype=np.int64)
            frames = np.asarray(record["valid_frames_per_sample"])
            if ids.ndim != 1 or not len(ids) or frames.shape != ids.shape or (ids < 0).any() or (ids >= count).any():
                raise ValueError("Revalidation must identify each tested state sample.")
            kind = record["kind"]
            if (values["kind"][ids] != kind).any() or record["seconds"] < 5.0 or not np.isfinite(frames).all() or (frames != round(record["seconds"] / 0.02)).any():
                raise ValueError("Forward samples do not match their successful revalidation record.")
            protocol = "fixed_target_hold" if kind < 2 else "restored_transition_then_hold"
            if record.get("protocol") != protocol:
                raise ValueError("Forward transition samples require transition revalidation, not endpoint holding.")
            if kind >= 2:
                remaining = np.asarray(record["remaining_seconds"], dtype=np.float64)
                full = record["full_transition_seconds"]
                if full <= 0 or remaining.shape != ids.shape or not np.allclose(values["difficulty"][ids], remaining / full, atol=1e-6):
                    raise ValueError("Transition difficulty must match the revalidated remaining trajectory.")
            proven[ids] = True
        if (values["validated"] & ~proven).any():
            raise ValueError("Validated forward samples require matching per-sample revalidation evidence.")
        self.values = {name: torch.as_tensor(values[name], dtype=torch.float32, device=device) for name in STATE_FIELDS}
        self.kind = torch.as_tensor(values["kind"], dtype=torch.long, device=device)
        self.difficulty = torch.as_tensor(values["difficulty"], dtype=torch.float32, device=device)
        self.validated = torch.as_tensor(values["validated"], dtype=torch.bool, device=device)
        self.pools = {}
        for kind in (0, 1):
            self.pools[kind] = self.indices(kind, 1.0)

    def indices(self, kind: int, difficulty: float):
        indices = ((self.kind == kind) & self.validated & (self.difficulty <= difficulty + 1e-6)).nonzero().flatten()
        if not len(indices):
            raise ValueError(f"No revalidated forward states for kind={kind}, difficulty={difficulty}.")
        if kind >= 2 and float(self.difficulty[indices].max()) < difficulty - 1e-6:
            raise ValueError("Requested forward difficulty is not represented by revalidated samples.")
        return indices


def reset_forward_curriculum(env, env_ids: torch.Tensor, command_name: str = "twist", case_override: str | None = None) -> None:
    """只写本次重置的环境；原生action reset随后回填控制初态。"""
    command = env.command_manager.get_term(command_name).cfg
    if "_forward_state_bank" not in env.__dict__:
        env._forward_state_bank = ForwardStateBank(command.state_bank, env.device)
        env._forward_initial_sit = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        env._forward_goal_sit = torch.zeros_like(env._forward_initial_sit)
        env._forward_sample_ids = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)
    bank = env._forward_state_bank
    if command.stage in ("sit", "rise"):
        bank.indices(2 if command.stage == "sit" else 3, command.difficulty)
    count = len(env_ids)
    cases = {"stand_hold": 0, "sit_hold": 1, "sit_transition": 2, "rise_transition": 3}
    if case_override is not None and case_override not in cases:
        raise ValueError(f"Unknown forward evaluation case: {case_override}")
    kinds = (torch.rand(count, device=env.device) < 0.5).long()
    if case_override is not None:
        kinds.fill_(cases[case_override])
    elif command.stage in ("sit", "rise"):
        transition_kind = 2 if command.stage == "sit" else 3
        kinds[torch.rand(count, device=env.device) < 0.5] = transition_kind
    selected = torch.empty(count, dtype=torch.long, device=env.device)
    for kind in kinds.unique().tolist():
        mask = kinds == kind
        candidates = bank.indices(kind, command.difficulty) if kind >= 2 else bank.pools[kind]
        selected[mask] = candidates[torch.randint(len(candidates), (int(mask.sum()),), device=env.device)]
    env._forward_sample_ids[env_ids] = selected
    env._forward_initial_sit[env_ids] = (kinds == 1) | (kinds == 3)
    env._forward_goal_sit[env_ids] = (kinds == 1) | (kinds == 2)
    set_forward_initial_state(env, env_ids, **{name: values[selected] for name, values in bank.values.items()})


def forward_transition_reward(env, reward_func, **params):
    """按CLI覆盖后的最终阶段启停原升降过程项，保留其公式与权重。"""
    if env.command_manager.get_term("twist").cfg.stage == "hold":
        return torch.zeros(env.num_envs, device=env.device)
    return reward_func(env, **params)
