from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode

from anvil.assurance.io import FileTooLargeError, NonRegularFileError, read_regular_file

DEFAULT_MAX_YAML_BYTES = 1024 * 1024
DEFAULT_MAX_YAML_NODES = 50_000
DEFAULT_MAX_YAML_DEPTH = 100


class ContractYamlError(yaml.YAMLError):
    """Sanitized failure raised before contract model validation."""


class StrictContractLoader(yaml.SafeLoader):
    """Safe YAML loader with unambiguous mappings and no aliases."""

    def __init__(
        self,
        stream: Any,
        *,
        max_nodes: int = DEFAULT_MAX_YAML_NODES,
        max_depth: int = DEFAULT_MAX_YAML_DEPTH,
    ) -> None:
        self._max_nodes = max_nodes
        self._max_depth = max_depth
        self._node_count = 0
        self._node_depth = 0
        super().__init__(stream)

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            raise ContractYamlError("YAML aliases are not allowed")
        self._node_count += 1
        if self._node_count > self._max_nodes:
            raise ContractYamlError("YAML contains too many nodes")
        self._node_depth += 1
        if self._node_depth > self._max_depth:
            raise ContractYamlError("YAML nesting is too deep")
        try:
            return super().compose_node(parent, index)
        finally:
            self._node_depth -= 1

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, MappingNode):
            raise ContractYamlError("YAML mapping is malformed")
        keys: set[str] = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
                raise ContractYamlError("YAML mapping keys must be strings")
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ContractYamlError("YAML mapping keys must be strings")
            if key in keys:
                raise ContractYamlError("duplicate YAML key is not allowed")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_bounded_yaml(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_YAML_BYTES,
    max_nodes: int = DEFAULT_MAX_YAML_NODES,
    max_depth: int = DEFAULT_MAX_YAML_DEPTH,
) -> Any:
    if min(max_bytes, max_nodes, max_depth) < 1:
        raise ValueError("YAML resource budgets must be positive")
    try:
        encoded = read_regular_file(path, max_bytes=max_bytes)
    except NonRegularFileError:
        raise ContractYamlError("YAML input must be a regular file") from None
    except FileTooLargeError:
        raise ContractYamlError("YAML exceeds the maximum encoded size") from None
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractYamlError("YAML must be UTF-8") from error
    loader = StrictContractLoader(text, max_nodes=max_nodes, max_depth=max_depth)
    try:
        return loader.get_single_data()
    except RecursionError:
        raise ContractYamlError("YAML nesting is too deep") from None
    except ValueError:
        raise ContractYamlError("YAML contains an invalid scalar value") from None
    finally:
        loader.dispose()
