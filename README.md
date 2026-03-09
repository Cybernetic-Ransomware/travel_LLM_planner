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
- Route optimization based on TSP with time window constraints *(upcoming)*.
- Docker deployment with MongoDB persistence.

## Requirements
- Python >=3.14
- [uv](https://github.com/astral-sh/uv) package manager
- [just](https://github.com/casey/just) task runner (`scoop install just` or `winget install Casey.Just`)
- Docker Desktop / Docker + Compose
- Google Maps API key (Places API + Distance Matrix API)

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
      docker-compose -f .\docker\docker-compose.yml up --build -d
      ```

****

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
```

#### Versioning & Releases
1. Daily commits — stage your changes, then use `just commit` to lint and open Commitizen:
      ```powershell
      git add <files>
      just commit
      ```
   Pre-commit runs only on staged files. If a formatter modifies any of them,
   the commit is aborted — re-stage the fixes and run `just commit` again.

2. Bump the application version on release branches:
      ```powershell
      just bump  # auto-tags vX.Y.Z and updates pyproject.toml
      ```

## Testing & Linting

Run unit and regression tests (no Docker required):
```powershell
just test
```

Run integration tests (requires Docker Desktop running):
```powershell
just test-integration
```

Run the full linting suite (format → lint → type check → spell check):
```powershell
just lint
```

Individual tools:
```powershell
uv run ruff check      # lint only
uvx ruff check         # as standalone (no project install needed)
uv run ty check        # type checker
uv run codespell       # spell checker
```

## Useful links and documentation
- FastAPI docs: [fastapi.tiangolo.com](https://fastapi.tiangolo.com/)
- Google Places API: [developers.google.com](https://developers.google.com/maps/documentation/places/web-service)
- Pydantic AI docs: [ai.pydantic.dev](https://ai.pydantic.dev/)
- Pendulum docs: [pendulum.eustace.io](https://pendulum.eustace.io/docs/)
- uv docs: [docs.astral.sh/uv](https://docs.astral.sh/uv/)