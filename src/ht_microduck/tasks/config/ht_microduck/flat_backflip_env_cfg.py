# Copyright (c) 2026-2027 zh
"""
内容：
    在 HT MicroDuck 上装配官方 hand-off 后空翻任务：50 kg 发射板、站立保持、
    后仰发射、空中进度、落地年金和 critic-only 板观测。

来源：
    pollen-robotics/microduck_rl@d26322f
    src/mjlab_microduck/tasks/microduck_backflip_env_cfg.py（Apache-2.0）。
    本机替换了机器人命名、接触传感器（含板接触）、观测/奖励/终止/初态和
    执行器路径；发射包线仍是官方 0.74 kg 机器人的临时基线，未在 HT 上标定。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import mujoco
from mjlab.entity import EntityCfg
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import (
    CurriculumTermCfg,
    EventTermCfg,
    MetricsTermCfg,
    ObservationTermCfg,
    RewardTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp

from ht_microduck.tasks import ht_microduck_backflip_contract as B
from ht_microduck.tasks.config.ht_microduck.flat_velocity_env_cfg import (
    NUM_STEPS_PER_ENV,
    make_flat_velocity_env_cfg,
)
from ht_microduck.tasks.mdp import ht_backflip_events as bf_events
from ht_microduck.tasks.mdp import ht_backflip_metrics as bf_metrics
from ht_microduck.tasks.mdp import ht_backflip_observations as bf_obs
from ht_microduck.tasks.mdp import ht_backflip_rewards as bf_rewards
from ht_microduck.tasks.mdp import official as microduck_mdp

_PLATE_XML = Path(__file__).resolve().parents[2] / "assets" / "backflip_launcher.xml"


def get_plate_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(_PLATE_XML))


PLATE_CFG = EntityCfg(
    spec_fn=get_plate_spec,
    init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, B.PLATE_HALF_THICKNESS)),
)


def _apply_final_curriculum(cfg: ManagerBasedRlEnvCfg) -> None:
    """play 时把课程快进到末段并删除课程项，避免 viewer 停在 stage 0。"""
    for name, term in list(cfg.curriculum.items()):
        params = term.params
        if "weight_stages" in params:
            cfg.rewards[params["reward_name"]].weight = params["weight_stages"][-1]["weight"]
        elif "param_stages" in params:
            cfg.rewards[params["reward_name"]].params.update(params["param_stages"][-1]["params"])
        elif "range_stages" in params:
            cfg.events[params["event_name"]].params["ranges"] = (
                -params["range_stages"][-1]["range"],
                params["range_stages"][-1]["range"],
            )
        else:
            raise AssertionError(f"unsupported backflip curriculum term: {name}")
        del cfg.curriculum[name]


def make_backflip_env_cfg(
    num_envs: int = 4096, seed: int | None = None, play: bool = False
) -> ManagerBasedRlEnvCfg:
    """装配 HT 后空翻环境；``play`` 只影响课程/最终门控，不改变接口。"""
    cfg = make_flat_velocity_env_cfg(num_envs=num_envs, seed=seed, play=play)

    # ---------- 场景与板 ----------
    z0_mid = 0.5 * (B.Z0_RANGE[0] + B.Z0_RANGE[1])
    robot_cfg = deepcopy(cfg.scene.entities["robot"])
    robot_cfg.init_state = deepcopy(robot_cfg.init_state)
    # 与官方一致：首个 episode 在 mjlab 不 reset 时也站在板顶，而不是穿板。
    robot_cfg.init_state.pos = (
        0.0,
        0.0,
        z0_mid + B.PLATE_HALF_THICKNESS + B.STAND_Z,
    )
    cfg.scene.entities = {
        "robot": robot_cfg,
        "plate": deepcopy(PLATE_CFG),
    }
    feet_plate_cfg = ContactSensorCfg(
        name="feet_plate_contact",
        primary=ContactMatch(
            mode="geom",
            pattern=r"^(r_foot_collision|l_foot_collision)$",
            entity="robot",
        ),
        secondary=ContactMatch(mode="body", pattern="plate", entity="plate"),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )
    feet_ground_cfg = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="geom",
            pattern=r"^(r_foot_collision|l_foot_collision)$",
            entity="robot",
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    self_collision_cfg = ContactSensorCfg(
        name="self_collision",
        primary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
        secondary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )
    robot_ground_cfg = ContactSensorCfg(
        name="robot_ground_contact",
        primary=ContactMatch(mode="subtree", pattern="base_link", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found",),
        reduce="none",
        num_slots=1,
    )
    cfg.scene.sensors = (
        feet_ground_cfg,
        feet_plate_cfg,
        self_collision_cfg,
        robot_ground_cfg,
    )
    cfg.scene.spec_fn = None
    cfg.viewer.body_name = "base_link"
    cfg.episode_length_s = B.EPISODE_LENGTH_S
    cfg.sim.nconmax = 60
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.metrics["backflip_success"] = MetricsTermCfg(
        func=bf_metrics.backflip_success, reduce="last"
    )
    cfg.metrics["backflip_angle"] = MetricsTermCfg(
        func=bf_metrics.backflip_angle, reduce="max"
    )

    # ---------- 动作与命令 ----------
    action = cfg.actions["joint_pos"]
    action.scale = B.ACTION_SCALE
    action.use_default_offset = True
    cfg.commands.clear()

    # ---------- 观测 ----------
    zero = microduck_mdp.zero_command_padding
    for group in ("actor", "critic"):
        cfg.observations[group].terms["command"] = ObservationTermCfg(
            func=zero, params={"dim": 3}
        )
        cfg.observations[group].terms["head_command"] = ObservationTermCfg(
            func=zero, params={"dim": 4}
        )
        cfg.observations[group].terms["body_command"] = ObservationTermCfg(
            func=zero, params={"dim": 6}
        )
    del cfg.observations["critic"].terms["foot_height"]
    cfg.observations["critic"].terms["plate_position"] = ObservationTermCfg(
        func=bf_obs.backflip_plate_pos_obs,
        params={"asset_name": "plate"},
    )
    cfg.observations["critic"].terms["plate_velocity"] = ObservationTermCfg(
        func=bf_obs.backflip_plate_vel_obs,
        params={"asset_name": "plate"},
    )
    cfg.observations["critic"].terms["plate_phase"] = ObservationTermCfg(
        func=bf_obs.backflip_phase_obs
    )
    cfg.observations["critic"].terms["hold_remaining"] = ObservationTermCfg(
        func=bf_obs.backflip_hold_remaining_obs
    )

    # ---------- 奖励 ----------
    for name in (
        "track_linear_velocity",
        "track_angular_velocity",
        "upright",
        "pose",
        "air_time",
        "foot_clearance",
        "foot_swing_height",
        "foot_slip",
        "head_pose_tracking",
        "body_pose_tracking",
        "head_pose_bias",
        "soft_landing",
    ):
        cfg.rewards.pop(name, None)
    cfg.rewards["flip_progress"] = RewardTermCfg(
        func=bf_rewards.backflip_progress,
        weight=8.0,
        params={
            "target_angle": B.TARGET_ANGLE,
            "max_paid_rate": B.MAX_PAID_RATE,
            "launch_gate_floor": B.LAUNCH_GATE_FLOOR,
            "hold_z": B.STAND_Z + B.PLATE_HALF_THICKNESS,
        },
    )
    cfg.rewards["landing"] = RewardTermCfg(
        func=bf_rewards.backflip_landing,
        weight=4.0,
        params={
            "stand_z": B.STAND_Z,
            "height_std": 0.04,
            "omega_std": 3.0,
            "lin_vel_std": 0.5,
            "window_s": B.LANDING_WINDOW_S,
            "launch_gate_floor": B.LAUNCH_GATE_FLOOR,
            "hold_z": B.STAND_Z + B.PLATE_HALF_THICKNESS,
            "sensor_name": "feet_ground_contact",
        },
    )
    cfg.rewards["ready_stance"] = RewardTermCfg(
        func=bf_rewards.backflip_ready_stance,
        weight=B.READY_STANCE_WEIGHT,
        params={
            "stand_z": B.STAND_Z + B.PLATE_HALF_THICKNESS,
            "height_std": 0.03,
            "tilt_full_deg": 10.0,
            "tilt_zero_deg": 45.0,
            "pose_std": B.POSE_STD,
        },
    )
    cfg.rewards["action_rate_l2"] = RewardTermCfg(
        func=mdp.action_rate_l2, weight=-0.05
    )
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = ("base_link",)
    cfg.rewards["body_ang_vel"].weight = -0.002
    cfg.rewards["angular_momentum"].weight = -0.001
    cfg.rewards["self_collisions"].weight = -0.1
    cfg.rewards["self_collisions"].params["sensor_name"] = "self_collision"
    cfg.rewards["gentle_landing"] = RewardTermCfg(
        func=microduck_mdp.trunk_vertical_accel_penalty,
        weight=0.004,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",))
        },
    )
    cfg.rewards["joint_torque_rate_l2"] = RewardTermCfg(
        func=microduck_mdp.joint_torque_rate_l2,
        weight=0.0,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )

    # ---------- 终止 ----------
    cfg.terminations.pop("fell_over", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["nan_state"].params["sensor_names"] = (
        "feet_ground_contact",
        "feet_plate_contact",
        "self_collision",
        "robot_ground_contact",
    )

    # ---------- 事件 ----------
    cfg.events.pop("push_robot", None)
    cfg.events["reset_base"].params["pose_range"] = {
        "x": (-0.01, 0.01),
        "y": (-0.01, 0.01),
        "z": (0.0, 0.0),
        "roll": (-0.02, 0.02),
        "pitch": (-0.02, 0.02),
        "yaw": (-0.05, 0.05),
    }
    cfg.events["reset_robot_joints"].params["position_range"] = (-0.05, 0.05)
    cfg.events["foot_friction"].params["ranges"] = (0.7, 1.3)
    cfg.events["backflip_launch_params"] = EventTermCfg(
        func=bf_events.reset_backflip_launch_params,
        mode="reset",
        params={
            "hold_range": B.HOLD_RANGE,
            "launch_range": B.LAUNCH_RANGE,
            "z0_range": B.Z0_RANGE,
            "vz_range": B.VZ_RANGE,
            "w0_range": B.W0_RANGE,
        },
    )
    cfg.events["backflip_metrics_reset"] = EventTermCfg(
        func=bf_metrics.reset_backflip_metrics, mode="reset"
    )
    cfg.events["backflip_spawn"] = EventTermCfg(
        func=bf_events.reset_backflip_robot_on_plate,
        mode="reset",
        params={
            "stand_z": B.STAND_Z,
            "plate_half_thickness": B.PLATE_HALF_THICKNESS,
        },
    )
    cfg.events["backflip_plate_reset"] = EventTermCfg(
        func=bf_events.backflip_plate_step,
        mode="reset",
        params={"asset_name": "plate", "t_override": 0.0},
    )
    cfg.events["backflip_plate"] = EventTermCfg(
        func=bf_events.backflip_plate_step,
        mode="step",
        params={"asset_name": "plate"},
    )

    # ---------- 课程 ----------
    cfg.curriculum.clear()
    for term in ("flip_progress", "landing"):
        cfg.curriculum[f"launch_gate_floor_{term}"] = CurriculumTermCfg(
            func=microduck_mdp.reward_param_curriculum,
            params={
                "reward_name": term,
                "param_stages": [
                    {"step": 0, "params": {"launch_gate_floor": B.LAUNCH_GATE_FLOOR}},
                    {"step": 2000 * NUM_STEPS_PER_ENV, "params": {"launch_gate_floor": 0.15}},
                    {"step": 4000 * NUM_STEPS_PER_ENV, "params": {"launch_gate_floor": B.LAUNCH_GATE_FLOOR_FINAL}},
                ],
            },
        )
    cfg.curriculum["action_rate_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "action_rate_l2",
            "weight_stages": [
                {"step": 0, "weight": -0.05},
                {"step": 1500 * NUM_STEPS_PER_ENV, "weight": -0.1},
                {"step": 3000 * NUM_STEPS_PER_ENV, "weight": -0.2},
            ],
        },
    )
    cfg.curriculum["com_range"] = CurriculumTermCfg(
        func=microduck_mdp.com_range_curriculum,
        params={
            "event_name": "randomize_com",
            "range_stages": [
                {"step": 0, "range": 0.003},
                {"step": 500 * NUM_STEPS_PER_ENV, "range": 0.005},
                {"step": 1000 * NUM_STEPS_PER_ENV, "range": 0.01},
                {"step": 1500 * NUM_STEPS_PER_ENV, "range": 0.015},
            ],
        },
    )
    cfg.curriculum["head_com_range"] = CurriculumTermCfg(
        func=microduck_mdp.com_range_curriculum,
        params={
            "event_name": "randomize_head_com",
            "range_stages": [
                {"step": 0, "range": 0.003},
                {"step": 500 * NUM_STEPS_PER_ENV, "range": 0.005},
                {"step": 1000 * NUM_STEPS_PER_ENV, "range": 0.01},
            ],
        },
    )
    cfg.curriculum["gentle_landing_weight"] = CurriculumTermCfg(
        func=microduck_mdp.reward_weight,
        params={
            "reward_name": "gentle_landing",
            "weight_stages": [
                {"step": 0, "weight": 0.004},
                {"step": 1500 * NUM_STEPS_PER_ENV, "weight": 0.008},
                {"step": 3000 * NUM_STEPS_PER_ENV, "weight": 0.0125},
            ],
        },
    )

    if play:
        _apply_final_curriculum(cfg)
    return cfg
