"""CPU checks for the complete robot entity and its model reference frames."""

import mujoco
import numpy as np
import pytest
from mjlab.entity import Entity, EntityCfg
from mjlab.scene import Scene, SceneCfg
from mjlab.sim import MujocoCfg
from mjlab.terrains import TerrainEntityCfg

from ht_microduck.robot.ht_microduck_constants import (
    BRUSHLESS_ACTUATOR_CFG,
    BRUSHLESS_ARMATURE,
    COLLISION_GEOM_NAMES,
    FOOT_SITE_NAMES,
    FULL_COLLISION,
    HOME_FRAME,
    HOME_JOINT_POS,
    HT_MICRODUCK_ROBOT_CFG,
    JOINT_NAMES,
    MJCF_PATH,
    SERVO_ACTUATOR_CFG,
    get_ht_microduck_robot_cfg,
    get_robot_spec,
    get_spec,
    make_preview,
)


@pytest.fixture(scope="module")
def robot_model():
    return Entity(get_ht_microduck_robot_cfg()).compile()


@pytest.fixture(scope="module")
def scene_model():
    scene = Scene(
        SceneCfg(
            entities={"robot": get_ht_microduck_robot_cfg()},
            terrain=TerrainEntityCfg(terrain_type="plane"),
        ),
        device="cpu",
    )
    return scene.compile()


def _reset_data(model):
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    return data


def _mesh_vertices_in_body(model, geom_id):
    """Undo the compiler's mesh recentering through the compiled geom pose."""
    mesh_id = model.geom_dataid[geom_id]
    start = model.mesh_vertadr[mesh_id]
    vertices = model.mesh_vert[start : start + model.mesh_vertnum[mesh_id]]
    rotation = np.empty(9)
    mujoco.mju_quat2Mat(rotation, model.geom_quat[geom_id])
    return vertices @ rotation.reshape(3, 3).T + model.geom_pos[geom_id]


def _sole_surface_vertices(model, geom_id):
    """Find the largest downward supporting face, including a tilted sole."""
    vertices = _mesh_vertices_in_body(model, geom_id)
    mesh_id = model.geom_dataid[geom_id]
    start = model.mesh_faceadr[mesh_id]
    faces = model.mesh_face[start : start + model.mesh_facenum[mesh_id]]
    triangles = vertices[faces]
    cross = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    area = np.linalg.norm(cross, axis=1)
    candidates = np.flatnonzero(cross[:, 2] < -0.9 * area)
    for index in candidates[np.argsort(area[candidates])[::-1]]:
        normal = cross[index] / area[index]
        distances = (vertices - triangles[index, 0]) @ normal
        if distances.max() < 1e-7:
            return vertices[np.abs(distances) < 1e-7]
    raise AssertionError("No downward sole support face found in the ankle mesh.")


def test_factory_configs_and_nested_mutable_values_are_independent():
    first = get_ht_microduck_robot_cfg()
    second = get_ht_microduck_robot_cfg()
    assert first is not second
    assert first is not HT_MICRODUCK_ROBOT_CFG
    assert first.init_state is not second.init_state
    assert first.articulation is not second.articulation
    assert first.collisions[0] is not second.collisions[0]
    first.init_state.joint_pos[JOINT_NAMES[0]] = 0.1
    first.init_state.joint_vel[JOINT_NAMES[1]] = 0.2
    first.articulation.actuators[0].stiffness = 123.0
    first.articulation.actuators[1].kp_fw = 1.0
    first.collisions[0].friction = (0.1, 0.0, 0.0)
    assert second.init_state.joint_pos[JOINT_NAMES[0]] == 0.0
    assert second.init_state.joint_vel[JOINT_NAMES[1]] == 0.0
    assert HOME_FRAME.joint_pos[JOINT_NAMES[0]] == 0.0
    assert HOME_FRAME.joint_vel[JOINT_NAMES[1]] == 0.0
    assert HT_MICRODUCK_ROBOT_CFG.init_state.joint_pos[JOINT_NAMES[0]] == 0.0
    assert HT_MICRODUCK_ROBOT_CFG.init_state.joint_vel[JOINT_NAMES[1]] == 0.0
    assert second.articulation.actuators[0].stiffness == 10.0
    assert BRUSHLESS_ACTUATOR_CFG.stiffness == 10.0
    assert HT_MICRODUCK_ROBOT_CFG.articulation.actuators[0].stiffness == 10.0
    assert second.articulation.actuators[1].kp_fw == 32.0
    assert SERVO_ACTUATOR_CFG.kp_fw == 32.0
    assert HT_MICRODUCK_ROBOT_CFG.articulation.actuators[1].kp_fw == 32.0
    assert second.collisions[0].friction == (1.0, 0.005, 0.0001)
    assert FULL_COLLISION.friction == (1.0, 0.005, 0.0001)
    assert HT_MICRODUCK_ROBOT_CFG.collisions[0].friction == (1.0, 0.005, 0.0001)
    assert all(
        a is not b
        for a, b in zip(
            first.articulation.actuators, second.articulation.actuators, strict=True
        )
    )


