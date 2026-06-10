# Plan: .env → YAML → OmegaConf Nested Config Migration (V3 Hardened)

# 方案：.env → YAML → OmegaConf 嵌套配置迁移（V3 契约强化版）

---

## 1. Problem & Motivation / 问题与动机

### Current state (Phase 0) / 当前状态（Phase 0）

Config is stored in `.env` files loaded by `python-dotenv`:
配置通过 `python-dotenv` 加载的 `.env` 文件存储：

```text
OPENAI_CHAT_API_BASE=https://...
OPENAI_CHAT_API_KEY=...
GRAPH_URL=mygraph:9999
...
```text

**Pain points / 痛点**：

- 60+ flat `KEY=VALUE` lines, no grouping — hard to tell which config belongs to which component
  60+ 个扁平的 `KEY=VALUE` 行，无分组 —— 难以区分哪些配置属于哪个组件
- `ALL_CAPS` keys everywhere, inconsistent with YAML/JSON conventions
  全大写键名遍布各处，与 YAML/JSON 惯例不一致
- No type semantics — everything is a string
  无语义类型 —— 一切都是字符串
- Provider × role combinations (4 providers × 4 roles = 16 config groups) all crammed into one flat namespace
  提供商 × 角色组合（4 提供商 × 4 角色 = 16 个配置组）全部挤在一个扁平命名空间中
- Environment variable override logic is scattered: each field default does `os.environ.get("X", default)` inline
  环境变量覆盖逻辑分散：每个字段默认值都内联调用 `os.environ.get("X", default)`
- No way to group-related settings (e.g., all OpenAI chat settings together)
  无法将相关配置分组（例如，将所有 OpenAI 聊天配置放在一起）
- Changing config requires app restart
  修改配置需要重启应用

### Initial improvement (Phase 1, PR already done) / 初步改进（Phase 1，PR 已完成）

Replaced `.env` with a flat `config.yaml` using `yaml.safe_load/safe_dump`. This fixes the file format but leaves the structural problems unsolved:
使用 `yaml.safe_load/safe_dump` 将 `.env` 替换为扁平的 `config.yaml`。这修复了文件格式，但仍未解决结构化问题：

- Section names are Python class names (`AdminConfig`, `LLMConfig`) — leaks implementation detail to users
  节名是 Python 类名（`AdminConfig`、`LLMConfig`）—— 向用户泄露了实现细节
- Keys remain ALL_CAPS
  键名仍为全大写
- LLMConfig still has 60+ flat entries from 4 providers all mixed together
  LLMConfig 仍然有 60+ 个扁平条目，4 个提供商全部混在一起

### Goal (Phase 2 — this plan, V3 hardened) / 目标（Phase 2 —— 本方案，V3 契约强化版）

A nested, semantic `config.yaml` managed by OmegaConf:
一个由 OmegaConf 管理的嵌套、语义化 `config.yaml`：

```yaml
llm:
  language: CN
  chat_llm_type: openai

  openai:
    chat:
      api_base: https://api.openai.com/v1
      api_key: null
      language_model: gpt-4.1-mini
    extract:
      api_base: https://api.openai.com/v1
      ...
    embedding:
      api_base: https://api.openai.com/v1
      ...

  ollama:
    chat:
      host: 127.0.0.1
      ...

hugegraph:
  graph:
    url: 127.0.0.1:8080
    name: hugegraph
  query:
    max_graph_path: 10
  vector:
    dis_threshold: 0.9

admin:
  login:
    enable: 'False'
    admin_token: xxxx

index:
  cur_vector_index: Faiss
  qdrant:
    host: null
    port: 6333
```text

**Design principles / 设计原则**：

1. Section names are semantic (`llm`, `hugegraph`), not class names (`LLMConfig`)
   节名语义化（`llm`、`hugegraph`），而非类名（`LLMConfig`）
2. Keys are lowercase (YAML convention)
   键名小写（YAML 惯例）
3. LLM config nested by provider → role (natural grouping)
   LLM 配置按 提供商 → 角色 嵌套（自然分组）
4. Merge priority / 合并优先级：`os.environ > config.yaml > pydantic defaults`
5. Environment variable mapping centralized in one place per config class
   环境变量映射集中在每个配置类的一个位置
6. **V1 scope constraint / V1 范围约束：config.yaml changes require process restart to take effect**
   **config.yaml 修改后需重启进程才能生效**
   — hot-reload is deferred to a future phase. OmegaConf is suited for YAML load/merge/save and structured config validation, not for automatic file watching or Spring/Log4j-style runtime refresh. This allows V1 to focus on getting the core concerns right: config splitting, migration compatibility, and env priority.
   — 热加载推迟到未来阶段。OmegaConf 适用于 YAML 加载/合并/保存以及结构化配置验证，而非自动文件监控或 Spring/Log4j 式的运行时刷新。这使得 V1 可以专注于做好核心关注点：配置拆分、迁移兼容性和环境变量优先级。

---

## 2. Architecture Design / 架构设计

### BEFORE (Phase 1) / 之前（Phase 1）

```text
config.yaml (flat, class-name sections, ALL_CAPS keys)
config.yaml（扁平，类名节名，全大写键名）
  → yaml.safe_load / yaml.safe_dump
  → pydantic_settings.BaseSettings
  → Field defaults scattered with os.environ.get()
    Field 默认值中散布 os.environ.get() 调用
```text

### AFTER (Phase 2, V3 hardened) / 之后（Phase 2，V3 契约强化版）

```text
config.yaml (nested, semantic sections, lowercase keys)
config.yaml（嵌套，语义节名，小写键名）
  → OmegaConf (structured load/merge/save)
    OmegaConf（结构化加载/合并/保存）
  → ConfigManager (singleton: unified entry point for all config operations)
    ConfigManager（单例：所有配置操作的统一入口）
      ├── persisted_config:  from config.yaml only, can be save()'d, no runtime env override
                            仅来自 config.yaml，可被 save()，不含运行时环境变量覆盖
      └── effective_config: pydantic defaults ← config.yaml ← os.environ (read-only at runtime)
                            pydantic 默认值 ← config.yaml ← os.environ（运行时只读）
  → pydantic.BaseModel (no env-file loading; OmegaConf takes over)
    pydantic.BaseModel（不再加载 env-file；OmegaConf 接管）
  → Centralized env-var override via _env_var_map per class (ordered resolution)
    通过每个类的 _env_var_map 集中管理环境变量覆盖（有序解析）
```text

**Key architectural decision — two-layer config split / 核心架构决策 —— 两层配置分离**：

ConfigManager separates "persisted config" from "effective config":
ConfigManager 将"持久化配置"与"生效配置"分离：

| Layer / 层 | Source / 来源 | Writable / 可写 | Contains / 包含 |
|-------|--------|----------|----------|
| `persisted_config` | `config.yaml` only / 仅 `config.yaml` | Yes (`save()`) / 是 | Declared config values; NO runtime env overrides / 声明式配置值；不含运行时环境变量覆盖 |
| `effective_config` | defaults → YAML → `os.environ` / 默认值 → YAML → `os.environ` | No (read-only) / 否（只读） | Final merged values used at runtime / 运行时使用的最终合并值 |

