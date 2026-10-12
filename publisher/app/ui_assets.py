"""Motion assets for the Studio's in-browser preview and export (docs/STUDIO_PLAN.md §1 decision 8).

The Pi serves the files listed in publisher/motion-assets.json (fonts, live music beds, SFX; generated on the Mac by
tools/export-motion-assets.mjs and committed) from its checkout's engines/motion/public. The manifest is the
allowlist and the cache key: URLs carry its version, so a response can be cached as immutable, and the ETag is the
file's sha256 from the manifest. Files stream in chunks with Range support (ui_server.Raw); nothing is buffered.
"""
import hashlib
import json
from pathlib import Path
import re

APP_DIR = Path(__file__).resolve().parent
MANIFEST = APP_DIR.parent/'motion-assets.json'
REPO = APP_DIR.parents[1]
MAX_MANIFEST_BYTES = 256_000
MAX_FILE_BYTES = 30_000_000
PATH = re.compile(r'(episodes/fonts/[a-z0-9-]+\.woff2|episodes/music/[a-z0-9-]+\.m4a|sfx/[a-z0-9]+\.wav)')
TYPES = {'.woff2': 'font/woff2', '.m4a': 'audio/mp4', '.wav': 'audio/wav'}


class AssetError(Exception):
    pass


def parse(raw):
    """(version, files) from manifest bytes; refuses anything outside the expected shape."""
    if len(raw) > MAX_MANIFEST_BYTES:
        raise AssetError('manifest too large')
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise AssetError('manifest is not JSON') from None
    if not isinstance(doc, dict) or doc.get('motionAssetsVersion') != 1 or doc.get('root') != 'engines/motion/public' \
            or not isinstance(doc.get('files'), dict):
        raise AssetError('manifest has an unknown shape')
    files = {}
    for path, entry in doc['files'].items():
        if not (isinstance(path, str) and PATH.fullmatch(path) and isinstance(entry, dict)
                and isinstance(entry.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])
                and isinstance(entry.get('bytes'), int) and not isinstance(entry['bytes'], bool)
                and 0 < entry['bytes'] <= MAX_FILE_BYTES):
            raise AssetError('manifest entry is invalid')
        files[path] = {'sha256': entry['sha256'], 'bytes': entry['bytes']}
    return hashlib.sha256(raw).hexdigest()[:16], files


class Assets:
    """The manifest, re-read when it changes on disk (an update swaps the checkout), and file lookup."""
    def __init__(self, manifest=MANIFEST, repo=REPO):
        self.manifest, self.root = Path(manifest), Path(repo)/'engines/motion/public'
        self.key, self.value = None, None

    def current(self):
        try:
            stat = self.manifest.stat()
            key = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if key != self.key:
                with open(self.manifest, 'rb') as handle:
                    raw = handle.read(MAX_MANIFEST_BYTES + 1)
                self.value, self.key = parse(raw), key
        except OSError:
            raise AssetError('manifest missing') from None
        return self.value

    def lookup(self, version, path):
        """(file path, size, content type, sha256) for an allowlisted asset of the current version, else None."""
        current, files = self.current()
        entry = files.get(path)
        if version != current or entry is None:
            return None
        root = self.root.resolve()
        candidate = (root/path).resolve()
        # No symlink may lead outside public/, and the file must be the size the manifest records.
        if not candidate.is_relative_to(root) or not candidate.is_file():
            return None
        size = candidate.stat().st_size
        if size != entry['bytes']:
            raise AssetError('asset differs from the manifest')
        return candidate, size, TYPES[candidate.suffix], entry['sha256']
