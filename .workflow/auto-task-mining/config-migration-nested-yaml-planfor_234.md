# Plan: .env → YAML → OmegaConf Nested Config Migration

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
- Changing config requires app restart — no hot-reload

### Initial improvement (Phase 1 ，PR already done)

Replaced `.env` with a flat `config.yaml` using `yaml.safe_load/safe_dump`. This fixes the file format but leaves the structural problems unsolved:

- Section names are Python class names (`AdminConfig`, `LLMConfig`) — leaks implementation detail to users
- Keys remain ALL_CAPS
- LLMConfig still has 60+ flat entries from 4 providers all mixed together

### Goal (Phase 2 — this plan)

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
  config_reload_interval: 5

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
6. Hot-reload: detect file changes and reload without restart

---

## 2. Architecture Design

### BEFORE (Phase 1)

```text
config.yaml (flat, class-name sections, ALL_CAPS keys)
  → yaml.safe_load / yaml.safe_dump
  → pydantic_settings.BaseSettings
  → Field defaults scattered with os.environ.get()
```text

### AFTER (Phase 2)

```text
config.yaml (nested, semantic sections, lowercase keys)
  → OmegaConf (structured load/merge/save)
  → ConfigManager (singleton: unified entry point for all config operations)
  → pydantic.BaseModel (no env-file loading; OmegaConf takes over)
  → Centralized env-var override via _env_var_map per class
  → Background daemon thread: mtime polling → atomic reload
```text

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

Thread-safe singleton that owns the OmegaConf config tree and all YAML I/O:

| Method | Responsibility |
|--------|---------------|
| `__init__` | Load `config.yaml` via OmegaConf (or migrate from `.env` if no YAML exists); start file watcher |
| `get_section_with_env_override()` | Return a section's config as flat dict, with `os.environ` values merged on top of YAML values |
| `update_section()` | Sync a pydantic model's current field values into the in-memory OmegaConf tree |
| `save()` | Persist the full tree to `config.yaml` |
| `_migrate_from_env()` | One-time `.env` → `config.yaml` migration for existing installations |

**2.3 Env var override design**

Merge priority example for `openai_chat_api_base`:

```text
pydantic default:     "https://api.openai.com/v1"
config.yaml (YAML):   "https://custom.com/v1"
os.environ override:   OPENAI_BASE_URL="https://env.com/v1"
→ Final result:       "https://env.com/v1"  (os.environ always wins)
```text

Type conversion: env var values (always strings) must be converted to the field's pydantic type (`int`, `float`, `Optional[str]`, etc.) via `TypeAdapter.validate_python()`.

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

New: `ConfigManager.get_section_with_env_override()` → merge programmatic overrides → `BaseModel.__init__` → write-back to YAML → register for hot-reload

**3.4 Method migration**:

- `update_env()` → `update_config()`: persist to YAML instead of `.env`
- `generate_env()` → `generate_yaml()`: interactive YAML generation
- `check_env()` → `check_config()`: reload from YAML and diff against object attributes

**3.5 Backward compatibility**: Keep `update_env()`, `generate_env()`, `check_env()` as Deprecated wrappers pointing to the new methods. Existing consumer code (e.g., `configs_block.py`) must not break.

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

**AdminConfig** (`_config_section = "admin"`): 3 fields under `login.*` (enable, user_token, admin_token). New field: `config_reload_interval` (int, default 5s, ≤0 disables hot-reload).

**IndexConfig** (`_config_section = "index"`): 7 fields under `qdrant.*` and `milvus.*`. `cur_vector_index` stays at top level. Also fix docstring (`"LLM settings"` → `"Vector index settings"`), remove `os.environ.get()` defaults.

(Req: U9, U10)

---

### Task 6: Hot-Reload `[Priority: Low]` (Depends on: Task 2)

**Goal**: Automatically detect and apply config.yaml changes without restart.

**File watcher**: Daemon thread that polls `config.yaml` mtime every N seconds (N = `admin.config_reload_interval`, default 5). Disabled when N ≤ 0.

**Atomic reload** (under lock):

1. Load new YAML → validate all sections by constructing pydantic model instances (failure at this step means the old config is preserved)
2. Atomically swap the in-memory `_cfg` tree
3. Push new values to all registered live config objects via `check_config()`

**Registration**: Each config singleton auto-registers itself at the end of `__init__`. ConfigManager maintains the registration list.

(Req: U13 — no network required, file polling is purely local)

---

### Task 7: Wire Everything Together — Init Chain & Consumers `[Priority: Medium]` (Depends on: Task 3, Task 4, Task 5)

**Goal**: Connect all the pieces and update every call site.

| File | Change | Purpose |
|------|--------|---------|
| `config/__init__.py` | Initialize `ConfigManager(sections={...})` before config singletons | Singleton must exist before any config object calls it |
| `config/generate.py` | 4 × `generate_env()` → `generate_yaml()` | API surface consistency |
| `demo/rag_demo/configs_block.py` | 6 × `update_env()` → `update_config()`; remove `dotenv_values` import; replace direct `.env` reads with config object attributes | Primary consumer |
| `pyproject.toml` | Add `omegaconf~=2.3` | New dependency |
| `.gitignore` | Add `config.yaml`, `config.yaml.bak` | Sensitive data |
| `config.md` | Rewrite docs for nested structure + priority + hot-reload | User-facing documentation |

(Req: U11)

---

### Task 8: Tests `[Priority: Medium]` (Depends on: Task 3, Task 4)

**Goal**: Verify correctness of the core mechanisms.

| Test | What it validates |
|------|-------------------|
| flat↔nested round-trip | `_nested_to_flat(_flat_to_nested(d, m), m) == d` for a dict with both mapped and unmapped keys |
| Env var priority | `os.environ` value overrides YAML value overrides pydantic default |
| ConfigManager singleton | Two `ConfigManager()` calls return the same instance |
| `.env` → YAML migration | Feeding a known `.env` produces the expected `config.yaml` structure |

---

## 4. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `__init__` flow change breaks downstream imports | High | Keep old methods as Deprecated aliases; search all call sites thoroughly (Task 1) |
| Missing entry in `_flat_to_nested_mapping` | Medium | Fields not in mapping stay at YAML top level — no data loss, just sub-optimal structure |
| YAML file corrupted or unreadable | High | OmegaConf load failure → fall back to empty config → pydantic defaults kick in; log error |
| Env var type coercion fails | Medium | `TypeAdapter.validate_python()` exception → keep env value as string as fallback |
| Hot-reload produces partial state | Low | Reload under lock; validate all sections before swap; keep old `_cfg` on any failure |
| Phase 1 YAML not auto-detected | Medium | OmegaConf can load any valid YAML; ALL_CAPS key structure degrades gracefully |

---

## 5. Requirements Coverage

| Requirement | Covered By |
|-------------|------------|
| U9 — Accept repo path as sole input | Task 1, Task 2 |
| U10 — Derive conventions from repo's own config | Task 2 (flat↔nested mapping driven by class vars) |
| U11 — Write output to specified path | Task 3, Task 7 |
| U13 — No network beyond `gh` CLI | Task 6 (hot-reload is local file polling, no external API calls) |
