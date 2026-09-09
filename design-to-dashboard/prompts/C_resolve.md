# Stage C — Resolve

**Input:** Stage A `regions` + `global`, Stage B `bindings`, viz-type **summaries** (key, name, category, tags, one-line description, `behaviors`).
**Tools:** MCP — `list_charts`, `get_chart_info`, `get_instance_info`.
**Not in context:** full control-panel schemas, the design image, dataset column lists.
**Output:** `ResolutionPlan`.

This is the only wide-context stage. You see every region at once because **consistency is your job**: four KPI tiles must resolve to the same `viz_type`, every currency must format the same way. Downstream workers see one region each and cannot make these calls.

## How to decide: look at the plugins first

A plugin **is** a UI component. Your system prompt includes a **contact sheet
image** showing every registered plugin's thumbnail, labelled with its
`viz_type`, name and category, with locally built ones badged `custom`.

That picture is your primary evidence. For each section of the design, compare
what is drawn against those thumbnails and ask: *does a plugin already render
this?* Text descriptions are a secondary check — a thumbnail shows the actual
mark, layout and label placement, which is exactly what a design specifies.

Work section by section, in this order:

1. **Match against the plugin registry (no tools needed).** Find the plugin
   whose thumbnail renders this section's structure. `custom` plugins were built
   for this deployment's own designs and usually fit a bespoke section better
   than a generic upstream one — check them first.
2. **Only then consider reusing an existing chart.** A chart is worth reusing
   when one already renders this section's bound data with that plugin. Search
   narrowly: one `list_charts` filtered to the bound dataset, or a name search
   using the section's title. Confirm **at most two** candidates with
   `get_chart_info`. Do not inspect every chart the instance holds — an
   instance can have thousands, and a near-match is worth less than the time
   spent finding it.
3. **If no plugin renders the section, build one.** `new_plugin` is a normal
   outcome, not a failure. A plugin is a UI component and we control that
   codebase, so anything the design shows can be built.

### Looking is not optional, and similar is not the same

For **every** section, state in `thumbnail_evidence` which plugin thumbnails you
compared it against and what you saw. A decision with no such evidence is not
acceptable — it means the picture was ignored and the choice was a guess.

A thumbnail that looks *broadly similar* is **not** a match. Compare the things
a design actually specifies:

- where labels sit relative to the mark (above a bar, beside it, in an axis gutter)
- what is composed inside one card (a value alone, or value + delta + sparkline)
- alignment and chrome the plugin fixes and `params` cannot change

If the thumbnail differs from the design on any of those, the plugin does not
render this section — say so and choose `new_plugin`. A near-match recorded as
`fidelity_loss` is a decision to ship something the user did not ask for; only
make it when the user has agreed to it in the clarification step.

### Calling the reuse tools

`list_charts` and `get_chart_info` are called by emitting the JSON envelope
described in your system prompt, not by using a native tool. You will not find
them among your own tools, and that is normal. If you skip the reuse check,
say so as a decision you made — never report the tools as unavailable.

### Budget

You have **6 tool calls**. Plugin matching costs none of them — it is done by
looking. Spend them only on the reuse check, and stop early: returning a good
plan quickly is worth more than an exhaustive search.

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

### Magnitude suffixes and unit labels — two different problems

First establish **what the stored value actually is**, then pick the mechanism.
Stage B's bindings and any `execute_sql` probe tell you the real magnitude.

**A. The value is in base units and the design abbreviates it.**
This is a number-format job. Use D3 SI notation (`,.3s`) or `SMART_NUMBER`,
which scale and append the magnitude letter automatically:
`8920400` → `8.92M`, `1240` → `1.24k`. This is the common case.

**B. The value is already scaled and the design shows a unit letter.**
`SUM(global_sales)` = `8920.13` where the column is already millions of units,
and the design draws `8,920.4M`. Here `,.3s` gives `8.92k` — wrong by three
orders of magnitude. A number format cannot append a literal unit, so:

- put the unit in the chart's **subheader or label** (`Millions of units`), or
- keep a plain format (`,.1f`) and note that the unit lives in the label.

`currency_format` exists for currency symbols (`$`, `€`) and is not the right
control for a magnitude letter.

Say which case applies in `fidelity_loss` only when the result genuinely differs
from the design. Do **not** write that a suffix is impossible without first
establishing which case you are in — case A is always achievable.

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
    "thumbnail_evidence": "which plugin thumbnails you compared and what you saw",
    "fidelity_loss": "what will differ, or null",
    "confidence": "high|medium|low"
  }],
  "native_filters": [{ "name": "...", "filterType": "...", "region_id": "...", "scope": "all|[refs]" }],
  "counts": { "reuse": 0, "configure": 0, "wrap": 0, "new_plugin": 0, "native_filter": 0, "drop": 0 },
  "plan_for_review": [
    { "step": 1,
      "what": "Build a custom plugin for the 'Sales by genre' card",
      "why": "Its thumbnail comparison showed every bar plugin puts category labels in the axis gutter; the design puts them above each bar.",
      "exactness": "Matches the design exactly, including label placement and the M suffix.",
      "cost": "Adds a plugin package and a frontend rebuild." }
  ],
  "tool_calls": 0,
  "summary": "N reused, M configured, K wrapped, J new plugins."
}
```

Return `"needs_approval"` whenever `counts.new_plugin > 0` — the orchestrator gates there and shows the decision table before any code is generated.

Order `decisions` so every `wrap` parent follows its children.

## The plan a human will read

`plan_for_review` is shown to the user for approval **before anything is
created**, so write it for them, not for the pipeline. One step per meaningful
piece of work, each saying **what** you will do, **why** (citing the thumbnail
comparison or the binding), how **exact** the result will be, and what it
**costs** (a plugin means a rebuild; a reused chart means accepting its existing
formatting).

Where a step will not match the design exactly, say so plainly in `exactness`.
The user is approving a specific outcome, and a step that oversells itself makes
the approval meaningless.
