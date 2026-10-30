# Copyright (c) 2026-2027 zh
"""验证官方数值修复的实例隔离及检查点加载后的课程刷新顺序。"""

from types import SimpleNamespace

import torch
from mjlab.rl import MjlabOnPolicyRunner

from ht_microduck.tasks.rl.runner import OfficialTaskOnPolicyRunner


class _RewardManager:
    def __init__(self):
        self._episode_sums = {"term": torch.tensor([float("nan"), 1.0])}

    def compute(self, dt):
        return torch.tensor([float("nan"), dt])


def test_numerical_guards_are_equivalent_and_do_not_patch_other_tasks(monkeypatch):
    manager = _RewardManager()
    legacy = _RewardManager()
    returns_calls = []
    storage = SimpleNamespace(
        advantages=torch.tensor([float("nan"), float("inf"), 1.0]),
        returns=torch.tensor([float("-inf"), 2.0]),
    )

    def initialize(runner, env, train_cfg, log_dir, device):
        runner.env = env
        runner.alg = SimpleNamespace(storage=storage, compute_returns=returns_calls.append)

    monkeypatch.setattr(MjlabOnPolicyRunner, "__init__", initialize)
    env = SimpleNamespace(unwrapped=SimpleNamespace(reward_manager=manager))
    class_compute = _RewardManager.compute
    runner = OfficialTaskOnPolicyRunner(env, {})
    assert _RewardManager.compute is class_compute
    assert torch.equal(manager.compute(0.02), torch.tensor([0.0, 0.02]))
    assert torch.equal(manager._episode_sums["term"], torch.tensor([0.0, 1.0]))
    assert torch.isnan(legacy.compute(0.02)[0])
    runner.alg.compute_returns("observations")
    assert returns_calls == ["observations"]
    assert torch.equal(storage.advantages, torch.tensor([0.0, 0.0, 1.0]))
    assert torch.equal(storage.returns, torch.tensor([0.0, 2.0]))


def test_checkpoint_load_refreshes_commands_after_restoring_the_counter(monkeypatch):
    order = []
    env = SimpleNamespace(unwrapped=SimpleNamespace(common_step_counter=0))

    def load(runner, path, load_cfg, strict, map_location):
        env.unwrapped.common_step_counter = 48_001
        order.append("load")
        return {"env_state": {"common_step_counter": 48_001}}

    def reset():
        assert env.unwrapped.common_step_counter == 48_001
        order.append("reset")

    monkeypatch.setattr(MjlabOnPolicyRunner, "load", load)
    env.reset = reset
    runner = object.__new__(OfficialTaskOnPolicyRunner)
    runner.env = env
    result = runner.load("checkpoint.pt")
    assert order == ["load", "reset"]
    assert result["env_state"]["common_step_counter"] == 48_001
