from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from buffer_adapter import credential_permissions_ok


class PermissionTests(unittest.TestCase):
    def test_systemd_root_acl_credential_is_accepted(self):
        metadata=SimpleNamespace(st_mode=0o100440,st_uid=0,st_gid=0)
        self.assertTrue(credential_permissions_ok(Path('/run/credentials/test.service/BUFFER_API_KEY'),metadata))
        self.assertFalse(credential_permissions_ok(Path('/tmp/BUFFER_API_KEY'),metadata))

    def test_other_readable_or_user_owned_group_credential_rejected(self):
        path=Path('/run/credentials/test.service/BUFFER_API_KEY')
        for mode,uid in ((0o444,0),(0o440,1000),(0o660,0)):
            self.assertFalse(credential_permissions_ok(path,SimpleNamespace(st_mode=mode,st_uid=uid,st_gid=0)))
