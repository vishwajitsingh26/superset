# Example run

A full trace of one design through the six-stage pipeline. Doubles as the fixture set for orchestrator tests — each stage's expected output is here.

**Design under test:** a cloud-cost dashboard — 4 KPI tiles across the top, a spend-over-time line chart, a tabbed card showing per-service breakdowns, a detail table, and a provider filter in a top bar.

---

## Stage A — decompose

Context: image + requirement only. Names no column and no `viz_type`, because neither is in its context.

```json
{
  "status": "ok",
  "regions": [
    { "region_id": "r00_filter_bar", "role": "filter", "bbox": {"x":24,"y":24,"w":1392,"h":48},
      "title": "Provider",
      "observed": "single dropdown, top-left, placeholder 'All providers'",
      "implied_data": "cloud provider selector",
      "confidence": "high", "ambiguity": null },

    { "region_id": "r01_aws_spend", "role": "kpi", "bbox": {"x":24,"y":96,"w":300,"h":140},
      "title": "AWS",
      "observed": "$1.24M in 32px semibold, green down-arrow '8.2% vs last month', 'AWS' label top-left, sparkline across the bottom third",
      "implied_data": "current-month AWS spend with month-over-month change and a short trend",
      "interactions": [], "confidence": "high", "ambiguity": null },

    { "region_id": "r05_spend_trend", "role": "chart", "bbox": {"x":24,"y":260,"w":900,"h":320},
      "title": "Spend over time",
      "observed": "multi-series line, 3 series, legend top-right, y-axis '$0–$2M', x-axis months Jan–Dec, gridlines horizontal only",
      "implied_data": "monthly spend split by cloud provider",
      "confidence": "high", "ambiguity": null },

    { "region_id": "r06_service_tabs", "role": "chart", "bbox": {"x":940,"y":260,"w":476,"h":320},
      "title": "By service",
      "observed": "card with tab switcher 'Compute | Storage | Network'; active tab shows a horizontal bar chart",
      "implied_data": "spend by service, grouped into three service families",
      "interactions": ["tab switcher"], "confidence": "medium",
      "ambiguity": "inactive tabs' contents not visible; assumed same mark type" }
  ],
  "global": {
    "canvas": {"w":1440,"h":900}, "column_count": 12, "tabs": null,
    "filter_bar": {"present": true, "position": "top", "controls": ["Provider"]},
    "palette": ["#1FA8C9","#454E7C","#5AC189"],
    "theme": "light",
    "card_chrome": "white, 8px radius, 1px #E0E0E0 border, 16px padding",
    "reading_order": ["r00_filter_bar","r01_aws_spend","r02_azure_spend","r03_gcp_spend","r04_total_spend","r05_spend_trend","r06_service_tabs","r09_detail_table"]
  },
  "conflicts": [],
  "notes": "Four KPI tiles are visually identical; emitted as four regions r01–r04."
}
```

Note `r06` stays **one** region despite containing three tabbed charts — wrappers are single regions.

## Stage B — bind

Context: A's regions + dataset catalogue. No image, no registry.

```json
{
  "status": "ok",
  "bindings": [
    { "region_id": "r01_aws_spend", "state": "bound", "dataset_id": 42,
      "dataset_name": "cloud_cost_daily",
      "dimensions": ["provider_name"], "measures": ["total_cost"],
      "time_column": "usage_date", "time_grain": "P1M",
      "filters": [{"col":"provider_name","op":"==","val":"AWS"}],
      "confidence": "high",
      "alternatives": ["amortized_cost — rejected, design says 'spend' not 'amortized'"] },

    { "region_id": "r05_spend_trend", "state": "bound", "dataset_id": 42,
      "dimensions": ["provider_name"], "measures": ["total_cost"],
      "time_column": "usage_date", "time_grain": "P1M", "filters": [],
      "confidence": "high" },

    { "region_id": "r00_filter_bar", "state": "bound", "dataset_id": 42,
      "dimensions": ["provider_name"], "measures": [], "confidence": "high" }
  ],
  "questions": [],
  "datasets_used": [{ "id": 42, "name": "cloud_cost_daily",
                      "region_ids": ["r00_filter_bar","r01_aws_spend","r05_spend_trend","r06_service_tabs"] }]
}
```

