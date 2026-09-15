/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { buildQueryContext, AdhocMetric } from "../adapters/supersetAdapter";
import { PeriodFilterFormData } from "../types";

// Read by `transformProps` to pull the two bounds back out of `queriesData`
// by name; exported rather than repeated so the query and the read of it
// cannot drift apart.
export const MIN_PERIOD_LABEL = "min_period";
export const MAX_PERIOD_LABEL = "max_period";

// Two SQL-expression metrics, not a groupby: a MIN/MAX pair only ever needs
// the single row SQL already collapses it to. `hasCustomLabel` is what makes
// the response column come back spelled `min_period`/`max_period` rather than
// the auto-generated expression text, which is what `transformProps` reads.
function boundsMetrics(dateColumn: string): AdhocMetric[] {
  return [
    {
      expressionType: "SQL",
      sqlExpression: `MIN(${dateColumn})`,
      label: MIN_PERIOD_LABEL,
      hasCustomLabel: true,
    },
    {
      expressionType: "SQL",
      sqlExpression: `MAX(${dateColumn})`,
      label: MAX_PERIOD_LABEL,
      hasCustomLabel: true,
    },
  ];
}

// Anchors the month dropdown to what the data actually contains, not to
// today's date: a dropdown built from `Date.now()` offers a month the
// dataset has no rows for, and every chart the selection drives renders
// empty. `row_limit: 1` and `time_range: "No filter"` are deliberate — the
// bounds query must see every row the dataset holds, not the slice the
// dashboard's own date range would otherwise apply to it.
export default function buildQuery(formData: PeriodFilterFormData) {
  const raw = formData as unknown as Record<string, unknown>;
  const dateColumn = raw.date_column as string | undefined;

  return buildQueryContext(formData, (baseQueryObject) => [
    {
      ...baseQueryObject,
      groupby: [],
      columns: [],
      metrics: dateColumn ? boundsMetrics(dateColumn) : [],
      orderby: [],
      row_limit: 1,
      time_range: "No filter",
      filters: [],
    },
  ]);
}
