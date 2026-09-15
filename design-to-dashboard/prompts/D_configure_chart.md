# Stage D — Configure chart

**Input:** exactly one region (Stage A), its binding (Stage B), its decision (Stage C), the design-system contract, and the **full control-panel schema for that one `viz_type`**.
**Not in context:** other regions, other viz types, the design image, the full registry.
**Output:** one `ChartSpec`.

Runs once per chart, in parallel. You configure a single chart completely and correctly. You do not second-guess Stage C's `viz_type` choice.

## When this region is part of a `same_as` group

Stage A marks regions that are visually the same component repeated with
different data -- four KPI tiles reading AWS, GCP, Azure and Total spend off
one shared layout, say. Stage C already groups these (`same_as_groups`) and
holds them to one `viz_type` among themselves. Ordinarily that is the last
either of them has to do with each other: every chart is still configured by
an independent call that knows nothing about any other chart in the run.

A `same_as` group is the one exception, and only for the choices that are a
property of the *component itself* rather than of whichever slice of the data
any one copy happens to be scoped to: the aggregate function every metric
control uses, `row_limit`, and any colour, palette, font-size or number/date
format field. The first member of a group is configured exactly as any solo
chart is -- nothing to reference yet. Every member configured after it is
handed that finished chart's `params_decoded` as a **reference**, under a
`## Part of a same_as group` heading, with the same instruction every time:
copy the shared fields verbatim, and keep your own `adhoc_filters`,
`datasource_id`, and any label or caption text that names your own slice of
the data (`"AWS"` vs `"GCP"`) -- that difference is the entire reason these
are separate regions instead of one chart.

This reference is authoritative in the same way a stage-F `params_hint` is:
the *names* and *shared values* are not this call's to re-derive, only its own
scoping fields are. Four independently-reasoned copies of one KPI tile have
already disagreed on exactly this in a real run -- `SUM` on one card, `MAX` on
its sibling; `row_limit` 1000 against 1; a caption colour set on one of two
literally-identical placeholder tiles and left blank on the other -- and every
chart involved passed every check that only ever looked at it alone. Do not
reinvent a shared choice the reference already answered.

This is not only a matter of following instructions well: a mechanical check
runs across the whole group once every member is configured, and rejects the
group -- every member, not just whichever one looks like the outlier -- if a
shared field still disagrees. There is no partial credit for "everything else
about this chart was right"; a same_as group either matches on its shared
properties or the whole group is sent back.

## Job

Produce the `POST /api/v1/chart/` body that renders this region.

```json
{
  "ref": "c1",
  "region_id": "...",
  "request": {
    "method": "POST",
    "path": "/api/v1/chart/",
    "body": {
      "slice_name": "...",
      "viz_type": "...",
      "datasource_id": <the binding's dataset_id>,
      "datasource_type": "table",
      "params": "<JSON-ENCODED STRING>",
      "query_context": "<JSON-ENCODED STRING or null>"
    }
  },
  "params_decoded": { },
  "unmapped": [{ "observed": "...", "reason": "no control expresses this" }],
  "confidence": "high|medium|low"
}
```

`params_decoded` is the same object un-stringified, for review and validation. The orchestrator validates `params_decoded` against the control schema, then serialises it into `params`.

## Rules

- **`datasource_id` is the binding's `dataset_id`. Never `0`.** Superset
  requires a real datasource on every chart, including one that draws no data:
  a title, a text block, a card whose content is entirely static. Stage B
  creates one dataset for exactly this — one row, one column — and binds every
  such region to it. When your binding is marked `attached_only`, put its id in
  `datasource_id` and query nothing from it: no metrics, no groupbys, no
  filters invented to justify the datasource being there. A `0` is not a
  dataset and the run cannot be applied.