Had the design shown a forecast card with no projected-cost column anywhere, this returns `status: "needs_input"` with one batched question and the run halts here — nothing is created.

## Stage C — resolve

Context: A + B + viz-type **summaries** + existing-chart index. No full control schemas.

```json
{
  "status": "ready",
  "design_system": {
    "palette": ["#1FA8C9","#454E7C","#5AC189"],
    "color_scheme": "supersetColors",
    "currency": {"symbol":"$","format":"SMART_NUMBER"},
    "number_formats": {"money":"$,.2f","percent":".1%","count":",d"},
    "date_format": "%b %Y", "default_time_grain": "P1M", "row_limit": 1000,
    "legend": {"show": true, "position": "top"},
    "naming_convention": "Cloud Spend — <Metric> by <Dimension>",
    "show_values": false
  },
  "decisions": [
    { "region_id":"r00_filter_bar","ref":null,"decision":"native_filter","viz_type":null,
      "rationale":"sits in a dedicated top bar, not in the grid" },
    { "region_id":"r01_aws_spend","ref":"c1","decision":"configure","viz_type":"custom_kpi_card",
      "slice_name":"Cloud Spend — AWS",
      "rationale":"big number + MoM delta + sparkline is exactly this plugin's shape",
      "fidelity_loss":null,"confidence":"high" },
    { "region_id":"r05_spend_trend","ref":"c5","decision":"reuse","existing_chart_id":318,
      "viz_type":"echarts_timeseries_line",
      "rationale":"chart 318 already renders monthly total_cost by provider",
      "fidelity_loss":"existing legend is bottom; design shows top","confidence":"high" },
    { "region_id":"r06_service_tabs","ref":"c6","decision":"wrap","viz_type":"custom_wrapper",
      "children":["c7","c8","c9"],
      "rationale":"one card, three charts behind tabs","confidence":"medium" }
  ],
  "native_filters": [
    { "name":"Provider","filterType":"filter_select","region_id":"r00_filter_bar","scope":"all" }
  ],
  "counts": {"reuse":1,"configure":6,"wrap":1,"new_plugin":0,"native_filter":1,"drop":0},
  "summary": "1 reused, 6 configured, 1 wrapped, 0 new plugins."
}
```

`new_plugin: 0` is the healthy outcome. `decisions` is ordered so `c7`–`c9` precede their `c6` parent.

## Stage D — configure (×N, parallel)

One worker per chart. Each holds exactly one control schema (~3k tokens) instead of all 72 (~140k).

```json
{
  "ref": "c1", "region_id": "r01_aws_spend",
  "request": { "method":"POST", "path":"/api/v1/chart/", "body": {
    "slice_name": "Cloud Spend — AWS",
    "viz_type": "custom_kpi_card",
    "datasource_id": 42, "datasource_type": "table",
    "params": "{\"metric\":\"total_cost\",\"provider_column\":\"provider_name\",\"time_column\":\"usage_date\",\"time_grain_sqla\":\"P1M\",\"adhoc_filters\":[{\"expressionType\":\"SIMPLE\",\"subject\":\"provider_name\",\"operator\":\"==\",\"comparator\":\"AWS\",\"clause\":\"WHERE\"}],\"y_axis_format\":\"$,.2f\",\"row_limit\":1000,\"time_range\":\"No filter\"}",
    "query_context": null }},
  "params_decoded": {
    "metric": "total_cost", "provider_column": "provider_name",
    "time_column": "usage_date", "time_grain_sqla": "P1M",
    "adhoc_filters": [{"expressionType":"SIMPLE","subject":"provider_name","operator":"==","comparator":"AWS","clause":"WHERE"}],
    "y_axis_format": "$,.2f", "row_limit": 1000, "time_range": "No filter"
  },
  "unmapped": [],
  "confidence": "high"
}
```

