# Requirements: Automated Newcomer Task Mining System

## 1. Introduction

Open-source projects struggle to attract and retain new contributors. A major bottleneck is the lack of well-scoped, difficulty-appropriate tasks. Manually curating "good first issues" is labor-intensive and doesn't scale across repositories.

This feature delivers an automated agent-based system that scans any repository, discovers candidate tasks suitable for newcomers, and outputs standardized task descriptions at two levels of detail: high-level direction (like a GitHub issue) and detailed implementation spec (with acceptance criteria, suggested tests, and scope boundaries).

The system must be repository-agnostic: it should work on `hugegraph-ai` today and on any other repository tomorrow, by consuming that repo's own `CLAUDE.md`, `AGENTS.md`, and `rules/` as context.

Related: Prior manual scan of `hugegraph-ai` discovered 48 TODO/FIXME markers, error handling gaps, partially implemented features, dead code, zero-test modules, and missing dependencies — demonstrating that raw signal exists but needs systematic extraction.

## 2. Requirements

### 2.1 Repository Scanning & Signal Detection

- **User Story**: As a **project maintainer**, I want **the system to scan a repository's code, comments, config, and test files for task-relevant signals**, so that **no candidate task is missed due to manual oversight**.

- **Acceptance Criteria (EARS format)**:
  - **U1**: The **scanner** shall **ingest the repository's own `CLAUDE.md`, `AGENTS.md`, and `rules/` files as context before scanning, so task suggestions respect the project's conventions and architecture**.
  - **U2**: The **scanner** shall **detect at minimum the following signal types: TODO/FIXME/HACK/XXX comments, `NotImplementedError` raise sites, `pass` in stub methods, silent `except:` or `except Exception: pass` blocks, and files with zero test coverage**.
  - **E1**: WHEN **the scanner runs against a repository**, the **system** shall **produce a structured signal inventory, with each signal linked to its file path and line number**.
  - **X1**: IF **the repository has no `CLAUDE.md` or `AGENTS.md`**, THEN the **system** shall **operate on code signals alone and note the absence as a limitation in its output**.

### 2.2 Task Extraction & Ranking

- **User Story**: As a **project maintainer**, I want **raw signals to be grouped, filtered, and ranked into concrete task candidates**, so that **I can review a prioritized list rather than a firehose of raw grep results**.

- **Acceptance Criteria (EARS format)**:
  - **U3**: The **task extractor** shall **group related signals (e.g., 3 TODOs about the same module) into a single candidate task**.
  - **U4**: The **task ranker** shall **assign each candidate task a difficulty label (beginner / intermediate / advanced) using the 5-dimensional scoring model defined in Appendix A, AND a criticality label (peripheral / supporting / core) using the 3-dimensional model defined in Appendix B**. The final suitability rating shall combine both axes — tasks rated `beginner + peripheral` are the best newcomer candidates.
  - **U5**: The **task ranker** shall **estimate scope in hours based on: number of files touched × complexity factor (1.0 for single-function, 1.5 for multi-function, 2.0 for cross-module)**.
  - **U6**: The **task ranker** shall **prioritize tasks by: (a) clear acceptance criteria derivable from existing code/tests, (b) self-contained scope within a single module, (c) low risk of breaking existing behavior**.
  - **X2**: IF **no clear scope boundary can be determined from the signal**, THEN the **system** shall **flag the task as "needs refinement" rather than omitting it**.

### 2.3 Task Description Generation (Dual Format)

- **User Story**: As a **maintainer or newcomer**, I want **each candidate task to be output in two standardized formats — a high-level issue and a detailed implementation spec**, so that **I can choose the right depth for my audience**.

