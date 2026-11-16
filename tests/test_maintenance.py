"""Backup pruning, leftover removal, size report and purge in an isolated home."""

import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from script_loader import load_script

maintenance = load_script("maintenance")
system_tools = load_script("system_tools")

DAY = 24 * 3600 * 10**9
NOW = 1_800_000_000 * 10**9


def backup(directory, base, age_days, legacy=False):
    stamp = NOW - int(age_days * DAY)
    name = f"{base}.btide-backup-{stamp}" if legacy else f"{base}.{stamp}.bak"
    path = directory / name
    path.write_text("old")
    return path


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve() / "home with spaces"
        self.state = self.home / ".local/share/btide"
        self.bin = self.home / ".local/bin"
        self.config = self.home / ".config/btide"
        for directory in (self.state, self.bin, self.config):
            directory.mkdir(parents=True)
        self.output = []

    def out(self, line):
        self.output.append(line)

    def build_current_state(self):
        (self.state / "install.lock").write_text("")
        (self.state / "nvim-install.json").write_text("{}")
        (self.state / "nvim.conf/mason").mkdir(parents=True)
        for name in ("receipts", "releases", "system-tools"):
            (self.state / name).mkdir()
        for name in ("check.json", "lazygit.json", "nvim.json", "system-go.json"):
            (self.state / "receipts" / name).write_text("{}")
        for name in ("lazygit.json", "go.json"):
            (self.state / "releases" / name).write_text("{}")
        (self.state / "system-tools/go").mkdir()
        (self.state / "system-tools/go.tree").write_text("")

    def test_backup_names_for_both_formats_are_parsed(self):
        self.assertEqual(
            maintenance.parse_backup("btide.1794431563254777540.bak"),
            ("btide", 1794431563254777540),
        )
        self.assertEqual(
            maintenance.parse_backup("omp.btide-backup-1791299539142829099"),
            ("omp", 1791299539142829099),
        )
        for name in ("btide", "btide.bak", "notes.123.bak", "x.btide-backup-abc"):
            self.assertIsNone(maintenance.parse_backup(name))

    def test_only_the_newest_recent_backup_of_each_name_is_kept(self):
        newest = backup(self.bin, "btide", 1)
        older = backup(self.bin, "btide", 2)
        oldest = backup(self.bin, "btide", 6)
        other = backup(self.bin, "ouro", 3, legacy=True)
        stale = maintenance.stale_backups(self.bin, NOW)
        self.assertEqual(stale, sorted([older, oldest]))
        self.assertNotIn(newest, stale)
        self.assertNotIn(other, stale)

    def test_backups_older_than_seven_days_are_deleted_even_when_newest(self):
        too_old = backup(self.bin, "btide", 7.5)
        edge = backup(self.bin, "ouro", 6.9)
        self.assertEqual(maintenance.stale_backups(self.bin, NOW), [too_old])
        self.assertTrue(edge.exists())

    def test_files_that_are_not_backups_or_have_odd_timestamps_are_kept(self):
        (self.bin / "btide").write_text("launcher")
        (self.bin / "notes.bak").write_text("mine")
        future = self.bin / f"btide.{NOW + 30 * DAY}.bak"
        future.write_text("odd")
        ancient = self.bin / "btide.1234567890123456.bak"
        ancient.write_text("odd")
        self.assertEqual(maintenance.stale_backups(self.bin, NOW), [])

    def test_missing_backup_directory_is_not_an_error(self):
        self.assertEqual(maintenance.stale_backups(self.home / "absent", NOW), [])

    def test_prune_backups_covers_all_managed_directories_and_never_follows_links(self):
        target = self.home / "checkout/config/btide.sh"
        target.parent.mkdir(parents=True)
        target.write_text("launcher")
        stamp = NOW - 20 * DAY
        link = self.bin / f"btide.{stamp}.bak"
        link.symlink_to(target)
        directory_backup = self.config / f"nvim.conf.{stamp}.bak"
        (directory_backup / "lua").mkdir(parents=True)
        legacy = backup(self.state, "ouro", 30, legacy=True)
        self.assertEqual(
            maintenance.prune_backups(self.home, now_ns=NOW, out=self.out), 0
        )
        for path in (link, directory_backup, legacy):
            self.assertFalse(path.exists() or path.is_symlink(), path)
        self.assertEqual(target.read_text(), "launcher")

    def test_dry_run_changes_nothing(self):
        old = backup(self.bin, "btide", 30)
        self.build_current_state()
        (self.state / "smart-approve").mkdir()
        maintenance.prune(self.home, dry_run=True, now_ns=NOW, out=self.out)
        self.assertTrue(old.exists())
        self.assertTrue((self.state / "smart-approve").exists())
        self.assertTrue(any(line.startswith("Would remove") for line in self.output))

    def test_leftovers_are_found_at_every_level_and_current_files_are_kept(self):
        self.build_current_state()
        (self.state / "omp-runtime").mkdir()
        (self.state / "smart-approve").mkdir()
        (self.state / "env.sh").write_text("")
        (self.state / "receipts/omp.json").write_text("{}")
        (self.state / "releases/bun.json").write_text("{}")
        (self.state / "system-tools/python").mkdir()
        keep = backup(self.state, "nvim.conf", 1)
        found = maintenance.leftover_entries(self.state)
        self.assertEqual(
            [path.relative_to(self.state).as_posix() for path in found],
            [
                "env.sh",
                "omp-runtime",
                "receipts/omp.json",
                "releases/bun.json",
                "smart-approve",
                "system-tools/python",
            ],
        )
        self.assertTrue(keep.exists())

    def test_prune_removes_leftovers_and_keeps_the_current_version(self):
        self.build_current_state()
        (self.state / "smart-approve/node_modules").mkdir(parents=True)
        (self.state / "receipts/smart-approve.json").write_text("{}")
        old = backup(self.bin, "btide", 30)
        recent = backup(self.bin, "btide", 1)
        self.assertEqual(maintenance.prune(self.home, now_ns=NOW, out=self.out), 0)
        self.assertFalse((self.state / "smart-approve").exists())
        self.assertFalse((self.state / "receipts/smart-approve.json").exists())
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        for name in (
            "install.lock",
            "nvim-install.json",
            "nvim.conf/mason",
            "receipts/nvim.json",
            "releases/lazygit.json",
            "system-tools/go",
            "system-tools/go.tree",
        ):
            self.assertTrue((self.state / name).exists(), name)

    def test_leftover_used_by_shell_startup_is_kept_and_reported(self):
        self.build_current_state()
        (self.state / "env.sh").write_text("export A=1")
        (self.home / ".bashrc").write_text('source "$HOME/.local/share/btide/env.sh"\n')
        (self.state / "ouro").mkdir()
        maintenance.prune(self.home, now_ns=NOW, out=self.out)
        self.assertTrue((self.state / "env.sh").exists())
        self.assertFalse((self.state / "ouro").exists())
        self.assertTrue(
            any("Kept" in line and ".bashrc" in line for line in self.output)
        )

    def test_symbolic_links_in_the_state_directory_are_not_followed(self):
        self.build_current_state()
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        (self.state / "ouro").symlink_to(outside)
        maintenance.prune(self.home, now_ns=NOW, out=self.out)
        self.assertFalse((self.state / "ouro").is_symlink())
        self.assertEqual((outside / "keep.txt").read_text(), "keep")

    def test_one_failure_does_not_stop_other_removals(self):
        self.build_current_state()
        (self.state / "aaa").mkdir()
        (self.state / "zzz").mkdir()
        real_remove = maintenance.remove

        def flaky(path):
            if path.name == "aaa":
                raise PermissionError("denied")
            real_remove(path)

        with mock.patch.object(maintenance, "remove", side_effect=flaky):
            failures = maintenance.prune(self.home, now_ns=NOW, out=self.out)
        self.assertEqual(failures, 1)
        self.assertTrue((self.state / "aaa").exists())
        self.assertFalse((self.state / "zzz").exists())

    def test_prune_is_refused_while_an_installation_holds_the_lock(self):
        self.build_current_state()
        (self.state / "ouro").mkdir()
        with (self.state / "install.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(RuntimeError, "installation is running"):
                maintenance.prune(self.home, now_ns=NOW, out=self.out)
        self.assertTrue((self.state / "ouro").exists())

    def test_quiet_mode_prints_nothing_and_skips_while_installing(self):
        self.build_current_state()
        (self.state / "ouro").mkdir()
        with mock.patch.object(maintenance.Path, "home", return_value=self.home):
            with mock.patch("builtins.print") as printed:
                self.assertEqual(maintenance.main(["prune", "--quiet"]), 0)
            printed.assert_not_called()
            self.assertFalse((self.state / "ouro").exists())
            (self.state / "ouro").mkdir()
            with (self.state / "install.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                self.assertEqual(maintenance.main(["prune", "--quiet"]), 0)
            self.assertTrue((self.state / "ouro").exists())

    def test_prune_without_state_directory_does_nothing(self):
        self.state.rmdir()
        self.assertEqual(maintenance.prune(self.home, out=self.out), 0)
        self.assertIn("Nothing to prune", self.output[0])

    def test_allowed_names_match_the_system_tools_the_installer_manages(self):
        self.assertEqual(set(maintenance.SYSTEM_TOOLS), set(system_tools.TOOLS))

    def test_size_report_lists_components_largest_first(self):
        self.build_current_state()
        (self.state / "nvim.conf/mason/big").write_bytes(b"x" * 200_000)
        maintenance.size_report(self.home, out=self.out)
        self.assertIn(str(self.state), self.output[0])
        names = [line.split()[-1] for line in self.output[1:]]
        self.assertEqual(names[0], "nvim.conf")

    def test_purge_removes_data_and_links_into_it_but_not_other_files(self):
        self.build_current_state()
        cache = self.home / ".cache/btide/nvim.conf"
        cache.mkdir(parents=True)
        (self.config / "tmux.conf").write_text("config")
        managed = self.state / "system-tools/go/bin"
        managed.mkdir(parents=True)
        (managed / "go").write_text("")
        (self.bin / "go").symlink_to(managed / "go")
        elsewhere = self.home / "tool"
        elsewhere.write_text("")
        (self.bin / "other").symlink_to(elsewhere)
        (self.bin / "ouro").write_text("binary")
        maintenance.purge(self.home, out=self.out)
        self.assertFalse(self.state.exists())
        self.assertFalse((self.home / ".cache/btide").exists())
        self.assertFalse((self.bin / "go").is_symlink())
        self.assertTrue((self.bin / "other").is_symlink())
        self.assertTrue((self.bin / "ouro").exists())
        self.assertEqual((self.config / "tmux.conf").read_text(), "config")

    def test_purge_refuses_a_symbolic_link_directory(self):
        self.state.rmdir()
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "keep.txt").write_text("keep")
        self.state.symlink_to(elsewhere)
        with self.assertRaisesRegex(RuntimeError, "unsafe data path"):
            maintenance.purge(self.home, out=self.out)
        self.assertEqual((elsewhere / "keep.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
