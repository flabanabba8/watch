import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1] / 'movies'
spec = importlib.util.spec_from_file_location('movies_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec); sys.modules[spec.name] = package; spec.loader.exec_module(package)
from movies_test.player import WatchMovies
from movies_test.provider import Provider, title_id, integer
from movies_test.library import Library


class Fixture(Provider):
    def __init__(self): self.requests = []; self.bridge = 'fixture-bridge'
    def call(self, request):
        self.requests.append(request)
        if request['action'] == 'search':
            return {'items': [{'id': 'movie-1', 'name': 'Original Film', 'info': '2026 · Movie'},
                              {'id': 'tv-2', 'name': 'Original Show', 'info': '2025 · Series'}], 'hasMore': False}
        if request['action'] == 'details':
            return {'description': 'Original fixture', 'episodes': [{'season': 1, 'number': '1'}, {'season': 1, 'number': '2'}, {'season': 2, 'number': '1'}]}
        return {'streams': [{'url': 'https://example.com/master.m3u8', 'headers': {'Referer': 'https://example.com/', 'Origin': 'https://example.com', 'User-Agent': 'Original fixture'},
                              'captions': [], 'sources': ['Cinejoy unavailable', 'VixSrc selected'], 'label': 'Auto · VixSrc'}]}


class MovieTests(unittest.TestCase):
    def test_registered_handler_reads_keyed_config_without_secret(self):
        class Context:
            def __init__(self): self.handlers = {}; self.keys = []
            def get_config(self, key): self.keys.append(key); return {'bridge_path': 'fixture-bridge'}.get(key)
            def register_tool(self, **kwargs): self.handlers[kwargs['name']] = kwargs['handler']
        ctx = Context(); package.register(ctx)
        with patch.object(package, 'invoke', return_value='{}') as call:
            ctx.handlers['movies_history']({})
        self.assertEqual(call.call_args.args[2], {'bridge_path': 'fixture-bridge'})
        self.assertNotIn('tmdb_api_key', ctx.keys)

    def test_unsupported_platform_refuses_before_storage_or_provider(self):
        with patch.object(package.sys, 'platform', 'win32'):
            result=json.loads(package.invoke('movies_search',{'query':'fictional'}))
            self.assertIn('requires Linux',result['error']);self.assertFalse(result['retry_automatically'])
            with self.assertRaisesRegex(ValueError,'requires Linux'):Provider(Path('/tmp/fixture')).call({'action':'search'})

    def test_search_year_kind_and_metadata_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = Fixture(); app = WatchMovies(tmp, provider)
            results = app.search('Original')
            self.assertEqual(results['items'][0]['title'], 'Original Film (2026)')
            self.assertIn('not endorsed or certified', results['attribution'])
            self.assertEqual(results['items'][1]['kind'], 'tv')
            self.assertEqual(app.details('tv-2', season=2)['episodes'], [{'season': 2, 'number': 1}])
            app.details('tv-2', season=1)
            self.assertEqual(sum(r['action'] == 'details' for r in provider.requests), 1)

    def test_master_and_required_headers_survive_resolution(self):
        provider = Fixture()
        with patch('movies_test.provider.public_url'):
            stream = provider.resolve({'id': 'movie-1', 'name': 'Original Film', 'year': '2026'}, 0, 0)
        self.assertEqual(stream['url'], 'https://example.com/master.m3u8')
        self.assertEqual(stream['headers']['Origin'], 'https://example.com')
        self.assertEqual(stream['headers']['User-Agent'], 'Original fixture')
        self.assertTrue(stream['master_playlist_preserved'])

    def test_source_independent_progress_and_tv_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = WatchMovies(tmp, Fixture()); app.search('Original')
            app.library.update_progress('movie-1', 'movie', 'cinejoy', 75, 100)
            self.assertEqual(app.library.latest_progress('movie-1', 'movie')['position'], 75)
            with patch.object(app, 'play') as play:
                app.resume('movie-1', source='vixsrc')
                self.assertEqual(play.call_args.args, ('movie-1', 0, 0, 'vixsrc', True))
            app.library.update_progress('tv-2', 'S1E2', 'auto', 99, 100, ended=True)
            with patch.object(app, 'play') as play:
                app.resume('tv-2')
                self.assertEqual(play.call_args.args[:3], ('tv-2', 2, 1))

    def test_finished_movie_requires_explicit_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = WatchMovies(tmp, Fixture()); app.search('Original')
            app.library.update_progress('movie-1', 'movie', 'auto', 99, 100, ended=True)
            with patch.object(app, 'play') as play:
                self.assertEqual(app.resume('movie-1')['state'], 'completed')
                play.assert_not_called()

    def test_changed_source_launches_at_saved_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = WatchMovies(tmp, Fixture()); app.search('Original')
            app.library.update_progress('movie-1', 'movie', 'cinejoy', 75, 100)
            process = Mock(pid=987654321); process.wait.return_value = 0
            with patch('movies_test.provider.public_url'), patch('movies_test.player.shutil.which', return_value='/fixture/mpv'), patch('movies_test.player.subprocess.Popen', return_value=process), patch.object(app, 'status', side_effect=lambda sid: {'id': sid, 'state': 'playing'}):
                app.play('movie-1', source='vixsrc')
            request = json.loads(next(Path(tmp).glob('*/request.json')).read_text())
            self.assertEqual(request['start'], 70)
            self.assertEqual(request['audio'], 'vixsrc')

    def test_input_boundaries(self):
        for value in ['../1', 'movie-1;exit', 'anime-1', '--help']:
            with self.assertRaises(ValueError): title_id(value)
        for value in [True, '1', -1, 1.5]:
            with self.assertRaises(ValueError): integer(value, 0, 100, 'episode')

    def test_playback_fallback_is_once_and_respects_cancellation(self):
        from movies_test import worker
        import uuid
        for first in [{'state': 'failed', 'loaded': False, 'cancelled': False},
                      {'state': 'failed', 'loaded': False, 'cancelled': True},
                      {'state': 'failed', 'loaded': True, 'cancelled': False}]:
            with tempfile.TemporaryDirectory() as tmp:
                lib = Library(tmp); sid = uuid.uuid4().hex; folder = Path(tmp) / sid; folder.mkdir()
                lib.session(sid, 'movie-1', 'movie', 'auto', 'starting', {})
                request = {'id': sid, 'title_id': 'movie-1', 'episode': 'movie', 'audio': 'auto',
                           'fallback': {'bridge': 'fixture', 'title': {}, 'season': 0, 'episode': 0}}
                (folder / 'request.json').write_text(json.dumps(request))
                stream = {'label': 'LookMovie fixture', 'sources': []}
                with patch.object(worker, 'play_once', side_effect=[first, {'state': 'stopped'}]) as play, patch.object(worker.Provider, 'resolve', return_value=stream) as resolve:
                    worker.watch(folder, headless=True)
                    expected = not first['cancelled'] and not first['loaded']
                    self.assertEqual(resolve.call_count, int(expected))
                    self.assertEqual(play.call_count, 2 if expected else 1)
                    if expected: self.assertNotIn('fallback', play.call_args.args[1])


if __name__ == '__main__': unittest.main()