This prevents secrets injected by container/Kubernetes (`OPENAI_API_KEY`, `QDRANT_API_KEY`, `ADMIN_TOKEN`) from being accidentally written back to `config.yaml`.
这可以防止容器/Kubernetes 注入的密钥（`OPENAI_API_KEY`、`QDRANT_API_KEY`、`ADMIN_TOKEN`）被意外写回 `config.yaml`。

### Critical source boundary: .env vs os.environ vs K8s Secret / 关键来源边界：.env vs os.environ vs K8s Secret

Three distinct config sources must never be conflated:
三种不同的配置来源绝不能混为一谈：

| Source / 来源 | Role / 角色 | Participates in effective config? / 参与 effective config？ | Can be persisted to YAML? / 可持久化到 YAML？ |
|-------|--------|----------|----------|
| Local `.env` file / 本地 `.env` 文件 | **One-time migration input only** / **仅一次性迁移输入** | No (never loaded into `os.environ`) / 否（绝不加载到 `os.environ`） | Yes — only during migration, values written to `config.yaml` / 是 —— 仅在迁移期间，值写入 `config.yaml` |
| Runtime `os.environ` / 运行时 `os.environ` | **Runtime override** / **运行时覆盖** | Yes (highest priority) / 是（最高优先级） | **NEVER** / **绝不** |
| K8s Secret / Container injection / K8s Secret / 容器注入 | **Runtime override** / **运行时覆盖** | Yes (highest priority) / 是（最高优先级） | **NEVER** / **绝不** |

**Hardened rules / 强化规则**：

1. `.env` is ONLY read when no Phase2 nested `config.yaml` exists — it is a local history input, not a runtime source
   `.env` 仅在没有 Phase2 nested `config.yaml` 时读取 —— 它是本地历史输入，不是运行时来源
2. Runtime `os.environ` / K8s Secret ONLY participate in `effective_config`, NEVER in `persisted_config`
   运行时 `os.environ` / K8s Secret 仅参与 `effective_config`，绝不参与 `persisted_config`
3. If `.env` and `os.environ` both have the same key: runtime takes `os.environ`; migration write-source is only local `.env` or old YAML
   如果 `.env` 和 `os.environ` 同时存在同名 key：运行时以 `os.environ` 为准；迁移写盘值仅来自本地 `.env` 或旧 YAML
4. After migration completes: **rename or backup `.env`** → `.env.bak` to prevent users from mistakenly treating it as an ongoing config source
   迁移完成后：**重命名或备份 `.env`** → `.env.bak`，避免用户误以为它仍是持续配置源

**No background daemon thread in V1 / V1 无后台守护线程**：The architecture stays simple — `config.yaml` → OmegaConf load/merge → Pydantic validation → config singleton objects. Manual config file changes require a process restart to take effect.
架构保持简洁 —— `config.yaml` → OmegaConf 加载/合并 → Pydantic 验证 → 配置单例对象。手动修改配置文件后需重启进程生效。

### Core design problem: flat fields vs nested YAML / 核心设计问题：扁平字段 vs 嵌套 YAML

pydantic models use flat field names (`openai_chat_api_key`), but users want nested YAML (`openai.chat.api_key`). Solution: each config class declares a `_flat_to_nested_mapping` that bridges the two:
pydantic 模型使用扁平字段名（`openai_chat_api_key`），但用户期望嵌套 YAML（`openai.chat.api_key`）。解决方案：每个配置类声明一个 `_flat_to_nested_mapping` 来桥接二者：

- `_flat_to_nested()`: converts pydantic flat dict → nested YAML dict (for writing config.yaml)
  将 pydantic 扁平字典 → 嵌套 YAML 字典（用于写 config.yaml）
- `_nested_to_flat()`: converts nested YAML dict → pydantic flat dict (for reading config.yaml)
  将嵌套 YAML 字典 → pydantic 扁平字典（用于读 config.yaml）

Both functions must satisfy the round-trip property: `nested_to_flat(flat_to_nested(d)) == d`.
两个函数必须满足往返属性：`nested_to_flat(flat_to_nested(d)) == d`。

---

## 3. Task Breakdown / 任务分解

### Task 1: Research — Full Dependency Scan / 任务 1：研究 —— 全量依赖扫描 `[Priority: High / 高]`

**Goal / 目标**：Map every line of code that touches `.env`, `dotenv`, `update_env`, `check_env`, or `generate_env` to ensure zero missed call sites.
映射每一行涉及 `.env`、`dotenv`、`update_env`、`check_env` 或 `generate_env` 的代码，确保零遗漏调用点。

**What to do / 要做什么**：

- Grep the codebase for `dotenv`, `update_env`, `check_env`, `generate_env`, `set_key`, `dotenv_values`
  在代码库中搜索以上关键字
- Build a hit list: file, line, current behavior, required change
  建立命中清单：文件、行号、当前行为、需要的变更
- Verify nothing is hidden behind dynamic imports or eval
  验证没有隐藏在动态导入或 eval 背后的调用

(Req: U9 — repo path as sole input / 仓库路径作为唯一输入)

---

### Task 2: Core Infrastructure — Utilities + ConfigManager / 任务 2：核心基础设施 —— 工具函数 + ConfigManager `[Priority: High / 高]` (Depends on: Task 1)

**Goal / 目标**：Build the two foundations everything else rests on.
构建所有其他部分依赖的两个基础。

**2.1 flat↔nested conversion functions / 扁平↔嵌套 转换函数**

Two pure functions that translate between flat pydantic field dicts and nested YAML dicts using a dot-notation mapping. Must satisfy the round-trip property and handle edge cases: fields not in the mapping, empty mapping, deeply nested paths.
两个纯函数，使用点号分隔的映射关系在 pydantic 扁平字段字典和嵌套 YAML 字典之间转换。必须满足往返属性，并处理边缘情况：不在映射中的字段、空映射、深层嵌套路径。

**Mapping coverage acceptance criteria (V3 hardened) / 映射覆盖率验收标准（V3 强化）**：

Round-trip alone is insufficient — "unmapped fields stay at top-level" avoids data loss but can hide missed migrations, producing a half-nested half-flat YAML. The following coverage contract is mandatory:
仅 round-trip 不够 —— "未映射字段保留在 top-level" 虽能避免数据丢失，但也可能掩盖字段漏迁移。以下覆盖率契约为强制要求：

| Requirement / 要求 | Enforcement / 执行方式 |
|-------------|------------|
| Every config model field must be classified as: `mapped` / `intentional top-level` / `ignored-deprecated` / 每个字段必须归类 | Code review checklist + CI assertion |
| No two flat fields may map to the same nested path (unless explicitly declared as compatible alias) / 同一 nested path 不能被多个 flat field 映射（除非显式声明兼容 alias） | Validation at ConfigManager init |
| Test asserts zero unreviewed unmapped fields per config class / 测试断言每个 config class 无不经审查的 unmapped field | Task 7.1 automated audit |
| Generate migration coverage checklist — especially for `LLMConfig` ~55 fields / 生成迁移覆盖清单 —— 尤其覆盖 LLMConfig 约 55 字段 | Output as build artifact |
| Unmapped field warnings are surfaced as review/CI signals, not silent / unmapped 警告作为可见的 review/CI 信号 | CI output |

