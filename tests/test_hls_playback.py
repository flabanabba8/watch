"""Original HLS fixture with a separate audio rendition and required headers."""
import functools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from test_movies import ROOT
from movies_test.library import Library
from movies_test.player import ipc


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('ffmpeg') and shutil.which('mpv'), 'Linux mpv/FFmpeg required')
class HLSPlayback(unittest.TestCase):
    def test_master_keeps_separate_audio_and_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); media = root / 'media'; media.mkdir()
            common = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi']
            subprocess.run(common + ['-i', 'testsrc2=size=320x180:rate=30', '-t', '5', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-g', '30',
                                     '-f', 'hls', '-hls_time', '1', '-hls_playlist_type', 'vod', '-hls_segment_filename', str(media / 'v%d.ts'), str(media / 'video.m3u8')], check=True, timeout=20)
            subprocess.run(common + ['-i', 'sine=frequency=440:sample_rate=48000', '-t', '5', '-vn', '-c:a', 'aac',
                                     '-f', 'hls', '-hls_time', '1', '-hls_playlist_type', 'vod', '-hls_segment_filename', str(media / 'a%d.ts'), str(media / 'audio.m3u8')], check=True, timeout=20)
            (media / 'master.m3u8').write_text('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="audio.m3u8"\n#EXT-X-STREAM-INF:BANDWIDTH=500000,AUDIO="audio"\nvideo.m3u8\n')
            received, wrong = [], []
            class Server(SimpleHTTPRequestHandler):
                def do_GET(self):
                    received.append(self.path)
                    if self.headers.get('Origin') != 'https://example.com' or self.headers.get('Referer') != 'https://example.com/' or self.headers.get('User-Agent') != 'MovieFixture':
                        wrong.append(self.path); self.send_error(403); return
                    super().do_GET()
                def log_message(self, *_): pass
            server = ThreadingHTTPServer(('localhost', 0), functools.partial(Server, directory=str(media)))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            data_root = root / 'library'; lib = Library(data_root)
            lib.save_titles([{'id': 'movie-1', 'title': 'Original HLS Fixture'}])
            sid = uuid.uuid4().hex; folder = data_root / sid; folder.mkdir()
            lib.session(sid, 'movie-1', 'movie', 'auto', 'starting', {})
            (folder / 'request.json').write_text(json.dumps({'id': sid, 'title_id': 'movie-1', 'title': 'Original HLS Fixture',
                'episode': 'movie', 'audio': 'auto', 'start': 0, 'stream': {
                    'url': f'http://localhost:{server.server_port}/master.m3u8', 'referer': 'https://example.com/', 'subtitle': None,
                    'headers': {'Origin': 'https://example.com', 'User-Agent': 'MovieFixture'}}}))
            process = subprocess.Popen([sys.executable, str(ROOT / 'worker.py'), str(folder), '--fixture-headless'])
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    state = lib.session(sid)
                    if state['state'] != 'starting': break
                    time.sleep(.1)
                self.assertEqual(state['state'], 'playing', state)
                tracks = ipc(state['detail']['socket'], ['get_property', 'track-list'])
                self.assertTrue(any(t['type'] == 'video' and t.get('selected') for t in tracks), tracks)
                self.assertTrue(any(t['type'] == 'audio' and t.get('selected') for t in tracks), tracks)
                process.wait(timeout=15)
                self.assertEqual(lib.session(sid)['state'], 'completed', lib.session(sid))
                self.assertTrue(lib.progress('movie-1', 'movie', 'auto')['watched'])
                self.assertFalse(wrong)
                self.assertIn('/master.m3u8', received)
                self.assertIn('/audio.m3u8', received)
                self.assertIn('/video.m3u8', received)
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=8)
                server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': unittest.main()
