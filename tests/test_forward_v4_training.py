# Copyright (c) 2026-2027 zh
"""
内容：
    显式检查v4初态、局部控制回填、固定目标保持及至少600秒PPO/完整恢复。
    固定目标保持只验收初态，不代表策略效果；策略行为由独立入口验收。

用法（先设置项目内TMPDIR和Warp/Torch缓存）：
    uv run --no-sync python -B tests/test_forward_v4_training.py env --output logs/forward_v4_20261103/environment.json
    uv run --no-sync python -B tests/test_forward_v4_training.py train --num-envs 512 --seed 0 --min-training-seconds 600 --output logs/forward_v4_20261103/train_hold
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import torch

from ht_microduck.tasks import ht_microduck_contract as C

ROOT = Path(__file__).resolve().parents[1]
TASK = "HtDuck-Flat-SitStand-Forward-V4"


def check_environment(args):
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import load_env_cfg
    from test_official_task_training import _assert_observations

    from ht_microduck.tasks.mdp.forward_behavior import forward_posture_valid

    cfg = load_env_cfg(TASK)
    cfg.scene.num_envs, cfg.seed, cfg.episode_length_s = args.num_envs, args.seed, 10.0
    cfg.sim.nan_guard.output_dir = str(args.output.parent / "environment-nan-dumps")
    env = ManagerBasedRlEnv(cfg, device=args.device)
    try:
        with torch.no_grad():
            obs, _ = env.reset()
            _assert_observations(env, obs, TASK)
            assert env.step_dt == 0.02
            robot = env.scene["robot"]
            action = env.action_manager.get_term("joint_pos")
            assert tuple(action.target_names) == C.POLICY_JOINT_NAMES
            target = robot.data.joint_pos_target[:, action.target_ids]
            bias = robot.data.encoder_bias[:, action.target_ids]
            raw = target + bias - robot.data.default_joint_pos[:, action.target_ids]
            torch.testing.assert_close(env.action_manager.action, raw)
            assert forward_posture_valid(env).all()
            ids = torch.tensor([0], device=args.device)
            neighbors = env.action_manager.action[1:].clone()
            targets = robot.data.joint_pos_target[1:].clone()
            delays = [(act._delay_buffer, act._delay_buffer.peek()[1:].clone(), act._delay_buffer._step_count[1:].clone()) for act in robot.actuators if act._delay_buffer is not None]
            env.action_manager.reset(ids)
            assert torch.equal(neighbors, env.action_manager.action[1:])
            assert torch.equal(targets, robot.data.joint_pos_target[1:])
            for buffer, previous, count in delays:
                assert torch.equal(previous, buffer.peek()[1:]) and torch.equal(count, buffer._step_count[1:])
            for _ in range(250):
                obs, reward, terminated, truncated, _ = env.step(raw)
                _assert_observations(env, obs, TASK)
                assert torch.isfinite(reward).all() and not (terminated | truncated).any()
                assert forward_posture_valid(env).all(), "Fixed-target endpoint lost validity."
                assert (action.applied_targets >= robot.data.joint_pos_limits[:, action.target_ids, 0]).all()
                assert (action.applied_targets <= robot.data.joint_pos_limits[:, action.target_ids, 1]).all()
            before = robot.data.joint_pos[1:].clone()
            env.reset(env_ids=ids)
            assert torch.equal(before, robot.data.joint_pos[1:])
            result = {"task": TASK, "passed": True, "num_envs": args.num_envs, "seed": args.seed, "steps": 250, "control_dt": env.step_dt, "dimensions": [61, 74, 14], "bank_sha256": env._forward_state_bank.sha256, "fixed_target_endpoint_seconds": 5.0, "action_initializer_neighbor_history_unchanged": True, "public_reset_neighbor_positions_unchanged": True, "scope": "Initialization and native control-channel validation; not learned policy behavior. Public mjlab reset may advance all native delay channels after the local initializer."}
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2), flush=True)
    finally:
        env.close()


def main():
    from test_official_task_training import run_training

    parser = argparse.ArgumentParser(description="Explicit forward v4 environment and training validation.")
    parser.add_argument("mode", choices=("env", "train", "restore"))
    parser.add_argument("--checkpoint-file", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-training-seconds", type=float, default=600.0)
    parser.add_argument("--max-iterations", type=int, default=100_000)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.task = TASK
    if not args.output.is_relative_to(ROOT) or args.output.exists() or args.num_envs < 2:
        parser.error("Output must be new and project-local; at least two environments are required.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "restore":
        if args.checkpoint_file is None or not args.checkpoint_file.resolve().is_relative_to(ROOT):
            parser.error("Restore requires a project-local checkpoint.")
        check_restored_snapshot(args)
    elif args.mode == "train":
        if args.min_training_seconds < 600:
            parser.error("Training requires at least 600 actual collection/update seconds.")
        run_training(args)
        # 训练入口通用快照只收录Python源码，此处保留任务实际使用的初态资源。
        from ht_microduck.tasks.mdp.forward_commands import DEFAULT_FORWARD_STATE_BANK
        bank = Path(DEFAULT_FORWARD_STATE_BANK)
        shutil.copy2(bank, args.output / bank.name)
        shutil.copy2(bank.with_suffix(".json"), args.output / bank.with_suffix(".json").name)
    else:
        check_environment(args)


def check_restored_snapshot(args):
    """验证原有训练状态未变、初态库随检查点保存，且新文件可完整恢复。"""
    from dataclasses import asdict

    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
    from test_official_task_training import restore_checkpoint

    args.output.mkdir()
    cfg = load_env_cfg(TASK)
    cfg.scene.num_envs, cfg.seed = args.num_envs, args.seed
    cfg.sim.nan_guard.output_dir = str(args.output / "nan-dumps")
    agent = load_rl_cfg(TASK)
    agent.upload_model = False
    env = ManagerBasedRlEnv(cfg, device=args.device)
    wrapper = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
    try:
        runner = load_runner_cls(TASK)(wrapper, asdict(agent), device=args.device)
        runner.load(str(args.checkpoint_file), map_location=args.device)
        checkpoint = args.output / "model_with_bank.pt"
        runner.save(str(checkpoint))
        old = torch.load(args.checkpoint_file, map_location="cpu", weights_only=False)
        new = torch.load(checkpoint, map_location="cpu", weights_only=False)
        compared = 0

        def compare(left, right):
            nonlocal compared
            if isinstance(left, torch.Tensor):
                assert torch.equal(left, right)
                compared += 1
            elif isinstance(left, dict):
                assert left.keys() == right.keys()
                for name in left:
                    compare(left[name], right[name])
            elif isinstance(left, (tuple, list)):
                assert len(left) == len(right)
                for first, second in zip(left, right, strict=True):
                    compare(first, second)
            else:
                assert left == right

        for name in ("actor_state_dict", "critic_state_dict", "optimizer_state_dict", "iter"):
            compare(old[name], new[name])
        state = new["infos"]["forward_curriculum"]
        assert hashlib.sha256(state["bank_snapshot"]).hexdigest() == state["bank_sha256"]
        assert old["infos"]["env_state"] == new["infos"]["env_state"]
    finally:
        wrapper.close()
    result = restore_checkpoint(TASK, checkpoint, args.device, args.num_envs, args.seed)
    result.update({"passed": True, "unchanged_training_tensors": compared, "bank_snapshot_hash_verified": True, "checkpoint": str(checkpoint.relative_to(ROOT))})
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
