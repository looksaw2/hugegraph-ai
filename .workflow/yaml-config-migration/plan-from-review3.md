# HugeGraph-AI 配置系统迁移 V1 可执行计划（Review3）

## 0. 来源与定位

本计划基于 `.workflow/yaml-config-migration/plan-from-review2.md`、本地
`修改意见2.md`、用户补充评论与 Issue 234，作为下一轮实现的 V1
任务书。`plan-from-review2.md` 仍可保留为完整设计草案，本文件只保留 V1
必须落地的执行切片，并把 V1.1 / V2 项明确移出主线。

关联 Issue:

- <https://github.com/apache/hugegraph-ai/issues/234>

核心定位：

- V1 不是“大一统配置系统”，而是“兼容旧入口的有效配置事实源”。
- V1 先补 `ConfigSnapshot` + `ConfigFacade`，避免业务方直接依赖
  `ConfigManager` 内部状态。
- V1 先修 import 写盘、secret 泄露、full dump 写盘、API/operator 默认值冻结和
  request 级 graph 配置污染这些高风险点。
- Prompt 全生命周期、UI 写回体验重构、部署 grep gate、rollback CLI、hot reload
  不进入 V1 主线。

## 1. Review3 相对 Review2 的调整

| 调整点 | Review2 倾向 | Review3 决策 |
|---|---|---|
| V1 半径 | V1 覆盖 registry、snapshot、facade、迁移、API、operator、部分消费者、文档 | 保留方向，拆成强依赖里程碑，先交付兼容事实源，再处理写盘与高风险消费者 |
| API/operator 默认值 | 已列为 V1 高优先级，但与大面积消费者迁移并列 | 提升为单独 M5 hard gate，只处理 import-time mutable config 默认值和 request model 动态默认冻结 |
| ConfigManager 角色 | 可作为主要 loader/writer 扩展 | 降为内部实现；公开入口是 `ConfigFacade` 和 legacy settings facade |
| 旧导入兼容 | 作为 V1 必做之一 | 提升为架构前置条件；没有 legacy facade 就不迁消费者 |
| Migration | doctor/plan/diff/apply 全部进入 V1 | 保留四步，但 V1 只做无副作用预览、事务 apply、脱敏报告；完整 rollback CLI 延后 |
| Prompt | V1 去掉 import 写盘，完整生命周期延后 | 保持不变，并明确 V1 不改 Prompt 存储模型 |
| UI 写回 | V1 最小消费者迁移里涉及 `configs_block.py` | V1 只保证旧 wrapper 安全；完整 Gradio 写回和 role 级联放 V1.1，除非阻塞测试 |
| 文档 | V1 更新升级指南和示例 | V1 只更新与新契约直接相关的最小文档，部署全量 grep gate 延后 |

## 2. V1 目标与非目标

### 2.1 V1 目标

V1 交付以下闭环：

```text
ConfigKeyRegistry
  -> ConfigSnapshot
  -> ConfigFacade
  -> LegacySettingsFacade
  -> secret-only loader
  -> patch-only transaction writer
  -> migration doctor / plan / diff / apply
  -> API/operator runtime default hardening
```

V1 成功的定义：

- 旧代码继续可以 `from hugegraph_llm.config import llm_settings, huge_settings,
  admin_settings, index_settings, prompt`。
- 读取配置和导入配置模块不会创建或改写 `config.yaml`、`.env`、
  `config_prompt.yaml` 或迁移报告。
- `.env` 只作为 secret-only legacy/运行时来源；非敏感 `.env` key 不覆盖 YAML。
- YAML 只持久化非敏感配置；secret 不进入 YAML、diff、报告、错误或日志明文。
- 写盘只接受 allowlisted leaf patch，拒绝 full dump、section dump、nested mapping 和
  sensitive path。
- 迁移可先 doctor / plan / diff，再事务 apply；失败不破坏原文件。
- API request model 和 operator 不再把可变配置值冻结在 import time。
- `rag_api.py` 的 request graph override 不再污染全局 settings。

### 2.2 V1 非目标

