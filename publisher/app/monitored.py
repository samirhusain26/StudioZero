"""Optional Healthchecks heartbeat. Only fixed categories, platform names and counts are transmitted."""
import os
from pathlib import Path
import re
import sys
import urllib.request
import runner


def alert_text(code, issues=(), attention=None, missed=0):
    """Ping body shown in the Healthchecks email: which check failed and where, never response text."""
    lines = ['scalar-social: failure' if code else 'scalar-social: healthy']
    if issues:
        lines.append('issues: '+', '.join(sorted(issues)))
    for platform, statuses in sorted((attention or {}).items()):
        lines.append(f'{platform}: '+', '.join(statuses))
    if missed:
        lines.append(f'missed slots in the last 24 h: {missed}')
    if code and len(lines) == 1:
        lines.append('see the Pi UI Health page')
    return '\n'.join(lines)[:2000]


def ping(code, body=None):
    directory=os.environ.get('CREDENTIALS_DIRECTORY')
    path=Path(directory or '/nonexistent')/'HEALTHCHECKS_PING_URL'
    if not path.exists():return False
    url=path.read_text().strip()
    if not re.fullmatch(r'https://hc-ping\.com/[0-9a-f-]{36}',url):return False
    try:
        req=urllib.request.Request(url+('/fail' if code else ''),data=(body or alert_text(code)).encode(),method='POST')
        with urllib.request.urlopen(req,timeout=10) as response:response.read(64)
        return True
    except OSError:
        # Missing external heartbeat will itself produce the configured outage alert.
        return False


if __name__=='__main__':
    code=0
    try: runner.main()
    except SystemExit as error: code=int(error.code or 0)
    except Exception:
        print('Scalar social stopped; configuration, storage or runtime check failed.',file=sys.stderr)
        code=1
    report=runner.LAST_REPORT
    issues=(['content_exhausted'] if report.get('contentExhausted') else [])+(['runner_stopped'] if code==1 else [])
    ping(code,alert_text(code,issues,report.get('attention'),report.get('missedLast24h',0)))
    sys.exit(code)
