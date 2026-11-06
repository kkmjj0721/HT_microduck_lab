# Copyright (c) 2026-2027 zh
"""
内容：
    显式验证前坐姿态的六秒GPU动作保持，以及至少600秒训练和全量检查点恢复。
    固定动作保持不代表策略学会坐站；普通pytest不自动启动GPU或训练。

用法（先设置项目内TMPDIR和Warp/Torch缓存）：
    uv run --no-sync python -B tests/test_sitstand_forward_training.py env --num-envs 8 --output logs/sitstand_forward_20261031/pose.json
    uv run --no-sync python -B tests/test_sitstand_forward_training.py train --num-envs 32 --output logs/sitstand_forward_20261031/train
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch

from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
)

ROOT = Path(__file__).resolve().parents[1]
TASK = "HtDuck-Flat-SitStand-Forward"


def check_forward_pose(args):
    """用真实动作和接触保持前坐目标，验收方向、稳定性及局部重置隔离。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import load_env_cfg
    from mjlab.utils.lab_api.math import quat_apply_inverse
    from test_official_task_training import _assert_observations

    from ht_microduck.tasks.mdp.events import reset_to_posture

    torch.manual_seed(args.seed)
    cfg = load_env_cfg(TASK)
    cfg.scene.num_envs = args.num_envs
    cfg.seed = args.seed
    cfg.episode_length_s = max(cfg.episode_length_s, args.seconds + 2.0)
    cfg.sim.nan_guard.output_dir = str(args.output.parent / "nan-dumps")
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.events["set_ground_state"].params.update(
        face_down_prob=0.0, face_up_prob=0.0, sitting_prob=1.0,
        standing_prob=0.0, sitting_joint_noise_std=0.0, sitting_tilt_max=0.0,
        sitting_z_min=FORWARD_SIT_Z, sitting_z_max=FORWARD_SIT_Z,
    )
    env = ManagerBasedRlEnv(cfg, device=args.device)
    try:
        with torch.no_grad():
            observations, _ = env.reset()
            _assert_observations(env, observations, TASK)
            robot = env.scene["robot"]
            action_term = env.action_manager.get_term("joint_pos")
            ids = action_term.target_ids
            assert tuple(action_term.target_names) == C.POLICY_JOINT_NAMES
            assert action_term.cfg.bound_targets and action_term.scale == 1.0
            assert env.step_dt == 0.02
            # 使用旧噪声强度复现越界压力，验收真实reset边界而非直接摆入目标。
            reset_params = env.event_manager.get_term_cfg("set_ground_state").params
            reset_params["sitting_joint_noise_std"] = 0.1
            for _ in range(64):
                env.reset()
                limits = robot.data.joint_pos_limits[:, ids]
                sampled = env.sim.data.qpos[:, robot.indexing.joint_q_adr[ids]]
                assert torch.all(sampled >= limits[..., 0] + 0.005 - 1e-6)
                assert torch.all(sampled <= limits[..., 1] - 0.005 + 1e-6)
            reset_params["sitting_joint_noise_std"] = 0.0
            target = robot.data.default_joint_pos[:, ids].clone()
            for name, value in FORWARD_SITTING_JOINT_POS.items():
                target[:, C.POLICY_JOINT_NAMES.index(name)] = value
            limits = robot.data.joint_pos_limits[:, ids]
            assert torch.all((target >= limits[..., 0]) & (target <= limits[..., 1]))
            action = target - robot.data.default_joint_pos[:, ids] + robot.data.encoder_bias[:, ids]
            action_term.process_actions(action)
            action_term.apply_actions()
            torch.testing.assert_close(robot.data.joint_pos_target[:, ids], target)
            neighbors = robot.data.joint_pos[1:].clone()
            neighbor_actions = action_term.applied_targets[1:].clone()
            env.reset(env_ids=torch.tensor([0], device=env.device))
            assert torch.equal(neighbors, robot.data.joint_pos[1:])
            assert torch.equal(neighbor_actions, action_term.applied_targets[1:])
            all_ids = torch.arange(args.num_envs, device=env.device)
            reset_to_posture(
                env, all_ids, FORWARD_SITTING_JOINT_POS, 0.0, 0.0,
                (0.0, 0.0), (0.0, 0.0),
                torch.full((args.num_envs,), FORWARD_SIT_Z, device=env.device), 0.0,
            )
            robot.write_joint_velocity_to_sim(torch.zeros_like(robot.data.joint_vel))
            env.sim.forward()
            env.scene.update(env.step_dt)
            env.episode_length_buf.zero_()
            twist = env.command_manager.get_term("twist")
            twist._alpha.fill_(1.0)
            twist.vel_command_b.zero_()
            twist.vel_command_b[:, 0] = 1.0
            twist.time_left.fill_(args.seconds + 10.0)
            foot_ids, _ = robot.find_sites(("r_foot", "l_foot"), preserve_order=True)
            mouth_ids, _ = robot.find_joints(C.HELD_JOINT_NAMES, preserve_order=True)
            samples = []
            termination_count = 0
            for _ in range(math.ceil(args.seconds / env.step_dt)):
                action = target - robot.data.default_joint_pos[:, ids] + robot.data.encoder_bias[:, ids]
                observations, rewards, terminated, truncated, _ = env.step(action)
                _assert_observations(env, observations, TASK)
                assert torch.isfinite(rewards).all()
                termination_count += int((terminated | truncated).sum())
                physical = robot.data.joint_pos_target[:, ids]
                assert torch.all((physical >= limits[..., 0]) & (physical <= limits[..., 1]))
                torch.testing.assert_close(physical, target)
                torch.testing.assert_close(
                    robot.data.joint_pos_target[:, mouth_ids], robot.data.default_joint_pos[:, mouth_ids]
                )
                root = robot.data.root_link_pos_w
                quat = robot.data.root_link_quat_w
                offset = robot.data.site_pos_w[:, foot_ids] - root[:, None, :]
                feet_b = quat_apply_inverse(
                    quat[:, None, :].expand(-1, 2, -1).reshape(-1, 4), offset.reshape(-1, 3)
                ).reshape(args.num_envs, 2, 3)
                z = root[:, 2] - env.scene.env_origins[:, 2]
                tilt = torch.rad2deg(torch.acos((-robot.data.projected_gravity_b[:, 2]).clamp(-1, 1)))
                samples.append(torch.cat((z[:, None], tilt[:, None], feet_b[:, :, 0]), dim=1))
            data = torch.stack(samples)
            assert torch.isfinite(data).all() and termination_count == 0
            final = data[-round(1.0 / env.step_dt):]
            assert final[:, :, 1].max() < 15.0
            assert final[:, :, 2:].min() > 0.015
            assert final[:, :, 0].std(dim=0).max() < 0.005
            assert (final[:, :, 0].mean(dim=0) - FORWARD_SIT_Z).abs().max() < 0.015
            assert final[:, :, 0].max() < C.STAND_Z - 0.015
            return {
                "task": TASK, "seed": args.seed, "device": args.device,
                "num_envs": args.num_envs, "step_dt": env.step_dt,
                "steps": len(samples), "seconds": len(samples) * env.step_dt,
                "terminations": termination_count, "partial_reset_preserves_neighbors": True,
                "physical_targets_in_limits": True,
                "reset_hard_limit_samples_verified": 64 * args.num_envs,
                "reset_stress_noise_std_rad": 0.1,
                "conditions": "fixed front-seated joint targets, level root, zero initial joint velocities and head targets; interval perturbations removed; startup/reset domain randomization retained",
                "last_second": {
                    "root_height_mean_m": final[:, :, 0].mean(dim=0).cpu().tolist(),
                    "root_height_std_m": final[:, :, 0].std(dim=0).cpu().tolist(),
                    "tilt_max_deg": float(final[:, :, 1].max()),
                    "minimum_foot_forward_x_m": float(final[:, :, 2:].min()),
                },
                "acceptance": {
                    "tilt_max_deg": 15.0, "minimum_foot_forward_x_m": 0.015,
                    "height_std_max_m": 0.005, "height_error_max_m": 0.015,
                    "maximum_height_m": C.STAND_Z - 0.015,
                },
                "scope": "fixed actuator target hold, not learned sit/stand performance",
            }
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description="Validate front-seated pose or budgeted training.")
    parser.add_argument("mode", choices=("env", "train"))
    parser.add_argument("--task", choices=(TASK,), default=TASK)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-training-seconds", type=float, default=600.0)
    parser.add_argument("--max-iterations", type=int, default=100_000)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.relative_to(ROOT)
    if args.num_envs < 2 or not math.isfinite(args.seconds) or args.seconds < 6.0:
        parser.error("At least two environments and six hold seconds are required.")
    if args.mode == "train":
        if not math.isfinite(args.min_training_seconds) or args.min_training_seconds < 600:
            parser.error("Training requires at least 600 actual collection/update seconds.")
        from test_bounded_action_training import check_training_metrics
        from test_official_task_training import run_training

        run_training(args)
        check_training_metrics(args.output)
    else:
        result = check_forward_pose(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
