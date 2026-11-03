# Copyright (c) 2026-2027 zh
"""验证前坐课程初态、编码器补偿、动作历史与局部延迟回填。"""

from types import SimpleNamespace

import numpy as np
import pytest
import torch
from mjlab.managers.action_manager import ActionManager
from mjlab.utils.buffers import DelayBuffer

from ht_microduck.robot.ht_microduck_constants import HOME_JOINT_POS
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.mdp.forward_initialization import (
    ForwardInitializedJointPositionActionCfg,
    capture_forward_state,
    set_forward_initial_state,
)


class _Robot:
    """保留实体与策略不同的关节顺序，延迟使用实际mjlab缓冲区。"""

    def __init__(self, count):
        self.joint_names = ["mouth_joint", *reversed(C.POLICY_JOINT_NAMES)]
        home = torch.tensor([HOME_JOINT_POS[name] for name in self.joint_names]).repeat(
            count, 1
        )
        self.data = SimpleNamespace(
            default_joint_pos=home.clone(),
            joint_pos=home.clone(),
            joint_vel=torch.zeros_like(home),
            joint_pos_target=home.clone(),
            joint_vel_target=torch.zeros_like(home),
            joint_effort_target=torch.zeros_like(home),
            joint_pos_limits=torch.tensor([-4.0, 4.0]).repeat(count, 15, 1),
            encoder_bias=torch.linspace(-0.015, 0.015, count * 15).reshape(count, 15),
            root_link_pose_w=torch.zeros(count, 7),
            root_link_vel_w=torch.zeros(count, 6),
        )
        self.data.root_link_pose_w[:, 3] = 1.0
        self.actuators = [
            SimpleNamespace(
                target_ids=torch.arange(0, 5),
                _delay_buffer=DelayBuffer(
                    max_lag=3, batch_size=count, update_period=10
                ),
                _load_valid=torch.zeros(count, 1, dtype=torch.bool),
            ),
            SimpleNamespace(
                target_ids=torch.arange(5, 15),
                _delay_buffer=DelayBuffer(
                    max_lag=3, batch_size=count, update_period=10
                ),
            ),
        ]

    def find_joints_by_actuator_names(self, names):
        return [self.joint_names.index(name) for name in names], list(names)

    def write_root_link_pose_to_sim(self, pose, *, env_ids):
        self.data.root_link_pose_w[env_ids] = pose

    def write_root_link_velocity_to_sim(self, velocity, *, env_ids):
        self.data.root_link_vel_w[env_ids] = velocity

    def write_joint_state_to_sim(self, position, velocity, *, env_ids):
        self.data.joint_pos[env_ids] = position
        self.data.joint_vel[env_ids] = velocity

    def set_joint_position_target(self, target, *, env_ids=None, joint_ids=None):
        rows = slice(None) if env_ids is None else env_ids
        if joint_ids is None:
            self.data.joint_pos_target[rows] = target
        else:
            self.data.joint_pos_target[rows, joint_ids] = target

    def set_joint_velocity_target(self, target, *, env_ids):
        self.data.joint_vel_target[env_ids] = target

    def set_joint_effort_target(self, target, *, env_ids):
        self.data.joint_effort_target[env_ids] = target


class _Scene(dict):
    pass


def _environment(count=3):
    robot = _Robot(count)
    scene = _Scene(robot=robot)
    scene.env_origins = torch.arange(count * 3).reshape(count, 3).float()
    env = SimpleNamespace(scene=scene, num_envs=count, device="cpu")
    cfg = ForwardInitializedJointPositionActionCfg(
        entity_name="robot", actuator_names=C.POLICY_JOINT_NAMES, scale=1.0
    )
    env.action_manager = ActionManager({"joint_pos": cfg}, env)
    return env, robot, env.action_manager.get_term("joint_pos")


