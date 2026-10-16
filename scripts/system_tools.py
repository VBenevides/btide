"""Verified compatible base-tool runtimes; no bootstrap imports or import-time writes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile

from releases import resolve_release, validate_spec


TOOLS = {
    'go': ((1, 25), ['version'], ['bin/go', 'bin/gofmt', 'src/runtime/runtime.go', 'pkg/include/textflag.h'], {'go': 'bin/go', 'gofmt': 'bin/gofmt'}),
    'node': ((20,), ['--version'], ['bin/node', 'bin/npm', 'bin/npx', 'lib/node_modules/npm/package.json'], {'node': 'bin/node', 'npm': 'bin/npm', 'npx': 'bin/npx'}),
    'nvim': ((0, 11, 2), ['--version'], ['bin/nvim', 'share/nvim/runtime/filetype.lua'], {'nvim': 'bin/nvim'}),
    'tmux': ((3, 2), ['-V'], ['bin/tmux'], {'tmux': 'bin/tmux'}),
}


def _identity(spec):
    return json.dumps(spec, sort_keys=True, separators=(',', ':'))


def _release_path(setup, name):
    return setup.state / 'releases' / (name + '.json')


def _installed_spec(setup, name):
    path = _release_path(setup, name)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise RuntimeError('Unsafe release metadata path')
    return validate_spec(json.loads(path.read_text()))


def _tree(root):
    """Fingerprint all runtime files and link targets, not just entry executables."""
    h = hashlib.sha256()
    paths = []
    total = 0
    for path in root.rglob('*'):
        paths.append(path)
        if not path.is_symlink() and path.is_file():
            total += path.stat().st_size
        if len(paths) > 100000 or total > 2 * 1024**3:
            raise RuntimeError('Runtime tree exceeds integrity-check limits')
    for path in sorted(paths):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise RuntimeError('Unsafe or broken runtime link: ' + str(path))
            value = 'link:' + os.readlink(path)
        elif path.is_file():
            file_hash = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    file_hash.update(block)
            value = 'file:' + str(path.stat().st_mode & 0o777) + ':' + file_hash.hexdigest()
        elif path.is_dir():
            value = 'directory'
        else:
            raise RuntimeError('Unsupported runtime file: ' + str(path))
        h.update((relative + '\0' + value + '\0').encode())
    return h.hexdigest()


def _paths(setup, name):
    root = setup.state / 'system-tools' / name
    manifest = setup.state / 'system-tools' / (name + '.tree')
    outputs = [manifest, _release_path(setup, name)]
    return root, manifest, outputs


def _valid(setup, versions, name):
    root, manifest, outputs = _paths(setup, name)
    try:
        spec = _installed_spec(setup, name)
        if not setup.receipt_valid('system-' + name, _identity(spec), outputs):
            return False
        return (not root.is_symlink() and not manifest.is_symlink()
                and manifest.read_text().strip() == _tree(root)
                and all((root / p).is_file() for p in TOOLS[name][2])
                and all((setup.bin / entry).is_symlink()
                        and os.readlink(setup.bin / entry) == str(root / target)
                        and (setup.bin / entry).resolve() == (root / target).resolve()
                        for entry, target in TOOLS[name][3].items()))
    except (OSError, RuntimeError, ValueError):
        return False


def check_managed_tools(setup, versions, allow_replacement=False):
    """Reject changed managed runtimes before any version probe or execution."""
    invalid = set()
    for directory in (setup.state / 'system-tools', setup.state / 'releases', setup.bin):
        for path in (directory, *directory.parents):
            if path == setup.home:
                break
            if path.is_symlink():
                raise RuntimeError('Refusing symlinked tool directory: ' + str(path))
    for name in TOOLS:
        root, manifest, _ = _paths(setup, name)
        receipt = setup.state / 'receipts' / ('system-' + name + '.json')
        managed_link = any((setup.bin / entry).is_symlink()
                           and (setup.bin / entry).resolve().is_relative_to(root.resolve())
                           for entry in TOOLS[name][3])
        if (os.path.lexists(root) or os.path.lexists(manifest) or receipt.exists() or managed_link):
            if not _valid(setup, versions, name):
                if not allow_replacement:
                    raise RuntimeError('Managed ' + name + ' runtime is missing or changed; inspect it, then use --install-deps --backup-existing')
                invalid.add(name)
    return invalid


def _compatible(setup, name, minimum=None):
    executable = shutil.which(name, path=setup.env['PATH'])
    if executable is None:
        return False
    result = setup.command([executable, *TOOLS[name][1]], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=30)
    match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?([a-z]?)', result.stdout)
    if not match:
        raise RuntimeError('Cannot determine ' + name + ' version: ' + result.stdout)
    version = tuple(int(part or 0) for part in match.groups()[:3])
    suffix = match[4]
    minimum = minimum or TOOLS[name][0]
    minimum = minimum + (0,) * (3 - len(minimum))
    return (*version, suffix) >= (*minimum[:3], minimum[3] if len(minimum) > 3 else '')


def _extract(archive, destination):
    """Extract regular files/directories and confined links with finite size limits."""
    with tarfile.open(archive, mode='r|*') as tar:
        count = total_size = 0
        seen = set()
        links = []
        for member in tar:
            count += 1
            total_size += member.size
            if count > 100000 or total_size > 2 * 1024**3 or member.size < 0:
                raise RuntimeError('Runtime archive exceeds extraction limits')
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise RuntimeError('Unsafe archive path: ' + member.name)
            target = destination.joinpath(*path.parts)
            if str(path) in seen:
                raise RuntimeError('Duplicate archive path: ' + member.name)
            seen.add(str(path))
            if member.issym() or member.islnk():
                links.append((member, target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True)
            elif member.isfile():
                with tar.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                target.chmod(member.mode & 0o777)
                # Make uses release mtimes to decide whether generated Autotools
                # files need regeneration. Extraction order must not change that.
                os.utime(target, (member.mtime, member.mtime))
            else:
                raise RuntimeError('Unsupported archive member: ' + member.name)
        for member, target in links:
            link = PurePosixPath(member.linkname)
            resolved = (target.parent / str(link) if member.issym() else destination / str(link)).resolve()
            if link.is_absolute() or not resolved.is_relative_to(destination.resolve()):
                raise RuntimeError('Unsafe archive link: ' + member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.issym():
                target.symlink_to(member.linkname)
            else:
                os.link(resolved, target)


def ensure_compatible_tools(setup, versions, download, atomic_write):
    invalid = check_managed_tools(setup, versions, allow_replacement=setup.backup)
    architecture = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(platform.machine(), platform.machine())
    if architecture not in ('x86_64', 'aarch64'):
        raise RuntimeError('Unsupported fallback architecture: ' + architecture)
    for name in TOOLS:
        spec = validate_spec(resolve_release(name, architecture))
        match = re.fullmatch(r'(\d+)\.(\d+)(?:\.(\d+))?([a-z]?)', spec['version'])
        latest = (*tuple(int(part or 0) for part in match.groups()[:3]), match[4])
        valid = name not in invalid and _valid(setup, versions, name)
        if valid and _installed_spec(setup, name) == spec:
            continue
        if not valid and name not in invalid and _compatible(setup, name, latest):
            continue
        root, manifest, outputs = _paths(setup, name)
        links = [setup.bin / entry for entry in TOOLS[name][3]]
        conflicts = [p for p in [root, manifest, *links] if os.path.lexists(p)]
        if conflicts and not setup.backup:
            raise RuntimeError('Existing tool paths conflict; use --backup-existing: ' + ', '.join(map(str, conflicts)))
        setup.state.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='system-tool-', dir=setup.state) as temporary:
            stage = Path(temporary)
            archive = stage / 'archive.tar.gz'
            download(spec['url'], archive, spec['sha256'])
            unpacked = stage / 'unpacked'
            unpacked.mkdir()
            _extract(archive, unpacked)
            children = list(unpacked.iterdir())
            if len(children) != 1 or not children[0].is_dir() or children[0].is_symlink():
                raise RuntimeError('Expected one runtime archive root: ' + name)
            runtime = children[0]
            if name == 'tmux':
                source = runtime
                runtime = stage / 'runtime'
                setup.command(['./configure', '--prefix=' + str(runtime)], cwd=source, timeout=180)
                setup.command(['make', '-j2'], cwd=source, timeout=600)
                # tmux is standalone; its upstream install hook does not quote prefix paths.
                (runtime / 'bin').mkdir(parents=True)
                shutil.copy2(source / 'tmux', runtime / 'bin/tmux')
            for required in TOOLS[name][2]:
                if not (runtime / required).is_file():
                    raise RuntimeError('Incomplete ' + name + ' runtime: missing ' + required)
            for target in TOOLS[name][3].values():
                if not os.access(runtime / target, os.X_OK):
                    raise RuntimeError('Nonexecutable runtime entry: ' + target)
            result = setup.command([runtime / TOOLS[name][3][name], *TOOLS[name][1]],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', result.stdout)
            actual = tuple(int(part or 0) for part in match.groups()) if match else ()
            minimum = tuple(map(int, versions['system_tools'][name]['minimum_version'].split('.')))
            if actual < minimum + (0,) * (3 - len(minimum)):
                raise RuntimeError('Installed ' + name + ' runtime does not meet its minimum version')
            fingerprint = _tree(runtime)
            # Conflict consent was checked before downloading or building.
            for path in conflicts:
                setup.preserve(path)
            root.parent.mkdir(parents=True, exist_ok=True)
            runtime.rename(root)
            setup.bin.mkdir(parents=True, exist_ok=True)
            for entry, target in TOOLS[name][3].items():
                (setup.bin / entry).symlink_to(root / target)
            atomic_write(manifest, fingerprint + '\n')
            atomic_write(_release_path(setup, name), json.dumps(spec, sort_keys=True) + '\n')
            setup.receipt('system-' + name, _identity(spec), outputs)