- **Acceptance Criteria (EARS format)**:
  - **U7**: The **high-level format** shall **include: a descriptive title, a 2-3 sentence problem statement, the affected module/path, a suggested direction, and a difficulty label**.
  - **U8**: The **detailed format** shall **include everything in U7 plus: concrete acceptance criteria (EARS-style), suggested test cases, explicit scope boundaries (what's in/out of scope), and references to relevant code paths**.
  - **E2**: WHEN **a task relates to a known bug or limitation**, the **system** shall **include the impacted behavior and a minimal reproduction scenario in the detailed format**.

### 2.4 Repository-Agnostic Design

- **User Story**: As a **developer evaluating this tool for a different project**, I want **zero hardcoded assumptions about hugegraph-ai**, so that **I can point it at my own repository and get useful results**.

- **Acceptance Criteria (EARS format)**:
  - **U9**: The **system** shall **accept the repository path as its only required input parameter**.
  - **U10**: The **system** shall **derive project conventions (language, framework, test patterns) from the repository's own config files and AGENTS.md, not from built-in defaults**.

### 2.5 Output & Integration

- **User Story**: As a **maintainer**, I want **the results saved as version-controlled Markdown files and optionally posted as GitHub issues**, so that **the output feeds directly into our existing contribution workflow**.

- **Acceptance Criteria (EARS format)**:
  - **U11**: The **system** shall **write all discovered tasks to `.workflow/auto-task-mining/output/tasks.md` (or a user-specified path) in a single structured Markdown file**.
  - **E3**: WHEN **a `--create-issues` flag is passed**, the **system** shall **create GitHub issues (via `gh` CLI) for each task rated beginner or intermediate, using the high-level format as the issue body**.
  - **X3**: IF **the GitHub issue creation fails for any task**, THEN the **system** shall **log the failure and continue with remaining tasks**.
  - **O1**: WHERE **the repository has a `rules/README.md` defining a staged workflow**, the **system** shall **tag each task with the recommended workflow stage where a contributor should start**.

### 2.6 Non-Functional Requirements

- **U12**: The **system** shall **complete a full scan of a ~200-file Python repository in under 5 minutes**.
- **U13**: The **system** shall **run without network access beyond the `gh` CLI for optional issue creation** (no external API calls to LLM services unless explicitly configured).
- **U14**: The **code** shall **follow the project's own `rules/` workflow for its own development** (this requirements doc is stage 1 of that workflow).

## Appendix A: Difficulty Scoring Model

Each candidate task is scored across 5 independent dimensions (0-2 points each), then mapped to a difficulty label.

### A.1 Scoring Dimensions

| Dimension | 0 (Simple) | 1 (Moderate) | 2 (Complex) |
|-----------|-----------|-------------|------------|
| **Change Surface** (`surf`) | Single file, single function | Multiple files, same module | Cross-module or cross-layer |
| **Domain Knowledge** (`domain`) | Pure syntax/format/typo fix | Requires understanding module-internal logic | Requires understanding full pipeline, external service, or protocol |
| **Test Burden** (`test`) | Existing tests directly cover the change | New tests needed but mocking is straightforward | Complex mocking, integration tests, or external-service fixtures required |
| **Risk Surface** (`risk`) | No external callers; internal helper | Has internal callers within the module | Affects public API, config schema, or cross-module contract |
| **Signal Clarity** (`clarity`) | Exact fix location and approach are obvious from the signal | Direction is clear but design decision is needed | Only a vague problem statement; root cause and approach are both TBD |

### A.2 Difficulty Mapping

Total score = `surf + domain + test + risk + clarity` (range: 0-10).

| Total Score | Difficulty Label | Suitable For |
|------------|-----------------|-------------|
| 0-3 | `beginner` | First-time contributors; 1-4 hour tasks |
| 4-6 | `intermediate` | Contributors with some project familiarity; 1-3 day tasks |
| 7-10 | `advanced` | Experienced contributors; multi-day to multi-week tasks |

### A.3 Examples (from hugegraph-ai prior scan)

| Candidate Task | surf | domain | test | risk | clarity | Total | Label |
|---------------|------|--------|------|------|---------|-------|-------|
| Replace `except: pass` with proper logging | 0 | 0 | 1 | 0 | 0 | 1 | beginner |
| Add missing `fastapi`/`uvicorn` to pyproject.toml deps | 0 | 0 | 0 | 1 | 0 | 1 | beginner |
| Convert `print()` calls to `log.*()` calls | 0 | 0 | 0 | 0 | 0 | 0 | beginner |
| Implement `keyword_index` stub | 1 | 1 | 2 | 1 | 1 | 6 | intermediate |
| Fix GraphIndex dead code (unused class) | 1 | 1 | 1 | 1 | 0 | 4 | intermediate |
| Implement PDF extraction feature | 2 | 2 | 2 | 1 | 1 | 8 | advanced |
| Migrate `.env` to YAML config (the completed work) | 2 | 2 | 2 | 2 | 1 | 9 | advanced |

### A.4 Scope Estimation Formula

```text
estimated_hours = files_touched × complexity_factor × (1 + test_burden × 0.5)
```text

Where:

- `files_touched`: number of files the task is expected to modify
- `complexity_factor`: 1.0 (single-function), 1.5 (multi-function), 2.0 (cross-module)
- `test_burden`: taken from the test dimension score (0, 1, or 2)

## Appendix B: Criticality Assessment Model

Each candidate task is scored across 3 dimensions (0-2 points each) to determine how central the affected code is to the system's core function.

### B.1 Scoring Dimensions

| Dimension | 0 (Peripheral) | 1 (Supporting) | 2 (Core) |
|-----------|---------------|----------------|----------|
| **Import Fan-in** (`importers`) | 0-1 files import this module | 2-5 files import it | 6+ files import it |
| **Path Role** (`path_role`) | `demo/`, `tests/`, `scripts/`, `utils/` (generic helpers) | `models/`, `operators/`, `resources/` | `api/`, `flows/`, `config/`, `indices/` (critical infrastructure) |
| **Blast Radius** (`blast`) | Change is internal to a helper; no external behavior change | Change affects data model, internal contract, or operator behavior | Change affects public API, config schema, data persistence, or security |

### B.2 Criticality Mapping

Total criticality score = `importers + path_role + blast` (range: 0-6).

| Total Score | Criticality Label | Risk Profile |
|------------|-------------------|-------------|
| 0-2 | `peripheral` | Low blast radius; safe for experimentation |
| 3-4 | `supporting` | Moderate impact; requires code review |
| 5-6 | `core` | High impact; requires design review and careful testing |

### B.3 Combined Suitability Matrix

The two axes — difficulty (Appendix A) and criticality (Appendix B) — form a 3×3 matrix:

|  | peripheral | supporting | core |
|--|-----------|-----------|------|
| **beginner** | **Best newcomer tasks** | Good newcomer tasks (with guidance) | Needs experienced reviewer |
| **intermediate** | Safe practice tasks | Standard tasks | Requires paired review |
| **advanced** | Low-priority unless blocking | Important but not urgent | Critical path, experienced only |

### B.4 Examples (from hugegraph-ai prior scan)

| Candidate Task | Difficulty | importers | path_role | blast | Criticality | Combined Label |
|---------------|-----------|-----------|-----------|-------|-------------|----------------|
| `print()` → `log.*()` in demo/ | beginner (2) | 0 | 0 (demo/) | 0 (helper) | peripheral (0) | `beginner/peripheral` |
| Add missing deps to pyproject.toml | beginner (1) | — (config) | 2 (config) | 1 (build) | supporting (3) | `beginner/supporting` |
| `except: pass` → logging in operators/ | beginner (2) | 3 | 1 (operators/) | 1 (logic) | supporting (4) | `beginner/supporting` |
| Implement `keyword_index` stub | intermediate (6) | 4 | 2 (indices/) | 1 (internal) | supporting (4) | `intermediate/supporting` |
| Fix GraphIndex dead code | intermediate (4) | 2 | 0 (unused) | 0 (internal) | peripheral (2) | `intermediate/peripheral` |
| Implement PDF extraction | advanced (8) | 5 | 1 (models/) | 1 (feature) | supporting (4) | `advanced/supporting` |
| Migrate `.env` to YAML | advanced (9) | 45+ | 2 (config/) | 2 (schema) | core (6) | `advanced/core` |
