# Copyright (c) 2026-2027 zh
"""通过官方Tyro入口解析动作约束选项，并在构造GPU环境前核对回放对照任务。"""

import sys

import pytest
from mjlab.scripts import play, train
from mjlab.tasks.registry import load_env_cfg


@pytest.mark.parametrize("task", ["SitStand", "VelStand"])
@pytest.mark.parametrize("legacy", [False, True])
def test_train_cli_can_select_the_original_action_semantics(monkeypatch, task, legacy):
    task_id = f"HtDuck-Flat-{task}"
    captured = {}

    def capture(task_id, args):
        captured["task"] = task_id
        captured["cfg"] = args.env

    arguments = ["duck-train", task_id]
    if legacy:
        arguments += ["--env.actions.joint-pos.bound-targets", "False"]
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setattr(train, "launch_training", capture)
    train.main()
    assert captured["task"] == task_id
    assert captured["cfg"].actions["joint_pos"].bound_targets is not legacy
    assert load_env_cfg(task_id).actions["joint_pos"].bound_targets


@pytest.mark.parametrize("task", ["SitStand", "VelStand"])
@pytest.mark.parametrize("legacy", [False, True])
def test_play_cli_uses_the_registered_action_contract(monkeypatch, task, legacy):
    task_id = f"HtDuck-Flat-{task}" + ("-Unbounded" if legacy else "")
    captured = {}

    class EnvironmentReached(Exception):
        """环境构造边界的显式测试终点。"""

    def capture(cfg, **kwargs):
        captured["cfg"] = cfg
        raise EnvironmentReached

    monkeypatch.setattr(sys, "argv", ["duck-play", task_id, "--agent", "zero", "--device", "cpu", "--num-envs", "2"])
    monkeypatch.setattr(play, "configure_torch_backends", lambda: None)
    monkeypatch.setattr(play, "ManagerBasedRlEnv", capture)
    with pytest.raises(EnvironmentReached):
        play.main()
    assert captured["cfg"].scene.num_envs == 2
    assert captured["cfg"].actions["joint_pos"].bound_targets is not legacy
