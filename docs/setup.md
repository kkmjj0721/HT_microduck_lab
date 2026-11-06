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

## 1. 一键安装 .venv

在仓库根目录执行：

```bash
bash setup.sh
```

脚本参考 `/home/sunteng/projects/quadruped_lab/setup.sh`，自动发现 uv，缺失时通过官方安装器
安装到 `~/.local/bin`；随后调用本项目 `tools/setup_env.py`，由 uv 准备 Python 3.12、
创建或同步仓库根目录的 `.venv/`，默认包含开发工具和 ONNX 导出依赖。
已有环境直接同步，依赖版本受 `uv.lock` 约束。脚本可以通过绝对路径从其他目录启动，
安装目标仍固定为本项目 `.venv/`。

查看选项、预览安装计划或在无 CUDA Toolkit 的机器安装 CPU 依赖：

```bash
bash setup.sh --help
bash setup.sh --dry-run
bash setup.sh --torch-backend cpu
```

默认按本机 Toolkit **精确匹配** CUDA 后端，检测失败时会报告原因；CPU 后端需显式选择。
`--torch-backend` 与原安装器的 `--backend` 等价，也支持 `--cuda-home`、`--no-dev` 和
`--no-export`。`--dry-run` 不安装 uv、Python 或依赖，需要已有 uv 与可用的 Python 3.10+
（系统解释器或 uv 可发现的 Python 3.12）。

