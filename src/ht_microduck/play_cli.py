"""``duck-play`` — the official mjlab replay entry point, on this project's rsl_rl.

Same contract as ``duck-train``: mjlab's ``PlayConfig`` verbatim, so
``--agent zero|random|trained``, ``--viewer auto|native|viser``,
``--checkpoint-file``, ``--video`` and the hot-swap ``CheckpointManager`` all
behave exactly as upstream. Importing :mod:`ht_microduck` first puts the in-repo
``rsl_rl/`` ahead of the wheel, so loading a checkpoint rebuilds the same network
classes the training run used.
"""

from __future__ import annotations

import sys

import ht_microduck  # noqa: F401  (applies the import-order guarantees)


def main() -> int | None:
    from mjlab.scripts.play import main as mjlab_play_main

    return mjlab_play_main()


if __name__ == "__main__":
    sys.exit(main())
