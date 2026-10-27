"""Verify the frozen control/observation contract against a live environment.

This is the T022 acceptance check. It confirms that what the policy will see and
control matches ``ht_microduck.tasks.common.contract`` exactly, and that the
non-policy joints really are held.

Run:
    uv run --no-sync python -B tools/check_task_contract.py --device cuda:0
"""

from __future__ import annotations

import argparse

import torch

from ht_microduck.robots.ht_microduck.ht_microduck_constants import (
    HOME_JOINT_POS,
    JOINT_NAMES,
)
from ht_microduck.tasks.common import contract as C
from ht_microduck.tasks.flat_velocity import make_flat_velocity_env_cfg


def _fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    from mjlab.envs import ManagerBasedRlEnv

    cfg = make_flat_velocity_env_cfg(num_envs=args.num_envs, seed=args.seed)
    env = ManagerBasedRlEnv(cfg, device=args.device)
    obs, info = env.reset()
    del info

    # --- timing -------------------------------------------------------------
    control_dt = env.cfg.sim.mujoco.timestep * env.cfg.decimation
    if abs(control_dt - 0.02) > 1e-12:
        _fail(f"Control period is {control_dt}s, expected 0.02s (50 Hz).")
    if abs(env.step_dt - 0.02) > 1e-12:
        _fail(f"env.step_dt is {env.step_dt}s, expected 0.02s.")
    print(f"timing: dt={env.cfg.sim.mujoco.timestep}s decimation={env.cfg.decimation} "
          f"control={1.0 / control_dt:.1f}Hz")

    # --- action space -------------------------------------------------------
    if env.action_manager.total_action_dim != C.ACTION_DIM:
        _fail(
            f"Action dim {env.action_manager.total_action_dim} != contract "
            f"{C.ACTION_DIM}."
        )
    term = env.action_manager.get_term("joint_pos")
    if tuple(term.target_names) != C.POLICY_JOINT_NAMES:
        _fail(f"Action joint order {tuple(term.target_names)} != contract order.")
    print(f"action: dim={C.ACTION_DIM} scale={C.ACTION_SCALE} names ok")

    # --- observation space --------------------------------------------------
    if tuple(obs["actor"].shape) != (args.num_envs, C.ACTOR_OBSERVATION_DIM):
        _fail(
            f"Actor obs {tuple(obs['actor'].shape)} != "
            f"({args.num_envs}, {C.ACTOR_OBSERVATION_DIM})."
        )
    if tuple(obs["critic"].shape) != (args.num_envs, C.CRITIC_OBSERVATION_DIM):
        _fail(
            f"Critic obs {tuple(obs['critic'].shape)} != "
            f"({args.num_envs}, {C.CRITIC_OBSERVATION_DIM})."
        )
    active = env.observation_manager.active_terms["actor"]
    if tuple(active) != C.ACTOR_OBSERVATION_TERMS:
        _fail(f"Actor term order {tuple(active)} != contract order.")
    if "base_lin_vel" in active:
        _fail("base_lin_vel leaked into the actor group; it is critic-only.")
    print(f"observations: actor={C.ACTOR_OBSERVATION_DIM} "
          f"critic={C.CRITIC_OBSERVATION_DIM}, order ok, no privileged actor terms")

    # --- privileged term is genuinely absent from the actor ------------------
    # Structural check: the contract already forbids base_lin_vel in the actor.
    # A numeric probe is unreliable here because re-stepping the sim perturbs
    # every term, so instead confirm the critic's last 3 slots really are the
    # linear velocity by checking they match robot.data.root_link_lin_vel_b.
    robot = env.scene["robot"]
    joint_idx = [JOINT_NAMES.index(n) for n in C.POLICY_JOINT_NAMES]
    env.reset()
    critic = env.observation_manager.compute_group("critic")
    true_lin_vel = robot.data.root_link_lin_vel_b
    if not torch.allclose(critic[:, -3:], true_lin_vel, atol=1e-5):
        _fail(
            "Critic tail does not equal base linear velocity: "
            f"{critic[0, -3:].tolist()} vs {true_lin_vel[0].tolist()}."
        )
    actor_terms = tuple(env.observation_manager.active_terms["actor"])
    if "base_lin_vel" in actor_terms:
        _fail("base_lin_vel is active in the actor group.")
    print(f"privileged: critic tail == root_link_lin_vel_b; actor has "
          f"{len(actor_terms)} terms and none is base_lin_vel")

    # --- per-joint pulse mapping --------------------------------------------
    # Check the *commanded target* rather than the settled position: the PD loop
    # needs many control steps to converge and the joints are under load, which
    # would make a position comparison a test of the controller, not of the
    # mapping. One apply_actions() is enough to prove index -> joint routing.
    term = env.action_manager.get_term("joint_pos")
    pulse = 0.6
    for index, joint_name in enumerate(C.POLICY_JOINT_NAMES):
        env.reset()
        action = torch.zeros((args.num_envs, C.ACTION_DIM), device=args.device)
        action[:, index] = pulse
        term = env.action_manager.get_term("joint_pos")
        term.process_actions(action)
        term.apply_actions()
        target = robot.data.joint_pos_target[0, joint_idx]
        # apply_actions() subtracts the per-world encoder bias introduced by the
        # domain-randomisation startup event, so compare against the bias-aware
        # expectation rather than the raw HOME + scale * action.
        bias = robot.data.encoder_bias[0, joint_idx]
        expect = HOME_JOINT_POS[joint_name] + C.ACTION_SCALE * pulse - float(bias[index])
        if abs(float(target[index]) - expect) > 1e-3:
            _fail(
                f"Pulse on action {index} ({joint_name}) commanded "
                f"{float(target[index]):.4f}, expected {expect:.4f}."
            )
        for other, other_name in enumerate(C.POLICY_JOINT_NAMES):
            if other == index:
                continue
            neutral = HOME_JOINT_POS[other_name] - float(bias[other])
            drift = abs(float(target[other]) - neutral)
            if drift > 1e-4:
                _fail(
                    f"Pulse on {joint_name} moved target of {other_name} "
                    f"by {drift:.6f} rad."
                )
    print(f"mapping: {C.ACTION_DIM} per-joint pulses each command only their own joint")

    # --- held joints stay at HOME -------------------------------------------
    n_control = int(round(args.seconds / control_dt))
    env.reset()
    held_idx = [JOINT_NAMES.index(n) for n in C.HELD_JOINT_NAMES]
    action = torch.randn((args.num_envs, C.ACTION_DIM), device=args.device) * 0.8
    held_drift = 0.0
    for _ in range(n_control):
        env.step(action)
        q = robot.data.joint_pos[:, held_idx]
        home = torch.tensor(
            [HOME_JOINT_POS[n] for n in C.HELD_JOINT_NAMES], device=args.device
        )
        held_drift = max(held_drift, float((q - home).abs().max()))
    if held_drift > 0.05:
        _fail(f"Non-policy joints drifted {held_drift:.4f} rad from HOME.")
    print(f"held joints: {len(C.HELD_JOINT_NAMES)} servos/neck stayed within "
          f"{held_drift * 1000:.1f} mrad of HOME under random actions")

    # --- local reset isolation ----------------------------------------------
    # Resetting a subset must not disturb the other worlds.
    env.reset()
    ids = torch.tensor([0], device=args.device)
    before = robot.data.joint_pos[1:].clone()
    env.reset(env_ids=ids)
    after = robot.data.joint_pos[1:].clone()
    if not torch.allclose(before, after, atol=1e-5):
        _fail("Resetting env 0 perturbed the other environments.")
    print("reset: per-env reset isolated to the requested worlds")

    # --- finite values over a run -------------------------------------------
    env.reset()
    for step in range(n_control):
        action = torch.randn((args.num_envs, C.ACTION_DIM), device=args.device) * 0.5
        obs, reward, terminated, truncated, _ = env.step(action)
        if not torch.isfinite(obs["actor"]).all():
            _fail(f"Non-finite actor observation at step {step}.")
        if not torch.isfinite(reward).all():
            _fail(f"Non-finite reward at step {step}.")
    print(f"run: {n_control} control steps finite obs/reward")

    print(
        f"\nContract check passed: device={args.device}, envs={args.num_envs}, "
        f"actor={C.ACTOR_OBSERVATION_DIM}D, action={C.ACTION_DIM}D, "
        f"control={1.0 / control_dt:.0f}Hz."
    )
    print(
        "Verified: timing, action order/scale, observation order and dimensions, "
        "no privileged actor terms, per-joint mapping, held joints, reset isolation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
