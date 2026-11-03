# Copyright (c) 2026-2027 zh
"""前坐课程的物理初态写入与新回合动作、目标和延迟历史初始化。

端点来自真实执行器保持后的采样；本模块恢复物理状态，再以当前保持命令回填历史。
这不是动态轨迹的精确恢复：不复制求解器载荷，BAM仍采用原生新回合载荷无效语义。
局部回填本身不推进邻居；公开环境reset中的全批控制刷新仍沿用mjlab。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import torch

from ht_microduck.tasks.mdp.actions import (
    BoundedJointPositionAction,
    BoundedJointPositionActionCfg,
)

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def set_forward_initial_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    *,
    root_pose: torch.Tensor,
    root_velocity: torch.Tensor,
    joint_pos: torch.Tensor,
    joint_vel: torch.Tensor,
    position_target: torch.Tensor,
) -> None:
    """在reset事件中写入初态，动作管理器随后负责恢复保持命令。

    根位姿为相对各环境原点的xyz与世界系wxyz四元数；根速度为世界系线速度、角速度。
    三个关节张量均使用实体15关节顺序，单位依次为rad、rad/s、rad。
    输入只在此入口转换并校验；写入后由正常环境reset统一刷新派生物理量。
    """
    robot = env.scene["robot"]
    if env_ids.ndim != 1 or env_ids.dtype not in (torch.int32, torch.int64):
        raise ValueError("Environment IDs must be a one-dimensional integer tensor.")
    env_ids = env_ids.to(device=env.device, dtype=torch.long)
    if ((env_ids < 0) | (env_ids >= env.num_envs)).any():
        raise ValueError("Environment IDs are outside the environment batch.")
    count = len(env_ids)
    width = robot.data.default_joint_pos.shape[1]
    values = {
        "root_pose": (root_pose, 7),
        "root_velocity": (root_velocity, 6),
        "joint_pos": (joint_pos, width),
        "joint_vel": (joint_vel, width),
        "position_target": (position_target, width),
    }
    prepared = {}
    for name, (value, columns) in values.items():
        tensor = torch.as_tensor(
            value, device=env.device, dtype=robot.data.default_joint_pos.dtype
        )
        if tensor.shape != (count, columns) or not torch.isfinite(tensor).all():
            raise ValueError(
                f"{name} must have shape ({count}, {columns}) and finite values."
            )
        prepared[name] = tensor
    pose = prepared["root_pose"].clone()
    if not torch.allclose(
        torch.linalg.vector_norm(pose[:, 3:7], dim=-1),
        torch.ones(count, device=env.device),
        atol=1e-4,
        rtol=0.0,
    ):
        raise ValueError("Root quaternions must be normalized.")
    limits = robot.data.joint_pos_limits[env_ids]
    target = prepared["position_target"]
    if ((target < limits[..., 0]) | (target > limits[..., 1])).any():
        raise ValueError("Initial position targets must respect physical joint limits.")
    pose[:, :3] += env.scene.env_origins[env_ids]
    robot.write_root_link_pose_to_sim(pose, env_ids=env_ids)
    robot.write_root_link_velocity_to_sim(prepared["root_velocity"], env_ids=env_ids)
    robot.write_joint_state_to_sim(
        prepared["joint_pos"], prepared["joint_vel"], env_ids=env_ids
    )
    env._forward_initial_target[env_ids] = target


def capture_forward_state(env: ManagerBasedRlEnv) -> dict[str, np.ndarray]:
    """采集已完成正常forward刷新的物理端点及当前保持目标，返回独立CPU数组。

    根位姿平移到环境原点；速度、四元数仍在世界系。这里只记录五项初始化输入，
    不将中间运动帧称为包含执行器历史和派生接触力的完整仿真快照。
    """
    robot = env.scene["robot"]
    pose = robot.data.root_link_pose_w.clone()
    pose[:, :3] -= env.scene.env_origins
    values = {
        "root_pose": pose,
        "root_velocity": robot.data.root_link_vel_w,
        "joint_pos": robot.data.joint_pos,
        "joint_vel": robot.data.joint_vel,
        "position_target": robot.data.joint_pos_target,
    }
    return {name: value.detach().cpu().numpy().copy() for name, value in values.items()}


@dataclass(kw_only=True)
class ForwardInitializedJointPositionActionCfg(BoundedJointPositionActionCfg):
    """沿用HOME加动作映射，在reset后按实际初态恢复保持命令。"""

    def build(self, env: ManagerBasedRlEnv) -> ForwardInitializedJointPositionAction:
        return ForwardInitializedJointPositionAction(self, env)


class ForwardInitializedJointPositionAction(BoundedJointPositionAction):
    """仅在新回合初始化动作与延迟；实际策略动作沿用原有物理限幅。"""

    def __init__(
        self, cfg: ForwardInitializedJointPositionActionCfg, env: ManagerBasedRlEnv
    ):
        super().__init__(cfg, env)
        env._forward_initial_target = self._entity.data.default_joint_pos.clone()
        # 首次真实reset前分配原生存储；本动作项后续局部回填不推进邻居指针。
        for actuator in self._entity.actuators:
            buffer = actuator._delay_buffer
            if buffer is not None and not buffer.is_initialized:
                ids = actuator.target_ids
                data = self._entity.data
                buffer.append(
                    torch.stack(
                        (
                            data.joint_pos_target[:, ids],
                            data.joint_vel_target[:, ids],
                            data.joint_effort_target[:, ids],
                        ),
                        dim=-1,
                    )
                )

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        ids = torch.arange(self.num_envs, device=self.device)
        if env_ids is not None:
            ids = ids[env_ids]
        super().reset(ids)
        robot = self._entity
        targets = self._env._forward_initial_target[ids]
        physical = targets[:, self._target_ids]
        bias = robot.data.encoder_bias[ids][:, self._target_ids]
        offset = self._offset if isinstance(self._offset, float) else self._offset[ids]
        scale = self._scale if isinstance(self._scale, float) else self._scale[ids]
        raw = (physical + bias - offset) / scale
        self._raw_actions[ids] = raw
        self._processed_actions[ids] = physical + bias
        self._requested_targets[ids] = physical
        self._applied_targets[ids] = physical
        for history in (
            self._env.action_manager.action,
            self._env.action_manager.prev_action,
            self._env.action_manager.prev_prev_action,
        ):
            history[ids] = raw
        robot.set_joint_position_target(targets, env_ids=ids)
        zeros = torch.zeros_like(targets)
        robot.set_joint_velocity_target(zeros, env_ids=ids)
        robot.set_joint_effort_target(zeros, env_ids=ids)
        for actuator in robot.actuators:
            buffer = actuator._delay_buffer
            if buffer is not None:
                columns = actuator.target_ids
                data = robot.data
                buffer.backfill(
                    torch.stack(
                        (
                            data.joint_pos_target[:, columns],
                            data.joint_vel_target[:, columns],
                            data.joint_effort_target[:, columns],
                        ),
                        dim=-1,
                    ),
                    ids,
                )
