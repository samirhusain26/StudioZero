"""The studio catalog (publisher/catalog.json, generated on the Mac by tools/export-catalog.mjs).

Read-only on the Pi: served at GET /api/catalog and the source of the games the UI knows. The file is
committed, so it arrives with the code through the normal update; nothing here writes it.
"""
import hashlib
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent/'catalog.json'
MAX_BYTES = 512_000
VERSION = 1


class CatalogError(Exception):
    pass


def read(path=PATH):
    """(raw bytes, parsed catalog, sha256 hex). Refuses a file over MAX_BYTES or of an unknown shape."""
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError:
        raise CatalogError('catalog missing') from None
    if len(raw) > MAX_BYTES:
        raise CatalogError('catalog too large')
    try:
        catalog = json.loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CatalogError('catalog is not JSON') from None
    if (not isinstance(catalog, dict) or catalog.get('catalogVersion') != VERSION
            or not isinstance(catalog.get('projects'), list) or not isinstance(catalog.get('engines'), list)):
        raise CatalogError('catalog has an unknown shape')
    return raw, catalog, hashlib.sha256(raw).hexdigest()


def games(catalog):
    """Game ids across projects, in catalog order (Scalargame's four today)."""
    out = []
    for project in catalog['projects']:
        for game in project.get('games') or ():
            if isinstance(game, dict) and isinstance(game.get('id'), str) and game['id'] not in out:
                out.append(game['id'])
    return tuple(out)


class Cache:
    """Re-reads the file only when its size or mtime changes (the updater swaps the checkout)."""
    def __init__(self, path=PATH):
        self.path, self.key, self.value = Path(path), None, None

    def get(self):
        try:
            stat = self.path.stat()
        except OSError:
            raise CatalogError('catalog missing') from None
        key = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        if key != self.key:
            self.value, self.key = read(self.path), key
        return self.value
