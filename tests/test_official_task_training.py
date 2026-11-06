# Copyright (c) 2026-2027 zh
"""通过实际注册任务执行显式 GPU 与有界训练验收。

用法（在仓库根目录设置项目内 TMPDIR 和 Warp/Torch 缓存）：
    uv run --no-sync python -B tests/test_official_task_training.py env --task HtDuck-Flat-Velocity
    uv run --no-sync python -B tests/test_official_task_training.py train --task HtDuck-Flat-Velocity --output logs/official_task_alignment_20261029/velocity --min-training-seconds 600

训练预算只累计 runner 报告的采样与 PPO 更新时间。测试日志回调在完整更新后结束上游循环，
再保存并恢复真实检查点；普通 pytest 发现不会运行训练。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

import torch

from ht_microduck.tasks import ht_microduck_contract as C

ROOT = Path(__file__).resolve().parents[1]


def _assert_observations(env, observations, task_id):
    expected = {"actor": C.ACTOR_OBSERVATION_DIM, "critic": C.TASK_CRITIC_OBSERVATION_DIMS[task_id]}
    for name, width in expected.items():
        assert observations[name].shape == (env.num_envs, width)
        assert observations[name].dtype == torch.float32
        assert torch.isfinite(observations[name]).all(), name
    assert tuple(env.observation_manager.active_terms["actor"]) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(env.observation_manager.active_terms["critic"]) == C.critic_observation_terms(task_id)


def check_environment(task_id: str, device: str, num_envs: int, steps: int, seed: int, checkpoint: Path | None = None):
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import load_env_cfg

    torch.manual_seed(seed)
    cfg = load_env_cfg(task_id)
    cfg.scene.num_envs = num_envs
    cfg.seed = seed
    env = ManagerBasedRlEnv(cfg, device=device)
    try:
        observations, _ = env.reset()
        _assert_observations(env, observations, task_id)
        robot = env.scene["robot"]
        joint_ids, _ = robot.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
        term = env.action_manager.get_term("joint_pos")
        assert tuple(term.target_names) == C.POLICY_JOINT_NAMES
        assert term.scale == 1.0
        neutral = robot.data.default_joint_pos[:, joint_ids] - robot.data.encoder_bias[:, joint_ids]
        for index in range(C.ACTION_DIM):
            action = torch.zeros(num_envs, C.ACTION_DIM, device=device)
            action[:, index] = 0.1
            term.process_actions(action)
            term.apply_actions()
            assert torch.allclose(robot.data.joint_pos_target[:, joint_ids], neutral + action, atol=1e-6)
        held_ids, _ = robot.find_joints(C.HELD_JOINT_NAMES, preserve_order=True)
        assert torch.equal(robot.data.joint_pos_target[:, held_ids], robot.data.default_joint_pos[:, held_ids])
        before = robot.data.joint_pos[1:].clone()
        env.reset(env_ids=torch.tensor([0], device=device))
        assert torch.equal(before, robot.data.joint_pos[1:])
        dr_term = env.event_manager.get_term_cfg("randomize_head_com")
        body_ids = robot.indexing.body_ids[dr_term.params["asset_cfg"].body_ids]
        expected_ids = {env.sim.mj_model.body("robot/" + name).id for name in ("neck_pitch_link", "head_pitch_link", "head_yaw_link", "head_roll_link", "r_hip_yaw_link")}
        assert set(body_ids.tolist()) == expected_ids
        before_com = env.sim.model.body_ipos.clone()
        dr_term.func(env, torch.tensor([0], device=device), **dr_term.params)
        changed = (env.sim.model.body_ipos[0] != before_com[0]).any(dim=-1).nonzero().flatten()
        assert set(changed.tolist()) == expected_ids
        assert torch.equal(env.sim.model.body_ipos[1:], before_com[1:])
        env.reset()
        ray_result = None
        if "foot_height_scan" in env.scene.sensors:
            import warp as wp

            from ht_microduck.robot.ht_microduck_constants import FOOT_SITE_NAMES

            feet = env.scene["feet_ground_contact"]
            names = tuple(name.rsplit("/", 1)[-1] for name in feet.primary_names)
            assert names == ("r_foot_collision", "l_foot_collision")
            scan = env.scene["foot_height_scan"]
            site_ids, _ = robot.find_sites(FOOT_SITE_NAMES, preserve_order=True)
            assert torch.allclose(scan.data.frame_pos_w, robot.data.site_pos_w[:, site_ids])
            terrain_id = env.sim.mj_model.geom("terrain").id
            assert torch.all(wp.to_torch(scan._ray_geomid) == terrain_id)
            ray_result = {"foot_order": list(names), "terrain_only": True}
        terminations = 0
        for _ in range(steps):
            action = torch.randn(num_envs, C.ACTION_DIM, device=device) * 0.1
            observations, reward, terminated, _, _ = env.step(action)
            _assert_observations(env, observations, task_id)
            assert torch.isfinite(reward).all()
            terminations += int(terminated.sum())
        stages = [
            stage["step"]
            for term in cfg.curriculum.values()
            for value in term.params.values()
            if isinstance(value, list)
            for stage in value
            if isinstance(stage, dict) and "step" in stage
        ]
        env.common_step_counter = max(stages, default=0) + 1
        observations, _ = env.reset()
        _assert_observations(env, observations, task_id)
        for term in cfg.curriculum.values():
            if "reward_name" in term.params:
                expected = term.params["weight_stages"][-1]["weight"]
                actual = env.reward_manager.get_term_cfg(term.params["reward_name"]).weight
                assert actual == expected, (term.params["reward_name"], actual, expected)
            if "range_stages" in term.params and "command_name" in term.params:
                expected = term.params["range_stages"][-1]["ranges"]
                actual = env.command_manager.get_term(term.params["command_name"]).cfg.ranges
                assert actual == expected
        for _ in range(10):
            observations, reward, _, _, _ = env.step(torch.zeros(num_envs, C.ACTION_DIM, device=device))
            _assert_observations(env, observations, task_id)
            assert torch.isfinite(reward).all()
        if checkpoint is not None:
            from mjlab.rl import RslRlVecEnvWrapper
            from mjlab.tasks.registry import load_rl_cfg, load_runner_cls

            wrapped = RslRlVecEnvWrapper(env)
            agent = load_rl_cfg(task_id)
            agent.upload_model = False
            runner = load_runner_cls(task_id)(wrapped, asdict(agent), device=device)
            infos = runner.load(str(checkpoint), map_location=device)
            assert env.common_step_counter == infos["env_state"]["common_step_counter"]
            observations = wrapped.get_observations()
            _assert_observations(env, observations, task_id)
        result = {
            "task": task_id, "device": device, "seed": seed, "num_envs": num_envs,
            "steps": steps, "actor_dim": C.ACTOR_OBSERVATION_DIM,
            "critic_dim": C.TASK_CRITIC_OBSERVATION_DIMS[task_id], "action_dim": C.ACTION_DIM,
            "step_dt": env.step_dt, "terminations": terminations,
            "foot_rays": ray_result, "late_curriculum_step": max(stages, default=0) + 1,
            "head_com_targets": [env.sim.mj_model.body(index).name for index in sorted(expected_ids)],
            "head_com_local_columns_only": True,
            "reward_terms": list(env.reward_manager.active_terms),
            "curricula": list(env.curriculum_manager.active_terms),
        }
        print(json.dumps(result, indent=2), flush=True)
        return result
    finally:
        env.close()


class _TrainingBudgetComplete(Exception):
    """在一次完整的上游 PPO 更新结束后停止显式验收。"""


def check_ground_heights(args):
    """在真实任务和执行器通道中验证名义前后躺高度带及两秒响应。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import load_env_cfg

    from ht_microduck.tasks.config.ht_microduck.official_robot import (
        FACE_DOWN_SUPPORT_Z,
        FACE_UP_SUPPORT_Z,
    )

    results = []
    for pose, support in (("face_down", FACE_DOWN_SUPPORT_Z), ("face_up", FACE_UP_SUPPORT_Z)):
        cfg = load_env_cfg("HtDuck-Flat-StandUp")
        cfg.scene.num_envs = args.num_envs
        cfg.seed = args.seed
        cfg.curriculum = {}
        params = cfg.events["set_ground_state"].params
        params.update(face_down_prob=float(pose == "face_down"), face_up_prob=float(pose == "face_up"), sitting_prob=0.0, standing_prob=0.0, face_up_roll_max=0.0)
        env = ManagerBasedRlEnv(cfg, device=args.device)
        try:
            env.reset()
            robot = env.scene["robot"]
            heights = robot.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]
            initial = heights.clone()
            assert torch.all(heights >= support + 0.006 - 1e-6)
            assert torch.all(heights <= support + 0.046 + 1e-6)
            assert torch.all(robot.data.projected_gravity_b[:, 0].abs() > 0.99)
            samples = []
            terminated_count = 0
            for _ in range(100):
                observations, rewards, terminated, _, _ = env.step(torch.zeros(args.num_envs, C.ACTION_DIM, device=args.device))
                _assert_observations(env, observations, "HtDuck-Flat-StandUp")
                assert torch.isfinite(rewards).all()
                samples.append((robot.data.root_link_pos_w[:, 2] - env.scene.env_origins[:, 2]).clone())
                terminated_count += int(terminated.sum())
            final = torch.stack(samples[-20:])
            results.append({"pose": pose, "nominal_geometric_support_z": support, "initial_root_z": initial.cpu().tolist(), "height_band": [support + 0.006, support + 0.046], "final_root_z_mean": float(final.mean()), "final_root_z_std": float(final.std()), "steps": 100, "terminations": terminated_count})
        finally:
            env.close()
    print(json.dumps(results, indent=2), flush=True)
    if args.output:
        args.output.resolve().relative_to(ROOT)
        args.output.write_text(json.dumps(results, indent=2) + "\n")


