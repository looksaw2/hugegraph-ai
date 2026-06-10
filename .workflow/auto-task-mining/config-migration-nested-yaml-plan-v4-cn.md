# V4版本中文

> 方案：.env → YAML → OmegaConf 嵌套配置迁移（V4 契约加固版）
>
> **关联 Issue：** https://github.com/apache/hugegraph-ai/issues/234

---

## 从 V3 到 V4 的变更

V3 审阅评分：7.8/10 —— 方向正确；实现契约需进一步加固。

| # | 来源 | 变更 | 优先级 |
|---|------|------|--------|
| 1 | 飞书评论 P1 | `update_config()` API 加固：仅接受显式 patch dict；强制 effective/env-sourced 字段不写回 YAML | P1 |
| 2 | 飞书评论 P2 | PromptConfig / config_prompt.yaml 副作用链纳入边界分析 | P2 |
| 3 | 飞书评论 P2 | CI 门禁命令改为仓库实际可执行路径 | P2 |
| 4 | 飞书评论 P2 | 部署文档改为真实路径级验收清单 + 验证 grep | P2 |
| 5 | 飞书评论 P2 | 未知用户 key 与未映射模型字段拆为两套策略；未知 key 归入 `_migration_unknown:` | P2 |
| 6 | 飞书评论 P2 | `.gitignore` 规则收窄到 `hugegraph-llm/`；添加 `config.example.yaml` | P2 |
| 7 | 飞书评论 P2 | **标题缺陷**：V3 标题"计划：.env → YAML → OmegaConf 嵌套配置迁移"过于冗长且中英混杂，不利于知识库检索和快速识别。**V4 解决**：标题改为简洁中文"V4版本中文"，完整描述性标题下移为副标题。 | P2 |

---

## 1. 问题与动机

### 当前状态（Phase 0）

配置通过 `python-dotenv` 加载的 `.env` 文件存储：

```text
OPENAI_CHAT_API_BASE=https://...
OPENAI_CHAT_API_KEY=...
GRAPH_URL=mygraph:9999
...
```

**痛点：**

- 60+ 个扁平的 `KEY=VALUE` 行，无分组 —— 难以区分哪些配置属于哪个组件
- 全大写键名遍布各处，与 YAML/JSON 惯例不一致
- 无语义类型 —— 一切都是字符串
- 提供商 × 角色组合（4 提供商 × 4 角色 = 16 个配置组）全部挤在一个扁平命名空间中
- 环境变量覆盖逻辑分散：每个字段默认值都内联调用 `os.environ.get("X", default)`
- 无法将相关配置分组（例如，将所有 OpenAI 聊天配置放在一起）
- 修改配置需要重启应用

### 初步改进（Phase 1，PR 已完成）

使用 `yaml.safe_load/safe_dump` 将 `.env` 替换为扁平的 `config.yaml`。这修复了文件格式，但仍未解决结构化问题：

- 节名是 Python 类名（`AdminConfig`、`LLMConfig`）—— 向用户泄露了实现细节
- 键名仍为全大写
- LLMConfig 仍然有 60+ 个扁平条目，4 个提供商全部混在一起

### 目标（Phase 2 —— 本方案，V4 契约加固版）

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
```

**设计原则：**

1. 节名语义化（`llm`、`hugegraph`），而非类名（`LLMConfig`）
2. 键名小写（YAML 惯例）
3. LLM 配置按 提供商 → 角色 嵌套（自然分组）
4. 合并优先级：`os.environ > config.yaml > pydantic defaults`
5. 环境变量映射集中在每个配置类的一个位置
6. **V1 范围约束：config.yaml 修改后需重启进程才能生效** —— 热加载推迟到未来阶段。OmegaConf 适用于 YAML 加载/合并/保存以及结构化配置验证，而非自动文件监控或 Spring/Log4j 式的运行时刷新。这使得 V1 可以专注于做好核心关注点：配置拆分、迁移兼容性和环境变量优先级。

---

## 2. 架构设计

### Before/After 对比

**Phase 1（之前）：**

```
config.yaml（扁平，类名节名，全大写键名）
  → yaml.safe_load / yaml.safe_dump
  → pydantic_settings.BaseSettings
  → Field 默认值中散布 os.environ.get() 调用
```

**Phase 2（V4 契约加固版）：**

```
config.yaml（嵌套，语义节名，小写键名）
  → OmegaConf（结构化加载/合并/保存）
  → ConfigManager（单例：所有配置操作的统一入口）
      ├── persisted_config:  仅来自 config.yaml，可被 save()，不含运行时环境变量覆盖
      └── effective_config:  pydantic 默认值 ← config.yaml ← os.environ（运行时只读）
  → pydantic.BaseModel（不再加载 env-file；OmegaConf 接管）
  → 通过每个类的 _env_var_map 集中管理环境变量覆盖（有序解析）
