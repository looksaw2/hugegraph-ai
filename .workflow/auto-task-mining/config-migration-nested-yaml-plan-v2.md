# Plan: .env → YAML → OmegaConf Nested Config Migration (V2 Revised)

## 1. Problem & Motivation

### Current state (Phase 0)

Config is stored in `.env` files loaded by `python-dotenv`:

```text
OPENAI_CHAT_API_BASE=https://...
OPENAI_CHAT_API_KEY=...
GRAPH_URL=mygraph:9999
...
```text

**Pain points**:

- 60+ flat `KEY=VALUE` lines, no grouping — hard to tell which config belongs to which component
- `ALL_CAPS` keys everywhere, inconsistent with YAML/JSON conventions
- No type semantics — everything is a string
- Provider × role combinations (4 providers × 4 roles = 16 config groups) all crammed into one flat namespace
- Environment variable override logic is scattered: each field default does `os.environ.get("X", default)` inline
- No way to group-related settings (e.g., all OpenAI chat settings together)
- Changing config requires app restart

### Initial improvement (Phase 1, PR already done)

Replaced `.env` with a flat `config.yaml` using `yaml.safe_load/safe_dump`. This fixes the file format but leaves the structural problems unsolved:

- Section names are Python class names (`AdminConfig`, `LLMConfig`) — leaks implementation detail to users
- Keys remain ALL_CAPS
- LLMConfig still has 60+ flat entries from 4 providers all mixed together

### Goal (Phase 2 — this plan, V2 revised)

A nested, semantic `config.yaml` managed by OmegaConf:

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

**Design principles**:

1. Section names are semantic (`llm`, `hugegraph`), not class names (`LLMConfig`)
2. Keys are lowercase (YAML convention)
3. LLM config nested by provider → role (natural grouping)
4. Merge priority: `os.environ > config.yaml > pydantic defaults`
5. Environment variable mapping centralized in one place per config class
6. **V1 scope constraint: config.yaml changes require process restart to take effect** — hot-reload is deferred to a future phase. OmegaConf is suited for YAML load/merge/save and structured config validation, not for automatic file watching or Spring/Log4j-style runtime refresh. This allows V1 to focus on getting the core concerns right: config splitting, migration compatibility, and env priority.

---

## 2. Architecture Design

### BEFORE (Phase 1)

```text
config.yaml (flat, class-name sections, ALL_CAPS keys)
  → yaml.safe_load / yaml.safe_dump
  → pydantic_settings.BaseSettings
  → Field defaults scattered with os.environ.get()
```text

### AFTER (Phase 2, V2 revised)

```text
config.yaml (nested, semantic sections, lowercase keys)
  → OmegaConf (structured load/merge/save)
  → ConfigManager (singleton: unified entry point for all config operations)
      ├── persisted_config:  from config.yaml only, can be save()'d, no runtime env override
      └── effective_config:  pydantic defaults ← config.yaml ← os.environ (read-only at runtime)
  → pydantic.BaseModel (no env-file loading; OmegaConf takes over)
  → Centralized env-var override via _env_var_map per class
```text

**Key architectural decision — two-layer config split**:

ConfigManager separates "persisted config" from "effective config":

| Layer | Source | Writable | Contains |
|-------|--------|----------|----------|
| `persisted_config` | `config.yaml` only | Yes (`save()`) | Declared config values; NO runtime env overrides |
| `effective_config` | defaults → YAML → `os.environ` | No (read-only) | Final merged values used at runtime |

This prevents secrets injected by container/Kubernetes (`OPENAI_API_KEY`, `QDRANT_API_KEY`, `ADMIN_TOKEN`) from being accidentally written back to `config.yaml`.

Additionally, `.env` is treated as a **one-time migration input only** — it is no longer written to `os.environ`.

**No background daemon thread in V1**: The architecture stays simple — `config.yaml` → OmegaConf load/merge → Pydantic validation → config singleton objects. Manual config file changes require a process restart to take effect.

### Core design problem: flat fields vs nested YAML

pydantic models use flat field names (`openai_chat_api_key`), but users want nested YAML (`openai.chat.api_key`). Solution: each config class declares a `_flat_to_nested_mapping` that bridges the two:

- `_flat_to_nested()`: converts pydantic flat dict → nested YAML dict (for writing config.yaml)
- `_nested_to_flat()`: converts nested YAML dict → pydantic flat dict (for reading config.yaml)

Both functions must satisfy the round-trip property: `nested_to_flat(flat_to_nested(d)) == d`.

---

## 3. Task Breakdown

### Task 1: Research — Full Dependency Scan `[Priority: High]`

**Goal**: Map every line of code that touches `.env`, `dotenv`, `update_env`, `check_env`, or `generate_env` to ensure zero missed call sites.

**What to do**:

