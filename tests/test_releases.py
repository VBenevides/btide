from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import releases


class ReleaseTests(unittest.TestCase):
    def test_github_digest_and_stable_requirement(self):
        metadata = {'tag_name': 'v0.99.0', 'prerelease': False, 'draft': False,
                    'assets': [{'name': 'nvim-linux-arm64.tar.gz',
                                'browser_download_url': 'https://github.com/neovim/neovim/releases/download/v0.99.0/nvim-linux-arm64.tar.gz',
                                'digest': 'sha256:' + 'a' * 64}]}
        with patch.object(releases, '_json', return_value=metadata):
            spec = releases.resolve_release('nvim', 'aarch64')
            self.assertEqual(spec['sha256'], 'a' * 64)
            self.assertEqual(spec['version'], '0.99.0')
            metadata['prerelease'] = True
            with self.assertRaisesRegex(RuntimeError, 'not stable'):
                releases.resolve_release('nvim', 'aarch64')

    def test_official_checksum_fallback(self):
        asset = 'lazygit_0.99.0_linux_x86_64.tar.gz'
        metadata = {'tag_name': 'v0.99.0', 'assets': [
            {'name': asset, 'browser_download_url': 'https://github.com/jesseduffield/lazygit/releases/download/v0.99.0/' + asset},
            {'name': 'checksums.txt', 'browser_download_url': 'https://github.com/jesseduffield/lazygit/releases/download/v0.99.0/checksums.txt'}]}
        with patch.object(releases, '_json', return_value=metadata), patch.object(releases, '_fetch', return_value='b' * 64 + '  ' + asset):
            self.assertEqual(releases.resolve_release('lazygit', 'x86_64')['sha256'], 'b' * 64)
        with patch.object(releases, '_json', return_value=metadata), patch.object(releases, '_fetch', return_value='unverified'):
            with self.assertRaisesRegex(RuntimeError, 'No verified'):
                releases.resolve_release('lazygit', 'x86_64')

    def test_go_official_stable_json(self):
        metadata = [{'version': 'go1.99.0', 'stable': True, 'files': [
            {'os': 'linux', 'arch': 'amd64', 'kind': 'archive', 'filename': 'go1.99.0.linux-amd64.tar.gz', 'sha256': 'c' * 64}]},
                    {'version': 'go2.0rc1', 'stable': False}]
        with patch.object(releases, '_json', return_value=metadata):
            self.assertEqual(releases.resolve_release('go', 'x86_64')['version'], '1.99.0')

    def test_node_selects_latest_stable_not_input_order_or_lts(self):
        asset = 'node-v99.1.0-linux-arm64.tar.gz'
        with patch.object(releases, '_json', return_value=[{'version': 'v98.0.0'}, {'version': 'v100.0.0-rc.1'}, {'version': 'v99.1.0'}]), patch.object(releases, '_fetch', return_value='d' * 64 + '  ' + asset):
            spec = releases.resolve_release('node', 'arm64')
            self.assertEqual(spec['version'], '99.1.0')
            self.assertEqual(spec['asset'], asset)

    def test_unsafe_urls_and_specs_rejected(self):
        for url in ('http://go.dev/file', 'https://evil.example/file', 'https://token@github.com/file', 'https://github.com:444/file'):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                releases.safe_url(url)
        with self.assertRaises(RuntimeError):
            releases.validate_spec({'version': '1.0.0', 'url': 'https://go.dev/file', 'sha256': '', 'asset': 'file'})

    def test_checksum_requires_unique_exact_filename(self):
        for text in ('a' * 64 + '  other', ('a' * 64 + '  file\n') * 2):
            with self.assertRaises(RuntimeError):
                releases._checksum(text, 'file')

    def test_redirect_is_rejected_before_following_untrusted_destination(self):
        from urllib.request import Request
        for url in ('http://github.com/file', 'https://127.0.0.1/file', 'https://evil.example/file'):
            with self.subTest(url=url), self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                releases._Redirects().redirect_request(
                    Request('https://github.com/file'), None, 302, '', {}, url)

    def test_metadata_size_is_bounded(self):
        class Response:
            url = 'https://go.dev/dl/?mode=json'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                return b'x' * size
        response = Response()
        with patch.object(releases, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(RuntimeError, 'size limit'):
                releases._fetch(response.url)


if __name__ == '__main__':
    unittest.main()