| 项目 | 阶段 | 说明 |
|---|---|---|
| hot reload | V2 | 与 snapshot 不变性和失败回退策略冲突，单独设计 |
| 完整 rollback CLI | V2 | V1 只做事务写入、备份、失败无副作用 |
| 全仓库消费者彻底去全局 settings | V2 | V1 先保 legacy facade，避免改动半径失控 |
| PromptConfig 完整生命周期 | V1.1 | V1 只移除 import 写盘和动态默认冻结 |
| Gradio UI 写回体验重构 | V1.1 | V1 只保证旧 wrapper 安全，不重构整套 UI |
| 部署文档 grep gate / Docker / Helm 全量收敛 | V1.1 | V1 只更新配置迁移关键说明 |

## 3. 当前基线与待验证假设

以下基线来自 Review2 与本地观察，M0 必须重新用代码搜索确认：

- `hugegraph_llm/config/manager.py` 已有 `ConfigManager`、
  `persisted_config`、`effective_config`、`field_source`、patch 写盘和
  Phase0 / Phase1 迁移雏形。
- `hugegraph_llm/config/mapping.py` 已有 flat/nested helper 和 sensitive path 判断。
- `hugegraph_llm/config/paths.py` 已把 config base dir 锚定到
  `HUGEGRAPH_LLM_CONFIG_DIR` / `HUGEGRAPH_AI_CONFIG_DIR` / module root。
- `BaseConfig.__init__` 当前从 manager 读取 effective values，不直接写盘。
- `config/__init__.py` 仍创建全局 settings 与 `prompt`，并存在 import 写
  `config_prompt.yaml` 的风险。
- `configs_block.py` 仍有 `update_env()` 写盘与 `.env` 级联判断逻辑。
- `rag_api.py` 仍可能在 request 期间修改全局 `huge_settings` / `llm_settings`。
- `operator_list.py`、`semantic_id_query.py` 等路径可能存在 import-time 读取
  `huge_settings` 作为默认参数的风险。

M0 输出必须是消费面矩阵，不能直接进入实现。

## 4. V1 架构契约

### 4.1 Canonical Key Registry

Registry 是配置 key 的唯一事实源。mapping、env alias、sensitive 判断、
mutable allowlist、migration 输出都从 registry 派生。

建议结构：

```python
@dataclass(frozen=True)
class ConfigKeySpec:
    canonical_key: str
    section: str
    field_name: str
    yaml_path: str
    env_aliases: tuple[str, ...]
    annotation: Any
    default: Any
    is_sensitive: bool
    is_mutable: bool
    is_runtime_overridable: bool
    is_legacy_supported: bool
```

硬规则：

- `canonical_key` 使用 global dotted leaf path，例如
  `llm.openai.chat.api_key`。
- 同一 canonical key、YAML leaf path、env alias 不能冲突；显式 alias 例外必须在
  registry 中声明。
- `env_aliases` 是有序 tuple，顺序就是优先级。
- mutable allowlist 必须由 registry 生成，不能散落在 manager 中。
- sensitive 判断由字段名规则和显式 registry override 合成。
- mutable key 不得是 sensitive key。

### 4.2 ConfigSnapshot

Snapshot 是一次加载后的不可变配置状态。

| 字段 | 含义 |
|---|---|
| `persisted_config` | 可写回 YAML 的非敏感配置 |
| `effective_config` | default + YAML + `.env` secret + process env 的合并结果 |
| `field_source` | canonical key -> source |
| `phase` | missing / phase0 / phase1 / phase2 |
| `config_base_dir` | 解析后的配置目录 |
| `diagnostics` | ignored key、unknown key、conflict、warning，全部脱敏 |
| `registry_version` | registry 版本或 hash |

`FieldSource` 统一使用：

```python
FieldSource = Literal[
    "effective_default",
    "yaml_persisted",
    "migrated_persisted",
    "dotenv_secret",
    "process_env_override",
    "explicit_persisted_patch",
    "runtime_only_override",
]
```

不变式：

- snapshot 创建后不可变。
- `field_source` key 必须全部是 canonical key。
- `effective_config` 永远不能 full dump 到 YAML。
- diagnostics、diff、error、report 不得包含 secret 明文。

### 4.3 ConfigFacade

Facade 是 V1 后配置系统的对外入口，业务方不直接依赖 `ConfigManager` 内部 dict。

接口草案：

