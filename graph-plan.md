# HugeGraph-AI 配置系统迁移：当前主线改造计划

## 0. 来源与定位

本文档是 HugeGraph-AI 配置系统迁移的当前协作计划，用于把需求边界、主线基线、设计约束、实现方法、改造路径、任务拆分和验收标准放在同一个入口内确认清楚。

状态说明：

- 本文档不是纯实现报告，但需要记录已有证据，避免把已落地能力误写成完全未开始。
- 第 0.1 节只记录当前工作区已经有测试或 smoke 证据支撑的状态锚。
- 第 3 节之后描述的是 V1 的计划目标、设计约束、待办任务和验收标准。
- 某项能力是否已经实现，只能以对应代码 diff、测试结果和验收记录为准。

### 0.1 V1 已落地与验证状态

本节用于锚定当前工作区的真实状态，避免计划文档反向失真。这里的“已落地”只表示本地分支存在对应实现并通过下列验证，不等同于主线已合并，也不替代后续代码审查。

当前已落地路径：

- `hugegraph-llm/src/hugegraph_llm/config/paths.py`：配置目录解析。
- `hugegraph-llm/src/hugegraph_llm/config/mapping.py`：flat field、nested path、global dotted path、sensitive path 映射。
- `hugegraph-llm/src/hugegraph_llm/config/manager.py`：effective config、field source、patch-only writer、secret env writer、migration 编排。
- `hugegraph-llm/src/hugegraph_llm/config/migration.py`：Phase 检测、迁移报告、备份和报告写入。
- `hugegraph-llm/src/hugegraph_llm/config_migrate.py`：`doctor`、`plan`、`diff`、`apply`、`export-env` CLI 模块入口。
- `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py`：Gradio 写回已收敛到 `_persist_config_updates()`，按敏感性分流。
- `hugegraph-llm/config.example.yaml`：非敏感嵌套 YAML 示例。
- `hugegraph-llm/src/tests/config/test_config_v1_contract.py`：V1 配置合同测试。

2026-06-06 本地验证结果：

- 配置测试：`SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/config/ -v --tb=short`，结果为 `33 passed, 3 warnings`。
- 迁移 CLI 模块 smoke：使用 `PYTHONPATH=hugegraph-llm/src .venv/bin/python -m hugegraph_llm.config_migrate --config-dir <tmp>` 依次执行 `doctor`、`plan`、`diff`、`apply --yes`、`export-env`，结果通过。
- smoke 产物：生成 `config.yaml`、`.env.bak.pre-phase-2.<migration_id>`、`migration-reports/<migration_id>.json`、`migration-reports/<migration_id>.md`、`export.env`。
- secret 审计：在 smoke 的 `config.yaml`、migration reports、`diff` 输出和 `apply` 输出中未检出测试 secret 明文。
- Gradio 相关合同测试已覆盖 `_persist_config_updates()` 分流、LLM 配置保存分流和 role key check 使用 effective config。

仍需作为收口项处理：

- freeze matrix 的逐点标注规则已经进入 M0 出口条件；矩阵正文仍是 M0 交付物，尚需在收口时产出。
- console script 安装态 smoke 需要在可完成 package build 的环境中验证；当前本地 smoke 已验证模块入口。
- Helm 全量文档审计保留为 P2，不作为 V1 合并阻塞；Docker compose `.env` 与 runtime `.env` 的区分仍属于 V1 文档验收。

### 0.2 评审闭合决策

本节用于记录前两轮评审中仍需拍板的边界项。写法遵循“计划与状态分离”：只说明决策、理由和归属，不使用 checkbox 或完成态清单。

freeze matrix：

- 当前决策：逐点打标签是 V1 必须遵守的 M0 出口规则。
- 当前状态：规则已经写入本文档；矩阵本身还没有落成正文，属于 M0 交付物。
- 收口要求：M0 结束前必须列出 API request model、operator、node、flow 中的冻结点，并为每个冻结点标注 `V1 处理`、`V1.1 延后` 或 `不适用`。
- 判定口径：这是“已排期、未产出”，不是漏项；若 M0 收口时没有矩阵正文，则不能进入后续实现收口。

