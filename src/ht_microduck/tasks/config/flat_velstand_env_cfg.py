# Copyright (c) 2026-2027 zh
"""配置 HT VelStand 的行走、身体姿态与倒地恢复环境。

恢复窗口、初态绝对概率与恢复奖励时序参考 microduck_rl@bae39f59
的 WARM_START=False 分支；保留 HT 的执行器、61/64/14 契约及恢复高度门限。
本阶段不包含官方热启动、专家蒸馏或完整硬件防护配方。
"""

from __future__ import annotations

import math

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.metrics_manager import MetricsTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.viewer import ViewerConfig

from ht_microduck.actuator.HD_1910_C001 import bam_init
from ht_microduck.actuator.HTDW_3532_02_DNE import htdw3532_init
from ht_microduck.robot.ht_microduck_constants import get_ht_microduck_robot_cfg
from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_velocity_env_cfg import COMMAND_RANGES
from ht_microduck.tasks.config.terrain import POSTURE_NCONMAX, POSTURE_NJMAX
from ht_microduck.tasks.mdp.action_metrics import (
    ActuatorSaturationDuration,
    actuator_saturation_fraction,
    applied_target_violation_fraction,
    requested_target_violation_fraction,
    target_clip_fraction,
)
from ht_microduck.tasks.mdp.actions import BoundedJointPositionActionCfg
from ht_microduck.tasks.mdp.commands import (
    BODY_POSE_DIM,
    HEAD_POSE_DIM,
    StandingGatedPoseCommandCfg,
    UniformPoseCommandCfg,
)
from ht_microduck.tasks.mdp.curriculums import event_param_curriculum
from ht_microduck.tasks.mdp.events import reset_to_ground_state
from ht_microduck.tasks.mdp.observations import (
    BODY_CONTACT_SENSOR,
    FEET_SENSOR,
    FOOT_SITE_NAMES,
    HEAD_JOINTS,
    ROBOT,
    SELF_COLLISION_SENSOR,
    actor_terms,
    body_contact_sensor,
    critic_terms,
    feet_contact_sensor,
    head_contact_sensor,
    self_collision_sensor,
)
from ht_microduck.tasks.mdp.official_posture_rewards import (
    body_pose_tracking_locomotion,
)
from ht_microduck.tasks.mdp.posture import (
    RewardStateReset,
    action_rate_l2_fallen_scaled,
    body_impact_cost,
    com_upward_velocity,
    fallen_tax,
    fallen_too_long,
    feet_air_time_upright,
    head_pose_tracking,
    height_progress,
    recovery_success,
    trunk_downward_velocity_penalty,
    trunk_vertical_accel_penalty,
    upright_body_cmd_relative,
    upright_gaussian_at_height,
    upright_progress,
)
from ht_microduck.tasks.mdp.rewards import (
    feet_clearance,
    feet_slip,
    self_collision_cost,
    state_is_nan,
    track_angular_velocity,
    track_linear_velocity,
)

__all__ = [
    "GROUND_STATE_MIX",
    "make_velstand_env_cfg",
    "velstand_curriculum",
]

# ---------------------------------------------------------------------------------
# Reward and gate constants.
#
# The weight magnitudes follow the official recipe after its 4x mass normalisation; the
# gates are this robot's measured heights (T049). Anything that was a measured height
# upstream is expressed here as a fraction of this robot's own range, because copying
# the absolute number would put the gate above the standing height.
# ---------------------------------------------------------------------------------

# 恢复角度沿用官方 40°/25°；完成高度继续使用 HT 实测门限。
RECOVERY_TILT_DEG = 40.0
RECOVERY_UP_TILT_DEG = 25.0
RECOVERY_UP_Z = C.RECOVERED_Z
RECOVERY_MIN_FALLEN_S = 0.5

# 一般倾角终止仅用于最初的行走阶段；500 迭代后允许倒地恢复。
INITIAL_FALL_LIMIT_DEG = 70.0
FELL_OVER_DISABLE_ITER = 500
TERM_GATE_Z = C.FALLEN_Z
TERM_GATE_TILT_DEG = 40.0
FALLEN_TIMEOUT_S = 8.0

