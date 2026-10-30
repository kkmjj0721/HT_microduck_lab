"""The package layout must match upstream ``microduck_rl``.

Upstream keeps exactly three subpackages under ``src/mjlab_microduck/``:
``robot``, ``actuator`` and ``tasks``. Each robot's MJCF lives next to its
``assets/`` directory in a plain data folder, and callers import the constants
module directly instead of going through a package re-export.

These guards keep the layout from drifting: they fail on a re-introduced
``robots``/``actuators``/``algorithms``/``cli`` package and on a model file that
moved away from its meshes.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import pytest

from ht_microduck.robot.ht_microduck_constants import (
    JOINT_NAMES,
    MJCF_PATH,
    get_spec,
)

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "ht_microduck"

# Upstream's subpackage set. ``algorithms`` and ``cli`` were this repository's
# pre-RSL-RL training stack and are gone on purpose; ``robots``/``actuators``
# became the singular ``robot``/``actuator``.
ALLOWED_SUBPACKAGES = {"robot", "actuator", "tasks"}
# ``rl`` was an empty leftover directory removed in T046; it is listed so a stray
# recreation is caught, even though it never held code.
REMOVED_SUBPACKAGES = {"robots", "actuators", "algorithms", "cli", "rl"}


def test_only_upstream_subpackages_exist():
    found = {
        path.name
        for path in PACKAGE.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    assert found == ALLOWED_SUBPACKAGES


@pytest.mark.parametrize("name", sorted(REMOVED_SUBPACKAGES))
def test_removed_packages_stay_removed(name):
    path = PACKAGE / name
    assert not path.exists(), (
        f"{path} is back; upstream has no {name}/ and reintroducing it means a "
        "second way to do the same thing"
    )


def test_model_sits_next_to_its_meshes():
    model_dir = MJCF_PATH.parent
    assert model_dir == PACKAGE / "robot" / "ht_microduck"
    assert (model_dir / "assets").is_dir()
    assert (model_dir / "assets" / "base_link.STL").is_file()
    # The XML refers to meshes as ``assets/<file>``; a second nesting level would
    # break that relative lookup at compile time, which the next test catches.
    assert 'meshdir="assets/"' in MJCF_PATH.read_text()


def test_the_model_folder_is_data_not_a_package():
    """Upstream keeps ``robot/microduck/`` as data; only the constants module imports."""
    assert not (MJCF_PATH.parent / "__init__.py").exists()


def test_compiled_model_is_unchanged():
    """Path moves must not touch the model: same joints, meshes and mass."""
    model = get_spec().compile()
    joint_names = tuple(
        model.joint(index).name
        for index in range(model.njnt)
        if model.jnt_type[index] != mujoco.mjtJoint.mjJNT_FREE
    )
    assert joint_names == JOINT_NAMES
    assert model.njnt == 16  # 15 hinged joints + the free base
    assert model.nmesh == 16
    assert model.body_subtreemass[1] == pytest.approx(3.2947, abs=1e-4)