Helm gate：

- 当前决策：Helm 全量文档审计不进入 V1 P0/P1 gate，保留为 P2 和后续计划。
- 裁剪理由：V1 的安全边界集中在 runtime config、secret-only `.env`、patch-only writer 和迁移可验证性；Helm 全量审计会扩大部署面，不作为当前 V1 合并阻塞。
- V1 保留项：Docker compose `.env` 与 HugeGraph-LLM runtime `.env` 的语义区分必须进入文档验收。
- 后续归属：Helm、workflow 和部署 grep gate 在第 9 节延后事项中保留，不从计划中删除。

Gradio 写回边界：

- 当前决策：Gradio 敏感/非敏感写回分流保留在 V1；完整 Gradio UX 重构延后。
- 决策理由：写回分流直接关系到 secret 是否误持久化，是安全边界的一部分；UX 重构不是 V1 必要安全闭环。
- 收口要求：V1 只验证 `_persist_config_updates()` 这类主要写回路径的分流行为，不把完整 UI 体验重构扩大进本轮。

总体口径：

- 前两轮评审的实质 blocker 已经转化为规则、状态锚或明确裁剪项。
- 未进入 V1 的内容必须在延后事项中保留归属，不得在实现中临时扩大范围。
- 若后续坚持 Helm 进入 V1，需要先修改本文档的 P0/P1 gate 和第 9 节延后事项，再进入实现。

关联 Issue：

<https://github.com/apache/hugegraph-ai/issues/234>

适用范围：

- 主要模块：`hugegraph-llm/`
- 主要路径：`hugegraph-llm/src/hugegraph_llm/config/`
- 关联消费面：API request model、Gradio demo、operators、nodes、utils 中真实存在的配置读写路径。
- 非必要不修改 `hugegraph-python-client/`、`hugegraph-ml/`、`vermeer-python-client/`。

推进方式：

1. 先确认需求边界：明确 V1 要解决什么、不解决什么。
2. 再确认主线基线：以当前代码为准列出现有入口、默认值冻结点、写盘路径和部署文档入口。
3. 再确认设计边界：确定从 `BaseConfig`、PromptConfig、旧全局 settings、Gradio 写入口到新配置语义的改造方式。
4. 再确认实现方法和路径：明确新增哪些文件、修改哪些文件、每个文件承担什么职责。
5. 需求、问题、设计、任务和验收确认清楚后，再进入实现或收口修正。

核心定位：

- V1 不是“大一统配置系统”，而是“兼容旧入口的有效配置事实源”。
- V1 计划优先解决读取写盘副作用、`.env` 职责混乱、secret 误持久化、full dump 写盘和迁移可验证性。
- 旧入口 `llm_settings`、`huge_settings`、`admin_settings`、`index_settings`、`prompt` 的兼容性是 V1 目标，避免一次性迁移所有业务消费者。
- Prompt 全生命周期、完整 Gradio 交互重构、部署 grep gate、rollback CLI、hot reload 不进入 V1 主线。

## 1. 单文档确认边界

本文档是唯一的计划与确认入口。需求边界、主线基线、问题矩阵、设计方向、实现方法、任务拆分、测试和验收标准都在本文档内确认；确认完成后按本文档进入实现或收口，不再拆出额外计划文件。

确认项：

- 需求边界：V1 收敛为“有效配置事实源 + 旧入口兼容 + 可验证迁移”。通过标准是第 3、4、8 节口径一致。
- 主线基线：覆盖现有配置入口、写盘副作用、默认值冻结点和部署文档入口。通过标准是第 2、6 节能映射到真实文件。
- 问题矩阵：覆盖 baseline matrix、freeze matrix、write-entry matrix、migration matrix、docs/deploy matrix。通过标准是 M0 出口条件明确。
- 设计方向：覆盖配置键元数据、当前有效配置、secret-only `.env`、patch-only 写盘、migration workflow、旧 settings 兼容。通过标准是第 5 节可直接指导实现。
- 实现路径：每个目标必须写清楚主要文件和落地方法。通过标准是第 5.4 节能直接对应代码改动。
- 测试与验收：覆盖 P0/P1/P2 gate、测试文件建议、功能/安全/兼容/文档验收标准。通过标准是第 7、8 节可作为实现 gate。

