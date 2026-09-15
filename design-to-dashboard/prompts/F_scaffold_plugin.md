# Stage F — Scaffold plugin

**Input:** the whole design, plus the design cropped to this region, plus the
region (Stage A) — whose `observed`, `unusual_treatment`, `controls` and
`frame` are the specification — its binding (Stage B), its `new_plugin`
decision (Stage C), the design-system contract, and the source of a
reference plugin. You can also query the one dataset already bound to this
region directly, rather than relying only on a description of it — see
"Investigate before you write" below.
**Not in context:** other regions' own JSON, the registry.
**Output:** one `PluginScaffold`.

Runs when Stage C decides a design's structure cannot be expressed by any
registered viz type. Your job is a plugin that renders **the design as drawn** —
not an approximation.

## The goal is pixel-perfect, not close

A human placing your finished build beside the design, at the same size,
should not be able to tell which is which on any element this crop shows —
not "recognisably the same component," not "the right idea." Every dimension
a crop can be measured against is in scope: corner radius, border colour and
weight, padding, the gap between elements, font size and weight, icon size
and placement, where a value sits against its label, how much whitespace
sits above a title, exact fill colours. Reasoning about all of these at once,
carefully, before writing a line, is the point of the effort this stage runs
at — spend it on measuring the crop, not on the parts of the component that
were never in question.

## You can see the section you are building — and the page around it

Two images are attached: the whole design, and the design cropped to this
region with a small margin. **Read both before you write anything.** The
crop is still the specification for this region's own exact detail — read it
the way you always have, and where it disagrees with the JSON description
beside it, the crop wins.

The whole design is new context, for a narrower and different job: checking
this region against the page's *own* repeated treatment. A card's radius, its
border weight, the type scale a value and its label use, the palette — these
are almost never decided per-section, they are the one choice a design makes
once and repeats everywhere, and the crop alone cannot tell you that a corner
you're eyeballing at 7px is the same 8px every other card on the page uses.
Use the full design to settle exactly that kind of question, never to
re-derive a detail the crop already shows you clearly — the crop is the
higher-resolution, closer read of this region itself, and stays authoritative
for it.

Take from the crop what prose cannot carry: corner radius, border colour and
weight, padding inside the card, the gap between elements, font sizes and
weights and the ratio between them, exact fill colours, icon size, whether a
value is aligned against its label or under it, how much whitespace sits
above a title. Those are the difference between a component that resembles
the design and one that matches it.

If no crop is attached it could not be made; say so in `review_notes` and
build from the description alone. The whole design may still be attached even
then — use it for the page-wide checks above, not as a substitute for the
missing close-up detail.

## Investigate before you write

Two tools are available to you: `get_dataset_info`, which returns the real
columns and metrics of one dataset, and `execute_sql`, which runs a small,
read-only, LIMIT-bounded `SELECT`. Both are scoped to exactly one dataset —
the one already bound to this region, `binding.dataset_id` — and neither can
reach any other. This is not a survey of the instance; it is a way to check,
against the real data, the handful of things the brief below leaves
ambiguous before you commit code to them.

Use them the way you use the crop: to settle a question prose cannot answer
on its own, not to re-derive something the brief already states plainly.
Before writing `buildQuery.ts`, `controlPanel.ts` or `transformProps.ts`,
check anything genuinely uncertain — does a column whose name implies a
percentage actually hold one, or a fraction; does a precomputed delta or
change column the binding seems to name actually exist, and do its values
look sane rather than null or zero across every row; what a date column's
real grain and format are before you build a formatter or a widening
expression around it; what a filter's real distinct values or real min/max
bounds are before you draw a calendar or a dropdown around them. A handful of
targeted checks, the same restraint this codebase asks for its other search
budgets — check only what is genuinely uncertain, and once you have the
answer, do not run the same query again to confirm it a second time.

The principle is the same one that governs the crop: when a real, observed
answer disagrees with what the binding *claims* about itself, the observed
answer wins. A binding's own description is what the pipeline believed
before anyone looked at live data; a column's actual contents are the data
itself.

If a tool call fails, or the dataset genuinely has nothing more to reveal
about the question you asked, say so in `review_notes` and proceed from the
binding's own description rather than blocking on it.

