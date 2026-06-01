# Travel Planner — Implementation Review and Roadmap

_Last updated: 2026-06-01_

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
| TSP solver (NN + 2-opt, time windows) | `src/optimizer/solver/engine.py`, `service.py` | Complete | ★★★ | **Known bug: split opening hours** (see Part 2, item 4). |
| Multi-day trip partitioning | `src/optimizer/solver/multi_day_service.py` | Complete | ★★★ | Three-tier bin-pack: pinned / flexible / auto-assigned. |
| AI assistant (LangGraph ReAct) | `src/orchestrator/` | Complete | ★★ | 4 tools, scope guard, human-in-the-loop confirm/cancel, OpenAI/Anthropic, SSE streaming. |
| MongoDB checkpoint saver | `src/orchestrator/checkpointer.py` | Complete | ★★ | **Missing index and TTL** (see Part 2, item 2). |
| SvelteKit frontend | `apps/frontend/` | Complete | ★★★ | 4 routes, Leaflet maps, SSE chat with HITL, i18n EN/PL (78/78 keys), Vitest component tests. |
| Streamlit panel (legacy) | `src/panel/` | Complete | ★ (to retire) | Being replaced by SvelteKit (ADR-11). Duplicate map render block in `app.py:300-342`. |
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

**1. No authentication on `/chat`**
`POST /chat` is publicly accessible. Any caller can drive the LLM and incur API
costs without limit. Planned solution is documented in `src/arch.md:32-40`: JWT
(RS256) middleware, `get_current_user` via FastAPI `Depends()`, `/health` and
`/status` remain public.

**2. `orchestrator_checkpoints` collection has no index and no TTL**
`MongoDBManager._create_indexes` (`src/core/db/manager.py:37-53`) creates indexes
only for `gmaps_places` and `distance_matrix_cache`. The checkpointer queries via
`find_one({"thread_id": ...}, sort=[("checkpoint_id", -1)])`, which is a full
collection scan. Without a TTL index the collection grows unboundedly.

**3. Prompt injection risk in AI assistant**
Place names fetched from MongoDB are interpolated directly into the system prompt
by `_build_place_context_prompt` (`src/orchestrator/graph.py`). A maliciously
crafted place name could alter the model's behaviour (ADR-10 Challenges).

### High — correctness

**4. Solver ignores split opening hours**
`_parse_time_window` (`src/optimizer/solver/service.py`) takes only the first
matching period for a given day. A place with a midday break (e.g. 13:00–15:00) is
treated as open the whole session. The solver may schedule a visit during the
break — the result is silently wrong, not an error (`src/arch.md:25-28`).

### Medium — technical debt / consistency

**5. Two frontends coexist**
Streamlit (`src/panel/`) is scheduled for retirement (ADR-11) but still ships.
`apps/api/` is an empty placeholder for the future uv workspace migration (ADR-12).

**6. `regression` marker declared but never used**
`pyproject.toml` and `CLAUDE.md` describe a `regression` marker for end-to-end
happy-path checks, but no test file uses it. The declaration and the code are out
of sync.

**7. `src/orchestrator/` excluded from `ty`**
Static type checking is disabled for the orchestrator package (ADR-08, intentional
— LangGraph TypeVar bounds are incompatible with `ty`). Coverage by unit tests
compensates; keep an eye on LangGraph version upgrades that may resolve this.

### Low — cosmetic

**8. Duplicate map render block in Streamlit panel**
`src/panel/app.py:300-342` contains two identical blocks that build and display the
locations map (copy-paste residue). Two identical maps are rendered.

**9. Minor inaccuracy in `CLAUDE.md` coverage note**
`CLAUDE.md` states `src/panel/` has no automated tests. `api_client.py` and
`chat_client.py` do have unit tests under `tests/panel/`. The gap is limited to
`app.py` (Streamlit UI).

---

## Part 3 — Roadmap

### Phase A — Production hardening (unblocks deployment)

**A1. JWT authentication**
Add RS256 JWT verification middleware to FastAPI (`authlib` or `python-jose` —
confirm library choice before running `uv add`). Introduce `get_current_user`
dependency injected on protected endpoints; keep `/`, `/api/v1/core/*/keycheck`,
and `GET /api/v1/core/orchestrator/status` public. Protect `POST /chat` and all
place-write endpoints. Add token attachment in the SvelteKit API client
(`apps/frontend/lib/api/client.ts`) and in the Streamlit panel
(`src/panel/api_client.py`, `chat_client.py`).