## 2. 当前主线基线

### 2.1 现有配置入口

`hugegraph-llm/src/hugegraph_llm/config/models/base_config.py`

- 当前职责：所有 section 配置基类，保留 `update_env()`、`generate_env()`、`check_env()` 等旧方法。
- V1 拟处理：不允许 import 或构造时写盘；旧 wrapper 只作为兼容 facade。

`hugegraph-llm/src/hugegraph_llm/config/llm_config.py`

- 当前职责：LLM、Embedding、Reranker 配置。
- V1 拟处理：声明 `_flat_to_nested_mapping`、`_env_var_map`、`_mutable_persisted_fields`。

`hugegraph-llm/src/hugegraph_llm/config/hugegraph_config.py`

- 当前职责：HugeGraph 连接与查询参数。
- V1 拟处理：`GRAPH_PWD` 视为敏感值，不写入 YAML。

`hugegraph-llm/src/hugegraph_llm/config/admin_config.py`

- 当前职责：登录开关、用户 token、管理员 token。
- V1 拟处理：`USER_TOKEN`、`ADMIN_TOKEN` 视为敏感值，不写入 YAML。

`hugegraph-llm/src/hugegraph_llm/config/index_config.py`

- 当前职责：Faiss、Qdrant、Milvus 配置。
- V1 拟处理：Qdrant/Milvus 密钥只走 secret path。

`hugegraph-llm/src/hugegraph_llm/config/prompt_config.py` 与 `hugegraph-llm/src/hugegraph_llm/config/models/base_prompt_config.py`

- 当前职责：Demo prompt YAML 生命周期。
- V1 拟处理：只做最小兼容，不扩大为完整 Prompt 生命周期。

`hugegraph-llm/src/hugegraph_llm/config/__init__.py`

- 当前职责：暴露旧全局 settings。
- V1 拟处理：目标是旧入口继续可用，内部读取当前 effective config。

`hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py`

- 当前职责：Gradio 配置读写入口。
- V1 拟处理：非敏感写 `config.yaml`，敏感写 secret-only `.env`。

### 2.2 旧 env 覆盖范围

旧 env 名称必须被新 `_env_var_map` 覆盖，未覆盖应进入审计失败或迁移报告。

- `LLMConfig`：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OLLAMA_HOST`、`LITELLM_BASE_URL`、`COHERE_API_KEY`。
- `HugeGraphConfig`：`GRAPH_URL`、`GRAPH_NAME`、`GRAPH_USER`、`GRAPH_PWD`。
- `AdminConfig`：`ENABLE_LOGIN`、`ADMIN_TOKEN`、`USER_TOKEN`。
- `IndexConfig`：`CUR_VECTOR_INDEX`、`QDRANT_API_KEY`、`MILVUS_PASSWORD`。

### 2.3 风险矩阵

import 写盘副作用：

- 典型表现：导入配置时创建 `.env`、`config.yaml` 或 prompt YAML。
- V1 约束：import 和配置对象构造必须只读。

`.env` 职责混乱：

- 典型表现：非敏感配置和密钥混在 `.env`。
- V1 约束：`.env` 退回 secret-only；非敏感值迁移到 `config.yaml`。

secret 误持久化：

- 典型表现：env secret 被 `save()` 或 full dump 带入 YAML。
- V1 约束：`save()` 只序列化 persisted config，敏感路径拒绝非空写入。

full dump 写盘：

- 典型表现：`update_config(model_dump())` 覆盖整段配置。
- V1 约束：patch-only writer，允许路径白名单判断。

默认值冻结：

- 典型表现：request model 或 operator 在 import/class definition 阶段读取配置。
- V1 约束：记录 freeze matrix；高风险入口按 runtime 读取推进，不能低风险处理的列入后续。

CWD 依赖：

- 典型表现：不同启动目录读取不同 `.env`。
- V1 约束：统一 config base dir，不 fallback 到 `os.getcwd()`。

迁移不可审计：

- 典型表现：旧格式迁移后无法确认哪些值被移动、忽略或保留。
- V1 约束：迁移报告输出 persisted/sensitive/unknown/ignored key。

### 2.4 新增与重点改造路径

以下路径是相对当前主线的新增或重点改造路径。若本地分支已经存在同名文件，也必须按本文档核对实现是否满足对应方法和验收标准。

`hugegraph-llm/src/hugegraph_llm/config/paths.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：解析 config base dir，统一 `config.yaml`、`.env`、migration report 路径。