# Reward gate for the tilted-state modifiers.
REWARD_GATE_TILT_DEG = 40.0
HEIGHT_CEILING = C.STAND_Z
# 官方上升辅助截止值为站高加 1 cm，映射到 HT 站高后仍覆盖起身末段。
COM_MAX_HEIGHT = C.STAND_Z + 0.01

# Impact pricing. Body weight is 3.2947 kg * 9.81 = 32.3 N, so these are all below one
# body weight: a real impact is well above them, while bracing on the ground to get up
# is not.
HEAD_IMPACT_N = 15.0
BODY_IMPACT_N = 20.0

# ---- curriculum ------------------------------------------------------------------
# **Curriculum steps are counted in environment steps, not iterations.** mjlab compares
# each stage against ``env.common_step_counter``, which advances once per environment
# step, so a stage intended to fire at iteration N must be written ``N * steps_per_iter``.
# mjlab's own velocity task does exactly this (``5000 * 24`` in
# ``tasks/velocity/velocity_env_cfg.py``). Writing the iteration count here would make
# every stage fire 24x too early -- the ground-start mixture would be at full strength
# within the first 25 iterations, before any gait existed.
STEPS_PER_ITER = 24


def _iter(iterations: int) -> int:
    """Convert an iteration count to the environment-step count mjlab compares."""
    return iterations * STEPS_PER_ITER


def assert_curriculum_units(rl_cfg: object) -> None:
    """Fail loudly if ``STEPS_PER_ITER`` has drifted from the runner's rollout length.

    The staged numbers were chosen in *iterations*, but mjlab compares them against
    environment steps, so the conversion factor has to match ``num_steps_per_env`` on
    the runner config. The two live in different objects and cannot be derived from one
    another at import time, so this is checked instead of assumed: a silent mismatch
    would shift every curriculum stage by a constant factor, which is invisible in the
    logs and would look like "the curriculum does not work".
    """
    actual = getattr(rl_cfg, "num_steps_per_env", None)
    if actual is not None and actual != STEPS_PER_ITER:
        raise ValueError(
            f"STEPS_PER_ITER={STEPS_PER_ITER} but the runner uses "
            f"num_steps_per_env={actual}; every curriculum stage would fire "
            f"{actual / STEPS_PER_ITER:g}x off"
        )


# 官方 bae39f59 非热启动初态课程；元组依次为 prone/crouch/side/face_down。
# prone 与 crouch 是绝对份额，side 与 face_down 只在 prone 内部条件采样。
# crouch 映射到 HT 已确认低姿态，其余概率保留给站立，不归一化到地面分组。
GROUND_STATE_MIX: tuple[tuple[int, tuple[float, float, float, float]], ...] = (
    (0, (0.00, 0.00, 0.50, 1.00)),
    (_iter(800), (0.00, 0.20, 0.50, 1.00)),
    (_iter(1_500), (0.15, 0.20, 0.50, 0.80)),
    (_iter(2_000), (0.30, 0.20, 0.50, 0.65)),
    (_iter(2_500), (0.45, 0.20, 0.50, 0.50)),
)
GROUND_STATE_PARAM_NAMES = ("prone_prob", "crouch_prob", "side_prob", "face_down_prob")
RECOVERY_ECON_KICKIN_ITER = 1_200

# Reward gate for the protective-fall shaping: while heavily tilted the smoothness tax
# is scaled down so that an attempt is affordable. 0.1 is upstream's value.
FALLEN_SMOOTHNESS_SCALE = 0.1

_WEIGHT_SCALE = 1.0


