# ADR-09: Custom MongoDB checkpoint saver for LangGraph

## Context
LangGraph requires a `BaseCheckpointSaver` implementation to persist conversation state (checkpoints) between requests. Without persistence, each `POST /chat` request starts a fresh conversation with no memory of previous turns — negating the conversational capabilities the orchestrator is built for.

The canonical package for MongoDB-backed checkpointing is `langgraph-checkpoint-mongodb`. However, it pins `pymongo<4.16`, which conflicts directly with ADR-06's decision to use `pymongo>=4.16.0` (native async client). Running `uv add langgraph-checkpoint-mongodb` produced an unsatisfiable dependency resolution:

```
Because langgraph-checkpoint-mongodb depends on pymongo>=4.9.0,<4.16
and your project depends on pymongo>=4.16.0,
your project's requirements are unsatisfiable.
```

The most recent release of `langgraph-checkpoint-mongodb` at the time of this decision was `0.3.1`.

## Decision
Implement a custom `MongoCheckpointSaver` by subclassing LangGraph's `BaseCheckpointSaver` directly, using the existing `pymongo>=4.16` async client already managed by `MongoDBManager`.

The implementation resides in `src/orchestrator/checkpointer.py` and stores checkpoints in the `orchestrator_checkpoints` MongoDB collection, keyed by `thread_id` + `checkpoint_id`.

## Rationale
### Evaluation of Alternatives
- **`langgraph-checkpoint-mongodb` (official package)** — rejected: requires downgrading pymongo to `<4.16`, which would break ADR-06. The native async client (`pymongo.asynchronous`) is only available from 4.16+; downgrading would force reverting to the synchronous client or Motor.
- **`MemorySaver` (in-process)** — rejected: conversation history is lost on every application restart. Unacceptable for a production travel planning assistant where multi-turn conversations may span hours or days.
- **Alternative storage backends** (Redis, PostgreSQL via `langgraph-checkpoint-postgres`)** — rejected: would introduce new infrastructure dependencies not present in the current stack. MongoDB is already running as a single-node Replica Set (ADR-06) and well-suited for document storage.
- **Custom `BaseCheckpointSaver` (chosen)** — implements only the methods required by the current LangGraph graph (`aget_tuple`, `aput`, `aput_writes`). The sync methods (`get_tuple`, `put`, `list`) raise `NotImplementedError` to make misuse explicit.

### Technical Considerations
- `BaseCheckpointSaver` is a well-defined abstract base class in `langgraph.checkpoint.base`. The async interface (`aget_tuple`, `aput`, `aput_writes`) maps cleanly to PyMongo async operations (`find_one`, `update_one` with `upsert=True`).
- `aget_tuple` fetches the most recent checkpoint for a `thread_id` by sorting on `checkpoint_id` descending — O(1) with the compound index `{thread_id: 1, checkpoint_id: -1}`.
- `aput` uses `update_one(..., upsert=True)` — idempotent, safe to retry on transient failures.
- `aput_writes` (intermediate node writes) is a no-op. LangGraph calls this for tool call results mid-graph; the skeleton does not require intermediate write persistence.
- The implementation is intentionally minimal. It covers the full conversation turn cycle without over-engineering for features (e.g., checkpoint listing, branching) that are not yet needed.
- `MongoCheckpointSaver` receives an `AsyncDatabase` instance injected by `OrchestratorManager.connect()`, keeping it consistent with the dependency injection pattern used by all other MongoDB-aware components.

### Integration with Existing Environment
- `OrchestratorManager` receives `db: AsyncDatabase | None` in its constructor. When `db` is provided (production lifespan), `build_graph()` is called with the checkpointer. When `db` is `None` (unit tests with mocked graph), `build_graph()` is called without a checkpointer.
- The `orchestrator_checkpoints` collection does not currently have an explicit index defined in `MongoDBManager.connect()`. This should be added when the feature is productionised (see Challenges below).
- `src/orchestrator/*` is excluded from `ty` (ADR-08), so the type annotations in the checkpointer are not statically verified. The `BaseCheckpointSaver` interface conformance is validated by the unit tests in `tests/orchestrator/test_manager.py`.

### Future Potential
- If `langgraph-checkpoint-mongodb` releases a version compatible with `pymongo>=4.16`, this custom implementation can be replaced with zero changes to the graph or manager (same interface).
- The `list` method (currently raises `NotImplementedError`) can be implemented to enable checkpoint browsing — useful for a future conversation history UI.
- Checkpoint TTL (automatic expiry of old conversations) can be added via a MongoDB TTL index on a `created_at` field without changing the saver interface.

## Consequences
### Positive Outcomes
- No dependency conflicts: the full stack runs on `pymongo>=4.16` as required by ADR-06.
- Conversation history persists across application restarts.
- The implementation reuses the existing MongoDB infrastructure and connection pool — no additional containers or services required.
- Behaviour is fully under project control; upgrades to LangGraph do not risk breaking persistence unless `BaseCheckpointSaver` itself changes.

### Challenges & Mitigation
- **Maintenance burden**: unlike the official package, this implementation must be manually updated if `BaseCheckpointSaver` adds required abstract methods in a future LangGraph release. Mitigated by the minimal interface surface and comprehensive test coverage.
- **Missing MongoDB index**: the `orchestrator_checkpoints` collection currently has no indexes. Queries will perform full collection scans at scale. Mitigated in the short term by the low volume of checkpoints per deployment; a compound index on `(thread_id, checkpoint_id)` should be added to `MongoDBManager.connect()` before going to production.
- **No checkpoint TTL**: old conversations accumulate indefinitely. A TTL index or a periodic cleanup task should be added before production deployment.

## Status
`Accepted` — effective from branch `feature/langgraph-orchestrator`. Supersedes the use of `MemorySaver` as a fallback.
