"""Check the actual floating-base robot in a small mjlab plane scene.

The gains, limits and 0.002 s timestep below are explicit smoke-test assumptions,
not identified hardware parameters or a tuned standing controller. This check
covers scene wiring, contacts and resets; it does not measure standing ability.
"""

from __future__ import annotations

import argparse

import mujoco
import torch
from mjlab.scene import Scene, SceneCfg
from mjlab.sensor import BuiltinSensor, ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, Simulation, SimulationCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.actuator.HD_1910_C001.model import compute_motor_torque
from ht_microduck.actuator.HTDW_3532_02_DNE.model import clip_nt_torque
from ht_microduck.robot.ht_microduck_constants import (
    BRUSHLESS_JOINT_NAMES,
    JOINT_NAMES,
    SERVO_JOINT_NAMES,
    get_ht_microduck_robot_cfg,
)

# Sensor names declared in the robot XML; the scene prefixes them with "robot/".
_IMU_SENSORS = (
    "imu_ang_vel",
    "imu_lin_vel",
    "imu_accel",
    "imu_upvector",
    "root_angmom",
)

_DT = 0.002
_ROBOT = "robot"
_CONTACT = "feet_ground"


def _close(actual: torch.Tensor, expected: torch.Tensor, label: str) -> None:
    try:
        torch.testing.assert_close(actual, expected, rtol=2e-5, atol=2e-6)
    except AssertionError as error:
        raise AssertionError(f"{label}: {error}") from error


def _reset(scene: Scene, sim: Simulation, env_ids: torch.Tensor | None = None) -> None:
    """Restore physical state and targets; Scene.reset alone only clears targets."""
    ids = slice(None) if env_ids is None else env_ids
    robot = scene[_ROBOT]
    sim.reset(env_ids)
    scene.reset(env_ids)
    root = robot.data.default_root_state[ids].clone()
    root[:, :3] += scene.env_origins[ids]
    robot.write_root_state_to_sim(root, env_ids=env_ids)
    robot.write_joint_state_to_sim(
        robot.data.default_joint_pos[ids],
        robot.data.default_joint_vel[ids],
        env_ids=env_ids,
    )
    robot.set_joint_position_target(robot.data.default_joint_pos[ids], env_ids=env_ids)
    # Do not call scene.update(0): actuator.update means a physics step completed.
    sim.forward()


def _check_reset_state(scene: Scene, sim: Simulation, ids: torch.Tensor) -> None:
    robot = scene[_ROBOT]
    root = robot.data.default_root_state[ids].clone()
    root[:, :3] += scene.env_origins[ids]
    _close(robot.data.root_link_pose_w[ids], root[:, :7], "reset root pose")
    _close(robot.data.root_link_vel_w[ids], root[:, 7:], "reset root velocity")
    _close(robot.data.joint_pos[ids], robot.data.default_joint_pos[ids], "reset joints")
    _close(robot.data.joint_vel[ids], robot.data.default_joint_vel[ids], "reset speeds")
    _close(
        robot.data.joint_pos_target[ids],
        robot.data.default_joint_pos[ids],
        "reset position targets",
    )
    if robot.data.joint_pos.shape != (scene.num_envs, len(JOINT_NAMES)):
        raise AssertionError("Unexpected joint state dimensions.")
    if robot.data.root_link_pose_w.shape != (scene.num_envs, 7):
        raise AssertionError("Unexpected root pose dimensions.")
    if sim.data.qpos.shape != (scene.num_envs, 22):
        raise AssertionError("Unexpected floating-base qpos dimensions.")


