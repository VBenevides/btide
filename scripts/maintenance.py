#!/usr/bin/env python3
"""Report and reduce the disk space used by BTIDE."""

import argparse
import fcntl
import os
import re
import shutil
import sys
import time
from pathlib import Path

BACKUP_MAX_AGE_NS = 7 * 24 * 3600 * 10**9
# preserve() writes NAME.<time_ns>.bak; older versions wrote NAME.btide-backup-<time_ns>.
BACKUP_NAME = re.compile(
    r"^(?P<base>.+?)\.(?:(?P<stamp>\d{16,20})\.bak|btide-backup-(?P<legacy>\d{16,20}))$"
)
MIN_PLAUSIBLE_STAMP_NS = 946684800 * 10**9  # 2000-01-01
CLOCK_SKEW_NS = 24 * 3600 * 10**9
STARTUP_FILES = (
    ".bashrc",
    ".bash_login",
    ".bash_profile",
    ".profile",
    ".zshenv",
    ".zprofile",
    ".zshrc",
)
# Keep in sync with system_tools.TOOLS; tests compare both lists.
SYSTEM_TOOLS = ("go", "node", "nvim", "tmux")
# Everything the current installer writes under ~/.local/share/btide.
# A set lists the allowed children of a directory; None keeps the entry whole.
CURRENT_STATE = {
    "install.lock": None,
    "nvim-install.json": None,
    "nvim.conf": None,
    "receipts": {
        "check.json",
        "lazygit.json",
        "nvim.json",
        *(f"system-{name}.json" for name in SYSTEM_TOOLS),
    },
    "releases": {"lazygit.json", *(f"{name}.json" for name in SYSTEM_TOOLS)},
    "system-tools": {
        *SYSTEM_TOOLS,
        *(f"{name}.tree" for name in SYSTEM_TOOLS),
    },
}


class InstallRunning(RuntimeError):
    """The installer holds the lock, so pruning must wait."""


def state_dir(home):
    return home / ".local/share/btide"


def data_dirs(home):
    return [state_dir(home), home / ".cache/btide", home / ".local/state/btide"]


def backup_dirs(home):
    return [
        home / ".local/bin",
        home / ".config/btide",
        state_dir(home),
        home / ".local/share/fonts/btide",
    ]


def parse_backup(name):
    match = BACKUP_NAME.match(name)
    if not match:
        return None
    return match["base"], int(match["stamp"] or match["legacy"])


def tree_size(path):
    """Disk usage in bytes without following symbolic links."""
    seen = set()
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            info = current.lstat()
        except OSError:
            continue
        if (info.st_dev, info.st_ino) in seen:
            continue
        seen.add((info.st_dev, info.st_ino))
        total += info.st_blocks * 512
        if current.is_dir() and not current.is_symlink():
            try:
                stack.extend(current.iterdir())
            except OSError:
                continue
    return total


def format_size(size):
    value = float(size)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def stale_backups(directory, now_ns):
    """Keep only the newest backup of each name, and none older than seven days."""
    if not directory.is_dir() or directory.is_symlink():
        return []
    groups = {}
    for entry in directory.iterdir():
        parsed = parse_backup(entry.name)
        if parsed is None:
            continue
        base, stamp = parsed
        if not MIN_PLAUSIBLE_STAMP_NS <= stamp <= now_ns + CLOCK_SKEW_NS:
            continue  # An unreadable age is never a reason to delete.
        groups.setdefault(base, []).append((stamp, entry))
    stale = []
    for items in groups.values():
        items.sort(key=lambda item: item[0], reverse=True)
        for index, (stamp, entry) in enumerate(items):
            if index > 0 or now_ns - stamp > BACKUP_MAX_AGE_NS:
                stale.append(entry)
    return sorted(stale)


def leftover_entries(state):
    """Return paths under the state directory that the current version does not use."""
    if not state.is_dir() or state.is_symlink():
        return []
    leftovers = []
    for entry in sorted(state.iterdir()):
        if parse_backup(entry.name):
            continue  # Backups follow the backup rules instead.
        if entry.name not in CURRENT_STATE:
            leftovers.append(entry)
            continue
        allowed = CURRENT_STATE[entry.name]
        if allowed is None:
            continue
        if entry.is_symlink() or not entry.is_dir():
            leftovers.append(entry)
            continue
        leftovers.extend(
            child
            for child in sorted(entry.iterdir())
            if child.name not in allowed and not parse_backup(child.name)
        )
    return leftovers


