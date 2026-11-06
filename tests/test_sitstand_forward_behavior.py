# Copyright (c) 2026-2027 zh
"""
内容：
    显式验收学习策略从站立进入前坐并再次站起的行为；普通pytest仅检查判定规则。

用法（先设置项目内TMPDIR和Warp/Torch缓存）：
    uv run --no-sync python -B tests/test_sitstand_forward_behavior.py --checkpoint-file logs/rsl_rl/flat_sitstand_forward/2026-10-31_14-31-57_sitstand_forward/model_26000.pt --output logs/forward_behavior/model_26000
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

from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
)
from ht_microduck.tasks.mdp.official_posture_events import (
    SitStandCommand,
    SitStandCommandCfg,
)

ROOT = Path(__file__).resolve().parents[1]
TASK = "HtDuck-Flat-SitStand-Forward"
CONTROL_DT = 0.02
DURATION_S = 24.0
HIP_INDICES = tuple(C.POLICY_JOINT_NAMES.index(name) for name in ("r_hip_pitch_joint", "l_hip_pitch_joint"))


class _BehaviorCommand(SitStandCommand):
    """经正常命令管理器执行4秒站立、12秒坐下和8秒站立。"""

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        self.vel_command_b[env_ids] = 0.0

    def compute(self, dt, env_ids=None) -> None:
        elapsed = self._env_ref.episode_length_buf * self._env_ref.step_dt
        self.vel_command_b[:, 0] = ((elapsed >= 4.0) & (elapsed < 16.0)).float()
        super().compute(dt, env_ids)


@dataclass(kw_only=True)
class _BehaviorCommandCfg(SitStandCommandCfg):
    def build(self, env) -> _BehaviorCommand:
        return _BehaviorCommand(self, env)


def _summarize_trace(trace: dict[str, np.ndarray]) -> dict:
    """同时检查前坐几何、关键髋角和再次站起，拒绝低位后坐及自动重置。"""
    count, num_envs = trace["height"].shape
    times = np.arange(1, count + 1) * CONTROL_DT
    sit_window = (times >= 14.0 - 1e-7) & (times < 16.0 - 1e-7)
    stand_window = (times >= 22.0 - 1e-7) & (times < 24.0 - 1e-7)
    complete = count == round(DURATION_S / CONTROL_DT)
    finite = all(np.isfinite(value).all() for value in trace.values())
    sit_ok = (
        (np.abs(trace["height"] - FORWARD_SIT_Z) < 0.015)
        & (trace["foot_x_b"] > 0.015).all(axis=-1)
        & (trace["tilt_deg"] < 15.0)
        & (trace["hip_error_rad"] < 0.35).all(axis=-1)
        & (trace["command"][..., 0] == 1.0)
    )
    stand_ok = (
        (np.abs(trace["height"] - C.STAND_Z) < 0.02)
        & (trace["tilt_deg"] < 15.0)
        & (trace["stand_leg_error_rad"].mean(axis=-1) < 0.25)
        & (trace["command"][..., 0] == 0.0)
    )
    sit_fraction = sit_ok[sit_window].mean(axis=0) if sit_window.any() else np.zeros(num_envs)
    stand_fraction = stand_ok[stand_window].mean(axis=0) if stand_window.any() else np.zeros(num_envs)
    per_env = (sit_fraction >= 0.8) & (stand_fraction >= 0.8)
    reset_count = int(np.count_nonzero(trace["done"]))
    expected_steps = np.arange(1, count + 1)[:, None]
    uninterrupted = bool(np.all(trace["episode_step"] == expected_steps))
    success_rate = float(per_env.mean())
    passed = complete and finite and reset_count == 0 and uninterrupted and success_rate >= 0.8
    return {
        "passed": passed, "completed": complete, "finite": finite,
        "steps": count, "num_envs": num_envs, "seconds": count * CONTROL_DT,
        "termination_or_timeout_count": reset_count, "episode_steps_uninterrupted": uninterrupted,
        "sit_valid_frame_fraction_per_env": sit_fraction.tolist(),
        "stand_valid_frame_fraction_per_env": stand_fraction.tolist(),
        "both_phases_success_per_env": per_env.tolist(), "success_rate": success_rate,
        "acceptance": {
            "sit_window_s": [14.0, 16.0], "stand_window_s": [22.0, 24.0],
            "sit_height_error_max_m": 0.015, "feet_forward_x_min_m": 0.015,
            "sit_hip_error_max_rad": 0.35, "tilt_max_deg": 15.0,
            "stand_height_error_max_m": 0.02, "stand_mean_leg_error_max_rad": 0.25,
            "valid_frame_fraction_min": 0.8, "successful_environment_fraction_min": 0.8,
            "automatic_resets_allowed": 0,
        },
    }


def run_behavior(args) -> dict:
    """只运行正常策略推理，保留成功或失败的完整配置、权重哈希与状态轨迹。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
    from mjlab.utils.lab_api.math import quat_apply_inverse
    from mjlab.utils.os import dump_yaml
    from mjlab.utils.torch import configure_torch_backends

    configure_torch_backends()
    cfg = load_env_cfg(TASK, play=True)
    cfg.scene.num_envs = args.num_envs
    cfg.seed = args.seed
    cfg.episode_length_s = DURATION_S + 2.0
    cfg.sim.nan_guard.output_dir = str(args.output / "nan-dumps")
    disabled_events = {name for name, term in cfg.events.items() if term.mode == "interval"}
    cfg.events = {name: term for name, term in cfg.events.items() if name not in disabled_events}
    cfg.curriculum = {
        name: term for name, term in cfg.curriculum.items()
        if term.params.get("command_name") != "head_pose" and term.params.get("event_name") not in disabled_events
    }
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.commands["twist"] = _BehaviorCommandCfg(
        **{**vars(cfg.commands["twist"]), "class_type": _BehaviorCommand, "resampling_time_range": (100.0, 100.0)}
    )
    cfg.events["set_ground_state"].params.update(
        face_down_prob=0.0, face_up_prob=0.0, sitting_prob=0.0, standing_prob=1.0
    )
    agent = load_rl_cfg(TASK)
    agent.seed = args.seed
    agent.upload_model = False
    with args.checkpoint_file.open("rb") as stream:
        checkpoint_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    dump_yaml(args.output / "env.yaml", asdict(cfg))
    dump_yaml(args.output / "agent.yaml", asdict(agent))
    samples = {name: [] for name in (
        "height", "tilt_deg", "foot_x_b", "hip_error_rad", "stand_leg_error_rad",
        "command", "alpha", "done", "episode_step", "joint_pos", "actions",
    )}
    result = {
        "task": TASK, "checkpoint": str(args.checkpoint_file), "checkpoint_sha256": checkpoint_hash,
        "seed": args.seed, "device": args.device, "num_envs": args.num_envs,
        "passed": False, "completed": False, "actor_command_slots_verified": False,
        "command_schedule_s": {"stand_initial": [0.0, 4.0], "sit": [4.0, 16.0], "stand_final": [16.0, 24.0]},
        "condition": "standing reset; 4s stand, 12s sit, 8s stand; zero head targets; interval disturbances disabled; startup/reset domain randomization retained",
        "disabled_interval_events": sorted(disabled_events),
        "scope": "Learned policy behavior for the specified checkpoint and seed; no training, action overrides, forced seated reset, or hardware validation.",
    }
    trace = {}
    try:
        env = ManagerBasedRlEnv(cfg, device=args.device)
        try:
            wrapper = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
            runner = load_runner_cls(TASK)(wrapper, asdict(agent), device=args.device)
            runner.load(str(args.checkpoint_file), load_cfg={"actor": True}, strict=True, map_location=args.device)
            policy = runner.get_inference_policy(device=args.device)
            obs = wrapper.get_observations()
            assert env.step_dt == CONTROL_DT, "Unexpected control period."
            assert obs["actor"].shape == (args.num_envs, 61), "Unexpected actor dimension."
            assert obs["critic"].shape == (args.num_envs, 74), "Unexpected critic dimension."
            assert env.action_manager.total_action_dim == 14, "Unexpected action dimension."
            robot = env.scene["robot"]
            joint_ids, _ = robot.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
            foot_ids, _ = robot.find_sites(("r_foot", "l_foot"), preserve_order=True)
            home = robot.data.default_joint_pos[:, joint_ids]
            hip_target = torch.tensor(
                [FORWARD_SITTING_JOINT_POS[C.POLICY_JOINT_NAMES[index]] for index in HIP_INDICES], device=args.device
            )
            # 配置快照在初始化及加载课程后保存，反映实际使用的地形数量与课程状态。
            dump_yaml(args.output / "env.yaml", asdict(cfg))
            with torch.no_grad():
                for _ in range(round(DURATION_S / CONTROL_DT)):
                    command = env.command_manager.get_command("twist")
                    torch.testing.assert_close(obs["actor"][:, C.ACTOR_OBSERVATION_SLICES["command"]], command, rtol=0, atol=1e-6)
                    torch.testing.assert_close(obs["actor"][:, C.ACTOR_OBSERVATION_SLICES["head_command"]], torch.zeros(args.num_envs, 4, device=args.device), rtol=0, atol=1e-6)
                    assert torch.isfinite(obs["actor"]).all(), "Non-finite actor observation."
                    actions = policy(obs)
                    assert torch.isfinite(actions).all(), "Non-finite policy action."
                    obs, _, dones, _ = wrapper.step(actions)
                    root = robot.data.root_link_pos_w
                    quat = robot.data.root_link_quat_w
                    offset = robot.data.site_pos_w[:, foot_ids] - root[:, None, :]
                    feet = quat_apply_inverse(
                        quat[:, None, :].expand(-1, 2, -1).reshape(-1, 4), offset.reshape(-1, 3)
                    ).reshape(args.num_envs, 2, 3)
                    tilt = torch.rad2deg(torch.acos((1 - 2 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)).clamp(-1, 1)))
                    joints = robot.data.joint_pos[:, joint_ids]
                    values = {
                        "height": root[:, 2] - env.scene.env_origins[:, 2], "tilt_deg": tilt,
                        "foot_x_b": feet[:, :, 0], "hip_error_rad": (joints[:, HIP_INDICES] - hip_target).abs(),
                        "stand_leg_error_rad": (joints[:, :10] - home[:, :10]).abs(),
                        "command": env.command_manager.get_command("twist"),
                        "alpha": env.command_manager.get_term("twist").alpha,
                        "done": dones, "episode_step": env.episode_length_buf,
                        "joint_pos": joints, "actions": actions,
                    }
                    for name, value in values.items():
                        samples[name].append(value.detach().cpu().numpy().copy())
            result["actor_command_slots_verified"] = True
        finally:
            env.close()
    finally:
        trace = {name: np.asarray(values) for name, values in samples.items()}
        if len(trace["height"]):
            result.update(_summarize_trace(trace))
        error_type, error, _ = sys.exc_info()
        if error_type is not None:
            result.update(passed=False, exception_type=error_type.__name__, exception=str(error))
        np.savez_compressed(args.output / "trace.npz", **trace, dt=CONTROL_DT)
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a learned front-sit and stand cycle without action overrides.")
    parser.add_argument("--checkpoint-file", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True, help="New project-local directory for JSON, NPZ, and configuration evidence.")
    parser.add_argument("--report-only", action="store_true", help="Report behavior failures without a nonzero acceptance exit code.")
    args = parser.parse_args()
    args.checkpoint_file = args.checkpoint_file.resolve()
    args.output = args.output.resolve()
    if args.num_envs < 1:
        parser.error("At least one environment is required.")
    if not args.checkpoint_file.is_file() or not args.checkpoint_file.is_relative_to(ROOT):
        parser.error("The checkpoint must be an existing project-local file.")
    if not args.output.is_relative_to(ROOT) or args.output.exists():
        parser.error("The output must be a new project-local directory.")
    args.output.mkdir(parents=True)
    result = run_behavior(args)
    if not result["passed"] and not args.report_only:
        raise SystemExit(1)


