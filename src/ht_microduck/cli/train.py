"""``duck-train``: train a policy on the flat-ground velocity task.

Layout and console output follow the official ``microduck_rl`` (mjlab + RSL-RL)
conventions so a run here is readable next to a run there:

    runs/<experiment_name>/<YYYY-mm-dd_HH-MM-SS>_<run_name>/
        params/env.yaml
        params/agent.yaml
        metrics.jsonl
        model_<iteration>.pt
        model_last.pt

``--out-dir`` keeps a plain directory (no timestamp, no experiment level) for
callers that want a fixed path, which is what the earlier entries in
``docs/development.md`` use.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ht_microduck.algorithms.logger import TrainingLogger
from ht_microduck.algorithms.networks import NetworkCfg
from ht_microduck.algorithms.ppo import PpoCfg
from ht_microduck.algorithms.runner import OnPolicyRunner, TrainCfg, write_metrics
from ht_microduck.tasks.common import contract as C
from ht_microduck.tasks.flat_velocity import make_flat_velocity_env_cfg

# Fields printed as "Mean <name> loss", mirroring upstream's loss_dict.
LOSS_KEYS = ("policy", "value", "entropy")

# Upstream resolves checkpoints by highest iteration when loading the latest.
DEFAULT_LOG_ROOT = "runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-envs", type=int, default=1024)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--experiment-name", default="flat_velocity")
    parser.add_argument("--run-name", default="")
    parser.add_argument(
        "--log-root",
        default=DEFAULT_LOG_ROOT,
        help=(
            "root under which runs are grouped as "
            "<log_root>/<experiment_name>/<timestamp>_<run_name>"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="explicit run directory; overrides --log-root and skips the timestamp",
    )
    parser.add_argument("--save-interval", type=int, default=25)
    parser.add_argument(
        "--log-interval",
        type=int,
        default=1,
        help="print the console block every N iterations (official prints each one)",
    )
    parser.add_argument("--num-steps-per-env", type=int, default=24)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--resume", default=None, help="checkpoint to resume from")
    parser.add_argument(
        "--logger",
        default="tensorboard",
        choices=("tensorboard", "none"),
        help="tensorboard writes event files next to metrics.jsonl",
    )
    parser.add_argument(
        "--nconmax",
        type=int,
        default=None,
        help=(
            "contacts allocated per world (default: task value 128). "
            "Large environments exhaust 8 GB cards with CUDA graphs; "
            "measured peak was 13 contacts/world on this robot."
        ),
    )
    parser.add_argument(
        "--njmax",
        type=int,
        default=None,
        help=(
            "constraints allocated per world (default: task value 512). "
            "Measured peak was 55 constraints/world on this robot."
        ),
    )
    return parser


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Pick the run directory, official-style unless ``--out-dir`` was given."""
    if args.out_dir:
        return Path(args.out_dir)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"{stamp}_{args.run_name}" if args.run_name else stamp
    return Path(args.log_root) / args.experiment_name / name


def write_params(run_dir: Path, args: argparse.Namespace, cfg: TrainCfg) -> None:
    """Write the two YAML files the official logger keeps per run."""
    import yaml

    params = run_dir / "params"
    params.mkdir(parents=True, exist_ok=True)
    env_params = {
        "num_envs": cfg.num_envs,
        "seed": cfg.seed,
        "device": cfg.device,
        "nconmax": args.nconmax,
        "njmax": args.njmax,
        "physics_timestep": C.PHYSICS_TIMESTEP,
        "decimation": C.DECIMATION,
        "control_hz": C.CONTROL_HZ,
        "episode_length_s": C.EPISODE_LENGTH_S,
        "actor_obs_dim": C.ACTOR_OBSERVATION_DIM,
        "critic_obs_dim": C.CRITIC_OBSERVATION_DIM,
        "action_dim": C.ACTION_DIM,
        "action_terms": list(C.POLICY_JOINT_NAMES),
    }
    agent_params = {
        "num_iterations": cfg.num_iterations,
        "save_interval": cfg.save_interval,
        "log_interval": cfg.log_interval,
        "actor": asdict(cfg.actor),
        "critic": asdict(cfg.critic),
        "ppo": asdict(cfg.ppo),
    }
    for path, data in ((params / "env.yaml", env_params), (params / "agent.yaml", agent_params)):
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False)


