# Pain Points → Solutions: Config Migration V2

本文档将当前配置系统的每一个痛点逐一映射到 V2 plan 中的具体解决方案，确保每个问题都有明确的、可追溯的应对措施。

---

## Phase 0 痛点（.env 阶段）

### 痛点 1：60+ 条扁平 KEY=VALUE，无分组

**现状**：所有配置项挤在一个 `.env` 文件中，无法区分哪个配置属于哪个组件。

```text
OPENAI_CHAT_API_BASE=https://...
OPENAI_CHAT_API_KEY=...
GRAPH_URL=mygraph:9999
QDRANT_HOST=...
ADMIN_TOKEN=...
```text

**解决方案**：语义化嵌套 YAML 结构

将配置按 **组件语义** 拆分到嵌套节中：

```yaml
llm:        # LLM 相关所有配置
  openai:
    chat:
      api_base: ...
      api_key: ...
hugegraph:  # 图数据库相关所有配置
  graph:
    url: ...
index:      # 向量索引相关所有配置
  qdrant:
    host: ...
admin:      # 管理相关所有配置
  login:
    admin_token: ...
```text

**实现位置**：Task 2 (Core Infrastructure — OmegaConf 结构化加载), Task 4 (LLM Config 嵌套映射), Task 5 (其余 Config 类嵌套映射)

---

### 痛点 2：ALL_CAPS 键名，不符合 YAML/JSON 惯例

**现状**：`.env` 文件中所有 key 都是大写 + 下划线（如 `OPENAI_CHAT_API_BASE`），与 YAML/JSON 生态系统的小写/驼峰约定不一致。

**解决方案**：全部迁移为小写 YAML 键名

| 旧格式 (ALL_CAPS) | 新格式 (lowercase nested) |
|-------------------|--------------------------|
| `OPENAI_CHAT_API_BASE` | `llm.openai.chat.api_base` |
| `GRAPH_URL` | `hugegraph.graph.url` |
| `QDRANT_HOST` | `index.qdrant.host` |

**实现位置**：Task 4, Task 5 — 通过 `_flat_to_nested_mapping` 集中声明映射关系

---

### 痛点 3：无类型语义 — 一切都是字符串

**现状**：`python-dotenv` 加载的所有值都是字符串类型。`max_graph_path: "10"` 和 `dis_threshold: "0.9"` 在运行时需要手动转换，容易出错。

**解决方案**：Pydantic BaseModel 提供完整类型系统

```python
# 旧：手动处理类型
max_graph_path = int(os.environ.get("MAX_GRAPH_PATH", "10"))

# 新：Pydantic 自动验证和转换
max_graph_path: int = 10  # Pydantic 自动将 YAML 中的 "10" 转为 int
dis_threshold: float = 0.9
```text

**实现位置**：Task 3 — `BaseSettings → BaseModel` 切换，OmegaConf 接管文件加载，Pydantic 负责类型验证

---

### 痛点 4：Provider × Role 组合全挤在扁平命名空间

**现状**：4 个 LLM 提供商 × 4 个角色 = 16 组配置，每组 3-4 个字段，全部以扁平前缀命名（`openai_chat_api_base`, `ollama_embedding_host`...），约 55 个字段混在一起。

**解决方案**：按 provider → role 两级嵌套分组

```yaml
# 旧：55 个扁平字段
openai_chat_api_base=...
openai_chat_api_key=...
openai_extract_api_base=...
ollama_chat_host=...
ollama_embedding_host=...

# 新：自然的两级嵌套
llm:
  openai:
    chat:    {api_base, api_key, language_model, tokens}
    extract: {api_base, api_key, language_model, tokens}
    embedding: {api_base, api_key, language_model, tokens}
  ollama:
    chat:    {host, ...}
    embedding: {host, ...}
```text

**实现位置**：Task 4 — LLMConfig 的 44 条映射规则 + 8 条 env var 映射

---

### 痛点 5：环境变量覆盖逻辑分散在各处

**现状**：每个字段的默认值都内联调用 `os.environ.get("X", default)`，逻辑碎片化：

