# AGENTS.md

Guidance for AI agents working in this repository. Keep README content in README files; keep this file focused on decisions agents commonly get wrong.

## Stack & Modules

- This is a Python `uv` workspace. Prefer root-level workspace commands unless a module-specific file says otherwise.
- `hugegraph-llm/` is the primary and most frequently changed module. When editing or reviewing it, read `hugegraph-llm/AGENTS.md` first.
- `hugegraph-python-client/` is a supporting dependency for HugeGraph access. Change it only when the client contract itself must change, and verify `hugegraph-llm` callers when you do.
- Treat `hugegraph-ml/` and `vermeer-python-client/` as lower-frequency modules. Do not expand changes into them without a direct reason.

## Testing Expectations

- Any code change must include sufficient and effective test coverage for the changed behavior, regression risk, or failure path.
- Do not add tests that only improve coverage numbers while mocking away the behavior being changed.
- If a change cannot reasonably include automated tests, state why and provide the manual verification performed.
- Cross-module or shared dependency changes must test the affected downstream module, not only the package where the edit was made.
- Do not silently skip integration failures. Use explicit skip controls only when the task is not validating that external service path, and report the skip in the handoff.

## Code Search Anchors

- `hugegraph-llm/src/hugegraph_llm/` - main LLM, RAG, KG, prompt, API, and vector-index code.
- `hugegraph-python-client/src/pyhugegraph/` - Python client used by LLM code to talk to HugeGraph.
- `pyproject.toml` and module `pyproject.toml` files - workspace membership, dependency groups, lint settings, Python versions.
- `rules/README.md` - staged AI-assisted workflow for multi-file features, API contract changes, or cross-module design changes.

## Build & Test

```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
```

- Run tests for the affected module rather than defaulting to a full-repository test sweep.
- For `hugegraph-llm`, read `hugegraph-llm/AGENTS.md` first and use its CI split. The common module commands are run from `hugegraph-llm/`:

```bash
SKIP_EXTERNAL_SERVICES=true uv run pytest src/tests/config/ src/tests/document/ src/tests/middleware/ src/tests/operators/ src/tests/models/ src/tests/indices/ src/tests/test_utils.py -v --tb=short
SKIP_EXTERNAL_SERVICES=true uv run pytest src/tests/integration/test_graph_rag_pipeline.py src/tests/integration/test_kg_construction.py src/tests/integration/test_rag_pipeline.py -v --tb=short
```

- For `hugegraph-python-client`, include the smallest relevant client tests while iterating. Full API tests require a local HugeGraph Server unless the specific test is mock-only:

```bash
uv run pytest hugegraph-python-client/src/tests/api/test_response_validation.py hugegraph-python-client/src/tests/api/test_auth_routing.py -v --tb=short
uv run pytest hugegraph-python-client/src/tests -v --tb=short
```

- Client contract changes must also run or justify the affected `hugegraph-llm` caller tests. Do not stop at client package tests when LLM behavior imports or depends on the changed API.
- `hugegraph-python-client` API tests assume HugeGraph is reachable at `http://127.0.0.1:8080`, graph `hugegraph`, user `admin`, password `admin`. `SKIP_GREMLIN_TESTS=true` skips only the Gremlin subset and must not be used to hide a Gremlin regression.
- `hugegraph-llm` external-service tests require explicit config for HugeGraph, LLM providers, and vector stores. Use `SKIP_EXTERNAL_SERVICES=true` for unit-style validation; when the task changes an external integration, configure the service and run the real integration path.

## Agent Workflow

- Before editing, identify whether the change belongs to `hugegraph-llm`, `hugegraph-python-client`, or root workspace configuration.
- For multi-file features, API contract changes, or cross-module design changes, read `rules/README.md` first.
- When the staged workflow applies, follow the minimum gate: requirements and design before task planning, unchecked `[ ]` task lists only in `.workflow/{feature_name}/tasks.md`, explicit approval before execution, and execution logs under `.workflow/{feature_name}/logs/`.
- If implementation work reveals that the approved design or task plan is wrong, stop and return to the relevant rules stage instead of patching around the mismatch.
- Keep changes scoped to the module that owns the behavior. Avoid opportunistic rewrites in sibling modules.

## Planning & Review Documents

- For release plans, Feishu documents, review notes, and other reader-facing plans, distinguish target-branch facts, PR diff facts, local workspace evidence, and final artifact evidence.
- Do not cite a concrete code file as an existing fact unless it is present on the target branch the reader can inspect. If a path exists only in a PR or local branch, describe the change area or link the public PR diff instead of presenting it as a master-branch file.
- Do not use local-only paths, temporary evidence directories, generated artifact names, or unmerged files as the main explanation for reviewers who cannot access them. Summarize the evidence and state what must be re-run on the final artifact or merged branch.
- Plan documents must not claim release readiness from local evidence alone. Use gate language such as "must pass", "pending", "requires final artifact scan", and record completion only after there is code diff, test output, review status, or artifact audit evidence.

## Cross-module Notes

- Root dependency or workspace changes can affect multiple packages; verify the package that consumes the changed dependency.
- `hugegraph-llm` imports `hugegraph-python-client`; client API changes must preserve or deliberately update those call sites.
- Do not duplicate README quick-start, Docker, or deployment instructions in AGENTS files.
