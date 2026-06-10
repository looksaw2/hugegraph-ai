# Config Migration V5.1 - Implementation Closure Plan

# 配置迁移 V5.1 - 实施收口文档

**Date / 日期**: 2026-06-03  
**Status / 状态**: In Progress / 进行中  
**Goal / 目标**: turn the V5.1 design document into code, tests, CI, and delivery artifacts with traceable evidence  
**目标分数**: from document-quality `9.0/10` to implementation-readiness `9.3+/10`

> This file supersedes the old V2 implementation summary.
> 此文档替代旧的 V2 “已完成实现文档”，用于驱动当前 V5.1 的实际收口工作。

---

## 1. Purpose / 目的

The V5.1 design document is now structurally strong enough to serve as the implementation baseline. The remaining gap is no longer document structure; it is execution alignment.

V5.1 方案文档已经足够完整，剩余问题主要不在“文档怎么写”，而在“文档声明是否被代码、测试、CI、交付文件真正兑现”。

This document defines:

1. what still blocks `9.3+/10`
2. which files must change
3. what tests and CI jobs must exist
4. how to prove closure with evidence

---

## 2. Current Blocking Gaps / 当前阻塞项

These are the remaining blockers preventing the work from being treated as `9.3+/10` implementation-ready.

| ID | Gap | Current State | Required Closure |
|---|---|---|---|
| B1 | `.env` runtime semantics mismatch | current code still treats `.env` primarily as one-time migration input | implement `secret-only .env` as runtime secret source with `override=False` |
| B2 | `update_config()` API mismatch | current code path persists current model state, not patch dict | implement patch-based write API with hard rejection rules |
| B3 | `persisted_config` vs `effective_config` boundary not fully enforced | document is clear, code path still coarse-grained | make save path serialize persisted values only |
| B4 | source tracking not fully materialized | document defines 7 source types, code does not yet prove full coverage | implement field source metadata and use it in fallback/write logic |
| B5 | CI gate still transitional | current workflow still relies heavily on `test_config.py -k ...` | split into stable config gate files/jobs |
| B6 | delivery artifacts missing | `config.example.yaml`, upgrade guide, grep script are design-time targets, not guaranteed files | create them as tracked files |
| B7 | traceability audit missing | no final proof that doc claims match code/workflow/files | produce claim-to-evidence matrix before closeout |

---

## 3. Definition of 9.3+ / 9.3+ 的定义

We only consider this work `9.3+/10` when the following are all true:

1. the design document, code behavior, and tests describe the same system
2. workflow gates execute the same checks the document promises
3. required user-facing artifacts exist in the repository
4. a reviewer can verify every critical claim with a concrete path

Concretely:

- `.env` semantics in code match V5.1
- `update_config()` accepts only explicit patch input
- secret values cannot leak into `config.yaml`
- PromptConfig path and read-only behavior are deterministic
- CI no longer depends on fragile test-name conventions as the only guard
- traceability evidence can be inspected without inference

---

## 4. Workstream A - Runtime Semantics and Core Code

### 4.1 Scope

Primary files:

- `hugegraph-llm/src/hugegraph_llm/config/models/base_config.py`
- `hugegraph-llm/src/hugegraph_llm/config/__init__.py`
- `hugegraph-llm/src/hugegraph_llm/config/llm_config.py`
- `hugegraph-llm/src/hugegraph_llm/config/hugegraph_config.py`
- `hugegraph-llm/src/hugegraph_llm/config/admin_config.py`
- `hugegraph-llm/src/hugegraph_llm/config/index_config.py`
- `hugegraph-llm/src/hugegraph_llm/config/prompt_config.py`
- `hugegraph-llm/src/hugegraph_llm/demo/rag_demo/configs_block.py`

### 4.2 A1 - Secret-only `.env` Runtime Semantics

Required behavior:

1. process env / K8s Secret has highest priority
2. `.env` is loaded as `secret-only`
3. `.env` must not override pre-existing process env values
4. `.env` non-sensitive legacy keys must not override YAML in Phase2

Implementation requirements:

- use `load_dotenv(..., override=False)` or equivalent behavior
- distinguish `dotenv_secret` vs `process_env_override`
- keep non-sensitive `.env` legacy keys for warning/reporting only

Acceptance:

- `process env > .env secret > config.yaml > default`
- `GRAPH_URL` in `.env` does not override Phase2 YAML
- `GRAPH_PWD` in `.env` does override YAML `null`

