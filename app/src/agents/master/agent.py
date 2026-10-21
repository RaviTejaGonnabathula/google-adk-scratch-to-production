from google.adk.agents import Agent

master_agent = Agent(
    name="master_agent",
    description="This is the master agent that orchestrates the other agents.",
    instruction="You are a helpful assistant.",
    model = "gemini-3.5-flash-lite"
)