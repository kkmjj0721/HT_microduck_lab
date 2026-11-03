# Copyright (c) 2026-2027 zh
"""仅用CPU验证正式行为入口的初态库选择与输出边界，仿真case由探针替代。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import test_forward_v4_behavior as behavior
import torch
from mjlab.utils import torch as torch_utils


@pytest.fixture
def case_probe(monkeypatch):
    """隔离仿真和网络，只记录入口传入每个case的资源与协议。"""
    calls = []
    monkeypatch.setattr(torch_utils, "configure_torch_backends", lambda: None)

    def run_case(args, stage, difficulty, name, expected_bank):
        selected = None if args.state_bank is None else Path(args.state_bank)
        calls.append({
            "state_bank": selected, "stage": stage, "difficulty": difficulty,
            "case": name, "expected_hash": expected_bank,
            "content": None if selected is None else selected.read_bytes(),
        })
        return {"passed": True, "success_rate": 1.0}, expected_bank or "packaged-bank-sha256"

    monkeypatch.setattr(behavior, "_run_case", run_case)
    return calls


def _checkpoint(path, *, snapshot=True, v4=True):
    """快照字节只用于选择测试，真实npz边界在课程测试中独立验证。"""
    content = b"fixture-state-bank-snapshot"
    state = {
        "schema_version": 1, "stage": "hold", "difficulty": 0.0,
        "bank_sha256": hashlib.sha256(content).hexdigest(),
    }
    if snapshot:
        state["bank_snapshot"] = content
    infos = {"forward_curriculum": state} if v4 else {"env_state": {"common_step_counter": 0}}
    torch.save({"infos": infos}, path)
    return content, state


def _main(monkeypatch, checkpoint, output, *extra):
    monkeypatch.setattr(sys, "argv", [
        "test_forward_v4_behavior.py", "--checkpoint-file", str(checkpoint),
        "--output", str(output), "--device", "cpu", *extra,
    ])
    behavior.main()


def test_default_cli_materializes_the_checkpoint_bank_only_inside_the_new_output_directory(tmp_path, monkeypatch, case_probe):
    checkpoint = tmp_path / "policy.pt"
    content, state = _checkpoint(checkpoint)
    checkpoint_content = checkpoint.read_bytes()
    output = tmp_path / "evaluation"
    _main(monkeypatch, checkpoint, output)
    bank = output / "initial_state_bank.npz"
    assert bank.read_bytes() == content
    assert len(case_probe) == 2
    assert all(call["state_bank"] == bank and call["content"] == content for call in case_probe)
    assert all(call["expected_hash"] == state["bank_sha256"] for call in case_probe)
    assert checkpoint.read_bytes() == checkpoint_content
    assert not list(tmp_path.glob("*.npz"))
    report = json.loads((output / "result.json").read_text())
    assert report["bank_sha256"] == state["bank_sha256"]


def test_explicit_cli_state_bank_takes_priority_over_checkpoint_materialization(tmp_path, monkeypatch, case_probe):
    checkpoint = tmp_path / "policy.pt"
    content, _ = _checkpoint(checkpoint)
    explicit = tmp_path / "explicit-bank.npz"
    explicit.write_bytes(content)
    output = tmp_path / "evaluation"
    _main(monkeypatch, checkpoint, output, "--state-bank", str(explicit))
    assert all(call["state_bank"] == explicit for call in case_probe)
    assert explicit.read_bytes() == content
    assert not (output / "initial_state_bank.npz").exists()


def test_cli_without_an_embedded_bank_leaves_packaged_bank_selection_to_the_environment(tmp_path, monkeypatch, case_probe):
    checkpoint = tmp_path / "policy-without-snapshot.pt"
    _checkpoint(checkpoint, snapshot=False)
    output = tmp_path / "evaluation"
    _main(monkeypatch, checkpoint, output)
    assert len(case_probe) == 2
    assert all(call["state_bank"] is None for call in case_probe)
    assert not (output / "initial_state_bank.npz").exists()


def test_v3_cli_requires_an_explicit_hold_diagnostic_protocol(tmp_path, monkeypatch, case_probe):
    checkpoint = tmp_path / "v3-policy.pt"
    _checkpoint(checkpoint, v4=False)
    output = tmp_path / "evaluation"
    with pytest.raises(ValueError, match="explicit --stage hold"):
        _main(monkeypatch, checkpoint, output)
    assert not case_probe
    assert not (output / "initial_state_bank.npz").exists()


def test_v3_explicit_hold_diagnostics_keep_the_requested_protocol(tmp_path, monkeypatch, case_probe):
    checkpoint = tmp_path / "v3-policy.pt"
    _checkpoint(checkpoint, v4=False)
    output = tmp_path / "evaluation"
    _main(monkeypatch, checkpoint, output, "--stage", "hold")
    assert len(case_probe) == 2
    assert all(call["stage"] == "hold" and call["difficulty"] == 0.0 for call in case_probe)
    assert all(call["state_bank"] is None and call["expected_hash"] is None for call in case_probe)
