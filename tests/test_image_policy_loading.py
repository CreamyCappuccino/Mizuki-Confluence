"""Explicit v2 loader, never automatic profile learning or file rewriting."""
from contextlib import redirect_stdout
from dataclasses import asdict
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from confluence_release.cli import main
from confluence_release.html_policy import load_html_policy
from confluence_pressroom.here_now_image_html import HereNowImageHtmlPolicy
from image_html_test_support import image_policy
from phase2_support import CONFIG


class ImagePolicyLoadingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.file = self.root/'v2.json'
        self.values = asdict(image_policy())
        self.file.write_text(json.dumps(self.values)); self.file.chmod(0o600)
        self.config = self.root/'release.json'
        self.config.write_text(json.dumps(dict(site_base=CONFIG.site_base,
            here_now_slug=CONFIG.here_now_slug, nor_base=CONFIG.nor_base,
            project_root='/synthetic/project/runtime/source', release_root='/synthetic/project/releases')))

    def test_explicit_v2_roundtrip_type_and_hash(self):
        p = load_html_policy(self.file)
        self.assertIsInstance(p, HereNowImageHtmlPolicy)
        self.assertEqual(p, image_policy())

    def test_every_v2_required_field_missing_is_rejected(self):
        for name in ('format','image_url','image_width','image_height','expected_manifest_sha256'):
            data = dict(self.values); del data[name]; self.file.write_text(json.dumps(data))
            with self.subTest(name=name), self.assertRaises(ValueError): load_html_policy(self.file)

    def test_unknown_duplicate_format_type_and_cross_version_fields_rejected(self):
        raws = [json.dumps(dict(self.values, extra='ignored?')),
                json.dumps(dict(self.values, tag_order=[])),
                json.dumps(self.values)[:-1]+',"image_width":1}',
                json.dumps(dict(self.values, format='here-now-og/v1')),
                json.dumps(dict(self.values, format='here-now-og/v3')),
                json.dumps(dict(self.values, format=[])), '[]', 'null']
        for raw in raws:
            self.file.write_text(raw)
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError): load_html_policy(self.file)

    def test_owner_size_mode_and_nofollow_guards_stay_active(self):
        self.file.chmod(0o644)
        with self.assertRaises(ValueError): load_html_policy(self.file)
        self.file.chmod(0o600)
        with patch('confluence_release.html_policy.os.getuid', return_value=os.getuid()+1):
            with self.assertRaises(ValueError): load_html_policy(self.file)
        link = self.root/'link'; link.symlink_to(self.file)
        with self.assertRaises(OSError): load_html_policy(link)
        self.file.write_bytes(b' ' * 16385)
        with self.assertRaises(ValueError): load_html_policy(self.file)

    def test_loaded_snapshot_does_not_change_with_file(self):
        p = load_html_policy(self.file)
        self.file.write_text(json.dumps(dict(self.values, image_width=1)))
        self.assertEqual(p, image_policy())
        self.assertNotEqual(p.sha256, load_html_policy(self.file).sha256)

    def test_cli_plan_stays_offline_and_reports_distinct_hash(self):
        out = StringIO()
        with patch('confluence_release.cli._worker', side_effect=AssertionError('no worker')), redirect_stdout(out):
            status = main(['--config',str(self.config),'--html-policy',str(self.file),'plan'])
        self.assertEqual(status,0); self.assertIn('here-now-og/v2',out.getvalue())
        self.assertIn(image_policy().sha256,out.getvalue())

    def test_cli_requires_exact_job_and_does_not_allow_retry_or_init(self):
        for args in (['run'], ['retry','JOB9999'], ['init-projection']):
            with patch('confluence_release.cli._worker', side_effect=AssertionError), redirect_stdout(StringIO()):
                status=main(['--config',str(self.config),'--html-policy',str(self.file),*args])
            self.assertEqual(status,1)