```

### 核心架构决策 —— 两层配置分离

ConfigManager 将"持久化配置"与"生效配置"分离：

| 层 | 来源 | 可写 | 包含 |
|----|------|------|------|
| `persisted_config` | 仅 `config.yaml` | 是（`save()`） | 声明式配置值；不含运行时环境变量覆盖 |
| `effective_config` | 默认值 → YAML → `os.environ` | 否（只读） | 运行时使用的最终合并值 |

> **关键安全边界：** 这可以防止容器/Kubernetes 注入的密钥（`OPENAI_API_KEY`、`QDRANT_API_KEY`、`ADMIN_TOKEN`）被意外写回 `config.yaml`。

### 关键来源边界：.env vs os.environ vs K8s Secret

三种不同的配置来源绝不能混为一谈：

| 来源 | 角色 | 参与 effective config？ | 可持久化到 YAML？ |
|------|------|------------------------|-------------------|
| 本地 `.env` 文件 | **仅一次性迁移输入** | 否（绝不加载到 `os.environ`） | 是 —— 仅在迁移期间，值写入 `config.yaml` |
| 运行时 `os.environ` | **运行时覆盖** | 是（最高优先级） | **绝不** |
| K8s Secret / 容器注入 | **运行时覆盖** | 是（最高优先级） | **绝不** |

**强化规则：**

1. `.env` 仅在没有 Phase2 nested `config.yaml` 时读取 —— 它是本地历史输入，不是运行时来源
2. 运行时 `os.environ` / K8s Secret 仅参与 `effective_config`，绝不参与 `persisted_config`
3. 如果 `.env` 和 `os.environ` 同时存在同名 key：运行时以 `os.environ` 为准；迁移写盘值仅来自本地 `.env` 或旧 YAML
4. 迁移完成后：**重命名或备份 `.env` → `.env.bak`**，避免用户误以为它仍是持续配置源

### V1 无后台守护线程

架构保持简洁 —— `config.yaml` → OmegaConf 加载/合并 → Pydantic 验证 → 配置单例对象。手动修改配置文件后需重启进程生效。

### 核心设计问题：扁平字段 vs 嵌套 YAML

pydantic 模型使用扁平字段名（`openai_chat_api_key`），但用户期望嵌套 YAML（`openai.chat.api_key`）。解决方案：每个配置类声明一个 `_flat_to_nested_mapping` 来桥接二者：

- `_flat_to_nested()`：将 pydantic 扁平字典 → 嵌套 YAML 字典（用于写 config.yaml）
- `_nested_to_flat()`：将嵌套 YAML 字典 → pydantic 扁平字典（用于读 config.yaml）

两个函数必须满足往返属性：`nested_to_flat(flat_to_nested(d)) == d`。

### V4 新增：PromptConfig / config_prompt.yaml 副作用链

**边界分析：**

当前 `hugegraph_llm.config.__init__` 创建 `PromptConfig(llm_settings)` 并调用 `prompt.ensure_yaml_file_exists()` —— 读写 `hugegraph_llm/resources/demo/config_prompt.yaml`。这条链与配置系统交互，因为：

- `llm.language` 通过 YAML/env override 设置，PromptConfig 据此选择/创建不同语言的 prompt YAML
- 在只读容器/只读 package 场景下，PromptConfig 可能尝试写 package 内部
- 当前 V3 测试覆盖只读 `config.yaml` 但未覆盖 prompt YAML 读写副作用

**V4 契约：**

| 规则 | 详情 |
|------|------|
| `config_prompt.yaml` 必须显式归类 | 选项：用户可写配置（与 config.yaml 同基准目录）或只读资源（不自动写入） |
| 若可写：路径相对于 config.yaml 同基准目录 | 统一配置路径基准 |
| 若只读：`ensure_yaml_file_exists()` 不得在启动时写入 | 缺失时 fail-fast，或作为 package resource 打包 |
| 测试覆盖 | `language=cn/en` × 已有 prompt yaml × 只读文件系统，验证三种组合下的行为 |

---

## 3. 任务分解

### 任务 1：研究 —— 全量依赖扫描 `[优先级: 高]`

**目标：** 映射每一行涉及 `.env`、`dotenv`、`update_env`、`check_env` 或 `generate_env` 的代码，确保零遗漏调用点。

**要做什么：**

- 在代码库中搜索 `dotenv`、`update_env`、`check_env`、`generate_env`、`set_key`、`dotenv_values`
- 建立命中清单：文件、行号、当前行为、需要的变更
- 验证没有隐藏在动态导入或 eval 背后的调用
- **V4 新增：** 同时映射 `PromptConfig`、`ensure_yaml_file_exists`、`config_prompt.yaml` 引用

---

### 任务 2：核心基础设施 —— 工具函数 + ConfigManager `[优先级: 高]`（依赖：任务 1）

**目标：** 构建所有其他部分依赖的两个基础。

#### 2.1 扁平↔嵌套 转换函数

两个纯函数，使用点号分隔的映射关系在 pydantic 扁平字段字典和嵌套 YAML 字典之间转换。必须满足往返属性，并处理边缘情况：不在映射中的字段、空映射、深层嵌套路径。

**映射覆盖率验收标准（V4 加强）：**

仅 round-trip 不够 —— "未映射字段保留在 top-level" 虽能避免数据丢失，但也可能掩盖字段漏迁移。以下覆盖率契约为强制要求：

| 要求 | 执行方式 |
|------|----------|
| 每个 config model 字段必须归类为：`mapped` / `intentional top-level` / `ignored-deprecated` | Code review checklist + CI assertion |
| 同一 nested path 不能被多个 flat field 映射（除非显式声明兼容 alias） | ConfigManager init 时验证 |
| 测试断言每个 config class 无不经审查的 unmapped field | 任务 7.1 自动化审计 |
| 生成迁移覆盖清单 —— 尤其覆盖 LLMConfig 约 55 字段 | 输出为 build artifact |
| Unmapped 字段警告作为可见的 review/CI 信号 | CI 输出 |

**V4 新增 —— unknown 分两类处理：**

| 类别 | 定义 | 行为 |
|------|------|------|
| **模型字段未映射** | 一个 pydantic model field 无映射条目且未归类为 `intentional top-level` 或 `ignored-deprecated` | **CI 失败** —— 必须在合并前解决 |
| **用户未知/旧 key** | 在 `.env` 或 Phase1 YAML 中发现的无匹配 pydantic model field 的 key | **保留** 到 `_migration_unknown:` 节；输出 WARNING（含来源和 key 名） |

这防止"保留在 top-level"成为掩盖映射审计失败的漏洞：

```yaml
# config.yaml
llm:
  ...

