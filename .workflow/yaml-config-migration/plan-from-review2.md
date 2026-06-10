# HugeGraph-AI 配置系统迁移新计划（基于三条评论与修改意见2）

## 0. 来源与定位

本计划替代当前 `.workflow/yaml-config-migration/plan.md` 作为下一轮实现计划输入。它不否定原计划里的技术方向，而是按最新评论把 V1 范围重新切小，避免一次实现同时触碰 import 副作用、全局单例、Prompt 默认值冻结、部署兼容、写盘事务和回滚语义。

来源：

- 飞书 Wiki：`方案：HugeGraph-AI 配置系统迁移计划`
- 飞书 Wiki：`从V2升级到v3改了什么`
- 飞书 Wiki：`Graph-AI配置存储重构版本迭代4->5`
- 用户补充的三条评论：
  - 总体评分 `7.3/10`，方向正确，但 V1 范围过大。
  - `API / operator 默认值审计` 应提升为更高优先级。
  - `ConfigManager` 外需要补 `ConfigSnapshot` 与兼容 facade。
- 本地评审意见：[修改意见2.md](/home/looksaw/hugegraph-ai/修改意见2.md)

关联 Issue：

- <https://github.com/apache/hugegraph-ai/issues/234>

## 1. 最新评论采纳摘要

| 评论 / 修改意见 | 核心判断 | 本计划处理 |
|---|---|---|
| 总体评分 `7.3/10` | 方向正确，但不能原样进入实现，V1 半径过大 | V1 收敛为“有效配置事实源 + 兼容 facade + 可验证迁移” |
| `canonical key registry` | 需要先建立统一事实源，否则 mapping、env alias、sensitive、mutable allowlist 分散 | V1 P0 新增 registry，作为 snapshot/facade 和迁移的底座 |
| `ConfigSnapshot + facade` | 当前仓库大量旧消费者直接 import 全局 settings，强推 ConfigManager 会失控 | V1 P0 新增不可变 snapshot 和兼容 facade，旧全局对象先代理到 snapshot |
| `no-write-on-read` | import 和构造配置对象不能创建或修改配置文件 | V1 P0 硬契约，导入 config 模块不得写 `config.yaml` / `.env` / `config_prompt.yaml` |
| API/operator 默认值冻结 | request model / class definition 可能把旧默认值固化 | V1 P0 审计并优先修 request model、endpoint 补默认、operator 默认参数 |
| request-scoped graph config | `rag_api.py` 临时修改全局 `huge_settings` 会污染后续请求 | V1 P0 改为 request scoped override / snapshot 派生 |
| migration doctor/plan/diff/apply | 自动迁移风险过大，用户看不到将发生什么 | V1 P0 提供可验证迁移流程，apply 前可诊断、预览、diff |
| secret redaction | secret 不能只防止落盘，还要防日志、错误、diff、报告泄露 | V1 P0 脱敏贯穿 error、report、doctor、diff、log |
| Prompt / UI 写回 | 正确但昂贵，不应塞入 V1 主线 | V1 只消除 import 写盘与默认值冻结；完整 Prompt 生命周期和 UI 写回放 V1.1 |

## 2. V1 核心结论

V1 不再是“大一统配置系统”，而是：

```text
canonical key registry
  -> ConfigSnapshot
  -> ConfigFacade / legacy settings facade
  -> transaction writer
  -> migration doctor / plan / diff / apply
```

V1 的目标是建立稳定、安全、兼容的配置事实源，并让旧消费者继续工作。全量消费者迁移、完整部署 grep gate、rollback CLI、Prompt 全生命周期和 UI 写回不进入 V1 主线。

## 3. 当前仓库基线

已观察到的本地状态：

- `hugegraph-llm/src/hugegraph_llm/config/manager.py` 已有 `ConfigManager`、`persisted_config`、`effective_config`、`field_source`、patch 写盘和 Phase0/Phase1 迁移雏形。
- `mapping.py` 已有 flat/nested helper 和 sensitive path 判断。
- `paths.py` 已把 config base dir 锚定到 `HUGEGRAPH_LLM_CONFIG_DIR` / `HUGEGRAPH_AI_CONFIG_DIR` / module root。
- `BaseConfig.__init__` 当前从 manager 读取 effective values，不直接写盘。
- `config/__init__.py` 当前仍会创建全局 `llm_settings`、`huge_settings`、`admin_settings`、`index_settings`、`prompt`，并调用 `prompt.ensure_yaml_file_exists()`，这是 import 写盘风险点。
- `configs_block.py` 仍有 `update_env()` 写盘与 `.env` 级联判断逻辑。
- `rag_api.py` 仍存在 request 期间直接改全局 `huge_settings` / `llm_settings` 的路径。
- `operator_list.py`、`semantic_id_query.py` 等仍有 import-time 读取 `huge_settings` 作为默认参数的高风险点。
- 根目录有未跟踪 [修改意见2.md](/home/looksaw/hugegraph-ai/修改意见2.md)，内容强调 V1 需补 facade/snapshot 并降低实现半径。

