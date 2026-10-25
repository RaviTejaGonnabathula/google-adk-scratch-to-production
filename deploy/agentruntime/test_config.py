"""Offline tests: no real credentials or cloud requests."""
import tempfile
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import preflight, read_config, runtime_config
from model_settings import resolve_model_settings


class ConfigTests(unittest.TestCase):
    def test_model_only_runtime_environment(self):
        self.assertEqual(runtime_config("us", "test-model"), {"env_vars": {"ADK_MODEL_LOCATION": "us", "ADK_MODEL_NAME": "test-model"}})
        with self.assertRaises(ValueError):
            runtime_config("", "test-model")

    def test_model_location_does_not_change_hosting_region(self):
        root = Path(__file__).resolve().parents[2]
        with patch.dict(os.environ, {"ADK_MODEL_NAME": "test-model", "ADK_MODEL_LOCATION": "us", "GOOGLE_CLOUD_LOCATION": "us-central1"}), patch.object(sys, "path", [str(root / "app/src"), *sys.path]):
            namespace = runpy.run_path(str(root / "app/src/agents/master/agent.py"), run_name="agents.master._test_agent")
            self.assertEqual(namespace["master_agent"].model.client_kwargs["location"], "us")
            self.assertEqual(namespace["master_agent"].model.model, "test-model")
            self.assertEqual(os.environ["GOOGLE_CLOUD_LOCATION"], "us-central1")

    def test_example_model_settings(self):
        root = Path(__file__).resolve().parents[2]
        with patch.dict(os.environ, {}, clear=True):
            settings = resolve_model_settings(root / "config/settings.dev.example.yaml")
            self.assertEqual(settings["model_name"], "gemini-3.5-flash-lite")
            self.assertEqual(settings["model_location"], "us")

    def test_environment_and_argument_precedence(self):
        with patch.dict(os.environ, {"ADK_MODEL_NAME": "env-model", "ADK_MODEL_LOCATION": "eu"}):
            values = resolve_model_settings("nonexistent.yaml")
            self.assertEqual(values, {"model_name": "env-model", "model_location": "eu"})
            values = resolve_model_settings("nonexistent.yaml", model_name="explicit-model", model_location="us")
            self.assertEqual(values, {"model_name": "explicit-model", "model_location": "us"})

    def test_missing_and_invalid_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                resolve_model_settings("nonexistent.yaml")
            with self.assertRaises(ValueError):
                resolve_model_settings("nonexistent.yaml", model_name=" ", model_location="us")
            with self.assertRaises(ValueError):
                resolve_model_settings("nonexistent.yaml", model_name="bad,ENV=value", model_location="us")

    def test_no_private_yaml_needed_in_runtime(self):
        with patch.dict(os.environ, {"ADK_MODEL_NAME": "deployed-model", "ADK_MODEL_LOCATION": "us"}):
            self.assertEqual(resolve_model_settings("nonexistent.yaml")["model_name"], "deployed-model")

    def test_example(self):
        root = Path(__file__).resolve().parents[2]
        config = read_config(root / "config/settings.dev.example.yaml")
        self.assertEqual(config["project_id"], "your-project-id")
        self.assertIsNone(config["credentials_file"])

    def test_reject_numeric_id(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "config/settings.dev.example.yaml").read_text()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"
            path.write_text(source.replace("agent_engine_id: null", "agent_engine_id: 123"))
            with self.assertRaises(ValueError):
                read_config(path)

    @patch("google.auth.transport.requests.AuthorizedSession")
    @patch("google.auth.default", return_value=(object(), None))
    def test_missing_permissions_blocks(self, auth, session):
        response = MagicMock(ok=True)
        response.json.return_value = {"permissions": []}
        session.return_value.post.return_value = response
        with self.assertRaisesRegex(ValueError, "Missing deployment permissions"):
            preflight("example-project", "runtime@example-project.iam.gserviceaccount.com", False)

    @patch("google.auth.transport.requests.AuthorizedSession")
    @patch("google.auth.default", return_value=(object(), None))
    def test_granted_permissions(self, auth, session):
        def respond(url, json, timeout):
            response = MagicMock(ok=True)
            response.json.return_value = json
            return response
        session.return_value.post.side_effect = respond
        preflight("example-project", "runtime@example-project.iam.gserviceaccount.com", True)
        self.assertEqual(session.return_value.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
