# Implementation log

Running history of the Design-to-Dashboard feature: what we decided, why, and what changed. Append to the top of "Changes" as work lands. Decisions that were reversed stay recorded with the reason.

---

## 2026-09-08 — Design phase

### How we got here

1. **Started from a single system prompt.** The original idea was one LLM that "knows the codebase and best practices", takes a Figma/screenshot plus a requirement, and builds a dashboard.

   Problem: *"knows the codebase"* is an assertion, not a capability. An LLM told it knows the codebase invents `viz_type` keys and column names. Replaced with **injected context slots** plus a hard rule: anything not in context does not exist.

2. **Split into a six-stage pipeline.** Measured the real context cost first: **567 KB of control-panel source across 72 registered `viz_type`s (~140k tokens)**, while any single chart needs exactly one entry (~3k tokens). The registry was ~95% of the budget.

   Rejected the intuitive split (a "create charts" agent + an "add existing charts" agent) — deciding whether a chart exists is *one* decision, so a router would still need both contexts. Split **by context need** instead. Stage D (per-chart fan-out, one control schema per worker) is the ~45× win.

3. **Researched Superset 6.1's MCP server.** Read the source rather than the docs. Adopted it for stages B and C; kept our own write path. Reasons in `MCP_INTEGRATION.md`.

4. **Researched plugin deployment.** Established that a generated plugin needs a rebuild + redeploy on the default path, and that 6.1's dynamic-plugin loader avoids it but should not be depended on. Evidence in `PLUGIN_DEPLOYMENT.md`.

5. **Planned the UI.** Confirmed the extensions architecture cannot host a new top-level page, so it's a first-class SPA route. Model in `UI_PLAN.md`.

### Decisions

| # | Decision | Why | Reversible? |
|---|---|---|---|
| D1 | Six-stage pipeline, not one agent | Registry is ~140k tokens; per-chart workers need ~8k | Yes — stages are independently promptable |
| D2 | Pipeline orchestrated by deterministic Python, not agents negotiating | Gives per-stage retries, schema validation, caching, unit-testable boundaries | Yes |
| D3 | Stage C stays a single wide-context call | Global consistency (shared palette, formats, dedup of identical tiles) needs a global view | Yes |
| D4 | Symbolic `ref` indirection (`__REF__:c1`) | No real chart ids exist at plan time; lets D and E run in parallel before any write | No — baked into every stage contract |
| D5 | Build on 6.1, not the 6.0 fork | MCP only exists in 6.1; avoids carrying a backport patch | Costly to reverse |
| D6 | MCP for reads (B, C), our own path for writes | `generate_chart` can't express our custom plugins; `generate_dashboard` discards layout | Yes |
| D7 | Viz registry manifest stays ours | `get_chart_type_schema` covers only 7 abstract families, not our 20 custom plugins | No |
| D8 | Static plugin bundling (Path 1) is the contract; dynamic loading (Path 2) an opt-in accelerator | Path 2 is untested upstream and version-coupled; `new_plugin` should be rare anyway | Yes |
| D9 | Feature-flagged SPA route, not an extension | 6.1 extension points are `sqllab`/`editors` only; no chart or page contribution type | Yes |
| D10 | Review gates before conversational refinement | Refinement without review produces confidently wrong dashboards with no audit trail | Yes |

### Findings worth not rediscovering

- `MainPreset` is upstream; **custom plugins register only in `setupPluginsExtra.ts`** — this is what keeps upstream merges clean.
- Every custom plugin imports `@superset-ui/*` through its own `src/adapters/supersetAdapter.ts` barrel.
- `generate_chart`'s `config` is a discriminated union over exactly `xy | table | pie | pivot_table | mixed_timeseries | handlebars | big_number`. No escape hatch to raw `params`.
- `generate_dashboard` hardcodes `charts_per_row = 2` and ignores `position_json` entirely.
- `get_chart_preview` returns `url | ascii | vega_lite | table` — **no PNG**, so no render-and-diff loop against the design.
- Dynamic plugins share deps via `window['__superset__/<name>']` globals; `shared-modules.ts` untouched since 2021 and effectively untested.
- Unknown keys in a chart's `params` are **silently dropped** — the chart renders wrong with no error. Hence stage D validates against the injected control schema.

