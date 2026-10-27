# Copyright (c) 2021-2026, ETH Zurich and NVIDIA CORPORATION
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause
"""Fill in submodules that this reference subset does not carry.

This directory is a partial mirror of RSL-RL (see ``VENDOR_NOTES.md``): it holds
the PPO algorithm and the network design, but not the runners, logger, or
distillation code.  Because it sits at the project root and Python puts the
current directory first on ``sys.path``, it shadows the ``rsl_rl`` wheel that
``mjlab`` depends on.  ``mjlab.rl`` imports ``rsl_rl.runners``, so the shadowing
would otherwise break that import.

``extend()`` appends the matching directory of the installed distribution to a
package's ``__path__``.  Vendored modules keep priority (they are found first),
and anything missing resolves from the wheel.  When the wheel is absent the call
is a no-op.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_ROOT)


def _installed_root() -> str | None:
    """Return the installed ``rsl_rl`` directory, skipping this checkout.

    ``.venv`` lives inside the project, so a prefix test against the project
    directory would wrongly discard the installed copy.  Skip only the exact
    vendored directory, and prefer a candidate that carries modules this subset
    lacks (e.g. ``runners``).
    """
    fallback: str | None = None
    for entry in sys.path:
        base = entry or os.getcwd()
        candidate = os.path.join(base, "rsl_rl")
        if not os.path.isfile(os.path.join(candidate, "__init__.py")):
            continue
        resolved = os.path.abspath(candidate)
        if resolved == _ROOT:
            continue
        if os.path.isdir(os.path.join(resolved, "runners")):
            return resolved
        fallback = fallback or resolved
    return fallback


def extend(package_file: str, path: list[str]) -> list[str]:
    """Append the installed counterpart of this package to ``path``."""
    root = _installed_root()
    if root is None:
        return path
    relative = os.path.relpath(os.path.dirname(os.path.abspath(package_file)), _ROOT)
    candidate = root if relative == "." else os.path.join(root, relative)
    if os.path.isdir(candidate) and candidate not in path:
        path.append(candidate)
    return path