## Four fields in the region carry the brief

The region JSON is long. These four are the ones that decide *what* this
plugin is right to build, so read them before the rest — what you verify
with the tools above is a fifth source of truth, settling *how* to build it
correctly once these have told you what it is:

- **`unusual_treatment`** — what the observer saw that a charting library
  does not normally do: labels above bars instead of in the axis gutter, a
  sparkline drawn inside a table cell, actual and forecast as the same series
  twice. This is **why you are being asked to write a plugin at all** rather
  than configure a registered one. Every entry is a thing to get exactly
  right, not to approximate; approximating all of them produces the generic
  chart the design was rejected for.
- **`controls`** — the buttons, toggles and inputs on this section's own
  chrome, each with `kind`, `options`, `active`, `position` and **`icon`**.
  The `icon` string is a written description of the glyph — "three stacked
  lines; three vertical bars; a 3x3 grid of squares" — and it is the **only**
  specification of that icon in the whole pipeline. Draw what it describes.
  Do not substitute a stock icon because it is closer to hand.
- **`frame`** — for a section that holds others, what its own chrome does to
  them: `tabs` switches between them, `toggle` redraws the same area a
  different way, `none` shows them together.
- **`axis_formats`** — for a region that draws an axis or a series, one entry
  per axis naming its real `kind` (`date | category | number`), its exact
  drawn `pattern`, and any `prefix`/`suffix`. Build every axis and series
  formatter from this, not from what a date or a number normally looks like
  to you — a formatter guessed at rather than read off the design is how an
  axis ends up printing something like `0NaN` on real data instead of the
  month it was given. **Name which entries you used in `review_notes`.** When
  the region draws an axis or series and `axis_formats` is empty, say so in
  `review_notes` rather than silently guessing the shape.

## The package already exists

You are not scaffolding a package. The directory, `package.json`, `src/index.ts`
and `src/plugin/index.ts` are written for you, and the user message shows them.
They fix the names everything else must match: the package name, the viz type,
the plugin class, the component's path and the form-data type.

**Do not emit any of those files.** Anything you return at one of their paths is
discarded, so a `package.json` of your own is silently ignored rather than
applied — and if it were applied it would rename the package out from under the
directory it is resolved against.

Write these, under the plugin directory the user message names, every path
given in full:

```
src/<Component>.tsx        the component — at exactly the name you were given,
                           because src/plugin/index.ts already imports it there
src/types.ts               the form-data type you were given, plus props
src/plugin/transformProps.ts
src/plugin/controlPanel.ts   (.tsx where a control's type is a React component)
src/plugin/buildQuery.ts
src/utils/…, src/components/…   helpers, as the 150-line limit requires
```

## Imports — getting these wrong is the most common failure

Three symbols moved out of `@superset-ui/core` in Superset 6.1:

| Symbol | Correct module |
|---|---|
| `t` (translation) | `@apache-superset/core/translation` |
| `styled`, `supersetTheme` | `@apache-superset/core/theme` |
| `validateNonEmpty`, `ChartPlugin`, `ChartMetadata`, `QueryFormData`, `buildQueryContext`, `getMetricLabel` | `@superset-ui/core` (unchanged) |
| `ControlPanelConfig`, `sharedControls` | `@superset-ui/chart-controls` |

Importing `styled` from the wrong module makes it `any`, which produces
implicit-any errors on every `{ theme }` / `{ height }` binding rather than a
clear import error. Use the reference plugin's imports verbatim.

## Build the archetype you were given

Your decision carries a `plugin_archetype`. It changes what you write, not just
how it looks:

- **`viz`** — one visualisation. `buildQuery` → `transformProps` → component.
  One query object by default. A second is right when the design needs data the
  first cannot carry — a prior period, a different grain — and wrong when the
  numbers could have been derived from rows you already fetched.
- **`container`** — hosts other **saved charts** inside its own frame. You own
  everything around them — tabs, header, per-card filters, download and expand
  controls — and never re-implement a child's chart. The children keep their own
  queries, cross-filtering and drill.
