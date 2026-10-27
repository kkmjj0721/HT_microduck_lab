# 环境安装

本文说明如何自动选择 PyTorch 的 CUDA 后端、按锁文件安装依赖，以及验证 GPU 环境。
所有项目命令均在仓库根目录执行。

## 环境要求

| 项目 | 配置 |
|---|---|
| 系统 | Linux x86_64 |
| GPU | NVIDIA GPU，驱动可通过 `nvidia-smi` 正常访问 |
| Python | 3.12，项目约束为 `>=3.12,<3.13` |
| 包管理 | uv |
| mjlab | 固定为 1.6.0 |
| PyTorch | `>=2.7,<3`，按本机 CUDA Toolkit 的实际版本精确匹配 wheel |
| 其他依赖 | 以仓库中的 `uv.lock` 为准 |

自动安装以 **本机实际选用的 CUDA Toolkit** 为准，通过 `nvcc --version` 读取主、次版本。
例如，本机 Toolkit 为 12.6 时选择 `cu126`。`nvidia-smi` 显示的是驱动能力，
安装脚本不会将其用作已安装 Toolkit 的版本。驱动与 PyTorch、Warp 的运行兼容性仍需检查。

## 1. 准备 uv 和 Python

检查工具和 GPU 驱动：

```bash
uv --version
nvidia-smi
nvcc --version
```

