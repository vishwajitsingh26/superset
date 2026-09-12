# Stage B — Build the data

**Input:** the design image(s), and stage A's regions.
**Tools:** `list_databases`, `create_fact_table`, `execute_sql`, `create_virtual_dataset`.
**Output:** `BindingSet`.

## Your job

Work out what data this dashboard needs, build it, and point every region at
it. You do not search for existing datasets — you design the tables the design
implies, create them, and prove they work.

The numbers you invent are not the point. **The shape is.** Someone replaces
this data with their real warehouse later, and the only thing that makes that
painless is a table whose columns are named and typed the way their real table
would be. Build what the design says the data looks like.

## You can see the design

The image is attached. Read it alongside stage A's regions — A's words tell you
what each section is *about*, and the picture tells you exactly which columns a
table draws, what the axis runs over, and how many rows or bars there are.
Where the two disagree, the image wins.

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
- Correctness of the *numbers* is not the goal; a dashboard that renders
  exactly like the design is.

## Step 4 — Create, and check it worked

1. `list_databases` once, to get the id everything else needs.
2. `create_fact_table` per table. The response reads the table back from the
   warehouse — **check the `row_count` and `columns` it returns against what
   you sent.** If they disagree, the table is not what you think it is; fix it
   before building anything on top.
3. Re-running is safe: a table of the same name is replaced, and its dataset
   keeps its id.

## Step 5 — One view per shape, not per section

A view is a saved `SELECT` over a fact table, shaped for what a section draws.
**Sections that need the same shape share one view.**

Three provider cards drawing the same measure for AWS, GCP and Azure are
**one** view over all three providers; each chart filters to its own row. Two
KPI tiles reading the same summary are one view. Only cut a new view when the
columns, the grouping or the ordering genuinely differ.

For each view:

1. Write the `SELECT`.
2. **Run it with `execute_sql` first.** The table exists by now, so this is a
   real check — a view that does not run is a chart that renders an error, and
   you are the last stage that can catch it.
3. `create_virtual_dataset` to save it, named for what it serves:
   `database_spend_by_provider`, `coverage_summary`.

Express the cut in SQL — `ORDER BY spend DESC LIMIT 5` for a top-5 — rather
than leaving the chart to discard rows it fetched.

## Step 6 — Point every region at something

Every region gets a `Binding`. Regions that draw no data still get one, because
Superset requires a datasource on every chart:

- **`wrapper`, `nav`, `header`, `text`, and any `decoration` that survives** →
  the **shared dataset**. It is one row and one column and it exists for
  exactly this. Create it the same way as any other table, named
  `shared_no_query`; if it already exists you get its id back.
- **A `filter` region reads data like any chart.** It is built as a real control
  and it needs real columns, so the shared dataset is never the answer for one:
  - **A date or time range control** → a **one-row view carrying the earliest
    and latest value** of the time column it filters, columns named
    `range_start` and `range_end`, plus that column's own name in
    `time_column`. The calendar opens on that window and rejects dates outside
    it, so a control bound to the shared dataset is a calendar with no range at
    all. Name it for the series it bounds: `cloud_spend_date_bounds`.
  - **A select** → a view of the distinct values it offers, one column per
    field. Several selects in one control band share one view.
- **Everything else** → the view that serves it.

**`same_as` never collapses two bindings.** Two regions can be the same
component and read completely different data — a coverage panel and a runtime
panel are built identically and share nothing. Same plugin, separate bindings,
often separate views.

## Rules

- **Never name a column you did not create.** Everything you bind must appear
  in a `create_fact_table` response or a view you wrote.
- **`is_dttm` is a claim, not a fact.** A column holding `1985` is not a date
  however it is typed; a time grain on it makes Superset emit
  `DATE_TRUNC('year', 1985)` and the chart errors. Type real dates as `DATE`
  or `TIMESTAMP` and leave `time_grain` null on anything else.
- **Measures are numeric, dimensions are not.** Report a mismatch; never coerce.
- **One dataset may serve many regions** — that is the point of step 5.
- **Nothing blocks.** You are building the data, so there is no section you
  cannot serve. If a section's meaning is genuinely unreadable, say so in
  `notes` and bind it to the shared dataset rather than stopping the run.

## Output

```json
{
  "status": "ok",
  "dashboard_name": "database_spend_multi_cloud",
  "fact_tables": [
    { "name": "database_spend_by_day",
      "dataset_id": 24,
      "grain": "one row per day per provider",
      "columns": ["usage_date", "provider_name", "unblended_cost", "is_forecast"],
      "row_count": 60,
      "serves": ["r12_database_cost_trend", "r05_aws_database"] }
  ],
  "views": [
    { "name": "database_spend_by_provider",
      "dataset_id": 31,
      "sql": "SELECT provider_name, SUM(unblended_cost) AS spend FROM d2d.database_spend_by_day WHERE is_forecast = false GROUP BY provider_name",
      "validated": true,
      "serves": ["r05_aws_database", "r06_gcp_database", "r07_azure_database"] }
  ],
  "bindings": [
    { "region_id": "r05_aws_database",
      "dataset_id": 31,
      "dimensions": ["provider_name"],
      "measures": ["spend"],
      "time_column": null,
      "time_grain": null,
      "filters": [{ "col": "provider_name", "op": "==", "val": "AWS" }],
      "confidence": "high",
      "note": "the card is scoped to one provider; the view carries all three" }
  ],
  "shared_dataset_id": 23,
  "notes": "anything a reviewer should know about the data that was built",
  "tool_calls": 0
}
```

Every region in your input appears exactly once in `bindings`.
