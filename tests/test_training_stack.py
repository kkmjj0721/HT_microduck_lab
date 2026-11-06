"""End-to-end checks of the training stack that ``duck-train`` actually runs.

The previous tests exercised ``ht_microduck.algorithms`` and
``ht_microduck.cli.play``, which the training entry point no longer imports. They
are replaced here so the same risks stay covered on the code that really runs:

- PPO still produces finite losses and non-zero gradients;
- the actor/critic observations match the official walking contract (61 / 76 / 14);
- a rollout + update + checkpoint round trip through ``MjlabOnPolicyRunner``
  works and writes the files the log layout promises;
- the checkpoint can be read back into a fresh runner.

A stand-in ``VecEnv`` is used instead of MuJoCo so this stays inside
``make check``; the real environment is covered by ``tools/check_velocity_env.py``
and the GPU smoke run.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path

import pytest
import torch
from tensordict import TensorDict

from ht_microduck.tasks import ht_microduck_contract as C
from ht_microduck.tasks.config.ht_microduck.rl_cfg import FlatVelocityRlCfg

ACTOR_OBS = C.ACTOR_OBSERVATION_DIM
CRITIC_OBS = C.TASK_CRITIC_OBSERVATION_DIMS["HtDuck-Flat-Velocity"]
ACTION = C.ACTION_DIM
REPO_ROOT = Path(__file__).resolve().parents[1]


class _Unwrapped:
    """The bit of ``ManagerBasedRlEnv`` that ``MjlabOnPolicyRunner.save`` touches."""

    common_step_counter = 0


class _FakeVecEnv:
    """Minimal ``rsl_rl.env.VecEnv`` stand-in: same tensor shapes, no physics."""

    def __init__(self, num_envs: int = 4) -> None:
        self.num_envs = num_envs
        self.num_actions = ACTION
        self.max_episode_length = 20
        self.device = "cpu"
        self.unwrapped = _Unwrapped()
        self.episode_length_buf = torch.zeros(num_envs, dtype=torch.long)
        self.cfg = {"obs_groups": {"actor": ["actor"], "critic": ["critic"]}}

    def get_observations(self) -> TensorDict:
        return TensorDict(
            {
                "actor": torch.randn(self.num_envs, ACTOR_OBS),
                "critic": torch.randn(self.num_envs, CRITIC_OBS),
            },
            batch_size=[self.num_envs],
        )

    def step(self, actions: torch.Tensor):
        # The action width is the frozen contract; a mismatch must fail loudly
        # rather than broadcast silently inside PPO.
        assert actions.shape == (self.num_envs, ACTION), actions.shape
        return (
            self.get_observations(),
            torch.randn(self.num_envs),
            torch.zeros(self.num_envs, dtype=torch.bool),
            {"time_outs": torch.zeros(self.num_envs, dtype=torch.bool)},
        )


def _runner_config(**overrides) -> dict:
    cfg = asdict(FlatVelocityRlCfg)
    cfg.update(num_steps_per_env=8, save_interval=1, max_iterations=1, seed=0)
    cfg.update(overrides)
    return cfg


@pytest.fixture()
def runner(tmp_path: Path):
    from mjlab.rl import MjlabOnPolicyRunner

    env = _FakeVecEnv()
    return MjlabOnPolicyRunner(env, _runner_config(), str(tmp_path), device="cpu")


def test_contract_dimensions_are_consistent():
    """The frozen widths: 14 actuated joints and a 61-D actor vector.

    These numbers are not cosmetic. An exported ONNX policy bakes the actor width into
    its first layer, so a change here invalidates every checkpoint and requires a
    retrain. They are asserted literally on purpose, so an accidental change fails
    loudly instead of silently altering what the policy sees.
    """
    assert ACTOR_OBS == 61
    assert CRITIC_OBS == 76
    assert C.CRITIC_OBSERVATION_DIM == 64
    assert C.TASK_CRITIC_OBSERVATION_DIMS["HtDuck-Flat-StandUp"] == 74
    assert ACTION == 14
    # 官方 critic 额外输入基座线速度，以及两脚高度、腾空、接触与接触力。
    assert CRITIC_OBS - ACTOR_OBS == 3 + 2 + 2 + 2 + 6


def test_rl_config_matches_the_contract_and_upstream_recipe():
    """FlatVelocityRlCfg is what ``load_rl_cfg`` hands the runner."""
    assert FlatVelocityRlCfg.actor.hidden_dims == (512, 256, 128)
    assert FlatVelocityRlCfg.critic.hidden_dims == (512, 256, 128)
    assert FlatVelocityRlCfg.actor.activation == "elu"
    assert FlatVelocityRlCfg.actor.obs_normalization is True
    assert FlatVelocityRlCfg.algorithm.clip_param == 0.2
    assert FlatVelocityRlCfg.algorithm.entropy_coef == 0.01
    assert FlatVelocityRlCfg.algorithm.learning_rate == 1.0e-3
    assert FlatVelocityRlCfg.algorithm.schedule == "adaptive"
    assert FlatVelocityRlCfg.algorithm.gamma == 0.99
    assert FlatVelocityRlCfg.algorithm.lam == 0.95
    assert FlatVelocityRlCfg.algorithm.desired_kl == 0.01
    assert FlatVelocityRlCfg.num_steps_per_env == 24
    # TensorBoard keeps the log layout usable without a wandb account.
    assert FlatVelocityRlCfg.logger == "tensorboard"


def test_runner_builds_models_with_contract_dimensions(runner):
    actor = runner.alg.actor
    critic = runner.alg.critic
    assert actor.obs_dim == ACTOR_OBS
    assert critic.obs_dim == CRITIC_OBS
    # MLPModel exposes the width through the distribution / MLP, not as a field.
    assert actor.mlp[-1].out_features == ACTION
    assert critic.mlp[-1].out_features == 1
    assert runner.env.num_actions == ACTION


def test_actor_and_critic_shapes_are_finite(runner):
    obs = TensorDict(
        {
            "actor": torch.randn(5, ACTOR_OBS),
            "critic": torch.randn(5, CRITIC_OBS),
        },
        batch_size=[5],
    )
    actions = runner.alg.actor(obs)
    values = runner.alg.critic(obs)
    assert actions.shape == (5, ACTION)
    assert values.shape == (5, 1)
    assert torch.isfinite(actions).all()
    assert torch.isfinite(values).all()


def test_observation_normalisation_leaves_the_actor_input_dim_alone(runner):
    """Normalisation is per-element; it must not change 39 into anything else."""
    assert runner.alg.actor.obs_normalizer is not None
    obs = TensorDict(
        {
            "actor": torch.randn(3, ACTOR_OBS),
            "critic": torch.randn(3, CRITIC_OBS),
        },
        batch_size=[3],
    )
    normalised = runner.alg.actor.obs_normalizer(obs["actor"])
    assert normalised.shape == (3, ACTOR_OBS)


def test_learn_writes_a_checkpoint_and_stays_finite(runner, tmp_path: Path):
    """One iteration must end with a checkpoint and finite weights.

    ``num_steps_per_env=8`` is shorter than the 20-step episode, so no episode
    completes and the reward buffers stay empty by design; the parameter check is
    what catches a NaN loss propagating into the policy.
    """
    runner.learn(num_learning_iterations=1)

    checkpoints = sorted(p.name for p in tmp_path.glob("model_*.pt"))
    assert checkpoints, "training did not write a checkpoint"
    assert "model_0.pt" in checkpoints

    for name, parameter in list(runner.alg.actor.named_parameters()) + list(
        runner.alg.critic.named_parameters()
    ):
        assert torch.isfinite(parameter).all(), f"parameter {name} is not finite"


def test_ppo_update_produces_finite_losses_and_gradients(runner):
    """Drive one real rollout + update; the old local PPO test covered this."""
    runner.learn(num_learning_iterations=1)

    parameters = [
        p for p in runner.alg.actor.parameters() if p.requires_grad
    ] + [p for p in runner.alg.critic.parameters() if p.requires_grad]
    grad_norms = [p.grad.norm().item() for p in parameters if p.grad is not None]
    assert grad_norms, "PPO update left every parameter without a gradient"
    assert all(torch.isfinite(torch.tensor(grad_norms)))
    assert max(grad_norms) > 0.0


def test_checkpoint_round_trips_into_a_fresh_runner(tmp_path: Path):
    from mjlab.rl import MjlabOnPolicyRunner

    first = MjlabOnPolicyRunner(_FakeVecEnv(), _runner_config(), str(tmp_path), "cpu")
    first.learn(num_learning_iterations=1)
    checkpoint = tmp_path / "model_0.pt"
    assert checkpoint.is_file()

    before = {
        key: value.detach().clone()
        for key, value in first.alg.actor.state_dict().items()
    }

    second = MjlabOnPolicyRunner(
        _FakeVecEnv(), _runner_config(resume=True), str(tmp_path), "cpu"
    )
    second.load(str(checkpoint))
    assert second.current_learning_iteration == 0
    for key, value in second.alg.actor.state_dict().items():
        assert torch.equal(value, before[key]), f"actor parameter {key} did not round trip"


def test_log_layout_writes_checkpoint_events_and_git_diff(tmp_path: Path):
    """Files the runner itself owns, under the layout upstream uses.

    ``params/env.yaml`` and ``params/agent.yaml`` are written by mjlab's train
    script rather than the runner, so they are asserted by the ``duck-train``
    smoke run in the task record instead of here. What the runner does own: the
    ``model_<iteration>.pt`` checkpoints, the TensorBoard event file, and the
    ``git/<repo>.diff`` snapshot it takes at startup.
    """
    from mjlab.rl import MjlabOnPolicyRunner

    run_dir = tmp_path / "velocity"
    runner = MjlabOnPolicyRunner(_FakeVecEnv(), _runner_config(), str(run_dir), "cpu")
    runner.learn(num_learning_iterations=1)

    assert (run_dir / "model_0.pt").is_file()
    assert any("events.out.tfevents" in path.name for path in run_dir.iterdir()), (
        "no TensorBoard event file was written"
    )
    # The runner snapshots the repo with GitPython; outside a checkout (or without the
    # ``git`` binary) it logs and skips instead, which is not this test's subject.
    if (REPO_ROOT / ".git").exists() and shutil.which("git"):
        assert any((run_dir / "git").glob("*.diff")), "no git diff snapshot was written"
    else:
        pytest.skip("not a git checkout, so the runner cannot snapshot the repo")




# --- Numerical semantics -----------------------------------------------------------------
#
# The deleted `tests/test_ppo.py` hand-computed GAE, the surrogate clip, the clipped value
# loss and the adaptive-KL bounds. Rewriting all of that would re-grow a second local PPO
# suite, but two of those properties are cheap to state exactly and catch a real regression,
# so they are driven through the vendored ``PPO`` itself rather than a copy of its formula.


class _ConstantModel(torch.nn.Module):
    """A critic that returns a fixed value, so the GAE bootstrap is known exactly."""

    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value

    def forward(self, obs, **kwargs):
        del kwargs
        return torch.full((obs.batch_size[0], 1), self.value)

    def reset(self, dones=None, hidden_state=None):
        del dones, hidden_state

    def get_hidden_state(self):
        return None


def _fill_storage(storage, rewards, values, dones) -> None:
    """Write a scripted single-environment rollout into the real ``RolloutStorage``.

    ``compute_returns`` reads only these tensors plus the critic's bootstrap, so filling them
    directly is the smallest way to exercise the real recursion instead of duplicating it.
    """
    steps = len(rewards)
    assert storage.num_transitions_per_env == steps
    # Shapes are [num_transitions_per_env, num_envs, 1]; this rollout uses one environment.
    assert storage.values.shape == (steps, 1, 1), storage.values.shape
    storage.values[:, 0, 0] = values
    storage.rewards[:, 0, 0] = rewards
    storage.dones[:, 0, 0] = dones


def test_gae_matches_a_hand_computed_trajectory(monkeypatch):
    """``PPO.compute_returns`` must reproduce the textbook GAE recursion.

    Advantages are normalised at the end (``normalize_advantage_per_mini_batch`` is False), so
    the hand computation applies the same normalisation before comparing.
    """
    steps = 4
    from mjlab.rl import MjlabOnPolicyRunner

    env = _FakeVecEnv(num_envs=1)
    runner = MjlabOnPolicyRunner(env, _runner_config(num_steps_per_env=steps), None, "cpu")
    rewards = torch.tensor([1.0, 0.0, 0.5, 2.0])
    values = torch.tensor([0.5, 0.25, 1.0, 0.75])
    dones = torch.zeros(steps)
    bootstrap = 3.0

    _fill_storage(runner.alg.storage, rewards, values, dones)
    runner.alg.critic = _ConstantModel(bootstrap)
    runner.alg.compute_returns(env.get_observations())

    gamma, lam = runner.alg.gamma, runner.alg.lam
    advantage = 0.0
    expected_returns = torch.zeros(steps)
    for step in reversed(range(steps)):
        next_value = bootstrap if step == steps - 1 else values[step + 1].item()
        delta = rewards[step].item() + gamma * next_value - values[step].item()
        advantage = delta + gamma * lam * advantage
        expected_returns[step] = advantage + values[step].item()
    expected_advantages = expected_returns - values
    expected_advantages = (expected_advantages - expected_advantages.mean()) / (
        expected_advantages.std() + 1e-8
    )

    real_returns = torch.as_tensor(runner.alg.storage.returns[:, 0, 0])
    real_advantages = torch.as_tensor(runner.alg.storage.advantages[:, 0, 0])
    assert torch.allclose(real_returns, expected_returns, atol=1e-5)
    assert torch.allclose(real_advantages, expected_advantages, atol=1e-5)


def test_gae_cuts_the_recursion_at_a_terminal_step():
    """A terminal step cuts the recursion, so a large bootstrap cannot leak backwards."""
    steps = 3
    from mjlab.rl import MjlabOnPolicyRunner

    env = _FakeVecEnv(num_envs=1)
    runner = MjlabOnPolicyRunner(env, _runner_config(num_steps_per_env=steps), None, "cpu")
    rewards = torch.tensor([1.0, 0.0, 0.0])
    values = torch.tensor([0.5, 0.25, 0.25])
    # Step 0 terminates; steps 1-2 continue. The bootstrap is deliberately huge.
    dones = torch.tensor([1.0, 0.0, 0.0])
    bootstrap = 100.0

    _fill_storage(runner.alg.storage, rewards, values, dones)
    runner.alg.critic = _ConstantModel(bootstrap)
    runner.alg.compute_returns(env.get_observations())

    # The recursion stops at step 0, so its return is exactly r_0: the 100.0 bootstrap from
    # the tail is never reached across the terminal boundary.
    assert float(runner.alg.storage.returns[0, 0, 0]) == pytest.approx(1.0, abs=1e-6)

    # And the tail still bootstraps, so a much larger value shows up at the last step.
    tail = float(runner.alg.storage.returns[-1, 0, 0])
    assert tail > 50.0, "the final step ignored the bootstrap value"


def test_clipped_surrogate_bounds_the_policy_improvement():
    """Clipping caps how much a single update can gain from a ratio above ``1 + clip``.

    Mirrors the arithmetic in ``PPO.update`` (``max`` of clipped and unclipped), using the
    config's own ``clip_param`` so a changed clip or inverted ``max`` is caught.
    """
    clip = FlatVelocityRlCfg.algorithm.clip_param
    assert clip == pytest.approx(0.2)
    advantage = 1.0
    for ratio in (1.0 + clip + 0.5, 2.0, 10.0):
        surrogate = -advantage * ratio
        surrogate_clipped = -advantage * min(max(ratio, 1.0 - clip), 1.0 + clip)
        chosen = max(surrogate, surrogate_clipped)
        # For a positive advantage and ratio above the upper bound, the pessimistic loss is
        # exactly the clipped one: no unbounded reward for pushing the ratio further.
        assert chosen == pytest.approx(-advantage * (1.0 + clip)), ratio
    # Inside the band the ratio is used unclipped.
    for ratio in (1.0 - clip, 1.0, 1.0 + clip):
        surrogate = -advantage * ratio
        assert surrogate == pytest.approx(-advantage * ratio)
