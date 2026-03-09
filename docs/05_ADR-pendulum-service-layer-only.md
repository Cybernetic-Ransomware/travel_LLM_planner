# ADR-05: pendulum used only in the service layer, not in Pydantic models

## Context
The project needs timezone-aware datetime handling. `pendulum` was introduced to replace `datetime.now(timezone.utc)` with the more expressive `pendulum.now("UTC")`. The natural next step was to use `pendulum.DateTime` as field types in Pydantic models (`ImportResponse.scraped_at`, `PlaceOut.scraped_at`, etc.) for richer datetime semantics.

At runtime this caused `PydanticSchemaGenerationError`: pendulum 3.x dropped its Pydantic v1 compatibility shim and `pendulum.DateTime` no longer registers a JSON schema with Pydantic v2. FastAPI's OpenAPI generation fails on startup.

## Decision
Use `pendulum.now("UTC")` only inside router and service functions where the value is created. All Pydantic model fields that carry datetime values use the standard `datetime` type from the Python standard library. No pendulum types appear in any model definition.

## Rationale
### Evaluation of Alternatives
- **Keep `pendulum.DateTime` in models + write a custom Pydantic validator** — possible but fragile; the validator would need updating with every pendulum major version.
- **Downgrade to pendulum 2.x** — retains Pydantic v1 compatibility shim but conflicts with Python 3.14 support.
- **Replace pendulum with `datetime.now(timezone.utc)` everywhere** — works but loses the ergonomic timezone API in the parts of the code that benefit from it.
- **Service-layer-only use (chosen)** — `pendulum.DateTime` is a subclass of `datetime`, so values produced by `pendulum.now("UTC")` are accepted by Pydantic `datetime` fields without coercion. No custom validators needed.

### Technical Considerations
- `pendulum.DateTime` subclasses `datetime` — assignment to a `datetime` field is type-safe and passes `ty` checks.
- Pydantic serialises the value as a standard ISO 8601 string regardless of whether the runtime object is `datetime` or `pendulum.DateTime`.
- The rule is enforced by `ty` type checking: model fields typed as `datetime` reject `pendulum.DateTime` annotations at the type level.

### Integration with Existing Environment
- `pendulum` remains a production dependency (used in `router.py` and `storage.py`).
- No changes required in MongoDB storage: Motor serialises `datetime` objects natively as BSON Date.
- The distinction is documented here so future contributors do not reintroduce `pendulum.DateTime` in model fields.

### Future Potential
If pendulum 4.x or a successor library restores Pydantic v2 compatibility, model fields can be migrated to richer types without breaking the API contract.

## Consequences
### Positive Outcomes
- FastAPI starts without schema generation errors.
- Ergonomic `pendulum.now("UTC")` available where timestamps are created.
- Standard `datetime` in models keeps the API contract simple and compatible with any serialiser.

### Challenges & Mitigation
- Easy to accidentally add `pendulum.DateTime` to a model field. Mitigated by `ty` catching the mismatch and this ADR documenting the constraint.

## Status
`Accepted` — project-wide. Effective from the `features/basic_ui` branch.
