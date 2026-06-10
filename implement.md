# HugeGraph-AI 配置系统迁移执行计划

**关联计划**: `graph-plan.md`  
**适用模块**: `hugegraph-llm/`  
**当前分支**: `refactor-config`

本文件是实现阶段的具体操作顺序。每个批次必须以测试或审计输出作为出口条件；前一批次未通过时，不进入下一批次。

## 1. 执行批次总览

Batch 0：基线审计与风险确认

- 主要文件：`hugegraph-llm/src/hugegraph_llm/config/`、`hugegraph-llm/src/tests/config/`。
- 出口条件：旧 env key、敏感字段、写盘路径、CWD 依赖清单完成。

Batch 1：建立失败优先的配置测试

- 主要文件：`hugegraph-llm/src/tests/config/`。
- 出口条件：新增测试能稳定复现当前缺陷，pytest 只因预期变更失败。

Batch 2：配置基础设施落地

- 主要文件：新增 `config/manager.py`、`config/paths.py`、`config/mapping.py`、`config/migration.py`。
- 出口条件：mapping、path、source、env 合并相关单测通过。

Batch 3：BaseConfig 与配置类接入

- 主要文件：`models/base_config.py`、`llm_config.py`、`hugegraph_config.py`、`admin_config.py`、`index_config.py`。
- 出口条件：配置类契约测试、deprecated wrapper 测试通过。

Batch 4：迁移与写盘安全闭环

- 主要文件：`manager.py`、`migration.py`、`generate.py`。
- 出口条件：Phase0/Phase1 迁移、patch-only、secret 不落盘测试通过。

Batch 5：PromptConfig 最小兼容与示例文档

- 主要文件：`prompt_config.py`、`models/base_prompt_config.py`、`config.example.yaml`、`.gitignore`。
- 出口条件：只读 fallback、示例 YAML、最小文档测试/审计通过。

Batch 6：消费面冒烟与收口

- 主要文件：`config/__init__.py`、必要消费者。
- 出口条件：配置测试、相关消费者测试、ruff 全部通过。

## 2. Batch 0：基线审计

**目标**: 在编码前把真实风险面固定下来，避免实现中途发现范围失控。

具体步骤：

1. 扫描配置文件：
   - `hugegraph-llm/src/hugegraph_llm/config/models/base_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/llm_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/hugegraph_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/admin_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/index_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/prompt_config.py`
   - `hugegraph-llm/src/hugegraph_llm/config/generate.py`
   - `hugegraph-llm/src/hugegraph_llm/config/__init__.py`
2. 扫描关键词：
   - `dotenv`
   - `set_key`
   - `dotenv_values`
   - `os.environ`
   - `update_env`
   - `generate_env`
   - `check_env`
   - `.env`
   - `config_prompt.yaml`
3. 输出四份清单，记录在实现日志或 PR 描述中：
   - `legacy_env_keys`: 旧 env key 全集。
   - `sensitive_paths`: 命中 `api_key`、`token`、`password`、`pwd`、`secret` 的字段。
   - `write_paths`: 所有可能写 `.env` / YAML 的路径。
   - `import_time_env_reads`: import-time `os.environ.get()` 的字段。

出口条件：

- 明确哪些字段进入 `_env_var_map`。
- 明确哪些字段进入 `_mutable_persisted_fields`。
- 明确 V1 不改的消费面，并列入 V1.1。

## 3. Batch 1：测试先行

**目标**: 先把 V1 合同写成测试，避免实现完成后无法判断是否满足 secret-only 和 patch-only 语义。

建议新增或拆分测试文件：

- `hugegraph-llm/src/tests/config/test_config_mapping_contract.py`：flat/nested mapping、global dotted path、mapping coverage。
- `hugegraph-llm/src/tests/config/test_config_env_priority.py`：process env、`.env secret-only`、非敏感 `.env` ignored matrix。
- `hugegraph-llm/src/tests/config/test_config_write_path.py`：`save()` secret 不落盘、patch-only、full dump 拒绝。
- `hugegraph-llm/src/tests/config/test_config_migration.py`：Phase0、Phase1、Phase2 检测和迁移。
- `hugegraph-llm/src/tests/config/test_config_path_resolution.py`：config base dir、deprecated env var、no CWD fallback。
- `hugegraph-llm/src/tests/config/test_config_prompt_minimal.py`：PromptConfig 只读 fallback 最小策略。

优先测试顺序：

1. `test_config_path_resolution_no_cwd_fallback`
2. `test_field_source_uses_global_dotted_paths`
3. `test_dotenv_secret_only_does_not_override_non_sensitive_yaml`
4. `test_process_env_overrides_yaml`
5. `test_update_config_rejects_full_dump`
6. `test_update_config_rejects_sensitive_non_null_path`
7. `test_save_does_not_persist_env_secret`
8. `test_phase0_env_migration_splits_sensitive_and_persisted_values`
9. `test_migration_report_json_contract`
10. `test_invalid_yaml_fail_fast`

出口条件：

