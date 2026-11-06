# Copyright (c) 2026-2027 zh
"""
内容：
    显式验证关节目标约束的GPU动作、固定初态推理及至少600秒训练与检查点恢复。
    普通pytest不自动启动GPU或训练；训练复用既有正式验收接口。

用法（先设置项目内TMPDIR和Warp/Torch缓存）：
    uv run --no-sync python -B tests/test_bounded_action_training.py env --task HtDuck-Flat-SitStand --output logs/action_bounds_20261030/validation/sitstand_gpu.json
    uv run --no-sync python -B tests/test_bounded_action_training.py train --task HtDuck-Flat-SitStand --num-envs 32 --output logs/action_bounds_20261030/sitstand
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import torch

from ht_microduck.tasks import ht_microduck_contract as C

ROOT = Path(__file__).resolve().parents[1]
METRICS = (
    "requested_target_outside_limits", "applied_target_outside_limits", "target_clip_fraction",
    "actuator_saturation_fraction", "actuator_saturation_duration",
)


def check_gpu_actions(args):
    """用实体实际目标检查边界，再在固定初态和命令下验证物理采样。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

    from ht_microduck.tasks.config.ht_microduck.official_robot import (
        FACE_DOWN_SUPPORT_Z,
        FACE_UP_SUPPORT_Z,
    )
    from ht_microduck.tasks.mdp.actions import BoundedJointPositionAction
    from ht_microduck.tasks.mdp.events import reset_to_posture
    from ht_microduck.tasks.mdp.posture import reset_reward_state

    torch.manual_seed(args.seed)
    cfg = load_env_cfg(args.task)
    cfg.scene.num_envs = args.num_envs
    cfg.seed = args.seed
    cfg.actions["joint_pos"].bound_targets = not args.legacy
    cfg.sim.nan_guard.output_dir = str(ROOT / ".artifacts/t058_20261030/nan_dumps")
    for name in ("push_robot", "seated_tip", "seated_head_jerk"):
        cfg.events.pop(name, None)
    for name in ("push_magnitude", "seated_tip_range", "seated_head_jerk_prob"):
        cfg.curriculum.pop(name, None)
    env = ManagerBasedRlEnv(cfg, device=args.device)
    wrapped = RslRlVecEnvWrapper(env)
    try:
        with torch.no_grad():
            robot = env.scene["robot"]
            term = env.action_manager.get_term("joint_pos")
            assert isinstance(term, BoundedJointPositionAction)
            assert tuple(term.target_names) == C.POLICY_JOINT_NAMES
            ids = term.target_ids
            limits = robot.data.joint_pos_limits[:, ids]
            assert term.action_dim == 14 and env.step_dt == 0.02
            observations = wrapped.get_observations()
            assert observations["actor"].shape == (args.num_envs, 61)
            assert observations["critic"].shape == (args.num_envs, 74 if args.task.endswith("SitStand") else 64)
            mouth_ids, _ = robot.find_joints(C.HELD_JOINT_NAMES, preserve_order=True)
            saved_bias = robot.data.encoder_bias[:, ids].clone()
            for bias in (-0.015, 0.015):
                robot.data.encoder_bias[:, ids] = bias
                for bound in (False, True):
                    term.cfg.bound_targets = bound
                    for value in (-30.0, 30.0):
                        action = torch.full((args.num_envs, 14), value, device=env.device)
                        term.process_actions(action)
                        term.apply_actions()
                        request = robot.data.default_joint_pos[:, ids] + action - bias
                        expected = torch.clamp(request, min=limits[..., 0], max=limits[..., 1]) if bound else request
                        torch.testing.assert_close(robot.data.joint_pos_target[:, ids], expected)
                        torch.testing.assert_close(term.requested_targets, request)
                        torch.testing.assert_close(term.raw_action, action)
            term.cfg.bound_targets = True
            sit = robot.data.default_joint_pos[:, ids].clone()
            for joint, value in C.LOW_POSTURE_JOINT_POS.items():
                sit[:, C.POLICY_JOINT_NAMES.index(joint)] = value
            term.process_actions(sit - robot.data.default_joint_pos[:, ids] + robot.data.encoder_bias[:, ids])
            term.apply_actions()
            torch.testing.assert_close(robot.data.joint_pos_target[:, ids], sit)
            neighbors = term.applied_targets[1:].clone()
            env.reset(env_ids=torch.tensor([0], device=env.device))
            assert torch.equal(term.applied_targets[1:], neighbors)
            assert term.applied_targets[0].eq(0).all()
            robot.data.encoder_bias[:, ids] = saved_bias
            torch.testing.assert_close(robot.data.joint_pos_target[:, mouth_ids], robot.data.default_joint_pos[:, mouth_ids])
            term.cfg.bound_targets = not args.legacy

            checkpoint_sha = None
            policy = None
            if args.checkpoint_file is not None:
                agent = load_rl_cfg(args.task)
                agent.upload_model = False
                runner = load_runner_cls(args.task)(wrapped, asdict(agent), device=args.device)
                runner.load(str(args.checkpoint_file), load_cfg={"actor": True}, map_location=args.device)
                policy = runner.get_inference_policy(device=args.device)
                checkpoint_sha = hashlib.sha256(args.checkpoint_file.read_bytes()).hexdigest()
            else:
                env.common_step_counter = 2500 * 24 + 1
            all_ids = torch.arange(args.num_envs, device=env.device)
            cases = (
                (("stand", False, 0, 0, 0), ("sit", True, 0, 0, 1), ("sit_to_stand", True, 0, 0, 0), ("stand_to_sit", False, 0, 0, 1))
                if args.task.endswith("SitStand") else
                (("stand", False, 0, 0, 0), ("walk", False, 0, 0, 0.2), ("sit", True, 0, 0, 0), ("face_down", False, 0, 90, 0), ("face_up", False, 0, -90, 0), ("side", False, 90, 0, 0))
            )
            results = []
            for label, sitting, roll, pitch, command in cases:
                wrapped.reset()
                height = C.SIT_Z if sitting else C.STAND_Z
                if pitch:
                    height = (FACE_DOWN_SUPPORT_Z if pitch > 0 else FACE_UP_SUPPORT_Z) + 0.006
                elif roll:
                    height = C.SIDE_Z
                reset_to_posture(env, all_ids, C.LOW_POSTURE_JOINT_POS if sitting else {}, 0, roll, (pitch, pitch), (0, 0), torch.full((args.num_envs,), height, device=env.device), 0)
                env.sim.forward()
                env.scene.update(env.step_dt)
                env.action_manager.reset(all_ids)
                env.metrics_manager.reset(all_ids)
                reset_reward_state(env, all_ids)
                env.episode_length_buf.zero_()
                twist = env.command_manager.get_term("twist")
                if args.task.endswith("SitStand"):
                    twist._alpha[:] = float(sitting)

                def fixed_commands():
                    twist.time_left[:] = 1000
                    twist.vel_command_b[:] = 0
                    twist.vel_command_b[:, 0] = command
                    twist.is_heading_env[:] = False
                    twist.is_standing_env[:] = command == 0
                    for name in ("head_pose", "body_pose"):
                        if name in env.command_manager.active_terms:
                            pose = env.command_manager.get_term(name)
                            pose.time_left[:] = 1000
                            pose.command[:] = 0
                            if name == "body_pose":
                                pose._raw[:] = 0

                fixed_commands()
                obs = wrapped.get_observations()
                active = torch.ones(args.num_envs, dtype=torch.bool, device=env.device)
                samples = []
                for _ in range(args.steps):
                    fixed_commands()
                    action = policy(obs) if policy is not None else torch.randn(args.num_envs, 14, device=env.device) * 3
                    obs, reward, done, _ = wrapped.step(action)
                    assert torch.isfinite(reward).all() and all(torch.isfinite(value).all() for value in obs.values())
                    physical = robot.data.joint_pos_target[:, ids]
                    physical_outside = ((physical < limits[..., 0]) | (physical > limits[..., 1])).float().mean(dim=1)
                    if not args.legacy:
                        assert physical_outside.eq(0).all()
                    active &= ~done.bool()
                    z = robot.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
                    tilt = torch.rad2deg(torch.acos((-robot.data.projected_gravity_b[:, 2]).clamp(-1, 1)))
                    values = env.metrics_manager._step_values
                    assert torch.isfinite(values).all()
                    ordered = torch.stack([values[:, env.metrics_manager.active_terms.index(name)] for name in METRICS], dim=1)
                    samples.append(torch.cat((z[:, None], tilt[:, None], robot.data.root_link_lin_vel_b[:, :1], physical_outside[:, None], ordered, active.float()[:, None]), dim=1))
                data = torch.stack(samples)
                valid = data[..., -1].bool()
                chosen = data[valid]
                assert len(chosen) > 0
                results.append({
                    "case": label, "first_episode_frames": int(valid.sum()), "height_mean_m": float(chosen[:, 0].mean()),
                    "tilt_mean_deg": float(chosen[:, 1].mean()), "vx_mean_m_s": float(chosen[:, 2].mean()),
                    "physical_target_outside_fraction": float(data[..., 3].mean()),
                    "metrics_mean": dict(zip(METRICS, data[..., 4:9].mean(dim=(0, 1)).cpu().tolist(), strict=True)),
                })
            return {
                "task": args.task, "seed": args.seed, "num_envs": args.num_envs, "device": args.device,
                "bound_targets": not args.legacy, "checkpoint": str(args.checkpoint_file) if args.checkpoint_file else None,
                "checkpoint_sha256": checkpoint_sha, "steps_per_case": args.steps, "step_dt": env.step_dt,
                "conditions": "fixed initial poses and commands, zero head/body targets, interval perturbations removed; startup DR retained",
                "extreme_actions_and_encoder_bias": True, "sitting_target_reachable": True,
                "partial_reset_preserves_neighbors": True, "cases": results,
            }
    finally:
        wrapped.close()


