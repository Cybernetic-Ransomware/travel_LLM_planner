# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**travel-planner** is a FastAPI application for scraping, storing, and serving Google Places data.
It uses MongoDB (single-node Replica Set) for persistence, Playwright for scraping, and Streamlit for a management panel.

- Python **3.14+**, managed with **uv**
- Async-first: `asyncio` mode throughout, PyMongo native async client

## Package Manager

This project uses **uv**. Never use `pip` directly.

```bash
uv sync                  # install all dependencies (including dev)
uv add <package>         # add production dependency
uv add --dev <package>   # add dev dependency
uv run <command>         # run command in project environment
```

## Task Runner

All common workflows are defined in **`justfile`** (PowerShell shell). Use `just` instead of running commands manually.

| Recipe             | Description                                        |
|--------------------|----------------------------------------------------|
| `just lint`        | ruff format + ruff check + ty check + codespell    |
| `just test`        | unit + regression tests (no Docker required)       |
| `just test-integration` | integration tests (requires Docker Desktop)   |
| `just docker-up`   | build and start full Docker stack (app + mongo)    |
| `just docker-down` | stop and remove containers                         |
| `just docker-logs` | stream app container logs                          |
| `just panel`       | start Streamlit location management panel          |
| `just commit`      | run pre-commit on staged files, then Commitizen    |
| `just bump`        | bump version on release branches                   |

## Running Tests

```bash
just test                # unit + regression (no Docker)
just test-integration    # integration tests (spins up testcontainers MongoDB)
```

Tests are organized by marker:
- `unit` — isolated, no external dependencies, uses `pytest-httpx` for HTTP mocking
- `integration` — requires Docker Desktop; uses `testcontainers[mongodb]` for real MongoDB
- `regression` — end-to-end happy-path checks

Coverage is measured by `pytest-cov` and reported automatically on every run.
HTML report is written to `tests/result/html/`. Known uncovered areas: `src/panel/app.py`
(Streamlit UI — `api_client.py` and `chat_client.py` have tests in `tests/panel/`) and
`src/gmaps/scraper.py` (Playwright, requires a real browser). These are intentional gaps,
not regressions.

### Test conventions

Always mark every test or test class explicitly — never leave tests unmarked.
The default `addopts` filter (`-m 'not integration'`) lets unmarked tests through,
but unmarked tests are invisible to targeted runs like `pytest -m unit`.

File layout mirrors the source tree — one test file per source module:
```
tests/
  accommodations/  # mirrors src/accommodations/
  gmaps/       # mirrors src/gmaps/
  optimizer/   # mirrors src/optimizer/
  core/        # mirrors src/core/
```

Fixture hierarchy (all defined in `tests/conftest.py`):
- `mongo_container` (session) — single MongoDB testcontainer for the whole run
- `test_db` (function) — fresh `AsyncDatabase` per test; indexes created via `MongoDBManager.connect()`
- `google_places_manager` / `google_routes_manager` (function) — connected managers with fake API keys
- `client` (function) — `AsyncClient` with `ASGITransport`; bypasses lifespan, sets `app.state` directly

HTTP calls in unit tests are intercepted by the `httpx_mock` fixture from `pytest-httpx`.
Any test that instantiates a manager wrapping `httpx.AsyncClient` must use `httpx_mock` — never hit real APIs.

Coverage depth expectations:
- **Pydantic models with validators** — each model that defines `@field_validator` or `@model_validator` must have a dedicated test class in `tests/{domain}/test_models.py`. Indirect coverage through service or tool tests is not sufficient; validators must be exercised in isolation.
- **Manager `@property` members** — properties must have direct unit tests on the manager instance. Coverage through HTTP endpoint tests is indirect and does not verify the property contract.
- **Router SSE event types** — each new SSE event key emitted by a router helper function (e.g. `tool_proposal`, `session_id`) must have at least one test case verifying its presence and structure.

## Architecture

