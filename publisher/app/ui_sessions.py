"""Persistent opaque browser sessions for the private UI (stdlib only)."""
import hashlib
import hmac
import os
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3

TTL_SECONDS = 90 * 24 * 60 * 60
MAX_SESSIONS = 32


class Sessions:
    def __init__(self, state: Path, clock):
        self.path = Path(state) / 'ui-sessions.sqlite3'
        self.clock = clock

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        db = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires INTEGER NOT NULL, binding TEXT NOT NULL)')
        return db

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _binding(token, passcode):
        return hmac.new(token.encode(), passcode.encode(), hashlib.sha256).hexdigest()

    def create(self, passcode):
        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        with closing(self._db()) as db, db:
            db.execute('DELETE FROM sessions WHERE expires <= ?', (int(self.clock()),))
            db.execute('DELETE FROM sessions WHERE digest IN (SELECT digest FROM sessions ORDER BY expires DESC LIMIT -1 OFFSET ?)', (MAX_SESSIONS - 1,))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest, int(self.clock()) + TTL_SECONDS, self._binding(token, passcode)))
        return token

    def valid(self, token, passcode):
        if not isinstance(token, str) or len(token) != 43 or not token.isascii() or not token.replace('-', '').replace('_', '').isalnum():
            return False
        with closing(self._db()) as db, db:
            row = db.execute('SELECT expires,binding FROM sessions WHERE digest=?', (self._digest(token),)).fetchone()
            if not row:
                return False
            if row[0] <= self.clock() or not hmac.compare_digest(row[1], self._binding(token, passcode or '')):
                db.execute('DELETE FROM sessions WHERE digest=?', (self._digest(token),))
                return False
            return True

    def revoke(self, token):
        if not isinstance(token, str) or len(token) != 43 or not token.isascii() or not token.replace('-', '').replace('_', '').isalnum():
            return
        with closing(self._db()) as db, db:
            db.execute('DELETE FROM sessions WHERE digest=?', (self._digest(token),))