## 4. V1 范围

### 4.1 V1 必做

| ID | 范围 | 说明 |
|---|---|---|
| V1-R1 | Canonical key registry | 所有配置 key 的唯一事实源 |
| V1-R2 | ConfigSnapshot | 一次加载结果的不可变快照 |
| V1-R3 | ConfigFacade | 对外统一读写入口，屏蔽 ConfigManager 内部状态 |
| V1-R4 | Legacy settings facade | 旧 `llm_settings` 等导入路径继续可用 |
| V1-R5 | No-write-on-read | import / 构造 / 读取不得写文件 |
| V1-R6 | Secret-only `.env` | process env > `.env` secret > YAML > default |
| V1-R7 | Patch-only 写盘 | 只允许 allowlisted leaf patch 写 YAML |
| V1-R8 | Migration doctor/plan/diff/apply | 迁移可诊断、可预览、可 diff、可事务 apply |
| V1-R9 | API/operator 默认值冻结修复 | 可变配置默认值从 import-time 改到 request/runtime |
| V1-R10 | Request-scoped graph config | API 请求不能污染全局 settings |
| V1-R11 | Secret redaction | 错误、日志、diff、报告全链路脱敏 |
| V1-R12 | V1 测试 gate | 覆盖兼容、迁移、写盘、安全和默认值冻结 |

### 4.2 V1 不做

| Deferred | 原因 | 后续阶段 |
|---|---|---|
| hot reload | 与 snapshot 不变性冲突，需单独设计 | V2 |
| 完整 rollback CLI | 先做 apply 事务与备份，CLI 放后续 | V2 |
| 全仓库所有 consumer 迁移 | V1 先保旧导入 facade，避免半径失控 | V1.1/V2 |
| 完整 Docker/Helm grep gate | V1 先更新关键文档，自动 gate 放后续 | V1.1 |
| Prompt 全生命周期 | V1 只消除 import 写盘，完整生命周期放后续 | V1.1 |
| UI 写回体验重构 | 依赖 facade 和 source tracking 稳定 | V1.1 |

## 5. 需求定义

### 5.1 功能需求

| ID | 需求 | 优先级 | 验收 |
|---|---|---|---|
| F1 | 建立 `canonical key registry`，每个 key 登记 section、flat field、YAML path、env aliases、类型、默认值、敏感性、可写性 | P0 | `test_registry_complete_for_config_models` |
| F2 | `ConfigSnapshot` 不可变，包含 persisted/effective/source/phase/base dir/registry version | P0 | `test_snapshot_is_immutable` |
| F3 | `ConfigFacade` 是唯一对外读写入口，业务方不直接依赖 manager 内部 dict | P0 | `test_facade_loads_snapshot` |
| F4 | 旧 `llm_settings` / `huge_settings` / `admin_settings` / `index_settings` 导入兼容 | P0 | `test_legacy_settings_import_contract` |
| F5 | 导入 `hugegraph_llm.config` 不创建、不覆盖任何配置文件 | P0 | `test_import_config_has_no_write_side_effects` |
| F6 | `.env` 为 secret-only，非敏感 legacy key 不覆盖 YAML | P0 | `test_dotenv_secret_only_contract` |
| F7 | `update_config()` 仅接受显式 leaf patch，拒绝 full dump/section dump/sensitive path | P0 | `test_patch_only_write_contract` |
| F8 | 迁移支持 doctor/plan/diff/apply 四步 | P0 | `test_migration_plan_diff_apply_contract` |
| F9 | API request model 可变配置默认值为 `None`，endpoint runtime 补默认值 | P0 | `test_api_defaults_resolve_from_runtime_snapshot` |
| F10 | request-scoped graph config 不修改全局 `huge_settings` | P0 | `test_request_graph_config_does_not_mutate_global_settings` |
| F11 | operator 默认参数不在 import-time 读取 mutable config | P1 | `test_operator_defaults_are_runtime_resolved` |
| F12 | 旧 wrapper 发 warning 且不 dump effective config | P1 | `test_deprecated_wrappers_are_safe` |

