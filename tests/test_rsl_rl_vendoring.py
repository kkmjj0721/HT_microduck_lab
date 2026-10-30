"""The training stack must resolve to this repository's ``rsl_rl/``.

Training, replay and export all import ``rsl_rl`` from the repository root, not
from the ``rsl-rl-lib`` wheel that ``mjlab`` pulls in transitively. That only
holds if the package is complete: while it was a partial mirror, ``_fallback.py``
extended each subpackage ``__path__`` into site-packages, so ``OnPolicyRunner``
and ``Logger`` -- the training loop and the console panel themselves -- silently
came from the wheel.

These tests fail if the vendored copy drifts back to a subset.

Importing :mod:`ht_microduck` first is deliberate: that is what every real entry
point does (``duck-train``, ``duck-play``, ``python -c "import ht_microduck"``),
and the ``sys.path`` preference lives in its ``__init__``. Importing ``rsl_rl``
before it would make the answer depend on whether the working directory happens
to be on ``sys.path`` -- true under ``python -m pytest``, false under a bare
``.venv/bin/pytest`` -- and the test would then pass or fail for the wrong reason.
``test_the_sys_path_preference_holds_from_a_hostile_ordering`` covers the ordering
that a console script actually sees.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import ht_microduck  # noqa: F401  (must precede any rsl_rl import; see the docstring)

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDORED = REPO_ROOT / "rsl_rl"

# Modules the training entry point actually executes, plus the subpackages whose
# ``__init__`` used to be rewritten by the fallback shim.
TRAINING_PATH = (
    ("rsl_rl", None),
    ("rsl_rl.algorithms", "PPO"),
    ("rsl_rl.algorithms.ppo", "PPO"),
    ("rsl_rl.runners", "OnPolicyRunner"),
    ("rsl_rl.runners.on_policy_runner", "OnPolicyRunner"),
    ("rsl_rl.utils.logger", "Logger"),
    ("rsl_rl.models.mlp_model", "MLPModel"),
    ("rsl_rl.modules", "MLP"),
    ("rsl_rl.storage", "RolloutStorage"),
    ("rsl_rl.env", "VecEnv"),
    ("rsl_rl.extensions", "Symmetry"),
)


def test_package_is_the_vendored_copy():
    import rsl_rl

    assert Path(rsl_rl.__file__).resolve() == VENDORED / "__init__.py"


def test_package_path_has_no_site_packages_fallback():
    """A single ``__path__`` entry means nothing falls through to the wheel."""
    import rsl_rl

    resolved = [Path(entry).resolve() for entry in rsl_rl.__path__]
    assert resolved == [VENDORED], (
        "rsl_rl.__path__ points outside the repository, so some submodules load "
        f"from site-packages: {resolved}"
    )


def test_fallback_shim_is_gone():
    """The shim would silently re-create the partial-mirror behaviour."""
    assert not (VENDORED / "_fallback.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("rsl_rl._fallback")


@pytest.mark.parametrize(("module_name", "attribute"), TRAINING_PATH)
def test_training_path_module_lives_in_the_repository(module_name, attribute):
    module = importlib.import_module(module_name)
    assert Path(module.__file__).resolve().is_relative_to(VENDORED)
    if attribute is not None:
        owner = getattr(module, attribute)
        source = Path(importlib.import_module(owner.__module__).__file__).resolve()
        assert source.is_relative_to(VENDORED)


def test_runner_and_logger_come_from_the_vendored_copy():
    """The two modules the old partial mirror had to borrow from the wheel."""
    from rsl_rl.runners import OnPolicyRunner
    from rsl_rl.utils.logger import Logger

    for owner in (OnPolicyRunner, Logger):
        source = Path(importlib.import_module(owner.__module__).__file__).resolve()
        assert source.is_relative_to(VENDORED), f"{owner.__name__} resolved to {source}"


def test_vendored_copy_covers_every_wheel_module():
    """Every module the installed distribution ships must exist in the vendored tree.

    This is the check the removed ``_fallback.py`` used to make unnecessary: a module
    present in the wheel but missing here would have been silently loaded from
    site-packages, so a gap must fail instead of loading.
    """
    import importlib.metadata

    distribution = importlib.metadata.distribution("rsl-rl-lib")
    wheel_root = Path(distribution.locate_file("rsl_rl"))

    def module_names(root: Path) -> set[str]:
        return {
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        }

    wheel_modules = module_names(wheel_root)
    vendored_modules = module_names(VENDORED)
    assert wheel_modules, f"no modules found under {wheel_root}"

    missing = wheel_modules - vendored_modules
    assert not missing, f"vendored rsl_rl is missing modules the wheel ships: {sorted(missing)}"


def test_the_sys_path_preference_holds_from_a_hostile_ordering():
    """A console script starts with ``.venv/bin`` first, not the project root.

    ``-P`` drops the script directory and the current directory from ``sys.path``,
    which is the worst case a real entry point meets. ``ht_microduck`` is imported
    first here because that is what every entry point does (``duck-train``,
    ``duck-play``, ``python -c "import ht_microduck"``); the ``sys.path`` preference
    lives in its ``__init__``.

    Run out-of-process so modules already imported by this test session cannot
    mask whether the preference works.
    """
    script = (
        "import ht_microduck, importlib; "
        "import rsl_rl; "
        "from rsl_rl.runners import OnPolicyRunner; "
        "from rsl_rl.utils.logger import Logger; "
        "print(rsl_rl.__file__); print(list(rsl_rl.__path__)); "
        "print(importlib.import_module(OnPolicyRunner.__module__).__file__); "
        "print(importlib.import_module(Logger.__module__).__file__)"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-P", "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    package, paths, runner, logger = completed.stdout.strip().splitlines()

    assert Path(package) == VENDORED / "__init__.py", (
        "with the project root off sys.path the wheel won, so the preference in "
        "ht_microduck.__init__ is not doing its job"
    )
    assert paths == f"['{VENDORED}']"
    assert Path(runner).is_relative_to(VENDORED)
    assert Path(logger).is_relative_to(VENDORED)


def test_importing_rsl_rl_first_still_yields_the_wheel():
    """Documents the one ordering the preference cannot fix.

    Python caches a module on first import, so a caller that does ``import rsl_rl``
    before ``import ht_microduck`` -- *while the repository root is off ``sys.path``*,
    as in a console script or with ``-P`` -- keeps the wheel copy. (Running from the
    repository root puts the cwd on ``sys.path``, so the same order happens to work
    there; this test pins the strict case.) This is interpreter behaviour, not
    something the package can intercept, so it is asserted rather than assumed.
    """
    script = "import rsl_rl; print(rsl_rl.__file__)"
    completed = subprocess.run(
        [sys.executable, "-B", "-P", "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "site-packages" in completed.stdout
