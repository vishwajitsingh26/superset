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
      "datasource_id": 0,
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
- **Always set `row_limit`**, and set it to what the design shows. A card
  drawing five bars asks for five rows, not ten thousand. `adhoc_filters` is a
  real array (`[]` if none) — filtering in the database beats shipping rows the
  chart will discard.
- **Set the time range explicitly.** Default to `"No filter"` rather than leaving it unset.
- Use only columns and metrics named in your binding. Nothing else exists.

## Wrapper children

If your decision is a `wrap` parent (`custom_wrapper` / `container_chart`), your `params` references child charts by the `ref`s in `decisions[].children`. Emit them as `"__REF__:c2"` placeholders — the orchestrator substitutes real chart ids after the children are created. Never guess a numeric chart id.

## Self-check before returning

- [ ] every `params` key exists in the control schema
- [ ] every column/metric appears in the binding
- [ ] `params` is a string, `params_decoded` is an object, and they match
- [ ] `row_limit`, `adhoc_filters`, and time range are set
- [ ] child references use `__REF__:` placeholders, never numeric ids
- [ ] `slice_name` follows the naming convention

Report a failed check in `unmapped` with `confidence: "low"` rather than papering over it.
