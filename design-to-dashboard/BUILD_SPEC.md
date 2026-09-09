# Build spec — Design-to-Dashboard chat in CloudKeeper Analytics (Superset fork)

> Hand this to Claude Code / a developer as the engineering brief.
> Repo: `~/Documents/cloudkeeper-analytics` (Superset 6.0.0 fork, branch `integration`).
> Verified: no LLM/AI code exists in this repo today — this is greenfield.

## 1. Goal

A user opens a chat panel in Superset, uploads a Figma export or screenshot of a dashboard, types what they want, and gets a real dashboard created in the instance — charts bound to real datasets, laid out to match the design, with filters wired. Where the design needs a visualization the fork doesn't have, the system produces a reviewable custom-plugin scaffold rather than failing.

**Non-goal (v1):** auto-deploying new plugin code. New plugins are emitted as a branch/patch for human review and a normal build+deploy. The chat never hot-loads code into a running instance.

## 2. Why this shape

The fork already carries 20 `plugin-chart-custom-*` plugins, including `custom_wrapper` (tabbed multi-chart widget) and `container_chart` (mini-dashboard in one cell). Most designs are therefore a *configuration* problem, not a *codegen* problem. The system must be biased hard toward reuse; codegen is the escape hatch, gated behind explicit user approval.

## 3. Architecture

```
┌─ superset-frontend/src/features/designToDashboard/ ─────────┐
│  ChatPanel.tsx        conversation UI, streaming             │
│  DesignUpload.tsx     image/PDF drop + Figma URL             │
│  RegionReview.tsx     stage A output — cheapest review point │
│  PlanReview.tsx       stage C decision table, approve gate   │
│  DashboardPreview.tsx renders position_json before commit    │
└──────────────────────────────────────────────────────────────┘
                    │ REST + SSE
┌─ superset/design_to_dashboard/ ─────────────────────────────┐
│  api.py              DesignToDashboardRestApi (FAB BaseApi)  │
│  orchestrator.py     runs the 6-stage graph, gates, retries  │
│  stages/                                                     │
│    a_decompose.py    vision call                             │
│    b_bind.py         dataset binding                         │
│    c_resolve.py      decisions + design-system contract      │
│    d_configure.py    per-chart fan-out (parallel)            │
│    e_layout.py       position_json geometry                  │
│    f_scaffold.py     plugin codegen (rare, gated)            │
│  llm/client.py       Anthropic client, streaming, retries    │
│  llm/prompts/        one file per stage + shared preamble    │
│  schema.py           pydantic models for every stage contract│
│  context.py          registry/dataset/chart introspection    │
│  applier.py          plan -> charts + dashboard, transactional│
│  models.py           DesignSession, DesignPlan (UUID PKs)    │
└──────────────────────────────────────────────────────────────┘
```

Stage boundaries, ref indirection, the applier algorithm, retry policy and caching are specified in **`PIPELINE_CONTRACT.md`**. Stage prompts live in `prompts/`.

### Endpoints (`/api/v1/design_to_dashboard/`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/session/` | Create a session; returns UUID |
| POST | `/session/<uuid>/asset/` | Upload design image/PDF; returns asset id |
| POST | `/session/<uuid>/message/` | Send requirement; SSE stream of the model's plan |
| GET | `/session/<uuid>/plan/` | Latest structured plan (the JSON contract) |
| POST | `/session/<uuid>/apply/` | Execute approved plan; returns dashboard id |
| GET | `/session/<uuid>/` | Session + history |

### Context assembly

Superset 6.1's MCP server supplies most of it. Stages B and C call tools directly (see `MCP_INTEGRATION.md`); only the viz registry is ours to build.

- **Datasets** — `list_datasets`, `get_dataset_info` (MCP). Permission-filtered, already schema'd. Replaces hand-rolled dataset introspection.
- **Existing charts** — `list_charts`, `get_chart_info` (MCP). The reuse index.
- **SQL validation** — `execute_sql` (MCP), to prove a derivable metric before building on it.
- **Viz registry** — **ours.** MCP's `get_chart_type_schema` covers only seven abstract families (`xy`, `table`, `pie`, `pivot_table`, `mixed_timeseries`, `handlebars`, `big_number`) and cannot describe our 20 custom plugins. Generate a build-time JSON manifest from the frontend's `getChartMetadataRegistry()`: **summaries** (key, name, category, tags, description, behaviors) for stage C, **full control schemas** for stage D — one per worker.

### Applier (`applier.py`)

Executes the approved plan **in-process through existing Superset commands**, not by re-entering the HTTP API: validate → create charts (children first) → resolve `__REF__` placeholders → create dashboard → write `position_json` + `json_metadata` → verify. **Not transactional** — Superset's commands carry `@transaction` and commit independently, so an outer `begin_nested()` is defeated by the first commit. The applier records what it creates and deletes it on failure instead. Full algorithm and the failure modes in `PIPELINE_CONTRACT.md`.

## 4. Constraints the implementation must respect

- **Custom plugins register only in `superset-frontend/src/setup/setupPluginsExtra.ts`.** `MainPreset.js` is upstream code and must stay untouched so Superset upgrades merge cleanly.
- **Plugins import `@superset-ui/*` only through their own `src/adapters/supersetAdapter.ts` barrel** (see `plugin-chart-custom-kpi` for the canonical shape).
- Per `CLAUDE.md`: TypeScript only, no `any`, functional components, `@superset-ui/core/components` over direct antd, antd theme tokens, minimal custom CSS; Python fully typed and mypy-clean; Jest + RTL for tests; UUID primary keys on new models.
- Dashboard grid: `GRID_COLUMN_COUNT = 12`, `GRID_BASE_UNIT = 8`.
- Feature-flagged: `DESIGN_TO_DASHBOARD_ENABLED`, default off.

## 5. Security & cost

- Design uploads are user content — store outside the web root, scan MIME, cap size, expire on a TTL.
- The LLM's output is **untrusted data**. Validate every plan against a pydantic schema *and* re-check that referenced datasets/columns/viz_types exist and are permitted **server-side** before applying. Never `eval`, never pass model output into raw SQL.
- Generated plugin code is written to a branch/patch for review — never executed or bundled automatically.
- Stages B and C call MCP tools under the requesting user's RBAC (`mcp_auth_hook`, `check_chart_data_access`), so they cannot reach data the user can't read. Tool output is still untrusted input — validate before use.
- Enforce per-user rate limits and a token budget; images are expensive. Prompt-cache the static system prompt and the registry dump.
- Audit-log every apply: who, which session, which plan hash, which dashboard.

## 6. Delivery order

1. Context introspection + registry manifest (no LLM) — provably correct inputs first
2. Models, migrations, session/asset endpoints
3. MCP gateway — in-process tool access for B and C
4. Pydantic schemas for all six stage contracts — the spine everything else validates against
5. Stages A → B → C with their gates; plan generation only, no apply
6. `RegionReview.tsx` + `PlanReview.tsx` approve gates
7. Stages D (fan-out) and E
8. Applier with transactional rollback
9. Chat panel and streaming UX
10. Stage F plugin scaffolding (last — the escape hatch, not the core)

## 7. Acceptance

- A screenshot of an existing CloudKeeper dashboard round-trips to a functionally equivalent new dashboard using **zero** new plugins.
- A design needing a tabbed multi-chart card resolves to `custom_wrapper`, not a new plugin.
- A design with an unavailable metric returns `status: "needs_input"` with a batched question and creates nothing.
- A malformed/adversarial model response is rejected by schema validation and creates nothing.
- Every row in every generated `position_json` has child widths summing to ≤ 12.
