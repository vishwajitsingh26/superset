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
   using the section's title. Confirm every plausible candidate with
   `get_chart_info` — a section you never searched is a section you decided
   about blind. Do not page through the instance's whole chart list; an
   instance can hold thousands, and the way to find a match is a targeted
   search by name, not enumeration.
3. **If no plugin renders the section, build one.** `new_plugin` is a normal
   outcome, not a failure. A plugin is a UI component and we control that
   codebase, so anything the design shows can be built.
4. **Name the plugin you intend to create**, in `viz_type`, as
   `custom_<something>`. It must not already be in the registry — that is what
   `reuse` and `configure` are for.

   **Regions that need the same component share one name.** Three KPI tiles
   differing only in which measure they show are three decisions, one
   `viz_type`, and one plugin: give all three `custom_kpi_card` and let each
   one's configuration differ. Building a plugin per tile costs ten minutes and
   a package each, and leaves near-identical code to maintain. Ask yourself
   what would differ in the *component* — if the answer is only the data, it is
   one plugin.

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

You have **24 tool calls**, and matching plugins by thumbnail costs none of
them — that is done by looking. Spend them all on the reuse check if the design
needs it.

These are build-time reads of chart metadata. They run once, while the
dashboard is being assembled, and nothing the user opens later is slower for
them. Reuse is the cheapest outcome the pipeline has — no new chart, no new
plugin, no rebuild — so a call spent confirming a candidate pays for itself the
moment it lands. Deciding a section blind because you were saving calls is the
expensive mistake, not the search.

What is still waste: enumerating an instance's whole chart list. Search by the
names the design gives you, and check what comes back.

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

## What a custom plugin can be

A plugin is a React component we own, so `new_plugin` is not limited to "a
chart shape Superset lacks". These are the archetypes actually in production in
this codebase; pick the one that matches the design, and name it in the plan.

- **`viz`** — a single visualisation: bars, lines, a KPI card, a treemap, a
  table. The common case.
- **`composite`** — one plugin that **hosts other saved charts** inside its own
  frame. It fetches each child chart by id and renders it through Superset's
  own chart renderer, so children keep their queries, cross-filtering and
  drill. This is how a card with a tab switcher, a segmented control, or
  several charts under one shared header is built. Anything you can put around
  a chart — tabs, a title bar, a download menu, a per-card filter row, an
  expand button — belongs to the wrapper, not to the children.
- **`filter_widget`** — a plugin that *is* a filter: it declares
  `Behavior.NativeFilter` and pushes `extraFormData` into the dashboard, so it
  drives every other chart while sitting in the grid like a card. Use this for
  a period picker, a dropdown or a segmented toggle the design draws **inside**
  the layout rather than in the filter bar.
- **`table`** — a table whose cells are not text: ratio bars, sparklines,
  trend arrows, chips, expandable hierarchy rows, resizable or reorderable
  columns. Stock tables render strings and numbers; anything drawn inside a
  cell means this archetype.
- **`navigation`** — breadcrumbs, drill headers, or any element whose job is to
  move the dashboard between states rather than to plot data.

A plugin may also carry its **own control-panel UI** (a React component as a
control `type`), issue **several queries** in one chart (a value and its
comparison period), and declare `DrillBy` / `DrillToDetail` / `InteractiveChart`
so it participates in cross-filtering. Say so in the plan when the design
implies it.

### Multi-chart regions

When one card holds several charts (`composition: composite` from stage A):

1. Look in the registry for an existing composing plugin — a tabbed wrapper or
   a container. If one fits, `wrap` and emit each child as its own decision.
2. **If none exists, build one.** Use `new_plugin` with
   `plugin_archetype: "composite"` and still emit the children as their own
   decisions. Composition is a normal thing to build, not a last resort.

Falling back to sibling charts is a real answer only when the card is a loose
grouping with no shared chrome — no tabs, no shared header, no shared filter.
Say so in `fidelity_loss` when you do it.

## Filter routing

**Check `user_answers` first — it overrides everything below.** If the user
said the dashboard is embedded with the chrome hidden, Superset's filter bar is
not rendered, so a `native_filter` is *invisible*: the viewer sees a dashboard
with no filter at all. In that case every filter is a `chart_widget`, whatever
the design's layout suggests. The same goes for the page heading: with the
dashboard title hidden, a `drop` deletes it from the page rather than deferring
it to chrome, so it becomes a grid element instead.

Only when the chrome is known to be visible does the design's own layout decide:

- `role: filter` **and** `global.filter_bar.present` → `target: "native_filter"`; emit a `filterType` (`filter_select`, `filter_range`, `filter_time`, `filter_timegrain`, `filter_timecolumn`). **Not a chart.**
- `role: filter` drawn inside the grid as a card → `target: "chart_widget"`. Reuse an existing filter plugin if the registry has one that matches; otherwise `new_plugin` with `plugin_archetype: "filter_widget"`. Do not demote an in-grid control to a filter-bar filter because no plugin exists — that moves it out of the design.

Backwards here produces a dashboard whose filters don't cross-filter. Check `global.filter_bar` before deciding.

