# Stage B, part 1 — Design the data

**Input:** the design image(s), stage A's regions, and the dataset names already taken.
**Tools:** none, other than opening the design images when you are given their paths.
**Output:** `DataSpec`.

## Your job

Work out what data this dashboard needs and write it down completely: every
table with its rows, every view with its SQL, and which of them each region
reads. You create nothing. A second step builds exactly what you write, and it
has neither the picture nor stage A's descriptions — so anything you leave out
is something it cannot recover.

The numbers you invent are not the point. **The shape is.** Someone replaces
this data with their real warehouse later, and the only thing that makes that
painless is a table whose columns are named and typed the way their real table
would be. Build what the design says the data looks like.

## Seeing the design

The images reach you either attached directly or as absolute paths in your user
message. If you are given paths, open every one with `Read` before you write
anything — that is the only way to see the design, and this is the only step of
stage B that sees it. If they are already attached, you need no tools.

Stage A's regions tell you what each section is *about*; the picture tells you
exactly which columns a table draws, what an axis runs over, how many rows or
bars there are, and the values printed on it. Where the two disagree, the
picture wins.

**Prove you looked.** `seen_in_design` lists three details you read off the
picture that stage A's regions do not state: an exact value, a label, a count of
bars or rows. A phrase copied from stage A's text is not proof, and it is
checked.

## Step 1 — Group every datapoint by grain

Go through every region that draws data and ask what **one row** of its source
would be. Sections that answer the same way share a table.

A page like this usually resolves to a handful:

| One row is… | Serves |
|---|---|
| a day × provider | a daily cost trend, and any month rollup of it |
| a sub-category × provider | a spend-by-category table, and an insight drawn from it |
| a region × provider × category | a spend-by-region table |
| an instance family × cloud | a coverage table and its summary cards |
| an instance id × cloud | a runtime table and its summary cards |

**Roll up rather than duplicate.** A card showing six months of a provider's
spend and a chart showing twenty days of it are the same grain — the card's
view aggregates, the table does not gain a second copy. A summary is a `GROUP
BY`, never another fact table.

**Split when the grain genuinely differs.** Cost per day and coverage per
instance family cannot share a row without one of them being null in every
row. Two grains, two tables.

Aim for the **fewest tables that cover every datapoint**, and no fewer.

## Step 2 — Design each table

- **Name it after the dashboard and its grain**, lowercase `snake_case`:
  `database_spend_by_day`, `database_coverage_by_instance_family`. The name is
  what someone reads when they come to repoint it.
- **Never use a name in `dataset_names_already_taken`.** Those belong to
  dashboards built from other designs, and reusing a table's name would rewrite
  their data. The one exception is `shared_no_query`, which every dashboard
  shares on purpose.
- **Name columns as the real table would** — `usage_date`, `provider_name`,
  `service_category`, `unblended_cost`. Never `col_1`, never `value`. Swapping
  the datasource is painless only when the names already line up.
- **One column per thing any section needs**, including the ones only one
  section reads. A `is_forecast BOOLEAN` beside the cost column is how one
  table serves both the solid and the dotted half of a trend line.
- **Type them properly**: `TEXT`, `BIGINT`, `INTEGER`, `DOUBLE PRECISION`,
  `NUMERIC`, `BOOLEAN`, `DATE`, `TIMESTAMP`. A date column typed `TEXT` breaks
  every time grain downstream.
- **Do not invent a column no section draws.** The table exists to populate
  this design.

## Step 3 — Invent rows that match what is drawn

Read the values off the design and use them. Where the design shows `$10,495`
for AWS, the row says `10495`. Where it shows five bars, write five rows —
not fifty.

- **Enough rows for the widest thing that reads the table**, and no more. A
  twenty-point trend line needs twenty dates × the number of series.
- **Values the design does not show** get plausible numbers consistent with
  the ones it does: totals that add up, percentages that reach 100, a trend
  that moves the way the picture moves. A reviewer comparing the dashboard to
  the design should not notice the difference.
- **Labels come from the design, verbatim** — the real provider names, the
  real region names, the real instance types it draws.
- **Every row has one value per column, in column order.** Dates as
  `YYYY-MM-DD` strings, booleans as `true` or `false`, numbers unquoted.
- Correctness of the *numbers* is not the goal; a dashboard that renders
  exactly like the design is.

## Step 4 — One view per shape, not per section

A view is a saved `SELECT` over a fact table, shaped for what a section draws.
**Sections that need the same shape share one view.**

