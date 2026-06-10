# Graph-AI 配置存储重构方案 V5

> 方案：.env → YAML → OmegaConf 嵌套配置迁移（V5 —— 基于飞书评论的全面修订）
>
> **关联 Issue：** https://github.com/apache/hugegraph-ai/issues/234
>
> **V4→V5 变更摘要**：V4 在飞书上收到 11 条评论，V5 全面整合：
> - `.env` 从"一次性迁移输入"重新定义为 **secret-only 文件**
> - 新增敏感字段分类表（可进 YAML vs 保留 secret）
> - 非 LLM 配置补充完整的 `_env_var_map`
> - `config_prompt.yaml` 选定唯一生命周期
> - 新增 API/operator 默认值审计任务
> - 字段来源追踪从 3 类细化为 4 类
> - `.env.bak` 安全策略
> - 二期内容（热加载等）已分离到独立章节

---

## 一、需求定义

### 1.1 核心目标

将 HugeGraph-AI 的配置系统从扁平的 `.env` / Phase1 flat YAML 升级为 OmegaConf 管理的**嵌套语义化 `config.yaml`**，同时保持 `.env` 作为 **secret-only 文件** 的角色。

### 1.2 功能需求

| ID | 需求 | 优先级 |
|----|------|--------|
| **F1** | 嵌套语义化 `config.yaml`：用户面向的配置使用语义节名（`llm`, `hugegraph`, `admin`, `index`）、小写键名、自然嵌套 | P0 |
| **F2** | `.env` 重新定义为 **secret-only 文件**：仅存储 API key、token、password 等敏感字段，非敏感配置全部迁移到 `config.yaml` | P0 |
| **F3** | 三层合并优先级：`os.environ` > `config.yaml` > pydantic 默认值 | P0 |
| **F4** | **敏感字段绝不写回 `config.yaml`**：env/secret 来源的值在任何写盘路径（`save()`, `update_config()`, 迁移）中均被排除 | P0 |
| **F5** | 自动迁移：从 Phase0 `.env` 或 Phase1 flat YAML 自动检测并迁移到 nested `config.yaml` | P0 |
| **F6** | 迁移时敏感字段分类：非敏感字段 → `config.yaml`，敏感字段保留在 `.env`（不写 YAML），用户被告知哪些保留在 `.env` | P0 |
| **F7** | 通过 `update_config()` 显式修改配置并持久化，仅接受 **patch dict**（非全量 dump） | P1 |
| **F8** | 废弃方法向后兼容：`update_env()`, `generate_env()`, `check_env()` 保留为 Deprecated wrapper | P1 |
| **F9** | 每个配置类必须声明 `_flat_to_nested_mapping` 和 `_env_var_map`，CI 强制检查覆盖率 | P1 |
| **F10** | 敏感信息脱敏：所有输出渠道（日志、错误、diff、`check_config()`）中的敏感字段显示为 `***` | P1 |
| **F11** | 配置修改需重启生效（热加载不在 V1 范围内） | 设计约束 |

### 1.3 非功能需求

| ID | 需求 | 优先级 |
|----|------|--------|
| **NF1** | **Fail-fast**：无效 config.yaml 在启动时报清晰错误，不静默回退默认值 | P0 |
| **NF2** | **环境变量类型转换失败 fail-fast**：类型不匹配时进程不启动 | P0 |
| **NF3** | **迁移不损坏文件**：校验失败不生成/覆盖 config.yaml，原子写入（写 temp + rename） | P0 |
| **NF4** | 配置路径不依赖 CWD：所有路径相对于固定基准目录解析 | P1 |
| **NF5** | 只读文件系统场景：启动读取可用，仅显式 save/update 失败 | P1 |
| **NF6** | `.env.bak` 安全策略：限制文件权限为 owner-readable，迁移日志脱敏 | P2 |

### 1.4 安全需求

| ID | 需求 | 优先级 |
|----|------|--------|
| **S1** | **两层配置分离**：`persisted_config`（仅 YAML 来源，可写盘）vs `effective_config`（含 env override，只读），硬边界 | P0 |
| **S2** | **Secret 不落盘**：`os.environ` / K8s Secret / `.env` 来源的敏感值绝不写入 `config.yaml` | P0 |
| **S3** | **Patch-based 写入**：`update_config()` 仅接受显式 patch dict，拒绝全量 model dump（防止 env secret 被连带写盘） | P0 |
| **S4** | `__init__` 不自动持久化：构造配置对象时不自动写回 YAML | P0 |
| **S5** | **敏感字段脱敏**：字段名含 `api_key`/`token`/`password`/`pwd`/`secret` 的统一脱敏 | P1 |
| **S6** | **`.env.bak` 权限**：限制 `0600`，迁移日志中不记录敏感字段名和值 | P2 |

### 1.5 迁移兼容性需求

| ID | 需求 | 优先级 |
|----|------|--------|
| **M1** | 支持三种格式自动检测：Phase0 `.env`、Phase1 flat YAML、Phase2 nested YAML（目标） | P0 |
| **M2** | 多格式冲突处理：Phase2 nested YAML 存在 → 直接加载；仅有旧格式 → 自动迁移；两者共存 → 以 YAML 为主，diff 打 warning | P0 |
| **M3** | 未知旧 key 保留到 `_migration_unknown:` 节，不散落 YAML top-level | P1 |
| **M4** | 迁移时**敏感字段分类**：`OPENAI_API_KEY`, `ADMIN_TOKEN`, `USER_TOKEN`, `GRAPH_PWD`, `QDRANT_API_KEY`, `MILVUS_PASSWORD` 等保留在 `.env`，不迁移到 `config.yaml` | P0 |
| **M5** | `.env.bak` 生成后限制文件权限，提示用户不要提交 | P2 |

---

## 二、技术方案

### 2.1 架构总览

```
config.yaml（嵌套，语义节名，小写键名）
  → OmegaConf（结构化加载/合并/保存）
  → ConfigManager（单例：所有配置操作的统一入口）
      ├── persisted_config:    仅来自 config.yaml（含显式 patch），可被 save()
      │                         不含 env override / .env secret
      └── effective_config:    pydantic 默认值 ← config.yaml ← os.environ
                               （运行时只读，永不写盘）
  → pydantic.BaseModel（不再加载 env-file；OmegaConf 接管）
  → 通过每个类的 _env_var_map 集中管理环境变量覆盖（有序解析）
```

### 2.2 核心架构决策

#### 2.2.1 两层配置分离 + 字段来源追踪

ConfigManager 将配置分为两层，并追踪每个字段的来源：

| 层 | 来源 | 可写 | 用途 |
|----|------|------|------|
| `persisted_config` | `config.yaml` + explicit_persisted_patch | `save()` 可写回 | 声明式非敏感配置 |
| `effective_config` | pydantic 默认值 ← YAML ← `os.environ` | 只读 | 运行时最终合并值 |

**V5 新增 —— 四类字段来源追踪**：

```python
_field_source: dict[str, Literal[
    "env_override",           # 来自 .env / os.environ / K8s Secret —— 永不持久化
    "effective_default",      # 来自 pydantic Field(default=...)，可用于生成示例，不是用户修改
    "explicit_persisted_patch", # 用户通过 UI/API 显式修改 —— 允许写入 YAML
    "runtime_only_patch"      # 只影响内存 —— 永不写入 YAML
]]
```

核心不变式：
- `save()` 只序列化 `persisted_config`
- `update_config({...})` 产生的 patch 标记为 `explicit_persisted_patch`
- `effective_config` 永远不 full dump 到 YAML
- env / secret 来源字段在所有写盘路径中排除

#### 2.2.2 `.env` 的重新定位：secret-only 文件

**V5 核心变更**：`.env` 不再被废弃，而是重新定义为 **secret-only 文件**。

| 来源 | 角色 | 是否参与 effective config？ | 是否可持久化到 YAML？ |
|------|------|---------------------------|----------------------|
| `.env`（secret-only） | **持久 secret 存储**（本地开发/部分服务端） | 是 —— 加载到 `os.environ` 后覆盖 YAML | **绝不**—— 仅存 secret |
| `os.environ` / K8s Secret | **运行时覆盖** | 是（最高优先级） | **绝不** |
| `config.yaml` | **非敏感配置主存储** | 是 | 是 |

**敏感字段分类表**：

| 可进 `config.yaml`（非敏感） | 保留在 `.env` / Secret（敏感） |
|------------------------------|-------------------------------|
| `OPENAI_BASE_URL`, `OPENAI_CHAT_API_BASE`, `OPENAI_EXTRACT_API_BASE` 等 | `OPENAI_API_KEY` |
| `GRAPH_URL`, `GRAPH_NAME` | `GRAPH_PWD` |
| `QDRANT_HOST`, `QDRANT_PORT` | `QDRANT_API_KEY` |
| `OLLAMA_HOST` | `MILVUS_PASSWORD` |
| `LITELLM_BASE_URL` | `ADMIN_TOKEN`, `USER_TOKEN` |
| `language`, `chat_llm_type`, `window_size` 等 | 任何含 `api_key`/`token`/`password`/`pwd`/`secret` 的字段 |

**`.env` 处理决策表**：

