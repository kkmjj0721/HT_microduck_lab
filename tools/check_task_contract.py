# Copyright (c) 2026-2027 zh
"""检查官方任务配方在 HT 机器人上的观测、动作映射、局部重置和数值有限性。

用法：
    uv run --no-sync python -B tools/check_task_contract.py --device cuda:0
"""

import runpy
import sys
from pathlib import Path


def main() -> None:
    """调用显式验收文件，保持现有工具命令入口。"""
    target = Path(__file__).resolve().parents[1] / "tests" / "test_official_task_training.py"
    sys.argv = [str(target), "env", "--task", "HtDuck-Flat-Velocity", *sys.argv[1:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
