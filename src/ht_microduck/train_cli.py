"""``duck-train`` — the official mjlab training entry point, on this project's rsl_rl.

The command line is mjlab's, unchanged: the first positional argument is a task
id from the registry, and every ``--env.*`` / ``--agent.*`` flag overrides the
task's ``ManagerBasedRlEnvCfg`` / ``RslRlOnPolicyRunnerCfg``. Delegating instead
of reimplementing is what keeps the log layout, the console panel, the checkpoint
naming and multi-GPU launching identical to upstream ``microduck_rl``.

What this shim adds is the two import-order guarantees documented in
:mod:`ht_microduck`: the in-repo ``rsl_rl/`` (a complete copy of rsl-rl-lib
5.4.2) is put ahead of the wheel, and ``mjlab`` finishes importing before any
submodule of this package starts. Both have to happen before
``mjlab.scripts.train`` is imported, which is why the package import comes first
and has no other purpose here.

``duck-train`` is deliberately *not* named ``train``: mjlab already installs a
``train`` console script, same-name scripts are last-writer-wins, and whichever
loses leaves a stale ``.venv/bin/train`` behind.
"""

from __future__ import annotations

import sys

import ht_microduck  # noqa: F401  (applies the import-order guarantees)


def main() -> int | None:
    from mjlab.scripts.train import main as mjlab_train_main

    return mjlab_train_main()


if __name__ == "__main__":
    sys.exit(main())
