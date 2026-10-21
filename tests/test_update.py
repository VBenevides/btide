"""Version-guarded updates without network access or real installations."""

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "btide_update", ROOT / "scripts/update.py"
)
assert spec is not None and spec.loader is not None
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.version = self.home / ".config/btide/VERSION"
        self.version.parent.mkdir(parents=True)
        self.version.write_text("0.1.0\n")
        self.remote = "0.2.0"
        self.failure = None
        self.checkouts = []

    def run_command(self, args, **kwargs):
        if args[0] == "git":
            self.assertIn("--branch", args)
            self.assertIn("main", args)
            checkout = Path(args[-1])
            self.checkouts.append(checkout)
            checkout.mkdir()
            (checkout / "VERSION").write_text(self.remote)
        elif self.failure:
            self.version.write_text(self.remote)
            raise self.failure
        else:
            self.assertEqual(args[-1], "--copy-config")
            self.version.write_text(self.remote)

    def test_upgrade_then_repeat_skips_install_and_cleans_checkout(self):
        with mock.patch.object(
            updater.subprocess, "run", side_effect=self.run_command
        ) as run:
            updater.update(self.home)
            updater.update(self.home)
        self.assertEqual(
            [call.args[0][0] for call in run.call_args_list], ["git", "bash", "git"]
        )
        self.assertTrue(all(not path.exists() for path in self.checkouts))

    def test_equal_and_newer_local_skip_install(self):
        for local in ("0.2.0", "1.0.0", "0.10.0"):
            with self.subTest(local=local):
                self.version.write_text(local)
                with mock.patch.object(
                    updater.subprocess, "run", side_effect=self.run_command
                ) as run:
                    updater.update(self.home)
                self.assertEqual(run.call_count, 1)

    def test_multi_digit_remote_version_installs(self):
        self.version.write_text("0.9.0")
        self.remote = "0.10.0"
        with mock.patch.object(
            updater.subprocess, "run", side_effect=self.run_command
        ) as run:
            updater.update(self.home)
        self.assertEqual(run.call_count, 2)

    def test_invalid_local_version_does_not_download(self):
        for value in ("", "1.2", "v1.2.3", "1.2.3-rc1", "01.2.3"):
            self.version.write_text(value)
            with mock.patch.object(updater.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Invalid BTIDE version"):
                    updater.update(self.home)
                run.assert_not_called()

    def test_invalid_remote_does_not_install(self):
        self.remote = "invalid"
        with (
            mock.patch.object(
                updater.subprocess, "run", side_effect=self.run_command
            ) as run,
            self.assertRaises(ValueError),
        ):
            updater.update(self.home)
        self.assertEqual(run.call_count, 1)
        self.assertTrue(all(not path.exists() for path in self.checkouts))

    def test_clone_failure_does_not_install(self):
        with (
            mock.patch.object(
                updater.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "git"),
            ) as run,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            updater.update(self.home)
        self.assertEqual(run.call_count, 1)

    def test_install_failure_preserves_local_version_and_never_reports_success(self):
        self.failure = subprocess.CalledProcessError(1, "install.sh")
        output = io.StringIO()
        with (
            mock.patch.object(updater.subprocess, "run", side_effect=self.run_command),
            contextlib.redirect_stdout(output),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            updater.update(self.home)
        self.assertEqual(self.version.read_text(), "0.1.0\n")
        self.assertNotIn("completed", output.getvalue())
        self.assertTrue(all(not path.exists() for path in self.checkouts))

    def test_main_reports_errors_and_nonzero_status(self):
        for error in (
            OSError("missing git"),
            ValueError("bad version"),
            subprocess.TimeoutExpired("git", 180),
        ):
            with (
                mock.patch.object(updater, "update", side_effect=error),
                contextlib.redirect_stderr(io.StringIO()) as output,
            ):
                self.assertEqual(updater.main(), 1)
            self.assertIn(str(error), output.getvalue())

    def test_installed_launcher_dispatches_update_in_both_modes(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import bootstrap

        for copy in (False, True):
            with self.subTest(copy=copy):
                setup = bootstrap.Setup(self.home, copy_config=copy)
                setup.configure()
                # A malformed installed version makes the real launcher fail before network access.
                version = setup.config / "VERSION"
                if version.is_symlink():
                    version.unlink()
                version.write_text("invalid")
                result = subprocess.run(
                    [str(setup.bin / "btide"), "--update"],
                    env=setup.env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid BTIDE version", result.stderr)
