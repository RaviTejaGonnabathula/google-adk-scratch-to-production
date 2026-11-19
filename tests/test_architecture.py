import inspect
import unittest

from agents.master.factory import build_agent
from composition.builder import build_application
from composition.specs import ConfigurationError
from tools.faq import MockFAQAdapter
from tools.contracts import mock_authorization
from tests.support import offline
from tests.test_composition_config import selection

FAQ = {"name": "faq", "integration": "direct_tool"}
SCHEDULER = {"name": "scheduler", "integration": "sub_agent"}
RAG = {"name": "rag", "integration": "agent_tool"}


class ArchitectureTests(unittest.TestCase):
    def test_master_individual_and_mixed_graphs(self):
        cases = [((), [], []), ((FAQ,), ["lookup_faq"], []),
                 ((SCHEDULER,), [], ["scheduler_agent"]), ((RAG,), ["rag_agent"], []),
                 ((FAQ, SCHEDULER, RAG), ["lookup_faq", "rag_agent"], ["scheduler_agent"])]
        with offline():
            for entries, tools, children in cases:
                with self.subTest(entries=entries):
                    master = build_application(master_factory=build_agent, specification=selection(*entries))
                    self.assertEqual(master.name, "master_agent")
                    self.assertEqual([tool.name for tool in master.tools], tools)
                    self.assertEqual([child.name for child in master.sub_agents], children)
                    for child in master.sub_agents:
                        self.assertIs(child.parent_agent, master)

    def test_fresh_instances_and_adapter_state(self):
        adapters = []
        def new_adapter():
            adapter = MockFAQAdapter()
            adapters.append(adapter)
            return adapter
        with offline():
            graphs = [build_application(master_factory=build_agent, specification=selection(FAQ), adapter_factories={"faq": new_adapter}) for _ in range(2)]
            mixed = [build_application(master_factory=build_agent, specification=selection(SCHEDULER, RAG)) for _ in range(2)]
        self.assertIsNot(graphs[0], graphs[1])
        self.assertIsNot(graphs[0].tools[0], graphs[1].tools[0])
        self.assertIsNot(adapters[0], adapters[1])
        result = adapters[0].lookup("hours", mock_authorization(None))
        result["answer"] = "changed by caller"
        self.assertNotEqual(adapters[1].lookup("hours", mock_authorization(None))["answer"], result["answer"])
        self.assertIsNot(mixed[0].sub_agents[0], mixed[1].sub_agents[0])
        self.assertIsNot(mixed[0].tools[0].agent, mixed[1].tools[0].agent)

    def test_adapter_results_cannot_change_later_sessions(self):
        from tools.scheduler import MockSchedulingAdapter
        from tools.rag import MockRetrievalAdapter
        context = mock_authorization(None)
        scheduler = MockSchedulingAdapter()
        scheduler.check_slots("2026-11-20", context)["times"].clear()
        self.assertEqual(scheduler.check_slots("2026-11-20", context)["times"], ["09:00", "14:00"])
        retriever = MockRetrievalAdapter()
        retriever.retrieve("onboarding", context)["documents"][0]["text"] = "tampered"
        self.assertNotEqual(retriever.retrieve("onboarding", context)["documents"][0]["text"], "tampered")

    def test_disabled_configuration_needs_no_adapter(self):
        with offline():
            app = build_application(master_factory=build_agent, specification=selection(
                {"name": "database", "integration": "sub_agent", "enabled": False, "adapter": "future-provider"}
            ), adapter_factories={})
        self.assertEqual(app.tools, [])
        self.assertEqual(app.sub_agents, [])

    def test_tools_only_expose_business_arguments(self):
        with offline():
            master = build_application(master_factory=build_agent, specification=selection(FAQ, SCHEDULER, RAG))
        candidates = [(master.tools[0], "question"), (master.sub_agents[0].tools[0], "day"), (master.tools[1].agent.tools[0], "query")]
        for tool, argument in candidates:
            declaration = tool._get_declaration().model_dump(exclude_none=True)
            schema = declaration.get("parameters_json_schema", declaration.get("parameters"))
            self.assertEqual(set(schema["properties"]), {argument})
            self.assertNotIn("adapter", inspect.signature(tool.func).parameters)

    def test_missing_and_invalid_adapters_fail(self):
        for kwargs in ({"adapter_factories": {}}, {"adapter_factories": {"faq": lambda: object()}}, {"authorization": "model-user-id"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError), offline():
                build_application(master_factory=build_agent, specification=selection(FAQ), **kwargs)