def test_task_can_edit_its_robot_config_before_compilation():
    cfg = get_ht_microduck_robot_cfg()
    cfg.init_state = EntityCfg.InitialStateCfg(
        pos=(0.1, 0.2, 0.3),
        joint_pos={name: 0.1 if name == "mouth_joint" else 0.0 for name in JOINT_NAMES},
        joint_vel={".*": 0.0},
    )
    cfg.articulation.soft_joint_pos_limit_factor = 0.9
    brushless = cfg.articulation.actuators[0]
    brushless.stiffness = 2.0
    brushless.damping = 0.1
    brushless.effort_limit = 0.35
    assert cfg.init_state.pos == (0.1, 0.2, 0.3)
    assert cfg.init_state.joint_vel == {".*": 0.0}
    assert cfg.articulation.soft_joint_pos_limit_factor == 0.9
    assert (brushless.stiffness, brushless.damping, brushless.effort_limit) == (
        2.0,
        0.1,
        0.35,
    )
    entity = Entity(cfg)
    model = entity.compile()
    data = _reset_data(model)
    np.testing.assert_allclose(data.qpos[:3], [0.1, 0.2, 0.3])
    assert data.qpos[model.joint("mouth_joint").qposadr[0]] == pytest.approx(0.1)
    # Native affine PD preserves the configured feedback gains and unit gain.
    assert entity.actuators[0].cfg.stiffness == 2.0
    assert entity.actuators[0].cfg.damping == 0.1
    np.testing.assert_allclose(model.actuator_gainprm[:12, 0], 1.0)
    np.testing.assert_allclose(model.actuator_biasprm[:12, 1], -2.0)
    np.testing.assert_allclose(model.actuator_biasprm[:12, 2], -0.1)
    assert not model.actuator_ctrllimited[:12].any()
    np.testing.assert_allclose(model.actuator_forcerange[:12], [[-0.35, 0.35]] * 12)
    assert HOME_FRAME.pos == (0.0, 0.0, 0.1534)
    assert HOME_FRAME.joint_pos["mouth_joint"] == 0.0
    assert BRUSHLESS_ACTUATOR_CFG.stiffness == 10.0
    assert HT_MICRODUCK_ROBOT_CFG.articulation.soft_joint_pos_limit_factor == 1.0


def test_module_robot_config_compiles_without_factory_arguments():
    model = Entity(HT_MICRODUCK_ROBOT_CFG).compile()
    assert (model.nq, model.nv, model.nu) == (22, 21, 15)
    brushless = HT_MICRODUCK_ROBOT_CFG.articulation.actuators[0]
    assert (brushless.stiffness, brushless.damping, brushless.effort_limit) == (
        10.0,
        0.4,
        2.0,
    )


