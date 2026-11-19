"""FAQ operation and an in-memory adapter with synthetic data."""
from dataclasses import dataclass

from google.adk.tools import FunctionTool, ToolContext

from tools.contracts import authorize, execute, mock_authorization, validate_text


@dataclass(frozen=True)
class MockFAQAdapter:
    answers: tuple[tuple[str, str], ...] = (("hours", "Demo support is open 09:00–17:00 UTC on weekdays."),)

    def lookup(self, question, context):
        authorize(context, "faq:read")
        question = validate_text(question).casefold()
        answer = next((value for key, value in self.answers if key in question), None)
        return {"answer": answer, "found": answer is not None, "source": "synthetic-faq"}


def get_tools(*, adapter, authorization=mock_authorization):
    def lookup_faq(question: str, tool_context: ToolContext) -> dict:
        """Look up a question in the approved synthetic FAQ; no external requests."""
        def operation():
            context = authorization(tool_context)
            authorize(context, "faq:read")
            return adapter.lookup(validate_text(question), context)
        return execute(operation)
    return [FunctionTool(lookup_faq)]
