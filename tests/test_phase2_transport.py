from pathlib import Path
import json
import tempfile
import unittest
from urllib.error import URLError

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.here_now_client import HereNowClient, HereNowError, HereNowOutcomeUnknownError
from phase2_support import CONFIG, article, assets
from test_phase2_artifacts import Response


class HereNowTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.receipt = ReleaseBuilder(
            source_assets=assets(root), config=CONFIG, source_commit='synthetic'
        ).build((article(),), root / 'release')
        self.requests = []
        self.active = {}
        self.finalize_fail = False
        self.finalize_url = (
            f'https://here.now/api/v1/publish/{CONFIG.here_now_slug}/finalize'
        )
        self.finalize_response = None
        self.prepared_slug = CONFIG.here_now_slug

    def tearDown(self):
        self.temp.cleanup()

    def opener(self, req, **kwargs):
        self.requests.append(req)
        if req.full_url.startswith('https://storage.example.invalid/'):
            self.assertIsNone(req.get_header('Authorization'))
            return Response(b'', 200)
        if req.method == 'GET':
            return Response(json.dumps(dict(
                manifest=[{'path': p, 'hash': h} for p, h in self.active.items()],
                currentVersionId='v2',
            )).encode())
        if req.method == 'PUT':
            data = json.loads(req.data)
            self.assertFalse(data['spaMode'])
            self.pending = {i['path']: i['hash'] for i in data['files']}
            prepared = dict(upload=dict(
                versionId='v2',
                finalizeUrl=self.finalize_url,
                uploads=[
                    {'path': p, 'url': 'https://storage.example.invalid/' + p}
                    for p in self.pending
                ],
            ))
            if self.prepared_slug is not None:
                prepared['slug'] = self.prepared_slug
            return Response(json.dumps(prepared).encode())
        if req.method == 'POST':
            self.assertEqual(req.full_url, self.finalize_url)
            self.assertEqual(json.loads(req.data), {'versionId': 'v2'})
            self.active = self.pending
            if self.finalize_fail:
                raise URLError('lost finalize response')
            response = self.finalize_response
            if response is None:
                response = dict(
                    success=True,
                    slug=CONFIG.here_now_slug,
                    currentVersionId='v2',
                )
            return Response(json.dumps(response).encode())
        self.fail('unexpected request')

    def test_diff_upload_and_finalize(self):
        result = HereNowClient('synthetic-key', opener=self.opener).publish(
            CONFIG.here_now_slug, self.receipt
        )
        self.assertFalse(result.reconciled)
        self.assertEqual(self.active, self.receipt.checksums)

    def test_equal_manifest_skips_upload(self):
        self.active = dict(self.receipt.checksums)
        result = HereNowClient('synthetic-key', opener=self.opener).publish(
            CONFIG.here_now_slug, self.receipt
        )
        self.assertTrue(result.reconciled)
        self.assertEqual(len(self.requests), 1)

    def test_unknown_finalize_then_observe_not_republish(self):
        client = HereNowClient('synthetic-key', opener=self.opener)
        self.finalize_fail = True
        with self.assertRaises(HereNowOutcomeUnknownError):
            client.publish(CONFIG.here_now_slug, self.receipt)
        before = len(self.requests)
        result = client.reconcile(CONFIG.here_now_slug, self.receipt)
        self.assertTrue(result.reconciled)
        self.assertEqual(len(self.requests), before + 1)

    def test_api_key_not_sent_to_other_origin(self):
        client = HereNowClient('synthetic-key', opener=self.opener)
        with self.assertRaises(HereNowError):
            client._request('POST', 'https://other.invalid/api/finalize', {})
        self.assertEqual(self.requests, [])

    def test_finalize_url_must_match_exact_prepared_site(self):
        unsafe_urls = (
            'https://here.now/api/v1/publish/other-test-site/finalize',
            f'http://here.now/api/v1/publish/{CONFIG.here_now_slug}/finalize',
            f'https://other.invalid/api/v1/publish/{CONFIG.here_now_slug}/finalize',
            f'https://here.now:443/api/v1/publish/{CONFIG.here_now_slug}/finalize',
            f'https://here.now/api/v1/artifact/{CONFIG.here_now_slug}/finalize',
            f'https://here.now/api/v1/publish/{CONFIG.here_now_slug}/finalize?site=other',
            f'https://here.now/api/v1/publish/{CONFIG.here_now_slug}/finalize#other',
            f'https://here.now/api/v1/publish/{CONFIG.here_now_slug}/../other/finalize',
        )
        for url in unsafe_urls:
            with self.subTest(url=url):
                self.requests = []
                self.active = {}
                self.finalize_url = url
                with self.assertRaises(HereNowError):
                    HereNowClient('synthetic-key', opener=self.opener).publish(
                        CONFIG.here_now_slug, self.receipt
                    )
                self.assertFalse(any(req.method == 'POST' for req in self.requests))
                self.assertFalse(any(
                    req.full_url.startswith('https://storage.example.invalid/')
                    for req in self.requests
                ))

    def test_prepare_slug_mismatch_fails_before_upload(self):
        self.prepared_slug = 'other-test-site'
        with self.assertRaises(HereNowError):
            HereNowClient('synthetic-key', opener=self.opener).publish(
                CONFIG.here_now_slug, self.receipt
            )
        self.assertFalse(any(req.method == 'POST' for req in self.requests))
        self.assertFalse(any(
            req.full_url.startswith('https://storage.example.invalid/')
            for req in self.requests
        ))

    def test_finalize_response_site_mismatch_is_unknown(self):
        self.finalize_response = dict(
            success=True,
            slug='other-test-site',
            currentVersionId='v2',
        )
        with self.assertRaises(HereNowOutcomeUnknownError):
            HereNowClient('synthetic-key', opener=self.opener).publish(
                CONFIG.here_now_slug, self.receipt
            )

    def test_finalize_response_version_mismatch_is_unknown(self):
        self.finalize_response = dict(
            success=True,
            slug=CONFIG.here_now_slug,
            currentVersionId='other-version',
        )
        with self.assertRaises(HereNowOutcomeUnknownError):
            HereNowClient('synthetic-key', opener=self.opener).publish(
                CONFIG.here_now_slug, self.receipt
            )

    def test_local_tamper_before_any_network(self):
        (self.receipt.output / 'index.html').write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            HereNowClient('synthetic-key', opener=self.opener).publish(
                CONFIG.here_now_slug, self.receipt
            )
        self.assertEqual(self.requests, [])

    def test_reconcile_missing_manifest_returns_none(self):
        self.assertIsNone(
            HereNowClient('synthetic-key', opener=self.opener).reconcile(
                CONFIG.here_now_slug, self.receipt
            )
        )


if __name__ == '__main__':
    unittest.main()
