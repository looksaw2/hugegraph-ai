# HugeGraph-LLM 配置说明

HugeGraph-LLM 使用 `config.yaml` 保存非敏感运行配置，使用 `.env` 保存本地密钥。环境变量仍可用于容器、Kubernetes Secret 或临时覆盖。

## 配置文件

| 文件 | 用途 | 是否提交 |
|---|---|---|
| `config.example.yaml` | 示例配置，只包含非敏感值 | 是 |
| `config.yaml` | 本地运行配置，保存模型、服务地址、查询限制等非敏感值 | 否 |
| `.env` | 本地密钥文件，只保存 API key、token、password 等敏感值 | 否 |
| `src/hugegraph_llm/resources/demo/config_prompt.yaml` | Demo prompt 配置 | 是 |

默认配置目录为 `hugegraph-llm/`。如需在部署环境中使用独立目录，设置：

```bash
export HUGEGRAPH_LLM_CONFIG_DIR=/path/to/hugegraph-llm-config
```

`HUGEGRAPH_AI_CONFIG_DIR` 仍可作为兼容别名使用。两个变量同时存在时，`HUGEGRAPH_LLM_CONFIG_DIR` 优先。

## 加载优先级

配置按以下顺序合并，越靠前优先级越高：

```text
process environment
  > .env secrets
  > config.yaml
  > defaults
```

说明：

- 进程环境变量可以覆盖已登记的任意配置项，适合容器和临时调试。
- `.env` 只作为 secret-only 文件；其中的非敏感旧配置不会覆盖 `config.yaml`。
- `config.yaml` 只保存非敏感配置，不应出现真实 API key、token 或 password。
- 导入 `hugegraph_llm.config` 不会创建或改写配置文件。

## 快速开始

从示例生成本地配置：

```bash
cp hugegraph-llm/config.example.yaml hugegraph-llm/config.yaml
```

把密钥写入 `.env`：

```properties
OPENAI_API_KEY=sk-...
GRAPH_PWD=your-password
ADMIN_TOKEN=your-admin-token
```

也可以显式生成当前配置文件：

```bash
cd hugegraph-llm
uv run python -m hugegraph_llm.config.generate
```

如果从旧版 `.env` 或扁平 YAML 升级，先查看迁移计划：

```bash
hugegraph-llm-config --config-dir /path/to/config doctor
hugegraph-llm-config --config-dir /path/to/config plan
hugegraph-llm-config --config-dir /path/to/config diff
```

确认后再执行迁移：

```bash
hugegraph-llm-config --config-dir /path/to/config apply --yes
```

更多迁移细节见 [config-migration-upgrade-guide.md](config-migration-upgrade-guide.md)。

## `config.yaml` 结构

`config.yaml` 使用嵌套结构，顶层分为 `llm`、`hugegraph`、`admin` 和 `index`：

```yaml
llm:
  language: EN
  chat_llm_type: openai
  openai:
    chat:
      api_base: https://api.openai.com/v1
      language_model: gpt-4.1-mini
      tokens: 8192

hugegraph:
  graph:
    url: 127.0.0.1:8080
    name: hugegraph
    user: admin

admin:
  login:
    enable: "False"

index:
  cur_vector_index: Faiss
```

完整示例见 [config.example.yaml](config.example.yaml)。

## LLM 配置

### 基础配置

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `llm.language` | `LANGUAGE` | `EN` | Prompt 语言，支持 `EN`、`CN` |
| `llm.chat_llm_type` | `CHAT_LLM_TYPE` | `openai` | 聊天模型类型 |
| `llm.extract_llm_type` | `EXTRACT_LLM_TYPE` | `openai` | 信息抽取模型类型 |
| `llm.text2gql_llm_type` | `TEXT2GQL_LLM_TYPE` | `openai` | Text2Gremlin 模型类型 |
| `llm.embedding_type` | `EMBEDDING_TYPE` | `openai` | Embedding 模型类型 |
| `llm.reranker.type` | `RERANKER_TYPE` | `null` | Reranker 类型，支持 `cohere`、`siliconflow` |
| `llm.keyword_extract.type` | `KEYWORD_EXTRACT_TYPE` | `llm` | 关键词提取类型 |
| `llm.keyword_extract.window_size` | `WINDOW_SIZE` | `3` | TextRank 滑窗大小 |
| `llm.keyword_extract.hybrid_llm_weights` | `HYBRID_LLM_WEIGHTS` | `0.5` | Hybrid 模式中 LLM 结果权重 |

