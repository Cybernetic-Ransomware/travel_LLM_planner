# ADR-03: Windows developer toolchain — pre-commit system hooks and `just` task runner

## Context
Two independent Windows-specific constraints shaped the developer workflow:

1. **AppLocker policy** blocks execution of arbitrary binaries from user-writable directories (e.g., `%APPDATA%`). Pre-commit's default behaviour creates isolated virtual environments per hook inside `%APPDATA%/pre-commit/`, which AppLocker refuses to run (`WinError 4551`).

2. **No native Make on Windows.** The project needed a way to sequence tasks (lint → commit, run tests, start dev server) that works cross-platform without requiring WSL or additional environment setup beyond the existing uv installation.

## Decision
1. Migrate all pre-commit hooks to `language: system` with `uv run <tool>` as the entry point. Hooks run inside the project's own virtual environment, which lives in the project directory and is permitted by AppLocker. Exception: `codespell` is invoked as `uv run python -m codespell_lib` because `codespell.EXE` in `.venv\Scripts\` is blocked even with a path rule — routing through `python.exe` (whitelisted via ManagedInstaller) bypasses the restriction.
2. Adopt `just` (Casey's command runner) as the project-level task runner, replacing ad-hoc PowerShell one-liners. A `justfile` at the project root defines tasks: `commit`, `bump`, `lint`, `dev`, `test`, `test-integration`.

## Rationale
### Evaluation of Alternatives
**For pre-commit:**
- **Disable AppLocker / WSL** — not feasible or too complex.
- **`language: system` + `uv run` (chosen)** — hooks run through `uv` and `python.exe`, both whitelisted by AppLocker. Tools without reliable EXE invocation are called as Python modules (e.g., `uv run python -m codespell_lib`).

**For task runner:**
- **PowerShell scripts** — no extra install, but verbose and not portable to Linux/macOS.
- **Makefile** — not natively available on Windows; requires GnuWin32 or WSL.
- **`just` (chosen)** — single binary, cross-platform, terse syntax similar to Make, installable via `winget install Casey.Just`.

### Technical Considerations
- `justfile` sets `set shell := ["powershell", "-Command"]` so tasks run in PowerShell on Windows.
- The `commit` task runs `uv run pre-commit run` (staged files only) before `uv run cz commit`, preventing Commitizen from prompting for a message before linters pass.
- `test` excludes integration tests by default (`-m 'not integration'`); `test-integration` requires Docker Desktop running.

### Integration with Existing Environment
- Developers must install `just` once (`winget install Casey.Just`).
- `uv sync --group dev` + `uv run pre-commit install` is still the standard dev setup step.
- The hook order (uv-lock-check → ruff format → ruff lint → ty → codespell) matches the `just lint` task order.
- `codespell` is invoked as `uv run python -m codespell_lib` — its module name differs from the package name, and routing through `python.exe` avoids AppLocker restrictions on script EXEs.

### Future Potential
`just` recipes can wrap Docker commands, database migrations, or deployment scripts as the project grows — keeping all entry points in one discoverable file.

## Consequences
### Positive Outcomes
- Pre-commit hooks work on Windows without AppLocker workarounds.
- `just commit` eliminates the two-pass commit (linter fails → re-stage → commit again) by running hooks before the Commitizen prompt.
- Consistent task interface across platforms.

### Challenges & Mitigation
- `just` is an additional install requirement. Documented in README and `justfile` header.
- `language: system` hooks depend on the project venv being up to date. `uv-lock-check` as the first hook catches drift.
- If a future tool doesn't support `-m` invocation and is blocked by AppLocker, it must be wrapped in a small Python helper script that imports and calls it directly.

## Status
`Accepted` — project-wide. Effective from the `features/basic_ui` branch.