def build_loss_dict(metrics: dict[str, float]) -> dict[str, float]:
    """Map runner metrics onto the names upstream prints."""
    mapping = {
        "policy": "train/policy_loss",
        "value": "train/value_loss",
        "entropy": "train/entropy",
    }
    return {
        name: float(metrics[source])
        for name, source in mapping.items()
        if source in metrics
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = resolve_run_dir(args)
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = TrainCfg(
        num_envs=args.num_envs,
        num_iterations=args.iterations,
        seed=args.seed,
        device=args.device,
        save_interval=args.save_interval,
        log_interval=args.log_interval,
        experiment_name=args.experiment_name,
        run_name=args.run_name,
        actor=NetworkCfg(),
        critic=NetworkCfg(),
        ppo=PpoCfg(
            num_steps_per_env=args.num_steps_per_env,
            learning_rate=args.learning_rate,
        ),
        out_dir=str(run_dir),
    )

    env = make_flat_velocity_env_cfg(num_envs=cfg.num_envs, seed=cfg.seed)
    # Optional per-run overrides; the task defaults stay authoritative so the
    # environment contract is unchanged unless the caller asks for it.
    if args.nconmax is not None:
        env.sim.nconmax = args.nconmax
    if args.njmax is not None:
        env.sim.njmax = args.njmax
    from mjlab.envs import ManagerBasedRlEnv

    env = ManagerBasedRlEnv(env, device=cfg.device)
    runner = OnPolicyRunner(env, cfg)
    if args.resume:
        runner.load(Path(args.resume))
        print(f"[INFO] Resumed from {args.resume} at iteration {runner.iteration}")
    # A resumed run reports "iteration i/(start+i)" like upstream, so the header
    # stays monotonic instead of restarting from 1.
    start_iteration = runner.iteration
    total_iterations = start_iteration + cfg.num_iterations

    write_params(run_dir, args, cfg)
    logger = TrainingLogger(
        log_dir=run_dir,
        metrics_path=run_dir / "metrics.jsonl",
        enable_tensorboard=args.logger == "tensorboard",
        log_interval=cfg.log_interval,
        run_name=args.run_name or None,
    )

    print(f"[INFO] Training with: device={cfg.device}, seed={cfg.seed}")
    print(f"[INFO] Logging experiment in directory: {run_dir}")
    print(
        f"[INFO] envs={cfg.num_envs} iterations={cfg.num_iterations} "
        f"actor_obs={C.ACTOR_OBSERVATION_DIM} action={C.ACTION_DIM} "
        f"control={C.CONTROL_HZ:.0f}Hz"
    )

    metrics_path = run_dir / "metrics.jsonl"
    try:
        for _ in range(cfg.num_iterations):
            metrics = runner.train_step()
            write_metrics(metrics_path, metrics)
            logger.record_episodes(runner.new_returns, runner.new_lengths)
            logger.log(
                iteration=runner.iteration,
                total_iterations=total_iterations,
                collect_time=metrics["train/collect_s"],
                learn_time=metrics["train/learn_s"],
                loss_dict=build_loss_dict(metrics),
                learning_rate=metrics["train/learning_rate"],
                action_std=runner.action_std,
                metrics=metrics,
                num_steps_per_env=cfg.ppo.num_steps_per_env,
                num_envs=cfg.num_envs,
                start_iteration=start_iteration,
            )
            if not math.isfinite(metrics["train/policy_loss"]):
                raise RuntimeError("PPO produced a non-finite policy loss; aborting.")
            if cfg.save_interval and (runner.iteration % cfg.save_interval == 0):
                runner.save(run_dir / f"model_{runner.iteration}.pt")
    finally:
        logger.close()

    runner.save(run_dir / "model_last.pt")
    print(f"[INFO] Saved final checkpoint and metrics to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