_migration_unknown:
  LLMConfig:
    OLD_FLAT_KEY: some_value
```

#### 2.2 ConfigManager 单例

线程安全的单例，掌管 OmegaConf 配置树和所有 YAML I/O。**关键设计边界：** 将"持久化配置"与"生效配置"分离。

| 方法 | 职责 |
|------|------|
| `__init__` | 通过 OmegaConf 加载 `config.yaml`（或在不存嵌套 YAML 时从 `.env` / Phase1 YAML 迁移） |
| `get_section_with_env_override()` | 以扁平字典形式返回某个配置节的生效配置，`os.environ` 值合并于 YAML 值之上 |
| `update_section()` | **V4 加固：** 仅接受显式 patch dict 或 `PersistedConfigPatch` —— 不接受完整 effective model。拒绝持久化任何来源为 `env` 或 `runtime_patch` 的值 |
| `save()` | 将 `persisted_config` 树持久化到 `config.yaml`（确保环境变量密钥绝不写入磁盘） |
| `_migrate_from_env()` | 一次性 `.env` → `config.yaml` 迁移；**成功后自动备份 `.env` → `.env.bak`** |
| `_migrate_from_phase1_yaml()` | 一次性 Phase1 扁平 YAML → 嵌套 YAML 迁移 |

**V4 新增 —— 字段来源追踪：**

```python
# ConfigManager 维护每个字段的来源元数据
_field_source: dict[str, Literal["default", "yaml", "env", "runtime_patch"]]
```

这是 `update_section()` 和 `save()` 拒绝 env 来源值的权威机制。字段来源在 `get_section_with_env_override()` 中设置一次，所有写入路径都查询它。

#### 2.3 环境变量覆盖设计

以 `openai_chat_api_base` 为例的合并优先级：

```text
pydantic 默认值：       "https://api.openai.com/v1"
config.yaml (YAML):     "https://custom.com/v1"
os.environ 覆盖：        OPENAI_BASE_URL="https://env.com/v1"
→ 最终结果：             "https://env.com/v1"  (os.environ 始终胜出)
```

类型转换：环境变量值（始终为字符串）必须通过 `TypeAdapter.validate_python()` 转换为字段的 pydantic 类型（`int`、`float`、`Optional[str]` 等）。**类型转换失败必须 fail-fast —— 不静默保留字符串值或回退到默认值。**

#### 2.4 .env 处理策略（V4 加强）

`.env` 仅被视为**一次性迁移输入**。以下可执行决策表约束所有 `.env` 交互：

| 场景 | 行为 |
|------|------|
| 已存在 Phase2 nested `config.yaml` | 直接从 YAML 加载；**绝不读取 `.env`** |
| 仅存在 Phase1 flat `config.yaml` | 迁移为 nested；生成 `config.yaml.bak` |
| 仅存在 `.env` | 迁移为 nested `config.yaml`；**自动备份 `.env` → `.env.bak`** |
| Phase1 `config.yaml` 和 `.env` 同时存在 | 以 `config.yaml` 为主；与 `.env` 差异字段 **打 warning** |
| 迁移后（任何场景） | `.env` 绝不加载到 `os.environ`；不作为持续配置源 |
| 运行时 `os.environ` / K8s Secret | 仅参与 `effective_config`；绝不持久化到 `config.yaml` |

---

### 任务 3：BaseConfig 基类重构 `[优先级: 高]`（依赖：任务 2）

**目标：** 重写配置基类，使其基于 OmegaConf 而非 pydantic-settings 工作。

#### 3.1 基类切换

`BaseSettings → BaseModel`。OmegaConf 接管文件加载；不再需要 pydantic-settings 的 `env_file` 功能。

#### 3.2 类变量契约

每个配置子类必须声明：

- `_config_section: ClassVar[str]` — 所属 YAML 节（`"llm"`, `"hugegraph"` 等）
- `_flat_to_nested_mapping: ClassVar[dict]` — 扁平字段名到嵌套 YAML 路径的映射
- `_env_var_map: ClassVar[dict]`（可选） — 每个字段应检查哪些环境变量名，**按优先级排序（list/tuple，非 set）**

#### 3.3 `__init__` 流程变更（V4 加强）

- 旧：`dotenv_values(.env)` → 注入 `os.environ` → `BaseSettings.__init__` → 同步到 `.env`
- 新：`ConfigManager.get_section_with_env_override()` → 合并程序化覆盖 → `BaseModel.__init__`

**关键约束 —— 初始化不自动持久化：**

| 规则 | 详情 |
|------|------|
| `__init__` 只构造运行时对象 | 不自动写回 YAML |
| 仅显式 `update_config()` / `generate_yaml()` / migration 可持久化 | 这些方法内部调用 `update_section()` + `save()` |
| `update_section()` 输入必须来自 persisted-source model | 不得包含 env override 值 |

#### 3.4 V4 新增 —— `update_config()` 加固 API 契约

V3 审阅中识别的风险路径：从 effective config 初始化的单例对象可能已包含 env secret。如果用户修改非敏感字段后调用 `update_config()`，naive 全量 dump 实现可能将 env secret 写入 `config.yaml`。

| V4 规则 | 详情 |
|------|------|
| `update_config()` 必须仅接受**显式 patch dict** | 示例: `update_config({"openai_chat_language_model": "gpt-4.1"})` —— 不是全量 model dump |
| ConfigManager 必须追踪字段来源 | `_field_source[field] ∈ {"default", "yaml", "env", "runtime_patch"}` |
| `update_section()` 必须拒绝 effective model | 仅接受 `PersistedConfigPatch` 或显式 dict |
| Env 来源字段值必须在所有写入路径中排除 | 每次赋值前检查字段来源 |

**测试要求：**
- YAML 无 `api_key`，env 有 `OPENAI_API_KEY=env-secret`
- 用户仅改 `language_model` 然后保存
- 断言 `config.yaml` 不含 `env-secret`

#### 3.5 方法迁移

- `update_env()` → `update_config()`：持久化到 YAML 而非 `.env`。**仅接受显式 patch dict（V4 加固）。**
- `generate_env()` → `generate_yaml()`：交互式 YAML 生成
- `check_env()` → `check_config()`：从 YAML 重新加载并与对象属性进行 diff；**敏感字段只显示 `***` 或 `changed`/`not changed`，绝不显示原值**

#### 3.6 向后兼容

保留 `update_env()`、`generate_env()`、`check_env()` 作为指向新方法的 Deprecated 包装器。现有消费者代码（如 `configs_block.py`）必须不被破坏。

#### 3.7 三格式迁移路径（V4 加强）

V1 必须支持从全部三种旧格式迁移：

| 格式 | 来源 | 特征 |
|------|------|------|
| Phase0 | `.env` | 全大写扁平键，由 `python-dotenv` 加载 |
| Phase1 | `config.yaml`（扁平） | 类名节名（`LLMConfig`, `AdminConfig`），全大写键 |
| Phase2（目标） | `config.yaml`（嵌套） | 语义节名（`llm`, `hugegraph`），小写键 |

**多格式冲突决策表（V4 加强）：**

| 已存在文件 | 行为 |
|------------|------|
| 已存在 Phase2 nested `config.yaml` | **直接加载** —— 不读取 `.env` 或 Phase1 YAML |
| 仅有 Phase1 flat `config.yaml` | 迁移为 nested；生成 `config.yaml.bak` |
| 仅有 `.env` | 迁移为 nested `config.yaml`；**备份 `.env` → `.env.bak`** |
| Phase1 `config.yaml` 和 `.env` 同时存在 | **以 `config.yaml` 为主**；对 `.env` 差异字段打 **warning** |
| 用户未知/旧 key（V4 细化） | **保留到 `_migration_unknown:` 节** 并标注来源；输出可追踪 warning |
| 模型字段未映射（V4 细化） | **CI 失败**，除非归类为 `intentional top-level` / `ignored-deprecated` |

**迁移流程（含无副作用验证）：**

```text
检测旧格式
  → 规范化为扁平 pydantic 字段字典
  → 用 model_validate / TypeAdapter 做纯校验（无 __init__、无单例初始化、无 env override、无 write-back）
  → IF 校验失败：终止并报清晰错误 —— 不生成或覆盖 config.yaml
  → IF 校验通过：转换为嵌套 YAML 结构
  → 分离已知模型字段 vs 未知旧 key
    → 已知字段 → 嵌套节
    → 未知 key → _migration_unknown 节（V4：保留，不散落 top-level）
  → 写 config.yaml.bak（备份）
  → 原子替换 config.yaml
  → IF 来源是 .env：重命名 .env → .env.bak
