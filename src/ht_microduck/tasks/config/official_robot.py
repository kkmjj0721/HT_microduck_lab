# Copyright (c) 2026-2027 zh
"""将官方任务映射到 HT 机器人，保留 VelStand 的原有行为。

仅处理本机命名、保持 HOME 的嘴、执行器初始化和姿态参考；奖励权重、命令分布及课程
保留在官方任务配方中。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

import mujoco
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import EventTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ObjRef, TerrainHeightSensorCfg

from ht_microduck.actuator.HD_1910_C001 import bam_init
from ht_microduck.actuator.HTDW_3532_02_DNE import htdw3532_init
from ht_microduck.robot.ht_microduck_constants import FOOT_SITE_NAMES, HOME_FRAME
from ht_microduck.tasks import contract as C

STAND_Z = C.STAND_Z
SIT_Z = C.SIT_Z
# HOME 关节下，真实碰撞网格在 pitch ±90° 的名义几何支撑高度；不是动态平衡实测值。
FACE_DOWN_SUPPORT_Z = 0.11338914768149877
FACE_UP_SUPPORT_Z = 0.095
LEG_JOINT_INDICES = tuple(range(len(C.LEG_JOINT_NAMES)))
HEAD_JOINT_INDICES = tuple(range(len(C.LEG_JOINT_NAMES), C.ACTION_DIM))
SITTING_JOINT_OVERRIDES = {
    C.POLICY_JOINT_NAMES.index(name): value
    for name, value in C.LOW_POSTURE_JOINT_POS.items()
}

_NAME_MAP = {
    "trunk_base": "base_link",
    "left_foot": "l_foot",
    "right_foot": "r_foot",
    "yaw_roll_motion": "head_yaw_link",
    "(bottom_head_shell|jaw_soft)": "head_roll_link",
    # 上游此名称实际挂 right_hip_yaw（轴Z），按关节拓扑映射，不按 roll 字面名称猜测。
    "bearing_roll": "r_hip_yaw_link",
    "neck_pitch": "head_pitch_link",
    "neck": "neck_pitch_link",
}


def _map_name(value: str) -> str:
    if value in _NAME_MAP:
        return _NAME_MAP[value]
    return (
        value.replace("trunk_base", "base_link")
        .replace("left_foot", "l_foot")
        .replace("right_foot", "r_foot")
        .replace("knee", "calf")
    )


def _map_config(value):
    if isinstance(value, str):
        return _map_name(value)
    if isinstance(value, dict):
        return {_map_config(key): _map_config(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        result = [_map_config(item) for item in value]
        return tuple(result) if isinstance(value, tuple) else result
    if isinstance(value, SceneEntityCfg):
        for name in ("body_names", "site_names", "geom_names"):
            setattr(value, name, _map_config(getattr(value, name)))
        if value.joint_names:
            patterns = value.joint_names
            text = str(patterns)
            if "?!passive_|.*neck.*|.*head.*" in text:
                value.joint_names = C.LEG_JOINT_NAMES
            elif "?!passive_" in text or patterns in ((".*",), ".*"):
                value.joint_names = C.POLICY_JOINT_NAMES
            else:
                value.joint_names = _map_config(patterns)
            value.preserve_order = True
        if value.site_names and set(value.site_names) == set(FOOT_SITE_NAMES):
            value.site_names = FOOT_SITE_NAMES
            value.preserve_order = True
        return value
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            if item.init:
                setattr(value, item.name, _map_config(getattr(value, item.name)))
    return value


def _terrain_ray_groups(spec: mujoco.MjSpec) -> None:
    """将 HT 机器人碰撞体移出官方仅地形的射线分组。"""
    for geom in spec.geoms:
        if geom.name.startswith("robot/") and geom.group == 0:
            geom.group = 3


def adapt_official_cfg(
    cfg: ManagerBasedRlEnvCfg, num_envs: int, seed: int | None
) -> ManagerBasedRlEnvCfg:
    """装配官方配方的本机选择器和原生执行器字段。"""
    for group in cfg.observations.values():
        _map_config(group)
        for name in ("joint_pos", "joint_vel"):
            group.terms[name].params["asset_cfg"] = SceneEntityCfg(
                "robot", joint_names=C.POLICY_JOINT_NAMES, preserve_order=True
            )
    for terms in (cfg.rewards, cfg.events, cfg.terminations, cfg.curriculum):
        _map_config(terms)
    _map_config(cfg.scene.sensors)
    cfg.viewer.body_name = _map_name(cfg.viewer.body_name)
    for sensor in cfg.scene.sensors:
        if isinstance(sensor, TerrainHeightSensorCfg):
            sensor.frame = tuple(
                ObjRef(type="site", name=name, entity="robot") for name in FOOT_SITE_NAMES
            )
    if any(isinstance(sensor, TerrainHeightSensorCfg) for sensor in cfg.scene.sensors):
        cfg.scene.spec_fn = _terrain_ray_groups
    action = cfg.actions["joint_pos"]
    action.actuator_names = C.POLICY_JOINT_NAMES
    action.preserve_order = True
    cfg.events["htdw3532_init"] = EventTermCfg(func=htdw3532_init, mode="startup")
    cfg.events["bam_init"] = EventTermCfg(func=bam_init, mode="startup")
    if "encoder_bias" in cfg.events:
        cfg.events["encoder_bias"].params["asset_cfg"] = SceneEntityCfg(
            "robot", joint_names=C.POLICY_JOINT_NAMES, preserve_order=True
        )
    if "body_pose_tracking" in cfg.rewards:
        term = cfg.rewards["body_pose_tracking"]
        if term.func.__name__ == "body_pose_tracking_locomotion":
            term.params["feet_cfg"] = SceneEntityCfg(
                "robot", site_names=FOOT_SITE_NAMES, preserve_order=True
            )
    # 官方实体默认根高为零，z 范围因此是绝对高度；HT 实体已有 HOME 根高，先换参考再扣除它。
    # 保留原均匀分布和带宽，不因本机更怕落体冲击而取消高度随机化。
    if "reset_base" in cfg.events:
        pose = cfg.events["reset_base"].params["pose_range"]
        if "z" in pose:
            pose["z"] = tuple(value - 0.115 + STAND_Z - HOME_FRAME.pos[2] for value in pose["z"])
    if "set_ground_state" in cfg.events:
        params = cfg.events["set_ground_state"].params
        for prefix, source_z, target_z in (
            ("standing", 0.115, STAND_Z),
            ("sitting", 0.060, SIT_Z),
        ):
            for suffix in ("min", "max"):
                key = f"{prefix}_z_{suffix}"
                if key in params:
                    params[key] += target_z - source_z
        # 官方前躺平衡参考为 0.044 m；保持原高度余隙和 4 cm 带宽，分别映射本机前后躺支撑面。
        params["face_down_z_offset"] = FACE_DOWN_SUPPORT_Z - 0.044
        params["face_up_z_offset"] = FACE_UP_SUPPORT_Z - 0.044
    cfg.scene.num_envs = num_envs
    cfg.seed = seed
    return cfg