## Dropping is deleting

`drop` means the section will not exist on the dashboard. Use it for decoration
only. Deferring a heading to "the dashboard title" is a `drop` plus an
assumption that the title is rendered — and when the user has said the chrome is
hidden, that assumption is wrong and the heading is simply gone.

Use **`grid_text`** for a heading or caption that must occupy a grid cell
without being a chart: it becomes a `MARKDOWN` or `HEADER` node, and its `text`
field carries what to render. Do not reach for `configure` without a
`viz_type` — a chart with no type is not something any later stage can build.

## The user's answers are settled

If the binding carries `user_answers`, the user has already been asked those
questions and has answered them. **Their answers are decisions, not opinions.**
A plan step that contradicts one is a bug, and the user has no way to tell you
so — the questions were their only turn, and everything after this runs without
stopping.

- Asked whether a table should be custom and told "custom" → `new_plugin`, not
  `configure` with a stock table.
- Told the dashboard is **embedded with chrome hidden** → the filter bar and
  the dashboard title may not render at all. A filter must then be a
  `chart_widget` in the grid, and a title must be a grid element. Routing
  either to Superset's chrome hides it.
- Told a cut is "all rows, sorted descending" → do not carry the design's
  visible row count into `row_limit`.

Where two answers conflict, follow the more specific one, and say in
`rationale` which you followed and why. Where an answer conflicts with what you
see in the design, follow the answer — they are looking at the same picture and
know what they want.

## Stage A's read is evidence, not instruction

Every region arrives with `composition` and a provisional `stock_feasibility`
lean. Stage A saw the image but has no registry, so treat its lean as a hint
and the `why` as observation to be checked:

- A leans `custom`, and a thumbnail shows a plugin that really does draw it →
  reuse or configure it, and say in `thumbnail_evidence` which thumbnail
  overturned the lean.
- A leans `stock`, but no thumbnail matches the described treatment → build.
  A's lean was a guess made without the registry; yours is made with it.

You own the verdict. Record disagreement rather than silently following.

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
    "decision": "reuse|configure|wrap|new_plugin|native_filter|grid_text|drop",
    "text": "markdown to render, for grid_text only",
    "viz_type": "...|null", "existing_chart_id": null, "children": ["c2","c3"],
    "plugin_archetype": "viz|composite|filter_widget|table|navigation|null",
    "behaviors": ["InteractiveChart", "DrillToDetail"],
    "slice_name": "...", "rationale": "one sentence",
    "reuse_evidence": "what get_chart_info confirmed, or null",
    "thumbnail_evidence": "which plugin thumbnails you compared and what you saw",
    "stock_feasibility_check": "whether you agree with stage A's lean, and what decided it",
    "fidelity_loss": "what will differ, or null",
    "confidence": "high|medium|low"
  }],
  "native_filters": [{ "name": "...", "filterType": "...", "region_id": "...", "scope": "all|[refs]" }],
  "counts": { "reuse": 0, "configure": 0, "wrap": 0, "new_plugin": 0, "native_filter": 0, "grid_text": 0, "drop": 0 },
  "plan_for_review": [
    { "step": 1,
      "kind": "reuse|configure|wrap|new_plugin|native_filter",
      "archetype": "viz|composite|filter_widget|table|navigation|null",
      "what": "Build a custom plugin for the 'Sales by genre' card",
      "why": "Its thumbnail comparison showed every bar plugin puts category labels in the axis gutter; the design puts them above each bar.",
      "exactness": "Matches the design exactly, including label placement and the M suffix.",
      "cost": "Adds a plugin package and a frontend rebuild." },
    { "step": 2,
      "kind": "new_plugin", "archetype": "composite",
      "what": "Build a wrapper for the 'Spend' card and put the three provider charts inside it",
      "why": "The card has one header and a tab switcher over three charts; no registry plugin composes children.",
      "exactness": "Matches the design exactly. The three charts keep their own queries and cross-filtering.",
      "cost": "One plugin package plus three child charts, and a frontend rebuild." }
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

**Name the archetype in plain words.** The user is deciding whether the plan
matches what they drew, and "a wrapper card holding your three provider charts
behind tabs" tells them that; "custom plugin for r04" does not. Say what will be
built, what goes inside it, and what it will drive:

- composite → what the card holds and how the pieces are switched between
- filter_widget → which sections it will filter, and that it sits in the grid
  rather than the filter bar
- table → which cells stop being plain text and what is drawn in them

**Every section appears in the plan.** A section you dropped, demoted or read
as decoration is exactly the one the user needs to see, so give it a step
saying so. Silence reads as agreement, and the user is approving this list as
the whole of what will be built.

**Say what the dashboard will cost to load.** In `cost`, state how many queries
the step adds — meaning queries the *finished* chart will run, every time
anyone opens the dashboard. Your own tool calls and the discovery stage's are
not part of this; they happen once, while building, and nobody waits on them. A composite hosting four charts issues four queries; a card showing a
total and its breakdown should issue one. Where a section could be built with
fewer queries at some cost to fidelity, say so — that is the user's trade to
make, not yours.
