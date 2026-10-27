"""Compile the robot, verify joint assignments, and optionally preview its pose."""

import argparse
import time

import mujoco

from ht_microduck.robots.ht_microduck.ht_microduck_constants import (
    JOINT_NAMES,
    JOINT_TO_MOTOR_MODEL,
    MJCF_PATH,
    get_ht_microduck_robot_cfg,
    get_spec,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", action="store_true", help="打开静态模型预览。")
    args = parser.parse_args()

    model = get_spec().compile()
    joint_ids = [
        index
        for index in range(model.njnt)
        if model.jnt_type[index] != mujoco.mjtJoint.mjJNT_FREE
    ]
    joint_names = tuple(model.joint(index).name for index in joint_ids)
    if joint_names != JOINT_NAMES:
        raise ValueError(
            f"模型关节或顺序与 ht_microduck_constants.py 不一致：\n"
            f"模型：{joint_names}\n映射：{JOINT_NAMES}"
        )
    if set(JOINT_TO_MOTOR_MODEL) != set(joint_names):
        raise ValueError("电机映射未恰好覆盖所有模型关节。")

    print(f"模型编译通过：{MJCF_PATH}")
    print(f"关节数：{len(joint_names)}，网格数：{model.nmesh}")
    print(f"nq={model.nq}, nv={model.nv}, nu={model.nu}")
    print(f"总质量：{model.body_mass.sum():.4f} kg")
    planes = sum(
        1 for index in range(model.ngeom)
        if model.geom_type[index] == mujoco.mjtGeom.mjGEOM_PLANE
    )
    if planes or model.nlight:
        raise ValueError(
            "机器人 XML 只应包含本体："
            f"发现 {planes} 个平面、{model.nlight} 个光源；"
            "地面与灯光由 mjlab 场景提供"
        )
    print("本体检查：无平面、无灯光；地面与灯光由 mjlab 场景提供")
    for index in joint_ids:
        name = model.joint(index).name
        lower, upper = model.jnt_range[index]
        print(
            f"  {name:<22} {JOINT_TO_MOTOR_MODEL[name]:<20} "
            f"[{lower:.3f}, {upper:.3f}] rad"
        )
    print("关节顺序和电机映射检查通过。")

    sensor_names = tuple(model.sensor(index).name for index in range(model.nsensor))
    imu = model.site("imu")
    imu_body = model.body(int(imu.bodyid[0])).name
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    start = model.sensor("imu_upvector").adr[0]
    up = data.sensordata[start : start + 3]
    print(
        f"IMU site：imu 挂在 {imu_body}，传感器 {len(sensor_names)} 个"
        f"（{'、'.join(sensor_names)}），水平时 up 向量 {up.round(6).tolist()}"
    )
    print("IMU 与根角动量传感器存在；读数为理想值，不含噪声、延迟与安装误差。")

    if model.nu == 0:
        print("原始 MJCF 保持被动；整机工厂另行接入无刷 PD 与 HD1910 BAM。")

    if args.viewer:
        from mjlab.scene import Scene, SceneCfg
        from mjlab.terrains import TerrainEntityCfg
        from mujoco import viewer as mj_viewer

        # Same preview as the official constants module: an mjlab Scene adds the
        # ground plane and sun, so the robot-only XML stays the training asset.
        scene = Scene(
            SceneCfg(
                terrain=TerrainEntityCfg(terrain_type="plane"),
                entities={"robot": get_ht_microduck_robot_cfg()},
            ),
            device="cuda:0",
        )
        scene_model = scene.compile()
        data = mujoco.MjData(scene_model)
        mujoco.mj_forward(scene_model, data)
        with mj_viewer.launch_passive(scene_model, data) as viewer:
            while viewer.is_running():
                viewer.sync()
                time.sleep(1.0 / 60.0)


if __name__ == "__main__":
    main()
