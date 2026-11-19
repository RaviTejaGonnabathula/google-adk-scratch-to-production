"""Factory for the AgentTool retrieval demonstration."""
from google.adk.agents import Agent

from agents.models import build_model
from tools.rag import get_tools


def build_agent(*, adapter, authorization, model=None):
    return Agent(
        name="rag_agent", description="Retrieves and summarizes synthetic reference documents.",
        instruction="Use retrieve_documents. Answer only from returned documents, cite their IDs, and disclose when no match exists.",
        model=model if model is not None else build_model(),
        tools=get_tools(adapter=adapter, authorization=authorization),
    )
