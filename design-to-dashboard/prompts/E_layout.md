# Stage E — Layout

**Input:** the design image, plus Stage A `regions` (`region_id`, `bbox`, `role`, `title`, `tab`) + `global`, Stage C `decisions` (`ref`, `region_id`, `slice_name`, `decision`), the measured `content_box` and `total_units`, and any `user_answers` Stage C collected.
**Not in context:** datasets, control schemas, `params`.
**Output:** `LayoutPlan` — the dashboard's `position_json`.

Geometry, but not blind geometry. You translate the design into Superset's 12-column grid. You do not touch data or chart configuration.

## You can see the design

**Look at it before you place anything.** The region list gives you boxes as
**fractions of the image**, `0.0` to `1.0`; the image gives you what those
boxes look like as a page. A box with `w: 0.5` is half the page wide, whatever
size the copy you are looking at happens to be.

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

Node types: `ROOT`, `GRID`, `ROW`, `COLUMN`, `CHART`, `TABS`, `TAB`, `HEADER`, `DIVIDER`. `MARKDOWN` is a real Superset node type and is deliberately not in this list — see below.

## Rules

- **Root chain is fixed.** `ROOT_ID → GRID_ID → rows`. When `global.tabs` is
  present: `ROOT_ID → TABS-<id> → TAB-<id> → ROW-...`, and each tab's rows sit
  under its `TAB` node. Each region carries a `tab` saying which one it belongs
  to — use it rather than guessing from geometry, because every tab's regions
  occupy the same boxes.
- **`width` is in twelfths of `content_box`, not of the canvas.** `content_box`
  is supplied: the area the surviving regions actually occupy, with the app
  shell already excluded. Convert each region's `bbox.w` as a fraction of
  `content_box.w`, scale by 12, round to an integer ≥ 1. Measure `x` from
  `content_box.x`, not from 0. Dividing by `global.canvas.w` counts a nav rail
  the dashboard does not have and makes every card a column or two too narrow.
- **Every `ROW`'s child widths must sum to ≤ 12.** After rounding, if a row overflows, shrink the widest child until it fits and record the adjustment. If it underflows by 1–2, widen the widest child to fill the row **and record the adjustment** — a check runs after you that fails the layout for a row left 1–2 columns short with no `adjustments` entry naming it, because an unrecorded underflow of that size has turned out to mean unfinished arithmetic, not a deliberate gap, every time it has been checked against the actual page. If the gap is genuinely the design's own intent, say so in `adjustments` rather than leaving it silent.
- **A `filter`-role card has a column floor of 3, whatever its measured bbox
  says.** Its content is fixed text — a label, a date range — not something
  stage D will shrink to fit, so a design drawn narrow (a date-range pill at
  0.145 of the page rounds to 2 columns) still needs room for that text or it
  truncates. This floor is enforced mechanically after you place the grid, not
  left to you to remember; widening a `filter` card that already meets it, or
  widening any other role on the same theory, is not something the check does
  and not something you should do either — only a `filter`'s content is fixed
  enough to predict a floor for.
- **`height` is in units of `GRID_BASE_UNIT` (8px), and is proportional.** Compute it, do not pick it from memory:

  `height = round(bbox.h / content_box.h × total_units) + 5`

  `total_units` is **supplied** — the content's height in grid units, measured
  from the real image. Do not derive it, and do not substitute a number of
  your own; it is the only pixel fact in your input and every card's height is
  a ratio against it. When it is `null` the image size could not be read: fall
  back to `600` so the page still has sane proportions, and say so in
  `adjustments`. The `+ 5`
  is Superset's chart header — roughly 40px of chrome the design does not
  draw, taken out of the card's content area. Omit it and the content is
  clipped: a KPI card sized at the design's own ratio has no room left for
  its number. Where the chrome pass hides that header instead, the reserved
  space is given back mechanically after you place the grid — you do not need
  to omit the `+ 5` yourself for a headerless card.

  The `+ 5` header allowance assumes the header row is where Superset draws
  a card's overflow menu. A region that draws its own action (a `link`, most
  often "View all →") hides that menu no matter what — the design already
  drew a control there, and Superset's menu would be a second one beside it —
  which leaves the action with no header to sit in even when the header
  itself is still drawn. That action still has to render somewhere, and the
  only place left is the card's own body, one chrome row taller than its
  bbox ratio says. This, too, is given back mechanically, not something you
  need to add by hand — it is the reverse of a *headerless* card's
  allowance, not a substitute for it: the two never apply to the same card.
- **A row's children all get the same height.** Superset lays a row out as one
  band, so three KPI tiles are one height, not three roundings of the same
  number. Use the tallest.
- **Rows come from vertical bands, not from exact y values.** Regions whose `bbox.y` ranges overlap by more than half their height belong in the same `ROW`. Do not create one row per region.
- **Preserve `global.reading_order`.** A dashboard that matches visually but scrambles the narrative order is wrong.
- **Charts reference `__REF__:<ref>` placeholders**, never numeric ids — the orchestrator substitutes real ids after chart creation.
- **Every node needs a correct `parents` array** listing its full ancestor chain from `ROOT_ID`. Superset's drag-and-drop breaks without it.
- **`uuid` is a fresh uuid4 per CHART node.**
- **Skip `decoration` regions** and any decision of `drop`.
- **Never lay out a wrapper's children.** A placement's `children` lists the refs that parent draws inside itself (a `new_plugin` with `plugin_archetype: "container"`): the parent gets **one** CHART node and every ref in its `children` gets **none**. Giving a child its own grid node draws it twice: once in the wrapper and once loose on the dashboard. Every placement not listed under another placement's `children` gets its own grid node — including a chart whose section on the page has no placement, because the frame that would have drawn it was dropped. Place those charts where their regions sit.
- **A `filter_widget` plugin gets a grid node like any other chart.** It is a chart that happens to filter, so it sits in the layout exactly where the design draws it.
- **Set `sliceNameOverride` to the label the design shows.** A chart's
  `slice_name` is long on purpose so it is findable among hundreds
  (`Video Game Sales Overview — Global Sales`), but the design's card says
  `Global Sales`. `sliceNameOverride` changes the header on this dashboard
  only and leaves the chart's real name alone. Where the design draws **no**
  header on the card, set it to `""`.
- **A `grid_text` decision becomes a `HEADER` node**, placed where its bbox
  says, its `text` copied into `meta.text`. It occupies a cell but is not a
  chart, so it gets no `ref` in `meta`.
  **A `grid_text` decision is always one line by the time it reaches you.**
  A `HEADER` node's `meta.text` holds exactly that one line -- there is no
  other native node this pipeline builds text on. Do not reach for
  `MARKDOWN`: it is a real Superset node type, but its own rendering always
  wraps content in a scrolling container no design draws, so it is not one
  of the node types available to you at all. A `grid_text` decision whose
  `text` carries more than one line — a title with a subtitle, written as
  `"**Title**\n\nSubtitle."` — is stage C's mistake, not yours to work
  around: it should have been `configure: custom_text` instead, which has
  its own `Text` and `Sub-text` controls built for exactly this shape. Place
  the `HEADER` node with just the first line and move on; the missing plan
  gets caught and sent back to stage C, not patched here.

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
