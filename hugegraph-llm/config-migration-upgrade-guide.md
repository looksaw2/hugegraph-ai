# HugeGraph-LLM Configuration Migration Guide

This guide describes how to migrate from the legacy flat `.env` or flat YAML configuration to the current `config.yaml` plus secret-only `.env` layout.

## What Changes

HugeGraph-LLM now separates regular runtime configuration from secrets:

| File | Purpose | Commit |
|---|---|---|
| `config.example.yaml` | Example non-secret configuration | Yes |
| `config.yaml` | Local non-secret runtime configuration | No |
| `.env` | Local secrets such as API keys, tokens, and passwords | No |
| `migration-reports/<migration_id>.json` | Machine-readable migration report | No |
| `migration-reports/<migration_id>.md` | Human-readable migration report | No |

Runtime config is resolved from the config base directory. Set `HUGEGRAPH_LLM_CONFIG_DIR` when the files should live outside the module directory:

```bash
export HUGEGRAPH_LLM_CONFIG_DIR=/opt/hugegraph-llm-config
```

`HUGEGRAPH_AI_CONFIG_DIR` is still accepted as a deprecated alias. If both are set, `HUGEGRAPH_LLM_CONFIG_DIR` wins.

## Precedence

Effective runtime configuration is built in this order:

```text
process environment
  > .env secrets
  > config.yaml
  > defaults
```

Only known sensitive keys in `.env` override runtime config. Non-sensitive legacy `.env` keys are migration input only; they do not override `config.yaml` during normal reads.

## Supported Inputs

The migration command recognizes these layouts:

| Phase | Input | Result |
|---|---|---|
| Phase0 | Legacy flat `.env` only | Non-sensitive values move to `config.yaml`; secrets remain in `.env` |
| Phase1 | Flat class-name YAML | Non-sensitive values move to nested `config.yaml`; secrets move to `.env` |
| Phase2 | Nested `config.yaml` | Used directly |

Importing `hugegraph_llm.config` is read-only. It does not create `config.yaml`, rewrite `.env`, create prompt files, or write migration reports.

## Migration Workflow

Start with read-only checks:

```bash
hugegraph-llm-config --config-dir /path/to/config doctor
hugegraph-llm-config --config-dir /path/to/config plan
hugegraph-llm-config --config-dir /path/to/config diff
```

Apply the migration only after reviewing the plan:

```bash
hugegraph-llm-config --config-dir /path/to/config apply --yes
```

The module entrypoint is also available:

```bash
uv run python -m hugegraph_llm.config_migrate --config-dir /path/to/config doctor
```

Migration writes are validated before side effects. If validation fails, the command does not create or overwrite `config.yaml`, `.env`, backups, or reports.

Backups include the migration id:

```text
.env.bak.pre-phase-2.<migration_id>
config.yaml.bak.pre-phase-2.<migration_id>
```

Secret files and migration backups are written with best-effort `0600` permissions.

## Generating Local Config

To materialize current non-secret settings into `config.yaml` and ensure the prompt YAML exists, run:

```bash
env HUGEGRAPH_LLM_CONFIG_DIR=/path/to/config uv run python -m hugegraph_llm.config.generate
```

This command does not copy secret values from `.env` or process environment into YAML.

## Rollback

There is no automatic rollback command yet. Use the migration report and backup files:

1. Stop the service.
2. Open the latest report under `migration-reports/`.
3. Restore the files listed in `backup_files`.
4. Remove or archive generated files that should not remain active.
5. Restart the service with the intended config base directory.

Review reports before sharing them. They redact secret values, but may still contain local paths and key names.

## Docker Compose `.env`

Docker compose `.env` files are used by Docker for variable interpolation. HugeGraph-LLM runtime `.env` is the secret-only file under `HUGEGRAPH_LLM_CONFIG_DIR`.

Keep them separate when possible:

```text
project/.env                         # compose interpolation, if needed
/opt/hugegraph-llm-config/.env       # HugeGraph-LLM secrets
/opt/hugegraph-llm-config/config.yaml
```

## Write Path Notes

The web configuration page stores values through the current config manager:

| Value | Destination |
|---|---|
| Non-sensitive UI settings | `config.yaml` |
| API keys, tokens, passwords | `.env` |

Deprecated wrappers such as `generate_env()`, `update_env()`, and `check_env()` remain for compatibility, but new code should write explicit config patches instead.
