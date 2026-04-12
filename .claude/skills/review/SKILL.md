---
name: review
description: >
  Code review a pull request or set of changes against travel-planner conventions. Use when the user
  wants to review a PR, diff, branch, or set of changed files. Checks for: architecture & ADR compliance,
  async patterns & MongoDB usage, test coverage & conventions, and code style & linting rules. Trigger
  phrases: "review PR", "code review", "review changes", "review this branch", "check my code".
argument-hint: "<PR number, branch name, or file paths> — what to review"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Agent
  - Bash(git log*)
  - Bash(git diff*)
  - Bash(git show*)
  - Bash(git branch*)
  - Bash(gh pr*)
  - Bash(gh api*)
  - Bash(ruff check*)
  - AskUserQuestion
model: inherit
context: inherit
hooks: {}
user-invocable: true
---

# Code Review — travel-planner Conventions

Reviews a PR, branch, or set of files against the project's established patterns and catches common mistakes.

## Review Agents

Launch **all agents marked `ON`** below in a **single message** (concurrent execution).

| # | Tag   | Name                          | `subagent_type` | Focus                                                    | Enabled |
|---|-------|-------------------------------|-----------------|----------------------------------------------------------|---------|
| 1 | ARCH  | Architecture & ADR Compliance | `Explore`       | Module boundaries, ADR rules, compositor, Manager, DI    | ON      |
| 2 | ASYNC | Async Patterns & MongoDB      | `Explore`       | PyMongo async, pendulum scope, 3-tuple returns, toolchain | ON      |
| 3 | TESTS | Test Coverage & Conventions   | `Explore`       | Markers, fixtures, testcontainers, pytest-httpx, layout  | ON      |
| 4 | STYLE | Code Style & Linting          | `Explore`       | Ruff rules, line length, Python 3.14+ syntax, naming     | ON      |

---

## 1. Resolve the Diff

Determine what to review from `$ARGUMENTS`:

| Input | How to get the diff |
|-------|---------------------|
| PR number (e.g. `123`) | `gh pr diff 123` and `gh pr view 123 --json files,title,body` |
| Branch name | `git diff main...{branch}` |
| File paths | `git diff HEAD -- {paths}` (unstaged) |
| Empty | `git diff main...HEAD` (current branch vs main) |

Collect the **full diff** and the **list of changed files**.

## 2. Launch Review Agents (parallel)

Spawn **all agents** in a **single message**. Each agent receives the diff and file list.

### ARCH — Architecture & ADR Compliance

**subagent_type:** `Explore`

**Before reviewing**, read the full architecture reviewer checklist:
`.claude/agents/reviewers/architecture-reviewer.md`

Apply **all 13 skill areas** from that document against the changed files. The skill areas cover:

1. **Dependency Direction & Module Boundaries** (ADR-02) — import direction `config/ → core/ → domain`, collection constants in `manager.py`
2. **Application Compositor Pattern** — `main.py` as pure compositor, `register_*(app)` functions
3. **Exception Handling Architecture** (ADR-07) — `StarletteHTTPException`, `ErrorResponse` shape, middleware ordering
4. **Manager Lifecycle Pattern** — constructor/connect/disconnect/client-guard/`__aenter__`
5. **Dependency Injection** — `Annotated[..., Depends(...)]` type aliases from `app.state`
6. **Database Infrastructure** (ADR-02, ADR-06) — PyMongo native async, `find_one_and_update`, storage function signatures
7. **Separation of Concerns** — router → service → storage layering per domain module
8. **External API Client Patterns** — 3-tuple returns, shared `httpx.AsyncClient`
9. **Configuration Management** — pydantic-settings, no scattered `os.environ`
10. **Coupling & Cohesion** — cross-module import analysis
11. **Anti-Pattern Detection** — God Object, Spaghetti Imports, Lava Flow, etc.
12. **Cross-Cutting Change Completeness** — verify all call sites touched
13. **Docker & Deployment** — Replica Set, uv in Dockerfile, port consistency

