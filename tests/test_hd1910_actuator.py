"""CPU checks for the HD1910 electrical model, friction, and MuJoCo setup."""

import dataclasses
import json
import math
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest
import torch
from mjlab.actuator.actuator import TransmissionType

from ht_microduck.actuator.HD_1910_C001.bam_actuator import HD1910BamActuatorCfg
from ht_microduck.actuator.HD_1910_C001.friction_dr_bam import (
    FrictionDRBamActuator,
    FrictionDRBamActuatorCfg,
)
from ht_microduck.actuator.HD_1910_C001.model import (
    compute_friction_budget,
    compute_motor_torque,
    load_hd1910_parameters,
)

# Feetech's original 7.4 V M6 fit, pinned in the package's parameter provenance.
# These are a public model prior, not measurements of this project's servos.
FACTORY_PARAMETERS = {
    "kt": 0.5644993059031307,
    "R": 2.9664762312357853,
    "armature": 0.0018273861091867637,
    "q_offset": 0.008824155147854507,
    "command_delay": 0.0009781055842204172,
    "friction_base": 0.011950659296477161,
    "friction_stribeck": 0.0,
    "load_friction_motor": 0.3534653049182988,
    "load_friction_external": 0.04335300722280222,
    "load_friction_motor_stribeck": 1.6996676628765351e-06,
    "load_friction_external_stribeck": 0.14250972390583813,
    "load_friction_motor_quad": 0.006861907376104702,
    "load_friction_external_quad": 0.009999951209775423,
    "dtheta_stribeck": 0.716192604078371,
    "alpha": 4.248291402139783,
    "friction_viscous": 0.004767196924056633,
    "model": "m6",
    "actuator": "hd1910",
}


def write_parameters(tmp_path: Path, changes: dict | None = None) -> Path:
    payload = FACTORY_PARAMETERS | (changes or {})
    path = tmp_path / "parameters.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_packaged_parameters_preserve_factory_fit_and_are_immutable():
    parameters = load_hd1910_parameters()
    for name, value in FACTORY_PARAMETERS.items():
        if isinstance(value, (int, float)):
            assert getattr(parameters, name) == value
    with pytest.raises(dataclasses.FrozenInstanceError):
        parameters.R = 0.0


@pytest.mark.parametrize("alias", ["hd1910", "HD1910"])
def test_loader_accepts_explicit_hd1910_aliases(tmp_path, alias):
    parameters = load_hd1910_parameters(write_parameters(tmp_path, {"actuator": alias}))
    assert parameters.kt == FACTORY_PARAMETERS["kt"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "m5"),
        ("actuator", "xl330"),
        ("kt", 0.0),
        ("R", 0.0),
        ("dtheta_stribeck", 0.0),
        ("alpha", 0.0),
        ("armature", -0.01),
        ("friction_base", -0.01),
        ("friction_viscous", -0.01),
        ("load_friction_motor_quad", -0.01),
        ("command_delay", -0.001),
        ("kt", float("nan")),
        ("R", float("inf")),
        ("kt", "0.5"),
        ("kt", True),
    ],
)
def test_loader_rejects_invalid_models_and_parameter_domains(tmp_path, field, value):
    with pytest.raises(ValueError):
        load_hd1910_parameters(write_parameters(tmp_path, {field: value}))