```python
# 分散在多个 Field 定义中
openai_chat_api_key: str = Field(default=os.environ.get("OPENAI_API_KEY", ""))
openai_extract_api_key: str = Field(default=os.environ.get("OPENAI_API_KEY", ""))
graph_url: str = Field(default=os.environ.get("GRAPH_URL", "127.0.0.1:8080"))
```text

**解决方案**：集中式 `_env_var_map`，每类一个地方声明 env 映射

```python
# LLMConfig 内部集中声明
_env_var_map: ClassVar[dict] = {
    "openai_chat_api_key": ["OPENAI_CHAT_API_KEY", "OPENAI_API_KEY"],
    "openai_extract_api_key": ["OPENAI_API_KEY"],
    ...
}
```text

合并优先级统一为：`os.environ > config.yaml > pydantic defaults`，由 ConfigManager 集中处理，不再散落在每个 Field 中。

**实现位置**：Task 2.3 (Env var override design), Task 3.2 (_env_var_map class variable contract)

---

### 痛点 6：无法将关联设置分组在一起

**现状**：用户想查看/修改 "所有 OpenAI Chat 相关设置" 时，需要在 60+ 行的 `.env` 文件中搜索 `openai_chat` 前缀，心智负担高。

**解决方案**：嵌套 YAML 自然分组

修改 OpenAI Chat 配置时，用户只需定位到一个清晰的 YAML 子树：

```yaml
llm:
  openai:
    chat:              # ← 所有 OpenAI Chat 配置集中在此
      api_base: ...
      api_key: ...
      language_model: ...
      tokens: ...
```text

**实现位置**：Task 4 (LLM 嵌套映射), Task 5 (其余配置类映射)

---

### 痛点 7：修改配置需要重启应用

**现状**：没有热加载机制，任何配置改动都需要重启进程。

**V1 方案**：**保持重启生效，明确边界**。V1 不引入热加载，原因是：

- OmegaConf 本身不提供文件监听或运行时刷新机制
- 即使引入 `watchfiles`/`watchdog`，真正复杂的是 reload 后如何安全影响已创建的 LLM/Embedding/HugeGraph/Vector DB client
- Reload 需要处理锁、回滚、校验失败、env override 优先级等问题

配置文件修改后**重启进程生效**。热加载作为 Future Phase 独立调研。

**实现位置**：§4 Future Phase: Hot-Reload (NOT in V1 MVP)

---

## Phase 1 痛点（flat config.yaml 阶段）

### 痛点 8：节名称是 Python 类名，泄露实现细节

**现状**：Phase 1 的 YAML 节名直接使用 Python 类名：

```yaml
AdminConfig:
  ...
LLMConfig:
  ...
HugeGraphConfig:
  ...
```text

**解决方案**：语义化节名

```yaml
# Phase 1 → Phase 2
AdminConfig     → admin
LLMConfig       → llm
HugeGraphConfig → hugegraph
IndexConfig     → index
```text

用户不需要知道 Python 类的名字，只需知道他们在配置哪个**组件**。

**实现位置**：Task 3.2 — `_config_section: ClassVar[str]` 声明每个类属于哪个语义节

---

### 痛点 9：Phase 1 YAML 键名仍然 ALL_CAPS

**现状**：Phase 1 把 `.env` 的内容几乎原样搬到了 YAML，键名仍然大写。

**解决方案**：同痛点 2，通过 `_flat_to_nested_mapping` 全部转为小写 + 嵌套路径。

---

### 痛点 10：LLMConfig 仍然有 60+ 扁平条目

**现状**：Phase 1 只是换了文件格式（`.env` → `.yaml`），没有改变数据结构，LLM 相关配置仍然全部扁平化。

**解决方案**：同痛点 4，按 provider → role 两级嵌套彻底重组 LLM 配置结构。

---

## 领导反馈新增的设计约束

### 痛点 11：容器/K8s 注入的 Secret 可能被写回 config.yaml

**风险场景**：Kubernetes 通过 `os.environ` 注入 `OPENAI_API_KEY`、`QDRANT_API_KEY`、`ADMIN_TOKEN` 等 secret。如果 `save()` 把包含 env override 的运行时配置直接写回磁盘，secret 就会泄露到 `config.yaml` 文件中。