def _check_command_mapping(scene: Scene, sim: Simulation) -> None:
    robot = scene[_ROBOT]
    target = robot.data.default_joint_pos.clone()
    target += torch.linspace(0.0002, 0.003, len(JOINT_NAMES), device=sim.device)
    target[1::2, :-1] -= 0.001
    robot.set_joint_position_target(target)
    # First post-reset append backfills each delay history with this target.
    scene.write_data_to_sim()
    brushless, servo = robot.actuators
    _close(
        sim.data.ctrl[:, brushless.global_ctrl_ids],
        brushless.stiffness * target[:, brushless.target_ids],
        "brushless affine command routing",
    )
    sim.forward()
    _close(
        sim.data.qfrc_actuator[:, robot.indexing.joint_v_adr[brushless.target_ids]],
        clip_nt_torque(
            brushless.stiffness
            * (
                target[:, brushless.target_ids]
                - robot.data.joint_pos[:, brushless.target_ids]
            )
            - brushless.damping * robot.data.joint_vel[:, brushless.target_ids],
            robot.data.joint_vel[:, brushless.target_ids],
            brushless.force_limit,
            brushless.parameters,
        ),
        "brushless native PD force routing",
    )
    expected = compute_motor_torque(
        servo.parameters,
        target[:, servo.target_ids] - robot.data.joint_pos[:, servo.target_ids],
        robot.data.joint_vel[:, servo.target_ids],
        torch.full_like(target[:, :1], servo.cfg.vin),
        servo.cfg.kp_fw,
    ).clamp(-servo.cfg.effort_limit, servo.cfg.effort_limit)
    _close(servo.last_motor_torque, expected, "BAM command routing")
    _close(sim.data.ctrl[:, servo.global_ctrl_ids], expected, "BAM control routing")


def _check_imu_sensors(
    scene: Scene, sim: Simulation, mj_model: mujoco.MjModel
) -> None:
    """Verify the entity XML IMU sensors reach the scene as usable tensors.

    Called after stepping: the root angular rate must be nonzero for the gyro
    comparison to mean anything (right after reset both sides are exactly zero).
    """
    expected = {f"{_ROBOT}/{name}" for name in _IMU_SENSORS}
    present = {name for name in expected if name in scene.sensors}
    if present != expected:
        raise AssertionError(f"Scene is missing IMU sensors: {expected - present}.")
    site = mj_model.site(f"{_ROBOT}/imu")
    if mj_model.body(int(site.bodyid[0])).name != f"{_ROBOT}/base_link":
        raise AssertionError("IMU site is not attached to the root body.")
    readings: dict[str, torch.Tensor] = {}
    for name in _IMU_SENSORS:
        sensor = scene[f"{_ROBOT}/{name}"]
        if not isinstance(sensor, BuiltinSensor):
            raise AssertionError(f"{name} is not a builtin sensor wrapper.")
        value = sensor.data
        if value.shape != (scene.num_envs, 3):
            raise AssertionError(f"Unexpected {name} dimensions: {tuple(value.shape)}.")
        if not torch.isfinite(value).all():
            raise AssertionError(f"Non-finite {name} reading.")
        readings[name] = value
    # The up vector is a unit vector: an easy end-to-end check that the site
    # frame and world reference were both resolved in every world.
    norm = readings["imu_upvector"].norm(dim=-1)
    if not torch.allclose(norm, torch.ones_like(norm), atol=1e-5):
        raise AssertionError(f"IMU up vector is not unit length: {norm}.")
    # The site sits at the root origin with identity attitude, so the gyro must
    # reproduce the root body-frame rate. Require a nonzero rate first, otherwise
    # a mis-wired gyro would pass this check trivially.
    robot = scene[_ROBOT]
    root_rate = robot.data.root_link_ang_vel_b
    if root_rate.abs().max() < 1e-3:
        raise AssertionError(
            "Root angular rate is ~0; the gyro comparison would be vacuous."
        )
    _close(readings["imu_ang_vel"], root_rate, "gyro vs root rate")
    # -up is the projected-gravity direction the actor observation will consume.
    _close(-readings["imu_upvector"], robot.data.projected_gravity_b, "up vs gravity")


