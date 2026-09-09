# The UI — where it lives and how the user moves through it

Verified against Superset 6.1.0 source.

## Why not an extension

The obvious instinct is to ship this through 6.1's extensions architecture. It can't carry it: the available extension points are **`sqllab` and `editors` only**, and the contribution types are views, commands, and menus — all scoped to existing surfaces. There is no way to contribute a new top-level page.

So this is a **first-class SPA route** in the host application, gated by a feature flag.

## Wiring it in

### 1. Feature flag

```python
# superset/config.py — DEFAULT_FEATURE_FLAGS
"DESIGN_TO_DASHBOARD": False,
```

Add the matching member to the `FeatureFlag` enum in `@superset-ui/core` so the frontend can gate on it.

### 2. Frontend route

`superset-frontend/src/views/routes.tsx` already gates routes behind flags — `FeatureFlag.TaggingSystem` (line ~335) and `FeatureFlag.EnableExtensions` (line ~367) are the patterns to copy.

```tsx
const DesignToDashboard = lazy(
  () => import(
    /* webpackChunkName: "DesignToDashboard" */ 'src/pages/DesignToDashboard'
  ),
);

if (isFeatureEnabled(FeatureFlag.DesignToDashboard)) {
  routes.push({
    path: '/design-to-dashboard/',
    Component: DesignToDashboard,
  });
}
```

Lazy-loaded with a `webpackChunkName`, matching every other page — the bundle cost is zero for instances with the flag off.

### 3. Navigation entry

`superset/initialization/__init__.py`, alongside the existing `appbuilder.add_link(...)` calls:

```python
if feature_flag_manager.is_feature_enabled("DESIGN_TO_DASHBOARD"):
    appbuilder.add_link(
        "Design to Dashboard",
        label=__("Design to Dashboard"),
        href="/design-to-dashboard/",
        category="",           # top-level, next to Dashboards/Charts
        category_label=__(""),
        icon="fa-wand-magic-sparkles",
    )
```

Second entry point worth adding: a **"From a design"** option on the Dashboard list's *+ Dashboard* affordance, since that's where users already are when they want a new dashboard.

### 4. Page shell

`superset-frontend/src/pages/DesignToDashboard/index.tsx`, with the feature components under `src/features/designToDashboard/`. That split matches the rest of the codebase — thin page, real components in `features/`.

## The interaction model

**A pure chat box would be the wrong UI here.** You cannot review a twenty-region decision table in a chat bubble, and the pipeline has two hard gates that need real interface. The chat is the *spine*; the value is in structured review cards rendered inline between messages.

```
┌──────────────────────────────┬──────────────────────────┐
│  conversation + review cards │   live preview pane      │
│                              │                          │
│  ① upload + requirement      │  design image            │
│  ② regions found  [review]   │  ↓ overlay bboxes        │
│  ③ questions      [answer]   │  ↓                       │
│  ④ plan           [approve]  │  layout preview          │
│  ⑤ building…                 │  ↓                       │
│  ⑥ done → open dashboard     │  the dashboard           │
└──────────────────────────────┴──────────────────────────┘
```

### The six states

**① Upload + requirement.** Drop a Figma export, screenshot, or PDF; type the requirement. One submit.

**② Region review** — *stage A output.* The design image with bounding boxes overlaid, each labelled with its `role` and `title`. The user can rename, merge, split, or drop a region.

This is the **cheapest correction point in the whole system**. A misread here propagates through binding, resolution, and N parallel configure workers before surfacing as a wrong dashboard. Ten seconds of review saves a full re-run. Make it skippable for confident runs, never absent.

**③ Blocking questions** — *stage B `needs_input`.* Rendered as a single batched form, not a chat interrogation. Each question shows the region thumbnail, what's missing, and the options from the prompt contract (drop / point at a dataset / substitute a measure / create a virtual dataset). Nothing has been created at this point.

**④ Plan review** — *stage C.* The decision table: region, decision, `viz_type`, rationale, fidelity loss. Grouped by decision with the counts up top — *"1 reused, 6 configured, 1 wrapped, 0 new plugins"*. Reuse rows link to the existing chart; `fidelity_loss` is shown inline, not hidden behind a tooltip.

This gate is **mandatory when `counts.new_plugin > 0`** and optional otherwise. When a new plugin is proposed, the card must say plainly that it needs code review and a deploy, and that the dashboard will be created partially now and completed after (see `PLUGIN_DEPLOYMENT.md`).

**⑤ Building.** Stage D fans out; stream per-chart progress as it lands. Stage E's `adjustments` array surfaces here — *"row 2 widths rounded, chart 5 narrowed 8→7"* — so grid compromises are visible rather than discovered later.

**⑥ Result.** Link to the dashboard, plus the honest summary: charts created, charts reused, adjustments, fidelity notes, and any pending regions blocked on a plugin deploy.

### Streaming

`POST /api/v1/design_to_dashboard/session/<uuid>/message/` returns SSE. Each stage emits `stage_start`, `stage_progress`, `stage_complete` with its contract object as payload; the UI renders the matching card on `stage_complete`. Stage D emits one event per worker so the fan-out is visible rather than a spinner.

## What to build first

The gates are worth more than the chat. A working flow with a plain form for ① and real review UI for ② and ④ is genuinely useful; a beautiful chat wrapped around unreviewable output is not.

1. Page shell + route + flag
2. Upload form and session creation
3. `RegionReview` — gate ②
4. `PlanReview` — gate ④
5. SSE streaming and progress
6. `DashboardPreview` — render `position_json` before commit
7. Conversational refinement — *"make the KPI row four across"* — last

Step 7 is the one everyone wants to build first. It's only safe once ② and ④ exist, because refinement without review is how you get a confidently wrong dashboard with no audit trail.
