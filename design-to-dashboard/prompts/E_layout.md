# Stage E — Layout

**Input:** Stage A `regions` (`region_id`, `bbox`, `role`, `title` only) + `global`, Stage C `decisions` (`ref`, `region_id`, `slice_name`, `decision`).
**Not in context:** datasets, control schemas, `params`, the design image.
**Output:** `LayoutPlan` — the dashboard's `position_json`.

Pure geometry. You translate pixel positions into Superset's 12-column grid. You do not touch data or chart configuration.

## Target structure

`position_json` is a **flat map of id → node**, not a tree. Parents reference children by id.

```json
{
  "DASHBOARD_VERSION_KEY": "v2",
  "ROOT_ID":   { "type": "ROOT",   "id": "ROOT_ID",   "children": ["GRID_ID"] },
  "GRID_ID":   { "type": "GRID",   "id": "GRID_ID",   "children": ["ROW-1"], "parents": ["ROOT_ID"] },
  "ROW-1":     { "type": "ROW",    "id": "ROW-1",     "children": ["CHART-1","CHART-2"],
                 "parents": ["ROOT_ID","GRID_ID"], "meta": { "background": "BACKGROUND_TRANSPARENT" } },
  "CHART-1":   { "type": "CHART",  "id": "CHART-1",   "children": [],
                 "parents": ["ROOT_ID","GRID_ID","ROW-1"],
                 "meta": { "chartId": "__REF__:c1", "sliceName": "...", "uuid": "<uuid4>", "width": 6, "height": 50 } }
}
```

Node types: `ROOT`, `GRID`, `ROW`, `COLUMN`, `CHART`, `TABS`, `TAB`, `MARKDOWN`, `HEADER`, `DIVIDER`.

## Rules

- **Root chain is fixed.** `ROOT_ID → GRID_ID → rows`. When `global.tabs` is present: `ROOT_ID → TABS-<id> → TAB-<id> → ROW-...`, and each tab's rows sit under its `TAB` node.
- **`width` is in twelfths.** Convert each region's `bbox.w` as a fraction of `global.canvas.w`, scale by 12, round to an integer ≥ 1.
- **Every `ROW`'s child widths must sum to ≤ 12.** After rounding, if a row overflows, shrink the widest child until it fits and record the adjustment. If it underflows by 1–2, widen the widest child to fill the row.
- **`height` is in units of `GRID_BASE_UNIT` (8px).** Convert `bbox.h` to that scale. Practical ranges: KPI tiles ~50, standard charts ~50–70, tall tables ~80–120.
- **Rows come from vertical bands, not from exact y values.** Regions whose `bbox.y` ranges overlap by more than half their height belong in the same `ROW`. Do not create one row per region.
- **Preserve `global.reading_order`.** A dashboard that matches visually but scrambles the narrative order is wrong.
- **Charts reference `__REF__:<ref>` placeholders**, never numeric ids — the orchestrator substitutes real ids after chart creation.
- **Every node needs a correct `parents` array** listing its full ancestor chain from `ROOT_ID`. Superset's drag-and-drop breaks without it.
- **`uuid` is a fresh uuid4 per CHART node.**
- **Skip `decoration` regions** and any decision of `drop`. Skip `native_filter` decisions — those live in `json_metadata`, not the grid.
- **`header` / `text` regions** become `MARKDOWN` nodes with the visible text, or `HEADER` nodes for section titles.

## Output

```json
{
  "status": "ok",
  "position_json": { },
  "adjustments": [{ "row_id": "ROW-2", "issue": "widths summed to 13", "resolution": "CHART-4 6->5" }],
  "unplaced": [{ "ref": "c7", "reason": "..." }]
}
```

`adjustments` must list every rounding compromise — this is what a reviewer checks against the design. `unplaced` must be empty for a clean run; anything in it blocks the apply.
