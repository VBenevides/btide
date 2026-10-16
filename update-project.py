#!/usr/bin/env python3
"""Copy mapped machine configuration back into this portable IDE checkout."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from bootstrap import ROOT, Setup, atomic_write


def capture(setup, dry_run=False):
    failures = 0
    excluded = {'.git', '.env', 'credentials.json', 'auth.json', 'node_modules',
                '__pycache__', '.venv', 'dist', 'build', 'cache', 'logs', 'sessions', 'lazy-lock.json'}

    def traversal_error(error):
        raise error

    def copy_file(source, destination):
        if not destination.resolve().is_relative_to(ROOT / 'config'):
            raise RuntimeError(f'Repository destination escapes config: {destination}')
        if not source.is_file():
            raise RuntimeError(f'Missing mapped file: {source}')
        content = source.read_bytes()
        if destination.is_file() and destination.read_bytes() == content:
            print(f'Unchanged: {destination.relative_to(ROOT)}')
            return
        print(f'{"Would update" if dry_run else "Updating"}: {destination.relative_to(ROOT)}')
        if not dry_run:
            # Configuration is text; preserve existing repository file permissions.
            atomic_write(destination, content.decode('utf-8'),
                         destination.stat().st_mode & 0o777 if destination.exists() else 0o644)

    mappings = [(source, destination) for destination, source in setup.links]
    for source, destination in mappings:
        try:
            for parent in source.parents:
                if parent == setup.home:
                    break
                if parent.is_symlink():
                    raise RuntimeError(f'Refusing symlinked source parent: {parent}')
            if source.is_symlink() and source.resolve() != destination.resolve():
                raise RuntimeError(f'Refusing unmanaged source symlink: {source}')
            if destination.is_dir():
                if not source.is_dir():
                    raise RuntimeError(f'Missing mapped directory: {source}')
                # Installed directory roots may link into this checkout. Nested
                # links must not import external data into configuration snapshots.
                for directory, dirs, files in os.walk(source, followlinks=False, onerror=traversal_error):
                    for name in sorted(dirs + files):
                        file = Path(directory) / name
                        if name in excluded or name.startswith('.env.'):
                            print(f'Skipping private/runtime path: {file}')
                            if name in dirs:
                                dirs.remove(name)
                            continue
                        try:
                            if file.is_symlink():
                                raise RuntimeError(f'Refusing nested configuration symlink: {file}')
                            if file.is_file():
                                copy_file(file, destination / file.relative_to(source))
                        except (OSError, RuntimeError, UnicodeError) as error:
                            print(f'Error: {error}', file=sys.stderr)
                            failures += 1
            else:
                copy_file(source, destination)
        except (OSError, RuntimeError, UnicodeError) as error:
            print(f'Error: {error}', file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home(), help='Read configuration from this home directory')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing')
    args = parser.parse_args()
    return capture(Setup(args.home), args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