---

## Changes

### 2026-09-09 — Live verification, providers, chat UI, fidelity, stage F

A long session. The theme: **every component had a defect on first contact with
a real instance**, and none of those defects were reachable from fixtures.

#### Ran it for real

Superset installed into `.venv` (editable, this checkout) against the Docker
Postgres. Two setup errors worth not repeating:

- Installing from `pyproject.toml` resolved `flask-caching` 2.5.1 against the
  repo's pinned 2.3.1, and 2.5.1 added a kwarg `SupersetMetastoreCache` does not
  accept. **Install from `requirements/base.txt`**, not the loose ranges.
- Sharing a metadata database means **sharing `SECRET_KEY`** — database URIs are
  encrypted with it, so a mismatched key authenticates users fine and then fails
  every analytics query with `Invalid decryption key`.

#### Eight defects only a live run could find

| # | Defect | Why fixtures missed it |
|---|---|---|
| 1 | `InProcessGateway` needs a Flask **request** context — `mcp_auth_hook` pushes a fresh app context and discards a pre-set `g.user` | fixtures never authenticate |
| 2 | `_decode()` assumed `result.data` was a pydantic model. It is a synthesised `Root` class with no `model_dump`; **`structured_content`** is the plain dict | fixture gateway returned dicts already |
| 3 | Fixture *shapes* were wrong: real responses key rows by entity (`datasets`, `charts`) and nest `get_dataset_info` under `result` | the fixtures encoded my own misreading |
| 4 | Tool catalogue documented `page` as 0-based; the schema is **1-based, `gt=0`**, so every live `list_datasets` failed validation | `FixtureGateway` ignores arguments |
| 5 | `--live` had never worked: the harness's namespace-package stub shadowed the real `superset` | flag added with stage B, never exercised |
| 6 | Charts saved without `query_context` → `GET /api/v1/chart/<id>/data/` fails with "Chart has no query context saved" | nothing queried the charts |
| 7 | Analytics DB registered as `db:5432`, unresolvable from the host | no queries were run |
| 8 | `apply_plan`'s `begin_nested()` gave **false** atomicity: Superset commands carry `@transaction` and commit independently, so chart #1 leaked when chart #2 failed | the applier had never run |

Defect 8 is the most important. The fix is **compensating cleanup** — record what
was created, delete it on failure — because there is no transaction to roll back.
`PIPELINE_CONTRACT.md` and `BUILD_SPEC.md` still claim "one transaction" and are
wrong; they need correcting.

A related gap: compensation only runs if the process survives. Restarting the
backend mid-apply left 6 orphan charts, exactly as a crash would.

#### Providers: three, one protocol

| Provider | Reasoning text | Credentials |
|---|---|---|
| `claude_cli` | **no** — the CLI returns `thinking: ""` | host CLI |
| `claude_agent_sdk` | **yes** | host Claude Code creds |
| `anthropic_api` / `bedrock` | yes | API key (untested) |

The CLI redacts reasoning because `display` defaults to `"omitted"`, which streams
thinking blocks with empty text. `thinking={"type": "adaptive", "display":
"summarized"}` returns it — the Agent SDK accepts that parameter **and** uses
local credentials, so readable reasoning works before any API key exists. I twice
concluded the text was unavailable; it was the default, not a limit.

Two further bugs in that work: reasoning arrived only in the completed
`AssistantMessage` (fixed with `include_partial_messages` + `StreamEvent`:
1 callback → 179), and `stage_complete` **cleared** the buffer, so the one late
callback was wiped within milliseconds (now `take_thinking()` attaches it to the
event).

#### Transport

SSE works direct but not through the webpack dev-server proxy, which rewrites
response bodies. Switched to **cursor polling** (`?since=`) at 900ms — proxy
agnostic, works in production, and cheap because only new events are returned.

#### Chat UI

Rewritten from a card feed to a conversation: user bubble with a design
thumbnail, one agent bubble containing a **stepper** over the pipeline's known
shape (`stageModel.ts` folds events onto it), live reasoning under the running
step collapsing to "Show reasoning" when done, per-chart progress on D, and a
running elapsed/cost header.

#### Fidelity — two defects of a new kind

