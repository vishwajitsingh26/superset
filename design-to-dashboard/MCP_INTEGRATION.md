# MCP in Superset 6.1 — what it gives us, what it can't

Researched directly against the 6.1.0 source at `~/Documents/GitHub/superset` (branch `6.1`), not from docs. **Decision taken: we build on 6.1**, so all of this is available. Stages B and C use it directly.

## What ships in 6.1

```
superset/mcp_service/          the server + tools (fastmcp>=3.1.0,<4.0)
superset/core/mcp/             dependency injection for @tool / @prompt
superset-core/src/superset_core/mcp/   the abstract decorators extensions use
superset/cli/mcp.py            CLI entrypoint
docs/admin_docs/configuration/mcp-server.mdx
docs/developer_docs/extensions/mcp.md
```

### Tool inventory

| Domain | Tools |
|---|---|
| discovery | `get_instance_info`, `get_schema`, `health_check` |
| database | `list_databases`, `get_database_info` |
| dataset | `list_datasets`, `get_dataset_info`, `create_virtual_dataset` |
| chart | `generate_chart`, `update_chart`, `list_charts`, `get_chart_info`, `get_chart_data`, `get_chart_preview`, `update_chart_preview`, `get_chart_type_schema` |
| dashboard | `generate_dashboard`, `add_chart_to_existing_dashboard`, `get_dashboard_info`, `list_dashboards` |
| SQL Lab | `execute_sql`, `save_sql_query`, `open_sql_lab_with_context` |
| explore | `generate_explore_link` |

Every mutating tool carries `class_permission_name` and runs through `mcp_auth_hook` + `check_chart_data_access`, so **RBAC is enforced per tool** against the calling user.

## The two blockers

### 1. `generate_chart` cannot create our custom plugins

`GenerateChartRequest.config` is a **pydantic discriminated union** on `chart_type`, and the discriminator accepts exactly seven values:

```
xy | table | pie | pivot_table | mixed_timeseries | handlebars | big_number
```

`get_chart_type_schema` exposes the same seven. There is no path to `custom_kpi_card`, `custom_wrapper`, `container_chart`, `custom_hierarchy_table`, or any of our other 20 `plugin-chart-custom-*` viz types — the union has no member for them and no escape hatch to raw `params`.

Since resolving a design to our custom plugins **is the core of this feature**, MCP cannot own chart creation. Stage D keeps its own write path.

### 2. `generate_dashboard` ignores layout

It takes `chart_ids` and calls `_create_dashboard_layout()`, which hardcodes:

```python
charts_per_row = 2
chart_width  = GRID_DEFAULT_CHART_WIDTH
chart_height = 50
```

Two charts per row, uniform size, `ROW > COLUMN > CHART`. It does not accept `position_json`. A design-to-dashboard feature whose entire value is reproducing a layout cannot delegate layout to a tool that discards it. Stage E and our applier stay.

### Also worth knowing

`get_chart_preview` returns `url | ascii | vega_lite | table` — **no PNG**. So there is no true rendered-image feedback loop to diff against the original design. `vega_lite` is a spec rather than Superset's actual render, and custom plugins won't emit it at all.

## What we should take

| Pipeline stage | MCP tool | Value |
|---|---|---|
| **B bind** | `list_datasets`, `get_dataset_info` | Replaces our `context.py` dataset introspection outright — same data, permission-filtered, already schema'd |
| **B bind** | `execute_sql` | Validate a `derivable` metric's SQL *before* building on it, instead of discovering it at render time |
| **B bind** | `create_virtual_dataset` | Rescues some `unavailable` regions — a missing shape can become a virtual dataset instead of a blocking question |
| **C resolve** | `list_charts`, `get_chart_info` | The reuse index, for free |
| **C resolve** | `get_instance_info`, `get_schema` | Instance capability discovery |
| **D configure** | the 5-layer validation pipeline | `schema_validator`, `dataset_validator`, `cardinality_validator`, `format_validator`, `chart_type_suggester` — column-existence checks with fuzzy-match suggestions, aggregate/type compatibility, XSS and SQL-injection prevention. Worth reusing directly even on our own write path |
| **verify** | `get_chart_data`, `get_chart_preview` | Confirm a created chart actually returns rows before declaring success |
| **all** | `mcp_auth_hook`, `check_chart_data_access` | Per-tool RBAC — satisfies the "re-validate against the caller's permissions" requirement in `BUILD_SPEC.md` §5. **Verified on a live 6.1 instance**, with one constraint: this works only from inside a Flask *request* context. `mcp_auth_hook` pushes a fresh app context when no request is active, discarding a pre-set `g.user`; from a bare app context tools raise "No authenticated user found" unless `MCP_DEV_USERNAME` is set. Serving the pipeline from an API endpoint satisfies this naturally. |

## Recommended architecture: hybrid

```
Stage A  decompose        ── ours (vision; MCP has nothing here)
Stage B  bind             ── MCP: list_datasets, get_dataset_info, execute_sql
Stage C  resolve          ── MCP: list_charts, get_chart_info  +  our registry summaries
Stage D  configure        ── OURS (custom viz types) + MCP validation pipeline
Stage E  layout           ── OURS (fidelity; generate_dashboard discards layout)
Stage F  scaffold         ── ours
apply                     ── OURS: CreateChartCommand + position_json write
verify                    ── MCP: get_chart_data, get_chart_preview
```

Read and validate through MCP; write through our own path. That inverts the usual instinct, and the reason is specific: MCP's write tools are deliberately narrow — a safe, small surface for a general-purpose assistant — while this feature needs the full `params` surface and exact layout control.

## A second, larger opportunity

The tools above are for *us calling MCP*. The reverse is also available: **expose this pipeline as MCP tools of its own**, using the `@tool` decorator from `superset_core.mcp`. A `design_to_dashboard` tool would then be callable from Claude Desktop, Claude Code, or any MCP client — not just the in-app chat panel. The extension path is documented in `docs/developer_docs/extensions/mcp.md`, and `superset/mcp_service/chart/prompts/create_chart_guided.py` shows the in-repo pattern for shipping an MCP *prompt* alongside tools.

Worth doing after the in-app flow works, not before.

## Baseline

We implement against 6.1, so `superset/mcp_service`, `superset/core/mcp`, `superset-core`'s MCP API and the `fastmcp` extra are all present. No backport, no patch to carry.

The 6.0 fork (`cloudkeeper-analytics`) does not have MCP; if work lands there first it must be rebased onto 6.1 before stage B can run. The 20 custom plugins are insulated from that rebase by `setupPluginsExtra.ts` and each plugin's `adapters/supersetAdapter.ts` barrel, so the merge surface is smaller than it looks.