| 场景 | 行为 |
|------|------|
| 已存在 Phase2 nested `config.yaml` | 直接从 YAML 加载；**`.env` 仅作为 secret 覆盖源**（加载到 `os.environ` 但不迁移） |
| 仅存在 Phase1 flat `config.yaml` | 迁移到 nested YAML；非敏感 → `config.yaml`，检测到 `.env` 中的 secret 保留在 `.env` |
| 仅存在 `.env` | **敏感分类迁移**：非敏感 → `config.yaml`，敏感字段 → 保留在 `.env` |
| Phase1 YAML + `.env` 共存 | 以 YAML 为主，`.env` 提供 secret 覆盖，差异打 warning |
| 运行时 | `.env` 加载到 `os.environ` 参与 effective config；**绝不写回** `.env` 或 `config.yaml` |

#### 2.2.3 `.env.bak` 安全策略

- 迁移后自动生成 `.env.bak` 备份
- 文件权限设为 `0600`（owner-readable only）
- 每次迁移时如果已存在 `.env.bak`，生成带时间戳的新文件（不覆盖旧的）
- 迁移日志中脱敏敏感字段名和值
- 迁移失败时保留原始 `.env` 不变，不生成 `.bak`
- `.gitignore` 中同时忽略 `.env` 和 `.env.bak`

### 2.3 核心组件设计

#### 2.3.1 扁平↔嵌套转换

pydantic 模型使用扁平字段名（`openai_chat_api_key`），用户面向嵌套 YAML（`openai.chat.api_key`）。每个配置类声明 `_flat_to_nested_mapping` 桥接二者：

- `_flat_to_nested()`: pydantic 扁平字典 → 嵌套 YAML 字典（写 config.yaml）
- `_nested_to_flat()`: 嵌套 YAML 字典 → pydantic 扁平字典（读 config.yaml）

必须满足往返属性：`nested_to_flat(flat_to_nested(d)) == d`

**V5 强化 —— 未知字段分两类**：

| 类别 | 定义 | 行为 |
|------|------|------|
| **模型字段未映射** | pydantic model field 无映射且未归类为 `intentional top-level` / `ignored-deprecated` | **CI 失败** |
| **用户旧 key** | `.env` / Phase1 YAML 中发现的无法匹配任何 pydantic field 的 key | 保留到 `_migration_unknown:` 节 + WARNING |

#### 2.3.2 ConfigManager 单例

| 方法 | 职责 |
|------|------|
| `__init__` | 加载 `config.yaml`（或从旧格式迁移）；加载 `.env` 作为 secret 覆盖 |
| `get_section_with_env_override()` | 返回某配置节的生效配置（扁平字典），含 env override |
| `update_section()` | **V5 加固**：仅接受 `ExplicitPersistedPatch`（标记来源为 `explicit_persisted_patch`）；拒绝任何来源为 `env_override` / `runtime_only_patch` 的值 |
| `save()` | 将 `persisted_config` 树持久化到 `config.yaml`。**排除所有来源为 `env_override` / `runtime_only_patch` 的字段** |
| `_migrate_from_legacy()` | 统一迁移入口：自动检测格式 → 敏感分类 → 非敏感写 `config.yaml`，敏感保留 `.env` → 原子写盘 |

#### 2.3.3 环境变量覆盖设计（有序解析契约）

每个字段的 `_env_var_map` 是**有序 list/tuple**（非 set），顺序决定解析优先级：

```python
_env_var_map = {
    "openai_chat_api_key": ["OPENAI_CHAT_API_KEY", "OPENAI_API_KEY"],
    # 字段级 > 共享级
}
```

| 规则 | 详情 |
|------|------|
| 字段级别名优先于提供商级/共享别名 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` |
| 空字符串不覆盖 YAML 非空值 | `KEY=` 不清除有效密钥 |
| 类型转换失败 fail-fast | `TypeAdapter.validate_python()` 失败 → 进程不启动 |

**V5 — 所有配置类必须声明 `_env_var_map`**：

| 配置类 | 关键环境变量 |
|--------|-------------|
| LLMConfig | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_HOST`, `LITELLM_BASE_URL` 等 |
| HugeGraphConfig | `GRAPH_PWD` |
| AdminConfig | `ADMIN_TOKEN`, `USER_TOKEN` |
| IndexConfig | `QDRANT_API_KEY`, `MILVUS_PASSWORD` |

旧 env 名称全集必须被新 `_env_var_map` 覆盖；未覆盖的旧 env 名称在 CI 中 fail。

#### 2.3.4 `update_config()` 加固 API

```python
# 正确用法 —— 显式 patch dict
llm_config.update_config({"openai_chat_language_model": "gpt-4.1"})

# 错误 —— 全量 dump（被 ConfigManager 拒绝）
llm_config.update_config(llm_config.model_dump())
```

ConfigManager 在 `update_section()` 中检查：只接受 `explicit_persisted_patch` 来源的值，拒绝 `env_override` / `runtime_only_patch` / `effective_default`。

#### 2.3.5 PromptConfig / `config_prompt.yaml` 生命周期

**V5 单一决策**：

- `config_prompt.yaml` 是**用户可写配置**（不是只读 package resource）
- 路径与 `config.yaml` 使用同一个 config base dir
- Package 内的 prompt YAML 只作为**默认模板**（`resources/demo/config_prompt.yaml`）
- 启动时：如果 config base dir 下没有 `config_prompt.yaml`，从模板复制一份过去
- 启动时**不写回 package resource**
- 只读配置目录 → fail-fast

### 2.4 迁移策略

#### 2.4.1 三格式检测

| 格式 | 来源 | 特征 |
|------|------|------|
| Phase0 | `.env` | `ALL_CAPS` 扁平键，`python-dotenv` 加载 |
| Phase1 | `config.yaml`（扁平） | 类名节名（`LLMConfig`, `AdminConfig`），`ALL_CAPS` 键 |
| Phase2（目标）| `config.yaml`（嵌套） | 语义节名（`llm`, `hugegraph`），小写键 |

#### 2.4.2 迁移流程（含敏感字段分类）

```text
检测旧格式
  → 规范化为扁平 pydantic 字段字典
  → 用 model_validate / TypeAdapter 做纯校验
    （无 __init__、无单例初始化、无 env override、无 write-back）
  → IF 校验失败：终止并报清晰错误 —— 不生成或覆盖任何文件
  → IF 校验通过：执行敏感字段分类
    ├── 非敏感字段 → 嵌套 YAML → config.yaml
    └── 敏感字段 → 保留在 .env（如不存在则生成含注释的 .env 模板）
  → 已知字段 → 嵌套节
  → 未知旧 key → _migration_unknown 节
  → 写 config.yaml.bak（备份，0600 权限）
  → 原子替换 config.yaml
  → 生成 .env.bak（备份原始 .env，0600 权限）
  → 输出迁移报告（含敏感字段脱敏列表）
```

#### 2.4.3 无副作用验证契约

迁移验证不得复用 `BaseConfig.__init__`（会触发单例初始化、env override、YAML 写回、PromptConfig 初始化等副作用）。改用 `model_validate` / `TypeAdapter`。

### 2.5 `configs_block.py` role 级联逻辑（V5 新增）

原有逻辑检查 `.env` 文件存在性来判断用户是否显式配置过 extract/text2gql 的 key。迁移后使用 source tracking 表达：

- 如果 extract/text2gql 对应字段来源是 `effective_default` → 允许从 chat 级联 fallback
- 如果字段来源是 YAML 或 explicit_persisted_patch → 不自动覆盖
- 如果字段来源是 env_override → 需要明确是否允许级联，避免覆盖 secret-only 配置

---

## 三、TODO（实现任务）

### 3.1 任务总览

| # | 任务 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | 全量依赖扫描 + 消费面审计 | P0 | - |
| 2 | 核心基础设施（转换函数 + ConfigManager） | P0 | 1 |
| 3 | BaseConfig 基类重构 | P0 | 2 |
| 4 | LLM 配置嵌套映射 | P0 | 3 |
| 5 | 其余配置类映射（含 _env_var_map） | P0 | 3 |
| 6 | API/operator 默认值审计与迁移 | P1 | 3, 4, 5 |
| 7 | 整体贯通 —— 初始化链与消费者 | P1 | 3, 4, 5, 6 |
| 8 | 测试 | P1 | 3, 4, 5 |
| 9 | 部署文档更新 | P1 | 7 |

---

### 任务 1：全量依赖扫描 + 消费面审计 `[P0]`

**目标**：映射每一行涉及 `.env`、`dotenv`、`update_env`、`check_env`、`generate_env` 的代码，以及所有**配置消费面**。

**扫描内容**：

- Grep：`dotenv`, `update_env`, `check_env`, `generate_env`, `set_key`, `dotenv_values`
- Grep：`PromptConfig`, `ensure_yaml_file_exists`, `config_prompt.yaml` 引用
- **V5 新增**：扫描 API request model 默认值、`/config/*` API 写入路径、operator 构造默认值、node 内部 fallback literal、import-time 绑定的配置值

**产出**：
- 命中清单：文件、行号、当前行为、需要的变更
- 敏感字段名列表（含 `api_key`/`token`/`password`/`pwd`/`secret`）
- 消费面覆盖矩阵

