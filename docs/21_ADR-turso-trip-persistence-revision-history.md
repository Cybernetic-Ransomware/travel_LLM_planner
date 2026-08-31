# ADR-21: Turso trip persistence + immutable revision history + restore

## Context

After ADR-18 / ADR-20 a persisted trip carries a monotonic `revision` and every write (UI
`PUT` and confirmation-gated chat edit) goes through one compare-and-set path in
`TripsManager.update()` on MongoDB — **without a transaction** (ADR-20 rejected a
multi-document Mongo transaction). There is **no history**: an update overwrites the
previous state in place, so a user cannot see or return to an earlier plan. Mongo also has
no index on `trips`, and the list projection reaches into a nested request field.

Two goals are addressed together:

1. **Product** — a full, listable, immutable history of every persisted revision of a trip,
   plus the ability to restore any earlier revision.
2. **Architecture** — move the persisted-trip domain (`trips` + the new `trip_revisions`)
   off MongoDB to Turso / libSQL, where the current state and its history row can be written
   in **one transaction**. MongoDB keeps every other domain (Places, distance-matrix cache,
   orchestrator checkpoints, `orchestrator_thread_trip_state`).

## Decision

1. **Turso is the sole runtime owner of persisted trips.** `src/trips/` is backed by
   `TripRepository` over a thin async adapter (`src/core/turso/adapter.py`). The legacy Mongo
   `trips` collection becomes migration/ops-only: it is **not read at startup, not read by
   any runtime route, and never written** after cutover.
2. **One driver boundary, two backends.** `src/core/turso/adapter.py` exposes a single async
   contract (`TripDbConnection.execute` / `.transaction()` with commit-on-exit,
   rollback-on-exception, and the connection lock held for the whole transaction body).
   * **sqlite** — stdlib `sqlite3` on a `file:` DB. Local development + the base integration
     suite. Zero install; works on Windows + Python 3.14 today.
   * **libsql** — the `libsql` package against a remote Turso database. Production, plus a
     Linux-only CI *driver-parity* job that re-runs the adapter + repository contract suite
     through `libsql` (via `TRIP_DB_FORCE_BACKEND=libsql`) to catch any
     transaction / affected-row / parameter-binding divergence.
   Both DB-API drivers are synchronous, so every call runs on a **dedicated single worker
   thread per connection** (thread affinity) and the event loop is never blocked.
   `libsql` is **not** in the locked dependencies — it has no Windows / cp314 wheel and
   needs a Rust + CMake + MSVC toolchain to build. The Docker image and the parity CI job
   `uv pip install libsql` explicitly. `libsql-client-py` (archived 2025-06-11, read-only)
   and `pyturso` (no Windows wheel) are **not used**.
3. **`TripRepository` is the one persistence boundary.** Every write to `trips` /
   `trip_revisions` goes through a method here, and each write pairs a current-state row with
   an immutable `trip_revisions` row in the **same** transaction. There is no raw SQL against
   these tables anywhere else — not in routers, not in the orchestrator, and **not in the
   migration script**, which calls `TripRepository.import_migration_baseline()`.
4. **Full immutable snapshots, not event sourcing.** A revision stores the whole canonical
   JSON of the `SaveTripRequest` (request + response + versioned trip metadata) plus
   `schema_version`. Serialisation is deterministic (`json.dumps(sort_keys=True,
   separators=(",", ":"), ensure_ascii=False)`) and hashed with SHA-256. No deltas, no patch
   chains, no replay, no recompute on restore. Stored as uncompressed `TEXT`; the
   `compression` column stays `'none'` as a forward hook.
5. **`name` is versioned with the trip.** It lives inside the snapshot, is restored on
   revert, and a rename changes the snapshot hash and is therefore a real new revision.
6. **Provenance is server-enforced by the repository API.** The persisted enum is
   `RevisionSource = CREATED | MANUAL | ORCHESTRATOR | REVERT | MIGRATION`, but a caller of
   `update()` may pass only `TripUpdateSource = MANUAL | ORCHESTRATOR`. `CREATED` / `REVERT`
   / `MIGRATION` are hard-coded inside `save()` / `restore_revision()` /
   `import_migration_baseline()` and have no `source` parameter.
