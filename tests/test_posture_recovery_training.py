# Copyright (c) 2026-2027 zh
"""
内容：
    显式检查修复后的 VelStand 恢复阶段、初态、局部重置和身体指令。
    默认 pytest 不运行 GPU 或训练；有界训练复用现有正式训练验收入口。

用法：
    uv run --no-sync python -B tests/test_posture_recovery_training.py --device cuda:0 --num-envs 32
    uv run --no-sync python -B tests/test_official_task_training.py train --task HtDuck-Flat-VelStand --num-envs 16 --min-training-seconds 600 --output logs/posture_recovery_20261030/velstand
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.mdp.official_posture_rewards import (
    body_pose_tracking_locomotion,
)
from ht_microduck.tasks.mdp.posture import reset_reward_state


def check_recovery_environment(device: str, num_envs: int, seed: int) -> dict:
    """在实际任务中检查阶段、随机初态、局部reset及真实指令目标。"""
    torch.manual_seed(seed)
    cfg = load_env_cfg("HtDuck-Flat-VelStand")
    cfg.scene.num_envs = num_envs
    cfg.seed = seed
    cfg.sim.nan_guard.output_dir = str(Path(__file__).resolve().parents[1] / ".artifacts/t057/nan-dumps")
    env = ManagerBasedRlEnv(cfg, device=device)
    try:
        robot = env.scene["robot"]
        phase_results = []
        # 与官方 ViewerBase 的回放循环一致，使用 no_grad，避免给上游延迟缓冲混用张量模式。
        with torch.no_grad():
            for iteration in (0, 499, 500, 800, 1200, 1500, 2000, 2500):
                env.common_step_counter = iteration * 24
                observations, _ = env.reset()
                assert observations["actor"].shape == (num_envs, 61)
                assert observations["critic"].shape == (num_envs, 64)
                assert all(torch.isfinite(value).all() for value in observations.values())
                termination = env.termination_manager.get_term_cfg("fell_over")
                expected = math.radians(70) if iteration < 500 else math.pi
                assert termination.params["limit_angle"] == expected
                initial_tilt = torch.rad2deg(torch.acos(torch.clamp(-robot.data.projected_gravity_b[:, 2], -1, 1)))
                initial_z = robot.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
                params = env.event_manager.get_term_cfg("reset_ground_or_stand").params
                assert params["prone_prob"] + params["crouch_prob"] <= 1
                observations, reward, _, _, _ = env.step(torch.zeros(num_envs, C.ACTION_DIM, device=device))
                assert torch.isfinite(reward).all()
                if iteration >= 500:
                    assert not env.termination_manager.get_term("fell_over").any()
                phase_results.append({"iteration": iteration, "prone_prob": params["prone_prob"], "crouch_prob": params["crouch_prob"], "standing_prob": 1 - params["prone_prob"] - params["crouch_prob"], "initial_tilt_over70": int((initial_tilt > 70).sum()), "initial_height_mean": float(initial_z.mean()), "first_step_fell_over": int(env.termination_manager.get_term("fell_over").sum())})

            # 从后期课程重新采样后，局部重置不能移动其他环境或清空其历史。
            env.common_step_counter = 2500 * 24 + 1
            env.reset()
            for _ in range(10):
                observations, reward, _, _, _ = env.step(torch.zeros(num_envs, C.ACTION_DIM, device=device))
                assert torch.isfinite(reward).all()
                assert all(torch.isfinite(value).all() for value in observations.values())
            history = {name: (values.clone(), valid.clone()) for name, (values, valid) in env._ht_posture_prev.items()}
            before = robot.data.root_link_pos_w[1:].clone()
            env.reset(env_ids=torch.tensor([0], device=device))
            assert torch.equal(before, robot.data.root_link_pos_w[1:])
            for name, (values, valid) in history.items():
                current_values, current_valid = env._ht_posture_prev[name]
                assert torch.equal(current_values[1:], values[1:])
                assert torch.equal(current_valid[1:], valid[1:])
                assert not current_valid[0]

            # 使用实际站姿与命令对象核对未跟踪轴及站立门控。
            env.common_step_counter = 0
            env.reset()
            twist = env.command_manager.get_term("twist")
            twist.is_standing_env[:] = True
            body = env.command_manager.get_term("body_pose")
            body._command[:] = 0
            tracking = env.reward_manager.get_term_cfg("body_pose_tracking")
            baseline = body_pose_tracking_locomotion(env, **tracking.params)
            body._command[:, 0] = 1.0
            body._command[:, 1] = -1.0
            body._command[:, 5] = 1.0
            ignored = body_pose_tracking_locomotion(env, **tracking.params)
            assert torch.equal(baseline, ignored)
            body._command[:, 2] = 0.02
            body._command[:, 3] = 0.10
            body._command[:, 4] = -0.10
            changed = body_pose_tracking_locomotion(env, **tracking.params)
            assert torch.isfinite(changed).all() and not torch.allclose(changed, baseline)
            twist.is_standing_env[:] = False
            gated = body_pose_tracking_locomotion(env, **tracking.params)
            assert torch.equal(gated, torch.zeros_like(gated))

            # 固定真实实体的已知姿态，验证恢复状态机能武装、付奖及超时；不代表策略能起身。
            env.common_step_counter = 2500 * 24 + 1
            env.reset()
            all_ids = torch.arange(num_envs, device=device)

            def set_pose(height, quaternion):
                position = env.scene.env_origins.clone()
                position[:, 2] += height
                rotation = torch.tensor(quaternion, device=device).repeat(num_envs, 1)
                robot.write_root_link_pose_to_sim(torch.cat((position, rotation), dim=1))
                robot.write_root_link_velocity_to_sim(torch.zeros(num_envs, 6, device=device))
                env.sim.forward()
                env.scene.update(env.step_dt)

            bounty = env.reward_manager.get_term_cfg("recovery_bounty")
            reset_reward_state(env, all_ids)
            set_pose(C.PRONE_Z + 0.05, (2**-0.5, 0.0, 2**-0.5, 0.0))
            assert torch.all(robot.data.projected_gravity_b[:, 0].abs() > 0.99)
            for _ in range(math.ceil(0.5 / env.step_dt) + 1):
                assert not bounty.func(env, **bounty.params).any()
            set_pose(C.STAND_Z, (1.0, 0.0, 0.0, 0.0))
            assert torch.all(bounty.func(env, **bounty.params) == 1)
            assert not bounty.func(env, **bounty.params).any()
            reset_reward_state(env, all_ids)
            timeout = env.termination_manager.get_term_cfg("fell_over_timeout")
            set_pose(C.PRONE_Z + 0.05, (2**-0.5, 0.0, 2**-0.5, 0.0))
            timed_out = torch.zeros(num_envs, dtype=torch.bool, device=device)
            for _ in range(math.ceil(8.0 / env.step_dt) + 2):
                timed_out = timeout.func(env, **timeout.params)
            assert timed_out.all()
            set_pose(C.STAND_Z, (1.0, 0.0, 0.0, 0.0))
            assert not timeout.func(env, **timeout.params).any()

        # 查看器手工 reset 可位于 no_grad 循环之外；局部状态仍须正确清理。
        env.reset(env_ids=torch.tensor([0], device=device))
        result = {"task": "HtDuck-Flat-VelStand", "device": device, "seed": seed, "num_envs": num_envs, "phases": phase_results, "partial_reset_preserved_neighbors": True, "body_tracking_axes_and_standing_gate": True, "controlled_recovery_bounty": True, "controlled_recovery_timeout": True, "actor_dim": 61, "critic_dim": 64, "action_dim": 14, "step_dt": env.step_dt}
        print(json.dumps(result, indent=2), flush=True)
        return result
    finally:
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.num_envs < 2:
        parser.error("At least two environments are required for partial-reset validation.")
    result = check_recovery_environment(args.device, args.num_envs, args.seed)
    if args.output is not None:
        root = Path(__file__).resolve().parents[1]
        args.output.resolve().relative_to(root)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
