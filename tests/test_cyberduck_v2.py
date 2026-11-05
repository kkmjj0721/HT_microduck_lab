# Copyright (c) 2026-2027 zh
"""
内容：
    验证 CyberDuck V2 资源、混合驱动实体及滚轮软约束，另提供显式运行时检查。

用法：
    make test
    uv run --no-sync python -B tests/test_cyberduck_v2.py --device cpu
    uv run --no-sync python -B tests/test_cyberduck_v2.py --device cuda:0

    专项运行使用 3 个环境、100 个物理步，检查 13 路位置和 2 路速度目标、NT/BAM 限幅、延迟和局部重置；
    不运行策略训练。直接运行前按项目规范设置项目内 TMPDIR 及 Warp/Torch 缓存。
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import mujoco
import numpy as np
import pytest
from mjlab.entity import Entity
from mjlab.scene import Scene, SceneCfg
from mjlab.sim import MujocoCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.actuator import FrictionDRBamActuatorCfg, HTDW3532ActuatorCfg
from ht_microduck.robot import cyberduck_v2_constants as robot


# ---------- 源资源与实体回归 ----------
@pytest.fixture(scope="module")
def source_model():
    return robot.get_spec().compile()


@pytest.fixture(scope="module")
def entity_model():
    return Entity(robot.get_cyberduck_v2_robot_cfg()).compile()


def test_resources_are_self_contained_and_match_import_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = robot.MJCF_PATH.parent
    manifest = json.loads((root / "source_manifest.json").read_text())
    assert root.name == "cyberduck_v2"
    assert not (root / "__init__.py").exists()
    assert 'meshdir="assets/"' in robot.MJCF_PATH.read_text()
    assert len(manifest["mesh_files"]) == 20
    assert {str(p.relative_to(root)) for p in (root / "assets").iterdir()} == set(
        manifest["mesh_files"]
    )
    for relative_path, record in manifest["mesh_files"].items():
        content = (root / relative_path).read_bytes()
        assert len(content) == record["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
    assert hashlib.sha256(robot.MJCF_PATH.read_bytes()).hexdigest() == manifest[
        "model_file"
    ]["sha256"]
    assert robot.get_spec().compile().nmesh == 20


def test_source_dimensions_mass_and_scene_boundary(source_model):
    model = source_model
    assert (model.nq, model.nv, model.nu, model.neq, model.nmesh) == (26, 25, 2, 4, 20)
    assert model.body_mass.sum() == pytest.approx(3.703212, abs=1e-8)
    assert model.nlight == model.ntex == model.nmat == model.nsensor == 0
    assert not (model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE).any()
    assert tuple(model.joint(i).name for i in range(1, model.njnt)) == robot.JOINT_NAMES
    assert len(robot.INDEPENDENT_JOINT_NAMES) == 15
    assert len(robot.MIMIC_JOINT_NAMES) == 4
    assert set(robot.INDEPENDENT_JOINT_NAMES).isdisjoint(robot.MIMIC_JOINT_NAMES)
    assert set(robot.INDEPENDENT_JOINT_NAMES + robot.MIMIC_JOINT_NAMES) == set(
        robot.JOINT_NAMES
    )


def test_ankles_and_rollers_keep_source_continuous_joints(source_model):
    for name in robot.SOURCE_ACTUATED_JOINT_NAMES + robot.MIMIC_JOINT_NAMES:
        joint = source_model.joint(name)
        assert not source_model.jnt_limited[joint.id]
        assert source_model.jnt_type[joint.id] == mujoco.mjtJoint.mjJNT_HINGE
        np.testing.assert_allclose(source_model.dof_damping[joint.dofadr], 0.02)


def test_mimic_constraints_keep_driver_and_ratio(source_model):
    actual = {}
    for index in range(source_model.neq):
        assert source_model.eq_type[index] == mujoco.mjtEq.mjEQ_JOINT
        assert source_model.eq_active0[index]
        follower = source_model.joint(int(source_model.eq_obj1id[index])).name
        driver = source_model.joint(int(source_model.eq_obj2id[index])).name
        actual[follower] = driver
        np.testing.assert_array_equal(
            source_model.eq_data[index, :5], [0, 1.210526, 0, 0, 0]
        )
    assert actual == robot.MIMIC_JOINT_MAP


def test_entity_preserves_source_physical_arrays(source_model, entity_model):
    for field in (
        "body_mass", "body_inertia", "body_pos", "body_quat", "body_ipos", "body_iquat",
        "jnt_type", "jnt_axis", "jnt_pos", "jnt_limited", "jnt_range",
        "geom_type", "geom_pos", "geom_quat", "geom_size", "geom_contype",
        "geom_conaffinity", "geom_condim", "geom_friction", "eq_type", "eq_obj1id",
        "eq_obj2id", "eq_data", "eq_solref", "eq_solimp", "eq_active0",
    ):
        np.testing.assert_array_equal(
            getattr(entity_model, field), getattr(source_model, field), err_msg=field
        )
    collisions = np.flatnonzero(entity_model.geom_contype | entity_model.geom_conaffinity)
    assert tuple(entity_model.geom(int(i)).name for i in collisions) == (
        robot.COLLISION_GEOM_NAMES
    )
    for name in robot.MIMIC_JOINT_NAMES:
        source_joint = source_model.joint(name)
        entity_joint = entity_model.joint(name)
        for field in ("dof_damping", "dof_armature", "dof_frictionloss"):
            np.testing.assert_array_equal(
                getattr(entity_model, field)[entity_joint.dofadr],
                getattr(source_model, field)[source_joint.dofadr],
                err_msg=f"{name}: {field}",
            )


def test_factory_copies_do_not_share_mutable_configuration():
    first = robot.get_cyberduck_v2_robot_cfg()
    second = robot.get_cyberduck_v2_robot_cfg()
    first.init_state.joint_pos["neck_pitch_joint"] = 0.1
    first.init_state.joint_vel["head_pitch_joint"] = 0.2
    first.articulation.actuators[0].stiffness = 123.0
    first.articulation.actuators[1].damping = 9.0
    first.articulation.actuators[2].kp_fw = 1.0
    first.articulation.actuators[0].delay_max_lag = 7
    first.articulation.actuators[1].delay_max_lag = 8
    for other in (second, robot.CYBERDUCK_V2_ROBOT_CFG):
        assert other.init_state.joint_pos["neck_pitch_joint"] == 0.0
        assert other.init_state.joint_vel["head_pitch_joint"] == 0.0
        assert other.articulation.actuators[0].stiffness == 10.0
        assert other.articulation.actuators[1].stiffness == 0.0
        assert other.articulation.actuators[1].damping == 0.4
        assert other.articulation.actuators[2].kp_fw == 32.0
        assert other.articulation.actuators[0].delay_max_lag == 3
        assert other.articulation.actuators[1].delay_max_lag == 3
    assert second.init_state.pos == (0.0, 0.0, 0.252)
    assert robot.SOURCE_JOINT_POS["neck_pitch_joint"] == 0.0


def test_mixed_drives_cover_only_independent_joints(entity_model):
    cfg = robot.get_cyberduck_v2_robot_cfg()
    assert cfg.sort_actuators
    entity = Entity(cfg)
    assert len(entity.actuators) == 3
    position, velocity, servo = entity.actuators
    assert isinstance(position.cfg, HTDW3532ActuatorCfg)
    assert isinstance(velocity.cfg, HTDW3532ActuatorCfg)
    assert isinstance(servo.cfg, FrictionDRBamActuatorCfg)
    assert tuple(position.target_names) == robot.BRUSHLESS_POSITION_JOINT_NAMES
    assert tuple(velocity.target_names) == robot.VELOCITY_JOINT_NAMES
    assert tuple(servo.target_names) == robot.SERVO_JOINT_NAMES
    assert tuple(len(act.target_names) for act in entity.actuators) == (10, 2, 3)
    assert robot.VELOCITY_JOINT_NAMES == ("r_ankle_joint", "l_ankle_joint")
    assert robot.POSITION_JOINT_NAMES == (
        robot.BRUSHLESS_POSITION_JOINT_NAMES + robot.SERVO_JOINT_NAMES
    )
    assert len(robot.POSITION_JOINT_NAMES) == 13
    assert set(robot.POSITION_JOINT_NAMES).isdisjoint(robot.VELOCITY_JOINT_NAMES)
    assert set(robot.BRUSHLESS_POSITION_JOINT_NAMES + robot.VELOCITY_JOINT_NAMES) == (
        set(robot.BRUSHLESS_JOINT_NAMES)
    )
    assert position.cfg.stiffness == 10.0 and velocity.cfg.stiffness == 0.0
    for actuator in (position, velocity):
        assert actuator.cfg.damping == 0.4
        assert actuator.cfg.effort_limit == 2.0
        assert actuator.cfg.armature == robot.BRUSHLESS_ARMATURE
    for actuator in entity.actuators:
        assert (
            actuator.cfg.delay_min_lag, actuator.cfg.delay_max_lag,
            actuator.cfg.delay_hold_prob, actuator.cfg.delay_update_period,
        ) == (0, 3, 0.4, 10)
    assert tuple(servo.target_names) == (
        "head_yaw_joint", "head_roll_joint", "mouth_joint"
    )
    assert tuple(entity_model.actuator(i).name for i in range(entity_model.nu)) == (
        robot.ACTUATOR_NAMES
    )
    targets = tuple(
        entity_model.joint(int(entity_model.actuator_trnid[i, 0])).name
        for i in range(entity_model.nu)
    )
    assert targets == robot.ACTUATED_JOINT_NAMES
    assert len(targets) == len(set(targets)) == 15
    assert set(targets) == set(robot.INDEPENDENT_JOINT_NAMES)
    assert not set(targets).intersection(robot.MIMIC_JOINT_NAMES)
    assert tuple(entity_model.actuator(name).id for name in robot.VELOCITY_JOINT_NAMES) == (4, 9)
    assert tuple(entity_model.actuator(name).id for name in robot.BRUSHLESS_POSITION_JOINT_NAMES) == (
        0, 1, 2, 3, 5, 6, 7, 8, 10, 11,
    )
    assert robot.get_robot_spec().compile().nu == 0
    source = robot.get_spec().compile()
    assert tuple(source.actuator(i).name for i in range(source.nu)) == (
        robot.SOURCE_ACTUATOR_NAMES
    )


@pytest.mark.parametrize("direction", (-1.0, 1.0))
def test_native_mixed_drive_caps_leave_rollers_unactuated(entity_model, direction):
    data = mujoco.MjData(entity_model)
    data.ctrl[:] = 12.0 * direction
    mujoco.mj_forward(entity_model, data)
    expected = direction * np.array([2.0] * 12 + [1.471] * 3)
    np.testing.assert_allclose(data.actuator_force, expected)
    force = np.zeros(entity_model.nv)
    for name, value in zip(robot.ACTUATED_JOINT_NAMES, expected, strict=True):
        force[entity_model.joint(name).dofadr] = value
    np.testing.assert_allclose(data.qfrc_actuator, force, atol=1e-12)


@pytest.mark.parametrize("angle", (-4.0 * np.pi, 0.0, 3.0 * np.pi))
def test_native_ankles_ignore_angle_and_apply_velocity_feedback(entity_model, angle):
    """不同转角下核对速度反馈方向、跟踪零误差与零速制动，不推进约束状态。"""
    data = mujoco.MjData(entity_model)
    actuator_ids = np.array([entity_model.actuator(name).id for name in robot.VELOCITY_JOINT_NAMES])
    joint_ids = np.array([entity_model.joint(name).id for name in robot.VELOCITY_JOINT_NAMES])
    qpos_ids = entity_model.jnt_qposadr[joint_ids]
    dof_ids = entity_model.jnt_dofadr[joint_ids]
    np.testing.assert_array_equal(entity_model.actuator_biasprm[actuator_ids, 1], 0.0)
    np.testing.assert_allclose(entity_model.actuator_biasprm[actuator_ids, 2], -0.4)
    data.qpos[qpos_ids] = (angle, -angle)
    for target_velocity, current_velocity in (
        ((1.5, -1.0), (0.0, 0.0)),
        ((-1.5, 1.0), (0.0, 0.0)),
        ((0.5, -0.5), (0.5, -0.5)),
        ((0.0, 0.0), (0.5, -0.5)),
    ):
        data.qvel[dof_ids] = current_velocity
        data.ctrl[actuator_ids] = 0.4 * np.array(target_velocity)
        mujoco.mj_forward(entity_model, data)
        expected = 0.4 * (np.array(target_velocity) - current_velocity)
        np.testing.assert_allclose(data.actuator_force[actuator_ids], expected, atol=1e-12)
        np.testing.assert_allclose(data.qfrc_actuator[dof_ids], expected, atol=1e-12)


def test_soft_mimic_relaxes_displaced_rollers_without_external_load():
    """无重力、无接触、无驱动力下检查约束恢复，不把软约束称为刚性传动。"""
    model = robot.get_spec().compile()
    MujocoCfg(gravity=(0.0, 0.0, 0.0), disableflags=("contact",)).apply(model)
    data = mujoco.MjData(model)
    for name, offset in zip(
        robot.MIMIC_JOINT_NAMES, (0.1, 0.08, -0.07, -0.1), strict=True
    ):
        data.qpos[model.joint(name).qposadr] = offset
    for _ in range(1500):
        mujoco.mj_step(model, data)
    assert data.time == pytest.approx(3.0)
    assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
    for follower, driver in robot.MIMIC_JOINT_MAP.items():
        residual = data.qpos[model.joint(follower).qposadr] - (
            robot.MIMIC_MULTIPLIER * data.qpos[model.joint(driver).qposadr]
        )
        assert abs(float(residual[0])) < 0.003


def test_preview_uses_source_pose_and_unique_scene_objects():
    model, data = robot.make_preview()
    key = model.key("init_state")
    np.testing.assert_array_equal(data.qpos, key.qpos)
    np.testing.assert_array_equal(data.qpos[:3], robot.SOURCE_FRAME.pos)
    np.testing.assert_array_equal(data.qpos[3:7], [1, 0, 0, 0])
    np.testing.assert_array_equal(data.qpos[7:], 0.0)
    np.testing.assert_array_equal(data.ctrl, 0.0)
    assert data.time == 0.0
    assert (model.nu, model.neq) == (15, 4)
    assert (model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE).sum() == 1
    assert model.nlight == 1
    assert model.opt.integrator == mujoco.mjtIntegrator.mjINT_IMPLICITFAST


def test_two_robot_models_can_share_one_scene():
    from ht_microduck.robot.ht_microduck_constants import get_ht_microduck_robot_cfg

    scene = Scene(
        SceneCfg(
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={
                "ht": get_ht_microduck_robot_cfg(),
                "cyberduck": robot.get_cyberduck_v2_robot_cfg(),
            },
        ),
        device="cpu",
    )
    model = scene.compile()
    assert (model.nq, model.nv, model.nu, model.neq) == (48, 46, 30, 4)
    assert model.body("ht/base_link").id != model.body("cyberduck/base_link").id
    assert model.joint("ht/r_ankle_joint").id != model.joint("cyberduck/r_ankle_joint").id
    assert (model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE).sum() == 1


def test_robot_selection_cli_loads_from_another_working_directory(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools" / "check_robot.py"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--robot", "cyberduck-v2"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    assert "nq=26, nv=25, nu=2" in result.stdout
    assert "Mixed-drive entity: nq=26, nv=25, nu=15, neq=4" in result.stdout
    assert "12 HTDW-3532 NT-PD motors + 3 HD1910 BAM servos" in result.stdout
    assert "13 position targets [rad], 2 ankle velocity targets [rad/s]" in result.stdout
    assert "Mimic check passed" in result.stdout


# ---------- 显式混合驱动运行检查 ----------
def _reset_runtime(scene, sim, env_ids=None) -> None:
    """恢复物理初态与位置目标，清零速度目标及所选环境的执行器历史。"""
    entity = scene["robot"]
    selected = slice(None) if env_ids is None else env_ids
    sim.reset(env_ids)
    scene.reset(env_ids)
    root = entity.data.default_root_state[selected].clone()
    root[:, :3] += scene.env_origins[selected]
    entity.write_root_state_to_sim(root, env_ids=env_ids)
    entity.write_joint_state_to_sim(
        entity.data.default_joint_pos[selected],
        entity.data.default_joint_vel[selected],
        env_ids=env_ids,
    )
    entity.set_joint_position_target(entity.data.default_joint_pos[selected], env_ids=env_ids)
    sim.forward()


def _check_runtime_controls(entity, sim, delayed_position, delayed_velocity) -> None:
    """用既有电机公式核对逐关节映射、当前反馈和源限幅。"""
    import torch

    from ht_microduck.actuator.HD_1910_C001.model import compute_motor_torque
    from ht_microduck.actuator.HTDW_3532_02_DNE.model import clip_nt_torque

    position, velocity, servo = entity.actuators
    sim.forward()
    for brushless in (position, velocity):
        target_pos = delayed_position[:, brushless.target_ids]
        target_vel = delayed_velocity[:, brushless.target_ids]
        torch.testing.assert_close(
            sim.data.ctrl[:, brushless.global_ctrl_ids],
            brushless.stiffness * target_pos + brushless.damping * target_vel,
            rtol=2e-5, atol=2e-6,
        )
        expected_brushless = clip_nt_torque(
            brushless.stiffness * (target_pos - entity.data.joint_pos[:, brushless.target_ids])
            + brushless.damping * (target_vel - entity.data.joint_vel[:, brushless.target_ids]),
            entity.data.joint_vel[:, brushless.target_ids],
            brushless.force_limit,
            brushless.parameters,
        )
        torch.testing.assert_close(
            sim.data.qfrc_actuator[:, entity.indexing.joint_v_adr[brushless.target_ids]],
            expected_brushless,
            rtol=2e-5, atol=2e-6,
        )
    servo_target = delayed_position[:, servo.target_ids]
    expected_servo = compute_motor_torque(
        servo.parameters,
        servo_target - entity.data.joint_pos[:, servo.target_ids],
        entity.data.joint_vel[:, servo.target_ids],
        torch.full_like(servo_target[:, :1], servo.cfg.vin),
        servo.cfg.kp_fw,
    ).clamp(-servo.cfg.effort_limit, servo.cfg.effort_limit)
    torch.testing.assert_close(servo.last_motor_torque, expected_servo, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(
        sim.data.ctrl[:, servo.global_ctrl_ids], expected_servo, rtol=2e-5, atol=2e-6
    )
    torch.testing.assert_close(
        sim.data.qfrc_actuator[:, entity.indexing.joint_v_adr[servo.target_ids]],
        expected_servo,
        rtol=2e-5, atol=2e-6,
    )


def check_scene_runtime(device: str) -> None:
    """显式检查 19 关节状态、15 路驱动、四从动及局部重置，不验收站立。"""
    import torch
    from mjlab.sim import Simulation, SimulationCfg

    torch.manual_seed(1910)
    scene = Scene(
        SceneCfg(
            num_envs=3,
            terrain=TerrainEntityCfg(terrain_type="plane"),
            entities={"robot": robot.get_cyberduck_v2_robot_cfg()},
        ),
        device=device,
    )
    model = scene.compile()
    sim = Simulation(
        num_envs=3,
        cfg=SimulationCfg(nconmax=128, njmax=512),
        model=model,
        device=device,
    )
    scene.initialize(model, sim.model, sim.data)
    model_fields = (
        "actuator_forcerange", "actuator_biasprm", "dof_frictionloss", "dof_damping"
    )
    sim.expand_model_fields(model_fields)
    entity = scene["robot"]
    position, velocity, servo = entity.actuators
    assert tuple(entity.joint_names) == robot.JOINT_NAMES
    assert tuple(position.target_names) == robot.BRUSHLESS_POSITION_JOINT_NAMES
    assert tuple(velocity.target_names) == robot.VELOCITY_JOINT_NAMES
    assert tuple(servo.target_names) == robot.SERVO_JOINT_NAMES
    assert velocity.ctrl_ids.tolist() == velocity.global_ctrl_ids.tolist() == [4, 9]
    assert position.ctrl_ids.tolist() == [0, 1, 2, 3, 5, 6, 7, 8, 10, 11]
    assert position.global_ctrl_ids.tolist() == position.ctrl_ids.tolist()
    for field in model_fields:
        value = getattr(sim.model, field)
        assert value.shape[0] == 3 and value.stride(0) != 0, field
    _reset_runtime(scene, sim)
    assert entity.data.joint_pos.shape == (3, 19)
    assert sim.data.qpos.shape == (3, 26)
    assert sim.data.qvel.shape == (3, 25)
    assert sim.data.ctrl.shape == (3, 15)
    follower_ids = torch.tensor(
        [robot.JOINT_NAMES.index(name) for name in robot.MIMIC_JOINT_NAMES], device=device
    )
    follower_dofs = entity.indexing.joint_v_adr[follower_ids]
    position_ids = torch.tensor(
        [robot.JOINT_NAMES.index(name) for name in robot.POSITION_JOINT_NAMES], device=device
    )
    velocity_dofs = entity.indexing.joint_v_adr[velocity.target_ids]

    # 13 路位置与两踝速度分别写入；四个从动槽另注入目标以确认没有直接控制输入。
    targets = entity.data.default_joint_pos + torch.linspace(0.002, 0.008, 19, device=device)
    targets += torch.arange(3, device=device)[:, None] * 0.001
    targets[:, velocity.target_ids] = 0.0
    targets[:, follower_ids] = 0.4
    velocities = torch.zeros_like(targets)
    velocities[:, velocity.target_ids] = torch.tensor([[0.6, -0.4], [-0.7, 0.5], [0.8, -0.6]], device=device)
    velocities[:, follower_ids] = 0.3
    entity.set_joint_position_target(targets[:, position_ids], joint_ids=position_ids)
    entity.set_joint_velocity_target(velocities[:, velocity.target_ids], joint_ids=velocity.target_ids)
    entity.set_joint_position_target(targets[:, follower_ids], joint_ids=follower_ids)
    entity.set_joint_velocity_target(velocities[:, follower_ids], joint_ids=follower_ids)
    scene.write_data_to_sim()
    _check_runtime_controls(entity, sim, targets, velocities)
    torch.testing.assert_close(sim.data.qfrc_actuator[:, follower_dofs], torch.zeros((3, 4), device=device))

    # 改变踝角度和位置目标，速度控制力矩保持不变；这些构造状态只 forward、不推进。
    current_velocity = torch.tensor([[0.4, -0.3], [-0.2, 0.5], [0.1, -0.1]], device=device)
    desired_velocity = torch.tensor([[1.5, -1.0], [-1.5, 1.0], [0.5, -0.5]], device=device)
    for angle, position_target in ((0.0, 0.0), (3.0, -7.0), (-4.0, 9.0)):
        _reset_runtime(scene, sim)
        joint_pos = entity.data.default_joint_pos.clone()
        joint_vel = entity.data.default_joint_vel.clone()
        joint_pos[:, velocity.target_ids] = angle
        joint_vel[:, velocity.target_ids] = current_velocity
        entity.write_joint_state_to_sim(joint_pos, joint_vel)
        sim.forward()
        targets = entity.data.default_joint_pos.clone()
        velocities = torch.zeros_like(targets)
        targets[:, velocity.target_ids] = position_target
        velocities[:, velocity.target_ids] = desired_velocity
        entity.set_joint_position_target(targets)
        entity.set_joint_velocity_target(desired_velocity, joint_ids=velocity.target_ids)
        scene.write_data_to_sim()
        _check_runtime_controls(entity, sim, targets, velocities)
        torch.testing.assert_close(
            sim.data.ctrl[:, velocity.global_ctrl_ids], 0.4 * desired_velocity,
            rtol=2e-5, atol=2e-6,
        )
        torch.testing.assert_close(
            sim.data.qfrc_actuator[:, velocity_dofs], 0.4 * (desired_velocity - current_velocity),
            rtol=2e-5, atol=2e-6,
        )

    # 零速度目标会制动当前运动；reset 必须清掉上一组非零速度目标。
    _reset_runtime(scene, sim)
    assert not entity.data.joint_vel_target.any()
    joint_vel = entity.data.default_joint_vel.clone()
    joint_vel[:, velocity.target_ids] = current_velocity
    entity.write_joint_state_to_sim(entity.data.default_joint_pos, joint_vel)
    sim.forward()
    scene.write_data_to_sim()
    _check_runtime_controls(entity, sim, entity.data.default_joint_pos, torch.zeros_like(joint_vel))
    torch.testing.assert_close(
        sim.data.qfrc_actuator[:, velocity_dofs], -0.4 * current_velocity,
        rtol=2e-5, atol=2e-6,
    )

    # 反向速度提供 BAM 反电动势工况，明确触发 1.471 N·m 上限；不推进此构造状态。
    for direction in (-1.0, 1.0):
        _reset_runtime(scene, sim)
        joint_vel = torch.zeros_like(entity.data.joint_vel)
        joint_vel[:, servo.target_ids] = -10.0 * direction
        entity.write_joint_state_to_sim(entity.data.default_joint_pos, joint_vel)
        sim.forward()
        high = entity.data.default_joint_pos.clone()
        high[:, position_ids] = direction
        high_velocity = torch.zeros_like(high)
        high_velocity[:, velocity.target_ids] = 8.0 * direction
        entity.set_joint_position_target(high[:, position_ids], joint_ids=position_ids)
        entity.set_joint_velocity_target(high_velocity[:, velocity.target_ids], joint_ids=velocity.target_ids)
        scene.write_data_to_sim()
        _check_runtime_controls(entity, sim, high, high_velocity)
        for brushless in (position, velocity):
            torch.testing.assert_close(
                sim.data.qfrc_actuator[:, entity.indexing.joint_v_adr[brushless.target_ids]],
                torch.full((3, len(brushless.target_ids)), 2.0 * direction, device=device),
                rtol=2e-5, atol=2e-6,
            )
        torch.testing.assert_close(
            servo.last_motor_torque,
            torch.full((3, 3), 1.471 * direction, device=device),
            rtol=2e-5, atol=2e-6,
        )

    # 用真实延迟历史核对三个组的位置/速度通道，反馈始终使用当前物理状态。
    _reset_runtime(scene, sim)
    history = []
    rows = torch.arange(3, device=device)
    phase = rows[:, None] * 0.7 + torch.arange(19, device=device)[None, :] * 0.3
    buffers = [act._delay_buffer for act in entity.actuators]
    assert all(buffer is not None for buffer in buffers)
    for buffer in buffers:
        assert (
            buffer.min_lag, buffer.max_lag, buffer.hold_prob,
            buffer.update_period, buffer.per_env_phase,
        ) == (0, 3, 0.4, 10, True)
    lag_values = [set() for _ in buffers]
    delayed_visible = [False for _ in buffers]
    for step in range(100):
        target = entity.data.default_joint_pos.clone()
        target[:, position_ids] += 0.01 * torch.sin(0.37 * step + phase[:, position_ids])
        mouth = robot.JOINT_NAMES.index("mouth_joint")
        target[:, mouth] = 0.01 + 0.005 * torch.sin(0.37 * step + phase[:, mouth])
        target_velocity = torch.zeros_like(target)
        target_velocity[:, velocity.target_ids] = 0.5 * torch.sin(0.29 * step + phase[:, velocity.target_ids])
        history.append(torch.stack((target, target_velocity), dim=-1))
        counters = [buffer._step_count.clone() for buffer in buffers]
        entity.set_joint_position_target(target[:, position_ids], joint_ids=position_ids)
        entity.set_joint_velocity_target(target_velocity[:, velocity.target_ids], joint_ids=velocity.target_ids)
        scene.write_data_to_sim()
        frames = torch.stack(history)
        delayed_position = target.clone()
        delayed_velocity = target_velocity.clone()
        for index, (actuator, buffer) in enumerate(zip(entity.actuators, buffers, strict=True)):
            lags = buffer.current_lags
            assert ((lags >= 0) & (lags <= 3)).all()
            torch.testing.assert_close(buffer._step_count, counters[index] + 1)
            lag_values[index].update(lags.tolist())
            value = frames[(step - lags).clamp_min(0), rows][:, actuator.target_ids]
            delayed_position[:, actuator.target_ids] = value[..., 0]
            delayed_velocity[:, actuator.target_ids] = value[..., 1]
            issued = torch.stack((target[:, actuator.target_ids], target_velocity[:, actuator.target_ids]), dim=-1)
            delayed_visible[index] |= bool((value - issued).abs().max() > 1e-5)
        _check_runtime_controls(entity, sim, delayed_position, delayed_velocity)
        torch.testing.assert_close(sim.data.qfrc_actuator[:, follower_dofs], torch.zeros((3, 4), device=device))
        sim.step()
        scene.update(model.opt.timestep)
    assert all(delayed_visible)
    assert all(max(values) > 0 for values in lag_values)
    torch.testing.assert_close(
        sim.data.time[:], torch.full((3,), 100 * model.opt.timestep, device=device),
        rtol=0.0, atol=1e-6,
    )
    for field in ("qpos", "qvel", "qacc", "ctrl", "actuator_force"):
        assert torch.isfinite(getattr(sim.data, field)).all(), field
    assert not sim.data.overflow.any()

    before = {
        field: getattr(sim.data, field)[1:].clone()
        for field in ("qpos", "qvel", "ctrl", "time")
    }
    before_targets = entity.data.joint_pos_target[1:].clone()
    before_velocity_targets = entity.data.joint_vel_target[1:].clone()
    before_motor = servo.last_motor_torque[1:].clone()
    before_friction = servo.last_friction_budget[1:].clone()
    before_fields = {field: getattr(sim.model, field)[1:].clone() for field in model_fields}
    before_delays = [(buffer._step_count[1:].clone(), buffer.current_lags[1:].clone()) for buffer in buffers]
    selected = torch.tensor([0], device=device)
    _reset_runtime(scene, sim, selected)
    for field, value in before.items():
        torch.testing.assert_close(getattr(sim.data, field)[1:], value)
    for field, value in before_fields.items():
        torch.testing.assert_close(getattr(sim.model, field)[1:], value)
    torch.testing.assert_close(entity.data.joint_pos_target[1:], before_targets)
    torch.testing.assert_close(entity.data.joint_vel_target[1:], before_velocity_targets)
    torch.testing.assert_close(servo.last_motor_torque[1:], before_motor)
    torch.testing.assert_close(servo.last_friction_budget[1:], before_friction)
    torch.testing.assert_close(entity.data.joint_pos[0], entity.data.default_joint_pos[0])
    torch.testing.assert_close(entity.data.joint_vel[0], entity.data.default_joint_vel[0])
    torch.testing.assert_close(entity.data.joint_pos_target[0], entity.data.default_joint_pos[0])
    assert not entity.data.joint_vel_target[0].any()
    assert not servo._load_valid[0].any()
    assert not servo.last_motor_torque[0].any()
    for buffer, (counts, lags) in zip(buffers, before_delays, strict=True):
        torch.testing.assert_close(buffer._step_count[1:], counts)
        torch.testing.assert_close(buffer.current_lags[1:], lags)
        assert buffer._step_count[0] == 0 and buffer.current_lags[0] == 0
    print(f"CyberDuck V2 mixed-drive runtime passed: device={device}, environments=3, steps=100.")
    print("Verified 19 joint states, 13 position targets, 2 ankle velocity targets and 4 unactuated followers.")
    print("Verified ankle position independence, velocity feedback and zero-speed braking.")
    print(f"Verified bidirectional NT/BAM caps, three command-delay groups {lag_values} and partial reset.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cpu", help="运行设备，例如 cpu 或 cuda:0。")
    args = parser.parse_args()
    check_scene_runtime(args.device)