def _valid_trace(num_envs=1):
    """构造包含前坐与站立的几何验收样例，不运行仿真。"""
    count = round(DURATION_S / CONTROL_DT)
    time = np.arange(1, count + 1) * CONTROL_DT
    sit = (time >= 4) & (time < 16)
    command = np.zeros((count, num_envs, 3))
    command[sit, :, 0] = 1
    return {
        "height": np.broadcast_to(np.where(sit, FORWARD_SIT_Z, C.STAND_Z)[:, None], (count, num_envs)).copy(),
        "tilt_deg": np.zeros((count, num_envs)), "foot_x_b": np.full((count, num_envs, 2), 0.1),
        "hip_error_rad": np.zeros((count, num_envs, 2)), "stand_leg_error_rad": np.zeros((count, num_envs, 10)),
        "command": command, "done": np.zeros((count, num_envs)),
        "episode_step": np.broadcast_to(np.arange(1, count + 1)[:, None], (count, num_envs)).copy(),
    }


def test_behavior_requires_feet_in_front_even_at_correct_seated_height():
    trace = _valid_trace()
    assert _summarize_trace(trace)["passed"]
    trace["foot_x_b"][:, :, 0] = -0.04
    assert not _summarize_trace(trace)["passed"]


def test_behavior_requires_eighty_percent_valid_frames_in_the_hold_window():
    trace = _valid_trace()
    times = np.arange(1, len(trace["height"]) + 1) * CONTROL_DT
    indices = np.flatnonzero((times >= 14.0) & (times < 16.0))
    trace["foot_x_b"][indices[:20]] = -0.04
    assert _summarize_trace(trace)["passed"]
    trace["foot_x_b"][indices[20]] = -0.04
    assert not _summarize_trace(trace)["passed"]


