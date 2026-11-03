# Copyright (c) 2026-2027 zh
"""
内容：
    用原生执行器采集并重新初始化复验前坐/站立端点，供v4课程使用。
    本入口仅采集两类端点；过渡样本需要另经恢复后重试，不能直接倒放或插值补造。

用法（先设置项目内TMPDIR及Warp/Torch缓存）：
    uv run --no-sync python -B tools/collect_forward_states.py --output src/ht_microduck/tasks/assets/forward_v4_states.npz
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
from mjlab.utils.torch import configure_torch_backends

from ht_microduck.robot.ht_microduck_constants import JOINT_NAMES
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_forward_env_cfg import (
    FORWARD_SIT_Z,
    FORWARD_SITTING_JOINT_POS,
)
from ht_microduck.tasks.mdp.forward_behavior import forward_posture_valid
from ht_microduck.tasks.mdp.forward_events import forward_model_fingerprint
from ht_microduck.tasks.mdp.forward_initialization import (
    ForwardInitializedJointPositionActionCfg,
    capture_forward_state,
    set_forward_initial_state,
)

ROOT = Path(__file__).resolve().parents[1]


def collect(output: Path, device: str, num_envs: int, seed: int):
    configure_torch_backends()
    cfg = load_env_cfg("HtDuck-Flat-SitStand-Forward")
    cfg.scene.num_envs, cfg.seed, cfg.episode_length_s = num_envs, seed, 30.0
    cfg.actions["joint_pos"] = ForwardInitializedJointPositionActionCfg(**vars(cfg.actions["joint_pos"]))
    # 初态库使用名义模型；正式训练仍保留原来的startup/reset随机化。
    cfg.events = {name: term for name, term in cfg.events.items() if name in ("htdw3532_init", "bam_init", "expand_bam_friction_fields")}
    cfg.commands["head_pose"].ranges = ((0.0, 0.0),) * 4
    cfg.sim.nan_guard.output_dir = str(output.parent / "collector-nan-dumps")
    env = ManagerBasedRlEnv(cfg, device=device)
    groups, labels, revalidation = [], [], []
    try:
        with torch.no_grad():
            env.reset()
            robot = env.scene["robot"]
            all_ids = torch.arange(num_envs, device=device)
            policy_ids, _ = robot.find_joints(C.POLICY_JOINT_NAMES, preserve_order=True)
            home = robot.data.default_joint_pos.clone()
            seat = home.clone()
            for name, value in FORWARD_SITTING_JOINT_POS.items():
                seat[:, robot.joint_names.index(name)] = value
            for sit, target, height in ((False, home, 0.1534), (True, seat, FORWARD_SIT_Z)):
                env.reset()
                pose = torch.zeros(num_envs, 7, device=device)
                pose[:, 2], pose[:, 3] = height, 1.0
                set_forward_initial_state(env, all_ids, root_pose=pose, root_velocity=torch.zeros(num_envs, 6, device=device), joint_pos=target, joint_vel=torch.zeros_like(target), position_target=target)
                env.action_manager.reset(all_ids)
                env.sim.forward()
                env.scene.update(env.step_dt)
                command = env.command_manager.get_term("twist")
                command.vel_command_b[:, 0] = float(sit)
                command.time_left.fill_(1e6)
                actions = target[:, policy_ids] - home[:, policy_ids] + robot.data.encoder_bias[:, policy_ids]
                for _ in range(400):
                    _, reward, terminated, truncated, _ = env.step(actions)
                    assert torch.isfinite(reward).all() and not (terminated | truncated).any()
                sample = capture_forward_state(env)
                desired = torch.full((num_envs,), sit, dtype=torch.bool, device=device)
                assert forward_posture_valid(env, desired).all(), "Collected endpoint is invalid."
                # 按正式v4的事件+action reset语义恢复，再用相同物理目标重试五秒。
                env.reset()
                set_forward_initial_state(env, all_ids, **{name: torch.as_tensor(value, device=device) for name, value in sample.items()})
                env.action_manager.reset(all_ids)
                env.sim.forward()
                env.scene.update(env.step_dt)
                command.vel_command_b[:, 0] = float(sit)
                command.time_left.fill_(1e6)
                valid_steps = torch.zeros(num_envs, device=device)
                for _ in range(250):
                    _, reward, terminated, truncated, _ = env.step(actions)
                    assert torch.isfinite(reward).all() and not (terminated | truncated).any()
                    valid_steps += forward_posture_valid(env, desired)
                assert torch.all(valid_steps == 250), "Endpoint failed native-reset revalidation."
                groups.append(sample)
                labels.extend([int(sit)] * num_envs)
                revalidation.append({"kind": int(sit), "sample_ids": list(range(len(labels) - num_envs, len(labels))), "protocol": "fixed_target_hold", "seconds": 5.0, "valid_frames_per_sample": valid_steps.cpu().tolist(), "policy_control": False})
        arrays = {name: np.concatenate([group[name] for group in groups]) for name in groups[0]}
        count = len(labels)
        metadata = {
            "schema_version": 1, "mjlab_version": "1.6.0", "joint_names": list(JOINT_NAMES),
            "model_fingerprint": forward_model_fingerprint(),
            "initialization": "physical_state_current_targets_native_reset", "revalidation": revalidation,
            "source": {"tool": "tools/collect_forward_states.py", "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "initializer_sha256": hashlib.sha256((ROOT / "src/ht_microduck/tasks/mdp/forward_initialization.py").read_bytes()).hexdigest(), "seed": seed, "num_envs": num_envs, "control_dt": 0.02, "physics_dt": 0.005, "settling_seconds": 8.0, "nominal_model": True},
            "scope": "Simulation initialization data; fixed-target validation is not learned-policy acceptance or hardware validation.",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(output, **arrays, kind=np.asarray(labels, dtype=np.int32), difficulty=np.zeros(count, dtype=np.float32), validated=np.ones(count, dtype=bool), metadata=json.dumps(metadata))
        output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps({"output": str(output), "samples": count, "endpoint_revalidation_passed": True, "available_kinds": [0, 1]}), flush=True)
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description="Collect physically settled forward curriculum endpoints.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists() or output.suffix != ".npz" or args.num_envs < 1:
        parser.error("Output must be a new project-local .npz file and num-envs must be positive.")
    collect(output, args.device, args.num_envs, args.seed)


if __name__ == "__main__":
    main()