def check_training_metrics(output):
    """训练结束后检查原始事件，指标有限且物理目标越界为零。"""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    accumulator = EventAccumulator(str(output), size_guidance={"scalars": 0})
    accumulator.Reload()
    result = {}
    for name in METRICS:
        values = torch.tensor([event.value for event in accumulator.Scalars("Episode_Metrics/" + name)])
        assert values.numel() > 0 and torch.isfinite(values).all(), name
        assert (values >= 0).all(), name
        if name != "actuator_saturation_duration":
            assert (values <= 1).all(), name
        if name == "applied_target_outside_limits":
            assert values.eq(0).all()
        result[name] = {"records": len(values), "mean": float(values.mean()), "max": float(values.max())}
    (output / "bounded_metrics.json").write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("env", "train"))
    parser.add_argument("--task", choices=("HtDuck-Flat-SitStand", "HtDuck-Flat-VelStand"), required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--checkpoint-file", type=Path)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-training-seconds", type=float, default=600)
    parser.add_argument("--max-iterations", type=int, default=100_000)
    args = parser.parse_args()
    args.output.resolve().relative_to(ROOT)
    if args.num_envs < 2 or args.steps < 1:
        parser.error("At least two environments and one step are required.")
    if args.mode == "train":
        if args.legacy or args.checkpoint_file or args.min_training_seconds < 600:
            parser.error("Training uses fresh bounded actions and at least 600 actual training seconds.")
        from test_official_task_training import run_training

        run_training(args)
        check_training_metrics(args.output)
    else:
        result = check_gpu_actions(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