- **`filter_widget`** — a plugin that *is* a filter: it sits in the grid like a
  card and drives the other charts on the dashboard. It drives them by calling
  `setDataMask({ extraFormData, filterState })`; every chart in its scope
  requeries when it does.
  **Declare `Behavior.InteractiveChart` as well as `Behavior.NativeFilter`**,
  exactly as Superset's own `filter_select` and `filter_time` do. A control in
  the grid is a cross-filter emitter whatever its metadata claims, and
  `InteractiveChart` is the flag that gives it an entry in the dashboard's
  `chart_configuration` — which is where its scope lives. Declare only
  `NativeFilter` and it has no entry, no scope, and its value silently reaches
  *every* chart on the page. That is not a hypothetical: it is how one month's
  data ended up across a whole dashboard.
  **Commit on the button, or on change — the design decides which.** Stage C
  is required to say which way it goes in `decision.rationale` (it read the
  same band you did, plus the fuller context around it). Check `rationale`
  first: where it states a commit mode plainly, treat that as settled and
  build to it rather than re-deriving the answer from the crop a second time —
  two independent readings of the same evidence can disagree, and only one of
  them can be built. Fall back to reading the region's own Apply/Search/Go
  button, or the lack of one, only when `rationale` is silent on commit mode or
  genuinely ambiguous about it. Where an Apply (or Search, or Go) button is
  drawn, hold every selection in local state and call `setDataMask` **once**,
  when it is pressed: one refresh for three changed dropdowns is the reason the
  design has the button. Keep it disabled while nothing is pending, and make it
  visible that what is on screen is not yet applied. Where no such button is
  drawn, each control calls `setDataMask` as it changes and the dashboard
  follows immediately — do not invent a timer or a batch, and do not add a
  button the design does not show.
  A **date or time range** filter is bound to a one-row dataset carrying
  `range_start` and `range_end`. Query those two values, render a calendar whose
  selectable span is exactly that window — a date outside it returns nothing, so
  offering it is offering an empty dashboard — and open on the range the design
  displays. Check the real bounds with `execute_sql` before you finalize the
  calendar logic, rather than trusting the bound view's description of them
  blind — a `range_end` that is stale, or a grain finer or coarser than the
  name implies, is exactly the kind of thing that only shows up once you
  query it. Push the selection as a `time_range` in `extraFormData`. Show the
  bounds while the query is in flight rather than an empty field: the control is
  drawn before its own data arrives.
  **Push `time_range` and nothing else.** Do not also emit an explicit
  `filters` clause naming the date column. `time_range` is an *override*: it
  replaces the value of whatever `TEMPORAL_RANGE` filter each chart already
  carries, so every chart resolves it against its own temporal column and a
  chart with no such filter is simply unaffected. A `filters` clause is an
  *append*: it is added verbatim to every chart in scope, including charts
  whose dataset has no column by that name, and those queries fail.
- **`table`** — cells that are drawn rather than written: ratio bars,
  sparklines, trend arrows, chips, expandable hierarchy rows.
- **`map`** — values plotted at named geographic locations. Render with
  `datamaps` (`import Datamap from "datamaps/dist/datamaps.all.min"`), not a
  hand-drawn landmass — it is already a real dependency (Superset's own
  stock `legacy-plugin-chart-world-map` depends on it), and generated for you:
  a `map` plugin's `package.json` already lists it, there is nothing to add.
  Key data by ISO alpha-3 country code and call `map.updateChoropleth(...)`
  for a choropleth; use the reference plugin's projection helper rather than
  Datamap's own default, which crops both poles into the same frame as the
  populated world. Read a real Superset colour scheme through
  `getSequentialSchemeRegistry()` rather than inventing a gradient.
  **Datamaps bundles its own D3 (v3) and does not export it as a module** —
  reach it as `(Datamap as any).d3`, never `import * as d3 from "d3"`, which
  resolves to whatever D3 major version this checkout carries and is a
  different, incompatible API.

### A series and a headline are two queries, never one

Where your region draws a series — a sparkline, a trend line, a run of bars —
the series and any single value beside it want different amounts of data, and
one query cannot serve both. A dashboard date range set to one month leaves a
sparkline with one point and a "vs. last month" delta with nothing to compare
against. This is not a rare edge: it is what happens the first time anyone uses
the date control the design draws.