**2.2 ConfigManager singleton / ConfigManager 单例**

Thread-safe singleton that owns the OmegaConf config tree and all YAML I/O. **Critical design boundary**: separates "persisted config" from "effective config".
线程安全的单例，掌管 OmegaConf 配置树和所有 YAML I/O。**关键设计边界**：将"持久化配置"与"生效配置"分离。

| Layer / 层 | Source / 来源 | Writable / 可写 | Purpose / 用途 |
|-------|--------|----------|---------|
| `persisted_config` | `config.yaml` only / 仅 `config.yaml` | Yes (`save()`) / 是 | Declared values; no runtime env override; safe to write back / 声明值；无运行时环境变量覆盖；可安全写回 |
| `effective_config` | pydantic defaults ← `config.yaml` ← `os.environ` | No / 否 | Final merged values for runtime reading only / 仅用于运行时读取的最终合并值 |

| Method / 方法 | Responsibility / 职责 |
|--------|---------------|
| `__init__` | Load `config.yaml` via OmegaConf (or migrate from `.env` / Phase1 YAML if no nested YAML exists) / 通过 OmegaConf 加载 `config.yaml`（或在不存嵌套 YAML 时从 `.env` / Phase1 YAML 迁移） |
| `get_section_with_env_override()` | Return a section's effective config as flat dict, with `os.environ` values merged on top of YAML values / 以扁平字典形式返回某个配置节的生效配置，`os.environ` 值合并于 YAML 值之上 |
| `update_section()` | Sync a pydantic model's current field values into the in-memory `persisted_config` tree. **Input MUST come from persisted-source model — must NOT include env override values** / 将 pydantic 模型当前字段值同步到内存中的 `persisted_config` 树。**输入必须来自 persisted-source model —— 不得包含 env override 值** |
| `save()` | Persist `persisted_config` tree to `config.yaml` (ensures env secrets are never written to disk) / 将 `persisted_config` 树持久化到 `config.yaml`（确保环境变量密钥绝不写入磁盘） |
| `_migrate_from_env()` | One-time `.env` → `config.yaml` migration for existing installations; **auto-backs up `.env` → `.env.bak` after success** / 为存量安装提供一次性 `.env` → `config.yaml` 迁移；**成功后自动备份 `.env` → `.env.bak`** |
| `_migrate_from_phase1_yaml()` | One-time Phase1 flat YAML → nested YAML migration / 一次性 Phase1 扁平 YAML → 嵌套 YAML 迁移 |

**2.3 Env var override design / 环境变量覆盖设计**

Merge priority example for `openai_chat_api_base` / 以 `openai_chat_api_base` 为例的合并优先级：

```text
pydantic default / pydantic 默认值：   "https://api.openai.com/v1"
config.yaml (YAML):                   "https://custom.com/v1"
os.environ override / os.environ 覆盖： OPENAI_BASE_URL="https://env.com/v1"
→ Final result / 最终结果：             "https://env.com/v1"  (os.environ always wins / os.environ 始终胜出)
```text

Type conversion: env var values (always strings) must be converted to the field's pydantic type (`int`, `float`, `Optional[str]`, etc.) via `TypeAdapter.validate_python()`. **Type conversion failure MUST fail-fast — do NOT silently keep env value as string or fall back to default.**
类型转换：环境变量值（始终为字符串）必须通过 `TypeAdapter.validate_python()` 转换为字段的 pydantic 类型（`int`、`float`、`Optional[str]` 等）。**类型转换失败必须 fail-fast —— 不静默保留字符串值或回退到默认值。**

**2.4 .env handling policy (V3 hardened) / .env 处理策略（V3 强化）**

`.env` is treated as **one-time migration input only**. The following executable decision table governs all `.env` interactions:
`.env` 仅被视为**一次性迁移输入**。以下可执行决策表约束所有 `.env` 交互：

| Scenario / 场景 | Behavior / 行为 |
|---------|----------|
| Phase2 nested `config.yaml` exists / 已存在 Phase2 nested `config.yaml` | Load directly from YAML; **NEVER read `.env`** / 直接从 YAML 加载；**绝不读取 `.env`** |
| Only Phase1 flat `config.yaml` exists / 仅存在 Phase1 flat `config.yaml` | Migrate to nested; generate `config.yaml.bak` / 迁移为 nested；生成 `config.yaml.bak` |
| Only `.env` exists / 仅存在 `.env` | Migrate to nested `config.yaml`; **auto-backup `.env` → `.env.bak`** / 迁移为 nested `config.yaml`；**自动备份 `.env` → `.env.bak`** |
| Both Phase1 `config.yaml` AND `.env` exist / Phase1 `config.yaml` 和 `.env` 同时存在 | Prioritize `config.yaml`; diff against `.env` and **emit warnings** for divergent keys / 以 `config.yaml` 为主；与 `.env` 差异字段 **打 warning** |
| After migration (any scenario) / 迁移后（任何场景） | `.env` is NEVER loaded into `os.environ`; NOT used as ongoing config source / `.env` 绝不加载到 `os.environ`；不作为持续配置源 |
| Runtime `os.environ` / K8s Secret | ONLY participate in `effective_config`; NEVER persisted to `config.yaml` / 仅参与 `effective_config`；绝不持久化到 `config.yaml` |

This avoids container/Kubernetes-injected secrets (`OPENAI_API_KEY`, `QDRANT_API_KEY`, `ADMIN_TOKEN`) being accidentally persisted to `config.yaml`.
这避免了容器/Kubernetes 注入的密钥（`OPENAI_API_KEY`、`QDRANT_API_KEY`、`ADMIN_TOKEN`）被意外持久化到 `config.yaml`。

(Req: U9, U10)

---

### Task 3: BaseConfig Base Class Refactor / 任务 3：BaseConfig 基类重构 `[Priority: High / 高]` (Depends on: Task 2)

**Goal / 目标**：Rewrite the config base class to work with OmegaConf instead of pydantic-settings.
重写配置基类，使其基于 OmegaConf 而非 pydantic-settings 工作。

**3.1 Base class switch / 基类切换**：`BaseSettings → BaseModel`。OmegaConf takes over file loading; pydantic-settings' `env_file` feature is no longer needed.
OmegaConf 接管文件加载；不再需要 pydantic-settings 的 `env_file` 功能。

**3.2 Class variable contract / 类变量契约**：Every config subclass must declare / 每个配置子类必须声明：

- `_config_section: ClassVar[str]` — which YAML section it belongs to / 所属 YAML 节（`"llm"`, `"hugegraph"` 等）
- `_flat_to_nested_mapping: ClassVar[dict]` — how its flat field names map to nested YAML paths / 扁平字段名到嵌套 YAML 路径的映射
- `_env_var_map: ClassVar[dict]` (optional / 可选) — which env var names to check for each field, **in priority order (list/tuple, not set)** / 每个字段应检查哪些环境变量名，**按优先级排序（list/tuple，非 set）**

**3.3 `__init__` flow change (V3 hardened) / `__init__` 流程变更（V3 强化）**：

