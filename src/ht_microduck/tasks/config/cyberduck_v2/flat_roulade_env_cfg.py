# Copyright (c) 2026-2027 zh
"""
内容：
    按官方 Roulade 方法装配 CyberDuck V2 的无参考动作前滚翻任务。

来源：pollen-robotics/microduck_rl@bae39f59/microduck_roulade_env_cfg.py，Apache-2.0。
make_roulade_env_cfg保留官方奖励及课程数值；机器人接口独立适配。
make_recovery_env_cfg另做本机动作、恢复奖励和初态课程实验，不能当作官方原配方。
"""

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
from mjlab.sensor import BuiltinSensorCfg, ContactMatch, ContactSensorCfg, ObjRef
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
from ht_microduck.tasks import cyberduck_v2_roulade_contract as C
from ht_microduck.tasks.mdp import cyberduck_roulade_rewards as rewards
from ht_microduck.tasks.mdp.cyberduck_actions import (
    CyberDuckJointPositionActionCfg,
    CyberDuckJointVelocityActionCfg,
)
from ht_microduck.tasks.mdp.cyberduck_observations import (
    clipped_last_action,
    wheel_contact,
)
from ht_microduck.tasks.mdp.cyberduck_roulade_actions import RouladePositionActionCfg
from ht_microduck.tasks.mdp.cyberduck_roulade_events import (
    init_roulade_geometry,
    reset_roulade_state,
)
from ht_microduck.tasks.mdp.cyberduck_roulade_metrics import (
    roulade_angle,
    roulade_head_contacted,
    roulade_success,
)
from ht_microduck.tasks.mdp.cyberduck_roulade_state import roulade_phase
from ht_microduck.tasks.mdp.official_curriculums import (
    com_range_curriculum,
    event_param_curriculum,
    reward_param_curriculum,
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


def _apply_final_curriculum(cfg: ManagerBasedRlEnvCfg) -> None:
    """play 时把课程快进到末段并删除课程项，避免 viewer 停在 stage 0。"""
    for name, term in list(cfg.curriculum.items()):
        params = term.params
        if "weight_stages" in params:
            cfg.rewards[params["reward_name"]].weight = params["weight_stages"][-1]["weight"]
        elif "range_stages" in params:
            cfg.events[params["event_name"]].params["ranges"] = (
                -params["range_stages"][-1]["range"],
                params["range_stages"][-1]["range"],
            )
        elif "param_stages" in params:
            if "event_name" in params:
                cfg.events[params["event_name"]].params.update(
                    params["param_stages"][-1]["params"]
                )
            else:
                # 奖励项参数课程（如 settle 的速度尺度）：末段值写回奖励项。
                cfg.rewards[params["reward_name"]].params.update(
                    params["param_stages"][-1]["params"]
                )
        elif "ramp_steps" in params:
            cfg.rewards[params["reward_name"]].weight = params["end_weight"]
        else:
            raise AssertionError(f"unsupported roulade curriculum term: {name}")
        del cfg.curriculum[name]


def make_roulade_env_cfg(*, num_envs: int = 512, seed: int | None = None,
                         play: bool = False) -> ManagerBasedRlEnvCfg:
    """构造独立滚翻环境；回放只从站立出发，避免中途初态被误判为完整技能。"""
    if num_envs < 1:
        raise ValueError("Roulade num_envs must be positive")
    positions = SceneEntityCfg("robot", joint_names=C.POSITION_JOINTS, preserve_order=True)
    joints = SceneEntityCfg("robot", joint_names=C.POLICY_JOINTS, preserve_order=True)
    legs = SceneEntityCfg("robot", joint_names=C.LEG_POSITION_JOINTS, preserve_order=True)
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
            name=C.SUPPORT_SENSOR,
            primary=ContactMatch(mode="geom", pattern=COLLISION_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found",), reduce="none", num_slots=1,
        ),
        ContactSensorCfg(
            name=C.HEAD_SENSOR,
            primary=ContactMatch(mode="geom", pattern="head_collision", entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found",), reduce="none", num_slots=1,
        ),
        ContactSensorCfg(
            name=C.WHEEL_SENSOR,
            primary=ContactMatch(mode="geom", pattern=C.WHEEL_GEOMS, entity="robot"),
            secondary=ContactMatch(mode="geom", pattern="terrain"),
            fields=("found", "force"), reduce="netforce", num_slots=1,
        ),
        ContactSensorCfg(
            name="roulade_self_contact",
            primary=ContactMatch(mode="geom", pattern=COLLISION_GEOM_NAMES, entity="robot"),
            secondary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
            fields=("found",), reduce="none", num_slots=1,
        ),
        BuiltinSensorCfg(name="root_angmom", sensor_type="subtreeangmom",
                         obj=ObjRef(type="body", name="base_link", entity="robot")),
    )
    gate = {"gate_lo": math.radians(260), "gate_hi": math.radians(330)}
    task_rewards = {
        "roulade_progress": RewardTermCfg(func=rewards.roulade_progress, weight=8.0,
                                          params={"target_angle": 2 * math.pi, "max_paid_rate": 5.0}),
        "roulade_overspeed": RewardTermCfg(func=rewards.roulade_overspeed_penalty, weight=-0.1,
                                           params={"omega_max": 7.0}),
        "roulade_head_pivot": RewardTermCfg(func=rewards.roulade_head_pivot, weight=0.5),
        # 密集进度信号：填补 0–260° 的奖励真空。三次从零训练都卡在 127–149°，
        # 该状态下除 roulade_progress(3.1/8) 外全部奖励为 0 或负，形成局部最优。
        "roulade_roll_continuity": RewardTermCfg(
            func=rewards.roulade_roll_continuity, weight=3.0,
            params={"angle_full": 2 * math.pi, "gate_hi": math.radians(260)},
        ),
        "roulade_landing_composite": RewardTermCfg(
            func=rewards.roulade_landing_composite, weight=4.0,
            params={"target_height": C.SUPPORT_HEIGHT, "height_std": 0.04, "upright_std": 0.4,
                    "pose_std": 0.4, "asset_cfg": legs, **gate},
        ),
        "roulade_upright_after_roll": RewardTermCfg(func=rewards.roulade_upright_after_roll, weight=1.5, params=gate.copy()),
        "roulade_height_after_roll": RewardTermCfg(func=rewards.roulade_height_after_roll, weight=1.0,
                                                   params={"target_height": C.SUPPORT_HEIGHT, "std": 0.04, **gate}),
        "roulade_landing_sharp": RewardTermCfg(func=rewards.roulade_landing_sharp, weight=2.0,
                                               params={"target_height": C.SUPPORT_HEIGHT, "height_std": 0.015,
                                                       "upright_std": 0.3, **gate}),
        "roulade_stand_tax": RewardTermCfg(func=rewards.roulade_stand_tax, weight=5.0,
                                           params={"target_height": C.SUPPORT_HEIGHT, **gate}),
        "roulade_rise_velocity": RewardTermCfg(func=rewards.roulade_rise_velocity, weight=0.75,
                                               params={"max_height": C.SUPPORT_HEIGHT + 0.01,
                                                       "gate_lo": math.radians(180), "gate_hi": math.radians(260)}),
        "roulade_sagittal": RewardTermCfg(func=rewards.roulade_sagittal_penalty, weight=-0.1),
        # 横滚姿态角本身：原有约束只看角速度和横轴水平度，策略可以慢慢歪过去。
        # 全电机版实测峰值横滚 152°、横向位移 0.26 m，观感变成侧翻。
        # 初始权重为 0，由 Recovery 课程在策略学会翻滚之后才逐步加重
        # （2026-11-16 实测：从第一步就用 -2.0 会把策略压回 132–148° 平台）。
        "roulade_lateral_tilt": RewardTermCfg(
            func=rewards.roulade_lateral_tilt, weight=0.0,
        ),
        "roulade_lateral_vel": RewardTermCfg(func=rewards.roulade_lateral_velocity_penalty, weight=-0.5),
        "roulade_flatness": RewardTermCfg(func=rewards.roulade_flatness_penalty, weight=-0.5),
        "action_rate_l2": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.1),
        "joint_torque_rate_l2": RewardTermCfg(func=rewards.joint_torque_rate_l2, weight=0.0),
        "body_ang_vel": RewardTermCfg(func=velocity_mdp.body_angular_velocity_penalty, weight=-0.002,
                                       params={"asset_cfg": deepcopy(base)}),
        "angular_momentum": RewardTermCfg(func=velocity_mdp.angular_momentum_penalty, weight=-0.001,
                                           params={"sensor_name": "robot/root_angmom"}),
        "dof_pos_limits": RewardTermCfg(func=mdp.joint_pos_limits, weight=-1.0,
                                        params={"asset_cfg": deepcopy(positions)}),
        "arrival_damping": RewardTermCfg(func=rewards.body_ang_vel_at_height, weight=0.0,
                                         params={"height_low": C.SUPPORT_HEIGHT - 0.025,
                                                 "height_high": C.SUPPORT_HEIGHT - 0.005,
                                                 "tilt_full_deg": 20.0, "tilt_zero_deg": 45.0,
                                                 "asset_cfg": deepcopy(base)}),
        "gentle_landing": RewardTermCfg(func=rewards.trunk_vertical_accel_penalty, weight=0.002),
        "self_collisions": RewardTermCfg(func=velocity_mdp.self_collision_cost, weight=-0.1,
                                         params={"sensor_name": "roulade_self_contact"}),
    }
    events = {
        "htdw3532_init": EventTermCfg(func=htdw3532_init, mode="startup"),
        "bam_init": EventTermCfg(func=bam_init, mode="startup"),
        "roulade_geometry": EventTermCfg(func=init_roulade_geometry, mode="startup"),
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
        "set_roulade_state": EventTermCfg(func=reset_roulade_state, mode="reset",
                                          params={"standing_prob": 1.0 if play else 0.5,
                                                  "midroll_prob": 0.0 if play else 0.5}),
    }
    curriculum = {}
    if not play:
        curriculum["roulade_spawn_mix"] = CurriculumTermCfg(
            func=event_param_curriculum,
            params={"event_name": "set_roulade_state", "param_stages": [
                {"step": 0, "params": {"standing_prob": 0.5, "midroll_prob": 0.5}},
                {"step": 3000 * 24, "params": {"standing_prob": 0.65, "midroll_prob": 0.35}},
                {"step": 6000 * 24, "params": {"standing_prob": 0.8, "midroll_prob": 0.2}},
            ]},
        )
    for name, event, stages in (
        ("com_range", "randomize_com", ((0, 0.003), (500, 0.005), (1000, 0.01), (1500, 0.015))),
        ("head_com_range", "randomize_head_com", ((0, 0.003), (500, 0.005), (1000, 0.01))),
    ):
        curriculum[name] = CurriculumTermCfg(func=com_range_curriculum, params={
            "event_name": event, "range_stages": [{"step": step * 24, "range": value} for step, value in stages],
        })
    for name, reward, stages in (
        ("action_rate_weight", "action_rate_l2", ((0, -0.1), (1500, -0.2), (3000, -0.4))),
        ("arrival_damping_weight", "arrival_damping", ((0, 0.0), (2500, -0.025), (3500, -0.05))),
        ("torque_rate_weight", "joint_torque_rate_l2", ((0, 0.0), (2500, -5e-4), (3500, -1e-3))),
        ("gentle_landing_weight", "gentle_landing", ((0, 0.002), (2500, 0.005))),
    ):
        curriculum[name] = CurriculumTermCfg(func=reward_weight, params={
            "reward_name": reward, "weight_stages": [{"step": step * 24, "weight": value} for step, value in stages],
        })
    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(num_envs=num_envs, env_spacing=2.0, terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": get_cyberduck_v2_robot_cfg()}, sensors=sensors),
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=C.PHYSICS_TIMESTEP), nconmax=128, njmax=1500),
        decimation=C.DECIMATION, episode_length_s=C.EPISODE_LENGTH_S, seed=seed,
        viewer=ViewerConfig(entity_name="robot", body_name="base_link", distance=1.2),
        observations={"actor": ObservationGroupCfg(terms=actor, enable_corruption=not play),
                      "critic": ObservationGroupCfg(terms=critic, enable_corruption=False)},
        actions={
            "joint_pos": CyberDuckJointPositionActionCfg(
                entity_name="robot", actuator_names=C.POSITION_JOINTS, preserve_order=True,
                scale=C.POSITION_SCALE, raw_action_limit=C.POSITION_ACTION_LIMIT, use_default_offset=True,
            ),
            "joint_vel": CyberDuckJointVelocityActionCfg(
                entity_name="robot", actuator_names=C.VELOCITY_JOINTS, preserve_order=True,
                scale=C.VELOCITY_SCALE, raw_action_limit=C.VELOCITY_ACTION_LIMIT, use_default_offset=True,
                clip={".*": (-C.VELOCITY_TARGET_LIMIT, C.VELOCITY_TARGET_LIMIT)},
            ),
        },
        commands={}, events=events, rewards=task_rewards, curriculum=curriculum,
        metrics={"roulade_angle": MetricsTermCfg(func=roulade_angle, reduce="max"),
                 "roulade_head_contacted": MetricsTermCfg(func=roulade_head_contacted, reduce="max"),
                 "roulade_success": MetricsTermCfg(func=roulade_success, reduce="max")},
        terminations={"time_out": TerminationTermCfg(func=mdp.time_out, time_out=True),
                      "nan_state": TerminationTermCfg(func=robot_state_is_nan)},
    )


