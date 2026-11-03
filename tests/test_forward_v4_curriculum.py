# Copyright (c) 2026-2027 zh
"""验证v4配置隔离、初态数据边界、命令匹配和基于独立报告的课程恢复。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

from ht_microduck.robot.ht_microduck_constants import JOINT_NAMES
from ht_microduck.tasks import _assert_task_contract
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_sitstand_forward_env_cfg import (
    make_sitstand_forward_env_cfg,
)
from ht_microduck.tasks.config.flat_sitstand_forward_v4_env_cfg import (
    make_sitstand_forward_v4_env_cfg,
)
from ht_microduck.tasks.mdp import forward_events
from ht_microduck.tasks.mdp.forward_commands import ForwardCurriculumCommand
from ht_microduck.tasks.mdp.forward_events import (
    STATE_FIELDS,
    ForwardStateBank,
    reset_forward_curriculum,
)
from ht_microduck.tasks.mdp.forward_initialization import (
    ForwardInitializedJointPositionActionCfg,
)
from ht_microduck.tasks.mdp.official_posture_events import SitStandCommand
from ht_microduck.tasks.rl.forward_runner import (
    ForwardCurriculumOnPolicyRunner,
    validate_forward_promotion,
)
from ht_microduck.tasks.rl.runner import OfficialTaskOnPolicyRunner

TASK = "HtDuck-Flat-SitStand-Forward-V4"
V3_TASK = "HtDuck-Flat-SitStand-Forward"
CHECKPOINT_HASH = "source-checkpoint-sha256"
THRESHOLDS = {
    "tilt_deg": 15.0, "sit_height_m": 0.015, "stand_height_m": 0.02,
    "foot_x_m": 0.015, "hip_knee_rad": 0.35, "mean_leg_rad": 0.25,
}


@pytest.mark.parametrize("play", [False, True])
def test_v4_keeps_the_complete_policy_contract_and_independent_ppo_configuration(play):
    cfg = make_sitstand_forward_v4_env_cfg(num_envs=3, seed=17, play=play)
    _assert_task_contract(TASK, cfg)
    assert cfg.scene.num_envs == 3 and cfg.seed == 17
    assert tuple(cfg.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS
    assert tuple(cfg.observations["critic"].terms) == C.critic_observation_terms(TASK)
    assert C.ACTOR_OBSERVATION_DIM == 61 and C.TASK_CRITIC_OBSERVATION_DIMS[TASK] == 74
    assert tuple(cfg.actions["joint_pos"].actuator_names) == C.POLICY_JOINT_NAMES
    assert len(cfg.actions["joint_pos"].actuator_names) == 14
    assert isinstance(cfg.actions["joint_pos"], ForwardInitializedJointPositionActionCfg)
    assert cfg.actions["joint_pos"].scale == 1.0
    assert cfg.actions["joint_pos"].bound_targets
    assert cfg.sim.mujoco.timestep * cfg.decimation == 0.02
    assert cfg.commands["twist"].stage == "hold" and cfg.commands["twist"].difficulty == 0.0
    assert cfg.commands["head_pose"].ranges == ((0.0, 0.0),) * 4
    assert cfg.metrics["forward_hold_seconds"].reduce == "max"
    assert not cfg.curriculum
    assert load_runner_cls(TASK) is ForwardCurriculumOnPolicyRunner
    v3_agent, v4_agent = asdict(load_rl_cfg(V3_TASK)), asdict(load_rl_cfg(TASK))
    for key in ("actor", "critic", "algorithm", "num_steps_per_env"):
        assert v3_agent[key] == v4_agent[key]
    assert v3_agent["experiment_name"] != v4_agent["experiment_name"]


def test_v4_mutation_cannot_change_v3_or_any_other_registered_task():
    task_ids = list(C.TASK_CRITIC_OBSERVATION_DIMS)
    before = {name: (asdict(load_env_cfg(name)), asdict(load_rl_cfg(name))) for name in task_ids}
    cfg = make_sitstand_forward_v4_env_cfg(num_envs=3)
    cfg.commands["twist"].stage = "sit"
    cfg.commands["twist"].difficulty = 0.25
    cfg.commands["head_pose"].ranges = ((1.0, 1.0),) * 4
    cfg.rewards["posture_pose_legs"].weight = 99.0
    cfg.rewards["rise_bootstrap"].params["max_height"] = 99.0
    cfg.events["set_ground_state"].params["command_name"] = "other"
    cfg.actions["joint_pos"].scale = 0.2
    assert before == {name: (asdict(load_env_cfg(name)), asdict(load_rl_cfg(name))) for name in task_ids}
    v3 = asdict(make_sitstand_forward_env_cfg())
    for section in ("actions", "commands", "events", "rewards", "observations", "curriculum", "metrics"):
        assert v3[section] == before[V3_TASK][0][section]


@pytest.mark.parametrize("name", ["rise_bootstrap", "descent_speed", "rise_speed", "gentle_motion"])
def test_transition_rewards_follow_the_final_command_configuration_after_cli_overrides(name):
    cfg = make_sitstand_forward_v4_env_cfg(num_envs=3)
    original = make_sitstand_forward_env_cfg(num_envs=3).rewards[name]
    term = cfg.rewards[name]
    assert term.weight == original.weight
    assert term.params["reward_func"] is original.func
    assert {key: value for key, value in term.params.items() if key != "reward_func"} == original.params
    env = SimpleNamespace(num_envs=3, device="cpu", command_manager=SimpleNamespace(get_term=lambda _: SimpleNamespace(cfg=cfg.commands["twist"])))
    calls = []

    def original_reward(actual_env, **params):
        calls.append((actual_env, params))
        return torch.tensor([0.2, 0.4, 0.6])

    params = {**term.params, "reward_func": original_reward}
    torch.testing.assert_close(term.func(env, **params), torch.zeros(3))
    assert not calls
    for stage in ("sit", "rise", "mixed"):
        cfg.commands["twist"].stage = stage
        torch.testing.assert_close(term.func(env, **params), torch.tensor([0.2, 0.4, 0.6]))
        assert calls[-1] == (env, original.params)


def _revalidation_records():
    """每个样本都有与其类别、实际难度对应的完整复验证据。"""
    records = []
    for kind in range(4):
        record = {
            "kind": kind, "sample_ids": [2 * kind, 2 * kind + 1],
            "protocol": "fixed_target_hold" if kind < 2 else "restored_transition_then_hold",
            "seconds": 5.0, "valid_frames_per_sample": [250, 250],
        }
        if kind >= 2:
            record.update(remaining_seconds=[0.2, 0.6], full_transition_seconds=0.8)
        records.append(record)
    return records


@pytest.fixture
def bank_writer(tmp_path, monkeypatch):
    """在pytest项目内临时目录写独立的小型状态库，不依赖GPU采集产物。"""
    fingerprint = {"robot/fixture.xml": "fixture-sha256"}
    monkeypatch.setattr(forward_events, "forward_model_fingerprint", lambda: fingerprint.copy())
    counter = 0

    def write(*, metadata=None, arrays=None, remove=None):
        nonlocal counter
        labels = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.int64)
        values = {name: np.zeros((8, width), dtype=np.float32) for name, width in STATE_FIELDS.items()}
        values["root_pose"][:, 3] = 1.0
        values["joint_pos"][:, 0] = np.arange(8) * 0.01
        values.update(kind=labels, difficulty=np.array([0, 0, 0, 0, 0.25, 0.75, 0.25, 0.75]), validated=np.ones(8, dtype=bool))
        meta = {
            "schema_version": 1, "mjlab_version": "1.6.0", "joint_names": list(JOINT_NAMES),
            "model_fingerprint": fingerprint.copy(),
            "initialization": "physical_state_current_targets_native_reset",
            "revalidation": _revalidation_records(),
        }
        meta.update(metadata or {})
        values.update(arrays or {})
        values["metadata"] = np.array(json.dumps(meta))
        if remove is not None:
            del values[remove]
        path = tmp_path / f"states-{counter}.npz"
        counter += 1
        np.savez_compressed(path, **values)
        return path

    return write


def test_state_bank_preserves_validated_samples_difficulty_and_source_fingerprint(bank_writer):
    path = bank_writer()
    bank = ForwardStateBank(str(path), "cpu")
    assert bank.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert bank.indices(0, 0.0).tolist() == [0, 1]
    assert bank.indices(1, 0.0).tolist() == [2, 3]
    assert bank.indices(2, 0.25).tolist() == [4]
    assert bank.indices(2, 0.75).tolist() == [4, 5]
    assert bank.indices(3, 0.25).tolist() == [6]
    assert all(value.dtype == torch.float32 and value.device.type == "cpu" for value in bank.values.values())
    with pytest.raises(ValueError, match="No revalidated"):
        bank.indices(2, 0.1)


def test_state_bank_retains_the_original_bytes_and_supports_checkpoint_embedded_loading(bank_writer):
    path = bank_writer()
    content = path.read_bytes()
    from_file = ForwardStateBank(str(path), "cpu")
    path.write_bytes(b"replaced-after-checkpoint-save")
    embedded = ForwardStateBank(from_file.content, "cpu")
    assert from_file.path == path.resolve() and embedded.path is None
    assert from_file.content == embedded.content == content
    assert from_file.sha256 == embedded.sha256 == hashlib.sha256(content).hexdigest()
    assert from_file.metadata == embedded.metadata
    for field in STATE_FIELDS:
        torch.testing.assert_close(from_file.values[field], embedded.values[field])
    assert torch.equal(from_file.kind, embedded.kind)
    assert torch.equal(from_file.validated, embedded.validated)


@pytest.mark.parametrize("labels", [np.full(8, 2, dtype=np.int8), np.ones(8, dtype=np.int64), np.ones(8, dtype=np.float32)])
def test_validated_flags_require_boolean_dtype_and_cannot_bypass_sample_proof(bank_writer, labels):
    path = bank_writer(arrays={"validated": labels}, metadata={"revalidation": _revalidation_records()[:2]})
    with pytest.raises(ValueError, match="boolean dtype"):
        ForwardStateBank(str(path), "cpu")


@pytest.mark.parametrize("metadata", [
    {"schema_version": 2}, {"mjlab_version": "1.5.0"},
    {"joint_names": list(reversed(JOINT_NAMES))}, {"model_fingerprint": {}},
    {"initialization": "qpos_only"}, {"revalidation": []},
])
def test_state_bank_rejects_incompatible_or_unverified_metadata(bank_writer, metadata):
    with pytest.raises(ValueError):
        ForwardStateBank(str(bank_writer(metadata=metadata)), "cpu")


@pytest.mark.parametrize("field", list(STATE_FIELDS))
@pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
def test_state_bank_rejects_nonfinite_physical_state_fields(bank_writer, field, invalid):
    array = np.zeros((8, STATE_FIELDS[field]), dtype=np.float32)
    array[0, 0] = invalid
    with pytest.raises(ValueError, match="Invalid forward state field"):
        ForwardStateBank(str(bank_writer(arrays={field: array})), "cpu")


@pytest.mark.parametrize("field", list(STATE_FIELDS))
def test_state_bank_rejects_incomplete_joint_or_root_state_widths(bank_writer, field):
    with pytest.raises(ValueError, match="Invalid forward state field"):
        ForwardStateBank(str(bank_writer(arrays={field: np.zeros((8, STATE_FIELDS[field] - 1))})), "cpu")


@pytest.mark.parametrize("field,values", [
    ("kind", np.full(8, 4)), ("kind", np.zeros((8, 1))),
    ("difficulty", np.full(8, -0.01)), ("difficulty", np.full(8, 1.01)),
    ("difficulty", np.full(8, np.nan)), ("validated", np.ones((8, 1), dtype=bool)),
])
def test_state_bank_rejects_invalid_sample_labels(bank_writer, field, values):
    with pytest.raises(ValueError):
        ForwardStateBank(str(bank_writer(arrays={field: values})), "cpu")


def test_state_bank_requires_both_revalidated_endpoints_and_normalized_quaternions(bank_writer):
    validated = np.ones(8, dtype=bool)
    validated[2:4] = False
    with pytest.raises(ValueError, match="No revalidated"):
        ForwardStateBank(str(bank_writer(arrays={"validated": validated})), "cpu")
    with pytest.raises(ValueError, match="unit norm"):
        ForwardStateBank(str(bank_writer(arrays={"root_pose": np.zeros((8, 7))})), "cpu")


def test_state_bank_rejects_validated_labels_without_matching_per_sample_evidence(bank_writer):
    records = _revalidation_records()[:2]
    with pytest.raises(ValueError, match="per-sample revalidation"):
        ForwardStateBank(str(bank_writer(metadata={"revalidation": records})), "cpu")
    records = _revalidation_records()
    records[0]["sample_ids"] = [0]
    records[0]["valid_frames_per_sample"] = [250]
    with pytest.raises(ValueError, match="per-sample revalidation"):
        ForwardStateBank(str(bank_writer(metadata={"revalidation": records})), "cpu")


@pytest.mark.parametrize("record_index,field,value", [
    (0, "sample_ids", []), (0, "sample_ids", [0, 8]),
    (0, "kind", 1), (2, "kind", 0),
    (0, "seconds", 4.99), (0, "seconds", 5.02),
    (0, "valid_frames_per_sample", [250]),
    (0, "valid_frames_per_sample", [250, 249]),
    (0, "valid_frames_per_sample", [250, 251]),
    (0, "valid_frames_per_sample", [float("nan"), 250]),
    (0, "protocol", "restored_transition_then_hold"),
    (2, "protocol", "fixed_target_hold"),
    (2, "remaining_seconds", [0.1, 0.6]),
    (2, "remaining_seconds", [0.2]),
    (2, "full_transition_seconds", 0.0),
])
def test_state_bank_rejects_forged_or_incomplete_revalidation_records(bank_writer, record_index, field, value):
    records = _revalidation_records()
    records[record_index][field] = value
    with pytest.raises(ValueError):
        ForwardStateBank(str(bank_writer(metadata={"revalidation": records})), "cpu")


@pytest.mark.parametrize("kind", [2, 3])
def test_requested_transition_difficulty_must_be_present_in_revalidated_states(bank_writer, kind):
    validated = np.ones(8, dtype=bool)
    validated[2 * kind + 1] = False
    bank = ForwardStateBank(str(bank_writer(arrays={"validated": validated})), "cpu")
    assert bank.indices(kind, 0.25).tolist() == [2 * kind]
    for requested in (0.5, 0.75, 1.0):
        with pytest.raises(ValueError, match="not represented"):
            bank.indices(kind, requested)


@pytest.mark.parametrize("remove", ["metadata", "root_pose", "validated"])
def test_state_bank_rejects_missing_required_data(bank_writer, remove):
    with pytest.raises((KeyError, ValueError)):
        ForwardStateBank(str(bank_writer(remove=remove)), "cpu")


@pytest.mark.parametrize("stage", ["hold", "sit", "rise", "mixed"])
def test_reset_samples_only_the_requested_stage_and_preserves_neighbor_state(bank_writer, monkeypatch, stage):
    difficulty = 1.0 if stage == "mixed" else 0.0 if stage == "hold" else 0.25
    cfg = SimpleNamespace(stage=stage, difficulty=difficulty, state_bank=str(bank_writer()))
    env = SimpleNamespace(num_envs=128, device="cpu", command_manager=SimpleNamespace(get_term=lambda _: SimpleNamespace(cfg=cfg)))
    writes = []
    monkeypatch.setattr(forward_events, "set_forward_initial_state", lambda actual_env, ids, **values: writes.append((actual_env, ids.clone(), values)))
    torch.manual_seed(17)
    reset_forward_curriculum(env, torch.arange(env.num_envs))
    bank = env._forward_state_bank
    kinds = bank.kind[env._forward_sample_ids]
    allowed = {0, 1, 2} if stage == "sit" else {0, 1, 3} if stage == "rise" else {0, 1}
    assert set(kinds.tolist()) == allowed
    assert torch.equal(env._forward_initial_sit, (kinds == 1) | (kinds == 3))
    assert torch.equal(env._forward_goal_sit, (kinds == 1) | (kinds == 2))
    assert bank.difficulty[env._forward_sample_ids].max() <= cfg.difficulty
    assert writes[-1][0] is env
    assert set(writes[-1][2]) == set(STATE_FIELDS)
    torch.testing.assert_close(writes[-1][2]["joint_pos"][:, 0], env._forward_sample_ids.float() * 0.01)
    before = {name: getattr(env, name).clone() for name in ("_forward_sample_ids", "_forward_initial_sit", "_forward_goal_sit")}
    rows = torch.tensor([2, 5, 17])
    reset_forward_curriculum(env, rows)
    neighbors = torch.ones(env.num_envs, dtype=torch.bool)
    neighbors[rows] = False
    for name, previous in before.items():
        assert torch.equal(getattr(env, name)[neighbors], previous[neighbors])
    assert torch.equal(writes[-1][1], rows)
    assert all(value.shape[0] == len(rows) for value in writes[-1][2].values())


def test_transition_reset_rejects_an_unvalidated_or_missing_transition_pool(bank_writer, monkeypatch):
    validated = np.ones(8, dtype=bool)
    validated[4:6] = False
    cfg = SimpleNamespace(stage="sit", difficulty=0.25, state_bank=str(bank_writer(arrays={"validated": validated})))
    env = SimpleNamespace(num_envs=4, device="cpu", command_manager=SimpleNamespace(get_term=lambda _: SimpleNamespace(cfg=cfg)))
    writes = []
    monkeypatch.setattr(forward_events, "set_forward_initial_state", lambda *args, **kwargs: writes.append(True))
    with pytest.raises(ValueError, match="No revalidated"):
        reset_forward_curriculum(env, torch.arange(4))
    assert not writes


@pytest.mark.parametrize("stage", ["hold", "sit", "rise"])
def test_nonmixed_command_resampling_keeps_goal_matches_and_other_rows_unchanged(stage):
    command = object.__new__(ForwardCurriculumCommand)
    command.cfg = SimpleNamespace(stage=stage)
    command._env_ref = SimpleNamespace(_forward_goal_sit=torch.tensor([True, False, False, True]))
    command.vel_command_b = torch.full((4, 3), 9.0)
    command.time_left = torch.full((4,), 0.1)
    command._resample_command(torch.tensor([0, 2]))
    torch.testing.assert_close(command.vel_command_b, torch.tensor([[1.0, 0.0, 0.0], [9.0, 9.0, 9.0], [0.0, 0.0, 0.0], [9.0, 9.0, 9.0]]))
    assert (command.time_left[[0, 2]] > 100.0).all()
    torch.testing.assert_close(command.time_left[[1, 3]], torch.tensor([0.1, 0.1]))


def test_mixed_command_resampling_uses_the_original_independent_posture_sampler(monkeypatch):
    calls = []
    monkeypatch.setattr(SitStandCommand, "_resample_command", lambda command, rows: calls.append(rows.clone()))
    command = object.__new__(ForwardCurriculumCommand)
    command.cfg = SimpleNamespace(stage="mixed")
    rows = torch.tensor([1, 3])
    command._resample_command(rows)
    assert len(calls) == 1 and torch.equal(calls[0], rows)


@pytest.mark.parametrize("stage,difficulty", [("unknown", 0.0), ("hold", 0.25), ("sit", -0.01), ("rise", 1.01), ("mixed", 0.25)])
def test_command_rejects_invalid_stage_configuration_before_simulation(stage, difficulty, monkeypatch):
    calls = []
    monkeypatch.setattr(SitStandCommand, "__init__", lambda *args: calls.append(True))
    with pytest.raises(ValueError):
        ForwardCurriculumCommand(SimpleNamespace(stage=stage, difficulty=difficulty), SimpleNamespace())
    assert not calls


def _state(stage="hold", difficulty=0.0, bank="source-bank-sha256"):
    return {"schema_version": 1, "stage": stage, "difficulty": difficulty, "bank_sha256": bank}


def _reports(state, cases=None):
    """构造完整的来源阶段证明，后续测试每次只破坏一个外部条件。"""
    rates = {"stand_hold": 0.95, "sit_hold": 0.95}
    if state["stage"] in ("sit", "mixed"):
        rates["sit_transition"] = 0.95
    if state["stage"] in ("rise", "mixed"):
        rates["rise_transition"] = 0.95
    return [{
        **state, "seed": seed, "passed": True, "checkpoint_sha256": CHECKPOINT_HASH,
        "policy_actions_unmodified": True, "num_envs_per_case": 16,
        "continuous_hold_seconds": 5.0, "thresholds": THRESHOLDS.copy(),
        "case_success_rates": rates.copy() if cases is None else cases.copy(),
    } for seed in (0, 1, 2)]


def test_same_curriculum_resume_needs_no_promotion_report_but_cannot_swap_the_state_bank():
    source = _state()
    validate_forward_promotion(source, source.copy(), [], CHECKPOINT_HASH)
    with pytest.raises(ValueError):
        validate_forward_promotion(source, _state(bank="other-bank"), _reports(source), CHECKPOINT_HASH)


@pytest.mark.parametrize("source,destination", [
    (_state(), _state("sit", 0.25)),
    (_state("sit", 0.25), _state("sit", 0.5)),
    (_state("sit", 1.0), _state("rise", 0.25)),
    (_state("rise", 1.0), _state("mixed", 1.0)),
])
def test_validated_promotions_keep_gradual_difficulty_and_complete_source_stages(source, destination):
    validate_forward_promotion(source, destination, _reports(source), CHECKPOINT_HASH)


@pytest.mark.parametrize("source,destination", [
    (_state(), _state("rise", 0.25)),
    (_state("rise", 1.0), _state("sit", 0.25)),
    (_state(), _state("sit", 0.5)),
    (_state("sit", 0.75), _state("rise", 0.25)),
    (_state("sit", 0.25), _state("sit", 0.75)),
    (_state("sit", 0.5), _state("sit", 0.25)),
    (_state("sit", 1.0), _state("sit", 1.0, "other-bank")),
])
def test_stage_skips_reversals_unfinished_source_stages_and_large_difficulty_jumps_are_rejected(source, destination):
    with pytest.raises(ValueError):
        validate_forward_promotion(source, destination, _reports(source), CHECKPOINT_HASH)


@pytest.mark.parametrize("field,value", [
    ("checkpoint_sha256", "wrong-checkpoint"), ("bank_sha256", "wrong-bank"),
    ("stage", "sit"), ("difficulty", 0.25), ("schema_version", 2),
    ("passed", False), ("passed", 1), ("policy_actions_unmodified", False),
    ("num_envs_per_case", 15), ("continuous_hold_seconds", 4.99),
    ("seed", "0"), ("seed", 0.0),
])
def test_promotion_rejects_reports_for_the_wrong_checkpoint_or_weaker_acceptance(field, value):
    source = _state()
    reports = _reports(source)
    reports[0][field] = value
    with pytest.raises(ValueError):
        validate_forward_promotion(source, _state("sit", 0.25), reports, CHECKPOINT_HASH)


@pytest.mark.parametrize("seeds", [(0, 1), (0, 0, 2), (0, 1, 2, 3)])
def test_promotion_requires_exactly_three_independent_seed_reports(seeds):
    source = _state()
    reports = [_reports(source)[0] | {"seed": seed} for seed in seeds]
    with pytest.raises(ValueError):
        validate_forward_promotion(source, _state("sit", 0.25), reports, CHECKPOINT_HASH)


@pytest.mark.parametrize("cases", [
    {}, {"stand_hold": 1.0}, {"stand_hold": 1.0, "sit_hold": 0.899},
    {"stand_hold": 0.95, "sit_hold": float("nan")},
    {"stand_hold": 0.95, "sit_hold": float("inf")},
    {"stand_hold": 0.95, "sit_hold": 1.01},
    {"stand_hold": 0.95, "sit_hold": 0.95, "sit_transition": 0.95},
])
def test_every_required_case_must_have_a_finite_ninety_percent_success_rate(cases):
    source = _state()
    with pytest.raises(ValueError):
        validate_forward_promotion(source, _state("sit", 0.25), _reports(source, cases), CHECKPOINT_HASH)


def test_report_thresholds_cannot_be_relaxed_to_promote_a_checkpoint():
    source = _state()
    reports = _reports(source)
    reports[0]["thresholds"]["tilt_deg"] = 20.0
    with pytest.raises(ValueError):
        validate_forward_promotion(source, _state("sit", 0.25), reports, CHECKPOINT_HASH)


def _runner(bank=None):
    """省去网络构造，仅验证任务适配确实在委托上游前执行恢复边界。"""
    cfg = SimpleNamespace(stage="hold", difficulty=0.0, gate_reports=(), restore_stage_on_inference=True, state_bank="explicit-state-bank.npz")
    bank = SimpleNamespace(sha256="source-bank-sha256") if bank is None else bank
    env = SimpleNamespace(device="cpu", command_manager=SimpleNamespace(get_term=lambda _: SimpleNamespace(cfg=cfg)), _forward_state_bank=bank)
    runner = object.__new__(ForwardCurriculumOnPolicyRunner)
    runner.env = SimpleNamespace(unwrapped=env)
    runner._forward_complete_resume = False
    runner._forward_inference_only = False
    return runner


def test_actor_only_v3_load_cannot_be_used_to_enter_training(tmp_path, monkeypatch):
    checkpoint = tmp_path / "v3.pt"
    torch.save({"infos": {"env_state": {"common_step_counter": 0}}}, checkpoint)
    loads, learns = [], []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: loads.append(args[2]) or {})
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "learn", lambda *args, **kwargs: learns.append(True))
    runner = _runner()
    runner.load(str(checkpoint), load_cfg={"actor": True})
    assert loads == [{"actor": True}]
    with pytest.raises(ValueError, match="Training must start"):
        runner.learn(1)
    assert not learns


@pytest.mark.parametrize("stage,difficulty", [("hold", 0.0), ("sit", 0.25), ("rise", 0.75), ("mixed", 1.0)])
def test_actor_only_v4_playback_restores_source_stage_before_the_upstream_reset(tmp_path, monkeypatch, stage, difficulty):
    checkpoint = tmp_path / "v4-playback.pt"
    state = _state(stage, difficulty)
    torch.save({"infos": {"forward_curriculum": state}}, checkpoint)
    loaded_stages = []

    def load(runner, *args):
        cfg = runner.env.unwrapped.command_manager.get_term("twist").cfg
        loaded_stages.append((cfg.stage, cfg.difficulty))
        return {"forward_curriculum": state}

    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", load)
    runner = _runner()
    runner.load(str(checkpoint), load_cfg={"actor": True})
    assert loaded_stages == [(stage, difficulty)]
    assert runner.curriculum_state() == state
    with pytest.raises(ValueError, match="Training must start"):
        runner.learn(1)


def test_actor_only_v4_playback_rejects_a_different_initial_state_bank_before_loading(tmp_path, monkeypatch):
    checkpoint = tmp_path / "v4-wrong-bank.pt"
    torch.save({"infos": {"forward_curriculum": _state("sit", 0.25, "other-bank")}}, checkpoint)
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: calls.append(True))
    runner = _runner()
    with pytest.raises(ValueError, match="matching forward state bank"):
        runner.load(str(checkpoint), load_cfg={"actor": True})
    assert runner.curriculum_state() == _state()
    assert not calls


def test_actor_only_v4_playback_restores_the_embedded_bank_before_upstream_loading(tmp_path, bank_writer, monkeypatch):
    path = bank_writer()
    content = path.read_bytes()
    state = _state("sit", 0.25, hashlib.sha256(content).hexdigest())
    checkpoint = tmp_path / "v4-embedded-bank.pt"
    torch.save({"infos": {"forward_curriculum": {**state, "bank_snapshot": content, "bank_source": str(path)}}}, checkpoint)
    calls = []

    def load(runner, *args):
        bank = runner.env.unwrapped._forward_state_bank
        calls.append((bank, runner.curriculum_state()))
        return {}

    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", load)
    runner = _runner()
    runner.load(str(checkpoint), load_cfg={"actor": True})
    bank = runner.env.unwrapped._forward_state_bank
    assert isinstance(bank, ForwardStateBank) and bank.path is None
    assert bank.content == content and bank.sha256 == state["bank_sha256"]
    assert calls == [(bank, state)]
    assert runner.env.unwrapped.command_manager.get_term("twist").cfg.state_bank == "checkpoint:" + bank.sha256
    with pytest.raises(ValueError, match="Training must start"):
        runner.learn(1)


def test_embedded_bank_with_a_wrong_hash_is_rejected_without_replacing_runtime_state(tmp_path, bank_writer, monkeypatch):
    source = bank_writer()
    other = bank_writer(metadata={"fixture_name": "different-valid-bank"})
    checkpoint = tmp_path / "v4-corrupt-bank-fingerprint.pt"
    state = _state("sit", 0.25, hashlib.sha256(source.read_bytes()).hexdigest())
    torch.save({"infos": {"forward_curriculum": {**state, "bank_snapshot": other.read_bytes()}}}, checkpoint)
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: calls.append(True))
    runner = _runner()
    previous_bank = runner.env.unwrapped._forward_state_bank
    with pytest.raises(ValueError, match="snapshot does not match"):
        runner.load(str(checkpoint), load_cfg={"actor": True})
    assert runner.env.unwrapped._forward_state_bank is previous_bank
    assert runner.curriculum_state() == _state()
    assert runner.env.unwrapped.command_manager.get_term("twist").cfg.state_bank == "explicit-state-bank.npz"
    assert not calls


def test_actor_only_evaluation_can_preserve_its_explicit_protocol_instead_of_source_stage(tmp_path, monkeypatch):
    checkpoint = tmp_path / "v4-evaluation.pt"
    torch.save({"infos": {"forward_curriculum": _state("rise", 0.75, "different-bank-without-snapshot")}}, checkpoint)
    loaded_stages = []

    def load(runner, *args):
        cfg = runner.env.unwrapped.command_manager.get_term("twist").cfg
        loaded_stages.append((cfg.stage, cfg.difficulty))
        return {}

    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", load)
    runner = _runner()
    cfg = runner.env.unwrapped.command_manager.get_term("twist").cfg
    cfg.restore_stage_on_inference = False
    runner.load(str(checkpoint), load_cfg={"actor": True})
    assert loaded_stages == [("hold", 0.0)]
    assert runner.curriculum_state() == _state()


def test_full_v3_resume_is_rejected_before_changing_the_algorithm(tmp_path, monkeypatch):
    checkpoint = tmp_path / "v3.pt"
    torch.save({"infos": {"env_state": {"common_step_counter": 0}}}, checkpoint)
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: calls.append(True))
    with pytest.raises(ValueError, match="metadata"):
        _runner().load(str(checkpoint))
    assert not calls


@pytest.mark.parametrize("load_cfg", [None, {"actor": True, "critic": True, "optimizer": True, "iteration": True}])
def test_same_v4_full_resume_delegates_and_preserves_learning_eligibility(tmp_path, monkeypatch, load_cfg):
    checkpoint = tmp_path / "v4.pt"
    infos = {"forward_curriculum": _state(), "env_state": {"common_step_counter": 480}}
    torch.save({"infos": infos}, checkpoint)
    learns = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: infos)
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "learn", lambda runner, count, randomize: learns.append((count, randomize)))
    runner = _runner()
    assert runner.load(str(checkpoint), load_cfg=load_cfg) == infos
    runner.learn(5, init_at_random_ep_len=True)
    assert learns == [(5, True)]


@pytest.mark.parametrize("load_cfg", [
    {"actor": True, "critic": True},
    {"actor": True, "critic": True, "optimizer": True},
    {"actor": True, "critic": True, "iteration": True},
    {"optimizer": True, "iteration": True},
])
def test_partial_v4_load_cannot_masquerade_as_complete_curriculum_resume(tmp_path, monkeypatch, load_cfg):
    checkpoint = tmp_path / "v4-partial.pt"
    torch.save({"infos": {"forward_curriculum": _state()}}, checkpoint)
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "load", lambda *args, **kwargs: calls.append(True) or {})
    with pytest.raises(ValueError):
        _runner().load(str(checkpoint), load_cfg=load_cfg)
    assert not calls


def test_runner_saves_curriculum_metadata_without_dropping_other_information(bank_writer, monkeypatch):
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "save", lambda runner, path, infos: calls.append((path, infos)))
    path = bank_writer()
    bank = ForwardStateBank(str(path), "cpu")
    _runner(bank).save("checkpoint.pt", {"experiment": "hold-boundary"})
    state = {**_state(bank=bank.sha256), "bank_snapshot": path.read_bytes(), "bank_source": str(path.resolve())}
    assert calls == [("checkpoint.pt", {"experiment": "hold-boundary", "forward_curriculum": state})]


@pytest.mark.parametrize("stage,difficulty", [("sit", 0.25), ("rise", 0.25), ("mixed", 1.0)])
def test_later_stages_cannot_start_without_a_complete_validated_resume(stage, difficulty, monkeypatch):
    calls = []
    monkeypatch.setattr(OfficialTaskOnPolicyRunner, "learn", lambda *args, **kwargs: calls.append(True))
    runner = _runner()
    cfg = runner.env.unwrapped.command_manager.get_term("twist").cfg
    cfg.stage, cfg.difficulty = stage, difficulty
    with pytest.raises(ValueError, match="Training must start"):
        runner.learn(1)
    assert not calls