```python
class ConfigFacade:
    def current_snapshot(self) -> ConfigSnapshot: ...
    def reload(self) -> ConfigSnapshot: ...
    def get_section(self, section: str) -> Mapping[str, Any]: ...
    def get_flat_section(self, config_class: type[Any]) -> dict[str, Any]: ...
    def update_config(self, patch: Mapping[str, Any]) -> ConfigSnapshot: ...
    def update_secret_env(self, patch: Mapping[str, Any]) -> ConfigSnapshot: ...
    def migration_doctor(self) -> MigrationDoctorResult: ...
    def migration_plan(self) -> MigrationPlan: ...
    def migration_diff(self, plan: MigrationPlan) -> MigrationDiff: ...
    def migration_apply(self, plan: MigrationPlan) -> MigrationReport: ...
```

Facade 规则：

- 读操作不写盘。
- 写操作必须走 transaction writer。
- `ConfigManager` 可作为内部 loader/writer 保留，但不作为业务公开 API。
- tests 可以通过 facade 构造临时 base dir，不依赖 CWD。

### 4.4 Legacy Settings Facade

旧入口必须继续可用：

```python
from hugegraph_llm.config import (
    llm_settings,
    huge_settings,
    admin_settings,
    index_settings,
    prompt,
)
```

契约：

- 属性读取从当前 snapshot 解析。
- `BaseConfig.update_config(patch)` 支持 section-local flat leaf patch，并转换为
  facade global dotted patch。
- 直接 `setattr(settings, field, value)` 只影响该对象的临时内存值，不作为 YAML
  写盘入口。
- `update_env()`、`generate_env()`、`check_env()` 保留兼容 warning，但不得无参 dump
  effective config，不得把 secret 写入 YAML。
- 如旧 UI 仍依赖 `setattr + update_env()`，wrapper 只能提取 changed mutable
  non-sensitive fields，并必须有安全测试。

### 4.5 Secret-only `.env`

优先级：

```text
process os.environ / K8s Secret
  > .env secret-only
  > config.yaml
  > registry / pydantic default
```

决策矩阵：

| 来源 | key 类型 | V1 行为 |
|---|---|---|
| process env | known sensitive | highest effective override，不持久化 |
| process env | known non-sensitive | runtime override，不持久化 |
| `.env` | known sensitive | effective override，不持久化 |
| `.env` | known non-sensitive | 进入 diagnostics/report，不覆盖 YAML |
| `.env` | unknown sensitive-like | 进入 diagnostics/report，默认不生效 |
| `.env` | unknown non-sensitive | 进入 diagnostics/report，默认不生效 |
| YAML | known non-sensitive | persisted 主来源 |
| YAML | known sensitive non-null | doctor warning；save/apply 时拒绝或置空 |

### 4.6 Patch-only transaction writer

允许：

```python
facade.update_config({"llm.openai.chat.language_model": "gpt-4.1"})
llm_settings.update_config({"openai_chat_language_model": "gpt-4.1"})
```

拒绝：

```python
facade.update_config({"llm": {"openai": {"chat": {"language_model": "gpt-4.1"}}}})
facade.update_config({"llm.openai.chat.api_key": "sk-secret"})
llm_settings.update_config(llm_settings.model_dump())
```

拒绝规则：

- patch value 是 mapping / section object。
- path 不在 registry。
- path 不在 mutable allowlist。
- path 是 sensitive key。
- path 是 metadata key。
- patch 形状等于 full dump、section dump 或 effective dump。
- key 数量阈值只能作为兜底，不能作为识别 full dump 的主逻辑。

事务规则：

- 所有输出先在内存构造并校验。
- 写入使用 temp file + fsync + atomic rename。
- 写入失败保留原文件。
- secret 文件和备份权限为 `0600`。

### 4.7 Migration doctor / plan / diff / apply

V1 保留四步，但只交付可验证迁移闭环，不交付完整 rollback CLI。

Doctor 只读诊断：

- 当前 phase。
- Phase0 `.env`、Phase1 YAML、Phase2 YAML 是否存在。
- `.env` 中 known sensitive、known non-sensitive、unknown sensitive-like、
  unknown non-sensitive。
- YAML 中 sensitive non-null。
- registry 缺失、重复 YAML path、重复 env alias。
- 目标目录可写性。
- 备份目标是否会覆盖。

Plan 不写盘：

- 将写入 YAML 的 canonical key。
- 将保留在 `.env` 的 secret key。
- 将忽略或进入 report 的 unknown key。
- 将创建的 backup/report 路径。
- 风险和 warnings。

