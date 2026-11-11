"""Structured boundary around ani-cli's pinned, source-only resolver."""
import html
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.parse import quote_plus

from .net import public_url


def title_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,199}', value):
        raise ValueError('Invalid title ID; select an ID returned by anime_search')
    return value


def episode_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?', value):
        raise ValueError('Episode must be a number string, for example "1" or "12.5"')
    return value


class Provider:
    def __init__(self, state_dir=None):
        self.state_dir = Path(state_dir) if state_dir is not None else None

    def call(self, *args):
        if sys.platform != 'linux': raise ValueError('Watch Anime provider requires Linux')
        if self.state_dir is None:
            return self._run(*args)
        import fcntl
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state_dir / 'provider.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another provider request is running; wait for it to finish') from None
            stamp = self.state_dir / 'provider-last-request.txt'
            try:
                elapsed = time.time() - float(stamp.read_text())
            except (OSError, ValueError):
                elapsed = 10
            if 0 <= elapsed < 1:
                time.sleep(1 - elapsed)
            try:
                return self._run(*args)
            finally:
                stamp.write_text(str(time.time()))

    def _run(self, *args):
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR') if key in os.environ}
        # Use the same Python executable as the plugin, without inheriting user Python startup settings.
        env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', os.defpath)
        env.update(LC_ALL='C.UTF-8', PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1')
        process = subprocess.Popen(['sh', str(Path(__file__).parent / 'vendor/provider.sh'), *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=75)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RuntimeError('Anime provider timed out; no automatic retries were made') from None
        if process.returncode:
            error = stderr.decode(errors='replace')
            if 'cloudflare' in error.lower() or 'HTTP 403' in error:
                raise RuntimeError('Provider blocked this request. Try later; no bypass or auto-update was attempted')
            if 'No playable source' in error:
                raise RuntimeError('No playable source for this episode and audio mode')
            status = re.search(r'HTTP (\d{3})', error)
            raise RuntimeError('Anime provider failed' + (' (HTTP ' + status[1] + ')' if status else '') + '; retry later')
        return stdout.decode('utf-8', errors='replace')

    def search(self, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 160 or any(ord(c) < 32 for c in query):
            raise ValueError('Query must contain 1–160 printable characters')
        titles = []
        seen = set()
        for line in self.call('search', quote_plus(query.strip())).splitlines():
            fields = line.split('\t', 1)
            if len(fields) != 2:
                continue
            identifier, name = fields
            title_id(identifier)
            if identifier not in seen:
                titles.append({'id': identifier, 'title': html.unescape(name)[:300]})
                seen.add(identifier)
        return titles[:50]

    def episodes(self, identifier):
        rows = []
        for line in self.call('episodes', title_id(identifier)).splitlines():
            fields = line.split('\t')
            if len(fields) == 2 and fields[0].isdigit():
                rows.append({'id': fields[0], 'number': episode_number(fields[1])})
        if not rows:
            raise RuntimeError('Episode list is unavailable; the provider may have changed')
        return rows

    def resolve(self, identifier, episode, audio='sub', quality='720'):
        title_id(identifier)
        episode_number(episode)
        if audio not in ('sub', 'dub') or quality not in ('best', 'worst', '360', '480', '720', '1080'):
            raise ValueError('Choose sub/dub and best/worst/360/480/720/1080 quality')
        episodes = {e['number']: e['id'] for e in self.episodes(identifier)}
        if episode not in episodes:
            raise ValueError('Episode is not in the current title episode list')
        referer, subtitle, variants = None, None, []
        for line in self.call('resolve', episodes[episode], episode, audio).splitlines():
            if line.startswith('REFERER\t'):
                referer = line.split('\t', 1)[1]
            elif line.startswith('SUBTITLE\t'):
                subtitle = line.split('\t', 1)[1] or None
            else:
                match = re.fullmatch(r'(\d{3,4})p?\s+>(https://\S+)', line)
                if match:
                    variants.append({'height': int(match[1]), 'url': match[2]})
        if not referer or not variants:
            raise RuntimeError('Provider returned no supported HLS variants')
        public_url(referer)
        if subtitle:
            public_url(subtitle)
        variants.sort(key=lambda v: v['height'])
        selected = variants[-1] if quality == 'best' else variants[0] if quality == 'worst' else next(
            (v for v in reversed(variants) if v['height'] <= int(quality)), variants[0])
        public_url(selected['url'])
        return {**selected, 'referer': referer, 'subtitle': subtitle,
                'available_heights': [v['height'] for v in variants],
                'quality_fallback': quality.isdigit() and selected['height'] != int(quality)}
