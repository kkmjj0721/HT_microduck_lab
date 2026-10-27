# Copyright (c) 2021-2026, ETH Zurich and NVIDIA CORPORATION
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Learning algorithms.

Vendored subset: only PPO is included (distillation.py is not part of the
PPO/network reference set).
"""

from .. import _fallback

__path__ = _fallback.extend(__file__, __path__)

from .ppo import PPO

__all__ = ["PPO"]

# ``rsl_rl.runners`` (imported by mjlab) pulls ``Distillation`` from the installed
# wheel. Re-export it when available so that import keeps working; this subset
# itself only documents PPO.
try:
    from .distillation import Distillation
except ImportError:  # pragma: no cover - only when the wheel is absent
    pass
else:
    __all__ = ["PPO", "Distillation"]
