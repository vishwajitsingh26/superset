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
- **Magnitude suffixes need `SMART_NUMBER`.** If the region's `observed` text
  shows an abbreviated number (`8,920.4M`, `1.2K`, `$3.4B`), set the number
  format to `SMART_NUMBER` — not `,.1f`, which drops the suffix and makes the
  value read as a different quantity. Use a fixed decimal format only when the
  design shows the unabbreviated number.
- **Always set `row_limit`** and a sane `adhoc_filters` array (`[]` if none).
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
