"""Compatibility launcher for the original `adk run/web app/src` commands."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents import root_agent

__all__ = ["root_agent"]
