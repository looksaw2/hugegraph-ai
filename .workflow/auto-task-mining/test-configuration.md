# Test Configuration / 测试配置

**Date / 日期**: 2026-06-01
**Branch / 分支**: `config-migration-v2-revised-plan`
**Test framework / 测试框架**: pytest 8.0.2 + unittest

---

## 1. Environment / 环境

### 1.1 Required / 必需

| Dependency / 依赖 | Version / 版本 | Note / 说明 |
|------|--------|------|
| Python | 3.10–3.11 | `requires-python = ">=3.10,<3.12"` |
| pytest | 8.0.2 | Test runner / 测试运行器 |
| pytest-cov | 5.0.0 | Coverage (optional / 可选) |
| NLTK | (auto-download) | `stopwords` corpus downloaded by conftest.py |

### 1.2 Optional (external services) / 可选（外部服务）

| Service / 服务 | Skipped tests / 跳过的测试 | Purpose / 用途 |
|---------|-------|------|
| Ollama | 5 | LLM embedding + chat generation tests |
| HugeGraph Server | 4 | Graph construction + schema validation tests |
| Milvus / Qdrant | 3 | Vector database integration tests |
| Faiss | 1 | Local vector index test |

### 1.3 Environment Variables / 环境变量

| Variable / 变量 | Default / 默认值 | Effect / 作用 |
|---------|---------|--------|
| `SKIP_EXTERNAL_SERVICES` | `"true"` (set in `conftest.py`) | Skips all tests requiring Ollama, HugeGraph, Milvus, Qdrant / 跳过所有需要外部服务的测试 |
| `HUGEGRAPH_AI_CONFIG_DIR` | (derived from `__file__`) | Override config file directory / 覆盖配置文件目录 |

---

## 2. Test Infrastructure / 测试基础设施

### 2.1 Directory Structure / 目录结构

```text
src/tests/
├── conftest.py              # Global setup: NLTK, SKIP_EXTERNAL_SERVICES, sys.path
├── test_utils.py            # Shared helpers: skip checks, mock factories, decorators
├── __init__.py
├── utils/
│   ├── __init__.py
│   └── mock.py              # MockEmbedding, VectorIndex (in-memory test doubles)
├── api/                     # 1 test  — Gradio API callback logic
│   └── test_rag_api.py
├── config/                  # 27 tests — V2 config migration + prompt config
│   ├── test_config.py       #   21 tests: flat↔nested, env priority, migration, fail-fast, security
│   └── test_prompt_config.py#   6 tests: prompt example contract validation
├── data/                    # Test fixtures (documents, knowledge graph samples, prompts)
│   ├── documents/
│   ├── kg/
│   └── prompts/
├── document/                # ~10 tests — document loading, splitting, text extraction
│   ├── test_document.py
│   ├── test_document_splitter.py
│   └── test_text_loader.py
├── indices/                 # 1 test (1 skipped) — Faiss vector index
│   ├── __init__.py
│   └── test_faiss_vector_index.py
├── integration/             # ~8 tests (7 skipped) — end-to-end KG + RAG pipelines
│   ├── test_graph_rag_pipeline.py
│   ├── test_kg_construction.py
│   └── test_rag_pipeline.py
├── middleware/               # ~6 tests — LLM middleware chain
│   └── test_middleware.py
├── models/                  # ~30 tests (6 skipped) — LLM clients, embeddings, rerankers
│   ├── embeddings/
│   │   └── test_ollama_embedding.py
│   ├── llms/
│   │   └── test_ollama_client.py
│   └── rerankers/
│       └── test_cohere_reranker.py
├── operators/               # ~200 tests — core pipeline operators
│   ├── __init__.py
│   ├── common_op/
│   ├── document_op/
│   ├── hugegraph_op/
│   ├── index_op/
│   └── llm_op/
└── utils/                   # ~12 tests — utility functions
    └── ...
```text

### 2.2 conftest.py — Global Setup / 全局设置

**File / 文件**: `src/tests/conftest.py`
**Runs before / 运行时机**: every test session / 每次测试会话

```python
# 1. Path setup — ensure src/ is importable
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

# 2. NLTK stopwords — downloaded once before tests
nltk.download("stopwords", quiet=True)

# 3. External service gate — skips 13 tests by default
os.environ["SKIP_EXTERNAL_SERVICES"] = "true"
```text

**Why `SKIP_EXTERNAL_SERVICES=true` by default / 为什么默认跳过外部服务**:

