# Frontend spike measurements: Astro islands vs SvelteKit

Quantitative comparison of `apps/frontend` (SvelteKit) and `apps/astro-frontend` (Astro + Svelte
islands) supporting the A/B/C decision in [ADR-14](14_ADR-astro-svelte-spike.md). This document
reports data only; the decision itself belongs in the ADR.

## Methodology

- Measured on 2026-07-03 with `scripts/measure_frontends.py` (Playwright chromium, production
  builds served by `vite preview` / `astro preview`). Rerun with:
  `uv run python scripts/measure_frontends.py --build-runs 3`.
- Prerequisites for a rerun: the Playwright Chromium binary (one-time
  `uv run playwright install chromium`; the Python package is already a project dependency)
  and a production build of both apps (`npm ci` + `npm run build` in `apps/frontend` and
  `apps/astro-frontend`).
- Environment: Windows 11, Node v26.3.1, Astro 7.0.6 (Vite 8), SvelteKit 2.57 (Vite 8.0.8),
  Svelte 5.55/5.56, Tailwind v4. CI (`astro-ci.yml`) builds on the same Node major (26).
- Backend: real Docker stack (`just docker-up`), dataset of **3 places** (places API response
  ≈ 4.1 kB). Payload numbers barely depend on dataset size, but the fetch column does.
- Byte counts are **uncompressed** response bodies. Neither preview server compresses, so this is
  the actual local transfer; production gzip would shrink both apps roughly proportionally
  (reference point: the SvelteKit build log reports ~3x gzip ratio on its largest chunks).
- Routes measured until network idle, before any interaction. A second run reproduced all numbers
  within 0.2 kB.
- SvelteKit had no `/health` screen; a minimal one (page + `/api/health` proxy endpoint) was added
  as part of this measurement so the comparison covers the same three screens.

## Initial payload and requests

| App | Route | Requests | JS kB | CSS kB | HTML kB | API fetch kB | Total kB |
|---|---|---|---|---|---|---|---|
| sveltekit | / | 19 | 125.0 | 32.5 | 12.1 | 0.0 | 169.6 |
| sveltekit | /places | 29 | 280.1 | 47.3 | 14.9 | 0.0 | 551.0 |
| sveltekit | /health | 19 | 120.3 | 32.5 | 8.3 | 0.0 | 161.1 |
| astro | / | 8 | 40.2 | 10.8 | 5.8 | 4.1 | 60.9 |
| astro | /places | 9 | 48.3 | 10.8 | 5.8 | 4.1 | 69.1 |
| astro | /health | 7 | 40.1 | 10.8 | 6.2 | 0.0 | 57.2 |

Notes:
- SvelteKit fetches data server-side (`+page.server.ts`), so its API column is zero; the data is
  embedded in the HTML payload instead. Astro islands fetch client-side after hydration.
- SvelteKit `/places` includes Leaflet and OpenStreetMap tiles in the initial load because the map
  is visible by default (see next section); that accounts for most of the 551 kB total.
- Astro ships **3.1x less JS** on the dashboard and health screens (40 vs ~120–125 kB) and
  **5.8x less** on `/places` as initially rendered (48 vs 280 kB).

## Leaflet loading on /places

| App | Map visible by default | Leaflet in initial load | Loads after "Show map" | Extra requests | Extra kB |
|---|---|---|---|---|---|
| sveltekit | yes | yes | n/a (already loaded) | 0 | 0 |
| astro | no | no | yes | 2 | 145.3 |

Both apps code-split Leaflet via dynamic `import('leaflet')`. The difference is a product decision,
not a framework property: SvelteKit's `/places` defaults to `showMap = true`, so the chunk loads
eagerly; Astro defaults to hidden, so the 145.3 kB (JS + CSS) arrive only on demand. Flipping the
SvelteKit default would defer the same chunk.

## Build times

| App | Runs (s) | Median (s) |
|---|---|---|
| sveltekit | 4.7, 4.5, 4.9 | 4.7 |
| astro | 3.8, 3.7, 3.3 | 3.7 |

Same order of magnitude; not a deciding factor.

## API error visibility (backend stopped)

Captured visible page text with the Docker stack down (`--scenario down`):

| App | Route | What the user sees |
|---|---|---|
| sveltekit | / | Stats show zeros; no error indication at all |
| sveltekit | /places | "Nie znaleziono miejsc." (no places found); no error indication |
| sveltekit | /health | Clear: "Backend niedostępny … Bad gateway — sprawdź, czy backend działa…" |
| astro | / | "Cannot load stats: Cannot connect to the backend API" |
| astro | /places | "Cannot load places: Cannot connect to the backend API" |
| astro | /health | Clear: "Backend unavailable … check that the backend is running and that its CORS configuration allows this origin" |

The SvelteKit server loads swallow fetch failures and return empty defaults
(`routes/+page.server.ts`, `routes/places/+page.server.ts`), so a dead backend is indistinguishable
from an empty database. The Astro islands surface an explicit error on every screen. This is again
implementation choice rather than framework necessity, but the spike's client-side fetching made
the honest failure mode the default.

## Code ergonomics

Screen-specific source files and non-blank LOC (app shell — layout, nav, UI primitives — excluded
from both; shared data-access files listed separately):

