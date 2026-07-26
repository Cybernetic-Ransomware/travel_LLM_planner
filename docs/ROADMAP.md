# Travel Planner — Implementation Review and Roadmap

_Last updated: 2026-06-02_

---

## Project Goal

Transform a personal Google Maps saved list into an optimised visit schedule.

**Core pipeline:** import list (Playwright scraping) → enrich with Places API data →
set per-place preferences (visit window, estimated duration, skip flag) → optimise
route (TSP with time windows) → multi-day partitioning → AI assistant for
interactive adjustments → SvelteKit frontend.

---

## Part 1 — Feature Implementation Review

Relevance to goal: ★★★ product core · ★★ supporting layer · ★ auxiliary / legacy.

| Feature | Location | Status | Relevance | Notes |
|---|---|---|---|---|
| Google Maps list scraping (Playwright) | `src/gmaps/scraper.py` | Complete | ★★★ | No automated tests by design (requires real browser). Two extraction strategies + DOM fallback. |
| Place enrichment (Places API New) | `src/gmaps/manager.py`, `router.py` | Complete | ★★★ | `POST /enrich` with place_id resolution and 24 h re-enrichment backoff. |
| Place storage / CRUD | `src/gmaps/storage.py`, `router.py` | Complete | ★★★ | Bulk upsert, enrichment-candidates aggregation pipeline, `find_one_and_update` (TOCTOU fix — ADR-06). |
| Distance matrix + cache | `src/optimizer/matrix/` | Complete | ★★★ | Google Routes `computeRouteMatrix`, TTL 7 d / 1 h (TRANSIT), full-coverage guard before solving. |
| TSP solver (NN + 2-opt, time windows) | `src/optimizer/solver/engine.py`, `service.py` | Complete | ★★★ | Split opening hours resolved (B1); `TimeWindow.earliest_start` enforces segment-level placement. |
| Multi-day trip partitioning | `src/optimizer/solver/multi_day_service.py` | Complete | ★★★ | Three-tier bin-pack: pinned / flexible / auto-assigned. |
| AI assistant (LangGraph ReAct) | `src/orchestrator/` | Complete | ★★ | 4 tools, scope guard, human-in-the-loop confirm/cancel, OpenAI/Anthropic, SSE streaming. |
| MongoDB checkpoint saver | `src/orchestrator/checkpointer.py` | Complete | ★★ | Index and TTL resolved (A2); compound index `checkpoint_lookup` + TTL on `expires_at` (30 d). |
| SvelteKit frontend | `apps/frontend/` | Complete | ★★★ | 4 routes, Leaflet maps, SSE chat with HITL, i18n EN/PL (149/149 keys), Vitest component tests. |
| Streamlit panel | `src/panel/` | Complete | ★★ | Repurposed as admin panel (replaces original retirement plan). Duplicate map render block in `app.py:300-342` deferred until conversion. |
| Config / lifespan / DI | `src/config/`, `src/core/` | Complete | ★★★ | Graceful orchestrator degradation when no LLM key is set (returns 503). |
| Exception handling | `src/core/middleware.py`, `exceptions.py` | Complete | ★★ | Hybrid: per-exception handlers + catch-all middleware (ADR-07). |

**Overall assessment:** implementation depth matches the stated goal. The full
product pipeline is wired end-to-end — SSE event types emitted by
`src/orchestrator/router.py` are matched exactly by `apps/frontend/lib/types/orchestrator.ts`.
Architecture is consistent (uniform Manager pattern: `connect/disconnect` + async
context manager). Development has been disciplined: every major feature ships as a
separate PR with a matching ADR.

---

## Part 2 — Gaps and Risks

### Critical — production blockers

**1. No authentication on `/chat`** ✅ resolved (ADR-13)
`POST /chat` and all place-write endpoints now require a valid RS256 JWT (Auth0).
`get_current_user` FastAPI dependency via `authlib`; `AUTH_ENABLED=False` (default)
keeps the gate open for local dev and CI.  See `src/core/auth.py`.

**2. `orchestrator_checkpoints` collection has no index and no TTL** ✅ resolved (ADR-09 updated)
Compound index `(thread_id, checkpoint_id DESC)` named `checkpoint_lookup` added to
`MongoDBManager._create_indexes`.  TTL index on `expires_at` (expireAfterSeconds=0)
added; `aput` writes `expires_at = now + CHECKPOINT_TTL_DAYS` (default 30 days).