Read the actual changed files to verify. Report each finding using the output format defined in the architecture-reviewer document (severity + category + ADR reference).

### ASYNC — Async Patterns & MongoDB Usage

**subagent_type:** `Explore`

Check every changed file for async and MongoDB patterns.

**PyMongo native async (ADR-06):**
- [ ] **PyMongo native async, not Motor** — imports must come from `pymongo` / `pymongo.asynchronous`, never from `motor`.
- [ ] **`find_one_and_update` for atomic ops** — not a separate `find_one` + `update_one` sequence that creates a TOCTOU race condition.
- [ ] **`bulk_write(ordered=False)` outside transactions** — bulk upserts must set `ordered=False` for performance; this pattern should stay outside transaction blocks.
- [ ] **`AsyncDatabase` as first arg to storage functions** — storage functions take `db: AsyncDatabase` as their first positional argument, not a manager or client object.

**pendulum scope (ADR-05):**
- [ ] **pendulum only in service layer** — `pendulum.DateTime`, `pendulum.now()`, or any pendulum type must not appear in Pydantic model field annotations.
- [ ] **Pydantic model fields use stdlib `datetime`** — conversion to/from pendulum happens in storage or service functions, not in model definitions.

**Async correctness:**
- [ ] **No blocking I/O in async functions** — `open()`, `time.sleep()`, synchronous `requests.*` must not appear inside `async def` functions.
- [ ] **Explicit timeout on `httpx.AsyncClient`** — new client instances must have an explicit `timeout` parameter; do not rely on the library default.

**Windows toolchain (ADR-03):**
- [ ] **`uv run` for commands** — never bare `python`, `pip install`, or `pip freeze` in scripts, Dockerfiles, or CI configs.
- [ ] **`just` task runner** — common workflows use justfile recipes; new automation should extend the justfile, not add raw shell scripts.

Read the actual changed files to verify. Report each violation with file:line.

### TESTS — Test Coverage & Conventions

**subagent_type:** `Explore`

Check test coverage and conventions for the changes.

**Coverage:**
- [ ] **New source modules have corresponding test files** — for each new file in `src/`, check that a corresponding test file exists in `tests/` mirroring the source tree (e.g., `src/gmaps/storage.py` → `tests/gmaps/test_storage.py`).
- [ ] **New public functions have tests** — new public functions or endpoints must have at least one test case.
- [ ] **Changed logic has test updates** — if business logic changed, existing tests should be updated or new tests added to cover the new behavior.
- [ ] **New Pydantic models with validators have a dedicated test class** — any model that defines `@field_validator` or `@model_validator` must have a dedicated class in `tests/{domain}/test_models.py`. Indirect coverage through service or tool tests is not sufficient.
- [ ] **Manager `@property` members have direct unit tests** — new properties must be tested directly on the manager instance (before/after connect, after disconnect). Endpoint tests that happen to call the property are not a substitute.
- [ ] **New SSE event types emitted by router helpers have test coverage** — each new event key yielded by a router SSE helper (e.g. `tool_proposal`) must have at least one test verifying its presence and structure in the parsed response.

**Markers (pyproject.toml):**
- [ ] **Every test is marked** — `@pytest.mark.unit`, `@pytest.mark.integration`, or `@pytest.mark.regression`. Unmarked tests are invisible to targeted runs like `pytest -m unit`.
- [ ] **Marker matches test type** — `unit` for isolated tests with no external services, `integration` for tests requiring Docker/testcontainers, `regression` for end-to-end happy-path checks.

**Fixtures and isolation (ADR-04, CLAUDE.md):**
- [ ] **Integration tests use testcontainers** — MongoDB integration tests use the `mongo_container` (session) and `test_db` (function) fixtures from `tests/conftest.py`, not mocks.
- [ ] **`MongoDBManager.connect()` reused in fixtures** — test fixtures call the same `connect()` method as production code to create indexes and ensure schema parity.
- [ ] **`client` fixture uses `ASGITransport`** — HTTP test client bypasses lifespan and sets `app.state` directly; never reuse the lifespan path in unit tests.
- [ ] **Unit tests do not require Docker** — tests marked `unit` must pass with `just test` (no Docker Desktop required).

