"""``duck-play``: replay a trained policy in the flat-ground velocity task.

Mirrors the official ``mjlab/scripts/play.py`` semantics: load a checkpoint (or
use a zero/random policy), run the environment at real time in a viewer, and
optionally record a video.

Examples:

    uv run --no-sync duck-play --checkpoint-file runs/flat_velocity/model_last.pt
    uv run --no-sync duck-play --agent zero --num-envs 1
    uv run --no-sync duck-play --checkpoint-file ... --viewer viser
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from ht_microduck.algorithms.networks import ActorCritic, NetworkCfg
from ht_microduck.tasks.common import contract as C
from ht_microduck.tasks.flat_velocity import make_flat_velocity_env_cfg

AGENTS = ("trained", "zero", "random")
VIEWERS = ("auto", "native", "viser")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint-file",
        default=None,
        help="checkpoint to load; required unless --agent is zero/random",
    )
    parser.add_argument(
        "--log-root",
        default="runs",
        help="searched for the newest run when --checkpoint-file is omitted",
    )
    parser.add_argument(
        "--experiment-name",
        default="flat_velocity",
        help="experiment subdirectory used with --log-root",
    )
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--agent", default="trained", choices=AGENTS)
    parser.add_argument("--viewer", default="auto", choices=VIEWERS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--no-terminations",
        action="store_true",
        help="ignore termination terms so the policy cannot end the episode early",
    )
    parser.add_argument(
        "--video",
        action="store_true",
        help="record an mp4 next to the checkpoint instead of opening a viewer",
    )
    parser.add_argument("--video-length", type=int, default=200)
    parser.add_argument(
        "--video-width",
        type=int,
        default=None,
        help="offscreen render width for --video (task default 320)",
    )
    parser.add_argument(
        "--video-height",
        type=int,
        default=None,
        help="offscreen render height for --video (task default 240)",
    )
    parser.add_argument(
        "--videos-dir",
        default=None,
        help=(
            "where to write the mp4; defaults to <checkpoint dir>/videos/play, "
            "matching the official play.py layout"
        ),
    )
    parser.add_argument("--nconmax", type=int, default=None)
    parser.add_argument("--njmax", type=int, default=None)
    return parser


def find_latest_checkpoint(log_root: Path, experiment_name: str) -> Path:
    """Resolve the newest ``model_*.pt`` the way upstream's ``get_checkpoint_path`` does."""
    experiment = Path(log_root) / experiment_name
    if not experiment.is_dir():
        raise FileNotFoundError(f"No experiment directory at {experiment}")
    runs = sorted(p for p in experiment.iterdir() if p.is_dir())
    if not runs:
        raise FileNotFoundError(f"No run directories under {experiment}")

    def key(path: Path) -> str:
        return path.name

    checkpoints = [
        p for p in runs[-1].iterdir() if p.name.startswith("model_") and p.suffix == ".pt"
    ]
    if not checkpoints:
        raise FileNotFoundError(f"No model_*.pt in {runs[-1]}")
    checkpoints.sort(key=lambda p: (p.name != "model_last.pt", key(p)))
    return checkpoints[-1]


class Policy:
    """Wraps the actor into the ``policy(obs) -> action`` the viewers expect."""

    def __init__(self, kind: str, model: ActorCritic | None, action_dim: int) -> None:
        self.kind = kind
        self.model = model
        self.action_dim = action_dim
        self._generator: torch.Generator | None = None

    def to(self, device: torch.device) -> "Policy":
        if self.model is not None:
            self.model.to(device)
        self._generator = torch.Generator(device=device)
        self._generator.manual_seed(0)
        self._device = device
        return self

    @torch.no_grad()
    def __call__(self, obs: torch.Tensor | dict) -> torch.Tensor:
        actor_obs = obs["actor"] if isinstance(obs, dict) else obs
        if actor_obs.dim() == 1:
            actor_obs = actor_obs.unsqueeze(0)
        if self.kind == "zero":
            return torch.zeros(actor_obs.shape[0], self.action_dim, device=actor_obs.device)
        if self.kind == "random":
            return torch.randn(
                actor_obs.shape[0],
                self.action_dim,
                generator=self._generator,
                device=actor_obs.device,
            )
        assert self.model is not None
        # Deterministic: the mean action, as upstream's play uses.
        return self.model.actor(actor_obs)

    def reset(self) -> None:
        """Hook the viewer calls on reset; nothing is stateful here."""