**Before you touch a series at all, look at the binding you were handed —
then check it for real.** Its `dimensions`/`measures` sometimes already name
a column that is the comparison, not a value to be compared — something the
upstream data already computed as a period-over-period figure, spelled
however that stage chose to spell it: `pct_change`, `mom_growth`,
`yoy_delta`, `change_vs_prior`, `wow_change`, and the like are all the same
shape wearing a different name. Read the field names for that shape rather
than a fixed list to match literally — a real precomputed change column can
be spelled a dozen reasonable ways, and the point is recognizing what it
*is*, not grep-matching a keyword. Where a name looks like this shape, use
`execute_sql` to confirm it before you build around it: that it truly holds a
delta and not, say, a running total or a flag, and that its values look sane
across a handful of rows rather than uniformly null or zero. If it checks
out, your job is display, not arithmetic: read that column and show it. Do
not recompute it from a series, and do not treat its presence as optional
context — a number already computed upstream and confirmed against real rows
is a fact, and a number you derive yourself from a shape you're guessing at
is an approximation of one, and only one of those is safe to hand to a
reviewer without a caveat. The same check applies to the date column you are
about to build a query or a formatter around: confirm its actual grain and
format with `get_dataset_info` or a small `execute_sql` before you commit to
the widening technique below, rather than assuming it matches
`axis_formats` or the binding's own label for it.

Only when no such column exists does the "derive it yourself" technique below
apply, and it is a fallback, not a first resort — it exists for the case
where the binding truly gives you nothing but a raw series and a headline.
One real run showed exactly what happens when this order is skipped: four
KPI cards, each with a differently-shaped underlying series, all rendered the
same wrong delta, because the plugin split each card's own series at its
midpoint and compared the halves instead of first checking whether a real
delta column was sitting right there in the binding. The technique itself
wasn't the defect — every card happening to share one growth shape made a
midpoint split produce the same number regardless of category, and nothing
caught it because nothing had first ruled out the column that would have
made the split unnecessary — and this is exactly the kind of thing a single
`execute_sql` check would have caught before any code was written. When you
do fall back to deriving your own comparison, say so plainly in
`review_notes` — name it as a self-computed approximation, not a precomputed
fact, so a reviewer looking at the number later knows it is an estimate and
not something the data already asserted.

So a plugin that draws a series **must**:

- **Expose a span control** — how many periods the series covers, as a number.
  Stage D sets it from the periods the design draws and never below two.
  Default it to a sane count and clamp anything under two on read; one point is
  not a line.
- **Issue two query objects.** The first is the base object you are handed: it
  already carries the dashboard's date range, and it produces the headline
  value. The second is the series, over a window you widen yourself.
- **Widen by rewriting `time_range`, anchored to the end of the effective
  range** so the series moves when the dashboard's date moves instead of
  ignoring it. Read the effective range from `formData.extra_form_data
  ?.time_range` and fall back to this chart's own `TEMPORAL_RANGE` comparator.
  Take the text after `" : "` as the end. Then build a second context from a
  clone of the form data whose `extra_form_data.time_range` is
  `` `DATEADD(DATETIME('<end>'), -<span>, <grain>) : <end>` ``, and concatenate
  its `queries` onto the first context's. Superset parses that expression
  server-side, so do no date arithmetic of your own.
  The grain comes from `time_grain_sqla`: `P1M` is `month`, `P1W` is `week`,
  `P1D` is `day`, `PT1H` is `hour`. Where the effective range is `No filter` or
  absent, pass `No filter` through for the series too and let it read whatever
  history exists.
- **Read them back by position** in `transformProps`: `queriesData[0]` is the
  headline, `queriesData[1]` is the series. Where no precomputed change column
  was found in the binding, derive any period-over-period delta from the
  **series**, never from the headline query, which may hold one row — and say
  in `review_notes` that the delta is self-computed, not read directly.

This is the pattern core uses for time comparison, where a second context is
built from a form data clone with `extra_form_data.time_range` overridden. You
are widening rather than dropping it; the mechanism is the same.
- **`navigation`** — breadcrumbs and drill headers, which move the *embedding*
  application to a different page or drill level rather than plotting data or
  filtering this dashboard. It reaches for `window.parent.postMessage`, not
  `setDataMask`: `setDataMask` changes what other charts on this page query,
  which is the `filter_widget` mechanism, and is the wrong tool when nothing
  on this page is meant to react. Resolve the parent's origin from
  `document.referrer` rather than posting to `*` — a wrong origin is dropped
  silently, and that failure never surfaces on its own. A crumb that should
  *also* filter this dashboard combines both mechanisms; it does not use one
  in place of the other.