def velstand_curriculum(play: bool = False) -> dict:
    """在配置入口校验分布并装配官方非热启动课程，边界采用 mjlab 的 >=。"""
    if not GROUND_STATE_MIX or GROUND_STATE_MIX[0][0] != 0:
        raise ValueError("The ground-state curriculum must start at step zero.")
    previous_step = -1
    for step, probabilities in GROUND_STATE_MIX:
        if not isinstance(step, int) or step <= previous_step:
            raise ValueError("Ground-state curriculum steps must be increasing integers.")
        previous_step = step
        if len(probabilities) != len(GROUND_STATE_PARAM_NAMES) or any(
            not math.isfinite(probability) or not 0.0 <= probability <= 1.0
            for probability in probabilities
        ):
            raise ValueError("Ground-state probabilities must be finite values in [0, 1].")
        prone_prob, crouch_prob, _, _ = probabilities
        if prone_prob + crouch_prob > 1.0:
            raise ValueError("Prone and crouch probabilities must sum to at most one.")
    for iteration in (FELL_OVER_DISABLE_ITER, RECOVERY_ECON_KICKIN_ITER):
        if not isinstance(iteration, int) or iteration < 0:
            raise ValueError("Recovery curriculum iterations must be nonnegative integers.")

    curriculum = {
        "ground_state_mix": CurriculumTermCfg(
            func=event_param_curriculum,
            params={
                "event_name": "reset_ground_or_stand",
                "stages": [
                    {"step": step, "params": dict(zip(GROUND_STATE_PARAM_NAMES, probabilities))}
                    for step, probabilities in GROUND_STATE_MIX
                ],
            },
        ),
    }
    # 500→1200 迭代留给无恢复税的探索，三项在 1200 边界同步启用。
    for name, reward_name, weight in (
        ("recovery_economy", "fallen_tax", -0.5),
        ("recovery_bounty_weight", "recovery_bounty", 10.0),
        ("com_upward_weight", "com_upward_velocity", 2.0),
    ):
        curriculum[name] = CurriculumTermCfg(
            func=envs_mdp.reward_curriculum,
            params={
                "reward_name": reward_name,
                "stages": [
                    {"step": 0, "weight": 0.0},
                    {"step": _iter(RECOVERY_ECON_KICKIN_ITER), "weight": weight},
                ],
            },
        )
    if not play:
        curriculum["fell_over_disable"] = CurriculumTermCfg(
            func=envs_mdp.termination_curriculum,
            params={
                "termination_name": "fell_over",
                "stages": [
                    {"step": 0, "params": {"limit_angle": math.radians(INITIAL_FALL_LIMIT_DEG)}},
                    {"step": _iter(FELL_OVER_DISABLE_ITER), "params": {"limit_angle": math.pi}},
                ],
            },
        )
    return curriculum


