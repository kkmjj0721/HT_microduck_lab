"""CPU integration checks for the robot's mixed actuator configuration."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest
import torch
from mjlab.actuator.actuator import ActuatorCmd
from mjlab.entity import Entity, EntityArticulationInfoCfg, EntityCfg

from ht_microduck.actuators import FrictionDRBamActuatorCfg
from ht_microduck.actuators.HD_1910_C001.model import load_hd1910_parameters
from ht_microduck.actuators.HTDW_3532_02_DNE.nt_actuator import HTDW3532ActuatorCfg
from ht_microduck.robots.ht_microduck.ht_microduck_constants import (
    BRUSHLESS_ACTUATOR_CFG,
    BRUSHLESS_JOINT_NAMES,
    BRUSHLESS_MJCF_EFFORT_LIMIT,
    JOINT_NAMES,
    SERVO_ACTUATOR_CFG,
    SERVO_JOINT_NAMES,
    get_spec,
)


# Explicit simulation cases, not hardware estimates. Include the XML ceiling
# and zero active damping to verify both boundaries in the compiled physics.
@pytest.fixture(scope="module", params=[(10.0, 0.4, 2.0), (2.0, 0.0, 3.7)])
def actuated_robot(request):
    stiffness, damping, effort_limit = request.param
    entity = Entity(
        EntityCfg(
            spec_fn=get_spec,
            articulation=EntityArticulationInfoCfg(
                actuators=(
                    replace(
                        BRUSHLESS_ACTUATOR_CFG,
                        stiffness=stiffness,
                        damping=damping,
                        effort_limit=effort_limit,
                    ),
                    deepcopy(SERVO_ACTUATOR_CFG),
                )
            ),
        )
    )
    return entity, entity.compile()


def test_configs_cover_each_hinge_once_in_source_order():
    brushless, servo = BRUSHLESS_ACTUATOR_CFG, SERVO_ACTUATOR_CFG
    assert isinstance(brushless, HTDW3532ActuatorCfg)
    assert isinstance(servo, FrictionDRBamActuatorCfg)
    assert len(brushless.target_names_expr) == 12
    assert len(servo.target_names_expr) == 3
    targets = brushless.target_names_expr + servo.target_names_expr
    assert targets == JOINT_NAMES
    assert len(set(targets)) == len(targets)
    source_order = tuple(
        joint.name
        for joint in get_spec().joints
        if joint.type == mujoco.mjtJoint.mjJNT_HINGE
    )
    assert targets == source_order
    assert brushless.armature is None
    assert brushless.frictionloss is None
    assert brushless.viscous_damping is None
    assert 0 < brushless.effort_limit <= BRUSHLESS_MJCF_EFFORT_LIMIT
    assert servo.vin == 7.4
    assert servo.kp_fw == 32.0
    assert servo.effort_limit == 1.471
    assert servo.friction_scale_range is None
    for cfg in (brushless, servo):
        assert (
            cfg.delay_min_lag,
            cfg.delay_max_lag,
            cfg.delay_hold_prob,
            cfg.delay_update_period,
        ) == (0, 3, 0.4, 10)
        assert cfg.delay_per_env_phase


def test_entity_compiles_all_fifteen_actuators_and_preserves_brushless_xml(
    actuated_robot,
):
    _, model = actuated_robot
    assert model.nu == 15
    target_ids = model.actuator_trnid[:, 0]
    target_names = tuple(model.joint(int(i)).name for i in target_ids)
    assert target_names == JOINT_NAMES
    assert len(set(target_ids)) == 15
    np.testing.assert_array_equal(
        model.actuator_trntype, int(mujoco.mjtTrn.mjTRN_JOINT)
    )
    for name in BRUSHLESS_JOINT_NAMES:
        joint = model.joint(name)
        dof = int(joint.dofadr[0])
        np.testing.assert_allclose(
            model.jnt_actfrcrange[joint.id],
            [-BRUSHLESS_MJCF_EFFORT_LIMIT, BRUSHLESS_MJCF_EFFORT_LIMIT],
        )
        assert model.dof_damping[dof] == pytest.approx(0.02)
        assert model.dof_armature[dof] == pytest.approx(0.0)
        assert model.dof_frictionloss[dof] == pytest.approx(0.0)


def test_brushless_affine_nt_pd_matches_torque_law_and_separate_passive_damping(
    actuated_robot,
):
    entity, model = actuated_robot
    cfg = entity.cfg.articulation.actuators[0]
    data = mujoco.MjData(model)
    names = BRUSHLESS_JOINT_NAMES
    q_ids = [int(model.joint(name).qposadr[0]) for name in names]
    dof_ids = [int(model.joint(name).dofadr[0]) for name in names]
    # Cover unsaturated torque, both saturation signs, high-speed driving and
    # velocity braking. Vary all twelve channels to expose target misrouting.
    position = np.linspace(-0.05, 0.05, len(names))
    velocity = np.array([0.0, 0.1, -211.0 * 2 * np.pi / 60, 0.5] * 3)
    error = np.array([0.02, 3.0, -3.0, 0.0] * 3)
    data.qpos[q_ids] = position
    data.qvel[dof_ids] = velocity
    entity.indexing = entity._compute_indexing(model, "cpu")
    actuator = entity.actuators[0]
    bridge = SimpleNamespace(
        actuator_biasprm=torch.tensor(model.actuator_biasprm, dtype=torch.float32)[
            None
        ].clone(),
        actuator_forcerange=torch.tensor(
            model.actuator_forcerange, dtype=torch.float32
        )[None].clone(),
    )
    actuator.initialize(model, bridge, SimpleNamespace(nworld=1), "cpu")
    cmd = ActuatorCmd(
        position_target=torch.tensor(position + error, dtype=torch.float32)[None],
        velocity_target=torch.zeros((1, len(names)), dtype=torch.float32),
        effort_target=torch.zeros((1, len(names)), dtype=torch.float32),
        pos=torch.tensor(position, dtype=torch.float32)[None],
        vel=torch.tensor(velocity, dtype=torch.float32)[None],
    )
    request = cfg.stiffness * error - cfg.damping * velocity
    expected = np.clip(
        request,
        -cfg.effort_limit,
        cfg.effort_limit,
    )
    nt_cap = np.interp(
        np.abs(velocity) * 60 / (2 * np.pi),
        [0, 26, 59, 92, 128, 167, 211, 258, 300],
        [3.7, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0],
        right=0.0,
    )
    expected = np.where(
        request * velocity >= 0, np.clip(expected, -nt_cap, nt_cap), expected
    )
    control = actuator.compute(cmd)[0].numpy()
    np.testing.assert_allclose(
        control, cfg.stiffness * (position + error), atol=1e-7, rtol=1e-6
    )
    model.actuator_biasprm[:] = bridge.actuator_biasprm[0].numpy()
    model.actuator_forcerange[:] = bridge.actuator_forcerange[0].numpy()
    data.ctrl[actuator.global_ctrl_ids.numpy()] = control
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(
        data.actuator_force[: len(names)], expected, atol=1e-7, rtol=1e-6
    )
    np.testing.assert_allclose(
        data.qfrc_actuator[dof_ids], expected, atol=1e-7, rtol=1e-6
    )
    np.testing.assert_allclose(data.qfrc_passive[dof_ids], -0.02 * velocity)


def test_servo_model_overrides_passive_fields_and_old_xml_force_ceiling(
    actuated_robot,
):
    _, model = actuated_robot
    parameters = load_hd1910_parameters()
    for name in SERVO_JOINT_NAMES:
        joint = model.joint(name)
        dof = int(joint.dofadr[0])
        assert model.dof_armature[dof] == pytest.approx(parameters.armature)
        assert model.dof_damping[dof] == pytest.approx(parameters.friction_viscous)
        assert model.dof_frictionloss[dof] == pytest.approx(
            parameters.friction_base + parameters.friction_stribeck
        )
        assert model.jnt_actfrclimited[joint.id]
        np.testing.assert_allclose(model.jnt_actfrcrange[joint.id], [-1.471, 1.471])
    np.testing.assert_allclose(
        model.actuator_forcerange[-len(SERVO_JOINT_NAMES) :],
        [[-1.471, 1.471]] * len(SERVO_JOINT_NAMES),
    )


def test_entity_configuration_does_not_change_fresh_source_specs(actuated_robot):
    entity, _ = actuated_robot
    source = get_spec()
    second_source = get_spec()
    assert source is not second_source
    assert source is not entity.spec
    assert source.compile().nu == second_source.compile().nu == 0
    for name in JOINT_NAMES:
        joint = source.joint(name)
        assert joint.damping[0] == pytest.approx(0.02)
        assert joint.armature == pytest.approx(0.0)
        limit = BRUSHLESS_MJCF_EFFORT_LIMIT if name in BRUSHLESS_JOINT_NAMES else 1.47
        np.testing.assert_allclose(joint.actfrcrange, [-limit, limit])
