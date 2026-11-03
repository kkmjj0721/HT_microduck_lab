# Copyright (c) 2026-2027 zh
"""
内容：
    显式验收v4保持与过渡阶段的连续姿态、完整坐站循环及课程升级报告。
    普通pytest只运行CPU判定测试，不启动仿真；动作始终由已加载策略原样输出。

用法（先设置项目内TMPDIR和Warp/Torch缓存）：
    uv run --no-sync python -B tests/test_forward_v4_behavior.py --checkpoint-file logs/forward_v4_20261103/train_hold/model_1000.pt --output logs/forward_v4_20261103/hold_seed0 --seed 0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.mdp.forward_behavior import forward_posture_valid
from ht_microduck.tasks.mdp.forward_commands import (
    FORWARD_STAGES,
    ForwardCurriculumCommand,
    ForwardCurriculumCommandCfg,
)

ROOT = Path(__file__).resolve().parents[1]
TASK = "HtDuck-Flat-SitStand-Forward-V4"
CONTROL_DT = 0.02
HOLD_SECONDS = 5.0
THRESHOLDS = {
    "tilt_deg": 15.0,
    "sit_height_m": 0.015,
    "stand_height_m": 0.02,
    "foot_x_m": 0.015,
    "hip_knee_rad": 0.35,
    "mean_leg_rad": 0.25,
}


class _EvaluationCommand(ForwardCurriculumCommand):
    """独立固定case终点，综合验收使用整数步数的4秒站、12秒坐、8秒站。"""

    def _resample_command(self, env_ids):
        self.vel_command_b[env_ids] = 0.0
        self.vel_command_b[env_ids, 0] = self._env_ref._forward_goal_sit[
            env_ids
        ].float()
        self.time_left[env_ids] = 1.0e6

    def compute(self, dt, env_ids=None):
        if self.cfg.cycle:
            ids = slice(None) if env_ids is None else env_ids
            steps = self._env_ref.episode_length_buf[ids]
            self.vel_command_b[ids] = 0.0
            self.vel_command_b[ids, 0] = ((steps >= 200) & (steps < 800)).float()
        super().compute(dt, env_ids)


@dataclass(kw_only=True)
class _EvaluationCommandCfg(ForwardCurriculumCommandCfg):
    """只替换评估命令时序，保存原阶段和初态库配置。"""

    class_type: type = _EvaluationCommand
    cycle: bool = False

    def build(self, env):
        return _EvaluationCommand(self, env)


def _longest_valid_runs(valid: np.ndarray) -> np.ndarray:
    """以整数控制步累计连续有效帧，避免浮点秒数使249步越过5秒门槛。"""
    current = np.zeros(valid.shape[1], dtype=np.int64)
    longest = np.zeros_like(current)
    for frame in valid:
        current = np.where(frame, current + 1, 0)
        longest = np.maximum(longest, current)
    return longest


def _summarize_hold_trace(trace: dict[str, np.ndarray], target_sit: bool) -> dict:
    """每个环境须在八秒内连续有效五秒，任意自动reset均拒绝该环境成功。"""
    count, num_envs = trace["valid"].shape
    command_valid = trace["command"][..., 0] == float(target_sit)
    uninterrupted = trace["episode_step"] == np.arange(1, count + 1)[:, None]
    longest = _longest_valid_runs(
        trace["valid"] & command_valid & uninterrupted & ~trace["done"].astype(bool)
    )
    reset_per_env = trace["done"].astype(bool).any(axis=0)
    succeeded = (
        (longest >= round(HOLD_SECONDS / CONTROL_DT))
        & ~reset_per_env
        & uninterrupted.all(axis=0)
    )
    finite = all(np.isfinite(value).all() for value in trace.values())
    complete = count == 400
    rate = float(succeeded.mean())
    passed = (
        complete
        and finite
        and not reset_per_env.any()
        and 10 * int(succeeded.sum()) >= 9 * num_envs
    )
    return {
        "passed": bool(passed),
        "completed": complete,
        "finite": finite,
        "steps": count,
        "seconds": count * CONTROL_DT,
        "num_envs": num_envs,
        "success_rate": rate,
        "successful_per_env": succeeded.tolist(),
        "longest_valid_steps_per_env": longest.tolist(),
        "longest_valid_seconds_per_env": (longest * CONTROL_DT).tolist(),
        "termination_or_timeout_count": int(np.count_nonzero(trace["done"])),
        "episode_steps_uninterrupted": bool(uninterrupted.all()),
    }


def _summarize_cycle_trace(trace: dict[str, np.ndarray]) -> dict:
    """综合阶段沿用24秒末窗判定，并要求同一环境同时完成坐和站。"""
    count, num_envs = trace["valid"].shape
    steps = np.arange(1, count + 1)
    sit_window = (steps >= 700) & (steps < 800)
    stand_window = (steps >= 1100) & (steps < 1200)
    sit_valid = trace["valid"] & (trace["command"][..., 0] == 1.0)
    stand_valid = trace["valid"] & (trace["command"][..., 0] == 0.0)
    sit_fraction = (
        sit_valid[sit_window].mean(axis=0) if sit_window.any() else np.zeros(num_envs)
    )
    stand_fraction = (
        stand_valid[stand_window].mean(axis=0)
        if stand_window.any()
        else np.zeros(num_envs)
    )
    sit_passed = sit_fraction >= 0.8
    stand_passed = stand_fraction >= 0.8
    uninterrupted = trace["episode_step"] == steps[:, None]
    reset_per_env = trace["done"].astype(bool).any(axis=0)
    both = sit_passed & stand_passed & ~reset_per_env & uninterrupted.all(axis=0)
    finite = all(np.isfinite(value).all() for value in trace.values())
    complete = count == 1200
    return {
        "passed": bool(
            complete
            and finite
            and not reset_per_env.any()
            and 5 * int(both.sum()) >= 4 * num_envs
        ),
        "completed": complete,
        "finite": finite,
        "steps": count,
        "seconds": count * CONTROL_DT,
        "num_envs": num_envs,
        "success_rate": float(both.mean()),
        "sit_success_rate": float(sit_passed.mean()),
        "rise_success_rate": float(stand_passed.mean()),
        "both_phases_success_per_env": both.tolist(),
        "sit_valid_frame_fraction_per_env": sit_fraction.tolist(),
        "stand_valid_frame_fraction_per_env": stand_fraction.tolist(),
        "sit_window_s": [14.0, 16.0],
        "stand_window_s": [22.0, 24.0],
        "termination_or_timeout_count": int(np.count_nonzero(trace["done"])),
        "episode_steps_uninterrupted": bool(uninterrupted.all()),
    }


def _aggregate_cases(stage: str, results: dict[str, dict]) -> dict:
    """保持与课程报告要求各case通过；综合最终报告另用80%联合门槛。"""
    expected = {"stand_hold", "sit_hold"}
    if stage in ("sit", "rise"):
        expected.add(f"{stage}_transition")
    elif stage == "mixed":
        expected.add("mixed_cycle")
    present = set(results) == expected
    rates = {
        name: values["success_rate"]
        for name, values in results.items()
        if name != "mixed_cycle"
    }
    if "mixed_cycle" in results:
        rates["sit_transition"] = results["mixed_cycle"]["sit_success_rate"]
        rates["rise_transition"] = results["mixed_cycle"]["rise_success_rate"]
    return {
        "passed": present and all(values["passed"] for values in results.values()),
        "required_cases_present": present,
        "missing_cases": sorted(expected - set(results)),
        "case_success_rates": rates,
        "mixed_success_rate": results.get("mixed_cycle", {}).get("success_rate"),
    }


def _run_case(
    args, stage: str, difficulty: float, name: str, expected_bank: str | None
) -> tuple[dict, str]:
    """新建环境后立即执行实际策略，无固定动作预热或动作覆盖。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
    from mjlab.utils.os import dump_yaml

    from ht_microduck.tasks.mdp.forward_initialization import capture_forward_state
    from ht_microduck.tasks.mdp.forward_posture import _feet_forward_x

    output = args.output / name
    output.mkdir()
    cycle = name == "mixed_cycle"
    duration = 24.0 if cycle else 8.0
    cfg = load_env_cfg(TASK, play=True)
    cfg.scene.num_envs = args.num_envs
    cfg.seed = args.seed
    cfg.episode_length_s = duration + 2.0
    cfg.sim.nan_guard.output_dir = str(output / "nan-dumps")
    command = cfg.commands["twist"]
    command.restore_stage_on_inference = False
    if args.state_bank is not None:
        command.state_bank = str(args.state_bank)
    cfg.commands["twist"] = _EvaluationCommandCfg(
        **{
            **vars(command),
            "class_type": _EvaluationCommand,
            "stage": stage,
            "difficulty": difficulty,
            "cycle": cycle,
            "resampling_time_range": (100.0, 100.0),
        }
    )
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.events["set_ground_state"].params = {
        "case_override": "stand_hold" if cycle else name
    }
    agent = load_rl_cfg(TASK)
    agent.seed = args.seed
    agent.upload_model = False
    if agent.clip_actions is not None:
        raise ValueError(
            "Behavior acceptance requires unmodified, unclipped policy actions."
        )
    dump_yaml(output / "env.yaml", asdict(cfg))
    dump_yaml(output / "agent.yaml", asdict(agent))
    samples = {
        key: []
        for key in (
            "height",
            "tilt_deg",
            "foot_x_b",
            "joint_pos",
            "command",
            "actions",
            "done",
            "episode_step",
            "valid",
            "foot_contact",
            "foot_contact_force",
        )
    }
    env = ManagerBasedRlEnv(cfg, device=args.device)
    try:
        wrapper = RslRlVecEnvWrapper(env, clip_actions=None)
        runner = load_runner_cls(TASK)(wrapper, asdict(agent), device=args.device)
        runner.load(
            str(args.checkpoint_file),
            load_cfg={"actor": True},
            strict=True,
            map_location=args.device,
        )
        bank_sha256 = env._forward_state_bank.sha256
        if expected_bank is not None and bank_sha256 != expected_bank:
            raise ValueError("Evaluation state-bank hash differs from the checkpoint.")
        policy = runner.get_inference_policy(device=args.device)
        obs = wrapper.get_observations()
        if (
            obs["actor"].shape != (args.num_envs, 61)
            or obs["critic"].shape != (args.num_envs, 74)
            or env.action_manager.total_action_dim != 14
            or env.step_dt != CONTROL_DT
        ):
            raise ValueError(
                "Unexpected v4 observation, action, or control-period contract."
            )
        robot = env.scene["robot"]
        ids, _ = robot.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
        np.savez_compressed(output / "initial_state.npz", **capture_forward_state(env))
        dump_yaml(output / "env.yaml", asdict(cfg))
        with torch.no_grad():
            for _ in range(round(duration / CONTROL_DT)):
                live_command = env.command_manager.get_command("twist")
                torch.testing.assert_close(
                    obs["actor"][:, C.ACTOR_OBSERVATION_SLICES["command"]],
                    live_command,
                    rtol=0.0,
                    atol=1e-6,
                )
                torch.testing.assert_close(
                    obs["actor"][:, C.ACTOR_OBSERVATION_SLICES["head_command"]],
                    torch.zeros(args.num_envs, 4, device=args.device),
                    rtol=0.0,
                    atol=1e-6,
                )
                applied_command = live_command.clone()
                actions = policy(obs)
                obs, _, dones, _ = wrapper.step(actions)
                quat = robot.data.root_link_quat_w
                tilt = torch.rad2deg(
                    torch.acos(
                        (1.0 - 2.0 * (quat[:, 1].square() + quat[:, 2].square())).clamp(
                            -1.0, 1.0
                        )
                    )
                )
                contact = env.scene["feet_ground_contact"].data
                values = {
                    "height": robot.data.root_link_pos_w[:, 2]
                    - env.scene.env_origins[:, 2],
                    "tilt_deg": tilt,
                    "foot_x_b": _feet_forward_x(env),
                    "joint_pos": robot.data.joint_pos[:, ids],
                    "command": applied_command,
                    "actions": actions,
                    "done": dones,
                    "episode_step": env.episode_length_buf,
                    "valid": forward_posture_valid(env, applied_command[:, 0] > 0.5),
                    "foot_contact": contact.found,
                    "foot_contact_force": contact.force,
                }
                for key, value in values.items():
                    samples[key].append(value.detach().cpu().numpy().copy())
    finally:
        env.close()
        trace = {key: np.asarray(values) for key, values in samples.items()}
        np.savez_compressed(output / "trace.npz", **trace, dt=CONTROL_DT)
    result = (
        _summarize_cycle_trace(trace)
        if cycle
        else _summarize_hold_trace(trace, name in ("sit_hold", "sit_transition"))
    )
    result["peak_tilt_deg_per_env"] = trace["tilt_deg"].max(axis=0).tolist()
    result["scope"] = (
        "Independent policy evaluation; no action overrides, fixed-control warmup, or resets counted as success."
    )
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result, bank_sha256


