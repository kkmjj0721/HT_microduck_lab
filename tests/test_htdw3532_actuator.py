"""CPU checks for the 3532 output-shaft NT envelope and native affine PD."""

import dataclasses
import json
import math
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest
import torch
from mjlab.actuator.actuator import ActuatorCmd, TransmissionType
from mjlab.actuator.fused_group import FusedActuatorGroup
from mjlab.entity import Entity, EntityArticulationInfoCfg, EntityCfg

from ht_microduck.actuators.HTDW_3532_02_DNE import model as nt_model
from ht_microduck.actuators.HTDW_3532_02_DNE.model import (
    clip_nt_torque,
    load_htdw3532_parameters,
    motoring_torque_limit,
)
from ht_microduck.actuators.HTDW_3532_02_DNE.nt_actuator import (
    HTDW3532Actuator,
    HTDW3532ActuatorCfg,
)

# Rounded samples of the supplied 24 V output-shaft curve, not hardware tests.
RPM = np.array([0.0, 26.0, 59.0, 92.0, 128.0, 167.0, 211.0, 258.0, 300.0])
TORQUE_NM = np.array([3.7, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0])


@pytest.fixture(scope="module")
def parameters():
    return load_htdw3532_parameters()


def _write_parameters(tmp_path, changes):
    path = Path(nt_model.__file__).parent / "params/htdw_3532_24v.json"
    payload = json.loads(path.read_text())
    payload.update(changes)
    destination = tmp_path / "parameters.json"
    destination.write_text(json.dumps(payload))
    return destination


def _hinge_spec(joint_type="hinge"):
    bodies = "".join(
        f'<body name="link_{index}" pos="{0.2 * index} 0 0">'
        f'<joint name="joint_{index}" type="{joint_type}" axis="0 0 1" '
        'range="-0.5 0.5" damping="0.02"/>'
        '<geom type="sphere" size="0.02" mass="0.1"/>'
        "</body>"
        for index in range(2)
    )
    return mujoco.MjSpec.from_string(
        f'<mujoco><compiler angle="radian"/><worldbody>{bodies}</worldbody></mujoco>'
    )


def _initialized_actuator(*, num_envs=2, **changes):
    cfg = HTDW3532ActuatorCfg(
        target_names_expr=("joint_0", "joint_1"),
        stiffness=changes.pop("stiffness", 2.0),
        damping=changes.pop("damping", 0.5),
        effort_limit=changes.pop("effort_limit", 2.0),
        **changes,
    )
    entity = Entity(
        EntityCfg(
            spec_fn=_hinge_spec,
            articulation=EntityArticulationInfoCfg(actuators=(cfg,)),
        )
    )
    model = entity.compile()
    # Actual compiled target/ctrl mappings, without allocating a GPU simulation.
    entity.indexing = entity._compute_indexing(model, "cpu")
    actuator = entity.actuators[0]
    bridge = SimpleNamespace(
        actuator_biasprm=torch.tensor(model.actuator_biasprm, dtype=torch.float32)[
            None
        ].repeat(num_envs, 1, 1),
        actuator_forcerange=torch.tensor(
            model.actuator_forcerange, dtype=torch.float32
        )[None].repeat(num_envs, 1, 1),
    )
    actuator.initialize(model, bridge, SimpleNamespace(nworld=num_envs), "cpu")
    return actuator, model, bridge


def _command(position_target, velocity_target, effort_target, pos, vel):
    return ActuatorCmd(
        position_target=torch.tensor(position_target, dtype=torch.float32),
        velocity_target=torch.tensor(velocity_target, dtype=torch.float32),
        effort_target=torch.tensor(effort_target, dtype=torch.float32),
        pos=torch.tensor(pos, dtype=torch.float32),
        vel=torch.tensor(vel, dtype=torch.float32),
    )