---

### 任务 2：核心基础设施 `[P0]`

#### 2.1 扁平↔嵌套转换函数

- 两个纯函数，往返可验证
- 覆盖率强制契约：每个 config model 字段必须归类（`mapped` / `intentional top-level` / `ignored-deprecated`）
- **V5**：unknown 分两类：model-unmapped → CI fail；user-legacy-key → `_migration_unknown:`
- 敏感字段识别函数：`is_sensitive_field(field_name) -> bool`

#### 2.2 ConfigManager 单例

- 两层配置分离（persisted vs effective）
- **V5**：四类字段来源追踪（`env_override`, `effective_default`, `explicit_persisted_patch`, `runtime_only_patch`）
- **V5**：`update_section()` 只接受 `explicit_persisted_patch`
- **V5**：`save()` 排除所有 `env_override` / `runtime_only_patch` 来源字段
- 统一迁移入口：`_migrate_from_legacy()`（自动检测格式 + 敏感分类）
- **V5**：`.env.bak` 安全策略（`0600` 权限、带时间戳备份、迁移日志脱敏）

#### 2.3 环境变量覆盖设计

- `_env_var_map` 使用有序 list/tuple
- `TypeAdapter.validate_python()` 做类型转换
- 空字符串不覆盖 YAML 非空值
- 类型转换失败 fail-fast

#### 2.4 `.env` 处理策略（V5 secret-only 语义）

- `.env` 作为 secret-only 文件，加载到 `os.environ`
- 敏感字段永不迁移到 `config.yaml`
- 迁移时只迁移非敏感字段
- 所有运行时场景：`.env` secret 参与 effective config 但不落盘

---

### 任务 3：BaseConfig 基类重构 `[P0]`

- `BaseSettings → BaseModel`
- 类变量契约：`_config_section`, `_flat_to_nested_mapping`, `_env_var_map`（**所有配置类必须**）
- `__init__` 不自动持久化
- **V5**：`update_config()` 仅接受显式 patch dict
- **V5**：`update_section()` 检查字段来源，拒绝 env 来源值
- 方法迁移：`update_env()` → `update_config()`, `generate_env()` → `generate_yaml()`, `check_env()` → `check_config()`
- 废弃方法包装器保留
- **V5**：敏感字段分类辅助：`_sensitive_fields: ClassVar[set[str]]`
- 三格式迁移路径（含敏感字段分类）

---

### 任务 4：LLM 配置嵌套映射 `[P0]`

- LLMConfig ~55 字段按 提供商 × 角色 嵌套
- ~44 映射条目 + ~8 环境变量条目
- 顶级字段：`language`, `chat_llm_type`, `extract_llm_type` 等
- 有序环境变量解析契约
- **V5**：LLMConfig 的 `_env_var_map` 需覆盖所有提供商/角色组合的旧 env 名称
- 移除 ~14 处 `os.environ.get()` 调用

---

### 任务 5：其余配置类映射（含完整 `_env_var_map`）`[P0]`

**V5 强化**：每个配置类都必须声明 `_env_var_map`。

**HugeGraphConfig**：12 字段 → `graph.*`, `query.*`, `vector.*`, `rerank.*`
- `_env_var_map` 覆盖：`GRAPH_PWD`

**AdminConfig**：3 字段 → `login.*`
- `_env_var_map` 覆盖：`ADMIN_TOKEN`, `USER_TOKEN`

**IndexConfig**：7 字段 → `qdrant.*`, `milvus.*`, 顶级 `cur_vector_index`
- `_env_var_map` 覆盖：`QDRANT_API_KEY`, `MILVUS_PASSWORD`
- 修复 docstring：`"LLM settings"` → `"Vector index settings"`

**CI 验收**：旧 env 名称全集必须被新 `_env_var_map` 覆盖；未覆盖的在 CI 中 fail。

---

### 任务 6：API/operator 默认值审计与迁移 `[P1]` **（V5 新增）**

**目标**：审计配置消费面，确保 YAML 中的配置、API 默认值、OpenAPI schema、operator 构造默认值一致。

**审计清单**：

| 消费面 | 审计内容 |
|--------|----------|
| API request model | `Field(default=...)` 是否与 `config.yaml` 默认值一致 |
| `/config/*` API | 写路径是否使用 `update_config()` patch-based API |
| Operator 构造 | 是否在 `__init__` 中固化了旧配置常量 |
| Node 内部 literal | fallback 值是否为真正合理的默认值（非历史残留） |
| Import-time 绑定 | 是否有在 import 时读配置的代码（应在运行时读） |
| OpenAPI schema | 默认值展示是否与 YAML effective config 一致 |

**产出**：
- 默认值一致性报告
- 不一致项的修复 PRs
- 非配置项明确标记（不纳入配置管理的 literal）

---

### 任务 7：整体贯通 —— 初始化链与消费者 `[P1]`

| 文件 | 变更 | 目的 |
|------|------|------|
| `config/__init__.py` | 在配置单例之前初始化 ConfigManager；**V5**：PromptConfig 使用 config base dir | ConfigManager 先于配置对象存在 |
| `config/generate.py` | 4 × `generate_env()` → `generate_yaml()` | API 一致性 |
| `demo/rag_demo/configs_block.py` | 6 × `update_env()` → `update_config()`（patch dict）；**V5**：role 级联逻辑使用 source tracking 重写 | 主要消费者 |
| `pyproject.toml` | 添加 `omegaconf~=2.3` | 新依赖 |
| `.gitignore` | **V5**：`hugegraph-llm/config.yaml`, `hugegraph-llm/config.yaml.bak`, `hugegraph-llm/.env`（secret 不应提交）, `hugegraph-llm/.env.bak` | 敏感数据防护 |
| **V5** `config.example.yaml` | 提交非敏感示例 YAML（占位值，不含真实 token/key）；标注哪些字段应来自 `.env`/env | 用户入门 |
| `config.md` | 嵌套结构 + 优先级 + `.env`=secret-only 语义 + `config_prompt.yaml` 生命周期 | 用户文档 |
| `README.md` | 移除 `.env` 作为通用配置的引用；改为 `config.yaml` + secret-only `.env` | 入门文档 |
| `Dockerfile` / Compose | `config.yaml` 卷挂载；`.env` 仅 secret；区分 compose `.env` 与 app secret `.env` | 容器部署 |

**V5 `configs_block.py` role 级联逻辑修改**：

旧逻辑基于 `.env` 文件存在性判断。新逻辑使用 source tracking：
1. extract/text2gql 字段来源是 `effective_default` → 允许从 chat 级联
2. 字段来源是 YAML 或 `explicit_persisted_patch` → 不覆盖
3. 字段来源是 `env_override` → 不级联，保护 secret-only 配置

---

### 任务 8：测试 `[P1]`

#### 8.1 机制测试

| 测试 | 验证内容 |
|------|----------|
| 扁平↔嵌套往返 | `round_trip(d) == d` |
| 环境变量优先级 | env > YAML > 默认值 |
| ConfigManager 单例 | 同一实例 |
| 未映射字段审计 | 每个 config class 无不经审查的 unmapped field |

#### 8.2 真实行为测试（V5 按 secret-only 语义补齐）

| 测试 | V5 要求 |
|------|--------|
| os.environ 覆盖 YAML | env 值优先 |
| 旧 `.env` 中非敏感字段迁移到 `config.yaml` | **V5 新增** |
| 旧 `.env` 中敏感字段保留在 `.env`，不进入 `config.yaml` | **V5 新增** |
| `.env` 中 secret 加载到 `os.environ` 后能覆盖 YAML | **V5 新增** |
| `.env` 迁移不污染 `os.environ`（非 secret 字段） | 环境隔离 |
| 来自 env 的 secret 不保存到 `config.yaml` | secret 隔离 |
| **V5**：`update_config()` 修改非敏感字段时，不把 env secret 写入 YAML | Patch 安全 |
| 字段级 env 别名优先级 | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` |
| 空 env 不覆盖 YAML 非空密钥 | 空字符串安全 |
| Phase1 扁平 YAML 迁移 | 完整迁移 |
| 所有旧 env 名称被 `_env_var_map` 覆盖 | **V5 新增** |
| 损坏 YAML fail-fast | 不静默回退 |
| 废弃包装器兼容 | 向后兼容 |
| Gradio 应用回调写入 YAML（patch-based）| UI 持久化 |
| 配置路径不依赖 CWD | 路径稳定性 |
| 只读 `config.yaml` / 目录 + prompt YAML 只读 | 只读场景 |
| 密钥脱敏验证 | 所有输出渠道 |
| 迁移失败不损坏 config.yaml | 原子写入 |
| 未知旧 key → `_migration_unknown:` | 迁移完整性 |
| PromptConfig 副作用 | `language=cn/en` × 已有 prompt yaml × 只读 FS |
| **V5**：`.env.bak` 文件权限为 0600 | 备份安全 |
| **V5**：新增 config tests 标记为 `unit` 或 `contract`，被现有 CI 收到 | CI 覆盖 |

#### 8.3 CI 集成

```bash
# CI 门禁（V5 真实可执行命令）
cd hugegraph-llm && SKIP_EXTERNAL_SERVICES=true uv run pytest src/tests/config/ \
  -k "migration or env or secret or deprecated or cwd or path or readonly or unmapped or coverage or mask or prompt or backup or legacy_env" \
  -v --tb=short