def make_velstand_env_cfg(
    num_envs: int = 4096, seed: int | None = None, play: bool = False, *, bound_targets: bool = True
):
    """装配任务；回放直接关闭一般倾角终止，保留原推搡设置和恢复超时。"""
    curriculum = velstand_curriculum(play=play)
    robot_cfg = get_ht_microduck_robot_cfg()

    rewards = {
        # Zero-weight, class-based: it exists only so the manager's reset path clears
        # the per-episode reward buffers (see RewardStateReset). Without it, a new
        # episode's first potential difference is taken against the previous episode's
        # terminal state and pays a windfall for ending the episode.
        "reward_state_reset": RewardTermCfg(func=RewardStateReset, weight=0.0),
        # ---- walking -------------------------------------------------------------
        "track_linear_velocity": RewardTermCfg(
            func=track_linear_velocity,
            weight=2.0,
            params={"command_name": "twist", "std": math.sqrt(0.1)},
        ),
        "track_angular_velocity": RewardTermCfg(
            func=track_angular_velocity,
            weight=2.0,
            params={"command_name": "twist", "std": math.sqrt(0.5)},
        ),
        "air_time": RewardTermCfg(
            func=feet_air_time_upright,
            weight=3.0,
            params={
                "sensor_name": FEET_SENSOR,
                "threshold_min": 0.125,
                "threshold_max": 0.300,
                "gate_tilt_above_deg": REWARD_GATE_TILT_DEG,
                "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",)),
                "command_name": "twist",
                "command_threshold": 0.01,
            },
        ),
        "foot_clearance": RewardTermCfg(
            func=feet_clearance,
            weight=-2.0,
            params={
                "sensor_name": FEET_SENSOR,
                "target_height": 0.02,
                "command_name": "twist",
                "command_threshold": 0.01,
                "asset_cfg": SceneEntityCfg(ROBOT, site_names=FOOT_SITE_NAMES),
            },
        ),
        "foot_slip": RewardTermCfg(
            func=feet_slip,
            weight=-0.1,
            params={
                "sensor_name": FEET_SENSOR,
                "command_name": "twist",
                "command_threshold": 0.01,
                "asset_cfg": SceneEntityCfg(ROBOT, site_names=FOOT_SITE_NAMES),
            },
        ),
        # ---- standing and posture -------------------------------------------------
        "upright": RewardTermCfg(
            func=upright_body_cmd_relative,
            weight=2.0,
            params={
                "std": math.sqrt(0.05),
                "command_name": "body_pose",
                "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",)),
            },
        ),
        "upright_when_tall": RewardTermCfg(
            func=upright_gaussian_at_height,
            weight=1.5,
            params={
                "std": math.sqrt(0.05),
                "height_low": C.SIT_Z,
                "height_high": C.STAND_Z,
                "command_name": "body_pose",
            },
        ),
        # 身体指令保持六维，但官方本阶段只跟踪站立时的 z/roll/pitch。
        "body_pose_tracking": RewardTermCfg(
            func=body_pose_tracking_locomotion,
            weight=2.0,
            params={
                "command_name": "body_pose",
                "nominal_height": C.STAND_Z,
                "z_std": 0.01,
                "angle_std": math.radians(5.0),
                "axis_weights": (0.0, 0.0, 1.0, 1.0, 1.0, 0.0),
                "standing_gate_command_name": "twist",
                "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",)),
                "feet_cfg": SceneEntityCfg(ROBOT, site_names=FOOT_SITE_NAMES, preserve_order=True),
            },
        ),
        "head_pose_tracking": RewardTermCfg(
            func=head_pose_tracking,
            weight=1.0,
            params={"command_name": "head_pose", "std": 0.5, "asset_cfg": HEAD_JOINTS},
        ),
        # ---- recovery ------------------------------------------------------------
        # Potential-based: pays for *becoming* upright, never for holding a pose.
        "upright_progress": RewardTermCfg(func=upright_progress, weight=5.0),
        "height_progress": RewardTermCfg(
            func=height_progress,
            weight=30.0,
            params={"ceiling": HEIGHT_CEILING},
        ),
        # Upward trunk motion while tilted: makes the first centimetre of a get-up worth
        # something, which a goal-only reward cannot (zero gradient at zero motion).
        "com_upward_velocity": RewardTermCfg(
            func=com_upward_velocity,
            weight=0.0,
            params={
                "max_height": COM_MAX_HEIGHT,
                "gate_tilt_above_deg": REWARD_GATE_TILT_DEG,
            },
        ),
        "recovery_bounty": RewardTermCfg(
            func=recovery_success,
            weight=0.0,
            params={
                "fallen_tilt_deg": RECOVERY_TILT_DEG,
                "up_tilt_deg": RECOVERY_UP_TILT_DEG,
                "up_z": RECOVERY_UP_Z,
                "min_fallen_s": RECOVERY_MIN_FALLEN_S,
            },
        ),
        # ---------- 恢复成本 ----------
        # 与成功奖励、质心上升奖励一起在 1200 迭代边界启用。
        "fallen_tax": RewardTermCfg(
            func=fallen_tax,
            weight=0.0,
            params={
                "gate_tilt_above_deg": RECOVERY_TILT_DEG,
                "release_tilt_deg": RECOVERY_UP_TILT_DEG,
                "release_z": RECOVERY_UP_Z,
            },
        ),
        # ---- regularisation ------------------------------------------------------
        "dof_pos_limits": RewardTermCfg(func=envs_mdp.joint_pos_limits, weight=-1.0),
        "action_rate_l2": RewardTermCfg(
            func=action_rate_l2_fallen_scaled,
            weight=-0.1,
            params={
                "fallen_scale": FALLEN_SMOOTHNESS_SCALE,
                "gate_tilt_above_deg": REWARD_GATE_TILT_DEG,
            },
        ),
        "joint_torques_l2": RewardTermCfg(func=envs_mdp.joint_torques_l2, weight=-2e-4),
        "joint_vel_l2": RewardTermCfg(func=envs_mdp.joint_vel_l2, weight=-2e-4),
        "self_collisions": RewardTermCfg(
            func=self_collision_cost,
            weight=-1.0,
            params={"sensor_name": SELF_COLLISION_SENSOR},
        ),
        # ---- impact pricing (negative weights) -----------------------------------
        "head_impact": RewardTermCfg(
            func=body_impact_cost,
            weight=-0.01,
            params={"sensor_name": "head_ground_contact", "threshold_n": HEAD_IMPACT_N},
        ),
        "body_impact": RewardTermCfg(
            func=body_impact_cost,
            weight=-0.01,
            params={"sensor_name": BODY_CONTACT_SENSOR, "threshold_n": BODY_IMPACT_N},
        ),
        # POSITIVE weight: the function already returns a negative value.
        "descent_speed_cap": RewardTermCfg(
            func=trunk_downward_velocity_penalty,
            weight=1.0,
            params={"max_down_vel": 0.6},
        ),
        "trunk_accel": RewardTermCfg(func=trunk_vertical_accel_penalty, weight=1.0),
    }

    terminations = {
        "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
        # 初始 70° 门限用于建立行走；500 迭代后课程改为 pi。
        "fell_over": TerminationTermCfg(
            func=envs_mdp.bad_orientation,
            params={"limit_angle": math.radians(INITIAL_FALL_LIMIT_DEG)},
        ),
        # A robot that stays on the ground for long enough has failed the recovery; the
        # timer resets as soon as it is upright, so a slow but working get-up survives.
        "fell_over_timeout": TerminationTermCfg(
            func=fallen_too_long,
            params={
                "gate_z_below": TERM_GATE_Z,
                "gate_tilt_above_deg": TERM_GATE_TILT_DEG,
                "max_duration_s": FALLEN_TIMEOUT_S,
            },
        ),
        "nan_state": TerminationTermCfg(func=state_is_nan, time_out=False),
    }

    if play:
        # 回放不执行课程，必须在配置阶段直接移除一般倾角终止。
        terminations.pop("fell_over")

    # Push: horizontal only, and much gentler than upstream's +-0.5 m/s. This robot is
    # 3.3 kg; the stock range launches it, which would teach it to brace against impulses
    # it will never see.
    push_range = (
        {"x": (-1.2, 1.2), "y": (-1.2, 1.2)}
        if play
        else {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}
    )

    events = {
        "htdw3532_init": EventTermCfg(func=htdw3532_init, mode="startup"),
        "bam_init": EventTermCfg(func=bam_init, mode="startup"),
        # Ground starts are staged by curriculum. The parameters below are the
        # iteration-0 values (all mass on "no ground start"); the curriculum raises them.
        "reset_ground_or_stand": EventTermCfg(
            func=reset_to_ground_state,
            mode="reset",
            params={
                **dict(zip(GROUND_STATE_PARAM_NAMES, GROUND_STATE_MIX[0][1])),
                "position_noise": 0.03,
                "asset_cfg": SceneEntityCfg(ROBOT),
            },
        ),
        "push_robot": EventTermCfg(
            func=envs_mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=(0.6, 1.2) if play else (3.0, 6.0),
            params={"velocity_range": push_range},
        ),
        "foot_friction": EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg(
                    ROBOT, geom_names=("r_foot_collision", "l_foot_collision")
                ),
                "operation": "abs",
                "ranges": (0.7, 1.3),
                "shared_random": True,
            },
        ),
        "encoder_bias": EventTermCfg(
            mode="startup",
            func=dr.encoder_bias,
            params={"asset_cfg": SceneEntityCfg(ROBOT), "bias_range": (-0.015, 0.015)},
        ),
        "base_com": EventTermCfg(
            mode="startup",
            func=dr.body_com_offset,
            params={
                "asset_cfg": SceneEntityCfg(ROBOT, body_names=("base_link",)),
                "operation": "add",
                "ranges": {0: (-0.02, 0.02), 1: (-0.02, 0.02), 2: (-0.02, 0.02)},
            },
        ),
    }

    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            num_envs=num_envs,
            terrain=_terrain(),
            entities={ROBOT: robot_cfg},
            sensors=(
                feet_contact_sensor(),
                body_contact_sensor(),
                head_contact_sensor(),
                self_collision_sensor(),
            ),
            extent=2.0,
        ),
        observations={
            "actor": ObservationGroupCfg(
                terms=actor_terms(body_command="body_pose"),
                concatenate_terms=True,
                enable_corruption=True,
            ),
            "critic": ObservationGroupCfg(
                terms=critic_terms(body_command="body_pose"),
                concatenate_terms=True,
                enable_corruption=False,
            ),
        },
        actions={
            "joint_pos": BoundedJointPositionActionCfg(
                bound_targets=bound_targets,
                entity_name=ROBOT,
                actuator_names=tuple(C.POLICY_JOINT_NAMES),
                scale=C.ACTION_SCALE,
                use_default_offset=True,
                preserve_order=True,
            )
        },
        commands={
            "twist": UniformVelocityCommandCfg(
                entity_name=ROBOT,
                resampling_time_range=(4.0, 8.0),
                rel_standing_envs=0.20,
                rel_heading_envs=0.3,
                rel_forward_envs=0.3,
                heading_command=True,
                heading_control_stiffness=0.5,
                debug_vis=False,
                ranges=UniformVelocityCommandCfg.Ranges(**COMMAND_RANGES),
            ),
            "head_pose": UniformPoseCommandCfg(
                dim=HEAD_POSE_DIM,
                resampling_time_range=(2.0, 5.0),
                ranges=(
                    (-1.10, 1.10),
                    (-1.10, 1.10),
                    (-1.40, 1.40),
                    (-0.31, 0.31),
                ),
                zero_command_prob=0.25,
            ),
            # Body pose is a standing feature: gated on the twist term's standing flag,
            # so it is zero whenever the robot is walking. The deployed runtime sends a
            # zero body command while walking, so a policy that only ever saw non-zero
            # body commands would not transfer.
            "body_pose": StandingGatedPoseCommandCfg(
                dim=BODY_POSE_DIM,
                twist_command_name="twist",
                resampling_time_range=(2.5, 5.0),
                ranges=(
                    (-0.02, 0.02),
                    (-0.02, 0.02),
                    (-0.02, 0.02),
                    (-0.14, 0.14),
                    (-0.14, 0.14),
                    (-0.26, 0.26),
                ),
                zero_command_prob=0.35,
                # Per-axis zeros: holding the trunk still on one axis while moving
                # another is a distinct skill from the all-zero hold.
                axis_zero_prob=(0.3, 0.3, 0.3, 0.3, 0.3, 0.3),
            ),
        },
        rewards=rewards,
        terminations=terminations,
        events=events,
        curriculum=curriculum,
        metrics={
            "requested_target_outside_limits": MetricsTermCfg(func=requested_target_violation_fraction),
            "applied_target_outside_limits": MetricsTermCfg(func=applied_target_violation_fraction),
            "target_clip_fraction": MetricsTermCfg(func=target_clip_fraction),
            **{
                name: MetricsTermCfg(
                    func=func,
                    params={
                        "asset_cfg": SceneEntityCfg(
                            ROBOT, actuator_names=list(C.POLICY_JOINT_NAMES), preserve_order=True
                        ),
                        "ratio": 0.95,
                    },
                    reduce=reduce,
                )
                for name, func, reduce in (
                    ("actuator_saturation_fraction", actuator_saturation_fraction, "mean"),
                    ("actuator_saturation_duration", ActuatorSaturationDuration, "max"),
                )
            },
        },
        viewer=ViewerConfig(
            origin_type=ViewerConfig.OriginType.ASSET_BODY,
            entity_name=ROBOT,
            body_name="base_link",
            distance=1.5,
            elevation=-5.0,
            azimuth=90.0,
        ),
        sim=SimulationCfg(
            nconmax=POSTURE_NCONMAX,
            njmax=POSTURE_NJMAX,
            mujoco=MujocoCfg(
                timestep=C.PHYSICS_TIMESTEP, iterations=10, ls_iterations=20
            ),
        ),
        decimation=C.DECIMATION,
        episode_length_s=C.EPISODE_LENGTH_S,
        seed=seed,
    )


def _terrain():
    from ht_microduck.tasks.config.terrain import FLAT_TERRAIN

    return FLAT_TERRAIN