### OpenAI

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `llm.openai.chat.api_base` | `OPENAI_CHAT_API_BASE`, `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Chat API 地址 |
| `llm.openai.chat.language_model` | `OPENAI_CHAT_LANGUAGE_MODEL` | `gpt-4.1-mini` | Chat 模型 |
| `llm.openai.chat.tokens` | `OPENAI_CHAT_TOKENS` | `8192` | Chat 最大 token |
| `llm.openai.extract.api_base` | `OPENAI_EXTRACT_API_BASE`, `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Extract API 地址 |
| `llm.openai.extract.language_model` | `OPENAI_EXTRACT_LANGUAGE_MODEL` | `gpt-4.1-mini` | Extract 模型 |
| `llm.openai.extract.tokens` | `OPENAI_EXTRACT_TOKENS` | `256` | Extract 最大 token |
| `llm.openai.text2gql.api_base` | `OPENAI_TEXT2GQL_API_BASE`, `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Text2Gremlin API 地址 |
| `llm.openai.text2gql.language_model` | `OPENAI_TEXT2GQL_LANGUAGE_MODEL` | `gpt-4.1-mini` | Text2Gremlin 模型 |
| `llm.openai.text2gql.tokens` | `OPENAI_TEXT2GQL_TOKENS` | `4096` | Text2Gremlin 最大 token |
| `llm.openai.embedding.api_base` | `OPENAI_EMBEDDING_API_BASE`, `OPENAI_EMBEDDING_BASE_URL`, `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Embedding API 地址 |
| `llm.openai.embedding.model` | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型 |

OpenAI 密钥写入 `.env` 或进程环境变量：

```properties
OPENAI_API_KEY=sk-...
# 或按用途分别配置
OPENAI_CHAT_API_KEY=sk-...
OPENAI_EXTRACT_API_KEY=sk-...
OPENAI_TEXT2GQL_API_KEY=sk-...
OPENAI_EMBEDDING_API_KEY=sk-...
```

### LiteLLM

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `llm.litellm.chat.api_base` | `LITELLM_CHAT_API_BASE`, `LITELLM_BASE_URL` | `null` | Chat API 地址 |
| `llm.litellm.chat.language_model` | `LITELLM_CHAT_LANGUAGE_MODEL` | `openai/gpt-4.1-mini` | Chat 模型 |
| `llm.litellm.chat.tokens` | `LITELLM_CHAT_TOKENS` | `8192` | Chat 最大 token |
| `llm.litellm.extract.api_base` | `LITELLM_EXTRACT_API_BASE`, `LITELLM_BASE_URL` | `null` | Extract API 地址 |
| `llm.litellm.extract.language_model` | `LITELLM_EXTRACT_LANGUAGE_MODEL` | `openai/gpt-4.1-mini` | Extract 模型 |
| `llm.litellm.extract.tokens` | `LITELLM_EXTRACT_TOKENS` | `256` | Extract 最大 token |
| `llm.litellm.text2gql.api_base` | `LITELLM_TEXT2GQL_API_BASE`, `LITELLM_BASE_URL` | `null` | Text2Gremlin API 地址 |
| `llm.litellm.text2gql.language_model` | `LITELLM_TEXT2GQL_LANGUAGE_MODEL` | `openai/gpt-4.1-mini` | Text2Gremlin 模型 |
| `llm.litellm.text2gql.tokens` | `LITELLM_TEXT2GQL_TOKENS` | `4096` | Text2Gremlin 最大 token |
| `llm.litellm.embedding.api_base` | `LITELLM_EMBEDDING_API_BASE`, `LITELLM_BASE_URL` | `null` | Embedding API 地址 |
| `llm.litellm.embedding.model` | `LITELLM_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding 模型 |

LiteLLM 密钥写入 `.env` 或进程环境变量：

```properties
LITELLM_API_KEY=sk-...
# 或按用途分别配置
LITELLM_CHAT_API_KEY=sk-...
LITELLM_EXTRACT_API_KEY=sk-...
LITELLM_TEXT2GQL_API_KEY=sk-...
LITELLM_EMBEDDING_API_KEY=sk-...
```

### Ollama

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `llm.ollama.chat.host` | `OLLAMA_CHAT_HOST`, `OLLAMA_HOST` | `127.0.0.1` | Chat 服务地址 |
| `llm.ollama.chat.port` | `OLLAMA_CHAT_PORT`, `OLLAMA_PORT` | `11434` | Chat 服务端口 |
| `llm.ollama.chat.language_model` | `OLLAMA_CHAT_LANGUAGE_MODEL` | `null` | Chat 模型 |
| `llm.ollama.extract.host` | `OLLAMA_EXTRACT_HOST`, `OLLAMA_HOST` | `127.0.0.1` | Extract 服务地址 |
| `llm.ollama.extract.port` | `OLLAMA_EXTRACT_PORT`, `OLLAMA_PORT` | `11434` | Extract 服务端口 |
| `llm.ollama.extract.language_model` | `OLLAMA_EXTRACT_LANGUAGE_MODEL` | `null` | Extract 模型 |
| `llm.ollama.text2gql.host` | `OLLAMA_TEXT2GQL_HOST`, `OLLAMA_HOST` | `127.0.0.1` | Text2Gremlin 服务地址 |
| `llm.ollama.text2gql.port` | `OLLAMA_TEXT2GQL_PORT`, `OLLAMA_PORT` | `11434` | Text2Gremlin 服务端口 |
| `llm.ollama.text2gql.language_model` | `OLLAMA_TEXT2GQL_LANGUAGE_MODEL` | `null` | Text2Gremlin 模型 |
| `llm.ollama.embedding.host` | `OLLAMA_EMBEDDING_HOST`, `OLLAMA_HOST` | `127.0.0.1` | Embedding 服务地址 |
| `llm.ollama.embedding.port` | `OLLAMA_EMBEDDING_PORT`, `OLLAMA_PORT` | `11434` | Embedding 服务端口 |
| `llm.ollama.embedding.model` | `OLLAMA_EMBEDDING_MODEL` | `null` | Embedding 模型 |

### Reranker

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `llm.cohere.base_url` | `CO_API_URL`, `COHERE_BASE_URL` | `https://api.cohere.com/v1/rerank` | Cohere rerank API 地址 |
| `llm.reranker.model` | `RERANKER_MODEL` | `null` | Reranker 模型 |

