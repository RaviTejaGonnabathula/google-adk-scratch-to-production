import unittest
from unittest.mock import MagicMock

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from agents.master.factory import build_agent
from composition.builder import build_application
from tools.contracts import AdapterError, AuthorizationContext
from tools.faq import MockFAQAdapter, get_tools
from tests.support import offline
from tests.test_architecture import FAQ, RAG, SCHEDULER
from tests.test_composition_config import selection


def response(text=None, name=None, args=None):
    part = types.Part(text=text) if text is not None else types.Part(function_call=types.FunctionCall(name=name, args=args))
    return LlmResponse(content=types.Content(role="model", parts=[part]))


class ScriptedModel(BaseLlm):
    replies: list[LlmResponse]
    requests: list = []

    async def generate_content_async(self, llm_request, stream=False):
        self.requests.append(llm_request.model_copy(deep=True))
        if not self.replies:
            raise AssertionError("Unexpected model call")
        yield self.replies.pop(0)


async def run_graph(specification, scripts):
    models = {}
    def model_factory(name):
        models[name] = ScriptedModel(model="offline", replies=scripts[name])
        return models[name]
    master = build_application(master_factory=build_agent, specification=specification, model_factory=model_factory)
    sessions = InMemorySessionService()
    await sessions.create_session(app_name="test_app", user_id="test-user", session_id="test-session")
    runner = Runner(app_name="test_app", agent=master, session_service=sessions)
    try:
        events = [event async for event in runner.run_async(user_id="test-user", session_id="test-session", new_message=types.Content(role="user", parts=[types.Part(text="Run the synthetic example")]))]
    finally:
        await runner.close()
    return events, models


class BehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_faq_function_executes_through_runner(self):
        with offline():
            events, models = await run_graph(selection(FAQ), {"master_agent": [response(name="lookup_faq", args={"question": "hours"}), response(text="Synthetic FAQ answer")]})
        results = [part.function_response.response for event in events if event.content for part in event.content.parts if part.function_response]
        self.assertEqual(results[0]["status"], "success")
        self.assertTrue(results[0]["data"]["found"])
        self.assertEqual(len(models["master_agent"].requests), 2)

    async def test_delegation_runs_specialist_and_availability_tool(self):
        with offline():
            events, models = await run_graph(selection(SCHEDULER), {
                "master_agent": [response(name="transfer_to_agent", args={"agent_name": "scheduler_agent"})],
                "scheduler_agent": [response(name="check_slots", args={"day": "2026-11-20"}), response(text="Synthetic slots only")],
            })
        self.assertEqual(events[-1].author, "scheduler_agent")
        results = [part.function_response.response for event in events if event.content for part in event.content.parts if part.function_response and part.function_response.name == "check_slots"]
        self.assertEqual(results[0]["data"]["times"], ["09:00", "14:00"])
        self.assertEqual(len(models["scheduler_agent"].requests), 2)

    async def test_agent_tool_returns_rag_result_to_master(self):
        with offline():
            events, models = await run_graph(selection(RAG), {
                "master_agent": [response(name="rag_agent", args={"request": "Find onboarding instructions"}), response(text="Master received the synthetic document answer")],
                "rag_agent": [response(name="retrieve_documents", args={"query": "onboarding"}), response(text="Synthetic source demo-001")],
            })
        self.assertEqual(events[-1].author, "master_agent")
        results = [part.function_response.response for event in events if event.content for part in event.content.parts if part.function_response and part.function_response.name == "rag_agent"]
        self.assertIn("demo-001", str(results))
        retrieved = [part.function_response.response for content in models["rag_agent"].requests[-1].contents for part in content.parts if part.function_response]
        self.assertEqual(retrieved[0]["data"]["documents"][0]["id"], "demo-001")

    async def test_authorization_uses_injected_context_not_session_claims(self):
        context = MagicMock(spec=ToolContext)
        context.state = {"user_id": "admin", "tenant": "demo", "scopes": ["faq:read"]}
        for identity in (AuthorizationContext("reader", "other-tenant", frozenset({"faq:read"})), AuthorizationContext("reader", "demo", frozenset())):
            adapter = MagicMock(wraps=MockFAQAdapter())
            tool = get_tools(adapter=adapter, authorization=lambda _: identity)[0]
            with offline():
                result = await tool.run_async(args={"question": "hours"}, tool_context=context)
            self.assertEqual(result["error"], "not_authorized")
            adapter.lookup.assert_not_called()

    async def test_validation_timeouts_and_provider_failures_are_structured(self):
        context = MagicMock(spec=ToolContext)
        adapter = MagicMock(wraps=MockFAQAdapter())
        tool = get_tools(adapter=adapter)[0]
        for value in ("", " " * 10, "x" * 501):
            result = await tool.run_async(args={"question": value}, tool_context=context)
            self.assertEqual(result["error"], "invalid_input")
        adapter.lookup.assert_not_called()
        for failure, code in ((TimeoutError("private detail"), "adapter_timeout"), (AdapterError("private detail"), "adapter_unavailable")):
            adapter.lookup.side_effect = failure
            result = await tool.run_async(args={"question": "hours"}, tool_context=context)
            self.assertEqual(result, {"status": "error", "data": {}, "error": code})