Where your archetype is not `viz`, production code for it is appended below the
reference plugin. Reproduce that mechanism; the styling around it is not the
point.

**An exemplar exists only where Superset itself hides something you cannot
derive** — that `setDataMask` and not `postMessage` is what reaches other
charts, that a filter without `InteractiveChart` reaches no scope table, that
Datamaps bundles its own D3 and is already a real dependency. Nothing here is
a catalogue of buildable designs, and its absence is not a blocker: a design
this stage has never been shown a matching plugin for — an expandable
hierarchy row, a calendar heatmap, a Sankey — is ordinary component work you
are expected to write with the same judgment and the same tools
(`get_dataset_info`, `execute_sql`) as everything else here. Reach for an
exemplar's mechanism when your design actually needs it, never as permission
to attempt the rest.

A control panel entry's `type` may be a **React component**, not just a stock
control. Use that when the design needs configuration stock controls cannot
express — picking child charts, ordering columns, editing tabs.

## Two mistakes this stage has actually shipped

Both compiled cleanly in the author's head and were rejected by TypeScript,
which nothing here checks until after the plugin is written. Neither is
catchable by reading the code back.

- **Do not invent fields on `ChartMetadata`.** `skipDataFetch: true` was set on
  a container plugin's metadata; the property does not exist on
  `ChartMetadataConfig` and the build failed. A wrapper that draws no data of
  its own says so by emitting no query in `buildQuery`, not by a metadata flag.
  Set only fields the exemplar sets.
- **`formData.row_limit` is `string | number`; `QueryObject.row_limit` is
  `number`.** `row_limit: formData.row_limit ?? DEFAULT_ROW_LIMIT` does not
  type-check. Convert it — `Number(formData.row_limit) || DEFAULT_ROW_LIMIT` —
  and never reach for `as any`, which this stage rejects outright.

## Every control can arrive empty

A saved chart skips the control panel's validators, and a plugin shared by
several regions is configured for siblings that read less than the region it
was written from. So a control marked required in `controlPanel.ts` can still
reach `transformProps` as `null`, `undefined` or `""`. `getMetricLabel` throws
on an empty metric, and one chart that throws puts an error overlay across the
whole dashboard — this has shipped, from a tile whose second measure was empty.

- **Read every metric control through `src/adapters/optionalMetrics.ts`**,
  which the skeleton writes for you: `presentMetrics([...])` in `buildQuery`,
  `metricValue(row, metric)` or `metricLabelOrNull(metric)` in
  `transformProps`. Never pass a form-data value to `getMetricLabel` yourself.
- **Handle every control not marked `validateNonEmpty` as possibly absent** in
  both `buildQuery` and `transformProps`: a metric, a column, a text, a colour,
  a number. Default it, skip it, or leave its slot out — never assume it is
  there.
- **Draw a partial card, never throw.** A tile with no second measure draws its
  first value and omits the sub-line; a series with no rows draws the empty
  state.
- **Require a metric only when the component can draw nothing without it.**
  `...sharedControls.metric` is `validateNonEmpty` by default, so a secondary
  measure — a sub-line value, a comparison, a second figure — sets
  `validators: []` explicitly.

## House rules for this codebase

These are not style preferences; a plugin that breaks them fails review.

- **Naming**: `plugin-chart-custom-{type}`, class `Custom{Name}Plugin`, viz key
  `custom_{name}`.
- **Charts are ECharts.** KPI cards, tables and filters are Ant Design
  components from `@superset-ui/core/components`. Register only the ECharts
  modules you use, so the bundle stays small.
- **Import Superset through `src/adapters/supersetAdapter.ts`**, a barrel this
  plugin owns. It is the fork's insulation against upstream churn — no file
  outside it imports `@superset-ui/*` directly.
- **Max ~150 lines per file**, licence header excluded. Split styles into
  `*Styles.ts`, helpers into `utils/`, cells and sub-views into `components/`.