`hugegraph-llm/src/hugegraph_llm/config/mapping.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：处理 flat field、nested path、global dotted path、sensitive path 判定。

`hugegraph-llm/src/hugegraph_llm/config/manager.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：统一加载、effective config、field source、patch-only writer、secret env writer。

`hugegraph-llm/src/hugegraph_llm/config/migration.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：Phase 检测、迁移计划、diff、报告、备份和事务写入编排。

`hugegraph-llm/src/hugegraph_llm/config_migrate.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：CLI 入口，暴露 `doctor`、`plan`、`diff`、`apply`、`export-env`。

`hugegraph-llm/config.example.yaml`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：嵌套 YAML 示例，只包含非敏感值。

`hugegraph-llm/src/tests/config/test_config_v1_contract.py`

- 类型：新增路径；当前分支存在时按职责复核。
- 目标职责：V1 配置合同测试，覆盖 no-write-on-read、secret-only、patch-only、迁移和文档示例。

`hugegraph-llm/pyproject.toml`

- 类型：拟修改。
- 目标职责：注册 `hugegraph-llm-config` CLI。

`.gitignore`

- 类型：拟修改。
- 目标职责：忽略真实 `config.yaml`、secret `.env`、备份和本地迁移产物。

## 3. V1 需求边界

### 3.1 V1 目标

V1 计划交付以下能力：

1. 用户面向配置迁移到嵌套语义化 `config.yaml`。
2. `.env` 只承载 API key、token、password、pwd、secret 等敏感值。
3. 固定优先级：`process env > .env secret > config.yaml > defaults`。
4. 建立 persisted/effective 双层边界，确保 env 来源 secret 永不写回 YAML。
5. 建立配置键元数据：section、flat field、nested path、env alias、默认值、敏感性、可写性。
6. 保持旧 settings 读取兼容，降低业务消费面改造半径。
7. 计划提供 patch-only 写盘入口，拒绝 full dump、section dump、unknown path、metadata key 和 sensitive path。
8. 计划提供 Phase0/Phase1/Phase2 迁移检测、计划、diff、apply 和报告。
9. 更新最小用户文档，明确 `config.yaml`、secret-only `.env` 和 Docker compose `.env` 的区别。

### 3.2 V1 非目标

以下不作为 V1 合并或收口阻塞项：

- PromptConfig 完整生命周期。
- 完整 Gradio UI 体验重构。
- 全仓库去全局 settings。
- request-scoped graph config 全链路隔离。
- 自动 rollback CLI。
- hot reload。
- 部署 grep gate 和发布级文档审计。

## 4. 关键决策

### 4.1 配置文件语义

- `config.example.yaml`：示例配置，只包含非敏感值，需要提交。
- `config.yaml`：用户非敏感运行配置，不提交。
- `.env`：本地 secret-only 文件，不提交。
- `migration-reports/*.json`：可审计迁移结果，不提交。
- `migration-reports/*.md`：人类可读迁移结果，不提交。

### 4.2 `.env` 共存决策矩阵

