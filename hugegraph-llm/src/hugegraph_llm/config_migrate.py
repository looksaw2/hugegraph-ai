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

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_config_manager(config_dir: str | None):
    if config_dir:
        os.environ["HUGEGRAPH_LLM_CONFIG_DIR"] = str(Path(config_dir).expanduser().resolve())
    from hugegraph_llm.config import config_manager

    return config_manager


def _detect_phase(manager) -> str:
    from hugegraph_llm.config.migration import detect_config_phase

    return detect_config_phase(manager.config_path, manager.dotenv_path)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _doctor(args: argparse.Namespace) -> int:
    manager = _load_config_manager(args.config_dir)
    phase = _detect_phase(manager)
    plan = manager.build_migration_plan()
    _print_json(
        {
            "config_base_dir": str(manager.config_base_dir),
            "config_path": str(manager.config_path),
            "dotenv_path": str(manager.dotenv_path),
            "phase": phase,
            "requires_migration": plan is not None,
            "migration_id": plan.report.migration_id if plan else None,
        }
    )
    return 0


def _plan(args: argparse.Namespace) -> int:
    manager = _load_config_manager(args.config_dir)
    plan = manager.build_migration_plan()
    if plan is None:
        _print_json({"phase": _detect_phase(manager), "requires_migration": False})
        return 0
    _print_json(plan.report.to_dict())
    return 0


def _diff(args: argparse.Namespace) -> int:
    manager = _load_config_manager(args.config_dir)
    plan = manager.build_migration_plan()
    if plan is None:
        _print_json({"phase": _detect_phase(manager), "requires_migration": False, "effective_drift": "NONE"})
        return 0
    _print_json(
        {
            "migration_id": plan.report.migration_id,
            "from_phase": plan.report.from_phase,
            "to_phase": plan.report.to_phase,
            "persisted_keys": plan.report.persisted_keys,
            "sensitive_keys_retained": plan.report.sensitive_keys_retained,
            "unknown_keys": plan.report.unknown_keys,
            "effective_drift": "CHANGED" if plan.report.persisted_keys else "NONE",
        }
    )
    return 0


def _apply(args: argparse.Namespace) -> int:
    if not args.yes:
        raise SystemExit("apply requires --yes")
    manager = _load_config_manager(args.config_dir)
    report = manager.migrate_from_legacy_if_needed()
    if report is None:
        _print_json({"phase": _detect_phase(manager), "requires_migration": False})
        return 0
    _print_json(report.to_dict())
    return 0


def _export_env(args: argparse.Namespace) -> int:
    manager = _load_config_manager(args.config_dir)
    output = Path(args.output).expanduser().resolve() if args.output else manager.config_base_dir / ".env.generated"
    lines: list[str] = []
    for global_path in sorted(manager.global_to_field):
        config_class, field_name = manager.global_to_field[global_path]
        env_names = manager.global_env_aliases.get(global_path)
        if not env_names:
            continue
        value = manager.get_section_flat(config_class).get(field_name)
        lines.append(f"{env_names[0]}={'' if value is None else value}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.chmod(output, 0o600)
    _print_json({"output": str(output), "keys": len(lines)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HugeGraph-LLM config migration utility")
    parser.add_argument("--config-dir", help="Runtime config directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Diagnose config phase without writing files").set_defaults(func=_doctor)
    subparsers.add_parser("plan", help="Print migration plan without writing files").set_defaults(func=_plan)
    subparsers.add_parser("diff", help="Print redacted migration diff without writing files").set_defaults(func=_diff)

    apply_parser = subparsers.add_parser("apply", help="Apply migration after explicit confirmation")
    apply_parser.add_argument("--yes", action="store_true", help="Confirm migration writes")
    apply_parser.set_defaults(func=_apply)

    export_parser = subparsers.add_parser("export-env", help="Export effective config to a legacy .env file")
    export_parser.add_argument("--output", help="Output path; defaults to .env.generated in the config directory")
    export_parser.set_defaults(func=_export_env)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
