#!/usr/bin/env bash
# Prepare uv and Python, then synchronize the project's .venv via setup_env.py.
# Usage: bash setup.sh [--torch-backend auto|cpu|cu130] [--dry-run]

set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
setup_args=()
dry_run=0
backend_selected=0
cuda_home_selected=0

print_help() {
  cat <<'EOF'
Usage: bash setup.sh [OPTIONS]

Prepare uv and Python 3.12, then install locked dependencies into .venv.
Development tools and ONNX export dependencies are included by default.

Options:
  --torch-backend BACKEND  auto (default), cpu, cu118, cu126, cu128, cu129, cu130.
  --backend BACKEND        Alias for --torch-backend, matching setup_env.py.
  --cuda-home PATH         Select an installed CUDA Toolkit instead of PATH.
  --no-dev                Skip development tools.
  --no-export             Skip ONNX export dependencies.
  --dry-run               Show the installation plan without installing anything.
  -h, --help              Show this help without installing anything.

Auto requires an exact match for the installed CUDA Toolkit version.
Use --torch-backend cpu explicitly on a machine without a CUDA Toolkit.
Dry-run requires uv and a Python 3.10+ interpreter to be installed already.

Examples:
  bash setup.sh
  bash setup.sh --torch-backend cpu
  bash setup.sh --cuda-home /usr/local/cuda-12.6
  bash setup.sh --dry-run
EOF
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 2
}

check_backend() {
  case "$1" in
    auto|cpu|cu118|cu126|cu128|cu129|cu130) ;;
    *) fail "Unsupported PyTorch backend: $1. Use --help for supported backends." ;;
  esac
  backend_selected=1
}

while (($#)); do
  case "$1" in
    --torch-backend|--backend|--cuda-home)
      (($# >= 2)) || fail "$1 requires a value."
      option="$1"
      [[ "${option}" != "--torch-backend" ]] || option="--backend"
      if [[ "${option}" == "--backend" ]]; then
        check_backend "$2"
      else
        cuda_home_selected=1
      fi
      setup_args+=("${option}" "$2")
      shift 2
      ;;
    --torch-backend=*|--backend=*)
      check_backend "${1#*=}"
      setup_args+=("--backend=${1#*=}")
      shift
      ;;
    --cuda-home=*)
      cuda_home_selected=1
      setup_args+=("$1")
      shift
      ;;
    --no-dev|--no-export)
      setup_args+=("$1")
      shift
      ;;
    --dry-run)
      dry_run=1
      setup_args+=("$1")
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *) fail "Unknown option: $1. Use --help for supported options." ;;
  esac
done

((backend_selected == 0 || cuda_home_selected == 0)) || fail "--backend/--torch-backend and --cuda-home are mutually exclusive."

for required_file in pyproject.toml uv.lock tools/setup_env.py; do
  [[ -f "${project_root}/${required_file}" ]] || fail "Missing project file: ${required_file}."
done

# Use the same proxy for the official installer, uv, and Python subprocesses.
if [[ -n "${UV_PROXY:-}" ]]; then
  export HTTP_PROXY="${HTTP_PROXY:-${http_proxy:-${UV_PROXY}}}"
  export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-${UV_PROXY}}}"
  export http_proxy="${http_proxy:-${HTTP_PROXY}}"
  export https_proxy="${https_proxy:-${HTTPS_PROXY}}"
fi

if command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  uv_bin="${HOME}/.local/bin/uv"
else
  ((dry_run == 0)) || fail "uv is required for --dry-run; no tools were installed."
  [[ "${UV_OFFLINE:-}" != "1" && "${UV_OFFLINE:-}" != "true" ]] || fail "uv must already be installed in offline mode."
  command -v curl >/dev/null 2>&1 || fail "curl is required to install uv from https://astral.sh/uv/install.sh."
  printf '%s\n' 'uv was not found; installing it from the official installer.'
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="${HOME}/.local/bin" UV_NO_MODIFY_PATH=1 sh
  uv_bin="${HOME}/.local/bin/uv"
  [[ -x "${uv_bin}" ]] || fail "uv installation did not create ${uv_bin}."
fi

# setup_env.py resolves uv through PATH; keep its project and target explicit.
uv_dir="$(cd -- "$(dirname -- "${uv_bin}")" && pwd)"
export PATH="${uv_dir}:${PATH}"
export UV_PROJECT="${project_root}" UV_WORKING_DIR="${project_root}"
export UV_PROJECT_ENVIRONMENT="${project_root}/.venv"
cd -- "${project_root}"

if command -v python3 >/dev/null 2>&1 && python3 -B -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  bootstrap_python="$(command -v python3)"
else
  printf '%s\n' 'Python 3.10+ was not found on PATH; locating Python 3.12 with uv.'
  find_args=(python find 3.12 --no-project --system --no-python-downloads)
  if ! bootstrap_python="$(uv "${find_args[@]}" 2>/dev/null)"; then
    ((dry_run == 0)) || fail "Python 3.12 must already be installed for --dry-run; no tools were installed."
    uv python install 3.12
    bootstrap_python="$(uv "${find_args[@]}")"
  fi
fi

"${bootstrap_python}" -B "${project_root}/tools/setup_env.py" "${setup_args[@]}"
if ((dry_run == 0)); then
  printf 'Setup completed: %s\n' "${UV_PROJECT_ENVIRONMENT}"
  printf '%s\n' 'Run project commands with: uv run --no-sync <command>'
  printf 'Or activate it in your current shell: source "%s/.venv/bin/activate"\n' "${project_root}"
fi
if [[ ":${PATH#*:}:" != *":${uv_dir}:"* ]]; then
  printf 'For uv in your current shell, add this directory to PATH: %s\n' "${uv_dir}"
fi
