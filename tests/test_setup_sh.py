"""Exercise the one-command installer with isolated tools and no network access."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")


@pytest.fixture
def setup_project(tmp_path):
    project = tmp_path / "project with spaces"
    (project / "tools").mkdir(parents=True)
    for name in ("setup.sh", "tools/setup_env.py"):
        shutil.copyfile(PROJECT_ROOT / name, project / name)
    for name in ("pyproject.toml", "uv.lock"):
        (project / name).touch()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dirname", "cat", "env", "sh", "mkdir", "cp", "chmod"):
        (bin_dir / name).symlink_to(shutil.which(name))
    home = tmp_path / "home with spaces"
    home.mkdir()
    log = tmp_path / "calls.jsonl"
    uv_source = tmp_path / "fake-uv"
    uv_source.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "keys = ('UV_PROJECT', 'UV_WORKING_DIR', 'UV_PROJECT_ENVIRONMENT', "
        "'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy')\n"
        "record = dict(args=args, cwd=os.getcwd(), "
        "env={key: os.environ.get(key) for key in keys})\n"
        "with open(os.environ['FAKE_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps(record) + '\\n')\n"
        "marker = Path(os.environ['FAKE_PYTHON_MARKER'])\n"
        "if args[:2] == ['python', 'find']:\n"
        "    if not marker.exists():\n"
        "        sys.exit(1)\n"
        "    print(sys.executable)\n"
        "elif args[:2] == ['python', 'install']:\n"
        "    code = int(os.environ.get('FAKE_INSTALL_EXIT', '0'))\n"
        "    if code == 0:\n"
        "        marker.touch()\n"
        "    sys.exit(code)\n"
        "elif args and args[0] == 'sync':\n"
        "    code = int(os.environ.get('FAKE_SYNC_EXIT', '0'))\n"
        "    if code == 0:\n"
        "        Path(os.environ['UV_PROJECT_ENVIRONMENT']).mkdir(exist_ok=True)\n"
        "    sys.exit(code)\n"
        "else:\n"
        "    sys.exit(99)\n"
    )
    uv_source.chmod(0o755)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UV_")
        and key
        not in {
            "VIRTUAL_ENV", "CUDA_HOME", "CUDA_PATH", "HTTP_PROXY", "HTTPS_PROXY",
            "http_proxy", "https_proxy",
        }
    }
    env.update(
        PATH=str(bin_dir), HOME=str(home), PYTHONDONTWRITEBYTECODE="1",
        FAKE_LOG=str(log), FAKE_UV_SOURCE=str(uv_source),
        FAKE_PYTHON_MARKER=str(tmp_path / "python-installed"),
    )

    class Harness:
        def python(self):
            (bin_dir / "python3").symlink_to(sys.executable)

        def uv(self, *, user_bin=False):
            target = home / ".local/bin/uv" if user_bin else bin_dir / "uv"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(uv_source)

        def curl(self, *, exit_code=0):
            curl = bin_dir / "curl"
            curl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' curl >> \"$FAKE_LOG\"\n"
                f"if [ {exit_code} -ne 0 ]; then exit {exit_code}; fi\n"
                "cat <<'INSTALLER'\n"
                "set -eu\n"
                "test \"$UV_NO_MODIFY_PATH\" = 1\n"
                "mkdir -p \"$UV_INSTALL_DIR\"\n"
                "cp \"$FAKE_UV_SOURCE\" \"$UV_INSTALL_DIR/uv\"\n"
                "chmod +x \"$UV_INSTALL_DIR/uv\"\n"
                "INSTALLER\n"
            )
            curl.chmod(0o755)

        def run(self, *args, **updates):
            return subprocess.run(
                [BASH, str(project / "setup.sh"), *args], cwd=tmp_path,
                env=env | updates, capture_output=True, text=True,
                timeout=20, check=False,
            )

        def calls(self):
            if not log.exists():
                return []
            return [json.loads(line) for line in log.read_text().splitlines()
                    if line != "curl"]

    harness = Harness()
    harness.project = project
    harness.home = home
    harness.log = log
    return harness


def test_help_requires_no_installed_tools(setup_project):
    result = setup_project.run("--help")
    assert result.returncode == 0, result.stderr
    assert "--torch-backend" in result.stdout
    assert not setup_project.log.exists()
    assert not (setup_project.project / ".venv").exists()


@pytest.mark.parametrize("args", [
    ("--unexpected",), ("--torch-backend",), ("--backend", "unsupported"),
    ("--torch-backend", "cpu", "--cuda-home", "/uninstalled/toolkit"),
])
def test_invalid_shell_arguments_stop_before_bootstrap(setup_project, args):
    setup_project.curl()
    result = setup_project.run(*args)
    assert result.returncode == 2
    assert not setup_project.log.exists()


def test_dry_run_without_uv_never_bootstraps(setup_project):
    setup_project.python()
    setup_project.curl()
    result = setup_project.run("--torch-backend", "cpu", "--dry-run")
    assert result.returncode == 2
    assert "uv is required" in result.stderr
    assert not setup_project.log.exists()
    assert not (setup_project.home / ".local").exists()


def test_dry_run_does_not_sync_or_create_environment(setup_project):
    setup_project.python()
    setup_project.uv()
    result = setup_project.run("--torch-backend=cpu", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "--locked --python 3.12 --extra cpu --extra export" in result.stdout
    assert setup_project.calls() == []
    assert not (setup_project.project / ".venv").exists()


def test_sync_anchors_project_and_environment_from_another_directory(setup_project):
    setup_project.python()
    setup_project.uv(user_bin=True)
    result = setup_project.run(
        "--backend", "cpu", "--no-dev", "--no-export",
        UV_PROJECT="/unrelated/project", UV_WORKING_DIR="/unrelated/directory",
        UV_PROJECT_ENVIRONMENT="/unrelated/environment", VIRTUAL_ENV="/active/env",
    )
    assert result.returncode == 0, result.stderr
    [call] = setup_project.calls()
    assert call["args"] == [
        "sync", "--locked", "--python", "3.12", "--extra", "cpu", "--no-dev",
    ]
    assert call["cwd"] == str(setup_project.project)
    assert call["env"]["UV_PROJECT"] == str(setup_project.project)
    assert call["env"]["UV_WORKING_DIR"] == str(setup_project.project)
    assert call["env"]["UV_PROJECT_ENVIRONMENT"] == str(setup_project.project / ".venv")
    assert (setup_project.project / ".venv").is_dir()


def test_proxy_reaches_sync_without_replacing_explicit_values(setup_project):
    setup_project.python()
    setup_project.uv()
    result = setup_project.run(
        "--torch-backend", "cpu", UV_PROXY="http://proxy.example:8080",
        HTTPS_PROXY="http://explicit.example:3128",
    )
    assert result.returncode == 0, result.stderr
    [call] = setup_project.calls()
    assert call["env"]["HTTP_PROXY"] == "http://proxy.example:8080"
    assert call["env"]["http_proxy"] == "http://proxy.example:8080"
    assert call["env"]["HTTPS_PROXY"] == "http://explicit.example:3128"
    assert call["env"]["https_proxy"] == "http://explicit.example:3128"


@pytest.mark.parametrize("version, expected_code", [("12.6", 0), ("12.4", 1)])
def test_cuda_home_keeps_exact_toolkit_matching(setup_project, version, expected_code):
    setup_project.python()
    setup_project.uv()
    cuda_home = setup_project.project.parent / "cuda toolkit with spaces"
    nvcc = cuda_home / "bin/nvcc"
    nvcc.parent.mkdir(parents=True)
    nvcc.write_text(f"#!/bin/sh\nprintf 'Cuda compilation tools, release {version}\\n'\n")
    nvcc.chmod(0o755)
    result = setup_project.run("--cuda-home", str(cuda_home))
    assert result.returncode == expected_code, result.stderr
    if expected_code == 0:
        [call] = setup_project.calls()
        assert call["args"] == [
            "sync", "--locked", "--python", "3.12", "--extra", "cu126",
            "--extra", "export",
        ]
    else:
        assert setup_project.calls() == []
        assert "cu124" in result.stderr


def test_sync_failure_preserves_exit_code_without_success_message(setup_project):
    setup_project.python()
    setup_project.uv()
    result = setup_project.run("--backend", "cpu", FAKE_SYNC_EXIT="7")
    assert result.returncode == 7
    assert "Setup completed" not in result.stdout
    assert not (setup_project.project / ".venv").exists()


def test_missing_uv_is_bootstrapped_then_visible_to_python_installer(setup_project):
    setup_project.python()
    setup_project.curl()
    result = setup_project.run("--torch-backend", "cpu")
    assert result.returncode == 0, result.stderr
    assert setup_project.log.read_text().splitlines()[0] == "curl"
    assert (setup_project.home / ".local/bin/uv").is_file()
    assert setup_project.calls()[0]["args"][0] == "sync"


def test_failed_uv_download_stops_before_success(setup_project):
    setup_project.python()
    setup_project.curl(exit_code=22)
    result = setup_project.run("--backend", "cpu")
    assert result.returncode == 22
    assert "Setup completed" not in result.stdout
    assert setup_project.calls() == []


def test_missing_python_is_installed_with_uv_before_sync(setup_project):
    setup_project.uv()
    result = setup_project.run("--backend", "cpu")
    assert result.returncode == 0, result.stderr
    calls = setup_project.calls()
    assert [call["args"][:2] for call in calls] == [
        ["python", "find"], ["python", "install"], ["python", "find"],
        ["sync", "--locked"],
    ]
    assert calls[1]["args"] == ["python", "install", "3.12"]


def test_dry_run_without_python_never_installs_it(setup_project):
    setup_project.uv()
    result = setup_project.run("--backend", "cpu", "--dry-run")
    assert result.returncode == 2
    assert "no tools were installed" in result.stderr
    assert [call["args"][:2] for call in setup_project.calls()] == [["python", "find"]]
    assert not (setup_project.project / ".venv").exists()


def test_failed_python_install_stops_before_sync(setup_project):
    setup_project.uv()
    result = setup_project.run("--backend", "cpu", FAKE_INSTALL_EXIT="9")
    assert result.returncode == 9
    assert "Setup completed" not in result.stdout
    assert [call["args"][:2] for call in setup_project.calls()] == [
        ["python", "find"], ["python", "install"],
    ]
