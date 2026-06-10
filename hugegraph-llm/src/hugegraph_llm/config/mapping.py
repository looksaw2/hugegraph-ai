# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from collections.abc import Mapping
from typing import Any

SENSITIVE_NAME_PARTS = {"token", "password", "pwd", "secret"}


def join_global_path(section: str, nested_path: str) -> str:
    return f"{section}.{nested_path}" if nested_path else section


def split_path(path: str) -> list[str]:
    return [part for part in path.split(".") if part]


def get_nested_value(data: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in split_path(dotted_path):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def set_nested_value(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    current = data
    parts = split_path(dotted_path)
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    if parts:
        current[parts[-1]] = value


def flat_to_nested(flat_data: Mapping[str, Any], flat_to_nested_mapping: Mapping[str, str]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for flat_key, value in flat_data.items():
        nested_path = flat_to_nested_mapping.get(flat_key)
        if nested_path is None:
            continue
        set_nested_value(nested, nested_path, value)
    return nested


def nested_to_flat(nested_data: Mapping[str, Any], flat_to_nested_mapping: Mapping[str, str]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for flat_key, nested_path in flat_to_nested_mapping.items():
        value = get_nested_value(nested_data, nested_path)
        if value is not None:
            flat[flat_key] = value
    return flat


def flatten_nested(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(flatten_nested(value, path))
        else:
            flat[path] = value
    return flat


def is_sensitive_path(path: str) -> bool:
    normalized = path.lower().replace("-", "_")
    if "api_key" in normalized:
        return True
    tokens = [token for segment in normalized.split(".") for token in segment.split("_")]
    return any(token in SENSITIVE_NAME_PARTS for token in tokens)


def global_path_for_field(section: str, field_name: str, flat_to_nested_mapping: Mapping[str, str]) -> str:
    return join_global_path(section, flat_to_nested_mapping[field_name])


def global_mapping(section: str, flat_to_nested_mapping: Mapping[str, str]) -> dict[str, str]:
    return {
        field_name: join_global_path(section, nested_path) for field_name, nested_path in flat_to_nested_mapping.items()
    }


def audit_mapping_coverage(model_fields: set[str], flat_to_nested_mapping: Mapping[str, str]) -> set[str]:
    return model_fields - set(flat_to_nested_mapping)
