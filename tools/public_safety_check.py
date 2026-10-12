#!/usr/bin/env python3
"""Public-safety check for this public repository (docs/PUBLIC_SAFETY.md). Stdlib only.

Scans every tracked file plus untracked files that are not ignored (what `git add -A` would publish) and fails on:
credentials and tokens, private keys, forbidden files (env files, credentials, Pi config, render output), Tailscale
host names, IP addresses, e-mail addresses, home-directory paths, platform account IDs, media without a recorded
licence, and (when a private hash list exists) any token whose hash is listed there. Findings print masked: path,
line, rule and the first characters only, never a full value.

    python3 tools/public_safety_check.py                 # before every commit/push; exit 1 on any finding
    python3 tools/public_safety_check.py --private-hashes ~/.config/studiozero/private-id-hashes.txt

The private hash list (outside the repo) holds sha256(value)[:16] per line for values that must never be
published (real account IDs, the Pi's tailnet host); STUDIOZERO_PRIVATE_HASHES names it too.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HASHES = Path.home()/'.config/studiozero/private-id-hashes.txt'

FORBIDDEN_PATHS = [
    (r'(^|/)\.env(\.(?!template$|example$)[^/]*)?$', 'env file'),
    (r'(^|/)env\.ya?ml$', 'env file'),
    (r'(^|/)assets/creds/', 'credentials folder'),
    (r'(^|/)(credentials|token|client_secret[^/]*|service[-_]account[^/]*)\.json$', 'credential file'),
    (r'^publisher/config\.json$', 'Pi config'),
    (r'(^|/)(deploy_key|id_(rsa|ed25519|ecdsa))(\.pub)?$|\.(pem|p12|key)$', 'key file'),
    (r'(^|/)settings\.local\.json$', 'local agent settings'),
    (r'(^|/)out/|(^|/)output/|(^|/)\.audio-work/', 'render or scratch output'),
    (r'\.(sqlite3?|db)$', 'database'),
]
MEDIA = re.compile(r'\.(mp4|mov|mkv|webm|mp3|wav|m4a|aac|ogg|oga|flac|png|jpe?g|gif|webp|psd)$', re.I)
# Media that may be tracked: path prefix -> how its licence is recorded.
MEDIA_ALLOWED = {
    'engines/motion/public/sfx/': 'procedural (tools/make_sfx.py)',
    'engines/motion/public/episodes/music/': 'beds.json',
    'publisher/profile-assets/': 'own brand artwork',
}
FREE_LICENSES = {'CC0-1.0', 'CC-BY-4.0', 'CC-BY-3.0', 'public-domain'}

FAKE = r'(?:a{24}|a0{20,}[0-9a-f]{1,3}|10{11,}[0-9]{1,3}|270{11,}[0-9]{1,3}|UCA{22}|did:plc:a{24})'
CONTENT = [
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'private key'),
    (r'AIza[0-9A-Za-z_-]{35}', 'Google API key'),
    (r'GOCSPX-[0-9A-Za-z_-]{20,}', 'Google OAuth secret'),
    (r'\bya29\.[0-9A-Za-z_-]{20,}', 'Google access token'),
    (r'\b1//0[0-9A-Za-z_-]{30,}', 'Google refresh token'),
    (r'[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com', 'service account'),
    (r'\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}', 'API secret key'),
    (r'\b(?:gsk|hf|r8)_[A-Za-z0-9]{20,}', 'API token'),
    (r'\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}', 'GitHub token'),
    (r'\bxox[bpoasr]-[A-Za-z0-9-]{10,}', 'Slack token'),
    (r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b', 'AWS key'),
    (r'\bEAA[A-Za-z0-9]{30,}', 'Meta token'),
    (r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', 'JWT'),
    (r'"private_key"\s*:\s*"-----BEGIN', 'service account key'),
    (r'\b[a-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net\b', 'Tailscale host name'),
    # 100.64.0.0/10: the RFC 6598 shared range (Tailscale's tailnet addresses) as a network, never a host address.
    (r'(?<![\d.])(?!127\.0\.0\.1\b|0\.0\.0\.0\b|255\.255\.255\.255\b|100\.64\.0\.0/10\b)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])', 'IP address'),
    # remotion.dev: Remotion's public support address inside its library code (the Studio's export bundle).
    (r'(?<![:/\w.%+-])[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net)\b|anthropic\.com\b|users\.noreply\.github\.com\b|github\.com\b|remotion\.dev\b)'
     r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|io|co|dev|app|me|uk|de|in|us|ai)\b', 'e-mail address'),
    (r'/Users/[A-Za-z0-9._-]+', 'Mac home path'),
    # web_user: Emscripten's virtual file system home inside WebAssembly glue code (a vendor encoder), not a real user.
    (r'/home/(?!scout\b|web_user\b)[a-z_][a-z0-9_-]*', 'home path'),
    (r'(?<![0-9a-zA-Z])(?!' + FAKE + r')[0-9a-f]{24}(?![0-9a-zA-Z])', 'Buffer/Mongo-style ID'),
    (r'(?<![A-Za-z0-9_-])(?!' + FAKE + r')UC[A-Za-z0-9_-]{22}(?![A-Za-z0-9_-])', 'YouTube channel ID'),
    (r'did:plc:(?!a{24})[a-z2-7]{24}', 'Bluesky DID'),
    (r'(?<![0-9a-zA-Z.])(?!' + FAKE + r')[0-9]{15,20}(?![0-9a-zA-Z.])', 'long numeric account ID'),
]
# Rules that do not apply to a path (value: rule names), each with its reason.
EXCEPTIONS = [
    (r'^library/_sources/', {'long numeric account ID', 'IP address', 'Buffer/Mongo-style ID'}),   # frozen game data
    (r'(^|/)(beds|catalog)\.json$|^engines/motion/music/|^engines/motion/music/', {'long numeric account ID', 'IP address'}),  # audio measurements
    (r'(^|/)package-lock\.json$|^publisher/pi-package-lock\.json$', {'Buffer/Mongo-style ID', 'long numeric account ID', 'IP address'}),
    (r'^publisher/app/static/', {'Buffer/Mongo-style ID', 'long numeric account ID', 'IP address'}),  # minified bundle
    (r'^publisher/tests/', {'IP address', 'long numeric account ID'}),   # fixtures (100.64.x tailnet ranges, fake IDs)
    (r'^library/[^/_][^/]*/batch\.json$', {'long numeric account ID'}),
    (r'^tools/public_safety_check\.py$', {r for _, r in CONTENT}),       # this file names the patterns
]


def tracked():
    out = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                         capture_output=True, check=True).stdout
    return sorted({p for p in out.decode().split('\0') if p and (ROOT/p).is_file()})


def mask(value):
    return f'{value[:4]}…({len(value)})'


def bed_licences():
    licences = {}
    for beds in ROOT.glob('*/public/episodes/music/beds.json'), ROOT.glob('engines/*/public/episodes/music/beds.json'):
        for path in beds:
            data = json.loads(path.read_text())
            for entry in (data.values() if isinstance(data, dict) else data):
                if isinstance(entry, dict) and entry.get('file'):
                    licences[str(path.parent.parent.parent.relative_to(ROOT)/entry['file'])] = entry.get('license')
    return licences


def check(private_hashes):
    findings = []
    files = tracked()
    licences = None
    for rel in files:
        for pattern, rule in FORBIDDEN_PATHS:
            if re.search(pattern, rel):
                findings.append((rel, 0, rule, '(file)'))
        if MEDIA.search(rel):
            prefix = next((p for p in MEDIA_ALLOWED if rel.startswith(p)), None)
            if prefix is None:
                findings.append((rel, 0, 'media outside the licensed asset folders', '(file)'))
            elif MEDIA_ALLOWED[prefix] == 'beds.json':
                licences = bed_licences() if licences is None else licences
                if licences.get(rel) not in FREE_LICENSES:
                    findings.append((rel, 0, f'music bed without a free licence in beds.json ({licences.get(rel)})', '(file)'))
            continue
        data = (ROOT/rel).read_bytes()
        if b'\0' in data[:8192]:
            continue
        text = data.decode('utf-8', errors='replace')
        skip = set().union(*(rules for pattern, rules in EXCEPTIONS if re.search(pattern, rel)))
        for number, line in enumerate(text.splitlines(), 1):
            for pattern, rule in CONTENT:
                if rule in skip:
                    continue
                for match in re.finditer(pattern, line):
                    findings.append((rel, number, rule, mask(match.group(0))))
            if private_hashes:
                for token in set(re.findall(r'[A-Za-z0-9:._/-]{6,}', line)):
                    for part in {token, *re.split(r'[/:]', token)}:
                        if len(part) >= 6 and hashlib.sha256(part.encode()).hexdigest()[:16] in private_hashes:
                            findings.append((rel, number, 'value on the private list', mask(part)))
    return files, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--private-hashes', type=Path, default=Path(os.environ.get('STUDIOZERO_PRIVATE_HASHES', DEFAULT_HASHES)))
    args = parser.parse_args(argv)
    hashes = set(args.private_hashes.read_text().split()) if args.private_hashes.is_file() else set()
    files, findings = check(hashes)
    for rel, line, rule, value in sorted(set(findings)):
        print(f'{rel}:{line}: {rule}: {value}')
    print(f'{len(files)} files checked, {len(set(findings))} findings'
          f"{'' if hashes else ' (no private hash list: real IDs are only caught by their shape)'}.")
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
