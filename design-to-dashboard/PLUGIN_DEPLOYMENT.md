# Deploying a generated plugin

What happens after Stage F emits a new `plugin-chart-custom-*`. Verified against Superset 6.1.0 source.

**Short answer:** with the default (static) path, yes — a new plugin needs a frontend rebuild and a redeploy before any dashboard can use it. Superset 6.1 also ships a **dynamic** path that avoids redeploying Superset, at the cost of building and hosting the plugin bundle yourself.

## Path 1 — Static bundling (what the fork does today)

Stage F writes the plugin and appends one import + one `.register()` call to `setupPluginsExtra.ts`. That file is compiled into the main frontend bundle by webpack, so the viz type does not exist for the browser until the bundle is rebuilt.

```
review the branch → npm ci && npm run build (superset-frontend)
                  → rebuild the image / ship static assets
                  → restart / redeploy
                  → viz_type now selectable in Explore and usable in dashboards
```

**Implications for this feature:**
- A run that produces a new plugin **cannot finish in one shot.** It ends at "branch ready for review", not at "dashboard created".
- The dashboard depending on that plugin must be created *after* the deploy. Either the user re-runs the pipeline post-deploy, or the orchestrator persists the plan and resumes it.
- This is the main reason Stage C's rubric is biased so hard toward `configure`: a `new_plugin` decision converts a two-minute interaction into a release cycle.

**Recommended orchestrator behaviour:** when `counts.new_plugin > 0`, split the run.
1. Build and create everything that does *not* depend on the new plugin — the dashboard exists, partially populated.
2. Emit the plugin branch for review.
3. Persist the pending regions against the session. After deploy, resume and add the remaining charts via `add_chart_to_existing_dashboard` (MCP) or `UpdateDashboardCommand`.

A half-built dashboard the user can see beats nothing while they wait on a release.

## Path 2 — Dynamic plugins (no Superset redeploy)

Superset 6.1 carries a runtime plugin loader, off by default.

```python
# superset_config.py
FEATURE_FLAGS = {"DYNAMIC_PLUGINS": True}
```

### Mechanism

Not module federation — `window` globals.

```ts
// superset-ui-core/src/dynamic-plugins/shared-modules.ts
const withNamespace = (name: string) => `__superset__/${name}`;
window[`__superset__/react`] = await import('react');
```

The host loads its shared deps and hangs each on a namespaced global. Your remote bundle is built with webpack `externals` mapping `react` → `window['__superset__/react']`, so it never bundles its own copy — it reads the host's:

```js
react, react-dom, lodash, @superset-ui/core, @superset-ui/chart-controls
```

Then `DynamicPluginProvider` (`superset-frontend/src/components/DynamicPlugins/index.tsx`) calls `GET /dynamic-plugins/api/read`, runs `defineSharedModules(...)`, loads each `bundle_url`, and the bundle self-registers into `getChartMetadataRegistry()` under `key`.

Storage: `superset/models/dynamic_plugins.py` — table `dynamic_plugin` with `name`, `key`, `bundle_url`. The model comment is explicit: *"key corresponds to viz_type from static plugins."* CRUD lives at `/dynamic-plugins/` (`superset/views/dynamic_plugins.py`), 404 unless the flag is on.

```
build the plugin bundle standalone → host it (CDN / bucket / same origin)
   → add a row: name, key = viz_type, bundle_url
   → hard-refresh; the viz type registers at runtime
```

No Superset rebuild, no restart.

### Maturity — the evidence

Being on 6.1 gets us the code. It says nothing about how mature this particular subsystem is. The git history does.

**Feature activity has been flat for ~4 years:**

| Commit | What |
|---|---|
| `b5dd0f32cc` #10288 (~2020) | `feat: Dynamically imported viz plugins` — the original |
| `e01015f792` #13141 (~2021) | `fix: handle lack of dynamic plugins` — last real frontend fix |
| `eb9dafc872` #14650 (~2021) | `chore: Register dynamic plugins and add feature checks` |
| `3c41ff68a4` #17552 (2021) | last commit touching `shared-modules.ts` — a monorepo move |

Everything after that is incidental: antd v5 theming overhaul (#31590), React import cleanup (#28571), TS enum casing (#26875), FAB 5.x bump (#33055), core repackaging (#38448). **The load mechanism itself has been untouched since 2021.**

**The source is candid about its own maturity.** From `shared-modules.ts`:

> *"Dependency management using global variables, because for the life of me I can't figure out how to hook into UMD from a dynamically imported package."*

and, on the module type:

> *"The type of an imported module. Don't fully understand this, yet."*

**Test coverage is close to nil.** `tests/integration_tests/dynamic_plugins_tests.py` contains two assertions: the route 404s when the flag is off, 200s when it's on. Nothing exercises loading a bundle, registering a `viz_type`, or rendering one. There is no frontend test of the loader.

**But it is not dead code.** `usePluginContext` is wired into real production paths — `VizTypeControl`, `VizTypeGallery`, `VizTile`, `ExploreViewContainer`, `AddSliceCard` — and maintainers carried it faithfully through the antd v5 overhaul and the core repackaging. It compiles, it stays wired, and dynamic plugin metadata genuinely reaches the viz picker.

### The risk that actually matters

A remote bundle must be built against the **exact** `@superset-ui/core` the host runs. Version skew fails at mount with an opaque error, and #38448 reorganized those very packages recently. That is precisely the class of change that silently breaks a remotely-built bundle, and no existing test would catch it.

Secondary risks:
- Externals must match `sharedModules` exactly, or a second React ships and hooks break.
- `bundle_url` is fetched and executed in every user's browser. Remote code execution by design.
- You still build the bundle — this removes the *Superset* deploy, not the build step.

### If we enable it

- Pin the plugin build to the host's exact `@superset-ui/core` version **in CI**, and fail the build on skew.
- Serve bundles over HTTPS from an origin we control. Never a third-party CDN.
- Restrict write access to the `dynamic_plugin` table to admins.
- Add the smoke test upstream doesn't have: load a bundle, assert the `viz_type` registers and renders.

## Path 3 — The new Extensions architecture: not applicable yet

6.1 ships `superset-extensions-cli`, `superset/extensions/`, and `superset-core`'s extension API, with a real deployment story in `docs/developer_docs/extensions/deployment.md`. It is the strategic direction.

But the available extension points are **`sqllab` and `editors` only**, and the contribution types are views, commands, and menus. There is **no visualization/chart contribution type**. A custom viz plugin cannot ship as an extension today.

Revisit when a chart extension point lands — at that point Stage F should target it instead of Path 1, and the redeploy problem disappears properly.

## Recommendation

Ship **Path 1** as the default and make the split-run behaviour above part of the orchestrator from day one — it is the honest, reviewable path, and code review on generated plugin code is a feature rather than an obstacle.

Treat **Path 2 as an accelerator, never a dependency.** Path 1 is the contract; Path 2 is an optimisation we can withdraw. Because Stage F emits identical plugin source either way — only packaging and registration differ — adopting Path 2 costs nothing structural, and if a future upgrade breaks it we fall back to a rebuild and lose only turnaround time.

There is also a proportionality argument. If the pipeline works as designed, `new_plugin` is **rare** — Stage C's rubric is deliberately biased toward `configure`. Taking an operational dependency on a lightly-tested subsystem, plus an RCE surface in every user's browser, to optimise a path we hit a handful of times a quarter is a poor trade.

Offer it as opt-in for teams that want same-session turnaround, with the security caveats surfaced in the UI at the point of enabling it.
