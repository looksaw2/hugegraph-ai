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

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from ..manager import get_config_manager, warn_deprecated


class BaseConfig(BaseModel):
    """Base config model backed by ConfigManager.

    The class intentionally avoids pydantic-settings env-file loading and does
    not write config files during initialization.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    _config_section: ClassVar[str] = ""
    _flat_to_nested_mapping: ClassVar[dict[str, str]] = {}
    _env_var_map: ClassVar[dict[str, list[str]]] = {}
    _mutable_persisted_fields: ClassVar[set[str]] = set()

    def __init__(self, **data: Any) -> None:
        manager = get_config_manager()
        manager_values = manager.get_section_flat(self.__class__)
        manager_values.update(data)
        super().__init__(**manager_values)

    def update_config(self, patch: dict[str, Any] | None = None) -> None:
        manager = get_config_manager()
        if patch is None:
            manager.persist_current_config(self)
        else:
            manager.update_section(self.__class__, patch)
        refreshed = manager.get_section_flat(self.__class__)
        for key, value in refreshed.items():
            setattr(self, key, value)

    def generate_env(self):
        warn_deprecated("generate_env")
        self.update_config()

    def update_env(self):
        warn_deprecated("update_env")
        self.update_config()

    def check_env(self):
        warn_deprecated("check_env")
        manager = get_config_manager()
        manager.reload()
        refreshed = manager.get_section_flat(self.__class__)
        for key, value in refreshed.items():
            setattr(self, key, value)
