"""Terrain sets for the flat and rough HT-Duck task families.

The rough set is deliberately **not** mjlab's ``ROUGH_TERRAINS_CFG``. That preset is
sized for a ~50 cm quadruped with a 20+ cm step budget, while the HT-Duck is 3.3 kg
with legs that lift a foot 1-2 cm at working gait; over the stock preset the robot
spawns inside obstacles and can never climb anything, so the curriculum would
measure nothing but falls. The heights below are scaled to what the foot clearance
reward (``target_height = 0.02``) actually achieves.

The mixture is chosen so that the *rough* tasks still spend most of their time on
ground that is roughly flat. A recovery skill trained only on rubble learns to be
lucky; a small step now and then is what forces the gait to generalise.
"""

from __future__ import annotations

from mjlab.terrains import TerrainEntityCfg
from mjlab.terrains.config import (
    flat,
    hf_pyramid_slope,
    hf_pyramid_slope_inv,
    pyramid_stairs,
    pyramid_stairs_inv,
    random_rough,
    wave_terrain,
)
from mjlab.terrains.terrain_generator import TerrainGeneratorCfg

FLAT_TERRAIN = TerrainEntityCfg(terrain_type="plane")

# Step heights and slopes scaled to this robot. 2.5 cm is the highest riser the
# HT-Duck clears without a running start (measured: the foot reaches 2 cm at the
# clearance target, so anything above that is a deliberate climbing task rather
# than a walking task).
_MAX_STEP = 0.025

ROUGH_TERRAINS_CFG = TerrainGeneratorCfg(
    size=(6.0, 6.0),
    border_width=10.0,
    num_rows=8,
    num_cols=12,
    sub_terrains={
        "flat": flat(proportion=0.30),
        "pyramid_stairs": pyramid_stairs(
            proportion=0.15,
            step_height_range=(0.0, _MAX_STEP),
            step_width=0.25,
            platform_width=1.5,
            border_width=0.5,
        ),
        "pyramid_stairs_inv": pyramid_stairs_inv(
            proportion=0.10,
            step_height_range=(0.0, _MAX_STEP),
            step_width=0.25,
            platform_width=1.5,
            border_width=0.5,
        ),
        "hf_pyramid_slope": hf_pyramid_slope(
            proportion=0.10,
            slope_range=(0.0, 0.3),
            platform_width=1.0,
            border_width=0.25,
        ),
        "hf_pyramid_slope_inv": hf_pyramid_slope_inv(
            proportion=0.10,
            slope_range=(0.0, 0.3),
            platform_width=1.0,
            border_width=0.25,
        ),
        "random_rough": random_rough(
            proportion=0.15,
            noise_range=(0.005, 0.02),
            noise_step=0.005,
            border_width=0.25,
        ),
        "wave_terrain": wave_terrain(
            proportion=0.10,
            amplitude_range=(0.0, 0.02),
            num_waves=3,
            border_width=0.25,
        ),
    },
    add_lights=True,
)

ROUGH_TERRAIN = TerrainEntityCfg(
    terrain_type="generator",
    terrain_generator=ROUGH_TERRAINS_CFG,
    env_spacing=2.5,
)

# Contact/constraint ceilings for the posture tasks: a robot lying on the ground
# has far more active contacts than a standing one (the trunk, both thighs and the
# feet all touch at once), so the walking task's 64/256 is doubled here. Measured
# peak on a prone spawn with 512 worlds stayed below 30 contacts / 90 constraints.
POSTURE_NCONMAX = 128
POSTURE_NJMAX = 512