- 新测试在当前实现上能暴露问题。
- 测试 fixture 全部使用 `tmp_path`，不得写仓库根目录 `.env` 或真实 `hugegraph-llm/config.yaml`。
- 不依赖外部 HugeGraph、LLM provider、Qdrant、Milvus。

## 4. Batch 2：配置基础设施

**目标**: 先实现纯函数和 ConfigManager 骨架，再动配置类。

建议新增文件：

- `hugegraph-llm/src/hugegraph_llm/config/paths.py`：`resolve_config_base_dir()`、`config.yaml` / `.env` / report 路径解析。
- `hugegraph-llm/src/hugegraph_llm/config/mapping.py`：flat/nested 转换、global dotted path 归一化、mapping audit。
- `hugegraph-llm/src/hugegraph_llm/config/manager.py`：`ConfigManager`、双层 config、source tracking、patch allowlist。
- `hugegraph-llm/src/hugegraph_llm/config/migration.py`：Phase 检测、legacy 迁移、报告生成、备份。

实现顺序：

1. `paths.py`
   - 支持 `HUGEGRAPH_LLM_CONFIG_DIR`。
   - 兼容 `HUGEGRAPH_AI_CONFIG_DIR` 并 warning。
   - 两者同时存在时 `HUGEGRAPH_LLM_CONFIG_DIR` 优先。
   - 禁止 fallback 到 CWD。
2. `mapping.py`
   - 实现 `join_global_path(section, nested_path)`。
   - 实现 `flat_to_nested()` / `nested_to_flat()`。
   - 实现 `is_sensitive_path()`。
   - 实现 mapping coverage audit。
3. `manager.py`
   - 定义 `FieldSource`。
   - 建立 `persisted_config` / `effective_config`。
   - 建立 `mutable_persisted_leaf_paths` 注册表。
   - 实现 env 合并但暂不替换全部配置类。
4. `migration.py`
   - 先实现 Phase 检测和报告数据结构。
   - 迁移写盘放到 Batch 4。

出口条件：

- `test_config_mapping_contract.py` 通过。
- `test_config_path_resolution.py` 通过。
- env 合并相关最小单测通过。

## 5. Batch 3：BaseConfig 与配置类接入

**目标**: 把现有配置类从 CWD `.env` 自动同步模式切到 ConfigManager 统一入口。

改动顺序：

1. `models/base_config.py`
   - 从 `BaseSettings` 改为 `BaseModel` 或等价的非 env-file 自动加载模型。
   - 移除 `env_path = os.path.join(os.getcwd(), ".env")` 依赖。
   - `__init__` 不再自动生成 `.env` 或写盘。
   - `update_config()` 接受 section-local flat patch，并转给 `ConfigManager.update_config()`。
   - `update_env()`、`generate_env()`、`check_env()` 保留 deprecated wrapper。
2. `llm_config.py`
   - 移除字段默认值中的 import-time `os.environ.get()`。
   - 增加 `_config_section = "llm"`。
   - 增加 `_flat_to_nested_mapping`。
   - 增加 `_env_var_map`，例如 `OPENAI_CHAT_API_KEY > OPENAI_API_KEY`。
   - 增加 `_mutable_persisted_fields`，排除 api key。
3. `index_config.py`
   - 移除 import-time `os.environ.get()` 和 `int(os.environ.get(...))`。
   - 补齐 Qdrant / Milvus env map。
   - 修正 docstring，避免仍写 “LLM settings”。
4. `hugegraph_config.py`
   - 标记 `graph_pwd` 为敏感。
   - 补齐 `GRAPH_URL`、`GRAPH_NAME`、`GRAPH_USER`、`GRAPH_PWD` 映射。
5. `admin_config.py`
   - 标记 `admin_token`、`user_token` 为敏感。
   - 补齐 `ADMIN_TOKEN`、`USER_TOKEN` 映射。
6. `config/__init__.py`
   - 初始化或暴露统一 ConfigManager。
   - 保持现有 import 兼容，避免业务代码一次性大改。

出口条件：

- 配置类实例化不创建 `.env`。
- deprecated wrapper 有 warning，不再把 secret 写入 YAML。
- `LLMConfig` / `IndexConfig` import 不读取 env。
- 现有 `test_config.py` 与新增配置契约测试通过。

## 6. Batch 4：迁移与写盘安全闭环

**目标**: 让 Phase0 / Phase1 旧配置可安全迁移，并确保所有写盘路径遵守 persisted/effective 边界。

实现顺序：

1. `migration.py`
   - 实现 Phase0 `.env` 解析。
   - 实现 Phase1 flat YAML 解析。
   - Phase2 nested YAML 存在时优先读取，不被 `.env` 非敏感 legacy key 覆盖。
2. 校验逻辑
   - 使用 `model_validate()` / `TypeAdapter`。
   - 校验失败直接终止，不生成 `config.yaml`、备份或报告。