def _state(robot, ids):
    count = len(ids)
    pose = torch.zeros(count, 7)
    pose[:, 2] = 0.0564
    pose[:, 3] = 1.0
    target = robot.data.default_joint_pos[ids].clone()
    target[:, robot.joint_names.index("r_hip_pitch_joint")] = -1.55
    target[:, robot.joint_names.index("l_hip_pitch_joint")] = -1.55
    return {
        "root_pose": pose,
        "root_velocity": torch.zeros(count, 6),
        "joint_pos": target + 0.002,
        "joint_vel": torch.full_like(target, 0.001),
        "position_target": target,
    }


def test_initial_state_translates_origins_without_mutating_input_or_neighbors():
    env, robot, _ = _environment()
    ids = torch.tensor([1])
    state = _state(robot, ids)
    original = {name: value.clone() for name, value in state.items()}
    neighbors = robot.data.joint_pos[[0, 2]].clone()
    set_forward_initial_state(env, ids, **state)
    torch.testing.assert_close(
        robot.data.root_link_pose_w[ids, :3],
        state["root_pose"][:, :3] + env.scene.env_origins[ids],
    )
    torch.testing.assert_close(robot.data.joint_pos[ids], state["joint_pos"])
    torch.testing.assert_close(robot.data.joint_vel[ids], state["joint_vel"])
    torch.testing.assert_close(
        env._forward_initial_target[ids], state["position_target"]
    )
    assert torch.equal(robot.data.joint_pos[[0, 2]], neighbors)
    assert all(torch.equal(state[name], original[name]) for name in state)


def test_action_reset_compensates_encoder_bias_and_restores_all_history_levels():
    env, robot, term = _environment()
    ids = torch.tensor([1])
    state = _state(robot, ids)
    set_forward_initial_state(env, ids, **state)
    env.action_manager.reset(ids)
    physical = state["position_target"][:, term.target_ids]
    raw = (
        physical
        + robot.data.encoder_bias[ids][:, term.target_ids]
        - robot.data.default_joint_pos[ids][:, term.target_ids]
    )
    for values in (
        env.action_manager.action,
        env.action_manager.prev_action,
        env.action_manager.prev_prev_action,
        term.raw_action,
    ):
        torch.testing.assert_close(values[ids], raw)
    torch.testing.assert_close(
        term._processed_actions[ids],
        physical + robot.data.encoder_bias[ids][:, term.target_ids],
    )
    torch.testing.assert_close(term.requested_targets[ids], physical)
    torch.testing.assert_close(term.applied_targets[ids], physical)
    torch.testing.assert_close(
        robot.data.joint_pos_target[ids], state["position_target"]
    )
    assert not robot.data.joint_vel_target[ids].any()
    assert not robot.data.joint_effort_target[ids].any()
    assert not robot.actuators[0]._load_valid.any()