- Grep the codebase for `dotenv`, `update_env`, `check_env`, `generate_env`, `set_key`, `dotenv_values`
- Build a hit list: file, line, current behavior, required change
- Verify nothing is hidden behind dynamic imports or eval

(Req: U9 — repo path as sole input)

---

### Task 2: Core Infrastructure — Utilities + ConfigManager `[Priority: High]` (Depends on: Task 1)

**Goal**: Build the two foundations everything else rests on.

**2.1 flat↔nested conversion functions**

Two pure functions that translate between flat pydantic field dicts and nested YAML dicts using a dot-notation mapping. Must satisfy the round-trip property and handle edge cases: fields not in the mapping, empty mapping, deeply nested paths.

**2.2 ConfigManager singleton**

Thread-safe singleton that owns the OmegaConf config tree and all YAML I/O. **Critical design boundary**: separates "persisted config" from "effective config".

| Layer | Source | Writable | Purpose |
|-------|--------|----------|---------|
| `persisted_config` | `config.yaml` only | Yes (`save()`) | Declared values; no runtime env override; safe to write back |
| `effective_config` | pydantic defaults ← `config.yaml` ← `os.environ` | No | Final merged values for runtime reading only |

| Method | Responsibility |
|--------|---------------|
| `__init__` | Load `config.yaml` via OmegaConf (or migrate from `.env` / Phase1 YAML if no nested YAML exists) |
| `get_section_with_env_override()` | Return a section's effective config as flat dict, with `os.environ` values merged on top of YAML values |
| `update_section()` | Sync a pydantic model's current field values into the in-memory `persisted_config` tree (NOT env overrides) |
| `save()` | Persist `persisted_config` tree to `config.yaml` (ensures env secrets are never written to disk) |
| `_migrate_from_env()` | One-time `.env` → `config.yaml` migration for existing installations |
| `_migrate_from_phase1_yaml()` | One-time Phase1 flat YAML → nested YAML migration |

**2.3 Env var override design**

Merge priority example for `openai_chat_api_base`:

```text
pydantic default:     "https://api.openai.com/v1"
config.yaml (YAML):   "https://custom.com/v1"
os.environ override:   OPENAI_BASE_URL="https://env.com/v1"
→ Final result:       "https://env.com/v1"  (os.environ always wins)
```text

Type conversion: env var values (always strings) must be converted to the field's pydantic type (`int`, `float`, `Optional[str]`, etc.) via `TypeAdapter.validate_python()`.

**2.4 .env handling policy**

`.env` is treated as **one-time migration input only**. During migration, values are read from `.env` and written to `config.yaml`. After migration, `.env` is NOT loaded into `os.environ` and NOT used as an ongoing config source. This avoids container/Kubernetes-injected secrets (`OPENAI_API_KEY`, `QDRANT_API_KEY`, `ADMIN_TOKEN`) being accidentally persisted to `config.yaml`.

(Req: U9, U10)

---

### Task 3: BaseConfig Base Class Refactor `[Priority: High]` (Depends on: Task 2)

**Goal**: Rewrite the config base class to work with OmegaConf instead of pydantic-settings.

**3.1 Base class switch**: `BaseSettings → BaseModel`. OmegaConf takes over file loading; pydantic-settings' `env_file` feature is no longer needed.

**3.2 Class variable contract**: Every config subclass must declare:

- `_config_section: ClassVar[str]` — which YAML section it belongs to (`"llm"`, `"hugegraph"`, etc.)
- `_flat_to_nested_mapping: ClassVar[dict]` — how its flat field names map to nested YAML paths
- `_env_var_map: ClassVar[dict]` (optional) — which env var names to check for each field

**3.3 `__init__` flow change**:

Old: `dotenv_values(.env)` → inject to `os.environ` → `BaseSettings.__init__` → sync to `.env`

New: `ConfigManager.get_section_with_env_override()` → merge programmatic overrides → `BaseModel.__init__` → write-back to YAML (persisted_config only)

**3.4 Method migration**:

- `update_env()` → `update_config()`: persist to YAML instead of `.env`
- `generate_env()` → `generate_yaml()`: interactive YAML generation
- `check_env()` → `check_config()`: reload from YAML and diff against object attributes

**3.5 Backward compatibility**: Keep `update_env()`, `generate_env()`, `check_env()` as Deprecated wrappers pointing to the new methods. Existing consumer code (e.g., `configs_block.py`) must not break.

**3.6 Three-format migration path**:

V1 must support migration from all three legacy formats:

| Format | Source | Characteristics |
|--------|--------|-----------------|
| Phase0 | `.env` | `ALL_CAPS` flat keys, loaded by `python-dotenv` |
| Phase1 | `config.yaml` (flat) | Class-name sections (`LLMConfig`, `AdminConfig`), `ALL_CAPS` keys |
| Phase2 (target) | `config.yaml` (nested) | Semantic sections (`llm`, `hugegraph`), lowercase keys |

