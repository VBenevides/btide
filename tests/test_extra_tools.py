"""Ouro and pig-plugins installation without network access."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "portable_ide_bootstrap", ROOT / "scripts/bootstrap.py"
)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class ExtraToolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name) / "home with spaces"
        self.home.mkdir()
        self.setup = bootstrap.Setup(self.home)
        self.setup.bin.mkdir(parents=True)
        self.commands = []
        self.remote = "0.2.0"
        self.checkouts = []

    def fake_clone(self, repository, destination):
        self.commands.append(("clone", repository))
        checkout = Path(destination)
        checkout.mkdir(parents=True)
        (checkout / "VERSION").write_text(self.remote + "\n")
        (checkout / "scripts").mkdir()
        self.checkouts.append(checkout)

    def fake_run(self, args, **kwargs):
        args = list(map(str, args))
        self.commands.append(tuple(args))
        if args[0] == "make":
            self.write_ouro(self.remote)
        elif args[0] == "sh":
            self.write_executable(self.setup.bin / "pig-plugins", "#!/bin/sh\n")

    def write_executable(self, path, text):
        path.write_text(text)
        path.chmod(0o755)

    def write_ouro(self, version):
        self.write_executable(self.setup.bin / "ouro", f"#!/bin/sh\necho {version}\n")

    def test_ouro_is_built_from_a_temporary_clone_when_missing(self):
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
        ):
            self.setup.install_ouro()
        self.assertEqual(self.commands[0], ("clone", bootstrap.OURO_REPO))
        self.assertEqual(self.commands[1][0:2], ("make", "-C"))
        self.assertEqual(
            self.commands[1][3:], ("install", "PREFIX=" + str(self.home / ".local"))
        )
        self.assertEqual(self.setup.ouro_version(), "0.2.0")
        self.assertFalse(self.checkouts[0].exists())

    def test_ouro_with_the_remote_version_is_not_installed_again(self):
        self.write_ouro("0.2.0")
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
        ):
            self.setup.install_ouro()
        self.assertEqual([command[0] for command in self.commands], ["clone"])

    def test_ouro_with_an_older_version_is_replaced(self):
        self.write_ouro("0.1.4")
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
        ):
            self.setup.install_ouro()
        self.assertEqual(self.setup.ouro_version(), "0.2.0")

    def test_invalid_remote_version_is_rejected_before_building(self):
        self.remote = "main; touch injected"
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
            self.assertRaisesRegex(RuntimeError, "Invalid Ouro version"),
        ):
            self.setup.install_ouro()
        self.assertNotIn("make", [command[0] for command in self.commands])

    def test_failed_ouro_build_is_reported_and_clone_is_removed(self):
        def failing(args, **kwargs):
            raise subprocess.CalledProcessError(2, args)

        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=failing),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            self.setup.install_ouro()
        self.assertFalse(self.checkouts[0].exists())

    def test_ouro_that_does_not_report_the_new_version_is_an_error(self):
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run"),
            self.assertRaisesRegex(RuntimeError, "Ouro installation failed"),
        ):
            self.setup.install_ouro()

    def test_pig_plugins_is_installed_from_a_temporary_clone_when_missing(self):
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run", side_effect=self.fake_run),
        ):
            self.setup.install_pig_plugins()
        self.assertEqual(self.commands[0], ("clone", bootstrap.PIG_PLUGINS_REPO))
        self.assertEqual(self.commands[1][0], "sh")
        self.assertTrue(self.commands[1][1].endswith("scripts/install.sh"))
        self.assertFalse(self.checkouts[0].exists())

    def test_existing_pig_plugins_is_reused(self):
        for path in (self.setup.bin / "pig-plugins", self.home / "pig/bin/pig-plugins"):
            path.parent.mkdir(parents=True, exist_ok=True)
            self.write_executable(path, "#!/bin/sh\n")
            with mock.patch.object(self.setup, "clone") as clone:
                self.setup.install_pig_plugins()
            clone.assert_not_called()
            path.unlink()

    def test_missing_pig_plugins_after_installation_is_an_error(self):
        with (
            mock.patch.object(self.setup, "clone", side_effect=self.fake_clone),
            mock.patch.object(bootstrap, "run"),
            self.assertRaisesRegex(RuntimeError, "not found after installation"),
        ):
            self.setup.install_pig_plugins()


if __name__ == "__main__":
    unittest.main()