def test_first_delay_allocation_and_selected_reset_keep_neighbor_timeline():
    env, robot, term = _environment()
    assert all(actuator._delay_buffer.is_initialized for actuator in robot.actuators)
    env.action_manager.reset()
    env.action_manager.process_action(torch.linspace(-0.2, 0.2, 42).reshape(3, 14))
    term.apply_actions()
    for actuator in robot.actuators:
        data = torch.stack(
            (
                robot.data.joint_pos_target[:, actuator.target_ids],
                robot.data.joint_vel_target[:, actuator.target_ids],
                robot.data.joint_effort_target[:, actuator.target_ids],
            ),
            dim=-1,
        )
        actuator._delay_buffer.append(data)
        actuator._delay_buffer.compute()
    neighbors = torch.tensor([0, 2])
    snapshots = [
        (
            actuator._delay_buffer._buffer.buffer.clone(),
            actuator._delay_buffer._current_lags.clone(),
            actuator._delay_buffer._step_count.clone(),
            actuator._delay_buffer._phase_offsets.clone(),
            actuator._delay_buffer._buffer._pointer,
        )
        for actuator in robot.actuators
    ]
    previous_actions = env.action_manager.action[neighbors].clone()
    previous_targets = robot.data.joint_pos_target[neighbors].clone()
    term_before = tuple(
        value[neighbors].clone()
        for value in (
            term.raw_action,
            term._processed_actions,
            term.requested_targets,
            term.applied_targets,
        )
    )
    ids = torch.tensor([1])
    for actuator in robot.actuators:
        actuator._delay_buffer.reset(ids)
    set_forward_initial_state(env, ids, **_state(robot, ids))
    env.action_manager.reset(ids)
    assert torch.equal(env.action_manager.action[neighbors], previous_actions)
    assert torch.equal(robot.data.joint_pos_target[neighbors], previous_targets)
    for before, after in zip(
        term_before,
        (
            term.raw_action,
            term._processed_actions,
            term.requested_targets,
            term.applied_targets,
        ),
    ):
        assert torch.equal(before, after[neighbors])
    for actuator, snapshot in zip(robot.actuators, snapshots):
        buffer = actuator._delay_buffer
        history, lags, steps, phases, pointer = snapshot
        assert torch.equal(buffer._buffer.buffer[neighbors], history[neighbors])
        assert torch.equal(buffer._current_lags[neighbors], lags[neighbors])
        assert torch.equal(buffer._step_count[neighbors], steps[neighbors])
        assert torch.equal(buffer._phase_offsets[neighbors], phases[neighbors])
        assert buffer._buffer._pointer == pointer
        targets = robot.data.joint_pos_target[ids][:, actuator.target_ids]
        expected = torch.stack(
            (targets, torch.zeros_like(targets), torch.zeros_like(targets)), dim=-1
        )
        torch.testing.assert_close(
            buffer._buffer.buffer[ids], expected[:, None].expand(-1, 4, -1, -1)
        )


def test_capture_uses_relative_root_pose_and_detached_copies():
    env, robot, _ = _environment()
    ids = torch.arange(env.num_envs)
    set_forward_initial_state(env, ids, **_state(robot, ids))
    env.action_manager.reset()
    state = capture_forward_state(env)
    assert set(state) == {
        "root_pose",
        "root_velocity",
        "joint_pos",
        "joint_vel",
        "position_target",
    }
    np.testing.assert_allclose(
        state["root_pose"][:, :3], np.tile([0.0, 0.0, 0.0564], (3, 1)), atol=1e-6
    )
    assert all(value.dtype == np.float32 for value in state.values())
    saved = state["position_target"].copy()
    robot.data.joint_pos_target.zero_()
    assert np.array_equal(state["position_target"], saved)


@pytest.mark.parametrize(
    "field", ["root_pose", "root_velocity", "joint_pos", "joint_vel", "position_target"]
)
def test_initial_state_rejects_nonfinite_values_before_writing(field):
    env, robot, _ = _environment()
    ids = torch.tensor([0])
    state = _state(robot, ids)
    state[field][0, 0] = float("nan")
    before = robot.data.joint_pos.clone()
    with pytest.raises(ValueError, match=field):
        set_forward_initial_state(env, ids, **state)
    assert torch.equal(robot.data.joint_pos, before)


def test_initial_state_rejects_invalid_quaternion_shape_and_physical_target():
    env, robot, _ = _environment()
    ids = torch.tensor([0])
    state = _state(robot, ids)
    state["root_pose"][0, 3] = 0.5
    with pytest.raises(ValueError, match="normalized"):
        set_forward_initial_state(env, ids, **state)
    state = _state(robot, ids)
    state["joint_vel"] = torch.zeros(1, 14)
    with pytest.raises(ValueError, match="joint_vel"):
        set_forward_initial_state(env, ids, **state)
    state = _state(robot, ids)
    state["position_target"][0, 0] = 5.0
    with pytest.raises(ValueError, match="physical joint limits"):
        set_forward_initial_state(env, ids, **state)
