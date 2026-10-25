from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from ..model_settings import resolve_model_settings

settings = resolve_model_settings()
# Model location is independent of the managed runtime's reserved location.
model = Gemini(
    model=settings["model_name"],
    client_kwargs={"location": settings["model_location"]},
)

master_agent = Agent(
    name="master_agent",
    description="This is the master agent that orchestrates the other agents.",
    instruction="You are a helpful assistant.",
    model=model,
)
