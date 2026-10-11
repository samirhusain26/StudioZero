"""Read-only Buffer identities/scopes; private systemd credential, bounded calls."""
import json
from pathlib import Path
import sys
import time
from buffer_adapter import request, secret, PublishError
from runner import Ledger

CHANNEL_QUERY = 'query($input:ChannelsInput!){channels(input:$input){id name service serviceId externalLink descriptor type allowedActions isDisconnected isLocked isQueuePaused scopes}}'


def inspect(config, ledger, token, transport=request):
    def call(query, variables):
        ledger.consume_call(time.time())
        return transport(query, variables, token)
    organization = config.get('bufferOrganizationId')
    organizations = []
    if not organization:
        organizations = call('{account{organizations{id name}}}', {})['account']['organizations']
        if len(organizations) != 1:
            return {'organizations': organizations, 'requiresOrganizationChoice': True, 'publicationEnabled': False}
        organization = organizations[0]['id']
    channels = call(CHANNEL_QUERY, {'input': {'organizationId': organization}})['channels']
    return {'organizationId': organization, 'channels': channels, 'publicationEnabled': False,
            'warning': 'Connection metadata does not prove public publishing; empty scopes are untracked, not verified permissions.'}


if __name__ == '__main__':
    ledger = None
    try:
        config = json.loads(Path(sys.argv[1]).read_text())
        ledger = Ledger(Path(sys.argv[2] if len(sys.argv)>2 else '/var/lib/scalar-social')/'ledger.sqlite3')
        print(json.dumps(inspect(config, ledger, secret()), indent=2))
    except Exception as error:
        category = error.category if isinstance(error, PublishError) else type(error).__name__
        print('Read-only Buffer verification failed; category: '+category+'. No response body or credential logged.', file=sys.stderr)
        sys.exit(1)
    finally:
        if ledger:
            ledger.db.close()
