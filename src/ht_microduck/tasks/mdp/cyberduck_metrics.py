# Copyright (c) 2026-2027 zh
"""
内容：
    计算 CyberDuck V2 四轮接触点滑移、皮带等效约束误差与驱动力矩饱和指标。

滑移只描述静止地面上每轮最大接触力对应的代表物质点，不代表全部接触斑。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.manager_base import ManagerTermBase
from mjlab.utils.lab_api.math import quat_apply

from ht_microduck.robot.cyberduck_v2_constants import (
    BRUSHLESS_JOINT_NAMES,
    MIMIC_JOINT_MAP,
    MIMIC_JOINT_NAMES,
    MIMIC_MULTIPLIER,
    VELOCITY_JOINT_NAMES,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def contact_tangent_velocity(
    origin_w: torch.Tensor,
    linear_velocity_w: torch.Tensor,
    angular_velocity_w: torch.Tensor,
    contact_position_w: torch.Tensor,
    contact_normal_w: torch.Tensor,
    contact: torch.Tensor,
) -> torch.Tensor:
    """返回轮固定物质点的世界系切向速度 [B,4,3] m/s，离地列清零。

    原点位置与线速度须对应同一刚体参考点；角速度包含基座、腿部与轮自身转动。
    法向来自传感器，方向不影响切平面投影。当前接口的地面静止。
    """
    velocity = linear_velocity_w + torch.cross(
        angular_velocity_w, contact_position_w - origin_w, dim=-1
    )
    normal = torch.nn.functional.normalize(contact_normal_w, dim=-1)
    tangent = velocity - (velocity * normal).sum(dim=-1, keepdim=True) * normal
    return torch.where(contact[..., None], tangent, 0.0)


class WheelDriveMetrics:
    """缓存模型索引；采样返回环境设备上的张量，不写日志或改变动力学。"""

    def __init__(self, env: ManagerBasedRlEnv):
        self.env = env
        self.robot = env.scene["robot"]
        self.load_sensor = env.scene["wheel_ground_contact"]
        self.slip_sensor = env.scene["wheel_rolling_contact"]
        expected = tuple(name.replace("_joint", "_collision") for name in MIMIC_JOINT_NAMES)
        for sensor in (self.load_sensor, self.slip_sensor):
            names = tuple(name.rsplit("/", 1)[-1] for name in sensor.primary_names)
            if names != expected:
                raise ValueError("CyberDuck wheel metrics require right-back/front, left-back/front sensor order")
        self.wheel_ids, _ = self.robot.find_joints(MIMIC_JOINT_NAMES, preserve_order=True)
        self.ankle_ids, _ = self.robot.find_joints(VELOCITY_JOINT_NAMES, preserve_order=True)
        driver_names = tuple(MIMIC_JOINT_MAP[name] for name in MIMIC_JOINT_NAMES)
        self.driver_ids = [self.robot.joint_names.index(name) for name in driver_names]
        body_names = tuple(name.replace("_joint", "_link") for name in MIMIC_JOINT_NAMES)
        self.body_ids, _ = self.robot.find_bodies(body_names, preserve_order=True)
        self.ankle_ctrl_ids, _ = self.robot.find_actuators(VELOCITY_JOINT_NAMES, preserve_order=True)
        self.nt_ctrl_ids, _ = self.robot.find_actuators(BRUSHLESS_JOINT_NAMES, preserve_order=True)
        self.ankle_nt_ids = [BRUSHLESS_JOINT_NAMES.index(name) for name in VELOCITY_JOINT_NAMES]

    def sample(self) -> dict[str, torch.Tensor]:
        """按右后/右前/左后/左前返回四轮指标，驱动顺序沿用实体的 15 路顺序。"""
        robot = self.robot
        data = robot.data
        load = self.load_sensor.data
        representative = self.slip_sensor.data
        contact = representative.found > 0
        tangent = contact_tangent_velocity(
            data.body_link_pos_w[:, self.body_ids],
            data.body_link_lin_vel_w[:, self.body_ids],
            data.body_link_ang_vel_w[:, self.body_ids],
            representative.pos,
            representative.normal,
            contact,
        )
        # 当前任务为水平平地，净法向载荷直接取世界 Z 分量，不依赖代表点是否保留。
        normal = torch.nn.functional.normalize(representative.normal, dim=-1)
        normal_load = load.force[..., 2].abs()
        normal_load = torch.where(load.found > 0, normal_load, 0.0)
        local_axis = torch.zeros_like(tangent)
        local_axis[..., 1] = 1.0
        axis = quat_apply(data.body_link_quat_w[:, self.body_ids], local_axis)
        rolling = torch.nn.functional.normalize(torch.cross(axis, -normal, dim=-1), dim=-1)
        lateral = torch.cross(-normal, rolling, dim=-1)

        ctrl_ids = robot.indexing.ctrl_ids
        force = self.env.sim.data.actuator_force[:, ctrl_ids]
        nt_ids = ctrl_ids[self.nt_ctrl_ids]
        ranges = self.env.sim.model.actuator_forcerange[:, nt_ids]
        # 原生 affine PD 的请求值用于区分零包络下的被限幅请求和真正的零力矩。
        bias = self.env.sim.model.actuator_biasprm[:, nt_ids]
        request = (
            self.env.sim.data.ctrl[:, nt_ids] + bias[..., 0]
            + bias[..., 1] * self.env.sim.data.actuator_length[:, nt_ids]
            + bias[..., 2] * self.env.sim.data.actuator_velocity[:, nt_ids]
        )
        saturation = (request > ranges[..., 1] + 1.0e-5) | (request < ranges[..., 0] - 1.0e-5)
        position_error = data.joint_pos[:, self.wheel_ids] - MIMIC_MULTIPLIER * data.joint_pos[:, self.driver_ids]
        velocity_error = data.joint_vel[:, self.wheel_ids] - MIMIC_MULTIPLIER * data.joint_vel[:, self.driver_ids]
        return {
            "ankle_velocity_rad_s": data.joint_vel[:, self.ankle_ids],
            "wheel_velocity_rad_s": data.joint_vel[:, self.wheel_ids],
            "root_linear_velocity_b": data.root_link_lin_vel_b,
            "root_angular_velocity_b": data.root_link_ang_vel_b,
            "wheel_normal_load_n": normal_load,
            "wheel_contact": load.found > 0,
            "wheel_slip_contact": contact,
            "contact_tangent_velocity_w_m_s": tangent,
            "wheel_slip_speed_m_s": torch.linalg.vector_norm(tangent, dim=-1),
            "wheel_longitudinal_slip_m_s": (tangent * rolling).sum(dim=-1),
            "wheel_lateral_slip_m_s": (tangent * lateral).sum(dim=-1),
            "mimic_position_error_rad": position_error,
            "mimic_velocity_error_rad_s": velocity_error,
            "mimic_position_abs_error_rad": position_error.abs(),
            "mimic_velocity_abs_error_rad_s": velocity_error.abs(),
            "actuator_torque_nm": force,
            # BAM 已在内部做电压/力矩裁剪，现有输出不足以恢复完整饱和状态；此处仅统计 NT。
            "nt_actuator_saturation": saturation,
            "ankle_saturation": saturation[:, self.ankle_nt_ids],
        }


class WheelDriveMetric(ManagerTermBase):
    """将物理指标适配到 mjlab MetricsManager 的逐环境标量接口。"""

    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(env)
        del cfg
        self.sampler = WheelDriveMetrics(env)

    def __call__(self, env: ManagerBasedRlEnv, field: str, index: int | None = None) -> torch.Tensor:
        del env
        value = self.sampler.sample()[field].float()
        return value.mean(dim=-1) if index is None else value[:, index]