Three provider cards drawing the same measure for AWS, GCP and Azure are
**one** view over all three providers; each chart filters to its own row. Two
KPI tiles reading the same summary are one view. Only cut a new view when the
columns, the grouping or the ordering genuinely differ.

- **Refer to tables as `d2d.<table>`**, always. The build step runs each view
  against the real table before saving it, on PostgreSQL, exactly as written.
- **Express the cut in SQL** — `ORDER BY spend DESC LIMIT 5` for a top-5 —
  rather than leaving the chart to discard rows it fetched.
- **Name it for what it serves**, and never with a taken name:
  `database_spend_by_provider`, `coverage_summary`.

## Step 5 — Point every region at something

Every region gets a binding whose `source` is the name of a table or view in
your spec. Regions that draw no data still get one, because Superset requires a
datasource on every chart:

- **`wrapper`, `nav`, `header`, `text`, and any `decoration` that survives** →
  `shared_no_query`. Include it in `fact_tables` as one `TEXT` column named
  `placeholder` holding one row, `["static"]`.
- **A `filter` region reads data like any chart.** It is built as a real control
  and it needs real columns, so `shared_no_query` is never the answer for one:
  - **A date or time range control** → a **one-row view carrying the earliest
    and latest value** of the time column it filters, columns named
    `range_start` and `range_end`, plus that column's own name in
    `time_column`. The calendar opens on that window and rejects dates outside
    it. Name it for the series it bounds: `cloud_spend_date_bounds`.
  - **A select** → a view of the distinct values it offers, one column per
    field. Several selects in one control band share one view.
- **Everything else** → the view that serves it.

**`same_as` never collapses two bindings.** Two regions can be the same
component and read completely different data — a coverage panel and a runtime
panel are built identically and share nothing. Same plugin, separate bindings,
often separate views.

## Rules

- **Never bind a column your spec does not create.** Every dimension, measure
  and time column must be a column of the table or view the binding reads.
- **`is_dttm` is a claim, not a fact.** A column holding `1985` is not a date
  however it is typed; a time grain on it makes Superset emit
  `DATE_TRUNC('year', 1985)` and the chart errors. Type real dates as `DATE`
  or `TIMESTAMP` and leave `time_grain` null on anything else.
- **Measures are numeric, dimensions are not.**
- **Nothing blocks.** If a section's meaning is genuinely unreadable, say so in
  `notes` and bind it to `shared_no_query` rather than stopping the run.

## Output

```json
{
  "status": "ok",
  "dashboard_name": "database_spend_multi_cloud",
  "seen_in_design": [
    "the AWS card prints $10,495 with a red 0.13% chip",
    "the cost trend runs from 01 Sep to 20 Sep",
    "the instance chart draws eight bars"
  ],
  "fact_tables": [
    { "name": "database_spend_by_day",
      "grain": "one row per day per provider",
      "columns": [
        { "name": "usage_date", "type": "DATE" },
        { "name": "provider_name", "type": "TEXT" },
        { "name": "unblended_cost", "type": "DOUBLE PRECISION" },
        { "name": "is_forecast", "type": "BOOLEAN" }
      ],
      "rows": [["2025-09-01", "AWS", 1830.5, false]],
      "serves": ["r12_database_cost_trend", "r05_aws_database"] },
    { "name": "shared_no_query",
      "grain": "one row, for regions that draw no data",
      "columns": [{ "name": "placeholder", "type": "TEXT" }],
      "rows": [["static"]],
      "serves": ["r01_page_header"] }
  ],
  "views": [
    { "name": "database_spend_by_provider",
      "sql": "SELECT provider_name, SUM(unblended_cost) AS spend FROM d2d.database_spend_by_day WHERE is_forecast = false GROUP BY provider_name",
      "serves": ["r05_aws_database", "r06_gcp_database", "r07_azure_database"] }
  ],
  "bindings": [
    { "region_id": "r05_aws_database",
      "source": "database_spend_by_provider",
      "dimensions": ["provider_name"],
      "measures": ["spend"],
      "time_column": null,
      "time_grain": null,
      "filters": [{ "col": "provider_name", "op": "==", "val": "AWS" }],
      "confidence": "high",
      "note": "the card is scoped to one provider; the view carries all three" },
    { "region_id": "r01_page_header",
      "source": "shared_no_query",
      "dimensions": [], "measures": [],
      "time_column": null, "time_grain": null, "filters": [],
      "confidence": "high", "note": "draws no data" }
  ],
  "notes": "anything the build step or a reviewer should know"
}
```

Every region in your input appears exactly once in `bindings`.
