"""Build a fresh ADK graph after validating the complete selection."""
from .config import UNSET, resolve_specification
from .registry import resolve_factory, validate_selection
from .specs import ConfigurationError, Integration


def build_application(*, master_factory, specification=UNSET, manifest_path=None,
                      default_manifest_path=None, model_factory=None,
                      adapter_factories=None, authorization=None):
    specification = resolve_specification(specification, manifest_path=manifest_path, default_manifest_path=default_manifest_path)
    selected = validate_selection(specification, adapter_factories)
    if not callable(master_factory) or (model_factory is not None and not callable(model_factory)):
        raise ConfigurationError("Agent and model factories must be callable.")
    if authorization is not None and not callable(authorization):
        raise ConfigurationError("Authorization provider must be callable.")
    tools, sub_agents = [], []
    if selected:
        from tools import contracts
        authorization = authorization if authorization is not None else contracts.mock_authorization
        for entry, definition in selected:
            make_adapter = adapter_factories[entry.name] if adapter_factories is not None else resolve_factory(definition.adapter_factory)
            adapter = make_adapter()
            if not isinstance(adapter, getattr(contracts, definition.adapter_protocol)):
                raise ConfigurationError(f"Adapter does not implement the {entry.name} contract.")
            factory = resolve_factory(definition.factory)
            kwargs = {"adapter": adapter, "authorization": authorization}
            if entry.integration == Integration.DIRECT_TOOL:
                tools.extend(factory(**kwargs))
            else:
                specialist = factory(**kwargs, model=model_factory(definition.symbol) if model_factory else None)
                if entry.integration == Integration.SUB_AGENT:
                    sub_agents.append(specialist)
                else:
                    from google.adk.tools import AgentTool
                    tools.append(AgentTool(agent=specialist))
    return master_factory(tools=tools, sub_agents=sub_agents, model=model_factory("master_agent") if model_factory else None)
