# Copyright (c) 2026-2027 zh
"""
内容：
    通过实际任务检查 CyberDuck V2 混合动作、连续转角观测、接地步进与局部重置。
    普通测试仅做少量 CPU 步进；显式专项可以指定设备和步数，不启动策略训练。

用法（先设置项目内 TMPDIR 和 Warp/Torch 缓存）：
    uv run --no-sync python -B tests/test_cyberduck_v2_motion.py --device cuda:0 --steps 300 --output .artifacts/cyberduck-motion-new
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import torch

from ht_microduck.tasks import cyberduck_v2_contract as C

ROOT = Path(__file__).resolve().parents[1]
TASK = "CyberDuckV2-Flat-Velocity"


def _assert_observations(env, observations):
    """检查实际环境输出，避免只验证配置声明。"""
    for name, width in (("actor", 49), ("critic", 56)):
        assert observations[name].shape == (env.num_envs, width)
        assert observations[name].dtype == torch.float32
        assert observations[name].device == torch.device(env.device)
        assert torch.isfinite(observations[name]).all(), name


def check_environment(device: str, steps: int = 3, seed: int = 3532):
    """以三环境验证接口与动力学数值；不验收未训练策略的滚动性能。"""
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import load_env_cfg

    cfg = load_env_cfg(TASK, play=True)
    cfg.scene.num_envs = 3
    cfg.seed = seed
    for group in cfg.observations.values():
        group.enable_corruption = False
    env = ManagerBasedRlEnv(cfg, device=device)
    try:
        observations, _ = env.reset()
        _assert_observations(env, observations)
        robot = env.scene["robot"]
        pos_ids, _ = robot.find_joints(C.POLICY_POSITION_JOINT_NAMES, preserve_order=True)
        vel_ids, _ = robot.find_joints(C.POLICY_VELOCITY_JOINT_NAMES, preserve_order=True)
        held_ids, _ = robot.find_joints(C.HELD_JOINT_NAMES, preserve_order=True)
        position = env.action_manager.get_term("joint_pos")
        velocity = env.action_manager.get_term("joint_vel")
        assert tuple(position.target_names) == C.POLICY_POSITION_JOINT_NAMES
        assert tuple(velocity.target_names) == C.POLICY_VELOCITY_JOINT_NAMES
        assert (position.action_dim, velocity.action_dim) == (12, 2)
        for name in ("actuator_forcerange", "actuator_biasprm", "dof_frictionloss", "dof_damping"):
            field = getattr(env.sim.model, name)
            assert field.shape[0] == 3 and field.stride(0) != 0, name

        # 独立给每一槽位脉冲，核对位置、速度和保持关节互不串位。
        default = robot.data.default_joint_pos[:, pos_ids]
        for index in range(14):
            action = torch.zeros(3, 14, device=device)
            action[:, index] = 0.2
            env.action_manager.process_action(action)
            env.action_manager.apply_action()
            torch.testing.assert_close(robot.data.joint_pos_target[:, pos_ids], default + 0.25 * action[:, :12])
            torch.testing.assert_close(robot.data.joint_vel_target[:, vel_ids], 4.0 * action[:, 12:])
            torch.testing.assert_close(robot.data.joint_pos_target[:, held_ids], robot.data.default_joint_pos[:, held_ids])
        for direction in (-1.0, 1.0):
            env.action_manager.process_action(torch.full((3, 14), direction * 100.0, device=device))
            env.action_manager.apply_action()
            limits = robot.data.joint_pos_limits[:, pos_ids]
            targets = robot.data.joint_pos_target[:, pos_ids]
            assert ((targets >= limits[..., 0]) & (targets <= limits[..., 1])).all()
            torch.testing.assert_close(robot.data.joint_vel_target[:, vel_ids], torch.full((3, 2), direction * 8.0, device=device))

        # 改变累计踝角和对应从动角，不推进物理；actor 不应依赖转过多少圈。
        env.reset()
        before = env.observation_manager.compute()["actor"].clone()
        joint_pos = robot.data.joint_pos.clone()
        joint_pos[:, vel_ids] += 20.0 * math.pi
        from ht_microduck.robot.cyberduck_v2_constants import (
            MIMIC_JOINT_NAMES,
            MIMIC_MULTIPLIER,
        )

        follower_ids, _ = robot.find_joints(MIMIC_JOINT_NAMES, preserve_order=True)
        joint_pos[:, follower_ids] += 20.0 * math.pi * MIMIC_MULTIPLIER
        robot.write_joint_position_to_sim(joint_pos)
        env.sim.forward()
        env.scene.update(0.0)
        after = env.observation_manager.compute()["actor"]
        torch.testing.assert_close(after, before)

        env.reset()
        sensor = env.scene[C.WHEEL_CONTACT_SENSOR_NAME]
        actual_names = tuple(name.rsplit("/", 1)[-1] for name in sensor.primary_names)
        assert actual_names == C.WHEEL_GEOM_NAMES
        origin = robot.data.root_link_pos_w.clone()
        peak_force = 0.0
        contact_counts = torch.zeros(4, device=device)
        terminations = 0
        for step in range(steps):
            action = torch.zeros(3, 14, device=device)
            action[1, 12:] = 0.1
            action[2, 12:] = torch.tensor([-0.1, 0.1], device=device)
            # 后半段施加零速度目标，覆盖局部 reset 前的制动命令。
            if step >= max(1, steps // 2):
                action[:, 12:] = 0.0
            observations, rewards, terminated, _, _ = env.step(action)
            _assert_observations(env, observations)
            assert torch.isfinite(rewards).all()
            assert torch.isfinite(env.sim.data.qpos[:]).all()
            assert torch.isfinite(env.sim.data.qvel[:]).all()
            force = env.sim.data.actuator_force[:]
            assert torch.isfinite(force).all()
            assert (force.abs() <= 2.0001).all()
            peak_force = max(peak_force, float(force.abs().max()))
            contact_counts += (sensor.data.found > 0).float().mean(dim=0)
            torch.testing.assert_close(robot.data.joint_pos_target[:, held_ids], robot.data.default_joint_pos[:, held_ids])
            terminations += int(terminated.sum())

        # 给不同环境保留不同目标和历史，重置第零个环境不得清掉其余环境。
        action = torch.zeros(3, 14, device=device)
        action[:, 0] = torch.tensor([0.1, 0.2, -0.1], device=device)
        action[:, 12:] = torch.tensor([[0.1, -0.1], [0.2, 0.1], [-0.1, 0.2]], device=device)
        env.action_manager.process_action(action)
        env.action_manager.apply_action()
        saved = {name: getattr(robot.data, name)[1:].clone() for name in ("joint_pos", "joint_vel", "joint_pos_target", "joint_vel_target")}
        saved_actions = env.action_manager.action[1:].clone()
        observations, _ = env.reset(env_ids=torch.tensor([0], device=device))
        _assert_observations(env, observations)
        for name, expected in saved.items():
            torch.testing.assert_close(getattr(robot.data, name)[1:], expected, rtol=0, atol=0)
        torch.testing.assert_close(env.action_manager.action[1:], saved_actions, rtol=0, atol=0)
        assert torch.count_nonzero(env.action_manager.action[0]) == 0
        torch.testing.assert_close(robot.data.joint_pos_target[0], robot.data.default_joint_pos[0])
        assert torch.count_nonzero(robot.data.joint_vel_target[0]) == 0

        displacement = (robot.data.root_link_pos_w[1:, :2] - origin[1:, :2]).tolist()
        return {
            "scope": "task integration, control mapping and finite simulation; not policy performance or hardware calibration",
            "task": TASK, "device": device, "seed": seed, "num_envs": 3,
            "control_steps": steps, "physics_steps": steps * 10,
            "step_dt_s": env.step_dt, "actor_dim": 49, "critic_dim": 56, "action_dim": 14,
            "wheel_order": actual_names, "mean_contact_fraction": (contact_counts / steps).tolist(),
            "peak_actuator_force_nm": peak_force, "terminations": terminations,
            "unreset_env_xy_displacement_m": displacement,
            "one_hot_mapping": True, "continuous_angle_invariance": True,
            "position_and_velocity_limits": True, "partial_reset_isolation": True,
        }, asdict(cfg)
    finally:
        env.close()


def test_cyberduck_task_mixed_control_and_reset_runtime_cpu():
    result, _ = check_environment("cpu")
    assert result["partial_reset_isolation"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check CyberDuck V2 task integration without training.")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=3532)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.steps < 1 or not output.is_relative_to(ROOT) or output == ROOT:
        parser.error("steps must be positive and output must be a new directory inside the project")
    output.mkdir(parents=True, exist_ok=False)
    result, env_cfg = check_environment(args.device, args.steps, args.seed)
    import yaml

    (output / "env.yaml").write_text(yaml.dump(env_cfg, sort_keys=False))
    result["versions"] = {name: version(name) for name in ("mjlab", "mujoco", "mujoco-warp", "torch")}
    result["git_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    result["git_status"] = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
    result["test_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