```

**无副作用验证契约（V4）：**

迁移验证不得复用正常 `BaseConfig.__init__`，否则会触发：
- 单例初始化副作用
- 环境变量覆盖注入
- 自动写回 YAML
- 路径解析副作用
- **V4 新增：** PromptConfig 初始化和 `config_prompt.yaml` 写入副作用

改用 `model_validate` / `TypeAdapter` 做纯校验和类型转换。校验失败不得生成或覆盖 `config.yaml`。

---

### 任务 4：LLM 配置嵌套映射 `[优先级: 高]`（依赖：任务 3）

**目标：** 为最复杂的配置类设计并实现嵌套结构。

**分析：** LLMConfig 有约 55 个字段。它们自然地沿两个维度组织：

| 维度 | 值 |
|------|-----|
| 提供商 | openai, ollama, litellm |
| 角色 | chat, extract, text2gql, embedding |

每个 提供商×角色 组合涵盖 3-4 个字段：`api_base`、`api_key`、`language_model`、`tokens`。

**映射模式（以 openai 为例）：**

```text
openai_chat_api_base          → openai.chat.api_base
openai_chat_api_key           → openai.chat.api_key
openai_chat_language_model    → openai.chat.language_model
openai_chat_tokens            → openai.chat.tokens
...对 extract、text2gql、embedding 同理...
...然后对 ollama、litellm 重复此模式...
```

**顶级字段（不嵌套）：** `language`, `chat_llm_type`, `extract_llm_type`, `text2gql_llm_type`, `embedding_type`, `reranker_type`, `keyword_extract_type`, `window_size`, `hybrid_llm_weights`。

**环境变量解析契约 —— 有序（V4 加强，P1）：**

多个字段共享同一个环境变量 —— 如 `openai_chat_api_key` 和 `openai_extract_api_key` 都从 `OPENAI_API_KEY` 读取。`_env_var_map` 必须将这些关系集中管理为**有序解析契约**。

| 规则 | 详情 |
|------|------|
| 字段级别名优先于提供商级/共享别名 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY`（对于 `openai_chat_api_key`） |
| 空字符串 env 不覆盖 YAML 非空值 | `KEY=` 不会清除 YAML 中的有效密钥 |
| 每个字段的 env 别名按优先级存储在 list/tuple 中 | 不是无序集合 —— 顺序决定解析结果 |
| 类型转换失败必须 fail-fast | 不允许静默退回字符串或默认值 |