def run_behavior(args) -> dict:
    """保存原始配置、源码与失败证据，保持课程报告和综合最终验收口径独立。"""
    from mjlab.utils.torch import configure_torch_backends

    configure_torch_backends()
    payload = torch.load(args.checkpoint_file, map_location="cpu", weights_only=False)
    metadata = (payload.get("infos") or {}).get("forward_curriculum")
    if metadata is None and args.stage != "hold":
        raise ValueError(
            "A checkpoint without v4 metadata requires explicit --stage hold diagnostics."
        )
    stage = args.stage if args.stage is not None else metadata["stage"]
    difficulty = (
        args.difficulty
        if args.difficulty is not None
        else (metadata["difficulty"] if metadata is not None else 0.0)
    )
    expected_bank = metadata["bank_sha256"] if metadata is not None else None
    if args.state_bank is None and metadata is not None and "bank_snapshot" in metadata:
        args.state_bank = args.output / "initial_state_bank.npz"
        args.state_bank.write_bytes(metadata["bank_snapshot"])
    with args.checkpoint_file.open("rb") as stream:
        checkpoint_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    sources = {}
    paths = [
        *sorted((ROOT / "src/ht_microduck/tasks").rglob("*.py")),
        Path(__file__).resolve(),
    ]
    for path in paths:
        relative = path.relative_to(ROOT)
        target = args.output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        target.write_bytes(data)
        sources[str(relative)] = hashlib.sha256(data).hexdigest()
    (args.output / "source_hashes.json").write_text(
        json.dumps(sources, indent=2) + "\n"
    )
    result = {
        "schema_version": 1,
        "task": TASK,
        "checkpoint": str(args.checkpoint_file),
        "checkpoint_sha256": checkpoint_hash,
        "bank_sha256": expected_bank,
        "stage": stage,
        "difficulty": difficulty,
        "seed": args.seed,
        "num_envs_per_case": args.num_envs,
        "continuous_hold_seconds": HOLD_SECONDS,
        "thresholds": THRESHOLDS,
        "policy_actions_unmodified": True,
        "protocol": "mixed_final_acceptance" if stage == "mixed" else "curriculum_gate",
        "passed": False,
        "cases": {},
        "case_success_rates": {},
    }
    cases = ["stand_hold", "sit_hold"]
    if stage in ("sit", "rise"):
        cases.append(f"{stage}_transition")
    elif stage == "mixed":
        cases.append("mixed_cycle")
    try:
        for case in cases:
            values, bank_hash = _run_case(args, stage, difficulty, case, expected_bank)
            result["cases"][case] = values
            result["bank_sha256"] = bank_hash
        result.update(_aggregate_cases(stage, result["cases"]))
    finally:
        error_type, error, _ = sys.exc_info()
        if error_type is not None:
            result.update(
                passed=False, exception_type=error_type.__name__, exception=str(error)
            )
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate v4 posture holding, curriculum transitions, or the complete sit-stand cycle."
    )
    parser.add_argument("--checkpoint-file", type=Path, required=True)
    parser.add_argument("--state-bank", type=Path, help="Explicit state bank; otherwise use the checkpoint snapshot or packaged endpoints.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--num-envs",
        type=int,
        default=16,
        help="Number of environments per independent case.",
    )
    parser.add_argument("--stage", choices=FORWARD_STAGES)
    parser.add_argument("--difficulty", type=float)
    args = parser.parse_args()
    args.checkpoint_file = args.checkpoint_file.resolve()
    args.output = args.output.resolve()
    if args.num_envs < 1:
        parser.error("At least one environment per case is required.")
    if (
        not args.checkpoint_file.is_relative_to(ROOT)
        or not args.checkpoint_file.is_file()
    ):
        parser.error("The checkpoint must be an existing project-local file.")
    if not args.output.is_relative_to(ROOT) or args.output.exists():
        parser.error("The output must be a new project-local directory.")
    args.output.mkdir(parents=True)
    if not run_behavior(args)["passed"]:
        raise SystemExit(1)