process env + 已知敏感 key：

- 参与 effective config。
- 不写入 YAML。
- 最高优先级，标记 process override。

process env + 已知非敏感 key：

- 参与 effective config。
- 不写入 YAML。
- 最高优先级，用于临时覆盖。

`.env` + 已知敏感 allowlist：

- 参与 effective config。
- 不写入 YAML。
- 标记 dotenv secret。

`.env` + 已知非敏感 legacy key：

- 不参与 effective config。
- 不写入 YAML。
- 进入 migration warning/report，提示迁移到 YAML。

`.env` + unknown sensitive-like key：

- 不参与 effective config。
- 不写入 YAML。
- report 为 unknown，不自动生效。

`.env` + unknown non-sensitive key：

- 不参与 effective config。
- 不写入 YAML。
- report 为 ignored unknown。

`config.yaml` + 非敏感 path：

- 参与 effective config。
- 可写入 YAML。
- 作为 persisted config。

`config.yaml` + 敏感 path `null`：

- 不构成 secret。
- 可省略或保留 `null`。
- 只用于可发现性。

### 4.3 patch-only 写盘契约

正确用法：

```python
llm_config.update_config({"openai_chat_language_model": "gpt-4.1"})
config_manager.update_config({"llm.openai.chat.language_model": "gpt-4.1"})
```

禁止用法：

```python
llm_config.update_config(llm_config.model_dump())
config_manager.update_config({"llm": {"openai": {"chat": {"language_model": "gpt-4.1"}}}})
config_manager.update_config({"llm.openai.chat.api_key": "sk-..."})
```

硬契约：

- 主判定机制必须是“允许路径白名单”，不是 patch key 数量猜测。
- `BaseConfig.update_config()` 只接受 section-local flat leaf patch。
- `ConfigManager.update_config()` 只接受全局 dotted leaf patch。
- patch value 必须是 leaf value，禁止 section object、nested mapping、effective config 聚合结构和 model dump。
- 禁止 sensitive key path、metadata key、unknown path。
- `save()` 只序列化 persisted config。

入口形状：

- `BaseConfig.update_config(patch)` 只允许 section-local flat leaf keys，例如 `{"openai_chat_language_model": "gpt-4.1"}`。不允许 dotted path、多 section 聚合结构、nested mapping、完整 section dump、model dump。
- `ConfigManager.update_config(patch)` 只允许全局 dotted leaf path，例如 `{"llm.openai.chat.language_model": "gpt-4.1"}`。不允许根 section object、nested mapping、effective config full dump、模型 dump 聚合结构。

## 5. 设计方向

### 5.1 配置键元数据

每个配置类声明三类元数据：

```python
_config_section = "llm"
_flat_to_nested_mapping = {
    "openai_chat_language_model": "openai.chat.language_model",
    "openai_chat_api_key": "openai.chat.api_key",
}
_env_var_map = {
    "openai_chat_api_key": ["OPENAI_CHAT_API_KEY", "OPENAI_API_KEY"],
}
_mutable_persisted_fields = {"openai_chat_language_model"}
```

统一归一化为全局 dotted path：

```text
openai_chat_language_model -> llm.openai.chat.language_model
openai_chat_api_key        -> llm.openai.chat.api_key
```

### 5.2 有效配置事实源

persisted config：

- 来源：`config.yaml` + explicit persisted patch。
- 可写：是。
- 用途：非敏感声明式配置。

effective config：

- 来源：defaults <- YAML <- `.env` secret <- process env。
- 可写：否。
- 用途：运行时最终配置。

旧 settings 不直接成为事实源，而是计划改造成兼容 facade。业务代码可以继续读 `llm_settings.openai_chat_language_model`，但读取结果应来自当前 effective config。

### 5.3 迁移工作流

迁移命令遵循：

```text
doctor -> plan -> diff -> apply
```

要求：