def _native_output(actuator, model, bridge, cmd):
    """Evaluate the actual affine actuator after copying each CPU bridge world."""
    control = actuator.compute(cmd)
    q_ids = [int(model.joint(name).qposadr[0]) for name in actuator.target_names]
    dof_ids = [int(model.joint(name).dofadr[0]) for name in actuator.target_names]
    ctrl_ids = actuator.global_ctrl_ids.numpy()
    torque = []
    for world in range(cmd.pos.shape[0]):
        model.actuator_biasprm[:] = bridge.actuator_biasprm[world].numpy()
        model.actuator_forcerange[:] = bridge.actuator_forcerange[world].numpy()
        data = mujoco.MjData(model)
        data.qpos[q_ids] = cmd.pos[world].numpy()
        data.qvel[dof_ids] = cmd.vel[world].numpy()
        data.ctrl[ctrl_ids] = control[world].numpy()
        mujoco.mj_forward(model, data)
        torque.append(data.actuator_force[ctrl_ids].copy())
    return control, torch.tensor(np.stack(torque), dtype=cmd.pos.dtype)


def test_packaged_curve_is_output_shaft_data_and_immutable(parameters):
    assert parameters.voltage_v == 24.0
    assert parameters.gear_ratio == 32
    assert parameters.continuous_rated_torque_nm == 0.6
    assert parameters.stall_torque_nm == 3.7
    assert parameters.rpm == tuple(RPM)
    assert parameters.motoring_torque_nm == tuple(TORQUE_NM)
    with pytest.raises(dataclasses.FrozenInstanceError):
        parameters.voltage_v = 12.0


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_anchors_midpoints_and_signed_speeds_match_independent_interpolation(
    parameters, dtype
):
    midpoints = (RPM[:-1] + RPM[1:]) / 2
    speeds_rpm = np.concatenate((-RPM[::-1], midpoints, RPM, [400.0, -400.0]))
    velocity = torch.tensor(speeds_rpm * (2 * math.pi / 60), dtype=dtype)[None]
    actual = motoring_torque_limit(velocity, parameters)
    expected = np.interp(np.abs(speeds_rpm), RPM, TORQUE_NM, right=0.0)
    np.testing.assert_allclose(actual[0].numpy(), expected, atol=2e-6, rtol=1e-6)
    assert actual.shape == velocity.shape
    assert actual.dtype == dtype
    assert actual.device == velocity.device
    # A second unit conversion or a second gearbox factor breaks these anchors.
    assert motoring_torque_limit(
        torch.tensor(211 * 2 * math.pi / 60, dtype=dtype), parameters
    ).item() == pytest.approx(1.0, abs=2e-6)


def test_four_quadrants_zero_speed_and_per_environment_derating(parameters):
    velocity = torch.tensor([[211.0, 211.0, -211.0, -211.0], [0.0] * 4])
    velocity *= 2 * math.pi / 60
    request = torch.tensor([[5.0, -5.0, 5.0, -5.0], [5.0, -5.0, 0.1, -0.1]])
    limit = torch.tensor([[2.0], [0.35]])
    actual = clip_nt_torque(request, velocity, limit, parameters)
    expected = torch.tensor([[1.0, -2.0, 2.0, -1.0], [0.35, -0.35, 0.1, -0.1]])
    torch.testing.assert_close(actual, expected, atol=2e-6, rtol=1e-6)


def test_no_load_and_overspeed_remove_drive_but_allow_braking_and_zero(parameters):
    velocity = torch.tensor([[300.0, -300.0, 400.0, -400.0]]).repeat(3, 1)
    velocity *= 2 * math.pi / 60
    requests = torch.tensor([[5.0, -5.0, 5.0, -5.0], [-5.0, 5.0, -5.0, 5.0], [0.0] * 4])
    actual = clip_nt_torque(requests, velocity, 2.0, parameters)
    expected = torch.tensor([[0.0] * 4, [-2.0, 2.0, -2.0, 2.0], [0.0] * 4])
    torch.testing.assert_close(actual, expected, atol=2e-6, rtol=1e-6)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("voltage_v", 0.0),
        ("voltage_v", math.inf),
        ("gear_ratio", True),
        ("continuous_rated_torque_nm", -0.1),
        ("continuous_rated_torque_nm", 3.8),
        ("stall_torque_nm", math.nan),
        ("rpm", [0.0]),
        ("rpm", [1.0, 300.0]),
        ("rpm", [0.0, 0.0]),
        ("rpm", [0.0, math.inf]),
        ("motoring_torque_nm", [3.7]),
        ("motoring_torque_nm", [3.7, 3.8, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0]),
        ("motoring_torque_nm", [3.6, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0]),
        ("motoring_torque_nm", [3.7, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.1]),
        ("motoring_torque_nm", [3.7, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, -0.1]),
        ("motoring_torque_nm", [3.7, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, math.nan]),
    ],
)
def test_loader_rejects_invalid_curve_domains(tmp_path, field, value):
    with pytest.raises(ValueError):
        load_htdw3532_parameters(_write_parameters(tmp_path, {field: value}))