### 5.2 非功能需求

| ID | 需求 | 优先级 | 验收 |
|---|---|---|---|
| NF1 | fail-fast：无效 YAML、类型转换失败、registry 冲突都清晰报错 | P0 | config contract tests |
| NF2 | 写盘事务：temp + fsync/rename，失败不破坏原文件 | P0 | migration transaction tests |
| NF3 | 只读目录：读取可用，显式写入失败清晰；import 不因自动写 prompt 失败 | P0 | readonly tests |
| NF4 | no CWD fallback：切换启动目录不改变配置解析结果 | P0 | path tests |
| NF5 | secret redaction：所有输出渠道不得出现 secret 明文 | P0 | masking tests |
| NF6 | 兼容可观测：doctor/plan/report 能说明哪些 key 被忽略、保留或迁移 | P1 | migration report tests |

### 5.3 安全需求

| ID | 需求 | 优先级 | 验收 |
|---|---|---|---|
| S1 | process env / `.env` secret 来源永不写入 YAML | P0 | secret not persisted tests |
| S2 | sensitive path 非空 patch 直接拒绝 | P0 | patch reject tests |
| S3 | `ConfigSnapshot` 不暴露可变 secret dict 给调用方修改 | P0 | immutability tests |
| S4 | migration diff/report/log 只显示 `***`、changed/not changed 或来源状态 | P0 | redaction tests |
| S5 | `.env.bak` / YAML backup 权限为 `0600` | P1 | permission tests |

## 6. 架构设计

### 6.1 组件关系

```text
ConfigKeyRegistry
  |- canonical key metadata
  |- env alias map
  |- YAML path map
  |- mutable allowlist
  |- sensitive classifier

ConfigLoader
  |- detect phase
  |- load persisted YAML
  |- load secret-only .env
  |- merge process env
  |- validate/coerce

ConfigSnapshot
  |- persisted_config
  |- effective_config
  |- field_source
  |- diagnostics

ConfigFacade
  |- current_snapshot()
  |- get_section()
  |- update_config()
  |- update_secret_env()
  |- migration doctor/plan/diff/apply

LegacySettingsFacade
  |- llm_settings
  |- huge_settings
  |- admin_settings
  |- index_settings
  |- prompt boundary
```

### 6.2 Canonical Key Registry

Registry 是 V1 的配置事实源。所有 mapping、env alias、sensitive 判断、mutable allowlist 和 migration 输出都从 registry 派生，避免多个模块各自维护口径。

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

Registry 规则：

- `canonical_key` 使用 global dotted leaf path，如 `llm.openai.chat.api_key`。
- 同一 `canonical_key` 只能对应一个 field。
- 同一 YAML leaf path 只能对应一个 canonical key，除非显式声明 alias。
- `env_aliases` 必须是 tuple/list，顺序即优先级。
- sensitive 判断既来自字段名规则，也允许 registry 显式覆盖。
- mutable allowlist 必须由 registry 生成，不能散落在 manager 中。

### 6.3 ConfigSnapshot

Snapshot 是一次加载后的不可变配置状态。

包含：

| 字段 | 含义 |
|---|---|
| `persisted_config` | 可写回 YAML 的非敏感配置 |
| `effective_config` | default + YAML + `.env` secret + process env 合并结果 |
| `field_source` | canonical key -> source |
| `phase` | missing / phase0 / phase1 / phase2 |
| `config_base_dir` | 解析后的配置目录 |
| `diagnostics` | ignored key、unknown key、conflict、warning |
| `registry_version` | registry 版本或 hash |

来源类型：

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
- `effective_config` 不允许 full dump 到 YAML。
- `field_source` key 必须全部是 canonical key。
- secret value 不进入 diagnostics 明文。

### 6.4 ConfigFacade

Facade 是业务方与测试方使用的统一入口。

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
- legacy settings 只通过 facade 读取当前 snapshot。
- ConfigManager 可保留为内部 loader/writer，但不作为业务公开 API。

### 6.5 Legacy Settings Facade

旧代码大量依赖：

```python
from hugegraph_llm.config import llm_settings, huge_settings, admin_settings, index_settings, prompt
```