```
src/
├── accommodations/  # Accommodation stay domain: derives per-day START/END anchors from hotel check-in/check-out dates (ADR-15)
├── transfers/  # Transfer domain: fixed-time journeys between accommodation stays on transition days (ADR-16)
├── config/     # Startup configuration: Settings (Pydantic), logger, FastAPI lifespan
├── core/       # Cross-cutting concerns: DB manager, exceptions, dependency injection
│   └── db/     # MongoDBManager, FastAPI deps (get_db, mongo_session, mongo_transaction)
├── gmaps/      # Google Places domain: scraper, storage, router, models
├── trips/      # Trip persistence domain: save/list/get optimized routes as named trips
├── panel/      # Streamlit UI + API client
└── main.py     # App composition only — registers components via register_*(app) functions
```

`main.py` contains no business logic. Each component is registered through a dedicated `register_*(app)` function.

See `docs/` for Architecture Decision Records that explain key structural choices.

## Linting & Type Checking

Configured in `pyproject.toml`, enforced via pre-commit and `just lint`:

- **ruff** — formatter + linter (line length: 124, rules: E, F, UP, B, SIM, I)
- **ty** — type checker (src only, tests excluded; `src/orchestrator/*` also excluded — see ADR-08)
- **codespell** — spell check for `.py`, `.md`, `.yaml`, `.rst` files
- **pre-commit** also checks `uv.lock` consistency with `pyproject.toml`

## Docker

Files live in `docker/`. Copy `.env.template` to `.env` and fill in secrets before running.

```bash
just docker-up      # docker compose up --build -d
just docker-down    # docker compose down
just docker-logs    # docker compose logs -f app
```

Services:
- **app** — FastAPI on port 8080
- **mongo** — MongoDB 8.0 with Replica Set `rs0` on port 27017 (required for transactions)

## Commits & Versioning

This project uses **Conventional Commits** enforced by Commitizen.

```bash
just commit   # runs pre-commit hooks, then cz commit (interactive)
just bump     # bumps version in pyproject.toml and creates a git tag
```

Tag format: `v{version}`. Supported types: `feat`, `fix`, `hotfix`, `chore`, `docs`, `refactor`, `test`.

Do not add `Co-Authored-By` trailers to commit messages.

## Architecture Decision Records

ADRs are stored in `docs/`. Before making structural decisions, check existing ADRs for context:

| ADR | Status | Topic |
|-----|--------|-------|
| 01 | Deprecated | Motor async driver (superseded by ADR-06) |
| 02 | Accepted | Database infrastructure in `src/core/db/` |
| 03 | Accepted | Windows developer toolchain (pre-commit + just, AppLocker-aware) |
| 04 | Accepted | testcontainers[mongodb] for integration test isolation |
| 05 | Accepted | pendulum usage limited to service layer only |
| 06 | Accepted | PyMongo native async client + single-node Replica Set |
| 07 | Accepted | Hybrid exception handling — exception handlers + catch-all middleware |
| 08 | Accepted | LangGraph orchestrator module with configurable LLM provider |
| 09 | Accepted | Custom MongoDB checkpoint saver for LangGraph |
| 10 | Accepted | LLM tool pattern — closure factory, RunnableConfig scope guard, conditional interrupt |
| 11 | Accepted | Svelte 5 + SvelteKit as frontend framework (runes mode, Tailwind v4, Paraglide) |
| 12 | Accepted | Frontend co-location — `apps/frontend/` alongside root `src/` |
| 13 | Accepted | JWT RS256 authentication via authlib — `get_current_user` dependency, AUTH_ENABLED flag |
| 14 | Accepted | Astro + Svelte islands spike (`apps/astro-frontend`) as alternative frontend shell |
| 15 | Accepted | Accommodation-derived daily START/END anchors — `src/accommodations/` module, precedence policy, changeover-day safety |
| 16 | Accepted | Transition-day transfers — `src/transfers/` module, minute-precision day bounds, transfer-derived anchor precedence, transfer-day eligibility/admission-budget partitioning |
| 17 | Accepted | Transition-day route segments — PRE/POST solver segments either side of a transfer, `DayPlan.route_segments`, `TransitionSide` classification, per-side visit budgets |
| — | — | [Frontend split roadmap](docs/frontend-roadmap.md) — Astro/SvelteKit decision rule and upcoming PRs |

New decisions should follow the template in `docs/00_ADR-subject.md.template`.

## Code Style

- All code, comments, and documentation must be written in **English**. No Polish in the codebase.
- Do not add decorative section separator comments such as `# ── SectionName ───────`.