The first run produced a dashboard that *looked* fine and was subtly wrong:

- **`M`/`K` suffixes dropped.** Every KPI saved `,.1f`, and stage C asserted the
  suffix "cannot be appended by a d3 number format". **That is false** —
  `SMART_NUMBER` renders `8.92M`. The model invented a platform limitation and
  its honesty machinery reported the wrong answer convincingly. Both C and D now
  carry the rule, plus a "do not invent limitations" instruction.
- **Duplicate heading.** C decided `drop` ("rendered as the dashboard title") but
  E received *all* regions and applied its own header→MARKDOWN rule. E now
  excludes anything C dropped, so C's decisions are authoritative.
- Dashboard titles were the generic fallback because stage A records the title as
  a `header` **region**, not in `global`. Now derived from that region.

These are the first defects that failed *quietly*. Everything before crashed.

#### Stage F: custom plugins for exact fidelity

Chosen over CSS/handlebars because it keeps interactivity and matches the design
exactly. C's rubric was rewritten so `new_plugin` is first-class, with named
structural triggers (label-above-value, composed cards, fixed alignment, absent
mark types) and an explicit ban on reaching for a plugin over a colour or format.

`stages/f_scaffold.py` generates from the exemplar vendored at `design-to-dashboard/assets/reference-plugin/`
(correct 6.1 imports), validating: snake_case unique viz_type, **scoped** package
name, required files, paths inside the declared directory, the moved-import trap
(`styled` from `@apache-superset/core/theme`), no `any`, no TODOs.

`plugin_writer.py` performs the three registration artifacts — files, the
**`file:` dependency** in `package.json` (webpack only aliases scoped `file:`
deps to `src/`), and a call inside `setupPluginsExtra()` so `MainPreset.ts` stays
untouched. Idempotent. A unit test on a temp root caught the brace bug: the file
ships as `setupPluginsExtra() {}` on one line, which the original regex missed.

The runner then re-runs `build_viz_registry.py` so D can see the new control
panel, and passes F's `params_hint` to D — the panel did not exist when the run
started.

**Not automated deliberately:** `npm install` and the webpack rebuild. A plugin
run therefore creates the dashboard, but a chart on a brand-new viz type does not
render until those are done by hand.

#### Still missing

- Review gates (`RegionReview`, `PlanReview`). Stage B questions and C approvals
  halt the run; they cannot be answered in the UI. This is the largest gap, and
  the fidelity defects above are exactly what a gate would have caught.
- Region overlay on the uploaded design.
- Post-build verification and confidence score.
- Sessions are process memory; a restart loses them.
- `pre-commit run --all-files` has never been run.


### 2026-09-09 — Stage D: per-chart fan-out

Branch: `feat/design-to-dashboard`.

| File | Change |
|---|---|
| `design-to-dashboard/scripts/build_viz_registry.py` | Resolves each viz type's `controlPanel` file and records the path. `_verified()` drops any path not on disk with a warning, so a rotted override fails at generation rather than at stage D run time |
| `superset/design_to_dashboard/registry.py` | `find()`, `load_control_panel()` — reads the real control-panel source rather than a re-derived schema |
| `superset/design_to_dashboard/stages/d_configure.py` | **New.** `load_panel()`, prompt assembly, `run_one()`, `run_all()` (ThreadPoolExecutor fan-out), and a viz-type-aware `validate()` |
| `superset/design_to_dashboard/llm/claude_cli.py` | `max_turns` default 1 → 3; error detail now includes stdout, not just stderr |
| `superset/design_to_dashboard/llm/factory.py`, `superset/config.py` | `max_turns` default → 3 |
| `design-to-dashboard/fixtures/stage_d_output.json` | **New.** Golden stage-D output |

**Registry coverage:** 49/53 viz types have a verified control panel, 2 KB (`filter_time`) to 30 KB (`table`). Missing: 3 filter plugins and `time_table`.

#### Live-run results

Final: **6/6 charts valid, 0 problems, ~$2.44** (3 workers).

#### Two bugs, and which side they were on

**1. The validator was wrong, not the model.** The first run flagged all 6 charts with 12 problems. Re-validating the *same saved output* against the corrected checks gave **12 → 0** — every one a false positive, proven without re-running the LLM. Three causes:

