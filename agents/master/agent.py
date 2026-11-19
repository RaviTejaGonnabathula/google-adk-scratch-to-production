"""Compatibility export: exactly one composition for the standard ADK entry point."""
from pathlib import Path

from composition.builder import build_application
from .factory import build_agent

master_agent = build_application(
    master_factory=build_agent,
    default_manifest_path=Path(__file__).resolve().parents[1] / "capabilities.yaml",
)