def test_behavior_rejects_wrong_hip_pose_and_missing_final_stand():
    trace = _valid_trace()
    trace["hip_error_rad"][:] = 2.4
    assert not _summarize_trace(trace)["passed"]
    trace = _valid_trace()
    trace["height"][1100:] = FORWARD_SIT_Z
    assert not _summarize_trace(trace)["passed"]


def test_behavior_requires_joint_success_in_both_phases_for_same_environments():
    trace = _valid_trace(5)
    trace["foot_x_b"][:, 0] = -0.04
    assert _summarize_trace(trace)["passed"]
    trace["stand_leg_error_rad"][:, 1] = 1.0
    result = _summarize_trace(trace)
    assert result["success_rate"] == 0.6
    assert not result["passed"]


def test_behavior_rejects_automatic_reset_and_partial_or_nonfinite_trace():
    trace = _valid_trace()
    trace["done"][500] = 1
    assert not _summarize_trace(trace)["passed"]
    trace = _valid_trace()
    trace["episode_step"][500] = 0
    assert not _summarize_trace(trace)["passed"]
    trace = {name: value[:500] for name, value in _valid_trace().items()}
    assert not _summarize_trace(trace)["passed"]
    trace = _valid_trace()
    trace["height"][500] = np.nan
    assert not _summarize_trace(trace)["passed"]


if __name__ == "__main__":
    main()