The wrapper parent `c6` references its children as placeholders:

```json
{ "ref":"c6", "params_decoded": { "tabs":[
    {"label":"Compute","chartId":"__REF__:c7"},
    {"label":"Storage","chartId":"__REF__:c8"},
    {"label":"Network","chartId":"__REF__:c9"}]}}
```

## Stage E — layout

Context: bboxes + refs. No datasets, no params, no image.

```json
{
  "status": "ok",
  "position_json": {
    "DASHBOARD_VERSION_KEY": "v2",
    "ROOT_ID": {"type":"ROOT","id":"ROOT_ID","children":["GRID_ID"]},
    "GRID_ID": {"type":"GRID","id":"GRID_ID","children":["ROW-1","ROW-2","ROW-3"],"parents":["ROOT_ID"]},
    "ROW-1": {"type":"ROW","id":"ROW-1","children":["CHART-1","CHART-2","CHART-3","CHART-4"],
              "parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}},
    "CHART-1": {"type":"CHART","id":"CHART-1","children":[],
                "parents":["ROOT_ID","GRID_ID","ROW-1"],
                "meta":{"chartId":"__REF__:c1","sliceName":"Cloud Spend — AWS",
                        "uuid":"7c1f...","width":3,"height":50}},
    "ROW-2": {"type":"ROW","id":"ROW-2","children":["CHART-5","CHART-6"],
              "parents":["ROOT_ID","GRID_ID"],"meta":{"background":"BACKGROUND_TRANSPARENT"}},
    "CHART-5": {"type":"CHART","id":"CHART-5","children":[],
                "parents":["ROOT_ID","GRID_ID","ROW-2"],
                "meta":{"chartId":"__REF__:c5","sliceName":"Spend over time",
                        "uuid":"9a2b...","width":7,"height":70}},
    "CHART-6": {"type":"CHART","id":"CHART-6","children":[],
                "parents":["ROOT_ID","GRID_ID","ROW-2"],
                "meta":{"chartId":"__REF__:c6","sliceName":"By service",
                        "uuid":"3d4e...","width":4,"height":70}}
  },
  "adjustments": [
    {"row_id":"ROW-2","issue":"900px + 476px of 1440px rounded to 8 + 4 = 12, but design gutter implied 7.5 + 4",
     "resolution":"CHART-5 8->7, row now sums to 11; 1 column of slack left at the right edge"}
  ],
  "unplaced": []
}
```

Four KPI tiles at `width: 3` sum to exactly 12. `adjustments` is the honest record of where the grid could not match the pixels — this is what a reviewer checks against the design.

## Apply

Deterministic Python. No LLM.

1. Validate the whole plan server-side — rejected whole if anything fails
2. `CreateChartCommand` ×7, children (`c7`–`c9`) before parent (`c6`); `c5` skipped, it's a reuse
3. Resolve `"__REF__:c1"` → `1042` throughout `position_json` and the wrapper's `params`
4. `CreateDashboardCommand`, then `UpdateDashboardCommand` with `position_json` + `json_metadata`
5. Native filter `Provider` written into `json_metadata.native_filter_configuration`, scoped to the resolved chart ids
6. Verify every chart builds a query context without error

Result:

```json
{
  "dashboard_id": 77,
  "url": "/superset/dashboard/77/",
  "published": false,
  "charts_created": 7,
  "charts_reused": 1,
  "new_plugins": 0,
  "adjustments": [{"row_id":"ROW-2","resolution":"CHART-5 8->7"}],
  "fidelity_notes": [{"region_id":"r05_spend_trend","note":"reused chart 318 has legend at bottom; design shows top"}]
}
```

The dashboard lands unpublished and owned by the requester, so nobody else sees it until it's reviewed.
