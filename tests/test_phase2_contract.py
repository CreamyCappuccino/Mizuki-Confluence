from copy import deepcopy
from dataclasses import replace
import unittest
from confluence_release.config import ReleaseConfig, digest
from confluence_release.projection import validate_projection
from confluence_release.release_contract import validate_release_contract, validate_reconcile_dispatch
from phase2_support import CONFIG, article, context, dispatch


class ReleaseContractTests(unittest.TestCase):
    def test_valid_contract(self):
        validate_release_contract(context(), CONFIG)
    def test_approval_is_required(self):
        with self.assertRaises(ValueError):
            validate_release_contract(context(candidate_status='awaiting_approval'), CONFIG)
    def test_payload_recomputed_not_just_two_equal_markers(self):
        with self.assertRaises(ValueError):
            validate_release_contract(context(candidate_payload_sha256='0'*64, attempt_payload_sha256='0'*64), CONFIG)
    def test_each_action_boundary(self):
        for field in ('job_action', 'attempt_action', 'candidate_action'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_release_contract(context(**{field:'unpublish'}), CONFIG)
    def test_response_is_not_silently_an_article(self):
        with self.assertRaises(ValueError):
            validate_release_contract(context(job_action='response_publish'), CONFIG)
    def test_each_pipeline_boundary(self):
        for field in ('job_pipeline_key', 'candidate_pipeline_key'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_release_contract(context(**{field:'ai-inner-life-nol'}), CONFIG)
    def test_config_change_invalidates_old_pipeline(self):
        changed = ReleaseConfig('https://nor.example.invalid/confluence', 'different-site', CONFIG.nor_base)
        self.assertNotEqual(CONFIG.pipeline_key, changed.pipeline_key)
        with self.assertRaises(ValueError):
            validate_release_contract(context(), changed)
    def test_discovery_change_is_not_silent(self):
        c = context(destination_config={**CONFIG.public_config, 'sitemap':True})
        with self.assertRaises(ValueError):
            validate_release_contract(c, CONFIG)
    def test_configuration_is_stable(self):
        self.assertEqual(CONFIG.pipeline_key, CONFIG.pipeline_key)
        self.assertLessEqual(len(CONFIG.pipeline_key),120)
    def test_invalid_base_urls(self):
        for url in ('http://x.invalid', 'https://u:p@x.invalid', 'https://x.invalid/../x',
                    'https://x.invalid/%2e', 'https://x.invalid?a=1', 'https://x.invalid/#x',
                    'https://x.invalid/ a', 'https://x.invalid/a//b'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ReleaseConfig(url,'synthetic-site',url)
    def test_invalid_slug(self):
        with self.assertRaises(ValueError):
            ReleaseConfig(CONFIG.site_base,'x/../ail',CONFIG.nor_base)
    def test_dispatch_is_the_approved_attempt(self):
        c = context()
        validate_reconcile_dispatch(c, dispatch(c))
        d = dispatch(c); d.attempt_ref='PUB99990002'
        with self.assertRaises(ValueError):
            validate_reconcile_dispatch(c,d)
    def test_dispatch_edited_payload_is_rejected(self):
        c = context(); d=dispatch(c); d.payload_snapshot['title']='different'
        with self.assertRaises(ValueError):
            validate_reconcile_dispatch(c,d)
    def test_projection_null_model_is_fine(self):
        validate_projection((article(),))
    def test_projection_private_rejected(self):
        a=article(); p={**a.payload,'visibility':'private'}
        with self.assertRaises(ValueError):
            validate_projection((replace(a,payload=p,payload_sha256=digest(p)),))
    def test_duplicate_projection(self):
        with self.assertRaises(ValueError):
            validate_projection((article(),article()))
    def test_noncanonical_author_not_invented(self):
        a=article(); p={**a.payload,'authors':[], 'author_label':None}
        validate_projection((replace(a,payload=p,payload_sha256=digest(p)),))

if __name__=='__main__':unittest.main()