3. 写盘逻辑
   - 非敏感 path 写入 nested YAML。
   - 敏感 path 写入或保留 `.env secret-only`。
   - `save()` 使用 temp + rename 原子写入。
   - 备份文件名包含 `migration_id`。
4. 报告逻辑
   - 生成 `<config_base_dir>/migration-reports/<migration_id>.md`。
   - 生成 `<config_base_dir>/migration-reports/<migration_id>.json`。
   - JSON 至少包含 `migration_id`、`from_phase`、`to_phase`、`config_base_dir`、`created_files`、`backup_files`、`sensitive_keys_retained`、`persisted_keys`、`unknown_keys`、`ignored_env_keys`、`warnings`。
5. `generate.py`
   - 保留旧入口兼容。
   - 新增或改为生成 YAML 示例 / secret-only `.env` 指引。

出口条件：

- Phase0 `.env` 迁移后，`OPENAI_API_KEY`、`GRAPH_PWD`、`ADMIN_TOKEN`、`USER_TOKEN`、`QDRANT_API_KEY` 等不进入 `config.yaml`。
- Phase2 YAML + legacy `.env` 共存时，`.env` 的 `GRAPH_URL` 等非敏感 key 不覆盖 YAML。
- `update_config(model_dump())`、section dump、nested mapping、sensitive non-null patch 全部失败。
- `update_config({"openai_chat_language_model": "gpt-4.1"})` 成功并只写非敏感 leaf。

## 7. Batch 5：PromptConfig 最小兼容与示例文档

**目标**: 不扩大 V1 范围，但避免 prompt 配置阻断主配置迁移。

执行步骤：

1. `prompt_config.py` / `models/base_prompt_config.py`
   - 确保主配置迁移校验不触发 prompt 写盘。
   - 缺少 `config_prompt.yaml` 且目录只读时，允许使用 package template 只读运行并 warning。
   - 显式保存 prompt 时再检查目录可写。
2. `hugegraph-llm/config.example.yaml`
   - 新增 nested YAML 示例。
   - 敏感 path 只写 `null`。
   - 不包含真实 token、password、API key。
3. `.gitignore`
   - 忽略真实 `config.yaml`。
   - 忽略 `.env`、`.env.bak*`、`config.yaml.bak*`。
   - 迁移报告是否忽略按最终实现判断；若报告可能包含用户路径和 key 名，默认建议忽略真实运行目录下报告。
4. 最小升级说明
   - 明确 `.env` 现在是 secret-only。
   - 区分 Docker compose `.env` 与 HugeGraph-AI secret `.env`。
   - 不宣称完整 rollback CLI 已存在。

出口条件：

- PromptConfig 相关测试通过。
- 示例 YAML 不含非空 sensitive 值。
- 文档不再把 `.env` 描述为通用配置文件。

## 8. Batch 6：收口验证

**目标**: 证明 V1 闭环可交付。

必跑命令：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/config/ -v --tb=short
uv run ruff format --check .
uv run ruff check .
```

条件性补跑：

API model / endpoint：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/models/ hugegraph-llm/src/tests/middleware/ -v --tb=short
```

operators：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/operators/ -v --tb=short
```

indices：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/indices/ -v --tb=short
```

pipeline / flow：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/integration/test_rag_pipeline.py -v --tb=short
```

人工审计清单：

- `rg -n "os\\.environ\\.get|BaseSettings|env_file|os\\.getcwd\\(\\).*\\.env|set_key|dotenv_values" hugegraph-llm/src/hugegraph_llm/config`
- `rg -n "api_key: [^n]|token: [^n]|password: [^n]|pwd: [^n]|secret: [^n]" hugegraph-llm/config.example.yaml`
- 检查迁移 JSON 报告不含 secret 明文。
- 检查 `config.yaml` 的 sensitive path 为省略或 `null`。

出口条件：

- 必跑命令通过。
- 条件性补跑按实际触及范围通过。
- 失败项若存在，必须明确属于 V1.1/V2 follow-up，不能影响 V1 hard gate。

## 9. 执行中的暂停点

以下任一情况出现时必须暂停重新对齐：

- 发现配置消费者依赖 `.env` 非敏感 key 覆盖 YAML，且无法在 V1 内兼容。
- 发现 API/operator 默认值必须同步改造，否则配置核心测试无法通过。
- 迁移需要修改 `hugegraph-python-client`。
- `PromptConfig` 无法使用只读 fallback，且会阻断主配置启动。
- 任何测试 fixture 需要真实外部服务才能验证配置核心行为。

## 10. 推荐实施顺序

实际编码按下面顺序推进：

```text
Batch 0 审计
  -> Batch 1 测试
  -> Batch 2 paths/mapping/manager 骨架
  -> Batch 3 BaseConfig + 四个配置类
  -> Batch 4 migration + patch-only save
  -> Batch 5 prompt 最小兼容 + example
  -> Batch 6 验证收口
```

每个批次结束后记录：

- 改了哪些文件。
- 新增或修改了哪些测试。
- 哪些 V1 需求已满足。
- 是否有 follow-up 项进入 V1.1/V2。
