# VISORA BI — Web Frontend

Premium React interface for VISORA BI. This app is a **transport-only
client**: it never recomputes analytics. Every number, finding, chart
series and AI interpretation comes from the existing Python backend
through the FastAPI adapter in `../api/`.

```
React (this app)  →  /api/v1/*  →  FastAPI (api/)  →  backend/ (single source of truth)
```

## Stack

- React 19 + TypeScript + Vite
- Tailwind CSS v4 (design tokens in `src/styles/globals.css`, derived from the VISORA mark)
- Radix primitives + hand-rolled shadcn-style components (`src/components/ui`)
- Motion (entrance/hover/route animation) · Lucide icons · ECharts (chart rendering)
- Zustand for preferences/caches · sonner for toasts

## Running

```bash
npm install

# 1) API (from the repository root)
python -m uvicorn api.main:app --reload --port 8000

# 2) Frontend (this directory)
npm run dev            # http://localhost:5173, proxies /api → 127.0.0.1:8000
```

`VISORA_API_URL` overrides the proxy target. `npm run build` emits
`dist/`; `npm run typecheck` runs a strict TypeScript build.

## Verifying

```bash
npm run verify     # typecheck + headless route smoke + end-to-end flow
```

- `npm run smoke` walks all six routes in headless Chrome, failing on any
  console/page error and writing screenshots to `.smoke/`.
- `npm run flow` uploads a generated CSV, follows the success → detail →
  analyze → analytics → insights path, exercises the delete confirmation
  dialog (cancel + confirm), then cleans up and restores the workspace.

Both use the system Chrome/Edge (`CHROME_PATH` overrides the lookup) — no
browser download required.

## Structure

| Path | Purpose |
| --- | --- |
| `src/lib/api` | Typed API client, error mapping (human-readable `ApiError`), XHR upload with progress/cancel |
| `src/store/app-store.ts` | Persisted preferences (theme, sidebar, profile, selection) + in-memory report cache |
| `src/components/ui` | Design-system primitives (button, card, dialog, select, tabs, progress…) |
| `src/components/layout` | 240px collapsible sidebar, topbar, app shell, page header |
| `src/components/charts` | ECharts wrapper, theme palette hook, option builders |
| `src/components/motion` | Entrance/reveal/stagger/animated-number primitives |
| `src/pages` | Overview · Datasets · Dataset details · Analytics · AI Insights · Reports · Settings |

## State handling

Every data view implements **loading** (skeletons), **error** (friendly
message + retry — never a raw exception), **empty** (guidance + CTA) and
**success** states. Uploads add drag-over, progress, cancellation,
processing, retry and success-transition phases.

## Backend contract

Routes are defined in `api/main.py` and validated by
`tests/api_contract_validation.py` (49 checks, sandboxed):

`/api/v1/health`, `/overview`, `/datasets` (GET/POST upload),
`/datasets/{id}` (GET/DELETE), `/datasets/{id}/analyze`, `/reports`,
`/reports/current`, `/reports/{id}/text`, `/history/clear`, `/insights`.
