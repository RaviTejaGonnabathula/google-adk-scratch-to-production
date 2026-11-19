"""Load the packaged, non-secret manifest without environment overrides."""
from pathlib import Path

import yaml

from .specs import CompositionSpec, ConfigurationError

UNSET = object()


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently taking the last value."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ConfigurationError("Manifest keys must be unique strings.")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_manifest(path, *, optional=False):
    path = Path(path)
    if not path.exists() and optional:
        return CompositionSpec()
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeError):
        raise ConfigurationError("Unable to read the capability manifest.") from None
    except yaml.YAMLError:
        raise ConfigurationError("Malformed capability manifest YAML.") from None
    if not isinstance(value, dict):
        raise ConfigurationError("The manifest must be a mapping with schema_version and capabilities.")
    return CompositionSpec.parse(value)


def resolve_specification(specification=UNSET, *, manifest_path=None, default_manifest_path=None):
    if specification is not UNSET:
        return CompositionSpec.parse(specification)
    if manifest_path is not None:
        return load_manifest(manifest_path)
    if default_manifest_path is not None:
        return load_manifest(default_manifest_path, optional=True)
    return CompositionSpec()