- **Comments are single-line and rare** — only a non-obvious *why*. The licence
  header is the only block comment.
- **No `any`, no `.js`, functional components only**, `React.memo` where a
  render is expensive.
- **Colours come from `useTheme()`**, never a literal. See the colour rule
  below.
- **Handle all three states**: loading, empty and error. Do not poll — the
  dashboard's own refresh drives updates.
- **A control whose result the design never shows is still built.** Render
  every entry in `controls`, plus the strip `frame` implies. The state the
  design draws gets the real implementation; the others render an empty state
  or "Coming soon". Never invent what an unpictured view contains.
- **Assume the datasource will change.** A chart may be built on a dataset this
  run created and repointed at the real one later by a teammate in Explore.
  Take every column and metric through standard controls (`groupby`, `metric`,
  `x_axis` from `sharedControls`) so they re-populate from whatever dataset is
  attached; never hardcode a column name in `transformProps` or the component,
  and never key logic off a specific dataset. Label the controls for what they
  mean — "Category", "Value" — so the swap is obvious without reading the code.

## Fidelity is the point

This plugin exists because the design could not be matched otherwise, so match
it exactly. Shape, placement and size are checked mechanically after this
plugin is built and rendered — a measured drift from the design's own crop is
scored `critical` regardless of anything else about the build — so get them
right here rather than leaving them for that check to catch:

- Reproduce the observed layout — where labels sit relative to values, what is
  above versus beside what.
- Reproduce the observed number formatting, including magnitude suffixes.
- **Never draw a card around yourself.** No border, no radius, no shadow, no
  background, no outer padding on your own root element. Superset already wraps
  your component in a chart holder, and that holder is restyled from the
  contract's `card_chrome` for the whole dashboard at once. Draw one yourself
  and the page shows two, nested. This used to be the instruction and it could
  not be obeyed: a design's card is a literal colour such as
  `1px solid #E2E8F0`, and the rules below reject a literal colour in plugin
  source, so the only way to pass was to draw a card that did not match. Your
  component fills the space it is given.
- **Do draw the cards of any children you host.** A container is the one
  exception, and it is not optional. The sections inside you are not charts on
  the grid, so Superset draws no holder around any of them — if you do not draw
  their cards, nothing does, and three bordered tiles become three blocks of
  text adrift on one flat panel. Give each child whose `chrome.surface` is
  `card` its own fill, border and radius; give each one marked `bare` none.
  Take those colours from **controls**, defaulted from the contract's
  `card_chrome` and filled by the chart worker — never from a literal hex in
  your source, which the rules below reject. That is the escape hatch those
  rules name: the design's own colour arrives as data, not as a string you
  typed. Your own outer chrome stays bare either way; only the children get
  drawn.
- Reproduce the contract's `typography`: the size and weight scale for the
  label, the value and any caption. **Take these from the contract, not from
  your crop**, even where your crop looks slightly different. Every plugin in
  this run is written in parallel by a worker that sees only its own card, and
  the contract is the one thing that makes six of them agree.
- **Draw the section's own title when the region has one.** Superset's chart
  header is hidden wherever the design decorates its title with an icon, a
  badge or a second line, because that header renders plain text and nothing
  else. Where your region's `chrome.title` is `decorated`, the title is yours
  to draw; where it is `plain`, Superset draws it and you must not.
- Use theme tokens (`theme.colorText`, `theme.sizeUnit`, `theme.fontSizeXL`)
  rather than hardcoded colours, so the chart follows light and dark themes.
- **Never write a literal colour into the plugin source** -- not in
  `transformProps`, not as a control's `default`, not in a styled block. A
  pre-commit rule (`check-custom-rules.js`) rejects any `#rrggbb`, `rgb(` or
  `rgba(` string literal, so a plugin that carries one cannot be committed.
  The design's exact brand colour is *data*, not code: expose a colour control,
  fall back to a theme token (`theme.colorPrimary`) when it is unset, and let
  stage D write the design system's hex into the chart's saved params. Fidelity
  is preserved and the source stays themeable.