V1 不强迫这些调用点一次性迁移，而是让旧全局对象成为 facade。

契约：

- 属性读取从当前 snapshot 取值。
- 显式 `update_config(patch)` 走 facade patch writer。
- 直接 `setattr(settings, field, value)` 默认只改对象临时状态，不作为 YAML 写盘入口。
- 旧 `update_env()` / `generate_env()` / `check_env()` 发 `DeprecationWarning`，但不能 dump effective config。
- 如必须支持旧 UI 的 `setattr + update_env()`，应在 wrapper 内只提取 changed mutable non-sensitive fields，并在测试中证明 secret 不落盘。

### 6.6 Secret-only `.env`

优先级：

```text
process os.environ / K8s Secret
  > .env secret-only
  > config.yaml
  > pydantic / registry default
```

决策矩阵：

| 来源 | key 类型 | 行为 |
|---|---|---|
| process env | known sensitive | highest effective override，不持久化 |
| process env | known non-sensitive | runtime override，不持久化 |
| `.env` | known sensitive | effective override，不持久化 |
| `.env` | known non-sensitive | doctor/report warning，不覆盖 YAML |
| `.env` | unknown sensitive-like | report，默认不生效 |
| `.env` | unknown non-sensitive | report / `_migration_unknown`，默认不生效 |
| YAML | non-sensitive | persisted 主来源 |
| YAML | sensitive non-null | doctor warning；save/apply 时拒绝或置空 |

### 6.7 Patch-only 写盘

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

- value 是 mapping / section object。
- path 不在 registry。
- path 不在 mutable allowlist。
- path 是 sensitive key。
- path 是 metadata key。
- patch 形状等于 full dump / section dump / effective dump。
- patch key 数量阈值只能作为防滥用兜底，不能作为识别 full dump 的主逻辑。

### 6.8 Migration Doctor / Plan / Diff / Apply

#### Doctor

只读检测：

- 当前 phase。
- 是否存在 Phase0 `.env`、Phase1 YAML、Phase2 YAML。
- `.env` 中 known sensitive、known non-sensitive、unknown sensitive-like、unknown non-sensitive。
- YAML 中 sensitive non-null。
- registry 缺失、重复 YAML path、重复 env alias 冲突。
- 目标目录是否可写。
- 备份目标是否会覆盖。

#### Plan

输出迁移计划，不写盘：

- 将写入 YAML 的 canonical key。
- 将保留在 `.env` 的 secret key。
- 将忽略或进入 report 的 unknown key。
- 将创建的 backup/report 路径。
- 将发生的权限设置。
- 风险和 warnings。

#### Diff

展示语义差异：

- persisted config before/after。
- effective config before/after。
- source change。
- secret 值只显示 `***` / changed / unchanged。

#### Apply

事务执行：

```text
doctor
  -> plan
  -> validate all values with TypeAdapter/model_validate
  -> build all output in memory
  -> write temp files
  -> chmod secret files/backups 0600
  -> atomic rename
  -> write report
  -> reload snapshot
```

失败规则：

- 校验失败不得创建或覆盖 `config.yaml`。
- 校验失败不得改写 `.env`。
- 写入失败保留原文件。
- report 不含 secret 明文。

### 6.9 API / Operator 默认值

硬契约：

- request model 的可变配置默认值一律为 `None`。
- endpoint 处理请求时从当前 snapshot / PromptConfig 补默认。
- OpenAPI 不展示伪动态默认值。
- operator 构造默认值不得直接绑定 import-time `huge_settings`。
- request-scoped graph config 不修改全局 settings。

示例方向：

```python
class GraphRAGRequest(BaseModel):
    max_graph_items: int | None = None

def graph_rag_api(req: GraphRAGRequest):
    snapshot = config_facade.current_snapshot()
    max_graph_items = req.max_graph_items or snapshot.hugegraph.max_graph_items
```

`rag_api.py` 当前 `set_graph_config(req)` 直接修改全局 `huge_settings`，V1 需改为 request scoped config：

```text
request client_config
  -> create request graph override
  -> pass into flow/operator/client factory
  -> do not mutate global snapshot/settings
```

### 6.10 Prompt 边界

V1 不做 PromptConfig 全生命周期重构，但必须去掉 import 写盘。

规则：

