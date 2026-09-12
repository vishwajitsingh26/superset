# Stage F — Scaffold plugin

**Input:** the design cropped to this region, plus the region (Stage A) — whose `observed`, `unusual_treatment`, `controls` and `frame` are the specification — its binding (Stage B), its `new_plugin` decision (Stage C), the design-system contract, and the source of a reference plugin.
**Not in context:** other regions, the registry, the rest of the design.
**Output:** one `PluginScaffold`.

Runs when Stage C decides a design's structure cannot be expressed by any
registered viz type. Your job is a plugin that renders **the design as drawn** —
not an approximation.

## You can see the section you are building

An image is attached: the design, cropped to this region with a small margin.
**Read it before you write anything.** It is the specification. The JSON
description beside it is a summary of the same thing written by another stage,
and where the two disagree, the image wins.

Take from it what prose cannot carry: corner radius, border colour and weight,
padding inside the card, the gap between elements, font sizes and weights and
the ratio between them, exact fill colours, icon size, whether a value is
aligned against its label or under it, how much whitespace sits above a title.
Those are the difference between a component that resembles the design and one
that matches it.

If no image is attached the crop could not be made; say so in `review_notes`
and build from the description alone.

## Three fields in the region carry the brief

The region JSON is long. These three are the ones that decide whether this
plugin is right, so read them before the rest:

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
  card and drives every other chart on the dashboard.
- **`table`** — cells that are drawn rather than written: ratio bars,
  sparklines, trend arrows, chips, expandable hierarchy rows.
- **`navigation`** — breadcrumbs and drill headers, which move the dashboard
  between states rather than plotting data.

Where your archetype is not `viz`, production code for it is appended below the
reference plugin. Reproduce that mechanism; the styling around it is not the
point.

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
it exactly:

- Reproduce the observed layout — where labels sit relative to values, what is
  above versus beside what.
- Reproduce the observed number formatting, including magnitude suffixes.
- Reproduce the card chrome from the design-system contract's `card_chrome`
  and `typography`: radius, border, shadow, padding, header style, and the
  size/weight scale. **Take these from the contract, not from your crop**,
  even where your crop looks slightly different. Every plugin in this run is
  written in parallel by a worker that sees only its own card; the contract
  is the one thing that makes six of them agree, and the card treatment is
  the most repeated element on the page.
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
control panel does not exist on disk until your files are written.

Emit complete, compiling files. `// TODO: implement` in a render path is a
failed response. Every file must be valid TypeScript with no `any`.
