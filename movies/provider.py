"""JSON-only adapter for AniDroid's pinned Luffy bridge. No interactive CLI menus."""
import json
import hashlib
try:
    import fcntl
except ImportError:
    fcntl = None
import stat
import sys
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

if __package__:
    from .net import public_url
    from .process_env import process_env
else:
    from net import public_url
    from process_env import process_env


def title_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'(movie|tv)-[0-9]{1,12}', value):
        raise ValueError('Choose an exact movie/TV ID returned by movies_search')
    return value


def integer(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer between {low} and {high}')
    return value


def open_trusted_bridge(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Configure the trusted bridge SHA-256 printed by the build in Hermes settings')
    if sys.platform != 'linux' or not all(hasattr(os, name) for name in ('memfd_create', 'MFD_CLOEXEC', 'MFD_ALLOW_SEALING')):
        raise RuntimeError('Linux sealed executable support is required before sending a metadata key')
    source = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    sealed = None
    try:
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 128 * 1024**2:
            raise ValueError('Bridge must be a regular file no larger than 128 MiB')
        sealed = os.memfd_create('watch-movies-bridge', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(source, 1024 * 1024)
            if not chunk: break
            total += len(chunk)
            if total > 128 * 1024**2: raise ValueError('Bridge exceeds 128 MiB')
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(sealed, view)
                if written <= 0: raise RuntimeError('Could not prepare the trusted bridge')
                view = view[written:]
        after = os.fstat(source)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or digest.hexdigest() != expected_sha256:
            raise ValueError('Bridge does not match the configured trusted SHA-256')
        os.fchmod(sealed, 0o500)
        # Linux UAPI values remain stable; some Python builds omit these names.
        add_seals = getattr(fcntl, 'F_ADD_SEALS', 1033)
        get_seals = getattr(fcntl, 'F_GET_SEALS', 1034)
        seals = 0x0001 | 0x0002 | 0x0004 | 0x0008
        fcntl.fcntl(sealed, add_seals, seals)
        if fcntl.fcntl(sealed, get_seals) & seals != seals:
            raise RuntimeError('Could not seal the trusted bridge')
        os.lseek(sealed, 0, os.SEEK_SET)
        return sealed
    except BaseException:
        if sealed is not None: os.close(sealed)
        raise
    finally:
        os.close(source)


class Provider:
    def __init__(self, root, bridge='ani-luffy-bridge', bridge_sha256=''):
        self.root, self.bridge, self.bridge_sha256 = Path(root), bridge, bridge_sha256

    def call(self, request):
        if sys.platform != 'linux' or fcntl is None: raise ValueError('Watch Movies provider requires Linux sealed executable support')
        request = dict(request)
        metadata = request.get('action') in ('search', 'browse', 'details', 'genres')
        executable = shutil.which(self.bridge)
        if not executable:
            raise ValueError('Install ani-luffy-bridge from the bundled native source instructions, or configure its executable path')
        with (self.root / 'provider.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another movie provider request is running; wait for it to finish') from None
            stamp = self.root / 'provider-last-request.txt'
            try: elapsed = time.time() - float(stamp.read_text())
            except (OSError, ValueError): elapsed = 10
            if 0 <= elapsed < 1: time.sleep(1 - elapsed)
            fd = None
            try:
                if metadata:
                    fd = open_trusted_bridge(executable, self.bridge_sha256)
                    from agent.secret_scope import get_secret
                    key = get_secret('TMDB_API_KEY') or ''
                    if key:  # optional override; without it the bridge keeps Luffy's own built-in metadata key
                        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}', key):
                            raise ValueError('The optional TMDB API v3 key in Hermes Settings is not valid; clear it or enter a v3 key')
                        request['tmdb_key'] = key
                command = [sys.executable, '-I', str(Path(__file__).with_name('bridge_exec.py')), str(fd)] if fd is not None else [executable]
                options = {'pass_fds': (fd,)} if fd is not None else {}
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, start_new_session=True, env=process_env(), **options)
            finally:
                if fd is not None: os.close(fd)
            try:
                stdout, _ = process.communicate(json.dumps(request).encode(), timeout=65)
                if len(stdout) > 4 * 1024 * 1024:
                    raise RuntimeError('Movie bridge response exceeded4 MiB')
                try: result = json.loads(stdout)
                except ValueError: raise RuntimeError('Movie bridge returned an invalid response') from None
                if process.returncode or not isinstance(result, dict) or result.get('error'):
                    if isinstance(result, dict) and result.get('error') == 'metadata returned HTTP 401':
                        raise RuntimeError('TMDB authentication failed; check your configured API v3 key. No automatic retry was made')
                    if isinstance(result, dict) and result.get('error') == 'Configure a TMDB API v3 key in Hermes settings':
                        raise ValueError('This bridge build has no built-in TMDB key. Add your own TMDB API v3 key in the Watch Movies plugin settings, or configure a bridge build that includes one. No automatic retry was made')
                    raise RuntimeError('Movie source unavailable for this request. Try later or select another source; no automatic retry was made')
                return result
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.communicate()
                raise RuntimeError('Movie provider timed out; no automatic retry was made') from None
            finally:
                stamp.write_text(str(time.time()))

    def search(self, query, page=1, kind='all'):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 160 or any(ord(c) < 32 for c in query):
            raise ValueError('Query must contain1–160 printable characters')
        integer(page, 1, 500, 'page')
        if kind not in ('all', 'movie', 'tv'): raise ValueError('Choose all, movie or tv')
        result = self.call({'action': 'search', 'query': query, 'page': page})
        items = []
        for t in result.get('items', []):
            identifier = title_id(t['id'])
            series = identifier.startswith('tv-')
            if kind != 'all' and (kind == 'tv') != series: continue
            name = str(t['name'])[:300]
            year_match = re.search(r'\b(?:18|19|20)\d{2}\b', str(t.get('info', '')))
            year = year_match[0] if year_match else ''
            items.append({'id': identifier, 'name': name, 'title': name + (f' ({year})' if year else ''),
                          'year': year, 'kind': 'tv' if series else 'movie'})
        return {'items': items[:50], 'has_more': bool(result.get('hasMore')), 'page': page}

    def details(self, identifier):
        result = self.call({'action': 'details', 'id': title_id(identifier)})
        episodes = []
        for row in result.get('episodes', []):
            season = integer(row['season'], 0, 1000, 'season')
            number = integer(int(row['number']), 0, 10000, 'episode')
            episodes.append({'season': season, 'number': number})
        if not episodes:
            raise RuntimeError('No episode/movie metadata is currently available')
        return {'description': str(result.get('description', ''))[:2500], 'episodes': episodes}

    def resolve(self, title, season, episode, source='auto'):
        if source not in ('auto', 'cinejoy', 'vixsrc', 'lookmovie'):
            raise ValueError('Choose auto, cinejoy, vixsrc or lookmovie')
        result = self.call({'action': 'streams', 'id': title['id'], 'title': title['name'], 'year': title['year'],
                            'season': season, 'episode': episode, 'source': source})
        streams = result.get('streams', [])
        if not streams: raise RuntimeError('No movie stream was returned')
        stream = streams[0]
        public_url(stream['url'])
        headers = stream.get('headers', {})
        if not isinstance(headers, dict) or any(k not in ('Referer', 'Origin', 'User-Agent') for k in headers):
            raise RuntimeError('Unsupported movie stream headers')
        for name, value in headers.items():
            if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
                raise RuntimeError('Invalid movie stream header')
            if name in ('Referer', 'Origin'): public_url(value)
        subtitles = stream.get('captions', [])
        subtitle = subtitles[0]['url'] if subtitles else None
        if subtitle: public_url(subtitle)
        reports = [re.sub(r'https?://\S+', '[provider URL]', str(x))[:180] for x in stream.get('sources', [])[:5]]
        return {'url': stream['url'], 'referer': headers.get('Referer', ''), 'headers': headers,
                'subtitle': subtitle, 'label': str(stream.get('label', 'Auto'))[:120], 'sources': reports,
                'resolved_source': 'lookmovie' if 'lookmovie' in str(stream.get('label', '')).lower() else 'vixsrc' if 'vixsrc' in str(stream.get('label', '')).lower() else 'cinejoy',
                'height': 0, 'quality_fallback': False, 'master_playlist_preserved': True}