7. **Revision semantics.**
   * Create → `revision 0`, `source='CREATED'`.
   * `update()` → `N → N+1` (`MANUAL` | `ORCHESTRATOR`); mandatory CAS via `expected_revision`
     (missing → 428, stale → 409, zero writes); a byte-identical snapshot **and** a matching
     token → a **no-op** (no write, no revision row); a byte-identical snapshot with a stale
     token still 409s.
   * `restore_revision()` of an earlier revision → **always** `N → N+1` with `source='REVERT'`
     and `restored_from_revision = target`, **even when the target snapshot is byte-identical
     to current** (the explicit historical action must keep its provenance — the no-op dedup
     is `update()`-only). `target == current_revision` → **400**
     (`RevisionAlreadyCurrentError`); the UI also hides the Restore button on the current
     row. The optimizer is **never** invoked.
   * Migration → legacy `revision N` becomes `current N` + exactly one `MIGRATION` row at
     `revision N`. No fabricated `0..N-1` history.
8. **Timestamp roles are distinct and never overloaded.** `trips.created_at` = when the trip
   was first created; `trips.updated_at` = when the current persisted state was last written
   (`NULL` until the first update/restore); `trip_revisions.recorded_at` = when that revision
   row was written. History list/detail and the frontend use `recorded_at`.
9. **Queryable list projection (amends ADR-18).** `trips` carries three write-time derived
   columns — `display_start_date`, `display_end_date`, `display_num_days` — recomputed from
   the snapshot on every write and never edited independently, so `list_all()` needs no JSON
   parse. The snapshot stays the single source of truth.
10. **Runtime startup is Turso-only.** Startup consults **only** a durable Turso-local
    `app_migrations` marker (one `SELECT`). It never reads, counts, or reconstructs the Mongo
    `trips` collection. `TRIPS_REQUIRE_MIGRATION_MARKER` (default `True`) gates this; `False`
    is a local-dev escape hatch. Full source-vs-Turso coverage verification lives **only** in
    `scripts/migrate_trips_to_turso.py`.
11. **Migration is idempotent, hash-checked, and non-destructive.** The script reads Mongo,
    validates each document through the existing Pydantic contracts, and calls
    `import_migration_baseline()`, which: creates the trip + `MIGRATION` row once; returns
    `"skipped_identical"` when the baseline hash matches; raises
    `MigrationBaselineConflictError` when the same id/revision has a different hash, or when a
    trip exists without a matching `MIGRATION` baseline; and never `UPDATE`s or `DELETE`s a
    `trip_revisions` row. After a full pass the script verifies that every Mongo trip has a
    matching baseline and that there are no stray baselines, and **stamps the marker only if
    everything is clean** — never on `--dry-run`, never when `--skip-invalid` skipped
    anything, never on a verification failure. A pre-existing marker is re-verified, not
    trusted. A fresh empty source is verified and stamped (`trip_count: 0`). Mongo is never
    mutated.
12. **Cutover requires a trip-write freeze; rollback after the first Turso write is not
    clean.** There is no dual-write, no outbox, no CDC. The rollout is: provision Turso →
    freeze old trip writes → run the migration → clean verification stamps the marker → start
    the new stack (marker gate passes) → read-only smoke on migrated data → write smoke on a
    **disposable** post-cutover trip → green ⇒ re-open real writes. Rolling back to the
    Mongo-backed version is clean only through the read-only + disposable-trip smoke; once a
    real trip is created / updated / restored on the new stack, Mongo no longer holds the
    newest revisions and rollback needs a reverse migration or a forward-fix.
13. **Orchestrator revision tools.** `list_trip_revisions` (read-only, `_READ_TOOL_NAMES`,
    reads the trusted `binding`, no confirmation, never spends the single-use pending scope)
    and `revert_trip_revision` (write, `_WRITE_TOOL_NAMES`, consumes the single-use
    `PendingScope`, LLM supplies only `target_revision` — a number scoped to *this* trip's
    history, CAS-guarded by `scope.revision`). The whole ADR-20 gate — one write call per
    confirmation, fail-closed on a stale/expired scope, trip-switch clears `pending`, cancel
    = zero writes — covers `revert_trip_revision` unchanged; a successful revert drives the
    existing `trip_updated` SSE.

## Rationale

### Evaluation of Alternatives

* **Keep trips in Mongo, add a `trip_revisions` collection.** Rejected: ADR-20 already
  rejected a multi-document Mongo transaction, and "current + history written atomically" is
  the central invariant here. A single-node replica set gives transactions, but a small
  relational store is a better fit for immutable, monotonically-numbered rows and cheap
  history queries.
