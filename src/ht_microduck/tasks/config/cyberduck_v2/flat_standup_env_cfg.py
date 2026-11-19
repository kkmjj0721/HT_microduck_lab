# Copyright (c) 2026-2027 zh
"""
内容：
    装配 CyberDuck V2 的摔倒起立任务：五类倒地初态课程、起立奖励与成功判据。

初态与奖励思路参照 pollen-robotics/microduck_rl@bae39f59 的官方 StandUp 配方
（Apache-2.0，本项目已移植为 ht_microduck/flat_standup_env_cfg.py）；本配置不是官方
数值复现：机器人、质量分布、动作接口与高度参考全部按本机新模型重标。
奖励、课程与终止均为待训练验证的仿真假设，不代表已收敛的策略行为。
"""

from __future__ import annotations

import math
from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg, mdp
from mjlab.envs.mdp import dr
from mjlab.managers import (
    CurriculumTermCfg,
    EventTermCfg,
    MetricsTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import UniformNoiseCfg
from mjlab.viewer import ViewerConfig

from ht_microduck.actuator import bam_init, htdw3532_init
from ht_microduck.robot.cyberduck_v2_constants import (
    COLLISION_GEOM_NAMES,
    get_cyberduck_v2_robot_cfg,
)
from ht_microduck.tasks import cyberduck_v2_standup_contract as C
from ht_microduck.tasks.mdp import cyberduck_standup_rewards as rewards
from ht_microduck.tasks.mdp.cyberduck_actions import (
    CyberDuckJointVelocityActionCfg,
)
from ht_microduck.tasks.mdp.cyberduck_observations import (
    clipped_last_action,
    wheel_contact,
)
from ht_microduck.tasks.mdp.cyberduck_roulade_actions import RouladePositionActionCfg
from ht_microduck.tasks.mdp.cyberduck_standup_events import (
    init_standup_geometry,
    reset_standup_state,
)
from ht_microduck.tasks.mdp.cyberduck_standup_metrics import (
    standup_both_sides_metric,
    standup_height_metric,
    standup_pose_metric,
    standup_success,
    standup_tilt_metric,
)
from ht_microduck.tasks.mdp.official_curriculums import (
    reward_weight,
    reward_weight_ramp,
)
from ht_microduck.tasks.mdp.official_events import (
    randomize_bam_friction,
    robot_state_is_nan,
)
from ht_microduck.tasks.mdp.official_observations import (
    base_ang_vel_imu_misaligned,
    projected_gravity_imu_misaligned,
)

# 初态权重顺序固定为 C.SPAWN_POSTURES：standing / sitting / face_down / face_up / side。
SPAWN_WEIGHT_STAGES: tuple[dict, ...] = (
    # 前 600 次更新以站姿与坐姿为主，先把“低姿态到站姿”的短行程学会。
    {"step": 0, "weights": (0.40, 0.30, 0.20, 0.10, 0.00)},
    # 之后逐步加入仰卧与侧卧，倒地类合计超过站姿，逼出真正的翻身起立。
    {"step": 600 * 24, "weights": (0.30, 0.25, 0.25, 0.15, 0.05)},
    {"step": 1500 * 24, "weights": (0.20, 0.20, 0.25, 0.20, 0.15)},
    {"step": 2500 * 24, "weights": (0.15, 0.15, 0.25, 0.25, 0.20)},
)
FINAL_SPAWN_WEIGHTS: tuple[float, ...] = SPAWN_WEIGHT_STAGES[-1]["weights"]


def _spawn_weight_curriculum(
    env,
    env_ids,
    event_name: str,
    weight_stages: tuple[dict, ...],
) -> float:
    """按训练步数把初态权重写回事件参数，使用 live EventManager 配置。

    ``event_param_curriculum`` 只做浅合并并取第一个数值项做日志，这里需要整体替换
    元组，因此单独实现，语义与官方 reward_weight 课程一致（取已到达的最新阶段）。
    """
    del env_ids
    current = weight_stages[0]["weights"]
    for stage in weight_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["weights"]
    env.event_manager.get_term_cfg(event_name).params["spawn_weights"] = current
    return float(sum(current))


def _apply_final_curriculum(cfg: ManagerBasedRlEnvCfg) -> None:
    """play 时把课程快进到末段并删除课程项，避免 viewer 停在 stage 0。"""
    for name, term in list(cfg.curriculum.items()):
        params = term.params
        if "event_name" in params:
            cfg.events[params["event_name"]].params["spawn_weights"] = params["weight_stages"][-1]["weights"]
        elif "ramp_steps" in params:
            cfg.rewards[params["reward_name"]].weight = params["end_weight"]
        elif "weight_stages" in params:
            cfg.rewards[params["reward_name"]].weight = params["weight_stages"][-1]["weight"]
        else:
            raise AssertionError(f"unsupported standup curriculum term: {name}")
        del cfg.curriculum[name]


def make_standup_env_cfg(
    num_envs: int = 4096, seed: int | None = None, play: bool = False
) -> ManagerBasedRlEnvCfg:
    """构造独立起立环境；play 使用同一物理、动作与观测语义。"""
    if num_envs < 1:
        raise ValueError("StandUp num_envs must be positive")
    positions = SceneEntityCfg("robot", joint_names=C.POSITION_JOINTS, preserve_order=True)
    joints = SceneEntityCfg("robot", joint_names=C.POLICY_JOINTS, preserve_order=True)
    base = SceneEntityCfg("robot", body_names=("base_link",))
    head_bodies = SceneEntityCfg("robot", body_names=(
        "neck_pitch_link", "head_pitch_link", "head_yaw_link", "head_roll_link", "r_hip_yaw_link",
    ))
    actor = {
        "base_ang_vel": ObservationTermCfg(
            func=base_ang_vel_imu_misaligned, params={"max_angle_deg": 6.0},
            noise=UniformNoiseCfg(n_min=-0.03, n_max=0.03),
            delay_min_lag=0, delay_max_lag=1, delay_update_period=64,
        ),
        "projected_gravity": ObservationTermCfg(
            func=projected_gravity_imu_misaligned, params={"max_angle_deg": 6.0},
            noise=UniformNoiseCfg(n_min=-0.01, n_max=0.01),
            delay_min_lag=0, delay_max_lag=1, delay_update_period=64,
        ),
        "joint_pos": ObservationTermCfg(
            func=mdp.joint_pos_rel, params={"asset_cfg": positions, "biased": True},
            noise=UniformNoiseCfg(n_min=-0.001, n_max=0.001),
        ),
        "joint_vel": ObservationTermCfg(
            func=mdp.joint_vel_rel, params={"asset_cfg": joints},
            noise=UniformNoiseCfg(n_min=-0.25, n_max=0.25),
            delay_min_lag=1, delay_max_lag=1, delay_update_period=0,
        ),
        "actions": ObservationTermCfg(func=clipped_last_action),
    }
    critic = deepcopy(actor)
    critic["base_ang_vel"] = ObservationTermCfg(func=mdp.base_ang_vel)
    critic["projected_gravity"] = ObservationTermCfg(func=mdp.projected_gravity)
    critic["joint_pos"] = ObservationTermCfg(func=mdp.joint_pos_rel, params={"asset_cfg": deepcopy(positions)})
    critic["joint_vel"] = ObservationTermCfg(func=mdp.joint_vel_rel, params={"asset_cfg": deepcopy(joints)})
    critic["base_lin_vel"] = ObservationTermCfg(func=mdp.base_lin_vel)
    critic["wheel_contact"] = ObservationTermCfg(func=wheel_contact, params={"sensor_name": C.WHEEL_SENSOR})
    sensors = (
        ContactSensorCfg(
            name=C.WHEEL_SENSOR,
            primary=ContactMatch(mode="geom", pattern=C.WHEEL_GEOMS, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found", "force"), reduce="netforce", num_slots=1,
        ),
        ContactSensorCfg(
            name=C.SELF_SENSOR,
            primary=ContactMatch(mode="geom", pattern=COLLISION_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
            fields=("found",), reduce="none", num_slots=1,
        ),
    )
    task_rewards = {
        # 主任务：站到参考高度。
        "height": RewardTermCfg(
            func=rewards.standup_height, weight=2.0,
            params={"std": 0.04, "target_height": C.SUPPORT_HEIGHT},
        ),
        "height_sharp": RewardTermCfg(
            func=rewards.standup_height, weight=1.5,
            params={"std": 0.015, "target_height": C.SUPPORT_HEIGHT},
        ),
        # 直立必须叠加高度门控：只做直立会让坐姿（躯干竖直、根高 0.10 m）拿满分。
        "upright": RewardTermCfg(
            func=rewards.standup_upright, weight=1.5,
            params={"upright_std": 0.4},
        ),
        "standing_composite": RewardTermCfg(
            func=rewards.standup_standing_composite, weight=3.5,
            params={"height_std": 0.04, "upright_std": 0.4, "pose_std": 0.4,
                    "target_height": C.SUPPORT_HEIGHT},
        ),
        # 参考站姿：正向奖励，躺平/坐姿因站立核拿不到。
        "stance_pose": RewardTermCfg(
            func=rewards.standup_stance_pose, weight=2.0,
            params={"pose_std": 0.25, "target_height": C.SUPPORT_HEIGHT},
        ),
        "yaw_roll_pose": RewardTermCfg(
            func=rewards.standup_yaw_roll_pose, weight=3.0,
            params={"pose_std": 0.10, "target_height": C.SUPPORT_HEIGHT},
        ),
        # 低头换重心：根高不变但 COM 下沉，只有 COM 项能看见。
        "com_height": RewardTermCfg(
            func=rewards.standup_com_height, weight=1.0,
            params={"height_std": 0.03, "target_height": C.COM_HEIGHT},
        ),
        # 起身过程反馈：upward velocity 只在未到目标高度时支付；
        # potential 只支付历史最高势能的增量，防止原地摇晃刷分。
        "rise_velocity": RewardTermCfg(
            func=rewards.standup_rise_velocity, weight=1.0,
            params={"max_height": C.SUPPORT_HEIGHT},
        ),
        "rise_potential": RewardTermCfg(func=rewards.standup_rise_potential, weight=2.0),
        # 倒地阶段的连续信号：倾角从 100° 收到 20° 时从 0 升到 1，不奖励躺平。
        "flat_recovery": RewardTermCfg(
            func=rewards.standup_flat_recovery, weight=1.5,
            params={"tilt_full_deg": 100.0, "tilt_zero_deg": 20.0},
        ),
        # 起身全程密集信号：根高与直立度的几何平均，没有任何高度阈值。
        # 2026-11-18 首次 1800 秒训练实测：倒地初态根高 0.09–0.13 m 时
        # height(std 0.04)=1e-6、height_sharp(std 0.015)=0、站立类奖励因站立核全 0，
        # 策略最优解变成"躺平不动"（倒地类 0/24 成功、末秒根高 0.118 m）。
        # 本项与 roulade_roll_continuity 同构，直接填满该真空。
        "rise_continuity": RewardTermCfg(
            func=rewards.standup_rise_continuity, weight=4.0,
            params={"tilt_full_deg": 100.0, "tilt_zero_deg": 20.0},
        ),
        # 站立段静止与平滑：全部乘站立核，落地前不生效。
        "settle": RewardTermCfg(
            func=rewards.standup_settle, weight=3.0,
            params={"max_linear_speed": C.SUCCESS_LINEAR_SPEED,
                    "max_angular_speed": C.SUCCESS_ANGULAR_SPEED},
        ),
        "stand_still": RewardTermCfg(
            func=rewards.standup_stand_still, weight=2.0, params={"speed_std": 0.5},
        ),
        "stand_action_rate": RewardTermCfg(
            func=rewards.standup_stand_action_rate, weight=0.0, params={"joint_std": 0.3},
        ),
        "stand_angvel": RewardTermCfg(
            func=rewards.standup_stand_angvel, weight=-0.5,
            params={"max_angular_speed": C.SUCCESS_ANGULAR_SPEED},
        ),
        "both_sides": RewardTermCfg(func=rewards.standup_both_sides, weight=1.0),
        # 头颈姿态：正向奖励朝上，负向压偏离参考站姿。
        "head_upright": RewardTermCfg(func=rewards.standup_head_upright, weight=1.0),
        "neck_pose_l2": RewardTermCfg(func=rewards.standup_neck_pose_l2, weight=-0.6),
        # 通用代价项。
        "action_rate_l2": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.1),
        "joint_torque_rate_l2": RewardTermCfg(func=rewards.standup_joint_torque_rate_l2, weight=0.0),
        "body_ang_vel": RewardTermCfg(
            func=velocity_mdp.body_angular_velocity_penalty, weight=-0.01,
            params={"asset_cfg": deepcopy(base)},
        ),
        "dof_pos_limits": RewardTermCfg(
            func=mdp.joint_pos_limits, weight=-1.0, params={"asset_cfg": deepcopy(positions)},
        ),
        "gentle_rise": RewardTermCfg(func=rewards.standup_trunk_vertical_accel, weight=0.002),
        "self_collisions": RewardTermCfg(
            func=velocity_mdp.self_collision_cost, weight=-0.5,
            params={"sensor_name": C.SELF_SENSOR},
        ),
    }
    events = {
        "htdw3532_init": EventTermCfg(func=htdw3532_init, mode="startup"),
        "bam_init": EventTermCfg(func=bam_init, mode="startup"),
        "standup_geometry": EventTermCfg(func=init_standup_geometry, mode="startup"),
        "foot_friction": EventTermCfg(func=dr.geom_friction, mode="startup",
                                      params={"asset_cfg": SceneEntityCfg("robot", geom_names=C.WHEEL_GEOMS),
                                              "operation": "abs", "ranges": (0.7, 1.3), "shared_random": True}),
        "encoder_bias": EventTermCfg(func=dr.encoder_bias, mode="startup",
                                     params={"asset_cfg": deepcopy(positions), "bias_range": (-0.015, 0.015)}),
        "base_com": EventTermCfg(func=dr.body_com_offset, mode="startup",
                                 params={"asset_cfg": deepcopy(base), "operation": "add",
                                         "ranges": {0: (-0.025, 0.025), 1: (-0.025, 0.025), 2: (-0.03, 0.03)}}),
        "randomize_mass_inertia": EventTermCfg(func=dr.pseudo_inertia, mode="startup",
                                               params={"asset_cfg": deepcopy(base),
                                                       "alpha_range": (math.log(0.95) / 2, math.log(1.05) / 2)}),
        "reset_scene": EventTermCfg(func=mdp.reset_scene_to_default, mode="reset"),
        "randomize_com": EventTermCfg(func=dr.body_ipos, mode="reset",
                                      params={"asset_cfg": deepcopy(base), "operation": "add", "ranges": (-0.003, 0.003)}),
        "randomize_head_com": EventTermCfg(func=dr.body_ipos, mode="reset",
                                           params={"asset_cfg": head_bodies, "operation": "add", "ranges": (-0.003, 0.003)}),
        "randomize_armature": EventTermCfg(func=dr.joint_armature, mode="reset",
                                           params={"asset_cfg": deepcopy(joints), "operation": "scale", "ranges": (0.9, 1.1)}),
        "randomize_joint_friction": EventTermCfg(func=randomize_bam_friction, mode="reset",
                                                 params={"scale_range": (0.9, 1.1)}),
        "set_standup_state": EventTermCfg(
            func=reset_standup_state, mode="reset",
            params={"spawn_weights": FINAL_SPAWN_WEIGHTS if play else SPAWN_WEIGHT_STAGES[0]["weights"],
                    "joint_noise_std": C.SPAWN_JOINT_NOISE_STD},
        ),
    }
    # 课程无论 play 与否都先建立，play 末尾统一快进到末段再删除；
    # 若只在训练时建立，play 会停在初始权重（前滚翻 Recovery 踩过同类问题）。
    curriculum = {"standup_spawn_mix": CurriculumTermCfg(
        func=_spawn_weight_curriculum,
        params={"event_name": "set_standup_state",
                "weight_stages": tuple(
                    {"step": stage["step"], "weights": stage["weights"]}
                    for stage in SPAWN_WEIGHT_STAGES
                )},
    )}
    # 站立段平滑与静止项：等策略能站起来之后再加重，否则会压住探索。
    for name, reward, start, end, ramp, delay in (
        ("settle_weight", "settle", 3.0, 10.0, 300 * 24, 600 * 24),
        ("stand_still_weight", "stand_still", 2.0, 6.0, 300 * 24, 400 * 24),
        ("stand_action_rate_weight", "stand_action_rate", 0.0, 8.0, 400 * 24, 600 * 24),
        ("stand_angvel_weight", "stand_angvel", -0.5, -1.5, 400 * 24, 600 * 24),
        ("neck_pose_weight", "neck_pose_l2", -0.6, -1.6, 300 * 24, 300 * 24),
        ("head_upright_weight", "head_upright", 1.0, 2.5, 300 * 24, 300 * 24),
        ("yaw_roll_pose_weight", "yaw_roll_pose", 3.0, 8.0, 400 * 24, 200 * 24),
        ("stance_pose_weight", "stance_pose", 2.0, 10.0, 600 * 24, 0),
        ("action_rate_weight", "action_rate_l2", -0.1, -0.4, 600 * 24, 0),
    ):
        curriculum[name] = CurriculumTermCfg(
            func=reward_weight_ramp,
            params={"reward_name": reward, "start_weight": start, "end_weight": end,
                    "ramp_steps": ramp, "delay_steps": delay},
        )
    curriculum["torque_rate_weight"] = CurriculumTermCfg(
        func=reward_weight,
        params={"reward_name": "joint_torque_rate_l2",
                "weight_stages": [{"step": 0, "weight": 0.0},
                                  {"step": 2500 * 24, "weight": -5e-4},
                                  {"step": 3500 * 24, "weight": -1e-3}]},
    )
    curriculum["rise_potential_weight"] = CurriculumTermCfg(
        func=reward_weight,
        params={"reward_name": "rise_potential",
                "weight_stages": [{"step": 0, "weight": 2.0},
                                  {"step": 1500 * 24, "weight": 3.0},
                                  {"step": 3000 * 24, "weight": 4.0}]},
    )
    cfg = ManagerBasedRlEnvCfg(
        scene=SceneCfg(num_envs=num_envs, env_spacing=2.0,
                       terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": get_cyberduck_v2_robot_cfg()}, sensors=sensors),
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=C.PHYSICS_TIMESTEP), nconmax=128, njmax=1500),
        decimation=C.DECIMATION, episode_length_s=C.EPISODE_LENGTH_S, seed=seed,
        viewer=ViewerConfig(entity_name="robot", body_name="base_link", distance=1.2),
        observations={"actor": ObservationGroupCfg(terms=actor, enable_corruption=not play),
                      "critic": ObservationGroupCfg(terms=critic, enable_corruption=False)},
        actions={
            "joint_pos": RouladePositionActionCfg(
                entity_name="robot", actuator_names=C.POSITION_JOINTS, preserve_order=True,
                use_default_offset=True,
            ),
            "joint_vel": CyberDuckJointVelocityActionCfg(
                entity_name="robot", actuator_names=C.VELOCITY_JOINTS, preserve_order=True,
                scale=C.VELOCITY_SCALE, raw_action_limit=C.VELOCITY_ACTION_LIMIT,
                use_default_offset=True,
                clip={".*": (-C.VELOCITY_TARGET_LIMIT, C.VELOCITY_TARGET_LIMIT)},
            ),
        },
        commands={}, events=events, rewards=task_rewards, curriculum=curriculum,
        metrics={
            "standup_success": MetricsTermCfg(func=standup_success, reduce="max"),
            "standup_height_error": MetricsTermCfg(func=standup_height_metric, reduce="mean"),
            "standup_tilt": MetricsTermCfg(func=standup_tilt_metric, reduce="mean"),
            "standup_pose_rms": MetricsTermCfg(func=standup_pose_metric, reduce="mean"),
            "standup_both_sides": MetricsTermCfg(func=standup_both_sides_metric, reduce="mean"),
        },
        terminations={"time_out": TerminationTermCfg(func=mdp.time_out, time_out=True),
                      "nan_state": TerminationTermCfg(func=robot_state_is_nan)},
    )
    if play:
        _apply_final_curriculum(cfg)
    return cfg


__all__ = ["FINAL_SPAWN_WEIGHTS", "SPAWN_WEIGHT_STAGES", "make_standup_env_cfg"]