# Lint
uv run ruff format --check . && uv run ruff check .

# 旧 env 名称覆盖审计
pytest hugegraph-llm/tests/ -k "legacy_env_coverage"
```

---

### 任务 9：部署文档更新 `[P1]`

**V5 核心区分**：三种不同的 `.env` 语义

| 类型 | 用途 | 是否保留 |
|------|------|----------|
| **Secret `.env`** | `hugegraph-llm` 的 API key / token / password | ✅ 保留（secret-only） |
| **Docker Compose `.env`** | `PROJECT_PATH` 等 compose 变量 | ✅ 保留（compose 基础设施） |
| **旧通用 `.env`** | 包含 `GRAPH_URL`、`QDRANT_HOST` 等非敏感配置 | ❌ 迁移到 `config.yaml` |

**真实文件路径清单**：

| 文件 | 更新内容 | 验证 |
|------|----------|------|
| `README.md` | 移除通用 `.env` 引用；说明 `config.yaml` + secret-only `.env` | `rg "\.env\|dotenv" README.md` → 仅 secret-only 描述 |
| `hugegraph-llm/README.md` | 同上 | 同上 |
| `hugegraph-llm/config.md` | 嵌套结构 + 优先级 + secret-only `.env` + PromptConfig 生命周期 | 人工审核 |
| `docker/env.template` | 完整 `config.yaml` 模板含注释；标注 `# secret: use .env` | 已完成 |
| `docker/docker-compose-llm.yml` | `config.yaml` 卷挂载；保留 secret env_file | `rg "\.env" docker/` → 仅 compose/secret `.env` |
| `docker/docker-compose-network.yml` | 同上 | 同上 |
| `docker/charts/hg-llm/values.yaml` | 更新 ConfigMap 为嵌套 YAML；说明 env Secret 优先级 | 人工审核 |
| `docker/charts/hg-llm/templates/*` | 移除通用 `.env` ConfigMap；添加 `config.yaml` ConfigMap | 确认 |
| `.github/workflows/hugegraph-llm.yml` | config test gate 含真实可执行路径 | 验证 pytest `-k` filter |
| 升级指南（新增） | 旧 `.env` → 新体系的迁移步骤（含敏感字段分类说明） | N/A |
| `hugegraph-llm/config.example.yaml` | 非敏感示例；标注 `# secret fields: keep in .env` | 人工审核 |

---

## 四、强化契约汇总（V5）

| 优先级 | 契约 | 出处（V4→V5 变更） |
|--------|------|-------------------|
| **P0** | `.env` 重新定义为 **secret-only 文件** | **V5 新增** —— 飞书评论 #2, #3 |
| **P0** | 迁移时执行**敏感字段分类**：非敏感 → YAML，敏感保留在 `.env` | **V5 新增** —— 飞书评论 #3 |
| **P0** | `__init__` 不自动持久化 env override 值到 YAML | 无变更 |
| **P0** | `.env`（secret-only）、运行时 `os.environ`、K8s Secret 硬边界 | 强化 |
| **P0** | env 别名解析有序：字段级 > 提供商级；空字符串不清除 YAML | 无变更 |
| **P1** | `update_config()` 仅接受显式 patch dict | 无变更 |
| **P1** | 字段来源追踪为 4 类（`env_override`, `effective_default`, `explicit_persisted_patch`, `runtime_only_patch`） | **V5 细化** —— 飞书评论 #7 |
| **P1** | 所有配置类必须声明 `_env_var_map`（含 HugeGraphConfig, AdminConfig, IndexConfig） | **V5 新增** —— 飞书评论 #4 |
| **P1** | 映射覆盖率审计 + 两类拆分（model-unmapped vs user-legacy） | 无变更 |
| **P1** | `config_prompt.yaml` 单一生命周期决策：用户可写配置，与 config.yaml 同基准目录 | **V5 确定** —— 飞书评论 #5 |
| **P1** | API/operator 默认值与 YAML effective config 一致性审计 | **V5 新增** —— 飞书评论 #6 |
| **P1** | `configs_block.py` role 级联逻辑使用 source tracking | **V5 新增** —— 飞书评论 #8 |
| **P1** | 敏感字段在所有输出渠道脱敏 | 无变更 |
| **P2** | `.env.bak` 安全策略：0600 权限、时间戳备份、日志脱敏 | **V5 新增** —— 飞书评论 #11 |
| **P2** | 部署文档区分 secret `.env` vs compose `.env` vs 旧通用 `.env` | **V5 新增** —— 飞书评论 #10 |
| **P2** | CI 测试按 `.env = secret-only` 语义补齐 | **V5 新增** —— 飞书评论 #9 |
| **P2** | 部署文档使用真实文件路径清单 | 无变更 |
| **P2** | CI 门禁使用真实可执行路径 | 无变更 |

---

## 五、V1 范围总结

### V1 包含

| 项目 | 状态 |
|------|------|
| 嵌套语义化 `config.yaml`（OmegaConf） | ✅ |
| `.env` 重新定义为 **secret-only 文件** | ✅ **V5 新增** |
| 敏感字段分类迁移（非敏感 → YAML，敏感保留 `.env`） | ✅ **V5 新增** |
| Phase0 `.env` / Phase1 flat YAML → nested YAML 迁移 | ✅ |
| `os.environ` > `config.yaml` > pydantic 默认值 优先级 | ✅ |
| 环境变量 secret 隔离（不写入 YAML） | ✅ |
| 四类字段来源追踪 | ✅ **V5 新增** |
| Patch-based `update_config()` API | ✅ |
| 所有配置类 `_env_var_map`（含非 LLM 配置） | ✅ **V5 新增** |
| 废弃方法包装器（向后兼容） | ✅ |
| PromptConfig 单一生命周期决策 | ✅ **V5 确定** |
| API/operator 默认值审计 | ✅ **V5 新增** |
| `configs_block.py` source-tracking 级联逻辑 | ✅ **V5 新增** |
| `.env.bak` 安全策略（0600 + 时间戳 + 脱敏） | ✅ **V5 新增** |
| `config.example.yaml` | ✅ |
| 映射覆盖率审计 + unknown 分两类 | ✅ |
| `.env` vs `os.environ` vs K8s Secret 边界 | ✅ |
| `__init__` 不自动持久化 | ✅ |
| 无副作用迁移验证 | ✅ |
| 多格式冲突决策表 | ✅ |
| 有序环境变量解析契约 | ✅ |
| 完整敏感信息脱敏 | ✅ |
| 部署文档更新 + 三种 `.env` 语义区分 | ✅ **V5 新增** |
| CI 门禁 + secret-only `.env` 测试 | ✅ **V5 新增** |
| 只读场景测试含 prompt YAML | ✅ |

### V1 排除（分离到二期）

| 项目 | 状态 |
|------|------|
| 自动热加载（hot-reload） | ❌ → 二期 |
| 后台文件监控守护线程 | ❌ → 二期 |
| 运行时配置变更不重启 | ❌ → 二期 |
| `watchfiles`/`watchdog` 集成 | ❌ → 二期 |
| Dynaconf `fresh_vars` 透读字段 | ❌ → 二期 |
| Reloadability 边界实现 | ❌ → 二期 |

---

## 六、验收标准汇总

> 回答"V1 做完，怎么判断是否成功"。以下验收条件覆盖功能、安全、测试、部署四个维度，每项均可在 PR 合并前独立验证。

### 6.1 配置功能验收

| # | 验收项 | 验证方式 |
|---|--------|---------|
| AC-F1 | `config.yaml` 使用小写键名、语义节名（`llm`/`hugegraph`/`admin`/`index`），LLM 按 provider→role 嵌套 | 人工审核生成的 config.yaml |
| AC-F2 | `.env` 中 API key/token/password 被识别为敏感字段，迁移后保留在 `.env`，不进入 `config.yaml` | 测试 `test_migration_sensitive_fields_stay_in_env` |
| AC-F3 | `os.environ` 值覆盖 YAML 值覆盖 pydantic 默认值 | 测试 `test_env_priority` |
| AC-F4 | 三种旧格式可自动检测并迁移：Phase0 `.env`、Phase1 flat YAML、两者共存 | 测试 `test_multi_format_migration` |
| AC-F5 | `update_config({"key": "val"})` patch dict 可正常工作 | 测试 `test_update_config_patch` |
| AC-F6 | `update_env()` / `generate_env()` / `check_env()` 废弃方法仍可调用并输出 DeprecationWarning | 测试 `test_deprecated_wrappers` |
| AC-F7 | `config.example.yaml` 文件存在，不含真实 token/key，标注 `# secret fields: keep in .env` | 人工审核 + CI 检查 |

### 6.2 安全验收

