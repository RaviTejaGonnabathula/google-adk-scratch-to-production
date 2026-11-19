"""Fresh master construction, independent of the exported application instance."""
from google.adk.agents import Agent

from ..models import build_model


def build_agent(*, model=None, tools=(), sub_agents=()):
    return Agent(
        name="master_agent",
        description="This is the master agent that orchestrates the other agents.",
        instruction=("You are a helpful assistant." if not tools and not sub_agents else
                     "You are a helpful assistant. Use the available FAQ tool for FAQs, transfer scheduling questions "
                     "to the scheduling specialist, and call the RAG specialist tool for document questions. "
                     "All example data is synthetic. Never claim to have made a booking or performed a real write."),
        model=model if model is not None else build_model(), tools=list(tools), sub_agents=list(sub_agents),
    )