- `doctor` 只判断当前 phase 和风险，不写文件。
- `plan` 只输出迁移计划，不写文件。
- `diff` 输出迁移前后差异，并对 secret 脱敏。
- `apply --yes` 才允许写入。
- 写入前必须完成校验；校验失败不得创建或覆盖目标文件。
- 备份文件名包含 `migration_id`。
- 报告同时输出 Markdown 和 JSON。

### 5.4 实现方法与路径

配置目录解析：

- 实现方法：新增 resolver；优先读取 `HUGEGRAPH_LLM_CONFIG_DIR`，兼容 `HUGEGRAPH_AI_CONFIG_DIR`，默认回到模块目录，不使用 CWD fallback。
- 主要路径：`config/paths.py`、`config/models/base_config.py`、`config/models/base_prompt_config.py`。

配置键元数据：

- 实现方法：在各配置类声明 section、flat-to-nested、env alias、mutable fields；注册后派生 global dotted path 和 allowlist。
- 主要路径：`config/llm_config.py`、`config/hugegraph_config.py`、`config/admin_config.py`、`config/index_config.py`、`config/mapping.py`。

effective config：

- 实现方法：从 defaults、`config.yaml`、secret `.env`、process env 合并；同时记录字段来源，不把 effective config 当作可写对象。
- 主要路径：`config/manager.py`、`config/__init__.py`。

旧入口兼容：

- 实现方法：保留 `llm_settings` 等全局入口；读取时从 effective config 初始化 section model；旧 wrapper 只作为兼容路径。
- 主要路径：`config/__init__.py`、`config/models/base_config.py`。

secret-only `.env`：

- 实现方法：`.env` 只接受 allowlisted sensitive key；非敏感 legacy key 只进入迁移报告，不参与正常 override。
- 主要路径：`config/manager.py`、`config/migration.py`。

patch-only 写盘：

- 实现方法：`BaseConfig.update_config()` 接受 section-local flat leaf；`ConfigManager.update_config()` 接受 global dotted leaf；所有路径走 allowlist 校验和 atomic save。
- 主要路径：`config/models/base_config.py`、`config/manager.py`、`config/mapping.py`。

迁移 CLI：

- 实现方法：CLI 调用 migration service；`doctor/plan/diff` 只读，`apply --yes` 先校验再备份和写入，失败不产生副作用。
- 主要路径：`config_migrate.py`、`config/migration.py`、`config/manager.py`、`pyproject.toml`。

Gradio 写回分流：

- 实现方法：收集 UI 更新后按敏感性分流；非敏感值写 `config.yaml`，API key、token、password 写 secret `.env`。
- 主要路径：`demo/rag_demo/configs_block.py`、`config/manager.py`。

prompt 最小兼容：

- 实现方法：主配置迁移不触发 prompt 写盘；只有显式 generate/save 才创建或更新 prompt YAML。
- 主要路径：`config/generate.py`、`config/models/base_prompt_config.py`。

文档与示例：

- 实现方法：用户手册说明新配置语义，迁移指南说明命令和备份，示例 YAML 不含非空 secret。
- 主要路径：`hugegraph-llm/config.md`、`hugegraph-llm/config-migration-upgrade-guide.md`、`hugegraph-llm/config.example.yaml`、`hugegraph-llm/README.md`。

合同测试：

- 实现方法：使用 `tmp_path` 构造配置目录；验证导入不写盘、secret 不落盘、patch 拒绝规则、迁移报告和示例合法性。
- 主要路径：`hugegraph-llm/src/tests/config/test_config_v1_contract.py`。

## 6. 任务拆分

### M0. 主线基线矩阵

目标：先固定真实起点，避免实现基于错误假设展开。

产出：

- baseline matrix：配置类、全局对象、config 文件、默认值来源。
- freeze matrix：API request model、operator、node、flow 中可能 import-time 冻结的配置；每个冻结点必须标注 `V1 处理`、`V1.1 延后` 或 `不适用`。
- write-entry matrix：所有 `.env` / YAML 写入口。
- migration matrix：Phase0 `.env`、Phase1 flat YAML、Phase2 nested YAML 共存场景。
- docs/deploy matrix：README、Docker compose、Helm、workflow 中的 `.env` 语义。