def restore_checkpoint(task_id, checkpoint, device, num_envs, seed):
    """与正式恢复入口一样新建环境，验证完整状态加载及十步推理。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

    cfg = load_env_cfg(task_id)
    cfg.scene.num_envs = num_envs
    cfg.seed = seed
    cfg.sim.nan_guard.output_dir = str(ROOT / ".artifacts/official-task-training/nan-dumps" / task_id)
    agent = load_rl_cfg(task_id)
    agent.upload_model = False
    env = ManagerBasedRlEnv(cfg, device=device)
    wrapped = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
    try:
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        count = 0

        def finite(value):
            nonlocal count
            if isinstance(value, torch.Tensor):
                assert torch.isfinite(value).all()
                count += 1
            elif isinstance(value, dict):
                for item in value.values():
                    finite(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    finite(item)

        finite(payload)
        runner = load_runner_cls(task_id)(wrapped, asdict(agent), device=device)
        infos = runner.load(str(checkpoint), map_location=device)
        assert runner.current_learning_iteration == payload["iter"]
        assert env.common_step_counter == infos["env_state"]["common_step_counter"]
        observations = wrapped.get_observations()
        _assert_observations(env, observations, task_id)
        policy = runner.get_inference_policy(device=device)
        with torch.no_grad():
            for _ in range(10):
                actions = policy(observations)
                assert torch.isfinite(actions).all()
                observations, rewards, _, _ = wrapped.step(actions)
                assert torch.isfinite(rewards).all()
                _assert_observations(env, observations, task_id)
        return {"task": task_id, "iteration": payload["iter"], "env_steps": infos["env_state"]["common_step_counter"], "finite_checkpoint_tensors": count, "restore_steps": 10, "restore_fresh_environment": True}
    finally:
        wrapped.close()


def run_training(args):
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
    from mjlab.utils.os import dump_yaml
    from mjlab.utils.torch import configure_torch_backends

    output = args.output.resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    configure_torch_backends()
    torch.manual_seed(args.seed)
    cfg = load_env_cfg(args.task)
    cfg.scene.num_envs = args.num_envs
    cfg.seed = args.seed
    cfg.sim.nan_guard.output_dir = str(output / "nan-dumps")
    agent = load_rl_cfg(args.task)
    agent.seed = args.seed
    agent.upload_model = False
    env = ManagerBasedRlEnv(cfg, device=args.device)
    wrapped = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
    dump_yaml(output / "params" / "env.yaml", asdict(cfg))
    dump_yaml(output / "params" / "agent.yaml", asdict(agent))
    source_files = {}
    for path in sorted((ROOT / "src" / "ht_microduck" / "tasks").rglob("*.py")):
        relative = path.relative_to(ROOT)
        target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        target.write_bytes(data)
        source_files[str(relative)] = hashlib.sha256(data).hexdigest()
    (output / "source_hashes.json").write_text(json.dumps(source_files, indent=2) + "\n")
    runner_class = load_runner_cls(args.task)
    runner = runner_class(wrapped, asdict(agent), str(output), device=args.device)
    runner.add_git_repo_to_log(__file__)
    original_log = runner.logger.log
    training_seconds = 0.0
    losses = {}
    updates = 0

    def budgeted_log(**kwargs):
        nonlocal training_seconds, losses, updates
        original_log(**kwargs)
        training_seconds += kwargs["collect_time"] + kwargs["learn_time"]
        losses = {name: float(value) for name, value in kwargs["loss_dict"].items()}
        assert all(math.isfinite(value) for value in losses.values()), losses
        updates += 1
        if updates == 1:
            # 首次真实采样和 PPO 更新成功后提供启动凭据，随后可完全阻塞等待。
            (output / "training_active.json").write_text(json.dumps({"task": args.task, "first_update_completed": True}) + "\n")
            print(f"TRAINING_ACTIVE task={args.task}", flush=True)
        if training_seconds >= args.min_training_seconds:
            raise _TrainingBudgetComplete

    runner.logger.log = budgeted_log
    start = time.monotonic()
    try:
        (output / "started.json").write_text(json.dumps({"task": args.task, "minimum_training_seconds": args.min_training_seconds}) + "\n")
        print(f"TRAINING_STARTED task={args.task} minimum_collection_update_seconds={args.min_training_seconds}", flush=True)
        try:
            runner.learn(num_learning_iterations=args.max_iterations, init_at_random_ep_len=True)
        except _TrainingBudgetComplete:
            pass
        assert training_seconds >= args.min_training_seconds, (training_seconds, args.min_training_seconds)
        checkpoint = output / f"model_{runner.current_learning_iteration}.pt"
        runner.save(str(checkpoint))
        runner.logger.writer.flush()
        runner.logger.writer.close()
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        tensor_count = 0

        def finite_tensors(value):
            nonlocal tensor_count
            if isinstance(value, torch.Tensor):
                assert torch.isfinite(value).all()
                tensor_count += 1
            elif isinstance(value, dict):
                for item in value.values():
                    finite_tensors(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    finite_tensors(item)

        finite_tensors(payload)
        result = {
            "task": args.task, "seed": args.seed, "device": args.device,
            "num_envs": args.num_envs, "num_steps_per_env": agent.num_steps_per_env,
            "training_seconds": training_seconds, "wall_seconds": time.monotonic() - start,
            "updates": updates, "iteration": runner.current_learning_iteration,
            "env_steps": payload["infos"]["env_state"]["common_step_counter"],
            "losses": losses, "finite_checkpoint_tensors": tensor_count,
            "checkpoint": str(checkpoint.relative_to(ROOT)),
        }
        (output / "training_result.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        wrapped.close()
    result.update(restore_checkpoint(args.task, checkpoint, args.device, args.num_envs, args.seed))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("env", "train", "ground", "restore"))
    parser.add_argument("--task", default="HtDuck-Flat-Velocity")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--checkpoint-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-training-seconds", type=float, default=600.0)
    parser.add_argument("--max-iterations", type=int, default=100_000)
    args = parser.parse_args()
    if args.mode == "train":
        if args.output is None or args.min_training_seconds < 600:
            parser.error("Training requires --output and at least 600 actual training seconds.")
        run_training(args)
    elif args.mode == "ground":
        check_ground_heights(args)
    elif args.mode == "restore":
        if args.checkpoint_file is None:
            parser.error("Restore requires --checkpoint-file.")
        result = restore_checkpoint(args.task, args.checkpoint_file, args.device, args.num_envs, args.seed)
        if args.output:
            args.output.resolve().relative_to(ROOT)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
    else:
        steps = round(args.seconds / 0.02) if args.seconds is not None else args.steps
        check_environment(args.task, args.device, args.num_envs, steps, args.seed, args.checkpoint_file)


if __name__ == "__main__":
    main()
