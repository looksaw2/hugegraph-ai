<title>从V2升级到v3改了什么</title>

# **changes2v2.md 痛点 → 解决方案**



对 V2 plan (\`config-migration-nested-yaml-plan-zh.md\`) 评审后提出了 10 条修改意见。本文档将每条意见对应的**原 plan 问题**和**修改方案**逐一列出。



---



## **问题 1：flat↔nested mapping 仅要求 round-trip，缺少映射覆盖率验收标准**



**原 plan 问题**（第 207 行 Task 2.1）：



*Two pure functions that translate between flat pydantic field dicts and nested YAML dicts using a dot-notation mapping. Must satisfy the round-trip property and handle edge cases: fields not in the mapping, empty mapping, deeply nested paths.*

*两个纯函数，使用点号分隔的映射关系在 pydantic 扁平字段字典和嵌套 YAML 字典之间转换。必须满足往返属性，并处理边缘情况：不在映射中的字段、空映射、深层嵌套路径。*



"未映射字段保留在 top-level" 虽然能避免数据丢失，但也可能掩盖字段漏迁移，最后得到一个半嵌套半扁平的 YAML。仅要求 round-trip 不够，需要把映射覆盖率作为明确的验收标准。



**修改方案**：



- 每个 config model 的字段必须被归类为：`mapped` / `intentional top-level` / `ignored-deprecated`
- 同一个 nested path 不能被多个 flat field 映射，除非显式声明兼容 alias
- 测试中断言没有未审查的 unmapped fields
- 生成一份迁移覆盖清单，尤其覆盖 `LLMConfig` 约 55 个字段
- 把"结构次优"的问题提前变成可见的 review/CI 信号

**体现在 V3 plan**：Task 2.1 — 新增 "Mapping coverage acceptance criteria" 子节，明确字段分类契约和覆盖率检查机制；Task 7.1 — 新增 unmapped field audit 测试用例



---



## **问题 2：.env 迁移值与运行时 os.environ 边界不够清晰**



**原 plan 问题**（第 224 行 Task 2.4）：



*> \`.env\` is treated as* **one-time migration input only***. During migration, values are read from \`.env\` and written to \`config.yaml\`. After migration, \`.env\` is NOT loaded into \`os.environ\` and NOT used as an ongoing config source.*

*> \`.env\` 仅被视为***一次性迁移输入***。迁移期间，值从 \`.env\` 读取并写入 \`config.yaml\`。迁移后，\`.env\` 不再加载到 \`os.environ\`，也不再作为持续配置源。*



方向是对的，但还需要补一个更明确的边界：`.env` 迁移值和运行时 `os.environ` 不是同一种来源。否则实现时很容易重新退回到旧的 `dotenv -> os.environ -> save` 路径。



**修改方案**：



把规则写成可执行决策：



| 场景 | 行为 |
|-|-|
| 仅在没有 Phase2 nested `config.yaml` 时 | `.env` 才作为本地历史配置输入参与一次性迁移 |
| 真实运行时 `os.environ` / K8s Secret | 永远只参与 effective config，不写入 persisted config |
| `.env` 和 `os.environ` 同时存在同名 key | 最终运行值以 `os.environ` 为准，但迁移写盘值只能来自本地 `.env` 或旧 YAML |
| 迁移完成后 | 重命名或备份 `.env`（如 `.env.bak`），避免后续用户误以为它仍是持续配置源 |



**体现在 V3 plan**：Task 2.4 — 扩展为可执行决策表；Task 3.6 迁移流程 — 新增 \`.env\` 迁移后自动备份步骤



---



## **问题 3：\`init\` 写回 YAML 的触发条件需要更严格**



**原 plan 问题**（第 268 行 Task 3.3）：



*New / 新：\`ConfigManager.get_section_with_env_override()\` → merge programmatic overrides / 合并程序化覆盖 → \`BaseModel.init\` → write-back to YAML (persisted_config only) / 写回 YAML（仅 persisted_config）*



当前流程里 `get_section_with_env_override()` 返回的是 effective config，已经包含 `os.environ` 和程序化覆盖值。如果 `BaseConfig.__init__` 在构造对象后自动写回 YAML，就可能把运行时 env secret 写入磁盘，或者用默认值覆盖用户文件。



**修改方案**：



明确契约：



\- \`init\` 只负责构造运行时对象，**不自动持久化**

- 只有显式的 `update_config()` / `generate_yaml()` / migration 可以调用 `update_section()` + `save()`

\- \`update_section()\` 的输入**必须**来自 persisted-source model，**不得包含 env override**



**体现在 V3 plan**：Task 3.3 — \`init\` 流程变更中新增 "No auto-persist on init" 约束；Task 2.2 ConfigManager 方法表 — \`update_section()\` 增加输入来源约束说明



---



## **问题 4：迁移验证必须无副作用**



**原 plan 问题**（第 278 行 Task 3.6）：



*迁移阶段会调用 Pydantic 做校验，但不能复用正常 \`BaseConfig.init\`，否则可能触发单例初始化、env override、write-back、路径解析等副作用。*



**修改方案**：



明确迁移验证的实现约束：



1. 旧格式先 normalize 成 flat dict

2. 用 \`model_validate\` / \`TypeAdapter\` 做**纯校验和类型转换**（不经过 \`init\`）

3. 校验通过后再转换 nested 并**原子写入**

4. 校验失败**不得生成或覆盖** \`config.yaml\`



这能避免"迁移失败但文件已经被部分写坏"的升级事故。



**体现在 V3 plan**：Task 3.6 — 迁移流程新增 "Side-effect-free validation" 子节；§5 Risk Assessment — 新增 "Migration partially writes corrupt config.yaml" 风险项



---



## **问题 5：缺少多旧格式共存时的冲突决策表**



**原 plan 问题**（第 289 行 Task 3.6 迁移流程）：



*迁移流程只描述了单一旧格式的线性处理路径，没有覆盖"存在多个旧格式时如何选择"的场景。没有这张表的话，实现者容易按"谁先被发现就迁移谁"处理，升级结果会不可预测。*



**修改方案**：



补充完整的格式检测决策表：



| 已存在文件 | 行为 |
|-|-|
| 已存在 Phase2 nested `config.yaml` | 直接加载，不再读取 `.env` |
| 只有 Phase1 flat `config.yaml` | 迁移为 nested，并生成 `config.yaml.bak` |
| 只有 `.env` | 迁移为 nested `config.yaml`，并备份 `.env` → `.env.bak` |
| Phase1 `config.yaml` 和 `.env` 同时存在 | 以 `config.yaml` 为主，对 `.env` 差异字段打 warning |
| unknown keys / unmapped fields | 保留到 top-level 并输出可追踪 warning（含字段名和来源） |



**体现在 V3 plan**：Task 3.6 — 新增 "Multi-format conflict resolution decision table" 子节



---



## **问题 6：\`\_env_var_map\` 需从"关系列表"提升为"有序解析契约"**



**原 plan 问题**（第 336 行 Task 4）：



*Several fields share one env var — e.g., \`openai_chat_api_key\` and \`openai_extract_api_key\` both read from \`OPENAI_API_KEY\`. The \`\_env_var_map\` must centralize these relationships.*

*多个字段共享同一个环境变量 —— 如 \`openai_chat_api_key\` 和 \`openai_extract_api_key\` 都从 \`OPENAI_API_KEY\` 读取。\`\_env_var_map\` 必须集中管理这些关系。*



关键是共享 env 和字段级 env 同时存在时必须有确定优先级，否则不同角色可能读到意外的 key。这部分直接影响线上 secret 覆盖行为。



**修改方案**：



把 `_env_var_map` 提升为有序解析契约：



| 规则 | 说明 |
|-|-|
| field-level alias 优先于 provider-level/shared alias | `OPENAI_CHAT_API_KEY` > `OPENAI_API_KEY` |
| 空字符串 env 不覆盖 YAML 中的非空值 | 避免 `KEY=` 清空有效密钥 |
| 每个字段的 env aliases 按优先级保存在 list/tuple 中 | 不是无序集合 |
| 类型转换失败必须 fail-fast | 不允许退回字符串或默认值 |



**体现在 V3 plan**：Task 4 — 新增 "Env var resolution contract (ordered)" 子节，作为 P1 契约；Task 7.2 — 新增 env alias 优先级边界测试



---



## **问题 7：文档更新范围需扩展到部署入口**



**原 plan 问题**（第 379 行 Task 6）：



*| \`config.md\` | Rewrite docs for nested structure + priority; document that config changes require restart | User-facing documentation |*



这次配置来源变化会影响 README、Docker、Compose、Helm 和示例启动方式。当前仓库里 README 和 Helm values 仍有 `.env`/ConfigMap 相关路径，如果不一起改，用户会按旧方式部署，实际行为和文档会分裂。



**修改方案**：



文档更新范围从 `config.md` 扩展到全部部署入口：



| 文档 | 更新内容 |
|-|-|
| `config.md` | 嵌套结构 + 优先级 + 重启说明 |
| `README.md` | 移除 `.env` 引用，改为 `config.yaml` 说明 |
| `Dockerfile` / `docker-compose.yml` | 非敏感配置通过挂载 `config.yaml` 或 ConfigMap 注入 |
| Helm values / templates | 敏感配置继续使用 env / K8s Secret，优先级高于 YAML |
| 示例启动脚本 | 更新为新的配置方式 |
| 升级指南（新增） | 旧 `.env` 用户的升级步骤和回滚方式 |



**体现在 V3 plan**：Task 6 — 文件变更表扩展，新增部署入口文档行；Task 8（新）— "Deployment Documentation Update"



---



## **问题 8：测试清单需补充 CI 门禁和只读部署场景**



**原 plan 问题**（第 387 行 Task 7）：



*测试清单已经比上一版完整很多，但建议再补 CI 门禁和只读部署场景。需要明确哪些测试必须进 CI，而不是只作为本地验证。*



**修改方案**：



明确 CI 门禁和边界场景测试：



**CI 门禁（每次 PR 必跑）**：

- `pytest hugegraph-llm/tests/...` 覆盖迁移、env priority、secret not persisted、deprecated wrapper
- `uv run ruff check` / format check 作为基本门禁
- config path 不依赖 CWD 的测试保留为必测项

**边界场景测试**：

- 只读 `config.yaml` 或只读目录场景：启动读取应可用；只有显式 save/update 才失败并报清晰错误
- 避免配置改造只在 happy path 通过，部署到容器或只读挂载时才暴露问题

**体现在 V3 plan**：Task 7.2 — 新增 CI gate 和 read-only filesystem 测试用例；Task 7 新增 "7.3 CI Integration" 子节



---



## **问题 9：敏感信息保护需从"不写盘"扩展为完整脱敏策略**



**原 plan 问题**（第 463 行 §5 Risk Assessment）：



*Env secrets written back to config.yaml | High | \`save()\` only writes \`persisted_config\` (YAML-sourced values); \`effective_config\` (with env overrides) is read-only*



除了 `config.yaml`，迁移、校验失败、diff、`check_config()`、debug log 也可能把 secret 打出来。这属于配置系统的安全边界。



**修改方案**：



建立完整的敏感信息保护要求：



| 层面 | 策略 |
|-|-|
| 字段识别 | 字段名包含 `api_key` / `token` / `password` / `pwd` / `secret` 的值统一脱敏 |

| error message | 可以显示字段路径和来源，但**不显示原值** |

| `check_config()` / diff 输出 | secret 只展示 `***` 或 `changed`/`not changed` |

| 日志 | debug log 中不出现明文密钥 |

| 测试覆盖 | 迁移失败、env 覆盖、save、check_config 日志中均不出现明文密钥 |



**体现在 V3 plan**：§5 Risk Assessment — "Env secrets written back to config.yaml" 扩展为 "Sensitive information leaked in logs/errors/diffs"；Task 7.2 — 新增 secret masking 验证测试



---



## **问题 10（总结）：整体方向认可但实现契约需写得更硬**



**原 plan 问题**：



*当前方案已吸收上一轮核心问题，综合评分约为 7/10。剩余主要风险不在方向，而在实现契约还需要写得更硬。*



**修改方案**：



V3 重点强化的契约：



| 优先级 | 契约 |
|-|-|
| ‼️ P0 | 明确初始化不能把 env 覆盖值自动写回 YAML |
| ‼️ P0 | 明确 `.env`、运行时 env、K8s Secret 的边界 |
| ‼️ P0 | 明确 env alias 优先级和空值规则 |
| ⚠️ P1 | 补齐三格式迁移的冲突决策表和副作用边界 |
| ⚠️ P1 | 补齐映射覆盖率、部署文档、CI 门禁和敏感日志脱敏 |



**体现在 V3 plan**：§7 V1 Scope Summary — 新增 "Hardened Contracts (V3 additions)" 表格；各 Task 对应位置逐一落实上述契约



---



## **追溯矩阵**



| 问题 # | 原 plan 位置 | 核心问题 | V3 plan 对应修改位置 |
|-|-|-|-|
| 1 | Task 2.1 (行 207) | mapping 仅要求 round-trip，缺覆盖率标准 | Task 2.1 新增 "Mapping coverage acceptance criteria"；Task 7.1 新增 unmapped audit 测试 |
| 2 | Task 2.4 (行 224) | .env 迁移 vs os.environ 边界模糊 | Task 2.4 扩展为可执行决策表；Task 3.6 新增 .env 自动备份 |
| 3 | Task 3.3 (行 268) | `__init__` 写回 YAML 触发条件过松 | Task 3.3 新增 "No auto-persist on init" 约束；Task 2.2 update_section() 输入来源约束 |
| 4 | Task 3.6 (行 278) | 迁移验证可能触发副作用 | Task 3.6 新增 "Side-effect-free validation"；§5 新增部分写坏风险项 |
| 5 | Task 3.6 (行 289) | 缺少多格式冲突决策表 | Task 3.6 新增 "Multi-format conflict resolution decision table" |
| 6 | Task 4 (行 336) | `_env_var_map` 缺少有序优先级 | Task 4 新增 "Env var resolution contract (ordered)" P1 契约；Task 7.2 边界测试 |
| 7 | Task 6 (行 379) | 文档更新仅覆盖 config.md | Task 6 文件表扩展；Task 8（新）部署文档更新 |
| 8 | Task 7 (行 387) | 测试缺 CI 门禁和只读场景 | Task 7.2 新增 CI gate + read-only 测试；Task 7.3 CI Integration |
| 9 | §5 Risk (行 463) | 敏感信息保护不完整 | §5 Risk 扩展为完整脱敏策略；Task 7.2 secret masking 测试 |
| 10 | 总结 | 实现契约不够硬 | §7 新增 "Hardened Contracts (V3 additions)" 表格 |