Reranker 密钥写入 `.env` 或进程环境变量：

```properties
RERANKER_API_KEY=...
# 兼容变量
COHERE_API_KEY=...
SILICONFLOW_API_KEY=...
```

## HugeGraph 配置

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `hugegraph.graph.url` | `GRAPH_URL` | `127.0.0.1:8080` | HugeGraph Server 地址 |
| `hugegraph.graph.name` | `GRAPH_NAME` | `hugegraph` | 图名称 |
| `hugegraph.graph.user` | `GRAPH_USER` | `admin` | 用户名 |
| `hugegraph.graph.space` | `GRAPH_SPACE` | `null` | Graph space |
| `hugegraph.query.limit_property` | `LIMIT_PROPERTY` | `"False"` | 是否限制属性，当前为字符串 |
| `hugegraph.query.max_graph_path` | `MAX_GRAPH_PATH` | `10` | 最大路径长度 |
| `hugegraph.query.max_graph_items` | `MAX_GRAPH_ITEMS` | `30` | 最大图元素数量 |
| `hugegraph.query.edge_limit_pre_label` | `EDGE_LIMIT_PRE_LABEL` | `8` | 每个 label 的边数量限制 |
| `hugegraph.vector.dis_threshold` | `VECTOR_DIS_THRESHOLD` | `0.9` | 向量距离阈值 |
| `hugegraph.vector.topk_per_keyword` | `TOPK_PER_KEYWORD` | `1` | 每个关键词的 TopK |
| `hugegraph.rerank.topk_return_results` | `TOPK_RETURN_RESULTS` | `20` | Rerank 返回数量 |

HugeGraph 密码写入 `.env` 或进程环境变量：

```properties
GRAPH_PWD=your-password
```

## Admin 配置

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `admin.login.enable` | `ENABLE_LOGIN`, `ENABLE` | `"False"` | 是否启用登录，当前为字符串 |

登录 token 写入 `.env` 或进程环境变量：

```properties
USER_TOKEN=4321
ADMIN_TOKEN=xxxx
```

## Vector Index 配置

| YAML path | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `index.cur_vector_index` | `CUR_VECTOR_INDEX` | `Faiss` | 当前向量索引类型 |
| `index.qdrant.host` | `QDRANT_HOST` | `null` | Qdrant 地址 |
| `index.qdrant.port` | `QDRANT_PORT` | `6333` | Qdrant 端口 |
| `index.milvus.host` | `MILVUS_HOST` | `null` | Milvus 地址 |
| `index.milvus.port` | `MILVUS_PORT` | `19530` | Milvus 端口 |
| `index.milvus.user` | `MILVUS_USER` | `""` | Milvus 用户 |

向量数据库密钥写入 `.env` 或进程环境变量：

```properties
QDRANT_API_KEY=...
MILVUS_PASSWORD=...
```

## 在代码中读取配置

现有 settings 入口保持兼容：

```python
from hugegraph_llm.config import huge_settings, llm_settings

print(llm_settings.language)
print(llm_settings.chat_llm_type)
print(huge_settings.graph_url)
```

也可以直接实例化配置类：

```python
from hugegraph_llm.config.hugegraph_config import HugeGraphConfig
from hugegraph_llm.config.llm_config import LLMConfig

llm_config = LLMConfig()
graph_config = HugeGraphConfig()

print(llm_config.openai_chat_language_model)
print(graph_config.graph_name)
```

## 注意事项

1. 不要把真实的 `config.yaml`、`.env`、迁移备份或迁移报告提交到代码仓库。
2. `config.yaml` 只放非敏感配置；API key、token、password 放到 `.env` 或进程环境变量。
3. `.env` 中的非敏感旧配置只用于迁移输入，正常读取时不会覆盖 `config.yaml`。
4. 修改 `LANGUAGE`、LLM 类型、模型名称等运行配置后，建议重启服务以保证所有消费者加载一致。
5. `LIMIT_PROPERTY` 和 `ENABLE_LOGIN` 目前仍是字符串值，例如 `"False"`、`"True"`。
6. Docker compose 的 `.env` 只用于 compose 变量插值，和 HugeGraph-LLM runtime `.env` 不是同一个概念。

## 相关文档

- [README](README.md)
- [配置迁移指南](config-migration-upgrade-guide.md)
