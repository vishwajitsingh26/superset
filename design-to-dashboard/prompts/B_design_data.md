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
- **A column that means a percentage is stored as a fraction of 1** —
  `-0.152` for `-15.2%`, never `-15.2`. The number-format stage C picks for a
  percent column multiplies by 100 to draw the `%` sign, the same way
  spreadsheet software does; a column already scaled to whole percentage
  points is drawn 100× too large.
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
- **A view that carries a real date or time value always exposes it as
  `d2d_date`** — `SELECT usage_date AS d2d_date, ...` — whatever the
  underlying fact table calls its own column. One fixed name means a later
  stage never has to look up what a specific view happens to call its time
  column: it is always this one. Only the two-column range-bounds shape below
  is exempt, because it has no single time column to name this way.

## Step 5 — Point every region at something

Every region gets a binding whose `source` is the name of a table or view in
your spec. Regions that draw no data still get one, because Superset requires a
datasource on every chart:

- **`wrapper`, `nav`, `header`, `text`, and any `decoration` that survives** →
  `shared_no_query` — **unless the region's own `wrapper_reads_data` is
  `true`.** That field is set only when a person, at the review gate between
  stage A and this one, was shown the region and said it genuinely prints a
  real value (a header total, a banner stat) — not a guess this stage makes
  itself. Where it is `true`, bind the region to a real source the way any
  chart would, and read `data_notes` for what the value actually is (often a
  sum or share of sibling regions' own figures — reconcile against those,
  don't invent a second number). Where it is absent or `false`, the plain
  role-based rule above still applies.
- **A `filter` region reads data like any chart.** It is built as a real control
  and it needs real columns, so `shared_no_query` is never the answer for one.
  If the region carries `filter_kind` from the gate, it names the shape
  directly — build to it rather than re-deriving it from `observed`:
  - **`date_range`** (or, absent a `filter_kind`, anything read as a date or
    time range control) → a **one-row view carrying the earliest and latest
    value** of the time column it filters, columns named `range_start` and
    `range_end`. **Set `time_column` to `null` on this binding** — the view
    has no single time column to name, only the two bounds, and a downstream
    stage that finds a name there and queries it as a literal column on this
    view is querying a column that does not exist. Name the view for the
    series it bounds: `cloud_spend_date_bounds`.
  - **`select`** (or, absent a `filter_kind`, anything read as a select) → a
    view of the distinct values it offers, one column per field. Several
    selects in one control band share one view.
  - **`search`** → a view of the column(s) it searches over; no distinct-value
    narrowing, the control reads free text.
  - **`other`**, or a `filter_kind` you cannot map to one of the above → fall
    back to your own reading of `observed`, same as when the field is absent.
- **Any region whose `has_embedded_series` is `true`, or whose
  `unusual_treatment` names a sparkline, trendline, or other embedded
  mini-series — not just a chart whose whole purpose is a trend — needs a
  real temporal column bound, even where its headline value would not
  otherwise require one.** `has_embedded_series` is decisive where it is set
  at all (`true` or `false`, from the gate) — do not fall back to reading
  `unusual_treatment` yourself when the field is present, only when it is
  absent entirely. A KPI card is drawn once for its value and again, silently,
  for the line beside it: a binding with no time column gives that second
  drawing nothing to run on, and the card ships with an empty sparkline the
  design never shows empty. Bind such a region to a view whose time column is
  `d2d_date`, wide enough to cover the span the design draws.
- **Everything else** → the view that serves it.

**`same_as` never collapses two bindings** on its own — two regions can be the
same component and read completely different data, a coverage panel and a
runtime panel are built identically and share nothing. **Where a `same_as`
group's first region carries `data_notes` from the gate, follow it instead of
guessing:** it may say the group genuinely shares one table (bind every member
to the same source, filtered differently) or that each member is separate
(the default). This is the one place `data_notes` is expected on a region that
is not itself `wrapper_reads_data` — it is answering "one table or several",
not "does this read data at all".

`plugin_choice` (stock vs. custom) is not yours to read or act on. It decides
how stage C builds the chart, not what data it reads; every binding is written
exactly the same regardless of what it says.

## Rules

- **Never bind a column your spec does not create.** Every dimension, measure
  and time column must be a column of the table or view the binding reads.
- **A binding's `time_column` names a column of the view it points at, never
  the fact table underneath it.** Since every view that carries a real date
  exposes it as `d2d_date` (Step 4), `time_column` is `"d2d_date"` whenever a
  binding is temporal at all, and `null` otherwise — never the fact table's
  own column name, which a view built on top of it may alias away, group by,
  or not expose at all. A `time_column` naming something the bound view does
  not select is a chart or filter that fails outright, with no warning until
  it is queried.
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
