# ADR-12: Frontend co-location — `apps/frontend/` alongside root `src/`

## Context
The travel-planner repository is a single Python package managed by a root `pyproject.toml`. The entire Python toolchain — `ruff`, `ty`, `pytest`, `docker/`, and `justfile` — is configured to treat `src/` as the Python source root. All import paths in the codebase follow `from src.<module>` conventions.

Adding a SvelteKit frontend (ADR-11) requires a decision on where to place the frontend code and whether to restructure the repository as a formal monorepo.

## Decision
Keep `src/` at the repository root unchanged. Place the SvelteKit frontend at `apps/frontend/`. The `apps/` namespace is reserved for future non-Python applications; the Python package continues to live directly under `src/` with no wrapper directory.

## Rationale
### Evaluation of Alternatives
- **Move `src/` to `apps/api/src/`** — requires updating `pyproject.toml` (`pythonpath`, `--cov`, `[tool.ty.src]`), all Docker `COPY` instructions, all `justfile` recipes, and every `from src.xxx` import across the entire codebase. High migration cost, no functional gain. Rejected.
- **uv workspace with `apps/api/` and `apps/frontend/`** — the correct long-term approach. Adopted as of the `refactor/critical-gaps` branch with a lightweight scaffold (see "Status" below): `apps/api/pyproject.toml` registers the sub-package stub; `apps/frontend/` is excluded from the workspace since it is a Node.js project.
- **`frontend/` at root (flat)** — simplest option. Rejected in favour of `apps/` because the `apps/` directory was already present (created as a placeholder) and better signals "this is one of potentially several deployable applications".
- **`apps/frontend/` with `src/` at root (chosen)** — zero migration cost. The asymmetry (`src/` at root vs `apps/frontend/`) is a deliberate trade-off: Python tooling stays unchanged, frontend has a clearly namespaced home. The asymmetry is documented here so it is not mistaken for an oversight.

### Technical Considerations
- `apps/frontend/` is a fully self-contained Node.js project: its own `package.json`, `node_modules/`, `tsconfig.json`, and `svelte.config.js`. It has no build-time dependency on the Python package.
- `apps/frontend/.gitignore` covers Node.js and SvelteKit artefacts (`node_modules/`, `.svelte-kit/`, `src/lib/paraglide/`, etc.) not addressed by the root Python `.gitignore`. Both files coexist and apply to their respective directory scopes.
- `apps/api/` is a minimal workspace member stub (`pyproject.toml` + `README.md`). It serves as the future home of the Python service once `src/` is migrated into it. The migration is deferred (see "Future Potential" below).

### Integration with Existing Environment
- All existing `just` recipes, Docker build contexts, and CI workflows remain unchanged.
- The root `CLAUDE.md` continues to describe the Python API. `apps/frontend/CLAUDE.md` describes the frontend context. Claude Code loads both hierarchically.
- The `svelte` MCP server entry in `.mcp.json` uses `"cwd": "apps/frontend"` to ensure the server starts in the correct directory.

### Future Potential
- The next step is migrating `src/` to `apps/api/src/`: update `pyproject.toml` `pythonpath`, `--cov`, `[tool.ty.src]`, Docker `COPY`, `justfile` recipes, and `from src.xxx` imports. A non-trivial but well-defined operation; tracked in ROADMAP Phase C2.
- The `apps/` prefix makes the intent clear to contributors: anything under `apps/` is a deployable application unit, not a shared library.

## Consequences
### Positive Outcomes
- Zero disruption to the existing Python toolchain, Docker setup, and CI configuration.
- The frontend has a clean, namespaced location that scales to multiple apps if needed.
- Git history for all Python code is preserved without path renames.

### Challenges & Mitigation
- **Asymmetry `src/` vs `apps/`**: may confuse contributors expecting full symmetry. Mitigated by this ADR, the workspace configuration, and `apps/api/README.md` signalling the intended long-term shape.
- **No shared type definitions**: the frontend cannot import Python types directly. Mitigated by generating a TypeScript client from the FastAPI OpenAPI schema (future work) or by manually mirroring critical types in `apps/frontend/src/lib/`.

## Status
`Accepted` — effective from branch `feature/frontend`.

**Updated** (`refactor/critical-gaps`): uv workspace formalised with a lightweight scaffold:
- `[tool.uv.workspace]` added to root `pyproject.toml` with `members = ["apps/*"]` and `exclude = ["apps/frontend"]`.
- `apps/api/pyproject.toml` created as a minimal stub (`travel-planner-api`).
- Full migration of `src/` into `apps/api/src/` remains deferred to a dedicated PR.