- `row_limit` was required universally, but `big_number` has no such control. Checks are now viz-type aware, consulting the actual control-panel source.
- The `allowed` set collected `dimensions`, `measures` and `time_column` but **not** `filters[].col`, so `provider_name` — which stage B bound as a filter — read as invented.
- Every string in `params` was scanned, flagging generated `filterOptionName` ids and the `smart_date` format token as columns. Now scoped to fields that actually carry columns: `groupby`, `x_axis`, `metric(s)`, `adhoc_filters[].subject`, adhoc-metric `column.column_name`.

The lesson is worth keeping: a heuristic validator that guesses at "column-looking strings" produces confident false alarms. Validate against the schema you already have.

**2. `max_turns: 1` was wrong in general.** One worker died with a bare `Claude CLI exited 1` and empty stderr. Including stdout in the error revealed `"stop_reason":"tool_use"` — the model reached for a tool and hit the turn cap. Two fixes: the turn floor is no longer 1, and the stage D prompt no longer *cites the control-panel path* in a way that invites reading a file whose contents are already inlined. This is the same root cause as the stage A image failure, so the default changed everywhere rather than being patched per-stage.

#### Notes

- Each worker carries preamble + stage prompt + **one** control panel ≈ 8-15k tokens, against ~140k for the whole registry. The fan-out is the expensive stage; prompt-caching the shared prefix is the obvious cost lever.
- Workers are independent and a failure in one is captured as a result rather than killing the pool.
- Consistency across workers comes from stage C's design-system contract, not shared context — the four KPI cards came back with matching formats from four separate calls.


### 2026-09-08 — Stage C: viz registry, resolution, decision validation

Branch: `feat/design-to-dashboard`.

| File | Change |
|---|---|
| `design-to-dashboard/scripts/build_viz_registry.py` | **New.** Generates the viz-type manifest from source: `VizType.ts` and the `FilterPlugins` enum for keys, `MainPreset.ts` + `setupPluginsExtra.ts` for registrations, each plugin's metadata for name/category/tags/description. Reports what it could not resolve rather than silently omitting it |
| `design-to-dashboard/fixtures/viz_registry.json` | **New.** 53 viz types, 49 with full metadata |
| `superset/design_to_dashboard/registry.py` | **New.** Loads the manifest and renders compact summaries; `chart_types()` / `filter_types()` back validation |
| `superset/design_to_dashboard/mcp/catalog.py` | Added `list_charts`, `get_chart_info`, `STAGE_C_TOOLS` |
| `superset/design_to_dashboard/stages/c_resolve.py` | **New.** Prompt assembly (preamble + stage + envelope + catalogue + registry summaries), the run entry point, and a thorough `validate()` |
| `design-to-dashboard/fixtures/mcp/list_charts.json`, `get_chart_info.json` | **New.** Four existing charts, one of them a genuine reuse candidate on the bound dataset |
| `design-to-dashboard/fixtures/stage_c_output.json` | **New.** Golden stage-C output for building stage D |
| `design-to-dashboard/prompts/C_resolve.md` | Hardcoded custom-plugin inventory **removed** — see below |

#### The registry is now the single source of truth

The stage C prompt used to carry a table of the fork's 20 `plugin-chart-custom-*` plugins. On the first run the model dutifully chose `custom_kpi_card` and `custom_wrapper` — and `validate()` rejected them, because this repo is upstream 6.1 and has no such plugins.

That is the docs/repo split showing up as a bug: the prompt described one deployment while the code ran in another. A duplicated list is guaranteed to drift.

The inventory table is gone. The prompt now points at the **"Registered viz types"** block generated from the deployment's real registry, with an explicit rule not to name a viz type absent from it, and generic guidance for multi-chart regions ("look for a tabbed wrapper or a container; if the registry has neither, do not invent one"). When the fork's `setupPluginsExtra.ts` is present, the generator picks up its custom plugins automatically.

#### Live-run results

`--stage C` against fixtures: **3 iterations, 5 tool calls (budget 10), validation clean, ~$0.81**.

`counts = {reuse: 1, configure: 6, wrap: 0, new_plugin: 0, native_filter: 1, drop: 1}` — 9 decisions for 9 regions.