| Screen | SvelteKit files / LOC | Astro files / LOC |
|---|---|---|
| / | 5 / 216 | 3 / 59 |
| /places | 10 / 525 | 6 / 290 |
| /health | 2 / 93 (+ nav link, 2 i18n entries) | 2 / 64 |
| shared data access | 3 / 129 (api client, gmaps api, proxy route) | 2 / 90 (api client, types) |

Caveats: the SvelteKit app does more per screen (i18n, dark mode, inline editing, delete dialog,
toasts, shared reactive state), so LOC is not a pure framework comparison. The `/health` screen is
the cleanest apples-to-apples case — built to the same spec in both apps: 93 LOC + 3 file edits
(SvelteKit needs a proxy endpoint and i18n entries) vs 64 LOC (Astro island calls the backend
directly).

## The key question: smaller JS or relocated complexity?

Astro client chunks on `/places` (from `dist/_astro/`):

| Chunk | kB |
|---|---|
| Svelte runtime + island client (`client.*.js`) | 38.3 |
| `PlacesExplorer` island (filters + table + stats + map toggle) | 8.9 |
| `StatCard` | 0.6 |
| `leaflet-src` (lazy, only after "Show map") | 145.3 |

The `PlacesExplorer` island — the thing that would "swell into a mini-app" — is currently 8.9 kB of
the 48.3 kB initial JS; the fixed cost is the 38 kB Svelte runtime/hydration layer, paid once
regardless of how many islands exist. So today the answer is: **yes, the shell genuinely shrinks**
(3–6x less initial JS, ~3x fewer requests), and the island is still small.

The honest counterpoint: `PlacesExplorer` already contains the filter/table/map composition that
SvelteKit spreads across load functions and shared state. Features that make the SvelteKit
`/places` heavier (inline editing, deletion, toasts, i18n) do not exist in the island yet. Each
one added moves the island toward the SvelteKit number, and interactive screens like the route
planner or chat would start near it. The measured advantage is real for mostly-static screens and
should be expected to erode in proportion to per-screen interactivity.

## Route planner preview

**Question:** Does a form-input → optimizer request → map-result workflow remain a small island,
or does it collapse into an SPA-in-one-component?

`/route-preview` is the first screen with a multi-step user workflow: select places → configure
start hour and transport mode → call the optimizer → display ordered route steps on a map. All
state lives in a single `RoutePreview.svelte` island; `LeafletMap.svelte` is reused unchanged.

Methodology: same as above (production build served by `astro preview`, network idle,
Playwright fresh browser context). Measured 2026-07-04 on the same dataset (3 active places).
The API fetch column is 0.0 because `astro preview` runs on port 4323, which is outside the
backend's default `CORS_ALLOW_ORIGINS`; at a CORS-allowed port the active-places fetch adds
~4.1 kB (same as `/places`). The "after map load" and "after optimizer result" columns require
a working Distance Matrix API key and are left TBD.

| App | Route | Requests | JS kB | CSS kB | HTML kB | API fetch kB | Total kB |
|---|---|---|---|---|---|---|---|
| astro | /route-preview | 7 | 51.9 | 12.9 | 6.0 | 0.0 (see note) | 70.8 |

For reference, the same build's numbers for the other three routes:

| App | Route | Requests | JS kB | CSS kB | HTML kB | API fetch kB | Total kB |
|---|---|---|---|---|---|---|---|
| astro | / | 7 | 42.7 | 12.9 | 5.9 | 0.0 | 61.5 |
| astro | /places | 8 | 50.8 | 12.9 | 5.9 | 0.0 | 69.7 |
| astro | /health | 6 | 42.6 | 12.9 | 6.3 | 0.0 | 61.8 |

The slight increase vs the 2026-07-03 measurements (e.g. `/places` 48.3 → 50.8 kB JS) reflects
the new `RoutePreview` island and its `SvelteSet` import expanding the shared Svelte runtime
chunk (~38.3 → 39.9 kB).

Astro client chunks on `/route-preview` (from `dist/_astro/`):

| Chunk | kB |
|---|---|
| Svelte runtime + island client (`client.*.js`) | 38.9 |
| `RoutePreview` island (selection + form + optimizer call + result list) | 6.9 |
| `LeafletMap` island (markers, polyline — lazy Leaflet import) | 4.2 |
| `leaflet-src` (lazy, only after optimizer result activates map) | 145.3 |

`RoutePreview` at 6.9 kB is 1.6 kB larger than `PlacesExplorer` (5.3 kB) despite handling a
noticeably more complex workflow. The fixed cost remains the ~39 kB Svelte runtime.

LOC: **178 non-blank lines** in `RoutePreview.svelte` (vs ~145 LOC for `PlacesExplorer`).

Qualitative assessment:

- [x] Island state cohesive — 8 `$state` variables form a single linear flow (fetch → form →
  request → result); no sub-state machines, no cross-island coordination.
- [x] Leaflet still lazy-loadable — same `onMount` dynamic import pattern; Leaflet fires only
  after the optimizer result renders `<LeafletMap>`, keeping the initial bundle at 51.9 kB.
- [x] Error handling straightforward — a backend error (`PERMISSION_DENIED` from Distance
  Matrix API tested live) surfaces as an explicit red banner; no silent failure.
- **Verdict: complex-but-coherent island.** More state than `PlacesExplorer`, but all of it
  belongs to one workflow and the framework did not fight back. The line to SPA-in-island is
  visible: any feature requiring coordination between the map markers and the place checklist
  (e.g. click marker → toggle selection) would need either a single larger island or a shared
  store — neither of which Astro makes easy without a workaround.