**预期影响：** 约 44 条映射条目 + 约 8 条环境变量条目。从字段默认值中移除约 14 处 `os.environ.get()` 调用 —— 全部变为静态默认值。

---

### 任务 5：其余配置类映射 `[优先级: 中]`（依赖：任务 3）

**目标：** 将相同的嵌套映射模式应用于其他三个配置类。

**HugeGraphConfig**（`_config_section = "hugegraph"`）：12 个字段分为 4 个子节：

- `graph.*`：服务器连接（url, name, user, pwd, space）
- `query.*`：查询参数（limit_property, max_graph_path, max_graph_items, edge_limit_pre_label）
- `vector.*`：向量搜索（dis_threshold, topk_per_keyword）
- `rerank.*`：重排序（topk_return_results）

**AdminConfig**（`_config_section = "admin"`）：3 个字段位于 `login.*` 下（enable、user_token、admin_token）。注意：原计划中的 `config_reload_interval` 字段已移除，因为热加载推迟到未来阶段。

**IndexConfig**（`_config_section = "index"`）：7 个字段位于 `qdrant.*` 和 `milvus.*` 下。`cur_vector_index` 保持在顶级。同时修复 docstring（`"LLM settings"` → `"Vector index settings"`），移除 `os.environ.get()` 默认值。

---

### 任务 6：整体贯通 —— 初始化链与消费者 `[优先级: 中]`（依赖：任务 3、4、5）

**目标：** 将所有部分串联起来并更新每一个调用点。

| 文件 | 变更 | 目的 |
|------|------|------|
| `config/__init__.py` | 在配置单例之前初始化 ConfigManager。**V4：审计 PromptConfig 副作用** —— 确保 `config_prompt.yaml` 路径与 `config.yaml` 基准目录一致 | 单例必须在任何配置对象调用它之前存在 |
| `config/generate.py` | 4 × `generate_env()` → `generate_yaml()` | API 表面一致性 |
| `demo/rag_demo/configs_block.py` | 6 × `update_env()` → `update_config()`；移除 `dotenv_values` 导入；用配置对象属性替换直接 `.env` 读取。**V4：确保 `update_config()` 传入显式 patch dict** | 主要消费者 |
| `pyproject.toml` | 添加 `omegaconf~=2.3` | 新依赖 |
| `.gitignore` | **V4 收窄：** `hugegraph-llm/config.yaml`, `hugegraph-llm/config.yaml.bak`, `hugegraph-llm/.env.bak` | 敏感数据 + 迁移备份 |
| **V4 新增** `config.example.yaml` | 提交非敏感示例 YAML，占位值 —— **不含真实 token/key** | 用户入门：无需迁移即可了解嵌套 YAML 结构 |
| `config.md` | 重写文档以反映嵌套结构 + 优先级；文档说明配置修改需重启；**V4：说明 `config_prompt.yaml` 生命周期** | 面向用户的文档 |
| `README.md` | 移除 `.env` 引用，改为 `config.yaml` 说明 | 首要入门文档 |
| `Dockerfile` / `docker-compose.yml` | 非敏感配置通过挂载 `config.yaml` 或 ConfigMap；敏感配置通过 env/K8s Secret | 容器部署 |
| Helm values / templates | 更新 ConfigMap 引用；文档说明 env Secret 优先级高于 YAML | K8s 部署 |
| 示例启动脚本 | 更新为新的配置方式 | 开发者入门 |

---

### 任务 7：测试 `[优先级: 中]`（依赖：任务 3、4）

**目标：** 验证核心机制的正确性及真实场景行为。

#### 7.1 机制测试（往返/单例/正常路径/覆盖率审计）

| 测试 | 验证内容 |
|------|----------|
| 扁平↔嵌套往返 | `_nested_to_flat(_flat_to_nested(d, m), m) == d` 对包含已映射和未映射键的字典成立 |
| 环境变量优先级 | `os.environ` 值覆盖 YAML 值覆盖 pydantic 默认值 |
| ConfigManager 单例 | 两次 `ConfigManager()` 调用返回同一个实例 |
| `.env` → YAML 迁移 | 输入已知的 `.env` 产生预期的 `config.yaml` 结构 |
| **未映射字段审计（V4）** | 断言每个 config class 无不经审查的 unmapped field；**V4：断言 model-field-unmapped ≠ user-legacy-key —— 两项独立检查** |

#### 7.2 真实行为测试（回归防护）

