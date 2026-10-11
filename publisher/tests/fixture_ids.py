"""Fake channel identities for tests: the identities block of publisher/config.example.json (never real IDs)."""
import json
from pathlib import Path

IDENTITIES = json.loads((Path(__file__).resolve().parents[1]/'config.example.json').read_text())['identities']
PAGE, PROFILE = IDENTITIES['facebookPageId'], IDENTITIES['facebookProfileUrl']
DID = IDENTITIES['blueskyDid']
THREADS_USER = IDENTITIES['threadsUserId']
