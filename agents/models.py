"""Construct a fresh model wrapper without making a model request."""
from google.adk.models.google_llm import Gemini

from .model_settings import resolve_model_settings


def build_model():
    settings = resolve_model_settings()
    return Gemini(model=settings["model_name"], client_kwargs={"location": settings["model_location"]})
