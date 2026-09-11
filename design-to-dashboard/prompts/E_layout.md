# Stage E — Layout

**Input:** the design image, plus Stage A `regions` (`region_id`, `bbox`, `role`, `title` only) + `global`, Stage C `decisions` (`ref`, `region_id`, `slice_name`, `decision`).
**Not in context:** datasets, control schemas, `params`.
**Output:** `LayoutPlan` — the dashboard's `position_json`.

Geometry, but not blind geometry. You translate the design into Superset's 12-column grid. You do not touch data or chart configuration.

## You can see the design

**Look at it before you place anything.** The region list gives you boxes in
design pixels; the image gives you what those boxes look like as a page.

Read off it: which sections share a row, how wide each is relative to its
neighbours, which cards are equal height and which are deliberately not, where
a row break falls, and how much breathing room sits between rows. A row of
cards that looks even in the design must be even in the grid — matching boxes
to the nearest column while the result looks ragged is the wrong trade.

If no image is attached, work from the boxes alone.

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
                 "meta": { "chartId": "__REF__:c1", "sliceName": "...",
                           "sliceNameOverride": "what the design's card header says, or \"\"",
                           "uuid": "<uuid4>", "width": 6, "height": 50 } }
}
```

Node types: `ROOT`, `GRID`, `ROW`, `COLUMN`, `CHART`, `TABS`, `TAB`, `MARKDOWN`, `HEADER`, `DIVIDER`.

## Rules

- **Root chain is fixed.** `ROOT_ID → GRID_ID → rows`. When `global.tabs` is present: `ROOT_ID → TABS-<id> → TAB-<id> → ROW-...`, and each tab's rows sit under its `TAB` node.
- **`width` is in twelfths of `content_box`, not of the canvas.** `content_box`
  is supplied: the area the surviving regions actually occupy, with the app
  shell already excluded. Convert each region's `bbox.w` as a fraction of
  `content_box.w`, scale by 12, round to an integer ≥ 1. Measure `x` from
  `content_box.x`, not from 0. Dividing by `global.canvas.w` counts a nav rail
  the dashboard does not have and makes every card a column or two too narrow.
- **Every `ROW`'s child widths must sum to ≤ 12.** After rounding, if a row overflows, shrink the widest child until it fits and record the adjustment. If it underflows by 1–2, widen the widest child to fill the row.
- **`height` is in units of `GRID_BASE_UNIT` (8px), and is proportional.** Compute it, do not pick it from memory:

  `height = round(bbox.h / content_box.h × total_units) + 5`

  where `total_units` is the whole design's height in grid units. The `+ 5`
  is Superset's chart header — roughly 40px of chrome the design does not
  draw, taken out of the card's content area. Omit it and the content is
  clipped: a KPI card sized at the design's own ratio has no room left for
  its number.
- **A row's children all get the same height.** Superset lays a row out as one
  band, so three KPI tiles are one height, not three roundings of the same
  number. Use the tallest.
- **Rows come from vertical bands, not from exact y values.** Regions whose `bbox.y` ranges overlap by more than half their height belong in the same `ROW`. Do not create one row per region.
- **Preserve `global.reading_order`.** A dashboard that matches visually but scrambles the narrative order is wrong.
- **Charts reference `__REF__:<ref>` placeholders**, never numeric ids — the orchestrator substitutes real ids after chart creation.
- **Every node needs a correct `parents` array** listing its full ancestor chain from `ROOT_ID`. Superset's drag-and-drop breaks without it.
- **`uuid` is a fresh uuid4 per CHART node.**
- **Skip `decoration` regions** and any decision of `drop`. Skip `native_filter` decisions — those live in `json_metadata`, not the grid.
- **Never lay out a wrapper's children.** When a decision has a `children` array (a `wrap`, or a `new_plugin` with `plugin_archetype: "composite"`), the parent gets **one** CHART node and the children get **none** — they are rendered inside the parent, by the parent. Giving a child its own grid node draws it twice: once in the wrapper and once loose on the dashboard.
- **A `filter_widget` plugin does get a grid node.** It is a chart that happens to filter, so it sits in the layout where the design draws it — unlike a `native_filter`, which does not.
- **Set `sliceNameOverride` to the label the design shows.** A chart's
  `slice_name` is long on purpose so it is findable among hundreds
  (`Video Game Sales Overview — Global Sales`), but the design's card says
  `Global Sales`. `sliceNameOverride` changes the header on this dashboard
  only and leaves the chart's real name alone. Where the design draws **no**
  header on the card, set it to `""`.
- **`header` / `text` regions** become `MARKDOWN` nodes with the visible text, or `HEADER` nodes for section titles. A `grid_text` decision is exactly this: place it where its bbox says, using its `text`. It occupies a cell but is not a chart, so it gets no `ref` in `meta`.

## Output

```json
{
  "status": "ok",
  "position_json": { },
  "adjustments": [{ "row_id": "ROW-2", "issue": "widths summed to 13", "resolution": "CHART-4 6->5" }],
  "unplaced": [{ "ref": "c7", "reason": "..." }]
}
```

`adjustments` must list every rounding compromise — this is what a reviewer
checks against the design.

`unplaced` is for a ref you could find **no** home for; anything left there
blocks the apply. A child its parent draws is not one of those — record it in
`unplaced` with the reason, naming the parent, and it is accepted rather than
treated as a lost section. Never give such a child a grid node to keep the list
empty: that draws it twice, which no check will tell you about.