def make_recovery_env_cfg(*, num_envs: int = 512, seed: int | None = None,
                          play: bool = False) -> ManagerBasedRlEnvCfg:
    """装配本机恢复适配实验，原官方配方任务保持独立。

    内部一律用 ``play=False`` 构造：``make_roulade_env_cfg(play=True)`` 会先把课程
    快进并清空，导致 Recovery 自己新增的课程项永远加不进去（此前 play 模式下
    settle/home_pose 等全部停在初始权重）。Recovery 的 play 快进在函数末尾统一做。
    """
    cfg = make_roulade_env_cfg(num_envs=num_envs, seed=seed, play=False)
    cfg.actions["joint_pos"] = RouladePositionActionCfg(
        entity_name="robot", actuator_names=C.POSITION_JOINTS, preserve_order=True,
        use_default_offset=True,
    )
    for group in ("actor", "critic"):
        cfg.observations[group].terms["roulade_phase"] = ObservationTermCfg(func=roulade_phase)
    for name in ("roulade_landing_composite", "roulade_upright_after_roll", "roulade_height_after_roll",
                 "roulade_landing_sharp", "roulade_stand_tax"):
        del cfg.rewards[name]
    legs = SceneEntityCfg("robot", joint_names=C.LEG_POSITION_JOINTS, preserve_order=True)
    gate = {"target_height": C.SUPPORT_HEIGHT, "gate_lo": math.radians(260), "gate_hi": math.radians(330)}
    cfg.rewards.update(
        # 原线性高度亏损在 260° 门控处形成悬崖：260° 前恒 0，越过即每秒约 -2.34，
        # 而进度只剩约 2.2 分；策略因此停在约 259.6°。改为连续势能，门控放宽到
        # 200–300°，低姿态不再被越扣越怕，同时保留“站立才得满分”。
        recovery_potential=RewardTermCfg(
            func=rewards.roulade_recovery_potential, weight=3.0,
            # 受载 HOME 实测根高 0.2399–0.2418 m。0.06 是唯一有 600 秒证据的取值：
            # v4 训练后末秒根高 0.195–0.202 m、双侧支撑 0.47–0.95；收紧到 0.035
            # 并加入站姿项的同预算实验反而塌到 0.072 m / 支撑 0，未采用。
            params={"target_height": C.SUPPORT_HEIGHT, "height_std": 0.06, "upright_std": 0.5,
                    "gate_lo": math.radians(200), "gate_hi": math.radians(300)},
        ),
        supported_upright=RewardTermCfg(func=rewards.roulade_supported_upright, weight=1.5, params=gate.copy()),
        supported_landing=RewardTermCfg(func=rewards.roulade_supported_landing, weight=4.0,
                                       params={**gate, "height_std": 0.08, "upright_std": 0.4}),
        # 没有这两项时，模型能完成 31/32 回合，但站立段把头颈顶到限位：
        # neck_pitch=2.92（上限）、head_pitch=-1.53，头部高度 0.385→0.258 m，
        # head_yaw 在 ±2.97 之间以约 0.78 Hz 摆动。头部质量约 1.13 kg（31%），
        # 低头能降低重心换稳定，所以奖励必须显式要求“头回到 HOME 且朝上”。
        neck_pose_l2=RewardTermCfg(
            func=rewards.roulade_neck_pose_l2, weight=-0.6,
            params={"gate_lo": math.radians(200), "gate_hi": math.radians(300)},
        ),
        head_upright=RewardTermCfg(
            func=rewards.roulade_head_upright, weight=1.0,
            params={"gate_lo": math.radians(200), "gate_hi": math.radians(300)},
        ),
        # 低头不是审美问题，是“用 31% 质量换重心”：HOME 整机 COM 0.223 m，
        # 折头后 0.186 m，而根体高度不变，之前所有高度项都看不见这个变化。
        com_height=RewardTermCfg(
            func=rewards.roulade_com_height, weight=2.0,
            params={"target_height": 0.223, "height_std": 0.03,
                    "gate_lo": math.radians(200), "gate_hi": math.radians(300)},
        ),
        # 六项验收判据里只有角速度不满足：站立段 |ω| 中位数 0.98 rad/s，
        # 仅 38.1% 控制步低于 0.8，无法连续 0.5 s。原奖励没有任何“停住”项，
        # 本项按验收阈值 0.2 m/s / 0.8 rad/s 做高斯，低于阈值近似 1。
        # 阈值取成功判据的 1/2：核函数在阈值处是 exp(-1)=0.37，
        # 实测会在 0.8 rad/s 附近徘徊（stage4 均值 1.49）；减半后 exp(-1) 对应
        # 0.4 rad/s，才能把实际速度压到判据以下而不是压在判据上。
        settle=RewardTermCfg(
            func=rewards.roulade_settle, weight=2.0,
            params={"max_linear_speed": C.SUCCESS_LINEAR_SPEED,
                    "max_angular_speed": C.SUCCESS_ANGULAR_SPEED,
                    "gate_lo": math.radians(200), "gate_hi": math.radians(300)},
        ),
        # 根因：Recovery 早先删掉了官方的 landing composite（它含相对 HOME 的
        # 关节姿态项），只剩躯干高度/直立/速度，于是策略可以任选站姿。
        # model_9999 实际用“腿几乎伸直（hip_pitch 0.01、calf -0.04）+ 头折到背后”
        # 站稳，根因是没有姿态约束，而不是头颈单独的问题。
        # 这里按官方数值加回姿态项，且 height_std 保持 0.04，不重复 v5 的收紧。
        roulade_landing_composite=RewardTermCfg(
            func=rewards.roulade_landing_composite, weight=3.0,
            params={"target_height": C.SUPPORT_HEIGHT, "height_std": 0.04, "upright_std": 0.4,
                    "pose_std": 0.4, "asset_cfg": legs, **gate},
        ),
        # 站姿回 HOME 用**正向奖励**而不是惩罚：罚项会让策略学会“不翻过门控”
        # （330–345° 门控的惩罚实验 0/32，角度掉到 273–458°）。正向项翻过去只会
        # 多一个得分机会，不会诱导逃避。覆盖全部 12 个位置关节，pose_std 0.25。
        home_pose=RewardTermCfg(
            func=rewards.roulade_home_pose, weight=2.0,
            params={"joint_names": C.POSITION_JOINTS, "pose_std": 0.15,
                    "gate_lo": math.radians(330), "gate_hi": math.radians(345)},
        ),
        # 静止站立用具正向奖励，不用惩罚：330–345° 门控的惩罚实测会让策略
        # 停在门控下方（前翻掉到 277.8–324.1°、四项目标奖励全 0）。
        # 正向项翻过去只多拿分，不会诱导逃避。
        # yaw/roll 类关节单独收紧：全局 home_pose 的均值把这几路的偏差摊薄了。
        yaw_roll_pose=RewardTermCfg(
            func=rewards.roulade_yaw_roll_pose, weight=4.0,
            params={"pose_std": 0.10,
                    "gate_lo": math.radians(330), "gate_hi": math.radians(345)},
        ),
        # 站立段动作平滑：`stand_still` 用的是被 PD 滤过的关节速度，
        # 而真正跳变的是策略输出的目标值（25 Hz 每帧反向）。这项直接压动作差。
        stand_action_rate=RewardTermCfg(
            func=rewards.roulade_stand_action_rate, weight=0.0,
            params={"joint_std": 0.3,
                    "gate_lo": math.radians(330), "gate_hi": math.radians(345)},
        ),
        # 角速度超限的即时信号：8 条判据里只有它打断 0.5 s 保持（833 帧 vs 其余 0–7 帧）。
        # settle 的高斯核在尖峰时给 ~0，方向对但缺少“超限即罚”的局部信号。
        stand_angvel=RewardTermCfg(
            func=rewards.roulade_stand_angvel, weight=-0.5,
            params={"max_angular_speed": C.SUCCESS_ANGULAR_SPEED,
                    "gate_lo": math.radians(330), "gate_hi": math.radians(345)},
        ),
        stand_still=RewardTermCfg(
            func=rewards.roulade_stand_still, weight=3.0,
            params={"joint_names": C.POSITION_JOINTS, "speed_std": 0.5,
                    "gate_lo": math.radians(330), "gate_hi": math.radians(345)},
        ),
        # 起翻阶段：头顶朝前 + 不拧 yaw。原 tuck 的头顶轴指向身体后方，
        # 策略只能靠脸/下巴过顶，并额外用 head_yaw 找平衡（实测 -1.32 rad）。
        # 两项都只作用于 0–250°，覆盖起翻与过顶，不影响落地段。
        head_crown_forward=RewardTermCfg(
            func=rewards.roulade_head_crown_forward, weight=1.0,
            params={"angle_lo": 0.0, "angle_hi": math.radians(250)},
        ),
        head_yaw_penalty=RewardTermCfg(
            func=rewards.roulade_head_yaw_penalty, weight=-0.3,
            params={"angle_hi": math.radians(250)},
        ),
    )
    # 恢复官方 action_rate 课程（-0.1 → -0.2 → -0.4）。Recovery 早先把它降到
    # -0.02 并删掉课程，结果站立段网络动作以 ±1.5–1.9 的幅度 bang-bang 切换，
    # 头颈关节速度 3.7–4.9 rad/s，肉眼就是持续抖动。动作项对潜变量生效，
    # 与 tanh 映射前的 1 rad/action 尺度匹配，不会像旧弧度动作那样过大。
    cfg.rewards["action_rate_l2"].weight = -0.1
    # 内部按 play=False 构造（见函数开头说明），所以基础任务把出生参数设成了
    # 0.5/0.5；play 时必须改回“只从站立出发”，否则回放会从翻滚中途开始。
    if play:
        cfg.events["set_roulade_state"].params.update(
            standing_prob=1.0, midroll_prob=0.0
        )
    else:
        # 中段出生覆盖 50–340°，但权重向“翻过头顶后的恢复段”倾斜：
        # 260° 之后的末段是当前失败点，需要更多 on-policy 样本。
        cfg.events["set_roulade_state"].params.update(
            standing_prob=0.5, midroll_prob=0.5,
            midroll_pitch_min=math.radians(50), midroll_pitch_max=math.radians(340),
            tuck_factor_range=(0.0, 0.3), midroll_omega_range=(0.0, 1.5),
        )
    # 移除旧角度课程，防止恢复 common_step_counter 后又被覆盖成仅末段出生。
    cfg.curriculum.pop("roulade_spawn_mix", None)
    # 固定 step 阈值在续训时会被一次性跳过（本机 common_step_counter 已 27 万步），
    # 因此 Recovery 的动作平滑课程改用从当前步起步的 ramp，-0.1 → -0.4。
    cfg.curriculum["action_rate_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "action_rate_l2",
            "start_weight": -0.1,
            "end_weight": -0.4,
            "ramp_steps": 600 * 24,
        },
    )
    # 恢复势能的权重课程：先给连续信号，再逐步加强站立目标。
    cfg.curriculum["recovery_potential_weight"] = CurriculumTermCfg(
        func=reward_weight,
        params={
            "reward_name": "recovery_potential",
            "weight_stages": [
                {"step": 0, "weight": 3.0},
                {"step": 1500 * 24, "weight": 4.5},
                {"step": 3000 * 24, "weight": 6.0},
            ],
        },
    )
    # 头颈姿态课程：从“轻微约束”线性加到“回到 HOME”。直接用固定权重会在
    # 站立能力尚未建立时把它压垮（neck -3.0 的同预算实验 0/32、根高 0.145 m）；
    # 相对步数起点的 ramp 保证从零和从检查点续训都不会被一次性跳过。
    # 横滚姿态约束：必须等策略学会翻滚之后再加重。
    # 2026-11-16 实测：从第一步就用 -2.0，策略学会"不动最安全"，卡在 132–148°。
    # 延迟 600 迭代（≈14400 步）后再从 0 收紧到 -4.0。
    cfg.curriculum["lateral_tilt_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "roulade_lateral_tilt",
            "start_weight": 0.0,
            # 实测 -4.0 只罚 -1.58，相对站立类奖励（合计 100+）可忽略，
            # 侧倾反而从 152° 增到 163°。加大到 -20 形成实质约束。
            "end_weight": -20.0,
            "ramp_steps": 400 * 24,
            "delay_steps": 600 * 24,
        },
    )
    cfg.curriculum["neck_pose_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "neck_pose_l2",
            "start_weight": -0.6,
            "end_weight": -1.6,
            "ramp_steps": 300 * 24,
        },
    )
    cfg.curriculum["head_upright_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "head_upright",
            "start_weight": 1.0,
            "end_weight": 2.5,
            "ramp_steps": 300 * 24,
        },
    )
    # settle 的速度尺度：从验收阈值起步，400 迭代后收紧到一半。
    # 直接上 0.5 倍会压住从零训练的翻滚探索（2026-11-15 单次训练验证）。
    cfg.curriculum["settle_scale"] = CurriculumTermCfg(
        func=reward_param_curriculum,
        params={
            "reward_name": "settle",
            "param_stages": [
                {"step": 0, "params": {"max_linear_speed": C.SUCCESS_LINEAR_SPEED,
                                       "max_angular_speed": C.SUCCESS_ANGULAR_SPEED}},
                {"step": 400 * 24,
                 "params": {"max_linear_speed": C.SUCCESS_LINEAR_SPEED * 0.5,
                            "max_angular_speed": C.SUCCESS_ANGULAR_SPEED * 0.5}},
            ],
        },
    )
    # 静止项从 2.0 加到 10.0，延迟 400 迭代再加重。
    cfg.curriculum["settle_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "settle",
            "start_weight": 2.0,
            "end_weight": 10.0,
            "ramp_steps": 300 * 24,
            # stage4 用 2.0 起（能翻完）；4.0 会压住翻滚探索，晚一点再加重。
            "delay_steps": 400 * 24,
        },
    )
    # 站姿回 HOME 的权重课程：先给信号，再加强到能把 hip_yaw/head_roll 拉回。
    cfg.curriculum["home_pose_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "home_pose",
            "start_weight": 2.0,
            "end_weight": 10.0,
            "ramp_steps": 600 * 24,
        },
    )
    cfg.curriculum["yaw_roll_pose_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "yaw_roll_pose",
            "start_weight": 4.0,
            "end_weight": 8.0,
            "ramp_steps": 400 * 24,
        },
    )
    cfg.curriculum["stand_action_rate_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "stand_action_rate",
            "start_weight": 0.0,
            "end_weight": 8.0,
            "ramp_steps": 400 * 24,
            # 抖动修复是在已能翻完的策略上调出来的；从零训练必须等翻滚学会。
            "delay_steps": 600 * 24,
        },
    )
    cfg.curriculum["stand_angvel_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "stand_angvel",
            "start_weight": -0.5,
            "end_weight": -1.5,
            "ramp_steps": 400 * 24,
            # 同 stand_action_rate：从零训练时角速度惩罚会压住翻滚。
            "delay_steps": 600 * 24,
        },
    )
    cfg.curriculum["stand_still_weight"] = CurriculumTermCfg(
        func=reward_weight_ramp,
        params={
            "reward_name": "stand_still",
            "start_weight": 3.0,
            "end_weight": 8.0,
            "ramp_steps": 600 * 24,
        },
    )
    if play:
        # 没有对应课程项的项直接写末段值；有课程的由 _apply_final_curriculum 统一快进。
        cfg.rewards["recovery_potential"].weight = 6.0
        cfg.rewards["roulade_lateral_tilt"].weight = -20.0
        cfg.rewards["neck_pose_l2"].weight = -1.6
        cfg.rewards["head_upright"].weight = 2.5
        _apply_final_curriculum(cfg)
        # settle 的速度尺度由 settle_scale 课程快进；显式再确认一次末段值，
        # 避免课程被删除后仍停在验收阈值。
        cfg.rewards["settle"].params["max_linear_speed"] = C.SUCCESS_LINEAR_SPEED * 0.5
        cfg.rewards["settle"].params["max_angular_speed"] = C.SUCCESS_ANGULAR_SPEED * 0.5
    return cfg