- 导入 config 模块不调用 `prompt.ensure_yaml_file_exists()`。
- `config_prompt.yaml` 的创建只发生在显式命令或 app 启动需要时。
- 只读目录下导入配置不失败，显式 ensure 才失败。
- request model / API 不固化 prompt 当前值为默认值。

## 7. 文件影响面

| 文件 / 区域 | V1 处理 |
|---|---|
| `hugegraph_llm/config/registry.py` | 新增 canonical key registry |
| `hugegraph_llm/config/snapshot.py` | 新增 ConfigSnapshot / diagnostics dataclasses |
| `hugegraph_llm/config/facade.py` | 新增 ConfigFacade |
| `hugegraph_llm/config/manager.py` | 收敛为内部 loader/writer，接入 registry |
| `hugegraph_llm/config/migration.py` | 扩展 doctor/plan/diff/apply |
| `hugegraph_llm/config/models/base_config.py` | 旧 settings facade / patch-only wrapper |
| `hugegraph_llm/config/__init__.py` | 去掉 import 写 prompt，导出 facade 和 legacy settings |
| `hugegraph_llm/config/models/base_prompt_config.py` | ensure 显式化，不在 import 链写文件 |
| `hugegraph_llm/api/rag_api.py` | request-scoped graph config，去全局 mutation |
| `hugegraph_llm/api/models/*` | 可变配置默认值改为 `None` |
| `hugegraph_llm/operators/*` | 移除 import-time mutable config 默认参数 |
| `hugegraph_llm/demo/rag_demo/configs_block.py` | 从 `update_env()` 迁到 patch/facade；role 级联用 source |
| `hugegraph-llm/src/tests/config/` | 新增 contract / migration / facade / no-write / default-freeze tests |
| `hugegraph-llm/config-migration-upgrade-guide.md` | 更新 V1 真实范围 |

## 8. 实现任务清单

- [ ] 1. **研究与基线确认** `[优先级: 高]`

  - [ ] 1.1. 扫描配置入口、全局对象、`update_env()`、`generate_env()`、`check_env()`、`dotenv`、`os.environ`、`config_prompt.yaml`、API request model 默认值、operator 默认参数。`(关联需求: F4, F5, F9, F11)`
  - [ ] 1.2. 输出消费面矩阵：文件、行号、当前行为、风险类型、V1 是否处理、后续阶段。`(依赖于: 1.1)`
  - [ ] 1.3. 梳理当前 ConfigManager/mapping/migration 实现已满足项与缺口，避免重复实现。`(依赖于: 1.1)`
  - [ ] 1.4. 确认 V1 兼容契约：旧导入、旧 wrapper、旧 `.env`、Phase1 YAML、Phase2 YAML、API 请求行为。`(依赖于: 1.2)`

- [ ] 2. **Canonical Key Registry** `[优先级: 高]`

  - [ ] 2.1. 新增 registry 数据结构和构建器，从配置类 `_config_section`、mapping、env map、mutable fields、model fields 生成 key spec。`(关联需求: F1)`
  - [ ] 2.2. 校验 registry：无未映射字段、无重复 YAML leaf、env alias 有序、mutable 不含 sensitive。`(依赖于: 2.1)`
  - [ ] 2.3. 用 registry 替换 manager 内散落的 `global_to_field`、`env_to_global_path`、`mutable_persisted_leaf_paths` 构建逻辑。`(依赖于: 2.2)`
  - [ ] 2.4. 增加 registry 测试，覆盖 LLM/HugeGraph/Admin/Index 全字段。`(依赖于: 2.2)`

- [ ] 3. **ConfigSnapshot 与 ConfigFacade** `[优先级: 高]`

  - [ ] 3.1. 新增不可变 `ConfigSnapshot` 和 diagnostics 类型。`(关联需求: F2)`
  - [ ] 3.2. 新增 `ConfigFacade.current_snapshot()` / `reload()` / `get_section()` / `get_flat_section()`。`(依赖于: 3.1)`
  - [ ] 3.3. 将 `ConfigManager.reload()` 输出转换为 snapshot，避免业务直接读取内部 mutable dict。`(依赖于: 3.2)`
  - [ ] 3.4. 新增 facade 单例获取函数，作为 `config/__init__.py` 对外入口。`(依赖于: 3.2)`
  - [ ] 3.5. 增加 snapshot immutability 与 facade reload 测试。`(依赖于: 3.3)`

