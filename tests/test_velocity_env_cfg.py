"""Configuration-level guards for the flat velocity task.

These do not build a MuJoCo environment, so they stay fast and run inside
``make check``. The runtime behaviour is covered by ``tools/check_velocity_env.py``.
"""

from __future__ import annotations

from ht_microduck.tasks import contract as C
from ht_microduck.tasks.config.flat_velocity_env_cfg import make_flat_velocity_env_cfg
from ht_microduck.tasks.mdp.observations import (
    ROBOT,
    SELF_COLLISION_SENSOR,
    self_collision_sensor,
)


def test_self_collision_sensor_filters_out_ground_contacts():
    """Both sides must be the robot subtree.

    With ``secondary=None`` the sensor also reports foot/terrain contacts, which
    made ``self_collisions`` a large constant penalty on a clean stance.
    """
    cfg = self_collision_sensor()
    assert cfg.secondary is not None, (
        "self-collision sensor lost its reference filter, so ground contacts "
        "will be counted as self-collisions again."
    )
    assert cfg.primary.mode == cfg.secondary.mode == "subtree"
    assert cfg.primary.pattern == cfg.secondary.pattern == "base_link"
    assert cfg.primary.entity == cfg.secondary.entity == ROBOT


def test_env_cfg_registers_the_filtered_self_collision_sensor():
    """The task must use the shared sensor factory, not a hand-rolled copy."""
    env_cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    sensors = {sensor.name: sensor for sensor in env_cfg.scene.sensors}
    assert SELF_COLLISION_SENSOR in sensors
    registered = sensors[SELF_COLLISION_SENSOR]
    assert registered.secondary is not None
    assert registered.secondary.mode == "subtree"
    assert registered.secondary.pattern == "base_link"


def test_self_collision_reward_uses_the_filtered_sensor():
    env_cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    assert env_cfg.rewards["self_collisions"].params["sensor_name"] == (
        SELF_COLLISION_SENSOR
    )


def test_velocity_task_actor_observation_matches_the_contract():
    env_cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    assert tuple(env_cfg.observations["actor"].terms) == C.ACTOR_OBSERVATION_TERMS


def test_velocity_task_keeps_the_official_live_body_pose_slot():
    """官方保留六维小范围躯干命令槽，但行走任务不奖励躯干指令跟踪。"""
    env_cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    assert C.ACTOR_OBSERVATION_DIMS["body_command"] == 6
    assert env_cfg.commands["body_pose"].dim == 6
    assert env_cfg.rewards["body_pose_tracking"].weight == 0.0


def test_velocity_task_head_pose_slot_width_matches_the_contract():
    env_cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    assert env_cfg.commands["head_pose"].dim == C.ACTOR_OBSERVATION_DIMS["head_command"]


def test_official_tasks_use_unit_actions_and_keep_legacy_velstand_mapping():
    from ht_microduck.tasks.config.flat_sitstand_env_cfg import make_sitstand_env_cfg
    from ht_microduck.tasks.config.flat_standup_env_cfg import make_standup_env_cfg
    from ht_microduck.tasks.config.flat_velstand_env_cfg import make_velstand_env_cfg

    cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    assert cfg.actions["joint_pos"].scale == 1.0
    assert C.WALKING_ACTION_SCALE == 0.25
    assert cfg.commands["head_pose"].ranges == (
        (-0.05, 0.05), (-0.05, 0.05), (-0.07, 0.07), (-0.015, 0.015)
    )
    for make_cfg in (make_sitstand_env_cfg, make_standup_env_cfg, make_velstand_env_cfg):
        skill = make_cfg(num_envs=1, seed=0)
        assert skill.actions["joint_pos"].scale == C.ACTION_SCALE == 1.0
        if make_cfg is make_velstand_env_cfg:
            assert skill.commands["head_pose"].ranges == (
                (-1.10, 1.10), (-1.10, 1.10), (-1.40, 1.40), (-0.31, 0.31)
            )
        else:
            assert skill.commands["head_pose"].ranges == cfg.commands["head_pose"].ranges


def test_air_time_sensor_and_play_disturbance_follow_the_official_recipe():
    from ht_microduck.tasks.mdp.observations import FEET_SENSOR

    train = make_flat_velocity_env_cfg(num_envs=1, seed=0)
    play = make_flat_velocity_env_cfg(num_envs=1, seed=0, play=True)
    sensors = {sensor.name: sensor for sensor in train.scene.sensors}
    assert sensors[FEET_SENSOR].track_air_time
    assert train.events["push_robot"].interval_range_s == (3.0, 6.0)
    assert play.events["push_robot"].interval_range_s == (0.5, 1.0)



def test_official_velocity_uses_leg_pose_without_local_extra_costs():
    from mjlab.tasks.velocity import mdp as velocity_mdp

    from ht_microduck.tasks.config.flat_velstand_env_cfg import make_velstand_env_cfg

    for play in (False, True):
        cfg = make_flat_velocity_env_cfg(num_envs=1, seed=0, play=play)
        term = cfg.rewards["pose"]
        assert term.func is velocity_mdp.variable_posture
        assert term.weight == 1.0
        assert term.params["asset_cfg"].joint_names == C.LEG_JOINT_NAMES
        assert term.params["walking_threshold"] == 0.01
        assert not {"stand_still", "idle_feet", "joint_torques_l2", "joint_vel_l2"} & cfg.rewards.keys()
        skill = make_velstand_env_cfg(num_envs=1, seed=0, play=play)
        assert "idle_feet" not in skill.rewards
        assert "stand_still" not in skill.rewards
        assert skill.rewards["joint_torques_l2"].weight == -2e-4
        assert skill.rewards["joint_vel_l2"].weight == -2e-4