def _valid_trace(count=400, num_envs=10, target_sit=True):
    """仅构造CPU判定输入，几何有效帧在GPU入口中来自生产联合判定。"""
    command = np.zeros((count, num_envs, 3), dtype=np.float32)
    command[..., 0] = float(target_sit)
    return {
        "valid": np.ones((count, num_envs), dtype=bool),
        "command": command,
        "done": np.zeros((count, num_envs), dtype=bool),
        "episode_step": np.broadcast_to(
            np.arange(1, count + 1)[:, None], (count, num_envs)
        ).copy(),
    }


def test_hold_requires_250_consecutive_steps_and_resets_the_run_after_one_bad_frame():
    trace = _valid_trace()
    trace["valid"][:151] = False
    assert not _summarize_hold_trace(trace, True)["passed"]
    trace["valid"][150] = True
    assert _summarize_hold_trace(trace, True)["passed"]
    trace["valid"][250] = False
    assert not _summarize_hold_trace(trace, True)["passed"]


def test_hold_requires_ninety_percent_per_case_and_does_not_pool_cases():
    trace = _valid_trace()
    trace["valid"][:, 0] = False
    sit = _summarize_hold_trace(trace, True)
    stand = _summarize_hold_trace(_valid_trace(target_sit=False), False)
    assert (
        sit["passed"]
        and _aggregate_cases("hold", {"sit_hold": sit, "stand_hold": stand})["passed"]
    )
    trace["valid"][:, 1] = False
    sit = _summarize_hold_trace(trace, True)
    assert not _aggregate_cases("hold", {"sit_hold": sit, "stand_hold": stand})[
        "passed"
    ]


