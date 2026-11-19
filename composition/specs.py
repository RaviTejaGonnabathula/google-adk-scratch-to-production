"""Strict, immutable capability selections, independent of ADK imports."""
from dataclasses import dataclass
from enum import StrEnum


class ConfigurationError(ValueError):
    """Invalid composition input; messages never include configuration values."""


class Capability(StrEnum):
    FAQ = "faq"
    SCHEDULER = "scheduler"
    RAG = "rag"
    DATABASE = "database"
    HUMAN_ESCALATION = "human_escalation"
    API_INTEGRATION = "api_integration"


class Integration(StrEnum):
    DIRECT_TOOL = "direct_tool"
    SUB_AGENT = "sub_agent"
    AGENT_TOOL = "agent_tool"


@dataclass(frozen=True)
class CapabilitySpec:
    name: Capability
    integration: Integration
    enabled: bool = True
    adapter: str = "mock"

    def __post_init__(self):
        if not isinstance(self.name, Capability) or not isinstance(self.integration, Integration):
            raise ConfigurationError("Unknown capability or integration identifier.")
        if type(self.enabled) is not bool:
            raise ConfigurationError("enabled must be a boolean.")
        if not isinstance(self.adapter, str) or not self.adapter.strip():
            raise ConfigurationError("adapter must be a nonempty identifier.")


@dataclass(frozen=True)
class CompositionSpec:
    capabilities: tuple[CapabilitySpec, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ConfigurationError("Only schema_version: 1 is supported.")
        if not isinstance(self.capabilities, tuple) or any(not isinstance(c, CapabilitySpec) for c in self.capabilities):
            raise ConfigurationError("Typed capabilities must be a tuple of CapabilitySpec values.")
        names = [c.name for c in self.capabilities]
        if len(names) != len(set(names)):
            raise ConfigurationError("Duplicate capability names are not allowed, including disabled entries.")

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return value
        # [] is the explicit programmatic master-only shorthand, not a file format.
        if isinstance(value, list) and not value:
            return cls()
        if not isinstance(value, dict) or set(value) != {"schema_version", "capabilities"}:
            raise ConfigurationError("Specification requires exactly schema_version and capabilities.")
        if not isinstance(value["capabilities"], list):
            raise ConfigurationError("capabilities must be a list.")
        selections = []
        for entry in value["capabilities"]:
            if not isinstance(entry, dict) or not {"name", "integration"} <= set(entry):
                raise ConfigurationError("Each capability requires name and integration.")
            if set(entry) - {"name", "integration", "enabled", "adapter"}:
                raise ConfigurationError("Unknown capability fields.")
            try:
                name, integration = Capability(entry["name"]), Integration(entry["integration"])
            except (ValueError, TypeError):
                raise ConfigurationError("Unknown capability or integration identifier.") from None
            selections.append(CapabilitySpec(name, integration, entry.get("enabled", True), entry.get("adapter", "mock")))
        return cls(tuple(selections), value["schema_version"])
