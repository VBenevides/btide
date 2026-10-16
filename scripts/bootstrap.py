#!/usr/bin/env python3
"""Install the portable IDE without importing another machine's private state."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import struct
import sys
import tarfile
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from system_tools import check_managed_tools, ensure_compatible_tools
from releases import resolve_release, validate_spec, safe_url, open_url
VERSIONS = json.loads((ROOT / 'versions.json').read_text())


def run(args, **kwargs):
    print('+ ' + shlex.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(path):
    h = hashlib.sha256()
    for file in sorted(path.rglob('*')):
        if file.is_file():
            h.update(str(file.relative_to(path)).encode())
            h.update(b'\0')
            h.update(bytes.fromhex(digest(file)))
    return h.hexdigest()


def download(url, destination, expected):
    print('Downloading ' + url, flush=True)
    with open_url(url, timeout=60) as response, destination.open('wb') as out:
        if hasattr(response, 'geturl'):
            safe_url(response.geturl())
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 2 * 1024**3:
                raise RuntimeError('Download exceeds archive size limit: ' + url)
            out.write(chunk)
    if digest(destination) != expected:
        raise RuntimeError('SHA-256 mismatch: ' + url)


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.btide-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', errors='surrogateescape') as stream:
            stream.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Setup:
    def __init__(self, home, backup=True, include_kitty=False, copy_config=False):
        self.copy_config = copy_config
        self.home = home.resolve()
        self.bin = self.home / '.local/bin'
        self.state = self.home / '.local/share/btide'
        self.config = self.home / '.config/btide'
        self.include_kitty = include_kitty or (self.config / 'kitty.conf').is_file()
        self.editor_disabled = (not os.path.lexists(self.config / 'nvim.conf')
                                and os.path.lexists(self.config / 'nvim.conf.nouse'))
        self.editor_data = self.home / '.local/share/btide/nvim.conf'
        # Retained for runtime installer compatibility; replacement always backs up.
        self.backup = True
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.env.pop('XDG_CONFIG_HOME', None)
        self.env.pop('PI_CODING_AGENT_DIR', None)
        for key in ('XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):
            self.env.pop(key, None)
        self.editor_tools = json.loads((ROOT / 'config/nvim-tools.json').read_text())
        self.links = [
            (ROOT / 'config/tmux/tmux.conf', self.config / 'tmux.conf'),
            (ROOT / 'config/nvim', self.config / 'nvim.conf'),
        ]
        self.links = [(source, target) for source, target in self.links
                      if os.path.lexists(target) or not os.path.lexists(target.with_name(target.name + '.nouse'))]
        self.links.append((ROOT / 'config/btide.sh', self.bin / 'btide'))
        if self.include_kitty:
            self.links.extend([
                (ROOT / 'config/kitty/kitty.conf', self.config / 'kitty.conf'),
                (ROOT / 'config/misc/MesloLGSNerdFontMono-Regular.ttf',
                 self.home / '.local/share/fonts/btide/MesloLGSNerdFontMono-Regular.ttf'),
            ])
        self.config_directories = {target for source, target in self.links if source.is_dir()}

    def validate_paths(self):
        paths = [self.bin / 'btide', self.state / 'receipts/check.json', self.state / 'install.lock',
                 self.state / 'releases/lazygit.json',
                 self.editor_data / 'mason/bin/tool', self.home / '.cache/btide/nvim.conf/tool',
                 self.home / '.local/state/btide/nvim.conf/tool', self.home / '.config/ranger/scope.sh',
                 *(target for _, target in self.links)]
        for path in paths:
            for parent in path.parents:
                if parent == self.home:
                    break
                if parent.is_symlink():
                    raise RuntimeError('Refusing symlinked installation directory: ' + str(parent))
                if parent.exists() and not parent.is_dir():
                    raise RuntimeError('Installation parent is not a directory: ' + str(parent))
        if (self.state / 'install.lock').is_symlink():
            raise RuntimeError('Refusing symlinked installation lock')

    def command(self, args, **kwargs):
        return run(args, env=self.env, **kwargs)

    def preserve(self, path):
        if not os.path.lexists(path):
            return
        timestamp = time.time_ns()
        backup = path.with_name(f'{path.name}.{timestamp}.bak')
        while os.path.lexists(backup):
            timestamp += 1
            backup = path.with_name(f'{path.name}.{timestamp}.bak')
        path.rename(backup)
        print(f'Backed up {path} to {backup}')

    def preflight_config(self):
        self.validate_paths()
        for source, _ in self.links:
            if not source.exists():
                raise RuntimeError('Missing configuration source: ' + str(source))
        return [target for _, target in self.links if os.path.lexists(target)]

    def configure(self):
        conflicts = self.preflight_config()
        for path in conflicts:
            self.preserve(path)
        for source, target in self.links:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not self.copy_config:
                target.symlink_to(source, target_is_directory=source.is_dir())
            elif source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        if self.include_kitty:
            run(['fc-cache', str(self.home / '.local/share/fonts/btide')],
                env=self.env, timeout=60)

    def receipt_valid(self, name, identity, outputs):
        receipt = self.state / 'receipts' / (name + '.json')
        try:
            recorded = json.loads(receipt.read_text())
            return recorded['identity'] == identity and recorded['outputs'] == {
                str(p): digest(p) for p in outputs if p.is_file()
            } and all(p.is_file() and not p.is_symlink() for p in outputs)
        except (OSError, ValueError, KeyError):
            return False

    def receipt(self, name, identity, outputs):
        atomic_write(self.state / 'receipts' / (name + '.json'), json.dumps({
            'identity': identity, 'outputs': {str(p): digest(p) for p in outputs}
        }, indent=2) + '\n')

    def executable(self, name, version_args, expected=None):
        path = shutil.which(name, path=self.env['PATH'])
        if not path:
            raise RuntimeError(f'Missing {name}; rerun ./install.sh to install dependencies')
        output = subprocess.check_output([path, *version_args], env=self.env, text=True).strip()
        print(output)
        if expected and output != expected:
            raise RuntimeError(f'{name}: expected {expected}, got {output}')
        return output

    def prerequisites(self):
        check_managed_tools(self, VERSIONS)
        if os.path.lexists(self.state / 'receipts/lazygit.json'):
            spec = self.installed_release('lazygit')
            identity = self.release_identity(spec)
            if not self.receipt_valid('lazygit', identity, self.archive_outputs('lazygit')):
                raise RuntimeError('Missing or changed managed lazygit; inspect the binary, then rerun '
                                   './install.sh')
        self.executable('git', ['--version'])
        for name, args in (('go', ['version']), ('node', ['--version']), ('tmux', ['-V'])):
            self.require_minimum(name, self.executable(name, args))
        if self.include_kitty:
            self.executable('kitty', ['--version'])
            self.executable('fc-cache', ['--version'])
        self.editor_prerequisites()
        self.require_minimum('lazygit', self.executable('lazygit', ['--version']))

    def editor_prerequisites(self):
        self.require_minimum('nvim', self.executable('nvim', ['--version']))
        self.executable('ranger', ['--version'])
        self.executable('rg', ['--version'])
        fd = 'fd' if shutil.which('fd', path=self.env['PATH']) else 'fdfind'
        self.executable(fd, ['--version'])
        self.executable('cc', ['--version'])
        for name, args in [('npm', ['--version']), ('npx', ['--version']), ('curl', ['--version']),
                           ('unzip', ['-v']), ('make', ['--version']),
                           ('file', ['--version'])]:
            self.executable(name, args)
        self.command(['python3', '-c', 'import venv, ensurepip'], timeout=30)
        if self.include_kitty:
            self.command(['python3', '-c', 'import PIL.Image'], timeout=30)

    def editor_identity(self):
        return ':'.join((tree_digest(ROOT / 'config/nvim'), digest(ROOT / 'config/nvim-tools.json'),
                         digest(ROOT / 'scripts/install-nvim.lua')))

    def editor_binaries(self):
        directory = self.editor_data / 'mason/bin'
        return [directory / binary for binaries in self.editor_tools.values() for binary in binaries]

    def editor_parsers(self):
        try:
            parsers = json.loads((self.state / 'nvim-install.json').read_text())['parsers']
            if not isinstance(parsers, list) or not 0 < len(parsers) <= 256:
                return []
            if any(not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]+', name) for name in parsers):
                return []
            return parsers
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def editor_outputs(self):
        data = self.editor_data
        parsers = self.editor_parsers()
        return [self.state / 'nvim-install.json',
                *(data / 'mason/packages' / name / 'mason-receipt.json' for name in self.editor_tools),
                *(path.resolve() if path.is_symlink()
                  and path.resolve().is_relative_to(data / 'mason/packages') else path
                  for path in self.editor_binaries()),
                *(data / 'site/parser' / (name + '.so') for name in parsers),
                *(data / 'site/parser-info' / (name + '.revision') for name in parsers)]

    def editor_valid(self, recorded=True):
        outputs = self.editor_outputs()
        if recorded and not self.receipt_valid('nvim', self.editor_identity(), outputs):
            return False
        if not all(path.is_file() for path in outputs):
            return False
        if not self.editor_parsers() or any(not os.access(path, os.X_OK) for path in self.editor_binaries()):
            return False
        try:
            installed = json.loads(outputs[0].read_text())['plugins']
            if not isinstance(installed, dict) or not installed:
                return False
            for plugin in installed.values():
                path = Path(plugin['directory'])
                if not path.resolve().is_relative_to(self.editor_data / 'lazy'):
                    return False
                commit = subprocess.check_output(['git', '-C', path, 'rev-parse', 'HEAD'],
                                                 env=self.env, text=True, timeout=30).strip()
                if commit != plugin['commit']:
                    return False
            return True
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            return False

    def install_editor(self):
        if self.editor_disabled:
            print('BTIDE Neovim configuration disabled; leaving the default configuration untouched.')
            return
        with tempfile.TemporaryDirectory(dir=self.state) as temporary:
            temporary = Path(temporary)
            lock = self.home / '.local/state/btide/nvim.conf/lazy-lock.json'
            report = temporary / 'nvim-install.json'
            env = dict(self.env, NVIM_APPNAME='btide/nvim.conf', PORTABLE_IDE_NVIM_LOCK=str(lock),
                       PORTABLE_IDE_NVIM_REPORT=str(report),
                       PORTABLE_IDE_NVIM_TOOLS=str(ROOT / 'config/nvim-tools.json'))
            run(['nvim', '--headless', '-c',
                 'lua dofile(' + json.dumps(str(ROOT / 'scripts/install-nvim.lua')) + ')'],
                env=env, timeout=1800)
            if not report.is_file():
                raise RuntimeError('Neovim provisioning did not produce a completion report')
            outputs = self.editor_outputs()
            for path in outputs[1:]:
                if not path.is_file():
                    raise RuntimeError('Neovim package output is missing: ' + str(path))
            for path in self.editor_binaries():
                if not os.access(path, os.X_OK):
                    raise RuntimeError('Neovim tool is not executable: ' + str(path))
            atomic_write(outputs[0], report.read_text())
            if not self.editor_valid(recorded=False):
                raise RuntimeError('Neovim provisioning output verification failed')
            self.receipt('nvim', self.editor_identity(), self.editor_outputs())

    def install_ranger(self):
        scope = self.home / '.config/ranger/scope.sh'
        if scope.is_symlink() or (scope.exists() and not scope.is_file()):
            raise RuntimeError('Ranger preview script is unsafe: ' + str(scope))
        if not scope.exists():
            self.command(['ranger', '--copy-config=scope'], timeout=30)
        if scope.is_symlink() or not scope.is_file() or not os.access(scope, os.X_OK):
            raise RuntimeError('Ranger preview script is missing or unsafe: ' + str(scope))

    def release_path(self, name):
        return self.state / 'releases' / (name + '.json')

    @staticmethod
    def release_identity(spec):
        return json.dumps(spec, sort_keys=True, separators=(',', ':'))

    @staticmethod
    def require_minimum(name, version):
        match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', version)
        policy = VERSIONS[name] if name in VERSIONS else VERSIONS['system_tools'][name]
        minimum = tuple(map(int, policy['minimum_version'].split('.')))
        actual = tuple(int(part or 0) for part in match.groups()) if match else ()
        if actual < minimum + (0,) * (3 - len(minimum)):
            raise RuntimeError(name + ' requires version ' + policy['minimum_version'] + ' or newer')

    def installed_release(self, name):
        path = self.release_path(name)
        if path.is_symlink():
            raise RuntimeError('Unsafe installed release metadata: ' + name)
        try:
            return validate_spec(json.loads(path.read_text()))
        except (OSError, ValueError) as error:
            raise RuntimeError('Missing or invalid installed release metadata: ' + name) from error

    def archive_outputs(self, name):
        return [self.bin / name, self.release_path(name)]

    def install_lazygit(self):
        self.install_archive('lazygit', platform.machine())

    def install_archive(self, name, arch):
        spec = validate_spec(resolve_release(name, arch))
        self.require_minimum(name, spec['version'])
        identity = self.release_identity(spec)
        target = self.bin / name
        if self.receipt_valid(name, identity, self.archive_outputs(name)):
            return
        with tempfile.TemporaryDirectory(dir=self.state) as tmp:
            archive = Path(tmp) / spec['asset']
            download(spec['url'], archive, spec['sha256'])
            staged = Path(tmp) / name
            if name == 'bun':
                # Bound the ZIP central directory before ZipFile allocates its index.
                with archive.open('rb') as stream:
                    stream.seek(max(0, archive.stat().st_size - 65557))
                    footer = stream.read(65557)
                end = footer.rfind(b'PK\x05\x06')
                if end >= 20 and footer[end - 20:end - 16] == b'PK\x06\x07':
                    raise RuntimeError('ZIP64 directory is not supported for binary archives')
                if end < 0 or len(footer) - end < 22:
                    raise RuntimeError('Missing ZIP directory footer')
                directory = struct.unpack_from('<4s4H2LH', footer, end)
                if directory[4] > 10000 or directory[5] > 8 * 1024**2:
                    raise RuntimeError('ZIP directory exceeds extraction limits')
                with zipfile.ZipFile(archive) as contents:
                    matches = [p for p in contents.infolist() if p.filename.endswith('/bun')]
                    if len(matches) != 1 or matches[0].file_size > 512 * 1024**2:
                        raise RuntimeError('Expected one bounded Bun binary in archive')
                    with contents.open(matches[0]) as binary, staged.open('wb') as output:
                        shutil.copyfileobj(binary, output, 1024 * 1024)
            else:
                count = total_size = matches = 0
                with tarfile.open(archive, mode='r|*') as contents:
                    for member in contents:
                        count += 1
                        total_size += member.size
                        if count > 100000 or total_size > 2 * 1024**3 or member.size < 0:
                            raise RuntimeError('Archive exceeds extraction limits')
                        if member.isfile() and Path(member.name).name == name:
                            matches += 1
                            if matches > 1 or member.size > 512 * 1024**2:
                                raise RuntimeError('Expected one bounded ' + name + ' binary in archive')
                            with contents.extractfile(member) as binary, staged.open('wb') as output:
                                shutil.copyfileobj(binary, output, 1024 * 1024)
                if matches != 1:
                    raise RuntimeError('Expected one ' + name + ' binary in archive')
            staged.chmod(0o755)
            result = self.command([staged, '--version'], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, timeout=30)
            print(result.stdout.strip())
            self.require_minimum(name, result.stdout)
            self.preserve(target)
            os.replace(staged, target)
        atomic_write(self.release_path(name), json.dumps(spec) + '\n')
        self.receipt(name, identity, self.archive_outputs(name))


    def check(self):
        self.validate_paths()
        check_managed_tools(self, VERSIONS)
        # Check managed artifacts before executing them through prerequisites.
        if self.release_path('lazygit').exists():
            spec = self.installed_release('lazygit')
            if not self.receipt_valid('lazygit', self.release_identity(spec), self.archive_outputs('lazygit')):
                raise RuntimeError('Missing or changed installation: lazygit')
        self.prerequisites()
        failures = []
        if not self.editor_disabled and not self.editor_valid():
            failures.append('Neovim plugins or toolchain are missing or changed; rerun the full bootstrap')
        scope = self.home / '.config/ranger/scope.sh'
        if scope.is_symlink() or not scope.is_file() or not os.access(scope, os.X_OK):
            failures.append('Ranger preview script is missing or unsafe')
        for source, target in self.links:
            if self.copy_config:
                valid = (not target.is_symlink() and target.exists()
                         and target.is_dir() == (target in self.config_directories))
            else:
                valid = target.is_symlink() and target.resolve() == source
            if not valid:
                failures.append('Missing or conflicting configuration: ' + str(target))
        launcher = self.bin / 'btide'
        if not os.access(launcher, os.X_OK):
            failures.append('BTIDE launcher is not executable')
        if failures:
            raise RuntimeError('\n'.join(failures))
        print('Portable IDE configuration and tools verified; PiG is installed on first use.')


def install_dependencies(include_kitty=False):
    if shutil.which('apt-get'):
        # Install lazygit separately: Ubuntu repositories may not provide it.
        commands = [['apt-get', 'update'], ['apt-get', 'install', '-y', 'git', 'golang-go', 'nodejs', 'npm',
                    'tmux', 'neovim', 'ranger', 'ripgrep', 'fd-find', 'build-essential',
                    'libevent-dev', 'libncurses-dev', 'pkg-config', 'bison', 'ca-certificates', 'curl',
                    'unzip', 'xz-utils', 'python3', 'python3-venv', 'python3-pip', 'file']]
        optional = ['kitty', 'fontconfig', 'python3-pil']
    elif shutil.which('dnf'):
        commands = [['dnf', '--refresh', 'install', '-y', 'git', 'golang', 'nodejs', 'npm', 'tmux',
                    'neovim', 'ranger', 'ripgrep', 'fd-find', 'gcc', 'gcc-c++', 'make', 'bison', 'libevent-devel',
                    'ncurses-devel', 'pkgconf-pkg-config', 'ca-certificates', 'curl', 'unzip',
                    'xz', 'python3', 'python3-pip', 'file']]
        optional = ['kitty', 'fontconfig', 'python3-pillow']
    elif shutil.which('pacman'):
        commands = [['pacman', '-S', '--needed', 'git', 'go', 'nodejs', 'npm', 'tmux', 'lazygit',
                    'neovim', 'ranger', 'ripgrep', 'fd', 'base-devel', 'libevent', 'ncurses',
                    'pkgconf', 'ca-certificates', 'curl', 'unzip', 'xz', 'python', 'python-pip', 'file']]
        optional = ['kitty', 'fontconfig', 'python-pillow']
    else:
        raise RuntimeError('Automatic dependency installation requires apt, dnf, or pacman. '
                           'Install Git, Go 1.25+, Node.js 20+, tmux 3.2+, lazygit, Neovim 0.11.2+, '
                           'Ranger, ripgrep, fd, a C compiler, make, npm, curl, unzip, file and Python '
                           'with venv and ensurepip using your package manager.'
                           + (' Kitty, fontconfig and Pillow are also required for --include kitty.'
                              if include_kitty else ''))
    if include_kitty:
        commands[-1].extend(optional)
    for command in commands:
        run(['sudo', *command])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='Verify without writing or downloading')
    group.add_argument('--config-only', action='store_true', help='Deploy configuration and the executable launcher')
    parser.add_argument('--copy-config', action='store_true',
                        help='Install standalone copies instead of links to this checkout')
    parser.add_argument('--backup-existing', action='store_true',
                        help='Compatibility option; replacements always create timestamped backups')
    parser.add_argument('--install-deps', action='store_true',
                        help='Compatibility option; full installations always install missing dependencies')
    parser.add_argument('--include', choices=['kitty'], action='append', default=[],
                        help='Include Kitty, its configuration and Ranger image previews')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Python 3.10+ required')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'aarch64'):
        parser.error('Supported platforms: Linux x86_64 and aarch64')
    if os.geteuid() == 0:
        parser.error('Run as your normal user, not root')
    if args.install_deps and (args.check or args.config_only):
        parser.error('--install-deps requires a full installation')
    setup = Setup(Path.home(), include_kitty='kitty' in args.include, copy_config=args.copy_config)
    if args.check:
        setup.check()
        return
    setup.preflight_config()
    setup.state.mkdir(parents=True, exist_ok=True)
    setup.bin.mkdir(parents=True, exist_ok=True)
    with (setup.state / 'install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another btide installation is running') from None
        if not args.config_only:
            install_dependencies(include_kitty=setup.include_kitty)
            setup.install_lazygit()
            ensure_compatible_tools(setup, VERSIONS, download, atomic_write)
            setup.prerequisites()
        setup.configure()
        if not args.config_only:
            setup.install_editor()
            setup.install_ranger()
            setup.check()
    print('Installed ~/.local/bin/btide. Ensure ~/.local/bin is on your PATH, then run btide in your project.')
    print('No shell startup files were changed. PiG installs lazily on Alt+2.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
        print('btide: ' + str(error), file=sys.stderr)
        sys.exit(1)
