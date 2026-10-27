"""Configuration-level guards for the flat velocity task.

These do not build a MuJoCo environment, so they stay fast and run inside
``make check``. The runtime behaviour is covered by ``tools/check_velocity_env.py``.
"""

from __future__ import annotations

from ht_microduck.tasks.flat_velocity import make_flat_velocity_env_cfg
from ht_microduck.tasks.flat_velocity.velocity_env_cfg import (
    ROBOT,
    SELF_COLLISION_SENSOR,
    _self_collision_sensor,
)


def test_self_collision_sensor_filters_out_ground_contacts():
    """Both sides must be the robot subtree.

    With ``secondary=None`` the sensor also reports foot/terrain contacts, which
    made ``self_collisions`` a large constant penalty on a clean stance.
    """
    cfg = _self_collision_sensor()
    assert cfg.secondary is not None, (
        "self-collision sensor lost its reference filter, so ground contacts "
        "will be counted as self-collisions again."
    )
    assert cfg.primary.mode == cfg.secondary.mode == "subtree"
    assert cfg.primary.pattern == cfg.secondary.pattern == "base_link"
    assert cfg.primary.entity == cfg.secondary.entity == ROBOT


def test_env_cfg_registers_the_filtered_self_collision_sensor():
    """The task must use ``_self_collision_sensor()``, not a hand-rolled copy."""
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
