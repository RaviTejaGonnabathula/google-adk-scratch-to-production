"""Shared model settings: explicit overrides > ADK environment > local YAML."""
import os
import re
from pathlib import Path

import yaml


def resolve_model_settings(path=None, *, model_name=None, model_location=None):
    path = Path(path) if path else Path(__file__).resolve().parents[3] / "config/settings.dev.yaml"
    application = {}
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError("Invalid settings YAML.") from None
        if not isinstance(data, dict) or not isinstance(data.get("application", {}), dict):
            raise ValueError("application must be a YAML mapping.")
        application = data.get("application", {})
    elif model_name is None and not os.environ.get("ADK_MODEL_NAME"):
        raise ValueError("Set application.model_name in config/settings.dev.yaml or ADK_MODEL_NAME.")
    values = {}
    for key, explicit, variable in [
        ("model_name", model_name, "ADK_MODEL_NAME"),
        ("model_location", model_location, "ADK_MODEL_LOCATION"),
    ]:
        value = explicit if explicit is not None else os.environ.get(variable, application.get(key))
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Set application.{key} or {variable} to a nonempty string.")
        value = value.strip()
        # Safe for CLI environment transport; model resource names may contain slashes.
        pattern = r"[A-Za-z0-9][A-Za-z0-9._/-]*" if key == "model_name" else r"[a-z][a-z0-9-]*"
        if not re.fullmatch(pattern, value):
            raise ValueError(f"Invalid {key} format.")
        values[key] = value
    return values
