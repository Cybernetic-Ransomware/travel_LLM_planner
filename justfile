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

# Start full Docker stack (app + mongo) with rebuild
up:
    docker-compose -f docker/docker-compose.yml up --build -d

# Stop and remove Docker stack containers
down:
    docker-compose -f docker/docker-compose.yml down

# Stream Docker app logs
logs:
    docker-compose -f docker/docker-compose.yml logs -f app

# Start Streamlit location management panel (requires: just up)
panel:
    $env:PYTHONPATH = "."; uv run streamlit run src/panel/app.py

# Run unit and regression tests (no Docker required)
test:
    uv run pytest

# Run integration tests — requires Docker Desktop running
test-integration:
    uv run pytest -m integration