"""Run a short HD1910 integration check on three independent MuJoCo hinges.

Run from the repository root with ``uv run --no-sync python tools/check_hd1910.py``.
The fixture has no gravity or contacts; it checks the actuator integration rather
than the robot's balance or the accuracy of the manufacturer's identification.
"""

from __future__ import annotations

import argparse

import mujoco
import torch
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.scene import Scene, SceneCfg
from mjlab.sim import MujocoCfg, Simulation, SimulationCfg

from ht_microduck.actuators.HD_1910_C001.friction_dr_bam import (
    FrictionDRBamActuator,
    FrictionDRBamActuatorCfg,
)
from ht_microduck.actuators.HD_1910_C001.model import compute_friction_budget

_JOINT_NAMES = ("servo_0", "servo_1", "servo_2")
_EFFORT_LIMIT = 0.35
_TIMESTEP = 0.002


def _fixture_spec() -> mujoco.MjSpec:
    """Keep the loads small and uncoupled so the checks have clear outcomes."""
    links = "".join(
        f'<body name="link_{index}" pos="{index * 0.12} 0 0">'
        f'<joint name="{name}" axis="0 0 1" range="-1.5 1.5" '
        'damping="0.02" actuatorfrclimited="true" '
        'actuatorfrcrange="-0.1 0.1"/>'
        '<geom type="box" size="0.04 0.01 0.01" pos="0.04 0 0" '
        'mass="0.05" contype="0" conaffinity="0"/>'
        "</body>"
        for index, name in enumerate(_JOINT_NAMES)
    )
    return mujoco.MjSpec.from_string(
        '<mujoco model="hd1910_integration_probe">'
        '<compiler angle="radian"/>'
        '<worldbody><body name="base">'
        '<geom type="box" size="0.01 0.01 0.01" mass="0.1" '
        'contype="0" conaffinity="0"/>'
        f"{links}</body></worldbody></mujoco>"
    )


def _check_close(actual: torch.Tensor, expected: torch.Tensor, label: str) -> None:
    try:
        torch.testing.assert_close(actual, expected, rtol=2e-5, atol=2e-6)
    except AssertionError as error:
        raise AssertionError(f"{label}: {error}") from error


def _check_delay_and_partial_reset(
    scene: Scene, actuator: FrictionDRBamActuator
) -> None:
    entity = scene["servo_fixture"]
    device = entity.data.joint_pos.device
    shape = entity.data.joint_pos.shape
    # These small targets are in the controller's linear, unsaturated region.
    parameters = actuator.parameters
    coefficient = parameters.kt / parameters.R * 7.4 * 0.163 * 32.0
    for target, delayed_target in (
        (0.0, 0.0),
        (0.005, 0.0),
        (0.010, 0.0),
        (0.015, 0.005),
    ):
        entity.set_joint_position_target(torch.full(shape, target, device=device))
        scene.write_data_to_sim()
        expected = torch.full(shape, delayed_target * coefficient, device=device)
        _check_close(actuator.last_motor_torque, expected, "two-step command delay")

    selected = torch.tensor([0], device=device)
    untouched = slice(1, None)
    previous_torque = actuator.last_motor_torque[untouched].clone()
    previous_budget = actuator.last_friction_budget[untouched].clone()
    previous_scale = actuator.friction_scale[untouched].clone()
    entity.reset(selected)
    _check_close(
        actuator.last_motor_torque[untouched],
        previous_torque,
        "partial reset changed another environment's torque history",
    )
    _check_close(
        actuator.last_friction_budget[untouched],
        previous_budget,
        "partial reset changed another environment's friction history",
    )
    _check_close(
        actuator.friction_scale[untouched],
        previous_scale,
        "partial reset changed another environment's friction scale",
    )
    if actuator._load_valid[0].any() or not actuator._load_valid[untouched].all():
        raise AssertionError("Partial reset did not isolate the previous-load state.")
    if not torch.all(
        (actuator.friction_scale[0] >= 0.8) & (actuator.friction_scale[0] <= 1.2)
    ):
        raise AssertionError("Reset friction sample is outside the configured range.")

    # mjlab backfills a reset row with its first new command. Other rows retain
    # their existing two-step command history.
    entity.set_joint_position_target(torch.full(shape, 0.020, device=device))
    scene.write_data_to_sim()
    expected = torch.full(shape, 0.010 * coefficient, device=device)
    expected[0] = 0.020 * coefficient
    _check_close(actuator.last_motor_torque, expected, "partial reset delay history")


