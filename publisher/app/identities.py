"""Pinned identities of the live channels.

The repo is public, so the account and channel IDs live only on the Pi: under "identities" in the root-owned
/etc/scalar-social/config.json (shape in publisher/config.example.json). Adapters and one-off test tools compare
what a platform or Buffer reports with these pins and refuse on any mismatch. A missing or malformed pin refuses
too (fail closed); nothing falls back to a value from a platform report.
"""
import re

PINS = {
    'bufferX': r'[0-9a-f]{24}',             # Buffer channel ids (configure_paused, first_post)
    'bufferInstagram': r'[0-9a-f]{24}',
    'bufferYoutube': r'[0-9a-f]{24}',
    'xUserId': r'[0-9]{1,20}',              # provider ids Buffer reports for those channels
    'youtubeChannelId': r'UC[A-Za-z0-9_-]{22}',
    'facebookPageId': r'[0-9]{5,20}',
    'facebookProfileUrl': r'https://www\.facebook\.com/[A-Za-z0-9./?=_-]+',
    'threadsUserId': r'[0-9]{5,20}',
    'blueskyDid': r'did:plc:[a-z2-7]{24}',
}


class IdentityMissing(ValueError):
    """A pin is absent or malformed in the Pi config."""


def pin(config, name):
    value = (config.get('identities') or {}).get(name)
    if not isinstance(value, str) or not re.fullmatch(PINS[name], value):
        raise IdentityMissing(f'identities.{name} missing or malformed in the Pi config')
    return value


def expected_buffer(config):
    """{platform: (Buffer service, Buffer channel id, provider id or None)} for the Buffer-routed channels."""
    return {
        'x': ('twitter', pin(config, 'bufferX'), pin(config, 'xUserId')),
        'instagram': ('instagram', pin(config, 'bufferInstagram'), None),
        'youtube': ('youtube', pin(config, 'bufferYoutube'), pin(config, 'youtubeChannelId')),
    }
