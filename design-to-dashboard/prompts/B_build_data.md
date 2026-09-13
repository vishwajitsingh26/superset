# Stage B, part 2 — Build the data

**Input:** a data spec written from the design, the regions it binds, the databases you can reach, and the dataset names already taken.
**Tools:** `create_fact_table`, `execute_sql`, `create_virtual_dataset`.
**Output:** `BindingSet`.

## Your job

Build exactly what the data spec describes, check that it works, and report the
ids. The spec was written by the step that saw the design. You do not have the
picture and you do not redesign: a table, column or view in the spec is what
this dashboard needs.

Change something only when building it fails. Change the least that makes it
work, and say what you changed in `notes`.

## Step 1 — Create every table

1. **Pick the database.** If one is listed, use it. If several are, use the one
   that already holds names in `dataset_names_already_taken`; otherwise the
   first.
2. **`create_fact_table` for every table in `fact_tables`**, sending its `name`,
   `columns` and `rows` exactly as the spec gives them. Send them all in one
   reply: they run in parallel.
3. **Check each response** — its `row_count` and `columns` come from the
   warehouse. If they disagree with the spec, the table is not what the spec
   describes; fix it and create it again before building anything on top.

## Step 2 — Check, then save every view

1. **Run every view's SQL with `execute_sql`** first, all in one reply. The
   tables exist by now, so this is a real check — a view that does not run is
   a chart that renders an error, and you are the last step that can catch it.
2. **Save each one that runs** with `create_virtual_dataset`, under the spec's
   name.
3. **Fix any that fail.** Read the error, correct the SQL, and keep the columns
   it returns — a view whose columns change breaks every binding that reads
   them. Run the corrected SQL before saving it.

## Step 3 — Report the bindings

Copy every binding from the spec, replacing its `source` name with the
`dataset_id` of that table or view. `shared_no_query` is the shared dataset:
its id is also `shared_dataset_id`.

## Rules

- **Never name a column you did not create.** Everything you bind must appear
  in a `create_fact_table` response or a view you saved.
- **Never use a name in `dataset_names_already_taken`** other than
  `shared_no_query`. The spec has already been checked for this; if a save
  still reports a name as taken, add a short suffix and use the new name
  everywhere that view is read.
- **One dataset may serve many regions.**
- **Nothing blocks.** If something cannot be built, bind its regions to the
  shared dataset and say why in `notes` rather than stopping the run.

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
  "notes": "what you changed from the spec, and why",
  "tool_calls": 0
}
```

Every region in your input appears exactly once in `bindings`.
