# Stage F — Scaffold plugin

**Input:** one region (Stage A), its binding (Stage B), its `new_plugin` decision (Stage C), the design-system contract, and the source of a reference plugin.
**Not in context:** other regions, the registry, the design image.
**Output:** one `PluginScaffold`.

Runs when Stage C decides a design's structure cannot be expressed by any
registered viz type. Your job is a plugin that renders **the design as drawn** —
not an approximation.

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
- Keep the component driven by `transformProps` output; do no data shaping in
  the component.

`ChartMetadata` must set `category`, a real `description`, `tags`, `thumbnail`,
`useLegacyApi: false`, and appropriate `behaviors` (`Behavior.InteractiveChart`
when it should participate in cross-filtering).

## Performance is part of the brief

These plugins run in dashboards that are often embedded and reloaded frequently,
so a slow chart is a slow product. Fidelity comes first; performance comes
immediately after.

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