### 4.3 A2 - `persisted_config` vs `effective_config`

Required behavior:

- `persisted_config` contains only YAML-safe persisted values
- `effective_config` contains defaults + YAML + env overrides
- `save()` serializes persisted values only
- no code path full-dumps `effective_config` to disk

Implementation requirements:

- introduce explicit internal structures for both layers
- make write path consume persisted data, not current model state wholesale
- make env-origin fields non-serializable by policy

Acceptance:

- env secret values never appear in saved YAML
- YAML changes survive restart
- runtime env overrides remain effective but unpersisted

### 4.4 A3 - Patch-based `update_config()` API

Required API contract:

```python
BaseConfig.update_config(patch: dict[str, Any]) -> None
ConfigManager.update_config(patch: dict[str, Any]) -> None
```

Shape rules:

- `BaseConfig.update_config(patch)` accepts section-local flat keys
- `ConfigManager.update_config(patch)` accepts global dotted paths
- neither accepts model full dump
- neither accepts section dump
- neither accepts sensitive key paths

Mandatory rejection cases:

- `model_dump()` payload
- `effective_config` payload
- metadata-bearing payload
- oversized patch
- multi-section aggregate payload

Acceptance:

- `test_update_config_rejects_full_dump`
- `test_update_config_rejects_section_dump`
- `test_update_config_rejects_sensitive_keys`
- `test_update_config_rejects_metadata_keys`
- `test_update_config_rejects_effective_dump`
- `test_update_config_patch`

### 4.5 A4 - Source Tracking

Implement the seven source types from V5.1:

```text
yaml_persisted
migrated_persisted
explicit_persisted_patch
effective_default
dotenv_secret
process_env_override
runtime_only_patch
```

Required usages:

- write path filtering
- `configs_block.py` role fallback logic
- debug / audit display
- migration provenance

Acceptance:

- every managed field can report a source
- role fallback only happens when source is `effective_default`
- YAML / explicit patch values are not silently overridden by fallback logic

### 4.6 A5 - PromptConfig Path and Read-only Behavior

Required behavior:

- canonical config dir env var: `HUGEGRAPH_LLM_CONFIG_DIR`
- compatible legacy alias: `HUGEGRAPH_AI_CONFIG_DIR`
- if both are set, canonical name wins
- if `config_prompt.yaml` is missing and directory is writable, create from template
- if `config_prompt.yaml` is missing and directory is read-only, fail fast
- if file exists and is readable, startup may proceed in read-only mode
- save/update in read-only mode must fail clearly

Acceptance:

- deterministic path resolution
- deterministic first-run behavior
- deterministic read-only behavior

---

## 5. Workstream B - Tests and CI

### 5.1 Required Test Files

The V5.1 document now names stable target files. These must exist as real files, not just conceptual buckets.

Required targets:

- `hugegraph-llm/src/tests/config/test_contract.py`
- `hugegraph-llm/src/tests/config/test_migration.py`
- `hugegraph-llm/src/tests/config/test_rollback.py`
- `hugegraph-llm/src/tests/config/test_mapping_audit.py`
- `hugegraph-llm/src/tests/config/test_env_coverage.py`
- `hugegraph-llm/src/tests/config/test_write_path_audit.py`

Minimum coverage by file:

| File | Purpose |
|---|---|
| `test_contract.py` | nested YAML contract, patch save contract, masking |
| `test_migration.py` | Phase0 / Phase1 / coexistence migration behavior |
| `test_rollback.py` | file rollback, semantic rollback, idempotence |
| `test_mapping_audit.py` | `_flat_to_nested_mapping` and `_env_var_map` coverage |
| `test_env_coverage.py` | env priority, alias order, read-only behavior, cwd independence |
| `test_write_path_audit.py` | full dump rejection, section dump rejection, secret leakage prevention |

### 5.2 Required CI Gates

Primary workflow:

- `.github/workflows/hugegraph-llm.yml`

Required gate names:

- `config-contract`
- `config-migration`
- `config-mapping-audit`
- `config-env-coverage`
- `config-deploy-grep`
- `config-write-path-audit`

Required characteristics:

1. each gate has a concrete command
2. each gate has a single clear failure meaning
3. each gate is independently visible in CI logs
4. these gates are not collapsed into one `-k` filter step in the final state

### 5.3 Deploy Grep Gate

Required script:

- `scripts/config_deploy_grep.sh`

It should verify:

- README no longer describes `.env` as general config storage
- compose and Helm files do not drift back to old `.env` semantics
- deprecated guidance strings are absent or intentionally annotated

---

## 6. Workstream C - User-facing Artifacts

### 6.1 Required Files

These files must exist in the repository before declaring closeout:

- `hugegraph-llm/config.example.yaml`
- `hugegraph-llm/config-migration-upgrade-guide.md`

### 6.2 `config.example.yaml`

Requirements:

- contains non-sensitive example values only
- shows nested Phase2 structure
- explicitly marks secret fields as `.env` / env-only
- is suitable for README and deployment docs to reference directly

### 6.3 Upgrade Guide

Required file:

- `hugegraph-llm/config-migration-upgrade-guide.md`

Required sections:

1. backup
2. migration
3. verification
4. rollback

Must include:

- `migration_id` meaning and naming pattern
- file-level rollback commands
- semantic rollback explanation
- secret-only `.env` caveat

---

## 7. Workstream D - Traceability Audit

### 7.1 Purpose

Before declaring `9.3+`, create a final claim-to-evidence matrix.

### 7.2 Evidence Types

Only accept these evidence types:

- code path
- test name
- workflow gate
- tracked file

### 7.3 Required Matrix Shape

| Claim | Evidence Type | Path / Name | Verified |
|---|---|---|---|
| `.env` does not override process env | test | `test_process_env_beats_dotenv` | yes/no |
| env secret not persisted to YAML | test + code | `test_secret_not_in_yaml`, save path | yes/no |
| patch API rejects full dump | test + code | rejection tests, update path | yes/no |
| PromptConfig read-only behavior is deterministic | test + code | prompt config tests | yes/no |
| CI gate proves migration behavior | workflow | `config-migration` | yes/no |
| user-facing sample config exists | file | `hugegraph-llm/config.example.yaml` | yes/no |
| upgrade guide exists | file | `hugegraph-llm/config-migration-upgrade-guide.md` | yes/no |

### 7.4 Exit Rule

If any claim cannot be tied to a concrete path, the implementation is not ready for `9.3+`.

---

## 8. Execution Order / 执行顺序

### Stage 1 - Core Runtime Semantics

1. fix `.env` runtime semantics
2. introduce `persisted_config` / `effective_config`
3. implement patch-based `update_config()`
4. implement source tracking
5. settle PromptConfig path rules

Exit criteria:

- core config tests can be written without ambiguity

### Stage 2 - Split Tests and CI

1. extract config tests into stable target files
2. add write-path audit tests
3. add rollback tests
4. split workflow into visible config gates
5. add deploy grep script

Exit criteria:

- config gates run independently in workflow

### Stage 3 - User-facing Artifacts

1. add `hugegraph-llm/config.example.yaml`
2. add `hugegraph-llm/config-migration-upgrade-guide.md`
3. align README, `config.md`, Docker and Helm references

Exit criteria:

- all document-promised files exist in the repository

### Stage 4 - Traceability Audit

1. build claim-to-evidence matrix
2. verify every critical V5.1 promise
3. run final lint + config gates

Exit criteria:

- no unproven claim remains

---

## 9. Definition of Done / 完成定义

The work is done only when all of the following are true:

1. `base_config.py` semantics match the V5.1 design
2. patch-based save path is the only persisted update path
3. `.env` secret-only semantics are enforced in runtime and migration
4. stable config test files exist
5. workflow has named config gates
6. `config.example.yaml` exists
7. upgrade guide exists
8. traceability matrix is complete
9. lint and config gates pass

Anything less is still intermediate.

---

## 10. Non-goals / 非目标

These remain out of scope for this closeout:

- hot reload
- watcher threads
- auto-rebuilding long-lived external clients after config change
- dynamic OpenAPI defaults beyond the documented runtime strategy

---

## 11. Immediate Next Changes / 紧接着要改的内容

If implementation starts now, change in this order:

1. `hugegraph-llm/src/hugegraph_llm/config/models/base_config.py`
2. `hugegraph-llm/src/tests/config/` split files
3. `.github/workflows/hugegraph-llm.yml`
4. `scripts/config_deploy_grep.sh`
5. `hugegraph-llm/config.example.yaml`
6. `hugegraph-llm/config-migration-upgrade-guide.md`
7. traceability matrix document or section

This order minimizes rework and makes review easier.