| # | 验收项 | 验证方式 |
|---|--------|---------|
| AC-S1 | `save()` 产出的 `config.yaml` 不含任何 `api_key` / `token` / `password` / `pwd` / `secret` 值的明文字段 | 测试 `test_secret_not_in_yaml` |
| AC-S2 | `update_config()` 修改非敏感字段后，env 来源的 secret 不被连带写入 YAML | 测试 `test_partial_update_no_secret_leak` |
| AC-S3 | `check_config()` 的输出中，敏感字段位置显示 `***` 或 `changed`/`not changed`，无明文 | 测试 `test_secret_masking` |
| AC-S4 | `__init__` 构造配置对象时不触发 YAML 写盘 | 测试 `test_init_no_auto_persist` |
| AC-S5 | `.env.bak` 文件权限为 `0600`；迁移日志不含敏感字段明文 | 测试 `test_env_bak_permission` |
| AC-S6 | 损坏的 `config.yaml` 在启动时 fail-fast，不静默回退默认值 | 测试 `test_corrupt_yaml_fail_fast` |

### 6.3 测试与 CI 验收

| # | 验收项 | 验证方式 |
|---|--------|---------|
| AC-T1 | `pytest src/tests/config/ -k "migration or env or secret or deprecated or cwd or path or readonly or unmapped or coverage or mask or prompt or backup or legacy_env"` 全部通过 | CI 门禁 |
| AC-T2 | `ruff format --check . && ruff check .` 通过 | CI 门禁 |
| AC-T3 | 每个 config class 的 `_flat_to_nested_mapping` 覆盖所有字段（除 `intentional top-level` / `ignored-deprecated`） | CI unmapped audit |
| AC-T4 | 每个 config class 的 `_env_var_map` 覆盖所有旧 env 名称 | CI legacy_env_coverage |
| AC-T5 | `config.yaml` 路径不依赖 CWD——换目录启动，配置加载结果一致 | 测试 `test_cwd_independence` |

### 6.4 部署验收

| # | 验收项 | 验证方式 |
|---|--------|---------|
| AC-D1 | `README.md` 中 `rg "\.env\|dotenv\|generate_env\|update_env\|check_env"` 仅返回 secret-only `.env` 描述，无通用 `.env` 配置指引 | CI grep gate |
| AC-D2 | `docker/` 下 compose 文件有 `config.yaml` 卷挂载，`.env` 引用仅限 compose 基础设施变量和 secret env_file | 人工审核 |
| AC-D3 | `docker/charts/` 下 Helm template 不含 `.env` ConfigMap 引用 | CI grep gate |
| AC-D4 | 升级指南文档存在，覆盖：备份 → 迁移 → 验证 → 回滚 四步 | 人工审核 |

---

## 七、时间线与里程碑

### 7.1 里程碑总览

```
M1 ──────── M2 ──────── M3 ──────── M4 ──────── M5
ConfigManager  LLMConfig  全部Config   消费者贯通   CI + 文档
可用          迁移完成    迁移完成     集成验证     交付就绪
```

| 里程碑 | 含义 | 出口条件 | 预计任务 |
|--------|------|----------|---------|
| **M1** | ConfigManager 核心可用 | 扁平↔嵌套转换函数 + ConfigManager 单例 + 两层分离 + 字段来源追踪通过单元测试 | 任务 1, 2 |
| **M2** | LLMConfig 迁移完成 | LLMConfig 全部 ~55 字段的 `_flat_to_nested_mapping` 和 `_env_var_map` 覆盖，round-trip 测试通过 | 任务 3, 4 |
| **M3** | 全部配置类迁移完成 | HugeGraphConfig / AdminConfig / IndexConfig 嵌套映射 + `_env_var_map` 完成，unmapped audit CI 通过 | 任务 5, 6 |
| **M4** | 消费者贯通 | `configs_block.py` / `config/__init__.py` / `generate.py` 全部接入新系统，旧方法 Deprecated wrapper 可用，Gradio UI 写 YAML 验证通过 | 任务 7 |
| **M5** | CI + 文档交付就绪 | 全部测试通过 CI 门禁，部署文档更新完成，升级指南就绪，`config.example.yaml` 提交 | 任务 8, 9 |

### 7.2 关键路径

```
任务1 (扫描) ──→ 任务2 (基础设施) ──→ 任务3 (基类) ──┬──→ 任务4 (LLM)
                                                     │
                                                     ├──→ 任务5 (其他配置)
                                                     │
                                                     └──→ 任务6 (审计) ──→ 任务7 (贯通) ──→ 任务8 (测试) ──→ 任务9 (文档)
```

任务 4 和任务 5 可并行（同依赖任务 3）。任务 6 可与 4/5 并行（依赖任务 3 但数据独立）。

### 7.3 风险缓冲

- 任务 4（LLMConfig ~55 字段映射）为最大不确定性——字段多、env alias 交叉。建议先做 **M2** 的 LLMConfig，验证模式正确后再铺开到任务 5
- 任务 8（测试）如果发现合约级缺陷（如 env secret 落盘），可能回溯修改任务 2/3。测试用例应**先在 M2 就并行编写**，不要等到 M4 再开始
- 每个里程碑出口设置硬性 CI 门禁，避免进度错觉

---

## 八、回滚方案

### 8.1 回滚原则

- 迁移过程**不删除原始 `.env`**，只生成 `.env.bak` 副本
- 迁移过程**写入前先备份** `config.yaml` → `config.yaml.bak`
- 回滚路径始终保持可达：用户始终可以用 `.env.bak` 或 `config.yaml.bak` 恢复

### 8.2 场景与操作

#### 场景 A：迁移后应用无法启动（config.yaml 校验失败）

**现象**：启动时报 `ConfigValidationError`，进程退出。

**根因**：迁移过程中字段映射或类型转换出错。

**回滚步骤**：
```bash
# 1. 恢复迁移前的 config.yaml（如果存在）
mv config.yaml.bak config.yaml

# 2. 恢复原始 .env（如果迁移来源是 .env）
mv .env.bak .env

# 3. 重启应用（使用旧配置方式）
```

**防范**：迁移流程已包含 `model_validate` 纯校验——校验失败不写盘。此场景理论上不应发生（V5 原子写入保证），但保留回滚路径。

#### 场景 B：迁移成功但运行时行为异常（配置语义偏差）

**现象**：应用启动正常，但 LLM 调用使用了错误的模型/API key/endpoint。

**根因**：扁平→嵌套映射中某个字段路径不正确，或 env alias 解析顺序与旧行为不一致。

**回滚步骤**：
```bash
# 1. 切回旧配置
mv config.yaml config.yaml.broken
cp config.yaml.bak config.yaml
mv .env.bak .env  # 如果原始来源是 .env

# 2. 重启应用

# 3. 对比 config.yaml.broken 和旧的 .env 找出差异字段
diff <(grep -v '^#' .env | sort) <(python -c "
from hugegraph_llm.config import ConfigManager
import yaml
print(yaml.dump(ConfigManager().persisted_config))
")
```

#### 场景 C：需在旧 .env 模式和新 YAML 模式间切换

**现象**：需要在 CI 中使用 `.env`，本地开发使用 YAML。

**方案**：ConfigManager 自动检测——如果 `config.yaml` 不存在且 `.env` 存在，使用 `.env` 模式（secret-only 语义）。两者共存时 YAML 优先，`.env` 提供 secret 覆盖。

```bash
# 强制使用 .env 模式
rm config.yaml          # 删除 YAML
cp .env.bak .env        # 还原 .env
# 重启 → ConfigManager 检测无 YAML → 从 .env 加载

# 切换回 YAML 模式
# ConfigManager 检测到 config.yaml → 直接加载
# .env 仅提供 secret 覆盖
```

### 8.3 不可回滚的操作（需人工确认）

| 操作 | 原因 | 预防 |
|------|------|------|
| `update_config()` 写盘 | 是用户主动行为，不是迁移副作用。如有问题，用 `config.yaml.bak` 恢复 | `update_config()` 仅接受 patch dict |
| `.env` 被删除（非 rename） | V5 从不删除 `.env`，只 rename 到 `.env.bak` | 迁移代码不含 `os.remove('.env')` |
| `config.yaml` 被覆盖 | 每次 `save()` 前自动生成 `config.yaml.bak` | 原子写入（写 temp + rename） |

### 8.4 回滚测试要求

| 测试 | 验证内容 |
|------|----------|
| `test_rollback_after_failed_migration` | 校验失败的迁移不破坏 config.yaml 和 .env |
| `test_rollback_env_bak_restore` | `.env.bak` 可恢复为有效 `.env` |
| `test_rollback_yaml_bak_restore` | `config.yaml.bak` 可恢复为有效 `config.yaml` |
| `test_double_migration_idempotent` | 对同一 .env 重复迁移不产生双重嵌套 |

---

## 九、配置迁移前后对照示例

> 以下展示同一份真实配置在三种格式下的对应关系。

### 9.1 Phase0：原始 `.env` 文件

