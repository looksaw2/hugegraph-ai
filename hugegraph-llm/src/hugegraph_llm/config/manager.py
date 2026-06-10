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

from __future__ import annotations

import os
import tempfile
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from dotenv import dotenv_values
from omegaconf import OmegaConf
from pydantic import TypeAdapter

from hugegraph_llm.config.mapping import (
    audit_mapping_coverage,
    flat_to_nested,
    flatten_nested,
    global_mapping,
    global_path_for_field,
    is_sensitive_path,
    nested_to_flat,
    set_nested_value,
)
from hugegraph_llm.config.migration import (
    MigrationReport,
    detect_config_phase,
    new_migration_id,
    read_dotenv_values,
    write_migration_reports,
    write_secret_dotenv,
)
from hugegraph_llm.config.paths import config_yaml_path, dotenv_path, resolve_config_base_dir

FieldSource = Literal[
    "yaml_persisted",
    "migrated_persisted",
    "explicit_persisted_patch",
    "effective_default",
    "dotenv_secret",
    "process_env_override",
    "runtime_only_patch",
]

METADATA_KEYS = {
    "_field_source",
    "_migration_phase",
    "_dotenv_path",
    "_persisted_cfg",
    "_effective_cfg",
}
MAX_PATCH_KEYS = 20


class ConfigError(ValueError):
    """Raised when config loading or validation fails."""


@dataclass(frozen=True)
class LegacyMigrationPlan:
    report: MigrationReport
    persisted_config: dict[str, Any]
    secret_values: dict[str, Any]
    source_path: Path | None
    backup_path: Path | None


