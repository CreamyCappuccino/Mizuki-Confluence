"""Synthetic immutable artifact tests; no private article or provider traffic."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from confluence_release.artifacts import ReleaseBuilder, read_files, sha256
from confluence_release.config import json_bytes
from confluence_release.presentation_artifact import (
    PresentationCandidate, asset_path, build_candidate, validate_candidate,
)
from phase2_support import CONFIG, article, assets


class PresentationArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.base = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
                                   source_commit='old-source').build((article(),), self.root/'releases'/'base')
        self.original = read_files(self.base.output)
        self.overlay = {'assets/styles.css': b'body { color: #123; }',
                        'assets/effect.js': b'/* presentation only */'}

    def build(self, **kwargs):
        values = dict(base_version='base-v1', source_commit='a'*40, source_job='JOB99990001',
                      config=CONFIG, overlay=self.overlay, output=self.root/'releases'/'candidate')
        values.update(kwargs)
        return build_candidate(self.base, **values)

    def rewrite(self, candidate, path, data):
        (candidate.artifact.output/path).write_bytes(data)
        files = read_files(candidate.artifact.output); files.pop('checksums.sha256')
        checksums = {name: sha256(raw) for name, raw in sorted(files.items())}
        raw = ''.join(f'{h}  {name}\n' for name, h in checksums.items()).encode()
        (candidate.artifact.output/'checksums.sha256').write_bytes(raw)
        checksums['checksums.sha256'] = sha256(raw)
        return replace(candidate, artifact=replace(candidate.artifact, checksums=checksums))

    def test_overlay_preserves_all_html_and_editorial_data(self):
        candidate = self.build(); current = read_files(candidate.artifact.output)
        self.assertEqual(read_files(self.base.output), self.original)
        for path, raw in self.original.items():
            if path not in {*self.overlay, 'checksums.sha256', 'release-manifest.json'}:
                self.assertEqual(current[path], raw)
        self.assertEqual(candidate.artifact.content_digest, self.base.content_digest)
        self.assertEqual(candidate.artifact.article_routes, self.base.article_routes)
        value = json.loads(current['release-manifest.json'])
        self.assertEqual(value, dict(json.loads(self.original['release-manifest.json']), source_commit='a'*40))
        self.assertEqual(PresentationCandidate.from_record(candidate.as_record()), candidate)

    def test_only_css_and_js_assets_are_eligible(self):
        for path in ('index.html', 'assets/x.html', 'assets/x.json', '../x.css', 'assets/../x.css', '/assets/x.css', 'assets/x.js?x=1'):
            with self.subTest(path=path), self.assertRaises(ValueError): asset_path(path)

    def test_rehashed_html_tamper_is_not_accepted(self):
        candidate = self.build()
        altered = self.rewrite(candidate, 'index.html', self.original['index.html']+b'<p>extra</p>')
        with self.assertRaises(ValueError): validate_candidate(altered, config=CONFIG)

    def test_rehashed_search_tamper_is_not_accepted(self):
        candidate = self.build()
        altered = self.rewrite(candidate, 'search.json', b'[]\n')
        with self.assertRaises(ValueError): validate_candidate(altered, config=CONFIG)

    def test_editorial_manifest_fields_are_not_presentation(self):
        candidate = self.build()
        value = json.loads((candidate.artifact.output/'release-manifest.json').read_text())
        value['article_count'] = 200
        altered = self.rewrite(candidate, 'release-manifest.json', json_bytes(value)+b'\n')
        with self.assertRaises(ValueError): validate_candidate(altered, config=CONFIG)

    def test_changed_base_bytes_are_rejected(self):
        candidate = self.build(); (self.base.output/'index.html').write_bytes(b'changed')
        with self.assertRaises(ValueError): validate_candidate(candidate, config=CONFIG)

    def test_wrong_site_and_identity_are_rejected(self):
        candidate = self.build()
        for changes in ({'site': {}}, {'source_commit': 'wrong'}, {'source_job': 'PUB0001'}, {'assets': ()}, {'assets': ('assets/a.js', 'assets/a.js')}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_candidate(replace(candidate, **changes), config=CONFIG)

    def test_cannot_overwrite_or_nest_in_base(self):
        for path in (self.base.output, self.base.output/'nested'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.build(output=path)
        self.assertEqual(read_files(self.base.output), self.original)

    def test_symlink_output_parent_is_rejected(self):
        link = self.root/'alias'; link.symlink_to(self.root/'releases', target_is_directory=True)
        with self.assertRaises(ValueError): self.build(output=link/'candidate')

    def test_overlay_is_bounded_utf8(self):
        for value in (b'\xff', 'not bytes', b'x'*2_000_001):
            with self.subTest(kind=type(value).__name__), self.assertRaises((ValueError, UnicodeError)):
                self.build(overlay={'assets/effect.js': value})

    def test_candidate_cannot_hide_added_file(self):
        candidate = self.build(); (candidate.artifact.output/'extra.txt').write_text('extra')
        with self.assertRaises(ValueError): validate_candidate(candidate, config=CONFIG)

    def test_candidate_record_unknown_fields_rejected(self):
        value = dict(self.build().as_record(), unexpected=True)
        with self.assertRaises(ValueError): PresentationCandidate.from_record(value)


if __name__ == '__main__': unittest.main()