- **`params` and `query_context` are JSON-encoded *strings*, not nested objects.** This is the single most common failure against Superset's API. Get it right.
- **Every key in `params` must exist in your injected control schema.** If the design needs something the schema has no control for, do not invent a key — record it in `unmapped`. An unknown key is silently dropped by Superset and the chart renders wrong with no error.
- **Respect control types.** A `SelectControl` takes one of its declared `choices`. A metric control takes a saved metric name or a well-formed adhoc metric object. A `BoundsControl` takes `[min, max]`. Read the schema; do not pattern-match from other charts.
- **Adhoc metrics** use the full shape: `{ "expressionType": "SQL", "sqlExpression": "...", "label": "...", "hasCustomLabel": true, "optionName": "metric_<uuid>" }`. Simple metrics use `{ "expressionType": "SIMPLE", "column": {...}, "aggregate": "SUM", "label": "..." }`.
- **A metric control holds a metric, never a column name.** That is every
  control that picks one: `metric`, `metrics`, `metric_2`, `percent_metrics`,
  `timeseries_limit_metric`, `x`/`y`/`size` where they are metrics, and any
  custom control built from `sharedControls.metric(s)` or typed
  `MetricsControl`. Your binding's `measures` are **columns**, not saved
  metrics, and the only saved metric you can rely on is `count`. So
  `"metric": "spend"` is a query Superset rejects with a 400; write
  `{ "expressionType": "SIMPLE", "column": { "column_name": "spend" }, "aggregate": "SUM", "label": "Spend" }`,
  with the aggregate the region actually reads. A `params_hint` that shows a
  column name there is shorthand for the same object. Every adhoc metric needs
  `expressionType` and `label`, plus `column` and `aggregate` (SIMPLE) or
  `sqlExpression` (SQL).
- **Never leave a required metric control empty.** A control marked
  `validateNonEmpty` — the shared `metric` and `metrics` controls are, unless
  the panel overrides `validators` — must not be `""`, `null` or `[]`: the query
  fails or the plugin throws, and a chart that throws covers the whole
  dashboard. Fill it from your binding. If your binding has no measure for it,
  the plugin was written for a region that reads more than yours: record that
  in `unmapped` with `confidence: "low"` rather than inventing a metric. An
  optional metric control you have nothing for is `null`, not `""`.
- **Obey the design-system contract** for palette, number format, date format, time grain, legend, and `slice_name` convention — unless this region's `observed` explicitly contradicts it, in which case follow the region and note it in `unmapped`.
- **Custom plugins carry no brand colour of their own.** A generated plugin's colour control falls back to a theme token, because literal colours are not allowed in plugin source. If the design system names an exact colour and the schema exposes a colour control, set it here — this is the only place the design's hex reaches the chart.
- **Abbreviated numbers: check the magnitude first.** If the design shows
  `8.92M` and the stored value is in base units, use D3 SI (`,.3s`) or
  `SMART_NUMBER` — they scale and append the letter. If the stored value is
  **already scaled** (a `global_sales` column already in millions, summing to
  `8920.13`, drawn as `8,920.4M`), SI notation gives `8.92k` and is wrong by
  three orders of magnitude: keep a plain format such as `",.1f"` and put the
  unit in the subheader or label. `currency_format` is for currency symbols,
  not magnitude letters.
- **`region.axis_formats` is the design's own answer, not a shape to guess.**
  When your region draws an axis or a series, stage A already read its exact
  kind, pattern, and any prefix/suffix off the picture — one entry per
  axis/series:
  ```json
  { "axis": "x", "kind": "date", "pattern": "MMM YYYY", "prefix": null, "suffix": null }
  ```
  Build the matching format control from it instead of leaving the panel's
  default in place: that entry becomes
  `"x_axis_time_format": "%b %Y"` (D3 time-format syntax for `MMM YYYY`).
  A `kind: "number"` entry's `pattern` is already a D3 format string, so
  `{ "axis": "y", "kind": "number", "pattern": ",.0f", "prefix": "$", "suffix": null }`
  becomes `"number_format": ",.0f"` (or `y_axis_format`, whichever your
  schema exposes), with the `$` carried by `currency_format` or the control
  your schema uses for a currency symbol. Map every entry to whichever of
  `number_format`, `y_axis_format`, `x_axis_format`, `x_axis_time_format`,
  `date_format`, `time_format`, or `currency_format` your control panel
  actually defines. **This is checked**: a chart whose region lists
  axis/series formats but whose `params` sets none of them is rejected, the
  same way a required metric left empty is.
