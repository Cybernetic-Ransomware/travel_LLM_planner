# Travel Planner

![Python](https://img.shields.io/badge/python-3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![PydanticAI](https://img.shields.io/badge/PydanticAI-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-FCC21B?style=for-the-badge&logo=ruff&logoColor=black)
![Pytest](https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![UV](https://img.shields.io/badge/UV-DE5FE9?style=for-the-badge&logo=python&logoColor=white)

A FastAPI-based backend for planning optimized visit routes from Google Maps saved lists.
It scrapes, enriches, and manages places of interest, then feeds them into a route optimizer based on the Travelling Salesman Problem.

## Overview
The purpose of this project is to transform a personal Google Maps saved list into an optimized visit schedule.
The user imports locations, sets per-place scheduling preferences (preferred visit window, estimated duration),
and the planner computes the most time-efficient visiting order using Google Maps Distance Matrix and TSP algorithms.

## Features
- Imports places from public Google Maps saved lists via Playwright scraper.
- Enriches place data (address, opening hours, coordinates) via Google Places API.
- Manages scheduling preferences per place: preferred visit window, duration, skip flag.
- REST API for full CRUD management of the location pool.
- Route optimization based on TSP with time window constraints (Nearest Neighbor + 2-opt, Google Routes API distance matrix).
- Docker deployment with MongoDB persistence.

## Requirements
- Python >=3.14
- [uv](https://github.com/astral-sh/uv) package manager
- Docker Desktop / Docker + Compose 2.22 or newer (required for `develop.watch`, used by `just dev`)
- Google Cloud API key with **Places API (New)** and **Routes API** enabled

## Environment Variables

Copy `docker/.env.template` to `docker/.env` and fill in the values:

| Variable | Required | Description |
|---|---|---|
| `MONGO_URI` | yes | MongoDB connection string (Places, distance-matrix cache, orchestrator state) |
| `MONGO_DB` | yes | Database name |
| `TURSO_DATABASE_URL` | yes | Persisted trips + revision history (ADR-21). `file:/data/trips.db` for local/dev (stdlib sqlite3); `libsql://<db>.turso.io` for production |
| `TURSO_AUTH_TOKEN` | for `libsql://` | Turso database auth token (empty for a `file:` URL) |
| `TRIPS_REQUIRE_MIGRATION_MARKER` | no | `True` in production — startup requires the Turso migration-complete marker; `False` for local dev |
| `GOOGLE_PLACES_API_KEY` | yes | Google Cloud key — must have **Places API (New)** enabled |
| `GOOGLE_ROUTES_API_KEY` | yes | Google Cloud key — must have **Routes API** enabled (can be the same key) |
| `DEBUG` | no | Set to `true` to enable debug logging |

### Trip persistence (Turso / libSQL)

Persisted trips and their immutable revision history live in Turso, not MongoDB (ADR-21).
Local development and CI use stdlib `sqlite3` on a file DB (`file:` URL) — no install.
Production uses the `libsql` driver against a remote Turso database; it is installed
explicitly in the Docker image (`uv pip install libsql`) because it has no Windows wheel.

**Production cutover (writes frozen):**

1. Provision the Turso database; set `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN`.
2. Freeze trip writes (stop the old app or disable the save + chat-edit paths).
3. `just migrate-trips-to-turso` — validates every Mongo `trips` document, imports it via
   `TripRepository.import_migration_baseline`, verifies coverage + hashes, and stamps the
   Turso `app_migrations` marker **only if everything is clean**. `--dry-run` reports without
   writing; `--skip-invalid` continues past malformed docs (exits non-zero, no marker).
4. Start the new stack (`TRIPS_REQUIRE_MIGRATION_MARKER=True`) — the marker gate passes.
5. Read-only smoke on migrated data (`GET /trips`, `GET /trips/:id`, `GET /trips/:id/revisions`).
6. Write smoke on a **disposable** trip created after cutover (`POST` → `PUT` → `DELETE`).
7. Green ⇒ re-open real writes.

Rollback to the Mongo-backed version is clean only through steps 5–6. Once a real trip is
created / updated / restored on the new stack, Mongo no longer holds the newest revisions.

## Getting Started (Windows)
### Docker Deploy
1. Clone the repository:
      ```powershell
      git clone <repository-url>
      ```
2. Set up the `.env` file based on the provided template:
      ```powershell
      copy docker\.env.template docker\.env
      ```
3. Run using Docker:
      ```powershell
      just up
      ```

For local development, `just dev` starts the same stack with `uvicorn --reload` and
Docker Compose `watch` enabled, so changes under `src/` are picked up without a rebuild:
      ```powershell
      just dev
      ```

#### MongoDB Compass
The Docker stack runs MongoDB as a single-node replica set for transaction support.
The application connects from inside the Docker network via the service name `mongo`, but MongoDB Compass connects from the Windows host, so it should use:

```text
mongodb://localhost:27017/?directConnection=true
```

If you omit `directConnection=true`, Compass may try to follow the replica set host `mongo:27017`, which is resolvable inside Docker but not from Windows.

---

### Dev Instance
1. Clone the repository:
      ```powershell
      git clone <repository-url>
      ```
2. Set up the `.env` file based on the provided template.
3. Install dependencies:
      ```powershell
      uv sync
      ```
4. Run the application locally:
      ```powershell
      uv run uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
      ```

#### Dev tools setup (optional)
*After step 4:* Install dev dependencies and pre-commit hooks:
```powershell
uv sync --group dev
uv run pre-commit install
uv run pre-commit run --all-files
```

#### Versioning & Releases
1. Daily commits — stage your changes and use Commitizen for consistent messages:
      ```powershell
      git add <files>
      just commit
      ```
2. Bump the application version on release branches:
      ```powershell
      just bump  # auto-tags vX.Y.Z and updates pyproject.toml
      ```

## Testing

Run unit and regression tests (no Docker required):
```powershell
just test
```

Run integration tests (requires Docker Desktop running for the MongoDB testcontainer;
the Turso trip tests use a stdlib sqlite file and need no Docker):
```powershell
just test-integration
```

## Linting

Run the full linting suite (ruff format + check, ty, codespell):
```powershell
just lint
```

## Useful links and documentation
- FastAPI docs: [fastapi.tiangolo.com](https://fastapi.tiangolo.com/)
- Google Places API: [developers.google.com](https://developers.google.com/maps/documentation/places/web-service)
- Google Routes API: [developers.google.com](https://developers.google.com/maps/documentation/routes)
- Pydantic AI docs: [ai.pydantic.dev](https://ai.pydantic.dev/)
- PyMongo docs: [pymongo.readthedocs.io](https://pymongo.readthedocs.io/en/stable/)
- uv docs: [docs.astral.sh/uv](https://docs.astral.sh/uv/)