Old / 旧：`dotenv_values(.env)` → inject to / 注入 `os.environ` → `BaseSettings.__init__` → sync to / 同步到 `.env`

New / 新：`ConfigManager.get_section_with_env_override()` → merge programmatic overrides / 合并程序化覆盖 → `BaseModel.__init__`

**Critical constraint — No auto-persist on init / 关键约束 —— 初始化不自动持久化**：

| Rule / 规则 | Detail / 详情 |
|------|--------|
| `__init__` ONLY constructs runtime object / `__init__` 只构造运行时对象 | No automatic write-back to YAML / 不自动写回 YAML |
| Only explicit `update_config()` / `generate_yaml()` / migration may persist / 仅显式操作可持久化 | These call `update_section()` + `save()` internally / 这些方法内部调用 `update_section()` + `save()` |
| `update_section()` input MUST be from persisted-source model / `update_section()` 输入必须来自 persisted-source model | Must NOT contain env override values / 不得包含 env override 值 |

This prevents runtime env secrets from being written to disk or user file values being overwritten by defaults during object construction.
这防止运行时 env secret 被写入磁盘，或用户文件值在对象构造时被默认值覆盖。

**3.4 Method migration / 方法迁移**：

- `update_env()` → `update_config()`: persist to YAML instead of `.env` / 持久化到 YAML 而非 `.env`
- `generate_env()` → `generate_yaml()`: interactive YAML generation / 交互式 YAML 生成
- `check_env()` → `check_config()`: reload from YAML and diff against object attributes; **secret fields show `***` or `changed`/`not changed`, never raw values** / 从 YAML 重新加载并与对象属性进行 diff；**敏感字段只显示 `***` 或 `changed`/`not changed`，绝不显示原值**

**3.5 Backward compatibility / 向后兼容**：Keep `update_env()`, `generate_env()`, `check_env()` as Deprecated wrappers pointing to the new methods. Existing consumer code (e.g., `configs_block.py`) must not break.
保留 `update_env()`、`generate_env()`、`check_env()` 作为指向新方法的 Deprecated 包装器。现有消费者代码（如 `configs_block.py`）必须不被破坏。

**3.6 Three-format migration path (V3 hardened) / 三格式迁移路径（V3 强化）**：

V1 must support migration from all three legacy formats:
V1 必须支持从全部三种旧格式迁移：

| Format / 格式 | Source / 来源 | Characteristics / 特征 |
|--------|--------|-----------------|
| Phase0 | `.env` | `ALL_CAPS` flat keys, loaded by `python-dotenv` / 全大写扁平键，由 `python-dotenv` 加载 |
| Phase1 | `config.yaml` (flat / 扁平) | Class-name sections (`LLMConfig`, `AdminConfig`), `ALL_CAPS` keys / 类名节名，全大写键 |
| Phase2 (target / 目标) | `config.yaml` (nested / 嵌套) | Semantic sections (`llm`, `hugegraph`), lowercase keys / 语义节名，小写键 |

**Multi-format conflict resolution decision table (V3 new) / 多格式冲突决策表（V3 新增）**：

| Existing files / 已存在文件 | Behavior / 行为 |
|--------|----------|
| Phase2 nested `config.yaml` exists / 已存在 Phase2 nested `config.yaml` | **Direct load** — do NOT read `.env` or Phase1 YAML / **直接加载** —— 不读取 `.env` 或 Phase1 YAML |
| Only Phase1 flat `config.yaml` / 仅有 Phase1 flat `config.yaml` | Migrate to nested; generate `config.yaml.bak` / 迁移为 nested；生成 `config.yaml.bak` |
| Only `.env` / 仅有 `.env` | Migrate to nested `config.yaml`; **backup `.env` → `.env.bak`** / 迁移为 nested `config.yaml`；**备份 `.env` → `.env.bak`** |
| Phase1 `config.yaml` AND `.env` coexist / Phase1 `config.yaml` 和 `.env` 同时存在 | **Prioritize `config.yaml`**; diff `.env` keys and emit **warnings** for divergent values / **以 `config.yaml` 为主**；对 `.env` 差异字段打 **warning** |
| Unknown keys / unmapped fields / 未知 key / 未映射字段 | Preserve at YAML top-level; emit trackable **warning** with field name and source / 保留在 YAML top-level；输出可追踪 **warning**（含字段名和来源） |

**Migration flow (with side-effect-free validation) / 迁移流程（含无副作用验证）**：

```text
detect old format / 检测旧格式
  → normalize to flat pydantic field dict / 规范化为扁平 pydantic 字段字典
  → validate with model_validate / TypeAdapter (PURE validation — NO __init__, NO singleton init, NO env override, NO write-back)
    用 model_validate / TypeAdapter 做纯校验（无 __init__、无单例初始化、无 env override、无 write-back）
  → IF validation fails: abort with clear error — do NOT generate or overwrite config.yaml
    IF 校验失败：终止并报清晰错误 —— 不生成或覆盖 config.yaml
  → IF validation passes: convert to nested YAML structure
    IF 校验通过：转换为嵌套 YAML 结构
  → write config.yaml.bak (backup / 备份)
  → atomic replace config.yaml / 原子替换 config.yaml
  → IF source was .env: rename .env → .env.bak / 如果来源是 .env：重命名 .env → .env.bak
```text

**Side-effect-free validation contract (V3 new) / 无副作用验证契约（V3 新增）**：

Migration validation MUST NOT reuse normal `BaseConfig.__init__`, which would trigger:
迁移验证不得复用正常 `BaseConfig.__init__`，否则会触发：

- Singleton initialization side effects / 单例初始化副作用
- Env var override injection / 环境变量覆盖注入
- Automatic write-back to YAML / 自动写回 YAML
- Path resolution side effects / 路径解析副作用

Instead, use `model_validate` / `TypeAdapter` for pure validation and type coercion. Validation failure MUST NOT generate or overwrite `config.yaml` — this prevents "migration failed but file partially corrupted" upgrade incidents.
改用 `model_validate` / `TypeAdapter` 做纯校验和类型转换。校验失败不得生成或覆盖 `config.yaml` —— 这能避免"迁移失败但文件已被部分写坏"的升级事故。

Do not rely solely on OmegaConf's ability to "read any valid YAML" — old flat YAML's section/key structure is not equivalent to the new nested YAML structure.
不要仅仅依赖 OmegaConf "读取任何有效 YAML" 的能力 —— 旧扁平 YAML 的节/键结构不等同于新的嵌套 YAML 结构。

(Req: U9, U10, U11)

---

### Task 4: LLM Config Nested Mapping / 任务 4：LLM 配置嵌套映射 `[Priority: High / 高]` (Depends on: Task 3)

**Goal / 目标**：Design and implement the nested structure for the most complex config class.
为最复杂的配置类设计并实现嵌套结构。

**Analysis / 分析**：LLMConfig has ~55 fields. They naturally organize along two axes:
LLMConfig 有约 55 个字段。它们自然地沿两个维度组织：

| Axis / 维度 | Values / 值 |
|------|--------|
| Provider / 提供商 | openai, ollama, litellm |
| Role / 角色 | chat, extract, text2gql, embedding |