def load_model(path: Path, device: str) -> ActorCritic:
    payload = torch.load(path, map_location=device, weights_only=False)
    cfg = payload.get("cfg", {})
    model = ActorCritic(
        NetworkCfg(**_filter_network_cfg(cfg.get("actor", {}))),
        NetworkCfg(**_filter_network_cfg(cfg.get("critic", {}))),
        C.ACTOR_OBSERVATION_DIM,
        C.CRITIC_OBSERVATION_DIM,
        C.ACTION_DIM,
    ).to(device)
    model.load_state_dict(payload["model"])
    model.eval()
    contract = payload.get("contract", {})
    if contract.get("actor_obs_dim") not in (None, C.ACTOR_OBSERVATION_DIM):
        raise ValueError(
            "Checkpoint observation size does not match the current contract; "
            "replay and evaluation must use the same contract as training."
        )
    return model


def _filter_network_cfg(raw: dict) -> dict:
    """Keep only the keys ``NetworkCfg`` accepts (checkpoints may carry extras)."""
    fields = set(NetworkCfg.__dataclass_fields__)
    known = {k: v for k, v in raw.items() if k in fields}
    if "hidden_dims" in known:
        known["hidden_dims"] = tuple(known["hidden_dims"])
    return known


def build_env(args: argparse.Namespace, render_mode: str | None = None):
    from mjlab.envs import ManagerBasedRlEnv

    cfg = make_flat_velocity_env_cfg(num_envs=args.num_envs, seed=args.seed)
    if args.nconmax is not None:
        cfg.sim.nconmax = args.nconmax
    if args.njmax is not None:
        cfg.sim.njmax = args.njmax
    # Offscreen render size; the task default is 320x240, as in upstream.
    if getattr(args, "video_width", None) is not None:
        cfg.viewer.width = args.video_width
    if getattr(args, "video_height", None) is not None:
        cfg.viewer.height = args.video_height
    env = ManagerBasedRlEnv(cfg, device=args.device, render_mode=render_mode)
    if args.no_terminations:
        env.termination_manager.active_terms = []
    return env


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    checkpoint: Path | None = None
    if args.checkpoint_file:
        checkpoint = Path(args.checkpoint_file)
    elif args.agent == "trained":
        checkpoint = find_latest_checkpoint(Path(args.log_root), args.experiment_name)
    if checkpoint is not None and not checkpoint.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")

    model = None
    if args.agent == "trained":
        assert checkpoint is not None
        model = load_model(checkpoint, args.device)
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        print(
            f"[INFO] Loaded {checkpoint} at iteration {payload.get('iteration', '?')}"
        )
    policy = Policy(args.agent, model, C.ACTION_DIM).to(torch.device(args.device))

    if args.video:
        return _record_video(args, policy)

    env = build_env(args)
    from mjlab.viewer.native import NativeMujocoViewer

    viewer_kind = args.viewer
    if viewer_kind == "viser":
        from mjlab.viewer.viser import ViserPlayViewer

        print("[INFO] Starting viser viewer; open the printed URL in a browser")
        viewer = ViserPlayViewer(env, policy, frame_rate=60.0)
    else:
        if viewer_kind == "auto" and not _has_display():
            print(
                "[WARN] No DISPLAY found; falling back to recording a video instead "
                "of opening a window. Pass --video explicitly to choose this."
            )
            env.close()
            return _record_video(args, policy)
        viewer = NativeMujocoViewer(env, policy, frame_rate=60.0)
    viewer.run()
    return 0


def _has_display() -> bool:
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _record_video(args: argparse.Namespace, policy: Policy) -> int:
    """Step the env headlessly and write an mp4 through mjlab's recorder.

    Frames land in ``<checkpoint dir>/videos/play`` when a checkpoint was given,
    matching the official ``play.py`` layout, and under the given video root
    otherwise.
    """
    from mjlab.utils.wrappers import VideoRecorder

    # The recorder only captures frames when the env renders arrays.
    env = build_env(args, render_mode="rgb_array")
    if args.videos_dir:
        out_dir = Path(args.videos_dir)
    elif args.checkpoint_file:
        out_dir = Path(args.checkpoint_file).parent / "videos" / "play"
    else:
        out_dir = Path(args.log_root) / args.experiment_name / "videos" / "play"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = VideoRecorder(
        env,
        video_folder=out_dir,
        step_trigger=lambda step: step == 0,
        video_length=args.video_length,
        name_prefix="duck-play",
    )
    obs, _ = env.reset()
    for _ in range(args.video_length):
        obs, _, _, _, _ = env.step(policy(obs))
    env.close()
    print(f"[INFO] Video written under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