Migration flow:

```text
detect old format
  → normalize to flat pydantic field dict
  → validate with Pydantic
  → convert to nested YAML structure
  → write config.yaml.bak (backup)
  → atomic replace config.yaml
```text

Do not rely solely on OmegaConf's ability to "read any valid YAML" — old flat YAML's section/key structure is not equivalent to the new nested YAML structure.

(Req: U9, U10, U11)

---

### Task 4: LLM Config Nested Mapping `[Priority: High]` (Depends on: Task 3)

**Goal**: Design and implement the nested structure for the most complex config class.

**Analysis**: LLMConfig has ~55 fields. They naturally organize along two axes:

| Axis | Values |
|------|--------|
| Provider | openai, ollama, litellm |
| Role | chat, extract, text2gql, embedding |

Each provider×role pair covers 3-4 fields: `api_base`, `api_key`, `language_model`, `tokens`.

**Mapping pattern** (openai example):

```text
openai_chat_api_base          → openai.chat.api_base
openai_chat_api_key           → openai.chat.api_key
openai_chat_language_model    → openai.chat.language_model
openai_chat_tokens            → openai.chat.tokens
...same pattern for extract, text2gql, embedding...
...then repeat for ollama, litellm...
```text

**Top-level fields** (not nested): `language`, `chat_llm_type`, `extract_llm_type`, `text2gql_llm_type`, `embedding_type`, `reranker_type`, `keyword_extract_type`, `window_size`, `hybrid_llm_weights`.

**Environment variable mapping**: Several fields share one env var — e.g., `openai_chat_api_key` and `openai_extract_api_key` both read from `OPENAI_API_KEY`. The `_env_var_map` must centralize these relationships.

**Expected impact**: ~44 mapping entries + ~8 env var entries. Remove ~14 `os.environ.get()` calls from field defaults — all become static defaults.

(Req: U9, U10)

---

### Task 5: Remaining Config Classes Mapping `[Priority: Medium]` (Depends on: Task 3)

**Goal**: Apply the same nested mapping pattern to the other three config classes.

**HugeGraphConfig** (`_config_section = "hugegraph"`): 12 fields grouped into 4 sub-sections:

- `graph.*`: server connection (url, name, user, pwd, space)
- `query.*`: query parameters (limit_property, max_graph_path, max_graph_items, edge_limit_pre_label)
- `vector.*`: vector search (dis_threshold, topk_per_keyword)
- `rerank.*`: re-ranking (topk_return_results)

**AdminConfig** (`_config_section = "admin"`): 3 fields under `login.*` (enable, user_token, admin_token). Note: `config_reload_interval` field from the original plan is removed since hot-reload is deferred to a future phase.

**IndexConfig** (`_config_section = "index"`): 7 fields under `qdrant.*` and `milvus.*`. `cur_vector_index` stays at top level. Also fix docstring (`"LLM settings"` → `"Vector index settings"`), remove `os.environ.get()` defaults.

(Req: U9, U10)

---

### Task 6: Wire Everything Together — Init Chain & Consumers `[Priority: Medium]` (Depends on: Task 3, Task 4, Task 5)

**Goal**: Connect all the pieces and update every call site.

| File | Change | Purpose |
|------|--------|---------|
| `config/__init__.py` | Initialize `ConfigManager(sections={...})` before config singletons | Singleton must exist before any config object calls it |
| `config/generate.py` | 4 × `generate_env()` → `generate_yaml()` | API surface consistency |
| `demo/rag_demo/configs_block.py` | 6 × `update_env()` → `update_config()`; remove `dotenv_values` import; replace direct `.env` reads with config object attributes | Primary consumer |
| `pyproject.toml` | Add `omegaconf~=2.3` | New dependency |
| `.gitignore` | Add `config.yaml`, `config.yaml.bak` | Sensitive data |
| `config.md` | Rewrite docs for nested structure + priority; document that config changes require restart | User-facing documentation |

(Req: U11)

---

### Task 7: Tests `[Priority: Medium]` (Depends on: Task 3, Task 4)

**Goal**: Verify correctness of core mechanisms AND real-world behavior.

**7.1 Mechanism tests** (round-trip / singleton / happy path):

| Test | What it validates |
|------|-------------------|
| flat↔nested round-trip | `_nested_to_flat(_flat_to_nested(d, m), m) == d` for a dict with both mapped and unmapped keys |
| Env var priority | `os.environ` value overrides YAML value overrides pydantic default |
| ConfigManager singleton | Two `ConfigManager()` calls return the same instance |
| `.env` → YAML migration | Feeding a known `.env` produces the expected `config.yaml` structure |

**7.2 Real-behavior tests** (regression prevention):