def _check_friction_scaling(scene: Scene, actuator: FrictionDRBamActuator) -> None:
    entity = scene["servo_fixture"]
    entity.reset()
    device = entity.data.joint_pos.device
    count = entity.data.joint_pos.shape[0]
    scales = torch.linspace(0.8, 1.2, count, device=device).unsqueeze(1)
    actuator.set_friction_scale(None, scales)
    entity.set_joint_position_target(torch.zeros_like(entity.data.joint_pos))
    scene.write_data_to_sim()
    budget = actuator.last_friction_budget
    unscaled = budget / scales
    _check_close(
        unscaled,
        unscaled[:1].expand_as(unscaled),
        "friction scale must be applied exactly once",
    )
    if not torch.all(budget > 0):
        raise AssertionError(
            "The manufacturer model should have positive dry friction."
        )
    dof_ids = entity.indexing.joint_v_adr
    field = entity.data.model.dof_frictionloss[...]
    _check_close(field[:, dof_ids], budget, "per-world friction model writes")
    if field.stride(0) == 0:
        raise AssertionError("Friction storage still aliases across environments.")
    damping = entity.data.model.dof_damping[...]
    if damping.stride(0) == 0:
        raise AssertionError("Damping storage still aliases across environments.")
    if not torch.isfinite(damping[:, dof_ids]).all():
        raise AssertionError("BAM wrote non-finite passive damping.")
    actuator.reset_friction_scale(None)
    _check_close(
        actuator.friction_scale,
        torch.ones_like(scales),
        "restore default friction scale",
    )


def _check_external_load_and_reset(
    scene: Scene, sim: Simulation, actuator: FrictionDRBamActuator
) -> None:
    entity = scene["servo_fixture"]
    sim.reset()
    scene.reset()
    actuator.reset_friction_scale()
    sim.forward()
    dof_ids = entity.indexing.joint_v_adr
    applied_load = torch.full_like(entity.data.joint_pos, 0.1)
    sim.data.qfrc_applied[:, dof_ids] = applied_load
    entity.set_joint_position_target(torch.zeros_like(entity.data.joint_pos))
    scene.write_data_to_sim()
    sim.step()
    scene.update(_TIMESTEP)
    previous_motor_load = sim.data.qfrc_actuator[:, dof_ids].clone()
    expected = compute_friction_budget(
        actuator.parameters,
        previous_motor_load,
        applied_load,
        entity.data.joint_vel,
    )
    scene.write_data_to_sim()
    _check_close(
        actuator.last_friction_budget,
        expected,
        "external generalized load must enter the friction budget",
    )

    # Keep the old solved loads in sim.data deliberately. Multiple writes after
    # an entity reset must ignore them until a new physics step has completed.
    selected = torch.tensor([0], device=entity.data.joint_pos.device)
    entity.reset(selected)
    actuator.set_friction_scale(selected, 1.0)
    zero_loads = torch.zeros_like(previous_motor_load[:1])
    reset_budget = compute_friction_budget(
        actuator.parameters, zero_loads, zero_loads, entity.data.joint_vel[:1]
    )
    for _ in range(2):
        scene.write_data_to_sim()
        _check_close(
            actuator.last_friction_budget[:1],
            reset_budget,
            "reset row reused stale loads before a physics update",
        )
        _check_close(
            actuator.last_friction_budget[1:],
            expected[1:],
            "reset row changed another environment's load estimate",
        )
        if actuator._load_valid[0].any() or not actuator._load_valid[1:].all():
            raise AssertionError("Control writes incorrectly validated old solve loads.")
    sim.data.qfrc_applied[:, dof_ids] = 0.0


