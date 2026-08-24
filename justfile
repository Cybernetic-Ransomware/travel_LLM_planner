# Travel Planner — task runner
# Install: scoop install just  |  winget install Casey.Just

set shell := ["pwsh", "-Command"]

# Run pre-commit on staged files, then open Commitizen
# Stage your changes first: git add <files>
commit:
    uv run pre-commit run
    uv run cz commit

# Bump version on release branches (auto-tags vX.Y.Z, updates pyproject.toml)
bump:
    uv run cz bump

# Run the full linting suite manually
lint:
    uv run ruff format src/
    uv run ruff check --fix src/
    uv run ty check
    uv run python -m codespell_lib src/

# Start full Docker stack (app + mongo) with rebuild
docker-up:
    docker-compose -f docker/docker-compose.yml up --build -d

# Stop and remove Docker stack containers
docker-down:
    docker-compose -f docker/docker-compose.yml down

# Stream Docker app logs
docker-logs:
    docker-compose -f docker/docker-compose.yml logs -f app

# Start Docker stack in dev mode (uvicorn --reload + compose watch, no rebuild on src changes)
dev:
    docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml watch

# Start Streamlit location management panel (requires: just up)
panel:
    $env:PYTHONPATH = "."; uv run streamlit run src/panel/app.py

# Run unit and regression tests (no Docker required)
test:
    uv run pytest

# Run integration tests — requires Docker Desktop running
test-integration:
    uv run pytest -m integration

# Start SvelteKit frontend dev server
frontend-dev:
    npm --prefix apps/frontend run dev

# Build SvelteKit frontend for production
frontend-build:
    npm --prefix apps/frontend run build

# Run svelte-check type checking on the frontend
frontend-check:
    npm --prefix apps/frontend run check

# Lint and format-check the frontend (prettier + eslint)
frontend-lint:
    npm --prefix apps/frontend run lint

# Auto-format frontend files with prettier
frontend-format:
    npm --prefix apps/frontend run format

# Run frontend unit tests (vitest)
frontend-test:
    npm --prefix apps/frontend run test

# Regenerate OpenAPI schema snapshot and derived TypeScript contracts (mutates tracked files)
frontend-types:
    $env:PYTHONPATH = "."; uv run python scripts/export_openapi.py openapi.json
    npm run generate --prefix tools/openapi-codegen
    npm --prefix apps/frontend run types:format

# Verify tracked openapi.json / generated/api.ts match a fresh regeneration, without touching tracked files
[script("pwsh")]
check-frontend-types:
    $env:PYTHONPATH = "."
    $tmp = (New-Item -ItemType Directory -Force -Path "$env:TEMP/travel-planner-contract-check").FullName
    uv run python scripts/export_openapi.py "$tmp/openapi.json"
    if ((Get-FileHash openapi.json).Hash -ne (Get-FileHash "$tmp/openapi.json").Hash) {
        throw "openapi.json is stale — run 'just frontend-types'"
    }
    npx --prefix tools/openapi-codegen openapi-typescript "$tmp/openapi.json" --default-non-nullable false -o "$tmp/api.ts"
    Push-Location apps/frontend
    npx prettier --config .prettierrc --write "$tmp/api.ts"
    Pop-Location
    if ((Get-FileHash apps/frontend/src/lib/types/generated/api.ts).Hash -ne (Get-FileHash "$tmp/api.ts").Hash) {
        throw "generated/api.ts is stale — run 'just frontend-types'"
    }
    Write-Output "Contracts are up to date."