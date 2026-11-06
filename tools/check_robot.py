# Copyright (c) 2026-2027 zh
"""
内容：
    编译指定机器人，核对关节与执行器映射，并可打开静态预览。

用法：
    uv run --no-sync python -B tools/check_robot.py --robot cyberduck-v2
    uv run --no-sync python -B tools/check_robot.py --robot cyberduck-v2 --viewer
"""

import argparse
import time

import mujoco

from ht_microduck.robot import (
    cyberduck_v2_constants,
    ht_microduck_constants,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--robot",
        choices=("ht-microduck", "cyberduck-v2"),
        default="ht-microduck",
        help="选择机器人，默认保留 HT Microduck。",
    )
    parser.add_argument("--viewer", action="store_true", help="打开静态模型预览。")
    args = parser.parse_args()

    robot = (
        ht_microduck_constants
        if args.robot == "ht-microduck"
        else cyberduck_v2_constants
    )
    model = robot.get_spec().compile()
    joint_ids = [
        index
        for index in range(model.njnt)
        if model.jnt_type[index] != mujoco.mjtJoint.mjJNT_FREE
    ]
    joint_names = tuple(model.joint(index).name for index in joint_ids)
    if joint_names != robot.JOINT_NAMES:
        raise ValueError(
            f"Joint order differs from {robot.__name__}: "
            f"model={joint_names}, mapping={robot.JOINT_NAMES}"
        )

    print(f"Model compiled: {robot.MJCF_PATH}")
    print(f"Joints: {len(joint_names)}, meshes: {model.nmesh}")
    print(f"nq={model.nq}, nv={model.nv}, nu={model.nu}")
    print(f"Total mass: {model.body_mass.sum():.6f} kg")
    planes = sum(
        1 for index in range(model.ngeom)
        if model.geom_type[index] == mujoco.mjtGeom.mjGEOM_PLANE
    )
    if planes or model.nlight:
        raise ValueError(
            "Robot XML must contain only the robot body: "
            f"found {planes} planes and {model.nlight} lights"
        )
    print("Body check passed: terrain and lighting are supplied by the mjlab scene.")
    for index in joint_ids:
        name = model.joint(index).name
        lower, upper = model.jnt_range[index]
        limits = (
            f"[{lower:.3f}, {upper:.3f}] rad"
            if model.jnt_limited[index]
            else "continuous"
        )
        print(f"  {name:<24} {limits}")

    if args.robot == "cyberduck-v2":
        _check_cyberduck(model)
    else:
        _check_ht_microduck(model, joint_names)

    if args.viewer:
        from mujoco import viewer as mj_viewer

        preview_model, preview_data = robot.make_preview()
        with mj_viewer.launch_passive(preview_model, preview_data) as viewer:
            while viewer.is_running():
                viewer.sync()
                time.sleep(1.0 / 60.0)


def _check_cyberduck(model: mujoco.MjModel) -> None:
    """分别核对原始模型与当前混合驱动实体，保留四个滚轮从动。"""
    from mjlab.entity import Entity

    robot = cyberduck_v2_constants
    if (model.nq, model.nv, model.nu, model.neq, model.nmesh) != (26, 25, 2, 4, 20):
        raise ValueError("CyberDuck V2 model dimensions differ from the source model.")
    actuators = tuple(model.actuator(i).name for i in range(model.nu))
    targets = tuple(
        model.joint(int(model.actuator_trnid[i, 0])).name for i in range(model.nu)
    )
    if (
        actuators != robot.SOURCE_ACTUATOR_NAMES
        or targets != robot.SOURCE_ACTUATED_JOINT_NAMES
    ):
        raise ValueError("CyberDuck V2 source ankle motor mapping is invalid.")
    mimic = {}
    for index in range(model.neq):
        if model.eq_type[index] != mujoco.mjtEq.mjEQ_JOINT:
            raise ValueError("CyberDuck V2 contains an unexpected equality type.")
        follower = model.joint(int(model.eq_obj1id[index])).name
        driver = model.joint(int(model.eq_obj2id[index])).name
        mimic[follower] = driver
        if tuple(model.eq_data[index, :5]) != (0, robot.MIMIC_MULTIPLIER, 0, 0, 0):
            raise ValueError(f"Unexpected mimic coefficients for {follower}.")
    if mimic != robot.MIMIC_JOINT_MAP:
        raise ValueError("CyberDuck V2 mimic joint mapping is invalid.")
    print("Mimic check passed: 4 rollers follow their ankles at ratio 1.210526.")
    print("Source XML retains two ankle motor examples; the entity replaces them in memory.")

    entity = Entity(robot.get_cyberduck_v2_robot_cfg())
    assembled = entity.compile()
    if (assembled.nq, assembled.nv, assembled.nu, assembled.neq) != (26, 25, 15, 4):
        raise ValueError("CyberDuck V2 mixed-drive entity dimensions are invalid.")
    names = tuple(assembled.actuator(i).name for i in range(assembled.nu))
    targets = tuple(
        assembled.joint(int(assembled.actuator_trnid[i, 0])).name
        for i in range(assembled.nu)
    )
    if names != robot.ACTUATOR_NAMES or targets != robot.ACTUATED_JOINT_NAMES:
        raise ValueError("CyberDuck V2 mixed-drive actuator order is invalid.")
    groups = tuple(tuple(act.target_names) for act in entity.actuators)
    if groups != (
        robot.BRUSHLESS_POSITION_JOINT_NAMES,
        robot.VELOCITY_JOINT_NAMES,
        robot.SERVO_JOINT_NAMES,
    ):
        raise ValueError("CyberDuck V2 position/velocity/servo grouping is invalid.")
    if set(targets).intersection(robot.MIMIC_JOINT_NAMES):
        raise ValueError("CyberDuck V2 follower rollers must not have actuators.")
    print("Mixed-drive entity: nq=26, nv=25, nu=15, neq=4.")
    print("Drive groups: 12 HTDW-3532 NT-PD motors + 3 HD1910 BAM servos.")
    print("Controls: 13 position targets [rad], 2 ankle velocity targets [rad/s].")
    print("Follower rollers have no direct control inputs.")
    for name in targets:
        mode = "velocity [rad/s]" if name in robot.VELOCITY_JOINT_NAMES else "position [rad]"
        print(f"  {name:<24} {robot.JOINT_TO_MOTOR_MODEL[name]:<20} {mode}")
    print("Controller gains, effort limits and delays are simulation defaults.")
    print("Default pose uses bent legs and a retracted neck; hardware stability is unverified.")


def _check_ht_microduck(
    model: mujoco.MjModel, joint_names: tuple[str, ...]
) -> None:
    """保留现有 HT 机器人电机分组与传感器检查。"""
    if set(ht_microduck_constants.JOINT_TO_MOTOR_MODEL) != set(joint_names):
        raise ValueError("The motor mapping must cover every HT Microduck joint.")
    print("HT Microduck joint order and motor mapping checks passed.")

    sensor_names = tuple(model.sensor(index).name for index in range(model.nsensor))
    imu = model.site("imu")
    imu_body = model.body(int(imu.bodyid[0])).name
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    start = model.sensor("imu_upvector").adr[0]
    up = data.sensordata[start : start + 3]
    print(
        f"IMU site: imu on {imu_body}; {len(sensor_names)} sensors "
        f"({', '.join(sensor_names)}); upright up vector: {up.round(6).tolist()}"
    )
    print("IMU and root angular momentum readings are ideal simulation values.")

    if model.nu == 0:
        print("Source MJCF is passive; the entity factory adds 3532 PD and HD1910 BAM.")


if __name__ == "__main__":
    main()
