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
import {
  ChartProps,
  DataRecord,
  QueryFormColumn,
  SetDataMaskHook,
  ensureIsArray,
  getColumnLabel,
  t,
} from '../adapters/supersetAdapter';
import { SelectFilterFormData, SelectFilterProps } from '../types';

type FilterStateShape = { value?: string[] | string | null };
type QueryResultShape = { data?: DataRecord[]; error?: string | null };

function toOptions(rows: DataRecord[], column: string): string[] {
  const seen = new Set<string>();
  rows.forEach(row => {
    const raw = row[column];
    if (raw !== null && raw !== undefined && raw !== '') {
      seen.add(String(raw));
    }
  });
  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}

export default function transformProps(
  chartProps: ChartProps<SelectFilterFormData>,
): SelectFilterProps {
  const { width, height, formData, queriesData, hooks, filterState } =
    chartProps as ChartProps<SelectFilterFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: FilterStateShape;
    };

  const column = ensureIsArray<QueryFormColumn>(formData.groupby)[0];
  const columnLabel = column ? getColumnLabel(column) : '';

  const result = (queriesData?.[0] ?? {}) as QueryResultShape;
  const rows = (result.data ?? []) as DataRecord[];
  const options = columnLabel ? toOptions(rows, columnLabel) : [];

  const selectedValues = ensureIsArray<string>(
    (filterState?.value ?? []) as string | string[],
  ).map(String);

  return {
    width,
    height,
    columnLabel,
    filterLabel: formData.filterLabel ?? t('Filter'),
    allLabel: formData.allLabel ?? t('All'),
    multiSelect: formData.multiSelect ?? true,
    options,
    selectedValues,
    errorMessage: result.error ?? null,
    isLoading: !result.data && !result.error,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
