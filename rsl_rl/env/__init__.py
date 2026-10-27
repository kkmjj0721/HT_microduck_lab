# Copyright (c) 2021-2026, ETH Zurich and NVIDIA CORPORATION
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Environment definition."""

from .. import _fallback

__path__ = _fallback.extend(__file__, __path__)

from .vec_env import VecEnv

__all__ = ["VecEnv"]