Diff 脱敏展示：

- persisted config before/after。
- effective config before/after。
- source change。
- secret 只显示 `***`、changed、unchanged 或 source 状态。

Apply 事务执行：

```text
doctor
  -> plan
  -> validate all values
  -> build output in memory
  -> write temp files
  -> chmod secret files/backups 0600
  -> atomic rename
  -> write redacted report
  -> reload snapshot
```

失败规则：

- 校验失败不得创建或覆盖 `config.yaml`。
- 校验失败不得改写 `.env`。
- 写入失败保留原文件。
- report 不含 secret 明文。

### 4.8 API/operator runtime default hardening

V1 必须处理高风险冻结点：

- request model 的可变配置默认值改为 `None`。
- endpoint 处理请求时从当前 snapshot / prompt runtime 读取默认值。
- OpenAPI 不展示伪动态默认值。
- operator 构造默认参数不得绑定 import-time `huge_settings.xxx` 等 mutable config。
- request-scoped graph config 不修改全局 settings。

V1 不要求迁移所有消费者，只处理 import-time mutable config 默认值、API request model
动态默认值和 `rag_api.py` 全局污染路径。

### 4.9 Prompt 边界

V1 只做边界修复：

- 导入 `hugegraph_llm.config` 不调用 `prompt.ensure_yaml_file_exists()`。
- `config_prompt.yaml` 创建只发生在显式命令或应用启动显式 ensure 中。
- 只读目录下导入配置不失败。
- request model / API 不把 prompt 当前值冻结为 class-level 默认值。

## 5. 里程碑与任务

### M0. 基线矩阵与边界确认

目标：先确认真实改动面，不直接编码。

- [ ] M0.1 搜索配置入口、全局对象、`update_env()`、`generate_env()`、
  `check_env()`、`dotenv`、`os.environ`、`config_prompt.yaml`。
- [ ] M0.2 搜索 API request model 中来自 config/prompt 的默认值。
- [ ] M0.3 搜索 operator / flow / index 构造默认参数中 import-time 读取 settings 的点。
- [ ] M0.4 输出消费面矩阵：文件、行号、当前行为、风险类型、V1 是否处理、
  V1.1/V2 是否延后。
- [ ] M0.5 梳理现有 `ConfigManager` / `mapping` / `migration` 已满足项与缺口。

出口条件：

- 有消费面矩阵。
- V1 处理点与延后点明确。
- 没有新增代码。

### M1. Registry + Snapshot + Facade 骨架

目标：建立事实源和不可变读取入口。

- [ ] M1.1 新增 `config/registry.py`，从配置类 `_config_section`、
  flat/nested mapping、env map、mutable fields、model fields 生成 `ConfigKeySpec`。
- [ ] M1.2 增加 registry 校验：无未映射字段、无重复 YAML leaf、无重复 env alias、
  mutable 不含 sensitive。
- [ ] M1.3 新增 `config/snapshot.py`，定义不可变 `ConfigSnapshot`、
  diagnostics、source type。
- [ ] M1.4 新增 `config/facade.py`，实现 `current_snapshot()`、`reload()`、
  `get_section()`、`get_flat_section()`。
- [ ] M1.5 将 `ConfigManager.reload()` 输出转换为 snapshot，manager 内部 mutable dict
  不直接暴露给业务。

必须测试：

- `test_registry_complete_for_config_models`
- `test_registry_rejects_duplicate_yaml_path`
- `test_registry_rejects_mutable_sensitive_conflict`
- `test_snapshot_is_immutable`
- `test_facade_loads_snapshot`

出口条件：

- registry 覆盖 LLM / HugeGraph / Admin / Index 全字段。
- snapshot 不可变。
- facade 能在临时 config base dir 下读取 snapshot。

### M2. Legacy facade + no-write-on-read + Prompt 边界

目标：保持旧导入可用，同时移除 import 写盘。

- [ ] M2.1 让 `llm_settings`、`huge_settings`、`admin_settings`、`index_settings`
  从 facade snapshot 读取值。
- [ ] M2.2 实现 `BaseConfig.update_config(patch)` 的 section-local patch 到
  facade global patch 转换。
