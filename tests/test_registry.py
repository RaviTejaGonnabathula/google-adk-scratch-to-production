import unittest
from unittest.mock import patch

from composition.builder import build_application
from composition.specs import ConfigurationError
from tests.test_architecture import FAQ, RAG, SCHEDULER
from tests.test_composition_config import selection


class RegistryTests(unittest.TestCase):
    def test_entire_selection_validated_before_any_factory(self):
        for bad in ({**SCHEDULER, "integration": "agent_tool"}, {**RAG, "integration": "sub_agent"},
                    {"name": "database", "integration": "direct_tool"}, {**RAG, "adapter": "live"}):
            with self.subTest(bad=bad), patch("composition.builder.resolve_factory", side_effect=AssertionError("Factory resolved before validation")), self.assertRaises(ConfigurationError):
                build_application(master_factory=lambda **kw: None, specification=selection(FAQ, bad))

    def test_all_required_injected_factories_checked_before_build(self):
        calls = []
        with self.assertRaisesRegex(ConfigurationError, "Missing adapter factory"):
            build_application(master_factory=lambda **kw: None, specification=selection(FAQ, RAG), adapter_factories={"faq": lambda: calls.append("called")})
        self.assertEqual(calls, [])
