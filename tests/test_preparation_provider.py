"""Unit-level read-only provider tests. DTO doubles are NOT real PUB/APR/JOBs."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
from confluence.config import ConfluenceError, RehearsalConfig
from confluence.dependency_pin import DependencyEvidence, verify_local_dependencies
from confluence.payload_schema import payload_sha256
from confluence.provider import PreparationProvider, create_preparation_provider
from prepare_renderer_fixture import raw_fixture, resolved_fixture


class PreparationProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = RehearsalConfig(Path(self.tmp.name))
        self.resolved = resolved_fixture()
        self.source = Mock()
        self.source.resolve.return_value = self.resolved
        _, pin = raw_fixture()
        self.evidence = DependencyEvidence(pin['pressroom']['commit'], pin['md_converter']['commit'],
                                           pin['renderer_version'], pin['python_version'])
        def prepared(mid, rid, preview, payload):
            return SimpleNamespace(manuscript_id=mid, revision_id=rid, preview=preview, payload_snapshot=payload)
        self.provider = PreparationProvider(self.config, self.source, self.evidence, prepared, SimpleNamespace)

    def prepare(self):
        return self.provider.prepare('ART99990001', 'ART99990001-R01', {'published_on': '2026-09-26'})

    def test_exact_revision_and_hash_prepared_without_writes(self):
        result = self.prepare()
        self.source.resolve.assert_called_once_with('ART99990001', 'ART99990001-R01')
        self.assertEqual(result.preview.payload_sha256, payload_sha256(result.payload_snapshot))
        self.assertTrue(result.preview.requires_two_step_approval)
        self.assertNotIn('state', result.payload_snapshot)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_wrong_manuscript_or_revision_from_source_rejected(self):
        for name, value in [('manuscript_ref', 'ART99990002'), ('revision_ref', 'ART99990001-R02')]:
            old = getattr(self.resolved.snapshot, name)
            setattr(self.resolved.snapshot, name, value)
            with self.assertRaises(ConfluenceError):
                self.prepare()
            setattr(self.resolved.snapshot, name, old)

    def test_unreviewed_renderer_never_silently_falls_back(self):
        self.resolved.snapshot.renderer_version = 'old-renderer'
        with self.assertRaises(ConfluenceError):
            self.prepare()

    def test_no_release_methods_available(self):
        for method in ['publish', 'unpublish', 'publish_dispatch', 'unpublish_dispatch']:
            self.assertFalse(hasattr(self.provider, method))

    def test_missing_checkouts_block_factory_before_source_is_read(self):
        with self.assertRaises(ConfluenceError):
            create_preparation_provider(
                self.config, self.source,
                provenance=ROOT / 'tests/fixtures/confluence/renderer/provenance.json',
                pressroom_root=Path(self.tmp.name) / 'absent-pr',
                converter_root=Path(self.tmp.name) / 'absent-converter',
            )
        self.source.resolve.assert_not_called()

    def test_invalid_pin_has_bounded_diagnostic(self):
        with self.assertRaises(ConfluenceError) as error:
            verify_local_dependencies(Path(self.tmp.name) / 'secret-missing-file',
                                      Path(self.tmp.name), Path(self.tmp.name))
        self.assertNotIn(self.tmp.name, str(error.exception))
        self.assertNotIn('secret-missing-file', str(error.exception))

    def test_resolve_identity_is_read_only(self):
        self.assertEqual(self.provider.resolve_manuscript_id('ART99990001'), self.resolved.manuscript_id)
        self.resolved.snapshot.manuscript_ref = 'ART99990002'
        with self.assertRaises(ConfluenceError):
            self.provider.resolve_manuscript_id('ART99990001')


if __name__ == '__main__':
    unittest.main()
