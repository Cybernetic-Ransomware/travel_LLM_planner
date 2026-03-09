# Travel Planner — task runner
# Install: scoop install just  |  winget install Casey.Just

set shell := ["powershell", "-Command"]

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
    uv run ruff format
    uv run ruff check --fix
    uv run ty check
    uv run python -m codespell_lib

# Start dev server
dev:
    uv run uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# Run unit and regression tests (no Docker required)
test:
    uv run pytest

# Run integration tests — requires Docker Desktop running
test-integration:
    uv run pytest -m integration