def test_source_xml_is_robot_only(scene_model):
    """The robot asset carries no ground or light; mjlab's Scene adds them.

    mjlab's Scene supplies its own terrain plane and sun, so a floor or light in
    the robot XML would be a duplicate. This mirrors the official microduck_rl
    split, where robot_walk.xml is included by a scene that adds the ground.
    """
    source = get_spec().compile()
    assert source.nu == 0
    assert source.nsite == 1
    assert source.nsensor == 5
    assert source.nlight == 0
    planes = np.flatnonzero(source.geom_type == mujoco.mjtGeom.mjGEOM_PLANE)
    assert len(planes) == 0
    assert source.qpos0[2] == pytest.approx(0.171)  # XML default, not HOME
    # The source XML carries no geom names; get_robot_spec() assigns them.
    active_robot_geoms = np.flatnonzero(
        (source.geom_bodyid != 0)
        & ((source.geom_contype != 0) | (source.geom_conaffinity != 0))
    )
    assert len(active_robot_geoms) == 10
    assert all(not source.geom(int(g)).name for g in active_robot_geoms)

    # The scene keeps text/xml completely separate, so no second floor appears.
    scene_planes = np.flatnonzero(
        scene_model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE
    )
    assert [scene_model.geom(int(g)).name for g in scene_planes] == ["terrain"]
    assert scene_model.nlight == 1


def test_prepared_spec_is_fresh_and_source_xml_remains_unchanged():
    source_xml = MJCF_PATH.read_bytes()
    first, second = get_robot_spec(), get_robot_spec()
    first.site(FOOT_SITE_NAMES[0]).pos[0] = 10.0
    assert second.site(FOOT_SITE_NAMES[0]).pos[0] != 10.0
    assert not first.lights and not second.lights
    assert all(g.type != mujoco.mjtGeom.mjGEOM_PLANE for g in second.geoms)
    assert second.compile().nu == 0
    model = second.compile()
    active_robot_geoms = np.flatnonzero(
        (model.geom_bodyid != 0)
        & ((model.geom_contype != 0) | (model.geom_conaffinity != 0))
    )
    assert len(active_robot_geoms) == 10
    assert MJCF_PATH.read_bytes() == source_xml


def test_source_has_ht_dk_urdf_mass_geometry_and_head_limits():
    model = get_spec().compile()
    assert model.body_mass.sum() == pytest.approx(3.2946797, abs=1e-7, rel=0.0)
    np.testing.assert_allclose(model.body("l_hip_pitch_link").pos, [0, 0.050899, 0])
    for name, limits in {
        "neck_pitch_joint": (-1.21, 2.3),
        "head_pitch_joint": (-1.571, 1.88),
        "head_roll_joint": (-0.36, 0.36),
        "mouth_joint": (0.0, 0.23),
    }.items():
        np.testing.assert_allclose(model.joint(name).range, limits)


def test_base_collision_names_match_the_new_models_front_and_rear(robot_model):
    front = robot_model.geom("base_front_collision")
    rear = robot_model.geom("base_rear_collision")
    np.testing.assert_allclose(front.pos, [-0.055, 0.0, 0.015])
    np.testing.assert_allclose(front.size, [0.015, 0.05, 0.0475])
    np.testing.assert_allclose(rear.pos, [-0.08, 0.0, 0.006])
    np.testing.assert_allclose(rear.size, [0.015, 0.05, 0.03])


def test_entity_has_fifteen_actuators_and_all_source_collisions(robot_model):
    model = robot_model
    assert (model.nq, model.nv, model.nu) == (22, 21, 15)
    assert tuple(model.joint(int(j)).name for j in model.actuator_trnid[:, 0]) == (
        JOINT_NAMES
    )
    collision_ids = np.flatnonzero(
        (model.geom_contype != 0) | (model.geom_conaffinity != 0)
    )
    assert {model.geom(int(g)).name for g in collision_ids} == set(COLLISION_GEOM_NAMES)
    assert len(collision_ids) == 10
    np.testing.assert_array_equal(model.geom_contype[collision_ids], 1)
    np.testing.assert_array_equal(model.geom_conaffinity[collision_ids], 1)
    np.testing.assert_array_equal(model.geom_condim[collision_ids], 3)
    np.testing.assert_array_equal(model.geom_priority[collision_ids], 0)
    np.testing.assert_allclose(
        model.geom_friction[collision_ids], [[1.0, 0.005, 0.0001]] * 10
    )
    visual_ids = np.flatnonzero(model.geom_group == 1)
    assert len(visual_ids) == 16
    np.testing.assert_array_equal(model.geom_contype[visual_ids], 0)
    np.testing.assert_array_equal(model.geom_conaffinity[visual_ids], 0)


