"""Offline contract/fixture checks, not a PUB/APR/JOB integration test."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from contract_html_policy import ContractError, validate_fixture_html
from validate_confluence_contract import load_fixture, payload_sha256, validate_payload

FIXTURE = ROOT / "tests/fixtures/confluence/publication_v1.json"
HASH = "dbf725ea30e225a9c24abfedb66525b5598e8f106e6d54e8554e89511af6c21a"


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture(FIXTURE)
        self.payload = deepcopy(self.fixture["payload_snapshot"])
        self.base = self.fixture["site_base_url"]

    def check(self, payload):
        validate_payload(payload, site_base_url=self.base)

    def test_golden_fixture_and_hash(self):
        self.check(self.payload)
        self.assertEqual(self.fixture["expected_payload_sha256"], HASH)
        self.assertEqual(payload_sha256(self.payload), HASH)

    def test_repeated_validation_never_changes_candidate(self):
        before = deepcopy(self.payload)
        for _ in range(3):
            self.check(self.payload)
            self.assertEqual(payload_sha256(self.payload), HASH)
        self.assertEqual(self.payload, before)
        self.assertNotIn("state", self.payload)

    def test_canonical_encoding_agrees_with_pressroom_choices(self):
        reversed_keys = dict(reversed(list(self.payload.items())))
        self.assertEqual(payload_sha256(reversed_keys), HASH)
        raw = json.dumps(self.payload, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), HASH)
        with self.assertRaises(ContractError):
            payload_sha256({"number": float("nan")})

    def test_every_candidate_field_is_explicit(self):
        for field in tuple(self.payload):
            with self.subTest(field=field):
                candidate = deepcopy(self.payload)
                del candidate[field]
                with self.assertRaises(ContractError):
                    self.check(candidate)

    def test_internal_or_cross_destination_fields_are_rejected(self):
        for field in (
            "binding_id", "actor", "session_ref", "source_relative_path",
            "markdown", "is_published", "published_at", "publishable_at", "state"
        ):
            with self.subTest(field=field):
                candidate = dict(self.payload, **{field: "must-not-export"})
                with self.assertRaises(ContractError):
                    self.check(candidate)

    def test_identity_and_revision_pairs(self):
        for field, value in [
            ("manuscript_ref", "PUB99990001"),
            ("revision_ref", "ART99990002-R01"),
            ("revision_no", 2), ("revision_no", True),
            ("revision_no", 0), ("edition_ref", "ART99990001"),
            ("destination_ref", "confluence:other"),
            ("destination_key", "ai-inner-life"),
            ("schema_version", "confluence.publication.v2"),
            ("locale", "jp"),
        ]:
            with self.subTest(field=field, value=value):
                candidate = dict(self.payload, **{field: value})
                with self.assertRaises(ContractError):
                    self.check(candidate)

    def test_english_edition_and_route(self):
        candidate = dict(self.payload, locale="en", edition_ref="EDN99990001",
                         destination_url=self.base + "/en/articles/art99990001.html")
        self.check(candidate)

    def test_visibility_is_only_candidate_intent(self):
        for value in ("private", "public", "published", None):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    self.check(dict(self.payload, visibility=value))
        self.assertNotIn("is_published", self.payload)

    def test_date_rules_and_unknown_values(self):
        self.check(dict(self.payload, content_updated_at=None,
                        excerpt=None, author_label=None, authors=[]))
        self.check(dict(self.payload, excerpt="", author_label=""))
        for field, value in [
            ("published_on", "20260926"),
            ("published_on", "2026-09-26T00:00:00+08:00"),
            ("published_on", "2026-02-30"),
            ("content_updated_at", "2026-09-26T21:00:00"),
            ("content_updated_at", "2026-09-26 21:00:00+08:00"),
            ("content_updated_at", "2026-99-26T21:00:00+08:00"),
        ]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ContractError):
                    self.check(dict(self.payload, **{field: value}))

    def test_taxonomy_hierarchy_is_not_flattened(self):
        self.assertEqual(self.payload["category_paths"],
                         [["研究ノート", "接続テスト"], ["ノート"]])
        self.check(dict(self.payload, category_paths=[], tags=[]))
        for field, value in [
            ("category_paths", ["研究ノート"]), ("category_paths", [[]]),
            ("category_paths", [[""]]), ("tags", [None]), ("tags", "接続確認"),
        ]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ContractError):
                    self.check(dict(self.payload, **{field: value}))

    def test_authorship_public_field_allowlist(self):
        author = self.payload["authors"][0]
        self.assertIsNone(author["model"])
        for field in ("actor", "session_ref", "source_path", "attribution_id"):
            with self.subTest(field=field):
                bad = dict(author, **{field: "internal"})
                with self.assertRaises(ContractError):
                    self.check(dict(self.payload, authors=[bad]))

    def test_destination_base_is_not_taken_from_the_payload(self):
        for url in [
            "https://other.invalid/ja/articles/art99990001.html",
            "https://confluence.invalid/ja/articles/other.html",
            "https://confluence.invalid/ja/articles/art99990001.html?preview=1",
            "https://confluence.invalid/ja/articles/art99990001.html#body",
            "javascript:alert(1)",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ContractError):
                    self.check(dict(self.payload, destination_url=url))

    def test_relative_links_and_assets_are_not_silently_resolved(self):
        for html in [
            '<p><a href="../private.md">link</a></p>',
            '<p><a href="//example.invalid">link</a></p>',
            '<p><img src="picture.jpg"></p>',
            '<p><a href="#cf-missing">link</a></p>',
        ]:
            with self.subTest(html=html):
                with self.assertRaises(ContractError):
                    validate_fixture_html(html)

    def test_unsupported_html_is_rejected_not_sanitized_after_approval(self):
        cases = [
            '<script>alert(1)</script>', '<p onclick="alert(1)">x</p>',
            '<p style="display:none">x</p>', '<iframe src="x"></iframe>',
            '<svg onload="alert(1)"></svg>', '<base href="https://x.invalid">',
            '<p><a href="javascript:alert(1)">x</a></p>',
            '<p><a href="java&#x09;script:alert(1)">x</a></p>',
            '<p><a href="https://u:p@x.invalid">x</a></p>',
            '<p><a href="file:///tmp/x">x</a></p>',
            '<p><a href="data:text/html,x">x</a></p>',
            '<p id="location">x</p>', '<p hidden>x</p>',
            '<p class="one" class="two">x</p>',
            '<p>unclosed', '<p>x</blockquote>',
            '<!-- not a prose field -->', '<!DOCTYPE html>',
        ]
        for html in cases:
            with self.subTest(html=html):
                with self.assertRaises(ContractError):
                    validate_fixture_html(html)

    def test_safe_prose_code_table_and_fragments(self):
        html = (
            '<h2 id="cf-section">Section</h2><p lang="ja">本文 &amp; 例</p>'
            '<pre><code class="language-python">print(&quot;hi&quot;)</code></pre>'
            '<table><thead><tr><th>名前</th></tr></thead>'
            '<tbody><tr><td>合成</td></tr></tbody></table><hr/>'
            '<p><a href="#cf-section">戻る</a> / '
            '<a href="https://example.invalid/resource">資料</a></p>'
        )
        validate_fixture_html(html)

    def test_fixture_gate_and_hash_tampering(self):
        for change in [
            {"fixture_only": False},
            {"site_base_url": "https://production.invalid"},
            {"expected_payload_sha256": "0" * 64},
        ]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "test.json"
                path.write_text(json.dumps(dict(self.fixture, **change)), encoding="utf-8")
                with self.assertRaises(ContractError):
                    load_fixture(path)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.json"
            path.write_text('{"fixture_only":true,"fixture_only":false}', encoding="utf-8")
            with self.assertRaises(ContractError):
                load_fixture(path)

    def test_cli_reports_fixture_only_not_publication(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/validate_confluence_contract.py"), str(FIXTURE)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DB/network/publication: not used", result.stdout)
        self.assertNotIn(self.payload["rendered_html"], result.stdout)


if __name__ == "__main__":
    unittest.main()
