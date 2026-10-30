"""Guard swing incentives against standing-only and turn-in-place regressions."""

from types import SimpleNamespace

import torch

from ht_microduck.tasks.mdp.observations import FEET_SENSOR, ROBOT
from ht_microduck.tasks.mdp.rewards import feet_air_time, stand_still


def test_air_time_pays_during_swing_and_includes_yaw_commands():
    air_time = torch.tensor([
        [0.14, 0.0],  # A swing is rewarded before it lands.
        [0.20, 0.0],  # Pure yaw commands need the same stepping incentive.
        [0.20, 0.0],  # Standing commands must not reward unnecessary steps.
        [0.0, 0.0],   # Standing still cannot earn swing rewards.
        [0.10, 0.32], # Shuffling and holding a foot up are outside the band.
        [0.125, 0.3], # Both interval boundaries are excluded.
    ])
    commands = torch.tensor([
        [0.2, 0.0, 0.0],
        [0.0, 0.0, 0.5],
        [0.0, 0.0, 0.0],
        [0.2, 0.0, 0.0],
        [0.2, 0.0, 0.0],
        [0.2, 0.0, 0.0],
    ])
    env = SimpleNamespace(
        scene={FEET_SENSOR: SimpleNamespace(data=SimpleNamespace(current_air_time=air_time))},
        command_manager=SimpleNamespace(get_command=lambda name: commands),
        extras={"log": {}},
    )
    kwargs = dict(
        sensor_name=FEET_SENSOR,
        threshold_min=0.125,
        threshold_max=0.3,
        command_name="twist",
        command_threshold=0.01,
    )
    expected = torch.tensor([1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    assert torch.equal(feet_air_time(env, **kwargs), expected)
    # A second control step in the same swing must still pay: no landing edge
    # or manually cached contact history should be required.
    assert torch.equal(feet_air_time(env, **kwargs), expected)



def test_stand_still_uses_default_pose_and_only_idle_commands():
    commands = torch.tensor([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.2, 0.0, 0.0],
        [0.0, 0.0, 0.5],
        [0.005, 0.0, 0.0],
        [0.01, 0.0, 0.0],
        [0.0, 0.0, 0.0101],
    ])
    default = torch.tensor([[0.85, -1.2, 0.35, 0.0]]).repeat(len(commands), 1)
    position = default.clone()
    position[:, :3] += torch.tensor([0.1, -0.2, 0.05])
    position[0, :3] = default[0, :3]
    position[:, 3] += 1.0  # The unselected joint must not affect the cost.
    env = SimpleNamespace(
        scene={ROBOT: SimpleNamespace(data=SimpleNamespace(
            joint_pos=position, default_joint_pos=default,
        ))},
        command_manager=SimpleNamespace(get_command=lambda name: commands),
    )
    asset = SimpleNamespace(name=ROBOT, joint_ids=[0, 1, 2])
    result = stand_still(env, "twist", 0.01, asset)
    assert torch.allclose(result, torch.tensor([0.0, 0.35, 0.0, 0.0, 0.35, 0.35, 0.0]))
