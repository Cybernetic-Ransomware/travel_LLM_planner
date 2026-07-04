# Frontend Architecture Roadmap

[ADR-14](14_ADR-astro-svelte-spike.md) (accepted 2026-07-04, Option C) established the split:
two apps coexist, each with a defined role. This document encodes which app owns which screens
and provides a decision rule so new screens don't require a framework discussion from scratch.

## Current split

| App | Path | Screens |
|-----|------|---------|
| Astro | `apps/astro-frontend/` | `/` public dashboard · `/places` read-only list + map island · `/health` connectivity check · `/route-preview` optimizer workflow island |
| SvelteKit | `apps/frontend/` | `/` authenticated entry · `/places` places management (edit, enrich) · `/optimizer` route optimizer workflow · `/trip` trip view · `/health` backend status |

## Framework decision rule

**Use Astro when:**

- Screen is public (no auth or minimal auth)
- Data is read-only
- Interactivity fits in one self-contained island
- No shared state between components

**Use SvelteKit when:**

- Screen requires authentication
- Screen is an application workflow (forms, edits, dialogs)
- State is shared across components (map marker ↔ list ↔ form)
- Feature needs orchestrator/chat, drag & drop, or realtime polling

## Upcoming PRs

1. Public Astro landing / docs
2. SvelteKit: backend-down error handling
3. SvelteKit: proper route planner
4. Types from OpenAPI
5. Spike cleanup after ADR-14 decision
