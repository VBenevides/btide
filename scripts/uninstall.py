"""Remove the installed BTIDE executable; --purge also deletes BTIDE data, cache and state."""

import argparse
import os
import sys
from pathlib import Path

import maintenance

ROOT = Path(__file__).resolve().parents[1]


def uninstall(home, purge=False):
    home = home.resolve()
    launcher = home / ".local/bin/btide"
    for parent in launcher.parents:
        if parent == home:
            break
        if parent.is_symlink():
            raise RuntimeError("Refusing unsafe launcher parent: " + str(parent))
    if os.path.lexists(launcher):
        expected = ROOT / "config/btide.sh"
        linked = launcher.is_symlink() and launcher.resolve() == expected.resolve()
        copied = (
            launcher.is_file()
            and not launcher.is_symlink()
            and launcher.read_bytes() == expected.read_bytes()
        )
        if not linked and not copied:
            raise RuntimeError(
                "Refusing to remove a launcher not owned by this checkout: "
                + str(launcher)
            )
        launcher.unlink()
    if purge:
        maintenance.purge(home)
        print(
            "Removed ~/.local/bin/btide and the BTIDE data, cache and state directories; "
            "configuration and other tools in ~/.local/bin retained."
        )
        return
    print(
        "Removed ~/.local/bin/btide; backups, tools, configuration and data retained."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Also delete ~/.local/share/btide, ~/.cache/btide and ~/.local/state/btide",
    )
    args = parser.parse_args()
    uninstall(Path.home(), purge=args.purge)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print("Uninstall failed: " + str(error), file=sys.stderr)
        sys.exit(1)