def test_loader_requires_complete_schema_and_reports_malformed_json(tmp_path):
    path = _write_parameters(tmp_path, {"voltag_v": 24.0})
    with pytest.raises(ValueError):
        load_htdw3532_parameters(path)
    payload = json.loads(path.read_text())
    del payload["voltag_v"]
    del payload["rpm"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_htdw3532_parameters(path)
    path.write_text("{broken")
    with pytest.raises(ValueError):
        load_htdw3532_parameters(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stiffness", -1.0),
        ("stiffness", math.nan),
        ("damping", -1.0),
        ("damping", math.inf),
        ("effort_limit", 0.0),
        ("effort_limit", -1.0),
        ("effort_limit", math.inf),
        ("effort_limit", 3.8),
        ("transmission_type", TransmissionType.TENDON),
        ("target_names_expr", ()),
    ],
)
def test_cfg_rejects_invalid_domains(field, value):
    values = {
        "target_names_expr": ("joint_0",),
        "stiffness": 2.0,
        "damping": 0.5,
        "effort_limit": 2.0,
    }
    values[field] = value
    with pytest.raises(ValueError):
        HTDW3532ActuatorCfg(**values)


def test_non_hinge_targets_are_rejected_before_actuators_are_added():
    cfg = HTDW3532ActuatorCfg(
        target_names_expr=("joint_0", "joint_1"),
        stiffness=2.0,
        damping=0.5,
        effort_limit=2.0,
    )
    spec = _hinge_spec(joint_type="slide")
    actuator = cfg.build(SimpleNamespace(), [0, 1], ["joint_0", "joint_1"])
    with pytest.raises(ValueError):
        actuator.edit_spec(spec, ["joint_0", "joint_1"])
    assert not spec.actuators


def test_initialized_compute_uses_position_velocity_and_feedforward_targets():
    actuator, model, bridge = _initialized_actuator()
    cmd = _command(
        [[0.4, -0.1], [-0.4, 0.1]],
        [[0.3, 0.1], [-0.3, -0.1]],
        [[0.15, -0.1], [-0.15, 0.1]],
        [[0.3, -0.2], [-0.3, 0.2]],
        [[0.1, -0.2], [-0.1, 0.2]],
    )
    control, actual = _native_output(actuator, model, bridge, cmd)
    expected = torch.tensor([[0.45, 0.25], [-0.45, -0.25]])
    torch.testing.assert_close(actual, expected)
    torch.testing.assert_close(control, torch.tensor([[1.1, -0.25], [-1.1, 0.25]]))
    assert isinstance(actuator, HTDW3532Actuator)
    np.testing.assert_allclose(model.actuator_gainprm[:, 0], 1.0)
    np.testing.assert_allclose(model.actuator_biasprm[:, 1], -2.0)
    np.testing.assert_allclose(model.actuator_biasprm[:, 2], -0.5)
    assert not model.actuator_ctrllimited.any()
    assert all(item.inheritrange == 0.0 for item in actuator._mjs_actuators)
    # Custom compute must update the native fields on every real Entity call.
    fused, remaining = FusedActuatorGroup.process((actuator,))
    assert remaining == (actuator,)
    assert not fused._groups


