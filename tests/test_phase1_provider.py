from __future__ import annotations

from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from contract_html_policy import ContractError, validate_fixture_html
from confluence_pressroom.dependency_pin import load_dependency_pin
from confluence_pressroom.html_prepare import PREPARATION_VERSION, prepare_rendered_html
from confluence_pressroom.payload import CandidateArticle, build_publication_payload, payload_sha256
from confluence_pressroom.provider_core import ConfluenceProviderCore, PublicAuthor, ResolvedArticle
from confluence_pressroom.staging import PrivateStagingStore, ROBOTS

FIX = ROOT / "tests/fixtures/confluence/renderer"
RAW = (FIX / "output.html").read_text(encoding="utf-8")
PROV = FIX / "provenance.json"


def article(raw_html=RAW, *, revision_no=1):
    prepared = prepare_rendered_html(raw_html)
    return CandidateArticle(
        manuscript_ref="ART99990001",
        revision_ref=f"ART99990001-R{revision_no:02d}",
        revision_no=revision_no,
        edition_ref=None,
        locale="ja",
        title="合成レンダラー試験",
        excerpt="Pressroom renderer由来の合成fixtureです。",
        author_label="接続テスト用AI",
        authors=({
            "author_ref":"AUT99990001","persona_name":"接続テスト用AI",
            "harness":None,"model":None,"role":"primary","provenance_source":"supplied"
        },),
        category_paths=(("研究ノート","接続テスト"),),
        tags=("接続確認","合成データ"),
        content_updated_at=datetime(2026,9,26,21,0,tzinfo=timezone.utc),
        renderer_version=load_dependency_pin(PROV).renderer_version,
        prepared_html=prepared,
    )


def payload(raw_html=RAW, *, revision_no=1):
    return build_publication_payload(
        article(raw_html, revision_no=revision_no),
        site_base_url="https://confluence.invalid",
        published_on=date(2026,9,26),
    )


def unpublish_payload(value=None):
    source = value or payload()
    return {
        "operation_kind": "unpublish",
        "destination_ref": source["destination_ref"],
        "destination_url": source["destination_url"],
        "published_revision_id": "00000000-0000-0000-0000-000000000002",
    }