**解决方案**：ConfigManager 两层分离

```text
persisted_config:   只来自 config.yaml → save() 写回（不含 env override）
effective_config:   defaults ← YAML ← os.environ → 仅运行时读取（只读）
```text

`save()` 只写 `persisted_config`，确保 env-sourced secret **永远不会落盘**。

**实现位置**：Task 2.2 (ConfigManager — 两层分离), Task 2.4 (.env handling policy)

---

### 痛点 12：缺少 Phase1 flat YAML 到 nested YAML 的迁移路径

**风险**：原 plan 主要覆盖 `.env` → `config.yaml`，但没有显式处理已有的 Phase1 flat YAML 用户。直接依赖 OmegaConf "能读任何合法 YAML" 不正确，因为旧的 flat section/key 结构与新的 nested 结构不等价。

**解决方案**：三格式完整迁移路径

| 格式 | 来源 | 特征 |
|------|------|------|
| Phase0 | `.env` | ALL_CAPS 扁平键，`python-dotenv` 加载 |
| Phase1 | `config.yaml` (flat) | 类名节 (`LLMConfig`)，ALL_CAPS 键 |
| Phase2 | `config.yaml` (nested) | 语义节 (`llm`)，小写键（目标格式） |

迁移流程：

```text
detect old format → normalize to flat pydantic dict → validate
→ convert to nested YAML → write config.yaml.bak → atomic replace
```text

**实现位置**：Task 2.2 (`_migrate_from_env()`, `_migrate_from_phase1_yaml()`), Task 3.6 (Three-format migration path)

---

### 痛点 13：配置错误时静默回退到默认值 — 生产风险

**风险场景**：原 plan 写的是 "YAML load failure → fall back to empty config → pydantic defaults"。如果 `config.yaml` 损坏或格式错误，系统静默使用默认值启动，可能连接到错误服务或使用错误凭证，在**生产环境造成严重事故**。

**解决方案**：Fail Fast 策略

| 场景 | 原策略 | 新策略 |
|------|--------|--------|
| 启动时 config.yaml 无效 | 回退到空配置 + pydantic 默认值 | **Fail fast** — 清晰报错，进程不启动 |
| 未来 reload 时新 YAML 无效 | 未定义 | 保留 last-known-good，清晰暴露错误 |
| env 类型转换失败 | 保留字符串值 | **Validation failure** — 进程不启动 |

核心原则：**配置错误应尽早、尽可能大声地暴露**。

**实现位置**：§5 Risk Assessment (V2 — tightened)

---

### 痛点 14：Config path 依赖 CWD

**风险**：如果 ConfigManager 使用相对路径定位 `config.yaml`，从不同工作目录启动应用会导致加载不同的配置文件或找不到文件。

**解决方案**：Config path 相对固定基准目录解析，不依赖 `os.getcwd()`。

**实现位置**：Task 7.2 (测试) — "config path does not depend on CWD"

---

## 痛点 → 任务 追溯矩阵

| 痛点 | 简述 | 主要实现 Task |
|------|------|--------------|
| 1 | 扁平无分组 | Task 2, 4, 5 |
| 2 | ALL_CAPS 键名 | Task 4, 5 |
| 3 | 无类型语义 | Task 3 |
| 4 | Provider×Role 扁平 | Task 4 |
| 5 | env 覆盖逻辑分散 | Task 2.3, 3.2 |
| 6 | 无法分组查看 | Task 4, 5 |
| 7 | 无热加载（V1 保持） | §4 Future Phase |
| 8 | 类名节泄露实现 | Task 3.2 |
| 9 | Phase1 仍 ALL_CAPS | Task 4, 5 |
| 10 | Phase1 仍 60+ 扁平 | Task 4 |
| 11 | Secret 可能落盘 | Task 2.2, 2.4 |
| 12 | Phase1→2 迁移缺失 | Task 2.2, 3.6 |
| 13 | 静默回退默认值 | §5 Risk Assessment |
| 14 | CWD 依赖 | Task 7.2 |
