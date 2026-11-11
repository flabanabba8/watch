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
from .provider import Provider, integer, title_id
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


TMDB_ATTRIBUTION = "This product uses the TMDB API but is not endorsed or certified by TMDB."


class WatchMovies:
    def __init__(self, root, provider=None, settings=None):
        self.library = Library(root)
        self.root = self.library.root
        self.provider = provider or Provider(self.root, (settings or {}).get('bridge_path', 'ani-luffy-bridge'), (settings or {}).get('bridge_sha256', ''))

    def search(self, query, page=1, kind='all'):
        result = self.provider.search(query, page, kind)
        self.library.save_catalog(result['items'])
        return {**result, 'notice': 'Choose the exact title, year and movie/TV kind. Filters apply to this result page.', 'attribution': TMDB_ATTRIBUTION}

    def _details(self, identifier, refresh=False):
        cached = self.library.details(identifier)
        if refresh or not cached or cached['age_seconds'] > 86400:
            data = self.provider.details(identifier)
            self.library.details(identifier, data)
            return data
        return cached['data']

    def details(self, identifier, season=1, refresh=False):
        title = self.library.catalog(title_id(identifier))
        integer(season, 0, 1000, 'season')
        if not isinstance(refresh, bool): raise ValueError('refresh must be true or false')
        data = self._details(identifier, refresh)
        seasons = sorted({e['season'] for e in data['episodes']})
        selected = 0 if title['kind'] == 'movie' else season
        return {'title': title, 'description': data['description'], 'seasons': seasons,
                'episodes': [e for e in data['episodes'] if e['season'] == selected],
                'notice': 'Listed TV episodes are metadata, not a guarantee that a playable source has been released.', 'attribution': TMDB_ATTRIBUTION}

    def play(self, identifier, season=0, episode=0, source='auto', resume=True):
        if sys.platform != 'linux':
            raise ValueError('This development build supports Linux playback; Windows is pending verification')
        if not isinstance(resume, bool):
            raise ValueError('resume must be true or false')
        if not shutil.which('mpv'):
            raise ValueError('Install mpv with your package manager before playing')
        title = self.library.catalog(title_id(identifier))
        integer(season, 0, 1000, 'season'); integer(episode, 0, 10000, 'episode')
        if title['kind'] == 'movie' and (season != 0 or episode != 0):
            raise ValueError('Movies use season0 and episode0')
        if title['kind'] == 'tv' and {'season': season, 'number': episode} not in self._details(identifier)['episodes']:
            raise ValueError('Select a listed season and episode for this TV title')
        stream = self.provider.resolve(title, season, episode, source)
        episode_key = 'movie' if title['kind'] == 'movie' else f'S{season}E{episode}'
        previous = self.library.latest_progress(identifier, episode_key)
        start = max(0, previous['position'] - 5) if resume and previous and not previous['watched'] else 0
        session_id = uuid.uuid4().hex
        folder = self.root / session_id
        folder.mkdir(mode=0o700)
        request = {'id': session_id, 'title_id': identifier, 'title': title['title'], 'episode': episode_key,
                   'audio': source, 'start': start, 'stream': stream,
                   'display_title': title['title'] + (f' — Season {season}, Episode {episode}' if title['kind'] == 'tv' else '')}
        if source == 'auto' and stream['resolved_source'] != 'lookmovie':
            request['load_timeout'] = 15
            request['fallback'] = {'bridge': self.provider.bridge, 'title': title, 'season': season, 'episode': episode}
        request_path = folder / 'request.json'
        fd = os.open(request_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(request, out)
        detail = {'source': source, 'source_label': stream['label'], 'source_reports': stream['sources'],
                  'master_playlist_preserved': True, 'season': season, 'episode_number': episode,
                  'start': start, 'title': title['title']}
        self.library.session(session_id, identifier, episode_key, source, 'starting', detail)
        try:
            with (folder / 'worker.log').open('wb') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('worker.py')), str(folder)],
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, env=process_env())
        except OSError:
            request_path.unlink(missing_ok=True)
            self.library.session(session_id, identifier, episode_key, source, 'failed', {'error': 'Could not start playback worker'})
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
        if state['state'] in ('starting', 'recovering', 'playing', 'paused') and owner_path.exists():
            owner = json.loads(owner_path.read_text())
            if owner['identity'] is None or process_identity(owner['pid']) != owner['identity']:
                state.update(state='interrupted', error='Playback worker exited; saved progress remains available')
        state['progress'] = self.library.progress(state['title_id'], state['episode'], state['audio'])
        # The model does not need the local IPC pathname.
        state['detail'].pop('socket', None)
        return state

    def control(self, session_id, action, seconds=None):
        state = self.status(session_id)
        if action == 'stop' and state['state'] in ('starting', 'recovering', 'playing', 'paused'):
            (self.root / session_id / 'stop').touch(mode=0o600, exist_ok=True)
            return {'session_id': session_id, 'action': action, 'stop_requested': True,
                    'notice': 'Status confirms shutdown; an in-flight provider resolution is bounded but may need to finish.'}
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
        rows, seen = [], set()
        for row in self.library.history():
            key = (row['title_id'], row['episode'])
            if key in seen: continue
            seen.add(key)
            rows.append({**row, 'source': row['audio']})
        return {'history': rows}

    def resume(self, identifier=None, source=None):
        rows = self.library.history()
        if identifier is not None:
            title_id(identifier)
            rows = [r for r in rows if r['title_id'] == identifier]
        if not rows:
            raise ValueError('No observed playback history is available')
        latest = rows[0]
        source = source or latest['audio']
        if latest['episode'] == 'movie':
            if latest['watched']:
                return {'state': 'completed', 'title': latest['title'], 'notice': 'Movie completed. Use movies_play with resume=false to watch again.'}
            season = episode = 0
        else:
            match = re.fullmatch(r'S(\d+)E(\d+)', latest['episode'])
            if not match: raise ValueError('Saved episode identity is invalid')
            season, episode = map(int, match.groups())
            if latest['watched']:
                episodes = self._details(latest['title_id'])['episodes']
                current = {'season': season, 'number': episode}
                if current not in episodes or episodes.index(current) + 1 >= len(episodes):
                    return {'state': 'caught_up', 'title': latest['title'], 'last_episode': latest['episode']}
                following = episodes[episodes.index(current) + 1]
                season, episode = following['season'], following['number']
        return self.play(latest['title_id'], season, episode, source, True)
