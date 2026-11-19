import tempfile
import unittest
from pathlib import Path

from composition.config import load_manifest, resolve_specification
from composition.specs import CompositionSpec, ConfigurationError


def selection(*entries):
    return {"schema_version": 1, "capabilities": list(entries)}


class ConfigTests(unittest.TestCase):
    def test_empty_and_default_enabled(self):
        self.assertEqual(CompositionSpec.parse([]), CompositionSpec())
        value = CompositionSpec.parse(selection({"name": "faq", "integration": "direct_tool"}))
        self.assertTrue(value.capabilities[0].enabled)
        self.assertEqual(value.capabilities[0].adapter, "mock")

    def test_strict_fields_and_duplicates(self):
        faq = {"name": "faq", "integration": "direct_tool"}
        bad = [None, {}, [], {"schema_version": True, "capabilities": []},
               {"schema_version": 1.0, "capabilities": []}, {"schema_version": 2, "capabilities": []},
               {**selection(), "extra": True}, selection({**faq, "enabled": "false"}),
               selection({**faq, "enabled": 0}), selection({**faq, "adapter": None}),
               selection({**faq, "extra": 1}), selection({**faq, "name": "unknown", "enabled": False}),
               selection({**faq, "integration": "unknown"}), selection({"name": "faq"}),
               selection(faq, {**faq, "enabled": False}), {"schema_version": 1, "capabilities": {}}]
        # [] is allowed only as an explicit programmatic empty selection.
        for value in bad:
            if value == []:
                continue
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                CompositionSpec.parse(value)

    def test_loader_missing_malformed_and_explicit_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capabilities.yaml"
            self.assertEqual(load_manifest(path, optional=True), CompositionSpec())
            with self.assertRaises(ConfigurationError):
                load_manifest(path)
            self.assertEqual(resolve_specification([], manifest_path=path), CompositionSpec())
            for invalid in ("", "[]", "schema_version: [", "schema_version: 1\nschema_version: 1\ncapabilities: []", "schema_version: 1\ncapabilities:\n  - name: faq\n    name: rag\n    integration: direct_tool"):
                path.write_text(invalid)
                with self.subTest(invalid=invalid), self.assertRaises(ConfigurationError):
                    load_manifest(path, optional=True)
            path.write_text("schema_version: 1\ncapabilities: []\n")
            self.assertEqual(load_manifest(path), CompositionSpec())
            self.assertEqual(resolve_specification(default_manifest_path=path), CompositionSpec())