Each provider×role pair covers 3-4 fields: `api_base`, `api_key`, `language_model`, `tokens`.
每个 提供商×角色 组合涵盖 3-4 个字段：`api_base`、`api_key`、`language_model`、`tokens`。

**Mapping pattern / 映射模式**（openai example / 以 openai 为例）：

```text
openai_chat_api_base          → openai.chat.api_base
openai_chat_api_key           → openai.chat.api_key
openai_chat_language_model    → openai.chat.language_model
openai_chat_tokens            → openai.chat.tokens
...same pattern for extract, text2gql, embedding...
...对 extract、text2gql、embedding 同理...
...then repeat for ollama, litellm...
...然后对 ollama、litellm 重复此模式...
```text

**Top-level fields** (not nested) / **顶级字段**（不嵌套）：`language`, `chat_llm_type`, `extract_llm_type`, `text2gql_llm_type`, `embedding_type`, `reranker_type`, `keyword_extract_type`, `window_size`, `hybrid_llm_weights`.

**Env var resolution contract — ordered (V3 hardened, P1) / 环境变量解析契约 —— 有序（V3 强化，P1）**：

Several fields share one env var — e.g., `openai_chat_api_key` and `openai_extract_api_key` both read from `OPENAI_API_KEY`. The `_env_var_map` must centralize these relationships as an **ordered resolution contract**, not just a list of relationships.
多个字段共享同一个环境变量 —— 如 `openai_chat_api_key` 和 `openai_extract_api_key` 都从 `OPENAI_API_KEY` 读取。`_env_var_map` 必须将这些关系集中管理为**有序解析契约**，而非仅仅是关系列表。

| Rule / 规则 | Detail / 详情 |
|------|--------|
| Field-level alias beats provider-level/shared alias / 字段级别名优先于提供商级/共享别名 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` for `openai_chat_api_key` |
| Empty string env does NOT override non-empty YAML value / 空字符串 env 不覆盖 YAML 非空值 | `KEY=` does not clear a valid secret from YAML / `KEY=` 不会清除 YAML 中的有效密钥 |
| Each field's env aliases stored as ordered list/tuple / 每个字段的 env 别名按优先级存储在 list/tuple 中 | NOT an unordered set — order determines resolution / 不是无序集合 —— 顺序决定解析结果 |
| Type conversion failure MUST fail-fast / 类型转换失败必须 fail-fast | No silent fallback to string or default / 不允许静默退回字符串或默认值 |

This directly impacts production secret override behavior and is a **P1 contract** for Task 4 and the test table.
这部分直接影响线上 secret 覆盖行为，是 Task 4 和测试表的 **P1 契约**。

**Expected impact / 预期影响**：~44 mapping entries + ~8 env var entries. Remove ~14 `os.environ.get()` calls from field defaults — all become static defaults.
约 44 条映射条目 + 约 8 条环境变量条目。从字段默认值中移除约 14 处 `os.environ.get()` 调用 —— 全部变为静态默认值。

(Req: U9, U10)

---

### Task 5: Remaining Config Classes Mapping / 任务 5：其余配置类映射 `[Priority: Medium / 中]` (Depends on: Task 3)

**Goal / 目标**：Apply the same nested mapping pattern to the other three config classes.
将相同的嵌套映射模式应用于其他三个配置类。

**HugeGraphConfig** (`_config_section = "hugegraph"`): 12 fields grouped into 4 sub-sections / 12 个字段分为 4 个子节：

- `graph.*`: server connection / 服务器连接 (url, name, user, pwd, space)
- `query.*`: query parameters / 查询参数 (limit_property, max_graph_path, max_graph_items, edge_limit_pre_label)
- `vector.*`: vector search / 向量搜索 (dis_threshold, topk_per_keyword)
- `rerank.*`: re-ranking / 重排序 (topk_return_results)

**AdminConfig** (`_config_section = "admin"`): 3 fields under `login.*` (enable, user_token, admin_token). Note: `config_reload_interval` field from the original plan is removed since hot-reload is deferred to a future phase.
3 个字段位于 `login.*` 下（enable、user_token、admin_token）。注意：原计划中的 `config_reload_interval` 字段已移除，因为热加载推迟到未来阶段。

**IndexConfig** (`_config_section = "index"`): 7 fields under `qdrant.*` and `milvus.*`. `cur_vector_index` stays at top level. Also fix docstring (`"LLM settings"` → `"Vector index settings"`), remove `os.environ.get()` defaults.
7 个字段位于 `qdrant.*` 和 `milvus.*` 下。`cur_vector_index` 保持在顶级。同时修复 docstring（`"LLM settings"` → `"Vector index settings"`），移除 `os.environ.get()` 默认值。

(Req: U9, U10)

---

### Task 6: Wire Everything Together — Init Chain & Consumers / 任务 6：整体贯通 —— 初始化链与消费者 `[Priority: Medium / 中]` (Depends on: Task 3, Task 4, Task 5)

**Goal / 目标**：Connect all the pieces and update every call site.
将所有部分串联起来并更新每一个调用点。

| File / 文件 | Change / 变更 | Purpose / 目的 |
|------|--------|---------|
| `config/__init__.py` | Initialize `ConfigManager(sections={...})` before config singletons / 在配置单例之前初始化 `ConfigManager` | Singleton must exist before any config object calls it / 单例必须在任何配置对象调用它之前存在 |
| `config/generate.py` | 4 × `generate_env()` → `generate_yaml()` | API surface consistency / API 表面一致性 |
| `demo/rag_demo/configs_block.py` | 6 × `update_env()` → `update_config()`; remove `dotenv_values` import; replace direct `.env` reads with config object attributes / 移除 `dotenv_values` 导入；用配置对象属性替换直接 `.env` 读取 | Primary consumer / 主要消费者 |
| `pyproject.toml` | Add / 添加 `omegaconf~=2.3` | New dependency / 新依赖 |
| `.gitignore` | Add / 添加 `config.yaml`, `config.yaml.bak`, `.env.bak` | Sensitive data + migration backups / 敏感数据 + 迁移备份 |
| `config.md` | Rewrite docs for nested structure + priority; document that config changes require restart / 重写文档以反映嵌套结构 + 优先级；文档说明配置修改需重启 | User-facing documentation / 面向用户的文档 |
| `README.md` | Remove `.env` references; replace with `config.yaml` instructions / 移除 `.env` 引用，改为 `config.yaml` 说明 | Primary onboarding doc / 首要入门文档 |
| `Dockerfile` / `docker-compose.yml` | Non-sensitive config via mounted `config.yaml` or ConfigMap; sensitive config via env/K8s Secret / 非敏感配置通过挂载 `config.yaml` 或 ConfigMap 注入；敏感配置通过 env/K8s Secret | Container deployment / 容器部署 |
| Helm values / templates | Update ConfigMap references; document env Secret priority over YAML / 更新 ConfigMap 引用；文档说明 env Secret 优先级高于 YAML | Kubernetes deployment / K8s 部署 |
| Example startup scripts / 示例启动脚本 | Update to new config method / 更新为新的配置方式 | Developer onboarding / 开发者入门 |

(Req: U11)

---

### Task 7: Tests / 任务 7：测试 `[Priority: Medium / 中]` (Depends on: Task 3, Task 4)

**Goal / 目标**：Verify correctness of core mechanisms AND real-world behavior.
验证核心机制的正确性及真实场景行为。

**7.1 Mechanism tests / 机制测试** (round-trip / singleton / happy path / coverage audit / 往返/单例/正常路径/覆盖率审计)：

| Test / 测试 | What it validates / 验证内容 |
|------|-------------------|
| flat↔nested round-trip / 扁平↔嵌套往返 | `_nested_to_flat(_flat_to_nested(d, m), m) == d` for a dict with both mapped and unmapped keys / 对同时包含已映射和未映射键的字典成立 |
| Env var priority / 环境变量优先级 | `os.environ` value overrides YAML value overrides pydantic default / `os.environ` 值覆盖 YAML 值覆盖 pydantic 默认值 |
| ConfigManager singleton / ConfigManager 单例 | Two `ConfigManager()` calls return the same instance / 两次 `ConfigManager()` 调用返回同一个实例 |
| `.env` → YAML migration / `.env` → YAML 迁移 | Feeding a known `.env` produces the expected `config.yaml` structure / 输入已知的 `.env` 产生预期的 `config.yaml` 结构 |
| **Unmapped field audit (V3 new)** / **未映射字段审计（V3 新增）** | Assert zero unreviewed unmapped fields per config class; every field classified as mapped / intentional top-level / ignored-deprecated / 断言每个 config class 无不经审查的 unmapped field |

**7.2 Real-behavior tests / 真实行为测试** (regression prevention / 回归防护)：

| Test / 测试 | What it validates / 验证内容 |
|------|-------------------|
| os.environ overrides YAML / os.environ 覆盖 YAML | Env var takes priority over YAML value for the same field / 对同一字段，环境变量优先于 YAML 值 |
| os.environ overrides migrated .env / os.environ 覆盖迁移的 .env | Env var wins even when .env had a different value / 即使 .env 有不同值，环境变量仍然胜出 |
| .env migration does NOT write to os.environ / .env 迁移不写入 os.environ | After migration, `os.environ` is not polluted with .env values / 迁移后 `os.environ` 不被 .env 值污染 |
| env-sourced secret NOT saved to config.yaml / 来自 env 的密钥不保存到 config.yaml | `save()` excludes values that came from `os.environ` / `save()` 排除来自 `os.environ` 的值 |
| field-level env alias priority / 字段级 env 别名优先级 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` for `openai_chat_api_key` |
| empty env does not clear YAML non-empty secret / 空 env 不覆盖 YAML 中的非空密钥 | `os.environ["KEY"]=""` does not overwrite a valid YAML value / 不会覆盖有效的 YAML 值 |
| Phase1 flat YAML migrates to nested YAML / Phase1 扁平 YAML 迁移到嵌套 YAML | Class-name sections + ALL_CAPS keys → semantic nested structure / 类名节 + 全大写键 → 语义嵌套结构 |
| corrupt YAML fails fast at startup / 损坏的 YAML 启动时快速失败 | Invalid `config.yaml` raises clear error, does not silently use defaults / 无效的 `config.yaml` 抛出明确错误，不静默使用默认值 |
| deprecated wrapper compatibility / 废弃包装器兼容性 | `update_env()` / `generate_env()` / `check_env()` still function / 仍然可用 |
| Gradio apply callbacks write to YAML not .env / Gradio 应用回调写入 YAML 而非 .env | UI config changes persist to `config.yaml` / UI 配置修改持久化到 `config.yaml` |
| config path does not depend on CWD / 配置路径不依赖 CWD | ConfigManager resolves `config.yaml` path relative to a fixed base, not `os.getcwd()` / ConfigManager 相对于固定基准解析 `config.yaml` 路径，而非 `os.getcwd()` |
| **Read-only config.yaml or read-only directory (V3 new)** / **只读 config.yaml 或只读目录（V3 新增）** | Startup read succeeds; only explicit save/update fails with clear error / 启动读取应可用；只有显式 save/update 才失败并报清晰错误 |
| **Secret masking in logs/errors/diffs (V3 new)** / **日志/错误/diff 中密钥脱敏（V3 新增）** | No plaintext secret in migration failure, env override, save, or check_config output / 迁移失败、env 覆盖、save、check_config 输出中均不出现明文密钥 |
| **Migration failure does not corrupt config.yaml (V3 new)** / **迁移失败不损坏 config.yaml（V3 新增）** | Validation failure aborts without generating or overwriting config.yaml / 校验失败终止，不生成或覆盖 config.yaml |
| **Multi-format conflict resolution (V3 new)** / **多格式冲突解决（V3 新增）** | Phase1 YAML + .env coexistence: YAML wins, .env diffs get warnings / Phase1 YAML + .env 共存：YAML 优先，.env 差异打 warning |