def test_loader_requires_complete_json_and_reports_malformed_data(tmp_path):
    path = tmp_path / "parameters.json"
    payload = FACTORY_PARAMETERS.copy()
    del payload["R"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_hd1910_parameters(path)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        load_hd1910_parameters(path)


def test_loader_rejects_unknown_fields_instead_of_ignoring_configuration_typos(
    tmp_path,
):
    with pytest.raises(ValueError):
        load_hd1910_parameters(write_parameters(tmp_path, {"friction_bas": 0.1}))


def test_electrical_model_has_pwm_saturation_and_back_emf_braking():
    parameters = load_hd1910_parameters()
    errors = torch.tensor([0.0, 0.0, 0.0, 100.0, -100.0], dtype=torch.float64)
    velocity = torch.tensor([0.0, 2.0, -2.0, 0.0, 0.0], dtype=torch.float64)
    actual = compute_motor_torque(
        parameters, errors, velocity, torch.tensor(7.4, dtype=torch.float64)
    )
    # Zero PWM shorts the motor electrically, while saturated PWM is bounded
    # by the supply. Neither condition depends on a chosen PD derivative gain.
    damping = parameters.kt**2 / parameters.R
    stall = parameters.kt * 7.4 * 0.97 / parameters.R
    expected = torch.tensor(
        [0.0, -2.0 * damping, 2.0 * damping, stall, -stall],
        dtype=torch.float64,
    )
    torch.testing.assert_close(actual, expected, rtol=1e-13, atol=1e-14)


def test_unsaturated_electrical_gain_and_supply_broadcasting():
    parameters = load_hd1910_parameters()
    errors = torch.full((2, 3), 0.01, dtype=torch.float64)
    velocity = torch.zeros_like(errors)
    supply = torch.tensor([[7.4], [6.8]], dtype=torch.float64)
    actual = compute_motor_torque(parameters, errors, velocity, supply, kp_fw=32.0)
    expected = (parameters.kt / parameters.R) * (0.01 * 32.0 * 0.163) * supply
    torch.testing.assert_close(
        actual, expected.expand_as(actual), rtol=1e-13, atol=1e-14
    )
    assert actual.shape == (2, 3)
    assert actual.dtype == torch.float64


@pytest.mark.parametrize("kp_fw", [-1.0, math.nan, math.inf])
def test_electrical_model_rejects_invalid_firmware_gains(kp_fw):
    zero = torch.tensor(0.0)
    with pytest.raises(ValueError):
        compute_motor_torque(load_hd1910_parameters(), zero, zero, zero, kp_fw=kp_fw)


@pytest.fixture
def simple_friction_parameters():
    return dataclasses.replace(
        load_hd1910_parameters(),
        friction_base=1.0,
        friction_stribeck=2.0,
        load_friction_motor=0.1,
        load_friction_external=0.2,
        load_friction_motor_stribeck=0.3,
        load_friction_external_stribeck=0.4,
        load_friction_motor_quad=0.5,
        load_friction_external_quad=0.7,
        dtheta_stribeck=1.0,
        alpha=2.0,
        friction_viscous=0.9,
    )


@pytest.mark.parametrize(
    ("motor", "external", "expected"),
    [
        (4.0, -2.0, 8.6),  # motor driving: external-side quadratic coefficient
        (2.0, -4.0, 8.2),  # backdriving: motor-side quadratic coefficient
        (4.0, 2.0, 3.4),  # same sign: quadratic contribution is disabled
        (4.0, -4.0, 7.0),  # equal magnitude: neither quadratic branch applies
        (0.0, 0.0, 3.0),
    ],
)
def test_m6_directional_load_friction_at_rest(
    simple_friction_parameters, motor, external, expected
):
    actual = compute_friction_budget(
        simple_friction_parameters,
        torch.tensor(motor, dtype=torch.float64),
        torch.tensor(external, dtype=torch.float64),
        torch.tensor(0.0, dtype=torch.float64),
    )
    assert actual.item() == pytest.approx(expected, rel=1e-13, abs=1e-14)


def test_stribeck_transition_is_even_and_budget_excludes_viscous_damping(
    simple_friction_parameters,
):
    velocities = torch.tensor([1.0, -1.0, 100.0], dtype=torch.float64)
    actual = compute_friction_budget(
        simple_friction_parameters,
        torch.tensor(4.0, dtype=torch.float64),
        torch.tensor(-2.0, dtype=torch.float64),
        velocities,
    )
    # At |dq|=dtheta, Stribeck is exp(-1). At high speed only the base
    # and directional load terms remain; viscous damping is configured apart.
    expected = torch.tensor([1.8 + 6.8 / math.e] * 2 + [1.8], dtype=torch.float64)
    torch.testing.assert_close(actual, expected, rtol=1e-13, atol=1e-14)


def hinge_spec(joint_type="hinge"):
    return mujoco.MjSpec.from_string(
        f"""<mujoco>
          <worldbody><body>
            <joint name="joint" type="{joint_type}" damping="0.02"
                   frictionloss="0.07" armature="0.03"
                   actuatorfrclimited="true" actuatorfrcrange="-0.2 0.2"/>
            <geom type="sphere" size="0.02" mass="1"/>
          </body></worldbody>
        </mujoco>"""
    )


def test_edit_spec_uses_fitted_passive_terms_and_one_motor_with_explicit_limit():
    cfg = HD1910BamActuatorCfg(target_names_expr=("joint",), effort_limit=0.7)
    actuator = cfg.build(SimpleNamespace(), [0], ["joint"])
    spec = hinge_spec()
    actuator.edit_spec(spec, ["joint"])
    model = spec.compile()
    assert model.nu == 1
    np.testing.assert_allclose(model.dof_armature, [FACTORY_PARAMETERS["armature"]])
    np.testing.assert_allclose(
        model.dof_damping, [FACTORY_PARAMETERS["friction_viscous"]]
    )
    np.testing.assert_allclose(
        model.dof_frictionloss, [FACTORY_PARAMETERS["friction_base"]]
    )
    np.testing.assert_allclose(model.jnt_actfrcrange, [[-0.7, 0.7]])
    np.testing.assert_allclose(model.actuator_forcerange, [[-0.7, 0.7]])
    np.testing.assert_allclose(model.actuator_gear[0], [1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert model.actuator_trntype[0] == mujoco.mjtTrn.mjTRN_JOINT
    assert model.actuator_trnid[0, 0] == 0


def test_armature_override_is_deliberate_and_does_not_modify_parameter_prior():
    cfg = HD1910BamActuatorCfg(target_names_expr=("joint",), armature=0.005)
    actuator = cfg.build(SimpleNamespace(), [0], ["joint"])
    spec = hinge_spec()
    actuator.edit_spec(spec, ["joint"])
    assert spec.compile().dof_armature[0] == pytest.approx(0.005)
    assert actuator.parameters.armature == FACTORY_PARAMETERS["armature"]


@pytest.mark.parametrize("joint_type", ["slide", "ball", "free"])
def test_edit_spec_rejects_unsupported_joint_types(joint_type):
    actuator = HD1910BamActuatorCfg(target_names_expr=("joint",)).build(
        SimpleNamespace(), [0], ["joint"]
    )
    with pytest.raises(ValueError):
        actuator.edit_spec(hinge_spec(joint_type), ["joint"])


def test_edit_spec_rejects_double_actuation():
    actuator = HD1910BamActuatorCfg(target_names_expr=("joint",)).build(
        SimpleNamespace(), [0], ["joint"]
    )
    spec = hinge_spec()
    spec.add_actuator(
        name="existing", target="joint", trntype=mujoco.mjtTrn.mjTRN_JOINT
    )
    with pytest.raises(ValueError):
        actuator.edit_spec(spec, ["joint"])


@pytest.mark.parametrize(
    "changes",
    [
        {"vin": 0.0},
        {"vin": 8.5},
        {"vin": float("nan")},
        {"kp_fw": -1.0},
        {"kp_fw": float("inf")},
        {"effort_limit": 0.0},
        {"effort_limit": float("nan")},
        {"frictionloss": 0.1},
        {"viscous_damping": 0.1},
        {"transmission_type": TransmissionType.TENDON},
        {"transmission_type": TransmissionType.SITE},
    ],
)
def test_cfg_rejects_invalid_domains_and_model_owned_overrides(changes):
    with pytest.raises(ValueError):
        HD1910BamActuatorCfg(target_names_expr=("joint",), **changes)


@pytest.mark.parametrize(
    "scale_range", [(-1.0, 1.0), (2.0, 1.0), (1.0, math.inf), (math.nan, 1.0)]
)
def test_friction_dr_cfg_rejects_invalid_scale_ranges(scale_range):
    with pytest.raises(ValueError):
        FrictionDRBamActuatorCfg(
            target_names_expr=("joint",), friction_scale_range=scale_range
        )


def test_friction_dr_cfg_allows_explicit_zero_friction_ablation():
    cfg = FrictionDRBamActuatorCfg(
        target_names_expr=("joint",), friction_scale_range=(0.0, 0.0)
    )
    assert cfg.friction_scale_range == (0.0, 0.0)


def test_friction_dr_builds_the_custom_class_with_randomization_disabled_by_default():
    cfg = FrictionDRBamActuatorCfg(target_names_expr=("joint",))
    assert cfg.friction_scale_range is None
    assert isinstance(
        cfg.build(SimpleNamespace(), [0], ["joint"]), FrictionDRBamActuator
    )
