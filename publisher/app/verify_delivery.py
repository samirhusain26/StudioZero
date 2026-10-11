"""Verify unauthenticated public media bytes before any social dispatch."""
import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request

from buffer_adapter import PublishError


def verify(url, expected_hash, opener=urllib.request.urlopen):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or not re.fullmatch('[0-9a-f]{64}', expected_hash):
        raise PublishError('media')
    digest = hashlib.sha256()
    total = 0
    try:
        with opener(urllib.request.Request(url, headers={'User-Agent': 'ScalarMediaVerifier/1.0'}), timeout=30) as response:
            redirected = urllib.parse.urlsplit(response.url)
            if redirected.scheme != 'https' or redirected.hostname != parsed.hostname:
                raise PublishError('media')
            if response.headers.get_content_type() not in ('video/mp4', 'application/octet-stream'):
                raise PublishError('media')
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 24_000_000:
                    raise PublishError('media')
                digest.update(chunk)
        if not total or digest.hexdigest() != expected_hash:
            raise PublishError('media')
    except OSError:
        raise PublishError('media') from None
    return {'sha256': expected_hash, 'bytes': total, 'publicDeliveryVerified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('sha256')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.url, args.sha256)))
    except PublishError:
        raise SystemExit('Public media delivery failed verification; no publication attempted.')
