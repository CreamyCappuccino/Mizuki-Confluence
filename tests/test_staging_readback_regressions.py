"""RLY2890: exact artifacts and independent withdrawal surfaces (offline)."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_phase1_provider import payload, unpublish_payload
from confluence_pressroom.staging import PrivateStagingStore
from confluence_pressroom.static_pages import render_browse, render_index, render_search


class ReadbackRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PrivateStagingStore(Path(self.temp.name) / "staging")
        self.payload = payload()
        self.store.publish(self.payload, idempotency_key="publish-one")
        self.article = self.store.site / "ja/articles/art99990001.html"

    def test_extra_paragraph_after_approved_body_is_rejected(self):
        text = self.article.read_text(encoding="utf-8")
        self.article.write_text(text.replace(
            "</article>", "<p>unexpected synthetic extra body</p></article>"
        ), encoding="utf-8")
        self.assertEqual(self.store.lookup("publish", self.payload).outcome, "failed")

    def test_extra_content_outside_article_is_rejected(self):
        text = self.article.read_text(encoding="utf-8")
        self.article.write_text(text + "<p>unexpected extra</p>", encoding="utf-8")
        self.assertEqual(self.store.lookup("publish", self.payload).outcome, "failed")

    def test_each_visible_public_field_is_verified(self):
        original = self.article.read_bytes()
        for field, changed in (("title", "改ざんタイトル"), ("author_label", "別の作者"),
                               ("published_on", "2026-01-01")):
            with self.subTest(field=field):
                text = original.decode("utf-8")
                text = text.replace(str(self.payload[field]), changed)
                self.article.write_text(text, encoding="utf-8")
                self.assertEqual(self.store.lookup("publish", self.payload).outcome, "failed")
        self.article.write_bytes(original)

    def test_publish_browse_count_corruption_is_rejected(self):
        path = self.store.site / "browse.html"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "<span>1</span>", "<span>99</span>"
        ), encoding="utf-8")
        self.assertEqual(self.store.lookup("publish", self.payload).outcome, "failed")

    def test_withdrawal_rejects_each_individually_restored_surface(self):
        names = ("index.html", "search.json", "browse.html", "ja/articles/art99990001.html")
        before = {name: (self.store.site / name).read_bytes() for name in names}
        removal = unpublish_payload(self.payload)
        self.store.unpublish(removal, idempotency_key="withdraw-one")
        after = {name: (self.store.site / name).read_bytes() for name in names[:-1]}
        for name in names:
            with self.subTest(surface=name):
                target = self.store.site / name
                target.write_bytes(before[name])
                self.assertEqual(self.store.lookup("unpublish", removal).outcome, "failed")
                if name in after:
                    target.write_bytes(after[name])
                else:
                    target.unlink()
                self.assertEqual(self.store.lookup("unpublish", removal).outcome, "succeeded")

    def test_missing_withdrawal_surface_is_not_proof_of_success(self):
        removal = unpublish_payload(self.payload)
        self.store.unpublish(removal, idempotency_key="withdraw-one")
        for name in ("index.html", "search.json", "browse.html"):
            with self.subTest(surface=name):
                path = self.store.site / name
                original = path.read_bytes()
                path.unlink()
                self.assertNotEqual(self.store.lookup("unpublish", removal).outcome, "succeeded")
                path.write_bytes(original)

    def test_shared_taxonomy_is_preserved_with_correct_remaining_counts(self):
        remaining = deepcopy(self.payload)
        remaining.update(manuscript_ref="ART99990002", revision_ref="ART99990002-R01",
                         destination_ref="confluence:ART99990002",
                         destination_url="https://confluence.invalid/ja/articles/art99990002.html")
        self.store.publish(remaining, idempotency_key="publish-two")
        browse = self.store.site / "browse.html"
        old_browse = browse.read_bytes()
        removal = unpublish_payload(self.payload)
        self.store.unpublish(removal, idempotency_key="withdraw-one")
        expected = {remaining["manuscript_ref"]: remaining}
        for name, render in (("index.html", render_index), ("search.json", render_search),
                             ("browse.html", render_browse)):
            self.assertEqual((self.store.site / name).read_bytes(), render(expected).encode("utf-8"))
        self.assertEqual(self.store.lookup("unpublish", removal).outcome, "succeeded")
        self.assertEqual(self.store.lookup("publish", remaining).outcome, "succeeded")
        browse.write_bytes(old_browse)  # same labels, now incorrect shared counts
        self.assertEqual(self.store.lookup("unpublish", removal).outcome, "failed")

    def test_retry_does_not_silently_repair_corrupt_artifact(self):
        self.article.write_bytes(self.article.read_bytes() + b"unexpected")
        before = self.article.read_bytes()
        with self.assertRaises(RuntimeError):
            self.store.publish(self.payload, idempotency_key="publish-one")
        self.assertEqual(self.article.read_bytes(), before)

    def test_unreadable_artifact_is_unknown_not_success_or_definitive_absence(self):
        with patch.object(Path, "read_bytes", side_effect=PermissionError("synthetic read failure")):
            result = self.store.lookup("publish", self.payload)
        self.assertEqual(result.outcome, "unknown")

    def test_withdrawal_retains_noindex_and_no_sitemap_policy(self):
        removal = unpublish_payload(self.payload)
        self.store.unpublish(removal, idempotency_key="withdraw-one")
        path = self.store.site / "index.html"
        original = path.read_bytes()
        path.write_bytes(original.replace(b"noindex, nofollow, noarchive", b"index, follow"))
        self.assertEqual(self.store.lookup("unpublish", removal).outcome, "failed")
        path.write_bytes(original)
        (self.store.site / "sitemap.xml").write_text("synthetic stale sitemap", encoding="utf-8")
        self.assertEqual(self.store.lookup("unpublish", removal).outcome, "failed")


if __name__ == "__main__":
    unittest.main()