- [ ] M2.3 明确 `setattr` 行为：只改临时对象，不自动写盘。
- [ ] M2.4 旧 `update_env()` / `generate_env()` / `check_env()` 发 warning 且安全，
  不 dump effective config，不写 secret。
- [ ] M2.5 修改 `config/__init__.py`，导入时不调用
  `prompt.ensure_yaml_file_exists()`。
- [ ] M2.6 将 prompt YAML 创建保留在显式 generate/app startup 入口。

必须测试：

- `test_legacy_settings_import_contract`
- `test_legacy_settings_reads_current_snapshot`
- `test_deprecated_wrappers_are_safe`
- `test_import_config_has_no_write_side_effects`
- `test_readonly_config_dir_import_does_not_write_prompt`

出口条件：

- 导入 `hugegraph_llm.config` 不创建 `config.yaml`、`.env`、`config_prompt.yaml`、
  migration report。
- 旧 settings 属性读取兼容。
- 旧 wrapper 不泄露 secret，不 full dump。

### M3. Secret-only loader + patch-only transaction writer

目标：完成安全读取和安全写盘基础。

- [ ] M3.1 用 registry 实现 process env 与 `.env` secret-only override。
- [ ] M3.2 `.env` known non-sensitive key 不覆盖 YAML，只进入 diagnostics/report。
- [ ] M3.3 空字符串 env 不覆盖 YAML/default。
- [ ] M3.4 类型转换 fail-fast，错误信息脱敏。
- [ ] M3.5 实现 `ConfigFacade.update_config()`，仅接受 global dotted leaf patch。
- [ ] M3.6 patch 校验走 registry allowlist + leaf-shape，拒绝 nested mapping、
  section dump、full dump、metadata key、sensitive key。
- [ ] M3.7 写盘只序列化 persisted config，secret path 省略或仅允许 null placeholder。
- [ ] M3.8 写盘使用 temp + fsync + atomic rename。

必须测试：

- `test_process_env_overrides_dotenv_yaml_default`
- `test_dotenv_secret_only_contract`
- `test_dotenv_non_sensitive_key_is_ignored`
- `test_empty_env_does_not_override`
- `test_secret_redacted_from_type_errors`
- `test_patch_only_write_contract`
- `test_patch_rejects_full_dump_and_section_dump`
- `test_patch_rejects_sensitive_path`
- `test_secret_not_persisted_to_yaml`
- `test_atomic_write_failure_preserves_original`

出口条件：

- priority、secret-only、patch-only、transaction writer 测试通过。
- `effective_config` 不存在任何写回 YAML 的路径。

### M4. Migration doctor / plan / diff / apply

目标：迁移可预览、可诊断、可脱敏、可事务 apply。

- [ ] M4.1 实现 `migration_doctor()`，只读诊断 phase、冲突、unknown key、
  sensitive non-null、目录权限。
- [ ] M4.2 实现 `migration_plan()`，输出将写入 YAML 的 key、保留 secret、
  ignored key、backup/report 路径。
- [ ] M4.3 实现 `migration_diff()`，展示 persisted/effective before/after 与
  source change，secret 全脱敏。
- [ ] M4.4 实现 `migration_apply()`，按 plan 事务写入，并生成脱敏报告。
- [ ] M4.5 `.env.bak` / `config.yaml.bak` 文件权限设为 `0600`，不覆盖旧备份。

必须测试：

- `test_migration_doctor_phase0_env`
- `test_migration_plan_phase1_yaml`
- `test_migration_diff_redacts_secret`
- `test_migration_apply_phase0_preserves_secret_env`
- `test_migration_apply_phase1_removes_sensitive_yaml_value`
- `test_migration_apply_failure_has_no_side_effects`
- `test_migration_backup_permissions_are_0600`

出口条件：

- Phase0、Phase1、Phase2 + `.env`、Phase1 + `.env` 关键矩阵通过。
- apply 失败不改写 `.env`、`config.yaml`、backup、report。

### M5. API/operator 默认值与 request-scoped graph config

目标：修掉 V1 高风险消费者，不做全仓库迁移。

- [ ] M5.1 审计 API request model 中来自 config/prompt 的默认值，改为 `None`。
- [ ] M5.2 endpoint 层从当前 snapshot / prompt runtime 读取默认值。
- [ ] M5.3 确认 OpenAPI 不展示伪动态默认值。
- [ ] M5.4 审计 operator 构造默认参数，移除 `huge_settings.xxx` 等
  import-time mutable config 默认值。
