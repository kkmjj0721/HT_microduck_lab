"""HT-Duck simulation and training package.

Two things happen here, in this order, before any submodule is imported.

1. **The in-repo ``rsl_rl`` wins over the wheel.** ``rsl_rl/`` at the repository
   root is a complete copy of ``rsl-rl-lib`` 5.4.2, and it is the code training,
   replay and export actually run. ``mjlab`` also depends on the wheel, so which
   copy Python imports depends purely on ``sys.path`` -- and a console script
   starts with ``.venv/bin``, not the project root, first. The preference is
   applied explicitly here, where it cannot be forgotten. It is a no-op for a
   non-editable install, where no copy sits next to the package.

2. **``mjlab`` is imported to completion.** Importing it runs mjlab's
   ``mjlab.tasks`` entry-point loader, which imports
   :mod:`ht_microduck.tasks`; that module builds the task configs out of
   ``ht_microduck.robot`` and ``ht_microduck.actuator``. If one of those
   subpackages were still part-way through its own ``__init__`` when the loader
   re-entered it, the import would fail with ``cannot import name ...
   (most likely due to a circular import)``. Doing it here, before anything else
   in this package starts, makes the order deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _prefer_repo_rsl_rl() -> None:
    """Put the project root ahead of site-packages so ``rsl_rl/`` wins."""
    if not (_REPO_ROOT / "rsl_rl" / "__init__.py").is_file():
        return
    root = str(_REPO_ROOT)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)


_prefer_repo_rsl_rl()

import mjlab  # noqa: E402,F401  (must follow the sys.path fix; see above)