**7.3 CI Integration (V3 new) / CI 集成（V3 新增）**：

Tests that MUST run in CI (every PR) / 必须在 CI 中运行的测试（每次 PR）：

| CI Gate / CI 门禁 | Command / 命令 |
|---------|---------|
| Migration + env priority + secret not persisted + deprecated wrapper | `pytest hugegraph-llm/tests/... -k "migration or env or secret or deprecated"` |
| Lint / format check | `uv run ruff check` / `uv run ruff format --check` |
| Config path CWD-independence | `pytest hugegraph-llm/tests/... -k "cwd or path"` |
| Read-only filesystem scenario | `pytest hugegraph-llm/tests/... -k "readonly"` |
| Unmapped field audit | `pytest hugegraph-llm/tests/... -k "unmapped or coverage"` |
| Secret masking verification | `pytest hugegraph-llm/tests/... -k "secret or mask"` |

---

### Task 8: Deployment Documentation Update (V3 new) / 任务 8：部署文档更新（V3 新增） `[Priority: Medium / 中]` (Depends on: Task 6)

**Goal / 目标**：Update all deployment entry points to reflect the new config system.
更新所有部署入口以反映新的配置系统。

| Document / 文档 | Update / 更新内容 |
|---------|----------|
| `README.md` | Remove `.env` references; add `config.yaml` setup instructions / 移除 `.env` 引用；添加 `config.yaml` 配置说明 |
| `Dockerfile` | Document volume mount for `config.yaml`; env vars for secrets only / 文档说明 `config.yaml` 卷挂载；敏感信息仅通过 env var |
| `docker-compose.yml` | Add `config.yaml` volume mount; remove `.env` file references / 添加 `config.yaml` 卷挂载；移除 `.env` 文件引用 |
| Helm `values.yaml` | Update ConfigMap to use nested YAML structure; document env Secret priority / 更新 ConfigMap 使用嵌套 YAML 结构；文档说明 env Secret 优先级 |
| Helm templates | Remove `.env` ConfigMap references; add `config.yaml` ConfigMap / 移除 `.env` ConfigMap 引用；添加 `config.yaml` ConfigMap |
| Upgrade guide (new) / 升级指南（新增） | Step-by-step for old `.env` users: backup → migrate → verify → rollback procedure / 旧 `.env` 用户的分步指南：备份 → 迁移 → 验证 → 回滚流程 |
| `config.md` | (Already covered in Task 6 / 已在 Task 6 覆盖) |

