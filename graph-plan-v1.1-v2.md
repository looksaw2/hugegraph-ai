# HugeGraph-AI 配置系统迁移后续计划：V1.1 / V2

**关联 V1 计划**: `graph-plan.md`  
**适用模块**: `hugegraph-llm/`  
**原则**: 本文件只承载 V1 核心配置闭环之外的后续能力，不反向扩大 V1 hard gate。

V1 计划聚焦 nested `config.yaml`、secret-only `.env`、配置优先级、迁移、patch-only 写盘、secret 不落盘、路径解析和最小 PromptConfig 兼容。以下事项从 V1 中剥离，作为 V1.1 / V2 单独推进。

## 一、V1.1 计划

### 1. PromptConfig 完整生命周期

目标：把 `config_prompt.yaml` 从 V1 的“最小兼容”提升为完整、可测试、可部署的用户配置生命周期。

任务：

- 统一 `config_prompt.yaml` 与 `config.yaml` 的 config base dir 策略。
- 明确 package template、用户可写文件、只读部署目录之间的边界。
- 补充只读目录、模板复制、显式保存、package resource 不写回测试。
- 补充部署说明，解释 prompt 文件在容器、K8s ConfigMap、只读镜像中的推荐挂载方式。

验收：

- PromptConfig 初始化不依赖 CWD。
- 显式保存才要求目标目录可写。
- 不向 package resource / site-packages 写入用户配置。

### 2. 消费面全面贯通

目标：把配置消费者从 deprecated wrapper 和 import-time/default-time 配置读取迁移到统一 ConfigManager/effective config 模型。

任务：

- 审计 API request model 的 import-time 默认值，改为 runtime effective config。
- 审计 operator / flow / node 的配置默认值绑定。
- 将 `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py` 中的 `update_env()` 调用迁移为显式 `update_config()` 或新的 ConfigManager API。
- 将 role 级联逻辑改为基于 `_field_source` 或等价 source tracking，避免把 env secret 写回 YAML。
- 为 demo/API/operator 消费面补对应回归测试。

需要审计的 V1 剩余调用点：

- `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py` 中的 `index_settings.update_env()`。
- `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py` 中的 `llm_settings.update_env()`。
- `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py` 中的 `huge_settings.update_env()`。

验收：

- 业务消费面不再依赖 deprecated `.env` sync wrapper。
- 仍保留 wrapper 作为兼容 API，但普通路径不再调用。
- 配置更新路径继续满足 secret 不落盘。

### 3. 部署文档与 CI Gate

目标：把 V1 的最小升级说明扩展为完整部署文档和自动化文档审计。

任务：

- 增加 config deploy grep，检查 README、compose、Helm、workflow 中 `.env` 语义。
- 扩展 `hugegraph-llm/config-migration-upgrade-guide.md`，覆盖更多部署拓扑、备份、迁移验证和文件级回滚。
- 增加 config doc audit，检查示例 YAML、升级文档和 secret 表述。
- 在 PR 模板或发布说明中记录 Ollama 外部服务测试 skip 原因和可选运行方式。

验收：

- 文档不再把 `.env` 描述为通用配置文件。
- Docker compose `.env` 与 HugeGraph-LLM runtime secret `.env` 明确区分。
- 示例 YAML 不包含任何非空 secret。

### 4. 外部服务测试 Gate

目标：把 Ollama 相关测试从普通 unit split 中明确拆为可选 integration gate，避免“0 skipped”目标和本地服务依赖混在一起。

任务：

- 为 Ollama embedding / LLM / Faiss integration 测试增加独立 marker 或命令。
- 将无条件 skip 改为按服务可用性、环境变量或 marker 控制。
- 记录所需模型：`quentinz/bge-large-zh-v1.5`、`llama3:8b-instruct-fp16`。
- 在 CI 或本地文档中说明默认 unit split 为什么跳过外部服务。

验收：

- 默认 unit split 无需 Ollama 服务即可稳定运行。
- 开启 integration gate 时，Ollama 服务不可用会明确失败或显式 skip，并输出可操作原因。

## 二、V2 计划

### 1. 自动 Rollback CLI

目标：基于 migration JSON 报告提供自动回滚命令，减少手动恢复风险。

任务：

- 基于 `migration-reports/<migration_id>.json` 实现 rollback CLI。
- 区分文件级回滚与语义回滚，避免误导用户“删除 YAML 即可回到旧 `.env` full-config 模式”。
- 支持恢复 `.env` 备份、`config.yaml` 备份和报告引用的文件。
- 补充多次迁移、失败迁移、部分文件缺失场景测试。

验收：

- rollback CLI 对缺失文件、重复执行、权限失败给出清晰错误。
- rollback 不输出 secret 明文。
- rollback 行为可从 JSON 报告稳定复现。

### 2. 热加载配置

目标：在不破坏 persisted/effective 边界的前提下，提供可控热加载。

任务：

- 设计热加载触发机制和并发安全模型。
- 明确哪些配置可热加载，哪些必须重启。
- 保持 env secret 不写回 YAML。
- 补充并发 reload、失败 reload 回滚、部分配置失效测试。

验收：

- 热加载失败不污染当前 effective config。
- 热加载不绕过 patch allowlist 和 secret policy。
- 配置消费者看到一致的 effective config 视图。

## 三、与 V1 的边界

V1.1 / V2 任务不得作为 V1 合并阻塞项。V1 只需要保留以下扩展接口：

- `_field_source`
- migration JSON report
- config base dir resolver
- global dotted leaf path mapping
- patch allowlist
- deprecated wrapper 的安全兼容行为