**A2. Index and TTL for `orchestrator_checkpoints`**
In `MongoDBManager._create_indexes` (`src/core/db/manager.py`) add:
- a compound index `(thread_id, checkpoint_id DESC)` for fast checkpoint lookup,
- a TTL index on a new `expires_at` field (e.g. 30-day retention).

`expires_at` must be written in `MongoCheckpointSaver.aput`
(`src/orchestrator/checkpointer.py`). Update ADR-09 to document the index strategy
and retention policy.

**A3. Prompt injection sanitisation**
Strip or neutralise potential instruction sequences from place names before they
reach the system prompt in `_build_place_context_prompt`
(`src/orchestrator/graph.py`). Add a unit test that asserts a name containing
`Ignore previous instructions` does not alter model-visible content.

### Phase B — Solver correctness

**B1. Split opening hours support**
Refactor `_parse_time_window` (`src/optimizer/solver/service.py`) to return a list
of valid time segments for a given day rather than a single window. Update
`is_feasible` and `schedule_route` in `src/optimizer/solver/engine.py` to reject
placement inside any break gap. Add dedicated unit tests for: (a) a single
continuous window, (b) a window with a midday break, (c) a place open past midnight.

**B2. Skip reason precision**
Clarify the `TIME_WINDOW_INFEASIBLE` vs `NO_MATRIX_ENTRY` classification when the
distance matrix is incomplete (partial API response). Consider a third reason code
`MATRIX_INCOMPLETE` to avoid misleading the caller.

### Phase C — Frontend migration and developer experience

**C1. Retire Streamlit panel**
Once the SvelteKit frontend covers all Streamlit panel features (verify parity),
remove `src/panel/`, related dependencies (`streamlit`, `folium`, `streamlit-folium`)
from `pyproject.toml`, and the `just panel` recipe from `justfile`. If the panel
stays as a transitional tool, remove the duplicate map block first (item 8 above).

**C2. Formalise uv workspace**
Populate `apps/api/` or define the workspace structure in `pyproject.toml`
(`[tool.uv.workspace]`). Update ADR-12 with the chosen layout.

**C3. Docker dev workflow**
Add `develop.watch` (sync `src/` without rebuild, Docker Compose v2.22+) and
`uvicorn --reload` to the Compose file, then add a `just dev` recipe. Eliminates
`just up` on every code change during development (`src/arch.md:1-6`).

### Phase D — Housekeeping (low effort, low risk)

- **D1.** Either write at least one `@pytest.mark.regression` end-to-end test or
  remove the marker declaration from `pyproject.toml` and `CLAUDE.md`.
- **D2.** Fix the `CLAUDE.md` coverage note: the uncovered area is
  `src/panel/app.py`, not all of `src/panel/`.
- **D3.** Remove the duplicate map render block from `src/panel/app.py:300-342`
  (if the panel is not retired first).
- **D4.** Retire `src/arch.md` once its items are captured in this document and
  tracked in PRs. (Most content is now superseded by the roadmap above.)

---

## Files affected by this roadmap

| Phase | Files |
|---|---|
| A1 | new `src/core/auth.py` (or `src/core/deps_auth.py`) · `src/main.py` · protected routers · `apps/frontend/lib/api/client.ts` · `src/panel/api_client.py`, `chat_client.py` |
| A2 | `src/core/db/manager.py` · `src/orchestrator/checkpointer.py` · `docs/09_ADR-custom-mongodb-checkpointer.md` |
| A3 | `src/orchestrator/graph.py` · `tests/orchestrator/test_graph.py` |
| B1 | `src/optimizer/solver/service.py` · `src/optimizer/solver/engine.py` · `tests/optimizer/test_service.py` |
| B2 | `src/optimizer/solver/service.py` · `src/optimizer/models.py` · related tests |
| C1 | `src/panel/` (removal) · `pyproject.toml` · `justfile` |
| C2 | `pyproject.toml` · `docs/12_ADR-frontend-monorepo-structure.md` |
| C3 | `docker/docker-compose.yml` · `justfile` |
| D1–D4 | `pyproject.toml` · `CLAUDE.md` · `src/panel/app.py` · `src/arch.md` |