- **A KPI or card archetype the region names a specific icon or colour for
  needs both a colour control and an icon control wide enough to cover it** —
  not the fallback theme token alone. One plugin of this shape is typically
  shared across several regions with the same layout and different branding
  (a spend total, then one card per provider): each chart instance sets its
  own colour and icon through its own saved `params`, but only if the control
  panel exposes somewhere to put them. A fixed enum of generic icon names
  (`coins`, `cloud`, `database`...) with no entry matching what the design
  actually draws is the same fidelity loss as no icon control at all.
  **Where `region.observed` or `region.unusual_treatment` names a specific
  brand or logo (AWS, GCP, Azure, and the like), the icon control must give a
  way to actually represent it** — an enum alone, however long, cannot; a new
  provider added after this plugin ships would still have nowhere to go. Two
  mechanisms are legitimate, and the design decides which:
  - An **image/URL control** — a plain `TextControl` (see `customColors` in
    the reference plugin's `controlPanel.tsx` for the shape: freeform text
    read straight through to the component, no closed `choices`) holding an
    SVG or image URL, rendered as the icon. This is the general case: it
    covers a brand not on any list, including one added after this plugin
    ships.
  - A **closed set of literal brand icons**, only when the design itself shows
    a closed, known set — "AWS or GCP or Azure" drawn as a small fixed switcher
    with no fourth option implied. Even here, add an escape hatch (a "custom"
    choice backed by the same URL field above) rather than assuming the set
    never grows.
  A fixed enum of generic icon names with no image/URL option anywhere in the
  control panel is not a stylistic gap here — it is checked. Stage F's own
  validator flags a control panel that names a specific brand and offers only
  a closed generic-icon enum with no way to add the real logo; treat this the
  same as the other rules in this document that the validator, not just this
  prose, holds you to.
- Keep the component driven by `transformProps` output; do no data shaping in
  the component.

`ChartMetadata` must set `category`, a real `description`, `tags`, `thumbnail`,
`useLegacyApi: false`, and appropriate `behaviors` (`Behavior.InteractiveChart`
when it should participate in cross-filtering).

## Performance is part of the brief

These plugins run in dashboards that are often embedded and reloaded frequently,
so a slow chart is a slow product. Fidelity comes first; performance comes
immediately after.

- **Ask the database once *per render*.** Every query object you declare runs
  again each time anyone opens the dashboard, forever — that is the cost being
  managed here, not the cost of you looking things up while building. If a card
  shows a total, a breakdown and a percentage, fetch the rows once and derive
  all three in `transformProps`.
  Reach for a second query object only when the shapes genuinely differ — a
  different grain, a different time window, a different dimension — never to
  save yourself a `reduce`.
- **Shape the data in `transformProps`, not in the component.** It runs once per
  data change; the component runs on every render.
- **Do not sort, group or aggregate in render.** If the design needs a top-5 cut
  or a descending order, express it in `buildQuery` as `row_limit` and `orderby`
  so the database does it, not the browser.
- **Memoise derived values** (`useMemo`) and avoid rebuilding arrays or objects
  inline in JSX.
- **Keep the DOM proportional to the data shown.** A ranked list of five bars
  should render five elements, not a virtualised grid.
- **No layout thrash.** Do not read `offsetWidth`/`getBoundingClientRect` during
  render; use the `width` and `height` props Superset already passes.
- **Import narrowly.** Pull in only what you use; a chart should not drag a
  charting library in for a handful of `div`s.

If the design's structure is simple — bars, a value, a list — render it with
plain elements and CSS rather than a charting library. It is faster, and it
matches the design more precisely than configuring a generic chart to look
like it.

## Output

```json
{
  "status": "ok",
  "files": [{ "path": "superset-frontend/plugins/...", "contents": "..." }],
  "params_hint": { },
  "review_notes": "what a reviewer should check first"
}
```

`params_hint` is the `params` a chart of this viz type needs — the control names
you defined and the values this region requires. Stage D uses it, since the
control panel does not exist on disk until your files are written. Write every
metric value as an adhoc metric object —
`{"expressionType": "SIMPLE", "column": {"column_name": "..."}, "aggregate": "SUM", "label": "..."}`
— never a bare column name: stage D copies the shape, and a column name in a
metric control is a query Superset rejects.

Emit complete, compiling files. `// TODO: implement` in a render path is a
failed response. Every file must be valid TypeScript with no `any`.