- [ ] M5.5 修改 `rag_api.py` 的 graph config 处理，不再临时修改全局 settings。
- [ ] M5.6 引入 request graph override 对象，并传递给直接相关的 flow/operator/client
  factory；无 override 时继续使用当前 snapshot。

必须测试：

- `test_api_defaults_resolve_from_runtime_snapshot`
- `test_openapi_does_not_freeze_dynamic_config_defaults`
- `test_operator_defaults_are_runtime_resolved`
- `test_request_graph_config_does_not_mutate_global_settings`
- `test_request_graph_override_does_not_pollute_next_request`

出口条件：

- API 省略字段使用 runtime snapshot。
- operator 不在 import time 绑定 mutable config。
- 单次 request override 不污染全局 snapshot/settings。

### M6. 最小消费者收敛、文档与 CI gate

目标：只收敛 V1 必须触碰的写入口和文档，不做 UI 全量重构。

- [ ] M6.1 迁移 `/config/*` API 写入路径到 facade patch 或 secret writer。
- [ ] M6.2 只在必要范围内适配 `configs_block.py`，保证旧 wrapper 安全；完整 role
  级联改造延后。
- [ ] M6.3 对模型初始化、embedding、reranker、vector index 读取 settings 的路径只做
  必要适配，避免 V1 全量重构。
- [ ] M6.4 更新 `hugegraph-llm/config-migration-upgrade-guide.md`，说明 V1 真实范围。
- [ ] M6.5 更新 `config.example.yaml` 与 `.env` 示例，区分 secret `.env`、
  compose `.env`、legacy full `.env`。
- [ ] M6.6 记录 V1.1 / V2 deferred 列表，避免后续误判为 V1 缺失。

必须测试：

- `test_config_api_write_uses_facade_patch`
- `test_config_ui_wrapper_does_not_dump_effective_config`，仅在触碰 UI wrapper 时新增
- `test_minimal_consumers_keep_legacy_read_contract`

出口条件：

- V1 触碰的消费者都有 contract tests。
- 文档明确 `.env` secret-only、patch-only、migration 四步和 V1 非目标。
- config tests、API/runtime default tests、ruff 通过。

## 6. 测试文件建议

V1 推荐新增或拆分以下测试文件。若现有测试结构不适合，可先合并到
`src/tests/config/`，但测试名必须体现风险。

| 文件 | 覆盖 |
|---|---|
| `hugegraph-llm/src/tests/config/test_registry_contract.py` | registry 完整性、重复 path、env alias 顺序、mutable/sensitive 冲突 |
| `hugegraph-llm/src/tests/config/test_snapshot_facade.py` | snapshot immutability、facade reload、legacy settings 兼容 |
| `hugegraph-llm/src/tests/config/test_no_write_on_read.py` | import 不写文件、只读目录导入 |
| `hugegraph-llm/src/tests/config/test_secret_only_dotenv.py` | `.env` secret-only、process env 优先、非敏感 `.env` ignored |
| `hugegraph-llm/src/tests/config/test_patch_writer.py` | patch-only、reject full dump、secret not persisted、atomic write |
| `hugegraph-llm/src/tests/config/test_migration_workflow.py` | doctor/plan/diff/apply、Phase0/Phase1、失败无副作用 |
| `hugegraph-llm/src/tests/config/test_api_runtime_defaults.py` | API 默认值 runtime resolve、OpenAPI 不固化动态默认 |
| `hugegraph-llm/src/tests/config/test_request_scoped_graph_config.py` | request graph override 不污染全局 |