| Reason / 原因 | Detail / 细节 |
|---------|--------|
| CI compatibility / CI 兼容 | CI runners have no Ollama, HugeGraph, or Milvus installed |
| Fast feedback / 快速反馈 | Unit tests complete in <1s vs minutes with external calls |
| No network flakiness / 无网络抖动 | Tests are deterministic without external dependencies |
| Opt-in for integration / 集成测试按需开启 | Developers with local services run `SKIP_EXTERNAL_SERVICES=false` explicitly |

### 2.3 Skip Mechanism / 跳过机制

**Central check / 中心检查** (`test_utils.py:27-28`):

```python
def should_skip_external():
    return os.environ.get("SKIP_EXTERNAL_SERVICES") == "true"
```text

**Per-test decorator pattern / 逐测试装饰器模式** (`test_ollama_client.py:28`):

```python
@unittest.skipIf(
    os.getenv("SKIP_EXTERNAL_SERVICES", "false").lower() == "true",
    "Skipping external service tests"
)
def test_generate(self):
    ollama_client = OllamaClient(model="llama3:8b-instruct-fp16")
    ...
```text

**Two patterns coexist** — `test_utils.should_skip_external()` (imported by newer tests) and inline `os.getenv("SKIP_EXTERNAL_SERVICES")` (older tests). Both gate on the same env var. This is pre-existing inconsistency, not introduced by V2.

### 2.4 Mock Infrastructure / Mock 设施

**File / 文件**: `src/tests/utils/mock.py`

| Mock Class / Mock 类 | Purpose / 用途 |
|------------|------|
| `MockEmbedding` | In-memory embedding with deterministic per-text vectors. Used by operator tests to avoid calling real OpenAI/Ollama APIs / 确定性向量的内存嵌入，避免调用真实 API |
| `VectorIndex` | In-memory vector index simulating Faiss/Milvus. Stores documents and vectors in Python lists / 内存向量索引，模拟 Faiss/Milvus |

**File / 文件**: `src/tests/test_utils.py`

| Decorator / Factory | Purpose / 用途 |
|------------|------|
| `with_mock_ollama_embedding` | Patches `ollama._client.Client._request_raw` to return mock embedding |
| `with_mock_openai_embedding` | Patches `openai.resources.embeddings.Embeddings.create` to return mock embedding |
| `with_mock_ollama_client` | Patches Ollama LLM client to return mock chat response |
| `with_mock_openai_client` | Patches OpenAI LLM client to return mock chat response |

**Design principle / 设计原则**: Operator tests use mocks (~200 tests). They test processing logic, not API integration. Integration tests use real services and are gated by `SKIP_EXTERNAL_SERVICES`.

---

## 3. How to Run / 如何运行

### 3.1 Quick Commands / 快速命令

```bash
# Must be run from hugegraph-llm/ directory
# 必须在 hugegraph-llm/ 目录下运行
cd hugegraph-llm

# Config V2 tests only (no external services needed)
# 仅 Config V2 测试（无需外部服务）
python -m pytest src/tests/config/ -v

# Full unit test suite (skips external services)
# 全量单元测试（跳过外部服务）
python -m pytest src/tests/ -v

# Full test suite WITH external services (needs Ollama + HugeGraph running)
# 含外部服务的全量测试（需要 Ollama + HugeGraph 运行中）
SKIP_EXTERNAL_SERVICES=false python -m pytest src/tests/ -v

# With coverage report
# 含覆盖率报告
python -m pytest src/tests/config/ src/tests/ --cov=src/hugegraph_llm/config --cov-report=term-missing

# Single test class
python -m pytest src/tests/config/test_config.py::TestSecretIsolation -v

# Single test method
python -m pytest src/tests/config/test_config.py::TestFailFast::test_corrupt_yaml_fails_fast -v
```text

### 3.2 Expected Results / 预期结果

**Default (SKIP_EXTERNAL_SERVICES=true) / 默认**:

```text
============================== 283 passed, 13 skipped in ~13s ==============================
```text

**With external services / 含外部服务** (Ollama + HugeGraph running):

```text
============================== 296 passed in ~60s ==============================
```text

### 3.3 CWD Requirement / 工作目录要求

Tests **must** be run from `hugegraph-llm/` (project root). Running from the repo root (`hugegraph-ai/`) will fail because `base_prompt_config.py` validates CWD against the project root.

This is enforced by `base_prompt_config.py:62-68`:

```python
if os.getcwd() != project_root:
    log.error("Current working directory is not the project root. ...")
    sys.exit(1)
```text

---

## 4. Config V2 Test Matrix / Config V2 测试矩阵

### 4.1 Test Classes & Requirements Coverage / 测试类与需求覆盖

