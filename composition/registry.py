"""Static metadata: importing this module never imports a capability implementation."""
from dataclasses import dataclass
from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType

from .specs import Capability, ConfigurationError, Integration


@dataclass(frozen=True)
class Definition:
    integration: Integration
    factory: str
    adapter_factory: str
    adapter_protocol: str
    symbol: str


REGISTRY = MappingProxyType({
    Capability.FAQ: Definition(Integration.DIRECT_TOOL, "tools.faq:get_tools", "tools.faq:MockFAQAdapter", "FAQAdapter", "lookup_faq"),
    Capability.SCHEDULER: Definition(Integration.SUB_AGENT, "agents.sub_agents.scheduler:build_agent", "tools.scheduler:MockSchedulingAdapter", "SchedulingAdapter", "scheduler_agent"),
    Capability.RAG: Definition(Integration.AGENT_TOOL, "agents.sub_agents.rag:build_agent", "tools.rag:MockRetrievalAdapter", "RetrievalAdapter", "rag_agent"),
})


def validate_selection(specification, adapter_factories=None):
    if adapter_factories is not None and not isinstance(adapter_factories, Mapping):
        raise ConfigurationError("Adapter factories must be a mapping keyed by capability.")
    selected = []
    symbols = {"master_agent"}
    for entry in specification.capabilities:
        if not entry.enabled:
            continue
        definition = REGISTRY.get(entry.name)
        if definition is None or definition.integration != entry.integration:
            raise ConfigurationError(f"Unsupported Phase 2 selection: {entry.name}/{entry.integration}.")
        if entry.adapter != "mock":
            raise ConfigurationError(f"Only the mock adapter is implemented for {entry.name}.")
        if adapter_factories is not None and not callable(adapter_factories.get(entry.name)):
            raise ConfigurationError(f"Missing adapter factory for {entry.name}.")
        if definition.symbol in symbols:
            raise ConfigurationError("Duplicate agent or tool names.")
        symbols.add(definition.symbol)
        selected.append((entry, definition))
    return selected


def resolve_factory(reference):
    # References come exclusively from REGISTRY, never from the YAML manifest.
    module, name = reference.split(":")
    return getattr(import_module(module), name)