**3. Prompt injection risk in AI assistant** ✅ resolved
`_sanitize_for_prompt` strips control characters (including `\n`) and truncates
place names/addresses to 200 characters before interpolation into the system prompt
in `_build_place_context_prompt` (`src/orchestrator/graph.py`).

### High — correctness

**4. Solver ignores split opening hours** ✅ resolved (B1)
`_parse_time_window` now collects all matching periods for a given day and returns a
multi-segment `TimeWindow`.  `TimeWindow.earliest_start(arrival_s, visit_s)` enforces
that visits fit within a single segment, correctly skipping over breaks.
`MATRIX_INCOMPLETE` (B2) added as a third skip-reason for partial matrix coverage.
Regression test: `test_split_hours_no_visit_scheduled_in_break`.

### Medium — technical debt / consistency

**5. Two frontends coexist** (partially resolved — C2 done)
Streamlit (`src/panel/`) is **not being retired**; it is repurposed as an admin panel
(richer auth and operator tooling, replacing the user-facing retirement plan).
`apps/api/` now has a minimal workspace stub; `[tool.uv.workspace]` formalised in
`pyproject.toml`.  Full `src/` → `apps/api/src/` migration remains deferred (see C2).

**6. `regression` marker declared but never used** ✅ resolved (D1)
`test_split_hours_no_visit_scheduled_in_break` in `tests/optimizer/test_solver_service.py`
is the first test using `@pytest.mark.regression`.  Run with `uv run pytest -m regression`.

**7. `src/orchestrator/` excluded from `ty`**
Static type checking is disabled for the orchestrator package (ADR-08, intentional
— LangGraph TypeVar bounds are incompatible with `ty`). Coverage by unit tests
compensates; keep an eye on LangGraph version upgrades that may resolve this.

### Low — cosmetic

**8. Duplicate map render block in Streamlit panel** (deferred — panel frozen)
`src/panel/app.py:300-342` contains two identical blocks that build and display the
locations map (copy-paste residue). Fix deferred until the panel is converted to the
admin panel role; removing it prematurely is low value while the panel is in flux.

**9. Minor inaccuracy in `CLAUDE.md` coverage note** ✅ resolved (D2)
`CLAUDE.md` now correctly states that only `src/panel/app.py` (Streamlit UI) lacks
automated tests. `api_client.py` and `chat_client.py` have tests in `tests/panel/`.

---

## Part 3 — Roadmap

### Phase A — Production hardening (unblocks deployment)

**A1. JWT authentication** ✅ done
RS256 JWT via `authlib`; `get_current_user` FastAPI dependency on all place-write
endpoints and `POST /chat`. `AUTH_ENABLED=False` default keeps local dev and CI open.
Token attachment added in SvelteKit client and Streamlit panel. See `src/core/auth.py`, ADR-13.

**A2. Index and TTL for `orchestrator_checkpoints`** ✅ done
Compound index `(thread_id, checkpoint_id DESC)` named `checkpoint_lookup` in
`MongoDBManager._create_indexes`. TTL index on `expires_at` (expireAfterSeconds=0);
`aput` writes `expires_at = now + CHECKPOINT_TTL_DAYS` (default 30 days). ADR-09 updated.

**A3. Prompt injection sanitisation** ✅ done
`_sanitize_for_prompt` strips control characters and truncates place names/addresses
to 200 chars before interpolation in `_build_place_context_prompt` (`src/orchestrator/graph.py`).

### Phase B — Solver correctness

**B1. Split opening hours support** ✅ done
`_parse_time_window` now collects all periods for the day; `TimeWindow` extended with
`segments: list[tuple[int, int]]`, `from_segments` classmethod, and `earliest_start`
method.  Engine (`schedule_route`, `_nn_from_start`) uses `earliest_start` as the
single placement oracle.  Missing matrix entry detected explicitly (returns `[]`)
instead of relying on the `_LARGE` sentinel overflow.