| # | Test Class / 测试类 | Methods / 方法数 | Requirement(s) Covered / 覆盖的需求 |
|---|------------|-------|------|
| 1 | `TestFlatNestedConversion` | 4 | flat↔nested round-trip (§3 architecture) |
| 2 | `TestEnvVarPriority` | 1 | `os.environ` > YAML > defaults priority |
| 3 | `TestSecretIsolation` | 1 | Env secret NOT written to config.yaml |
| 4 | `TestPhase1Migration` | 2 | Phase1→Phase2 migration + backup |
| 5 | `TestFailFast` | 2 | Invalid YAML + type mismatch → exception |
| 6 | `TestDeprecatedWrappers` | 1 | `update_env()` / `check_env()` backward compat |
| 7 | `TestEnvMigrationDoesNotPolluteOsEnviron` | 1 | `.env` migration uses `dotenv_values()`, not `os.environ` |
| 8 | `TestEmptyEnvDoesNotClearYaml` | 1 | Empty env `""` preserves YAML value |
| 9 | `TestConfigPathNotCwd` | 1 | `YAML_PATH` derived from `__file__`, not `os.getcwd()` |
| 10 | `TestConfigManagerSingleton` | 2 | Singleton identity + sections preservation |
| 11 | `TestEnvToYamlMigration` | 2 | `.env` → nested YAML happy path + field filtering |
| 12 | `TestEnvOverridesMigratedEnv` | 1 | `os.environ` overrides migrated `.env` value after restart |
| 13 | `TestEnvAliasPriority` | 2 | `_env_var_map` custom names + shared env vars |

### 4.2 Test Isolation Strategy / 测试隔离策略

Each test class follows this pattern to avoid singleton pollution:
每个测试类遵循此模式以避免单例污染：

```python
class TestSomething(unittest.TestCase):
    def setUp(self):
        # Reset singleton before each test
        ConfigManager._instance = None

    def tearDown(self):
        # Clean up singleton + env vars after each test
        ConfigManager._instance = None
        os.environ.pop("ENV_VAR_USED_IN_TEST", None)

    def test_something(self):
        # Use tempfile.TemporaryDirectory() for config files
        # Use mock.patch() to redirect YAML_PATH / ENV_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = os.path.join(tmpdir, "config.yaml")
            with mock.patch("...YAML_PATH", yaml_path):
                ...  # test logic
```text

**Why this matters / 为什么这很重要**: `ConfigManager` is a singleton. Without `_instance = None` reset, test order would matter — a test that creates ConfigManager with `sections={"llm": LLMConfig}` would leak into the next test. Each test creates its own ConfigManager in a temp directory to ensure full isolation.
`ConfigManager` 是单例。不重置 `_instance` 会导致测试顺序依赖 —— 前一个测试的 sections 会泄露到后一个测试。

---

## 5. Known Limitations / 已知限制

### 5.1 Skipped Test Model Dependency / 跳过测试的模型依赖

The 3 Ollama tests are hardcoded to use `llama3:8b-instruct-fp16` (~16GB VRAM). Running them requires:
3 个 Ollama 测试硬编码使用 `llama3:8b-instruct-fp16`（~16GB VRAM）。运行需要：

- Ollama service running / Ollama 服务运行中
- `ollama pull llama3:8b-instruct-fp16` — **requires ~16GB VRAM / 需要约 16GB 显存**
- RTX 2060 (6GB) **cannot** run this test even with external services enabled / 即使启用外部服务，RTX 2060 也无法运行此测试

**Workaround**: Edit `test_ollama_client.py` to use a smaller model like `llama3.2:3b` before running.
**解决方法**: 运行前编辑 `test_ollama_client.py`，将模型改为更小的模型如 `llama3.2:3b`。

### 5.2 CWD Constraint / 工作目录约束

Tests must be run from `hugegraph-llm/`. Running from `hugegraph-ai/` (repo root) will fail with `SystemExit: 1`.
测试必须在 `hugegraph-llm/` 下运行。从 `hugegraph-ai/`（仓库根）运行会以 `SystemExit: 1` 失败。

### 5.3 Coverage Gaps / 覆盖率缺口

| File / 文件 | Gap / 缺口 | Severity / 严重度 |
|------|-------|---------|
| `generate.py` (0%) | CLI entry point — tested manually only | Low / 低 |
| `base_prompt_config.py` (58%) | Pre-existing; separate prompt system | Low / 低 |
| `base_config.py` `generate_yaml()` interactive path | Requires stdin; tested manually | Low / 低 |
| `base_config.py` `check_config()` diff logic | Requires real config.yaml state transitions | Low / 低 |
