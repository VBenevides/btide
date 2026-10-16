"""Bounded upstream stable-release discovery; downloads require upstream SHA256."""
import json
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_METADATA = 8 * 1024 * 1024
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
         'objects.githubusercontent.com', 'go.dev', 'dl.google.com', 'nodejs.org',
         'registry.npmjs.org'}


def safe_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username
            or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
        raise RuntimeError('Unsafe upstream metadata/download URL')
    return url


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url, timeout=30):
    safe_url(url)
    return build_opener(_Redirects()).open(Request(url, headers={
        'User-Agent': 'BTIDE-release-resolver', 'Accept': 'application/json'}), timeout=timeout)


def _fetch(url):
    safe_url(url)
    try:
        with open_url(url) as response:
            safe_url(response.url)
            data = response.read(MAX_METADATA + 1)
        if len(data) > MAX_METADATA:
            raise RuntimeError('Upstream metadata exceeds size limit')
        return data.decode('utf-8')
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError('Cannot retrieve upstream release metadata') from error


def _json(url):
    try:
        return json.loads(_fetch(url))
    except ValueError as error:
        raise RuntimeError('Invalid upstream release JSON') from error


def _checksum(text, filename):
    matches = []
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(.+)', line.strip())
        if match and match[2] == filename:
            matches.append(match[1].lower())
        bsd = re.fullmatch(r'SHA256 \((.+)\) = ([0-9a-fA-F]{64})', line.strip())
        if bsd and bsd[1] == filename:
            matches.append(bsd[2].lower())
    if len(matches) != 1:
        raise RuntimeError('Missing or ambiguous upstream SHA256 for ' + filename)
    return matches[0]


def validate_spec(spec):
    if (not isinstance(spec, dict) or set(spec) != {'version', 'url', 'sha256', 'asset'}
            or not all(isinstance(value, str) for value in spec.values())
            or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?[a-z]?', spec['version'])
            or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256'])
            or not re.fullmatch(r'[A-Za-z0-9_.-]+', spec['asset'])):
        raise RuntimeError('Invalid resolved release specification')
    parsed = urlsplit(spec['url'])
    if parsed.query or parsed.path.rsplit('/', 1)[-1] != spec['asset']:
        raise RuntimeError('Resolved asset URL contains credentials or mismatched filename')
    safe_url(spec['url'])
    return spec


def _spec(version, url, sha256, asset):
    return validate_spec(dict(version=version, url=url, sha256=sha256, asset=asset))


def resolve_release(name, architecture):
    architecture = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(architecture, architecture)
    if architecture not in ('x86_64', 'aarch64'):
        raise RuntimeError('Unsupported release architecture: ' + architecture)
    if name == 'go':
        releases = _json('https://go.dev/dl/?mode=json')
        stable = [r for r in releases if r.get('stable') and re.fullmatch(r'go\d+\.\d+\.\d+', r.get('version', ''))]
        release = max(stable, key=lambda r: tuple(map(int, r['version'][2:].split('.'))))
        arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}[architecture]
        files = [f for f in release['files'] if f.get('os') == 'linux' and f.get('arch') == arch and f.get('kind') == 'archive']
        if len(files) != 1:
            raise RuntimeError('Missing or ambiguous Go archive')
        file = files[0]
        return _spec(release['version'][2:], 'https://go.dev/dl/' + file['filename'], file['sha256'], file['filename'])
    if name == 'node':
        releases = _json('https://nodejs.org/dist/index.json')
        stable = [r for r in releases if re.fullmatch(r'v\d+\.\d+\.\d+', r.get('version', ''))]
        version = max(stable, key=lambda r: tuple(map(int, r['version'][1:].split('.'))))['version']
        arch = {'x86_64': 'x64', 'aarch64': 'arm64'}[architecture]
        asset = 'node-' + version + '-linux-' + arch + '.tar.gz'
        base = 'https://nodejs.org/dist/' + version + '/'
        return _spec(version[1:], base + asset, _checksum(_fetch(base + 'SHASUMS256.txt'), asset), asset)
    repos = {'bun': 'oven-sh/bun', 'lazygit': 'jesseduffield/lazygit', 'nvim': 'neovim/neovim', 'tmux': 'tmux/tmux'}
    if name not in repos:
        raise RuntimeError('Unknown upstream release: ' + name)
    release = _json('https://api.github.com/repos/' + repos[name] + '/releases/latest')
    if release.get('prerelease') or release.get('draft'):
        raise RuntimeError('Upstream latest release is not stable')
    version = release['tag_name'].removeprefix('bun-v').removeprefix('v')
    arch = 'arm64' if architecture == 'aarch64' else 'x86_64'
    asset = {'bun': 'bun-linux-' + ('aarch64' if architecture == 'aarch64' else 'x64-baseline') + '.zip',
             'lazygit': 'lazygit_' + version + '_linux_' + arch + '.tar.gz',
             'nvim': 'nvim-linux-' + arch + '.tar.gz',
             'tmux': 'tmux-' + version + '.tar.gz'}[name]
    assets = release['assets']
    selected = [a for a in assets if a['name'] == asset]
    if len(selected) != 1:
        raise RuntimeError('Missing or ambiguous upstream asset: ' + asset)
    selected = selected[0]
    digest = selected.get('digest') or ''
    if re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        checksum = digest[7:]
    else:
        candidates = [a for a in assets if re.search(r'(checksums?|sha256|shasums)', a['name'], re.I)]
        if len(candidates) > 8:
            raise RuntimeError('Too many upstream checksum assets')
        checksum = None
        for candidate in candidates:
            text = _fetch(candidate['browser_download_url'])
            if candidate['name'] in (asset + '.sha256', asset + '.sha256sum') and re.fullmatch(r'[0-9a-fA-F]{64}\s*', text):
                checksum = text.strip().lower()
                break
            try:
                checksum = _checksum(text, asset)
                break
            except RuntimeError:
                continue
        if checksum is None:
            raise RuntimeError('No verified upstream SHA256 for ' + asset)
    return _spec(version, selected['browser_download_url'], checksum, asset)