class HTMLPreparationTests(unittest.TestCase):
    def test_raw_renderer_output_is_not_already_confluence_prepared(self):
        with self.assertRaises(ContractError):
            validate_fixture_html(RAW)

    def test_prepared_renderer_output_passes_contract_checker(self):
        value = prepare_rendered_html(RAW)
        validate_fixture_html(value.html)
        self.assertEqual(value.preparation_version, PREPARATION_VERSION)

    def test_duplicate_headings_receive_unique_ids(self):
        value = prepare_rendered_html(RAW)
        self.assertEqual(len(value.heading_ids), 5)
        self.assertEqual(len(set(value.heading_ids)), 5)
        duplicate_base = value.heading_ids[1]
        self.assertEqual(value.heading_ids[-1], duplicate_base + "-2")

    def test_both_fragment_links_choose_first_duplicate_heading(self):
        value = prepare_rendered_html(RAW)
        target = value.heading_ids[1]
        self.assertEqual(value.html.count(f'href="#{target}"'), 2)
        self.assertNotIn("%E6%97%A5", value.html)

    def test_renderer_rel_attribute_is_normalized_away(self):
        value = prepare_rendered_html(RAW)
        self.assertNotIn(" rel=", value.html)
        self.assertIn('href="https://example.invalid/synthetic"', value.html)

    def test_preparation_is_deterministic(self):
        self.assertEqual(prepare_rendered_html(RAW), prepare_rendered_html(RAW))

    def test_unsafe_or_unknown_link_rel_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_rendered_html('<p><a href="https://example.invalid" rel="nofollow">x</a></p>')

    def test_unresolved_fragment_fails_closed(self):
        with self.assertRaises(ValueError):
            prepare_rendered_html('<p><a href="#missing">x</a></p><h2>other</h2>')

    def test_unsupported_element_and_attribute_fail_closed(self):
        for html in ('<script>x</script>', '<p style="x">x</p>', '<img src="x">'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                prepare_rendered_html(html)


class DependencyAndPayloadTests(unittest.TestCase):
    def test_dependency_pin_records_local_source_identity(self):
        pin = load_dependency_pin(PROV)
        self.assertEqual(pin.pressroom_commit, "b5ce8d9422f0b90377145471bcb96f870e3e9263")
        self.assertEqual(pin.md_converter_commit, "0d98198dd2da1abf82e4cf17c1bf8658027f021c")
        self.assertEqual(pin.dependencies["nh3"], "0.3.6")

    def test_payload_contains_prepared_not_raw_renderer_html(self):
        value = payload()
        self.assertNotEqual(value["rendered_html"], RAW)
        self.assertIn(PREPARATION_VERSION, value["renderer_version"])
        validate_fixture_html(value["rendered_html"])

    def test_payload_hash_is_stable(self):
        first = payload()
        second = payload()
        self.assertEqual(payload_sha256(first), payload_sha256(second))

    def test_route_and_identity_are_title_independent(self):
        value = payload()
        self.assertEqual(value["destination_ref"], "confluence:ART99990001")
        self.assertEqual(value["destination_url"], "https://confluence.invalid/ja/articles/art99990001.html")

    def test_phase1_visibility_is_public_inside_confluence(self):
        self.assertEqual(payload()["visibility"], "public")
        with self.assertRaises(ValueError):
            build_publication_payload(article(), site_base_url="https://confluence.invalid", published_on=date(2026,9,26), visibility="unlisted")

    def test_actual_ledger_timestamps_are_not_candidate_fields(self):
        value = payload()
        self.assertNotIn("first_published_at", value)
        self.assertNotIn("last_published_at", value)
        self.assertNotIn("state", value)


class FakeResolver:
    def __init__(self, resolved):
        self.resolved = resolved
        self.current = resolved

    def get(self, ref, *, mode="current"):
        if ref not in {self.resolved.manuscript_ref, self.resolved.revision_ref}:
            raise KeyError(ref)
        return self.current if ref == self.resolved.manuscript_ref else self.resolved


def resolved_article():
    pin = load_dependency_pin(PROV)
    return ResolvedArticle(
        manuscript_id=UUID("00000000-0000-0000-0000-000000000001"),
        revision_id=UUID("00000000-0000-0000-0000-000000000002"),
        manuscript_ref="ART99990001", revision_ref="ART99990001-R01", revision_no=1,
        edition_ref=None, locale="ja", title="合成レンダラー試験",
        excerpt="fixture", author_label="接続テスト用AI",
        authors=(PublicAuthor("AUT99990001","接続テスト用AI",None,None,"primary","supplied"),),
        category_paths=(("研究ノート","接続テスト"),), tags=("接続確認",),
        content_updated_at=datetime(2026,9,26,21,0,tzinfo=timezone.utc),
        rendered_html=RAW, renderer_version=pin.renderer_version,
    )


class ProviderCoreTests(unittest.TestCase):
    def test_prepare_requires_explicit_display_date(self):
        core = ConfluenceProviderCore(FakeResolver(resolved_article()), site_base_url="https://confluence.invalid")
        with self.assertRaises(ValueError):
            core.prepare("ART99990001", None, None)

    def test_prepare_normalizes_real_renderer_seam_before_hash(self):
        core = ConfluenceProviderCore(FakeResolver(resolved_article()), site_base_url="https://confluence.invalid")
        value = core.prepare("ART99990001", None, {"published_on":"2026-09-26"})
        validate_fixture_html(value.payload_snapshot["rendered_html"])
        self.assertEqual(value.payload_sha256, payload_sha256(value.payload_snapshot))

    def test_prepare_rejects_unknown_destination_metadata(self):
        core = ConfluenceProviderCore(FakeResolver(resolved_article()), site_base_url="https://confluence.invalid")
        with self.assertRaises(ValueError):
            core.prepare("ART99990001", None, {"published_on":"2026-09-26","x":1})


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "staging"
        self.store = PrivateStagingStore(self.root)
        self.payload = payload()

    def tearDown(self):
        self.temp.cleanup()

    def test_staging_root_must_be_absolute(self):
        with self.assertRaises(ValueError):
            PrivateStagingStore("relative")

    def test_publish_writes_detail_and_internal_discovery_surfaces(self):
        receipt = self.store.publish(self.payload, idempotency_key="job-1")
        self.assertEqual(receipt.action, "publish")
        article_path = self.root / "site/ja/articles/art99990001.html"
        self.assertTrue(article_path.exists())
        self.assertIn("ART99990001", (self.root/"site/index.html").read_text(encoding="utf-8"))
        self.assertIn("ART99990001", (self.root/"site/search.json").read_text(encoding="utf-8"))
        self.assertIn("研究ノート › 接続テスト", (self.root/"site/browse.html").read_text(encoding="utf-8"))

    def test_site_discourages_external_discovery(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        for name in ("index.html", "browse.html", "ja/articles/art99990001.html"):
            self.assertIn(ROBOTS, (self.root/"site"/name).read_text(encoding="utf-8"))
        self.assertFalse((self.root/"site/sitemap.xml").exists())

    def test_publish_lookup_verifies_artifact_and_listing(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        self.assertEqual(self.store.lookup("publish", self.payload).outcome, "succeeded")
        (self.root/"site/index.html").write_text("broken", encoding="utf-8")
        self.assertEqual(self.store.lookup("publish", self.payload).error_code, "listing_missing")

    def test_tampered_article_body_fails_readback(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        article_path = self.root/"site/ja/articles/art99990001.html"
        article_path.write_text(article_path.read_text(encoding="utf-8").replace("合成fixtureのみ", "改ざん"), encoding="utf-8")
        self.assertEqual(self.store.lookup("publish", self.payload).error_code, "artifact_mismatch")

    def test_same_key_same_payload_is_idempotent(self):
        a = self.store.publish(self.payload, idempotency_key="job-1")
        b = self.store.publish(self.payload, idempotency_key="job-1")
        self.assertEqual(a, b)

    def test_same_key_different_payload_is_rejected(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        changed = dict(self.payload, title="changed")
        with self.assertRaises(ValueError):
            self.store.publish(changed, idempotency_key="job-1")

    def test_lookup_can_recover_external_success_without_operation_receipt(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        for path in (self.root/"operations").glob("*.json"):
            path.unlink()
        self.assertEqual(self.store.lookup("publish", self.payload).outcome, "succeeded")

    def test_unpublish_removes_body_and_all_listing_surfaces(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        self.store.unpublish(unpublish_payload(self.payload), idempotency_key="job-2")
        self.assertFalse((self.root/"site/ja/articles/art99990001.html").exists())
        self.assertNotIn("ART99990001", (self.root/"site/index.html").read_text(encoding="utf-8"))
        self.assertNotIn("ART99990001", (self.root/"site/search.json").read_text(encoding="utf-8"))
        self.assertEqual(self.store.lookup("unpublish", unpublish_payload(self.payload)).outcome, "succeeded")

    def test_unpublish_same_key_same_payload_is_idempotent(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        first = self.store.unpublish(unpublish_payload(self.payload), idempotency_key="job-2")
        second = self.store.unpublish(unpublish_payload(self.payload), idempotency_key="job-2")
        self.assertEqual(first, second)

    def test_display_date_history_survives_withdrawal(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        self.store.unpublish(unpublish_payload(self.payload), idempotency_key="job-2")
        self.assertEqual(self.store.published_on("ART99990001"), "2026-09-26")
        self.assertIsNone(self.store.published_payload("ART99990001"))

    def test_revision_replaces_same_route_without_duplicate_entry(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        newer = payload(revision_no=2)
        self.store.publish(newer, idempotency_key="job-2")
        index = (self.root/"site/index.html").read_text(encoding="utf-8")
        self.assertEqual(index.count('data-manuscript-ref="ART99990001"'), 1)
        article = (self.root/"site/ja/articles/art99990001.html").read_text(encoding="utf-8")
        self.assertIn('data-revision-ref="ART99990001-R02"', article)

    def test_unpublish_requires_pressroom_operation_payload_shape(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        with self.assertRaises(ValueError):
            self.store.unpublish(self.payload, idempotency_key="job-2")
        bad = dict(unpublish_payload(self.payload), destination_ref="confluence:ART99990002")
        with self.assertRaises(ValueError):
            self.store.unpublish(bad, idempotency_key="job-3")

    def test_http_readback_200_then_404_after_unpublish(self):
        self.store.publish(self.payload, idempotency_key="job-1")
        handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(self.root/"site"), **kw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/ja/articles/art99990001.html") as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as missing_sitemap:
                urllib.request.urlopen(base + "/sitemap.xml")
            self.assertEqual(missing_sitemap.exception.code, 404)
            self.store.unpublish(unpublish_payload(self.payload), idempotency_key="job-2")
            with self.assertRaises(urllib.error.HTTPError) as missing_article:
                urllib.request.urlopen(base + "/ja/articles/art99990001.html")
            self.assertEqual(missing_article.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
