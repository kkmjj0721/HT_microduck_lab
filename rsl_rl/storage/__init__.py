# Copyright (c) 2021-2026, ETH Zurich and NVIDIA CORPORATION
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Storage for the learning algorithms."""

from .. import _fallback

__path__ = _fallback.extend(__file__, __path__)

from .rollout_storage import RolloutStorage

__all__ = ["RolloutStorage"]
