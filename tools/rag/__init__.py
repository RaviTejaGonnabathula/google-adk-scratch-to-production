"""A fixed synthetic retriever; no embedding or vector-store service."""
from dataclasses import dataclass

from google.adk.tools import FunctionTool, ToolContext

from tools.contracts import authorize, execute, mock_authorization, validate_text


@dataclass(frozen=True)
class MockRetrievalAdapter:
    documents: tuple[tuple[str, str], ...] = (
        ("demo-001", "The demo onboarding guide asks new users to read the FAQ."),
        ("demo-002", "The demo scheduling guide uses UTC availability and does not book appointments."),
    )

    def retrieve(self, query, context):
        authorize(context, "rag:read")
        terms = validate_text(query).casefold().split()
        matches = [{"id": key, "text": text} for key, text in self.documents if any(term in text.casefold() for term in terms)]
        return {"documents": matches, "synthetic": True}


def get_tools(*, adapter, authorization=mock_authorization):
    def retrieve_documents(query: str, tool_context: ToolContext) -> dict:
        """Retrieve relevant synthetic documents and their source identifiers."""
        def operation():
            context = authorization(tool_context)
            authorize(context, "rag:read")
            return adapter.retrieve(validate_text(query), context)
        return execute(operation)
    return [FunctionTool(retrieve_documents)]