**Key messaging for deployment docs / 部署文档的关键信息**：

- Non-sensitive config: use `config.yaml` (mount file or ConfigMap) / 非敏感配置：使用 `config.yaml`（挂载文件或 ConfigMap）
- Sensitive config (secrets): continue using env / K8s Secret, which takes priority over YAML / 敏感配置（密钥）：继续使用 env / K8s Secret，优先级高于 YAML
- Config changes require restart; V1 does not support hot-reload / 配置修改需重启；V1 不支持热加载
- Old `.env` users: follow the upgrade guide for one-time migration / 旧 `.env` 用户：按升级指南完成一次性迁移

---

## 4. Future Phase: Hot-Reload (NOT in V1 MVP) / 未来阶段：热加载（不在 V1 MVP 中）

Hot-reload is explicitly **excluded from V1 scope**. This section documents the research direction for a future phase.
热加载被明确**排除在 V1 范围之外**。本节记录未来阶段的研究方向。

### Why not in V1 / 为什么不在 V1

OmegaConf handles YAML load/merge/validation well, but does not provide Spring/Log4j-style automatic runtime refresh. Even with file-watch libraries (`watchfiles`/`watchdog`), detecting file changes is only the first step. The real complexity is safely propagating changes to live runtime objects:
OmegaConf 能很好地处理 YAML 的加载/合并/验证，但不提供 Spring/Log4j 式的自动运行时刷新。即使使用文件监控库（`watchfiles`/`watchdog`），检测文件变化只是第一步。真正的复杂性在于将变更安全地传播到运行中的运行时对象：

- Already-created LLM / Embedding clients won't auto-rebuild / 已创建的 LLM/Embedding 客户端不会自动重建
- HugeGraph / Vector DB connection params are typically fixed at construction time / HugeGraph/向量数据库连接参数通常在构造时固定
- Reload requires handling locks, rollback, validation failures, and env override priority / 重载需要处理锁、回滚、验证失败和环境变量覆盖优先级
- Some values are captured by clients or at import time and cannot be changed / 部分值被客户端捕获或固定在导入时，无法变更

### Reloadability boundaries (for future reference) / 可重载边界（供未来参考）

**Can reload later** (simple value changes) / **以后可重载**（简单值变更）：

- Log level / 日志级别
- Simple numeric thresholds / 简单数值阈值
- Non-client feature flags / 非客户端功能开关

**Require restart** (captured at construction time) / **需要重启**（构造时捕获）：

- LLM provider / `api_base` / `api_key` / LLM 提供商/API 地址/API 密钥
- Embedding model / 嵌入模型
- HugeGraph connection params / HugeGraph 连接参数
- Vector DB connection params / 向量数据库连接参数
- Any field already captured by an existing client or import-time constant / 任何已被现有客户端或导入时常量捕获的字段

### Future research directions / 未来研究方向

- Whether `Dynaconf fresh_vars` suits a small set of read-through fields / `Dynaconf fresh_vars` 是否适用于少量透读字段
- Whether `watchfiles`/`watchdog` is suitable as an explicit reload trigger / `watchfiles`/`watchdog` 是否适合作为显式重载触发器
- Which fields are safe to reload vs. which require restart / 哪些字段可安全重载 vs 哪些需要重启

---

## 5. Risk Assessment (V3 — tightened + sensitive info protection) / 风险评估（V3 —— 收紧 + 敏感信息保护）

| Risk / 风险 | Severity / 严重程度 | Mitigation / 缓解措施 |
|------|----------|------------|
| `__init__` flow change breaks downstream imports / `__init__` 流程变更破坏下游导入 | High / 高 | Keep old methods as Deprecated aliases; search all call sites thoroughly (Task 1) / 保留旧方法作为 Deprecated 别名；彻底搜索所有调用点（任务 1） |
| Missing entry in `_flat_to_nested_mapping` / `_flat_to_nested_mapping` 中缺少条目 | Medium / 中 | **V3: Mandatory field classification audit** (mapped / intentional top-level / ignored-deprecated); CI assertion for zero unreviewed unmapped fields; generate coverage checklist for ~55 LLMConfig fields / **V3：强制字段分类审计**（mapped / intentional top-level / ignored-deprecated）；CI 断言零未审查 unmapped field；为 LLMConfig 约 55 字段生成覆盖清单 |
| YAML file corrupted or unreadable / YAML 文件损坏或不可读 | High / 高 | **Fail fast at startup** with clear error message — do NOT silently fall back to pydantic defaults. Invalid config means the process does not start / **启动时快速失败**，附带明确错误信息 —— 不静默回退到 pydantic 默认值。无效配置意味着进程不启动 |
| Future reload: new config.yaml invalid / 未来重载：新 config.yaml 无效 | Medium / 中 | Keep last-known-good config in memory; expose error clearly; do NOT swap in broken config / 在内存中保留最后已知正常配置；清晰暴露错误；不换入损坏的配置 |
| Env var type coercion fails / 环境变量类型强制转换失败 | High / 高 | **Validation failure** — do NOT silently keep env value as string. Type mismatch means the process does not start / **验证失败** —— 不静默地将环境变量值保留为字符串。类型不匹配意味着进程不启动 |
| Env secrets written back to config.yaml / 环境变量密钥写回 config.yaml | High / 高 | `save()` only writes `persisted_config` (YAML-sourced values); `effective_config` (with env overrides) is read-only. **V3: `__init__` MUST NOT auto-persist** — only explicit `update_config()` / `generate_yaml()` / migration may write / `save()` 仅写 `persisted_config`（YAML 来源值）；`effective_config`（含环境变量覆盖）为只读。**V3：`__init__` 不得自动持久化** —— 仅显式操作可写入 |
| **Sensitive info leaked in logs/errors/diffs (V3 new)** / **敏感信息在日志/错误/diff 中泄露（V3 新增）** | High / 高 | Fields with `api_key`/`token`/`password`/`pwd`/`secret` in name are uniformly masked; error messages show field path + source but NOT raw value; `check_config()` / diff output shows `***` or `changed`/`not changed`; test coverage for: migration failure, env override, save, check_config logs contain no plaintext secrets / 字段名含 `api_key`/`token`/`password`/`pwd`/`secret` 的统一脱敏；错误信息显示字段路径和来源但不显示原值；`check_config()` / diff 输出仅显示 `***` 或 `changed`/`not changed`；测试覆盖迁移失败、env 覆盖、save、check_config 日志中不出现明文密钥 |
| **Migration partially writes corrupt config.yaml (V3 new)** / **迁移部分写入损坏的 config.yaml（V3 新增）** | High / 高 | Side-effect-free validation via `model_validate`/`TypeAdapter` (no `__init__`); validation failure aborts without touching `config.yaml`; atomic write (write temp + rename) / 无副作用校验通过 `model_validate`/`TypeAdapter`（不经过 `__init__`）；校验失败终止，不触及 `config.yaml`；原子写入（写临时文件 + 重命名） |
| Phase 0/1 YAML not auto-detected / Phase 0/1 YAML 未自动检测 | Medium / 中 | Explicit format detection + **V3 multi-format conflict decision table** (Task 3.6); do not rely on OmegaConf to guess the format / 显式格式检测 + **V3 多格式冲突决策表**（Task 3.6）；不依赖 OmegaConf 猜测格式 |
| `.env` mistakenly treated as ongoing config source / `.env` 被误认为持续配置源 | Medium / 中 | **V3: Auto-backup `.env` → `.env.bak` after migration**; `.env` never loaded into `os.environ`; clear runtime boundary between `.env` (migration-only) and `os.environ` (runtime-only) / **V3：迁移后自动备份 `.env` → `.env.bak`**；`.env` 绝不加载到 `os.environ`；`.env`（仅迁移）与 `os.environ`（仅运行时）之间的清晰边界 |
| Config path depends on CWD / 配置路径依赖 CWD | Low / 低 | Resolve `config.yaml` path relative to a fixed base directory, not `os.getcwd()` / 相对于固定基准目录解析 `config.yaml` 路径，而非 `os.getcwd()` |
| Env alias resolution non-deterministic / 环境变量别名解析不确定 | Medium / 中 | **V3: Ordered resolution contract** — field-level > provider-level; stored as list/tuple not set; empty string does not clear YAML value; fail-fast on type mismatch / **V3：有序解析契约** —— 字段级 > 提供商级；存储为 list/tuple 非 set；空字符串不清除 YAML 值；类型不匹配 fail-fast |

