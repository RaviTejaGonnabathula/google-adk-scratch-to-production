"""Factory for the delegated scheduling demonstration."""
from google.adk.agents import Agent

from agents.models import build_model
from tools.scheduler import get_tools


def build_agent(*, adapter, authorization, model=None):
    return Agent(
        name="scheduler_agent", description="Answers questions about synthetic appointment availability.",
        instruction="Use check_slots to check synthetic availability. Ask for a date if missing. Never book an appointment.",
        model=model if model is not None else build_model(),
        tools=get_tools(adapter=adapter, authorization=authorization),
    )