```bash
# ========== LLM: OpenAI ==========
OPENAI_CHAT_API_BASE=https://api.openai.com/v1
OPENAI_CHAT_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_CHAT_LANGUAGE_MODEL=gpt-4.1-mini
OPENAI_CHAT_TOKENS=8192
OPENAI_EXTRACT_API_BASE=https://api.openai.com/v1
OPENAI_EXTRACT_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_EXTRACT_LANGUAGE_MODEL=gpt-4.1-mini
OPENAI_EXTRACT_TOKENS=256
OPENAI_TEXT2GQL_API_BASE=https://api.openai.com/v1
OPENAI_TEXT2GQL_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_TEXT2GQL_LANGUAGE_MODEL=gpt-4.1-mini
OPENAI_TEXT2GQL_TOKENS=4096
OPENAI_EMBEDDING_API_BASE=https://api.openai.com/v1
OPENAI_EMBEDDING_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# ========== LLM: Ollama ==========
OLLAMA_CHAT_HOST=127.0.0.1
OLLAMA_CHAT_PORT=11434
OLLAMA_CHAT_LANGUAGE_MODEL=qwen3:0.5b

# ========== LLM: General ==========
LANGUAGE=CN
CHAT_LLM_TYPE=openai
EXTRACT_LLM_TYPE=openai

# ========== HugeGraph ==========
GRAPH_URL=127.0.0.1:8080
GRAPH_NAME=hugegraph
GRAPH_USER=admin
GRAPH_PWD=my-graph-password
GRAPH_SPACE=

# ========== Admin ==========
ADMIN_TOKEN=my-admin-token
USER_TOKEN=my-user-token

# ========== Vector Index ==========
CUR_VECTOR_INDEX=Faiss
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
QDRANT_API_KEY=my-qdrant-key
```

### 9.2 Phase1：扁平 `config.yaml`（类名节，ALL_CAPS 键）

```yaml
LLMConfig:
  LANGUAGE: CN
  CHAT_LLM_TYPE: openai
  EXTRACT_LLM_TYPE: openai
  OPENAI_CHAT_API_BASE: https://api.openai.com/v1
  OPENAI_CHAT_API_KEY: sk-xxxxxxxxxxxxxxxxxxxx
  OPENAI_CHAT_LANGUAGE_MODEL: gpt-4.1-mini
  OPENAI_CHAT_TOKENS: 8192
  OPENAI_EXTRACT_API_BASE: https://api.openai.com/v1
  OPENAI_EXTRACT_API_KEY: sk-xxxxxxxxxxxxxxxxxxxx
  OPENAI_EXTRACT_LANGUAGE_MODEL: gpt-4.1-mini
  OPENAI_EXTRACT_TOKENS: 256
  # ... 60+ flat entries

AdminConfig:
  ENABLE: 'False'
  ADMIN_TOKEN: my-admin-token
  USER_TOKEN: my-user-token

HugeGraphConfig:
  GRAPH_URL: 127.0.0.1:8080
  GRAPH_NAME: hugegraph
  GRAPH_USER: admin
  GRAPH_PWD: my-graph-password
  # ...

IndexConfig:
  CUR_VECTOR_INDEX: Faiss
  QDRANT_HOST: 127.0.0.1
  QDRANT_PORT: 6333
  QDRANT_API_KEY: my-qdrant-key
```

### 9.3 Phase2（目标）：嵌套 `config.yaml` + secret-only `.env`

**`config.yaml`**（非敏感配置，可提交/挂载）：

```yaml
llm:
  language: CN
  chat_llm_type: openai
  extract_llm_type: openai
  text2gql_llm_type: openai
  embedding_type: openai
  reranker_type: none
  keyword_extract_type: none
  window_size: 3000
  hybrid_llm_weights: [0.5, 0.5]

  openai:
    chat:
      api_base: https://api.openai.com/v1
      api_key: null            # ← secret: see .env
      language_model: gpt-4.1-mini
      tokens: 8192
    extract:
      api_base: https://api.openai.com/v1
      api_key: null            # ← secret: see .env
      language_model: gpt-4.1-mini
      tokens: 256
    text2gql:
      api_base: https://api.openai.com/v1
      api_key: null            # ← secret: see .env
      language_model: gpt-4.1-mini
      tokens: 4096
    embedding:
      api_base: https://api.openai.com/v1
      api_key: null            # ← secret: see .env
      model: text-embedding-3-small

  ollama:
    chat:
      host: 127.0.0.1
      port: 11434
      language_model: qwen3:0.5b
    extract:
      host: null
      port: 11434
      language_model: null
    text2gql:
      host: null
      port: 11434
      language_model: null
    embedding:
      host: null
      port: 11434
      model: null

  litellm:
    chat:
      api_base: null
      api_key: null            # ← secret: see .env
      language_model: null
      tokens: 8192
    # ...

hugegraph:
  graph:
    url: 127.0.0.1:8080
    name: hugegraph
    user: admin
    pwd: null                 # ← secret: see .env
    space: null
  query:
    limit_property: 10
    max_graph_path: 10
    max_graph_items: 100
    edge_limit_pre_label: 100
  vector:
    dis_threshold: 0.9
    topk_per_keyword: 5
  rerank:
    topk_return_results: 10

admin:
  login:
    enable: 'False'
    admin_token: null          # ← secret: see .env
    user_token: null           # ← secret: see .env

index:
  cur_vector_index: Faiss
  qdrant:
    host: 127.0.0.1
    port: 6333
    api_key: null              # ← secret: see .env
  milvus:
    host: null
    port: 19530
    user: null
    password: null             # ← secret: see .env
```

**`.env`**（仅敏感字段，绝不提交到 Git）：

```bash
# ===== LLM Secrets =====
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
# (LITELLM_API_KEY if using litellm)

# ===== HugeGraph Secrets =====
GRAPH_PWD=my-graph-password

# ===== Admin Secrets =====
ADMIN_TOKEN=my-admin-token
USER_TOKEN=my-user-token

# ===== Vector Index Secrets =====
QDRANT_API_KEY=my-qdrant-key
# (MILVUS_PASSWORD if using milvus)
```

### 9.4 合并后运行时有效值

| 字段 | YAML 值 | `.env`/`os.environ` | 最终生效值 |
|------|---------|---------------------|-----------|
| `llm.openai.chat.api_base` | `https://api.openai.com/v1` | (无) | `https://api.openai.com/v1` |
| `llm.openai.chat.api_key` | `null` | `OPENAI_API_KEY=sk-xxx` | `sk-xxx` |
| `llm.openai.chat.language_model` | `gpt-4.1-mini` | (无) | `gpt-4.1-mini` |
| `hugegraph.graph.pwd` | `null` | `GRAPH_PWD=my-graph-password` | `my-graph-password` |
| `admin.login.admin_token` | `null` | `ADMIN_TOKEN=my-admin-token` | `my-admin-token` |
| `index.qdrant.api_key` | `null` | `QDRANT_API_KEY=my-qdrant-key` | `my-qdrant-key` |

> **关键原则**：YAML 中所有敏感字段值为 `null`，通过 `.env` / `os.environ` / K8s Secret 注入运行时值。`save()` 永不会将 null 替换为 env 中的 secret 明文。

---

## 附录 A：V4→V5 飞书评论逐条回复

> 以下逐一列出飞书知识库文档"Graph-AI的配置存储重构方案"上的 11 条评论原文、分析、以及 V5 的修改方案和落地位置。

---

### 评论 #1：标题修正（已解决）

**原评论**：
> "Graph-AI的配置特性修改" → 建议改为 "Graph-AI 配置存储重构方案"

**分析**：标题不准确，未反映文档内容范围。

**V5 修改**：标题已修正为"Graph-AI 配置存储重构方案 V5"。完整描述性副标题下移为 subtitle。

---

### 评论 #2：‼️ `.env` 角色需重新定义 —— secret-only 文件

**原评论**：
> ‼️ 需要先明确 `.env` 的最终角色。
>
> 基于当前目标，`.env` 不应该被完全废弃，而应调整为 **secret-only 文件**：
> - `.env` 可以继续作为本地或服务端 secret 存储；
> - 生产环境推荐 K8s Secret / Docker Secret / CI Secret / 系统 EnvironmentFile；
> - 普通非敏感配置迁移到 `config.yaml`；
> - 应用运行时统一从 `os.environ` 读取 secret；
> - `config.yaml` 保存时永远不序列化 `.env` / `os.environ` 来源的 secret。
>
> 否则读者会误解为"迁移后 `.env` 完全不用"，但实际本地开发和部分服务端部署仍需要一个持久化 secret 文件。

**分析**：这是 V4 最大的设计偏差。V4 将 `.env` 定位为"一次性迁移输入"——迁移后备份并废弃。但实际生产环境中，本地开发、CI/CD、部分非 K8s 部署场景需要持久化的 secret 文件。完全废弃 `.env` 会导致这些场景无路可走。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 重新定义 `.env` 角色 | §1.2 F2 | `.env` 重新定义为 secret-only 文件：仅存储 API key/token/password，非敏感配置全部迁移到 `config.yaml` |
| 新的三层来源表 | §2.2.2 | `.env`（secret-only）参与 effective config（加载到 `os.environ`），但绝不持久化到 YAML |
| `.env` 处理决策表 | §2.2.2 | 覆盖 5 种场景：Phase2 YAML 存在 / 仅 Phase1 YAML / 仅 `.env` / 两者共存 / 运行时，每种场景明确 `.env` 的行为 |
| 安全需求补充 | §1.4 S2 | 明确 `.env` 来源的敏感值也不写入 `config.yaml` |