def _check_response(
    scene: Scene, sim: Simulation, actuator: FrictionDRBamActuator, steps: int
) -> tuple[float, float]:
    entity = scene["servo_fixture"]
    sim.reset()
    scene.reset()
    actuator.set_friction_scale(None, torch.ones_like(actuator.friction_scale))
    sim.forward()
    target = torch.full_like(entity.data.joint_pos, 0.2)
    entity.set_joint_position_target(target)
    maximum_effort = 0.0
    for _ in range(steps):
        scene.write_data_to_sim()
        sim.step()
        scene.update(_TIMESTEP)
        if not (
            torch.isfinite(entity.data.joint_pos).all()
            and torch.isfinite(entity.data.joint_vel).all()
            and torch.isfinite(actuator.last_motor_torque).all()
        ):
            raise AssertionError("Non-finite state during the target response.")
        effort = sim.data.qfrc_actuator[..., entity.indexing.joint_v_adr]
        maximum_effort = max(maximum_effort, float(effort.abs().max()))
    if maximum_effort > _EFFORT_LIMIT + 1e-5:
        raise AssertionError(
            f"Applied torque exceeded {_EFFORT_LIMIT}: {maximum_effort}"
        )
    error = float((entity.data.joint_pos - target).abs().max())
    speed = float(entity.data.joint_vel.abs().max())
    if error > 0.06 or speed > 0.5:
        raise AssertionError(f"Target did not settle: error={error}, speed={speed}")
    if maximum_effort < _EFFORT_LIMIT - 1e-4:
        raise AssertionError("The response never exercised the configured torque cap.")
    return error, maximum_effort


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=4)
    parser.add_argument("--steps", type=int, default=300)
    args = parser.parse_args()
    if args.num_envs < 2 or args.steps < 300:
        parser.error("Use at least two environments and 300 physics steps.")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("The requested CUDA device is unavailable.")
    torch.manual_seed(1910)
    actuator_cfg = FrictionDRBamActuatorCfg(
        target_names_expr=_JOINT_NAMES,
        vin=7.4,
        kp_fw=32.0,
        effort_limit=_EFFORT_LIMIT,
        delay_min_lag=2,
        delay_max_lag=2,
        friction_scale_range=(0.8, 1.2),
    )
    scene = Scene(
        SceneCfg(
            num_envs=args.num_envs,
            entities={
                "servo_fixture": EntityCfg(
                    spec_fn=_fixture_spec,
                    articulation=EntityArticulationInfoCfg(actuators=(actuator_cfg,)),
                )
            },
        ),
        device=args.device,
    )
    sim = Simulation(
        args.num_envs,
        SimulationCfg(
            mujoco=MujocoCfg(
                timestep=_TIMESTEP,
                gravity=(0.0, 0.0, 0.0),
            )
        ),
        model=scene.compile(),
        device=args.device,
    )
    scene.initialize(sim.mj_model, sim.model, sim.data)
    try:
        scene.write_data_to_sim()
    except RuntimeError as error:
        if "expand_model_fields" not in str(error):
            raise
    else:
        raise AssertionError("Unexpanded per-world friction fields were accepted.")
    # Match mjlab's manager lifecycle: initialize entities first, then expand
    # model arrays when event requirements are discovered.
    sim.expand_model_fields(("dof_frictionloss", "dof_damping"))
    actuator = scene["servo_fixture"].actuators[0]
    if not isinstance(actuator, FrictionDRBamActuator):
        raise AssertionError("The custom actuator was not constructed.")
    if not (sim.mj_model.jnt_actfrcrange == (-_EFFORT_LIMIT, _EFFORT_LIMIT)).all():
        raise AssertionError("The original XML joint torque limit was not updated.")
    sim.reset()
    scene.reset()
    sim.forward()
    scene.write_data_to_sim()
    sim.step()
    scene.update(_TIMESTEP)
    _check_delay_and_partial_reset(scene, actuator)
    _check_external_load_and_reset(scene, sim, actuator)
    _check_friction_scaling(scene, actuator)
    error, effort = _check_response(scene, sim, actuator, args.steps)
    if args.device.startswith("cuda"):
        torch.cuda.synchronize(args.device)
    print(
        f"HD1910 integration passed: device={args.device}, envs={args.num_envs}, "
        f"joints=3, steps={args.steps}, dt={_TIMESTEP}s, "
        f"max_target_error={error:.6f}rad, max_applied_torque={effort:.6f}Nm."
    )
    print(
        "Verified: unexpanded-field guard, 2-step delay, partial reset, "
        "external generalized loads, stale-load reset guard, per-world "
        "friction/damping, single friction scaling, torque cap, finite "
        "step/hold response."
    )


if __name__ == "__main__":
    main()
