from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode

DEFAULT_MAX_YAML_BYTES = 1024 * 1024


class ContractYamlError(yaml.YAMLError):
    """Sanitized failure raised before contract model validation."""


class StrictContractLoader(yaml.SafeLoader):
    """Safe YAML loader with unambiguous mappings and no aliases."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            raise ContractYamlError("YAML aliases are not allowed")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, MappingNode):
            raise ContractYamlError("YAML mapping is malformed")
        keys: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
            except TypeError as error:
                raise ContractYamlError("YAML mapping keys must be scalar") from error
            if duplicate:
                raise ContractYamlError("duplicate YAML key is not allowed")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_bounded_yaml(path: Path, *, max_bytes: int = DEFAULT_MAX_YAML_BYTES) -> Any:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    with path.open("rb") as source:
        encoded = source.read(max_bytes + 1)
    if len(encoded) > max_bytes:
        raise ContractYamlError("YAML exceeds the maximum encoded size")
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractYamlError("YAML must be UTF-8") from error
    try:
        return yaml.load(text, Loader=StrictContractLoader)
    except RecursionError as error:
        raise ContractYamlError("YAML nesting is too deep") from error