---

### 评论 #3：‼️ `.env` 迁移需补"敏感字段分类"层

**原评论**：
> ‼️ `.env` 迁移规则需要补一层"敏感字段分类"。
>
> 这里不能简单写成"`.env` 迁移到 `config.yaml`"。更安全的规则应该是：
> - 非敏感字段迁移到 `config.yaml`；
> - 敏感字段继续保留在 `.env`，或提示用户迁移到 K8s Secret / Docker Secret / CI Secret；
> - 敏感字段不会写入 `config.yaml`；
> - `save()` / `update_config()` 永远不把 env 来源的 secret 序列化到 YAML。
>
> 建议增加字段分类表：
> - 可进 YAML：`OPENAI_BASE_URL`、`GRAPH_URL`、`GRAPH_NAME`、`QDRANT_HOST`、`QDRANT_PORT`
> - 保留 secret：`OPENAI_API_KEY`、`ADMIN_TOKEN`、`USER_TOKEN`、`GRAPH_PWD`、`QDRANT_API_KEY`、`MILVUS_PASSWORD`
>
> 否则"YAML 化配置"和"secret 不进入 YAML"两个目标会在迁移阶段发生冲突。

**分析**：V4 的 `.env` 迁移逻辑是"所有字段迁移到 YAML + env secret 不落盘"。但这存在内在矛盾：如果 `.env` 同时包含敏感和非敏感字段，全量迁移会把敏感字段也写进 `config.yaml`；如果全靠 env override 机制防止落盘，又会在"用户拿到一个干净的 YAML 但发现缺少很多字段"时产生困惑。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 敏感字段分类表 | §2.2.2 | 明确列出：`OPENAI_API_KEY`、`ADMIN_TOKEN`、`USER_TOKEN`、`GRAPH_PWD`、`QDRANT_API_KEY`、`MILVUS_PASSWORD` 等保留在 `.env`；`OPENAI_BASE_URL`、`GRAPH_URL`、`QDRANT_HOST` 等迁移到 YAML |
| 迁移流程重写 | §2.4.2 | 增加敏感字段分类步骤：非敏感 → 嵌套 YAML → `config.yaml`；敏感 → 保留在 `.env`（如不存在则生成含注释的 .env 模板） |
| 兼容性需求 | §1.5 M4 | 迁移时敏感字段分类作为正式需求 |
| `is_sensitive_field()` | 任务 2.1 | 新增敏感字段识别函数，作为转换基础设施的一部分 |

---

### 评论 #4：‼️ 非 LLM 配置也需要完整 `_env_var_map`

**原评论**：
> ‼️ 非 LLM 配置也需要完整 `_env_var_map`。
>
> 现在文档对 LLM env alias 设计比较完整，但 `HugeGraphConfig`、`AdminConfig`、`IndexConfig` 还没有明确保留旧 env 覆盖能力。
>
> 这在新的 `.env = secret-only` 设计下更重要：`.env` 中的 `GRAPH_PWD`、`ADMIN_TOKEN`、`QDRANT_API_KEY`、`MILVUS_PASSWORD` 最终都需要通过 `os.environ` 覆盖 YAML，否则 secret-only `.env` 会无法生效。
>
> 建议补充验收：
> - 每个 config class 都必须声明 `_env_var_map`；
> - 旧 env 名称全集必须被新 `_env_var_map` 覆盖；
> - 未覆盖的旧 env 名称在 CI 中 fail；
> - secret 字段验证 env 覆盖 YAML，但不会写入 `config.yaml`。

**分析**：V4 主要聚焦于 LLMConfig 的 `_env_var_map`，但新语义下 HugeGraphConfig、AdminConfig、IndexConfig 的敏感字段（`GRAPH_PWD`, `ADMIN_TOKEN`, `QDRANT_API_KEY` 等）也需要通过 env 覆盖 YAML。如果没有 `_env_var_map`，secret-only `.env` 对这些字段就会失效。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 所有配置类的 `_env_var_map` | §2.3.3 | 新增表格指定每个配置类的关键环境变量：LLMConfig → `OPENAI_API_KEY` 等；HugeGraphConfig → `GRAPH_PWD`；AdminConfig → `ADMIN_TOKEN`, `USER_TOKEN`；IndexConfig → `QDRANT_API_KEY`, `MILVUS_PASSWORD` |
| 任务 5 强化 | 任务 5 | 从"其余配置类映射"升级为"其余配置类映射（含完整 `_env_var_map`）"；每个类都需要声明 |
| CI 验收 | 任务 5 + §3.8.3 | 旧 env 名称全集必须被覆盖；CI 中增加 `legacy_env_coverage` 检查 |
| 功能需求 | §1.2 F9 | 每个配置类必须声明 `_env_var_map` |

---

### 评论 #5：‼️ `config_prompt.yaml` 需唯一生命周期决策

**原评论**：
> ‼️ `config_prompt.yaml` 需要给 V1 一个唯一生命周期决策。
>
> 当前文档同时保留了两种路线：
> - 用户可写配置，与 `config.yaml` 同基准目录；
> - 只读 package resource，不自动写入。
>
> 这不是实现细节，而是启动行为、部署挂载、只读文件系统测试和配置示例的基础契约。
>
> 建议 V1 直接选择：
> - `config_prompt.yaml` 是用户可写配置；
> - 路径与 `config.yaml` 使用同一个 config base dir；
> - package 内 prompt yaml 只作为默认模板；
> - 启动时不得写回 package resource；
> - 缺失时从模板复制到用户配置目录；
> - 只读配置目录 fail-fast。

**分析**：V4 在这个问题上确实摇摆不定，同时保留了两种设计方案。这会导致实现时认知不统一。评论明确推荐了"用户可写配置"路线，并给出了完整的行为契约。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 唯一生命周期决策 | §2.3.5 | 选定：用户可写配置，路径与 `config.yaml` 同基准目录；package 内作为默认模板；启动时从模板复制到用户配置目录（不写回 package）；只读 fail-fast |
| 移除二选一 | §2.3.5 | 删除原来的"若可写...若只读..."的两种分支描述 |

---

### 评论 #6：‼️ 新增 API/operator 默认值审计与迁移任务

**原评论**：
> ‼️ 需要新增 "API/operator 默认值审计与迁移" 任务。
>
> 当前文档主要覆盖 `configs_block.py` 和 config 生成逻辑，但配置消费面还包括：
> - API request model 默认值；
> - `/config/*` API 写入路径；
> - operator 构造默认值；
> - node 内部 fallback literal；
> - import-time 绑定的配置值。
>
> 这些如果不统一迁移，可能出现：
> - YAML 中配置已修改；
> - API 默认值仍是旧常量；
> - OpenAPI 展示默认值不一致；
> - operator 在模块导入时固化旧配置。
>
> 建议新增验收：请求省略字段时的运行时行为、OpenAPI 默认值、operator 默认值和 YAML effective config 必须一致；如果某些 literal 不属于配置项，也需要明确列为非配置项。

**分析**：V4 的消费面覆盖确实局限在 `configs_block.py`。但整个系统中配置值被多处引用：API 层的 `Field(default=...)`、operator 构造时的默认参数、node 内部的 fallback 常量、import 时读取的配置值。如果这些不同步迁移，用户改了 YAML 但运行时行为不变（因为其他地方还有旧常量），是最难排查的 bug。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| **新增任务 6** | §3（任务 6） | "API/operator 默认值审计与迁移"作为独立任务，优先级 P1 |
| 审计清单 | 任务 6 | 6 个维度的审计：API request model 默认值、`/config/*` API 写入路径、operator 构造默认值、node fallback literal、import-time 绑定、OpenAPI schema |
| 任务 1 扩展 | 任务 1 | 扫描范围从 `.env`/dotenv 扩展为也包括配置消费面（API、operator、node、import-time） |
| 非配置项标记 | 任务 6 产出 | 明确列出不属于配置管理的 literal，防止后续混淆 |

---

### 评论 #7：⚠️ `update_config()` / `update_section()` 的 source 类型细分

**原评论**：
> ⚠️ `update_config()` / `update_section()` 的 source 类型建议拆清楚。
>
> 当前文档里 `runtime_patch` 容易和"用户显式提交的可持久化 patch"混在一起。
>
> 建议拆成：
> - `env_override`：来自 `.env` / `os.environ`，永不持久化；
> - `effective_default`：默认值，可用于生成配置，但不能伪装成用户修改；
> - `explicit_persisted_patch`：用户通过 UI/API 显式修改，允许写入 YAML；
> - `runtime_only_patch`：只影响内存，永不写入 YAML。
>
> 同时明确：
> - `update_config({...})` 产生的是 `explicit_persisted_patch`；
> - `save()` 只序列化 `persisted_config`；
> - 禁止把 `effective_config` full dump 到 YAML。

