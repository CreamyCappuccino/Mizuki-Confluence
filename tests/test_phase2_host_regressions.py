"""RLY2923 constructor/input regressions using explicit boundary doubles.

These tests execute the actual composition and probe request builder. They do
not substitute for real Pressroom writer-profile read/write or PG chain tests.
Private module names and scoped patches avoid polluting the other test suites.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _composition():
    namespace = '_confluence_rly2923_boundary'
    package = ModuleType(namespace)
    package.__path__ = []
    adapter = ModuleType(namespace + '.adapter')
    adapter.HereNowDestinationAdapter = Mock(return_value=SimpleNamespace(key='confluence'))
    pressroom = ModuleType('pressroom')
    pressroom.__path__ = []
    services = ModuleType('pressroom.services')

    def constructor(manuscripts, destinations, *, publication_workflow, approvals,
                    responses, editorial_state, system, writer_profiles=None):
        return SimpleNamespace(manuscripts=manuscripts, destinations=destinations,
            publication_workflow=publication_workflow, approvals=approvals,
            responses=responses, editorial_state=editorial_state, system=system,
            writer_profiles=writer_profiles)

    services.PressroomToolCore = Mock(side_effect=constructor)
    services.PublicationWorkflow = Mock(side_effect=lambda sf, ds:
        SimpleNamespace(session_factory=sf, destinations=ds))
    with patch.dict(sys.modules, {namespace: package, namespace + '.adapter': adapter,
                                 'pressroom': pressroom, 'pressroom.services': services}):
        module = _load(namespace + '.runtime_composition',
                       ROOT / 'src/confluence_release/runtime_composition.py')
        yield module, adapter, services


class HostCompositionRegressions(unittest.TestCase):
    def setUp(self):
        self.sf, self.config = object(), object()
        self.host = {name: object() for name in (
            'manuscripts', 'approvals', 'responses', 'editorial_state', 'system',
            'writer_profiles')}
        self.existing = (SimpleNamespace(key='ai-inner-life'),)

    def call(self, module, **overrides):
        values = dict(config=self.config, existing_destinations=self.existing, **self.host)
        values.update(overrides)
        return module.create_pressroom_core(self.sf, **values)

    def test_writer_profiles_service_is_forwarded_by_identity(self):
        with _composition() as (module, adapter, services):
            result = self.call(module)
            self.assertIs(result.writer_profiles, self.host['writer_profiles'])
            self.assertIs(services.PressroomToolCore.call_args.kwargs['writer_profiles'],
                          self.host['writer_profiles'])

    def test_all_existing_host_services_are_preserved(self):
        with _composition() as (module, adapter, services):
            result = self.call(module)
            for name, original in self.host.items():
                with self.subTest(service=name):
                    self.assertIs(getattr(result, name), original)
            services.PressroomToolCore.assert_called_once()

    def test_existing_destinations_and_workflow_share_the_same_objects(self):
        with _composition() as (module, adapter, services):
            result = self.call(module)
            self.assertIs(result.destinations[0], self.existing[0])
            self.assertIs(result.destinations[1], adapter.HereNowDestinationAdapter.return_value)
            self.assertIs(result.publication_workflow.destinations, result.destinations)
            self.assertIs(result.publication_workflow.session_factory, self.sf)
            self.assertEqual(len(self.existing), 1)
            adapter.HereNowDestinationAdapter.assert_called_once_with(self.sf, self.config)

    def test_optional_profiles_remain_none_without_fabricated_service(self):
        with _composition() as (module, adapter, services):
            args = dict(self.host)
            del args['writer_profiles']
            result = module.create_pressroom_core(self.sf, config=self.config, **args)
            self.assertIsNone(result.writer_profiles)
            self.assertIn('writer_profiles', services.PressroomToolCore.call_args.kwargs)
            self.assertIsNone(services.PressroomToolCore.call_args.kwargs['writer_profiles'])

    def test_falsey_but_configured_profile_service_is_not_discarded(self):
        class EmptyProfileService:
            def __bool__(self):
                return False
        profiles = EmptyProfileService()
        with _composition() as (module, adapter, services):
            self.assertIs(self.call(module, writer_profiles=profiles).writer_profiles, profiles)

    def test_duplicate_destination_rejected_before_new_components(self):
        with _composition() as (module, adapter, services):
            with self.assertRaisesRegex(ValueError, 'already composed'):
                self.call(module, existing_destinations=(SimpleNamespace(key='confluence'),))
            adapter.HereNowDestinationAdapter.assert_not_called()
            services.PressroomToolCore.assert_not_called()
            services.PublicationWorkflow.assert_not_called()


@dataclass(frozen=True)
class AuthorInputDouble:
    persona_name: str | None = None
    persona_key: str | None = None
    author_ref: str | None = None
    harness: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class CreateInputDouble:
    action: str
    title: str
    markdown: str
    slug: str
    locale: str
    author: AuthorInputDouble
    actor_name: str
    format: str


def _request():
    pressroom = ModuleType('pressroom')
    pressroom.__path__ = []
    domain, services = ModuleType('pressroom.domain'), ModuleType('pressroom.services')
    domain.AuthorAttributionInput = AuthorInputDouble
    services.ManuscriptManageInput = CreateInputDouble
    with patch.dict(sys.modules, {'pressroom': pressroom, 'pressroom.domain': domain,
                                 'pressroom.services': services}):
        probe = _load('_confluence_rly2923_probe', ROOT / 'tests/phase2_pg_probe.py')
        return probe._synthetic_create_request()


class ProbeInputRegressions(unittest.TestCase):
    def test_new_author_has_explicit_synthetic_persona_key(self):
        request = _request()
        self.assertIsNone(request.author.author_ref)
        self.assertEqual(request.author.persona_key, 'confluence-phase2a-probe')
        self.assertTrue(request.author.persona_key.strip())

    def test_unknown_model_and_existing_author_metadata_preserved(self):
        author = _request().author
        self.assertIsNone(author.model)
        self.assertEqual(author.persona_name, '合成作者')
        self.assertEqual(author.harness, 'Probe')

    def test_request_is_draft_creation_not_publication_or_id_lookup(self):
        request = _request()
        self.assertEqual(request.action, 'create')
        self.assertEqual(request.format, 'json')
        self.assertEqual(request.locale, 'ja')
        self.assertEqual(request.actor_name, 'Confluence synthetic probe')
        self.assertIn('接続確認専用', request.markdown)
        self.assertIsNone(request.author.author_ref)

    def test_separate_probe_requests_share_persona_not_article_slug(self):
        first, second = _request(), _request()
        self.assertEqual(first.author.persona_key, second.author.persona_key)
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(first.slug.startswith('confluence-probe-'))


if __name__ == '__main__':
    unittest.main()