def referenced_by_shell(home, path):
    """True when a shell startup file mentions the path, so deleting it breaks new shells."""
    relative = path.relative_to(home).as_posix()
    needles = (
        str(path),
        relative,
        "~/" + relative,
        "$HOME/" + relative,
        "${HOME}/" + relative,
    )
    for name in STARTUP_FILES:
        try:
            text = (home / name).read_text(errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            return name
    return None


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def remove_all(targets, dry_run, out=print):
    """Remove each path, isolating failures. Return (bytes freed, failure count)."""
    freed = failures = 0
    for path in targets:
        size = tree_size(path)
        try:
            if not dry_run:
                remove(path)
        except OSError as error:
            failures += 1
            print(f"Cannot remove {path}: {error}", file=sys.stderr)
            continue
        freed += size
        out(f"{'Would remove' if dry_run else 'Removed'} {path} ({format_size(size)})")
    return freed, failures


def prune_backups(home, dry_run=False, now_ns=None, out=print):
    """Delete stale backups only. Return the failure count."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    targets = [
        path
        for directory in backup_dirs(home)
        for path in stale_backups(directory, now_ns)
    ]
    freed, failures = remove_all(targets, dry_run, out)
    if targets:
        out(f"Backups: {format_size(freed)} {'reclaimable' if dry_run else 'freed'}.")
    return failures


def lock_state(home):
    """Hold the installer lock so pruning cannot overlap an installation."""
    lock_path = state_dir(home) / "install.lock"
    handle = lock_path.open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise InstallRunning("Another btide installation is running") from None
    return handle


def prune(home, dry_run=False, now_ns=None, out=print):
    state = state_dir(home)
    if not state.is_dir() or state.is_symlink():
        out("Nothing to prune: " + str(state) + " does not exist.")
        return 0
    with lock_state(home):
        failures = prune_backups(home, dry_run, now_ns, out)
        targets = []
        for path in leftover_entries(state):
            startup = referenced_by_shell(home, path)
            if startup:
                out(f"Kept {path}: {startup} refers to it. Remove that line first.")
            else:
                targets.append(path)
        freed, more = remove_all(targets, dry_run, out)
        if targets:
            verb = "reclaimable" if dry_run else "freed"
            out(f"Leftovers from other versions: {format_size(freed)} {verb}.")
        elif not failures and not more:
            out("Nothing else to prune.")
        return failures + more


def size_report(home, out=print):
    for directory in data_dirs(home):
        if not os.path.lexists(directory):
            continue
        out(f"{format_size(tree_size(directory)):>8}  {directory}")
        if directory.is_dir() and not directory.is_symlink():
            entries = sorted(
                ((tree_size(entry), entry) for entry in directory.iterdir()),
                key=lambda item: item[0],
                reverse=True,
            )
            for size, entry in entries:
                out(f"{format_size(size):>8}    {entry.name}")


def purge(home, out=print):
    """Delete BTIDE data, cache and state. Configuration and tools in ~/.local/bin stay."""
    for directory in data_dirs(home):
        for parent in (directory, *directory.parents):
            if parent == home:
                break
            if parent.is_symlink():
                raise RuntimeError("Refusing unsafe data path: " + str(parent))
    state = state_dir(home)
    existing = [path for path in data_dirs(home) if os.path.lexists(path)]
    if state.is_dir():
        with lock_state(home):
            remove_all(existing, False, out)
    else:
        remove_all(existing, False, out)
    # Remove links that pointed into the deleted managed tools.
    bin_dir = home / ".local/bin"
    if bin_dir.is_dir() and not bin_dir.is_symlink():
        for entry in sorted(bin_dir.iterdir()):
            if not entry.is_symlink():
                continue
            target = os.path.normpath(os.path.join(entry.parent, os.readlink(entry)))
            if target.startswith(str(state) + os.sep):
                entry.unlink()
                out(f"Removed {entry} (link into deleted data)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("size", help="Show disk use per component")
    pruning = commands.add_parser(
        "prune", help="Delete old backups and files left by other versions"
    )
    pruning.add_argument(
        "--dry-run", action="store_true", help="List what would be removed"
    )
    pruning.add_argument(
        "--quiet",
        action="store_true",
        help="Print nothing and skip silently while an installation runs (used at launch)",
    )
    args = parser.parse_args(argv)
    home = Path.home().resolve()
    if args.command == "size":
        size_report(home)
        return 0
    if not args.quiet:
        return 1 if prune(home, dry_run=args.dry_run) else 0
    try:
        return 1 if prune(home, dry_run=args.dry_run, out=lambda line: None) else 0
    except InstallRunning:
        return 0  # The next launch prunes instead.


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print("btide: " + str(error), file=sys.stderr)
        sys.exit(1)