脚本安装 uv 时不修改 shell 配置，使用 [uv 官方安装器选项](https://docs.astral.sh/uv/reference/installer/)
`UV_INSTALL_DIR` 和 `UV_NO_MODIFY_PATH`。若安装结束提示 uv 不在当前终端 PATH 中，执行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

设置了 `UV_PROXY` 时，脚本为安装器与 Python 子进程补齐 HTTP/HTTPS 代理变量，保留已设置的代理值。
CUDA Toolkit、NVIDIA 驱动仍需由系统提供；GPU 环境可用 `nvidia-smi` 和 `nvcc --version` 检查。
安装后推荐 `uv run --no-sync ...`，也可在当前终端用 `source .venv/bin/activate` 激活。

## 2. 依赖同步与后端选择

以下为一键入口内部调用的 Python 安装器；已有 uv 和 Python 3.10+ 时也可直接使用。
它只依赖 Python 标准库；uv 在同步时准备项目所需的 Python 3.12。

可以先预览识别结果和安装命令；此步骤不安装包，也不修改环境：

```bash
python3 tools/setup_env.py --dry-run
```

自动安装基础依赖、开发工具和策略导出依赖：

```bash
python3 tools/setup_env.py
```

安装器会找到本机选用的 `nvcc`，
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
| Warp（`cpu` / `cu130`） | `https://pypi.nvidia.com/` |
| Warp（`cu118` / `cu126` / `cu128` / `cu129`） | NVIDIA Warp 官方 GitHub Release 的 `1.18.0+cu12` wheel |
| 其他依赖 | `https://pypi.tuna.tsinghua.edu.cn/simple`（清华 PyPI 镜像） |

普通依赖使用 [清华 PyPI 镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)，
减少访问 PyPI 官方文件服务器超时的情况。PyTorch 的 CUDA 后端选择不受此设置影响。

Warp 的构建也需要匹配驱动。按 [Warp v1.18.0 官方安装说明](https://github.com/NVIDIA/warp/blob/v1.18.0/docs/user_guide/installation.rst)，
默认 wheel 使用 CUDA 13.4，要求 R580 及以上驱动；官方同版本 `+cu12` 构建要求 R525 及以上。
本项目为 CUDA 12 系列及 `cu118` 后端锁定此兼容构建，`cpu` 和 `cu130` 保留 NVIDIA 源。
这不会切换系统 Toolkit，也不保证旧驱动可运行全部仿真依赖；PyTorch、Warp 与 GPU JIT
仍需按下一节分别验证。每次运行 `setup.sh` 都按后端恢复对应的锁定构建。

RSL-RL wheel 会随 mjlab 的依赖安装；训练实际使用的 PPO、网络、轨迹存储和 Runner
来自本仓库根目录的 `rsl_rl/`，入口关系见 [README](../README.md#训练与回放)。

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

这些检查验证依赖和 GPU 基础环境；机器人环境创建、执行器响应和训练运行需通过专项检查另行验证。

模型加载与关节映射检查：

```bash
uv run --no-sync python tools/check_robot.py
```

本机有图形桌面时，可加 `--viewer` 静态查看机器人。该工具验证 MJCF 编译与关节、电机映射。
混合执行器和任务环境已接入，训练与回放入口见[第 5 节](#5-当前训练入口状态)；
动态执行器响应、环境步进和策略效果需分别通过对应专项检查验收。

## 4. 日常使用和依赖维护

安装后通过 `uv run --no-sync` 使用现有项目环境，无需手动激活 `.venv/`。
`--no-sync` 保留刚刚选择的 PyTorch 后端，避免省略后端 extra 时重新同步。例如：

```bash
uv run --no-sync python
uv run --no-sync ruff check src tools tests
```

在新机器或更新仓库后，重新执行推荐的同步命令：

```bash
bash setup.sh
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

`duck-train` 与 `duck-play` 已启用，是官方 `mjlab.scripts.train` / `mjlab.scripts.play`
的薄封装；`duck-eval` 与 `duck-export` 仍属后续任务。

`pyproject.toml` 用 `[project.entry-points."mjlab.tasks"]` 注册任务包，`import mjlab`
时会自动加载 `ht_microduck.tasks`。**改动该 entry point、`[project.scripts]` 或包结构后，
需要重新安装本包**，否则 `dist-info/entry_points.txt` 仍是旧内容：

```bash
uv pip install --no-deps -e .
uv run --no-sync list-envs        # 应能看到 HtDuck-Flat-Velocity
```

## 6. 训练日志可视化

`duck-train` 默认把 TensorBoard 事件写到 `logs/rsl_rl/<experiment_name>/<时间戳>_<run_name>/`
（`--log-root` 可改根目录），该目录被 `.gitignore` 排除，不随仓库分发。
在本机查看曲线：

```bash
uv run --no-sync tensorboard --logdir logs/rsl_rl --bind_all --port 6006
```

`--bind_all` 让同一局域网内的浏览器可以访问；只在开发机本机查看时改用
`--host 127.0.0.1` 更安全。服务以前台方式运行，用 `Ctrl+C` 结束；不需要时不要
长期驻留，也不要在训练进行中反复刷新页面代替等待。

需要从其他机器访问时，优先用 SSH 端口转发，而不是把 TensorBoard 直接暴露到公网：

```bash
ssh -N -L 6006:127.0.0.1:6006 <user>@<开发机地址>
# 浏览器打开 http://127.0.0.1:6006
```

端口、主机名和转发方式按本机实际网络确定，不要照抄示例地址。
训练产物（事件文件、检查点、`params/*.yaml`、`git/*.diff`）保留在输出目录，
代码仓库只保留复现实验所需的配置与结论。

## 7. XN-4090-GPU1 远端环境

通过 `ssh hupeiyan@j4.tx.ppp.clicki.cn` 进入堡垒机，输入 `p` 后选择资产 1
（XN-4090-GPU1）。本项目部署目录为 `/data/hupeiyan/projects/HT_microduck_lab`，
上传的是当前工作区源码快照，包含未提交的实现、机器人资源与本地 `rsl_rl/`，不包含本机
`.venv`、Git 历史或训练产物。Python 3.12.14 在远端单独准备，项目环境由 uv 创建。

该机 Toolkit 为 `/usr/local/cuda-12.8`（12.8.93），驱动为 570.124.06，选择 `cu128`。
GitHub 不可达且清华镜像返回 403，本次传输已验证的 Python/Warp 缓存，并从可达的阿里云 PyPI 镜像
补齐其他锁定依赖。下载准备期间只替换临时下载地址，保留版本与 SHA256，结束后恢复原始
`uv.lock`；正式安装使用原锁文件与项目内缓存。再次同步使用：

```bash
cd /data/hupeiyan/projects/HT_microduck_lab
UV_CACHE_DIR="$PWD/.cache/uv" UV_OFFLINE=1 bash setup.sh --cuda-home /usr/local/cuda-12.8
```

保留 `.cache/uv` 供离线同步使用。日常无需访问包源：

```bash
source .venv/bin/activate
uv run --no-sync list-envs
```

GPU 检查通过 `CUDA_VISIBLE_DEVICES=GPU-450c3470-1f63-9d53-43d4-366538571ecf`
选择物理 GPU 1，在进程内显示为 `cuda:0`。
训练时按服务器实际空闲情况选择 GPU；环境安装本身不启动训练。

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
