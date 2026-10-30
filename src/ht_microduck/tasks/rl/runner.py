"""Refresh head-pose curricula after upstream checkpoint restoration."""

from __future__ import annotations

from types import MethodType

import torch
from mjlab.rl import MjlabOnPolicyRunner


class OfficialTaskOnPolicyRunner(MjlabOnPolicyRunner):
    """仅给当前任务实例装配官方数值修复，加载后刷新恢复的课程。

    官方 MDP 全局修改 RewardManager 和 PPO；这里绑定相同操作到指定实例，避免影响
    用户要求保留的 VelStand。
    """

    def __init__(self, env, train_cfg: dict, log_dir=None, device="cpu"):
        manager = env.unwrapped.reward_manager
        original_reward_compute = manager.compute

        def finite_rewards(manager, dt):
            result = original_reward_compute(dt)
            for values in manager._episode_sums.values():
                torch.nan_to_num_(values, nan=0.0)
            return torch.nan_to_num(result, nan=0.0)

        manager.compute = MethodType(finite_rewards, manager)
        super().__init__(env, train_cfg, log_dir, device)
        original_returns = self.alg.compute_returns

        def finite_returns(algorithm, observations):
            original_returns(observations)
            torch.nan_to_num_(algorithm.storage.advantages, nan=0.0, posinf=0.0, neginf=0.0)
            torch.nan_to_num_(algorithm.storage.returns, nan=0.0, posinf=0.0, neginf=0.0)

        self.alg.compute_returns = MethodType(finite_returns, self.alg)

    def load(
        self,
        path: str,
        load_cfg: dict | None = None,
        strict: bool = True,
        map_location: str | None = None,
    ) -> dict:
        infos = super().load(path, load_cfg, strict, map_location)
        self.env.reset()
        return infos


class VelocityHeadOnPolicyRunner(OfficialTaskOnPolicyRunner):
    """保留 Head 任务已经注册的 runner 名称。"""
