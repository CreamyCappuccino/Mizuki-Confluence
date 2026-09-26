"""RLY2890 regressions through real Confluence adapter code, fake Pressroom ports."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from uuid import UUID

from adapter_test_support import dispatch, make_adapter, pressroom_double, snapshot_files
from test_phase1_provider import resolved_article
from confluence_pressroom.payload import payload_sha256
from confluence_pressroom.pressroom_adapter import _CanonicalReader, ConfluenceDestinationAdapter


class ExactAuthorsTests(unittest.TestCase):
    def test_exact_revision_authors_are_not_taken_from_standalone_snapshot(self):
        resolved = resolved_article()
        def record(revision):
            return SimpleNamespace(manuscript=SimpleNamespace(id=revision.manuscript_id),
                revision=SimpleNamespace(id=revision.revision_id), snapshot=replace(revision, authors=()))
        newer = replace(resolved, revision_ref="ART99990001-R02", revision_no=2,
                        revision_id=UUID("00000000-0000-0000-0000-000000000003"))
        author = SimpleNamespace(author_ref="AUT99990001", persona_name="合成作者",
            harness="fixture-harness", model="fixture-model", role="primary",
            provenance_source="supplied", provider="private-provider",
            session_ref="private-session", source_path="private-path", contributor_id="private-id")
        records = {resolved.revision_ref: record(resolved), newer.revision_ref: record(newer),
                   resolved.manuscript_ref: record(newer)}
        authors = {resolved.revision_ref: (author,), newer.revision_ref: ()}
        with pressroom_double(records=records, authors_by_revision=authors) as calls:
            reader = _CanonicalReader(None)
            old = reader.get(resolved.revision_ref)
            current = reader.get(resolved.manuscript_ref)
            with tempfile.TemporaryDirectory() as directory:
                adapter = ConfluenceDestinationAdapter(None, staging_root=Path(directory) / "staging",
                    site_base_url="https://confluence.invalid")
                prepared = adapter.prepare(resolved.manuscript_ref, resolved.revision_ref,
                                           {"published_on": "2026-09-26"})
        self.assertEqual(calls[:2], [(resolved.revision_ref,), (newer.revision_ref,)])
        self.assertEqual(calls[-1], (resolved.revision_ref,))
        self.assertEqual(prepared.payload_snapshot["authors"], [old.authors[0].as_payload()])
        self.assertEqual(len(old.authors), 1)
        public = old.authors[0].as_payload()
        self.assertEqual(public, {"author_ref": "AUT99990001", "persona_name": "合成作者",
            "harness": "fixture-harness", "model": "fixture-model", "role": "primary",
            "provenance_source": "supplied"})
        self.assertEqual(current.authors, ())


class DispatchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ports = pressroom_double()
        self.ports.__enter__()
        self.addCleanup(self.ports.__exit__, None, None, None)
        self.adapter = make_adapter(self.root)

    def reject_without_writes(self, value, *, action="publish"):
        before = snapshot_files(self.root)
        with self.assertRaises(ValueError):
            if action == "publish":
                self.adapter.publish_dispatch(value, expected_revision=1)
            else:
                self.adapter.unpublish_dispatch(value)
        self.assertEqual(snapshot_files(self.root), before)

    def test_publish_hash_mismatch_is_rejected_before_any_files(self):
        value = dispatch()
        value.payload_sha256 = "0" * 64
        self.reject_without_writes(value)
        self.assertFalse(self.adapter._staging.root.exists())

    def test_changed_payload_with_old_approved_hash_is_rejected(self):
        value = dispatch()
        value.payload_snapshot["title"] = "changed after approval"
        self.reject_without_writes(value)

    def test_action_and_destination_are_checked_before_publish(self):
        for key, changed in (("action", "unpublish"), ("destination_key", "ai-inner-life")):
            with self.subTest(key=key):
                value = dispatch()
                setattr(value, key, changed)
                self.reject_without_writes(value)

    def test_wrong_payload_identity_is_rejected_even_with_matching_hash(self):
        for key, changed in (("manuscript_ref", "ART99990002"),
                             ("destination_ref", "confluence:ART99990002"),
                             ("revision_no", 2), ("destination_key", "ai-inner-life"),
                             ("visibility", "private"),
                             ("destination_url", "https://other.invalid/ja/articles/art99990001.html")):
            with self.subTest(key=key):
                value = dispatch()
                value.payload_snapshot[key] = changed
                value.payload_sha256 = payload_sha256(value.payload_snapshot)
                self.reject_without_writes(value)

    def test_internal_ids_must_match_selected_revision(self):
        for key in ("manuscript_id", "revision_id"):
            with self.subTest(key=key):
                value = dispatch()
                setattr(value, key, UUID("00000000-0000-0000-0000-000000000099"))
                self.reject_without_writes(value)

    def test_valid_publish_lookup_retry_and_withdrawal(self):
        publish = dispatch()
        self.assertEqual(self.adapter.publish_dispatch(publish, expected_revision=1).state, "published")
        self.assertEqual(self.adapter.publish_dispatch(publish, expected_revision=1).state, "published")
        self.assertEqual(self.adapter.lookup_dispatch(publish).outcome, "succeeded")
        withdraw = dispatch("unpublish")
        self.assertEqual(self.adapter.unpublish_dispatch(withdraw).state, "unpublished")
        self.assertEqual(self.adapter.unpublish_dispatch(withdraw).state, "unpublished")
        self.assertEqual(self.adapter.lookup_dispatch(withdraw).outcome, "succeeded")

    def test_unpublish_checks_hash_action_destination_and_revision(self):
        self.adapter.publish_dispatch(dispatch(), expected_revision=1)
        for key, changed in (("payload_sha256", "0" * 64), ("action", "publish"),
                             ("destination_key", "ai-inner-life"),
                             ("revision_id", UUID("00000000-0000-0000-0000-000000000099")),
                             ("manuscript_id", UUID("00000000-0000-0000-0000-000000000099"))):
            with self.subTest(key=key):
                value = dispatch("unpublish")
                setattr(value, key, changed)
                self.reject_without_writes(value, action="unpublish")

    def test_unpublish_cannot_retarget_another_origin_with_recomputed_hash(self):
        self.adapter.publish_dispatch(dispatch(), expected_revision=1)
        value = dispatch("unpublish")
        value.payload_snapshot["destination_url"] = "https://other.invalid/ja/articles/art99990001.html"
        value.payload_sha256 = payload_sha256(value.payload_snapshot)
        self.reject_without_writes(value, action="unpublish")

    def test_lookup_rejects_changed_hash_without_side_effects(self):
        for action in ("publish", "unpublish"):
            with self.subTest(action=action):
                value = dispatch(action)
                value.payload_sha256 = "0" * 64
                before = snapshot_files(self.root)
                self.assertEqual(self.adapter.lookup_dispatch(value).outcome, "failed")
                self.assertEqual(snapshot_files(self.root), before)

    def test_lookup_does_not_accept_wrong_destination_or_internal_identity(self):
        value = dispatch()
        self.adapter.publish_dispatch(value, expected_revision=1)
        for key, changed in (("destination_key", "ai-inner-life"),
                             ("revision_id", UUID("00000000-0000-0000-0000-000000000099"))):
            with self.subTest(key=key):
                bad = dispatch()
                setattr(bad, key, changed)
                self.assertEqual(self.adapter.lookup_dispatch(bad).outcome, "failed")

    def test_new_current_revision_blocks_dispatch_but_not_old_result_lookup(self):
        value = dispatch()
        self.adapter.publish_dispatch(value, expected_revision=1)
        self.adapter._reader.current = replace(resolved_article(), revision_no=2,
            revision_ref="ART99990001-R02", revision_id=UUID("00000000-0000-0000-0000-000000000003"))
        self.assertEqual(self.adapter.lookup_dispatch(value).outcome, "succeeded")
        self.reject_without_writes(value)

    def test_lookup_rejects_reused_key_with_conflicting_operation_receipt(self):
        value = dispatch()
        self.adapter.publish_dispatch(value, expected_revision=1)
        withdraw = dispatch("unpublish")
        self.adapter.unpublish_dispatch(withdraw)
        withdraw.idempotency_key = value.idempotency_key
        self.assertEqual(self.adapter.lookup_dispatch(withdraw).outcome, "failed")

    def test_lookup_withdrawal_without_private_evidence_stays_unknown(self):
        before = snapshot_files(self.root)
        self.assertEqual(self.adapter.lookup_dispatch(dispatch("unpublish")).outcome, "unknown")
        self.assertEqual(snapshot_files(self.root), before)

    def test_lookup_cannot_use_a_published_revision_uuid_from_another_article(self):
        self.adapter.publish_dispatch(dispatch(), expected_revision=1)
        value = dispatch("unpublish")
        value.payload_snapshot["published_revision_id"] = "00000000-0000-0000-0000-000000000099"
        value.payload_sha256 = payload_sha256(value.payload_snapshot)
        self.reject_without_writes(value, action="unpublish")


if __name__ == "__main__":
    unittest.main()
