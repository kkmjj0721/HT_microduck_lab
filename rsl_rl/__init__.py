# Copyright (c) 2021-2026, ETH Zurich and NVIDIA CORPORATION
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Main module for the rsl_rl package.

This is a partial, read-only mirror of RSL-RL used as a reference for PPO and
network design; see ``VENDOR_NOTES.md``.  Missing submodules (runners, logger,
distillation) resolve from the installed ``rsl-rl-lib`` wheel so that ``mjlab``
keeps working.  Remove this directory once the reference is no longer needed.
"""

from . import _fallback

__path__ = _fallback.extend(__file__, __path__)