出口条件：每个矩阵能映射到具体文件和后续任务；freeze matrix 不把处理决策留到实现期临时判断。

### M1. no-write-on-read 与路径解析

目标：配置导入和构造只读。

任务：

- 移除 `BaseConfig.__init__` 中的写盘行为。
- `.env` 只读加载，不自动创建。
- 明确 `HUGEGRAPH_LLM_CONFIG_DIR` 与 `HUGEGRAPH_AI_CONFIG_DIR` 的优先级。
- 禁止 CWD fallback。
- Prompt YAML 只在显式生成入口中创建。

出口条件：导入 `hugegraph_llm.config` 不创建 `.env`、`config.yaml` 或 prompt YAML。

### M2. 配置键元数据与旧入口兼容

目标：建立有效配置事实源，同时保留旧 settings 入口。

任务：

- 为 `LLMConfig`、`HugeGraphConfig`、`AdminConfig`、`IndexConfig` 补齐 mapping/env/mutable 元数据。
- 建立 global dotted path registry。
- 构建 effective config 和 field source map。
- 让旧全局 settings 从 effective config 读取。
- 保留 deprecated wrapper，但写入必须受安全规则约束。

出口条件：旧属性读取继续工作，元数据覆盖审计通过。

### M3. secret-only `.env` 与 patch-only writer

目标：把 secret 和非敏感持久化边界落到代码。

任务：

- `.env` 只允许 known sensitive key 参与 override。
- 非敏感 legacy `.env` key 不覆盖 YAML。
- 空字符串不覆盖有效值。
- 类型转换失败 fail-fast。
- `update_config()` 只接受 leaf patch。
- 拒绝 sensitive path、unknown path、metadata key、full dump、section dump、nested mapping。
- 写盘使用 temp + fsync + atomic rename。

出口条件：secret-only、patch-only、失败无副作用测试通过。

### M4. Migration CLI

目标：让旧配置迁移可预览、可审计、可回退到备份。

任务：

- 新增 `doctor`、`plan`、`diff`、`apply`、`export-env`。
- Phase0 legacy `.env` 可迁移。
- Phase1 flat YAML 可迁移。
- Phase2 nested YAML 直接读取。
- 报告包含 `migration_id`、`backup_files`、`persisted_keys`、`sensitive_keys_retained`、`unknown_keys`、`ignored_env_keys`。
- secret 值在 diff、report、log 中统一脱敏。

出口条件：Phase0/Phase1/Phase2 主路径和失败路径测试通过。

### M5. 消费面收口

目标：处理本次改造直接触达的高风险消费面，不扩大到全仓库重构。

任务：

- Gradio 主要写回路径改为非敏感写 YAML、敏感写 `.env`。
- 对已落地的 `_persist_config_updates()` 分流实现进行复核，确保测试和文档口径一致。
- 旧 `update_env()` 调用只保留兼容用途。
- role 级联逻辑不得从 CWD `.env` 读取。
- API/operator 默认值冻结点按 M0 freeze matrix 的标签执行；`V1 处理` 项按 runtime 读取收口，`V1.1 延后` 项不得临时扩大进 V1。

出口条件：Gradio 写回不污染 YAML，freeze matrix 每个冻结点都有处理标签。

### M6. 文档与示例

目标：文档口径和实现语义一致。

任务：

- `config.example.yaml` 只包含非敏感值。
- `config.md` 说明 `config.yaml`、secret-only `.env`、优先级和配置字段。
- `config-migration-upgrade-guide.md` 说明迁移命令、备份、报告和手动回滚。
- README 不再把 `.env` 描述为通用配置文件。
- 区分 Docker compose `.env` 与 HugeGraph-LLM runtime `.env`。

出口条件：文档不出现旧 `.env` 全量配置口径，示例不包含非空 secret。