**分析**：V4 的 `_field_source` 只定义了 3 类（`default`, `yaml`, `env`, `runtime_patch`），把"用户显式 patch"和"临时的仅内存 patch"混为 `runtime_patch`，这会让 `update_section()` 无法区分"用户想持久化的 patch"和"只是临时生效的 patch"。拆成 4 类后边界清晰，每种来源的可持久化语义不言自明。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 四类来源定义 | §2.2.1 | `env_override`（永不持久化）、`effective_default`（不伪装用户修改）、`explicit_persisted_patch`（用户显式修改，可写盘）、`runtime_only_patch`（只影响内存） |
| 核心不变式 | §2.2.1 | `update_config({...})` → `explicit_persisted_patch`；`save()` 只序列化 `persisted_config`；禁止 full dump `effective_config` |
| 与之前 3 类模型的对比 | §4 | 标记为 V5 细化 |

---

### 评论 #8：⚠️ `configs_block.py` role 级联逻辑需用户 source tracking

**原评论**：
> ⚠️ `configs_block.py` 中基于 `.env` 是否存在的 role 级联逻辑需要单独定义。
>
> 当前逻辑不是普通配置读取，而是在判断用户是否显式配置过 extract/text2gql 的 key。
>
> 迁移后建议使用 `persisted_config` + source tracking 表达：
> - 如果 extract/text2gql 对应字段在 YAML 中缺失，允许从 chat patch 级联；
> - 如果字段来源是 YAML 或 explicit persisted patch，不自动覆盖；
> - 如果字段来源是 `.env` / `os.environ`，需要明确是否允许级联，避免覆盖 secret-only 配置。
>
> 否则 chat 配置可能意外覆盖 extract/text2gql 的专用 secret 或专用模型配置。

**分析**：现有的 `configs_block.py` 中有一个特殊逻辑：如果用户没有显式配置 extract/text2gql 的 API key，自动从 chat 的配置级联。这个逻辑之前通过检查 `.env` 文件是否存在来判断。迁移后 `.env` 变成了 secret-only，必须改用 source tracking 来判断"用户是否显式配置过"。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 独立设计章节 | §2.5 | "`configs_block.py` role 级联逻辑"作为独立章节，定义了三层判断规则 |
| 级联规则 | §2.5 | 1) `effective_default` → 允许级联；2) YAML / `explicit_persisted_patch` → 不覆盖；3) `env_override` → 不级联（保护 secret-only） |
| 任务 7 中的实现指引 | 任务 7 | 明确 `configs_block.py` 需要使用 source tracking 重写级联逻辑 |

---

### 评论 #9：⚠️ CI 测试按 secret-only `.env` 语义补齐

**原评论**：
> ⚠️ CI 测试需要按新的 `.env = secret-only` 语义补齐。
>
> 建议至少增加这些 case：
> - 旧 `.env` 中非敏感字段迁移到 `config.yaml`；
> - 旧 `.env` 中敏感字段保留在 `.env`，不进入 `config.yaml`；
> - `.env` 中的 secret 加载到 `os.environ` 后能覆盖 YAML；
> - `update_config()` 修改非敏感字段时，不会把 env secret 写入 YAML；
> - 所有旧 env 名称都被 `_env_var_map` 覆盖；
> - 新增 config tests 必须带 `unit` 或 `contract` marker，能被现有 CI 收到。
>
> 避免只在文档里写测试命令，但 PR CI 实际没有覆盖。

**分析**：V4 的 CI 测试设计时 `.env` 还是"一次性迁移输入"的语义。改为 secret-only 后，测试覆盖有空白——特别是新旧 `.env` 语义转换的边界行为、以及 tests 的 marker 体系需要确保被现有 CI 接收到。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 5 个新增测试 case | §3.8.2 | 非敏感字段迁移到 `config.yaml`、敏感字段保留在 `.env`、`.env` secret 覆盖 YAML、update_config 不泄露 env secret、旧 env 名称全覆盖 |
| 测试 marker 要求 | §3.8.2 | 新增 config tests 必须标记为 `unit` 或 `contract`，能被现有 CI 收到 |
| CI 命令更新 | §3.8.3 | `-k` filter 增加 `backup` 和 `legacy_env` 关键字 |

---

### 评论 #10：⚠️ 部署文档需区分不同 `.env` 语义

**原评论**：
> ⚠️ 部署文档需要区分不同 `.env` 语义。
>
> 当前不能简单要求全局 `.env` 清零，因为至少存在两类合法 `.env`：
> - secret `.env`：用于本地或服务端保存 API key / token / password；
> - docker compose `.env`：用于 `PROJECT_PATH` 等 compose 变量。
>
> 建议部署文档明确：
> - `hugegraph-llm` 的普通运行配置不再放 `.env`；
> - secret 可以继续来自 `.env` / Docker env_file / K8s Secret / CI Secret；
> - Docker Compose 自身的 `.env` 可以保留；
> - `config.yaml` 只管理非敏感配置。
>
> 同时修正真实文件路径，避免写不存在的 `docker/docker-compose.yml`。

**分析**：V4 的部署文档倾向于"全局消灭 `.env` 引用"，但在实际部署中存在两种完全不同的 `.env`——应用级的 secret 文件和 Docker Compose 自身的变量文件。不区分会导致混乱。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 三种 `.env` 区分 | §3 任务 9 | Secret `.env`（保留，secret-only）；Docker Compose `.env`（保留，compose 基础设施）；旧通用 `.env`（迁移到 `config.yaml`） |
| 部署文件验收 | 任务 9 | 明确每个部署文件的更新内容，区分三种 `.env` 处理方式 |
| 路径修正 | 任务 9 | `docker/docker-compose.yml` 改为实际存在 `docker/docker-compose-llm.yml` 和 `docker/docker-compose-network.yml` |

---

### 评论 #11：🧹 `.env.bak` 备份与权限安全策略

**原评论**：
> 🧹 如果迁移过程会处理 `.env`，建议补充备份和权限策略。
>
> 因为 `.env` 可能包含 secret，`.env.bak` 也同样是敏感文件。建议明确：
> - `.env.bak` 是否生成；
> - 是否覆盖已有 `.env.bak`；
> - 文件权限是否限制为 owner readable；
> - 迁移日志是否脱敏；
> - 迁移失败时如何回滚；
> - 是否提示用户不要提交 `.env` / `.env.bak`。
>
> 否则即使 `config.yaml` 不保存 secret，备份文件也可能成为泄露点。

**分析**：V4 提到了 `.env.bak` 的生成但对其安全属性没有任何约束。在新语义下 `.env` 专门存 secret，所以 `.env.bak` 的安全风险比之前更高。需要完整的权限、覆盖、日志、回滚策略。

**V5 修改**：

| 修改点 | 位置 | 具体内容 |
|--------|------|----------|
| 独立安全设计章节 | §2.2.3 | "`.env.bak` 安全策略"逐一回答全部 6 个问题 |
| 权限：`0600` | §2.2.3 | owner-readable only |
| 覆盖：时间戳备份 | §2.2.3 | 每次迁移生成带时间戳的新文件，不覆盖已有备份 |
| 日志脱敏 | §2.2.3 | 迁移日志不记录敏感字段名和值 |
| 回滚：迁移失败不生成 .bak | §2.2.3 | 保留原始 `.env` 不变 |
| .gitignore | 任务 7 | 同时忽略 `.env` 和 `.env.bak` |
| 非功能需求 | §1.3 NF6 | 作为正式非功能需求 |
| 安全需求 | §1.4 S6 | 作为正式安全需求 |

---

## 附录 B：V4→V5 变更摘要

| 飞书评论 | 问题关键词 | 优先级 | V5 核心变更 | 影响章节 |
|----------|-----------|--------|------------|----------|
| #1 | 标题修正 | - | 标题改为"Graph-AI 配置存储重构方案 V5" | 标题 |
| #2 | `.env` 角色重定义 | P0 | `.env` 从"一次性迁移输入"改为"secret-only 文件" | §1.2, §2.2.2 |
| #3 | 敏感字段分类 | P0 | 新增分类表 + 迁移流程含敏感分类 + `is_sensitive_field()` | §2.2.2, §2.4.2, 任务 2.1 |
| #4 | 非 LLM `_env_var_map` | P1 | HugeGraph/Admin/IndexConfig 全部声明 `_env_var_map` | §2.3.3, 任务 5 |
| #5 | `config_prompt.yaml` 决策 | P1 | 选定"用户可写配置"唯一路线 | §2.3.5 |
| #6 | API/operator 审计 | P1 | **新增任务 6**：全链路默认值一致性审计 | §3 任务 6 |
| #7 | 字段来源细分 | P1 | 3 类 → 4 类：`env_override`, `effective_default`, `explicit_persisted_patch`, `runtime_only_patch` | §2.2.1 |
| #8 | 级联逻辑 | P1 | `configs_block.py` 使用 source tracking 重写 | §2.5, 任务 7 |
| #9 | CI test 补齐 | P2 | 5 个新 test case + marker 体系 + CI 命令更新 | §3.8.2, §3.8.3 |
| #10 | 部署文档 `.env` 区分 | P2 | 三种 `.env` 语义 + 路径修正 | §3 任务 9 |
| #11 | `.env.bak` 安全 | P2 | 0600 权限 + 时间戳备份 + 日志脱敏 + 回滚 | §2.2.3, §1.3 NF6 |