* **Event sourcing / deltas.** Rejected: the payload is tens of KB; a full snapshot per
  revision is simple, self-describing, trivially restorable (byte copy), and needs no replay
  engine or schema-migration story for historical events.
* **`pyturso` for local, `libsql` for remote (one code path or two).** The intended
  single-driver path does not exist on this toolchain: `pyturso` has no Windows wheel and
  `libsql` has no cp314 Windows wheel and needs CMake + MSVC to build from source. `sqlite3`
  (local) + `libsql` (prod) behind the adapter gives identical
  BEGIN/COMMIT/ROLLBACK, `rowcount` 0/1 for a CAS `UPDATE`, `?` binding, FK/PK enforcement,
  and `ON CONFLICT` for the plain-table SQL subset this domain uses — verified by a Stage 0a
  spike and re-verified per-PR by the Linux driver-parity job.
* **Dual-write / outbox / CDC for zero-downtime cutover.** Rejected as disproportionate for a
  personal planner: it re-introduces two trip-persistence implementations and a consistency
  problem. A short maintenance window with a write freeze is enough.
* **Runtime coverage verification against Mongo at startup.** Rejected: it keeps a runtime
  dependency on the legacy store and becomes decorative once writes are Turso-only. The
  durable marker + ops-path verification keeps startup a single `SELECT`.

### Technical Considerations

* The adapter's per-connection worker thread + `asyncio.Lock` guarantees that
  `BEGIN → CAS UPDATE → history INSERT → COMMIT/ROLLBACK` runs on one connection and is never
  interleaved with another statement.
* CAS is enforced twice: an up-front `expected_revision` check, and the transactional
  `UPDATE ... WHERE id=? AND revision=?` affected-row check (0 rows ⇒ raise inside the tx ⇒
  rollback before the history INSERT ⇒ `TripConcurrencyConflictError`).
* New trip ids stay `str(bson.ObjectId())` so `/trips/:id` links and orchestrator
  `get_trip_details` are unchanged; the migration copies Mongo `_id` values verbatim.

### Integration with Existing Environment

* `src/trips/manager.py` (`TripsManager`) is deleted; `src/trips/deps.py`,
  `src/trips/editing/service.py`, and the orchestrator (`manager` → `graph` → `tools`,
  `router`, `trip_edit_tool`) are threaded with `TripRepository`.
* `src/config/lifespan.py` opens the Turso connection, applies the schema, checks the marker,
  and exposes `app.state.trip_db`.
* New settings: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `TRIPS_REQUIRE_MIGRATION_MARKER`.
  `docker/.env.template` uses a `file:` URL + `TRIPS_REQUIRE_MIGRATION_MARKER=False` so
  `just docker-up` boots without a migration step; `.env.example` is production-shaped.
* CI gains an `integration` job (`pytest -m integration`, first time integration runs in CI)
  and a `driver-parity` job (adapter + repository suite on `libsql`).
* `just migrate-trips-to-turso *ARGS` runs the migration; the 9-step rollout is documented in
  the README.

### Future Potential

* `compression='zlib'` on the snapshot column is a localised change (the reader already
  branches on the column).
* A follow-up PR may drop the legacy Mongo `trips` collection once the safety window passes.
* Embedded replicas / Turso Sync / offline-first are possible later but out of scope here.

## Consequences

### Positive Outcomes

* Every persisted state has a matching immutable history row, written atomically.
* Users can list, view, and restore any earlier revision; restore is instant (byte copy) and
  keeps provenance.
* One transactional writer for trips; provenance is type-enforced; the runtime has zero
  dependency on the legacy Mongo `trips` collection.
* `list_all()` is a column-only query with a real index.

### Challenges & Mitigation

* **Turso is a hard runtime dependency (no Mongo fallback).** Accepted by design; a fallback
  would re-introduce dual persistence. `/trips` endpoints 5xx via the global handler on an
  outage.
* **Cutover write-loss window.** Mitigated by the write freeze + disposable-trip write smoke;
  rollback limits are documented honestly.
* **Two drivers can drift.** Mitigated by the Linux driver-parity CI job.
* **Committed `docker/.env` secrets (pre-existing).** Not widened — Turso keys are only empty
  placeholders in `.env.template` / `.env.example`; flagged for a separate fix.

## Status

`Accepted` — project-wide for the persisted-trip domain. Amends ADR-02, ADR-06 (scope),
ADR-18 (list denormalization), and ADR-20 (persistence backend, revert tool). References
ADR-04 (integration tests) and ADR-19 (generated contracts).
