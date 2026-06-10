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

import os
from pathlib import Path

from hugegraph_llm.utils.log import log

CONFIG_DIR_ENV = "HUGEGRAPH_LLM_CONFIG_DIR"
LEGACY_CONFIG_DIR_ENV = "HUGEGRAPH_AI_CONFIG_DIR"


def resolve_module_root() -> Path:
    """Return the hugegraph-llm module root without depending on CWD."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "hugegraph_llm").exists() and (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Unable to resolve hugegraph-llm module root")


def resolve_config_base_dir() -> Path:
    """Resolve the config base directory using explicit env vars or module root."""
    configured = os.environ.get(CONFIG_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    legacy = os.environ.get(LEGACY_CONFIG_DIR_ENV)
    if legacy:
        log.warning(
            "%s is deprecated; please use %s instead",
            LEGACY_CONFIG_DIR_ENV,
            CONFIG_DIR_ENV,
        )
        return Path(legacy).expanduser().resolve()

    return resolve_module_root()


def config_yaml_path(config_base_dir: Path | None = None) -> Path:
    return (config_base_dir or resolve_config_base_dir()) / "config.yaml"


def dotenv_path(config_base_dir: Path | None = None) -> Path:
    return (config_base_dir or resolve_config_base_dir()) / ".env"


def prompt_yaml_path(config_base_dir: Path | None = None) -> Path:
    return (config_base_dir or resolve_config_base_dir()) / "config_prompt.yaml"


def migration_reports_dir(config_base_dir: Path | None = None) -> Path:
    return (config_base_dir or resolve_config_base_dir()) / "migration-reports"