| 测试 | 验证内容 |
|------|----------|
| os.environ 覆盖 YAML | 对同一字段，环境变量优先于 YAML 值 |
| os.environ 覆盖迁移的 .env | 即使 .env 有不同值，环境变量仍然胜出 |
| .env 迁移不写入 os.environ | 迁移后 `os.environ` 不被 .env 值污染 |
| 来自 env 的密钥不保存到 config.yaml | `save()` 排除来自 `os.environ` 的值 |
| **V4 P1：部分字段更新不泄露 env secret 到 YAML** | YAML 无 `api_key` + env 有 `OPENAI_API_KEY=env-secret` + 用户仅改 `language_model` → `config.yaml` 不含 `env-secret` |
| 字段级 env 别名优先级 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY`（对于 `openai_chat_api_key`） |
| 空 env 不覆盖 YAML 非空密钥 | `KEY=""` 不会覆盖有效的 YAML 值 |
| Phase1 扁平 YAML 迁移到嵌套 YAML | 类名节 + 全大写键 → 语义嵌套结构 |
| 损坏的 YAML 启动时快速失败 | 无效 `config.yaml` 抛出明确错误，不静默使用默认值 |
| 废弃包装器兼容性 | `update_env()` / `generate_env()` / `check_env()` 仍然可用 |
| Gradio 应用回调写入 YAML 而非 .env | UI 配置修改持久化到 `config.yaml`；**V4：验证 patch-based 写入** |
| 配置路径不依赖 CWD | ConfigManager 相对于固定基准解析 `config.yaml` 路径，而非 `os.getcwd()` |
| **只读 config.yaml 或只读目录（V4）** | 启动读取应可用；只有显式 save/update 才失败；**V4 扩展：同时覆盖 prompt YAML 只读场景** |
| **日志/错误/diff 中密钥脱敏（V4）** | 迁移失败、env 覆盖、save、check_config 输出中均不出现明文密钥 |
| **迁移失败不损坏 config.yaml（V4）** | 校验失败终止，不生成或覆盖 config.yaml |
| **多格式冲突解决（V4）** | Phase1 YAML + .env 共存：YAML 优先，.env 差异打 warning |
| **V4 新增：未知旧 key → _migration_unknown** | .env 中无 pydantic 字段对应的 key 归入 `_migration_unknown:` 节，不散落 YAML top-level |
| **V4 新增：PromptConfig 副作用** | `language=cn/en` + 已有 prompt yaml + 只读文件系统 |

#### 7.3 CI 集成（V4 —— 真实可执行路径）

每次 PR 必须在 CI 中运行的测试：

| CI 门禁 | 命令 |
|---------|------|
| 迁移 + env 优先级 + secret 不落盘 + 废弃包装器 + update_config patch | `cd hugegraph-llm && SKIP_EXTERNAL_SERVICES=true uv run pytest src/tests/config/ -k "migration or env or secret or deprecated or cwd or path or readonly or unmapped or coverage or mask or prompt" -v --tb=short` |
| Lint / 格式检查 | `uv run ruff format --check . && uv run ruff check .` |
| 配置路径 CWD 独立性 | 已包含在上述 `-k "cwd or path"` 中 |
| 只读文件系统场景（含 prompt YAML） | 已包含在上述 `-k "readonly or prompt"` 中 |
| 未映射字段审计（含 unknown→_migration_unknown） | 已包含在上述 `-k "unmapped or coverage"` 中 |
| 密钥脱敏验证 | 已包含在上述 `-k "mask or secret"` 中 |

---

### 任务 8：部署文档更新（V4 —— 真实路径验收清单） `[优先级: 中]`（依赖：任务 6）

**目标：** 以可验证的路径级清单更新所有部署入口。

**真实文件清单：**

| 文档 | 更新内容 | 验证 |
|------|----------|------|
| `README.md` | 移除 `.env` 引用；添加 `config.yaml` 配置说明 | `rg "\.env\|dotenv\|generate_env\|update_env\|check_env" README.md` → 必须返回零结果 |
| `hugegraph-llm/README.md` | 同样审计 | 同上 |
| `hugegraph-llm/config.md` | 嵌套结构 + 优先级 + 重启 + PromptConfig 生命周期 | 人工审核 |
| `docker/env.template` | 完整 `config.yaml` 模板含注释 | 已完成 |
| `docker/docker-compose.yml` | 添加 `config.yaml` 卷挂载；移除 `.env` 文件引用 | `rg "\.env" docker/` → 运行时 .env 引用为零 |
| `docker/docker-compose-network.yml` | 同样审计 | 同上 |
| `docker/docker-compose-llm.yml` | 更新注释 | 检查 secret 相关 env var 注释 |
| `docker/charts/hg-llm/values.yaml` | 更新 ConfigMap 使用嵌套 YAML；文档说明 env Secret 优先级 | 人工审核 |
| `docker/charts/hg-llm/Chart.yaml` | 审计 .env 引用 | `rg "\.env" docker/charts/` → 零 |
| `docker/charts/hg-llm/templates/*` | 移除 `.env` ConfigMap 引用；添加 `config.yaml` ConfigMap | `rg "\.env" docker/charts/hg-llm/templates/` → 零 |
| `.github/workflows/hugegraph-llm.yml` | **V4：config test gate 含真实可执行路径** | 验证 pytest 含正确 `-k` filter |
| 升级指南（新增） | 旧 `.env` 用户分步指南：备份 → 迁移 → 验证 → 回滚流程 | N/A |
| **V4 新增** `hugegraph-llm/config.example.yaml` | 提交非敏感示例含占位值和内联注释 | 人工审核 |

**全局验证命令：**

```bash
# 从 repo root 运行：所有部署相关路径必须返回零
rg "\.env|dotenv|generate_env|update_env|check_env" \
  README.md hugegraph-llm/README.md hugegraph-llm/config.md \
  docker/ .github/ \
  --ignore-case
# 预期：运行时 .env 引用为零
# （允许：描述 .env → YAML 迁移的迁移文档）
```

**部署文档的关键信息：**

- 非敏感配置：使用 `config.yaml`（挂载文件或 ConfigMap）。参考 `config.example.yaml` 了解结构。
- 敏感配置（密钥）：继续使用 env / K8s Secret，优先级高于 YAML
- 配置修改需重启；V1 不支持热加载
- 旧 `.env` 用户：按升级指南完成一次性迁移
- **V4 新增：** `config_prompt.yaml` 生命周期文档化 —— 用户可写（与 config.yaml 同基准目录）或只读资源

---

## 4. 未来阶段：热加载（不在 V1 MVP 中）

热加载被明确**排除在 V1 范围之外**。本节记录未来阶段的研究方向。

### 为什么不在 V1

OmegaConf 能很好地处理 YAML 的加载/合并/验证，但不提供 Spring/Log4j 式的自动运行时刷新。即使使用文件监控库（`watchfiles`/`watchdog`），检测文件变化只是第一步。真正的复杂性在于将变更安全地传播到运行中的运行时对象：

- 已创建的 LLM/Embedding 客户端不会自动重建
- HugeGraph/向量数据库连接参数通常在构造时固定
- 重载需要处理锁、回滚、验证失败和环境变量覆盖优先级
- 部分值被客户端捕获或固定在导入时，无法变更

### 可重载边界（供未来参考）

**以后可重载（简单值变更）：**

- 日志级别
- 简单数值阈值
- 非客户端功能开关

**需要重启（构造时捕获）：**

- LLM 提供商/API 地址/API 密钥
- 嵌入模型
- HugeGraph 连接参数
- 向量数据库连接参数
- 任何已被现有客户端或导入时常量捕获的字段

### 未来研究方向

- `Dynaconf fresh_vars` 是否适用于少量透读字段
- `watchfiles`/`watchdog` 是否适合作为显式重载触发器
- 哪些字段可安全重载 vs 哪些需要重启

---

## 5. 风险评估（V4 —— 契约加固 + PromptConfig 边界）

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| `__init__` 流程变更破坏下游导入 | 高 | 保留旧方法作为 Deprecated 别名；彻底搜索所有调用点（任务 1） |
| `_flat_to_nested_mapping` 中缺少条目 | 中 | **V4：强制字段分类审计** + **两类拆分**：model-field-unmapped → CI 失败；user-legacy-key → `_migration_unknown:` |
| YAML 文件损坏或不可读 | 高 | **启动时快速失败**，附带明确错误信息 —— 不静默回退到 pydantic 默认值。无效配置意味着进程不启动 |
| 未来重载：新 config.yaml 无效 | 中 | 在内存中保留最后已知正常配置；清晰暴露错误；不换入损坏的配置 |
| 环境变量类型强制转换失败 | 高 | **验证失败** —— 不静默地将环境变量值保留为字符串。类型不匹配意味着进程不启动 |
| **V4 P1：通过 `update_config()` 全量 dump 将 env secret 写回 config.yaml** | 高 | `update_config()` **仅接受显式 patch dict**；ConfigManager 追踪字段来源；`save()` 排除所有 `env` 来源字段；`update_section()` 拒绝 effective model 输入；**专项测试验证** |
| **敏感信息在日志/错误/diff 中泄露（V4）** | 高 | 字段名含 `api_key`/`token`/`password`/`pwd`/`secret` 的统一脱敏；错误信息显示字段路径和来源但不显示原值；`check_config()` / diff 输出仅显示 `***` |
| **V4 新增：PromptConfig 在只读部署中写入 package resource** | 中 | 将 `config_prompt.yaml` 归类为用户可写配置或只读资源；若可写，路径与 `config.yaml` 基准目录对齐；若只读，禁止启动时自动写入 |
| **迁移部分写入损坏的 config.yaml（V4）** | 高 | 无副作用校验通过 `model_validate`/`TypeAdapter`；校验失败终止，不触及 `config.yaml`；原子写入（写临时文件 + 重命名） |
| Phase 0/1 YAML 未自动检测 | 中 | 显式格式检测 + **V4 多格式冲突决策表**（任务 3.7）；不依赖 OmegaConf 猜测格式 |
| `.env` 被误认为持续配置源 | 中 | **V4：迁移后自动备份 `.env` → `.env.bak`**；`.env` 绝不加载到 `os.environ`；`.env`（仅迁移）与 `os.environ`（仅运行时）之间的清晰边界 |
| 配置路径依赖 CWD | 低 | 相对于固定基准目录解析 `config.yaml` 路径，而非 `os.getcwd()`；**V4：config_prompt.yaml 和 config.example.yaml 同理** |
| 环境变量别名解析不确定 | 中 | **V4：有序解析契约** —— 字段级 > 提供商级；存储为 list/tuple 非 set；空字符串不清除 YAML 值；类型不匹配 fail-fast |
| **V4 新增：部署文档引用过期路径** | 低 | **V4：真实路径验收清单**（任务 8）+ 验证 `rg` 命令 |

**核心原则：** 配置错误应尽可能早、尽可能大声地暴露。静默回退到默认值可能导致在生产环境中连接到错误的服务或使用错误的凭据。密钥绝不在任何输出渠道（文件、日志、错误、diff）中以明文出现。**V4 新增：配置写入路径必须基于 patch 而非全量 dump —— 单个非敏感字段变更不得携带 env secret 落盘。**

---

## 6. 需求覆盖

| 需求 | 覆盖方式 |
|------|----------|
| U9 — 接受仓库路径作为唯一输入 | 任务 1, 任务 2 |
| U10 — 从仓库自身配置推导约定 | 任务 2（扁平↔嵌套映射由类变量驱动） |
| U11 — 将输出写入指定路径 | 任务 3, 任务 6, 任务 8 |
| U13 — 不超过 `gh` CLI 的网络范围 | 整个方案（热加载推迟到未来阶段；V1 无文件监控守护线程） |

---

## 7. V1 范围总结

### V1 包含/排除清单

| 项目 | V1 状态 |
|------|---------|
| 嵌套语义化 `config.yaml`（OmegaConf） | ✅ 包含 |
| `.env` → 嵌套 YAML 迁移 | ✅ 包含 |
| Phase1 扁平 YAML → 嵌套 YAML 迁移 | ✅ 包含 |
| `os.environ` > `config.yaml` > pydantic 默认值 优先级 | ✅ 包含 |
| 环境变量密钥隔离（不写入 YAML） | ✅ 包含 |
| 废弃方法包装器（向后兼容） | ✅ 包含 |
| 配置修改需重启 | ✅ 包含（设计如此） |
| **映射覆盖率审计 + 字段分类（V4 加强）** | ✅ 包含 |
| **两类拆分：model-unmapped（CI 失败）vs user-legacy-key（_migration_unknown）（V4 新增）** | ✅ 包含 |
| **.env vs os.environ vs K8s Secret 边界（V4）** | ✅ 包含 |
| **`__init__` 不自动持久化（V4）** | ✅ 包含 |
| **Patch-based `update_config()` API —— 不全量 model dump（V4 新增）** | ✅ 包含 |
| **字段来源追踪：default / yaml / env / runtime_patch（V4 新增）** | ✅ 包含 |
| **无副作用迁移验证（V4）** | ✅ 包含 |
| **多格式冲突决策表（V4）** | ✅ 包含 |
| **有序环境变量解析契约（V4）** | ✅ 包含 |
| **完整敏感信息脱敏（V4）** | ✅ 包含 |
| **PromptConfig 边界分析（V4 新增）** | ✅ 包含 |
| **部署文档更新 + 真实路径清单（V4 加强）** | ✅ 包含 |
| **config.example.yaml（V4 新增）** | ✅ 包含 |
| **CI 门禁 + 真实可执行路径（V4 加强）** | ✅ 包含 |
| **只读场景测试含 prompt YAML（V4 加强）** | ✅ 包含 |
| 自动热加载 | ❌ 推迟到未来阶段 |
| 后台文件监控守护线程 | ❌ 推迟到未来阶段 |

### 强化契约（V4 —— 自 V3 加强）

| 优先级 | 契约 | V3→V4 变更 | 执行位置 |
|--------|------|------------|----------|
| P0 | `__init__` 不得将 env 覆盖值自动写回 YAML | 无变更（已是 P0） | 任务 3.3, §5 风险 |
| P0 | `.env`（仅迁移）、运行时 `os.environ`、K8s Secret 必须有硬边界 | 无变更（已是 P0） | 任务 2.4, §2 架构 |
| P0 | 环境变量别名解析必须有序：字段级 > 提供商级；空字符串不清除 YAML | 无变更（已是 P0） | 任务 4, 任务 7.2 |
| **V4 P1（新增）** | **`update_config()` 必须仅接受显式 patch dict —— 不全量 model dump；ConfigManager 必须追踪字段来源；`save()` 必须排除所有 env 来源值** | **V4 新增 —— 基于审阅反馈加固** | 任务 3.4, 任务 7.2, §5 风险 |
| P1 | 三格式迁移必须有冲突决策表 + 无副作用验证 | 无变更 | 任务 3.7 |
| P1 | 映射覆盖率必须审计：每个字段归类；CI 断言零未审查 unmapped | **V4：拆分为 model-unmapped（CI 失败）vs user-legacy（_migration_unknown）** | 任务 2.1, 任务 7.1, 任务 7.3 |
| P1 | 敏感字段必须在所有输出中脱敏：日志、错误、diff、check_config、**partial update_config()** | **V4 扩展：包含 partial update_config() 路径** | §5 风险, 任务 7.2 |
| **V4 P2（新增）** | **部署文档必须使用真实路径验收清单 + 验证 rg 命令** | **V4 新增 —— 从审阅 P2 反馈转换** | 任务 8 |
| **V4 P2（新增）** | **CI 门禁命令必须是仓库实际可执行路径（非占位符）** | **V4 新增 —— 从审阅 P2 反馈转换** | 任务 7.3 |
| **V4 P2（新增）** | **PromptConfig/config_prompt.yaml 副作用链必须被归类并文档化** | **V4 新增 —— 从审阅 P2 反馈转换** | §2 架构, 任务 6, §5 风险 |

---

## 附录：V3 → V4 变更追溯

| 飞书评论编号 | 问题 | V4 修改的章节 |
|-------------|------|--------------|
| P1 (inline) | `update_config()` 全量 dump 有 env secret 泄露风险 | §5 风险（新增风险行）, 任务 3.4（V4 新增 API 契约）, 任务 7.2（新增测试）, §7 强化契约（新增 P1 行） |
| P2 (inline) | PromptConfig/config_prompt.yaml 副作用 | §2 架构（新增 PromptConfig 子节）, 任务 1（扩展 grep 范围）, 任务 6（config/__init__.py 注释）, 任务 7.2（新增测试）, §5 风险（新增风险行） |
| P2 (inline) | CI 命令占位符路径 | 任务 7.3（真实可执行命令）, 任务 8（验证 grep） |
| P2 (inline) | 部署文档缺少真实路径清单 | 任务 8（真实路径清单 + 验证命令）, §7 强化契约（新增 P2） |
| P2 (inline) | 未知用户 key 与未映射模型字段混为一谈 | §2.1（两类拆分）, 任务 3.7（决策表）, 任务 7.2（新增测试）, §7 范围总结 |
| P2 (inline) | .gitignore 范围太宽 + 需要 config.example.yaml | 任务 6（.gitignore 收窄 + 新增示例文件）, 任务 8（config.example.yaml 条目） |
| P2 (title) | 标题可读性 | 文档标题 |
| 整体审阅 | 7.8/10，方向确认 | §0（V3 到 V4 变更汇总表）, §7（更新强化契约） |
