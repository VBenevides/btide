#!/usr/bin/env python3
"""Reinstall from upstream main only when its stable BTIDE version is newer."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REMOTE = "https://github.com/VBenevides/btide.git"


def read_version(path):
    text = path.read_text().strip()
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", text):
        raise ValueError(f"Invalid BTIDE version in {path}: expected MAJOR.MINOR.PATCH")
    return tuple(map(int, text.split(".")))


def update(home):
    version_path = home / ".config/btide/VERSION"
    local = read_version(version_path)
    with tempfile.TemporaryDirectory(prefix="btide-update-") as temporary:
        checkout = Path(temporary) / "repo"
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "main",
                "--",
                REMOTE,
                str(checkout),
            ],
            check=True,
            timeout=180,
            stdin=subprocess.DEVNULL,
        )
        remote = read_version(checkout / "VERSION")
        if local >= remote:
            print("BTIDE is already up to date (local version is equal or newer).")
            return
        print(
            "Updating BTIDE from "
            + ".".join(map(str, local))
            + " to "
            + ".".join(map(str, remote)),
            flush=True,
        )
        # Deployment precedes editor provisioning; keep failed updates retryable.
        with tempfile.TemporaryDirectory(
            prefix=".update-", dir=version_path.parent
        ) as recovery:
            previous = Path(recovery) / "VERSION"
            previous.write_text(".".join(map(str, local)) + "\n")
            try:
                subprocess.run(
                    ["bash", str(checkout / "install.sh"), "--copy-config"],
                    check=True,
                    stdin=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError) as error:
                try:
                    previous.replace(version_path)
                except OSError as restore_error:
                    raise RuntimeError(
                        f"{error}; restoring local version failed: {restore_error}"
                    ) from error
                raise
        print("BTIDE update completed.")


def main():
    try:
        update(Path.home())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"BTIDE update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