def test_hold_rejects_resets_wrong_commands_incomplete_or_nonfinite_trace():
    trace = _valid_trace()
    trace["done"][10, 0] = True
    assert not _summarize_hold_trace(trace, True)["passed"]
    assert not _summarize_hold_trace(_valid_trace(count=399), True)["passed"]
    assert not _summarize_hold_trace(_valid_trace(target_sit=False), True)["passed"]
    trace = _valid_trace()
    trace["command"][0, 0, 1] = np.nan
    assert not _summarize_hold_trace(trace, True)["passed"]


def test_reports_reject_missing_required_cases():
    case = _summarize_hold_trace(_valid_trace(), True)
    assert not _aggregate_cases("hold", {"sit_hold": case})["passed"]
    assert not _aggregate_cases("sit", {"sit_hold": case, "stand_hold": case})["passed"]
    assert not _aggregate_cases("rise", {"sit_hold": case, "stand_hold": case})[
        "passed"
    ]
    assert not _aggregate_cases("mixed", {"sit_hold": case, "stand_hold": case})[
        "passed"
    ]


def test_mixed_requires_joint_eighty_percent_success_from_the_same_environments():
    trace = _valid_trace(count=1200)
    trace["command"][:200, :, 0] = 0.0
    trace["command"][800:, :, 0] = 0.0
    trace["valid"][699:799, :2] = False
    cycle = _summarize_cycle_trace(trace)
    assert cycle["passed"] and cycle["success_rate"] == 0.8
    trace["valid"][1099:1199, 2] = False
    assert not _summarize_cycle_trace(trace)["passed"]
    hold = _summarize_hold_trace(_valid_trace(), True)
    result = _aggregate_cases(
        "mixed", {"sit_hold": hold, "stand_hold": hold, "mixed_cycle": cycle}
    )
    assert result["passed"] and result["mixed_success_rate"] == 0.8


if __name__ == "__main__":
    main()
