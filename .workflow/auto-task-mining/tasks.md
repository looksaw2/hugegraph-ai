# 实现计划: Config Migration V2 — 领导反馈修订

## 研究结论

当前代码库已部分实现 OmegaConf 迁移，但存在与 V2 plan 不符的设计问题：

- `base_config.py`: ConfigManager 已有 singleton、flat↔nested 转换、BaseConfig 基类
- 4 个 config 类 (`LLMConfig`, `HugeGraphConfig`, `AdminConfig`, `IndexConfig`) 已定义 `_config_section` 和 `_flat_to_nested_mapping`
- **需要修改**: 移除热加载设施、两层分离、.env 策略收紧、fail fast、Phase1 迁移、CWD 修复

---

- [x] 1. **移除热加载基础设施** `[优先级: 高]`

  - [x] 1.1. 从 `ConfigManager` 移除 `_start_file_watcher()`, `reload()`, `register_reload_target()`, `_stop_file_watcher()` 及所有 watcher 相关属性 (`_watching`, `_watcher_thread`, `_last_mtime`, `_reload_targets`, `_reload_lock`) `(关联需求: changes1v1 #2, #5)`
  - [x] 1.2. 从 `AdminConfig` 移除 `config_reload_interval` 字段 `(关联需求: changes1v1 #5)`
  - [x] 1.3. 移除 `import threading`, `import time`（如不再需要） `(依赖于: 1.1)`

- [x] 2. **ConfigManager 两层分离 (persisted_config / effective_config)** `[优先级: 高]` `(依赖于: 1.1)`

  - [x] 2.1. 将 `_cfg` 重命名为 `_persisted_cfg`，明确其只包含 YAML 来源的配置 `(关联需求: changes1v1 #3)`
  - [x] 2.2. 修改 `save()` 只写 `_persisted_cfg`，确保 env-sourced secret 不会落盘 `(关联需求: changes1v1 #3)`
  - [x] 2.3. 修改 `update_section()` 只更新 `_persisted_cfg`（不包含 env override） `(关联需求: changes1v1 #3)`
  - [x] 2.4. `get_section_with_env_override()` 保持从 YAML 读取 + env override 合并，但不修改 `_persisted_cfg` `(关联需求: changes1v1 #3)`

- [x] 3. **.env 策略收紧：仅作一次性迁移输入** `[优先级: 高]` `(依赖于: 2.1)`

  - [x] 3.1. 移除 `__init__` 中将 `.env` 注入 `os.environ` 的逻辑（第 118-120 行） `(关联需求: changes1v1 #3)`
  - [x] 3.2. `.env` 仅在 `_migrate_from_env()` 中作为迁移数据源读取，迁移后不再使用 `(关联需求: changes1v1 #3)`

- [x] 4. **Fail Fast 策略：配置错误不静默回退** `[优先级: 高]` `(依赖于: 2.4)`

  - [x] 4.1. `__init__` 中 YAML 加载失败时抛出明确异常，不再 `OmegaConf.create({})` 静默继续 `(关联需求: changes1v1 #7)`
  - [x] 4.2. `get_section_with_env_override()` 中 env 类型转换失败时抛出 `ValidationError`，不再静默保留字符串值 `(关联需求: changes1v1 #7)`

- [x] 5. **Phase1 flat YAML 迁移支持** `[优先级: 中]` `(依赖于: 2.1)`

  - [x] 5.1. 实现 `_detect_config_format()` 方法：自动识别 Phase0 (.env) / Phase1 (flat, class-name sections) / Phase2 (nested) `(关联需求: changes1v1 #4)`
  - [x] 5.2. 实现 `_migrate_from_phase1_yaml()` 方法：将 Phase1 格式（类名节 + ALL_CAPS 键）转为 Phase2 嵌套格式 `(关联需求: changes1v1 #4)`
  - [x] 5.3. 集成迁移流程：`detect → normalize → validate → convert → write .bak → atomic replace` `(依赖于: 5.1, 5.2)`

- [x] 6. **修复 CWD 依赖** `[优先级: 中]`

  - [x] 6.1. 将 `YAML_PATH` 和 `ENV_PATH` 从 `os.getcwd()` 改为基于项目根目录的固定路径 `(关联需求: changes1v1 #6)`
  - [x] 6.2. 在 `BaseConfig.generate_yaml()` 中使用相同的固定路径逻辑 `(依赖于: 6.1)`

- [x] 7. **修复 BaseConfig.**init** 中 env override 被写回的问题** `[优先级: 高]` `(依赖于: 2.3)`

  - [x] 7.1. `__init__` 中移除 `register_reload_target()` 调用 `(关联需求: changes1v1 #2)`
  - [x] 7.2. 确保 `__init__` 中的 `update_section()` + `save()` 只写入 YAML 来源的值，不写入 env override `(关联需求: changes1v1 #3)` `(依赖于: 2.3)`

- [x] 8. **更新测试** `[优先级: 中]` `(依赖于: 4.2, 5.3)`

  - [x] 8.1. 更新现有测试以适配 fail fast 行为（无效 YAML → 抛异常） `(关联需求: changes1v1 #7)`
  - [x] 8.2. 新增测试: `os.environ` 覆盖 YAML 值 `(关联需求: changes1v1 #6)`
  - [x] 8.3. 新增测试: env-sourced secret 不保存到 `config.yaml` `(关联需求: changes1v1 #6)`
  - [x] 8.4. 新增测试: Phase1 flat YAML 迁移到 nested YAML `(关联需求: changes1v1 #6)`
  - [x] 8.5. 新增测试: corrupt YAML 启动时 fail fast `(关联需求: changes1v1 #6)`
  - [x] 8.6. 新增测试: deprecated wrapper 兼容性 `(关联需求: changes1v1 #6)`
  - [x] 8.7. 新增测试: `.env` 迁移不写入 `os.environ` `(关联需求: changes1v1 #6)`
  - [x] 8.8. 新增测试: empty env 不清空 YAML 非空 secret `(关联需求: changes1v1 #6)`
  - [x] 8.9. 新增测试: config path 不依赖 CWD `(关联需求: changes1v1 #6)`

- [x] 9. **端到端验证** `[优先级: 低]` `(依赖于: 1.1, 2.2, 3.1, 4.1, 5.3, 6.1, 7.1)`

  - [x] 9.1. 运行完整测试套件，确保所有现有测试通过 `(依赖于: 8.1)`
  - [x] 9.2. 手动验证: 删除 `config.yaml`，从 `.env` 迁移启动，确认生成正确的 nested YAML `(依赖于: 5.3)`
  - [x] 9.3. 手动验证: 删除 `config.yaml`，从 Phase1 flat YAML 迁移启动，确认生成正确的 nested YAML `(依赖于: 5.3)`
  - [x] 9.4. 手动验证: 设置 `OPENAI_API_KEY` 环境变量，确认不会被写入 `config.yaml` `(依赖于: 3.1)`