### M7. 收口验证

目标：通过测试和审计证明 V1 闭环达到可交付标准。

必跑：

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest hugegraph-llm/src/tests/config/ -v --tb=short
uv run ruff format --check .
uv run ruff check .
```

触及 Gradio、operators、indices、API 时补跑对应 split。

## 7. 测试 Gate

P0：

- 范围：no-write-on-read、secret-only、patch-only、迁移安全、路径解析。
- 要求：必须自动化覆盖；迁移链路必须包含 `doctor -> plan -> diff -> apply --yes -> export-env` 的端到端 CLI smoke gate。

P1：

- 范围：Gradio 主要写回路径、旧 wrapper 兼容、report redaction。
- 要求：必须有回归测试或明确手工验证。

P2：

- 范围：README/Docker/Helm 全量文档审计、Prompt 全生命周期、hot reload。
- 要求：不阻塞 V1，列入后续。Helm 全量审计属于范围裁剪项，需要在后续计划中单独确认。

最低测试清单：

- `test_config_import_does_not_write_files`
- `test_dotenv_secret_only_does_not_override_non_sensitive_yaml`
- `test_process_env_overrides_yaml`
- `test_update_config_rejects_full_dump`
- `test_update_config_rejects_section_dump`
- `test_update_config_rejects_sensitive_path`
- `test_update_config_rejects_metadata_keys`
- `test_save_does_not_persist_env_secret`
- `test_phase0_env_migration_splits_sensitive_and_persisted_values`
- `test_phase1_yaml_migration_splits_sensitive_and_persisted_values`
- `test_migration_validation_has_no_side_effect`
- `test_migration_report_json_contract`
- `test_migration_end_to_end_cli_smoke`
- `test_config_example_yaml_is_valid_and_non_sensitive`

## 8. 验收标准

功能验收：

- AC-F1：配置键元数据覆盖旧字段和旧 env 名称。
- AC-F2：能返回当前 effective config 和字段来源。
- AC-F3：旧 settings 属性读取继续工作。
- AC-F4：导入配置无写盘副作用。
- AC-F5：`.env` 为 secret-only。
- AC-F6：YAML 写入为 patch-only。
- AC-F7：Phase0/Phase1/Phase2 迁移工具链可用。
- AC-F8：Gradio 主要写回路径完成敏感/非敏感分流。

安全验收：

- AC-S1：YAML、report、log、diff 不出现 secret 明文。
- AC-S2：secret 文件、备份和导出文件使用 best-effort `0600`。
- AC-S3：sensitive path 不能写入 YAML。
- AC-S4：迁移失败不改写原文件。
- AC-S5：full dump、section dump、metadata key 全部拒绝。

兼容验收：

- AC-C1：旧 `.env` 可迁移。
- AC-C2：旧 flat YAML 可迁移。
- AC-C3：新 `config.yaml` + secret `.env` 可启动。
- AC-C4：旧属性读取和主要调用点不需要一次性改造。

文档验收：

- AC-D1：配置目录位置和优先级明确。
- AC-D2：secret-only `.env` 边界明确。
- AC-D3：`config.example.yaml` 不包含非空 secret。
- AC-D4：迁移命令示例可执行。
- AC-D5：Docker compose `.env` 与 runtime `.env` 明确区分。

## 9. 延后事项

以下事项进入后续计划，不反向扩大 V1：

- PromptConfig 完整生命周期。
- request-scoped graph config。
- API request model 和 operator 默认值冻结点的全量改造。
- rollback CLI。
- hot reload。
- README/Docker/Helm/workflow 自动 grep gate。
- 全仓库去全局 settings。

## 10. 实现纪律

- 先写或更新能暴露行为风险的测试，再改实现。
- 迁移和写盘路径必须先校验再写入。
- 不用覆盖率测试替代行为验证。
- 不把 env secret、process env override、effective config 聚合结构写入 YAML。
- 不做顺手重构；每个改动必须能回到本文档中的任务和验收项。