**Core principle / 核心原则**：Configuration errors should be exposed as early and as loudly as possible. Silent fallback to defaults risks connecting to wrong services or using wrong credentials in production. Secrets must never appear in plaintext in any output channel (files, logs, errors, diffs).
配置错误应尽可能早、尽可能大声地暴露。静默回退到默认值可能导致在生产环境中连接到错误的服务或使用错误的凭据。密钥绝不在任何输出渠道（文件、日志、错误、diff）中以明文出现。

---

## 6. Requirements Coverage / 需求覆盖

| Requirement / 需求 | Covered By / 覆盖方式 |
|-------------|------------|
| U9 — Accept repo path as sole input / 接受仓库路径作为唯一输入 | Task 1, Task 2 |
| U10 — Derive conventions from repo's own config / 从仓库自身配置推导约定 | Task 2 (flat↔nested mapping driven by class vars / 扁平↔嵌套映射由类变量驱动) |
| U11 — Write output to specified path / 将输出写入指定路径 | Task 3, Task 6, Task 8 |
| U13 — No network beyond `gh` CLI / 不超过 `gh` CLI 的网络范围 | Entire plan / 整个方案 (hot-reload deferred to future phase; no file watcher daemon in V1 / 热加载推迟到未来阶段；V1 无文件监控守护线程) |

---

## 7. V1 Scope Summary / V1 范围总结

| Item / 项目 | V1 Status / V1 状态 |
|------|-----------|
| Nested semantic `config.yaml` (OmegaConf) / 嵌套语义化 `config.yaml`（OmegaConf） | Included / 包含 |
| `.env` → nested YAML migration / `.env` → 嵌套 YAML 迁移 | Included / 包含 |
| Phase1 flat YAML → nested YAML migration / Phase1 扁平 YAML → 嵌套 YAML 迁移 | Included / 包含 |
| `os.environ` > `config.yaml` > pydantic defaults priority / `os.environ` > `config.yaml` > pydantic 默认值 优先级 | Included / 包含 |
| Env secret isolation (not written to YAML) / 环境变量密钥隔离（不写入 YAML） | Included / 包含 |
| Deprecated method wrappers (backward compat) / 废弃方法包装器（向后兼容） | Included / 包含 |
| Config change requires restart / 配置修改需重启 | Included / 包含 (by design / 设计如此) |
| **Mapping coverage audit + field classification (V3 new)** / **映射覆盖率审计 + 字段分类（V3 新增）** | Included / 包含 |
| **.env vs os.environ vs K8s Secret boundary (V3 new)** / **.env vs os.environ vs K8s Secret 边界（V3 新增）** | Included / 包含 |
| **No auto-persist on `__init__` (V3 new)** / **`__init__` 不自动持久化（V3 新增）** | Included / 包含 |
| **Side-effect-free migration validation (V3 new)** / **无副作用迁移验证（V3 新增）** | Included / 包含 |
| **Multi-format conflict decision table (V3 new)** / **多格式冲突决策表（V3 新增）** | Included / 包含 |
| **Ordered env var resolution contract (V3 new)** / **有序环境变量解析契约（V3 新增）** | Included / 包含 |
| **Full sensitive info masking (V3 new)** / **完整敏感信息脱敏（V3 新增）** | Included / 包含 |
| **Deployment doc update (README/Docker/Helm) (V3 new)** / **部署文档更新（README/Docker/Helm）（V3 新增）** | Included / 包含 |
| **CI gates + read-only scenario tests (V3 new)** / **CI 门禁 + 只读场景测试（V3 新增）** | Included / 包含 |
| Automatic hot-reload / 自动热加载 | **Deferred to Future Phase / 推迟到未来阶段** |
| Background file watcher daemon / 后台文件监控守护线程 | **Deferred to Future Phase / 推迟到未来阶段** |

### Hardened Contracts (V3 additions) / 强化契约（V3 新增）

| Priority / 优先级 | Contract / 契约 | Enforced In / 执行位置 |
|------|----------|------------|
| ‼️ P0 | `__init__` MUST NOT auto-persist env override values to YAML / `__init__` 不得将 env 覆盖值自动写回 YAML | Task 3.3, §5 Risk |
| ‼️ P0 | `.env` (migration-only) vs runtime `os.environ` vs K8s Secret MUST have hard boundaries / `.env`（仅迁移）、运行时 `os.environ`、K8s Secret 必须有硬边界 | Task 2.4, §2 Architecture |
| ‼️ P0 | Env alias resolution MUST be ordered: field-level > provider-level; empty string does not clear YAML / 环境变量别名解析必须有序：字段级 > 提供商级；空字符串不清除 YAML | Task 4, Task 7.2 |
| ⚠️ P1 | Three-format migration MUST have conflict decision table + side-effect-free validation / 三格式迁移必须有冲突决策表 + 无副作用验证 | Task 3.6 |
| ⚠️ P1 | Mapping coverage MUST be audited: every field classified; CI asserts zero unreviewed unmapped / 映射覆盖率必须审计：每个字段归类；CI 断言零未审查 unmapped | Task 2.1, Task 7.1, Task 7.3 |
| ⚠️ P1 | Sensitive fields MUST be masked in all output: logs, errors, diffs, check_config / 敏感字段必须在所有输出中脱敏：日志、错误、diff、check_config | §5 Risk, Task 7.2 |
| ⚠️ P1 | Deployment docs (README, Docker, Compose, Helm) MUST reflect new config system / 部署文档必须反映新配置系统 | Task 8 |
| ⚠️ P1 | CI gates MUST include migration, env priority, secret masking, readonly scenario, unmapped audit / CI 门禁必须包含迁移、env 优先级、脱敏、只读场景、unmapped 审计 | Task 7.3 |
