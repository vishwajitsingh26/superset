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
import { ExtraFormData } from "../adapters/supersetAdapter";
import { WrapperFilter, WrapperFilterValues } from "../types";

const asArray = (value: string | string[] | null | undefined): string[] => {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
};

// Pure transformation of the wrapper's own filter selections into the
// `extra_form_data` shape Superset merges into a hosted chart's query. Kept
// pure (no Redux, no chart id) so `TabContent` can call it once per render
// without worrying about when it runs.
export function wrapperFilterValuesAsExtraFormData(
  filters: WrapperFilter[],
  values: WrapperFilterValues,
): ExtraFormData {
  const filterClauses: NonNullable<ExtraFormData["filters"]> = [];

  filters.forEach((filter) => {
    // A filter with no column chosen yet cannot constrain anything --
    // treating it as "match everything" rather than erroring keeps a
    // half-configured wrapper renderable while it is being edited.
    if (!filter.column) return;
    const selected = asArray(values[filter.id]);
    if (selected.length === 0) return;
    filterClauses.push({ col: filter.column, op: "IN", val: selected });
  });

  return filterClauses.length > 0 ? { filters: filterClauses } : {};
}

// Merges a wrapper-derived `extraFormData` on top of whatever the dashboard
// (native filters, cross-filters) already contributed to a hosted chart's
// query. A shallow merge would drop one side's `filters` array entirely,
// since both sides use the same key -- concatenating that array is what
// keeps both sets of clauses.
export function mergeExtraFormData(
  base: ExtraFormData | undefined,
  wrapper: ExtraFormData,
): ExtraFormData {
  const merged: ExtraFormData = { ...(base ?? {}), ...wrapper };
  const baseFilters = base?.filters ?? [];
  const wrapperFilters = wrapper.filters ?? [];
  if (baseFilters.length > 0 || wrapperFilters.length > 0) {
    merged.filters = [...baseFilters, ...wrapperFilters];
  }
  return merged;
}
