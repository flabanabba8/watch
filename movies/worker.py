"""Supervise mpv, saving observed positions. Private transient stream data is removed."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

if __package__:
    from .library import Library
    from .provider import Provider
    from .process_env import process_env
else:
    from library import Library
    from provider import Provider
    from process_env import process_env


def play_once(folder, request, headless=False):
    library = Library(folder.parent)
    session_id = request['id']
    detail = library.session(session_id)['detail']
    stopping = False
    process = None
    position = float(request['start'])
    duration = None
    ended = False
    loaded = False
    state = 'starting'

    def stop(*_):
        nonlocal stopping
        stopping = True
        (folder / 'stop').touch(mode=0o600, exist_ok=True)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def persist():
        if loaded:
            library.update_progress(request['title_id'], request['episode'], request['audio'], position, duration, ended)
        visible_state = 'recovering' if state == 'failed' and request.get('fallback') and not loaded and not (folder / 'stop').exists() else state
        library.session(session_id, request['title_id'], request['episode'], request['audio'], visible_state, detail)

    try:
        with tempfile.TemporaryDirectory(prefix='watch-movies-') as tmp:
            sockpath = str(Path(tmp) / 'mpv.sock')
            playlist = Path(tmp) / 'stream.m3u'
            playlist.write_text(request['stream']['url'] + '\n')
            playlist.chmod(0o600)
            # No user configs, scripts, shell, yt-dlp, or arbitrary IPC commands.
            command = ['mpv', '--no-config', '--load-scripts=no', '--ytdl=no', '--idle=no',
                       '--terminal=no', '--input-terminal=no', '--save-position-on-quit=no',
                       '--network-timeout=15',
                       '--input-ipc-server=' + sockpath, '--start=' + str(position),
                       '--force-media-title=' + request.get('display_title', request['title']),
                       '--referrer=' + request['stream']['referer'], '--playlist=' + str(playlist)]
            headers = request['stream'].get('headers', {})
            if headers.get('User-Agent'):
                command += ['--user-agent=' + headers['User-Agent']]
            if headers.get('Origin'):
                command += ['--http-header-fields=Origin: ' + headers['Origin']]
            if request['stream'].get('subtitle'):
                # Avoid putting a signed subtitle URL in the process command line.
                sub = Path(tmp) / 'sub.conf'
                url = request['stream']['subtitle']
                sub.write_text('sub-file=%' + str(len(url.encode())) + '%' + url + '\n')
                sub.chmod(0o600)
                command += ['--include=' + str(sub)]
            if headless:  # internal integration fixture only; never exposed by a plugin tool
                command += ['--vo=null', '--ao=null']
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=process_env())
            until = time.monotonic() + 12
            while not Path(sockpath).exists():
                if process.poll() is not None or time.monotonic() > until or stopping:
                    raise RuntimeError('Player failed to initialize; check mpv/display availability')
                time.sleep(.05)
            with socket.socket(socket.AF_UNIX) as conn:
                conn.settimeout(.5)
                conn.connect(sockpath)
                for i, prop in enumerate(['time-pos', 'duration', 'pause']):
                    conn.sendall((json.dumps({'command': ['observe_property', i, prop]}) + '\n').encode())
                detail['socket'] = sockpath
                buffer = b''
                started = last_save = time.monotonic()
                quit_sent = False
                while True:
                    if not quit_sent and (stopping or (folder / 'stop').exists() or time.monotonic() - started > 28800):
                        conn.sendall(b'{"command":["quit"]}\n')
                        stopping, quit_sent = True, True
                    try:
                        data = conn.recv(16384)
                    except socket.timeout:
                        data = None
                    if data == b'':
                        break
                    if data:
                        buffer += data
                        if len(buffer) > 1024 * 1024:
                            raise RuntimeError('Player IPC response exceeded limit')
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            event = json.loads(line)
                            if event.get('event') == 'file-loaded':
                                loaded, state = True, 'playing'
                                persist()
                            elif event.get('event') == 'end-file':
                                if event.get('reason') == 'error':
                                    raise RuntimeError('Playback source failed to load or expired; resume resolves a fresh source')
                                ended = event.get('reason') == 'eof'
                            elif event.get('event') == 'property-change' and event.get('data') is not None:
                                if event['name'] == 'time-pos':
                                    position = event['data']
                                    # A very short local file can load before the observer connects.
                                    if not loaded:
                                        loaded, state = True, 'playing'
                                elif event['name'] == 'duration':
                                    duration = event['data']
                                elif event['name'] == 'pause' and loaded:
                                    state = 'paused' if event['data'] else 'playing'
                    if time.monotonic() - last_save >= 1:
                        persist()
                        last_save = time.monotonic()
                    if not loaded and time.monotonic() - started > request.get('load_timeout', 45):
                        raise RuntimeError('Playback source did not become ready within the startup deadline')
                process.wait(timeout=5)
                if (process.returncode or not loaded) and not stopping:
                    raise RuntimeError('Player exited before successful playback')
                state = 'completed' if ended else 'stopped'
                persist()
    except Exception as exc:
        state = 'stopped' if stopping or (folder / 'stop').exists() else 'failed'
        if state == 'failed': detail['error'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        persist()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        detail.pop('socket', None)
        persist()
    return {'state': state, 'loaded': loaded, 'cancelled': stopping or (folder / 'stop').exists()}


def watch(folder, headless=False):
    request_path = folder / 'request.json'
    request = json.loads(request_path.read_text())
    request_path.unlink()
    first = play_once(folder, request, headless)
    fallback = request.get('fallback')
    if first['state'] != 'failed' or first['loaded'] or first['cancelled'] or not fallback:
        return first
    library = Library(folder.parent)
    detail = library.session(request['id'])['detail']
    detail.pop('error', None)
    detail['playback_fallback'] = 'Initial source did not load; trying LookMovie once.'
    library.session(request['id'], request['title_id'], request['episode'], request['audio'], 'starting', detail)
    try:
        stream = Provider(folder.parent, fallback['bridge']).resolve(fallback['title'], fallback['season'], fallback['episode'], 'lookmovie')
        if (folder / 'stop').exists():
            library.session(request['id'], request['title_id'], request['episode'], request['audio'], 'stopped', detail)
            return {'state': 'stopped', 'loaded': False, 'cancelled': True}
        detail.update(source_label=stream['label'], source_reports=stream['sources'])
        library.session(request['id'], request['title_id'], request['episode'], request['audio'], 'starting', detail)
        retry = {k: v for k, v in request.items() if k != 'fallback'}
        return play_once(folder, {**retry, 'stream': stream, 'load_timeout': 30}, headless)
    except Exception as exc:
        if (folder / 'stop').exists():
            library.session(request['id'], request['title_id'], request['episode'], request['audio'], 'stopped', detail)
            return {'state': 'stopped', 'loaded': False, 'cancelled': True}
        detail['error'] = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Alternate source failed to initialize'
        library.session(request['id'], request['title_id'], request['episode'], request['audio'], 'failed', detail)
        return {'state': 'failed', 'loaded': False, 'cancelled': False}


if __name__ == '__main__':
    watch(Path(sys.argv[1]), headless='--fixture-headless' in sys.argv[2:])