Behaviour worth recording:

- **Consistency, which is this stage's whole reason for being wide-context.** All four KPI tiles resolved to the same `big_number`, sharing one number format.
- **Reuse with real evidence.** It confirmed chart 318 via `get_chart_info` (right viz type, right datasource), and separately *rejected* charts 401 and 502 with reasons — 502 because it sits on `billing_accounts`, not the bound dataset.
- **The new registry rule fired.** For the tabbed "By service" card it noted this deployment has no wrapper or container viz type, dropped the tab switcher, and recorded that in `fidelity_loss` instead of inventing `custom_wrapper`.
- **Accurate limitation-spotting.** It flagged that `big_number` colours its delta by sign and cannot be inverted for cost semantics (green-on-decrease), and that Superset's table right-aligns numerics against the design's left alignment. Both are real.
- **Zero `new_plugin`** — the rubric's bias toward `configure` holding even with a design that has a bespoke KPI card and a tabbed widget.

#### Notes

- Registry summaries cost **~2,800 tokens for all 53 viz types**, against ~140k for the full control schemas. This is the context split working as designed: stage C gets enough to choose, never enough to configure.
- `validate()` checks decision coverage, viz types against the registry, reuse evidence, wrap children resolving and ordering before their parent, `filterType` against registered filter plugins, counts matching the decisions, and `needs_approval` whenever `new_plugin > 0`.
- 4 of 53 entries still lack metadata (3 filter plugins, `pivot_table_v2`) because they are re-exported under aliases the source parser cannot follow. The generator prints them on every run.


### 2026-09-08 — Stage B: MCP gateway, tool loop, binding

Branch: `feat/design-to-dashboard`.

| File | Change |
|---|---|
| `superset/design_to_dashboard/mcp/gateway.py` | **New.** `MCPGateway` Protocol; `InProcessGateway` calls Superset's MCP tools in-memory via `fastmcp.Client(mcp)`; `FixtureGateway` replays recorded JSON so stages run with no Superset |
| `superset/design_to_dashboard/mcp/catalog.py` | **New.** Tool specs shown to the model (`list_datasets`, `get_dataset_info`, `execute_sql`), mirroring the real MCP request schemas while hiding options the stage shouldn't set |
| `superset/design_to_dashboard/pipeline/tool_loop.py` | **New.** Bounded, provider-agnostic loop. Model replies `{"tool_calls":[...]}` or `{"final":{...}}`; Python executes and feeds observations back. Transcript re-sent each iteration rather than relying on server-side session state, so it behaves identically on `claude -p` and on a future API provider |
| `superset/design_to_dashboard/stages/b_bind.py` | **New.** Assembles B's system prompt (preamble + stage + envelope + catalog), filters non-data roles before the model sees them, runs the loop, and `validate()`s the result structurally |
| `design-to-dashboard/fixtures/mcp/*.json` | **New.** `list_datasets`, `get_dataset_info` (keyed by identifier), `execute_sql` responses for a plausible `finops.cloud_cost_daily` schema |
| `design-to-dashboard/fixtures/stage_b_output.json` | **New.** Golden stage-B output for developing stage C |
| `design-to-dashboard/scripts/smoke_test.py` | Rewritten loader: registers `superset` as a namespace package pointing at the source tree so submodules import **without executing `superset/__init__.py`** — replaces the earlier `exec()` hack. Added `--stage B`, `--live`, `--max-tool-calls`, `--out`, and a tool-call dump on both success and failure |

#### Live-run results

`--stage B` against fixtures: **4 iterations, 7 tool calls (budget 8), validation clean, ~$0.51**.

All 8 data regions bound to dataset 42. Behaviour worth recording, because it shows the prompt rules actually firing:

- **Search then narrow, as instructed** — three `list_datasets` probes in one round, then `get_dataset_info` on only two candidates.
- **Rejected a join it didn't need.** It considered `billing_accounts` for the detail table, then rejected it because `cloud_cost_daily` already carries `account_name` — the "one dataset per region" rule working.
- **Two-level read of the tabbed card.** It bound `service_family` to the tabs and `service_name` to the bars, and explained why using `service_name` for both would be wrong.
- **Refused to over-claim.** The `execute_sql` fixture returns a canned success with a note saying nothing is really executed; the model read that note, kept `validated: false`, and wrote the caveat into `evidence`. It also flagged that `'AWS'`/`'Azure'`/`'GCP'` literal casing was never verified against stored values.