class ConfigManager:
    """Single entry point for config loading, env override, migration, and writes."""

    _instance: ClassVar["ConfigManager | None"] = None

    def __init__(self, config_base_dir: Path | None = None) -> None:
        self.config_base_dir = config_base_dir or resolve_config_base_dir()
        self.config_path = config_yaml_path(self.config_base_dir)
        self.dotenv_path = dotenv_path(self.config_base_dir)
        self.config_classes: dict[str, type[Any]] = {}
        self.section_by_class: dict[type[Any], str] = {}
        self.field_to_global_path: dict[type[Any], dict[str, str]] = {}
        self.global_to_field: dict[str, tuple[type[Any], str]] = {}
        self.env_to_global_path: dict[str, list[str]] = {}
        self.global_env_aliases: dict[str, list[str]] = {}
        self.mutable_persisted_leaf_paths: set[str] = set()
        self.persisted_config: dict[str, Any] = {}
        self.effective_config: dict[str, Any] = {}
        self.field_source: dict[str, FieldSource] = {}
        self._loaded = False

    @classmethod
    def instance(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def initialize(self, config_classes: list[type[Any]]) -> None:
        for config_class in config_classes:
            self.register_config_class(config_class)
        self.reload()

    def register_config_class(self, config_class: type[Any]) -> None:
        section = getattr(config_class, "_config_section", None)
        mapping = getattr(config_class, "_flat_to_nested_mapping", None)
        env_var_map = getattr(config_class, "_env_var_map", None)
        mutable_fields = getattr(config_class, "_mutable_persisted_fields", None)
        if not section or not isinstance(mapping, Mapping):
            raise ConfigError(f"{config_class.__name__} must declare _config_section and _flat_to_nested_mapping")
        if not isinstance(env_var_map, Mapping):
            raise ConfigError(f"{config_class.__name__} must declare _env_var_map")
        if not isinstance(mutable_fields, set):
            raise ConfigError(f"{config_class.__name__} must declare _mutable_persisted_fields")

        model_fields = set(config_class.model_fields)
        missing_fields = audit_mapping_coverage(model_fields, mapping)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ConfigError(f"{config_class.__name__} has unmapped fields: {missing}")

        self.config_classes[section] = config_class
        self.section_by_class[config_class] = section
        field_paths = global_mapping(section, mapping)
        self.field_to_global_path[config_class] = field_paths
        for field_name, global_path in field_paths.items():
            self.global_to_field[global_path] = (config_class, field_name)

        for field_name, env_names in env_var_map.items():
            if field_name not in field_paths:
                raise ConfigError(f"{config_class.__name__} env map references unknown field: {field_name}")
            global_path = field_paths[field_name]
            aliases = list(env_names)
            self.global_env_aliases[global_path] = aliases
            for env_name in aliases:
                self.env_to_global_path.setdefault(env_name, []).append(global_path)

        for field_name in mutable_fields:
            if field_name not in field_paths:
                raise ConfigError(f"{config_class.__name__} mutable set references unknown field: {field_name}")
            global_path = field_paths[field_name]
            if is_sensitive_path(global_path):
                raise ConfigError(f"{config_class.__name__} mutable field is sensitive: {field_name}")
            self.mutable_persisted_leaf_paths.add(global_path)

    def reload(self) -> None:
        self.persisted_config = self._load_persisted_config()
        self.effective_config = {}
        self.field_source = {}
        for config_class in self.section_by_class:
            self._build_effective_section(config_class)
        self._loaded = True

    def _load_persisted_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            loaded = OmegaConf.to_container(OmegaConf.load(self.config_path), resolve=True)
        except Exception as exc:
            raise ConfigError(f"Invalid config.yaml at {self.config_path}: {exc}") from exc
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"Invalid config.yaml at {self.config_path}: expected mapping")
        return loaded

    def _build_effective_section(self, config_class: type[Any]) -> None:
        section = self.section_by_class[config_class]
        mapping = getattr(config_class, "_flat_to_nested_mapping")
        section_persisted = self.persisted_config.get(section, {})
        if section_persisted is None:
            section_persisted = {}
        if not isinstance(section_persisted, Mapping):
            raise ConfigError(f"Invalid config section {section}: expected mapping")

        flat_values = self._default_values(config_class)
        for field_name in flat_values:
            global_path = global_path_for_field(section, field_name, mapping)
            self.field_source[global_path] = "effective_default"

        persisted_flat = nested_to_flat(section_persisted, mapping)
        for field_name, value in persisted_flat.items():
            global_path = global_path_for_field(section, field_name, mapping)
            if is_sensitive_path(global_path):
                continue
            flat_values[field_name] = value
            self.field_source[global_path] = "yaml_persisted"

        self._apply_env_overrides(config_class, flat_values)
        section_effective = flat_to_nested(flat_values, mapping)
        self.effective_config[section] = section_effective

    def _default_values(self, config_class: type[Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field_name, field_info in config_class.model_fields.items():
            default = field_info.get_default(call_default_factory=True)
            if default is not None:
                values[field_name] = default
            else:
                values[field_name] = None
        return values

    def _apply_env_overrides(self, config_class: type[Any], flat_values: dict[str, Any]) -> None:
        section = self.section_by_class[config_class]
        mapping = getattr(config_class, "_flat_to_nested_mapping")
        env_var_map = getattr(config_class, "_env_var_map")
        dotenv_values_map = dotenv_values(self.dotenv_path) if self.dotenv_path.exists() else {}

        for field_name, env_names in env_var_map.items():
            global_path = global_path_for_field(section, field_name, mapping)
            process_value = self._first_env_value(env_names, os.environ)
            if process_value is not None:
                flat_values[field_name] = self._coerce_field_value(config_class, field_name, process_value)
                self.field_source[global_path] = "process_env_override"
                continue

            if not is_sensitive_path(global_path):
                self._record_ignored_dotenv_non_sensitive(global_path, env_names, dotenv_values_map)
                continue

            dotenv_value = self._first_env_value(env_names, dotenv_values_map)
            if dotenv_value is not None:
                flat_values[field_name] = self._coerce_field_value(config_class, field_name, dotenv_value)
                self.field_source[global_path] = "dotenv_secret"

    def _record_ignored_dotenv_non_sensitive(
        self,
        _global_path: str,
        _env_names: list[str] | tuple[str, ...],
        _dotenv_values_map: Mapping[str, Any],
    ) -> None:
        # Reserved for migration/reporting; Phase2 .env non-sensitive values intentionally do not override YAML.
        return

    def _first_env_value(self, env_names: list[str] | tuple[str, ...], values: Mapping[str, Any]) -> str | None:
        for env_name in env_names:
            if env_name in values:
                value = values[env_name]
                if value is None:
                    continue
                value_str = str(value)
                if value_str == "":
                    continue
                return value_str
        return None

    def _coerce_field_value(self, config_class: type[Any], field_name: str, value: Any) -> Any:
        field = config_class.model_fields[field_name]
        try:
            return TypeAdapter(field.annotation).validate_python(value)
        except Exception as exc:
            raise ConfigError(f"Invalid config value for {config_class.__name__}.{field_name}") from exc

    def get_effective_config(self) -> Mapping[str, Any]:
        if not self._loaded:
            self.reload()
        return self._freeze(self.effective_config)

    def get_field_source(self) -> Mapping[str, FieldSource]:
        if not self._loaded:
            self.reload()
        return MappingProxyType(dict(self.field_source))

    def _freeze(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return MappingProxyType({key: self._freeze(nested_value) for key, nested_value in value.items()})
        if isinstance(value, list):
            return tuple(self._freeze(item) for item in value)
        return value

    def get_section_flat(self, config_class: type[Any]) -> dict[str, Any]:
        if config_class not in self.section_by_class:
            self.register_config_class(config_class)
            self.reload()
        elif not self._loaded:
            self.reload()
        section = self.section_by_class[config_class]
        mapping = getattr(config_class, "_flat_to_nested_mapping")
        section_data = self.effective_config.get(section, {})
        return {**self._default_values(config_class), **nested_to_flat(section_data, mapping)}

    def update_config(self, patch: dict[str, Any]) -> None:
        if not isinstance(patch, dict) or not patch:
            raise ConfigError("update_config() requires a non-empty patch dict")
        if len(patch) > MAX_PATCH_KEYS:
            raise ConfigError(f"Patch is too large; max keys: {MAX_PATCH_KEYS}")
        self._apply_persisted_patch(patch)

    def _apply_persisted_patch(self, patch: dict[str, Any]) -> None:
        coerced_patch: dict[str, Any] = {}
        for path, value in patch.items():
            self._validate_patch_leaf(path, value)
            coerced_patch[path] = self._coerce_global_value(path, value)
        for path, value in coerced_patch.items():
            set_nested_value(self.persisted_config, path, value)
            self.field_source[path] = "explicit_persisted_patch"
        self.save()
        self.reload()

    def update_section(self, config_class: type[Any], patch: dict[str, Any]) -> None:
        if config_class not in self.section_by_class:
            self.register_config_class(config_class)
        field_paths = self.field_to_global_path[config_class]
        global_patch: dict[str, Any] = {}
        for field_name, value in patch.items():
            if field_name not in field_paths:
                raise ConfigError(f"Unknown config field: {field_name}")
            global_patch[field_paths[field_name]] = value
        self.update_config(global_patch)

    def persist_current_config(self, config_obj: Any) -> None:
        config_class = config_obj.__class__
        if config_class not in self.section_by_class:
            self.register_config_class(config_class)
        patch: dict[str, Any] = {}
        field_paths = self.field_to_global_path[config_class]
        for field_name, value in config_obj.model_dump().items():
            global_path = field_paths[field_name]
            if is_sensitive_path(global_path):
                continue
            if global_path in self.mutable_persisted_leaf_paths:
                patch[global_path] = value
        if patch:
            self._apply_persisted_patch(patch)

    def update_secret_env(self, secret_values: dict[str, Any]) -> None:
        existing = read_dotenv_values(self.dotenv_path) if self.dotenv_path.exists() else {}
        existing.update({key: value for key, value in secret_values.items() if value not in (None, "")})
        secret_only = {
            key: value
            for key, value in existing.items()
            if any(is_sensitive_path(path) for path in self.env_to_global_path.get(key, [])) or is_sensitive_path(key)
        }
        write_secret_dotenv(self.dotenv_path, secret_only)
        self.reload()

    def _validate_patch_leaf(self, path: str, value: Any) -> None:
        if not isinstance(path, str) or not path:
            raise ConfigError("Patch keys must be non-empty dotted paths")
        if path in METADATA_KEYS or any(part in METADATA_KEYS for part in path.split(".")):
            raise ConfigError(f"Metadata key is not configurable: {path}")
        if isinstance(value, Mapping):
            raise ConfigError(f"Patch values must be leaf values: {path}")
        if path not in self.mutable_persisted_leaf_paths:
            if is_sensitive_path(path):
                raise ConfigError(f"Sensitive config values cannot be written to YAML: {path}")
            raise ConfigError(f"Unknown or immutable config path: {path}")
        if is_sensitive_path(path) and value not in (None, ""):
            raise ConfigError(f"Sensitive config values cannot be written to YAML: {path}")

    def save(self) -> None:
        safe_config = self._safe_persisted_config()
        self.config_base_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".yaml", dir=self.config_base_dir)
        tmp_file = Path(tmp_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                OmegaConf.save(config=OmegaConf.create(safe_config), f=file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_file, self.config_path)
            self._fsync_directory(self.config_base_dir)
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

    def _fsync_directory(self, directory: Path) -> None:
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            return

    def _safe_persisted_config(self) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for path, value in flatten_nested(self.persisted_config).items():
            if is_sensitive_path(path):
                if value is None:
                    set_nested_value(safe, path, None)
                continue
            set_nested_value(safe, path, value)
        return safe

    def migrate_from_legacy_if_needed(self) -> MigrationReport | None:
        plan = self.build_migration_plan()
        if plan is None:
            return None
        if plan.source_path and plan.backup_path:
            self._copy_file_with_secret_permissions(plan.source_path, plan.backup_path)
        self.persisted_config = plan.persisted_config
        self.save()
        if plan.secret_values or (plan.source_path == self.dotenv_path and self.dotenv_path.exists()):
            write_secret_dotenv(self.dotenv_path, plan.secret_values)
        write_migration_reports(self.config_base_dir, plan.report)
        self.reload()
        return plan.report

    def build_migration_plan(self) -> LegacyMigrationPlan | None:
        phase = detect_config_phase(self.config_path, self.dotenv_path)
        if phase == "phase2" or phase == "missing":
            return None
        if phase == "phase1":
            return self._build_phase1_plan()
        if phase == "phase0":
            return self._build_phase0_plan()
        return None

    def _build_phase0_plan(self) -> LegacyMigrationPlan:
        migration_id = new_migration_id()
        env_values = read_dotenv_values(self.dotenv_path)
        nested: dict[str, Any] = {}
        secret_values: dict[str, Any] = {}
        unknown_keys: list[str] = []
        persisted_keys: list[str] = []

        for env_key, value in env_values.items():
            paths = self.env_to_global_path.get(env_key)
            if not paths:
                unknown_keys.append(env_key)
                continue
            for global_path in paths:
                if is_sensitive_path(global_path):
                    secret_values[env_key] = value
                else:
                    set_nested_value(nested, global_path, self._coerce_global_value(global_path, value))
                    persisted_keys.append(global_path)

        backup_path = self.dotenv_path.with_name(f".env.bak.pre-phase-2.{migration_id}")

        report = MigrationReport(
            migration_id=migration_id,
            from_phase="phase0",
            to_phase="phase2",
            config_base_dir=str(self.config_base_dir),
            created_files=[str(self.config_path)],
            backup_files=[str(backup_path)] if self.dotenv_path.exists() else [],
            sensitive_keys_retained=sorted(secret_values),
            persisted_keys=sorted(set(persisted_keys)),
            unknown_keys=sorted(unknown_keys),
        )
        return LegacyMigrationPlan(
            report=report,
            persisted_config=nested,
            secret_values=secret_values,
            source_path=self.dotenv_path if self.dotenv_path.exists() else None,
            backup_path=backup_path if self.dotenv_path.exists() else None,
        )

    def _build_phase1_plan(self) -> LegacyMigrationPlan:
        migration_id = new_migration_id()
        raw = OmegaConf.to_container(OmegaConf.load(self.config_path), resolve=True)
        if not isinstance(raw, dict):
            raise ConfigError("Phase1 config.yaml must be a mapping")
        nested: dict[str, Any] = {}
        secret_values: dict[str, Any] = {}
        unknown_keys: list[str] = []
        persisted_keys: list[str] = []
        section_name_by_class_name = {
            config_class.__name__: section for section, config_class in self.config_classes.items()
        }

        for legacy_section, values in raw.items():
            section = section_name_by_class_name.get(str(legacy_section))
            if section is None or not isinstance(values, Mapping):
                unknown_keys.append(str(legacy_section))
                continue
            config_class = self.config_classes[section]
            field_paths = self.field_to_global_path[config_class]
            for legacy_key, value in values.items():
                field_name = str(legacy_key).lower()
                if field_name not in field_paths:
                    unknown_keys.append(f"{legacy_section}.{legacy_key}")
                    continue
                global_path = field_paths[field_name]
                coerced_value = self._coerce_global_value(global_path, value)
                if is_sensitive_path(global_path):
                    env_names = getattr(config_class, "_env_var_map").get(field_name, [])
                    if env_names and coerced_value not in (None, ""):
                        secret_values[env_names[0]] = coerced_value
                    continue
                set_nested_value(nested, global_path, coerced_value)
                persisted_keys.append(global_path)

        backup_path = self.config_path.with_name(f"config.yaml.bak.pre-phase-2.{migration_id}")

        report = MigrationReport(
            migration_id=migration_id,
            from_phase="phase1",
            to_phase="phase2",
            config_base_dir=str(self.config_base_dir),
            created_files=[str(self.config_path)],
            backup_files=[str(backup_path)] if self.config_path.exists() else [],
            sensitive_keys_retained=sorted(secret_values),
            persisted_keys=sorted(set(persisted_keys)),
            unknown_keys=sorted(unknown_keys),
        )
        return LegacyMigrationPlan(
            report=report,
            persisted_config=nested,
            secret_values=secret_values,
            source_path=self.config_path if self.config_path.exists() else None,
            backup_path=backup_path if self.config_path.exists() else None,
        )

    def _coerce_global_value(self, global_path: str, value: Any) -> Any:
        config_class, field_name = self.global_to_field[global_path]
        return self._coerce_field_value(config_class, field_name, value)

    def _copy_file_with_secret_permissions(self, source: Path, destination: Path) -> None:
        destination.write_bytes(source.read_bytes())
        os.chmod(destination, 0o600)


def get_config_manager() -> ConfigManager:
    return ConfigManager.instance()


def reset_config_manager() -> None:
    ConfigManager.reset_instance()


def warn_deprecated(method_name: str) -> None:
    warnings.warn(
        f"{method_name}() is deprecated; use update_config() and config.yaml/.env secret-only instead",
        DeprecationWarning,
        stacklevel=2,
    )
