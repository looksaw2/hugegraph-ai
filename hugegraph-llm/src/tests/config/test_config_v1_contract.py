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

import importlib
import json
import runpy
import stat
import sys
import warnings
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

ENV_KEYS = [
    "HUGEGRAPH_LLM_CONFIG_DIR",
    "HUGEGRAPH_AI_CONFIG_DIR",
    "OPENAI_API_KEY",
    "OPENAI_CHAT_API_KEY",
    "OPENAI_BASE_URL",
    "GRAPH_URL",
    "GRAPH_PWD",
    "ADMIN_TOKEN",
    "USER_TOKEN",
    "QDRANT_API_KEY",
    "QDRANT_PORT",
]


@pytest.fixture(autouse=True)
def clean_config_modules(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    _drop_config_modules()
    yield
    _drop_config_modules()


def _drop_config_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "hugegraph_llm.config" or module_name.startswith("hugegraph_llm.config."):
            sys.modules.pop(module_name)


def load_config(monkeypatch, config_dir: Path):
    monkeypatch.setenv("HUGEGRAPH_LLM_CONFIG_DIR", str(config_dir))
    return importlib.import_module("hugegraph_llm.config")


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def read_single_report(config_dir: Path) -> dict:
    reports = list((config_dir / "migration-reports").glob("*.json"))
    assert len(reports) == 1
    return json.loads(reports[0].read_text(encoding="utf-8"))


def flatten_nested(data: dict, prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_nested(value, path))
        else:
            flat[path] = value
    return flat


def is_sensitive_example_path(path: str) -> bool:
    normalized = path.lower().replace("-", "_")
    if "api_key" in normalized:
        return True
    tokens = [token for segment in normalized.split(".") for token in segment.split("_")]
    return any(token in {"token", "password", "pwd", "secret"} for token in tokens)


def test_config_example_yaml_is_valid_and_non_sensitive():
    module_root = Path(__file__).resolve().parents[3]
    example = yaml.safe_load((module_root / "config.example.yaml").read_text(encoding="utf-8"))

    assert isinstance(example, dict)
    assert not [path for path in flatten_nested(example) if is_sensitive_example_path(path)]


def test_import_config_has_no_write_side_effects(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config = load_config(monkeypatch, config_dir)

    assert config.llm_settings.language == "EN"
    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / ".env").exists()
    assert not (config_dir / "config_prompt.yaml").exists()
    assert not (config_dir / "migration-reports").exists()


def test_legacy_dotenv_import_is_secret_only_and_does_not_migrate(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_dotenv = "GRAPH_URL=dotenv-url\nGRAPH_PWD=dotenv-secret\nOPENAI_API_KEY=sk-secret\n"
    (config_dir / ".env").write_text(original_dotenv, encoding="utf-8")

    config = load_config(monkeypatch, config_dir)

    assert config.huge_settings.graph_url == "127.0.0.1:8080"
    assert config.huge_settings.graph_pwd == "dotenv-secret"
    assert config.llm_settings.openai_chat_api_key == "sk-secret"
    assert (config_dir / ".env").read_text(encoding="utf-8") == original_dotenv
    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / "migration-reports").exists()
    assert not list(config_dir.glob("*.bak*"))


def test_config_dir_resolution_no_cwd_fallback(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(
        config_dir / "config.yaml",
        {
            "llm": {"language": "CN"},
            "hugegraph": {"graph": {"url": "configured:8080"}},
        },
    )
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    config = load_config(monkeypatch, config_dir)

    assert config.llm_settings.language == "CN"
    assert config.huge_settings.graph_url == "configured:8080"
    assert not (other_cwd / ".env").exists()


def test_effective_config_and_field_source_are_read_only(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(config_dir / "config.yaml", {"llm": {"openai": {"chat": {"language_model": "gpt-x"}}}})

    config = load_config(monkeypatch, config_dir)
    effective = config.config_manager.get_effective_config()
    field_source = config.config_manager.get_field_source()

    assert isinstance(effective, MappingProxyType)
    assert isinstance(effective["llm"], MappingProxyType)
    assert effective["llm"]["openai"]["chat"]["language_model"] == "gpt-x"
    assert field_source["llm.openai.chat.language_model"] == "yaml_persisted"
    with pytest.raises(TypeError):
        effective["llm"] = {}
    with pytest.raises(TypeError):
        field_source["llm.openai.chat.language_model"] = "other"


def test_dotenv_secret_only_does_not_override_non_sensitive_yaml(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(
        config_dir / "config.yaml",
        {
            "hugegraph": {"graph": {"url": "yaml-url", "pwd": None}},
            "llm": {"openai": {"chat": {"api_key": "should-not-load"}}},
        },
    )
    (config_dir / ".env").write_text(
        "GRAPH_URL=dotenv-url\nGRAPH_PWD=dotenv-secret\nOPENAI_API_KEY=dotenv-openai\n",
        encoding="utf-8",
    )

    config = load_config(monkeypatch, config_dir)

    assert config.huge_settings.graph_url == "yaml-url"
    assert config.huge_settings.graph_pwd == "dotenv-secret"
    assert config.llm_settings.openai_chat_api_key == "dotenv-openai"
    assert config.config_manager.field_source["hugegraph.graph.pwd"] == "dotenv_secret"
    assert config.config_manager.field_source["llm.openai.chat.api_key"] == "dotenv_secret"


def test_process_env_overrides_yaml_and_dotenv(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(config_dir / "config.yaml", {"hugegraph": {"graph": {"url": "yaml-url"}}})
    (config_dir / ".env").write_text("GRAPH_PWD=dotenv-secret\n", encoding="utf-8")
    monkeypatch.setenv("GRAPH_URL", "process-url")
    monkeypatch.setenv("GRAPH_PWD", "process-secret")

    config = load_config(monkeypatch, config_dir)

    assert config.huge_settings.graph_url == "process-url"
    assert config.huge_settings.graph_pwd == "process-secret"
    assert config.config_manager.field_source["hugegraph.graph.url"] == "process_env_override"
    assert config.config_manager.field_source["hugegraph.graph.pwd"] == "process_env_override"


def test_update_config_rejects_full_dump_and_sensitive_non_null_path(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = load_config(monkeypatch, config_dir)

    with pytest.raises(ValueError):
        config.llm_settings.update_config(config.llm_settings.model_dump())

    with pytest.raises(ValueError):
        config.config_manager.update_config({"llm.openai.chat.api_key": "sk-secret"})


def test_update_config_persists_only_non_sensitive_leaf(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    config.llm_settings.update_config({"openai_chat_language_model": "gpt-4.1"})

    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    persisted = yaml.safe_load(persisted_text)
    assert persisted["llm"]["openai"]["chat"]["language_model"] == "gpt-4.1"
    assert "sk-secret" not in persisted_text
    assert "api_key" not in persisted_text


def test_migration_plan_phase0_is_read_only(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_dotenv = "GRAPH_URL=legacy-url\nGRAPH_PWD=secret\nUNKNOWN_KEY=kept\n"
    (config_dir / ".env").write_text(original_dotenv, encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    plan = config.config_manager.build_migration_plan()

    assert plan is not None
    assert plan.report.from_phase == "phase0"
    assert "hugegraph.graph.url" in plan.report.persisted_keys
    assert "GRAPH_PWD" in plan.report.sensitive_keys_retained
    assert "UNKNOWN_KEY" in plan.report.unknown_keys
    assert (config_dir / ".env").read_text(encoding="utf-8") == original_dotenv
    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / "migration-reports").exists()
    assert not list(config_dir.glob("*.bak*"))


def test_migration_cli_plan_is_read_only(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_dotenv = "GRAPH_URL=legacy-url\nGRAPH_PWD=secret\n"
    (config_dir / ".env").write_text(original_dotenv, encoding="utf-8")
    from hugegraph_llm.config_migrate import main

    assert main(["--config-dir", str(config_dir), "plan"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["from_phase"] == "phase0"
    assert "hugegraph.graph.url" in output["persisted_keys"]
    assert "GRAPH_PWD" in output["sensitive_keys_retained"]
    assert (config_dir / ".env").read_text(encoding="utf-8") == original_dotenv
    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / "migration-reports").exists()
    assert not list(config_dir.glob("*.bak*"))


def test_migration_cli_apply_requires_yes(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("GRAPH_URL=legacy-url\n", encoding="utf-8")
    from hugegraph_llm.config_migrate import main

    with pytest.raises(SystemExit):
        main(["--config-dir", str(config_dir), "apply"])

    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / "migration-reports").exists()


def test_explicit_phase0_migration_splits_sensitive_and_persisted_values(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_dotenv = "\n".join(
        [
            "OPENAI_API_KEY=sk-secret",
            "OPENAI_CHAT_LANGUAGE_MODEL=gpt-4.1-mini",
            "GRAPH_URL=legacy-url",
            "GRAPH_PWD=graph-secret",
            "QDRANT_API_KEY=qdrant-secret",
        ]
    )
    (config_dir / ".env").write_text(original_dotenv + "\n", encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    report = config.config_manager.migrate_from_legacy_if_needed()

    assert report is not None
    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    persisted = yaml.safe_load(persisted_text)
    assert persisted["llm"]["openai"]["chat"]["language_model"] == "gpt-4.1-mini"
    assert persisted["hugegraph"]["graph"]["url"] == "legacy-url"
    assert "sk-secret" not in persisted_text
    assert "graph-secret" not in persisted_text
    assert "qdrant-secret" not in persisted_text
    dotenv_text = (config_dir / ".env").read_text(encoding="utf-8")
    assert dotenv_text == "GRAPH_PWD=graph-secret\nOPENAI_API_KEY=sk-secret\nQDRANT_API_KEY=qdrant-secret\n"
    report_json = read_single_report(config_dir)
    assert report_json["from_phase"] == "phase0"
    assert "graph-secret" not in json.dumps(report_json)


def test_migration_cli_apply_writes_after_confirmation(tmp_path, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("GRAPH_URL=legacy-url\nGRAPH_PWD=secret\n", encoding="utf-8")
    from hugegraph_llm.config_migrate import main

    assert main(["--config-dir", str(config_dir), "apply", "--yes"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["from_phase"] == "phase0"
    assert (
        yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))["hugegraph"]["graph"]["url"]
        == "legacy-url"
    )
    assert (config_dir / ".env").read_text(encoding="utf-8") == "GRAPH_PWD=secret\n"
    assert (config_dir / "migration-reports").exists()


def test_migration_cli_export_env_writes_requested_file(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(config_dir / "config.yaml", {"hugegraph": {"graph": {"url": "configured:8080"}}})
    output = tmp_path / ".env.generated"
    from hugegraph_llm.config_migrate import main

    assert main(["--config-dir", str(config_dir), "export-env", "--output", str(output)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["output"] == str(output.resolve())
    exported = output.read_text(encoding="utf-8")
    assert "GRAPH_URL=configured:8080" in exported
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_explicit_phase0_migration_backs_up_original_dotenv(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_dotenv = "GRAPH_URL=legacy-url\nGRAPH_PWD=secret\nUNKNOWN_KEY=kept-in-backup\n"
    (config_dir / ".env").write_text(original_dotenv, encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    config.config_manager.migrate_from_legacy_if_needed()

    report = read_single_report(config_dir)
    backup_path = Path(report["backup_files"][0])
    assert backup_path.exists()
    assert report["migration_id"] in backup_path.name
    assert backup_path.read_text(encoding="utf-8") == original_dotenv
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert (config_dir / ".env").read_text(encoding="utf-8") == "GRAPH_PWD=secret\n"
    assert stat.S_IMODE((config_dir / ".env").stat().st_mode) == 0o600


def test_explicit_phase1_migration_backup_filename_matches_report_id(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    write_yaml(
        config_dir / "config.yaml",
        {
            "HugeGraphConfig": {
                "GRAPH_URL": "legacy-url",
                "GRAPH_PWD": "secret",
            }
        },
    )
    config = load_config(monkeypatch, config_dir)

    config.config_manager.migrate_from_legacy_if_needed()

    report = read_single_report(config_dir)
    backup_path = Path(report["backup_files"][0])
    assert backup_path.exists()
    assert report["migration_id"] in backup_path.name
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert "GRAPH_PWD" in report["sensitive_keys_retained"]
    assert "secret" not in (config_dir / "config.yaml").read_text(encoding="utf-8")
    assert (config_dir / ".env").read_text(encoding="utf-8") == "GRAPH_PWD=secret\n"
    assert stat.S_IMODE((config_dir / ".env").stat().st_mode) == 0o600


def test_phase1_migration_validation_failure_has_no_side_effect(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original_yaml = "IndexConfig:\n  QDRANT_PORT: not-an-int\n"
    (config_dir / "config.yaml").write_text(original_yaml, encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    with pytest.raises(ValueError):
        config.config_manager.migrate_from_legacy_if_needed()

    assert (config_dir / "config.yaml").read_text(encoding="utf-8") == original_yaml
    assert not (config_dir / ".env").exists()
    assert not (config_dir / "migration-reports").exists()
    assert not list(config_dir.glob("*.bak*"))


def test_update_config_invalid_leaf_value_has_no_side_effect(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = load_config(monkeypatch, config_dir)

    with pytest.raises(ValueError):
        config.index_settings.update_config({"qdrant_port": "not-an-int"})

    assert not (config_dir / "config.yaml").exists()


def test_process_env_type_conversion_fail_fast(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("QDRANT_PORT", "not-an-int")

    with pytest.raises(ValueError):
        load_config(monkeypatch, config_dir)

    assert not (config_dir / "config.yaml").exists()
    assert not (config_dir / "config_prompt.yaml").exists()


def test_deprecated_generate_env_does_not_write_env_secret_to_yaml(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    config = load_config(monkeypatch, config_dir)

    with pytest.warns(DeprecationWarning):
        config.llm_settings.generate_env()

    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    assert "sk-secret" not in persisted_text
    assert "api_key" not in persisted_text
    assert (config_dir / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-secret\n"


def test_gradio_config_helper_splits_sensitive_and_persisted_updates(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = load_config(monkeypatch, config_dir)
    sys.modules.pop("hugegraph_llm.demo.rag_demo.configs_block", None)
    from hugegraph_llm.demo.rag_demo.configs_block import _persist_config_updates

    _persist_config_updates(
        config.llm_settings,
        {
            "openai_chat_api_key": "sk-ui-secret",
            "openai_chat_language_model": "gpt-ui",
        },
    )

    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    persisted = yaml.safe_load(persisted_text)
    assert persisted["llm"]["openai"]["chat"]["language_model"] == "gpt-ui"
    assert "sk-ui-secret" not in persisted_text
    assert "api_key" not in persisted_text
    assert (config_dir / ".env").read_text(encoding="utf-8") == "OPENAI_CHAT_API_KEY=sk-ui-secret\n"


def test_gradio_apply_llm_config_persists_selected_type_and_splits_secret(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    load_config(monkeypatch, config_dir)
    sys.modules.pop("hugegraph_llm.demo.rag_demo.configs_block", None)
    configs_block = importlib.import_module("hugegraph_llm.demo.rag_demo.configs_block")

    configs_block.llm_settings.chat_llm_type = "litellm"
    monkeypatch.setattr(configs_block, "test_litellm_chat", lambda *args, **kwargs: 200)
    monkeypatch.setattr(configs_block.gr, "Info", lambda *args, **kwargs: None)

    assert configs_block.apply_llm_config("chat", "sk-ui-secret", "https://litellm.example", "openai/gpt", "128") == 200

    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    persisted = yaml.safe_load(persisted_text)
    assert persisted["llm"]["chat_llm_type"] == "litellm"
    assert persisted["llm"]["litellm"]["chat"]["api_base"] == "https://litellm.example"
    assert persisted["llm"]["litellm"]["chat"]["language_model"] == "openai/gpt"
    assert persisted["llm"]["litellm"]["chat"]["tokens"] == 128
    assert "sk-ui-secret" not in persisted_text
    assert "api_key" not in persisted_text
    assert (config_dir / ".env").read_text(encoding="utf-8") == "LITELLM_CHAT_API_KEY=sk-ui-secret\n"


def test_gradio_openai_role_key_check_uses_effective_config_not_cwd_dotenv(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("OPENAI_EXTRACT_API_KEY=sk-extract\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".env").write_text("OPENAI_TEXT2GQL_API_KEY=sk-cwd-text2gql\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    load_config(monkeypatch, config_dir)
    sys.modules.pop("hugegraph_llm.demo.rag_demo.configs_block", None)
    configs_block = importlib.import_module("hugegraph_llm.demo.rag_demo.configs_block")

    assert configs_block._has_openai_role_api_key("extract") is True
    assert configs_block._has_openai_role_api_key("text2gql") is False


def test_generate_entrypoint_is_explicit_write_path(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    monkeypatch.setenv("HUGEGRAPH_LLM_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(sys, "argv", ["generate.py"])

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        runpy.run_module("hugegraph_llm.config.generate", run_name="__main__")

    assert not [warning for warning in captured if issubclass(warning.category, DeprecationWarning)]
    persisted_text = (config_dir / "config.yaml").read_text(encoding="utf-8")
    assert "sk-secret" not in persisted_text
    assert "api_key" not in persisted_text
    assert (config_dir / "config_prompt.yaml").exists()
    assert (config_dir / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-secret\n"


def test_invalid_yaml_fail_fast(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("llm: [broken", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(monkeypatch, config_dir)