最低验证命令：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/config/ -v --tb=short
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/api/ -v --tb=short
uv run ruff format --check .
uv run ruff check .
```

如果 `src/tests/api/` 当前没有独立目录，runtime default tests 可暂放在
`src/tests/config/` 或 `src/tests/integration/`，但文件名和测试名必须明确指向
API/operator 默认值冻结风险。

## 7. V1 验收标准

### 7.1 功能验收

| ID | 验收项 |
|---|---|
| AC-F1 | registry 覆盖所有配置模型字段，能生成 canonical key、YAML path、env alias、mutable allowlist |
| AC-F2 | facade 能返回不可变 snapshot，业务方无需读取 manager 内部 dict |
| AC-F3 | 旧导入 `llm_settings` 等可用，读取当前 snapshot |
| AC-F4 | 导入 `hugegraph_llm.config` 不创建或覆盖配置文件 |
| AC-F5 | `.env` secret 生效，`.env` 非敏感 legacy key 不覆盖 YAML |
| AC-F6 | patch-only 写盘可写非敏感 leaf，拒绝 secret、full dump、section dump |
| AC-F7 | migration doctor/plan/diff/apply 可分别执行，apply 失败无副作用 |
| AC-F8 | API 省略字段使用 runtime snapshot，不使用 import-time 旧默认 |
| AC-F9 | request graph config 不污染全局 settings |

### 7.2 安全验收

| ID | 验收项 |
|---|---|
| AC-S1 | YAML、report、log、diff、error 中不出现 secret 明文 |
| AC-S2 | `.env.bak` 和 YAML backup 权限为 `0600` |
| AC-S3 | `update_config()` 不能写入 sensitive path |
| AC-S4 | 迁移失败不改写 `.env`、`config.yaml`、backup、report |
| AC-S5 | `ConfigSnapshot` 不暴露可变 secret dict 给调用方修改 |

### 7.3 兼容验收

| ID | 验收项 |
|---|---|
| AC-C1 | 旧 `.env` 可通过 plan/apply 迁移，secret 保留 |
| AC-C2 | Phase1 flat YAML 可迁移，sensitive non-null 不进入 YAML |
| AC-C3 | Phase2 YAML + `.env` secret-only 共存可启动 |
| AC-C4 | 旧 wrapper 保留 warning，不泄露 secret，不 dump effective config |
| AC-C5 | 旧属性读取路径在 V1 仍工作，未迁移消费者不需要一次性改造 |

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| legacy facade 行为与 Pydantic model 行为不一致 | 旧调用方读写异常 | V1 只保证属性读取和 patch 写入；直接 setattr 明确为临时态 |
| snapshot 不变性与旧 UI 写回习惯冲突 | UI 可能依赖 `setattr + update_env()` | V1 wrapper 提供安全兼容，完整 UI 写回放 V1.1 |
| registry 一次覆盖所有字段容易漏 | source/migration 口径不一致 | M1 测试 hard gate：字段覆盖、重复 path、重复 env alias |
| migration apply 写盘失败 | 配置损坏 | temp + fsync + atomic rename + failure tests |
| API 默认值改为 `None` 影响 OpenAPI | 用户看到默认值消失 | 文档说明 runtime default；OpenAPI 不展示伪动态默认 |
| request-scoped graph override 传递过深 | Flow/operator 改动扩大 | V1 只改 API 直接路径和关键 factory，其他消费者延后 |
| secret 脱敏遗漏 | 安全风险 | 统一 redaction helper，测试覆盖 error、diff、report、diagnostics |

## 9. V1.1 / V2 后续清单

| 阶段 | 项目 |
|---|---|
| V1.1 | PromptConfig 完整生命周期：模板复制、用户可写目录、只读部署策略 |
| V1.1 | Gradio UI 写回体验重构，所有写盘改 patch facade |
| V1.1 | `configs_block.py` role 级联基于 field source，而不是 `.env` 文件存在性 |
| V1.1 | README / Docker / Helm / 部署文档全量收敛与 grep gate |
| V2 | rollback CLI，按 migration id 精确恢复备份 |
| V2 | hot reload / snapshot refresh strategy |
| V2 | 全仓库消费者彻底去 legacy global settings |

## 10. 推荐执行顺序

```text
M0 baseline matrix
  -> M1 registry + snapshot + facade
  -> M2 legacy facade + no-write-on-read
  -> M3 secret-only loader + patch writer
  -> M4 migration workflow
  -> M5 API/operator runtime defaults + request-scoped graph
  -> M6 minimal consumers + docs + CI
```

执行原则：

- 没有 registry，不做迁移输出。
- 没有 snapshot/facade，不迁消费者。
- 没有 no-write-on-read 测试，不改 Prompt 或旧全局对象。
- 没有 patch-only writer，不开放写盘入口。
- 没有 doctor/plan/diff，不允许自动 apply。
- API/operator 默认值冻结是 V1 hard gate，但只处理高风险动态配置点。
