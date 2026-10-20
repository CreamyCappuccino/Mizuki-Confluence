"""Actual client version preconditions over an explicit synthetic HTTP transport."""
import json
import unittest

from confluence_release.here_now_client import HereNowClient, HereNowError
from phase2_support import CONFIG
import test_phase2_transport as fixture


class PresentationTransportTests(unittest.TestCase):
    setUp = fixture.HereNowTransportTests.setUp
    tearDown = fixture.HereNowTransportTests.tearDown
    opener = fixture.HereNowTransportTests.opener

    def test_expected_version_is_sent_at_prepare_not_as_a_new_finalize_contract(self):
        client = HereNowClient('synthetic-key', opener=self.opener)
        client.publish(CONFIG.here_now_slug, self.receipt, base_version_id='v2')
        prepares = [req for req in self.requests if req.method == 'PUT'
                    and req.full_url.startswith('https://here.now/')]
        self.assertEqual(len(prepares), 1)
        self.assertEqual(json.loads(prepares[0].data)['baseVersionId'], 'v2')
        finalizes = [req for req in self.requests if req.method == 'POST']
        self.assertEqual(json.loads(finalizes[0].data), {'versionId': 'v2'})

    def test_stale_base_rejects_before_prepare_or_upload(self):
        client = HereNowClient('synthetic-key', opener=self.opener)
        with self.assertRaises(HereNowError):
            client.publish(CONFIG.here_now_slug, self.receipt, base_version_id='stale')
        self.assertEqual([req.method for req in self.requests], ['GET'])

    def test_ordinary_jobs_keep_the_existing_optional_precondition_default(self):
        client = HereNowClient('synthetic-key', opener=self.opener)
        client.publish(CONFIG.here_now_slug, self.receipt)
        prepares = [req for req in self.requests if req.method == 'PUT'
                    and req.full_url.startswith('https://here.now/')]
        self.assertNotIn('baseVersionId', json.loads(prepares[0].data))


if __name__ == '__main__':
    unittest.main()