def test_compute_respects_runtime_gains_and_per_environment_effort_limit():
    actuator, model, bridge = _initialized_actuator()
    actuator.set_gains(
        slice(None), kp=torch.tensor([1.0, 2.0]), kd=torch.tensor([0.0, 0.0])
    )
    actuator.set_effort_limit(slice(None), torch.tensor([0.1, 0.3]))
    cmd = _command(
        [[0.2, -0.2]] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
    )
    _, actual = _native_output(actuator, model, bridge, cmd)
    torch.testing.assert_close(actual, torch.tensor([[0.1, -0.1], [0.3, -0.3]]))
    torch.testing.assert_close(
        bridge.actuator_biasprm[:, :, 1],
        torch.tensor([[-1.0] * 2, [-2.0] * 2], dtype=bridge.actuator_biasprm.dtype),
    )


def test_position_target_is_not_silently_clipped_to_joint_limits():
    actuator, model, bridge = _initialized_actuator(stiffness=0.1, damping=0.0)
    cmd = _command(
        [[2.0, -2.0]] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
    )
    _, actual = _native_output(actuator, model, bridge, cmd)
    torch.testing.assert_close(actual, torch.tensor([[0.2, -0.2]] * 2))


def test_large_absolute_positions_do_not_clip_the_affine_target_term():
    actuator, model, bridge = _initialized_actuator(stiffness=10.0, damping=0.4)
    cmd = _command(
        [[3.01, -3.01]] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[3.0, -3.0]] * 2,
        [[0.0] * 2] * 2,
    )
    control, actual = _native_output(actuator, model, bridge, cmd)
    assert control.abs().min() > 30.0
    torch.testing.assert_close(
        actual, torch.tensor([[0.1, -0.1]] * 2), atol=3e-6, rtol=1e-5
    )


def test_zero_kp_still_supports_velocity_targets_and_feedforward():
    actuator, model, bridge = _initialized_actuator(stiffness=0.0, damping=0.5)
    cmd = _command(
        [[1000.0, -1000.0]] * 2,
        [[0.4, -0.4]] * 2,
        [[0.1, -0.1]] * 2,
        [[0.3, -0.3]] * 2,
        [[0.1, -0.1]] * 2,
    )
    _, actual = _native_output(actuator, model, bridge, cmd)
    torch.testing.assert_close(actual, torch.tensor([[0.25, -0.25]] * 2))


@pytest.mark.parametrize("field", ["actuator_forcerange", "actuator_biasprm"])
@pytest.mark.parametrize("problem", ["missing", "aliased"])
def test_compute_requires_independent_expanded_model_fields(field, problem):
    actuator, _, bridge = _initialized_actuator()
    if problem == "missing":
        delattr(bridge, field)
    else:
        original = getattr(bridge, field)
        setattr(bridge, field, original[:1].expand(2, -1, -1))
    cmd = _command(*([[[0.0] * 2] * 2] * 5))
    with pytest.raises(RuntimeError):
        actuator.compute(cmd)


def test_ranges_are_independent_and_partial_reset_restores_only_selected_world():
    actuator, _, bridge = _initialized_actuator()
    speed = 211 * 2 * math.pi / 60
    cmd = _command(
        [[0.1] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[speed, -speed], [-speed, speed]],
    )
    actuator.compute(cmd)
    expected = torch.tensor(
        [[[-2.0, 1.0], [-1.0, 2.0]], [[-1.0, 2.0], [-2.0, 1.0]]],
        dtype=bridge.actuator_forcerange.dtype,
    )
    torch.testing.assert_close(
        bridge.actuator_forcerange, expected, atol=2e-6, rtol=1e-6
    )
    before_other = bridge.actuator_forcerange[1].clone()
    before_other_bias = bridge.actuator_biasprm[1].clone()
    actuator.set_gains(
        torch.tensor([0]), kp=torch.tensor([1.25]), kd=torch.tensor([0.75])
    )
    actuator.reset(torch.tensor([0]))
    torch.testing.assert_close(
        bridge.actuator_forcerange[0],
        torch.tensor([[-2.0, 2.0]] * 2, dtype=expected.dtype),
    )
    torch.testing.assert_close(bridge.actuator_forcerange[1], before_other)
    torch.testing.assert_close(bridge.actuator_biasprm[1], before_other_bias)
    torch.testing.assert_close(
        bridge.actuator_biasprm[0, :, 1],
        torch.full((2,), -1.25, dtype=bridge.actuator_biasprm.dtype),
    )
    torch.testing.assert_close(
        bridge.actuator_biasprm[0, :, 2],
        torch.full((2,), -0.75, dtype=bridge.actuator_biasprm.dtype),
    )