- [ ] 4. **Legacy Settings Facade** `[优先级: 高]`

  - [ ] 4.1. 让 `llm_settings`、`huge_settings`、`admin_settings`、`index_settings` 从 facade snapshot 读取值，保持旧属性访问。`(关联需求: F4)`
  - [ ] 4.2. 明确并实现直接 `setattr` 行为：只改临时对象，不自动写盘；写盘必须走 patch。`(依赖于: 4.1)`
  - [ ] 4.3. `BaseConfig.update_config(patch)` 转换 section-local patch 到 facade global patch。`(依赖于: 4.1)`
  - [ ] 4.4. 旧 wrapper 发 warning，但不 dump effective config，不写 secret。`(依赖于: 4.3)`
  - [ ] 4.5. 增加旧导入兼容和 wrapper 安全测试。`(依赖于: 4.4)`

- [ ] 5. **No-write-on-read 与 Prompt 边界** `[优先级: 高]`

  - [ ] 5.1. 修改 `config/__init__.py`，导入时不调用 `prompt.ensure_yaml_file_exists()`。`(关联需求: F5)`
  - [ ] 5.2. 将 prompt YAML 创建动作保留在显式 generate/app 启动入口。`(依赖于: 5.1)`
  - [ ] 5.3. 导入 config 模块时不得创建 `config.yaml`、`.env`、`config_prompt.yaml`、migration report。`(依赖于: 5.1)`
  - [ ] 5.4. 增加 no-write-on-read 测试，覆盖只读目录。`(依赖于: 5.3)`

- [ ] 6. **Secret-only `.env` 与加载优先级** `[优先级: 高]`

  - [ ] 6.1. 用 registry 实现 process env 与 `.env` secret-only override，区分 `process_env_override` 与 `dotenv_secret`。`(关联需求: F6)`
  - [ ] 6.2. `.env` 中 known non-sensitive legacy key 不覆盖 YAML，只进入 diagnostics/report。`(依赖于: 6.1)`
  - [ ] 6.3. 空字符串 env 不覆盖已有 YAML/default。`(依赖于: 6.1)`
  - [ ] 6.4. 类型转换失败 fail-fast，错误信息不包含原 secret 值。`(依赖于: 6.1)`
  - [ ] 6.5. 增加优先级、空值、非敏感 `.env` ignored、secret redaction 测试。`(依赖于: 6.1)`

- [ ] 7. **Patch-only Transaction Writer** `[优先级: 高]`

  - [ ] 7.1. `ConfigFacade.update_config()` 仅接受 global dotted leaf patch。`(关联需求: F7)`
  - [ ] 7.2. patch 校验走 registry allowlist + leaf-shape，拒绝 nested mapping、section dump、full dump、metadata key、sensitive key。`(依赖于: 7.1)`
  - [ ] 7.3. 写盘只序列化 persisted config，secret path 省略或仅允许 `null` placeholder。`(依赖于: 7.2)`
  - [ ] 7.4. 写盘使用 temp + atomic rename，失败不破坏原 YAML。`(依赖于: 7.3)`
  - [ ] 7.5. 增加 patch reject、secret not persisted、atomic failure 测试。`(依赖于: 7.4)`

- [ ] 8. **Migration Doctor / Plan / Diff / Apply** `[优先级: 高]`

  - [ ] 8.1. 实现 `migration_doctor()`，只读诊断 Phase、冲突、unknown key、sensitive non-null、目录权限。`(关联需求: F8)`
  - [ ] 8.2. 实现 `migration_plan()`，输出将写入 YAML 的 key、保留 secret、ignored key、backup/report 路径。`(依赖于: 8.1)`
  - [ ] 8.3. 实现 `migration_diff()`，展示 persisted/effective before/after，secret 全脱敏。`(依赖于: 8.2)`
  - [ ] 8.4. 实现 `migration_apply()`，按 plan 事务写入，并生成 Markdown/JSON 报告。`(依赖于: 8.3)`
  - [ ] 8.5. `.env.bak` / `config.yaml.bak` 文件权限设为 `0600`，不覆盖旧备份。`(依赖于: 8.4)`
  - [ ] 8.6. 增加 Phase0、Phase1、Phase2+.env、Phase1+.env、失败无副作用、备份权限测试。`(依赖于: 8.4)`

