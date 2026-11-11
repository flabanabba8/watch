"""Launch only plugin-owned mpv sessions; communicate through their private sockets."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import threading
import uuid

from .library import Library
from .provider import Provider, episode_number, title_id
from .process_env import process_env


def process_identity(pid):
    try:
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, ValueError, IndexError):
        return None


def ipc(path, command):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(3)
        conn.connect(path)
        conn.sendall((json.dumps({'command': command, 'request_id': 42}) + '\n').encode())
        pending = b''
        while len(pending) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                break
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                response = json.loads(line)
                if response.get('request_id') == 42:
                    if response.get('error') != 'success':
                        raise RuntimeError('Player command failed: ' + str(response.get('error')))
                    return response.get('data')
        raise RuntimeError('Player did not acknowledge the command')


class WatchAnime:
    def __init__(self, root, provider=None):
        self.library = Library(root)
        self.root = self.library.root
        self.provider = provider or Provider(self.root)

    def search(self, query):
        titles = self.provider.search(query)
        self.library.save_titles(titles)
        return {'results': titles, 'notice': 'Select the exact title/season ID before playback; provider availability may change.'}

    def episodes(self, identifier):
        title = self.library.title(title_id(identifier))
        return {'title': title['title'], 'id': identifier, 'episodes': self.provider.episodes(identifier)}

    def play(self, identifier, episode, audio='sub', quality='720', resume=True):
        if sys.platform != 'linux':
            raise ValueError('This development build supports Linux playback; Windows is pending verification')
        if not isinstance(resume, bool):
            raise ValueError('resume must be true or false')
        if not shutil.which('mpv'):
            raise ValueError('Install mpv with your package manager before playing')
        title = self.library.title(title_id(identifier))
        episode_number(episode)
        stream = self.provider.resolve(identifier, episode, audio, quality)
        previous = self.library.progress(identifier, episode, audio)
        start = max(0, previous['position'] - 5) if resume and previous and not previous['watched'] else 0
        session_id = uuid.uuid4().hex
        folder = self.root / session_id
        folder.mkdir(mode=0o700)
        request = {'id': session_id, 'title_id': identifier, 'title': title['title'], 'episode': episode,
                   'audio': audio, 'start': start, 'stream': stream}
        request_path = folder / 'request.json'
        fd = os.open(request_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(request, out)
        detail = {'height': stream['height'], 'quality_fallback': stream['quality_fallback'],
                  'start': start, 'title': title['title']}
        self.library.session(session_id, identifier, episode, audio, 'starting', detail)
        try:
            with (folder / 'worker.log').open('wb') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker.py')), str(folder)],
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, env=process_env())
        except OSError:
            request_path.unlink(missing_ok=True)
            self.library.session(session_id, identifier, episode, audio, 'failed', {'error': 'Could not start playback worker'})
            raise RuntimeError('Could not start playback worker') from None
        owner = {'pid': process.pid, 'identity': process_identity(process.pid)}
        threading.Thread(target=process.wait, daemon=True).start()
        (folder / 'owner.json').write_text(json.dumps(owner))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            state = self.status(session_id)
            if state['state'] != 'starting':
                return state
            time.sleep(.1)
        return self.status(session_id)

    def status(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{32}', session_id):
            raise ValueError('Invalid playback session ID')
        state = self.library.session(session_id)
        owner_path = self.root / session_id / 'owner.json'
        if state['state'] in ('starting', 'playing', 'paused') and owner_path.exists():
            owner = json.loads(owner_path.read_text())
            if owner['identity'] is None or process_identity(owner['pid']) != owner['identity']:
                state.update(state='interrupted', error='Playback worker exited; saved progress remains available')
        state['progress'] = self.library.progress(state['title_id'], state['episode'], state['audio'])
        # The model does not need the local IPC pathname.
        state['detail'].pop('socket', None)
        return state

    def control(self, session_id, action, seconds=None):
        state = self.status(session_id)
        if state['state'] not in ('playing', 'paused'):
            raise ValueError('Session is not ready for playback control')
        if action not in ('pause', 'unpause', 'seek', 'stop'):
            raise ValueError('Choose pause, unpause, seek or stop')
        socket_path = self.library.session(session_id)['detail']['socket']
        if action == 'seek':
            if isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not 0 <= seconds <= 28800:
                raise ValueError('Seek requires a finite position between 0 and 28800 seconds')
            duration = (state['progress'] or {}).get('duration')
            if duration and seconds > duration:
                raise ValueError('Seek exceeds episode duration')
            command = ['seek', seconds, 'absolute+exact']
        elif action == 'stop':
            # The observer saves the actual position continuously and on shutdown.
            command = ['quit']
        else:
            command = ['set_property', 'pause', action == 'pause']
        result = ipc(socket_path, command)
        return {'session_id': session_id, 'action': action, 'acknowledged': True, 'result': result}

    def history(self):
        return {'history': self.library.history()}

    def resume(self, identifier=None, quality='720'):
        rows = self.library.history()
        if identifier is not None:
            title_id(identifier)
            rows = [r for r in rows if r['title_id'] == identifier]
        if not rows:
            raise ValueError('No observed playback history is available')
        latest = rows[0]
        episode = latest['episode']
        if latest['watched']:
            episodes = [e['number'] for e in self.provider.episodes(latest['title_id'])]
            if episode not in episodes or episodes.index(episode) + 1 >= len(episodes):
                return {'state': 'caught_up', 'title': latest['title'], 'last_episode': episode}
            episode = episodes[episodes.index(episode) + 1]
        return self.play(latest['title_id'], episode, latest['audio'], quality, True)