def test_compute_reloads_fields_after_model_reallocation():
    actuator, _, bridge = _initialized_actuator()
    previous_range = bridge.actuator_forcerange
    previous_bias = bridge.actuator_biasprm
    bridge.actuator_forcerange = previous_range.clone()
    bridge.actuator_biasprm = previous_bias.clone()
    speed = 211 * 2 * math.pi / 60
    cmd = _command(*([[[0.0] * 2] * 2] * 4), [[speed] * 2] * 2)
    actuator.set_gains(slice(None), kp=torch.tensor([1.0, 1.0]))
    actuator.compute(cmd)
    torch.testing.assert_close(
        previous_range,
        torch.tensor([[[-2.0, 2.0]] * 2] * 2, dtype=previous_range.dtype),
    )
    torch.testing.assert_close(
        previous_bias[:, :, 1], torch.full((2, 2), -2.0, dtype=previous_bias.dtype)
    )
    torch.testing.assert_close(
        bridge.actuator_forcerange[:, :, 1],
        torch.ones((2, 2), dtype=previous_range.dtype),
        atol=2e-6,
        rtol=1e-6,
    )
    torch.testing.assert_close(
        bridge.actuator_biasprm[:, :, 1],
        torch.full((2, 2), -1.0, dtype=previous_bias.dtype),
    )


def test_runtime_effort_increase_cannot_remove_the_initial_compiled_cap():
    actuator, model, bridge = _initialized_actuator(effort_limit=0.35)
    actuator.set_effort_limit(slice(None), torch.tensor([2.0, 3.7]))
    cmd = _command(
        [[10.0, -10.0]] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
        [[0.0] * 2] * 2,
    )
    _, actual = _native_output(actuator, model, bridge, cmd)
    torch.testing.assert_close(actual, torch.tensor([[0.35, -0.35]] * 2))
    actuator.reset(torch.tensor([0]))
    torch.testing.assert_close(
        bridge.actuator_forcerange[:, :, 1],
        torch.full((2, 2), 0.35, dtype=bridge.actuator_forcerange.dtype),
    )


def test_delay_delays_all_targets_but_uses_current_feedback_after_partial_reset():
    actuator, model, bridge = _initialized_actuator(delay_min_lag=1, delay_max_lag=1)
    first = _command(
        [[0.1, 0.1]] * 2,
        [[0.2, 0.2]] * 2,
        [[0.03, 0.03]] * 2,
        [[0.0, 0.0]] * 2,
        [[0.0, 0.0]] * 2,
    )
    actuator.apply_delay(first)
    second = _command(
        [[0.2, 0.2]] * 2,
        [[0.4, 0.4]] * 2,
        [[0.06, 0.06]] * 2,
        [[0.04, 0.04]] * 2,
        [[0.1, 0.1]] * 2,
    )
    delayed = actuator.apply_delay(second)
    # Delayed target fields from first; current position and speed from second.
    _, actual = _native_output(actuator, model, bridge, delayed)
    torch.testing.assert_close(actual, torch.full((2, 2), 0.2))
    actuator.reset(torch.tensor([0]))
    third = _command(
        [[0.3, 0.3]] * 2,
        [[0.6, 0.6]] * 2,
        [[0.09, 0.09]] * 2,
        [[0.04, 0.04]] * 2,
        [[0.1, 0.1]] * 2,
    )
    delayed = actuator.apply_delay(third)
    # Reset world backfills the new target; other world retains second's history.
    _, actual = _native_output(actuator, model, bridge, delayed)
    torch.testing.assert_close(actual, torch.tensor([[0.86, 0.86], [0.53, 0.53]]))