- [ ] 9. **API / Operator 默认值冻结修复** `[优先级: 高]`

  - [ ] 9.1. 审计 API request model 中来自 config/prompt 的默认值，改为 `None`。`(关联需求: F9)`
  - [ ] 9.2. endpoint 层从当前 snapshot / prompt runtime 读取默认值。`(依赖于: 9.1)`
  - [ ] 9.3. OpenAPI 不展示伪动态默认值。`(依赖于: 9.1)`
  - [ ] 9.4. 审计 operator 构造默认参数，移除 `huge_settings.xxx` 这类 import-time 默认。`(关联需求: F11)`
  - [ ] 9.5. 增加 API 省略字段后读取 runtime snapshot 的测试。`(依赖于: 9.2)`
  - [ ] 9.6. 增加 operator runtime default 测试。`(依赖于: 9.4)`

- [ ] 10. **Request-scoped Graph Config** `[优先级: 高]`

  - [ ] 10.1. 修改 `rag_api.py` 的 graph config 处理，不再临时修改全局 `huge_settings`。`(关联需求: F10)`
  - [ ] 10.2. 增加 request graph override 对象，并传递给 flow/operator/client factory。`(依赖于: 10.1)`
  - [ ] 10.3. 保持无 request override 时继续使用当前 snapshot。`(依赖于: 10.2)`
  - [ ] 10.4. 增加一次请求配置不污染后续请求和全局 snapshot 的测试。`(依赖于: 10.2)`

- [ ] 11. **最小消费者迁移** `[优先级: 中]`

  - [ ] 11.1. 迁移 `/config/*` API 写入路径到 facade patch 或 secret writer。`(依赖于: 7.1)`
  - [ ] 11.2. 迁移 `configs_block.py` 的 `update_env()` 写盘到 patch-only；role 级联用 field source 判断。`(依赖于: 4.3, 7.1)`
  - [ ] 11.3. 对模型初始化、embedding/reranker/vector index 读取 settings 的路径只做必要适配，避免 V1 全量重构。`(依赖于: 3.2)`
  - [ ] 11.4. 为已迁移消费者补 contract tests。`(依赖于: 11.1, 11.2)`

- [ ] 12. **文档与交付收敛** `[优先级: 中]`

  - [ ] 12.1. 更新 `config-migration-upgrade-guide.md`，明确 V1 是 registry/snapshot/facade/可验证迁移优先。`(关联需求: V1 scope)`
  - [ ] 12.2. 更新 `config.example.yaml` 与 `.env` 示例，区分 secret `.env`、compose `.env`、legacy full `.env`。`(依赖于: 6.1)`
  - [ ] 12.3. 记录 V1.1/V2 deferred 列表，避免后续误把 deferred 当 V1 缺失。`(依赖于: 12.1)`
  - [ ] 12.4. 补充迁移 doctor/plan/diff/apply 使用说明。`(依赖于: 8.4)`

## 9. 测试计划

### 9.1 必须新增测试文件

| 文件 | 覆盖 |
|---|---|
| `src/tests/config/test_registry_contract.py` | registry 完整性、重复 path、env alias 顺序、mutable/sensitive 冲突 |
| `src/tests/config/test_snapshot_facade.py` | snapshot immutability、facade reload、legacy settings 兼容 |
| `src/tests/config/test_no_write_on_read.py` | import 不写文件、只读目录导入 |
| `src/tests/config/test_secret_only_dotenv.py` | `.env` secret-only、process env 优先、非敏感 `.env` ignored |
| `src/tests/config/test_patch_writer.py` | patch-only、reject full dump、secret not persisted、atomic write |
| `src/tests/config/test_migration_workflow.py` | doctor/plan/diff/apply、Phase0/Phase1、失败无副作用 |
| `src/tests/config/test_api_runtime_defaults.py` | API 默认值 runtime resolve、OpenAPI 不固化动态默认 |
| `src/tests/config/test_request_scoped_graph_config.py` | request graph override 不污染全局 |

