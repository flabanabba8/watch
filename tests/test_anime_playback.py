"""Real mpv integration using original generated media and null outputs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from test_anime import ROOT
from watch_anime_test.library import Library
from watch_anime_test.player import WatchAnime, process_identity, ipc


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('mpv') and shutil.which('ffmpeg'), 'Linux mpv/FFmpeg required')
class PlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.media = Path(cls.temp.name) / 'original-fixture.mp4'
        cls.subtitles = Path(cls.temp.name) / 'original captions.vtt'
        cls.subtitles.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nOriginal test caption.\n')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000', '-t', '5',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(cls.media)], check=True, timeout=20)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def launch(self, root, start=0):
        lib = Library(root)
        lib.save_titles([{'id': 'original-test-123', 'title': 'Original test fixture'}])
        sid = uuid.uuid4().hex
        folder = Path(root) / sid
        folder.mkdir()
        lib.session(sid, 'original-test-123', '1', 'sub', 'starting', {'fixture': True})
        (folder / 'request.json').write_text(json.dumps({'id': sid, 'title_id': 'original-test-123',
            'title': 'Original test fixture', 'episode': '1', 'audio': 'sub', 'start': start,
            'stream': {'url': str(self.media), 'referer': 'https://example.com/', 'subtitle': str(self.subtitles)}}))
        proc = subprocess.Popen([sys.executable, str(ROOT / 'worker.py'), str(folder), '--fixture-headless'])
        (folder / 'owner.json').write_text(json.dumps({'pid': proc.pid, 'identity': process_identity(proc.pid)}))
        return lib, sid, proc

    def test_natural_playback_persists_completion(self):
        with tempfile.TemporaryDirectory() as root:
            lib, sid, proc = self.launch(root)
            try:
                proc.wait(timeout=15)
                state = lib.session(sid)
                self.assertEqual(state['state'], 'completed', state)
                progress = lib.progress('original-test-123', '1', 'sub')
                self.assertGreater(progress['position'], 4)
                self.assertTrue(progress['watched'], progress)
                self.assertNotIn('socket', state['detail'])
                self.assertFalse((Path(root) / sid / 'request.json').exists())
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()

    def test_controls_and_resume_offset(self):
        with tempfile.TemporaryDirectory() as root:
            lib, sid, proc = self.launch(root, start=1)
            app = WatchAnime(root)
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and app.status(sid)['state'] == 'starting': time.sleep(.1)
                self.assertEqual(app.status(sid)['state'], 'playing', app.status(sid))
                tracks = ipc(lib.session(sid)['detail']['socket'], ['get_property', 'track-list'])
                self.assertTrue(any(t['type'] == 'sub' and t.get('selected') for t in tracks), tracks)
                self.assertTrue(app.control(sid, 'pause')['acknowledged'])
                app.control(sid, 'seek', 2)
                time.sleep(1.2)
                state = app.status(sid)
                self.assertEqual(state['state'], 'paused', state)
                self.assertAlmostEqual(state['progress']['position'], 2, delta=.25)
                app.control(sid, 'stop')
                proc.wait(timeout=8)
                self.assertEqual(app.status(sid)['state'], 'stopped')
                self.assertFalse(app.history()['history'][0]['watched'])
                self.assertGreater(app.history()['history'][0]['position'], 1)
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()

    def test_worker_shutdown_keeps_progress(self):
        with tempfile.TemporaryDirectory() as root:
            lib, sid, proc = self.launch(root)
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    progress = lib.progress('original-test-123', '1', 'sub')
                    if progress and progress['position'] >= 1: break
                    time.sleep(.1)
                proc.terminate()
                proc.wait(timeout=8)
                self.assertEqual(lib.session(sid)['state'], 'stopped', lib.session(sid))
                self.assertGreater(lib.progress('original-test-123', '1', 'sub')['position'], .5)
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()


if __name__ == '__main__': unittest.main()
