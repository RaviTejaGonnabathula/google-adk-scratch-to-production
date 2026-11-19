import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from deploy.agentruntime.package_sources import check_sources, prepare_sources
from tests.support import ROOT, isolated_python, offline


def stage_runtime(source, artifact):
    """Execute ADK's real packaging implementation; replace only cloud client I/O."""
    from google.adk.cli import cli_deploy
    from google.adk.dependencies._agentplatform import agentplatform

    with tempfile.TemporaryDirectory(prefix="adk-test-sdk-") as temporary:
        temporary = Path(temporary)
        build = temporary / "sdk-build"
        config = temporary / "runtime.json"
        config.write_text(json.dumps({"env_vars": {"ADK_MODEL_NAME": "offline-model", "ADK_MODEL_LOCATION": "us"}}))
        client = MagicMock()

        def capture(*, name, config):
            assert config["source_packages"] == ["agents/agents", "Dockerfile", "tools", "composition"]
            shutil.copytree(build, artifact)

        client.runtimes.update.side_effect = capture
        with offline(), patch.object(agentplatform, "Client", return_value=client), contextlib.redirect_stdout(io.StringIO()):
            cli_deploy.to_agent_engine(
                agent_folder=str(source / "agents"),
                extra_packages=[str(source / "tools"), str(source / "composition")],
                temp_folder=str(build), project="offline-project", region="us-central1",
                agent_engine_id="123", agent_engine_config_file=str(config),
                absolutize_imports=False, skip_agent_import_validation=False,
            )
        client.runtimes.update.assert_called_once()
        client.runtimes.create.assert_not_called()
        client.runtimes.delete.assert_not_called()


class PackagingTests(unittest.TestCase):
    def test_staging_omits_local_runtime_data_and_rejects_ambient_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            prepare_sources(ROOT, source)
            for package in ("agents", "tools", "composition"):
                runtime = source / package / ".adk"
                runtime.mkdir()
                (runtime / "session.db").write_text("synthetic-secret-fixture")
                with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": str(source / package / "__init__.py")}):
                    with self.assertRaisesRegex(ValueError, "Credentials must be outside"):
                        check_sources(source)
            artifact = Path(temporary) / "staged"
            prepare_sources(source, artifact)
            self.assertFalse(list(artifact.rglob(".adk")))

    def test_selected_manifests_survive_both_deployment_paths(self):
        from tests.test_architecture import FAQ, SCHEDULER, RAG
        import yaml
        for entries in ([], [FAQ], [SCHEDULER], [RAG], [FAQ, SCHEDULER, RAG]):
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as temporary:
                temporary = Path(temporary)
                source, artifact = temporary / "source", temporary / "runtime"
                prepare_sources(ROOT, source)
                manifest = source / "agents/capabilities.yaml"
                manifest.write_text(yaml.safe_dump({"schema_version": 1, "capabilities": entries}))
                stage_runtime(source, artifact)
                expected_tools = [name for entry, name in ((FAQ, "lookup_faq"), (RAG, "rag_agent")) if entry in entries]
                expected_children = ["scheduler_agent"] if SCHEDULER in entries else []
                script = f"""
from pathlib import Path
import agents, composition, tools
root = agents.root_agent
assert [t.name for t in root.tools] == {expected_tools!r}
assert [a.name for a in root.sub_agents] == {expected_children!r}
assert not (Path(agents.__file__).parents[1] / 'config/settings.dev.yaml').exists()
"""
                isolated_python([artifact / "agents", artifact], script, temporary)
                self.assertEqual(manifest.read_bytes(), (artifact / "agents/agents/capabilities.yaml").read_bytes())
                # Interpret the actual COPY sources, not a hand-maintained list
                # of assumed container modules. Source packages are guarded by
                # the same preflight used by the real Cloud Run script.
                container = temporary / "cloudrun"
                container.mkdir()
                dockerfile = (ROOT / "Dockerfile").read_text()
                for directive in re.findall(r"^COPY (.+)$", dockerfile, re.M):
                    parts = directive.split()
                    for name in parts[:-1]:
                        origin = source / name if (source / name).exists() else ROOT / name
                        target = container / name
                        if origin.is_dir():
                            shutil.copytree(origin, target)
                        else:
                            shutil.copy2(origin, target)
                isolated_python([container], script + "\nimport agent; assert agent.root_agent is root\n", temporary)
                startup = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
                self.assertEqual(startup[startup.index("api_server") + 1], "agents")
                self.assertEqual(manifest.read_bytes(), (container / "agents/capabilities.yaml").read_bytes())

    def test_requirements_match_locked_export(self):
        result = subprocess.run(["uv", "export", "--locked", "--no-dev", "--no-hashes", "--no-emit-project", "--no-annotate"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
        def dependencies(text):
            return [line for line in text.splitlines() if line and not line.startswith("#")]
        self.assertEqual(dependencies(result.stdout), dependencies((ROOT / "agents/requirements.txt").read_text()))

    def test_sdk_staging_imports_without_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            source, artifact = temporary / "source", temporary / "runtime"
            prepare_sources(ROOT, source)
            stage_runtime(source, artifact)
            output = isolated_python([artifact / "agents", artifact], """
import agents, tools, composition
assert agents.root_agent.name == 'master_agent'
assert not agents.root_agent.tools and not agents.root_agent.sub_agents
from pathlib import Path
assert not (Path(agents.__file__).parents[1] / 'config/settings.dev.yaml').exists()
print('isolated package import passed')
""", temporary)
            self.assertIn("passed", output)
            dockerfile = (artifact / "Dockerfile").read_text()
            self.assertIn('/app/tools/', dockerfile)
            self.assertIn('/app/composition/', dockerfile)
            self.assertIn('PYTHONPATH=', dockerfile)
            self.assertEqual((source / "agents/capabilities.yaml").read_bytes(), (artifact / "agents/agents/capabilities.yaml").read_bytes())
            requirements = (artifact / "agents/agents/requirements.txt").read_text()
            for line in (source / "agents/requirements.txt").read_text().splitlines():
                if line and not line.startswith("#"):
                    self.assertIn(line, requirements)
            self.assertNotIn(b"synthetic-secret-fixture", b"".join(p.read_bytes() for p in artifact.rglob("*") if p.is_file()))

    def test_all_upload_roots_reject_secret_fixtures(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            prepare_sources(ROOT, source)
            for package in ("agents", "tools", "composition"):
                for filename in (".env", ".env.local", "sa-key.json", "settings.dev.yaml", "private.pem"):
                    with self.subTest(package=package, filename=filename):
                        fixture = source / package / filename
                        fixture.write_text("synthetic-secret-fixture")
                        with self.assertRaises(ValueError):
                            check_sources(source)
                        fixture.unlink()
                with self.assertRaisesRegex(ValueError, "Credentials must be outside"):
                    check_sources(source, source / package / "__init__.py")


if __name__ == "__main__":
    unittest.main()
