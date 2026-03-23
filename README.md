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
- Docker Desktop / Docker + Compose
- Google Cloud API key with **Places API (New)** and **Routes API** enabled

## Environment Variables

Copy `docker/.env.template` to `docker/.env` and fill in the values:

| Variable | Required | Description |
|---|---|---|
| `MONGO_URI` | yes | MongoDB connection string |
| `MONGO_DB` | yes | Database name |
| `GOOGLE_PLACES_API_KEY` | yes | Google Cloud key — must have **Places API (New)** enabled |
| `GOOGLE_ROUTES_API_KEY` | yes | Google Cloud key — must have **Routes API** enabled (can be the same key) |
| `DEBUG` | no | Set to `true` to enable debug logging |

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

Run integration tests (requires Docker Desktop running):
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