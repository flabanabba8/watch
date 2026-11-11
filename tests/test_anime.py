import importlib.util
import json
import socket
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'anime'
spec = importlib.util.spec_from_file_location('watch_anime_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from watch_anime_test.library import Library
from watch_anime_test.net import public_url
from watch_anime_test.provider import Provider, title_id, episode_number
from watch_anime_test.player import WatchAnime


class ProviderFixture(Provider):
    def __init__(self):
        self.calls = []

    def call(self, *args):
        self.calls.append(args)
        if args[0] == 'search':
            return 'original-test-123\tOriginal &amp; Test\nother-season-456\tOther season\n'
        if args[0] == 'episodes':
            return '10\t1\n11\t2\n12\t12.5\n'
        return 'REFERER\thttps://example.com/\nSUBTITLE\thttps://example.com/captions.vtt\n1080p >https://example.com/high.m3u8\n360p >https://example.com/low.m3u8\n'


class WatchAnimeTests(unittest.TestCase):
    def test_unsupported_platform_refuses_before_storage_or_provider(self):
        with patch.object(package.sys, 'platform', 'win32'):
            result=json.loads(package.invoke('anime_search',{'query':'fictional'}))
            self.assertIn('requires Linux',result['error']);self.assertFalse(result['retry_automatically'])
            with self.assertRaisesRegex(ValueError,'requires Linux'):Provider().call('fictional')

    def test_exact_title_and_quality_fallback(self):
        p = ProviderFixture()
        self.assertEqual(p.search('A & B')[0]['title'], 'Original & Test')
        self.assertEqual(p.calls[0], ('search', 'A+%26+B'))
        with patch('watch_anime_test.provider.public_url'):
            result = p.resolve('original-test-123', '12.5', 'sub', '720')
        self.assertEqual(result['height'], 360)
        self.assertTrue(result['quality_fallback'])
        self.assertEqual(p.calls[-1], ('resolve', '12', '12.5', 'sub'))

    def test_boundary_inputs_and_unreleased_episode(self):
        for value in ['../x', 'x;touch y', '--version', 'foo\nbar', '']:
            with self.assertRaises(ValueError): title_id(value)
        for value in ['1-12', '1;exit', 'nan', '1.2.3', 2]:
            with self.assertRaises(ValueError): episode_number(value)
        with self.assertRaises(ValueError): ProviderFixture().resolve('original-test-123', '999')

    def test_public_url_rejects_private_and_credential_destinations(self):
        for url in ['http://example.com/a', 'file:///etc/passwd', 'https://user:pass@example.com/a']:
            with self.assertRaises(ValueError): public_url(url)
        with patch('watch_anime_test.net.socket.getaddrinfo', return_value=[(2,1,6,'',(socket.gethostbyname('localhost'),443))]):
            with self.assertRaises(ValueError): public_url('https://example.com/a')

    def test_profile_isolation_and_completion(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            lib, other = Library(a), Library(b)
            lib.save_titles([{'id': 'original-test-123', 'title': 'Original'}])
            lib.update_progress('original-test-123', '1', 'sub', 98, 100)
            self.assertFalse(lib.history()[0]['watched'])
            self.assertEqual(other.history(), [])
            lib.update_progress('original-test-123', '1', 'sub', 99, 100, ended=True)
            self.assertTrue(lib.history()[0]['watched'])
            with self.assertRaises(ValueError): lib.update_progress('original-test-123', '1', 'sub', float('nan'), 100)

    def test_resume_uses_observed_episode_then_advances_only_after_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = WatchAnime(tmp, ProviderFixture())
            app.search('Original')
            app.library.update_progress('original-test-123', '1', 'sub', 40, 100)
            with patch.object(app, 'play', return_value={'state': 'starting'}) as play:
                app.resume()
                self.assertEqual(play.call_args.args[:3], ('original-test-123', '1', 'sub'))
            app.library.update_progress('original-test-123', '1', 'sub', 99, 100, ended=True)
            with patch.object(app, 'play') as play:
                app.resume()
                self.assertEqual(play.call_args.args[1], '2')

    def test_registration_has_no_network_or_player_side_effects(self):
        class Context:
            def __init__(self): self.tools = []
            def register_tool(self, **kw): self.tools.append(kw)
        context = Context()
        package.register(context)
        self.assertEqual(len(context.tools), 7)
        self.assertEqual(len({t['name'] for t in context.tools}), 7)

    def test_provider_calls_are_serialized_across_instances(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            p = Provider(tmp)
            with (Path(tmp) / 'provider.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(p, '_run') as run:
                    with self.assertRaisesRegex(RuntimeError, 'Another provider request'):
                        p.call('search', 'test')
                    run.assert_not_called()
            with patch.object(p, '_run', return_value='test'):
                self.assertEqual(p.call('search', 'test'), 'test')
                self.assertTrue((Path(tmp) / 'provider-last-request.txt').exists())


if __name__ == '__main__': unittest.main()
