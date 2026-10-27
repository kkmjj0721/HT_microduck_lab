"""Check Toolkit matching and installer behavior without installing packages."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import setup_env


class SetupEnvironmentTests(unittest.TestCase):
    def test_exact_toolkit_version_selects_matching_backend(self):
        for version, backend in [
            ((11, 8), "cu118"),
            ((12, 6), "cu126"),
            ((12, 8), "cu128"),
            ((12, 9), "cu129"),
            ((13, 0), "cu130"),
        ]:
            with self.subTest(version=version):
                self.assertEqual(setup_env.select_backend(version), backend)

    def test_missing_match_does_not_select_a_nearby_backend(self):
        for version in [(11, 7), (12, 4), (13, 2)]:
            with self.subTest(version=version):
                with self.assertRaises(RuntimeError):
                    setup_env.select_backend(version)

    def test_nvcc_version_is_used_instead_of_driver_capability(self):
        nvcc = Path("/example/cuda/bin/nvcc")
        result = subprocess.CompletedProcess(
            [], 0, stdout="Cuda compilation tools, release 11.7, V11.7.99", stderr=""
        )
        with patch.object(setup_env.subprocess, "run", return_value=result) as run:
            self.assertEqual(setup_env.detect_cuda_version(nvcc), (11, 7))
        self.assertEqual(run.call_args.args[0], [str(nvcc), "--version"])

    def test_cuda_home_selects_installed_toolkit_before_path(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            nvcc = home / "bin" / "nvcc"
            nvcc.parent.mkdir()
            nvcc.touch()
            with patch.dict(setup_env.os.environ, {"CUDA_HOME": directory}):
                with patch.object(setup_env.shutil, "which") as which:
                    self.assertEqual(setup_env.find_nvcc(), nvcc.resolve())
                    which.assert_not_called()

    def test_failed_nvcc_is_reported(self):
        result = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="nvcc failed"
        )
        with patch.object(setup_env.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError):
                setup_env.detect_cuda_version(Path("/example/nvcc"))

    def test_invalid_selected_toolkit_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(setup_env.shutil, "which") as which:
                with self.assertRaises(RuntimeError):
                    setup_env.find_nvcc(Path(directory))
                which.assert_not_called()

    def test_automatic_dry_run_does_not_install_or_change_environment(self):
        output = io.StringIO()
        with patch.object(setup_env.shutil, "which", return_value="uv"):
            with patch.object(setup_env, "find_nvcc", return_value=Path("/example/nvcc")):
                with patch.object(setup_env, "detect_cuda_version", return_value=(12, 6)):
                    with patch.object(setup_env.subprocess, "run") as run:
                        with contextlib.redirect_stdout(output):
                            code = setup_env.main(["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("--locked --python 3.12 --extra cu126 --extra export", output.getvalue())
        run.assert_not_called()

    def test_incompatible_installed_toolkit_stops_before_sync(self):
        output = io.StringIO()
        with patch.object(setup_env.shutil, "which", return_value="uv"):
            with patch.object(setup_env, "find_nvcc", return_value=Path("/example/nvcc")):
                with patch.object(setup_env, "detect_cuda_version", return_value=(11, 7)):
                    with patch.object(setup_env.subprocess, "run") as run:
                        with contextlib.redirect_stdout(io.StringIO()):
                            with contextlib.redirect_stderr(output):
                                code = setup_env.main([])
        self.assertEqual(code, 1)
        self.assertIn("cu117", output.getvalue())
        self.assertIn("torch>=2.7", output.getvalue())
        run.assert_not_called()

    def test_explicit_backend_and_minimal_install(self):
        with patch.object(setup_env.shutil, "which", return_value="uv"):
            with patch.object(setup_env, "detect_cuda_version") as detect:
                result = subprocess.CompletedProcess([], 0)
                with patch.object(setup_env.subprocess, "run", return_value=result) as run:
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = setup_env.main(["--backend", "cpu", "--no-dev", "--no-export"])
        self.assertEqual(code, 0)
        detect.assert_not_called()
        self.assertEqual(
            run.call_args.args[0],
            ["uv", "sync", "--locked", "--python", "3.12", "--extra", "cpu", "--no-dev"],
        )
        self.assertEqual(run.call_args.kwargs["cwd"], setup_env.PROJECT_ROOT)

    def test_failed_sync_exit_code_is_preserved(self):
        with patch.object(setup_env.shutil, "which", return_value="uv"):
            result = subprocess.CompletedProcess([], 7)
            with patch.object(setup_env.subprocess, "run", return_value=result):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(setup_env.main(["--backend", "cu128"]), 7)


if __name__ == "__main__":
    unittest.main()