**One bug found and fixed:** `FixtureGateway` looked up its switch key at the top level of `arguments`, but real MCP tools nest everything under a single `request` model. Every `get_dataset_info` call therefore failed, and the model — correctly — fell back to `needs_input` with questions instead of inventing columns. The gateway now accepts both shapes. Worth noting the failure mode was *safe*: a broken tool produced honest questions, not fabricated bindings.

#### Design notes

- **Tool loop over free-form agentic calling.** Bounded iterations and an explicit call budget make the stage cacheable, replayable and unit-testable, and the budget is enforced in Python rather than trusted to the prompt.
- **Failed tool calls become observations, not exceptions.** A wrong dataset id or bad SQL is information the model should act on.
- **`InProcessGateway` inherits RBAC for free.** `mcp_auth_hook` reuses the active Flask request context, so tools execute as the requesting user with no gateway-side permission code.
- Stage B costs roughly 3× stage A. The transcript is re-sent each iteration; if this becomes an issue, prompt-cache the system prompt and truncate old observations rather than shortening the budget.


### 2026-09-08 — Backend view, LLM provider, local test harness

Branch: `feat/design-to-dashboard`.

| File | Change |
|---|---|
| `superset/views/design_to_dashboard.py` | **New.** `DesignToDashboardView(BaseSupersetView)`, `route_base="/design-to-dashboard"`, `class_permission_name="DesignToDashboard"`, `MODEL_VIEW_RW_METHOD_PERMISSION_MAP`. `@before_request` raises `NotFound` when the flag is off — mirrors `TagView`. Serves the SPA via `render_app_template()` |
| `superset/initialization/__init__.py` | `appbuilder.add_view_no_menu(DesignToDashboardView)` |
| `superset/config.py` | `DESIGN_TO_DASHBOARD_LLM` settings block (provider, model, timeout, max_turns, allow_cli_provider) |
| `superset/design_to_dashboard/llm/base.py` | **New.** `LLMProvider` Protocol, `LLMResponse`, `LLMError`/`LLMTimeoutError`. Stages talk to this, never to a vendor SDK |
| `superset/design_to_dashboard/llm/claude_cli.py` | **New.** Shells out to `claude -p --output-format json`. Prompt via stdin, system prompt via temp file (stage prompts exceed comfortable argv length and would otherwise be visible to `ps`). `subprocess.run` list-form, `shell=False` |
| `superset/design_to_dashboard/llm/factory.py` | **New.** Resolves provider from config; refuses `claude_cli` unless `app.debug` or `allow_cli_provider`, and logs a warning when used |
| `design-to-dashboard/scripts/smoke_test.py` | **New.** Runs one stage against the local CLI without booting Superset — loads the provider by file path so no virtualenv is needed for prompt iteration |
| `design-to-dashboard/fixtures/mock_dashboard.png` | **New.** Synthetic 1440×900 cloud-cost dashboard (4 KPI tiles, line chart, tabbed bar chart, table, filter bar) for testing without real customer designs |
| `design-to-dashboard/fixtures/stage_a_output.json` | **New.** Golden stage-A output — lets stages B+ be developed without re-calling the LLM |

#### Live-run results

`--stage ping` and `--stage A` both pass against `claude -p` (model `claude-opus-5`), ~$0.18/run for stage A.

Stage A returned all five contract keys and **9 regions** — 1 header, 1 filter, 4 KPI, 2 chart, 1 table — exactly matching the fixture, with all nine `global` keys, correct canvas, complete `reading_order`, and empty `conflicts`. It correctly kept the four identical KPI tiles as separate regions, classified the filter bar as top-positioned, and flagged the green-down delta as cost-inverted semantics in `ambiguity`.

**Two bugs found by running it, both fixed:**

