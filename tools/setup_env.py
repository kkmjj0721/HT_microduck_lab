"""Match the installed CUDA Toolkit to a PyTorch extra and sync the environment.

Uses only the Python standard library so it can run before dependencies exist.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUDA_BACKENDS = {
    "cu118": (11, 8),
    "cu126": (12, 6),
    "cu128": (12, 8),
    "cu129": (12, 9),
    "cu130": (13, 0),
}


def find_nvcc(cuda_home: Path | None = None) -> Path:
    """Find the selected Toolkit without switching to another installation."""
    home = cuda_home or os.environ.get("CUDA_HOME") or os.environ.get("CUDA_PATH")
    if home is not None:
        nvcc = Path(home).expanduser() / "bin" / "nvcc"
        if not nvcc.is_file():
            raise RuntimeError(f"指定的 CUDA Toolkit 中找不到 nvcc：{nvcc}")
        return nvcc.resolve()

    on_path = shutil.which("nvcc")
    if on_path is not None:
        return Path(on_path).resolve()
    nvcc = Path("/usr/local/cuda/bin/nvcc")
    if nvcc.is_file():
        return nvcc.resolve()
    raise RuntimeError(
        "找不到本机 CUDA Toolkit 的 nvcc。请设置 CUDA_HOME、CUDA_PATH，"
        "或使用 --cuda-home 指定已经安装的 Toolkit 目录。"
    )


def detect_cuda_version(nvcc: Path) -> tuple[int, int]:
    """Read the installed Toolkit's major/minor version from nvcc --version."""
    try:
        result = subprocess.run(
            [str(nvcc), "--version"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"无法读取本机 CUDA Toolkit 版本：{nvcc}") from error

    output = result.stdout + "\n" + result.stderr
    match = re.search(r"\brelease\s+(\d+)\.(\d+)\b", output)
    if result.returncode != 0 or match is None:
        raise RuntimeError(f"无法从 {nvcc} --version 解析 CUDA Toolkit 版本。")
    return int(match.group(1)), int(match.group(2))


def select_backend(cuda_version: tuple[int, int]) -> str:
    backend = f"cu{cuda_version[0]}{cuda_version[1]}"
    if backend not in CUDA_BACKENDS:
        detail = (
            "官方 cu117 的 PyTorch 构建最高为 2.0.1，且没有 Python 3.12 wheel"
            if cuda_version == (11, 7)
            else f"当前锁文件没有与 {backend} 精确匹配的兼容依赖组合"
        )
        raise RuntimeError(
            f"本机 CUDA Toolkit 为 {cuda_version[0]}.{cuda_version[1]}（{backend}）；"
            f"{detail}。本项目使用 mjlab 1.6.0、torch>=2.7 和 Python 3.12。"
            "请准备匹配的 CUDA Toolkit，可用 --cuda-home 指定其目录。"
        )
    return backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--backend", choices=("auto", "cpu", *CUDA_BACKENDS), default="auto",
        help="默认根据本机 CUDA Toolkit 精确匹配；也可显式指定后端。",
    )
    selection.add_argument(
        "--cuda-home", type=Path, help="选择本机已安装的 CUDA Toolkit 目录。",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅显示选择结果和安装命令。"
    )
    parser.add_argument("--no-dev", action="store_true", help="不安装开发工具。")
    parser.add_argument(
        "--no-export", action="store_true", help="不安装 ONNX 导出依赖。"
    )
    args = parser.parse_args(argv)

    try:
        if sys.platform != "linux" or platform.machine() not in ("x86_64", "amd64"):
            raise RuntimeError("当前项目的依赖配置仅支持 Linux x86_64。")
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("找不到 uv，请先按 docs/setup.md 安装 uv。")

        backend = args.backend
        if backend == "auto":
            nvcc = find_nvcc(args.cuda_home)
            version = detect_cuda_version(nvcc)
            print(
                f"本机 CUDA Toolkit：{version[0]}.{version[1]}（{nvcc}）。",
                flush=True,
            )
            backend = select_backend(version)
            print(f"精确匹配 PyTorch 后端 {backend}。", flush=True)
        else:
            print(f"手动选择 PyTorch 后端 {backend}。", flush=True)

        command = [uv, "sync", "--locked", "--python", "3.12", "--extra", backend]
        if not args.no_export:
            command.extend(["--extra", "export"])
        if args.no_dev:
            command.append("--no-dev")

        print(f"项目目录：{PROJECT_ROOT}", flush=True)
        print(f"安装命令：{shlex.join(command)}", flush=True)
        if args.dry_run:
            return 0
        return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode
    except (OSError, RuntimeError) as error:
        print(f"安装失败：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