### 9.2 最低验证命令

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/config/ -v --tb=short
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/api/ -v --tb=short
uv run ruff format --check .
uv run ruff check .
```

如 API tests 当前没有独立目录，可将 runtime default tests 放在 `src/tests/config/` 或 `src/tests/integration/` 中，但测试名称必须明确反映 API/operator 默认值冻结风险。

## 10. 验收标准

### 10.1 功能验收

| ID | 验收项 |
|---|---|
| AC-F1 | registry 能覆盖所有配置模型字段，且生成 canonical key / YAML path / env alias / mutable allowlist |
| AC-F2 | 旧导入 `llm_settings` 等可用，且读取当前 snapshot |
| AC-F3 | 导入 `hugegraph_llm.config` 不创建或覆盖配置文件 |
| AC-F4 | `.env` secret 生效，`.env` 非敏感 legacy key 不覆盖 YAML |
| AC-F5 | patch-only 写盘可写非敏感 leaf，拒绝 secret 和 full dump |
| AC-F6 | migration doctor/plan/diff/apply 可分别执行，apply 失败无副作用 |
| AC-F7 | API 省略字段使用 runtime snapshot，不使用 import-time 旧默认 |
| AC-F8 | request graph config 不污染全局 settings |

### 10.2 安全验收

| ID | 验收项 |
|---|---|
| AC-S1 | YAML、report、log、diff、error 中不出现 secret 明文 |
| AC-S2 | `.env.bak` 和 YAML backup 权限为 `0600` |
| AC-S3 | `update_config()` 不能写入 sensitive path |
| AC-S4 | 迁移失败不改写 `.env`、`config.yaml`、backup、report |

### 10.3 兼容验收

| ID | 验收项 |
|---|---|
| AC-C1 | 旧 `.env` 可通过 plan/apply 迁移，secret 保留 |
| AC-C2 | Phase1 flat YAML 可迁移，sensitive non-null 不进入 YAML |
| AC-C3 | Phase2 YAML + `.env` secret-only 共存可启动 |
| AC-C4 | 旧 wrapper 保留 warning，不泄露 secret |

## 11. 里程碑

```text
M0 基线矩阵
  -> M1 registry + snapshot + facade
  -> M2 no-write-on-read + secret-only loader
  -> M3 patch writer + migration workflow
  -> M4 API/operator 默认值与 request-scoped graph
  -> M5 最小消费者迁移 + 文档 + CI gate
```

| 里程碑 | 出口条件 |
|---|---|
| M0 | 消费面矩阵完成，V1/V1.1/V2 边界确认 |
| M1 | registry/snapshot/facade 测试通过，旧导入兼容 |
| M2 | import 不写盘、secret-only `.env`、no CWD fallback 测试通过 |
| M3 | patch writer 与 migration doctor/plan/diff/apply 测试通过 |
| M4 | API/operator 默认值冻结风险的 V1 高危点已修 |
| M5 | config tests、API/runtime default tests、ruff 通过，文档更新 |

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| legacy facade 行为和真实 Pydantic model 行为不一致 | 旧调用方可能读写异常 | facade 先保持属性访问兼容，写入路径显式收紧 |
| snapshot 不变性与旧 `setattr` 习惯冲突 | UI 旧代码可能依赖临时赋值 | 明确 `setattr` 只影响对象内存，持久化必须 patch |
| API 默认值迁移影响 OpenAPI | 用户看到默认值变化 | OpenAPI 不展示伪动态默认，文档说明 runtime default |
| request-scoped graph config 需要传递更深 | Flow/operator 改动可能扩大 | V1 只改 API 直接路径和关键 client factory |
| migration apply 写盘失败 | 配置损坏风险 | temp + atomic rename + failure tests |
| secret 脱敏遗漏 | 安全风险 | redaction helper + tests 覆盖 error/log/diff/report |

## 13. V1.1 / V2 后续项

| 阶段 | 项目 |
|---|---|
| V1.1 | PromptConfig 完整生命周期，含模板复制、用户可写目录、只读部署策略 |
| V1.1 | Gradio UI 写回体验重构，所有写盘改 patch facade |
| V1.1 | 部署文档 grep gate，README/Docker/Helm 全量收敛 |
| V2 | rollback CLI |
| V2 | hot reload / snapshot refresh strategy |
| V2 | 全仓库消费者彻底去 legacy global settings |

## 14. 推荐执行顺序

```text
1 基线确认
  -> 2 registry
  -> 3 snapshot/facade
  -> 4 legacy settings facade
  -> 5 no-write-on-read
  -> 6 secret-only loader
  -> 7 patch writer
  -> 8 migration doctor/plan/diff/apply
  -> 9 API/operator runtime defaults
  -> 10 request-scoped graph config
  -> 11 minimal consumers
  -> 12 docs and CI
```

关键原则：

- 先建立事实源，再迁消费者。
- 先保持旧导入兼容，再收紧写盘路径。
- 先让迁移可预览，再允许事务 apply。
- 先修 API/operator 默认值冻结的高危点，再做大面积 UI 和部署改造。
