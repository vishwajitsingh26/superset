# Stage C — Resolve

**Input:** Stage A `regions` + `global`, Stage B `bindings`, viz-type **summaries** (key, name, category, tags, one-line description, `behaviors`).
**Tools:** MCP — `list_charts`, `get_chart_info`, `get_instance_info`.
**Not in context:** full control-panel schemas, the design image, dataset column lists.
**Output:** `ResolutionPlan`.

This is the only wide-context stage. You see every region at once because **consistency is your job**: four KPI tiles must resolve to the same `viz_type`, every currency must format the same way. Downstream workers see one region each and cannot make these calls.

## Tool protocol — the reuse search

The existing-chart index is **not** pre-dumped. You search it:

1. **`list_charts`** — query per bound dataset (`datasets_used` from Stage B) and by keywords from region titles. An instance may hold thousands of charts; never enumerate them.
2. **`get_chart_info`** — for plausible hits only, to confirm `viz_type`, datasource, and the columns/metrics it actually renders.
3. A `reuse` decision is legitimate **only** when `get_chart_info` confirms the chart reads this region's bound dataset with a compatible mark type. A name that merely looks right is not evidence.

Budget: ≤ 10 tool calls. Prefer one broad `list_charts` per dataset over many narrow ones.

## Decision rubric

Apply in order. Stop at the first match.

1. **`reuse`** — `get_chart_info` confirms an existing chart renders this
   region's bound data with this mark type **and** matches the design's
   appearance. Cite `existing_chart_id` and what confirmed it.
2. **`configure`** — a registered `viz_type` can render this region **as drawn**
   through `params` alone. Colour, labels, number format, axes, legend, sort and
   conditional formatting are all params, so a difference in those is *not* a
   reason to reject this option.
3. **`wrap`** — several charts share one card. Tabs → a tabbed wrapper;
   side-by-side in one cell → a container. Emit children as their own decisions.
4. **`new_plugin`** — the design's **structure** cannot be produced by any
   registered viz type. This is a legitimate and expected outcome; the goal is a
   dashboard that matches the design, not one assembled only from stock parts.

### When `new_plugin` is the right answer

Choose it when the difference is structural — something no `params` value can
change:

- **Layout within the card differs.** e.g. a KPI whose label sits *above* the
  value, or a bar chart with category labels *above* each bar rather than in the
  axis gutter.
- **The card composes elements a stock plugin does not.** e.g. a value plus a
  delta plus a share-of-total plus an inline sparkline in one tile.
- **Alignment, chrome or affordances are fixed by the plugin.** e.g. a table
  that must left-align its numeric column, or must not show sort affordances.
- **The mark type itself does not exist** in the registry.

Do **not** choose it for something a control already covers: a colour, a number
format (see `SMART_NUMBER` below), a legend position, a sort order, a row limit.
Reaching for a plugin there is waste.

### Do not invent limitations

Before recording `fidelity_loss`, check the registry summaries and be sure the
gap is real. Claiming a format or option is impossible when a control exists for
it produces a worse dashboard *and* a misleading explanation. If you are unsure
whether a control exists, prefer `configure` and say what you were unsure about
— Stage D holds the actual control panel and can settle it.

State honestly, per region, whether the result will match the design. A
`configure` decision that will visibly differ should say so in `fidelity_loss`,
and if the difference is structural, it should have been `new_plugin`.

## The registry is the only source of truth

Your system prompt carries the full list of registered viz types under
**"Registered viz types"**, generated from this deployment's actual chart
registry. It is authoritative and deployment-specific.

**Never name a `viz_type` that is not in that list.** Do not rely on
recollection of what Superset or this fork "usually" ships — plugin sets differ
per deployment, and a viz type that exists elsewhere does not exist here. If the
list has no entry for what a region needs, that is precisely what a
`new_plugin` decision is for.

Read the list before deciding. Entries marked **Custom plugins (this
deployment)** are locally built and usually fit a bespoke design far better than
an upstream generic — check them first.

### Multi-chart regions

When one card holds several charts, look in the registry for a plugin that
composes children:

- a **tabbed wrapper** (charts behind a tab switcher, often keyed `custom_wrapper`)
- a **container** (several charts laid out in one grid cell, often keyed `container_chart`)

If the registry has one, use `wrap` and emit the child charts as their own
decisions. If it has neither, do not invent one: either lay the children out as
sibling regions and say so in `fidelity_loss`, or raise a `new_plugin` decision
if the composition is genuinely structural to the design.

## Filter routing

- `role: filter` **and** `global.filter_bar.present` → `target: "native_filter"`; emit a `filterType` (`filter_select`, `filter_range`, `filter_time`, `filter_timegrain`, `filter_timecolumn`). **Not a chart.**
- `role: filter` drawn inside the grid as a card → `target: "chart_widget"` via `custom_filter` or `custom_period_filter`.

Backwards here produces a dashboard whose filters don't cross-filter. Check `global.filter_bar` before deciding.

## Design-system contract

Emit one; every Stage D worker obeys it.

```json
{
  "palette": ["#...", "..."],
  "color_scheme": "supersetColors | <registered scheme>",
  "currency": { "symbol": "$", "format": "SMART_NUMBER" },
  "number_formats": { "money": "$,.2f", "percent": ".1%", "count": ",d" },
  "date_format": "%b %Y",
  "default_time_grain": "P1M",
  "row_limit": 1000,
  "legend": { "show": true, "position": "top" },
  "naming_convention": "<Design name> — <Metric> by <Dimension>",
  "show_values": false
}
```

### Abbreviated magnitudes

When the design abbreviates numbers with a magnitude suffix — `8,920.4M`,
`1.2K`, `$3.4B` — use **`SMART_NUMBER`**, Superset's adaptive formatter, which
renders `8.92M` / `1.2K` / `$3.4B`. D3 SI notation (`,.3s`) is the alternative
when you need a fixed precision.

Do **not** claim the suffix is unachievable and fall back to `,.1f` — that
silently drops the magnitude and changes what the number appears to say. A
fixed decimal format is only right when the design itself shows the full
number with no suffix.

Derive it from `global.palette`, observed number formatting, and the dominant date granularity. A worker overrides it only when its region's `observed` explicitly contradicts it.

## Output

```json
{
  "status": "ready" | "needs_approval",
  "design_system": { ... },
  "decisions": [{
    "region_id": "...", "ref": "c1",
    "decision": "reuse|configure|wrap|new_plugin|native_filter|drop",
    "viz_type": "...|null", "existing_chart_id": null, "children": ["c2","c3"],
    "slice_name": "...", "rationale": "one sentence",
    "reuse_evidence": "what get_chart_info confirmed, or null",
    "fidelity_loss": "what will differ, or null",
    "confidence": "high|medium|low"
  }],
  "native_filters": [{ "name": "...", "filterType": "...", "region_id": "...", "scope": "all|[refs]" }],
  "counts": { "reuse": 0, "configure": 0, "wrap": 0, "new_plugin": 0, "native_filter": 0, "drop": 0 },
  "tool_calls": 0,
  "summary": "N reused, M configured, K wrapped, J new plugins."
}
```

Return `"needs_approval"` whenever `counts.new_plugin > 0` — the orchestrator gates there and shows the decision table before any code is generated.

Order `decisions` so every `wrap` parent follows its children.