**B2. Skip reason precision** ✅ done
`MATRIX_INCOMPLETE` added as a third `SkippedPlace.reason` (actual_edges > 0 but
< expected).  Frontend `SkippedPlace` union type updated in
`apps/frontend/src/lib/types/optimizer.ts`.
UX follow-up: raw reason codes are no longer shown to the user — the frontend maps
each reason to a human-readable i18n message (`skippedReasons.ts`), shows an
actionable tip for `DROPPED_LOW_PRIORITY` (raise priority or extend the day), and
`RouteResults` displays a planned / skipped / must-see-kept summary.

### Phase C — Frontend migration and developer experience

**C1. Convert Streamlit panel to admin panel** (replaces original retirement plan)
`src/panel/` is no longer being retired. The plan is to convert it into an operator
admin panel with richer Auth0 integration and features not covered by the user-facing
SvelteKit frontend (bulk operations, enrichment management, etc.).

Known UI limitations to keep in mind during conversion:
- `st.data_editor` `TimeColumn(step=3600)` uses a 1 h step with no +/- buttons.
  A `step=900` (15 min snap) is possible but still lacks visible increment buttons.
  In Svelte the recommended approach is `<input type="time" step="900">` with a
  custom step component.
- `st.data_editor` with `num_rows="dynamic"` does not validate duplicate rows on the
  client side; duplicate-ID validation is delegated to the API (Pydantic).
- `st.sidebar` is a global singleton. Filters are placed directly in the tab
  (`st.columns`) rather than the sidebar, which is reserved for the global chat widget.

Before conversion: remove the duplicate map render block (`app.py:300-342`, item 8).

**C2. Formalise uv workspace** ✅ done (lightweight scaffold)
`[tool.uv.workspace]` added to root `pyproject.toml` (`members = ["apps/*"]`,
`exclude = ["apps/frontend"]`). `apps/api/pyproject.toml` stub created.
Full migration of `src/` → `apps/api/src/` is deferred to a dedicated PR (involves
updating `pyproject.toml`, Docker, `justfile`, and all import paths).

**C3. Docker dev workflow** ✅ done
`docker/docker-compose.dev.yml` adds `uvicorn --reload` and a `develop.watch` block
(sync `../src` → `/src`, rebuild on `pyproject.toml`/`uv.lock` changes). `just dev` runs
both compose files together via `docker compose ... watch`.

### Phase D — Housekeeping (low effort, low risk)

- **D1.** ✅ `@pytest.mark.regression` first used in `test_split_hours_no_visit_scheduled_in_break`.
- **D2.** ✅ `CLAUDE.md` coverage note updated: uncovered area is `src/panel/app.py` only.
- **D3.** Deferred — panel is frozen pending admin panel conversion (see C1).
- **D4.** ✅ `src/arch.md` retired: open items migrated to ROADMAP (C1 panel notes, C3 docker dev).

---

## Files affected by this roadmap

| Phase | Files |
|---|---|
| A1 ✅ | `src/core/auth.py` · protected routers · `apps/frontend/src/lib/api/client.ts` · `src/panel/api_client.py`, `chat_client.py` · `docs/13_ADR-jwt-authentication.md` |
| A2 ✅ | `src/core/db/manager.py` · `src/orchestrator/checkpointer.py` · `docs/09_ADR-custom-mongodb-checkpointer.md` |
| A3 ✅ | `src/orchestrator/graph.py` · `tests/orchestrator/test_graph.py` |
| B1 ✅ | `src/optimizer/solver/models.py` · `src/optimizer/solver/engine.py` · `src/optimizer/solver/service.py` · `tests/optimizer/test_engine.py` · `tests/optimizer/test_solver_service.py` |
| B2 ✅ | `src/optimizer/solver/service.py` · `src/optimizer/solver/models.py` · `apps/frontend/src/lib/types/optimizer.ts` |
| C1 | `src/panel/` (admin panel conversion) |
| C2 ✅ | `pyproject.toml` · `apps/api/pyproject.toml` · `docs/12_ADR-frontend-monorepo-structure.md` |
| C3 ✅ | `docker/docker-compose.dev.yml` · `docker/Dockerfile` · `justfile` · `README.md` |
| D1–D4 | `pyproject.toml` · `CLAUDE.md` · `src/panel/app.py` · ~~`src/arch.md`~~ (removed) |
