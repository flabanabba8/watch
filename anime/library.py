"""Profile-local title library and observed playback progress; no stream URLs."""
import json
import math
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager


class Library:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'library.db'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS titles(id TEXT PRIMARY KEY, title TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS progress(
              title_id TEXT NOT NULL, episode TEXT NOT NULL, audio TEXT NOT NULL,
              position REAL NOT NULL, duration REAL, watched INTEGER NOT NULL DEFAULT 0,
              updated REAL NOT NULL, PRIMARY KEY(title_id,episode,audio));
            CREATE TABLE IF NOT EXISTS sessions(
              id TEXT PRIMARY KEY, title_id TEXT NOT NULL, episode TEXT NOT NULL, audio TEXT NOT NULL,
              state TEXT NOT NULL, detail TEXT NOT NULL, updated REAL NOT NULL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save_titles(self, titles):
        with self.connect() as db:
            db.executemany('INSERT INTO titles VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,updated=excluded.updated',
                           [(t['id'], t['title'], time.time()) for t in titles])

    def title(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT * FROM titles WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Search and select this title before opening it')
        return dict(row)

    def progress(self, identifier, episode, audio):
        with self.connect() as db:
            row = db.execute('SELECT * FROM progress WHERE title_id=? AND episode=? AND audio=?', (identifier, episode, audio)).fetchone()
        return dict(row) if row else None

    def update_progress(self, identifier, episode, audio, position, duration, ended=False):
        if not isinstance(position, (int, float)) or isinstance(position, bool) or not math.isfinite(position) or position < 0:
            raise ValueError('Player reported invalid position')
        if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0):
            duration = None
        # Seeking near the end alone is not completion; require an observed natural end.
        watched = bool(ended and duration and position >= duration * .9)
        with self.connect() as db:
            db.execute('INSERT INTO progress VALUES(?,?,?,?,?,?,?) ON CONFLICT(title_id,episode,audio) DO UPDATE SET position=excluded.position,duration=excluded.duration,watched=MAX(progress.watched,excluded.watched),updated=excluded.updated',
                       (identifier, episode, audio, position, duration, int(watched), time.time()))

    def session(self, session_id, identifier=None, episode=None, audio=None, state=None, detail=None):
        with self.connect() as db:
            if state is not None:
                db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated=excluded.updated',
                           (session_id, identifier, episode, audio, state, json.dumps(detail or {}), time.time()))
            row = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown playback session')
        result = dict(row)
        result['detail'] = json.loads(result['detail'])
        return result

    def history(self):
        with self.connect() as db:
            rows = db.execute('SELECT p.*,t.title FROM progress p JOIN titles t ON p.title_id=t.id ORDER BY p.updated DESC LIMIT 30').fetchall()
        return [dict(row) for row in rows]