1. `--max-turns 1` failed on any image stage. Reading an image costs a tool-use turn, so the model hit the cap before answering. The provider now floors turns at `len(images) + 2` when images are present; text-only stages keep the 1-turn budget.
2. Stage A returned `column_count: 4` — the KPI row's card count, not a page grid. The prompt said "the design's own grid, if inferable", which is genuinely ambiguous. Reworded to ask for the repeating unit the widest row is built on, explicitly not the count of cards in a row.

#### Notes and constraints

- The `claude_cli` provider is **development only** and says so in its module docstring, in `config.py`, and via a runtime warning. It spawns a subprocess as the web server's OS user using the host developer's Claude credentials — no per-user attribution, quota, or audit. Swap `provider` before any shared deployment. Bedrock lands as a sibling module implementing the same Protocol; **no stage code changes** when it does.
- `claude_cli.py` uses stdlib `json`, not `superset.utils.json` — it parses an external process's stdout, and staying import-light is what lets the harness run without the app.
- A new FAB permission (`can_read on DesignToDashboard`) is created on init; **run `superset init`** after enabling the flag or the route 403s for non-admins.


### 2026-09-08 — Feature flag, route, page shell

Branch: `feat/design-to-dashboard` (off `6.1`).

| File | Change |
|---|---|
| `superset/config.py` | Added `"DESIGN_TO_DASHBOARD": False` to `DEFAULT_FEATURE_FLAGS`, alphabetically between `DATE_FORMAT_IN_EMAIL_SUBJECT` and `DYNAMIC_PLUGINS`, with a `@lifecycle: testing` comment matching the file's convention |
| `superset-frontend/packages/superset-ui-core/src/utils/featureFlags.ts` | Added `DesignToDashboard = 'DESIGN_TO_DASHBOARD'` to the `FeatureFlag` enum, respecting the file's "KEEP THE LIST SORTED ALPHABETICALLY" instruction |
| `superset-frontend/src/views/routes.tsx` | Lazy import with `webpackChunkName: "DesignToDashboard"`; route `/design-to-dashboard/` pushed inside an `isFeatureEnabled(FeatureFlag.DesignToDashboard)` block, mirroring the `TaggingSystem` pattern |
| `superset-frontend/src/pages/DesignToDashboard/index.tsx` | **New.** Page shell: header + two-pane layout (conversation, preview). Emotion `styled` with antd v5 theme tokens only, no hardcoded colours. `data-test` hooks on both panes |
| `superset/initialization/__init__.py` | `appbuilder.add_link("Design to Dashboard", ...)` at top level, gated by `cond=lambda: feature_flag_manager.is_feature_enabled("DESIGN_TO_DASHBOARD")` |

Verification run: `py_compile` clean on both Python files; `prettier --check` and `eslint` clean on all changed frontend files; every theme token used (`sizeUnit`, `colorBgLayout`, `colorBgContainer`, `colorBorder`, `colorText`, `colorTextSecondary`, `colorTextTertiary`, `fontSizeXL`, `fontWeightStrong`, `borderRadius`) confirmed in existing use.

**Not done yet:** no backend blueprint serves `/design-to-dashboard/` — the SPA route exists but the nav link will 404 until a view is registered. That lands with the API in the next step.

**Note on the working tree:** the branch was cut with pre-existing uncommitted changes present (`superset-frontend/package.json`, `package-lock.json`, `MainPreset.ts`, and an untracked `plugin-chart-hello-world/`). These are unrelated to this feature and were carried along by the branch, not authored here.

---

## Next

1. `superset/design_to_dashboard/` package — models (`DesignSession`, `DesignPlan`, UUID PKs), migration, session + asset endpoints
3. MCP gateway for in-process tool access (stages B and C)
4. Pydantic schemas for all six stage contracts — the spine everything validates against
5. Stages A → B → C behind their gates; plan generation only, no apply
6. `RegionReview` and `PlanReview` components
7. Stage D fan-out, stage E, then the applier with transactional rollback

## Open questions

- **LLM provider config** — Bedrock credentials and per-user token budget still open. Unblocked for local dev by the `claude_cli` provider.
- **Viz registry manifest** — build-time generated file, or a runtime endpoint the frontend populates from `getChartMetadataRegistry()`? Affects whether stage D can run without a browser.
- **Asset storage** — design uploads need a store with a TTL; reuse the thumbnail cache config or add one?
