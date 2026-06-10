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

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from omegaconf import OmegaConf

from hugegraph_llm.config.mapping import is_sensitive_path
from hugegraph_llm.config.paths import migration_reports_dir

ConfigPhase = Literal["missing", "phase0", "phase1", "phase2"]


@dataclass
class MigrationReport:
    migration_id: str
    from_phase: ConfigPhase
    to_phase: ConfigPhase
    config_base_dir: str
    created_files: list[str] = field(default_factory=list)
    backup_files: list[str] = field(default_factory=list)
    sensitive_keys_retained: list[str] = field(default_factory=list)
    persisted_keys: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    ignored_env_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "config_base_dir": self.config_base_dir,
            "created_files": self.created_files,
            "backup_files": self.backup_files,
            "sensitive_keys_retained": self.sensitive_keys_retained,
            "persisted_keys": self.persisted_keys,
            "unknown_keys": self.unknown_keys,
            "ignored_env_keys": self.ignored_env_keys,
            "warnings": self.warnings,
        }


def new_migration_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def detect_config_phase(config_path: Path, dotenv_file: Path) -> ConfigPhase:
    if config_path.exists():
        try:
            data = OmegaConf.to_container(OmegaConf.load(config_path), resolve=True)
        except Exception as exc:
            raise ValueError(f"Invalid config.yaml at {config_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Invalid config.yaml: expected mapping at {config_path}")
        keys = set(data)
        if keys & {"llm", "hugegraph", "admin", "index"}:
            return "phase2"
        if keys & {"LLMConfig", "HugeGraphConfig", "AdminConfig", "IndexConfig"}:
            return "phase1"
        return "phase2"
    if dotenv_file.exists():
        return "phase0"
    return "missing"


def write_migration_reports(
    config_base_dir: Path,
    report: MigrationReport,
) -> tuple[Path, Path]:
    reports_dir = migration_reports_dir(config_base_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{report.migration_id}.json"
    md_path = reports_dir / f"{report.migration_id}.md"

    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown_report(report), encoding="utf-8")
    return md_path, json_path


def _render_markdown_report(report: MigrationReport) -> str:
    lines = [
        f"# Config Migration Report {report.migration_id}",
        "",
        f"- from_phase: `{report.from_phase}`",
        f"- to_phase: `{report.to_phase}`",
        f"- config_base_dir: `{report.config_base_dir}`",
        "",
        "## Created Files",
        *[f"- `{path}`" for path in report.created_files],
        "",
        "## Backup Files",
        *[f"- `{path}`" for path in report.backup_files],
        "",
        "## Sensitive Keys Retained",
        *[f"- `{key}`" for key in report.sensitive_keys_retained],
        "",
        "## Persisted Keys",
        *[f"- `{key}`" for key in report.persisted_keys],
        "",
        "## Unknown Keys",
        *[f"- `{key}`" for key in report.unknown_keys],
        "",
        "## Ignored Env Keys",
        *[f"- `{key}`" for key in report.ignored_env_keys],
        "",
        "## Warnings",
        *[f"- {warning}" for warning in report.warnings],
        "",
    ]
    return "\n".join(lines)


def read_dotenv_values(dotenv_file: Path) -> dict[str, str]:
    values = dotenv_values(dotenv_file)
    return {key: value for key, value in values.items() if value is not None}


def write_secret_dotenv(dotenv_file: Path, values: dict[str, Any]) -> None:
    dotenv_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={'' if value is None else value}" for key, value in sorted(values.items())]
    dotenv_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.chmod(dotenv_file, 0o600)


def is_sensitive_env_key(env_key: str) -> bool:
    return is_sensitive_path(env_key.lower())
