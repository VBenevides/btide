"""Remove the installed BTIDE executable, retaining tools and user configuration."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def uninstall(home):
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
    print(
        "Removed ~/.local/bin/btide; backups, tools, configuration and data retained."
    )


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    uninstall(Path.home())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print("Uninstall failed: " + str(error), file=sys.stderr)
        sys.exit(1)
