from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'publisher/app'))
from refresh_instagram import refresh

class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.config = {'channels': {'instagram': {'accountId':'17841400000000001',
            'profileUrl':'https://www.instagram.com/studiozeroflow/', 'identityVerified':True}}}
    def test_refuses_token_under_24_hours(self):
        with self.assertRaises(ValueError): refresh(self.config, 'secret-fixture', 1000, now=1000+86399)
    def test_refresh_validates_same_numeric_direct_identity(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"access_token":"replacement-fixture","expires_in":5184000}'
        class JsonResponse(Response):
            pass
        result = refresh(self.config, 'old-fixture', 0, opener=lambda *a, **k: JsonResponse(),
            profile_request=lambda *a: {'user_id':'17841400000000001','username':'studiozeroflow'}, now=86400)
        self.assertEqual(result, ('replacement-fixture', 5184000))
        with self.assertRaises(ValueError):
            refresh(self.config, 'old-fixture', 0, opener=lambda *a, **k: JsonResponse(),
                profile_request=lambda *a: {'user_id':'buffer-provider-id','username':'studiozeroflow'}, now=86400)

if __name__ == '__main__': unittest.main()