def _check_partial_reset(scene: Scene, sim: Simulation) -> None:
    robot = scene[_ROBOT]
    selected = torch.tensor([0, scene.num_envs - 1], device=sim.device)
    keep = torch.arange(1, scene.num_envs - 1, device=sim.device)
    before = {
        "qpos": sim.data.qpos[keep].clone(),
        "qvel": sim.data.qvel[keep].clone(),
        "ctrl": sim.data.ctrl[keep].clone(),
        "time": sim.data.time[keep].clone(),
        "targets": robot.data.joint_pos_target[keep].clone(),
        "motor": robot.actuators[1].last_motor_torque[keep].clone(),
    }
    _reset(scene, sim, selected)
    _check_reset_state(scene, sim, selected)
    for name in ("qpos", "qvel", "ctrl", "time"):
        _close(getattr(sim.data, name)[keep], before[name], f"partial reset {name}")
    _close(robot.data.joint_pos_target[keep], before["targets"], "other targets")
    _close(
        robot.actuators[1].last_motor_torque[keep], before["motor"], "other BAM state"
    )
    if robot.actuators[1]._load_valid[selected].any():
        raise AssertionError("Partial reset retained stale BAM load history.")


def _step(scene: Scene, sim: Simulation) -> None:
    scene.write_data_to_sim()
    sim.step()
    scene.update(_DT)
    # A finite but oscillating explicit controller used to pass this fixture.
    # This bound belongs to the short neutral-hold test, not the motor model.
    if scene[_ROBOT].data.joint_vel.abs().max() > 2.0:
        raise AssertionError(
            "Neutral-hold joint speed exceeded 2 rad/s; check PD integration."
        )
    for name in ("qpos", "qvel", "qacc", "ctrl", "actuator_force", "sensordata"):
        if not torch.isfinite(getattr(sim.data, name)).all():
            raise AssertionError(f"Non-finite {name} in whole-robot scene.")
    if sim.data.overflow.any():
        raise AssertionError("Simulation contact or constraint capacity exceeded.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-envs", type=int, default=4)
    parser.add_argument("--steps", type=int, default=150)
    args = parser.parse_args()
    if args.num_envs < 3 or args.steps < 50:
        parser.error("Use at least three environments and 50 physics steps.")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("The requested CUDA device is unavailable.")
    torch.manual_seed(1910)
    # A small custom neck offset exercises a nonzero configured reset target.
    # The neutral feet/root pose is unchanged; this is a test pose, not hardware data.
    robot_cfg = get_ht_microduck_robot_cfg()
    robot_cfg.init_state.joint_pos["neck_pitch_joint"] = 0.03
    scene = Scene(
        SceneCfg(
            num_envs=args.num_envs,
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={_ROBOT: robot_cfg},
            sensors=(
                ContactSensorCfg(
                    name=_CONTACT,
                    primary=ContactMatch(
                        mode="geom", pattern=r"[rl]_foot_collision", entity=_ROBOT
                    ),
                    secondary=ContactMatch(mode="geom", pattern="terrain"),
                    fields=("found", "force"),
                    reduce="netforce",
                    num_slots=1,
                ),
            ),
        ),
        device=args.device,
    )
    model = scene.compile()
    planes = [
        model.geom(i).name
        for i in range(model.ngeom)
        if model.geom_type[i] == mujoco.mjtGeom.mjGEOM_PLANE
    ]
    if planes != ["terrain"] or model.nlight != 1 or model.nu != len(JOINT_NAMES):
        raise AssertionError(
            f"Unexpected scene topology: planes={planes}, nu={model.nu}."
        )
    sim = Simulation(
        args.num_envs,
        SimulationCfg(nconmax=128, njmax=512, mujoco=MujocoCfg(timestep=_DT)),
        model=model,
        device=args.device,
    )
    scene.initialize(sim.mj_model, sim.model, sim.data)
    sim.expand_model_fields(
        ("dof_frictionloss", "dof_damping", "actuator_forcerange", "actuator_biasprm")
    )
    robot = scene[_ROBOT]
    if tuple(robot.joint_names) != JOINT_NAMES or tuple(
        tuple(act.target_names) for act in robot.actuators
    ) != (BRUSHLESS_JOINT_NAMES, SERVO_JOINT_NAMES):
        raise AssertionError("Whole-robot actuator mapping differs from constants.")
    if any(
        getattr(sim.model, name).stride(0) == 0
        for name in ("dof_frictionloss", "dof_damping")
    ):
        raise AssertionError("BAM model fields alias across worlds.")
    _reset(scene, sim)
    _check_reset_state(scene, sim, torch.arange(args.num_envs, device=args.device))
    _check_command_mapping(scene, sim)
    for _ in range(12):
        _step(scene, sim)
    # Step first: right after reset the root rate is zero in every world, which
    # would let a mis-wired gyro pass the comparison below.
    _check_imu_sensors(scene, sim, sim.mj_model)
    _check_partial_reset(scene, sim)
    _reset(scene, sim)
    sensor = scene[_CONTACT]
    names = tuple(name.removeprefix("robot/") for name in sensor.primary_names)
    if set(names) != {"r_foot_collision", "l_foot_collision"}:
        raise AssertionError(f"Unexpected foot sensor mapping: {names}.")
    seen = torch.zeros((args.num_envs, 2), dtype=torch.bool, device=args.device)
    peak_effort = torch.zeros(len(JOINT_NAMES), device=args.device)
    peak_speed = torch.zeros((), device=args.device)
    for _ in range(args.steps):
        _step(scene, sim)
        contact = sensor.data
        if contact.found.shape != (args.num_envs, 2) or contact.force.shape != (
            args.num_envs,
            2,
            3,
        ):
            raise AssertionError("Unexpected contact tensor dimensions.")
        if not torch.isfinite(contact.force).all():
            raise AssertionError("Non-finite ground-contact forces.")
        seen |= (contact.found > 0) & (contact.force.norm(dim=-1) > 0)
        peak_effort = torch.maximum(
            peak_effort, sim.data.actuator_force.abs().amax(dim=0)
        )
        peak_speed = torch.maximum(peak_speed, robot.data.joint_vel.abs().max())
    if not seen.all():
        raise AssertionError(
            f"Not every foot in every world contacted terrain: {seen}."
        )
    limits = torch.tensor(
        [robot.actuators[0].cfg.effort_limit] * len(BRUSHLESS_JOINT_NAMES)
        + [robot.actuators[1].cfg.effort_limit] * len(SERVO_JOINT_NAMES),
        device=args.device,
    )
    if (peak_effort > limits + 1e-5).any():
        raise AssertionError(f"Actuator force caps exceeded: {peak_effort}.")
    if args.device.startswith("cuda"):
        torch.cuda.synchronize(args.device)
    height = sim.data.qpos[:, 2] - scene.env_origins[:, 2]
    # The guard is relative to HOME because the crouched stance is ~1.3 cm lower
    # than a straight-legged one; an absolute threshold would either be vacuous
    # for the old pose or trip on a healthy crouch.
    home_height = float(robot.data.default_root_state[0, 2])
    if height.min() < 0.9 * home_height:
        raise AssertionError(
            "Short neutral-hold root dropped below the HOME-relative guard: "
            f"{float(height.min()):.6f} m vs HOME {home_height:.6f} m."
        )
    print(
        f"Whole robot scene passed: device={args.device}, envs={args.num_envs}, "
        f"steps={args.steps}, dt={_DT}s, joints=12+3, planes=1, "
        f"foot_contacts={names}, root_height=[{float(height.min()):.6f}, "
        f"{float(height.max()):.6f}]m, peak_effort={float(peak_effort.max()):.6f}Nm, "
        f"peak_joint_speed={float(peak_speed):.6f}rad/s."
    )
    print(
        "Verified: explicit state/target reset, partial reset isolation, control mapping, "
        "independent BAM fields, both foot contacts, finite state and force caps, "
        f"IMU sensors={len(_IMU_SENSORS)}."
    )
    print(
        "Test pose/gains/timestep are simulation assumptions. "
        "This does not establish stable standing or calibrated hardware behavior."
    )


if __name__ == "__main__":
    main()
