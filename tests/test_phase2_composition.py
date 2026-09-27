"""Explicit constructor doubles, not a running Pressroom MCP acceptance test."""
import sys
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch

from confluence_release.runtime_composition import create_pressroom_core
from phase2_support import CONFIG


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.services=ModuleType('pressroom.services')
        self.services.PressroomToolCore=lambda *a,**k:self.calls.append((a,k)) or k
        self.services.PublicationWorkflow=lambda *a:SimpleNamespace(arguments=a)
        self.existing=(SimpleNamespace(key='ai-inner-life'),)
    def call(self,existing=None):
        with patch.dict(sys.modules,{'pressroom.services':self.services}),patch(
            'confluence_release.runtime_composition.HereNowDestinationAdapter',
            return_value=SimpleNamespace(key='confluence')):
            return create_pressroom_core('factory',config=CONFIG,manuscripts='gateway',
                approvals='existing-approvals',existing_destinations=self.existing if existing is None else existing)
    def test_existing_approval_services_reused(self):
        result=self.call()
        self.assertEqual(result['approvals'],'existing-approvals')
        self.assertEqual(self.calls[0][0][0],'gateway')
    def test_existing_destination_not_replaced(self):
        result=self.call()
        self.assertEqual([d.key for d in result['publication_workflow'].arguments[1]],['ai-inner-life','confluence'])
        self.assertEqual(len(self.existing),1)
    def test_duplicate_destination_not_silently_changed(self):
        with self.assertRaises(ValueError):self.call((SimpleNamespace(key='confluence'),))