def test_neutral_reset_has_valid_joint_limits_and_zero_velocities(robot_model):
    model = robot_model
    data = _reset_data(model)
    cfg = get_ht_microduck_robot_cfg()
    assert cfg.articulation.soft_joint_pos_limit_factor == 1.0
    assert set(cfg.init_state.joint_pos) == set(JOINT_NAMES)
    assert set(cfg.init_state.joint_vel) == set(JOINT_NAMES)
    np.testing.assert_allclose(data.qpos[:7], [0.0, 0.0, 0.1534, 1.0, 0.0, 0.0, 0.0])
    np.testing.assert_array_equal(data.qvel, 0.0)
    for name in JOINT_NAMES:
        joint = model.joint(name)
        position = data.qpos[joint.qposadr[0]]
        assert joint.range[0] <= position <= joint.range[1]
    mouth = model.joint("mouth_joint")
    assert data.qpos[mouth.qposadr[0]] == mouth.range[0]
    assert data.ncon == 0  # No initial self-intersection.


@pytest.mark.parametrize("side", ["r", "l"])
def test_foot_reference_sites_match_this_models_sole_surface(robot_model, side):
    model = robot_model
    geom_id = model.geom(f"{side}_foot_collision").id
    sole = _sole_surface_vertices(model, geom_id)
    assert len(sole) > 3
    # Derive the expected position from the real mesh, independent of constants.
    center = (sole.min(axis=0) + sole.max(axis=0)) / 2
    site = model.site(f"{side}_foot")
    assert site.bodyid == model.body(f"{side}_ankle_link").id
    np.testing.assert_allclose(site.pos, center, atol=1e-7, rtol=0.0)
    np.testing.assert_allclose(site.quat, [1.0, 0.0, 0.0, 0.0])
    assert model.nsensor == 5  # Foot sites stay sensor-free.