| Test | What it validates |
|------|-------------------|
| os.environ overrides YAML | Env var takes priority over YAML value for the same field |
| os.environ overrides migrated .env | Env var wins even when .env had a different value |
| .env migration does NOT write to os.environ | After migration, `os.environ` is not polluted with .env values |
| env-sourced secret NOT saved to config.yaml | `save()` excludes values that came from `os.environ` |
| field-level env alias priority | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` for `openai_chat_api_key` |
| empty env does not clear YAML non-empty secret | `os.environ["KEY"]=""` does not overwrite a valid YAML value |
| Phase1 flat YAML migrates to nested YAML | Class-name sections + ALL_CAPS keys → semantic nested structure |
| corrupt YAML fails fast at startup | Invalid `config.yaml` raises clear error, does not silently use defaults |
| deprecated wrapper compatibility | `update_env()` / `generate_env()` / `check_env()` still function |
| Gradio apply callbacks write to YAML not .env | UI config changes persist to `config.yaml` |
| config path does not depend on CWD | ConfigManager resolves `config.yaml` path relative to a fixed base, not `os.getcwd()` |

---

## 4. Future Phase: Hot-Reload (NOT in V1 MVP)

Hot-reload is explicitly **excluded from V1 scope**. This section documents the research direction for a future phase.

### Why not in V1

OmegaConf handles YAML load/merge/validation well, but does not provide Spring/Log4j-style automatic runtime refresh. Even with file-watch libraries (`watchfiles`/`watchdog`), detecting file changes is only the first step. The real complexity is safely propagating changes to live runtime objects:

- Already-created LLM / Embedding clients won't auto-rebuild
- HugeGraph / Vector DB connection params are typically fixed at construction time
- Reload requires handling locks, rollback, validation failures, and env override priority
- Some values are captured by clients or at import time and cannot be changed

### Reloadability boundaries (for future reference)

**Can reload later** (simple value changes):

- Log level
- Simple numeric thresholds
- Non-client feature flags

**Require restart** (captured at construction time):

- LLM provider / `api_base` / `api_key`
- Embedding model
- HugeGraph connection params
- Vector DB connection params
- Any field already captured by an existing client or import-time constant

### Future research directions

- Whether `Dynaconf fresh_vars` suits a small set of read-through fields
- Whether `watchfiles`/`watchdog` is suitable as an explicit reload trigger
- Which fields are safe to reload vs. which require restart

---

## 5. Risk Assessment (V2 — tightened)

| Risk | Severity | Mitigation |
|------|----------|------------|
| `__init__` flow change breaks downstream imports | High | Keep old methods as Deprecated aliases; search all call sites thoroughly (Task 1) |
| Missing entry in `_flat_to_nested_mapping` | Medium | Fields not in mapping stay at YAML top level — no data loss, just sub-optimal structure |
| YAML file corrupted or unreadable | High | **Fail fast at startup** with clear error message — do NOT silently fall back to pydantic defaults. Invalid config means the process does not start |
| Future reload: new config.yaml invalid | Medium | Keep last-known-good config in memory; expose error clearly; do NOT swap in broken config |
| Env var type coercion fails | High | **Validation failure** — do NOT silently keep env value as string. Type mismatch means the process does not start |
| Env secrets written back to config.yaml | High | `save()` only writes `persisted_config` (YAML-sourced values); `effective_config` (with env overrides) is read-only |
| Phase 0/1 YAML not auto-detected | Medium | Explicit format detection + normalize → validate → convert flow (Task 3.6); do not rely on OmegaConf to guess the format |
| Config path depends on CWD | Low | Resolve `config.yaml` path relative to a fixed base directory, not `os.getcwd()` |

**Core principle**: Configuration errors should be exposed as early and as loudly as possible. Silent fallback to defaults risks connecting to wrong services or using wrong credentials in production.

---

## 6. Requirements Coverage

| Requirement | Covered By |
|-------------|------------|
| U9 — Accept repo path as sole input | Task 1, Task 2 |
| U10 — Derive conventions from repo's own config | Task 2 (flat↔nested mapping driven by class vars) |
| U11 — Write output to specified path | Task 3, Task 6 |
| U13 — No network beyond `gh` CLI | Entire plan (hot-reload deferred to future phase; no file watcher daemon in V1) |

---

## 7. V1 Scope Summary

| Item | V1 Status |
|------|-----------|
| Nested semantic `config.yaml` (OmegaConf) | Included |
| `.env` → nested YAML migration | Included |
| Phase1 flat YAML → nested YAML migration | Included |
| `os.environ` > `config.yaml` > pydantic defaults priority | Included |
| Env secret isolation (not written to YAML) | Included |
| Deprecated method wrappers (backward compat) | Included |
| Config change requires restart | Included (by design) |
| Automatic hot-reload | **Deferred to Future Phase** |
| Background file watcher daemon | **Deferred to Future Phase** |
