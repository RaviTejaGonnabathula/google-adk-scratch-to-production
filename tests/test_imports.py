import tempfile
import unittest
from pathlib import Path

from deploy.agentruntime.package_sources import prepare_sources
from tests.support import ROOT, isolated_python
from tests.support import offline


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_adk_api_server_discovers_root_package(self):
        import httpx
        from google.adk.cli.fast_api import get_fast_api_app
        with offline():
            app = get_fast_api_app(agents_dir=str(ROOT / "agents"), web=False, use_local_storage=False)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    result = await client.get("/list-apps")
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json(), ["agents"])


class ImportTests(unittest.TestCase):
    def test_entry_aliases_and_adk_loader(self):
        script = """
import runpy
from pathlib import Path
import agents
from agents.agent import root_agent
from agents.master import master_agent
from google.adk.cli.utils.agent_loader import AgentLoader
assert agents.root_agent is root_agent is master_agent
loader = AgentLoader(str(Path(agents.__file__).parent))
assert loader.load_agent(loader.list_agents()[0]) is root_agent
assert not root_agent.tools and not root_agent.sub_agents
"""
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "source"
            prepare_sources(ROOT, destination)
            isolated_python([destination], script, temporary)
            for entry in (ROOT / "agent.py", ROOT / "app/src/agent.py"):
                isolated_python([ROOT], f"import runpy; result = runpy.run_path({str(entry)!r}); assert result['root_agent'].name == 'master_agent'", temporary)
            isolated_python([ROOT], """
from google.adk.cli.utils.agent_loader import AgentLoader
from pathlib import Path
import agents
loader = AgentLoader(str(Path(agents.__file__).parents[1] / 'app/src'))
assert loader.load_agent(loader.list_agents()[0]) is agents.root_agent
""", temporary)

    def test_factories_import_without_settings_or_constructed_exports(self):
        isolated_python([ROOT], """
import os, sys
os.environ.pop('ADK_MODEL_NAME', None)
os.environ.pop('ADK_MODEL_LOCATION', None)
from unittest.mock import patch
with patch('agents.model_settings.resolve_model_settings', side_effect=AssertionError('Eager model setup')):
    from agents.master.factory import build_agent
    import composition.registry
assert 'agents.master.agent' not in sys.modules
assert 'agents.agent' not in sys.modules
""", ROOT)

    def test_unselected_and_disabled_capabilities_are_not_imported(self):
        cases = [([], []), ([{"name": "faq", "integration": "direct_tool"}], ["tools.faq"]),
                 ([{"name": "rag", "integration": "agent_tool", "enabled": False}], [])]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "source"
            prepare_sources(ROOT, destination)
            for selected, allowed in cases:
                with self.subTest(selected=selected):
                    script = f"""
import importlib.abc, sys
allowed = {allowed!r}
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.startswith('agents.sub_agents.') or any(fullname.startswith('tools.' + name) for name in ('faq','scheduler','rag','database','human_escalation','api_integration'))) and fullname not in allowed:
            raise AssertionError('Unselected module imported: ' + fullname)
sys.meta_path.insert(0, Guard())
from agents.master.factory import build_agent
from composition.builder import build_application
app = build_application(master_factory=build_agent, specification={{'schema_version': 1, 'capabilities': {selected!r}}})
"""
                    isolated_python([destination], script, temporary)