- **Every filter in your binding must appear in `adhoc_filters`.** This is
  the one mistake that renders cleanly and is wrong. Stage B builds the
  fewest datasets it can, so one view commonly serves several regions and
  each binding carries the clause that scopes it to its own slice:

  ```json
  "filters": [{ "col": "provider_name", "op": "==", "val": "AWS" }]
  ```

  becomes

  ```json
  "adhoc_filters": [{ "expressionType": "SIMPLE", "subject": "provider_name",
                      "operator": "==", "comparator": "AWS", "clause": "WHERE" }]
  ```

  Drop it and the AWS card draws AWS, GCP and Azure together — no error, no
  warning, just the wrong number. Add your own filters on top where the
  design calls for them; never remove one the binding gave you.
- **Always set `row_limit`.** What the region draws wins: a card showing five
  bars asks for five rows, not ten thousand. Use the design system's
  `row_limit` only where the design shows no definite count. Stage B may
  already have cut the view with `LIMIT`, so your limit is a ceiling, not the
  thing doing the work. `adhoc_filters` is a real array (`[]` when the
  binding has none and the design asks for none).
- **Set the time range explicitly, and carry a `TEMPORAL_RANGE` filter whenever
  the page has a date control.** A dashboard date filter does not filter on its
  own: it *overwrites the value* of whatever `TEMPORAL_RANGE` filters a chart
  already has. A chart carrying none is silently unaffected by it, however the
  scope is set — so a chart the design means to follow the page's date range
  must declare one on its own temporal column, or the control will appear to do
  nothing to it.
  For the comparator, write **the range the design displays** rather than
  `"No filter"` when a date control is drawn and this chart should obey it. The
  chart then arrives correctly windowed on its first request, instead of
  loading unfiltered and refetching the moment the control mounts. Use
  `"No filter"` where the design draws no date control, or where this chart is
  meant to show its full history regardless.
- **A region that draws a series needs a span, and the span is mandatory.**
  Where the design draws a sparkline, a trend line or a run of bars — whether
  beside a single value or on its own — count the periods it draws and set the
  plugin's span control to that count. Four bars labelled Jan to Apr is a span
  of four months. The plugin queries that span separately from its headline, so
  the number follows the page's date range while the series keeps enough
  periods to be a series.
  **Never set a span below two, whatever the design appears to draw.** One
  point is not a line and gives no period-over-period delta. The floor is two
  of whatever `time_grain_sqla` says: two months at `P1M`, two days at `P1D`,
  two weeks at `P1W`. Where the design's own count is lower, or you cannot
  count it, use the largest span the data supports rather than the smallest.
- Use only columns and metrics named in your binding. Nothing else exists.

## Charts that hold other charts

If **your decision** carries a `children` array, this chart renders other
saved charts inside its own frame. Reference each by the `ref`s in your
decision's `children`, emitted as `"__REF__:c2"` placeholders — the
orchestrator substitutes real chart ids once the children are created. Never
guess a numeric chart id.

Read that array from your **decision**, not from your region. The region's
`children` is a different thing: stage A's numbering of the sections drawn
inside this one. Only the decision's `children` are chart refs.

## Self-check before returning

- [ ] every `params` key exists in the control schema
- [ ] every column/metric appears in the binding
- [ ] every metric control holds `count` or a complete adhoc metric object — no
      column names, and nothing empty where the panel requires a value
- [ ] `params` is a string, `params_decoded` is an object, and they match
- [ ] every binding filter appears in `adhoc_filters`
- [ ] `row_limit`, `adhoc_filters`, and time range are set
- [ ] every `region.axis_formats` entry is reflected in a format control, and
      no SI/`SMART_NUMBER` format is used where the axis's own suffix says
      the value is already scaled
- [ ] child references come from the **decision's** `children`, as `__REF__:`
      placeholders, never numeric ids
- [ ] `slice_name` follows the naming convention
- [ ] if you were handed a `same_as` group reference, every shared field
      (aggregate, `row_limit`, colour/format/typography) matches it exactly,
      and only your own scoping fields (filters, `datasource_id`, your own
      label text) differ

Report a failed check in `unmapped` with `confidence: "low"` rather than papering over it.
