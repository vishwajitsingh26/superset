# Stage F — Scaffold plugin

**Input:** the design cropped to this region, plus the region (Stage A), its binding (Stage B), its `new_plugin` decision (Stage C), the design-system contract, and the source of a reference plugin.
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

## Required structure

```
superset-frontend/plugins/plugin-chart-<name>/
├── package.json          # "@superset-ui/plugin-chart-<name>", peerDependencies only
└── src/
    ├── index.ts          # export { default as <Class> } from './plugin'
    ├── types.ts          # FormData + StylesProps + component props
    ├── <Component>.tsx   # the React component
    ├── images/thumbnail.png
    └── plugin/
        ├── index.ts          # ChartPlugin subclass + ChartMetadata
        ├── buildQuery.ts     # buildQueryContext(formData)
        ├── controlPanel.ts   # ControlPanelConfig
        └── transformProps.ts # ChartProps -> component props
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

## Naming is load-bearing

The package **must** be named `@superset-ui/plugin-chart-<name>` and live in
`plugins/plugin-chart-<name>`. Webpack only aliases a `file:` dependency to its
`src/` when the package name starts with `@superset-ui` or `@apache-superset`;
an unscoped name compiles under TypeScript but fails webpack with
`Module not found`, because it resolves `main: lib/index.js`, which dev never
builds.

## Three registration artifacts — all required

1. **`package.json` dependency** in `superset-frontend/package.json`:
   `"@superset-ui/plugin-chart-<name>": "file:./plugins/plugin-chart-<name>"`.
   Without it webpack will not alias the package and the import fails.
2. **Registration** appended inside `setupPluginsExtra()` in
   `superset-frontend/src/setup/setupPluginsExtra.ts` — the deployment's
   override hook, already called by `setupPlugins.ts`. **Do not edit
   `MainPreset.ts`**: it is upstream code and edits create merge conflicts on
   every Superset upgrade.
3. **A `viz_type` key** in `snake_case`, unique against the registry.

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
- **A control whose result the design never shows is still built.** Render the
  toggle, the tab strip, the expand button. The state the design draws gets the
  real implementation; the others render an empty state or "Coming soon". Never
  invent what an unpictured view contains.
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
- Reproduce the card chrome from the design-system contract: radius, border,
  padding, typography scale.
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
  "viz_type": "custom_<name>",
  "plugin_name": "Custom <Name>",
  "package_name": "@superset-ui/plugin-chart-<name>",
  "directory": "superset-frontend/plugins/plugin-chart-<name>",
  "files": [{ "path": "superset-frontend/plugins/...", "contents": "..." }],
  "package_json_dependency": {
    "name": "@superset-ui/plugin-chart-<name>",
    "spec": "file:./plugins/plugin-chart-<name>"
  },
  "registration": {
    "import_line": "import { <Class> } from '@superset-ui/plugin-chart-<name>';",
    "register_line": "  new <Class>().configure({ key: '<viz_type>' }).register();"
  },
  "params_hint": { },
  "review_notes": "what a reviewer should check first"
}
```

`params_hint` is the `params` a chart of this viz type needs — the control names
you defined and the values this region requires. Stage D uses it, since the
control panel does not exist on disk until your files are written.

Emit complete, compiling files. `// TODO: implement` in a render path is a
failed response. Every file must be valid TypeScript with no `any`.