**Mocking:**
- [ ] **HTTP mocking via `pytest-httpx`** — tests use the `httpx_mock` fixture; any test that instantiates a manager wrapping `httpx.AsyncClient` must use `httpx_mock`.
- [ ] **Never hit real APIs in tests** — no real Google Places or Google Routes API calls in any test.
- [ ] **Integration tests use real MongoDB** — tests marked `integration` use testcontainers, not `mongomock` or other MongoDB fakes.

**File structure:**
- [ ] **Test directories have `__init__.py`** — new test directories must include an `__init__.py` file.
- [ ] **`asyncio_mode = "auto"`** — no `@pytest.mark.asyncio` decorator needed; its presence is harmless but unnecessary clutter.

Read the actual changed test files and source files to verify. Report each violation with file:line.

### STYLE — Code Style & Linting

**subagent_type:** `Explore`

Check all changed Python files for style and linting compliance.

**Ruff & formatting (pyproject.toml):**
- [ ] **Run `ruff check --select E,F,UP,B,SIM,I`** on each changed Python file. Report only actual ruff violations, not manual analysis.
- [ ] **Line length ≤ 124** — the project uses 124, not 120 or 100. Check `pyproject.toml` `[tool.ruff]` for the canonical value.
- [ ] **No unused imports** — `ruff check --select F401` on changed files.

**Modern Python 3.14+ syntax (UP rule):**
- [ ] **`X | None` not `Optional[X]`** — use PEP 604 union syntax.
- [ ] **`list[...]` not `List[...]`**, **`dict[...]` not `Dict[...]`** — use lowercase built-in generics (PEP 585).
- [ ] **No `from __future__ import annotations`** — not needed in Python 3.14+; flag its presence.

**Project conventions (CLAUDE.md):**
- [ ] **English only** — all code, comments, docstrings, variable names, and log messages must be in English. No Polish or other languages in the codebase. Exception: real-world proper nouns (place names, city names) used as fixture data values in tests are acceptable — this is a travel planner for Polish locations.
- [ ] **No decorative separators** — `# ── SectionName ───────` style comments are prohibited.
- [ ] **No `pip`** — package management must use `uv`. Flag any `pip install`, `pip freeze`, or `pip uninstall`.
- [ ] **No hardcoded secrets** — no API keys, passwords, tokens, or connection strings in source files.

**Type checking:**
- [ ] **`ty` scope** — type checking applies to `src/` only (`tests/*` excluded). Verify that new `src/` code does not introduce `ty` errors.
- [ ] **codespell** — spell check applies to `.py`, `.md`, `.yaml`, `.rst` files; new words should not introduce typos flagged by codespell's `builtin = "clear"` dictionary.

**Naming conventions:**
- [ ] **No star imports** — `from module import *` is prohibited.
- [ ] **Import ordering** — handled by ruff `I` rule; flagged automatically.
- [ ] **Snake_case** for functions and variables, **PascalCase** for classes only.

Read the actual changed files to verify. Report each violation with file:line.

## 3. Aggregate Findings

After all agents return, compile findings into a structured review:

```markdown
## Code Review: <PR title or branch name>

### Summary
<1-2 sentence overview of the changes>

### Critical Issues (must fix)
- [ ] **[ARCH]** file:line — description
- [ ] **[ASYNC]** file:line — description

### Warnings (should fix)
- [ ] **[TESTS]** file:line — description
- [ ] **[STYLE]** file:line — description

### Suggestions (nice to have)
- description

### Test Coverage
- New code covered: yes / no / partial
- Missing tests: list

### Verdict
LGTM / Approve with comments / Request changes
```

Prioritize: Architecture & ADR compliance > Async & MongoDB patterns > Test coverage > Code style.

## 4. Post Review (if PR number provided)

If the input was a PR number, ask the user if they want to post the review as a GitHub PR comment using `gh pr review`.