如果尚未安装 uv，可以使用[官方安装方式](https://docs.astral.sh/uv/getting-started/installation/)：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后重新打开终端，再确认 `uv --version` 可以运行。

进入本项目并准备 Python 3.12：

```bash
cd /home/sunteng/projects/HT_microduck_lab
uv python install 3.12
```

其他机器上的仓库路径不同时，替换上述 `cd` 路径。

## 2. 安装项目依赖

可以先预览识别结果和安装命令；此步骤不安装包，也不修改环境：

```bash
python3 tools/setup_env.py --dry-run
```

自动安装基础依赖、开发工具和策略导出依赖：

```bash
python3 tools/setup_env.py
```

脚本仅使用 Python 标准库，可以在项目依赖尚未安装时运行。它会找到本机选用的 `nvcc`，
解析 `nvcc --version`，将 Toolkit 的主、次版本精确转换为 PyTorch 后端，再执行带对应
`--extra` 的 `uv sync --locked --python 3.12`。

Toolkit 的选择优先级为：

1. 命令行 `--cuda-home` 指定的目录。
2. 环境变量 `CUDA_HOME`，其次为 `CUDA_PATH`。
3. 当前 `PATH` 中的 `nvcc`。
4. `/usr/local/cuda/bin/nvcc`。

如果显式指定的 Toolkit 目录无效，脚本直接报错。多版本共存时使用上述选定的 Toolkit，
不扫描并切换到其他版本。只有存在精确匹配的锁定依赖组合时才执行安装。
没有对应组合时会说明原因，不自动改用相邻 CUDA 版本。

这一步会在项目根目录创建 `.venv/`，并以可编辑方式安装 `ht-microduck`。
其中，`dev` 依赖组默认安装，包含 pytest 和 Ruff；`export` 包含 ONNX 和 ONNX Runtime。
可编辑安装使 `src/ht_microduck/` 中的 Python 源码修改直接生效。

`--locked` 会检查 `pyproject.toml` 与 `uv.lock` 是否一致，并保持锁定版本。
仓库的 `uv.lock` 同时记录各个后端的依赖组合，安装时只启用其中一个。
PyTorch 的具体版本仍由锁文件记录，同一个后端可以复现相同安装；不同后端的版本可能不同。
锁定和同步的行为见 [uv 官方说明](https://docs.astral.sh/uv/concepts/projects/sync/)。

自动选择后端，但只安装基础依赖时使用：

```bash
python3 tools/setup_env.py --no-dev --no-export
```

多版本 Toolkit 共存时，可以选择本机已经安装的目录，例如：

```bash
python3 tools/setup_env.py --cuda-home /usr/local/cuda-12.6
```

脚本仍提供显式覆盖参数，例如 `--backend cu126`；使用该参数会跳过 Toolkit 检测。
没有 GPU 的开发环境可显式使用 `--backend cpu`；本项目的 GPU 训练需要 CUDA 后端。

等价的手动 uv 命令是：

```bash
uv sync --locked --python 3.12 --extra cu126 --extra export
```

每次同步都需要选择后端；日常推荐继续使用安装脚本，以本机 Toolkit 自动匹配。
项目通过后端 extra 使用对应包源，保持与锁文件一致。
相关机制见 [uv 的 PyTorch 集成说明](https://docs.astral.sh/uv/guides/integration/pytorch/)。

包源已经在 [pyproject.toml](../pyproject.toml) 中配置：

| 包 | 包源 |
|---|---|
| PyTorch | `https://download.pytorch.org/whl/<所选后端>` |
| Warp | `https://pypi.nvidia.com/` |
| 其他依赖 | `https://pypi.tuna.tsinghua.edu.cn/simple`（清华 PyPI 镜像） |

普通依赖使用 [清华 PyPI 镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)，
减少访问 PyPI 官方文件服务器超时的情况。PyTorch 的 CUDA 后端选择不受此设置影响。

项目的 PPO、网络、轨迹存储、Runner 和训练入口将在本仓库实现。
RSL-RL 会随 mjlab 的依赖安装。

## 3. 验证安装和 GPU 环境

以下 GPU 检查用于 CUDA 后端安装，并假定包含 `export` 依赖。
匹配本机 Toolkit 不等于完成整个仿真栈的运行验证，Warp 也必须单独通过 GPU 检查。

检查 Python、包版本，以及 PyTorch 和 Warp 能否访问 GPU：

```bash
uv run --no-sync python - <<'PY'
import sys
from importlib.metadata import version

import ht_microduck
import mujoco
import torch
import warp as wp

assert sys.version_info[:2] == (3, 12), sys.version
assert version("mjlab") == "1.6.0"

print("Python:", sys.version.split()[0])
print("Project:", ht_microduck.__file__)
for package in ("mjlab", "torch", "mujoco", "mujoco-warp", "warp-lang"):
    print(f"{package}: {version(package)}")
print("PyTorch CUDA runtime:", torch.version.cuda)

assert torch.cuda.is_available(), "PyTorch 无法访问 CUDA，请检查驱动和安装环境"
torch.zeros(1, device="cuda:0")
torch.cuda.synchronize()
print("PyTorch GPU:", torch.cuda.get_device_name(0))

wp.init()
device = wp.get_device("cuda:0")
assert device.is_cuda
wp.zeros(1, dtype=wp.float32, device=device)
wp.synchronize()
print("Warp GPU:", device)
print("Python、包导入和 GPU 基础检查通过")
PY
```

检查导出依赖：

```bash
uv run --no-sync python -c \
  "import onnx, onnxruntime; print('ONNX:', onnx.__version__); print('ONNX Runtime:', onnxruntime.__version__)"
```

这些检查验证依赖和 GPU 基础环境。机器人环境创建、执行器响应和训练短跑需要在对应模块实现后另行验证。

模型加载与关节映射检查：

```bash
uv run --no-sync python tools/check_robot.py
```

本机有图形桌面时，可加 `--viewer` 静态查看机器人。当前检查验证 MJCF 编译与 15 个关节的电机映射，
执行器和训练环境仍需在后续步骤实现。

## 4. 日常使用和依赖维护

安装后通过 `uv run --no-sync` 使用现有项目环境，无需手动激活 `.venv/`。
`--no-sync` 保留刚刚选择的 PyTorch 后端，避免省略后端 extra 时重新同步。例如：

```bash
uv run --no-sync python
uv run --no-sync ruff check src tools tests
```

在新机器或更新仓库后，重新执行推荐的同步命令：

```bash
python3 tools/setup_env.py
```

检查锁文件与依赖声明是否一致：

```bash
uv lock --check --python 3.12
```

主动修改依赖声明后，重新解析并同步环境：

```bash
uv lock --python 3.12
python3 tools/setup_env.py
```

依赖发生变更时，将 `pyproject.toml` 和生成的 `uv.lock` 一起提交；锁文件由 uv 维护。

## 5. 当前训练入口状态

项目目前包含依赖配置、锁文件、机器人 MJCF 和 mesh 资源。
`ht_microduck_constants.py` 已记录关节分组与电机型号并实现 MJCF 加载，
`tools/check_robot.py` 提供模型编译、关节映射检查及静态预览。mjlab 实体、执行器、训练环境与本地算法链路待实现。

`pyproject.toml` 已用注释预留 `duck-train`、`duck-play`、`duck-eval` 和 `duck-export`。
实现 `ht_microduck.cli` 中对应的 `main()` 后，再启用这些入口并重新运行安装脚本。
当前安装完成后，还不能使用上述命令启动本项目训练。

## 常见问题

### 下载缓慢或出现 `operation timed out`

若错误中的下载地址为 `files.pythonhosted.org`，说明失败的是 PyPI 文件下载。
项目已将普通依赖切换到清华镜像，`uv.lock` 也由 uv 重新生成了对应下载地址。
保留现有 `.venv/` 和 uv 缓存，重新执行：

```bash
python3 tools/setup_env.py
```

首次安装的 PyTorch、CUDA 运行库和 Warp 文件较大，镜像源也不能消除这些下载量。
如果仍然超时，可以增加本次命令的 HTTP 读取超时：

```bash
UV_HTTP_TIMEOUT=600 python3 tools/setup_env.py
```

延长超时不会提高带宽；该设置说明见 [uv 环境变量文档](https://docs.astral.sh/uv/reference/environment/#uv_http_timeout)。
若失败地址属于 `download.pytorch.org`、`download-r2.pytorch.org` 或 NVIDIA，
需要检查到对应官方源的连接，普通 PyPI 镜像不会替换这些独立包源。

`uv.lock` 包含具体下载地址。以后更换普通依赖镜像时，应修改 `pyproject.toml` 中
名为 `pypi` 的 index URL，再执行 `uv lock --python 3.12`，检查版本变化后重新安装。
安装脚本使用 `--locked`，不会在安装时自行改写旧锁文件中的地址。

### PyTorch 或 Warp 无法访问 GPU

先确认 `nvidia-smi` 正常，再查看上方检查输出的包版本、PyTorch CUDA runtime 和具体错误。
两套库都需要各自通过 GPU 检查。脚本根据已安装 Toolkit 选择 PyTorch，
实际 GPU 运行还要求驱动满足 PyTorch 和 Warp 的要求。

### 当前开发机检查结果

本次检查（2026-10-22），开发机的 `/usr/local/cuda/bin/nvcc` 已指向
`/usr/local/cuda-13.0/bin/nvcc`，实际 Toolkit 为 13.0。
安装脚本成功精确匹配 `cu130`，已完成 151 个包的安装，包括 Python 3.12.14 环境中的
`torch==2.14.1+cu130`、`mjlab==1.6.0`、`mujoco==3.11.0` 和 `warp-lang==1.18.0`。
PyTorch 和 Warp 均在 NVIDIA GeForce RTX 4060 上通过 GPU 内存分配与同步检查，
ONNX 和 ONNX Runtime 导入检查通过。其他机器仍需执行上文检查。

### 检测到旧版 CUDA Toolkit 11.7

官方 `cu117` PyTorch wheel 最高为 2.0.1，且不提供 Python 3.12 构建，无法满足
mjlab 1.6.0 的 `torch>=2.7` 和本项目的 Python 3.12 要求。
版本记录见 [PyTorch 官方历史版本](https://pytorch.org/get-started/previous-versions/)。

因此，自动安装会报告版本冲突。保持当前项目要求时，需要先准备存在对应兼容 wheel 的
Toolkit（例如 12.6 或 12.8），再通过 `--cuda-home` 或 `CUDA_HOME` 选择它。
脚本只安装 Python 环境，不会修改系统 CUDA Toolkit 或 NVIDIA 驱动。

### 更换机器或 CUDA Toolkit 后想重新匹配

重新运行 `python3 tools/setup_env.py`，脚本会重新读取选定 `nvcc` 的版本。
可先加 `--dry-run` 查看计划；多版本共存时用 `--cuda-home` 指定目录。

### 提示锁文件需要更新

核对 `pyproject.toml` 和 `uv.lock` 是否来自同一次仓库更新。
需要复现已有环境时使用匹配的文件；主动调整依赖后，按“依赖维护”流程更新锁文件。