def test_imu_site_and_sensors_match_the_root_body_reference_frame(robot_model):
    model = robot_model
    site = model.site("imu")
    assert site.bodyid == model.body("base_link").id
    np.testing.assert_allclose(site.pos, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(site.quat, [1.0, 0.0, 0.0, 0.0])
    expected_dims = ("imu_ang_vel", "imu_lin_vel", "imu_accel", "imu_upvector",
                     "root_angmom")
    sensor_names = tuple(model.sensor(i).name for i in range(model.nsensor))
    assert sensor_names == expected_dims
    root_body = model.body("base_link").id
    for name in expected_dims:
        sensor = model.sensor(name)
        assert sensor.dim[0] == 3
        # Site sensors point at the IMU site; subtreeangmom points at the root body.
        expected_obj = root_body if name == "root_angmom" else site.id
        np.testing.assert_array_equal(sensor.objid[0], expected_obj)


def test_imu_readings_report_attitude_and_body_rates(robot_model):
    model = robot_model
    data = mujoco.MjData(model)
    names = tuple(model.sensor(i).name for i in range(model.nsensor))
    offsets = {name: model.sensor(name).adr[0] for name in names}

    def reading(name):
        start = offsets[name]
        return np.array(data.sensordata[start : start + 3])

    # Reset pose: upright body. The entity model has no ground, so this state has
    # no contacts and the IMU is in free fall -- hence zero linear velocity,
    # angular rate, angular momentum and accelerometer reading.
    mujoco.mj_forward(model, data)
    assert data.ncon == 0
    np.testing.assert_allclose(reading("imu_upvector"), [0.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(reading("imu_ang_vel"), 0.0, atol=1e-12)
    np.testing.assert_allclose(reading("imu_lin_vel"), 0.0, atol=1e-12)
    np.testing.assert_allclose(reading("imu_accel"), 0.0, atol=1e-12)
    np.testing.assert_allclose(reading("root_angmom"), 0.0, atol=1e-12)

    # Yaw leaves the up vector unchanged, as a real IMU-based estimate would.
    quat = np.empty(4)
    mujoco.mju_axisAngle2Quat(quat, np.array([0.0, 0.0, 1.0]), np.deg2rad(30.0))
    data.qpos[3:7] = quat
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(reading("imu_upvector"), [0.0, 0.0, 1.0], atol=1e-12)

    # Pitching -30 deg about +y tilts the world +Z axis toward +x in the IMU frame.
    mujoco.mju_axisAngle2Quat(quat, np.array([0.0, 1.0, 0.0]), np.deg2rad(-30.0))
    data.qpos[3:7] = quat
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(
        reading("imu_upvector"), [0.5, 0.0, np.cos(np.deg2rad(30.0))], atol=1e-12
    )

    # A rotating body reports its angular velocity in the IMU frame.
    data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    data.qvel[:] = 0.0
    data.qvel[3:6] = [0.3, -0.2, 0.5]
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(reading("imu_ang_vel"), [0.3, -0.2, 0.5], atol=1e-12)


def test_plane_scene_has_one_ground_and_collision_free_neutral_pose(scene_model):
    model = scene_model
    planes = np.flatnonzero(model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE)
    assert [model.geom(int(g)).name for g in planes] == ["terrain"]
    assert model.nlight == 1
    data = _reset_data(model)
    sole_positions = np.array(
        [data.site_xpos[model.site(f"robot/{name}").id] for name in FOOT_SITE_NAMES]
    )
    assert data.ncon == 0
    com = data.subtree_com[model.body("robot/base_link").id]
    assert np.all(np.isfinite(com))
    # Check that projected COM lies in a strip between both sole surfaces.
    # This geometric condition does not establish dynamic standing stability.
    sole_x_bounds = []
    for side in ("r", "l"):
        gid = model.geom(f"robot/{side}_foot_collision").id
        sole = _sole_surface_vertices(model, gid)
        body_pos = data.xpos[model.body(f"robot/{side}_ankle_link").id]
        clearance = sole[:, 2].min() + body_pos[2]
        # HOME rests just above the plane: the largest support face sits ~1.4 mm
        # below the plane while the lowest mesh point (a heel arc) floats ~0.4 mm
        # above it, so both feet touch with no initial penetration of the plane.
        assert -0.0015 < clearance < 0.0
        assert data.site_xpos[model.site(f"robot/{side}_foot").id, 2] > clearance
        body_x = body_pos[0]
        sole_x_bounds.append(sole[:, 0].min() + body_x)
        sole_x_bounds.append(sole[:, 0].max() + body_x)
    assert max(sole_x_bounds[::2]) < com[0] < min(sole_x_bounds[1::2])
    assert sole_positions[:, 1].min() < com[1] < sole_positions[:, 1].max()


def test_both_feet_and_other_source_geoms_can_contact_scene_ground(scene_model):
    model = scene_model
    data = _reset_data(model)
    ground = model.geom("terrain").id
    # Pure collision queries at constructed heights; no dynamics or standing
    # claim. First touch both feet, then expose the other collision geoms.
    # HOME clears the plane by ~3.8 mm measured on the sole support face, but the
    # lowest mesh point is the heel arc, so step down past both to guarantee contact.
    data.qpos[2] -= 0.008
    mujoco.mj_forward(model, data)
    contacting_names = {
        model.geom(int(g)).name
        for contact in data.contact
        if ground in contact.geom
        for g in contact.geom
        if g != ground
    }
    assert {"robot/r_foot_collision", "robot/l_foot_collision"} <= contacting_names
    data.qpos[2] = 0.0
    mujoco.mj_forward(model, data)
    contacting_names = {
        model.geom(int(g)).name
        for contact in data.contact
        if ground in contact.geom
        for g in contact.geom
        if g != ground
    }
    assert "robot/base_rear_collision" in contacting_names
    assert "robot/r_hip_roll_collision" in contacting_names
    assert "robot/l_hip_roll_collision" in contacting_names


def test_preview_starts_from_the_init_state_keyframe():
    """The old preview let MuJoCo build MjData, so init_state was never applied."""
    model, data = make_preview()
    key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "init_state")
    assert key_id >= 0
    np.testing.assert_allclose(data.qpos, model.key(key_id).qpos, atol=1e-9)
    assert data.qpos[2] == pytest.approx(HOME_FRAME.pos[2])
    # Root height alone would also match the XML default pose; the joints are
    # the part that was invisible, since the default keeps every joint at zero.
    assert not np.allclose(data.qpos[7:], 0.0)
    # ctrl is an affine-PD input here, so it must be kp * q_target, not
    # q_target and not zero. The keyframe stores plain joint targets, so the
    # preview has to scale them by the compiled gain.
    np.testing.assert_allclose(
        data.ctrl, -model.actuator_biasprm[:, 1] * np.asarray(model.key(key_id).ctrl)
    )
    for actuator_id in range(model.nu):
        name = (model.actuator(actuator_id).name or "").removeprefix("robot/")
        stiffness = -float(model.actuator_biasprm[actuator_id, 1])
        assert data.ctrl[actuator_id] == pytest.approx(
            stiffness * HOME_JOINT_POS[name], abs=1e-9
        )


def test_preview_adds_one_ground_and_light_without_touching_the_robot_xml():
    """The reference entry points preview a bare entity; this one supplies ground."""
    model, _ = make_preview()
    planes = np.flatnonzero(model.geom_type == mujoco.mjtGeom.mjGEOM_PLANE)
    assert [model.geom(int(g)).name for g in planes] == ["terrain"]
    assert model.geom("terrain").friction[0] == pytest.approx(1.0)
    assert model.nlight == 1
    assert model.ntex == 1 and model.nmat == 1
    assert model.nu == 15
    # The robot XML must stay floor- and light-free (T016/T039).
    source = get_spec().compile()
    assert source.nlight == 0
    assert not (source.geom_type == mujoco.mjtGeom.mjGEOM_PLANE).any()


def test_preview_uses_the_training_integrator_and_holds_the_stance():
    """Explicit Euler makes the brushless damping unstable and the robot judders."""
    reference = mujoco.MjModel.from_xml_string("<mujoco><worldbody/></mujoco>")
    MujocoCfg().apply(reference)
    model, data = make_preview()
    assert model.opt.integrator == reference.opt.integrator
    assert model.opt.integrator != mujoco.mjtIntegrator.mjINT_EULER

    for _ in range(1000):
        mujoco.mj_step(model, data)
    # Juddering sits at ~25 rad/s indefinitely; a settled robot is ~0.3 rad/s.
    assert np.abs(data.qvel).max() < 2.0
    assert data.qpos[2] > 0.1


def test_brushless_joints_carry_reflected_rotor_inertia_and_stop_buzzing():
    """Without armature the PD damping buzzes at ~6 Hz instead of holding still.

    This is a timestep-dependent numerical artefact, not real motion: halving
    ``dt`` halves the buzz, and adding the HTDW-3532 armature cuts the mean joint
    speed by ~29x. Locking both the value and the resulting behaviour keeps a
    future edit from silently dropping the armature or the integrator.
    """
    model, data = make_preview()
    leg_dofs = [
        int(model.jnt_dofadr[model.actuator_trnid[i, 0]])
        for i in range(model.nu)
        if -model.actuator_biasprm[i, 1] > 0  # brushless: affine position bias
    ]
    assert len(leg_dofs) == 12
    assert all(
        model.dof_armature[dof] == pytest.approx(BRUSHLESS_ARMATURE) for dof in leg_dofs
    )
    # The user-supplied joint-side value, kept with all its digits.
    assert BRUSHLESS_ARMATURE == pytest.approx(0.0069753532276)

    # Let the stance settle, then measure the residual motion over 3 s.
    for _ in range(2500):
        mujoco.mj_step(model, data)
    leg_qvel = np.abs(data.qvel[1:]).mean()  # skip the 6 free-joint DOFs
    speeds = []
    for _ in range(1500):
        mujoco.mj_step(model, data)
        speeds.append(np.abs(data.qvel[1:]).mean())
    # Measured 0.0037 rad/s with the real armature; 0.0249 with the 0.002
    # placeholder; 0.105 without any armature.
    assert np.mean(speeds) < 0.01, f"joints are buzzing: {np.mean(speeds):.4f} rad/s"
    assert leg_qvel < 0.05
    # Buzzing must not cost the stance.
    assert data.qpos[2] > 0.14
