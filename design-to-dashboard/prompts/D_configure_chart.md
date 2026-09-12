# Stage D — Configure chart

**Input:** exactly one region (Stage A), its binding (Stage B), its decision (Stage C), the design-system contract, and the **full control-panel schema for that one `viz_type`**.
**Not in context:** other regions, other viz types, the design image, the full registry.
**Output:** one `ChartSpec`.

Runs once per chart, in parallel. You configure a single chart completely and correctly. You do not second-guess Stage C's `viz_type` choice.

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
- **Set the time range explicitly.** Default to `"No filter"` rather than leaving it unset.
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
- [ ] `params` is a string, `params_decoded` is an object, and they match
- [ ] every binding filter appears in `adhoc_filters`
- [ ] `row_limit`, `adhoc_filters`, and time range are set
- [ ] child references come from the **decision's** `children`, as `__REF__:`
      placeholders, never numeric ids
- [ ] `slice_name` follows the naming convention

Report a failed check in `unmapped` with `confidence: "low"` rather than papering over it.
