# ADR-02: Database infrastructure in `src/core/db/` instead of `src/config/`

## Context
The initial `src/config/db.py` file contained both MongoDB client creation and the `GMAPS_COLLECTION` constant. Because `config/` imported from `core/gmaps/storage.py` (which also needed the collection name), and `storage.py` needed to import from `config/db.py`, the layering became circular and conceptually wrong: configuration importing business-domain constants.

## Decision
Move all database infrastructure to a dedicated `src/core/db/` package with three responsibilities:
- `manager.py` — `MongoDBManager` class, `GMAPS_COLLECTION` constant, index creation.
- `deps.py` — FastAPI dependency `get_db` and `MongoDbDep` type alias.
- `__init__.py` — empty package marker.

## Rationale
### Evaluation of Alternatives
- **Keep in `config/`** — quick fix, but continues to blur the boundary between application configuration and runtime infrastructure.
- **Inline in `main.py`** — breaks separation of concerns entirely.
- **`src/core/db/` (chosen)** — `core/` already holds domain logic; database infrastructure is a cross-cutting concern that belongs there, not in `config/` which should remain purely about settings loading.

### Technical Considerations
- `GMAPS_COLLECTION` is defined once in `manager.py` and imported by `storage.py`, eliminating the circular dependency.
- `MongoDBManager` encapsulates client lifecycle so `lifespan.py` stays thin — it just orchestrates, it does not know Motor internals.
- `deps.py` keeps the FastAPI-specific glue (Request, Depends) isolated from the Motor logic.

### Integration with Existing Environment
- `src/config/lifespan.py` imports `MongoDBManager` from `core/db/manager` — the only cross-layer import, which is acceptable (config orchestrates core).
- Any future database (e.g., Redis, vector store) would get its own subpackage under `core/`.

### Future Potential
Clean separation allows adding a second database driver without touching `config/` or other `core/` modules.

## Consequences
### Positive Outcomes
- No circular imports.
- Clear ownership: `config/` = settings & startup; `core/db/` = DB infrastructure; `core/gmaps/` = domain.
- Easy to locate all DB-related code in one place.

### Challenges & Mitigation
- One more package to navigate. Mitigated by the consistent `core/<domain>/` pattern already established.

## Status
`Accepted` — project-wide. Effective from the `features/basic_ui` branch.
